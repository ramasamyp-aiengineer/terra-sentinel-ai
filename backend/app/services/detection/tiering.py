"""Confidence, state classification, warning tier and Risk Priority Index (RPI).

Design rules (enforced by tests):
  * Low-quality data can never produce a CRITICAL tier -> it becomes WEAK.
  * Confidence lowers rank: a weak signal must not outrank a strong one.
  * Hazard alone is geography; hazard x consequence is priority.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.core.config import AssetProfile
from app.services.detection.forecast import Outlook
from app.services.detection.metrics import MotionMetrics, SiteSeries

TIER_RANK = {"WEAK": -1, "STABLE": 0, "WATCH": 1, "ELEVATED": 2, "CRITICAL": 3}
HIGH_CRITICALITY = 0.7


def _clip(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return float(max(lo, min(hi, x)))


@dataclass
class Confidence:
    score: float
    label: str  # high | medium | low
    drivers: dict[str, float]


def compute_confidence(series: SiteSeries, m: MotionMetrics) -> Confidence:
    coh = _clip((series.coherence_mean - 0.4) / 0.5)
    epochs = _clip(m.n_epochs / 30)
    points = _clip(series.n_points / 8)
    agree = _clip(series.agreement)
    noise = m.noise_mm if m.noise_mm == m.noise_mm else 2.0
    snr = _clip(abs(m.d60_mm) / (2.0 * noise + 0.5))
    score = 0.30 * coh + 0.15 * epochs + 0.20 * points + 0.20 * agree + 0.15 * snr
    # Hard caps: a weighted average must not hide fundamentally unusable inputs.
    if series.coherence_mean < 0.5 or series.n_points < 3:
        score = min(score, 0.30)
    label = "high" if score >= 0.7 else "medium" if score >= 0.45 else "low"
    return Confidence(
        score=round(score, 3),
        label=label,
        drivers={
            "coherence": round(coh, 2),
            "epochs": round(epochs, 2),
            "points": round(points, 2),
            "agreement": round(agree, 2),
            "signal_to_noise": round(snr, 2),
        },
    )


def classify_state(
    series: SiteSeries,
    m: MotionMetrics,
    outlook: Outlook,
    conf: Confidence,
    profile: AssetProfile,
) -> tuple[str, list[str]]:
    """Return (state, reasons). Reasons are human-readable, derived from numbers."""
    speed = abs(m.rate_recent_mm_month)
    reasons: list[str] = []

    if (
        conf.score < 0.35
        or series.coherence_mean < profile.min_coherence
        or series.n_points < 3
        or m.n_epochs < 8
    ):
        reasons.append(
            f"Data quality insufficient (confidence {conf.score:.2f}, coherence "
            f"{series.coherence_mean:.2f}, {series.n_points} points, {m.n_epochs} epochs)."
        )
        return "data_degraded", reasons

    if m.seasonal_flag:
        reasons.append(
            f"Seasonal pattern: peak excursion {m.peak_excursion_mm:.1f} mm largely recovers over 12 months."
        )
        return "seasonal", reasons

    if outlook.status == "threshold_exceeded" or (
        outlook.status == "approaching"
        and outlook.eta_low_days is not None
        and outlook.eta_low_days <= profile.approach_days
        and speed >= profile.creep_mm_month
    ):
        reasons.append(
            f"Cumulative displacement {outlook.progress_mm:.1f} mm of {outlook.threshold_mm:.0f} mm "
            f"operational threshold; projected crossing in "
            f"{outlook.eta_low_days}-{outlook.eta_high_days} days."
            if outlook.status == "approaching"
            else f"Operational threshold of {outlook.threshold_mm:.0f} mm already exceeded."
        )
        return "threshold_approach", reasons

    if m.accel_ratio >= profile.accel_ratio and speed >= profile.creep_mm_month and m.persistence >= 3:
        reasons.append(
            f"Speed rose from {abs(m.rate_baseline_mm_month):.1f} to {speed:.1f} mm/month "
            f"({m.accel_ratio:.1f}x) over {m.persistence} consecutive epochs."
        )
        return "accelerating", reasons

    if speed >= profile.creep_mm_month and m.persistence >= 4:
        reasons.append(
            f"Persistent creep of {speed:.1f} mm/month for {m.persistence} consecutive epochs, no acceleration."
        )
        return "persistent_creep", reasons

    reasons.append("No meaningful motion above baseline noise.")
    return "stable", reasons


def assign_tier(
    state: str, criticality: float, outlook: Outlook, rain_trigger: float | None, profile: AssetProfile
) -> str:
    high = criticality >= HIGH_CRITICALITY
    heavy_rain = rain_trigger is not None and rain_trigger >= 60
    if state == "data_degraded":
        return "WEAK"
    if state == "stable":
        return "STABLE"
    if state == "seasonal":
        return "WATCH"
    if state == "persistent_creep":
        return "ELEVATED" if high else "WATCH"
    if state == "accelerating":
        near = outlook.eta_low_days is not None and outlook.eta_low_days <= profile.approach_days
        return "CRITICAL" if high and (heavy_rain or near) else "ELEVATED"
    if state == "threshold_approach":
        return "CRITICAL" if criticality >= 0.5 else "ELEVATED"
    return "WATCH"


def compute_rpi(
    m: MotionMetrics,
    outlook: Outlook,
    conf: Confidence,
    criticality: float,
    rain_trigger: float | None,
    profile: AssetProfile,
) -> tuple[float, dict[str, float]]:
    """Risk Priority Index 0-100.

    rpi = hazard x consequence x confidence
      hazard      = kinematic x (1 + 0.5 * trigger/100)   (rain AMPLIFIES motion)
      consequence = 0.5 + 0.5 * criticality
      confidence  = 0.5 + 0.5 * confidence_score

    Two deliberate departures from a naive additive index:
      * Rain alone creates no hazard. Heavy rain over perfectly stable ground
        must not rank as urgent (that is the false-alarm problem we exist to fix).
      * A perfectly stable but critical asset must score ~0, not "urgent".
    Seasonal (known recovering) patterns are discounted; they stay on watch.
    """
    speed = abs(m.rate_recent_mm_month)
    speed_t = _clip(speed / (5 * profile.creep_mm_month))
    accel_t = _clip((m.accel_ratio - 1) / 3)
    prog_t = _clip(outlook.progress_mm / outlook.threshold_mm) if outlook.threshold_mm else 0.0
    kin = 100 * (0.4 * speed_t + 0.3 * accel_t + 0.3 * prog_t)
    trig = rain_trigger if rain_trigger is not None else 0.0
    hazard = min(100.0, kin * (1 + 0.5 * trig / 100))
    if m.seasonal_flag:
        hazard *= 0.35
    # Below the creep threshold there is no meaningful motion: damp, don't rank.
    if speed < profile.creep_mm_month and outlook.progress_mm < 0.25 * outlook.threshold_mm:
        hazard *= 0.2
    consequence = 0.5 + 0.5 * criticality
    confidence = 0.5 + 0.5 * conf.score
    rpi = float(np.clip(hazard * consequence * confidence, 0, 100))
    return round(rpi, 1), {
        "kinematic": round(kin, 1),
        "trigger": round(trig, 1),
        "hazard": round(hazard, 1),
        "consequence_factor": round(consequence, 2),
        "confidence_factor": round(confidence, 2),
    }
