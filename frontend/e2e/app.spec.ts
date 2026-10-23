import AxeBuilder from '@axe-core/playwright'
import { expect, test, type Page } from '@playwright/test'

const bootstrap = (connected: boolean) => ({
  status: 'success',
  data: {
    version: '1.1.0', csrf_token: 'browser-test-token', timezone: 'Europe/Berlin', busy: false,
    sources: {
      garmin: { connected, label: 'Garmin Connect', detail: connected ? 'Connected: Test User' : 'No saved Garmin session' },
      renpho: { connected, label: 'RENPHO', detail: connected ? 'Connected' : 'Not connected' },
    },
    capabilities: { gui_auth: true, renpho_auth: true, weekly_report: true },
    latest_weekly_report_id: null,
    profile: null,
  },
})

async function mockApi(page: Page, connected = true) {
  if (connected) await page.addInitScript(() => localStorage.setItem('garmin-health-sync.ui.v1.onboarding-complete', 'true'))
  await page.route('**/api/v1/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/bootstrap')) return route.fulfill({ json: bootstrap(connected) })
    if (path.endsWith('/dashboard')) return route.fulfill({ json: { status: 'success', data: { latest_body: null, report: null, events: [] } } })
    if (path.endsWith('/dashboard/refresh')) return route.fulfill({ json: { status: 'success', data: { job_id: 'dashboard-job', kind: 'dashboard' } } })
    if (path.endsWith('/jobs/dashboard-job')) return route.fulfill({ json: { status: 'success', data: { id: 'dashboard-job', state: 'verified' } } })
    if (path.endsWith('/schedule')) return route.fulfill({ json: { status: 'success', data: { supported: false, installed: false, loaded: false, legacy: false } } })
    if (path.endsWith('/pressure/preview')) return route.fulfill({ json: { status: 'success', data: { summary: '120/80 mmHg' } } })
    return route.fulfill({ status: 404, json: { status: 'error', error: { message: 'Unmocked test endpoint' } } })
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

test('Garmin alone does not dismiss setup and RENPHO can be explicitly skipped', async ({ page }) => {
  await mockApi(page, false)
  const payload = bootstrap(true)
  payload.data.sources.renpho.connected = false
  await page.route('**/api/v1/bootstrap', (route) => route.fulfill({ json: payload }))
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Connect RENPHO' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Continue to dashboard' })).toBeDisabled()
  await page.getByRole('button', { name: 'Continue with Garmin only' }).click()
  await expect(page.getByRole('heading', { name: 'Today' })).toBeVisible()
  await page.reload()
  await expect(page.getByRole('heading', { name: 'Today' })).toBeVisible()
})

test('both connections still require an explicit Continue on first setup', async ({ page }) => {
  await mockApi(page, false)
  await page.route('**/api/v1/bootstrap', (route) => route.fulfill({ json: bootstrap(true) }))
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Your data, connected locally.' })).toBeVisible()
  await page.getByRole('button', { name: 'Continue to dashboard' }).click()
  await expect(page.getByRole('heading', { name: 'Today' })).toBeVisible()
})

test('mobile More sheet exposes every destination without replacing bottom navigation', async ({ page, isMobile }) => {
  test.skip(!isMobile, 'This interaction is specific to the mobile shell.')
  await mockApi(page)
  await page.goto('/')
  await page.getByRole('button', { name: 'More' }).click()
  await expect(page.getByRole('dialog', { name: 'More navigation' })).toBeVisible()
  await page.getByRole('dialog', { name: 'More navigation' }).getByRole('link', { name: 'Settings' }).click()
  await expect(page.getByRole('heading', { name: 'Settings' })).toBeVisible()
})

test('health data is never persisted in browser storage', async ({ page }) => {
  await mockApi(page)
  await page.goto('/')
  const storage = await page.evaluate(() => ({ ...localStorage }))
  expect(Object.keys(storage).every((key) => key.startsWith('garmin-health-sync.ui.'))).toBeTruthy()
})
