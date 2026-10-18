"""Deterministic tools exposed to the agent.

Every number the agent is allowed to quote comes from one of these functions.
They are plain Python callables with type hints + docstrings so the Gemini SDK
can register them directly for function calling.
"""
from __future__ import annotations

from app.services.detection import views


def _detail(site_id: str) -> dict:
    s = views.site_by_id().get(site_id)
    if s is None:
        return {"error": f"unknown site_id {site_id}"}
    return views.site_detail(s)


def get_site_metrics(site_id: str) -> dict:
    """Current motion metrics, tier and state for a monitored site.

    Args:
        site_id: Site identifier, e.g. "NH58-DEMO-010".
    Returns:
        Tier, state, speed (mm/month, negative = moving away from satellite),
        acceleration ratio, 60-day and window displacement, point count.
    """
    d = _detail(site_id)
    if "error" in d:
        return d
    m = d["metrics"]
    return {
        "site_id": site_id,
        "tier": d["tier"],
        "state": d["state"],
        "state_reasons": d["state_reasons"],
        "rate_recent_mm_month": m["rate_recent_mm_month"],
        "rate_baseline_mm_month": m["rate_baseline_mm_month"],
        "accel_ratio": m["accel_ratio"],
        "d60_mm": m["d60_mm"],
        "d_window_mm": m["d_window_mm"],
        "persistence_epochs": m["persistence"],
        "n_points": d["n_points"],
        "last_epoch": m["last_epoch"],
        "rpi": d["rpi"],
        "recent_window_days": 60,
        "peak_excursion_mm": m["peak_excursion_mm"],
    }


def get_displacement_history(site_id: str) -> dict:
    """Summary of the displacement time series (not the full array) for a site.

    Args:
        site_id: Site identifier.
    Returns:
        Number of epochs, span in days, first/last displacement and the
        displacement at roughly 30, 90 and 180 days before the last epoch.
    """
    from app.services.detection.views import site_timeseries

    if site_id not in views.site_by_id():
        return {"error": f"unknown site_id {site_id}"}
    ts = site_timeseries(site_id)
    disp, dates = ts["disp_mm"], ts["dates"]
    n = len(disp)

    def back(k: int) -> float:
        return disp[max(0, n - 1 - round(k / 12))]

    return {
        "site_id": site_id,
        "epochs": n,
        "first_date": dates[0],
        "last_date": dates[-1],
        "displacement_first_mm": disp[0],
        "displacement_last_mm": disp[-1],
        "displacement_30d_ago_mm": back(30),
        "displacement_90d_ago_mm": back(90),
        "displacement_180d_ago_mm": back(180),
        "convention": "negative = moving away from satellite (typically subsidence / downslope)",
    }


def get_outlook(site_id: str) -> dict:
    """Time-to-threshold outlook if the current motion regime continues.

    Args:
        site_id: Site identifier.
    Returns:
        Status, operational threshold (mm), progress (mm), an ETA band in days
        (low-high), and the assumptions. This is NOT a failure prediction.
    """
    d = _detail(site_id)
    if "error" in d:
        return d
    o = d["outlook"]
    return {
        "site_id": site_id,
        "status": o["status"],
        "threshold_mm": o["threshold_mm"],
        "threshold_window_days": d["thresholds"]["window_days"],
        "progress_mm": o["progress_mm"],
        "eta_low_days": o["eta_low_days"],
        "eta_high_days": o["eta_high_days"],
        "assumptions": o["assumptions"],
    }


def get_rainfall_context(site_id: str) -> dict:
    """Recent rainfall for the site's region (a trigger amplifier, not a hazard by itself).

    Args:
        site_id: Site identifier.
    Returns:
        14-day and 7-day rainfall totals (mm), peak day (mm), trigger score 0-100, data source.
    """
    d = _detail(site_id)
    if "error" in d:
        return d
    r = d.get("rain")
    if not r:
        return {"site_id": site_id, "available": False, "note": "Rainfall data unavailable; confidence reduced."}
    return {
        "site_id": site_id,
        "available": True,
        "rain_window_days": r["window_days"],
        **{k: r[k] for k in ("rain_14d_mm", "rain_7d_mm", "peak_day_mm", "trigger_score", "source")},
    }


def get_seismic_context(site_id: str) -> dict:
    """Recent and historical earthquakes near the site (public USGS data). Context only, never a cause.

    Args:
        site_id: Site identifier.
    Returns:
        Whether earthquake data is loaded; count and largest magnitude of M4.0+ events within 100 km in the
        30 days before the assessment date; the largest M5.0+ event within 200 km in the loaded history.
    """
    d = _detail(site_id)
    if "error" in d:
        return d
    s = d["seismic"]
    if not s["available"]:
        return {"site_id": site_id, "available": False, "note": "No earthquake data loaded; say nothing about seismicity."}
    out = {
        "site_id": site_id,
        "available": True,
        "recent_window_days": s["recent"]["window_days"],
        "recent_radius_km": s["recent"]["radius_km"],
        "recent_min_magnitude": s["recent"]["min_magnitude"],
        "recent_count": s["recent_count"],
        "recent_max_magnitude": s["recent_max_magnitude"],
        "recent_nearest_km": s["recent_nearest_km"],
        "history_radius_km": s["history"]["radius_km"],
        "history_min_magnitude": s["history"]["min_magnitude"],
        "history_count": s["history_count"],
        "history_largest": s["history_largest"],
        "coverage_from": s["coverage"].get("date_from"),
        "coverage_to": s["coverage"].get("date_to"),
        "source": s["source"],
    }
    return out


def get_asset_exposure(site_id: str) -> dict:
    """What the site can affect: asset, criticality and consequence note.

    Args:
        site_id: Site identifier.
    Returns:
        Asset name/type, criticality (0-1), consequence description, chainage range.
    """
    d = _detail(site_id)
    if "error" in d:
        return d
    return {
        "site_id": site_id,
        "asset_name": d["asset_name"],
        "asset_type": d["asset_type"],
        "criticality": d["criticality"],
        "consequence_note": d["consequence_note"],
        "chainage_start_km": d["chainage_start_km"],
        "chainage_end_km": d["chainage_end_km"],
        "mechanism_hint": d["thresholds"]["mechanism_hint"],
    }


def get_data_quality(site_id: str) -> dict:
    """Measurement quality and confidence for a site.

    Args:
        site_id: Site identifier.
    Returns:
        Confidence score/label, drivers, mean coherence, scatterer agreement,
        number of scatterers and whether the data is demonstration data.
    """
    d = _detail(site_id)
    if "error" in d:
        return d
    c = d["confidence_detail"]
    return {
        "site_id": site_id,
        "confidence_score": c["score"],
        "confidence_label": c["label"],
        "drivers": c["drivers"],
        "coherence_mean": d["coherence_mean"],
        "agreement": d["agreement"],
        "n_points": d["n_points"],
        "data_source": d["data_source"],
    }


TOOLS = [
    get_site_metrics,
    get_displacement_history,
    get_outlook,
    get_rainfall_context,
    get_seismic_context,
    get_asset_exposure,
    get_data_quality,
]
TOOL_MAP = {f.__name__: f for f in TOOLS}
