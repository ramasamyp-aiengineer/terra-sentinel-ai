import { Area, AreaChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { SiteHistoryPoint, Tier, TrendPoint } from '../api/types'
import { TIER_LABEL, TIER_ORDER, TIER_UI } from '../lib/tier'
import { shortDate } from '../lib/format'

const AXIS = '#5E6C7E'
const GRID = '#E7EBF0'

/* ------------------------------------------------------------------ ETA band */

const MAX_DAYS = 365

/** Time-to-threshold as a band on a 0-365 day axis, with the planning horizon marked. */
export function EtaBand({
  low,
  high,
  constant,
  accelerating,
  horizon,
  tier,
  exceeded = false,
}: {
  low: number | null
  high: number | null
  constant?: number | null
  accelerating?: number | null
  horizon?: number
  tier: Tier
  exceeded?: boolean
}) {
  const W = 100
  const x = (d: number) => Math.min(W, Math.max(0, (d / MAX_DAYS) * W))
  const color = TIER_UI[tier].fill
  const desc = exceeded
    ? 'Threshold exceeded'
    : low != null && high != null
      ? `Projected crossing in ${low} to ${high} days`
      : 'No crossing expected within a year'
  return (
    <div className="etaband" role="img" aria-label={desc}>
      <svg viewBox="0 0 100 22" preserveAspectRatio="none">
        <rect x="0" y="9" width="100" height="4" rx="2" fill="#EEF1F5" />
        {horizon != null && <line x1={x(horizon)} x2={x(horizon)} y1="2" y2="20" stroke="#8795A6" strokeWidth="0.5" strokeDasharray="1.5 1.5" vectorEffect="non-scaling-stroke" />}
        {exceeded ? (
          <rect x="0" y="6" width="100" height="10" rx="2" fill={color} opacity="0.9" />
        ) : (
          low != null &&
          high != null && <rect x={x(low)} y="6" width={Math.max(1.2, x(high) - x(low))} height="10" rx="2" fill={color} opacity="0.9" />
        )}
        {!exceeded && constant != null && <circle cx={x(constant)} cy="11" r="1.6" fill="#fff" stroke="#46566A" strokeWidth="0.6" vectorEffect="non-scaling-stroke" />}
        {!exceeded && accelerating != null && <rect x={x(accelerating) - 1.4} y="9.6" width="2.8" height="2.8" transform={`rotate(45 ${x(accelerating)} 11)`} fill="#fff" stroke="#46566A" strokeWidth="0.6" vectorEffect="non-scaling-stroke" />}
      </svg>
      <div className="etaband-axis mono" aria-hidden>
        <span>0</span>
        <span>90</span>
        <span>180</span>
        <span>270</span>
        <span>365 d</span>
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ chainage strip */

export function ChainageStrip({
  items,
  onSelect,
  selected,
}: {
  items: { site_id: string; km_start: number; km_end: number; tier: Tier; rpi: number; rate_mm_month: number }[]
  onSelect?: (id: string) => void
  selected?: string | null
}) {
  if (!items.length) return <div className="muted">No sites</div>
  const start = items[0].km_start
  const end = items[items.length - 1].km_end
  const total = Math.max(end - start, 0.25)
  const ticks: number[] = []
  const step = total > 12 ? 2 : 1
  for (let k = Math.ceil(start / step) * step; k <= end; k += step) ticks.push(k)
  return (
    <div className="strip">
      <div className="strip-bar" role="list" aria-label="Sites along the asset, by chainage">
        {items.map((s) => (
          <button
            key={s.site_id}
            role="listitem"
            className={`strip-seg ${selected === s.site_id ? 'sel' : ''}`}
            style={{ left: `${((s.km_start - start) / total) * 100}%`, width: `calc(${((s.km_end - s.km_start) / total) * 100}% - 1px)`, background: TIER_UI[s.tier].fill }}
            onClick={() => onSelect?.(s.site_id)}
            title={`KM ${s.km_start.toFixed(2)}-${s.km_end.toFixed(2)} · ${TIER_LABEL[s.tier]} · RPI ${s.rpi.toFixed(0)} · ${Math.abs(s.rate_mm_month).toFixed(1)} mm/month`}
            aria-label={`KM ${s.km_start.toFixed(2)} to ${s.km_end.toFixed(2)}, ${TIER_LABEL[s.tier]}, RPI ${s.rpi.toFixed(0)}`}
          />
        ))}
      </div>
      <div className="strip-axis mono" aria-hidden>
        {ticks.map((k) => (
          <span key={k} style={{ left: `${((k - start) / total) * 100}%` }}>
            {k}
          </span>
        ))}
        <em>km</em>
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ sparkline */

export function Sparkline({ values, color = '#0F766E', width = 96, height = 26 }: { values: number[]; color?: string; width?: number; height?: number }) {
  if (values.length < 2) return <span className="muted">-</span>
  const min = Math.min(...values)
  const max = Math.max(...values)
  const span = max - min || 1
  const pts = values.map((v, i) => [(i / (values.length - 1)) * (width - 4) + 2, height - 3 - ((v - min) / span) * (height - 6)] as const)
  const last = pts[pts.length - 1]
  return (
    <svg width={width} height={height} className="spark" aria-hidden>
      <polyline points={pts.map((p) => p.join(',')).join(' ')} fill="none" stroke={color} strokeWidth="1.6" strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={last[0]} cy={last[1]} r="2.4" fill={color} />
    </svg>
  )
}

/* ------------------------------------------------------------------ tier trend */

const tickDate = (s: string) => new Date(s).toLocaleDateString('en-GB', { day: '2-digit', month: 'short' })

export function TierTrend({ series, height = 260 }: { series: TrendPoint[]; height?: number }) {
  const rows = series.map((p) => ({ as_of: p.as_of, ...p.counts }))
  const order: Tier[] = ['STABLE', 'WEAK', 'WATCH', 'ELEVATED', 'CRITICAL']
  const hidden = new Set<Tier>(['STABLE'])
  return (
    <div style={{ width: '100%', height }} role="img" aria-label="Number of sites per risk tier over recent satellite passes">
      <ResponsiveContainer>
        <AreaChart data={rows} margin={{ top: 8, right: 12, bottom: 0, left: -12 }}>
          <CartesianGrid stroke={GRID} vertical={false} />
          <XAxis dataKey="as_of" tickFormatter={tickDate} tick={{ fill: AXIS, fontSize: 11 }} stroke={GRID} minTickGap={24} />
          <YAxis allowDecimals={false} tick={{ fill: AXIS, fontSize: 11 }} stroke={GRID} width={40} />
          <Tooltip contentStyle={{ border: '1px solid #D5DBE3', borderRadius: 6, fontSize: 12 }} labelFormatter={(l) => shortDate(String(l))} />
          <Legend wrapperStyle={{ fontSize: 12 }} iconSize={10} formatter={(v) => TIER_LABEL[v as Tier]} />
          {order
            .filter((t) => !hidden.has(t))
            .map((t) => (
              <Area key={t} type="monotone" dataKey={t} name={t} stackId="1" stroke={TIER_UI[t].fill} fill={TIER_UI[t].fill} fillOpacity={0.85} isAnimationActive={false} />
            ))}
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}

export function RpiTrend({ series, height = 200 }: { series: TrendPoint[]; height?: number }) {
  return (
    <div style={{ width: '100%', height }} role="img" aria-label="Highest and average Risk Priority Index over recent satellite passes">
      <ResponsiveContainer>
        <LineChart data={series} margin={{ top: 8, right: 12, bottom: 0, left: -12 }}>
          <CartesianGrid stroke={GRID} vertical={false} />
          <XAxis dataKey="as_of" tickFormatter={tickDate} tick={{ fill: AXIS, fontSize: 11 }} stroke={GRID} minTickGap={24} />
          <YAxis domain={[0, 100]} tick={{ fill: AXIS, fontSize: 11 }} stroke={GRID} width={40} />
          <Tooltip contentStyle={{ border: '1px solid #D5DBE3', borderRadius: 6, fontSize: 12 }} labelFormatter={(l) => shortDate(String(l))} />
          <Legend wrapperStyle={{ fontSize: 12 }} iconSize={10} />
          <Line type="monotone" dataKey="max_rpi" name="Highest RPI" stroke="#C62828" strokeWidth={2} dot={false} isAnimationActive={false} />
          <Line type="monotone" dataKey="mean_act_rpi" name="Average RPI of action sites" stroke="#0F766E" strokeWidth={2} dot={false} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

export function SiteHistoryChart({ history, height = 210 }: { history: SiteHistoryPoint[]; height?: number }) {
  const rows = history.map((h) => ({ ...h, speed: Math.abs(h.rate_mm_month) }))
  return (
    <div style={{ width: '100%', height }} role="img" aria-label="Risk Priority Index and speed of this site over recent satellite passes">
      <ResponsiveContainer>
        <LineChart data={rows} margin={{ top: 8, right: 8, bottom: 0, left: -12 }}>
          <CartesianGrid stroke={GRID} vertical={false} />
          <XAxis dataKey="as_of" tickFormatter={tickDate} tick={{ fill: AXIS, fontSize: 11 }} stroke={GRID} minTickGap={24} />
          <YAxis yAxisId="rpi" domain={[0, 100]} tick={{ fill: AXIS, fontSize: 11 }} stroke={GRID} width={40} />
          <YAxis yAxisId="spd" orientation="right" tick={{ fill: AXIS, fontSize: 11 }} stroke={GRID} width={36} />
          <Tooltip contentStyle={{ border: '1px solid #D5DBE3', borderRadius: 6, fontSize: 12 }} labelFormatter={(l) => shortDate(String(l))} />
          <Legend wrapperStyle={{ fontSize: 12 }} iconSize={10} />
          <Line yAxisId="rpi" type="monotone" dataKey="rpi" name="RPI" stroke="#C62828" strokeWidth={2} dot={{ r: 2 }} isAnimationActive={false} />
          <Line yAxisId="spd" type="monotone" dataKey="speed" name="Speed (mm/month)" stroke="#0F766E" strokeWidth={2} strokeDasharray="4 3" dot={false} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

/** Tiny tier history strip (one cell per pass, oldest to newest). */
export function TierTimeline({ history }: { history: SiteHistoryPoint[] }) {
  return (
    <div className="timeline" role="img" aria-label={`Tier at each of the last ${history.length} passes: ${history.map((h) => TIER_LABEL[h.tier]).join(', ')}`}>
      {history.map((h) => (
        <span key={h.as_of} style={{ background: TIER_UI[h.tier].fill }} title={`${shortDate(h.as_of)}: ${TIER_LABEL[h.tier]} (RPI ${h.rpi.toFixed(0)})`} />
      ))}
    </div>
  )
}

export { TIER_ORDER }
