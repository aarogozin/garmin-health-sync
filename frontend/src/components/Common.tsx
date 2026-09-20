import type { ReactNode } from 'react'
import { AlertCircle, ArrowRight, RefreshCw } from 'lucide-react'

export function PageHeader({ eyebrow, title, description, actions }: { eyebrow: string; title: string; description: string; actions?: ReactNode }) {
  return <header className="page-header"><div><span className="eyebrow">{eyebrow}</span><h1>{title}</h1><p>{description}</p></div>{actions && <div className="page-actions">{actions}</div>}</header>
}

export function EmptyState({ title, description, action }: { title: string; description: string; action?: ReactNode }) {
  return <section className="empty-state"><AlertCircle /><h2>{title}</h2><p>{description}</p>{action}</section>
}

export function LoadingScreen() {
  return <main className="startup"><span className="brand__mark"><RefreshCw className="spin" /></span><span className="eyebrow">Private health cockpit</span><h1>Preparing your workspace</h1><p>Checking the local server and secure stores.</p></main>
}

export function TextLink({ href, children }: { href: string; children: ReactNode }) {
  return <a className="text-link" href={href}>{children}<ArrowRight /></a>
}
