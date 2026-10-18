"""Early-warning board: time-to-threshold outlook bands for every site that is moving.

Outlooks are bands, never dates: "if the current regime continues, the threshold is crossed in
X-Y days". The what-if endpoint rescales the recent rate linearly so an engineer can see how
sensitive the outlook is to the regime changing; the engine's band stays the authoritative output.
"""
from __future__ import annotations

from app.core.config import profile_for
from app.services.detection import views
from app.services.detection.metrics import DAYS_PER_MONTH
from app.services.detection.pipeline import run_pipeline
from app.services.intel import snapshots

BUCKETS = [
    ("exceeded", "Threshold exceeded", None, None),
    ("d0_30", "Within 30 days", 0, 30),
    ("d31_60", "31-60 days", 31, 60),
    ("d61_120", "61-120 days", 61, 120),
    ("d121_365", "121-365 days", 121, 365),
    ("none", "No crossing expected", None, None),
]


def bucket_of(outlook_status: str, eta_low: int | None) -> str:
    if outlook_status == "threshold_exceeded":
        return "exceeded"
    if outlook_status == "approaching" and eta_low is not None:
        for key, _, lo, hi in BUCKETS[1:5]:
            if lo <= eta_low <= hi:
                return key
        return "d121_365"
    return "none"


def board(region: str | None = None, asset_type: str | None = None) -> dict:
    ids = views.descendants(region) if region else None
    ps = snapshots.passes()
    prev = snapshots.table_for(ps[1]) if len(ps) > 1 else {}
    items = []
    for s in run_pipeline():
        if ids and s.region_id not in ids:
            continue
        if asset_type and s.asset_type != asset_type.upper():
            continue
        if s.tier in ("STABLE", "WEAK"):
            continue
        o = s.outlook
        p = prev.get(s.site_id)
        prog_pct = round(100 * o.progress_mm / o.threshold_mm, 0) if o.threshold_mm else 0
        d = views.site_summary(s)
        d.update(
            {
                "bucket": bucket_of(o.status, o.eta_low_days),
                "progress_mm": round(o.progress_mm, 1),
                "threshold_mm": o.threshold_mm,
                "progress_pct": min(prog_pct, 150),
                "eta_constant_days": o.eta_constant_days,
                "eta_accelerating_days": o.eta_accelerating_days,
                "assumptions": o.assumptions,
                "rate_baseline_mm_month": round(s.metrics.rate_baseline_mm_month, 2),
                "rpi_previous": p["rpi"] if p else None,
                "rpi_delta": round(s.rpi - p["rpi"], 1) if p else None,
                "tier_previous": p["tier"] if p else None,
                "state_reasons": s.reasons,
            }
        )
        items.append(views.clean(d))
    order = {k: i for i, (k, *_r) in enumerate(BUCKETS)}
    items.sort(key=lambda x: (order[x["bucket"]], x["eta_low_days"] if x["eta_low_days"] is not None else 9999, -x["rpi"]))
    summary = [{"key": k, "label": lab, "count": sum(1 for x in items if x["bucket"] == k)} for k, lab, *_ in BUCKETS]
    return {
        "as_of": ps[0].as_of if ps else None,
        "buckets": summary,
        "sites": items,
        "note": "Outlook bands assume the current motion regime continues. They are planning aids, not predictions of failure.",
    }


def scenario(site_id: str, rate_change_pct: float) -> dict:
    s = views.site_by_id().get(site_id)
    if s is None:
        raise KeyError(site_id)
    pct = max(-90.0, min(float(rate_change_pct), 300.0))
    o, m = s.outlook, s.metrics
    profile = profile_for(s.asset_type)
    base_rate = abs(m.rate_recent_mm_month)
    remaining = max(o.threshold_mm - o.progress_mm, 0.0)

    def days(rate: float) -> int | None:
        if o.status == "threshold_exceeded":
            return 0
        if o.status == "not_applicable" or rate < 0.05:
            return None
        return int(round(remaining / rate * DAYS_PER_MONTH))

    scenario_rate = base_rate * (1 + pct / 100.0)
    return {
        "site_id": site_id,
        "rate_change_pct": pct,
        "threshold_mm": o.threshold_mm,
        "progress_mm": round(o.progress_mm, 1),
        "remaining_mm": round(remaining, 1),
        "current_rate_mm_month": round(base_rate, 2),
        "scenario_rate_mm_month": round(scenario_rate, 2),
        "linear_days_current": days(base_rate),
        "linear_days_scenario": days(scenario_rate),
        "engine_band_days": [o.eta_low_days, o.eta_high_days],
        "within_planning_horizon": (days(scenario_rate) or 10**6) <= profile.approach_days,
        "approach_days": profile.approach_days,
        "note": (
            "Linear what-if: remaining displacement divided by the scaled recent rate. "
            "The engine's band (constant vs accelerating regimes) remains the authoritative outlook."
        ),
    }
