import type {
  Alert,
  AuditEvent,
  AuthMe,
  DoctorResult,
  PublicDataset,
  PublicPreview,
  QuakeEvent,
  Role,
  SessionUser,
  StoredPublicMeta,
  UserRow,
  AlertAction,
  AlertsResponse,
  AssetBoardItem,
  AssetDetail,
  Brief,
  CorridorCollection,
  DataStatus,
  EarlyWarningBoard,
  MapPoint,
  Methodology,
  Meta,
  Mover,
  ParseResultPayload,
  Portfolio,
  RainFetchResult,
  Region,
  RegionSummary,
  Scenario,
  SearchResult,
  SiteDetail,
  SiteHistoryPoint,
  SiteSummary,
  TimeSeries,
  TrendPoint,
  UploadKind,
  WorkOrder,
  WorkOrderQueue,
} from './types'

const BASE = import.meta.env.VITE_API_URL ?? ''

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

/** Sent on every request. The server refuses writes without it, which stops other websites from acting as the user. */
const CSRF = { 'X-Requested-With': 'TerraSentinel' }

/** Fired when the server says the session is gone, so the app can show the sign-in page instead of broken screens. */
export const UNAUTHORIZED_EVENT = 'ts:unauthorized'

async function req<T>(path: string, init: RequestInit = {}): Promise<T> {
  let res: Response
  try {
    res = await fetch(`${BASE}${path}`, { credentials: 'same-origin', ...init, headers: { ...CSRF, ...(init.headers as Record<string, string> | undefined) } })
  } catch {
    throw new ApiError(0, 'Cannot reach the API. Is the backend running?')
  }
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail ?? detail)
    } catch {
      /* non-JSON error body */
    }
    // A wrong password is also a 401, but that is the sign-in form's business, not a lost session.
    if (res.status === 401 && !path.startsWith('/api/auth/login')) window.dispatchEvent(new Event(UNAUTHORIZED_EVENT))
    throw new ApiError(res.status, detail)
  }
  return res.json() as Promise<T>
}

const qs = (o: Record<string, string | number | undefined | null>) => {
  const p = Object.entries(o).filter(([, v]) => v !== undefined && v !== null && v !== '')
  return p.length ? `?${p.map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`).join('&')}` : ''
}

const send = (method: 'POST' | 'PATCH', body: unknown): RequestInit => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
})

const json = (body: unknown): RequestInit => ({
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
})

function form(file: File, fields: Record<string, string | undefined>): RequestInit {
  const f = new FormData()
  f.append('file', file)
  for (const [k, v] of Object.entries(fields)) if (v) f.append(k, v)
  return { method: 'POST', body: f }
}

/** A region id of "IN" is the root: treat it as "no filter" is wrong, so every call passes it explicitly. */
export const api = {
  meta: () => req<Meta>('/api/meta'),
  regions: () => req<Region[]>('/api/regions'),
  regionSummary: (id: string) => req<RegionSummary>(`/api/regions/${id}/summary`),
  corridors: (region?: string) => req<CorridorCollection>(`/api/corridors${qs({ region })}`),
  sites: (region: string) => req<{ count: number; sites: SiteSummary[] }>(`/api/sites?region=${region}&limit=1000`),
  site: (id: string) => req<SiteDetail>(`/api/sites/${id}`),
  timeseries: (id: string) => req<TimeSeries>(`/api/sites/${id}/timeseries`),
  siteHistory: (id: string) => req<{ site_id: string; history: SiteHistoryPoint[] }>(`/api/sites/${id}/history`),
  points: (bbox: [number, number, number, number], limit = 4000) =>
    req<{ count: number; truncated: boolean; points: MapPoint[] }>(`/api/points?bbox=${bbox.join(',')}&limit=${limit}`),
  workOrder: (id: string, refresh = false, mode: 'auto' | 'template' = 'auto') =>
    req<WorkOrder>(`/api/sites/${id}/workorder${qs({ mode, refresh: refresh ? 'true' : undefined })}`, { method: 'POST' }),
  workOrderQueue: (region?: string) => req<WorkOrderQueue>(`/api/workorders${qs({ region })}`),

  alerts: (region: string, status?: string, severity?: string) => req<AlertsResponse>(`/api/alerts${qs({ region, status, severity })}`),
  alertAction: (b: { alert_id: string; action: AlertAction; actor?: string; note?: string; assignee?: string }) =>
    req<Alert>('/api/alerts/action', json(b)),

  earlyWarning: (region: string, asset_type?: string) => req<EarlyWarningBoard>(`/api/early-warning${qs({ region, asset_type })}`),
  scenario: (site_id: string, rate_change_pct: number) => req<Scenario>(`/api/early-warning/scenario${qs({ site_id, rate_change_pct })}`),
  trends: (region: string) => req<{ region: string | null; series: TrendPoint[]; passes: number }>(`/api/trends/portfolio${qs({ region })}`),
  movers: (region: string) => req<{ since: string | null; risers: Mover[]; fallers: Mover[] }>(`/api/trends/movers${qs({ region })}`),

  assets: (region: string) => req<{ count: number; assets: AssetBoardItem[] }>(`/api/assets${qs({ region })}`),
  asset: (id: string) => req<AssetDetail>(`/api/assets/${id}`),
  portfolio: (region: string) => req<Portfolio>(`/api/portfolio${qs({ region })}`),
  brief: (region: string) => req<Brief>(`/api/brief${qs({ region })}`),
  search: (q: string) => req<{ query: string; results: SearchResult[] }>(`/api/search${qs({ q })}`),
  methodology: () => req<Methodology>('/api/methodology'),

  dataStatus: () => req<DataStatus>('/api/data/status'),
  validateFile: (file: File, kind: UploadKind, defaultRegion?: string) =>
    req<ParseResultPayload>('/api/data/validate', form(file, { kind, default_region: defaultRegion })),
  uploadFile: (file: File, kind: UploadKind, mode: 'merge' | 'replace', defaultRegion?: string) =>
    req<ParseResultPayload>('/api/data/upload', form(file, { kind, mode, default_region: defaultRegion })),
  fetchUrl: (b: { url: string; kind?: UploadKind; mode: 'merge' | 'replace'; default_region?: string; dry_run?: boolean }) =>
    req<ParseResultPayload>('/api/data/fetch-url', json({ ...b, kind: b.kind === 'auto' ? undefined : b.kind })),
  fetchRain: (region_id: string, days: number) => req<RainFetchResult>('/api/data/fetch-rain', json({ region_id, days })),
  addRegion: (b: { name: string; region_id?: string; parent_id?: string | null; level: string; center_lon: number; center_lat: number; zoom: number }) =>
    req<Region>('/api/data/regions', json(b)),
  resetDemo: () => req<{ ok: boolean; workspace_removed: boolean }>('/api/data/reset-demo', { method: 'POST' }),
  syncBigQuery: () => req<{ ok: boolean; project: string; dataset: string; tables: Record<string, { written: number; total: number }> }>('/api/data/sync-bigquery', { method: 'POST' }),
  publicCatalog: () => req<{ datasets: PublicDataset[]; attribution: string }>('/api/data/public'),
  publicPreview: (id: string) => req<PublicPreview>(`/api/data/public/${id}/preview`),
  publicFetch: (id: string) => req<StoredPublicMeta>(`/api/data/public/${id}/fetch`, { method: 'POST' }),
  publicSeismicity: (b: { region_id: string; radius_km: number; days: number; min_mag: number }) => req<StoredPublicMeta>('/api/data/public/seismicity', json(b)),
  publicDelete: (id: string) => req<{ ok: boolean }>(`/api/data/public/${id}`, { method: 'DELETE' }),
  quakes: (bbox: [number, number, number, number], minMag = 2.5, limit = 1500) =>
    req<{ count: number; truncated: boolean; events: QuakeEvent[] }>(`/api/context/events?bbox=${bbox.join(',')}&min_mag=${minMag}&limit=${limit}`),
  bigQueryDoctor: () => req<DoctorResult>('/api/data/bigquery/doctor'),

  me: () => req<AuthMe>('/api/auth/me'),
  loginHint: () =>
    req<{ enabled: boolean; username?: string; password?: string | null; role?: string; note?: string }>('/api/auth/login-hint'),
  login: (username: string, password: string) => req<{ auth_enabled: boolean; user: SessionUser }>('/api/auth/login', json({ username, password })),
  logout: () => req<{ ok: boolean }>('/api/auth/logout', { method: 'POST' }),
  changePassword: (current_password: string, new_password: string) => req<{ ok: boolean }>('/api/auth/password', json({ current_password, new_password })),
  users: () => req<{ users: UserRow[]; roles: Role[] }>('/api/auth/users'),
  createUser: (b: { username: string; display_name: string; role: Role; password: string }) => req<UserRow>('/api/auth/users', json(b)),
  updateUser: (username: string, b: { role?: Role; disabled?: boolean; password?: string; display_name?: string }) =>
    req<UserRow>(`/api/auth/users/${encodeURIComponent(username)}`, send('PATCH', b)),
  audit: (limit = 60) => req<{ events: AuditEvent[] }>(`/api/auth/audit?limit=${limit}`),

  templateUrl: (kind: string) => `${BASE}/api/data/templates/${kind}`,
  exportUrl: (kind: string) => `${BASE}/api/data/export/${kind}`,
}
