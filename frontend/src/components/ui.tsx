import type { ButtonHTMLAttributes, ReactNode } from 'react'
import { AlertTriangle, Loader2, type LucideIcon } from 'lucide-react'
import { ApiError } from '../api/client'
import type { Tier } from '../api/types'
import { TIER_LABEL, TIER_ORDER, TIER_UI } from '../lib/tier'

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <header className="page-header">
      <div>
        <h1>{title}</h1>
        {subtitle && <p className="page-sub">{subtitle}</p>}
      </div>
      {actions && <div className="page-actions">{actions}</div>}
    </header>
  )
}

export function Card({
  title,
  subtitle,
  actions,
  children,
  className = '',
  flush = false,
}: {
  title?: ReactNode
  subtitle?: ReactNode
  actions?: ReactNode
  children: ReactNode
  className?: string
  flush?: boolean
}) {
  return (
    <section className={`card ${className}`}>
      {(title || actions) && (
        <header className="card-head">
          <div>
            {title && <h2 className="card-title">{title}</h2>}
            {subtitle && <p className="card-sub">{subtitle}</p>}
          </div>
          {actions && <div className="card-actions">{actions}</div>}
        </header>
      )}
      <div className={flush ? 'card-body flush' : 'card-body'}>{children}</div>
    </section>
  )
}

export function Stat({ label, value, hint, color, sub }: { label: string; value: ReactNode; hint?: string; color?: string; sub?: ReactNode }) {
  return (
    <div className="stat" title={hint}>
      <span className="stat-label">{label}</span>
      <span className="stat-value mono" style={color ? { color } : undefined}>
        {value}
      </span>
      {sub && <span className="stat-sub">{sub}</span>}
    </div>
  )
}

export type Tone = 'neutral' | 'brand' | 'ok' | 'warn' | 'bad' | 'info'

export function Chip({ tone = 'neutral', icon: Icon, children, title }: { tone?: Tone; icon?: LucideIcon; children: ReactNode; title?: string }) {
  return (
    <span className={`chip chip-${tone}`} title={title}>
      {Icon && <Icon size={12} aria-hidden />}
      {children}
    </span>
  )
}

interface BtnProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger'
  icon?: LucideIcon
  loading?: boolean
  small?: boolean
}

export function Btn({ variant = 'secondary', icon: Icon, loading, small, children, className = '', disabled, ...rest }: BtnProps) {
  return (
    <button {...rest} disabled={disabled || loading} className={`btn btn-${variant} ${small ? 'btn-sm' : ''} ${className}`}>
      {loading ? <Loader2 size={14} className="spin" aria-hidden /> : Icon ? <Icon size={14} aria-hidden /> : null}
      {children}
    </button>
  )
}

export function Segmented<T extends string>({
  value,
  onChange,
  options,
  label,
}: {
  value: T
  onChange: (v: T) => void
  options: { value: T; label: ReactNode; count?: number }[]
  label: string
}) {
  return (
    <div className="segmented" role="group" aria-label={label}>
      {options.map((o) => (
        <button key={o.value} type="button" aria-pressed={value === o.value} className={value === o.value ? 'on' : ''} onClick={() => onChange(o.value)}>
          {o.label}
          {o.count !== undefined && <span className="seg-count mono">{o.count}</span>}
        </button>
      ))}
    </div>
  )
}

export function Empty({ icon: Icon, title, children }: { icon?: LucideIcon; title: string; children?: ReactNode }) {
  return (
    <div className="empty">
      {Icon && <Icon size={22} aria-hidden />}
      <strong>{title}</strong>
      {children && <p>{children}</p>}
    </div>
  )
}

export function Loading({ label = 'Loading' }: { label?: string }) {
  return (
    <div className="loading" role="status">
      <Loader2 size={16} className="spin" aria-hidden /> {label}...
    </div>
  )
}

export function ErrorBox({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const msg = error instanceof Error ? error.message : String(error)
  // A 4xx means the request itself was refused (bad file, blocked link): say so instead of "went wrong".
  const refused = error instanceof ApiError && error.status >= 400 && error.status < 500
  return (
    <div className="error-box" role="alert">
      <AlertTriangle size={16} aria-hidden />
      <div>
        <strong>{refused ? 'That could not be done' : 'Something went wrong'}</strong>
        <p>{msg}</p>
      </div>
      {onRetry && (
        <Btn small onClick={onRetry}>
          Retry
        </Btn>
      )}
    </div>
  )
}

export function Notice({ tone = 'info', children, icon: Icon }: { tone?: Tone; children: ReactNode; icon?: LucideIcon }) {
  return (
    <div className={`notice notice-${tone}`} role={tone === 'bad' || tone === 'warn' ? 'alert' : 'note'}>
      {Icon && <Icon size={15} aria-hidden />}
      <div>{children}</div>
    </div>
  )
}

export function TierBadge({ tier }: { tier: Tier }) {
  const c = TIER_UI[tier]
  return (
    <span className="tier-badge" style={{ background: c.fill, color: c.text }} aria-label={`Tier ${TIER_LABEL[tier]}`}>
      {TIER_LABEL[tier].toUpperCase()}
    </span>
  )
}

/** Stacked horizontal bar of tier counts. Colour + count + legend text: never colour alone. */
export function TierBar({ counts, legend = false, height = 10 }: { counts: Record<Tier, number>; legend?: boolean; height?: number }) {
  const total = TIER_ORDER.reduce((s, t) => s + (counts[t] ?? 0), 0)
  if (!total) return <div className="tierbar-empty muted">No sites</div>
  const desc = TIER_ORDER.filter((t) => counts[t]).map((t) => `${counts[t]} ${TIER_LABEL[t]}`).join(', ')
  return (
    <div className="tierbar-wrap">
      <div className="tierbar" style={{ height }} role="img" aria-label={desc}>
        {TIER_ORDER.map((t) =>
          counts[t] ? <span key={t} style={{ width: `${(counts[t] / total) * 100}%`, background: TIER_UI[t].fill }} title={`${counts[t]} ${TIER_LABEL[t]}`} /> : null,
        )}
      </div>
      {legend && (
        <div className="tierbar-legend">
          {TIER_ORDER.filter((t) => counts[t]).map((t) => (
            <span key={t}>
              <i style={{ background: TIER_UI[t].fill }} /> {counts[t]} {TIER_LABEL[t]}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}

export function Field({ label, hint, children }: { label: string; hint?: ReactNode; children: ReactNode }) {
  return (
    <label className="field">
      <span className="field-label">{label}</span>
      {children}
      {hint && <span className="field-hint">{hint}</span>}
    </label>
  )
}

export function DataTable({ children, caption }: { children: ReactNode; caption: string }) {
  return (
    <div className="table-wrap">
      <table className="table">
        <caption className="sr-only">{caption}</caption>
        {children}
      </table>
    </div>
  )
}
