import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ArrowDownRight, ArrowUpRight, ChevronDown, ChevronRight, FlaskConical, Minus } from 'lucide-react'
import { api } from '../api/client'
import type { EarlyWarningSite } from '../api/types'
import { EtaBand } from '../components/charts'
import { Btn, Card, Chip, Empty, ErrorBox, Loading, Notice, PageHeader, Segmented, TierBadge } from '../components/ui'
import { etaText, mmMonth } from '../lib/format'
import { STATE_LABEL, TIER_UI } from '../lib/tier'
import { useUi } from '../store'

const BUCKET_TONE: Record<string, string> = { exceeded: '#C62828', d0_30: '#C62828', d31_60: '#B85209', d61_120: '#B58900', d121_365: '#3B6E8F', none: '#6B7785' }

function WhatIf({ s }: { s: EarlyWarningSite }) {
  const [pct, setPct] = useState(0)
  const [debounced, setDebounced] = useState(0)
  useEffect(() => {
    const t = setTimeout(() => setDebounced(pct), 200)
    return () => clearTimeout(t)
  }, [pct])
  const { data, error } = useQuery({ queryKey: ['scenario', s.site_id, debounced], queryFn: () => api.scenario(s.site_id, debounced), placeholderData: (p) => p })

  const fmt = (d: number | null | undefined) => (d == null ? 'no crossing' : d === 0 ? 'already exceeded' : `${d} days`)
  return (
    <div className="whatif">
      <div className="whatif-head">
        <FlaskConical size={15} aria-hidden /> <strong>What if the speed changes?</strong>
        <span className="muted">Move the slider to rescale today's {mmMonth(s.rate_recent_mm_month)}.</span>
      </div>
      <div className="whatif-body">
        <label className="slider">
          <span className="mono">{pct > 0 ? `+${pct}` : pct}% speed</span>
          <input type="range" min={-50} max={100} step={10} value={pct} onChange={(e) => setPct(Number(e.target.value))} aria-label="Change in speed, percent" />
          <span className="slider-scale mono"><span>-50%</span><span>0</span><span>+100%</span></span>
        </label>
        {error && <ErrorBox error={error} />}
        {data && (
          <dl className="whatif-out">
            <div>
              <dt>Remaining to threshold</dt>
              <dd className="mono">{data.remaining_mm.toFixed(1)} mm</dd>
            </div>
            <div>
              <dt>Speed</dt>
              <dd className="mono">{data.scenario_rate_mm_month.toFixed(1)} mm/month</dd>
            </div>
            <div>
              <dt>Linear estimate (today)</dt>
              <dd className="mono">{fmt(data.linear_days_current)}</dd>
            </div>
            <div className="hl">
              <dt>Linear estimate (scenario)</dt>
              <dd className="mono">{fmt(data.linear_days_scenario)}</dd>
            </div>
            <div>
              <dt>Engine band (authoritative)</dt>
              <dd className="mono">{data.engine_band_days[0] != null ? `${data.engine_band_days[0]}-${data.engine_band_days[1]} days` : 'n/a'}</dd>
            </div>
          </dl>
        )}
        {data && data.within_planning_horizon && <Notice tone="warn">At this speed the threshold would fall inside the {data.approach_days}-day planning horizon.</Notice>}
        <p className="muted">{data?.note}</p>
      </div>
    </div>
  )
}

function Row({ s }: { s: EarlyWarningSite }) {
  const select = useUi((st) => st.selectSite)
  const [open, setOpen] = useState(false)
  const d = s.rpi_delta
  const Trend = d == null || Math.abs(d) < 0.5 ? Minus : d > 0 ? ArrowUpRight : ArrowDownRight
  const exceeded = s.outlook_status === 'threshold_exceeded'
  return (
    <>
      <tr className={open ? 'row-open' : ''}>
        <td>
          <button className="row-title" onClick={() => select(s.site_id, 'outlook')}>
            {s.label}
          </button>
          <div className="muted">{s.asset_name.split(' (')[0]} · {STATE_LABEL[s.state] ?? s.state}</div>
        </td>
        <td>
          <TierBadge tier={s.tier} />
        </td>
        <td className="cell-progress">
          <div className="progress-track slim" role="progressbar" aria-valuenow={Math.round(s.progress_pct)} aria-valuemin={0} aria-valuemax={100} aria-label="Progress to threshold">
            <div className="progress-fill" style={{ width: `${Math.min(100, s.progress_pct)}%`, background: TIER_UI[s.tier].fill }} />
          </div>
          <span className="mono muted">
            {s.progress_mm.toFixed(0)} / {s.threshold_mm.toFixed(0)} mm
          </span>
        </td>
        <td className="cell-band">
          <EtaBand low={s.eta_low_days} high={s.eta_high_days} constant={s.eta_constant_days} accelerating={s.eta_accelerating_days} horizon={60} tier={s.tier} exceeded={exceeded} />
        </td>
        <td className="num mono">
          <strong>{etaText(s.eta_low_days, s.eta_high_days, s.outlook_status)}</strong>
        </td>
        <td className="num mono" title="Change in RPI since the previous satellite pass">
          <span className={`delta ${d != null && d > 0.5 ? 'up' : d != null && d < -0.5 ? 'down' : ''}`}>
            <Trend size={13} aria-hidden /> {d == null ? '-' : `${d > 0 ? '+' : ''}${d.toFixed(0)}`}
          </span>
        </td>
        <td className="num">
          <Btn small variant="ghost" icon={open ? ChevronDown : ChevronRight} onClick={() => setOpen((v) => !v)} aria-expanded={open}>
            What-if
          </Btn>
        </td>
      </tr>
      {open && (
        <tr className="row-detail">
          <td colSpan={7}>
            <WhatIf s={s} />
            {s.assumptions.length > 0 && (
              <details className="assump">
                <summary>Assumptions behind this outlook</summary>
                <ul className="plain-list">
                  {s.assumptions.map((a) => (
                    <li key={a}>{a}</li>
                  ))}
                </ul>
              </details>
            )}
          </td>
        </tr>
      )}
    </>
  )
}

export default function EarlyWarningPage() {
  const regionId = useUi((s) => s.regionId)
  const [bucket, setBucket] = useState('')
  const [type, setType] = useState('')
  const { data, isLoading, error, refetch } = useQuery({ queryKey: ['early-warning', regionId, type], queryFn: () => api.earlyWarning(regionId, type || undefined) })
  const rows = (data?.sites ?? []).filter((s) => !bucket || s.bucket === bucket)

  return (
    <div className="page">
      <PageHeader
        title="Early Warning"
        subtitle="How long until a moving site reaches its operational threshold, if the current motion continues. A band, not a date."
        actions={<Segmented label="Asset type" value={type} onChange={setType} options={[{ value: '', label: 'All assets' }, { value: 'HIGHWAY', label: 'Highway' }, { value: 'METRO', label: 'Metro' }, { value: 'DAM', label: 'Dam' }]} />}
      />

      {isLoading && <Loading label="Computing outlooks" />}
      {error && <ErrorBox error={error} onRetry={() => refetch()} />}

      {data && (
        <>
          <div className="bucket-row" role="group" aria-label="Filter by time to threshold">
            {data.buckets.map((b) => (
              <button key={b.key} className={`bucket ${bucket === b.key ? 'on' : ''}`} aria-pressed={bucket === b.key} onClick={() => setBucket(bucket === b.key ? '' : b.key)} style={{ ['--bucket' as string]: BUCKET_TONE[b.key] }}>
                <span className="bucket-count mono">{b.count}</span>
                <span className="bucket-label">{b.label}</span>
              </button>
            ))}
          </div>

          <Card flush>
            {rows.length === 0 ? (
              <Empty title="Nothing in this window">No moving sites match this time-to-threshold filter.</Empty>
            ) : (
              <div className="table-wrap">
                <table className="table board">
                  <caption className="sr-only">Sites ordered by time to operational threshold</caption>
                  <thead>
                    <tr>
                      <th>Site</th>
                      <th>Tier</th>
                      <th>Progress</th>
                      <th>Time to threshold, 0-365 days</th>
                      <th className="num">Outlook</th>
                      <th className="num" title="Change in RPI since the previous pass">Δ RPI</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((s) => (
                      <Row key={s.site_id} s={s} />
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
          <div className="legend-row">
            <Chip>Bar = band from both regimes</Chip>
            <Chip>Circle = constant speed</Chip>
            <Chip>Diamond = accelerating</Chip>
            <Chip>Dashed = 60-day planning horizon</Chip>
          </div>
          <p className="muted foot-note">{data.note}</p>
        </>
      )}
    </div>
  )
}
