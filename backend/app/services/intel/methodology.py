"""Methodology: the rules the platform applies, rendered from the live configuration (never hand-copied)."""
from __future__ import annotations

from app.core.config import PROFILES
from app.services.detection.engine import CHAINAGE_BIN_M
from app.services.detection.pipeline import RAIN_SATURATION_MM
from app.services.detection.tiering import HIGH_CRITICALITY


def methodology() -> dict:
    return {
        "principle": "Mathematics detects. Gemini explains. Every number shown comes from a tool, a query or a stored observation.",
        "pipeline": [
            {"step": "1. Ingest", "text": "InSAR scatterers (position, velocity, coherence) and their displacement time series, plus daily rainfall and the asset geometry, are validated and stored."},
            {"step": "2. Locate", "text": f"Each scatterer within an asset's buffer is assigned a chainage along the asset. Sites are {CHAINAGE_BIN_M:.0f} m chainage bins."},
            {"step": "3. Measure", "text": "Per site, the median displacement series gives recent and baseline speed, acceleration, 60-day change, persistence, noise and a seasonality check."},
            {"step": "4. Classify", "text": "Each site is stable, seasonal, persistent creep, accelerating, approaching its operational threshold, or data-degraded."},
            {"step": "5. Rank", "text": "Risk Priority Index = hazard x consequence x confidence, then a tier (CRITICAL / ELEVATED / WATCH / STABLE / WEAK)."},
            {"step": "6. Outlook", "text": "A time-to-threshold band from two regimes: speed continues, or acceleration continues. Reported as a band, never as a failure date."},
            {"step": "7. Explain", "text": "Gemini drafts the narrative of a work order from tool outputs. A validator rejects any number not found in the tool data; a template is the fallback."},
        ],
        "tiers": [
            {"tier": "CRITICAL", "rule": f"Accelerating on a high-criticality asset (>= {HIGH_CRITICALITY:.1f}) with heavy rain or an outlook inside the planning horizon; or approaching/exceeding the threshold on an asset with criticality >= 0.5."},
            {"tier": "ELEVATED", "rule": "Accelerating, approaching threshold, or persistent creep on a high-criticality asset, below the CRITICAL conditions."},
            {"tier": "WATCH", "rule": "Seasonal recoverable pattern, or persistent creep on a lower-criticality asset."},
            {"tier": "STABLE", "rule": "No motion above baseline noise."},
            {"tier": "WEAK", "rule": "Data too weak to assess: low confidence, low coherence, fewer than 3 scatterers or fewer than 8 epochs. Excluded from rankings; no outlook is shown."},
        ],
        "rpi": {
            "formula": "RPI = hazard x consequence x confidence (0-100)",
            "hazard": f"Kinematic score (speed 40%, acceleration 30%, progress to threshold 30%) x (1 + 0.5 x rain trigger/100). The rain trigger maps 14-day rainfall to 0-100, saturating at {RAIN_SATURATION_MM:.0f} mm.",
            "consequence": "0.5 + 0.5 x asset criticality",
            "confidence": "0.5 + 0.5 x data-confidence score",
            "guards": ["Rain alone creates no hazard: heavy rain over stable ground does not rank as urgent.", "A stable but critical asset scores near zero.", "Seasonal patterns are discounted to 35%.", "WEAK sites are capped at 15."],
        },
        "profiles": [
            {
                "asset_type": p.asset_type,
                "label": p.label,
                "buffer_m": p.buffer_m,
                "threshold_mm": p.threshold_mm,
                "window_days": p.threshold_window_days,
                "creep_mm_month": p.creep_mm_month,
                "accel_ratio": p.accel_ratio,
                "approach_days": p.approach_days,
                "min_coherence": p.min_coherence,
                "mechanism_hint": p.mechanism_hint,
            }
            for p in PROFILES.values()
        ],
        "alerts": [
            "An alert is a change between two consecutive satellite passes, not a state.",
            "Rules: threshold exceeded, escalation to CRITICAL or ELEVATED, entering the planning horizon, acceleration onset, data degradation, de-escalation, and heavy rain over a region that has active sites.",
            "Each alert states the previous and current values. Acknowledge, assign, escalate and resolve actions are recorded with who and when.",
        ],
        "limitations": [
            "InSAR measures displacement along the satellite line of sight, not true 3-D movement.",
            "Scatterer density is low over vegetation and snow; sparse coverage lowers confidence and is shown as WEAK.",
            "Outlooks assume the current motion regime continues. They are not predictions of failure.",
            "Thresholds are defaults per asset type; the asset owner's engineers should set the real ones.",
            "Decision-support for qualified engineers; not a substitute for field inspection.",
        ],
    }
