"""Batch pipeline: load data -> assess every asset -> ranked sites (cached).

``run_pipeline(offset_days=N)`` re-runs the *same* analysis as it would have looked N days
ago (observations after that date are ignored). That is how alert diffs, trend history and
what-if comparisons are derived from data alone - nothing is invented.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from functools import lru_cache

import numpy as np
import pandas as pd

from app.core.config import settings
from app.services.data.repo import get_repo
from app.services.detection.engine import SiteAssessment, assess_asset, rank_sites

RAIN_SATURATION_MM = 200.0  # 14-day rainfall mapped to trigger score 100 (demo calibration)


@dataclass
class RainContext:
    region_id: str
    window_days: int
    rain_14d_mm: float
    rain_7d_mm: float
    peak_day_mm: float
    trigger_score: float  # 0..100
    source: str


def rain_source_label(repo) -> str:
    """'observed' once any real rainfall was loaded (upload / link / Open-Meteo); else the data-source label."""
    try:
        from app.services.data.state import get_state

        real = [d for d in get_state().list_datasets() if d["kind"] == "rain" and d.get("source_type") not in ("demo", "seed")]
    except Exception:  # noqa: BLE001 - labelling must never break the pipeline
        real = []
    return "observed" if real else ("DEMO-SYNTHETIC" if repo.is_demo() else repo.data_source())


def rain_context(repo, region_id: str, as_of: pd.Timestamp) -> RainContext | None:
    df = repo.rain()
    df = df[df["region_id"] == region_id]
    if df.empty:
        return None
    w14 = df[(df["date"] > as_of - pd.Timedelta(days=14)) & (df["date"] <= as_of)]
    w7 = df[(df["date"] > as_of - pd.Timedelta(days=7)) & (df["date"] <= as_of)]
    if w14.empty:
        return None
    r14 = float(w14["precip_mm"].sum())
    return RainContext(
        region_id=region_id,
        window_days=14,
        rain_14d_mm=round(r14, 1),
        rain_7d_mm=round(float(w7["precip_mm"].sum()), 1),
        peak_day_mm=round(float(w14["precip_mm"].max()), 1),
        trigger_score=round(float(np.clip(r14 / RAIN_SATURATION_MM, 0, 1) * 100), 1),
        source=rain_source_label(repo),
    )


def as_of_date(repo, offset_days: int = 0) -> pd.Timestamp:
    """The assessment date: last satellite epoch + 6 days (or the configured override), minus any offset."""
    if settings.as_of_date:
        base = pd.Timestamp(settings.as_of_date)
    else:
        ts = repo.timeseries()
        base = ts["date"].max() + pd.Timedelta(days=6) if len(ts) else pd.Timestamp.now().normalize()
    return base - pd.Timedelta(days=int(offset_days))


@lru_cache(maxsize=32)
def _run(offset_days: int) -> list[SiteAssessment]:
    repo = get_repo()
    points, ts = repo.points(), repo.timeseries()
    if points.empty or ts.empty:
        return []
    as_of = as_of_date(repo, offset_days)
    if offset_days:
        ts = ts[ts["date"] <= as_of]  # only what was knowable on that date
    rain_cache: dict[str, float | None] = {}

    sites: list[SiteAssessment] = []
    for asset in repo.assets():
        if asset.region_id not in rain_cache:
            ctx = rain_context(repo, asset.region_id, as_of)
            rain_cache[asset.region_id] = ctx.trigger_score if ctx else None
        trig = rain_cache[asset.region_id]
        sites.extend(assess_asset(asset, points, ts, rain_trigger_for=lambda lat, lon, t=trig: t))
    return rank_sites(sites)


_LOCK = threading.RLock()  # serialise cache misses so the background warm-up never duplicates work


def run_pipeline(offset_days: int = 0) -> list[SiteAssessment]:
    with _LOCK:
        return _run(int(offset_days))


def clear_cache() -> None:
    with _LOCK:  # wait for any in-flight pass so a stale result is never cached after the clear
        _run.cache_clear()
