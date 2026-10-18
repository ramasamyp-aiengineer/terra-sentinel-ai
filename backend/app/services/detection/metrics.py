"""Deterministic motion metrics for one site time series.

Convention: displacement is in mm along the satellite line of sight (LOS).
Negative = moving away from the satellite (typically subsidence / downslope).
Everything here is plain numpy so it is unit-testable and explainable.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

DAYS_PER_MONTH = 30.4375
RATE_FLOOR_MM_MONTH = 0.5  # floor for the baseline rate, avoids divide-by-~0


@dataclass
class SiteSeries:
    """Aggregated (median across clustered scatterers) series for one site."""

    dates: np.ndarray  # datetime64[D], ascending
    disp_mm: np.ndarray  # float, same length
    n_points: int
    coherence_mean: float
    agreement: float  # share of points whose net motion has the same sign as the site


@dataclass
class MotionMetrics:
    n_epochs: int
    span_days: int
    last_epoch: str
    current_disp_mm: float
    rate_recent_mm_month: float  # signed
    rate_baseline_mm_month: float  # signed
    accel_ratio: float  # |recent| / max(|baseline|, floor)
    d60_mm: float  # signed change over trailing 60 days
    d_window_mm: float  # signed change over the threshold window
    persistence: int  # consecutive trailing epoch steps moving in the recent direction
    noise_mm: float  # residual std from linear fit (trailing 180d)
    seasonal_flag: bool
    peak_excursion_mm: float


def _t_days(dates: np.ndarray) -> np.ndarray:
    return (dates - dates[0]).astype("timedelta64[D]").astype(float)


def _slice_by_days(dates: np.ndarray, end_idx: int, start_back: int, end_back: int) -> slice:
    """Index slice for epochs within (end - start_back, end - end_back] days."""
    end_date = dates[end_idx]
    lo = end_date - np.timedelta64(start_back, "D")
    hi = end_date - np.timedelta64(end_back, "D")
    idx = np.where((dates >= lo) & (dates <= hi))[0]
    if len(idx) == 0:
        return slice(0, 0)
    return slice(idx[0], idx[-1] + 1)


def linear_rate(dates: np.ndarray, disp: np.ndarray) -> float:
    """OLS slope in mm/month. Returns 0 if fewer than 3 epochs."""
    if len(dates) < 3:
        return 0.0
    t = _t_days(dates)
    slope = np.polyfit(t, disp, 1)[0]  # mm/day
    return float(slope * DAYS_PER_MONTH)


def displacement_at(dates: np.ndarray, disp: np.ndarray, target: np.datetime64) -> float:
    """Linear interpolation of displacement at a date (clamped to range)."""
    t = (dates - dates[0]).astype("timedelta64[D]").astype(float)
    tt = float((target - dates[0]) / np.timedelta64(1, "D"))
    return float(np.interp(tt, t, disp))


def compute_metrics(series: SiteSeries, threshold_window_days: int = 180) -> MotionMetrics:
    dates, disp = series.dates, series.disp_mm
    n = len(dates)
    end = n - 1

    recent = _slice_by_days(dates, end, 60, 0)
    # Baseline sits BEHIND a 30-day gap so the onset of an acceleration is not
    # averaged into "normal" (which would hide a clean 2 -> 4 mm/month doubling).
    baseline = _slice_by_days(dates, end, 270, 90)
    rate_recent = linear_rate(dates[recent], disp[recent])
    rate_base = linear_rate(dates[baseline], disp[baseline])
    ratio = abs(rate_recent) / max(abs(rate_base), RATE_FLOOR_MM_MONTH)

    last = dates[end]
    d60 = disp[end] - displacement_at(dates, disp, last - np.timedelta64(60, "D"))
    d_win = disp[end] - displacement_at(dates, disp, last - np.timedelta64(threshold_window_days, "D"))

    # Persistence: how many consecutive trailing steps move in the recent direction
    # Computed on a 3-epoch moving average so single noisy epochs don't break a real trend.
    direction = np.sign(rate_recent) or 1.0
    smooth = np.convolve(disp, np.ones(3) / 3, mode="valid") if n >= 5 else disp
    steps = np.diff(smooth)
    persistence = 0
    for s in steps[::-1]:
        if np.sign(s) == direction and abs(s) > 0.1:  # ignore sub-noise wiggles
            persistence += 1
        else:
            break

    # Noise: residual of linear fit on trailing 180d
    w = _slice_by_days(dates, end, 180, 0)
    if len(dates[w]) >= 4:
        t = _t_days(dates[w])
        coef = np.polyfit(t, disp[w], 1)
        noise = float(np.std(disp[w] - np.polyval(coef, t)))
    else:
        noise = float("nan")

    # Seasonality: big excursion within last year that mostly recovers
    yr = _slice_by_days(dates, end, 365, 0)
    seg = disp[yr]
    if len(seg) >= 6:
        excursion = float(np.max(np.abs(seg - seg[0])))
        net = float(abs(seg[-1] - seg[0]))
        seasonal = excursion >= 6.0 and net / excursion < 0.35
    else:
        excursion, seasonal = 0.0, False

    return MotionMetrics(
        n_epochs=n,
        span_days=int((dates[-1] - dates[0]) / np.timedelta64(1, "D")),
        last_epoch=str(dates[-1]),
        current_disp_mm=float(disp[-1]),
        rate_recent_mm_month=round(rate_recent, 3),
        rate_baseline_mm_month=round(rate_base, 3),
        accel_ratio=round(float(ratio), 3),
        d60_mm=round(float(d60), 2),
        d_window_mm=round(float(d_win), 2),
        persistence=int(persistence),
        noise_mm=round(noise, 3) if noise == noise else float("nan"),
        seasonal_flag=bool(seasonal),
        peak_excursion_mm=round(excursion, 2),
    )
