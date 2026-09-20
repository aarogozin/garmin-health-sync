import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, expect, test, vi } from 'vitest'
import { api, download, downloadFilename } from './api'
import { JobsProvider, useJobs } from './jobs'
import { reportDays } from './report-period'

afterEach(() => { cleanup(); vi.useRealTimers(); vi.unstubAllGlobals() })

function DirectActions() {
  const { run, start } = useJobs()
  return <>
    <button onClick={() => void start('/dashboard/refresh')}>Start</button>
    <button onClick={() => void run(() => download('/reports/weekly/missing/download', 'report.pdf'))}>Download</button>
    <button onClick={() => void run(() => api('/archive/open', { method: 'POST' }))}>Open archive</button>
    <button onClick={() => void run(() => api('/auth/garmin/mfa', { method: 'POST' }))}>Send MFA</button>
  </>
}

test('malformed job acknowledgments become safe errors instead of crashing the UI', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => ({ status: 'success', data: [] }) })))
  render(<QueryClientProvider client={new QueryClient()}><JobsProvider><DirectActions /></JobsProvider></QueryClientProvider>)
  fireEvent.click(screen.getByRole('button', { name: 'Start' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Check its status before retrying')
})

test.each(['Download', 'Open archive', 'Send MFA'])('%s failures reach the visible activity center', async (label) => {
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 409, json: async () => ({ error: { message: 'Action unavailable' } }) })))
  const client = new QueryClient()
  render(<QueryClientProvider client={client}><JobsProvider><DirectActions /></JobsProvider></QueryClientProvider>)
  fireEvent.click(screen.getByRole('button', { name: label }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Action unavailable')
})

test('successful operations dismiss themselves after one minute while failures remain visible', async () => {
  vi.useFakeTimers()
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
    const path = String(input)
    if (path.endsWith('/dashboard/refresh')) return { ok: true, json: async () => ({ status: 'queued', data: { job_id: 'job-1', kind: 'dashboard' } }) }
    if (path.endsWith('/jobs/job-1')) return { ok: true, json: async () => ({ status: 'success', data: { id: 'job-1', state: 'verified' } }) }
    return { ok: false, status: 500, json: async () => ({ error: { message: 'Unexpected request' } }) }
  }))
  render(<QueryClientProvider client={new QueryClient()}><JobsProvider><DirectActions /></JobsProvider></QueryClientProvider>)
  fireEvent.click(screen.getByRole('button', { name: 'Start' }))
  await act(async () => { await Promise.resolve() })
  await act(async () => { await vi.advanceTimersByTimeAsync(750) })
  expect(screen.getByLabelText('Activity center')).toBeInTheDocument()
  await act(async () => { await vi.advanceTimersByTimeAsync(60_000) })
  expect(screen.queryByLabelText('Activity center')).not.toBeInTheDocument()
})

test('report periods count inclusive dates across daylight-saving boundaries', () => {
  expect(reportDays({ start_date: '2026-03-29', end_date: '2026-03-29' })).toBe(1)
  expect(reportDays({ start_date: '2026-03-01', end_date: '2026-03-30' })).toBe(30)
})

test('downloads prefer generated server filenames and reject path components', () => {
  expect(downloadFilename('attachment; filename="health-context-30d-2026-09-19_18-30-02.json"', 'fallback.json')).toBe('health-context-30d-2026-09-19_18-30-02.json')
  expect(downloadFilename('attachment; filename="../../private.json"', 'fallback.json')).toBe('private.json')
  expect(downloadFilename(null, 'fallback.json')).toBe('fallback.json')
})
