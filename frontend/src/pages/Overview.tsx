import { useMemo, useState } from 'react'
import { DndContext, KeyboardSensor, PointerSensor, closestCenter, useSensor, useSensors, type DragEndEvent } from '@dnd-kit/core'
import { SortableContext, arrayMove, sortableKeyboardCoordinates, useSortable, verticalListSortingStrategy } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { Activity, BatteryCharging, BedDouble, Gauge, GripVertical, HeartPulse, RefreshCw, Settings2, Sparkles, Weight } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../api'
import { MetricChart } from '../components/MetricChart'
import { EmptyState, PageHeader } from '../components/Common'
import { SegmentedControl } from '../components/UI'
import { useJobs } from '../jobs'
import type { Dashboard, WeeklyReport } from '../types'

const defaultOrder = ['sleep', 'battery', 'heart', 'stress', 'vo2max']

/** Preserve a user's card order while making newly introduced cards visible once. */
function dashboardOrder(value: string | null): string[] {
  try {
    const saved = JSON.parse(value ?? 'null')
    if (!Array.isArray(saved)) return defaultOrder
    const known = saved.filter((item): item is string => typeof item === 'string' && defaultOrder.includes(item))
    return [...known, ...defaultOrder.filter((item) => !known.includes(item))]
  } catch { return defaultOrder }
}

export function Overview() {
  const [period, setPeriod] = useState<1 | 7 | 30>(7)
  const { data } = useQuery({ queryKey: ['dashboard', period], queryFn: () => api<Dashboard>(`/dashboard?period_days=${period}`) })
  const { start, busy } = useJobs()
  const [customizing, setCustomizing] = useState(false)
  const [order, setOrder] = useState<string[]>(() => { try { return dashboardOrder(window.localStorage.getItem('garmin-health-sync.ui.v1.dashboard')) } catch { return defaultOrder } })
  const sensors = useSensors(useSensor(PointerSensor), useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }))
  const cards = useMemo(() => scoreCards(data?.report), [data?.report])
  const recovery = cards.battery.value
  const chart = data?.report?.charts.charts.find((item) => item.id === 'stress-battery')
  const onDragEnd = (event: DragEndEvent) => { if (!event.over || event.active.id === event.over.id) return; const next = arrayMove(order, order.indexOf(String(event.active.id)), order.indexOf(String(event.over.id))); setOrder(next); try { window.localStorage.setItem('garmin-health-sync.ui.v1.dashboard', JSON.stringify(next)) } catch { /* customization remains in this session */ } }
  return <>
    <PageHeader eyebrow={new Intl.DateTimeFormat('en', { weekday: 'long', month: 'long', day: 'numeric' }).format(new Date())} title="Today" description="Recovery first, with your current signals and a selectable read-only context." actions={<><button className="button" onClick={() => setCustomizing(!customizing)}><Settings2 />{customizing ? 'Done' : 'Customize'}</button><SegmentedControl label="Dashboard period" value={period} onChange={setPeriod} options={[{ value: 1, label: 'Today' }, { value: 7, label: '7 days' }, { value: 30, label: '30 days' }]} /><button className="button button--primary" disabled={busy} onClick={() => void start('/dashboard/refresh', { period_days: period })}><RefreshCw />Refresh</button></>} />
    <section className="atlas-hero" aria-label="Recovery summary"><div className="atlas-hero__score"><div className="recovery-ring"><strong>{recovery}</strong><span>Body Battery</span></div></div><div className="atlas-hero__detail"><span className="eyebrow">Recovery signal</span><h2>{recovery === '—' ? 'Your recovery snapshot is ready to load.' : 'Ready for the day.'}</h2><p>{recovery === '—' ? 'Load a read-only Garmin snapshot to see recovery, sleep and stress together.' : `${cards.sleep.value === '—' ? 'Sleep is not available yet.' : `Sleep score ${cards.sleep.value}.`} Stress and recovery remain available as separate source-labelled signals.`}</p><span className="atlas-hero__source">Garmin · {period === 1 ? 'today' : `${period}-day context`}</span></div></section>
    <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onDragEnd}><SortableContext items={order} strategy={verticalListSortingStrategy}><section className="score-grid section-gap">{order.map((id) => <SortableScore key={id} item={cards[id]} id={id} editing={customizing} />)}</section></SortableContext></DndContext>
    <section className="dashboard-grid">
      <article className="panel panel--wide"><div className="panel__head"><div><span className="eyebrow">{period}-day context</span><h2>Stress and Body Battery</h2></div>{data?.report && <span className="period-chip">{data.report.start_date} – {data.report.end_date}</span>}</div>{chart ? <MetricChart chart={chart} compact /> : <EmptyState title="Load this dashboard period" description="The read-only snapshot stays in memory only while the local app is running." action={<button className="button button--primary" disabled={busy} onClick={() => void start('/dashboard/refresh', { period_days: period })}>Load {period}-day snapshot</button>} />}</article>
      <article className="panel"><div className="panel__head"><div><span className="eyebrow">Today</span><h2>Measurement timeline</h2></div></div><div className="timeline">{data?.latest_body && <Timeline icon={<Weight />} title="Body composition" detail={`${data.latest_body.weight_kg.toFixed(1)} kg · ${new Date(data.latest_body.measured_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`} source="RENPHO" />}{data?.report?.activities.slice(-2).map((item) => <Timeline key={item.id ?? item.measured_at} icon={<Activity />} title={String(item.name)} detail={`${Math.round(Number(item.duration_minutes))} min`} source="Garmin" />)}{!data?.latest_body && !data?.report?.activities.length && <p className="muted">No measurements loaded yet.</p>}</div></article>
      <article className="panel panel--wide"><div className="panel__head"><div><span className="eyebrow">Evidence, not guesses</span><h2>Observed insights</h2></div><Sparkles /></div><div className="insight-list">{data?.report?.insights.slice(0, 5).map((insight, index) => <article key={`${insight.category}-${index}`}><span className={`insight-level insight-level--${insight.level}`}>{insight.category}</span><p>{insight.text}</p><small>{insight.confidence}</small></article>)}{!data?.report?.insights.length && <p className="muted">Insights appear after a weekly snapshot has enough source data.</p>}</div></article>
    </section>
  </>
}

function scoreCards(report?: WeeklyReport | null): Record<string, { label: string; value: string; detail: string; icon: any; tone: string }> {
  const latest = (chartId: string, series: string) => { const chart = report?.charts.charts.find((item) => item.id === chartId); const values = chart?.series.find((item) => item.name === series)?.values.filter((item) => item != null) ?? []; return values.at(-1) }
  const sleep = latest('sleep-score', 'Sleep score'); const battery = latest('stress-battery', 'Body Battery'); const minHr = latest('heart-rate', 'Daily minimum HR'); const stress = latest('stress-battery', 'Stress'); const vo2max = report?.vo2_max
  return {
    sleep: { label: 'Sleep', value: sleep == null ? '—' : String(Math.round(sleep)), detail: 'Latest sleep score', icon: BedDouble, tone: 'indigo' },
    battery: { label: 'Body Battery', value: battery == null ? '—' : String(Math.round(battery)), detail: 'Charged today', icon: BatteryCharging, tone: 'teal' },
    heart: { label: 'Daily minimum HR', value: minHr == null ? '—' : `${Math.round(minHr)} bpm`, detail: 'Resting HR unavailable', icon: HeartPulse, tone: 'blue' },
    stress: { label: 'Stress', value: stress == null ? '—' : String(Math.round(stress)), detail: 'Daily average', icon: Activity, tone: 'amber' },
    vo2max: { label: 'VO₂ max', value: vo2max == null ? '—' : `${vo2max.toFixed(1)} mL/kg/min`, detail: 'Garmin estimate', icon: Gauge, tone: 'blue' },
  }
}

function SortableScore({ id, item, editing }: { id: string; item: ReturnType<typeof scoreCards>[string]; editing: boolean }) { const { attributes, listeners, setNodeRef, transform, transition } = useSortable({ id, disabled: !editing }); const Icon = item.icon; return <article ref={setNodeRef} style={{ transform: CSS.Transform.toString(transform), transition }} className={`score-card score-card--${item.tone}`}><div className="score-card__top"><span>{item.label}</span>{editing ? <button className="drag-handle" aria-label={`Move ${item.label}`} {...attributes} {...listeners}><GripVertical /></button> : <Icon />}</div><strong>{item.value}</strong><small>{item.detail}</small></article> }
function Timeline({ icon, title, detail, source }: { icon: any; title: string; detail: string; source: string }) { return <div className="timeline__item"><span className="timeline__icon">{icon}</span><div><b>{title}</b><small>{detail}</small></div><span className="source-chip">{source}</span></div> }
