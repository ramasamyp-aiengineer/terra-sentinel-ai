import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Activity, CloudDownload, Eye, EyeOff, Globe2, RefreshCw, Trash2 } from 'lucide-react'
import { api } from '../api/client'
import type { PublicDataset, Region } from '../api/types'
import { useCan } from '../lib/auth'
import { bytes, dateTime, int, shortDate } from '../lib/format'
import { Btn, Card, Chip, DataTable, ErrorBox, Field, Loading, Notice, Segmented } from './ui'

function Preview({ id }: { id: string }) {
  const { data, isLoading, error } = useQuery({ queryKey: ['public-preview', id], queryFn: () => api.publicPreview(id) })
  if (isLoading) return <Loading />
  if (error) return <ErrorBox error={error} />
  if (!data) return null
  return (
    <div className="stack tight">
      <div className="chips">
        {Object.entries(data.by_magnitude).map(([band, n]) => (
          <Chip key={band}>
            M{band}: {int(n)}
          </Chip>
        ))}
      </div>
      <DataTable caption="Largest stored earthquakes">
        <thead>
          <tr><th>When (UTC)</th><th className="num">Magnitude</th><th>Place</th></tr>
        </thead>
        <tbody>
          {data.largest.map((e, i) => (
            <tr key={`${e.time}-${i}`}>
              <td className="mono">{e.time}</td>
              <td className="num mono">{e.mag.toFixed(1)}</td>
              <td>{e.place}</td>
            </tr>
          ))}
        </tbody>
      </DataTable>
    </div>
  )
}

function DatasetCard({ d, admin }: { d: PublicDataset; admin: boolean }) {
  const qc = useQueryClient()
  const [view, setView] = useState(false)
  const [confirm, setConfirm] = useState(false)
  const done = () => qc.invalidateQueries()
  const fetchIt = useMutation({ mutationFn: () => api.publicFetch(d.id), onSuccess: done })
  const remove = useMutation({ mutationFn: () => api.publicDelete(d.id), onSuccess: () => { setConfirm(false); setView(false); done() } })
  const s = d.stored

  return (
    <article className="public-card">
      <header>
        <h3>{d.title}</h3>
        <div className="chips">
          <Chip tone={d.scope === 'region' ? 'info' : 'neutral'} icon={Globe2}>{d.scope === 'region' ? 'One region' : 'Worldwide'}</Chip>
          {s ? <Chip tone={s.stale ? 'warn' : 'ok'}>{s.stale ? `Stale (${s.age_days} days old)` : 'Stored'}</Chip> : <Chip>Not downloaded</Chip>}
        </div>
      </header>
      <p className="muted">{d.description}</p>
      <dl className="kv">
        <div><dt>Publisher</dt><dd>{d.publisher}</dd></div>
        <div><dt>License</dt><dd>{d.license}</dd></div>
        {s && (
          <>
            <div><dt>Stored copy</dt><dd className="mono">{int(s.rows)} events · {bytes(s.bytes)} · {shortDate(s.date_min)} to {shortDate(s.date_max)}</dd></div>
            <div><dt>Downloaded</dt><dd className="mono">{dateTime(s.fetched_at)}</dd></div>
            <div><dt>Fingerprint</dt><dd className="mono" title={s.sha256}>{s.sha256.slice(0, 12)}…</dd></div>
          </>
        )}
      </dl>
      <div className="btn-row">
        {admin && d.scope === 'global' && (
          <Btn variant={s ? 'secondary' : 'primary'} icon={s ? RefreshCw : CloudDownload} loading={fetchIt.isPending} onClick={() => fetchIt.mutate()}>
            {s ? 'Refresh' : 'Download'}
          </Btn>
        )}
        {s && (
          <Btn icon={view ? EyeOff : Eye} onClick={() => setView((v) => !v)} aria-expanded={view}>
            {view ? 'Hide preview' : 'Preview'}
          </Btn>
        )}
        {admin && s && !confirm && <Btn variant="ghost" icon={Trash2} onClick={() => setConfirm(true)}>Delete</Btn>}
        {admin && s && confirm && (
          <>
            <Btn variant="danger" icon={Trash2} loading={remove.isPending} onClick={() => remove.mutate()}>Delete stored copy</Btn>
            <Btn variant="ghost" onClick={() => setConfirm(false)}>Keep</Btn>
          </>
        )}
      </div>
      {fetchIt.error && <ErrorBox error={fetchIt.error} />}
      {remove.error && <ErrorBox error={remove.error} />}
      {fetchIt.data && <Notice tone="ok">Downloaded {int(fetchIt.data.rows)} events and stored them as CSV.</Notice>}
      {view && s && <Preview id={d.id} />}
      {s && <p className="muted cite">{s.citation}</p>}
    </article>
  )
}

function RegionSeismicity({ regions }: { regions: Region[] }) {
  const qc = useQueryClient()
  const [region, setRegion] = useState(regions[0]?.region_id ?? '')
  const [radius, setRadius] = useState('300')
  const [days, setDays] = useState('365')
  const [mag, setMag] = useState('2.5')
  const m = useMutation({
    mutationFn: () => api.publicSeismicity({ region_id: region, radius_km: Number(radius), days: Number(days), min_mag: Number(mag) }),
    onSuccess: () => qc.invalidateQueries(),
  })
  return (
    <Card title="Earthquakes around a region" subtitle="Download the USGS catalog for the area around one of your regions, as a CSV kept on this server.">
      <form className="stack tight" onSubmit={(e) => { e.preventDefault(); m.mutate() }}>
        <div className="form-grid">
          <Field label="Region">
            <select value={region} onChange={(e) => setRegion(e.target.value)}>
              {regions.map((r) => <option key={r.region_id} value={r.region_id}>{r.name} ({r.level})</option>)}
            </select>
          </Field>
          <Field label="Radius from region centre" hint="10 to 1000 km">
            <select value={radius} onChange={(e) => setRadius(e.target.value)}>
              {['100', '200', '300', '500', '1000'].map((v) => <option key={v} value={v}>{v} km</option>)}
            </select>
          </Field>
          <Field label="Look back">
            <select value={days} onChange={(e) => setDays(e.target.value)}>
              {[['90', '90 days'], ['365', '1 year'], ['1825', '5 years'], ['3650', '10 years']].map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </Field>
          <Field label="Smallest magnitude">
            <select value={mag} onChange={(e) => setMag(e.target.value)}>
              {['1.5', '2.5', '3.5', '4.5'].map((v) => <option key={v} value={v}>M {v}+</option>)}
            </select>
          </Field>
        </div>
        <div className="btn-row">
          <Btn type="submit" variant="primary" icon={Activity} loading={m.isPending} disabled={!region}>Download earthquakes</Btn>
        </div>
        {m.error && <ErrorBox error={m.error} />}
        {m.data && <Notice tone="ok">Stored {int(m.data.rows)} earthquakes for this area. Sites in that region now show seismic context.</Notice>}
      </form>
    </Card>
  )
}

export function PublicDataPanel({ regions }: { regions: Region[] }) {
  const admin = useCan('admin')
  const { data, isLoading, error, refetch } = useQuery({ queryKey: ['public-catalog'], queryFn: api.publicCatalog })
  const [scope, setScope] = useState<'all' | 'global' | 'region'>('all')
  if (isLoading) return <Loading />
  if (error) return <ErrorBox error={error} onRetry={() => refetch()} />
  const list = (data?.datasets ?? []).filter((d) => scope === 'all' || d.scope === scope)

  return (
    <div className="stack">
      <Notice tone="brand" icon={Globe2}>
        Open datasets kept as CSV files on this server. They are shown beside a site as <strong>context</strong> and never change a risk score or tier.
        {!admin && ' Downloading and deleting need the Admin role.'}
      </Notice>
      <Segmented
        label="Dataset scope"
        value={scope}
        onChange={setScope}
        options={[{ value: 'all', label: 'All', count: data?.datasets.length }, { value: 'global', label: 'Worldwide' }, { value: 'region', label: 'Per region' }]}
      />
      <div className="public-grid">
        {list.map((d) => <DatasetCard key={d.id} d={d} admin={admin} />)}
      </div>
      {admin && <RegionSeismicity regions={regions} />}
      {data?.attribution && <p className="muted foot-note">{data.attribution}</p>}
    </div>
  )
}
