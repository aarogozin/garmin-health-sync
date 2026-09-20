import { BrainCircuit, Download, FileBarChart, FolderOpen, Map, RefreshCw } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import { api, download } from '../api'
import { reportDays } from '../report-period'
import { MetricChart } from '../components/MetricChart'
import { EmptyState, PageHeader } from '../components/Common'
import { useJobs } from '../jobs'
import type { Bootstrap, HealthContextMetadata, WeeklyReport } from '../types'

export function ReportsPage() {
  const { data } = useQuery({ queryKey: ['bootstrap'], queryFn: () => api<Bootstrap>('/bootstrap') })
  const { start, busy, run } = useJobs()
  const reportId = data?.latest_weekly_report_id
  const contexts = data?.latest_health_context_ids ?? {}
  return <>
    <PageHeader eyebrow="In-memory documents" title="Reports" description="Generate human-readable reports and structured, privacy-safe context for local AI tools." actions={<button className="button button--primary" disabled={busy} onClick={() => void start('/reports/weekly', {})}><RefreshCw />Generate report</button>} />
    <section className="report-grid">
      <article className="report-card"><FileBarChart /><span className="eyebrow">Weekly health</span><h2>Training, recovery and trends</h2><p>Seven days of Garmin, RENPHO and manual data with a 30-day lifestyle context.</p>{reportId ? <div className="button-row"><Link className="button button--primary" to={`/reports/weekly/${reportId}`}>Open latest report</Link><button className="button" onClick={() => void run(() => download(`/reports/weekly/${reportId}/markdown`, 'weekly-health-report.md'))}><Download />Download Markdown</button></div> : <span className="muted">No report in memory</span>}</article>
      <article className="report-card"><Map /><span className="eyebrow">Privacy option</span><h2>Routes are opt-in</h2><p>Location and GPS points remain in memory. AI context exports always exclude routes and locations.</p><button className="button" disabled={busy} onClick={() => void start('/reports/weekly', { include_routes: true, map_tiles_enabled: false })}>Generate with route lines</button></article>
    </section>
    <section className="panel section-gap ai-context-panel">
      <div className="panel__head"><div><span className="eyebrow">Structured local export</span><h2>AI Health Context</h2></div><BrainCircuit /></div>
      <p className="muted">Canonical JSON and matching Markdown include training, recovery, pressure and body-composition trends. GPS, locations, account identifiers and raw API responses are excluded.</p>
      <div className="button-row">
        {([['current', 'Current'], ['7d', 'Last 7 days'], ['30d', 'Last 30 days']] as const).map(([period, label]) => <button key={period} className={period === '30d' ? 'button button--primary' : 'button'} disabled={busy} onClick={() => void start('/ai-context/generate', { period })}>{label}</button>)}
        <button className="button" onClick={() => void run(() => api('/archive/open', { method: 'POST', body: '{}' }))}><FolderOpen />Open archive folder</button>
      </div>
      <div className="context-grid">
        {(['current', '7d', '30d'] as const).map((period) => <ContextDownload key={period} period={period} contextId={contexts[period]} run={run} />)}
      </div>
    </section>
  </>
}

function ContextDownload({ period, contextId, run }: { period: 'current' | '7d' | '30d'; contextId?: string; run: (operation: () => Promise<unknown>) => Promise<void> }) {
  const { data } = useQuery({ queryKey: ['ai-context', contextId], queryFn: () => api<HealthContextMetadata>(`/ai-context/${contextId}`), enabled: Boolean(contextId) })
  const label = period === 'current' ? 'Current' : period === '7d' ? 'Last 7 days' : 'Last 30 days'
  return <article className="context-download"><strong>{label}</strong>{data ? <><span>{data.summary.activities} activities · {data.summary.body_measurements} body measurements</span><small>{data.archived ? 'Saved to the private archive' : 'Download available; archived copy was preserved or unavailable'}</small><div className="button-row"><button className="button" onClick={() => void run(() => download(`/ai-context/${data.id}/json`, `health-context-${period}.json`))}><Download />JSON</button><button className="button" onClick={() => void run(() => download(`/ai-context/${data.id}/markdown`, `health-context-${period}.md`))}><Download />Markdown</button></div></> : <span className="muted">Not generated in this session</span>}</article>
}

export function WeeklyReportPage() { const { run } = useJobs(); const { reportId = '' } = useParams(); const { data, isLoading, error } = useQuery({ queryKey: ['weekly-report', reportId], queryFn: () => api<WeeklyReport>(`/reports/weekly/${reportId}`) }); if (isLoading) return <EmptyState title="Opening report" description="Loading the in-memory snapshot." />; if (error || !data) return <EmptyState title="Report unavailable" description="Reports live only for the current GUI process. Generate a new report." />; return <><PageHeader eyebrow={`${data.start_date} – ${data.end_date}`} title={`${reportDays(data)}-day health report`} description={`Generated ${new Date(data.generated_at).toLocaleString()}. Observations are not medical diagnoses.`} actions={<><button className="button" onClick={() => void run(() => download(`/reports/weekly/${data.id}/markdown`, `weekly-health-report-${data.start_date}-to-${data.end_date}.md`))}><Download />Download Markdown</button><button className="button button--primary" onClick={() => void run(() => download(`/reports/weekly/${data.id}/download`, `weekly-health-report-${data.start_date}-to-${data.end_date}.pdf`))}><Download />Download PDF</button></>} /><section className="report-summary">{Object.entries(data.summary).map(([label, value]) => <article key={label}><span>{label.replaceAll('_', ' ')}</span><strong>{value}</strong></article>)}</section><section className="chart-grid">{data.charts.charts.map((chart) => <article className="panel" key={chart.id}><div className="panel__head"><h2>{chart.title}</h2></div><MetricChart chart={chart} /></article>)}</section><section className="panel section-gap"><div className="panel__head"><h2>Insights and limitations</h2><span>{data.availability.unavailable.length} unavailable</span></div><div className="insight-list">{data.insights.map((item, index) => <article key={`${item.category}-${index}`}><span className="insight-level">{item.category}</span><p>{item.text}</p>{item.source_url && <a className="text-link" href={item.source_url} target="_blank" rel="noreferrer">{item.source_title}</a>}</article>)}</div></section></> }
