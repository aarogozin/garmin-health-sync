import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { Check, HeartPulse } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../api'
import { MetricChart } from '../components/MetricChart'
import { EmptyState, PageHeader } from '../components/Common'
import { useJobs } from '../jobs'
import type { Dashboard } from '../types'

const schema = z.object({ measured_at: z.string().min(1), systolic: z.number().min(70).max(260), diastolic: z.number().min(40).max(150), pulse: z.number().min(20).max(250), notes: z.string().max(500) })
type Values = z.infer<typeof schema>
const localDateTime = () => { const now = new Date(); now.setMinutes(now.getMinutes() - now.getTimezoneOffset()); return now.toISOString().slice(0, 16) }

export function BloodPressurePage() {
  const { data } = useQuery({ queryKey: ['dashboard'], queryFn: () => api<Dashboard>('/dashboard') }); const chart = data?.report?.charts.charts.find((item) => item.id === 'blood-pressure'); const { start, busy } = useJobs(); const [preview, setPreview] = useState<Values | null>(null)
  const { register, handleSubmit, formState: { errors }, reset } = useForm<Values>({ resolver: zodResolver(schema), defaultValues: { measured_at: localDateTime(), systolic: 120, diastolic: 80, pulse: 60, notes: '' } })
  const submit = async (values: Values) => { await api('/pressure/preview', { method: 'POST', body: JSON.stringify(values) }); setPreview(values) }
  return <><PageHeader eyebrow="Manual measurement" title="Blood pressure" description="Review every entry before Garmin receives it. Exact duplicates are blocked." />
      <section className="split-layout"><article className="panel"><div className="panel__head"><div><h2>Add a measurement</h2><p>Use a rested home reading.</p></div><HeartPulse /></div><form className="form-grid" onSubmit={handleSubmit(submit)}><label>Date and time<input type="datetime-local" {...register('measured_at')} />{errors.measured_at && <small className="error-text">Required</small>}</label><div className="field-row"><label>Systolic <span>mmHg</span><input type="number" {...register('systolic', { valueAsNumber: true })} />{errors.systolic && <small className="error-text">70–260</small>}</label><label>Diastolic <span>mmHg</span><input type="number" {...register('diastolic', { valueAsNumber: true })} />{errors.diastolic && <small className="error-text">40–150</small>}</label><label>Pulse <span>bpm</span><input type="number" {...register('pulse', { valueAsNumber: true })} />{errors.pulse && <small className="error-text">20–250</small>}</label></div><label>Notes <span>optional</span><textarea rows={3} {...register('notes')} /></label><button className="button button--primary" disabled={busy}>Review measurement</button></form></article>
      <article className="panel"><div className="panel__head"><h2>Seven-day trend</h2><span className="source-chip">Garmin</span></div>{chart ? <MetricChart chart={chart} /> : <EmptyState title="No pressure series loaded" description="Generate a health snapshot after adding a measurement." />}</article></section>
    {preview && <div className="modal-backdrop" role="presentation"><section className="confirm-dialog" role="dialog" aria-modal="true" aria-labelledby="pressure-confirm"><span className="confirm-icon"><Check /></span><h2 id="pressure-confirm">Confirm blood pressure</h2><div className="pressure-reading"><strong>{preview.systolic}/{preview.diastolic}</strong><span>mmHg</span><b>{preview.pulse} bpm</b></div><dl><div><dt>Measured</dt><dd>{new Date(preview.measured_at).toLocaleString()}</dd></div>{preview.notes && <div><dt>Notes</dt><dd>{preview.notes}</dd></div>}</dl><p className="caution">Garmin writes cannot be automatically retried if verification is uncertain.</p><div className="dialog-actions"><button className="button" onClick={() => setPreview(null)}>Go back</button><button className="button button--primary" onClick={() => { void start('/pressure', preview); setPreview(null); reset({ ...preview, measured_at: localDateTime(), notes: '' }) }}>Upload to Garmin</button></div></section></div>}
  </>
}
