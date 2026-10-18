import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowUpRight, Check, CheckCheck, ChevronDown, ChevronRight, History, MapPin, RotateCcw, ShieldAlert, UserPlus } from 'lucide-react'
import { api } from '../api/client'
import type { Alert, AlertAction, AlertStatus, Severity } from '../api/types'
import { Btn, Card, Chip, Empty, ErrorBox, Loading, PageHeader, Segmented, Stat, TierBadge, type Tone } from '../components/ui'
import { dateTime, shortDate } from '../lib/format'
import { useCan } from '../lib/auth'
import { navigate } from '../lib/router'
import { SEVERITY_UI } from '../lib/tier'
import { useUi } from '../store'

const STATUS_TONE: Record<AlertStatus, Tone> = { open: 'bad', acknowledged: 'info', assigned: 'brand', escalated: 'warn', resolved: 'ok' }
const ACTION_LABEL: Record<AlertAction, string> = { acknowledge: 'Acknowledged', assign: 'Assigned', escalate: 'Escalated', resolve: 'Resolved', reopen: 'Reopened' }

function AlertCard({ a }: { a: Alert }) {
  const qc = useQueryClient()
  const select = useUi((s) => s.selectSite)
  const flyTo = useUi((s) => s.flyTo)
  const [mode, setMode] = useState<null | 'assign' | 'escalate'>(null)
  const [who, setWho] = useState('')
  const [note, setNote] = useState('')
  const [showHistory, setShowHistory] = useState(false)
  const canAct = useCan('analyst')

  const act = useMutation({
    mutationFn: (b: { action: AlertAction; assignee?: string; note?: string }) => api.alertAction({ alert_id: a.alert_id, actor: 'operator', ...b }),
    onSuccess: () => {
      setMode(null)
      setWho('')
      setNote('')
      qc.invalidateQueries({ queryKey: ['alerts'] })
    },
  })
  const sev = SEVERITY_UI[a.severity]
  const done = a.status === 'resolved'

  return (
    <article className={`alert-card ${done ? 'done' : ''}`} style={{ borderLeftColor: sev.fill }}>
      <header className="alert-head">
        <div className="alert-title">
          <span className="sev-pill" style={{ background: sev.soft, color: sev.text }}>
            {sev.label}
          </span>
          <h3>{a.title}</h3>
        </div>
        <div className="alert-chips">
          <Chip tone={STATUS_TONE[a.status]}>{a.status}</Chip>
          <span className="muted mono" title="Satellite pass date">
            {shortDate(a.as_of)}
          </span>
        </div>
      </header>

      <p className="alert-detail">{a.detail}</p>

      <div className="alert-meta">
        {a.tier && a.previous_tier && (
          <span className="tier-move">
            <TierBadge tier={a.previous_tier} /> <ArrowUpRight size={13} aria-hidden /> <TierBadge tier={a.tier} />
          </span>
        )}
        {a.rpi != null && <span className="muted">RPI <span className="mono secondary">{a.rpi.toFixed(0)}</span></span>}
        {a.also.length > 0 && <span className="muted">also: {a.also.map((k) => k.toLowerCase().replaceAll('_', ' ')).join(', ')}</span>}
        {a.assignee && (
          <span className="muted">
            owner: <strong className="secondary">{a.assignee}</strong>
          </span>
        )}
      </div>

      <div className="alert-actions">
        {a.site_id && (
          <Btn small icon={ShieldAlert} onClick={() => select(a.site_id, 'now')}>
            Open site
          </Btn>
        )}
        {a.lat != null && a.lon != null && (
          <Btn
            small
            variant="ghost"
            icon={MapPin}
            onClick={() => {
              navigate('/')
              flyTo([a.lon!, a.lat!], 14.5)
              if (a.site_id) select(a.site_id, 'now')
            }}
          >
            Map
          </Btn>
        )}
        <span className="grow" />
        {!canAct && <span className="muted" title="Acting on alerts needs the Analyst role">Read-only</span>}
        {canAct && !done && a.status === 'open' && (
          <Btn small icon={Check} loading={act.isPending && act.variables?.action === 'acknowledge'} onClick={() => act.mutate({ action: 'acknowledge' })}>
            Acknowledge
          </Btn>
        )}
        {canAct && !done && (
          <>
            <Btn small icon={UserPlus} onClick={() => setMode(mode === 'assign' ? null : 'assign')} aria-expanded={mode === 'assign'}>
              Assign
            </Btn>
            <Btn small variant="danger" onClick={() => setMode(mode === 'escalate' ? null : 'escalate')} aria-expanded={mode === 'escalate'}>
              Escalate
            </Btn>
            <Btn small variant="primary" icon={CheckCheck} loading={act.isPending && act.variables?.action === 'resolve'} onClick={() => act.mutate({ action: 'resolve', note: note || undefined })}>
              Resolve
            </Btn>
          </>
        )}
        {canAct && done && (
          <Btn small icon={RotateCcw} onClick={() => act.mutate({ action: 'reopen' })}>
            Reopen
          </Btn>
        )}
      </div>

      {canAct && mode && (
        <form
          className="alert-form"
          onSubmit={(e) => {
            e.preventDefault()
            if (who.trim()) act.mutate({ action: mode, assignee: who.trim(), note: note || undefined })
          }}
        >
          <input autoFocus placeholder={mode === 'assign' ? 'Assign to (person or team)' : 'Escalate to (person or role)'} value={who} onChange={(e) => setWho(e.target.value)} aria-label="Assignee" required maxLength={60} />
          <input placeholder="Note (optional)" value={note} onChange={(e) => setNote(e.target.value)} aria-label="Note" maxLength={500} />
          <Btn type="submit" variant={mode === 'escalate' ? 'danger' : 'primary'} small loading={act.isPending}>
            {mode === 'assign' ? 'Assign' : 'Escalate'}
          </Btn>
        </form>
      )}
      {act.error && <ErrorBox error={act.error} />}

      {a.history.length > 0 && (
        <div className="alert-history">
          <button className="link-btn" onClick={() => setShowHistory((v) => !v)} aria-expanded={showHistory}>
            {showHistory ? <ChevronDown size={13} aria-hidden /> : <ChevronRight size={13} aria-hidden />} <History size={13} aria-hidden /> {a.history.length} action{a.history.length > 1 ? 's' : ''}
          </button>
          {showHistory && (
            <ol className="history-list">
              {a.history.map((h) => (
                <li key={h.at + h.action}>
                  <strong>{ACTION_LABEL[h.action]}</strong>
                  {h.assignee && <> to <strong>{h.assignee}</strong></>} by {h.actor} <span className="muted mono">{dateTime(h.at)}</span>
                  {h.note && <div className="muted">"{h.note}"</div>}
                </li>
              ))}
            </ol>
          )}
        </div>
      )}
    </article>
  )
}

export default function AlertsPage() {
  const regionId = useUi((s) => s.regionId)
  const [status, setStatus] = useState<'' | AlertStatus>('')
  const [severity, setSeverity] = useState<'' | Severity>('')
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['alerts', regionId, status, severity],
    queryFn: () => api.alerts(regionId, status || undefined, severity || undefined),
  })
  const s = data?.summary

  // group by satellite pass date
  const groups = new Map<string, Alert[]>()
  data?.alerts.forEach((a) => groups.set(a.as_of, [...(groups.get(a.as_of) ?? []), a]))

  return (
    <div className="page">
      <PageHeader title="Alerts" subtitle="A change between two consecutive satellite passes. The Act List shows what is risky; alerts show what just got worse." />

      {s && (
        <div className="stat-row">
          <Stat label="Open" value={s.open} hint="Open or escalated, not yet handled" />
          <Stat label="Open critical" value={s.open_critical} color={s.open_critical ? SEVERITY_UI.critical.fill : undefined} />
          <Stat label="Latest pass" value={s.latest_pass} hint="Alerts raised by the most recent satellite pass" />
          <Stat label="Assigned" value={s.by_status.assigned + s.by_status.escalated} />
          <Stat label="Resolved" value={s.by_status.resolved} />
        </div>
      )}

      <div className="filters">
        <Segmented
          label="Filter by status"
          value={status}
          onChange={setStatus}
          options={[
            { value: '', label: 'All' },
            { value: 'open', label: 'Open', count: s?.by_status.open },
            { value: 'acknowledged', label: 'Acknowledged', count: s?.by_status.acknowledged },
            { value: 'assigned', label: 'Assigned', count: s?.by_status.assigned },
            { value: 'escalated', label: 'Escalated', count: s?.by_status.escalated },
            { value: 'resolved', label: 'Resolved', count: s?.by_status.resolved },
          ]}
        />
        <Segmented
          label="Filter by severity"
          value={severity}
          onChange={setSeverity}
          options={[
            { value: '', label: 'Any severity' },
            { value: 'critical', label: 'Critical' },
            { value: 'high', label: 'High' },
            { value: 'medium', label: 'Medium' },
            { value: 'info', label: 'Info' },
          ]}
        />
      </div>

      {isLoading && <Loading label="Comparing satellite passes" />}
      {error && <ErrorBox error={error} onRetry={() => refetch()} />}
      {data && data.count === 0 && (
        <Card>
          <Empty title="No alerts match">Nothing changed enough to alert on for this region and filter. That is good news.</Empty>
        </Card>
      )}

      {[...groups.entries()].map(([asOf, items]) => (
        <section key={asOf} className="alert-group" aria-label={`Alerts from ${asOf}`}>
          <h2 className="group-title">
            Pass of {shortDate(asOf)} <span className="muted">· {items.length} alert{items.length > 1 ? 's' : ''}</span>
          </h2>
          <div className="alert-list">
            {items.map((a) => (
              <AlertCard key={a.alert_id} a={a} />
            ))}
          </div>
        </section>
      ))}
    </div>
  )
}
