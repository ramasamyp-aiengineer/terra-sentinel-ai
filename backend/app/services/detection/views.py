"""Read-model helpers: turn engine results into JSON-safe API payloads."""
from __future__ import annotations

import math
from dataclasses import asdict
from functools import lru_cache

import numpy as np
import pandas as pd

from app.core.config import profile_for
from app.services.data.repo import get_repo
from app.services.detection.engine import SiteAssessment, _build_series
from app.services.detection.forecast import projection_curves
from app.services.detection.pipeline import as_of_date, rain_context, run_pipeline
from app.services.detection.tiering import TIER_RANK

ACT_TIERS = ("CRITICAL", "ELEVATED")


def clean(obj):
    """Recursively replace NaN/inf with None so JSON encoding never fails."""
    if isinstance(obj, dict):
        return {k: clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [clean(v) for v in obj]
    if isinstance(obj, (np.floating, float)):
        return None if (math.isnan(obj) or math.isinf(obj)) else float(obj)
    if isinstance(obj, np.integer):
        return int(obj)
    return obj


def site_by_id() -> dict[str, SiteAssessment]:
    return {s.site_id: s for s in run_pipeline()}


def descendants(region_id: str) -> set[str]:
    regions = get_repo().regions()
    out, frontier = {region_id}, [region_id]
    while frontier:
        cur = frontier.pop()
        for r in regions:
            if r["parent_id"] == cur and r["region_id"] not in out:
                out.add(r["region_id"])
                frontier.append(r["region_id"])
    return out


def site_summary(s: SiteAssessment) -> dict:
    m, o = s.metrics, s.outlook
    return clean(
        {
            "site_id": s.site_id,
            "asset_id": s.asset_id,
            "asset_name": s.asset_name,
            "asset_type": s.asset_type,
            "region_id": s.region_id,
            "label": f"{s.asset_name.split(' (')[0]} - KM {s.chainage_start_km:.2f}-{s.chainage_end_km:.2f}",
            "chainage_start_km": s.chainage_start_km,
            "chainage_end_km": s.chainage_end_km,
            "lat": s.lat,
            "lon": s.lon,
            "tier": s.tier,
            "state": s.state,
            "rpi": s.rpi,
            "criticality": s.criticality,
            "consequence_note": s.consequence_note,
            "rate_recent_mm_month": m.rate_recent_mm_month,
            "accel_ratio": m.accel_ratio,
            "d60_mm": m.d60_mm,
            "d_window_mm": m.d_window_mm,
            "outlook_status": o.status,
            "eta_low_days": o.eta_low_days,
            "eta_high_days": o.eta_high_days,
            "confidence": s.confidence.score,
            "confidence_label": s.confidence.label,
            "n_points": s.n_points,
            "headline": s.reasons[0] if s.reasons else "",
        }
    )


def site_detail(s: SiteAssessment) -> dict:
    repo = get_repo()
    as_of = as_of_date(repo)
    rain = rain_context(repo, s.region_id, as_of)
    profile = profile_for(s.asset_type)
    from app.services.intel.context import seismic_for  # lazy: intel imports this module

    d = site_summary(s)
    d.update(
        clean(
            {
                "state_reasons": s.reasons,
                "metrics": asdict(s.metrics),
                "outlook": asdict(s.outlook),
                "confidence_detail": {"score": s.confidence.score, "label": s.confidence.label, "drivers": s.confidence.drivers},
                "rpi_breakdown": s.rpi_breakdown,
                "coherence_mean": s.coherence_mean,
                "agreement": s.agreement,
                "thresholds": {
                    "operational_threshold_mm": profile.threshold_mm,
                    "window_days": profile.threshold_window_days,
                    "creep_mm_month": profile.creep_mm_month,
                    "accel_ratio": profile.accel_ratio,
                    "approach_days": profile.approach_days,
                    "mechanism_hint": profile.mechanism_hint,
                },
                "rain": asdict(rain) if rain else None,
                "seismic": seismic_for(s.lat, s.lon, as_of),  # context from public data; never part of the score
                "as_of": str(as_of.date()),
                "data_source": repo.data_source(),
            }
        )
    )
    return d


@lru_cache(maxsize=512)
def series_for(site_id: str):
    s = site_by_id()[site_id]
    repo = get_repo()
    pts = repo.points()
    group = pts[pts["point_id"].isin(s.point_ids)]
    ts = repo.timeseries()
    return _build_series(group, ts)


def site_timeseries(site_id: str) -> dict:
    s = site_by_id()[site_id]
    series = series_for(site_id)
    profile = profile_for(s.asset_type)
    repo = get_repo()
    as_of = as_of_date(repo)

    # per-point envelope (min/max across scatterers) to show spread
    pts = repo.points()
    group = pts[pts["point_id"].isin(s.point_ids)]
    sub = repo.timeseries()
    sub = sub[sub["point_id"].isin(group["point_id"])]
    wide = sub.pivot_table(index="date", columns="point_id", values="disp_mm").sort_index()
    q25, q75 = wide.quantile(0.25, axis=1), wide.quantile(0.75, axis=1)

    rain = repo.rain()
    rain = rain[(rain["region_id"] == s.region_id)]
    horizon = int(min(max((s.outlook.eta_high_days or 120) + 30, 90), 330))
    proj = projection_curves(series, profile, horizon) if s.outlook.status != "not_applicable" else None

    return clean(
        {
            "site_id": site_id,
            "dates": [str(d) for d in series.dates],
            "disp_mm": [round(float(x), 2) for x in series.disp_mm],
            "q25_mm": [round(float(x), 2) for x in q25.reindex(pd.to_datetime(series.dates)).to_numpy()],
            "q75_mm": [round(float(x), 2) for x in q75.reindex(pd.to_datetime(series.dates)).to_numpy()],
            "projection": proj,
            "threshold_mm": profile.threshold_mm,
            "rain": [
                {"date": str(r.date.date()), "precip_mm": r.precip_mm}
                for r in rain.itertuples()
                if r.date >= pd.Timestamp(series.dates[0])
            ],
            "as_of": str(as_of.date()),
            "last_epoch": str(series.dates[-1]),
        }
    )


def region_summary(region_id: str) -> dict:
    ids = descendants(region_id)
    sites = [s for s in run_pipeline() if s.region_id in ids]
    by_tier = {t: 0 for t in ("CRITICAL", "ELEVATED", "WATCH", "STABLE", "WEAK")}
    for s in sites:
        by_tier[s.tier] += 1
    approaching = [s for s in sites if s.outlook.eta_low_days is not None and s.outlook.eta_low_days <= 60 and s.tier in ACT_TIERS]
    accelerating = [s for s in sites if s.state in ("accelerating", "threshold_approach")]
    act = sorted([s for s in sites if s.tier in ACT_TIERS], key=lambda s: -s.rpi)
    repo = get_repo()
    region = next((r for r in repo.regions() if r["region_id"] == region_id), None)
    return clean(
        {
            "region": region,
            "total_sites": len(sites),
            "by_tier": by_tier,
            "accelerating_sites": len(accelerating),
            "approaching_threshold_60d": len(approaching),
            "data_degraded_sites": by_tier["WEAK"],
            "act_list": [site_summary(s) for s in act],
            "as_of": str(as_of_date(repo).date()),
            "data_source": repo.data_source(),
        }
    )


@lru_cache(maxsize=1)
def point_index() -> pd.DataFrame:
    """Every scatterer with its latest displacement and the site/tier it belongs to (viewport queries)."""
    repo = get_repo()
    pts = repo.points()
    ts = repo.timeseries()
    if ts.empty:
        return pts.assign(last_disp_mm=np.nan, site_id=None, tier="UNMONITORED")
    last = ts[ts["date"] == ts["date"].max()].set_index("point_id")["disp_mm"]
    pts = pts.assign(last_disp_mm=pts["point_id"].map(last))
    site_of = {pid: s for s in run_pipeline() for pid in s.point_ids}
    pts["site_id"] = pts["point_id"].map(lambda p: site_of[p].site_id if p in site_of else None)
    pts["tier"] = pts["point_id"].map(lambda p: site_of[p].tier if p in site_of else "UNMONITORED")
    return pts


def tier_sort_key(s: SiteAssessment):
    return (-TIER_RANK[s.tier], -s.rpi)
