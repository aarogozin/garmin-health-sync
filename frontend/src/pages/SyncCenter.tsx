import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { ArrowUpFromLine, CalendarClock, Play, RefreshCw, Scale, Trash2 } from 'lucide-react'
import { api } from '../api'
import { PageHeader } from '../components/Common'
import { useJobs } from '../jobs'

export function SyncCenterPage() {
  const { start, busy } = useJobs()
  const [hour, setHour] = useState(7)
  const [minute, setMinute] = useState(0)
  const schedule = useQuery({ queryKey: ['schedule'], queryFn: () => api<{ supported: boolean; installed: boolean; loaded: boolean; legacy: boolean }>('/schedule'), refetchInterval: busy ? 1000 : false })
  return <><PageHeader eyebrow="Verified transfers" title="Sync center" description="Preview every batch, review mappings, then confirm. Writes never retry automatically." />
    <section className="sync-grid"><article className="sync-card"><span className="sync-icon"><ArrowUpFromLine /></span><div><span className="eyebrow">RENPHO → Garmin</span><h2>Body composition</h2><p>Uploads the latest measurement or one record per day from history.</p></div><div className="button-row"><button className="button button--primary" disabled={busy} onClick={() => void start('/renpho/sync/preview', { mode: 'latest' })}><Scale />Latest</button><button className="button" disabled={busy} onClick={() => void start('/renpho/sync/preview', { mode: 'all' })}><CalendarClock />History</button></div></article>
      <article className="sync-card sync-card--compact"><RefreshCw /><div><h2>Refresh source status</h2><p>Read-only connection check for both saved sessions.</p></div><button className="button" disabled={busy} onClick={() => void start('/sources/status')}>Check now</button></article>
      <article className="sync-card"><span className="sync-icon"><CalendarClock /></span><div><span className="eyebrow">Automation</span><h2>Daily body sync</h2><p>Uploads the newest eligible RENPHO body measurement to Garmin once per day. {!schedule.data?.supported ? 'LaunchAgent scheduling is available in the native macOS runtime.' : schedule.data.installed ? `${schedule.data.loaded ? 'Active' : 'Installed but not loaded'}${schedule.data.legacy ? ' · update required' : ''}` : 'Not installed'}</p></div>{schedule.data?.supported && <><div className="schedule-time"><label><span>Hour</span><input type="number" min="0" max="23" value={hour} onChange={(event) => setHour(Number(event.target.value))} /></label><label><span>Minute</span><input type="number" min="0" max="59" value={minute} onChange={(event) => setMinute(Number(event.target.value))} /></label></div><div className="button-row"><button className="button button--primary" disabled={busy} onClick={() => void start('/schedule/install', { hour, minute })}>{schedule.data.installed ? 'Update schedule' : 'Install schedule'}</button>{schedule.data.installed && <><button className="button" disabled={busy} onClick={() => void start('/schedule/run')}><Play />Run now</button><button className="button button--danger" disabled={busy} onClick={() => void start('/schedule/uninstall')}><Trash2 />Remove</button></>}</div></>}</article>
    </section>
    <section className="panel section-gap"><div className="panel__head"><div><span className="eyebrow">Safety model</span><h2>What “verified” means</h2></div></div><div className="principles"><div><b>1. Preview</b><p>The app normalizes data and detects known duplicates.</p></div><div><b>2. Write once</b><p>Only confirmed candidates reach the destination service.</p></div><div><b>3. Read back</b><p>An exact remote match marks the operation verified.</p></div><div><b>4. Stop on uncertainty</b><p>No automatic retry can create a silent duplicate.</p></div></div></section>
  </>
}
