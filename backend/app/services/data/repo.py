"""Local data repository (CSV / GeoJSON / JSON files).

Two directories are involved:
  * ``settings.data_dir``       read-only demo dataset shipped with the repo
  * ``settings.workspace_dir``  writable copy, created on the first upload

``get_repo()`` serves the workspace once it exists, otherwise the demo data.
The BigQuery repository (``app.services.bq.repo``) implements the same interface.
"""
from __future__ import annotations

import json
import shutil
import threading
from contextlib import contextmanager
from functools import cached_property, lru_cache
from pathlib import Path
from typing import Literal

import pandas as pd
from shapely.geometry import shape

from app.core.config import settings
from app.services.detection.engine import Asset

Kind = Literal["points", "timeseries", "rain", "assets", "regions"]
Mode = Literal["merge", "replace"]

POINT_COLS = ["point_id", "lat", "lon", "velocity_mm_yr", "coherence", "region_id", "source"]
TS_COLS = ["point_id", "date", "disp_mm"]
RAIN_COLS = ["region_id", "date", "precip_mm"]


class RowLimitError(ValueError):
    """Raised when local CSV storage would be pushed past its practical limit."""


def data_source_label(points: pd.DataFrame) -> str:
    """DEMO-SYNTHETIC only if *every* scatterer is synthetic; 'mixed' when demo and real coexist."""
    if points.empty or "source" not in points:
        return "DEMO-SYNTHETIC"
    demo = points["source"].astype(str).str.upper().str.startswith("DEMO")
    if demo.all():
        return "DEMO-SYNTHETIC"
    return "mixed" if demo.any() else "observed"


class LocalRepo:
    backend = "local"

    def __init__(self, data_dir: Path | None = None):
        self.dir = Path(data_dir or settings.data_dir)

    @property
    def is_workspace(self) -> bool:
        return self.dir.resolve() == Path(settings.workspace_dir).resolve()

    # ---- reads ----------------------------------------------------------------

    def assets_geojson(self) -> dict:
        return json.loads((self.dir / "assets.geojson").read_text(encoding="utf-8"))

    def assets(self) -> list[Asset]:
        out = []
        for f in self.assets_geojson()["features"]:
            p = f["properties"]
            out.append(
                Asset(
                    asset_id=p["asset_id"],
                    name=p["name"],
                    asset_type=p["asset_type"],
                    region_id=p["region_id"],
                    criticality=float(p["criticality"]),
                    consequence_note=p.get("consequence_note", ""),
                    geometry=shape(f["geometry"]),
                )
            )
        return out

    # Frames are parsed once per repo instance (callers must not mutate them).
    @cached_property
    def _points(self) -> pd.DataFrame:
        return pd.read_csv(self.dir / "insar_points.csv", dtype={"point_id": str})

    @cached_property
    def _timeseries(self) -> pd.DataFrame:
        return pd.read_csv(self.dir / "insar_timeseries.csv", parse_dates=["date"], dtype={"point_id": str})

    @cached_property
    def _regions(self) -> list[dict]:
        return json.loads((self.dir / "regions.json").read_text(encoding="utf-8"))

    def _rain_path(self) -> Path:
        new = self.dir / "rain.csv"
        return new if new.exists() else self.dir / "rain_demo.csv"

    @cached_property
    def _rain(self) -> pd.DataFrame:
        p = self._rain_path()
        if not p.exists():
            return pd.DataFrame(columns=RAIN_COLS)
        return pd.read_csv(p, parse_dates=["date"])

    def points(self) -> pd.DataFrame:
        return self._points

    def timeseries(self) -> pd.DataFrame:
        return self._timeseries

    def regions(self) -> list[dict]:
        return self._regions

    def rain(self) -> pd.DataFrame:
        return self._rain

    def data_source(self) -> str:
        return data_source_label(self._points)

    def is_demo(self) -> bool:
        return self.data_source() == "DEMO-SYNTHETIC"

    def counts(self) -> dict:
        ts = self._timeseries
        rain = self._rain
        return {
            "regions": len(self._regions),
            "assets": len(self.assets_geojson()["features"]),
            "points": len(self._points),
            "timeseries_rows": len(ts),
            "epochs": int(ts["date"].nunique()) if len(ts) else 0,
            "rain_rows": len(rain),
            "date_min": str(ts["date"].min().date()) if len(ts) else None,
            "date_max": str(ts["date"].max().date()) if len(ts) else None,
        }

    # ---- writes ---------------------------------------------------------------

    def write(self, kind: Kind, payload, mode: Mode = "merge") -> dict:
        """Merge or replace one kind of data in the workspace. Returns row counts."""
        ws = ensure_workspace()
        return _WorkspaceWriter(ws).write(kind, payload, mode)


# --------------------------------------------------------------------------------
# workspace
# --------------------------------------------------------------------------------


def workspace_exists() -> bool:
    return (Path(settings.workspace_dir) / "regions.json").exists()


# One writer at a time: uploads read-modify-write whole CSV files, so two at once would lose data.
WORKSPACE_LOCK = threading.RLock()


def _backup_dir() -> Path:
    ws = Path(settings.workspace_dir)
    return ws.with_name(ws.name + ".bak")


@contextmanager
def workspace_transaction():
    """Serialise workspace writes and roll the folder back if anything fails part-way.

    A multi-file import (regions, assets, points, series) must apply completely or not at all; otherwise a
    failure on the last file leaves points that reference regions or series that were never written.
    """
    with WORKSPACE_LOCK:
        ws, bak = Path(settings.workspace_dir), _backup_dir()
        existed = ws.exists()
        if bak.exists():
            shutil.rmtree(bak)
        if existed:
            shutil.copytree(ws, bak)
        try:
            yield
        except BaseException:
            if ws.exists():
                shutil.rmtree(ws)
            if existed:
                bak.rename(ws)
            raise
        else:
            if bak.exists():
                shutil.rmtree(bak)


def recover_workspace() -> bool:
    """After a crash mid-write the backup is the last consistent state: put it back. Call once at startup."""
    ws, bak = Path(settings.workspace_dir), _backup_dir()
    if not bak.exists():
        return False
    if ws.exists():
        shutil.rmtree(ws)
    bak.rename(ws)
    return True


def ensure_workspace() -> Path:
    """Create the writable workspace as a copy of the demo data (once)."""
    ws = Path(settings.workspace_dir)
    if workspace_exists():
        return ws
    ws.mkdir(parents=True, exist_ok=True)
    src = Path(settings.data_dir)
    for name in ("insar_points.csv", "insar_timeseries.csv", "assets.geojson", "regions.json"):
        shutil.copyfile(src / name, ws / name)
    rain = src / "rain_demo.csv"
    if rain.exists():
        shutil.copyfile(rain, ws / "rain.csv")
    else:
        pd.DataFrame(columns=RAIN_COLS).to_csv(ws / "rain.csv", index=False)
    return ws


def reset_workspace() -> bool:
    ws = Path(settings.workspace_dir)
    if ws.exists():
        shutil.rmtree(ws)
        return True
    return False


class _WorkspaceWriter:
    def __init__(self, ws: Path):
        self.ws = ws

    def write(self, kind: Kind, payload, mode: Mode) -> dict:
        fn = {
            "points": self._points,
            "timeseries": self._timeseries,
            "rain": self._rain,
            "assets": self._assets,
            "regions": self._regions,
        }[kind]
        return fn(payload, mode)

    # -- helpers
    def _read_points(self) -> pd.DataFrame:
        return pd.read_csv(self.ws / "insar_points.csv", dtype={"point_id": str})

    def _read_ts(self) -> pd.DataFrame:
        return pd.read_csv(self.ws / "insar_timeseries.csv", parse_dates=["date"], dtype={"point_id": str})

    # -- kinds
    def _points(self, df: pd.DataFrame, mode: Mode) -> dict:
        new = df[POINT_COLS].copy()
        old = self._read_points() if mode == "merge" else pd.DataFrame(columns=POINT_COLS)
        out = pd.concat([old, new], ignore_index=True).drop_duplicates("point_id", keep="last")
        out.to_csv(self.ws / "insar_points.csv", index=False)
        dropped = 0
        if mode == "replace":  # orphaned series would silently distort site medians
            ts = self._read_ts()
            keep = ts[ts["point_id"].isin(out["point_id"])]
            dropped = len(ts) - len(keep)
            keep.to_csv(self.ws / "insar_timeseries.csv", index=False)
        return {"written": len(new), "total": len(out), "orphan_timeseries_dropped": dropped}

    def _timeseries(self, df: pd.DataFrame, mode: Mode) -> dict:
        new = df[TS_COLS].copy()
        old = self._read_ts() if mode == "merge" else pd.DataFrame(columns=TS_COLS)
        out = pd.concat([old, new], ignore_index=True)
        out["date"] = pd.to_datetime(out["date"])
        out = out.drop_duplicates(["point_id", "date"], keep="last").sort_values(["point_id", "date"])
        if len(out) > settings.max_local_timeseries_rows:
            raise RowLimitError(
                f"{len(out):,} time-series rows exceeds the local limit of {settings.max_local_timeseries_rows:,}. "
                "Use the BigQuery backend (TS_DATA_BACKEND=bigquery) for datasets this large."
            )
        out.to_csv(self.ws / "insar_timeseries.csv", index=False, date_format="%Y-%m-%d")
        return {"written": len(new), "total": len(out)}

    def _rain(self, df: pd.DataFrame, mode: Mode) -> dict:
        p = self.ws / "rain.csv"
        new = df[RAIN_COLS].copy()
        old = pd.read_csv(p, parse_dates=["date"]) if (mode == "merge" and p.exists()) else pd.DataFrame(columns=RAIN_COLS)
        out = pd.concat([old, new], ignore_index=True)
        out["date"] = pd.to_datetime(out["date"])
        out = out.drop_duplicates(["region_id", "date"], keep="last").sort_values(["region_id", "date"])
        out.to_csv(p, index=False, date_format="%Y-%m-%d")
        return {"written": len(new), "total": len(out)}

    def _assets(self, features: list[dict], mode: Mode) -> dict:
        p = self.ws / "assets.geojson"
        existing = json.loads(p.read_text(encoding="utf-8"))["features"] if mode == "merge" else []
        by_id = {f["properties"]["asset_id"]: f for f in existing}
        for f in features:
            by_id[f["properties"]["asset_id"]] = f
        merged = list(by_id.values())
        p.write_text(json.dumps({"type": "FeatureCollection", "features": merged}), encoding="utf-8")
        return {"written": len(features), "total": len(merged)}

    def _regions(self, regions: list[dict], mode: Mode) -> dict:
        p = self.ws / "regions.json"
        existing = json.loads(p.read_text(encoding="utf-8")) if mode == "merge" else []
        by_id = {r["region_id"]: r for r in existing}
        for r in regions:
            by_id[r["region_id"]] = r
        merged = list(by_id.values())
        p.write_text(json.dumps(merged, indent=1), encoding="utf-8")
        return {"written": len(regions), "total": len(merged)}


@lru_cache(maxsize=1)
def get_repo():
    if settings.data_backend.lower() == "bigquery":
        from app.services.bq.repo import BigQueryRepo

        return BigQueryRepo()
    return LocalRepo(settings.workspace_dir if workspace_exists() else settings.data_dir)
