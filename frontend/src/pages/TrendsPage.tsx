import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ArrowDownRight, ArrowUpRight } from 'lucide-react'
import { api } from '../api/client'
import type { Mover } from '../api/types'
import { RpiTrend, SiteHistoryChart, TierTimeline, TierTrend } from '../components/charts'
import { Card, DataTable, Empty, ErrorBox, Loading, PageHeader, Stat, TierBadge } from '../components/ui'
import { shortDate } from '../lib/format'
import { useUi } from '../store'

function Movers({ rows, kind }: { rows: Mover[]; kind: 'up' | 'down' }) {
  const select = useUi((s) => s.selectSite)
  if (!rows.length) return <Empty title={kind === 'up' ? 'Nothing got worse' : 'Nothing improved'} />
  return (
    <DataTable caption={kind === 'up' ? 'Sites whose risk rose most' : 'Sites whose risk fell most'}>
      <thead>
        <tr>
          <th>Site</th>
          <th>Tier</th>
          <th className="num">RPI</th>
          <th className="num">Change</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((m) => (
          <tr key={m.site_id}>
            <td>
              <button className="row-title" onClick={() => select(m.site_id, 'history')}>
                {m.label}
              </button>
            </td>
            <td>
              <span className="tier-move">
                <TierBadge tier={m.previous_tier} /> {m.tier_change !== 0 && <>→ <TierBadge tier={m.tier} /></>}
              </span>
            </td>
            <td className="num mono">
              {m.previous_rpi.toFixed(0)} → {m.rpi.toFixed(0)}
            </td>
            <td className={`num mono delta ${kind}`}>
              {kind === 'up' ? <ArrowUpRight size={13} aria-hidden /> : <ArrowDownRight size={13} aria-hidden />} {m.delta_rpi > 0 ? '+' : ''}
              {m.delta_rpi.toFixed(0)}
            </td>
          </tr>
        ))}
      </tbody>
    </DataTable>
  )
}

export default function TrendsPage() {
  const regionId = useUi((s) => s.regionId)
  const { data, isLoading, error, refetch } = useQuery({ queryKey: ['trends', regionId], queryFn: () => api.trends(regionId) })
  const { data: mv } = useQuery({ queryKey: ['movers', regionId], queryFn: () => api.movers(regionId) })
  const { data: summary } = useQuery({ queryKey: ['summary', regionId], queryFn: () => api.regionSummary(regionId) })

  const [picked, setPicked] = useState<string>('')
  const candidates = summary?.act_list ?? []
  const siteId = candidates.some((s) => s.site_id === picked) ? picked : (candidates[0]?.site_id ?? '')
  const { data: hist } = useQuery({ queryKey: ['site-history', siteId], queryFn: () => api.siteHistory(siteId), enabled: !!siteId })

  const series = data?.series ?? []
  const first = series[0]
  const last = series[series.length - 1]

  return (
    <div className="page">
      <PageHeader title="Trends & History" subtitle="Each point is the full analysis re-run using only the satellite data available on that date, so the history is reproducible, not remembered." />

      {isLoading && <Loading label="Replaying recent satellite passes (first view can take a few seconds)" />}
      {error && <ErrorBox error={error} onRetry={() => refetch()} />}

      {data && series.length === 0 && (
        <Card>
          <Empty title="Not enough history yet">At least 12 satellite epochs are needed to rebuild earlier passes.</Empty>
        </Card>
      )}

      {data && series.length > 0 && first && last && (
        <>
          <div className="stat-row">
            <Stat label="Passes replayed" value={series.length} sub={`${shortDate(first.as_of)} to ${shortDate(last.as_of)}`} />
            <Stat label="Action sites now" value={last.act_sites} sub={`was ${first.act_sites}`} />
            <Stat label="Highest RPI now" value={last.max_rpi.toFixed(0)} sub={`was ${first.max_rpi.toFixed(0)}`} />
            <Stat label="Accelerating" value={last.accelerating} sub={`was ${first.accelerating}`} />
            <Stat label="Threshold ≤ 60 d" value={last.approaching_60d} sub={`was ${first.approaching_60d}`} />
          </div>

          <div className="grid-2">
            <Card title="Sites by risk tier" subtitle="Stable sites are hidden so the movement is visible.">
              <TierTrend series={series} />
            </Card>
            <Card title="Risk Priority Index" subtitle="Highest score, and the average of sites needing action.">
              <RpiTrend series={series} />
            </Card>
          </div>

          <div className="grid-2">
            <Card title="Risers" subtitle={mv?.since ? `Biggest RPI increase since ${shortDate(mv.since)}` : undefined} flush>
              <Movers rows={mv?.risers ?? []} kind="up" />
            </Card>
            <Card title="Fallers" subtitle="Sites whose risk reduced" flush>
              <Movers rows={mv?.fallers ?? []} kind="down" />
            </Card>
          </div>

          <Card
            title="Site timeline"
            subtitle="Pick a site to see how its tier, risk score and speed changed pass by pass."
            actions={
              <select value={siteId} onChange={(e) => setPicked(e.target.value)} aria-label="Choose a site">
                {candidates.map((s) => (
                  <option key={s.site_id} value={s.site_id}>
                    {s.label}
                  </option>
                ))}
              </select>
            }
          >
            {candidates.length === 0 ? (
              <Empty title="No sites need action in this region" />
            ) : hist ? (
              <>
                <TierTimeline history={hist.history} />
                <SiteHistoryChart history={hist.history} height={230} />
              </>
            ) : (
              <Loading />
            )}
          </Card>
        </>
      )}
    </div>
  )
}
