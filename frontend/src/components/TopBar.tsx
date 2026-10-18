import { useQuery } from '@tanstack/react-query'
import { Bell, Menu } from 'lucide-react'
import { api } from '../api/client'
import { navigate } from '../lib/router'
import { shortDate, sourceLabel } from '../lib/format'
import { useUi } from '../store'
import { AccountMenu } from './Account'
import { GlobalSearch } from './GlobalSearch'
import { Chip } from './ui'

export function TopBar() {
  const regionId = useUi((s) => s.regionId)
  const setRegion = useUi((s) => s.setRegion)
  const setNavOpen = useUi((s) => s.setNavOpen)
  const { data: regions } = useQuery({ queryKey: ['regions'], queryFn: api.regions, staleTime: 60_000 })
  const { data: meta } = useQuery({ queryKey: ['meta'], queryFn: api.meta, staleTime: 60_000 })
  // After region chrome is up — never race the first summary/map paint.
  const { data: alerts } = useQuery({
    queryKey: ['alerts', regionId, '', ''],
    queryFn: () => api.alerts(regionId),
    staleTime: 60_000,
    enabled: !!regions,
  })

  // depth-first so the hierarchy reads naturally
  const ordered: { region_id: string; name: string; depth: number }[] = []
  const walk = (parent: string | null, depth: number) => {
    regions
      ?.filter((r) => r.parent_id === parent)
      .forEach((r) => {
        ordered.push({ region_id: r.region_id, name: r.name, depth })
        walk(r.region_id, depth + 1)
      })
  }
  walk(null, 0)

  const src = meta ? sourceLabel(meta.data_source) : null
  const open = alerts?.summary.open ?? 0
  const critical = alerts?.summary.open_critical ?? 0

  return (
    <header className="topbar">
      <button className="icon-btn menu-btn" onClick={() => setNavOpen(true)} aria-label="Open menu">
        <Menu size={18} />
      </button>

      <label className="region-select">
        <span className="sr-only">Region</span>
        <select value={regionId} onChange={(e) => setRegion(e.target.value)} aria-label="Region">
          {ordered.map((r) => (
            <option key={r.region_id} value={r.region_id}>
              {'\u00A0\u00A0'.repeat(r.depth)}
              {r.name}
            </option>
          ))}
        </select>
      </label>

      <GlobalSearch />

      <div className="topbar-spacer" />

      {src && (
        <Chip tone={src.tone} title={src.hint}>
          {src.text}
        </Chip>
      )}
      {meta && <span className="asof mono" title="Assessment date">As of {shortDate(meta.as_of)}</span>}

      <button className="bell" onClick={() => navigate('/alerts')} aria-label={`${open} open alerts${critical ? `, ${critical} critical` : ''}`}>
        <Bell size={17} />
        {open > 0 && <span className={`bell-count mono ${critical ? 'crit' : ''}`}>{open}</span>}
      </button>

      <AccountMenu />
    </header>
  )
}
