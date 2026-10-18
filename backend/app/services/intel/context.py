"""Context layers from public data: what else was happening near a site.

This is *context for the person reading the site*, never an input to the risk score. The detection maths
(motion, acceleration, thresholds, rain trigger) is unchanged by anything here, so adding or deleting a public
dataset can not move a site between tiers. If seismic data is absent the answer says so rather than implying
"no earthquakes".
"""
from __future__ import annotations

import threading

import numpy as np
import pandas as pd

from app.services.data import public_catalog as pc

EARTH_KM = 6371.0088
RECENT_RADIUS_KM = 100.0
RECENT_WINDOW_DAYS = 30
RECENT_MIN_MAG = 4.0
HISTORY_RADIUS_KM = 200.0
HISTORY_MIN_MAG = 5.0
SOURCE = pc.USGS_CITE

_lock = threading.Lock()
_cache: dict = {"key": None, "df": None}


def _events() -> tuple[pd.DataFrame, dict]:
    """All stored earthquake datasets merged (cached until a file changes) and their coverage."""
    ids = pc.stored_ids()
    key = tuple((i, pc._meta_path(i).stat().st_mtime_ns) for i in ids)
    with _lock:
        if _cache["key"] != key:
            frames = [pc.read_events(i) for i in ids]
            df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=pc.EVENT_COLS)
            if len(df):
                df = df.drop_duplicates("id").reset_index(drop=True)
                df["_lat"] = np.radians(df["latitude"].to_numpy(float))
                df["_lon"] = np.radians(df["longitude"].to_numpy(float))
            _cache["key"], _cache["df"] = key, df
        df = _cache["df"]
    cover = {"datasets": ids}
    if len(df):
        cover.update(date_from=str(df["time"].min().date()), date_to=str(df["time"].max().date()))
    return df, cover


def clear_cache() -> None:
    with _lock:
        _cache["key"] = None


def _distances_km(df: pd.DataFrame, lat: float, lon: float) -> np.ndarray:
    la1, lo1 = np.radians(lat), np.radians(lon)
    dlat, dlon = df["_lat"].to_numpy() - la1, df["_lon"].to_numpy() - lo1
    a = np.sin(dlat / 2) ** 2 + np.cos(la1) * np.cos(df["_lat"].to_numpy()) * np.sin(dlon / 2) ** 2
    return 2 * EARTH_KM * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def _row(r, dist: float) -> dict:
    return {
        "time": r.time.strftime("%Y-%m-%d"),
        "mag": round(float(r.mag), 1),
        "distance_km": round(float(dist)),
        "depth_km": None if pd.isna(r.depth_km) else round(float(r.depth_km)),
        "place": r.place,
    }


def seismic_for(lat: float, lon: float, as_of: pd.Timestamp) -> dict:
    """Earthquakes near a point, relative to the assessment date ``as_of``."""
    df, cover = _events()
    base = {
        "available": False,
        "source": SOURCE,
        "note": "Context only: earthquakes are not used in the risk score.",
        "recent": {"radius_km": RECENT_RADIUS_KM, "window_days": RECENT_WINDOW_DAYS, "min_magnitude": RECENT_MIN_MAG},
        "history": {"radius_km": HISTORY_RADIUS_KM, "min_magnitude": HISTORY_MIN_MAG},
        "coverage": cover,
    }
    if df.empty:
        return {**base, "message": "No earthquake data loaded. Fetch it from Data Hub, Public data."}

    ref = pd.Timestamp(as_of)
    ref = ref.tz_localize("UTC") if ref.tzinfo is None else ref.tz_convert("UTC")
    dist = _distances_km(df, lat, lon)
    d = df.assign(distance_km=dist)

    start = ref - pd.Timedelta(days=RECENT_WINDOW_DAYS)
    covered_from = df["time"].min()
    recent = d[(d["time"] > start) & (d["time"] <= ref) & (d["mag"] >= RECENT_MIN_MAG) & (d["distance_km"] <= RECENT_RADIUS_KM)]
    hist = d[(d["time"] <= ref) & (d["mag"] >= HISTORY_MIN_MAG) & (d["distance_km"] <= HISTORY_RADIUS_KM)]

    recent_list = [_row(r, r.distance_km) for r in recent.sort_values("mag", ascending=False).head(5).itertuples()]
    largest = hist.sort_values("mag", ascending=False).head(1)
    warnings = []
    if covered_from > start:
        warnings.append(f"Loaded data starts {covered_from.date()}, so the last {RECENT_WINDOW_DAYS} days are only partly covered.")
    if df["time"].max() < ref - pd.Timedelta(days=3):
        warnings.append(f"Loaded data ends {df['time'].max().date()}, before the assessment date {ref.date()}. Refresh it.")

    return {
        **base,
        "available": True,
        "recent_count": int(len(recent)),
        "recent_max_magnitude": round(float(recent["mag"].max()), 1) if len(recent) else None,
        "recent_nearest_km": round(float(recent["distance_km"].min())) if len(recent) else None,
        "recent_events": recent_list,
        "history_count": int(len(hist)),
        "history_largest": _row(largest.iloc[0], largest.iloc[0].distance_km) if len(largest) else None,
        "warnings": warnings,
    }


def events_in_bbox(x0: float, y0: float, x1: float, y1: float, min_mag: float = 2.5, limit: int = 1500) -> dict:
    """Events for the map layer, largest first when truncated."""
    df, cover = _events()
    if df.empty:
        return {"count": 0, "truncated": False, "events": [], "coverage": cover}
    sel = df[(df["longitude"] >= x0) & (df["longitude"] <= x1) & (df["latitude"] >= y0) & (df["latitude"] <= y1) & (df["mag"] >= min_mag)]
    truncated = len(sel) > limit
    sel = sel.sort_values("mag", ascending=False).head(limit)
    events = [
        {"id": r.id, "time": r.time.strftime("%Y-%m-%d %H:%M"), "mag": round(float(r.mag), 1), "lat": round(float(r.latitude), 4),
         "lon": round(float(r.longitude), 4), "place": r.place}
        for r in sel.itertuples()
    ]
    return {"count": len(events), "truncated": truncated, "events": events, "coverage": cover}
