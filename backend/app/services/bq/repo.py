"""BigQuery-backed repository: the same interface as ``LocalRepo``.

Reads are issued once and held in memory for ``bq_cache_ttl_s`` seconds. Points and time series are
pre-filtered *in BigQuery* (``v_point_assignment``: ST_DWITHIN against asset corridors), so the pipeline
only receives scatterers that can matter - a national archive is reduced to the corridors before it
leaves the warehouse.
"""
from __future__ import annotations

import json
import threading
import time

import pandas as pd
from shapely.geometry import shape

from app.core.config import settings
from app.services.bq import loader, sql
from app.services.bq.client import Runner, get_runner
from app.services.data.repo import POINT_COLS, RAIN_COLS, TS_COLS, data_source_label
from app.services.detection.engine import Asset


class BigQueryRepo:
    backend = "bigquery"

    def __init__(self, runner: Runner | None = None, ttl_s: int | None = None):
        self._runner = runner
        self._ttl = settings.bq_cache_ttl_s if ttl_s is None else ttl_s
        self._cache: dict[str, tuple[float, object]] = {}
        self._lock = threading.Lock()

    @property
    def runner(self) -> Runner:
        return self._runner or get_runner()

    @property
    def _queries(self) -> dict[str, str]:
        return sql.read_queries(self.runner.project, self.runner.dataset)

    def _fetch(self, name: str) -> pd.DataFrame:
        with self._lock:
            hit = self._cache.get(name)
            if hit and time.monotonic() - hit[0] < self._ttl:
                return hit[1]  # type: ignore[return-value]
            df = self.runner.query_df(self._queries[name], label=f"read:{name}")
            self._cache[name] = (time.monotonic(), df)
            return df

    def invalidate(self) -> None:
        with self._lock:
            self._cache.clear()

    # ---- reads ----------------------------------------------------------------

    def regions(self) -> list[dict]:
        df = self._fetch("regions")
        return [
            {
                "region_id": r.region_id,
                "parent_id": None if pd.isna(r.parent_id) else r.parent_id,
                "name": r.name,
                "level": r.level,
                "center": [float(r.center_lon), float(r.center_lat)],
                "zoom": float(r.zoom),
            }
            for r in df.itertuples()
        ]

    def assets_geojson(self) -> dict:
        feats = []
        for r in self._fetch("assets").itertuples():
            feats.append(
                {
                    "type": "Feature",
                    "properties": {
                        "asset_id": r.asset_id,
                        "name": r.name,
                        "asset_type": r.asset_type,
                        "region_id": r.region_id,
                        "criticality": float(r.criticality),
                        "consequence_note": r.consequence_note or "",
                        "buffer_m": None if pd.isna(r.buffer_m) else float(r.buffer_m),
                    },
                    "geometry": json.loads(r.geometry_json),
                }
            )
        return {"type": "FeatureCollection", "features": feats}

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
                    criticality=p["criticality"],
                    consequence_note=p["consequence_note"],
                    geometry=shape(f["geometry"]),
                )
            )
        return out

    def points(self) -> pd.DataFrame:
        df = self._fetch("points")
        return df[POINT_COLS].astype({"point_id": str}) if len(df) else pd.DataFrame(columns=POINT_COLS)

    def timeseries(self) -> pd.DataFrame:
        df = self._fetch("timeseries")
        if not len(df):
            return pd.DataFrame(columns=TS_COLS)
        out = df[TS_COLS].copy()
        out["point_id"] = out["point_id"].astype(str)
        out["date"] = pd.to_datetime(out["date"])
        return out

    def rain(self) -> pd.DataFrame:
        df = self._fetch("rain")
        if not len(df):
            return pd.DataFrame(columns=RAIN_COLS)
        out = df[RAIN_COLS].copy()
        out["date"] = pd.to_datetime(out["date"])
        return out

    def data_source(self) -> str:
        r = self._fetch("source_label").iloc[0]
        total, demo = int(r["total_points"]), int(r["demo_points"])
        if total == 0 or demo == total:
            return "DEMO-SYNTHETIC"
        return "mixed" if demo else "observed"

    def is_demo(self) -> bool:
        return self.data_source() == "DEMO-SYNTHETIC"

    def counts(self) -> dict:
        r = self._fetch("counts").iloc[0]
        d0, d1 = r["date_min"], r["date_max"]
        return {
            "regions": int(r["regions"]),
            "assets": int(r["assets"]),
            "points": int(r["points"]),
            "timeseries_rows": int(r["timeseries_rows"]),
            "epochs": int(r["epochs"]),
            "rain_rows": int(r["rain_rows"]),
            "date_min": None if pd.isna(d0) else str(pd.Timestamp(d0).date()),
            "date_max": None if pd.isna(d1) else str(pd.Timestamp(d1).date()),
        }

    # ---- writes ---------------------------------------------------------------

    def write(self, kind: str, payload, mode: str = "merge") -> dict:
        out = loader.upsert(kind, payload, mode, self.runner)
        self.invalidate()
        return out
