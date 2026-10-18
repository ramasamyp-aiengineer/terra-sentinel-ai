"""Load data into BigQuery: stage in a temporary table, then MERGE (idempotent) or TRUNCATE + INSERT.

Staging + MERGE means re-uploading the same file never duplicates rows, a failed load never leaves a
half-written target, and GEOGRAPHY columns are computed in SQL from plain lat/lon or GeoJSON.

Runner labels are ``op:table[:staging]`` so a test double can interpret each statement without parsing SQL.
"""
from __future__ import annotations

import json
import uuid

import pandas as pd

from app.services.bq import segments, sql
from app.services.bq.client import Runner, get_runner
from app.services.bq.schema import ASSET_SEGMENTS, ASSETS, TABLES, Table, fq


def _frame(kind: str, payload) -> pd.DataFrame:
    if kind == "assets":
        return segments.assets_frame(payload)
    if kind == "regions":
        rows = [
            {
                "region_id": r["region_id"],
                "parent_id": r.get("parent_id"),
                "name": r["name"],
                "level": r["level"],
                "center_lon": float(r["center"][0]),
                "center_lat": float(r["center"][1]),
                "zoom": float(r["zoom"]),
            }
            for r in payload
        ]
        return pd.DataFrame(rows)
    df = payload.copy()
    if "date" in df:
        df["date"] = pd.to_datetime(df["date"]).dt.date
    return df


def _stage(runner: Runner, t: Table, df: pd.DataFrame) -> str:
    stg = f"{t.name}_stg_{uuid.uuid4().hex[:8]}"
    cols = [n for n, _ in t.load_columns]
    runner.load_df(df[cols], stg, list(t.load_columns), replace=True)
    return stg


def _drop(runner: Runner, stg: str) -> None:
    runner.execute(f"DROP TABLE IF EXISTS `{runner.project}.{runner.dataset}.{stg}`", label=f"drop::{stg}")


def _count(runner: Runner, name: str) -> int:
    df = runner.query_df(f"SELECT COUNT(*) AS n FROM {fq(runner.project, runner.dataset, name)}", label=f"count:{name}")
    return int(df["n"].iloc[0])


def _with_computed(t: Table, df: pd.DataFrame) -> pd.DataFrame:
    """Materialise SQL-computed GEOGRAPHY columns in Python so a load job can WRITE_TRUNCATE without DML."""
    out = df.copy()
    if "geom" in t.computed and "lon" in out.columns and "lat" in out.columns:
        # WKT for ST_GEOGPOINT(lon, lat)
        out["geom"] = [f"POINT({lon} {lat})" for lon, lat in zip(out["lon"].tolist(), out["lat"].tolist(), strict=False)]
    elif "geom" in t.computed and "geometry_json" in out.columns:
        from shapely.geometry import shape

        out["geom"] = [shape(json.loads(g)).wkt if isinstance(g, str) else shape(g).wkt for g in out["geometry_json"].tolist()]
    elif "geom" in t.computed and "geom_wkt" in out.columns:
        out["geom"] = out["geom_wkt"]
    return out


def _replace_via_load(runner: Runner, t: Table, df: pd.DataFrame) -> None:
    """Full-table replace with a load job (sandbox-safe: no MERGE/TRUNCATE DML required)."""
    full = _with_computed(t, df)
    cols = [n for n, _ in t.columns]
    missing = [c for c in cols if c not in full.columns]
    if missing:
        raise RuntimeError(f"Cannot load {t.name}: missing columns {missing}")
    runner.load_df(full[cols], t.name, list(t.columns), replace=True)


def upsert(kind: str, payload, mode: str = "merge", runner: Runner | None = None) -> dict:
    """Write one kind of data. ``mode='replace'`` swaps the whole table's content."""
    runner = runner or get_runner()
    p, d = runner.project, runner.dataset
    table_name = {"points": "points", "timeseries": "timeseries", "rain": "rain", "assets": "assets", "regions": "regions"}[kind]
    t = TABLES[table_name]
    df = _frame(kind, payload)
    if mode == "replace":
        # Prefer load-job replace: works in BigQuery sandbox without billing (DML does not).
        _replace_via_load(runner, t, df)
        if kind == "assets":
            _replace_segments_via_load(runner, payload)
        if kind == "points":
            # Orphan cleanup is DML (needs open billing). Skip cleanly in the sandbox.
            try:
                from app.services.bq.client import BigQueryUnavailable

                runner.execute(sql.delete_orphan_timeseries_sql(p, d), label="delete:orphan_timeseries")
            except BigQueryUnavailable as exc:
                if "Billing" not in str(exc) and "billing" not in str(exc).lower() and "DML" not in str(exc):
                    raise
        return {"written": len(df), "total": _count(runner, t.name)}

    stg = _stage(runner, t, df)
    try:
        runner.execute(sql.merge_sql(t, p, d, stg), label=f"merge:{t.name}:{stg}")
        if kind == "assets":
            _refresh_segments(runner, payload, stg, replace=False)
    finally:
        _drop(runner, stg)
    return {"written": len(df), "total": _count(runner, t.name)}


def _replace_segments_via_load(runner: Runner, features: list[dict]) -> None:
    seg_df = segments.segment_features(features)
    _replace_via_load(runner, ASSET_SEGMENTS, seg_df)


def _refresh_segments(runner: Runner, features: list[dict], assets_stg: str, replace: bool) -> None:
    """Segments are derived data: rebuild them for every asset that was just written."""
    p, d = runner.project, runner.dataset
    seg_df = segments.segment_features(features)
    seg_stg = _stage(runner, ASSET_SEGMENTS, seg_df)
    try:
        if replace:
            runner.execute(sql.truncate_sql("asset_segments", p, d), label="truncate:asset_segments")
        else:
            runner.execute(
                f"DELETE FROM {fq(p, d, 'asset_segments')}\nWHERE asset_id IN (SELECT asset_id FROM `{p}.{d}.{assets_stg}`)",
                label=f"delete_segments:asset_segments:{assets_stg}",
            )
        runner.execute(sql.insert_from_staging_sql(ASSET_SEGMENTS, p, d, seg_stg), label=f"insert:asset_segments:{seg_stg}")
    finally:
        _drop(runner, seg_stg)


def append_rows(table: str, df: pd.DataFrame, runner: Runner | None = None) -> None:
    """Append-only write (audit log, registry)."""
    runner = runner or get_runner()
    t = TABLES[table]
    stg = _stage(runner, t, df)
    try:
        runner.execute(sql.insert_from_staging_sql(t, runner.project, runner.dataset, stg), label=f"insert:{table}:{stg}")
    finally:
        _drop(runner, stg)


def merge_rows(table: str, df: pd.DataFrame, runner: Runner | None = None) -> None:
    """Idempotent write keyed on the table's key (re-running a daily job overwrites, never duplicates)."""
    runner = runner or get_runner()
    t = TABLES[table]
    stg = _stage(runner, t, df)
    try:
        runner.execute(sql.merge_sql(t, runner.project, runner.dataset, stg), label=f"merge:{table}:{stg}")
    finally:
        _drop(runner, stg)


def register_dataset(entry: dict, runner: Runner | None = None) -> None:
    row = {**entry, "notes": json.dumps(entry.get("notes") or [])}
    for k in ("date_min", "date_max"):
        row[k] = pd.to_datetime(row[k]).date() if row.get(k) else None
    row["added_at"] = pd.to_datetime(row["added_at"], utc=True)
    t = TABLES["datasets"]
    append_rows("datasets", pd.DataFrame([row])[[n for n, _ in t.load_columns]], runner)


def sync_repo(repo, runner: Runner | None = None) -> dict:
    """Copy everything a (local) repository holds into BigQuery, replacing the BigQuery content."""
    runner = runner or get_runner()
    out: dict[str, dict] = {}
    out["regions"] = upsert("regions", repo.regions(), "replace", runner)
    out["assets"] = upsert("assets", repo.assets_geojson()["features"], "replace", runner)
    out["points"] = upsert("points", repo.points(), "replace", runner)
    out["timeseries"] = upsert("timeseries", repo.timeseries(), "replace", runner)
    out["rain"] = upsert("rain", repo.rain(), "replace", runner)
    return {"ok": True, "project": runner.project, "dataset": runner.dataset, "tables": out}
