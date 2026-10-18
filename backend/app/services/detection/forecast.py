"""Time-to-threshold outlook.

This is NOT a failure date. It answers a narrower, defensible question:
"If the current motion regime continues, when might cumulative displacement
reach this asset type's operational inspection threshold?"

Two models are run and reported as a band:
  * constant-velocity  (conservative)
  * accelerating       (quadratic fit over the trailing window)
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from app.core.config import AssetProfile
from app.services.detection.metrics import (
    DAYS_PER_MONTH,
    MotionMetrics,
    SiteSeries,
    displacement_at,
)

HORIZON_DAYS = 365
MIN_BAND_SPREAD = 0.15  # if both models agree within 15%, widen to a single-model band


@dataclass
class Outlook:
    status: str  # threshold_exceeded | approaching | no_crossing_expected | not_applicable
    threshold_mm: float
    progress_mm: float  # magnitude of displacement already accumulated in the window
    eta_low_days: int | None
    eta_high_days: int | None
    eta_constant_days: int | None
    eta_accelerating_days: int | None
    assumptions: list[str] = field(default_factory=list)


def _assumptions(profile: AssetProfile) -> list[str]:
    return [
        "Current motion regime continues; no new extreme rainfall, excavation or seismic event.",
        f"Threshold measured as cumulative displacement over a {profile.threshold_window_days}-day window.",
        "Single line-of-sight (LOS) geometry; true 3D motion may differ.",
        "Satellite revisit cadence is 6-12 days; sudden events between passes are not captured.",
    ]


def _quadratic_eta(
    dates: np.ndarray, disp: np.ndarray, window_days: int, threshold: float, direction: float
) -> float | None:
    last = dates[-1]
    start = last - np.timedelta64(window_days, "D")
    mask = dates >= start
    if mask.sum() < 6:
        return None
    t = (dates[mask] - dates[mask][0]).astype("timedelta64[D]").astype(float)
    ref = displacement_at(dates, disp, start)
    y = direction * (disp[mask] - ref)  # growth in the direction of motion
    a, b, c = np.polyfit(t, y, 2)
    if a <= 1e-6:  # not accelerating in this direction
        return None
    t_now = float(t[-1])
    # a t^2 + b t + (c - T) = 0
    disc = b * b - 4 * a * (c - threshold)
    if disc < 0:
        return None
    roots = [(-b + np.sqrt(disc)) / (2 * a), (-b - np.sqrt(disc)) / (2 * a)]
    future = [r - t_now for r in roots if r > t_now]
    if not future:
        return None
    return float(min(future))


def compute_outlook(
    series: SiteSeries, m: MotionMetrics, profile: AssetProfile
) -> Outlook:
    threshold = profile.threshold_mm
    progress = abs(m.d_window_mm)
    base = Outlook(
        status="not_applicable",
        threshold_mm=threshold,
        progress_mm=round(progress, 2),
        eta_low_days=None,
        eta_high_days=None,
        eta_constant_days=None,
        eta_accelerating_days=None,
        assumptions=_assumptions(profile),
    )

    if progress >= threshold:
        base.status = "threshold_exceeded"
        base.eta_low_days = base.eta_high_days = 0
        return base

    v = m.rate_recent_mm_month
    direction = float(np.sign(m.d_window_mm) or np.sign(v) or -1.0)
    # Only project forward if recent motion continues in the same direction as the window motion
    same_dir = np.sign(v) == direction and abs(v) >= 0.3
    if not same_dir:
        base.status = "no_crossing_expected"
        return base

    v_day = abs(v) / DAYS_PER_MONTH
    remaining = threshold - progress
    const_days = remaining / v_day if v_day > 0 else None
    accel_days = _quadratic_eta(
        series.dates, series.disp_mm, profile.threshold_window_days, threshold, direction
    )

    candidates = [d for d in (const_days, accel_days) if d is not None and d <= HORIZON_DAYS]
    if not candidates:
        base.status = "no_crossing_expected"
        base.eta_constant_days = int(const_days) if const_days is not None else None
        return base

    lo, hi = min(candidates), max(candidates)
    if len(candidates) == 1 or (hi - lo) / max(hi, 1) < MIN_BAND_SPREAD:
        mid = (lo + hi) / 2
        lo, hi = mid * 0.75, mid * 1.35

    base.status = "approaching"
    base.eta_low_days = max(1, int(round(lo)))
    base.eta_high_days = max(base.eta_low_days, int(round(min(hi, HORIZON_DAYS))))
    base.eta_constant_days = int(round(const_days)) if const_days is not None else None
    base.eta_accelerating_days = int(round(accel_days)) if accel_days is not None else None
    return base


def projection_curves(series: SiteSeries, profile: AssetProfile, horizon_days: int, step_days: int = 6) -> dict:
    """Forward curves for the Outlook chart (absolute LOS displacement, mm).

    Both are projections of the *current regime*, not predictions of failure.
    """
    last = series.dates[-1]
    d_last = float(series.disp_mm[-1])
    start = last - np.timedelta64(profile.threshold_window_days, "D")
    ref = displacement_at(series.dates, series.disp_mm, start)
    direction = float(np.sign(d_last - ref) or -1.0)

    mask = series.dates >= start
    t = (series.dates[mask] - series.dates[mask][0]).astype("timedelta64[D]").astype(float)
    t_now = float(t[-1])
    horizon = np.arange(0, horizon_days + 1, step_days, dtype=float)

    # constant velocity from the recent 60-day slope
    recent = series.dates >= last - np.timedelta64(60, "D")
    from app.services.detection.metrics import linear_rate

    v_month = linear_rate(series.dates[recent], series.disp_mm[recent])
    constant = d_last + (v_month / DAYS_PER_MONTH) * horizon

    accelerating = None
    if mask.sum() >= 6:
        y = direction * (series.disp_mm[mask] - ref)
        a, b, c = np.polyfit(t, y, 2)
        if a > 1e-6:
            y_future = a * (t_now + horizon) ** 2 + b * (t_now + horizon) + c
            accelerating = (ref + direction * y_future).tolist()

    threshold_level = ref + direction * profile.threshold_mm
    return {
        "days_ahead": horizon.tolist(),
        "constant_mm": [round(float(x), 2) for x in constant],
        "accelerating_mm": [round(float(x), 2) for x in accelerating] if accelerating else None,
        "threshold_level_mm": round(float(threshold_level), 2),
        "window_reference_mm": round(float(ref), 2),
    }
