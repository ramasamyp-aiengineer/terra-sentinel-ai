"""Central configuration: environment settings + asset-type threshold profiles.

All detection thresholds live here so they are documented, testable and
adjustable per asset type (a highway slope is not a metro tunnel is not a dam).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="TS_", extra="ignore")

    data_dir: Path = REPO_ROOT / "data" / "demo"  # read-only baseline demo dataset
    # Writable copy created on the first upload; deleted by "Reset to demo".
    workspace_dir: Path = REPO_ROOT / "data" / "workspace"
    cache_dir: Path = REPO_ROOT / "data" / "cache"
    # Dataset registry, alert actions, daily snapshots (local mode). BigQuery mode uses tables instead.
    state_dir: Path = REPO_ROOT / "data" / "state"
    # "local" reads CSV/GeoJSON; "bigquery" reads and writes the BigQuery dataset.
    data_backend: str = "local"
    gcp_project: str = ""
    gcp_region: str = "us-central1"
    bq_location: str = "US"
    bq_dataset: str = "terrasentinel"
    # Path to a service-account key JSON. Empty = Application Default Credentials (gcloud login, Cloud Run identity).
    google_credentials_file: str = ""
    # Hard cost guard: any query that would scan more than this many GB fails instead of billing.
    bq_max_gb_billed: float = 10.0
    # How long BigQuery reads are reused in memory before re-querying.
    bq_cache_ttl_s: int = 300
    # Local CSV storage is for demos and small pilots; refuse to silently crawl on big files.
    max_local_timeseries_rows: int = 3_000_000
    max_upload_mb: int = 50
    fetch_timeout_s: float = 30.0
    # Plain-http fetches are refused unless explicitly enabled (e.g. an internal mirror).
    allow_http_fetch: bool = False
    # Pre-compute historical passes in the background after startup / data changes.
    warm_on_change: bool = True
    # Gemini API key (Google AI Studio). When set it is used instead of Vertex AI.
    gemini_api_key: str = ""
    gemini_model: str = "gemini-flash-latest"
    # Tried in order when the primary model returns 429/5xx (overloaded or quota).
    gemini_fallback_models: str = "gemini-flash-lite-latest,gemini-3.7-flash,gemini-3.5-flash"
    gemini_timeout_s: float = 20.0
    # Total time spent trying models for one work order before using the template.
    gemini_budget_s: float = 30.0
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    # --- access control -------------------------------------------------------------------------
    # Sign-in is on by default. Set TS_AUTH_ENABLED=false only for local development.
    auth_enabled: bool = True
    # HMAC key for session cookies. Empty = generate one and keep it in state_dir (survives restarts).
    session_secret: str = ""
    session_ttl_h: float = 12.0
    # None = mark the cookie Secure whenever the request arrived over https.
    cookie_secure: bool | None = None
    # First-run administrator. Empty password = generate one, log it once and save it under state_dir.
    admin_user: str = "admin"
    admin_password: str = ""
    # Lock a username (per client address) after this many wrong passwords, for this many seconds.
    login_max_failures: int = 5
    login_lockout_s: int = 300
    # Trust X-Forwarded-For for the client address (only behind a proxy you control, e.g. Cloud Run).
    trust_proxy: bool = False
    # How many proxies sit in front of the API; the client address is that many entries from the right of X-Forwarded-For.
    proxy_hops: int = 1
    # Requests per minute per client for the whole API (a coarse brake; sensitive routes have tighter ones).
    api_rate_per_min: int = 900
    # Built frontend served by the API in a single-container deployment. Empty = auto-detect frontend/dist.
    static_dir: str = ""
    # Where fetched public datasets are kept as CSV (a cache that can be deleted and re-fetched).
    public_dir: Path = REPO_ROOT / "data" / "public"
    # The reference "today" for the demo dataset (last satellite epoch + a few days).
    as_of_date: str = ""


settings = Settings()


@dataclass(frozen=True)
class AssetProfile:
    """Operational thresholds for one asset type. Units: mm, days."""

    asset_type: str
    label: str
    buffer_m: float
    # Minimum recent speed (mm/month, magnitude) to count as real creep.
    creep_mm_month: float
    # Recent-vs-baseline speed ratio that counts as acceleration.
    accel_ratio: float
    # Operational threshold: cumulative displacement over the trailing window.
    threshold_mm: float
    threshold_window_days: int
    # Early-warning planning horizon (days) for "approaching threshold".
    approach_days: int
    # Coherence below this -> data-degraded.
    min_coherence: float
    mechanism_hint: str


PROFILES: dict[str, AssetProfile] = {
    "HIGHWAY": AssetProfile(
        asset_type="HIGHWAY",
        label="Highway / mountain road",
        buffer_m=150,
        creep_mm_month=2.0,
        accel_ratio=1.8,
        threshold_mm=40.0,
        threshold_window_days=180,
        approach_days=60,
        min_coherence=0.55,
        mechanism_hint="slope creep / toe-unloading slip",
    ),
    "METRO": AssetProfile(
        asset_type="METRO",
        label="Metro / urban tunnel corridor",
        buffer_m=100,
        creep_mm_month=1.5,
        accel_ratio=1.8,
        threshold_mm=25.0,
        threshold_window_days=180,
        approach_days=45,
        min_coherence=0.65,
        mechanism_hint="settlement trough above tunnelling / dewatering",
    ),
    "DAM": AssetProfile(
        asset_type="DAM",
        label="Dam / tailings embankment",
        buffer_m=200,
        creep_mm_month=1.0,
        accel_ratio=1.6,
        threshold_mm=30.0,
        threshold_window_days=180,
        approach_days=60,
        min_coherence=0.6,
        mechanism_hint="crest settlement / downstream bulging / seepage creep",
    ),
}

DEFAULT_PROFILE = PROFILES["HIGHWAY"]


def profile_for(asset_type: str) -> AssetProfile:
    return PROFILES.get(asset_type.upper(), DEFAULT_PROFILE)
