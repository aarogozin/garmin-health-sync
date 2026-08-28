/* eslint-disable react-refresh/only-export-components */
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { AlertCircle, CheckCircle2, LoaderCircle, ShieldCheck, X } from 'lucide-react'
import { api } from './api'
import type { Job } from './types'

type JobsContextValue = {
  jobs: Record<string, Job>
  busy: boolean
  start: (path: string, body?: unknown) => Promise<string>
  dismiss: (id: string) => void
}

const JobsContext = createContext<JobsContextValue | null>(null)

export function JobsProvider({ children }: { children: ReactNode }) {
  const [jobs, setJobs] = useState<Record<string, Job>>({})
  const queryClient = useQueryClient()
  const start = useCallback(async (path: string, body: unknown = {}) => {
    try {
      const data = await api<{ job_id: string; kind: string }>(path, { method: 'POST', body: JSON.stringify(body) })
      setJobs((current) => ({ ...current, [data.job_id]: { id: data.job_id, state: 'queued', stage: data.kind } }))
      return data.job_id
    } catch (error) {
      const jobId = `local-${crypto.randomUUID()}`
      const message = error instanceof Error ? error.message : 'Could not start the operation'
      setJobs((current) => ({ ...current, [jobId]: { id: jobId, state: 'error', error: { code: 'start_error', message } } }))
      return jobId
    }
  }, [])
  const active = useMemo(() => Object.values(jobs).filter((job) => ['queued', 'running', 'awaiting_input'].includes(job.state)), [jobs])

  useEffect(() => {
    if (!active.length) return
    const poll = window.setInterval(() => {
      active.forEach((current) => {
        api<Job>(`/jobs/${current.id}`).then((job) => {
          setJobs((items) => ({ ...items, [job.id]: job }))
          if (!['queued', 'running', 'awaiting_input'].includes(job.state)) {
            void queryClient.invalidateQueries({ queryKey: ['bootstrap'] })
            void queryClient.invalidateQueries({ queryKey: ['dashboard'] })
            void queryClient.invalidateQueries({ queryKey: ['schedule'] })
          }
        }).catch(() => { /* A polling failure never changes the remote operation's state. */ })
      })
    }, 750)
    return () => window.clearInterval(poll)
  }, [active, queryClient])

  const value = useMemo(() => ({
    jobs,
    busy: active.length > 0,
    start,
    dismiss: (id: string) => setJobs((current) => { const next = { ...current }; delete next[id]; return next }),
  }), [active.length, jobs, start])
  return <JobsContext.Provider value={value}>{children}<ActivityCenter /></JobsContext.Provider>
}

export function useJobs() {
  const context = useContext(JobsContext)
  if (!context) throw new Error('useJobs must be used inside JobsProvider')
  return context
}

function ActivityCenter() {
  const context = useContext(JobsContext)
  const [mfa, setMfa] = useState('')
  if (!context) return null
  const items = Object.values(context.jobs)
  if (!items.length) return null
  return <aside className="activity-center" aria-label="Activity center">
    <div className="activity-center__head"><div><span className="eyebrow">Activity center</span><h2>Operations</h2></div><span className="count-badge">{items.length}</span></div>
    <div className="activity-list">{items.map((job) => <article className="job" key={job.id}>
      <div className="job__icon">{['error', 'uncertain', 'conflict', 'auth_required', 'rate_limited'].includes(job.state) ? <AlertCircle /> : ['verified', 'already_exists', 'partial'].includes(job.state) ? <CheckCircle2 /> : job.state === 'awaiting_input' ? <ShieldCheck /> : <LoaderCircle className="spin" />}</div>
      <div className="job__body"><strong>{job.stage ?? titleFor(job)}</strong><small>{job.state.replace('_', ' ')}</small>
        {typeof job.completed === 'number' && <progress value={job.completed} max={Math.max(1, job.total ?? 1)} />}
        {job.error && <p className="error-text">{job.error.message}</p>}
        {job.state === 'awaiting_input' && <form className="inline-form" onSubmit={(event) => { event.preventDefault(); void api('/auth/garmin/mfa', { method: 'POST', body: JSON.stringify({ job_id: job.id, code: mfa }) }); setMfa('') }}><label><span>Garmin MFA code</span><input value={mfa} onChange={(event) => setMfa(event.target.value)} required autoComplete="one-time-code" /></label><button className="button button--primary">Continue</button></form>}
        <JobResult result={job.result} start={context.start} />
      </div>
      {!['queued', 'running', 'awaiting_input'].includes(job.state) && <button className="icon-button" aria-label="Dismiss operation" onClick={() => context.dismiss(job.id)}><X /></button>}
    </article>)}</div>
  </aside>
}

function titleFor(job: Job) {
  const type = job.result?.type
  return type ? String(type).replaceAll('_', ' ') : job.state === 'verified' ? 'Operation complete' : 'Operation'
}

function JobResult({ result, start }: { result: any; start: JobsContextValue['start'] }) {
  if (!result) return null
  if (result.type === 'operation') return <p className={`result result--${result.status}`}>{result.message}</p>
  if (result.type === 'renpho_preview') return <div className="result"><b>{result.count} measurement(s) ready</b><span>{result.skipped} skipped</span>{result.count > 0 && <button className="button button--primary" onClick={() => void start(`/renpho/sync/${result.preview_id}`)}>Confirm sync</button>}</div>
  if (result.type === 'weekly_report') return <div className="result"><b>Weekly report ready</b><a className="text-link" href={`/reports/weekly/${result.id}`}>Open report</a></div>
  if (Array.isArray(result)) return <div className="result"><b>{result.length} result(s)</b><span>{result.filter((item) => item.status === 'success').length} verified</span></div>
  return null
}
