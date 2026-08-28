import AxeBuilder from '@axe-core/playwright'
import { expect, test, type Page } from '@playwright/test'

const bootstrap = (connected: boolean) => ({
  status: 'success',
  data: {
    version: '1.0.0', csrf_token: 'browser-test-token', timezone: 'Europe/Berlin', busy: false,
    sources: {
      garmin: { connected, label: 'Garmin Connect', detail: connected ? 'Connected: Test User' : 'No saved Garmin session' },
      renpho: { connected: false, label: 'RENPHO', detail: 'Not connected' },
    },
    capabilities: { gui_auth: true, renpho_auth: true, weekly_report: true },
    latest_weekly_report_id: null,
  },
})

async function mockApi(page: Page, connected = true) {
  await page.route('**/api/v1/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/bootstrap')) return route.fulfill({ json: bootstrap(connected) })
    if (path.endsWith('/dashboard')) return route.fulfill({ json: { status: 'success', data: { latest_body: null, report: null, events: [] } } })
    if (path.endsWith('/schedule')) return route.fulfill({ json: { status: 'success', data: { supported: false, installed: false, loaded: false, legacy: false } } })
    if (path.endsWith('/pressure/preview')) return route.fulfill({ json: { status: 'success', data: { summary: '120/80 mmHg' } } })
    return route.fulfill({ json: { status: 'success', data: [] } })
  })
}

test('first run explains the local privacy boundary', async ({ page }) => {
  await mockApi(page, false)
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Your data, connected locally.' })).toBeVisible()
  await expect(page.getByText('Loopback-only interface')).toBeVisible()
  await page.getByRole('button', { name: 'Explore available data' }).click()
  await expect(page.getByRole('heading', { name: 'Today' })).toBeVisible()
})

test('navigation, pressure confirmation and accessibility', async ({ page, isMobile }) => {
  await mockApi(page)
  await page.goto('/')
  if (isMobile) await page.getByRole('button', { name: 'Open navigation' }).click()
  await page.getByRole('link', { name: 'Blood pressure' }).click()
  await expect(page.getByRole('heading', { name: 'Blood pressure' })).toBeVisible()
  await page.getByRole('button', { name: 'Review measurement' }).click()
  await expect(page.getByRole('dialog', { name: 'Confirm blood pressure' })).toBeVisible()
  await page.getByRole('button', { name: 'Go back' }).click()
  const results = await new AxeBuilder({ page }).analyze()
  expect(results.violations).toEqual([])
})

test('health data is never persisted in browser storage', async ({ page }) => {
  await mockApi(page)
  await page.goto('/')
  const storage = await page.evaluate(() => ({ ...localStorage }))
  expect(Object.keys(storage).every((key) => key.startsWith('garmin-health-sync.ui.'))).toBeTruthy()
})
