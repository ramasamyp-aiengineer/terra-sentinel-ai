"""Detection engine tests: math, golden cases and safety guarantees."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.core.config import PROFILES
from app.services.detection.forecast import compute_outlook
from app.services.detection.metrics import SiteSeries, compute_metrics, linear_rate
from app.services.detection.tiering import (
    assign_tier,
    classify_state,
    compute_confidence,
    compute_rpi,
)

HW = PROFILES["HIGHWAY"]


def make_series(disp, step=12, coherence=0.88, n_points=10, agreement=0.95, end="2026-10-10"):
    n = len(disp)
    dates = pd.date_range(end=end, periods=n, freq=f"{step}D").to_numpy().astype("datetime64[D]")
    return SiteSeries(dates, np.asarray(disp, float), n_points, coherence, agreement)


def run(series, criticality=0.9, rain=None, profile=HW):
    m = compute_metrics(series, profile.threshold_window_days)
    o = compute_outlook(series, m, profile)
    c = compute_confidence(series, m)
    state, _ = classify_state(series, m, o, c, profile)
    tier = assign_tier(state, criticality, o, rain, profile)
    rpi, _ = compute_rpi(m, o, c, criticality, rain, profile)
    return m, o, c, state, tier, rpi


def linear(n, mm_per_month, step=12, noise=0.0, seed=1):
    rng = np.random.default_rng(seed)
    t = np.arange(n) * step
    return -(mm_per_month / 30.4375) * t + rng.normal(0, noise, n)


# ---- math -------------------------------------------------------------------


def test_linear_rate_recovers_known_slope():
    s = make_series(linear(40, 3.0))
    assert linear_rate(s.dates, s.disp_mm) == pytest.approx(-3.0, abs=0.05)


def test_acceleration_ratio_detects_doubling():
    # 2 mm/month for a year, then 4 mm/month for the last ~90 days
    n = 46
    t = np.arange(n) * 12
    v = np.where(t < t[-1] - 90, 2.0, 4.0)
    disp = -np.cumsum(v * 12 / 30.4375)
    m = compute_metrics(make_series(disp))
    assert m.accel_ratio >= 1.8
    assert m.rate_recent_mm_month < -3.0


def test_constant_creep_has_ratio_near_one():
    m = compute_metrics(make_series(linear(46, 2.5, noise=0.2)))
    assert 0.8 <= m.accel_ratio <= 1.3


# ---- outlook ----------------------------------------------------------------


def test_outlook_constant_velocity_eta_is_sensible():
    # 4 mm/month steady; window 180d already at ~24 mm => ~16 mm left => ~4 months
    s = make_series(linear(46, 4.0))
    m = compute_metrics(s)
    o = compute_outlook(s, m, HW)
    assert o.status == "approaching"
    assert o.eta_low_days < o.eta_high_days
    assert 60 <= (o.eta_low_days + o.eta_high_days) / 2 <= 200


def test_outlook_threshold_exceeded():
    s = make_series(linear(46, 10.0))  # ~60 mm in 180d > 40 mm threshold
    m = compute_metrics(s)
    o = compute_outlook(s, m, HW)
    assert o.status == "threshold_exceeded"
    assert o.eta_low_days == 0


def test_outlook_never_projects_when_motion_reverses():
    disp = np.concatenate([linear(30, 4.0), linear(16, -2.0) + linear(30, 4.0)[-1]])
    s = make_series(disp)
    m = compute_metrics(s)
    o = compute_outlook(s, m, HW)
    assert o.status in ("no_crossing_expected", "not_applicable")


def test_outlook_always_lists_assumptions_and_never_a_date():
    s = make_series(linear(46, 4.0))
    o = compute_outlook(s, compute_metrics(s), HW)
    assert len(o.assumptions) >= 3
    assert not hasattr(o, "failure_date")


# ---- golden cases -----------------------------------------------------------


def test_golden_stable():
    rng = np.random.default_rng(3)
    s = make_series(rng.normal(0, 0.4, 46))
    *_, state, tier, rpi = run(s)
    assert state == "stable" and tier == "STABLE" and rpi < 5


def test_golden_persistent_creep():
    s = make_series(linear(46, 2.8, noise=0.3))
    *_, state, tier, _ = run(s)
    assert state == "persistent_creep"
    assert tier == "ELEVATED"


def test_golden_accelerating_critical_with_rain_on_critical_asset():
    n = 46
    t = np.arange(n) * 12
    v = np.where(t < 360, 1.2, 1.2 + (t - 360) / (t[-1] - 360) * 4.6)
    disp = -np.cumsum(v * 12 / 30.4375)
    *_, state, tier, _ = run(make_series(disp), criticality=0.95, rain=100)
    assert state in ("accelerating", "threshold_approach")
    assert tier == "CRITICAL"


def test_same_motion_lower_consequence_ranks_lower():
    n = 46
    t = np.arange(n) * 12
    v = np.where(t < 360, 1.2, 1.2 + (t - 360) / (t[-1] - 360) * 4.6)
    s = make_series(-np.cumsum(v * 12 / 30.4375))
    *_, tier_hi, rpi_hi = run(s, criticality=0.95, rain=100)
    *_, tier_lo, rpi_lo = run(s, criticality=0.40, rain=100)
    assert rpi_hi > rpi_lo
    assert tier_lo != "CRITICAL"


def test_golden_seasonal_is_watch_and_discounted():
    t = np.arange(46) * 12.0
    bump = np.exp(-0.5 * ((t - 120) / 35) ** 2) + np.exp(-0.5 * ((t - 485) / 35) ** 2)
    s = make_series(-9.0 * bump)
    m, o, c, state, tier, rpi = run(s)
    assert state == "seasonal"
    assert tier == "WATCH"
    assert rpi < 25


# ---- safety guarantees ------------------------------------------------------


@pytest.mark.parametrize("coherence", [0.2, 0.35, 0.45])
def test_low_coherence_never_critical(coherence):
    # Violent apparent motion, but unusable coherence
    s = make_series(linear(46, 12.0, noise=3.0), coherence=coherence, n_points=10)
    *_, state, tier, rpi = run(s, criticality=1.0, rain=100)
    assert tier == "WEAK"
    assert state == "data_degraded"


def test_too_few_points_never_critical():
    s = make_series(linear(46, 12.0), n_points=2)
    *_, tier, _ = run(s, criticality=1.0, rain=100)[3:]
    assert tier != "CRITICAL"


def test_rain_alone_does_not_create_priority():
    rng = np.random.default_rng(5)
    s = make_series(rng.normal(0, 0.3, 46))
    *_, tier, rpi = run(s, criticality=1.0, rain=100)
    assert tier == "STABLE"
    assert rpi < 5


def test_confidence_lowers_rank():
    base = linear(46, 5.0)
    good = make_series(base, coherence=0.9, n_points=12, agreement=0.95)
    weak = make_series(base, coherence=0.62, n_points=4, agreement=0.6)
    *_, rpi_good = run(good)
    *_, rpi_weak = run(weak)
    assert rpi_good > rpi_weak
