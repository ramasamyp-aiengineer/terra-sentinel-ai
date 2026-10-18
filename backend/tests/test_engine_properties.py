"""Property tests: the engine must never crash or emit nonsense, whatever the series looks like.

Real satellite data is messy (short series, gaps, spikes, flat lines, huge values). These tests
generate thousands of random and degenerate series and check invariants, not exact numbers.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from app.core.config import PROFILES
from app.services.detection.forecast import HORIZON_DAYS, compute_outlook, projection_curves
from app.services.detection.metrics import SiteSeries, compute_metrics
from app.services.detection.tiering import assign_tier, classify_state, compute_confidence, compute_rpi

TIERS = {"CRITICAL", "ELEVATED", "WATCH", "STABLE", "WEAK"}


def _series(disp, step, coherence=0.8, agreement=0.9, n_points=5):
    n = len(disp)
    dates = pd.date_range(end="2026-10-10", periods=n, freq=f"{step}D").to_numpy().astype("datetime64[D]")
    return SiteSeries(dates, np.asarray(disp, float), n_points, coherence, agreement)


def _assess(series, profile, criticality, rain=None):
    m = compute_metrics(series, profile.threshold_window_days)
    o = compute_outlook(series, m, profile)
    c = compute_confidence(series, m)
    state, reasons = classify_state(series, m, o, c, profile)
    tier = assign_tier(state, criticality, o, rain, profile)
    rpi, breakdown = compute_rpi(m, o, c, criticality, rain, profile)
    return m, o, c, state, reasons, tier, rpi, breakdown


def _random_disp(rng: np.random.Generator, n: int, step: int):
    kind = rng.integers(0, 7)
    t = np.arange(n) * step
    if kind == 0:  # flat
        return np.zeros(n)
    if kind == 1:  # linear creep with noise
        return -rng.uniform(0, 12) / 30.4375 * t + rng.normal(0, rng.uniform(0, 2), n)
    if kind == 2:  # accelerating
        return -(rng.uniform(0, 0.002) * t**2 + rng.uniform(0, 0.1) * t)
    if kind == 3:  # seasonal
        return rng.uniform(1, 15) * np.sin(2 * np.pi * t / 365)
    if kind == 4:  # single spike
        d = rng.normal(0, 0.5, n)
        d[rng.integers(0, n)] += rng.uniform(-200, 200)
        return d
    if kind == 5:  # huge magnitudes
        return rng.uniform(-1, 1) * 1e6 * t / max(t.max(), 1)
    return np.cumsum(rng.normal(0, 3, n))  # random walk


@pytest.mark.parametrize("asset_type", sorted(PROFILES))
def test_random_series_never_crash_and_respect_invariants(asset_type):
    rng = np.random.default_rng(20261016)
    profile = PROFILES[asset_type]
    for _ in range(400):
        n = int(rng.integers(3, 90))
        step = int(rng.integers(1, 60))
        series = _series(
            _random_disp(rng, n, step),
            step,
            coherence=float(rng.uniform(0, 1)),
            agreement=float(rng.uniform(0, 1)),
            n_points=int(rng.integers(1, 40)),
        )
        crit = float(rng.uniform(0, 1))
        rain = None if rng.random() < 0.5 else float(rng.uniform(0, 100))
        try:
            m, o, c, state, reasons, tier, rpi, _ = _assess(series, profile, crit, rain)
        except Exception as exc:  # noqa: BLE001 - the point is to catch any crash
            pytest.fail(f"engine crashed for n={n} step={step}: {exc!r}")

        assert tier in TIERS
        assert state
        assert math.isfinite(rpi) and 0.0 <= rpi <= 100.0, rpi
        for v in (m.rate_recent_mm_month, m.rate_baseline_mm_month, m.accel_ratio, m.d60_mm, m.d_window_mm, m.current_disp_mm):
            assert math.isfinite(v), (m, n, step)
        assert o.status in {"threshold_exceeded", "approaching", "no_crossing_expected", "not_applicable"}
        if o.status == "approaching":
            assert o.eta_low_days is not None and o.eta_high_days is not None
            assert 1 <= o.eta_low_days <= o.eta_high_days <= HORIZON_DAYS
        if o.status == "threshold_exceeded":
            assert o.eta_low_days == o.eta_high_days == 0
        if o.status in {"no_crossing_expected", "not_applicable"}:
            assert o.eta_low_days is None and o.eta_high_days is None


def test_engine_is_deterministic():
    rng = np.random.default_rng(7)
    s = _series(_random_disp(rng, 40, 12), 12)
    a = _assess(s, PROFILES["HIGHWAY"], 0.7)
    b = _assess(s, PROFILES["HIGHWAY"], 0.7)
    assert a[5] == b[5] and a[6] == b[6] and a[1] == b[1]


def test_flat_series_is_never_alarming():
    for n in (3, 10, 60):
        _, o, _, _, _, tier, rpi, _ = _assess(_series(np.zeros(n), 12), PROFILES["METRO"], 1.0, rain=100.0)
        assert tier in {"STABLE", "WEAK"}
        assert o.status in {"no_crossing_expected", "not_applicable"}
        assert rpi <= 15.0  # heavy rain over still ground must not look urgent


def test_unusable_data_never_outranks_clean_signal():
    """A noisy, low-coherence series must not get a higher priority than the same motion on clean data."""
    t = np.arange(40) * 12
    motion = -(6.0 / 30.4375) * t
    clean = _assess(_series(motion, 12, coherence=0.9, agreement=0.95), PROFILES["HIGHWAY"], 0.9)
    dirty = _assess(_series(motion, 12, coherence=0.05, agreement=0.2), PROFILES["HIGHWAY"], 0.9)
    assert dirty[6] <= clean[6]


def test_higher_criticality_never_lowers_priority():
    t = np.arange(40) * 12
    s = _series(-(5.0 / 30.4375) * t, 12)
    prev = -1.0
    for crit in (0.1, 0.3, 0.5, 0.7, 0.9, 1.0):
        rpi = _assess(s, PROFILES["DAM"], crit)[6]
        assert rpi >= prev - 1e-9
        prev = rpi


def test_faster_motion_never_lowers_priority():
    t = np.arange(40) * 12
    prev = -1.0
    for rate in (0.0, 1.0, 2.0, 4.0, 8.0, 16.0):
        rpi = _assess(_series(-(rate / 30.4375) * t, 12), PROFILES["HIGHWAY"], 0.8)[6]
        assert rpi >= prev - 1e-9, (rate, rpi, prev)
        prev = rpi


def test_projection_curves_stay_finite():
    rng = np.random.default_rng(11)
    for _ in range(150):
        n = int(rng.integers(3, 80))
        step = int(rng.integers(1, 40))
        s = _series(_random_disp(rng, n, step), step)
        curves = projection_curves(s, PROFILES["HIGHWAY"], 180)
        assert all(math.isfinite(x) for x in curves["constant_mm"])
        if curves["accelerating_mm"]:
            assert all(math.isfinite(x) for x in curves["accelerating_mm"])


# ---- messy tables through the full asset -> site path ----------------------------------------------


def _assess_tables(points: pd.DataFrame, ts: pd.DataFrame):
    from shapely.geometry import LineString

    from app.services.detection.engine import Asset, assess_asset

    asset = Asset("A1", "Test road", "HIGHWAY", "R1", 0.8, "note", LineString([(79.50, 30.50), (79.60, 30.55)]))
    return assess_asset(asset, points, ts)


def _points(n=6):
    return pd.DataFrame(
        {
            "point_id": [f"P{i}" for i in range(n)],
            "lat": [30.5 + 0.001 * i for i in range(n)],
            "lon": [79.5 + 0.001 * i for i in range(n)],
            "velocity_mm_yr": -20.0,
            "coherence": 0.85,
        }
    )


def _ts(points, epochs=30, rate=-0.4, nan_share=0.0, dup=False, seed=3):
    rng = np.random.default_rng(seed)
    dates = pd.date_range(end="2026-10-10", periods=epochs, freq="12D")
    rows = []
    for pid in points["point_id"]:
        for i, d in enumerate(dates):
            v = rate * i + rng.normal(0, 0.3)
            rows.append((pid, d, np.nan if rng.random() < nan_share else v))
            if dup:
                rows.append((pid, d, v + 5))
    return pd.DataFrame(rows, columns=["point_id", "date", "disp_mm"])


@pytest.mark.parametrize(
    "kwargs",
    [
        {},
        {"nan_share": 0.3},
        {"nan_share": 0.95},
        {"dup": True},
        {"epochs": 3},
        {"epochs": 1},
        {"epochs": 2},
        {"rate": 0.0},
        {"rate": -50.0},
    ],
)
def test_messy_tables_never_crash(kwargs):
    pts = _points()
    sites = _assess_tables(pts, _ts(pts, **kwargs))
    for s in sites:
        assert s.tier in TIERS
        assert math.isfinite(s.rpi) and 0 <= s.rpi <= 100


def test_points_without_any_timeseries_are_skipped_not_fatal():
    pts = _points()
    ts = pd.DataFrame({"point_id": ["OTHER"], "date": [pd.Timestamp("2026-10-01")], "disp_mm": [0.0]})
    assert _assess_tables(pts, ts) == []


def test_empty_inputs_are_handled():
    pts = _points()
    assert _assess_tables(pts.iloc[0:0], _ts(pts)) == []
    assert _assess_tables(pts, pd.DataFrame({"point_id": [], "date": pd.to_datetime([]), "disp_mm": []})) == []
