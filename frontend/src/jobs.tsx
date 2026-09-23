/* eslint-disable react-refresh/only-export-components */
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { AlertCircle, CheckCircle2, ChevronDown, ChevronUp, LoaderCircle, ShieldCheck, X } from 'lucide-react'
import { api } from './api'
import { reportDays } from './report-period'
import type { Job } from './types'

type JobsContextValue = {
  jobs: Record<string, Job>
  busy: boolean
  start: (path: string, body?: unknown) => Promise<string>
  run: (operation: () => Promise<unknown>) => Promise<void>
  dismiss: (id: string) => void
}

const JobsContext = createContext<JobsContextValue | null>(null)
const SUCCESS_NOTIFICATION_TTL_MS = 60_000
const AUTO_DISMISS_STATES = new Set<Job['state']>(['verified', 'already_exists'])

/** Track asynchronous operations and refresh shared snapshots when each one settles. */
export function JobsProvider({ children }: { children: ReactNode }) {
  const [jobs, setJobs] = useState<Record<string, Job>>({})
  const dismissalTimers = useRef(new Map<string, number>())
  const queryClient = useQueryClient()
  const dismiss = useCallback((id: string) => {
    const timer = dismissalTimers.current.get(id)
    if (timer !== undefined) window.clearTimeout(timer)
    dismissalTimers.current.delete(id)
    setJobs((current) => { const next = { ...current }; delete next[id]; return next })
  }, [])
  const recordError = useCallback((error: unknown) => {
    const jobId = `local-${crypto.randomUUID()}`
    const message = error instanceof Error ? error.message : 'The operation failed'
    setJobs((current) => ({ ...current, [jobId]: { id: jobId, state: 'error', error: { code: 'action_error', message } } }))
    return jobId
  }, [])
  // Direct actions (downloads, MFA and folder opening) share the visible error surface.
  const run = useCallback(async (operation: () => Promise<unknown>) => {
    try { await operation() } catch (error) { recordError(error) }
  }, [recordError])
  const start = useCallback(async (path: string, body: unknown = {}) => {
    try {
      const data = await api<{ job_id: string; kind: string }>(path, { method: 'POST', body: JSON.stringify(body) })
      if (!data || typeof data.job_id !== 'string' || !data.job_id || typeof data.kind !== 'string') {
        throw new Error('The server did not confirm the operation. Check its status before retrying.')
      }
      setJobs((current) => ({ ...current, [data.job_id]: { id: data.job_id, state: 'queued', stage: data.kind } }))
      return data.job_id
    } catch (error) {
      return recordError(error)
    }
  }, [recordError])
  const active = useMemo(() => Object.values(jobs).filter((job) => ['queued', 'running', 'awaiting_input'].includes(job.state)), [jobs])
  const autoDismissable = useMemo(
    () => Object.values(jobs).filter((job) => AUTO_DISMISS_STATES.has(job.state)),
    [jobs],
  )

  useEffect(() => {
    const currentIds = new Set(autoDismissable.map((job) => job.id))
    for (const job of autoDismissable) {
      if (dismissalTimers.current.has(job.id)) continue
      dismissalTimers.current.set(job.id, window.setTimeout(() => dismiss(job.id), SUCCESS_NOTIFICATION_TTL_MS))
    }
    for (const [id, timer] of dismissalTimers.current) {
      if (!currentIds.has(id)) {
        window.clearTimeout(timer)
        dismissalTimers.current.delete(id)
      }
    }
  }, [autoDismissable, dismiss])

  useEffect(() => () => {
    for (const timer of dismissalTimers.current.values()) window.clearTimeout(timer)
    dismissalTimers.current.clear()
  }, [])

  useEffect(() => {
    if (!active.length) return
    const poll = window.setInterval(() => {
      active.forEach((current) => {
        api<Job>(`/jobs/${current.id}`).then((job) => {
          // Invalid polling data must not replace a valid running operation or trigger a write retry.
          const states: Job['state'][] = ['queued', 'running', 'awaiting_input', 'verified', 'already_exists', 'conflict', 'partial', 'uncertain', 'auth_required', 'rate_limited', 'error']
          if (!job || job.id !== current.id || !states.includes(job.state)) return
          setJobs((items) => ({ ...items, [job.id]: job }))
          if (!['queued', 'running', 'awaiting_input'].includes(job.state)) {
            void queryClient.invalidateQueries({ queryKey: ['bootstrap'] })
            void queryClient.invalidateQueries({ queryKey: ['dashboard'] })
            void queryClient.invalidateQueries({ queryKey: ['schedule'] })
            void queryClient.invalidateQueries({ queryKey: ['archive'] })
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
    run,
    dismiss,
  }), [active.length, dismiss, jobs, start, run])
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
  const [expanded, setExpanded] = useState(false)
  if (!context) return null
  const items = Object.values(context.jobs)
  if (!items.length) return null
  const active = items.find((job) => ['queued', 'running', 'awaiting_input'].includes(job.state))
  const persistent = items.some((job) => ['conflict', 'partial', 'uncertain', 'auth_required', 'rate_limited', 'error'].includes(job.state))
  const drawerOpen = expanded || persistent
  const headline = active ? (active.stage ?? 'Operation in progress') : `${items.length} recent operation${items.length === 1 ? '' : 's'}`
  return <aside className="activity-center" aria-label="Activity center">
    <div className="activity-center__head"><button className="activity-center__toggle" aria-expanded={drawerOpen} onClick={() => setExpanded((value) => !value)}><div>{active ? <LoaderCircle className="spin" /> : <CheckCircle2 />}</div><div><strong>{headline}</strong><small>{active ? active.state.replace('_', ' ') : 'Activity Center'}</small></div>{drawerOpen ? <ChevronDown /> : <ChevronUp />}</button><span className="count-badge">{items.length}</span></div>
    {drawerOpen && <div className="activity-center__body"><div className="activity-list">{items.map((job) => <article className="job" key={job.id}>
      <div className="job__icon">{['error', 'uncertain', 'conflict', 'auth_required', 'rate_limited'].includes(job.state) ? <AlertCircle /> : ['verified', 'already_exists', 'partial'].includes(job.state) ? <CheckCircle2 /> : job.state === 'awaiting_input' ? <ShieldCheck /> : <LoaderCircle className="spin" />}</div>
      <div className="job__body"><strong>{job.stage ?? titleFor(job)}</strong><small>{job.state.replace('_', ' ')}</small>
        {typeof job.completed === 'number' && <progress value={job.completed} max={Math.max(1, job.total ?? 1)} />}
        {job.error && <p className="error-text" role="alert">{job.error.message}</p>}
        {job.state === 'awaiting_input' && <form className="inline-form" onSubmit={(event) => { event.preventDefault(); void context.run(async () => { await api('/auth/garmin/mfa', { method: 'POST', body: JSON.stringify({ job_id: job.id, code: mfa }) }); setMfa('') }) }}><label><span>Garmin MFA code</span><input value={mfa} onChange={(event) => setMfa(event.target.value)} required autoComplete="one-time-code" /></label><button className="button button--primary">Continue</button></form>}
        <JobResult result={job.result} start={context.start} />
      </div>
      {!['queued', 'running', 'awaiting_input'].includes(job.state) && <button className="icon-button" aria-label="Dismiss operation" onClick={() => context.dismiss(job.id)}><X /></button>}
    </article>)}</div></div>}
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
  if (result.type === 'weekly_report') return <div className="result"><b>{reportDays(result)}-day report ready</b><a className="text-link" href={`/reports/weekly/${result.id}`}>Open report</a></div>
  if (result.type === 'health_context') return <div className="result"><b>{result.period} AI context ready</b><span>{result.archived ? 'Saved to archive' : 'Partial; download only'}</span></div>
  if (Array.isArray(result)) return <div className="result"><b>{result.length} result(s)</b><span>{result.filter((item) => item.status === 'success').length} verified</span></div>
  return null
}
