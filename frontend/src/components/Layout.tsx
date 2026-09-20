import { Activity, BarChart3, CircleGauge, Droplets, FileText, HeartPulse, Menu, Moon, Settings, SlidersHorizontal, X } from 'lucide-react'
import { NavLink } from 'react-router-dom'
import { useState, type ReactNode } from 'react'
import type { Bootstrap } from '../types'

const navigation = [
  ['Overview', '/overview', CircleGauge], ['Training', '/training', Activity], ['Recovery', '/recovery', Moon],
  ['Body', '/body', Droplets], ['Blood pressure', '/blood-pressure', HeartPulse], ['Reports', '/reports', FileText],
  ['Sync center', '/sync', SlidersHorizontal], ['Settings', '/settings', Settings],
] as const

export function Layout({ bootstrap, children }: { bootstrap: Bootstrap; children: ReactNode }) {
  const [mobileOpen, setMobileOpen] = useState(false)
  return <div className="app-shell">
    <aside className={`sidebar ${mobileOpen ? 'sidebar--open' : ''}`}>
      <div className="brand"><span className="brand__mark"><BarChart3 /></span><span>Health Sync</span><button className="icon-button mobile-only" aria-label="Close navigation" onClick={() => setMobileOpen(false)}><X /></button></div>
      <nav aria-label="Primary navigation">{navigation.map(([label, path, Icon]) => <NavLink key={path} to={path} onClick={() => setMobileOpen(false)} className={({ isActive }) => isActive ? 'nav-link nav-link--active' : 'nav-link'}><Icon /><span>{label}</span></NavLink>)}</nav>
      <div className="source-stack"><Profile profile={bootstrap.profile}/><Source connected={bootstrap.sources.garmin.connected} label="Garmin"/><Source connected={bootstrap.sources.renpho.connected} label="RENPHO"/><small>Local only · v{bootstrap.version}</small></div>
    </aside>
    <header className="mobile-bar"><button className="icon-button" onClick={() => setMobileOpen(true)} aria-label="Open navigation"><Menu /></button><span>Health Sync</span><NavLink to="/settings" aria-label="Settings"><Profile profile={bootstrap.profile} compact /></NavLink></header>
    <main className="content">{children}</main>
  </div>
}

function Profile({ profile, compact = false }: { profile: Bootstrap['profile']; compact?: boolean }) {
  if (!profile) return null
  return <div className={compact ? 'profile profile--compact' : 'profile'}>{profile.avatar_available ? <img src="/api/v1/profile/avatar" alt="" onError={(event) => { event.currentTarget.style.display = 'none' }} /> : null}<span className="profile__initials" aria-label={profile.display_name}>{profile.initials}</span>{!compact && <span className="profile__name">{profile.display_name}</span>}</div>
}

function Source({ connected, label }: { connected: boolean; label: string }) {
  return <div className="source-state"><span className={connected ? 'status-dot status-dot--ok' : 'status-dot'} />{label}<small>{connected ? 'Connected' : 'Needs setup'}</small></div>
}
