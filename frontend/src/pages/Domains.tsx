import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '../api'
import { MetricChart } from '../components/MetricChart'
import { EmptyState, PageHeader } from '../components/Common'
import { useJobs } from '../jobs'
import type { Dashboard } from '../types'

const configs = {
  training: { eyebrow: 'Movement and load', title: 'Training', description: 'Activities, intensity, energy and training load.', chartIds: ['steps', 'calories', 'intensity-minutes', 'training-duration', 'training-load'] },
  recovery: { eyebrow: 'Sleep and physiology', title: 'Recovery', description: 'Sleep, stress, Body Battery, HRV and respiratory signals.', chartIds: ['stress-battery', 'sleep-duration', 'sleep-score', 'hrv', 'heart-rate', 'spo2', 'respiration'] },
} as const

export function DomainPage({ domain }: { domain: keyof typeof configs }) {
  const [period, setPeriod] = useState<1 | 7 | 30>(7)
  const config = configs[domain]; const { data } = useQuery({ queryKey: ['dashboard', period], queryFn: () => api<Dashboard>(`/dashboard?period_days=${period}`) }); const { start, busy } = useJobs(); const charts = data?.report?.charts.charts.filter((item) => config.chartIds.includes(item.id as never)) ?? []
  return <><PageHeader eyebrow={config.eyebrow} title={config.title} description={config.description} actions={<><div className="segmented" aria-label="Period">{([1, 7, 30] as const).map((days) => <button key={days} className={period === days ? 'active' : ''} aria-pressed={period === days} onClick={() => setPeriod(days)}>{days === 1 ? 'Today' : `${days} days`}</button>)}</div><button className="button" disabled={busy} onClick={() => void start('/dashboard/refresh', { period_days: period })}>Refresh snapshot</button></>} />{charts.length ? <section className="chart-grid">{charts.map((chart) => <article className="panel" key={chart.id}><div className="panel__head"><h2>{chart.title}</h2><span className="source-chip">Garmin</span></div><MetricChart chart={chart} /></article>)}</section> : <EmptyState title={`No ${domain} snapshot yet`} description="Load the selected period to see these read-only Garmin signals." action={<button className="button button--primary" disabled={busy} onClick={() => void start('/dashboard/refresh', { period_days: period })}>Load {period}-day snapshot</button>} />}{domain === 'training' && data?.report?.activities.length ? <section className="panel section-gap"><div className="panel__head"><h2>Activities</h2><span>{data.report.activities.length} records</span></div><div className="activity-table table-scroll"><table><thead><tr><th>Activity</th><th>Start</th><th>Duration</th><th>Distance</th><th>Heart rate</th><th></th></tr></thead><tbody>{data.report.activities.map((item) => <tr key={String(item.id ?? item.measured_at)}><td><b>{String(item.name)}</b><small>{String(item.type)}</small></td><td>{new Date(String(item.measured_at)).toLocaleString()}</td><td>{Math.round(Number(item.duration_minutes))} min</td><td>{item.distance_km ? `${Number(item.distance_km).toFixed(1)} km` : '—'}</td><td>{item.average_hr ? `${Math.round(Number(item.average_hr))} bpm` : '—'}</td><td>{item.id && <a className="text-link" href={`https://connect.garmin.com/modern/activity/${item.id}`} target="_blank" rel="noreferrer">Garmin</a>}</td></tr>)}</tbody></table></div></section> : null}</>
}
