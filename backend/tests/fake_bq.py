"""In-memory stand-in for BigQuery, driven by the statement *labels* the loader and repository attach.

It does NOT parse SQL (sqlglot checks the SQL text separately). It applies the same semantics the SQL
promises - MERGE on key, TRUNCATE, INSERT from staging, and the corridor pre-filter - so the Python
code around BigQuery (staging, ordering, caching, repository interface) is tested end to end offline.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import shapely
from shapely import wkt

from app.services.bq.schema import TABLES


def _empty(name: str) -> pd.DataFrame:
    return pd.DataFrame({c: pd.Series(dtype="object") for c, _ in TABLES[name].columns})


class FakeRunner:
    project = "test-project"
    dataset = "terrasentinel"

    def __init__(self):
        self.tables: dict[str, pd.DataFrame] = {n: _empty(n) for n in TABLES}
        self.log: list[tuple[str, str]] = []  # (kind, label)
        self.sql_seen: list[str] = []

    # ---- helpers
    def count_reads(self, label: str) -> int:
        return sum(1 for k, lab in self.log if k == "query" and lab == label)

    def staging_tables(self) -> list[str]:
        return [n for n in self.tables if "_stg" in n]

    # ---- Runner protocol
    def load_df(self, df, table, schema, replace=False):
        self.log.append(("load", table))
        cols = [n for n, _ in schema]
        assert list(df.columns) == cols, f"staging columns {list(df.columns)} != schema {cols}"
        self.tables[table] = df.copy().reset_index(drop=True) if replace or table not in self.tables else pd.concat([self.tables[table], df], ignore_index=True)

    def execute(self, sql, params=None, label=None):
        assert label, f"unlabelled statement reached the runner: {sql[:80]}"
        self.log.append(("exec", label))
        self.sql_seen.append(sql)
        op, _, rest = label.partition(":")
        table, _, stg = rest.partition(":")
        if op == "truncate":
            self.tables[table] = _empty(table)
        elif op == "insert":
            self._insert(table, self.tables[stg])
        elif op == "merge":
            self._merge(table, self.tables[stg])
        elif op == "delete_segments":
            gone = set(self.tables[stg]["asset_id"])
            seg = self.tables["asset_segments"]
            self.tables["asset_segments"] = seg[~seg["asset_id"].isin(gone)].reset_index(drop=True)
        elif op == "delete" and table == "orphan_timeseries":
            ts, pts = self.tables["timeseries"], self.tables["points"]
            self.tables["timeseries"] = ts[ts["point_id"].isin(pts["point_id"])].reset_index(drop=True)
        elif op == "drop":
            self.tables.pop(stg, None)
        else:
            raise AssertionError(f"unknown statement label {label!r}")

    def _computed(self, table: str, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        for col in TABLES[table].computed:
            out[col] = "<geography>"
        return out[[c for c, _ in TABLES[table].columns]]

    def _insert(self, table: str, stg: pd.DataFrame):
        new = self._computed(table, stg)
        cur = self.tables[table]
        self.tables[table] = new if cur.empty else pd.concat([cur, new], ignore_index=True)

    def _merge(self, table: str, stg: pd.DataFrame):
        key = list(TABLES[table].key)
        new = self._computed(table, stg)
        cur = self.tables[table]
        both = new if cur.empty else pd.concat([cur, new], ignore_index=True)
        self.tables[table] = both.drop_duplicates(key, keep="last").reset_index(drop=True)

    def query_df(self, sql, params=None, label=None):
        assert label, f"unlabelled query reached the runner: {sql[:80]}"
        self.log.append(("query", label))
        self.sql_seen.append(sql)
        kind, _, name = label.partition(":")
        T = self.tables
        if kind == "count":
            return pd.DataFrame({"n": [len(T[name])]})
        assert kind == "read", label
        if name == "regions":
            return T["regions"].sort_values("region_id").reset_index(drop=True)
        if name == "assets":
            return T["assets"].sort_values("asset_id")[["asset_id", "name", "asset_type", "region_id", "criticality", "consequence_note", "buffer_m", "geometry_json"]].reset_index(drop=True)
        if name == "rain":
            r = T["rain"].copy()
            r["date"] = pd.to_datetime(r["date"])
            return r.sort_values(["region_id", "date"]).reset_index(drop=True)
        if name == "points":
            keep = self._corridor_points()
            return T["points"][T["points"]["point_id"].isin(keep)][["point_id", "lat", "lon", "velocity_mm_yr", "coherence", "region_id", "source"]].reset_index(drop=True)
        if name == "timeseries":
            keep = self._corridor_points()
            ts = T["timeseries"]
            out = ts[ts["point_id"].isin(keep)].copy()
            out["date"] = pd.to_datetime(out["date"])
            return out.sort_values(["point_id", "date"]).reset_index(drop=True)
        if name == "counts":
            ts = T["timeseries"]
            dates = pd.to_datetime(ts["date"]) if len(ts) else pd.Series(dtype="datetime64[ns]")
            return pd.DataFrame(
                [
                    {
                        "regions": len(T["regions"]),
                        "assets": len(T["assets"]),
                        "points": len(T["points"]),
                        "timeseries_rows": len(ts),
                        "epochs": int(dates.nunique()),
                        "rain_rows": len(T["rain"]),
                        "date_min": dates.min() if len(dates) else pd.NaT,
                        "date_max": dates.max() if len(dates) else pd.NaT,
                    }
                ]
            )
        if name == "source_label":
            src = T["points"]["source"].astype(str).str.upper() if len(T["points"]) else pd.Series(dtype=str)
            return pd.DataFrame([{"demo_points": int(src.str.startswith("DEMO").sum()), "total_points": len(src)}])
        if name == "list_datasets":
            d = T["datasets"].copy()
            return d.sort_values("added_at", ascending=False).reset_index(drop=True)
        if name == "list_actions":
            return T["alert_actions"].sort_values("at").reset_index(drop=True)
        if name == "list_snapshots":
            s = T["site_snapshots"]
            if s.empty:
                return pd.DataFrame(columns=["as_of", "saved_at", "sites"])
            g = s.groupby("as_of").agg(saved_at=("saved_at", "max"), sites=("site_id", "count")).reset_index()
            return g.sort_values("as_of").reset_index(drop=True)
        raise AssertionError(f"unknown read {name}")

    # ---- the corridor pre-filter (ST_DWITHIN against asset segments), emulated with shapely
    def _corridor_points(self) -> set[str]:
        pts, seg = self.tables["points"], self.tables["asset_segments"]
        if pts.empty or seg.empty:
            return set()
        lon, lat = pts["lon"].to_numpy(float), pts["lat"].to_numpy(float)
        near = np.zeros(len(pts), dtype=bool)
        for r in seg.itertuples():
            line = wkt.loads(r.geom_wkt)
            lat0 = line.centroid.y
            mx, my = 111_320.0 * np.cos(np.radians(lat0)), 110_540.0
            lon0, lat_ref = line.coords[0]
            line_m = shapely.linestrings([((x - lon0) * mx, (y - lat_ref) * my) for x, y in line.coords])
            pm = shapely.points((lon - lon0) * mx, (lat - lat_ref) * my)
            near |= shapely.distance(pm, line_m) <= r.buffer_m
        return set(pts["point_id"][near])
