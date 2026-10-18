import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Bot, ClipboardCheck } from 'lucide-react'
import { api } from '../api/client'
import { WorkOrderPanel } from '../components/WorkOrderPanel'
import { Card, Chip, Empty, ErrorBox, Loading, Notice, PageHeader, Stat, TierBadge } from '../components/ui'
import { etaText, shortDate } from '../lib/format'
import { TIER_UI } from '../lib/tier'
import { useUi } from '../store'

export default function WorkOrdersPage() {
  const regionId = useUi((s) => s.regionId)
  const [picked, setPicked] = useState<string | null>(null)
  const { data, isLoading, error, refetch } = useQuery({ queryKey: ['workorders', regionId], queryFn: () => api.workOrderQueue(regionId) })
  const current = picked ?? data?.sites[0]?.site_id ?? null
  const agent = data?.agent

  return (
    <div className="page">
      <PageHeader title="Work Orders" subtitle="Inspection tickets for the sites that need action. Every number in a ticket comes from a computed tool result." />
      {isLoading && <Loading label="Loading queue" />}
      {error && <ErrorBox error={error} onRetry={() => refetch()} />}

      {data && agent && (
        <>
          <div className="stat-row compact">
            <Stat label="In queue" value={data.count} />
            <Stat label="Drafted" value={data.drafted} />
            <Stat label="Drafting mode" value={agent.gemini_configured ? 'Gemini' : 'Template'} sub={agent.gemini_configured ? agent.model : 'No API key'} />
          </div>
          {!agent.gemini_configured && (
            <Notice tone="info" icon={Bot}>
              Gemini is not configured, so tickets are drafted from a deterministic template using the same tool outputs. Set <code>TS_GEMINI_API_KEY</code> in <code>backend/.env</code> to enable model drafting.
            </Notice>
          )}

          {data.count === 0 ? (
            <Card>
              <Empty icon={ClipboardCheck} title="Queue is empty">No sites in this region need an inspection ticket right now.</Empty>
            </Card>
          ) : (
            <div className="split">
              <nav className="queue" aria-label="Work order queue">
                {data.sites.map((s) => (
                  <button key={s.site_id} className={`queue-row ${current === s.site_id ? 'on' : ''}`} aria-current={current === s.site_id} onClick={() => setPicked(s.site_id)} style={{ borderLeftColor: TIER_UI[s.tier].fill }}>
                    <div className="queue-top">
                      <TierBadge tier={s.tier} />
                      {s.work_order ? <Chip tone="ok">{s.work_order.ticket_id}</Chip> : <Chip>Not drafted</Chip>}
                    </div>
                    <strong>{s.label}</strong>
                    <span className="muted">
                      RPI {s.rpi.toFixed(0)} · outlook {etaText(s.eta_low_days, s.eta_high_days, s.outlook_status)}
                    </span>
                    {s.work_order && <span className="muted mono">drafted {shortDate(s.work_order.as_of)} · {s.work_order.generated_by}</span>}
                  </button>
                ))}
              </nav>
              <div className="split-main">{current && <WorkOrderPanel key={current} siteId={current} />}</div>
            </div>
          )}
        </>
      )}
    </div>
  )
}
