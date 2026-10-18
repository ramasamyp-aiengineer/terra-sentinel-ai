import { TrendingDown } from 'lucide-react'
import type { SiteSummary } from '../api/types'
import { etaText, mmMonth } from '../lib/format'
import { STATE_LABEL, TIER_UI } from '../lib/tier'
import { useUi } from '../store'
import { Empty, TierBadge } from './ui'

export function ActList({ sites, emptyText = 'No sites need attention in this region.' }: { sites: SiteSummary[]; emptyText?: string }) {
  const selected = useUi((s) => s.selectedSiteId)
  const select = useUi((s) => s.selectSite)

  if (!sites.length) return <Empty title="All clear">{emptyText}</Empty>

  return (
    <ol className="act-list">
      {sites.map((s, i) => (
        <li key={s.site_id}>
          <button className={`act-row ${selected === s.site_id ? 'selected' : ''}`} style={{ borderLeftColor: TIER_UI[s.tier].fill }} onClick={() => select(s.site_id, 'now')}>
            <div className="act-top">
              <span className="act-rank mono">{i + 1}</span>
              <TierBadge tier={s.tier} />
              <span className="act-rpi mono" title="Risk Priority Index (hazard x consequence x confidence)">
                RPI {s.rpi.toFixed(0)}
              </span>
            </div>
            <div className="act-title">{s.label}</div>
            <div className="act-meta secondary">
              <span className="act-trend" style={{ color: TIER_UI[s.tier].strong }}>
                <TrendingDown size={13} strokeWidth={2} aria-hidden /> {mmMonth(s.rate_recent_mm_month)}
              </span>
              <span>{STATE_LABEL[s.state] ?? s.state}</span>
            </div>
            <div className="act-meta muted">
              <span>
                To threshold: <span className="mono secondary">{etaText(s.eta_low_days, s.eta_high_days, s.outlook_status)}</span>
              </span>
              <span>conf. {s.confidence_label}</span>
            </div>
          </button>
        </li>
      ))}
    </ol>
  )
}
