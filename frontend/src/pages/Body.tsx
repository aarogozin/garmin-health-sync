import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Download, RefreshCw, Ruler, Weight } from 'lucide-react'
import { api, download } from '../api'
import { MetricChart } from '../components/MetricChart'
import { EmptyState, PageHeader } from '../components/Common'
import { useJobs } from '../jobs'
import type { Dashboard } from '../types'

export function BodyPage() {
  const { data } = useQuery({ queryKey: ['dashboard'], queryFn: () => api<Dashboard>('/dashboard') }); const { jobs, start, busy } = useJobs(); const [historyJob, setHistoryJob] = useState<string | null>(null); const history = historyJob ? jobs[historyJob]?.result : null; const chart = data?.report?.charts.charts.find((item) => item.id === 'body-kg')
  return <><PageHeader eyebrow="RENPHO + Garmin" title="Body" description="Weight, composition and circumference measurements with their source preserved." actions={<button className="button" disabled={busy} onClick={async () => setHistoryJob(await start('/renpho/history'))}><Ruler />Load measurements</button>} />
    <section className="body-grid"><article className="panel body-hero"><span className="eyebrow">Latest measurement</span><div className="body-value"><Weight /><strong>{data?.latest_body ? `${data.latest_body.weight_kg.toFixed(1)} kg` : '—'}</strong></div><p>{data?.latest_body ? new Date(data.latest_body.measured_at).toLocaleString() : 'Connect RENPHO to load body data.'}</p>{data?.latest_body && <div className="button-row"><button className="button" disabled={busy} onClick={() => void start('/renpho/latest')}><RefreshCw />Refresh</button><button className="button" onClick={() => void download('/reports/renpho/download', `renpho-body-composition-${data.latest_body!.measured_at.slice(0, 10)}.pdf`)}><Download />Report</button></div>}</article><article className="panel panel--wide"><div className="panel__head"><h2>Composition trend</h2><span className="source-chip">Combined sources</span></div>{chart ? <MetricChart chart={chart} /> : <EmptyState title="No body trend loaded" description="Generate a weekly snapshot to combine Garmin and RENPHO history." />}</article></section>
    {history?.type === 'renpho_history' && <section className="panel section-gap"><div className="panel__head"><div><span className="eyebrow">Circumference history</span><h2>Body measurements</h2></div><span>{history.girth.length} records</span></div>{history.girth.length ? <div className="measurement-grid">{history.girth.map((item: any) => <article key={item.measured_at} className="measurement-card"><h3>{new Date(item.measured_at).toLocaleString()}</h3><div className="measurement-visual"><img src="/assets/body-silhouette.svg" alt="Neutral human silhouette"/><div className="measurement-labels">{item.values.map((value: any) => <div key={value.label}><span>{value.label}</span><strong>{value.value.toFixed(1)} {value.unit === 'ratio' ? '' : value.unit}</strong></div>)}</div></div></article>)}</div> : <EmptyState title="No circumference measurements" description="RENPHO did not return a body-measurement record." />}</section>}
  </>
}
