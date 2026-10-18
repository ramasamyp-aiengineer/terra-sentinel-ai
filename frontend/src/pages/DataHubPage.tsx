import { useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CloudRain, Cloud, Database, Download, FileUp, Globe, Link2, MapPinPlus, RotateCcw, UploadCloud } from 'lucide-react'
import { api } from '../api/client'
import type { DataKind, DataStatus, ParseResultPayload, Region, UploadKind } from '../api/types'
import { BigQueryDoctor } from '../components/BigQueryDoctor'
import { PublicDataPanel } from '../components/PublicData'
import { ResultView } from '../components/ValidationView'
import { useCan } from '../lib/auth'
import { Btn, Card, Chip, DataTable, Empty, ErrorBox, Field, Loading, Notice, PageHeader, Segmented, Stat } from '../components/ui'
import { bytes, dateTime, int, shortDate, sourceLabel } from '../lib/format'
import { useUi } from '../store'

type Tab = 'import' | 'rain' | 'regions' | 'public' | 'datasets' | 'export' | 'cloud'

const KIND_OPTIONS: { value: UploadKind; label: string }[] = [
  { value: 'auto', label: 'Detect automatically' },
  { value: 'insar', label: 'InSAR product (points + time series)' },
  { value: 'points', label: 'Points only' },
  { value: 'timeseries', label: 'Time series only' },
  { value: 'rain', label: 'Rainfall' },
  { value: 'assets', label: 'Assets (GeoJSON only)' },
  { value: 'regions', label: 'Regions' },
]

function useRefreshAll() {
  const qc = useQueryClient()
  return () => qc.invalidateQueries()
}

/* ---------------------------------------------------------------- overview */

function Overview({ s }: { s: DataStatus }) {
  const c = s.counts
  return (
    <div className="stat-row">
      <Stat label="Regions" value={int(c.regions)} />
      <Stat label="Assets" value={int(c.assets)} />
      <Stat label="InSAR points" value={int(c.points)} />
      <Stat label="Time-series rows" value={int(c.timeseries_rows)} sub={`${c.epochs} epochs`} />
      <Stat label="Rain rows" value={int(c.rain_rows)} />
      <Stat label="Newest data" value={shortDate(c.date_max)} sub={c.date_min ? `from ${shortDate(c.date_min)}` : undefined} />
    </div>
  )
}

/* ---------------------------------------------------------------- import */

function RegionSelect({ regions, value, onChange, allowNone }: { regions: Region[]; value: string; onChange: (v: string) => void; allowNone?: boolean }) {
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)}>
      {allowNone && <option value="">Use the region column in the file</option>}
      {regions.map((r) => (
        <option key={r.region_id} value={r.region_id}>
          {r.name} ({r.level})
        </option>
      ))}
    </select>
  )
}

function FileImport({ regions, limits }: { regions: Region[]; limits: DataStatus['limits'] }) {
  const refresh = useRefreshAll()
  const input = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [kind, setKind] = useState<UploadKind>('auto')
  const [region, setRegion] = useState('')
  const [mode, setMode] = useState<'merge' | 'replace'>('merge')
  const [confirm, setConfirm] = useState(false)
  const [drag, setDrag] = useState(false)
  const [result, setResult] = useState<ParseResultPayload | null>(null)

  const check = useMutation({ mutationFn: () => api.validateFile(file!, kind, region || undefined), onSuccess: setResult })
  const run = useMutation({
    mutationFn: () => api.uploadFile(file!, kind, mode, region || undefined),
    onSuccess: (r) => {
      setResult(r)
      if (r.applied) refresh()
    },
  })
  const pick = (f: File | null) => {
    setFile(f)
    setResult(null)
    check.reset()
    run.reset()
  }
  const tooBig = file ? file.size > limits.max_upload_mb * 1024 * 1024 : false
  const canImport = !!file && result?.ok && !result.applied && !tooBig && (mode === 'merge' || confirm)

  return (
    <Card title="Upload a file" subtitle="CSV or GeoJSON (assets). EGMS-style wide InSAR exports are understood directly. UTF-8 only.">
      <div
        className={`dropzone ${drag ? 'drag' : ''} ${file ? 'has-file' : ''}`}
        onDragOver={(e) => {
          e.preventDefault()
          setDrag(true)
        }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => {
          e.preventDefault()
          setDrag(false)
          pick(e.dataTransfer.files?.[0] ?? null)
        }}
      >
        <UploadCloud size={26} aria-hidden />
        {file ? (
          <>
            <strong>{file.name}</strong>
            <span className="muted">{bytes(file.size)}</span>
          </>
        ) : (
          <>
            <strong>Drop a file here</strong>
            <span className="muted">or</span>
          </>
        )}
        <Btn icon={FileUp} onClick={() => input.current?.click()}>
          {file ? 'Choose another file' : 'Browse files'}
        </Btn>
        <input ref={input} type="file" hidden accept=".csv,.txt,.json,.geojson,.tsv" onChange={(e) => pick(e.target.files?.[0] ?? null)} aria-label="Choose a data file" />
      </div>
      {tooBig && <Notice tone="bad">This file is larger than the {limits.max_upload_mb} MB limit.</Notice>}

      <div className="form-grid">
        <Field label="What is in the file?">
          <select value={kind} onChange={(e) => { setKind(e.target.value as UploadKind); setResult(null) }}>
            {KIND_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
        </Field>
        <Field label="Region for rows without one" hint="Used when the file has no region column.">
          <RegionSelect regions={regions} value={region} onChange={setRegion} allowNone />
        </Field>
        <Field label="When it is added">
          <Segmented label="Import mode" value={mode} onChange={(m) => { setMode(m); setConfirm(false) }} options={[{ value: 'merge', label: 'Add / update' }, { value: 'replace', label: 'Replace this kind' }]} />
        </Field>
      </div>
      {mode === 'merge' && (
        <Notice tone="warn">
          Add / update keeps the built-in demo data underneath. Rankings can stay mixed with synthetic sites until you choose Replace for each kind you upload (points, time series, assets).
        </Notice>
      )}
      {mode === 'replace' && (
        <label className="check">
          <input type="checkbox" checked={confirm} onChange={(e) => setConfirm(e.target.checked)} />
          I understand this removes the existing data of this kind in the workspace.
        </label>
      )}

      <div className="btn-row">
        <Btn variant="secondary" disabled={!file || tooBig} loading={check.isPending} onClick={() => check.mutate()}>
          1. Check file
        </Btn>
        <Btn variant="primary" disabled={!canImport} loading={run.isPending} onClick={() => run.mutate()}>
          2. Import
        </Btn>
        <a className="link-btn" href={api.templateUrl('insar')} download>
          <Download size={13} aria-hidden /> Get a template
        </a>
      </div>
      <p className="muted">Nothing is saved until you press Import. Rows that fail checks are listed with their row numbers. Prefer the wide InSAR template when you have points and epochs together — replacing points alone removes time series for points that are no longer present.</p>

      {(check.error || run.error) && <ErrorBox error={check.error ?? run.error} />}
      {result && <ResultView result={result} />}
    </Card>
  )
}

function LinkImport({ regions }: { regions: Region[] }) {
  const refresh = useRefreshAll()
  const [url, setUrl] = useState('')
  const [kind, setKind] = useState<UploadKind>('auto')
  const [region, setRegion] = useState('')
  const [mode, setMode] = useState<'merge' | 'replace'>('merge')
  const [confirm, setConfirm] = useState(false)
  const [result, setResult] = useState<ParseResultPayload | null>(null)
  const [checked, setChecked] = useState('')

  const invalidateCheck = () => {
    setResult(null)
    setChecked('')
    check.reset()
    run.reset()
  }
  const body = (dry: boolean) => ({ url: url.trim(), kind, mode, default_region: region || undefined, dry_run: dry })
  const check = useMutation({ mutationFn: () => api.fetchUrl(body(true)), onSuccess: (r) => { setResult(r); setChecked(url.trim()) } })
  const run = useMutation({
    mutationFn: () => api.fetchUrl(body(false)),
    onSuccess: (r) => {
      setResult(r)
      if (r.applied) refresh()
    },
  })
  const valid = /^https?:\/\/.{4,}/i.test(url.trim())
  const canImport = valid && result?.ok && !result.applied && checked === url.trim() && (mode === 'merge' || confirm)

  return (
    <Card title="Fetch from a link" subtitle="A public file URL (CSV or GeoJSON). The server downloads it, checks it, and only then imports.">
      <div className="form-grid single">
        <Field label="File URL" hint="Must be a public https link. Private and internal addresses are blocked.">
          <input type="url" inputMode="url" placeholder="https://example.org/data/insar_points.csv" value={url} onChange={(e) => { setUrl(e.target.value); invalidateCheck() }} spellCheck={false} />
        </Field>
      </div>
      <div className="form-grid">
        <Field label="What is in the file?">
          <select value={kind} onChange={(e) => { setKind(e.target.value as UploadKind); invalidateCheck() }}>
            {KIND_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
        </Field>
        <Field label="Region for rows without one">
          <RegionSelect regions={regions} value={region} onChange={(v) => { setRegion(v); invalidateCheck() }} allowNone />
        </Field>
        <Field label="When it is added">
          <Segmented label="Import mode" value={mode} onChange={(m) => { setMode(m); setConfirm(false) }} options={[{ value: 'merge', label: 'Add / update' }, { value: 'replace', label: 'Replace' }]} />
        </Field>
      </div>
      {mode === 'replace' && (
        <label className="check">
          <input type="checkbox" checked={confirm} onChange={(e) => setConfirm(e.target.checked)} />
          I understand this removes the existing data of this kind in the workspace.
        </label>
      )}
      <div className="btn-row">
        <Btn icon={Link2} disabled={!valid} loading={check.isPending} onClick={() => check.mutate()}>
          1. Check link
        </Btn>
        <Btn variant="primary" disabled={!canImport} loading={run.isPending} onClick={() => run.mutate()}>
          2. Fetch &amp; import
        </Btn>
      </div>
      {(check.error || run.error) && <ErrorBox error={check.error ?? run.error} />}
      {result && <ResultView result={result} />}
    </Card>
  )
}

/* ---------------------------------------------------------------- rainfall */

function RainFetch({ regions }: { regions: Region[] }) {
  const refresh = useRefreshAll()
  const current = useUi((s) => s.regionId)
  const [region, setRegion] = useState(current)
  const [days, setDays] = useState(60)
  const m = useMutation({ mutationFn: () => api.fetchRain(region, days), onSuccess: () => refresh() })
  const r = m.data

  return (
    <Card title="Fetch rainfall for a region" subtitle="Daily rainfall for the region centre from the open Open-Meteo archive. No key needed. Heavy rain is used as a trigger in the risk logic.">
      <div className="form-grid">
        <Field label="Region">
          <RegionSelect regions={regions} value={region} onChange={setRegion} />
        </Field>
        <Field label="History">
          <Segmented label="Days" value={String(days)} onChange={(v) => setDays(Number(v))} options={[{ value: '30', label: '30 days' }, { value: '60', label: '60 days' }, { value: '90', label: '90 days' }]} />
        </Field>
      </div>
      <div className="btn-row">
        <Btn variant="primary" icon={CloudRain} loading={m.isPending} onClick={() => m.mutate()}>
          Fetch rainfall
        </Btn>
      </div>
      {m.error && <ErrorBox error={m.error} />}
      {r && (
        <Notice tone="ok" icon={CloudRain}>
          <strong>{r.rows} days loaded</strong> for {r.region_id} ({shortDate(r.date_min)} to {shortDate(r.date_max)}), {r.total_mm.toFixed(0)} mm in total. {r.overlap_days_in_assessment_window} days overlap the analysis window.
          {r.warnings.map((w) => (
            <div key={w} className="warn-text">{w}</div>
          ))}
          <div className="muted">Source: {r.source}</div>
        </Notice>
      )}
    </Card>
  )
}

/* ---------------------------------------------------------------- regions */

function RegionManager({ regions }: { regions: Region[] }) {
  const refresh = useRefreshAll()
  const [f, setF] = useState({ name: '', parent_id: 'IN', level: 'district', lon: '', lat: '', zoom: '9' })
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setF({ ...f, [k]: e.target.value })
  const lon = Number(f.lon)
  const lat = Number(f.lat)
  const valid = f.name.trim().length >= 2 && f.lon !== '' && f.lat !== '' && Math.abs(lon) <= 180 && Math.abs(lat) <= 90
  const m = useMutation({
    mutationFn: () => api.addRegion({ name: f.name.trim(), parent_id: f.parent_id || null, level: f.level, center_lon: lon, center_lat: lat, zoom: Number(f.zoom) }),
    onSuccess: () => {
      setF({ ...f, name: '', lon: '', lat: '' })
      refresh()
    },
  })

  return (
    <div className="grid-2">
      <Card title="Add a region" subtitle="Regions scope the dashboard, alerts and rainfall. Use the centre point of the area.">
        <form
          className="stack tight"
          onSubmit={(e) => {
            e.preventDefault()
            if (valid) m.mutate()
          }}
        >
          <Field label="Name">
            <input value={f.name} onChange={set('name')} placeholder="e.g. Pune district" maxLength={80} required />
          </Field>
          <div className="form-grid">
            <Field label="Inside">
              <select value={f.parent_id} onChange={set('parent_id')}>
                <option value="">Top level</option>
                {regions.map((r) => (
                  <option key={r.region_id} value={r.region_id}>{r.name}</option>
                ))}
              </select>
            </Field>
            <Field label="Level">
              <select value={f.level} onChange={set('level')}>
                {['country', 'state', 'district', 'city', 'site'].map((l) => (
                  <option key={l}>{l}</option>
                ))}
              </select>
            </Field>
          </div>
          <div className="form-grid">
            <Field label="Longitude" hint="-180 to 180">
              <input inputMode="decimal" value={f.lon} onChange={set('lon')} placeholder="73.86" />
            </Field>
            <Field label="Latitude" hint="-90 to 90">
              <input inputMode="decimal" value={f.lat} onChange={set('lat')} placeholder="18.52" />
            </Field>
            <Field label="Map zoom" hint="1 world, 9 district">
              <input inputMode="decimal" value={f.zoom} onChange={set('zoom')} />
            </Field>
          </div>
          <div className="btn-row">
            <Btn type="submit" variant="primary" icon={MapPinPlus} disabled={!valid} loading={m.isPending}>
              Add region
            </Btn>
          </div>
          {m.error && <ErrorBox error={m.error} />}
          {m.isSuccess && <Notice tone="ok">Added {m.data.name}. It now appears in the region picker.</Notice>}
        </form>
      </Card>
      <Card title="Regions" subtitle={`${regions.length} in this workspace`} flush>
        <DataTable caption="Regions">
          <thead>
            <tr><th>Name</th><th>Level</th><th>Id</th></tr>
          </thead>
          <tbody>
            {regions.map((r) => (
              <tr key={r.region_id}>
                <td>{r.name}</td>
                <td className="muted">{r.level}</td>
                <td className="mono muted">{r.region_id}</td>
              </tr>
            ))}
          </tbody>
        </DataTable>
      </Card>
    </div>
  )
}

/* ---------------------------------------------------------------- datasets */

function Datasets({ s }: { s: DataStatus }) {
  return (
    <Card title="Where the data came from" subtitle="Every upload, link and fetch is recorded so a result can be traced to its source." flush>
      {s.datasets.length === 0 ? (
        <Empty title="No datasets yet" />
      ) : (
        <DataTable caption="Dataset provenance">
          <thead>
            <tr><th>Dataset</th><th>Kind</th><th>Source</th><th className="num">Rows</th><th>Dates</th><th>Added</th></tr>
          </thead>
          <tbody>
            {s.datasets.map((d) => (
              <tr key={d.dataset_id}>
                <td>
                  <strong>{d.name}</strong>
                  {d.notes.slice(0, 2).map((n) => (
                    <div key={n} className="muted">{n}</div>
                  ))}
                </td>
                <td><Chip>{s.kinds[d.kind] ?? d.kind}</Chip></td>
                <td>
                  <Chip tone={d.source_type === 'demo' ? 'neutral' : 'brand'}>{d.source_type}</Chip>
                  <div className="muted ellipsis" title={d.source_ref}>{d.source_ref}</div>
                </td>
                <td className="num mono">{int(d.rows)}</td>
                <td className="mono muted">{d.date_min ? `${shortDate(d.date_min)} to ${shortDate(d.date_max)}` : '-'}</td>
                <td className="mono muted">{dateTime(d.added_at)}</td>
              </tr>
            ))}
          </tbody>
        </DataTable>
      )}
    </Card>
  )
}

/* ---------------------------------------------------------------- export */

function Export({ s }: { s: DataStatus }) {
  const kinds = (Object.keys(s.kinds) as DataKind[]).filter((k) => k !== 'events') // earthquake events live in Public data
  return (
    <div className="grid-2">
      <Card title="Templates" subtitle="Empty files with the right headers and an example row.">
        <ul className="download-list">
          {kinds.map((k) => (
            <li key={k}>
              <span>{s.kinds[k]}</span>
              <a className="btn btn-secondary btn-sm" href={api.templateUrl(k)} download>
                <Download size={13} aria-hidden /> Template
              </a>
            </li>
          ))}
        </ul>
      </Card>
      <Card title="Export current data" subtitle="Download what the platform is using right now.">
        <ul className="download-list">
          {kinds.map((k) => (
            <li key={k}>
              <span>{s.kinds[k]}</span>
              <a className="btn btn-secondary btn-sm" href={api.exportUrl(k)} download>
                <Download size={13} aria-hidden /> Export
              </a>
            </li>
          ))}
        </ul>
      </Card>
    </div>
  )
}

/* ---------------------------------------------------------------- cloud */

function CloudPanel({ s }: { s: DataStatus }) {
  const admin = useCan('admin')
  const refresh = useRefreshAll()
  const bq = s.bigquery
  const [confirm, setConfirm] = useState(false)
  const sync = useMutation({ mutationFn: api.syncBigQuery, onSuccess: () => refresh() })
  const reset = useMutation({
    mutationFn: api.resetDemo,
    onSuccess: () => {
      setConfirm(false)
      refresh()
    },
  })

  return (
    <div className="grid-2">
      <Card title="BigQuery" subtitle="Warehouse storage, spatial joins and snapshots at scale.">
        <dl className="kv">
          <div><dt>Active backend</dt><dd><Chip tone={s.backend === 'bigquery' ? 'brand' : 'neutral'}>{s.backend}</Chip></dd></div>
          <div><dt>Project</dt><dd className="mono">{bq.project ?? 'not set'}</dd></div>
          <div><dt>Dataset</dt><dd className="mono">{bq.dataset}</dd></div>
          <div><dt>Location</dt><dd className="mono">{bq.location}</dd></div>
          <div><dt>Connection</dt><dd><Chip tone={bq.reachable ? 'ok' : bq.configured ? 'warn' : 'neutral'}>{bq.reachable ? 'Reachable' : bq.configured ? 'Not reachable' : 'Not configured'}</Chip></dd></div>
        </dl>
        <p className="muted">{bq.detail}</p>
        {bq.tables && bq.tables.length > 0 && (
          <div className="chips">
            {bq.tables.map((t) => (
              <Chip key={t}>{t}</Chip>
            ))}
          </div>
        )}
        {admin && (
          <div className="btn-row">
            <Btn variant="primary" icon={Cloud} disabled={!bq.reachable} loading={sync.isPending} onClick={() => sync.mutate()}>
              Copy workspace to BigQuery
            </Btn>
          </div>
        )}
        {admin && (
          <details className="doctor-box">
            <summary>Connection checks</summary>
            <BigQueryDoctor />
          </details>
        )}
        {!bq.configured && (
          <Notice tone="info">
            Set <code>TS_GCP_PROJECT</code>, then run <code>python -m app.services.bq.setup --load-demo</code> and start the API with <code>TS_DATA_BACKEND=bigquery</code>.
          </Notice>
        )}
        {sync.error && <ErrorBox error={sync.error} />}
        {sync.data && (
          <Notice tone="ok">
            Synced to {sync.data.project}.{sync.data.dataset}: {Object.entries(sync.data.tables).map(([k, v]) => `${int(v.written)} ${k}`).join(', ')}.
          </Notice>
        )}
      </Card>

      <Card title="Workspace" subtitle="Your uploads live in a workspace layered over the built-in demo data.">
        <dl className="kv">
          <div><dt>Data in use</dt><dd>{sourceLabel(s.data_source).text}</dd></div>
          <div><dt>Limits</dt><dd className="muted">{s.limits.max_upload_mb} MB per file · {int(s.limits.max_local_timeseries_rows)} time-series rows locally</dd></div>
        </dl>
        {s.workspace_active && admin ? (
          <>
            <label className="check">
              <input type="checkbox" checked={confirm} onChange={(e) => setConfirm(e.target.checked)} />
              Delete my uploaded data and go back to the demo data.
            </label>
            <div className="btn-row">
              <Btn variant="danger" icon={RotateCcw} disabled={!confirm} loading={reset.isPending} onClick={() => reset.mutate()}>
                Reset to demo data
              </Btn>
            </div>
          </>
        ) : (
          <p className="muted">{s.workspace_active ? 'Resetting to the demo data needs the Admin role.' : 'You are using the built-in demo data. Upload or fetch data and it will appear here.'}</p>
        )}
        {reset.error && <ErrorBox error={reset.error} />}
      </Card>
    </div>
  )
}

/* ---------------------------------------------------------------- page */

export default function DataHubPage() {
  const admin = useCan('admin')
  const analyst = useCan('analyst')
  const [picked, setTab] = useState<Tab | null>(null)
  const tab: Tab = picked ?? (admin ? 'import' : 'public')
  const { data: s, isLoading, error, refetch } = useQuery({ queryKey: ['data-status'], queryFn: api.dataStatus })
  const { data: regions } = useQuery({ queryKey: ['regions'], queryFn: api.regions })

  return (
    <div className="page">
      <PageHeader
        title="Data Hub"
        subtitle="Bring in your own satellite data, links and regions. Every import is validated first and recorded."
        actions={s && <Chip tone={s.workspace_active ? 'brand' : 'neutral'} icon={Database} title={sourceLabel(s.data_source).hint}>{sourceLabel(s.data_source).text}</Chip>}
      />
      {isLoading && <Loading />}
      {error && <ErrorBox error={error} onRetry={() => refetch()} />}
      {s && regions && (
        <>
          <Overview s={s} />
          <Segmented
            label="Data hub section"
            value={tab}
            onChange={setTab}
            options={[
              ...(admin ? ([{ value: 'import', label: 'Import' }, { value: 'rain', label: 'Rainfall' }, { value: 'regions', label: 'Regions' }] as const) : []),
              { value: 'public', label: 'Public data' },
              { value: 'datasets', label: 'Datasets', count: s.datasets.length },
              ...(analyst ? ([{ value: 'export', label: 'Templates & export' }] as const) : []),
              { value: 'cloud', label: 'Cloud & workspace' },
            ]}
          />
          {tab === 'public' && <PublicDataPanel regions={regions} />}
          {tab === 'import' && admin && (
            <div className="grid-2 top">
              <FileImport regions={regions} limits={s.limits} />
              <LinkImport regions={regions} />
            </div>
          )}
          {tab === 'rain' && admin && <RainFetch regions={regions} />}
          {tab === 'regions' && admin && <RegionManager regions={regions} />}
          {tab === 'datasets' && <Datasets s={s} />}
          {tab === 'export' && analyst && <Export s={s} />}
          {tab === 'cloud' && <CloudPanel s={s} />}
          <p className="muted foot-note"><Globe size={12} aria-hidden /> Link fetch accepts public https URLs only; redirects are re-checked and large files are refused.</p>
        </>
      )}
    </div>
  )
}
