import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, expect, test, vi } from 'vitest'
import { DomainPage } from './Domains'
import { BodyPage } from './Body'

const start = vi.fn()
vi.mock('../jobs', () => ({ useJobs: () => ({ start, busy: false }) }))

afterEach(() => { cleanup(); vi.unstubAllGlobals(); start.mockClear() })

test('domain period controls fetch and refresh the selected period', async () => {
  const fetchMock = vi.fn(async () => ({ ok: true, json: async () => ({ data: { report: null } }) }))
  vi.stubGlobal('fetch', fetchMock)
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(<QueryClientProvider client={client}><DomainPage domain="training" /></QueryClientProvider>)
  await waitFor(() => expect(fetchMock).toHaveBeenCalledWith('/api/v1/dashboard?period_days=7', expect.anything()))
  fireEvent.click(screen.getByRole('button', { name: '30 days' }))
  await waitFor(() => expect(fetchMock).toHaveBeenCalledWith('/api/v1/dashboard?period_days=30', expect.anything()))
  fireEvent.click(screen.getByRole('button', { name: 'Refresh snapshot' }))
  expect(start).toHaveBeenCalledWith('/dashboard/refresh', { period_days: 30 })
  fireEvent.click(screen.getByRole('button', { name: 'Today' }))
  await waitFor(() => expect(fetchMock).toHaveBeenCalledWith('/api/v1/dashboard?period_days=1', expect.anything()))
  expect(screen.getByRole('button', { name: 'Today' })).toHaveAttribute('aria-pressed', 'true')
})

test('a newly connected body source can fetch its first measurement', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => ({ data: { report: null, latest_body: null } }) })))
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(<QueryClientProvider client={client}><BodyPage /></QueryClientProvider>)
  fireEvent.click(screen.getByRole('button', { name: 'Refresh' }))
  expect(start).toHaveBeenCalledWith('/renpho/latest')
})
