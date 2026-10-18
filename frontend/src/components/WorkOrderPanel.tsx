import { useEffect, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, FileText, Printer, ShieldCheck, Sparkles } from 'lucide-react'
import { api } from '../api/client'
import type { WorkOrder } from '../api/types'
import { useCan } from '../lib/auth'
import { TIER_UI } from '../lib/tier'
import { TierBadge } from './ui'

export function WorkOrderPanel({ siteId }: { siteId: string }) {
  const qc = useQueryClient()
  const canDraft = useCan('analyst')
  const [geminiUpgrade, setGeminiUpgrade] = useState<'idle' | 'running' | 'done' | 'skip'>('idle')

  // Instant: deterministic template (same tools / numbers). Then upgrade with Gemini in the background.
  const { data: wo, isLoading, error, refetch, isFetching } = useQuery({
    queryKey: ['workorder', siteId],
    queryFn: async () => {
      const draft = await api.workOrder(siteId, false, 'template')
      qc.invalidateQueries({ queryKey: ['workorders'] })
      return draft
    },
    staleTime: Infinity,
    enabled: canDraft,
  })

  useEffect(() => {
    if (!canDraft || !wo || geminiUpgrade !== 'idle') return
    let cancelled = false
    setGeminiUpgrade('running')
    api
      .workOrder(siteId, false, 'auto')
      .then((upgraded) => {
        if (cancelled) return
        qc.setQueryData(['workorder', siteId], upgraded)
        qc.invalidateQueries({ queryKey: ['workorders'] })
        setGeminiUpgrade(upgraded.generated_by === 'gemini' ? 'done' : 'skip')
      })
      .catch(() => {
        if (!cancelled) setGeminiUpgrade('skip')
      })
    return () => {
      cancelled = true
    }
  }, [canDraft, wo, siteId, geminiUpgrade, qc])

  if (!canDraft) {
    return (
      <div className="notice notice-info" role="note">
        <div>Drafting a work order needs the Analyst role. Tickets that already exist are listed under Work Orders.</div>
      </div>
    )
  }
  if (isLoading) {
    return (
      <div className="wo-loading">
        <Sparkles size={16} className="spin" /> Assembling evidence from site metrics…
      </div>
    )
  }
  if (error || !wo) {
    return (
      <div className="error-box">
        Could not generate the work order. {(error as Error)?.message}{' '}
        <button className="btn-secondary" onClick={() => refetch()}>
          Retry
        </button>
      </div>
    )
  }

  return (
    <WorkOrderBody
      wo={wo}
      enhancing={geminiUpgrade === 'running'}
      busy={isFetching}
      onRegenerate={() => {
        setGeminiUpgrade('idle')
        api.workOrder(siteId, true, 'auto').then((next) => {
          qc.setQueryData(['workorder', siteId], next)
          qc.invalidateQueries({ queryKey: ['workorders'] })
          setGeminiUpgrade(next.generated_by === 'gemini' ? 'done' : 'skip')
        })
      }}
    />
  )
}

function WorkOrderBody({
  wo,
  enhancing,
  busy,
  onRegenerate,
}: {
  wo: WorkOrder
  enhancing: boolean
  busy: boolean
  onRegenerate: () => void
}) {
  return (
    <article className="workorder" style={{ borderTopColor: TIER_UI[wo.tier].fill }}>
      <header className="wo-head">
        <div className="wo-id mono">{wo.ticket_id}</div>
        <div className="wo-priority">
          <TierBadge tier={wo.tier} />
          <span>{wo.priority_label}</span>
        </div>
        <div className="wo-asset">
          <strong>{wo.asset_name}</strong>
          <span className="mono secondary">{wo.chainage}</span>
        </div>
        <div className="muted mono">
          {wo.lat.toFixed(5)}, {wo.lon.toFixed(5)} · as of {wo.as_of}
        </div>
      </header>

      <div className="wo-provenance">
        <span className="chip" title={wo.model ?? 'Deterministic template'}>
          <Sparkles size={12} /> {wo.generated_by === 'gemini' ? `Gemini (${wo.model})` : 'Grounded template'}
        </span>
        <span className={`chip ${wo.validation.passed ? 'chip-ok' : 'chip-bad'}`} title={wo.validation.issues.join('\n')}>
          <ShieldCheck size={12} /> Numbers verified against tools ({wo.validation.numbers_checked})
        </span>
        {wo.tool_calls.length > 0 && <span className="chip">{wo.tool_calls.length} tool calls</span>}
        {enhancing && (
          <span className="chip chip-brand">
            <Sparkles size={12} className="spin" /> Gemini refining…
          </span>
        )}
      </div>

      <section>
        <h3 className="label">Grounded brief</h3>
        <p className="wo-summary">{wo.summary}</p>
      </section>

      <section>
        <h3 className="label">Evidence</h3>
        <dl className="evidence">
          {wo.evidence.map((e) => (
            <div key={e.label} className="evidence-row">
              <dt>{e.label}</dt>
              <dd className="mono">{e.value}</dd>
              <span className="src muted">{e.source}</span>
            </div>
          ))}
        </dl>
      </section>

      <section>
        <h3 className="label">Outlook</h3>
        <p>{wo.outlook_text}</p>
      </section>

      <section>
        <h3 className="label">Likely mechanism (hypothesis)</h3>
        <p>{wo.mechanism_hypothesis}</p>
      </section>

      <section>
        <h3 className="label">Recommended action</h3>
        <p className="wo-action">{wo.recommended_action}</p>
      </section>

      <section>
        <h3 className="label">Field checklist</h3>
        <ul className="checklist">
          {wo.checklist.map((c) => (
            <li key={c.item}>
              <span className="box" aria-hidden />
              <div>
                {c.item}
                {c.why && <div className="muted why">{c.why}</div>}
              </div>
            </li>
          ))}
        </ul>
      </section>

      <section className="limits">
        <h3 className="label" style={{ color: 'var(--info)' }}>
          Limitations
        </h3>
        <ul>
          {wo.limitations.map((l) => (
            <li key={l}>{l}</li>
          ))}
        </ul>
      </section>

      <footer className="wo-foot muted">{wo.citations.join(' · ')}</footer>

      <div className="wo-actions no-print">
        <button className="btn-primary" onClick={() => window.print()}>
          <Printer size={14} /> Print / save PDF
        </button>
        <button className="btn-secondary" onClick={() => navigator.clipboard?.writeText(wo.ticket_id)}>
          <FileText size={14} /> Copy ticket ID
        </button>
        <button className="btn-secondary" disabled={busy || enhancing} onClick={onRegenerate}>
          <Check size={14} /> Regenerate
        </button>
      </div>
    </article>
  )
}
