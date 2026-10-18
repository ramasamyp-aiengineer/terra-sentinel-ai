"""Pre-segment assets into chainage bins for BigQuery.

BigQuery has no linear referencing (no ST_LINELOCATEPOINT), so the along-line position of a point cannot
be asked for directly. Instead each asset is cut into bins of ``CHAINAGE_BIN_M`` metres; a point is
assigned to the nearest bin inside the asset's buffer. The Python engine measures true chainage, so
``tests/test_bigquery.py`` checks the two agree.
"""
from __future__ import annotations

import json
import math

import pandas as pd
from shapely.geometry import LineString, MultiLineString, shape
from shapely.ops import substring

from app.core.config import profile_for
from app.services.detection.engine import CHAINAGE_BIN_M, _meters_per_deg, _project_line


def _lines(geom) -> list[LineString]:
    if isinstance(geom, LineString):
        return [geom]
    if isinstance(geom, MultiLineString):
        return list(geom.geoms)
    return []


def segment_geometry(geometry, asset_type: str = "HIGHWAY", buffer_m: float | None = None, asset_id: str = "", step_m: float = CHAINAGE_BIN_M) -> list[dict]:
    """Rows for ``asset_segments``. The first line of a MultiLineString defines chainage (as in the engine)."""
    lines = _lines(geometry)
    if not lines:
        return []
    line = lines[0]
    line_m, lon0, lat_ref = _project_line(line)
    mx, my = _meters_per_deg(line.centroid.y)
    length = line_m.length
    buf = buffer_m or profile_for(asset_type).buffer_m
    rows = []
    for i in range(max(1, math.ceil(length / step_m))):
        a, b = i * step_m, min((i + 1) * step_m, length)
        if b - a < 1e-6:
            continue
        sub = substring(line_m, a, b)
        coords = [(x / mx + lon0, y / my + lat_ref) for x, y in sub.coords]
        rows.append(
            {
                "asset_id": asset_id,
                "seg_idx": i,
                "chainage_start_m": round(a, 1),
                "chainage_end_m": round(b, 1),
                "buffer_m": float(buf),
                "geom_wkt": LineString(coords).wkt,
            }
        )
    return rows


def segment_features(features: list[dict]) -> pd.DataFrame:
    """Segments for GeoJSON asset features (as stored in assets.geojson)."""
    rows: list[dict] = []
    for f in features:
        p = f["properties"]
        rows += segment_geometry(shape(f["geometry"]), p.get("asset_type", "HIGHWAY"), p.get("buffer_m"), p["asset_id"])
    return pd.DataFrame(rows, columns=["asset_id", "seg_idx", "chainage_start_m", "chainage_end_m", "buffer_m", "geom_wkt"])


def assets_frame(features: list[dict]) -> pd.DataFrame:
    rows = []
    for f in features:
        p = f["properties"]
        rows.append(
            {
                "asset_id": p["asset_id"],
                "name": p["name"],
                "asset_type": p["asset_type"],
                "region_id": p["region_id"],
                "criticality": float(p["criticality"]),
                "consequence_note": p.get("consequence_note", ""),
                "buffer_m": float(p["buffer_m"]) if p.get("buffer_m") is not None else float(profile_for(p["asset_type"]).buffer_m),
                "geometry_json": json.dumps(f["geometry"]),
            }
        )
    return pd.DataFrame(rows)
