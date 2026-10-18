import { useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { MapPin, X } from 'lucide-react'
import { api } from '../api/client'
import type { SeismicContext, SiteDetail, TimeSeries } from '../api/types'
import { chainage, etaText, mm, mmMonth, shortDate } from '../lib/format'
import { navigate, useRoute } from '../lib/router'
import { STATE_LABEL, TIER_UI } from '../lib/tier'
import { useUi, type DrawerTab } from '../store'
import { EtaBand, SiteHistoryChart, TierTimeline } from './charts'
import { MotionChart } from './MotionChart'
import { Btn, Empty, ErrorBox, Loading, TierBadge } from './ui'
import { WorkOrderPanel } from './WorkOrderPanel'

const TABS: { id: DrawerTab; label: string }[] = [
  { id: 'now', label: 'Now' },
  { id: 'trend', label: 'Trend' },
  { id: 'history', label: 'History' },
  { id: 'outlook', label: 'Outlook' },
  { id: 'action', label: 'Action' },
]

function Metric({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="metric">
      <span className="label">{label}</span>
      <span className="metric-value mono">{value}</span>
      {sub && <span className="muted metric-sub">{sub}</span>}
    </div>
  )
}

function SeismicSection({ q }: { q: SeismicContext }) {
  if (!q.available) {
    return (
      <section>
        <h4 className="label">Earthquakes nearby (context)</h4>
        <p className="muted">{q.message ?? 'No earthquake catalog is stored yet.'} An administrator can download one in Data Hub, under Public data.</p>
      </section>
    )
  }
  const r = q.recent
  const big = q.history_largest
  return (
    <section>
      <h4 className="label">Earthquakes nearby (context)</h4>
      <p>
        <span className="mono">{q.recent_count ?? 0}</span> earthquake{q.recent_count === 1 ? '' : 's'} of M{r.min_magnitude}+ within <span className="mono">{r.radius_km} km</span> in the last {r.window_days} days
        {q.recent_max_magnitude != null && (
          <>
            , largest <span className="mono">M{q.recent_max_magnitude.toFixed(1)}</span>
          </>
        )}
        {q.recent_nearest_km != null && (
          <>
            , nearest <span className="mono">{q.recent_nearest_km.toFixed(0)} km</span> away
          </>
        )}
        .
      </p>
      {big && (
        <p className="secondary">
          Largest in the stored history within {q.history.radius_km} km: <span className="mono">M{big.mag.toFixed(1)}</span>, {big.place}, {shortDate(big.time)}.
        </p>
      )}
      {q.warnings?.map((w) => (
        <p key={w} className="muted warn-text">{w}</p>
      ))}
      <p className="muted">
        {q.note} Source: {q.source}.
      </p>
    </section>
  )
}

function NowTab({ d }: { d: SiteDetail }) {
  const m = d.metrics
  const pct = Math.min(100, (Math.abs(m.d_window_mm) / d.thresholds.operational_threshold_mm) * 100)
  const { data: hist } = useQuery({ queryKey: ['site-history', d.site_id], queryFn: () => api.siteHistory(d.site_id) })
  const prev = hist && hist.history.length > 1 ? hist.history[hist.history.length - 2] : null
  return (
    <div className="tab-body">
      <p className="headline">{d.state_reasons[0]}</p>

      {prev && (
        <p className="since">
          Previous pass ({shortDate(prev.as_of)}): <TierBadge tier={prev.tier} /> RPI <span className="mono">{prev.rpi.toFixed(0)}</span>
          {prev.tier !== d.tier && <strong> → now {d.tier.toLowerCase()}</strong>}
        </p>
      )}

      <div className="metric-grid">
        <Metric label="Recent speed" value={mmMonth(m.rate_recent_mm_month)} sub="last 60 days" />
        <Metric label="Baseline speed" value={mmMonth(m.rate_baseline_mm_month)} sub="earlier regime" />
        <Metric label="Acceleration" value={`${m.accel_ratio.toFixed(1)}x`} sub={`alert at ≥ ${d.thresholds.accel_ratio}x`} />
        <Metric label="Last 60 days" value={mm(m.d60_mm)} sub="cumulative" />
      </div>

      <div className="progress-block">
        <div className="progress-head">
          <span className="label">Toward operational threshold</span>
          <span className="mono">
            {mm(m.d_window_mm)} / {d.thresholds.operational_threshold_mm.toFixed(0)} mm
          </span>
        </div>
        <div className="progress-track" role="progressbar" aria-valuenow={Math.round(pct)} aria-valuemin={0} aria-valuemax={100} aria-label="Progress toward operational threshold">
          <div className="progress-fill" style={{ width: `${pct}%`, background: TIER_UI[d.tier].fill }} />
        </div>
        <div className="muted">
          over a {d.thresholds.window_days}-day window · projected crossing:{' '}
          <span className="mono secondary">{etaText(d.eta_low_days, d.eta_high_days, d.outlook_status)}</span>
        </div>
      </div>

      <section>
        <h4 className="label">Exposure</h4>
        <p>
          <strong>{d.asset_name}</strong> · criticality <span className="mono">{d.criticality.toFixed(2)}</span>
        </p>
        <p className="secondary">{d.consequence_note}</p>
      </section>

      <section>
        <h4 className="label">Trigger context</h4>
        {d.rain ? (
          <p>
            <span className="mono">{d.rain.rain_14d_mm.toFixed(0)} mm</span> rain in the last 14 days (peak day <span className="mono">{d.rain.peak_day_mm.toFixed(0)} mm</span>). Rain amplifies existing motion; it is
            not a hazard on its own. <span className="muted">Source: {d.rain.source}.</span>
          </p>
        ) : (
          <p className="muted">Rainfall unavailable: confidence reduced.</p>
        )}
      </section>

      {d.seismic && <SeismicSection q={d.seismic} />}

      <section>
        <h4 className="label">Why it ranks here</h4>
        <table className="mini-table">
          <tbody>
            <tr><td>Kinematic score</td><td className="mono">{d.rpi_breakdown.kinematic}</td></tr>
            <tr><td>Rain trigger</td><td className="mono">{d.rpi_breakdown.trigger}</td></tr>
            <tr><td>Hazard (rain amplifies motion)</td><td className="mono">{d.rpi_breakdown.hazard}</td></tr>
            <tr><td>Consequence factor</td><td className="mono">x {d.rpi_breakdown.consequence_factor}</td></tr>
            <tr><td>Confidence factor</td><td className="mono">x {d.rpi_breakdown.confidence_factor}</td></tr>
            <tr className="total"><td>Risk Priority Index</td><td className="mono">{d.rpi}</td></tr>
          </tbody>
        </table>
      </section>

      <section>
        <h4 className="label">Data quality</h4>
        <p>
          Confidence <strong>{d.confidence_detail.label}</strong> ({d.confidence_detail.score.toFixed(2)}) · coherence <span className="mono">{d.coherence_mean.toFixed(2)}</span> ·{' '}
          <span className="mono">{d.n_points}</span> scatterers · agreement <span className="mono">{(d.agreement * 100).toFixed(0)}%</span>
        </p>
      </section>
    </div>
  )
}

function ChartTab({ ts, mode, caption }: { ts: TimeSeries; mode: 'trend' | 'history' | 'outlook'; caption: string }) {
  return (
    <div className="tab-body">
      <MotionChart ts={ts} mode={mode} height={mode === 'history' ? 280 : 270} />
      <p className="muted chart-caption">{caption}</p>
    </div>
  )
}

function HistoryTab({ ts, siteId }: { ts: TimeSeries; siteId: string }) {
  const { data } = useQuery({ queryKey: ['site-history', siteId], queryFn: () => api.siteHistory(siteId) })
  return (
    <div className="tab-body">
      <h4 className="label">Displacement, full history</h4>
      <MotionChart ts={ts} mode="history" height={250} />
      <p className="muted chart-caption">Compare this season with the previous one to separate seasonal cycles from sustained creep.</p>

      <h4 className="label" style={{ marginTop: 18 }}>Risk across recent satellite passes</h4>
      {data && data.history.length > 1 ? (
        <>
          <TierTimeline history={data.history} />
          <SiteHistoryChart history={data.history} />
          <p className="muted chart-caption">Each pass re-runs the same analysis using only data available on that date. Oldest on the left.</p>
        </>
      ) : (
        <Empty title="No pass history yet">At least 12 satellite epochs are needed to reconstruct earlier passes.</Empty>
      )}
    </div>
  )
}

function OutlookTab({ d, ts }: { d: SiteDetail; ts: TimeSeries }) {
  const o = d.outlook
  return (
    <div className="tab-body">
      {ts.projection ? (
        <MotionChart ts={ts} mode="outlook" height={270} />
      ) : (
        <Empty title="No projection">{o.status === 'not_applicable' ? 'Data quality is insufficient or motion is not sustained.' : 'No crossing is expected.'}</Empty>
      )}
      <div className="outlook-band">
        <span className="label">Time to operational threshold</span>
        <span className="eta mono" style={{ color: TIER_UI[d.tier].strong }}>
          {etaText(o.eta_low_days, o.eta_high_days, o.status)}
        </span>
        <span className="muted">if the current regime continues</span>
        <EtaBand low={o.eta_low_days} high={o.eta_high_days} constant={o.eta_constant_days} accelerating={o.eta_accelerating_days} horizon={d.thresholds.approach_days} tier={d.tier} exceeded={o.status === 'threshold_exceeded'} />
        <span className="muted legend-line">Band spans both regimes · circle = constant speed · diamond = accelerating · dashed line = {d.thresholds.approach_days}-day planning horizon</span>
      </div>
      {(o.eta_constant_days || o.eta_accelerating_days) && (
        <p className="secondary">
          Constant-speed model: <span className="mono">{o.eta_constant_days ?? 'n/a'}</span> days · accelerating model: <span className="mono">{o.eta_accelerating_days ?? 'n/a'}</span> days.
        </p>
      )}
      <section>
        <h4 className="label">Assumptions</h4>
        <ul className="plain-list">
          {o.assumptions.map((a) => (
            <li key={a}>{a}</li>
          ))}
        </ul>
      </section>
      <p className="notice-line">This is a projection of the current trend. It is not a prediction of failure.</p>
    </div>
  )
}

export function SiteDrawer() {
  const siteId = useUi((s) => s.selectedSiteId)
  const tab = useUi((s) => s.tab)
  const setTab = useUi((s) => s.setTab)
  const select = useUi((s) => s.selectSite)
  const flyTo = useUi((s) => s.flyTo)
  const route = useRoute()

  const { data: d, isLoading, error, refetch } = useQuery({
    queryKey: ['site', siteId],
    queryFn: () => api.site(siteId!),
    enabled: !!siteId,
  })
  const { data: ts } = useQuery({
    queryKey: ['ts', siteId],
    queryFn: () => api.timeseries(siteId!),
    enabled: !!siteId,
  })

  useEffect(() => {
    if (!siteId) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && select(null)
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [siteId, select])

  if (!siteId) return null

  return (
    <aside className="drawer" aria-label="Site intelligence">
      <header className="drawer-head">
        <div>
          <div className="drawer-title">{d?.label ?? 'Loading...'}</div>
          {d && (
            <div className="drawer-sub">
              <TierBadge tier={d.tier} />
              <span className="secondary">{STATE_LABEL[d.state] ?? d.state}</span>
              <span className="muted mono">{chainage(d.chainage_start_km, d.chainage_end_km)}</span>
            </div>
          )}
        </div>
        <div className="drawer-tools">
          {d && route !== '/' && (
            <Btn
              small
              icon={MapPin}
              onClick={() => {
                navigate('/')
                flyTo([d.lon, d.lat], 14.5)
              }}
            >
              Map
            </Btn>
          )}
          <button className="icon-btn" onClick={() => select(null)} aria-label="Close site panel">
            <X size={16} />
          </button>
        </div>
      </header>

      <nav className="tabs" role="tablist">
        {TABS.map((t) => (
          <button key={t.id} role="tab" aria-selected={tab === t.id} className={tab === t.id ? 'active' : ''} onClick={() => setTab(t.id)}>
            {t.label}
          </button>
        ))}
      </nav>

      <div className="drawer-scroll">
        {isLoading && <Loading label="Loading site" />}
        {error && <ErrorBox error={error} onRetry={() => refetch()} />}
        {d && tab === 'now' && <NowTab d={d} />}
        {d && ts && tab === 'trend' && <ChartTab ts={ts} mode="trend" caption="Last 120 days. Bars show daily rainfall; the shaded band is the spread across scatterers at this site." />}
        {d && ts && tab === 'history' && <HistoryTab ts={ts} siteId={d.site_id} />}
        {d && ts && tab === 'outlook' && <OutlookTab d={d} ts={ts} />}
        {d && tab === 'action' && <WorkOrderPanel siteId={d.site_id} />}
      </div>
    </aside>
  )
}
