import { Activity, BarChart3, CircleGauge, Droplets, FileText, HeartPulse, Menu, Moon, MoreHorizontal, Settings, SlidersHorizontal, X } from 'lucide-react'
import { NavLink, useLocation } from 'react-router-dom'
import { useState, type ReactNode } from 'react'
import type { Bootstrap } from '../types'

const navigation = [
  ['Overview', '/overview', CircleGauge], ['Training', '/training', Activity], ['Recovery', '/recovery', Moon],
  ['Body', '/body', Droplets], ['Blood pressure', '/blood-pressure', HeartPulse], ['Reports', '/reports', FileText],
  ['Sync center', '/sync', SlidersHorizontal], ['Settings', '/settings', Settings],
] as const

export function Layout({ bootstrap, children }: { bootstrap: Bootstrap; children: ReactNode }) {
  const [mobileOpen, setMobileOpen] = useState(false)
  const location = useLocation()
  const current = navigation.find(([, path]) => location.pathname === path || (path === '/reports' && location.pathname.startsWith('/reports/')))?.[0] ?? 'Health Sync'
  const mobileNavigation = navigation.slice(0, 4)
  return <div className="app-shell">
    <aside className="sidebar">
      <div className="brand"><span className="brand__mark"><BarChart3 /></span><span>Health Sync</span></div>
      <nav aria-label="Primary navigation">{navigation.map(([label, path, Icon]) => <NavLink key={path} to={path} className={({ isActive }) => isActive ? 'nav-link nav-link--active' : 'nav-link'}><Icon /><span>{label}</span></NavLink>)}</nav>
      <div className="source-stack"><Profile profile={bootstrap.profile}/><Source connected={bootstrap.sources.garmin.connected} label="Garmin"/><Source connected={bootstrap.sources.renpho.connected} label="RENPHO"/><small>Local only · v{bootstrap.version}</small></div>
    </aside>
    <header className="mobile-bar"><button className="icon-button" onClick={() => setMobileOpen(true)} aria-label="Open navigation"><Menu /></button><span className="mobile-bar__title">{current}</span><NavLink to="/settings" aria-label="Settings"><Profile profile={bootstrap.profile} compact /></NavLink></header>
    <main className="content">{children}</main>
    <nav className="mobile-nav" aria-label="Primary navigation">{mobileNavigation.map(([label, path, Icon]) => <NavLink key={path} to={path} className={({ isActive }) => isActive ? 'mobile-nav--active' : ''}><Icon /><span>{label}</span></NavLink>)}<button aria-expanded={mobileOpen} aria-controls="mobile-actions" onClick={() => setMobileOpen(true)}><MoreHorizontal /><span>More</span></button></nav>
    {mobileOpen && <><button className="mobile-sheet-backdrop" aria-label="Close navigation" onClick={() => setMobileOpen(false)} /><section className="mobile-sheet" id="mobile-actions" role="dialog" aria-modal="true" aria-label="More navigation"><span className="mobile-sheet__handle" />{navigation.map(([label, path, Icon]) => <NavLink key={path} to={path} onClick={() => setMobileOpen(false)} className={({ isActive }) => isActive ? 'nav-link nav-link--active' : 'nav-link'}><Icon /><span>{label}</span></NavLink>)}<button className="button button--quiet" onClick={() => setMobileOpen(false)}><X />Close</button></section></>}
  </div>
}

function Profile({ profile, compact = false }: { profile: Bootstrap['profile']; compact?: boolean }) {
  if (!profile) return null
  return <div className={compact ? 'profile profile--compact' : 'profile'}>{profile.avatar_available ? <img src="/api/v1/profile/avatar" alt="" onError={(event) => { event.currentTarget.style.display = 'none' }} /> : null}<span className="profile__initials" aria-label={profile.display_name}>{profile.initials}</span>{!compact && <span className="profile__name">{profile.display_name}</span>}</div>
}

function Source({ connected, label }: { connected: boolean; label: string }) {
  return <div className="source-state"><span className={connected ? 'status-dot status-dot--ok' : 'status-dot'} />{label}<small>{connected ? 'Connected' : 'Needs setup'}</small></div>
}
