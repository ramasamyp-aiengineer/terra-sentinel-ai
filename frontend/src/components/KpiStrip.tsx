import type { RegionSummary } from '../api/types'
import { TIER_UI } from '../lib/tier'
import { Stat } from './ui'

export function KpiStrip({ data }: { data: RegionSummary }) {
  const c = data.by_tier
  return (
    <div className="kpi-grid">
      <Stat label="Critical" value={c.CRITICAL} color={c.CRITICAL ? TIER_UI.CRITICAL.fill : undefined} hint="Sites needing urgent field investigation" />
      <Stat label="Elevated" value={c.ELEVATED} color={c.ELEVATED ? TIER_UI.ELEVATED.fill : undefined} hint="Sites to plan an inspection for" />
      <Stat label="Accelerating" value={data.accelerating_sites} hint="Sites whose speed has risen versus their own baseline" />
      <Stat label="Threshold ≤ 60 d" value={data.approaching_threshold_60d} hint="Projected to reach the operational threshold within 60 days if the trend continues" />
    </div>
  )
}
