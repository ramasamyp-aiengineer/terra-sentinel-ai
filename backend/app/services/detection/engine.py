"""Site detection engine.

points + time series + asset geometry  ->  ranked site assessments.

A *site* is a chainage bin along a linear asset (e.g. KM 74.0-74.25 of a highway).
Scatterers inside the asset buffer are grouped by chainage so one slope = one
incident, not 200 red dots.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, replace

import numpy as np
import pandas as pd
from shapely.geometry import LineString, Point

from app.core.config import AssetProfile, profile_for
from app.services.detection.forecast import Outlook, compute_outlook
from app.services.detection.metrics import MotionMetrics, SiteSeries, compute_metrics
from app.services.detection.tiering import (
    Confidence,
    assign_tier,
    classify_state,
    compute_confidence,
    compute_rpi,
)

CHAINAGE_BIN_M = 250.0
MIN_POINTS_PER_SITE = 1


@dataclass
class Asset:
    asset_id: str
    name: str
    asset_type: str
    region_id: str
    criticality: float  # 0..1
    consequence_note: str
    geometry: LineString  # lon/lat
    buffer_m: float | None = None


@dataclass
class SiteAssessment:
    site_id: str
    asset_id: str
    asset_name: str
    asset_type: str
    region_id: str
    chainage_start_km: float
    chainage_end_km: float
    lat: float
    lon: float
    n_points: int
    criticality: float
    consequence_note: str
    state: str
    tier: str
    rpi: float
    rpi_breakdown: dict
    reasons: list[str]
    metrics: MotionMetrics
    outlook: Outlook
    confidence: Confidence
    coherence_mean: float
    agreement: float
    point_ids: list[str] = field(default_factory=list)


# ---- geometry helpers -------------------------------------------------------


def _meters_per_deg(lat: float) -> tuple[float, float]:
    return 111_320.0 * math.cos(math.radians(lat)), 110_540.0


def _project_line(line: LineString) -> tuple[LineString, float, float]:
    lat0 = line.centroid.y
    mx, my = _meters_per_deg(lat0)
    lon0 = line.coords[0][0]
    lat_ref = line.coords[0][1]
    xy = [((x - lon0) * mx, (y - lat_ref) * my) for x, y in line.coords]
    return LineString(xy), lon0, lat_ref


def assign_chainage(points: pd.DataFrame, asset: Asset, profile: AssetProfile) -> pd.DataFrame:
    """Add chainage_m and offset_m for each point; keep only points inside the buffer."""
    line_m, lon0, lat_ref = _project_line(asset.geometry)
    mx, my = _meters_per_deg(asset.geometry.centroid.y)
    buffer_m = asset.buffer_m or profile.buffer_m

    xs = (points["lon"].to_numpy() - lon0) * mx
    ys = (points["lat"].to_numpy() - lat_ref) * my
    chain, off = [], []
    for x, y in zip(xs, ys):
        p = Point(x, y)
        chain.append(line_m.project(p))
        off.append(line_m.distance(p))
    out = points.copy()
    out["chainage_m"] = chain
    out["offset_m"] = off
    return out[out["offset_m"] <= buffer_m].reset_index(drop=True)


# ---- site building ----------------------------------------------------------


def _build_series(group: pd.DataFrame, ts: pd.DataFrame) -> SiteSeries | None:
    sub = ts[ts["point_id"].isin(group["point_id"])]
    if sub.empty:
        return None
    wide = sub.pivot_table(index="date", columns="point_id", values="disp_mm", aggfunc="mean").sort_index()
    wide = wide.interpolate(limit_direction="both")
    site = wide.median(axis=1)
    dates = site.index.to_numpy().astype("datetime64[D]")
    disp = site.to_numpy(dtype=float)

    # Agreement: share of points whose trailing-window net motion matches the site's sign
    cut = dates[-1] - np.timedelta64(180, "D")
    recent = wide[wide.index >= pd.Timestamp(cut)]
    if len(recent) >= 2:
        net = recent.iloc[-1] - recent.iloc[0]
        site_net = site.iloc[-1] - site[site.index >= pd.Timestamp(cut)].iloc[0]
        if abs(site_net) < 0.5:
            agreement = float((net.abs() < 1.5).mean())
        else:
            agreement = float((np.sign(net) == np.sign(site_net)).mean())
    else:
        agreement = 0.0

    return SiteSeries(
        dates=dates,
        disp_mm=disp,
        n_points=int(wide.shape[1]),
        coherence_mean=float(group["coherence"].mean()),
        agreement=agreement,
    )


def assess_asset(
    asset: Asset,
    points: pd.DataFrame,
    ts: pd.DataFrame,
    rain_trigger_for: callable | None = None,
) -> list[SiteAssessment]:
    profile = profile_for(asset.asset_type)
    pts = assign_chainage(points, asset, profile)
    if pts.empty:
        return []
    pts["bin"] = (pts["chainage_m"] // CHAINAGE_BIN_M).astype(int)

    results: list[SiteAssessment] = []
    for b, group in pts.groupby("bin"):
        if len(group) < MIN_POINTS_PER_SITE:
            continue
        series = _build_series(group, ts)
        if series is None or len(series.dates) < 3:
            continue

        metrics = compute_metrics(series, profile.threshold_window_days)
        outlook = compute_outlook(series, metrics, profile)
        conf = compute_confidence(series, metrics)
        lat, lon = float(group["lat"].mean()), float(group["lon"].mean())
        rain = rain_trigger_for(lat, lon) if rain_trigger_for else None
        state, reasons = classify_state(series, metrics, outlook, conf, profile)
        if state == "data_degraded":
            # Never present a forecast built on unusable data.
            outlook = replace(
                outlook,
                status="not_applicable",
                eta_low_days=None,
                eta_high_days=None,
                eta_constant_days=None,
                eta_accelerating_days=None,
            )
        tier = assign_tier(state, asset.criticality, outlook, rain, profile)
        rpi, breakdown = compute_rpi(metrics, outlook, conf, asset.criticality, rain, profile)
        if tier == "WEAK":
            rpi = min(rpi, 15.0)  # weak data never tops the Act List

        start_km = b * CHAINAGE_BIN_M / 1000
        results.append(
            SiteAssessment(
                site_id=f"{asset.asset_id}-{int(b):03d}",
                asset_id=asset.asset_id,
                asset_name=asset.name,
                asset_type=asset.asset_type,
                region_id=asset.region_id,
                chainage_start_km=round(start_km, 2),
                chainage_end_km=round(start_km + CHAINAGE_BIN_M / 1000, 2),
                lat=lat,
                lon=lon,
                n_points=series.n_points,
                criticality=asset.criticality,
                consequence_note=asset.consequence_note,
                state=state,
                tier=tier,
                rpi=rpi,
                rpi_breakdown=breakdown,
                reasons=reasons,
                metrics=metrics,
                outlook=outlook,
                confidence=conf,
                coherence_mean=round(series.coherence_mean, 3),
                agreement=round(series.agreement, 3),
                point_ids=group["point_id"].tolist(),
            )
        )
    return results


def rank_sites(sites: list[SiteAssessment]) -> list[SiteAssessment]:
    return sorted(sites, key=lambda s: (-s.rpi, s.site_id))
