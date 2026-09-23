import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { expect, test, vi } from 'vitest'
import { App } from './App'

const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
  const path = String(input)
  const bootstrap = { version: '1.1.0', csrf_token: 'test', timezone: 'Europe/Berlin', busy: false, sources: { garmin: { connected: true, label: 'Garmin', detail: 'Connected' }, renpho: { connected: false, label: 'RENPHO', detail: 'Not connected' } }, capabilities: {}, latest_weekly_report_id: null }
  const data = path.includes('/dashboard') && (init?.method ?? 'GET') === 'GET' ? { latest_body: null, report: null, events: [] } : path.includes('/dashboard/refresh') ? { job_id: 'dashboard-job', kind: 'dashboard-7-days' } : bootstrap
  return { ok: true, json: async () => ({ status: 'success', data }) }
})
vi.stubGlobal('fetch', fetchMock)

test('renders the product navigation after bootstrap', async () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(<QueryClientProvider client={client}><MemoryRouter initialEntries={['/overview']}><App /></MemoryRouter></QueryClientProvider>)
  // Lazy route chunks can take longer than Testing Library's 1 s default on a cold CI runner.
  expect(await screen.findByRole('heading', { name: 'Today', level: 1 }, { timeout: 5_000 })).toBeInTheDocument()
  expect(screen.getByText('Sync center')).toBeInTheDocument()
  expect(fetchMock).toHaveBeenCalledWith('/api/v1/dashboard/refresh', expect.objectContaining({ method: 'POST' }))
})
