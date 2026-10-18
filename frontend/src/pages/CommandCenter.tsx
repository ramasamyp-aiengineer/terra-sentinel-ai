import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ArrowRight, X } from 'lucide-react'
import { api } from '../api/client'
import { ActList } from '../components/ActList'
import { KpiStrip } from '../components/KpiStrip'
import { MapView } from '../components/MapView'
import { Chip, ErrorBox, Loading, TierBar } from '../components/ui'
import { SEVERITY_UI } from '../lib/tier'
import { navigate } from '../lib/router'
import { useUi } from '../store'

const SEEN_KEY = 'terrasentinel.howto.v1'

/** First-run orientation in plain words. Dismissed for good once understood. */
function HowTo() {
  const [open, setOpen] = useState(() => {
    try {
      return localStorage.getItem(SEEN_KEY) !== '1'
    } catch {
      return true
    }
  })
  if (!open) return null
  const close = () => {
    try {
      localStorage.setItem(SEEN_KEY, '1')
    } catch {
      /* private mode: just hide for this session */
    }
    setOpen(false)
  }
  return (
    <aside className="howto" aria-label="How to read this screen">
      <div className="howto-head">
        <strong>How to read this</strong>
        <button className="icon-btn" onClick={close} aria-label="Dismiss this guide">
          <X size={15} />
        </button>
      </div>
      <ol>
        <li>Satellites measure how the ground moves under roads, metro lines and dams, down to millimetres.</li>
        <li>
          <strong>Act today</strong> lists the few places that need a person to go and look. Red is most urgent.
        </li>
        <li>
          <strong>To threshold</strong> is a range of days until a place reaches its safety limit <em>if the trend continues</em>. It is not a failure date.
        </li>
      </ol>
      <button className="link-btn" onClick={() => navigate('/methodology')}>
        How it works <ArrowRight size={12} aria-hidden />
      </button>
    </aside>
  )
}
export default function CommandCenter() {
  const regionId = useUi((s) => s.regionId)
  const select = useUi((s) => s.selectSite)
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['summary', regionId],
    queryFn: () => api.regionSummary(regionId),
    staleTime: 60_000,
  })
  // Alerts can wait a beat — summary + map are what make Command Center feel ready.
  const { data: alerts } = useQuery({
    queryKey: ['alerts', regionId, '', ''],
    queryFn: () => api.alerts(regionId),
    staleTime: 60_000,
    enabled: !!data,
  })
  const fresh = alerts?.alerts.filter((a) => a.pass_index === 0 && a.severity !== 'info' && a.status === 'open').slice(0, 3) ?? []

  return (
    <div className="cc">
      <section className="cc-panel" aria-label="Decisions">
        <div className="panel-head">
          <div>
            <h1>{data?.region?.name ?? 'Region'}</h1>
            <span className="muted">{data ? `${data.total_sites} monitored sites` : ' '}</span>
          </div>
          {data && <TierBar counts={data.by_tier} height={8} />}
        </div>

        {isLoading && <Loading label="Loading region" />}
        {error && <ErrorBox error={error} onRetry={() => refetch()} />}

        {data && (
          <>
            <HowTo />
            <KpiStrip data={data} />

            {fresh.length > 0 && (
              <div className="cc-changes">
                <div className="section-head">
                  <h2 className="label">New since last pass</h2>
                  <button className="link-btn" onClick={() => navigate('/alerts')}>
                    All alerts <ArrowRight size={12} aria-hidden />
                  </button>
                </div>
                {fresh.map((a) => (
                  <button key={a.alert_id} className="change-row" onClick={() => (a.site_id ? select(a.site_id, 'now') : navigate('/alerts'))}>
                    <i style={{ background: SEVERITY_UI[a.severity].fill }} aria-hidden />
                    <span>{a.title}</span>
                    <Chip tone={a.severity === 'critical' ? 'bad' : 'warn'}>{SEVERITY_UI[a.severity].label}</Chip>
                  </button>
                ))}
              </div>
            )}

            <div className="section-head">
              <h2 className="label">Act today</h2>
              <span className="muted">
                {data.act_list.length} of {data.total_sites} sites
              </span>
            </div>
            <div className="panel-scroll">
              <ActList sites={data.act_list} />
            </div>
          </>
        )}
      </section>

      <section className="cc-stage">
        <MapView />
      </section>
    </div>
  )
}
