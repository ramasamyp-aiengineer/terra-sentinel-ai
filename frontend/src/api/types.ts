import type { FeatureCollection, LineString } from 'geojson'

export type Tier = 'CRITICAL' | 'ELEVATED' | 'WATCH' | 'STABLE' | 'WEAK'

export interface Region {
  region_id: string
  parent_id: string | null
  name: string
  level: string
  center: [number, number]
  zoom: number
}

export interface SiteSummary {
  site_id: string
  asset_id: string
  asset_name: string
  asset_type: string
  region_id: string
  label: string
  chainage_start_km: number
  chainage_end_km: number
  lat: number
  lon: number
  tier: Tier
  state: string
  rpi: number
  criticality: number
  consequence_note: string
  rate_recent_mm_month: number
  accel_ratio: number
  d60_mm: number
  d_window_mm: number
  outlook_status: string
  eta_low_days: number | null
  eta_high_days: number | null
  confidence: number
  confidence_label: string
  n_points: number
  headline: string
}

export interface Outlook {
  status: string
  threshold_mm: number
  progress_mm: number
  eta_low_days: number | null
  eta_high_days: number | null
  eta_constant_days: number | null
  eta_accelerating_days: number | null
  assumptions: string[]
}

export interface SiteDetail extends SiteSummary {
  state_reasons: string[]
  metrics: {
    n_epochs: number
    span_days: number
    last_epoch: string
    current_disp_mm: number
    rate_recent_mm_month: number
    rate_baseline_mm_month: number
    accel_ratio: number
    d60_mm: number
    d_window_mm: number
    persistence: number
    noise_mm: number | null
    seasonal_flag: boolean
    peak_excursion_mm: number
  }
  outlook: Outlook
  confidence_detail: { score: number; label: string; drivers: Record<string, number> }
  rpi_breakdown: Record<string, number>
  coherence_mean: number
  agreement: number
  thresholds: {
    operational_threshold_mm: number
    window_days: number
    creep_mm_month: number
    accel_ratio: number
    approach_days: number
    mechanism_hint: string
  }
  rain: {
    region_id: string
    window_days: number
    rain_14d_mm: number
    rain_7d_mm: number
    peak_day_mm: number
    trigger_score: number
    source: string
  } | null
  seismic: SeismicContext
  as_of: string
  data_source: string
}

export interface Projection {
  days_ahead: number[]
  constant_mm: number[]
  accelerating_mm: number[] | null
  threshold_level_mm: number
  window_reference_mm: number
}

export interface TimeSeries {
  site_id: string
  dates: string[]
  disp_mm: number[]
  q25_mm: (number | null)[]
  q75_mm: (number | null)[]
  projection: Projection | null
  threshold_mm: number
  rain: { date: string; precip_mm: number }[]
  as_of: string
  last_epoch: string
}

export interface RegionSummary {
  region: Region | null
  total_sites: number
  by_tier: Record<Tier, number>
  accelerating_sites: number
  approaching_threshold_60d: number
  data_degraded_sites: number
  act_list: SiteSummary[]
  as_of: string
  data_source: string
}

export interface Meta {
  product: string
  data_source: string
  is_demo: boolean
  backend: string
  as_of: string
  sites: number
  disclaimer: string
}

export interface MapPoint {
  point_id: string
  lat: number
  lon: number
  velocity_mm_yr: number
  coherence: number
  last_disp_mm: number | null
  site_id: string | null
  tier: Tier | 'UNMONITORED'
}

export interface WorkOrder {
  ticket_id: string
  site_id: string
  tier: Tier
  priority_label: string
  asset_name: string
  chainage: string
  lat: number
  lon: number
  as_of: string
  data_source: string
  consequence: string
  evidence: { label: string; value: string; source: string }[]
  outlook_text: string
  summary: string
  mechanism_hypothesis: string
  recommended_action: string
  checklist: { item: string; why: string | null }[]
  limitations: string[]
  citations: string[]
  generated_by: 'gemini' | 'template'
  model: string | null
  validation: { passed: boolean; issues: string[]; numbers_checked: number }
  tool_calls: { tool: string }[]
}

export type CorridorCollection = FeatureCollection<
  LineString,
  { asset_id: string; name: string; asset_type: string; worst_tier: Tier; site_count: number }
>

/* ------------------------------------------------------------------ intelligence */

export type Severity = 'critical' | 'high' | 'medium' | 'info'
export type AlertStatus = 'open' | 'acknowledged' | 'assigned' | 'escalated' | 'resolved'
export type AlertAction = 'acknowledge' | 'assign' | 'escalate' | 'resolve' | 'reopen'

export interface AlertHistoryEntry {
  alert_id: string
  action: AlertAction
  actor: string
  note: string
  assignee: string | null
  at: string
}

export interface Alert {
  alert_id: string
  as_of: string
  pass_index: number
  kind: string
  also: string[]
  severity: Severity
  title: string
  detail: string
  site_id: string | null
  region_id: string
  asset_id: string | null
  asset_name: string | null
  tier: Tier | null
  previous_tier: Tier | null
  rpi: number | null
  lat: number | null
  lon: number | null
  status: AlertStatus
  assignee: string | null
  history: AlertHistoryEntry[]
}

export interface AlertsResponse {
  count: number
  summary: {
    total: number
    open: number
    open_critical: number
    latest_pass: number
    by_status: Record<AlertStatus, number>
  }
  alerts: Alert[]
}

export interface EarlyWarningSite extends SiteSummary {
  bucket: 'exceeded' | 'd0_30' | 'd31_60' | 'd61_120' | 'd121_365' | 'none'
  progress_mm: number
  threshold_mm: number
  progress_pct: number
  eta_constant_days: number | null
  eta_accelerating_days: number | null
  assumptions: string[]
  rate_baseline_mm_month: number
  rpi_previous: number | null
  rpi_delta: number | null
  tier_previous: Tier | null
  state_reasons: string[]
}

export interface EarlyWarningBoard {
  as_of: string | null
  buckets: { key: EarlyWarningSite['bucket']; label: string; count: number }[]
  sites: EarlyWarningSite[]
  note: string
}

export interface Scenario {
  site_id: string
  rate_change_pct: number
  threshold_mm: number
  progress_mm: number
  remaining_mm: number
  current_rate_mm_month: number
  scenario_rate_mm_month: number
  linear_days_current: number | null
  linear_days_scenario: number | null
  engine_band_days: [number | null, number | null]
  within_planning_horizon: boolean
  approach_days: number
  note: string
}

export interface TrendPoint {
  as_of: string
  pass_index: number
  counts: Record<Tier, number>
  act_sites: number
  max_rpi: number
  mean_act_rpi: number
  accelerating: number
  approaching_60d: number
}

export interface Mover {
  site_id: string
  label: string
  asset_name: string
  tier: Tier
  previous_tier: Tier
  rpi: number
  previous_rpi: number
  delta_rpi: number
  tier_change: number
}

export interface SiteHistoryPoint {
  as_of: string
  tier: Tier
  rpi: number
  state: string
  rate_mm_month: number
  accel_ratio: number
  eta_low_days: number | null
  eta_high_days: number | null
  progress_mm: number
}

export interface AssetBoardItem {
  asset_id: string
  name: string
  asset_type: string
  type_label: string
  region_id: string
  region_name: string
  criticality: number
  consequence_note: string
  length_km: number
  sites: number
  points: number
  tier_counts: Record<Tier, number>
  worst_tier: Tier
  max_rpi: number
  earliest_eta_days: number | null
  moving_sites: number
  mean_moving_rate_mm_month: number
  center: [number, number]
  bbox: [number, number, number, number]
}

export interface AssetDetail extends AssetBoardItem {
  strip: { site_id: string; km_start: number; km_end: number; tier: Tier; rpi: number; state: string; rate_mm_month: number; n_points: number }[]
  top_sites: SiteSummary[]
  profile: { buffer_m: number; threshold_mm: number; window_days: number; mechanism_hint: string }
}

export interface Portfolio {
  region: string | null
  as_of: string
  data_source: string
  totals: { sites: number; assets: number; points: number; tier_counts: Record<Tier, number>; act_sites: number; exposure: number; earliest_eta_days: number | null }
  by_region: {
    region_id: string
    name: string
    level: string
    sites: number
    tier_counts: Record<Tier, number>
    worst_tier: Tier
    max_rpi: number
    act_sites: number
    exposure: number
    earliest_eta_days: number | null
  }[]
  by_asset_type: { asset_type: string; label: string; sites: number; tier_counts: Record<Tier, number>; act_sites: number }[]
  rain: { region_id: string; name: string; rain_14d_mm: number; peak_day_mm: number; trigger_score: number }[]
  top_sites: SiteSummary[]
  data_health: { last_epoch: string | null; days_since_last_epoch: number | null; epochs: number; weak_sites: number; mean_confidence: number | null; fresh: boolean }
}

export interface Brief {
  as_of: string
  region: string | null
  region_name: string
  headline: string
  counts: Record<Tier, number>
  sections: { title: string; bullets: string[] }[]
  top_actions: SiteSummary[]
  generated_by: string
  note: string
}

export interface SearchResult {
  type: 'region' | 'asset' | 'site'
  id: string
  title: string
  subtitle: string
  lon: number
  lat: number
  zoom: number
}

export interface Methodology {
  principle: string
  pipeline: { step: string; text: string }[]
  tiers: { tier: Tier; rule: string }[]
  rpi: { formula: string; hazard: string; consequence: string; confidence: string; guards: string[] }
  profiles: {
    asset_type: string
    label: string
    buffer_m: number
    threshold_mm: number
    window_days: number
    creep_mm_month: number
    accel_ratio: number
    approach_days: number
    min_coherence: number
    mechanism_hint: string
  }[]
  alerts: string[]
  limitations: string[]
}

export interface WorkOrderQueue {
  count: number
  drafted: number
  sites: (SiteSummary & { work_order: { ticket_id: string; generated_by: string; as_of: string } | null })[]
  agent: { gemini_configured: boolean; provider: 'api-key' | 'vertex' | 'none'; project: string | null; region: string; model: string; mode: string }
}

/* ------------------------------------------------------------------ data hub */

export type DataKind = 'points' | 'timeseries' | 'rain' | 'assets' | 'regions' | 'events'
export type UploadKind = DataKind | 'insar' | 'auto'

export interface ValidationReport {
  kind: string
  ok: boolean
  detected_format: string
  rows_in: number
  rows_ok: number
  rows_rejected: number
  errors: { row: number | string; field: string; message: string }[]
  warnings: string[]
  mapped_columns: Record<string, string>
  summary: Record<string, unknown>
  preview: Record<string, unknown>[]
  blocked_reason: string | null
}

export interface ParseResultPayload {
  ok: boolean
  reports: ValidationReport[]
  applied?: boolean
  written?: Record<string, { written: number; total: number; orphan_timeseries_dropped?: number }>
  post_checks?: { level: 'info' | 'warning'; message: string }[]
  fetched_as?: string
  bytes?: number
}

export interface DatasetEntry {
  dataset_id: string
  kind: DataKind
  name: string
  source_type: string
  source_ref: string
  rows: number
  date_min: string | null
  date_max: string | null
  mode: string
  notes: string[]
  added_at: string
}

export interface DataStatus {
  backend: string
  workspace_active: boolean
  data_source: string
  counts: { regions: number; assets: number; points: number; timeseries_rows: number; epochs: number; rain_rows: number; date_min: string | null; date_max: string | null }
  as_of: string
  datasets: DatasetEntry[]
  limits: { max_upload_mb: number; max_local_timeseries_rows: number }
  bigquery: { configured: boolean; active: boolean; project: string | null; dataset: string; location: string; reachable: boolean; detail: string; tables?: string[] }
  kinds: Record<DataKind, string>
}

export interface RainFetchResult {
  ok: boolean
  region_id: string
  rows: number
  date_min: string
  date_max: string
  total_mm: number
  overlap_days_in_assessment_window: number
  warnings: string[]
  source: string
}

/* ---- access control ------------------------------------------------------------------ */

export type Role = 'viewer' | 'analyst' | 'admin'

export interface SessionUser {
  username: string
  display_name: string
  role: Role
}

export interface AuthMe {
  auth_enabled: boolean
  user: SessionUser | null
  roles: Role[]
  password_min_length: number
  /** Set client-side when the server says the session ended while the app was open. */
  expired?: boolean
}

export interface UserRow {
  username: string
  display_name: string
  role: Role
  disabled: boolean
  created_at: string
  last_login: string | null
}

export interface AuditEvent {
  at: string
  event: string
  actor: string
  ip: string
  detail: string
}

/* ---- public data and context ----------------------------------------------------------- */

export interface StoredPublicMeta {
  id: string
  title: string
  publisher: string
  license: string
  source_url: string
  fetched_at: string
  rows: number
  date_min: string
  date_max: string
  bytes: number
  sha256: string
  max_magnitude: number
  citation: string
  age_days: number
  stale: boolean
}

export interface PublicDataset {
  id: string
  title: string
  publisher: string
  license: string
  description: string
  scope: 'global' | 'region'
  refresh_days: number
  url: string
  stored: StoredPublicMeta | null
}

export interface PublicPreview {
  meta: StoredPublicMeta
  largest: { time: string; mag: number; place: string; latitude: number; longitude: number }[]
  by_magnitude: Record<string, number>
}

export interface SeismicEvent {
  time: string
  mag: number
  distance_km: number
  depth_km: number | null
  place: string
}

export interface SeismicContext {
  available: boolean
  source: string
  note: string
  message?: string
  recent: { radius_km: number; window_days: number; min_magnitude: number }
  history: { radius_km: number; min_magnitude: number }
  coverage: { datasets: string[]; date_from?: string; date_to?: string }
  recent_count?: number
  recent_max_magnitude?: number | null
  recent_nearest_km?: number | null
  recent_events?: SeismicEvent[]
  history_count?: number
  history_largest?: SeismicEvent | null
  warnings?: string[]
}

export interface QuakeEvent {
  id: string
  time: string
  mag: number
  lat: number
  lon: number
  place: string
}

export interface DoctorCheck {
  id: string
  label: string
  status: 'pass' | 'warn' | 'fail' | 'skip'
  detail: string
  fix: string
}

export interface DoctorResult {
  state: 'ready' | 'ready-not-active' | 'ready-with-notes' | 'blocked'
  headline: string
  checks: DoctorCheck[]
}
