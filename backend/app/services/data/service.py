"""Data Hub orchestration: validate -> write -> register provenance -> refresh -> sanity-check."""
from __future__ import annotations

import functools
import io
import json
import uuid

import pandas as pd

from app.core.config import settings
from app.services import runtime
from app.services.data import connectors, ingest
from app.services.data.repo import RowLimitError, get_repo, reset_workspace, workspace_exists, workspace_transaction
from app.services.data.state import get_state, now_iso

KIND_LABEL = {
    "points": "InSAR points",
    "timeseries": "InSAR time series",
    "rain": "Rainfall",
    "assets": "Assets",
    "regions": "Regions",
    "events": "Earthquake events",
}
WRITE_ORDER = ["regions", "assets", "points", "timeseries", "rain"]  # parents before children


class DataError(ValueError):
    """A request the user can fix (bad input, unsupported action)."""


def transactional(fn):
    """Run a data-changing operation as one all-or-nothing, one-at-a-time step (see workspace_transaction)."""

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        with workspace_transaction():
            return fn(*args, **kwargs)

    return wrapper


def _context(filename: str, default_region: str | None) -> ingest.ParseContext:
    return ingest.ParseContext(filename=filename, regions=get_repo().regions(), default_region=default_region or None)


def _date_range(kind: str, payload) -> tuple[str | None, str | None]:
    if kind in ("timeseries", "rain") and isinstance(payload, pd.DataFrame) and len(payload):
        return str(payload["date"].min().date()), str(payload["date"].max().date())
    return None, None


def _rows(payload) -> int:
    return len(payload)


# ---------------------------------------------------------------------------


def validate(filename: str, content: bytes, kind: str | None = None, default_region: str | None = None) -> dict:
    """Dry run: parse and report, write nothing."""
    result = ingest.parse_upload(filename, content, kind, _context(filename, default_region))
    return result.to_dict()


def ingest_file(
    filename: str,
    content: bytes,
    kind: str | None = None,
    mode: str = "merge",
    default_region: str | None = None,
    source_type: str = "upload",
    source_ref: str | None = None,
) -> dict:
    if mode not in ("merge", "replace"):
        raise DataError("mode must be 'merge' or 'replace'.")
    result = ingest.parse_upload(filename, content, kind, _context(filename, default_region))
    if not result.ok:
        return {**result.to_dict(), "written": {}, "applied": False}
    return _apply(result, ingest.clean_filename(filename), mode, source_type, source_ref)


@transactional
def _apply(result, filename: str, mode: str, source_type: str, source_ref: str | None) -> dict:
    repo = get_repo()
    written: dict[str, dict] = {}
    try:
        for k in WRITE_ORDER:
            if k in result.payloads:
                written[k] = repo.write(k, result.payloads[k], mode)  # type: ignore[arg-type]
    except RowLimitError as exc:
        raise DataError(str(exc)) from exc

    state = get_state()
    for k, payload in result.payloads.items():
        d0, d1 = _date_range(k, payload)
        rep = next((r for r in result.reports if r.kind == k), None)
        state.add_dataset(
            {
                "dataset_id": uuid.uuid4().hex[:8],
                "kind": k,
                "name": filename,
                "source_type": source_type,
                "source_ref": source_ref or filename,
                "rows": _rows(payload),
                "date_min": d0,
                "date_max": d1,
                "mode": mode,
                "notes": (rep.warnings[:3] if rep else []),
                "added_at": now_iso(),
            }
        )
    runtime.refresh_all()
    return {
        **result.to_dict(),
        "written": written,
        "applied": True,
        "post_checks": post_checks(set(result.payloads), written),
    }


def ingest_url(url: str, kind: str | None, mode: str, default_region: str | None) -> dict:
    try:
        filename, content = connectors.fetch_url(url)
    except connectors.FetchError as exc:
        raise DataError(str(exc)) from exc
    out = ingest_file(filename, content, kind, mode, default_region, source_type="url", source_ref=url)
    out["fetched_as"] = filename
    out["bytes"] = len(content)
    return out


@transactional
def fetch_region_rain(region_id: str, days: int = 60) -> dict:
    repo = get_repo()
    region = next((r for r in repo.regions() if r["region_id"] == region_id), None)
    if region is None:
        raise DataError(f"Unknown region {region_id!r}.")
    try:
        df = connectors.fetch_rain(region["center"][0], region["center"][1], region_id, days)
    except connectors.FetchError as exc:
        raise DataError(str(exc)) from exc

    written = repo.write("rain", df, "merge")
    get_state().add_dataset(
        {
            "dataset_id": uuid.uuid4().hex[:8],
            "kind": "rain",
            "name": f"Open-Meteo rainfall - {region['name']}",
            "source_type": "open-meteo",
            "source_ref": f"{region['center'][1]},{region['center'][0]}",
            "rows": len(df),
            "date_min": str(df["date"].min().date()),
            "date_max": str(df["date"].max().date()),
            "mode": "merge",
            "notes": [],
            "added_at": now_iso(),
        }
    )
    runtime.refresh_all()

    from app.services.detection.pipeline import as_of_date

    as_of = as_of_date(get_repo())
    window_start = as_of - pd.Timedelta(days=14)
    overlap = int(((df["date"] > window_start) & (df["date"] <= as_of)).sum())
    warnings = []
    if overlap == 0:
        warnings.append(
            f"The fetched rainfall ({df['date'].min().date()} to {df['date'].max().date()}) does not overlap the "
            f"assessment date ({as_of.date()}), so it will not change rankings until your InSAR data is as recent."
        )
    return {
        "ok": True,
        "region_id": region_id,
        "rows": len(df),
        "date_min": str(df["date"].min().date()),
        "date_max": str(df["date"].max().date()),
        "total_mm": round(float(df["precip_mm"].sum()), 1),
        "written": written,
        "overlap_days_in_assessment_window": overlap,
        "warnings": warnings,
        "source": "Open-Meteo (open-meteo.com), observed/reanalysis daily precipitation",
    }


@transactional
def add_region(region: dict) -> dict:
    region = {**region}
    if not region.get("region_id"):
        region["region_id"] = ingest._slug(region.get("name") or "")
    rep_in = [region]
    regions, rep = ingest.parse_regions(rep_in, _context("manual", None))
    if not rep.ok:
        raise DataError(rep.errors[0]["message"] if rep.errors else (rep.blocked_reason or "Invalid region."))
    get_repo().write("regions", regions, "merge")
    get_state().add_dataset(
        {
            "dataset_id": uuid.uuid4().hex[:8],
            "kind": "regions",
            "name": regions[0]["name"],
            "source_type": "manual",
            "source_ref": "Data Hub form",
            "rows": 1,
            "date_min": None,
            "date_max": None,
            "mode": "merge",
            "notes": [],
            "added_at": now_iso(),
        }
    )
    runtime.refresh_all()
    return regions[0]


@transactional
def reset_to_demo() -> dict:
    if settings.data_backend.lower() == "bigquery":
        raise DataError("Reset is only available for the local workspace. In BigQuery mode, manage tables from the console.")
    existed = reset_workspace()
    # Public datasets live outside the workspace (their CSVs are kept), so their provenance rows stay too.
    state = get_state()
    state.reset_datasets([d for d in state.list_datasets() if d.get("source_type") == "public"])
    runtime.refresh_all()
    return {"ok": True, "workspace_removed": existed}


# ---------------------------------------------------------------------------


def post_checks(kinds: set[str], written: dict | None = None) -> list[dict]:
    """Plain-language findings about whether the new data will actually produce sites."""
    from app.services.detection.pipeline import run_pipeline

    out: list[dict] = []
    written = written or {}
    dropped = int((written.get("points") or {}).get("orphan_timeseries_dropped") or 0)
    if dropped:
        out.append(
            {
                "level": "warning",
                "message": (
                    f"{dropped:,} previous time-series row(s) were removed because their points were replaced. "
                    "Upload a matching time series next, or use the wide InSAR template that carries points and epochs together."
                ),
            }
        )
    repo = get_repo()
    pts, ts = repo.points(), repo.timeseries()
    if kinds & {"points", "timeseries"}:
        no_ts = int((~pts["point_id"].isin(ts["point_id"].unique())).sum()) if len(pts) else 0
        if no_ts:
            out.append({"level": "warning", "message": f"{no_ts:,} point(s) have no time series and cannot be assessed."})
        orphan = int((~ts["point_id"].isin(pts["point_id"].unique())).sum()) if len(ts) else 0
        if orphan:
            out.append({"level": "warning", "message": f"{orphan:,} time-series row(s) reference unknown points and are ignored."})
        if len(pts) and len(ts) == 0:
            out.append(
                {
                    "level": "warning",
                    "message": "There is no time series in the workspace yet, so rankings stay empty until epochs are imported.",
                }
            )
    if kinds & {"assets", "points", "timeseries"}:
        sites = run_pipeline()
        have = {s.asset_id for s in sites}
        for a in repo.assets():
            if a.asset_id not in have:
                out.append({"level": "warning", "message": f"Asset {a.asset_id} ({a.name}) has no scatterers inside its buffer - no sites were created. Check coordinates or add InSAR points near it."})
        out.append({"level": "info", "message": f"{len(sites)} monitored site(s) across {len(have)} asset(s) after this change."})
    return out


def status() -> dict:
    repo = get_repo()
    state = get_state()
    from app.services.detection.pipeline import as_of_date

    datasets = state.list_datasets()
    # Built-in demo data stays listed for every kind the user has not fully replaced:
    # merged uploads sit on top of it, so it is still part of what the analysis reads.
    replaced = {d["kind"] for d in datasets if d.get("mode") == "replace"}
    datasets = [*datasets, *[s for s in _demo_seed(repo) if s["kind"] not in replaced]]
    bq = bigquery_status()
    return {
        "backend": repo.backend,
        "workspace_active": workspace_exists() and settings.data_backend.lower() != "bigquery",
        "data_source": repo.data_source(),
        "counts": repo.counts(),
        "as_of": str(as_of_date(repo).date()),
        "datasets": sorted(datasets, key=lambda d: d["added_at"], reverse=True),
        "limits": {"max_upload_mb": settings.max_upload_mb, "max_local_timeseries_rows": settings.max_local_timeseries_rows},
        "bigquery": bq,
        "kinds": KIND_LABEL,
    }


def _demo_seed(repo) -> list[dict]:
    c = repo.counts()
    t = "2026-01-01T00:00:00+00:00"
    base = {"source_type": "demo", "source_ref": "data/demo (synthetic)", "mode": "seed", "notes": ["Synthetic - follows the schema of real InSAR products."], "added_at": t}
    return [
        {**base, "dataset_id": "demo-pts", "kind": "points", "name": "Demo InSAR points", "rows": c["points"], "date_min": None, "date_max": None},
        {**base, "dataset_id": "demo-ts", "kind": "timeseries", "name": "Demo InSAR time series", "rows": c["timeseries_rows"], "date_min": c["date_min"], "date_max": c["date_max"]},
        {**base, "dataset_id": "demo-rain", "kind": "rain", "name": "Demo rainfall", "rows": c["rain_rows"], "date_min": None, "date_max": None},
        {**base, "dataset_id": "demo-assets", "kind": "assets", "name": "Demo assets", "rows": c["assets"], "date_min": None, "date_max": None},
        {**base, "dataset_id": "demo-regions", "kind": "regions", "name": "Demo regions", "rows": c["regions"], "date_min": None, "date_max": None},
    ]


_PROBE_TTL_S = 60.0
_probe_cache: dict = {}


def clear_bigquery_probe() -> None:
    _probe_cache.clear()


def _cached_probe() -> dict:
    """Probing can take ~20 s when credentials are missing (google-auth waits on the cloud metadata server), and the
    Data Hub polls status. Remember the answer briefly so a misconfiguration does not make the whole page slow."""
    import time

    from app.services.bq import client as bqc

    key = (settings.gcp_project, settings.bq_dataset, settings.google_credentials_file)
    hit = _probe_cache.get(key)
    if hit and time.monotonic() - hit[0] < _PROBE_TTL_S:
        return hit[1]
    result = bqc.probe()
    _probe_cache[key] = (time.monotonic(), result)
    return result


def bigquery_status() -> dict:
    configured = bool(settings.gcp_project)
    base = {
        "configured": configured,
        "active": settings.data_backend.lower() == "bigquery",
        "project": settings.gcp_project or None,
        "dataset": settings.bq_dataset,
        "location": settings.bq_location,
    }
    if not configured:
        if base["active"]:
            detail = (
                "TS_DATA_BACKEND=bigquery but TS_GCP_PROJECT is not set. "
                "Set TS_GCP_PROJECT=your-project-id or switch to TS_DATA_BACKEND=local. See docs/BIGQUERY.md."
            )
        else:
            detail = "Set TS_GCP_PROJECT (and credentials) to enable BigQuery. See docs/BIGQUERY.md."
        return {**base, "reachable": False, "detail": detail}
    try:
        return {**base, **_cached_probe()}
    except Exception as exc:  # noqa: BLE001 - status must never raise
        return {**base, "reachable": False, "detail": f"{exc.__class__.__name__}: {exc}"[:240]}


def sync_to_bigquery() -> dict:
    if not settings.gcp_project:
        raise DataError("BigQuery is not configured. Set TS_GCP_PROJECT and Google credentials first (docs/BIGQUERY.md).")
    from app.services.bq import loader
    from app.services.bq.client import BigQueryUnavailable

    try:
        out = loader.sync_repo(get_repo())
        clear_bigquery_probe()
        return out
    except BigQueryUnavailable as exc:
        raise DataError(str(exc)) from exc


def export(kind: str) -> tuple[str, str, bytes]:
    """(filename, media_type, bytes) of the current data for one kind."""
    repo = get_repo()
    if kind == "points":
        buf = repo.points().to_csv(index=False)
        return "insar_points.csv", "text/csv", buf.encode()
    if kind == "timeseries":
        buf = repo.timeseries().to_csv(index=False, date_format="%Y-%m-%d")
        return "insar_timeseries.csv", "text/csv", buf.encode()
    if kind == "rain":
        buf = repo.rain().to_csv(index=False, date_format="%Y-%m-%d")
        return "rain.csv", "text/csv", buf.encode()
    if kind == "assets":
        return "assets.geojson", "application/geo+json", json.dumps(repo.assets_geojson()).encode()
    if kind == "regions":
        df = pd.DataFrame(
            [{"region_id": r["region_id"], "parent_id": r["parent_id"], "name": r["name"], "level": r["level"], "center_lon": r["center"][0], "center_lat": r["center"][1], "zoom": r["zoom"]} for r in repo.regions()]
        )
        out = io.StringIO()
        df.to_csv(out, index=False)
        return "regions.csv", "text/csv", out.getvalue().encode()
    raise DataError(f"Unknown data kind {kind!r}.")
