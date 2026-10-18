import { useQuery } from '@tanstack/react-query'
import { Map as MapIcon, Route } from 'lucide-react'
import { api } from '../api/client'
import { ActList } from '../components/ActList'
import { ChainageStrip } from '../components/charts'
import { Btn, Card, Chip, Empty, ErrorBox, Loading, PageHeader, Stat, TierBar } from '../components/ui'
import { mmMonth } from '../lib/format'
import { navigate } from '../lib/router'
import { TIER_UI } from '../lib/tier'
import { useUi } from '../store'

function AssetDetailPanel({ id }: { id: string }) {
  const select = useUi((s) => s.selectSite)
  const flyTo = useUi((s) => s.flyTo)
  const selected = useUi((s) => s.selectedSiteId)
  const { data, isLoading, error, refetch } = useQuery({ queryKey: ['asset', id], queryFn: () => api.asset(id) })
  if (isLoading) return <Loading label="Loading corridor" />
  if (error) return <ErrorBox error={error} onRetry={() => refetch()} />
  if (!data) return null
  return (
    <div className="stack">
      <Card
        title={data.name}
        subtitle={`${data.type_label} · ${data.length_km.toFixed(1)} km · ${data.region_name}`}
        actions={
          <Btn
            icon={MapIcon}
            onClick={() => {
              navigate('/')
              flyTo(data.center, 11.5)
            }}
          >
            View on map
          </Btn>
        }
      >
        <div className="stat-row compact">
          <Stat label="Sites" value={data.sites} sub={`${data.points.toLocaleString()} points`} />
          <Stat label="Moving" value={data.moving_sites} sub={data.moving_sites ? mmMonth(data.mean_moving_rate_mm_month) : 'none'} />
          <Stat label="Max RPI" value={data.max_rpi.toFixed(0)} color={TIER_UI[data.worst_tier].fill} />
          <Stat label="Earliest outlook" value={data.earliest_eta_days != null ? `${data.earliest_eta_days} d` : 'none'} />
        </div>
        <p className="muted">
          <strong className="secondary">Why it matters:</strong> {data.consequence_note}
        </p>
      </Card>

      <Card title="Along the corridor" subtitle={`Each block is a 250 m chainage bin, km ${data.strip[0]?.km_start.toFixed(1)} to ${data.strip[data.strip.length - 1]?.km_end.toFixed(1)}. Click a block to inspect it.`}>
        <ChainageStrip items={data.strip} selected={selected} onSelect={(sid) => select(sid, 'now')} />
        <TierBar counts={data.tier_counts} legend height={8} />
      </Card>

      <div className="grid-2">
        <Card title="Worst sites on this corridor" flush>
          <ActList sites={data.top_sites} emptyText="No sites need attention on this corridor." />
        </Card>
        <Card title="How it is assessed" subtitle="Rules applied for this asset type">
          <dl className="kv">
            <div><dt>Buffer around the line</dt><dd className="mono">{data.profile.buffer_m} m</dd></div>
            <div><dt>Operational threshold</dt><dd className="mono">{data.profile.threshold_mm} mm</dd></div>
            <div><dt>Analysis window</dt><dd className="mono">{data.profile.window_days} days</dd></div>
          </dl>
          <p className="muted">{data.profile.mechanism_hint}</p>
        </Card>
      </div>
    </div>
  )
}

export default function CorridorsPage() {
  const regionId = useUi((s) => s.regionId)
  const selectedAssetId = useUi((s) => s.selectedAssetId)
  const selectAsset = useUi((s) => s.selectAsset)
  const { data, isLoading, error, refetch } = useQuery({ queryKey: ['assets', regionId], queryFn: () => api.assets(regionId) })
  const assets = data?.assets ?? []
  const current = assets.find((a) => a.asset_id === selectedAssetId) ?? assets[0]

  return (
    <div className="page">
      <PageHeader title="Corridors & Assets" subtitle="Roads, metro lines and dams, ranked by how much risk each one carries." />
      {isLoading && <Loading label="Loading assets" />}
      {error && <ErrorBox error={error} onRetry={() => refetch()} />}
      {data && assets.length === 0 && (
        <Card>
          <Empty icon={Route} title="No assets in this region">Add assets from the Data Hub.</Empty>
        </Card>
      )}
      {assets.length > 0 && (
        <div className="split">
          <nav className="asset-list" aria-label="Assets">
            {assets.map((a) => (
              <button key={a.asset_id} className={`asset-card ${current?.asset_id === a.asset_id ? 'on' : ''}`} aria-current={current?.asset_id === a.asset_id} onClick={() => selectAsset(a.asset_id)} style={{ borderLeftColor: TIER_UI[a.worst_tier].fill }}>
                <div className="asset-top">
                  <strong>{a.name.split(' (')[0]}</strong>
                  <Chip>{a.type_label}</Chip>
                </div>
                <TierBar counts={a.tier_counts} height={6} />
                <div className="asset-meta muted">
                  <span>{a.length_km.toFixed(1)} km</span>
                  <span>RPI <span className="mono secondary">{a.max_rpi.toFixed(0)}</span></span>
                  <span>{a.earliest_eta_days != null ? `${a.earliest_eta_days} d out` : 'no outlook'}</span>
                </div>
              </button>
            ))}
          </nav>
          <div className="split-main">{current && <AssetDetailPanel id={current.asset_id} />}</div>
        </div>
      )}
    </div>
  )
}
