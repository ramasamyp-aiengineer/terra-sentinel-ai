"""Historical passes: the analysis as it looked at each past satellite epoch.

A *pass* is the full pipeline run using only data available at that epoch. Passes are aligned
to real acquisition dates (a 6-day offset on a 6-day cadence would just repeat the same data).
Pass 0 is "now" (assessment date = last epoch + a few days); pass k is k epochs earlier.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from functools import lru_cache

import pandas as pd

from app.services.data.repo import get_repo
from app.services.detection.engine import SiteAssessment
from app.services.detection.pipeline import _LOCK, as_of_date, run_pipeline

MAX_PASSES = 16
MIN_EPOCHS = 12  # a pass with fewer epochs would mostly be data_degraded noise


@dataclass(frozen=True)
class Pass:
    index: int  # 0 = now
    offset_days: int
    as_of: str


@lru_cache(maxsize=1)
def _epochs() -> tuple[pd.Timestamp, ...]:
    with _LOCK:
        ts = get_repo().timeseries()
        return tuple(sorted(ts["date"].unique())) if len(ts) else ()


@lru_cache(maxsize=4)
def passes(n: int = MAX_PASSES) -> tuple[Pass, ...]:
    with _LOCK:
        return _passes(n)


def _passes(n: int) -> tuple[Pass, ...]:
    repo = get_repo()
    epochs = [pd.Timestamp(e) for e in _epochs()]
    if len(epochs) < MIN_EPOCHS:
        return ()
    now = as_of_date(repo)
    out = [Pass(0, 0, str(now.date()))]
    for k in range(1, n):
        idx = len(epochs) - 1 - k
        if idx + 1 < MIN_EPOCHS:
            break
        e = epochs[idx]
        out.append(Pass(k, int((now - e).days), str(e.date())))
    return tuple(out)


def sites_at(p: Pass) -> list[SiteAssessment]:
    return run_pipeline(p.offset_days)


def label(s: SiteAssessment) -> str:
    return f"{s.asset_name.split(' (')[0]} - KM {s.chainage_start_km:.2f}-{s.chainage_end_km:.2f}"


def row(s: SiteAssessment) -> dict:
    m, o = s.metrics, s.outlook
    return {
        "site_id": s.site_id,
        "asset_id": s.asset_id,
        "asset_name": s.asset_name,
        "asset_type": s.asset_type,
        "region_id": s.region_id,
        "label": label(s),
        "lat": s.lat,
        "lon": s.lon,
        "tier": s.tier,
        "state": s.state,
        "rpi": s.rpi,
        "criticality": s.criticality,
        "rate_mm_month": round(m.rate_recent_mm_month, 2),
        "baseline_rate_mm_month": round(m.rate_baseline_mm_month, 2),
        "accel_ratio": round(m.accel_ratio, 2),
        "outlook_status": o.status,
        "eta_low_days": o.eta_low_days,
        "eta_high_days": o.eta_high_days,
        "progress_mm": round(o.progress_mm, 1),
        "threshold_mm": o.threshold_mm,
        "confidence": s.confidence.score,
        "n_points": s.n_points,
    }


@lru_cache(maxsize=MAX_PASSES + 2)
def _table(offset_days: int) -> dict[str, dict]:
    return {s.site_id: row(s) for s in run_pipeline(offset_days)}


def table(offset_days: int) -> dict[str, dict]:
    with _LOCK:  # same lock as the pipeline: clear() waits for an in-flight build
        return _table(int(offset_days))


def table_for(p: Pass) -> dict[str, dict]:
    return table(p.offset_days)


def warm(n: int = MAX_PASSES) -> None:
    """Pre-compute every pass (called in the background so the first Trends/Alerts view is instant)."""
    for p in passes(n):
        table(p.offset_days)


_warm_thread: threading.Thread | None = None


def warm_in_background(n: int = MAX_PASSES) -> None:
    global _warm_thread
    if _warm_thread and _warm_thread.is_alive():
        return
    _warm_thread = threading.Thread(target=_safe_warm, args=(n,), daemon=True, name="ts-warm")
    _warm_thread.start()


def _safe_warm(n: int) -> None:
    try:
        warm(n)
    except Exception:  # noqa: BLE001 - warming is best-effort
        pass


def clear() -> None:
    with _LOCK:
        _epochs.cache_clear()
        passes.cache_clear()
        _table.cache_clear()
        from app.services.intel import alerts

        alerts.clear()
