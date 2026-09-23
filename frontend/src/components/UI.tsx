import type { ButtonHTMLAttributes, ReactNode } from 'react'

/** Small visual primitives shared by the dashboard and all workflow pages. */
export function Button({ tone = 'default', className = '', children, ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { tone?: 'default' | 'primary' | 'quiet' | 'danger' }) {
  const modifier = tone === 'default' ? '' : ` button--${tone}`
  return <button className={`button${modifier} ${className}`.trim()} {...props}>{children}</button>
}

export function Card({ className = '', children }: { className?: string; children: ReactNode }) {
  return <article className={`panel ${className}`.trim()}>{children}</article>
}

export function StatusBadge({ state, children }: { state: string; children: ReactNode }) {
  return <span className={`status-badge status-badge--${state}`}>{children}</span>
}

export function SegmentedControl<T extends string | number>({ value, options, label, onChange }: { value: T; options: ReadonlyArray<{ value: T; label: string }>; label: string; onChange: (value: T) => void }) {
  return <div className="segmented" aria-label={label}>{options.map((option) => <button key={String(option.value)} className={value === option.value ? 'active' : ''} aria-pressed={value === option.value} onClick={() => onChange(option.value)}>{option.label}</button>)}</div>
}

export function Skeleton({ width = '100%', height = 18 }: { width?: string; height?: number }) {
  return <span className="skeleton" style={{ width, height }} aria-label="Loading" />
}

export function FormField({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return <label>{label}{hint && <span>{hint}</span>}{children}</label>
}
