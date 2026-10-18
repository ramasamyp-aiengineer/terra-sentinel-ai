import { useQuery } from '@tanstack/react-query'
import { CloudRain } from 'lucide-react'
import { api } from '../api/client'
import { ActList } from '../components/ActList'
import { Card, Chip, DataTable, ErrorBox, Loading, Notice, PageHeader, Stat, TierBadge, TierBar } from '../components/ui'
import { shortDate } from '../lib/format'
import { navigate } from '../lib/router'
import { TIER_UI } from '../lib/tier'
import { useUi } from '../store'

export default function PortfolioPage() {
  const regionId = useUi((s) => s.regionId)
  const setRegion = useUi((s) => s.setRegion)
  const { data, isLoading, error, refetch } = useQuery({ queryKey: ['portfolio', regionId], queryFn: () => api.portfolio(regionId) })

  return (
    <div className="page">
      <PageHeader title="Portfolio" subtitle="The whole estate in one view: where risk is concentrated, how fresh the data is, and what the rain is doing." />
      {isLoading && <Loading label="Rolling up regions" />}
      {error && <ErrorBox error={error} onRetry={() => refetch()} />}

      {data && (
        <>
          {!data.data_health.fresh && (
            <Notice tone="warn">
              The latest satellite epoch is {data.data_health.days_since_last_epoch} days old ({shortDate(data.data_health.last_epoch)}). Outlooks are measured against the newest data, not today.
            </Notice>
          )}
          <div className="stat-row">
            <Stat label="Monitored sites" value={data.totals.sites.toLocaleString()} sub={`${data.totals.assets} assets · ${data.totals.points.toLocaleString()} points`} />
            <Stat label="Need action" value={data.totals.act_sites} color={data.totals.act_sites ? TIER_UI.ELEVATED.fill : undefined} />
            <Stat label="Critical" value={data.totals.tier_counts.CRITICAL} color={data.totals.tier_counts.CRITICAL ? TIER_UI.CRITICAL.fill : undefined} />
            <Stat label="Earliest outlook" value={data.totals.earliest_eta_days != null ? `${data.totals.earliest_eta_days} d` : 'none'} />
            <Stat label="Data health" value={data.data_health.fresh ? 'Fresh' : 'Stale'} sub={`${data.data_health.epochs} epochs · ${data.data_health.weak_sites} weak sites`} />
          </div>

          <Card title={data.region ? 'Breakdown' : 'By region'} subtitle="Click a row to scope the whole app to that region." flush>
            <DataTable caption="Risk by region">
              <thead>
                <tr>
                  <th>Region</th>
                  <th>Level</th>
                  <th style={{ width: '26%' }}>Tiers</th>
                  <th className="num">Sites</th>
                  <th className="num">Act</th>
                  <th className="num">Max RPI</th>
                  <th className="num">Earliest</th>
                </tr>
              </thead>
              <tbody>
                {data.by_region.map((r) => (
                  <tr key={r.region_id}>
                    <td>
                      <button
                        className="row-title"
                        onClick={() => {
                          setRegion(r.region_id)
                          navigate('/')
                        }}
                      >
                        {r.name}
                      </button>
                    </td>
                    <td className="muted">{r.level}</td>
                    <td><TierBar counts={r.tier_counts} height={8} /></td>
                    <td className="num mono">{r.sites}</td>
                    <td className="num mono">{r.act_sites}</td>
                    <td className="num mono"><TierBadge tier={r.worst_tier} /> {r.max_rpi.toFixed(0)}</td>
                    <td className="num mono">{r.earliest_eta_days != null ? `${r.earliest_eta_days} d` : '-'}</td>
                  </tr>
                ))}
              </tbody>
            </DataTable>
          </Card>

          <div className="grid-2">
            <Card title="By asset type" flush>
              <DataTable caption="Risk by asset type">
                <thead>
                  <tr><th>Type</th><th style={{ width: '40%' }}>Tiers</th><th className="num">Sites</th><th className="num">Act</th></tr>
                </thead>
                <tbody>
                  {data.by_asset_type.map((t) => (
                    <tr key={t.asset_type}>
                      <td>{t.label}</td>
                      <td><TierBar counts={t.tier_counts} height={8} /></td>
                      <td className="num mono">{t.sites}</td>
                      <td className="num mono">{t.act_sites}</td>
                    </tr>
                  ))}
                </tbody>
              </DataTable>
            </Card>
            <Card title="Rainfall, last 14 days" subtitle="Heavy rain can speed up slope and settlement movement." flush>
              {data.rain.length === 0 ? (
                <div className="empty"><CloudRain size={20} aria-hidden /><p>No rainfall data loaded. Fetch it from the Data Hub.</p></div>
              ) : (
                <DataTable caption="Recent rainfall by region">
                  <thead>
                    <tr><th>Region</th><th className="num">14 d total</th><th className="num">Peak day</th><th className="num">Trigger</th></tr>
                  </thead>
                  <tbody>
                    {data.rain.map((r) => (
                      <tr key={r.region_id}>
                        <td>{r.name}</td>
                        <td className="num mono">{r.rain_14d_mm.toFixed(0)} mm</td>
                        <td className="num mono">{r.peak_day_mm.toFixed(0)} mm</td>
                        <td className="num">{r.trigger_score >= 1 ? <Chip tone="warn">Triggered</Chip> : <span className="muted mono">{r.trigger_score.toFixed(2)}</span>}</td>
                      </tr>
                    ))}
                  </tbody>
                </DataTable>
              )}
            </Card>
          </div>

          <Card title="Top sites across the portfolio" flush>
            <ActList sites={data.top_sites} />
          </Card>
        </>
      )}
    </div>
  )
}
