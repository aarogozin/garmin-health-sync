import { lazy, Suspense, useEffect, useRef, useState } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { api, setCsrfToken } from './api'
import { Layout } from './components/Layout'
import { LoadingScreen } from './components/Common'
import { JobsProvider, useJobs } from './jobs'
import { Onboarding } from './pages/Onboarding'
import { applyTheme, THEME_STORAGE_KEY, type Theme } from './theme'
import type { Bootstrap } from './types'

const Overview = lazy(() => import('./pages/Overview').then((module) => ({ default: module.Overview })))
const DomainPage = lazy(() => import('./pages/Domains').then((module) => ({ default: module.DomainPage })))
const BloodPressurePage = lazy(() => import('./pages/BloodPressure').then((module) => ({ default: module.BloodPressurePage })))
const BodyPage = lazy(() => import('./pages/Body').then((module) => ({ default: module.BodyPage })))
const ReportsPage = lazy(() => import('./pages/Reports').then((module) => ({ default: module.ReportsPage })))
const WeeklyReportPage = lazy(() => import('./pages/Reports').then((module) => ({ default: module.WeeklyReportPage })))
const SyncCenterPage = lazy(() => import('./pages/SyncCenter').then((module) => ({ default: module.SyncCenterPage })))
const SettingsPage = lazy(() => import('./pages/Settings').then((module) => ({ default: module.SettingsPage })))

export function App() {
  const { data, isLoading, error } = useQuery({ queryKey: ['bootstrap'], queryFn: () => api<Bootstrap>('/bootstrap'), refetchInterval: (query) => query.state.data?.busy ? 1000 : false })
  const [setupComplete, setSetupComplete] = useState(false)
  useEffect(() => { let saved: string | null = null; try { saved = window.localStorage.getItem(THEME_STORAGE_KEY) } catch { /* storage is optional */ } applyTheme((saved as Theme) || 'system') }, [])
  useEffect(() => { if (data?.csrf_token) setCsrfToken(data.csrf_token) }, [data?.csrf_token])
  if (isLoading) return <LoadingScreen />
  if (error || !data) return <main className="startup"><h1>Local server unavailable</h1><p>{error instanceof Error ? error.message : 'Could not load application state.'}</p></main>
  const finishSetup = () => { try { window.localStorage.setItem('garmin-health-sync.ui.v1.onboarding-complete', 'true') } catch { /* completion remains in this session */ }; setSetupComplete(true) }
  let storedSetup = false
  try { storedSetup = window.localStorage.getItem('garmin-health-sync.ui.v1.onboarding-complete') === 'true' } catch { /* storage is optional */ }
  const complete = setupComplete || (data.sources.garmin.connected && data.sources.renpho.connected && storedSetup)
  return <JobsProvider>{!complete ? <Onboarding bootstrap={data} onContinue={finishSetup} /> : <><DashboardBootstrap /><Layout bootstrap={data}><Suspense fallback={<LoadingScreen />}><Routes><Route path="/" element={<Navigate to="/overview" replace />} /><Route path="/overview" element={<Overview />} /><Route path="/training" element={<DomainPage domain="training" />} /><Route path="/recovery" element={<DomainPage domain="recovery" />} /><Route path="/body" element={<BodyPage />} /><Route path="/blood-pressure" element={<BloodPressurePage />} /><Route path="/reports" element={<ReportsPage />} /><Route path="/reports/weekly/:reportId" element={<WeeklyReportPage />} /><Route path="/sync" element={<SyncCenterPage />} /><Route path="/settings" element={<SettingsPage bootstrap={data} />} /><Route path="*" element={<Navigate to="/overview" replace />} /></Routes></Suspense></Layout></>}</JobsProvider>
}

function DashboardBootstrap() {
  const { data } = useQuery({ queryKey: ['dashboard', 7], queryFn: () => api<{ report: unknown | null }>('/dashboard?period_days=7') })
  const { start } = useJobs()
  const requested = useRef(false)
  useEffect(() => {
    if (requested.current || !data || data.report) return
    requested.current = true
    void start('/dashboard/refresh', { period_days: 7 })
  }, [data, start])
  return null
}
