import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { expect, test, vi } from 'vitest'
import { App } from './App'

vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => ({ status: 'success', data: { version: '1.0.0', csrf_token: 'test', timezone: 'Europe/Berlin', busy: false, sources: { garmin: { connected: true, label: 'Garmin', detail: 'Connected' }, renpho: { connected: false, label: 'RENPHO', detail: 'Not connected' } }, capabilities: {}, latest_weekly_report_id: null } }) })))

test('renders the product navigation after bootstrap', async () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(<QueryClientProvider client={client}><MemoryRouter initialEntries={['/overview']}><App /></MemoryRouter></QueryClientProvider>)
  expect(await screen.findByRole('heading', { name: 'Today', level: 1 })).toBeInTheDocument()
  expect(screen.getByText('Sync center')).toBeInTheDocument()
})
