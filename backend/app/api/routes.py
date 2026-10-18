"""HTTP API. Thin layer: all logic lives in services/."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import require_role
from app.core.ratelimit import limit
from app.services.data.repo import get_repo
from app.services.detection import views
from app.services.detection.pipeline import as_of_date, run_pipeline
from app.services.detection.tiering import TIER_RANK

router = APIRouter(prefix="/api")


def _region_ids(region: str | None) -> set[str] | None:
    """Resolve a region filter; unknown ids are 404 (not an empty list)."""
    if not region:
        return None
    if not any(r["region_id"] == region for r in get_repo().regions()):
        raise HTTPException(404, "Unknown region")
    return views.descendants(region)


@router.get("/meta")
def meta():
    repo = get_repo()
    sites = run_pipeline()
    return {
        "product": "TerraSentinel",
        "data_source": repo.data_source(),
        "is_demo": repo.data_source() == "DEMO-SYNTHETIC",
        "backend": repo.backend,
        "as_of": str(as_of_date(repo).date()),
        "sites": len(sites),
        "disclaimer": (
            "Decision-support for qualified engineers. Early-warning outlooks assume the current "
            "motion regime continues and are not predictions of failure."
        ),
    }


@router.get("/regions")
def regions():
    return get_repo().regions()


@router.get("/regions/{region_id}/summary")
def region_summary(region_id: str):
    if not any(r["region_id"] == region_id for r in get_repo().regions()):
        raise HTTPException(404, "Unknown region")
    return views.region_summary(region_id)


@router.get("/corridors")
def corridors(region: str | None = None):
    """Asset lines enriched with the worst tier among their sites (low-zoom map layer)."""
    repo = get_repo()
    ids = _region_ids(region)
    sites = run_pipeline()
    gj = repo.assets_geojson()
    feats = []
    for f in gj["features"]:
        p = f["properties"]
        if ids and p["region_id"] not in ids:
            continue
        mine = [s for s in sites if s.asset_id == p["asset_id"]]
        worst = max(mine, key=lambda s: (TIER_RANK[s.tier], s.rpi), default=None)
        tiers = {}
        for s in mine:
            tiers[s.tier] = tiers.get(s.tier, 0) + 1
        feats.append(
            {
                "type": "Feature",
                "geometry": f["geometry"],
                "properties": {
                    **p,
                    "worst_tier": worst.tier if worst else "STABLE",
                    "worst_rpi": worst.rpi if worst else 0,
                    "site_count": len(mine),
                    "tier_counts": tiers,
                },
            }
        )
    return {"type": "FeatureCollection", "features": feats}


@router.get("/sites")
def sites(
    region: str | None = None,
    tier: str | None = Query(None, description="comma-separated tiers"),
    asset_id: str | None = None,
    bbox: str | None = Query(None, description="min_lon,min_lat,max_lon,max_lat"),
    include_stable: bool = False,
    limit: int = Query(300, ge=1, le=1000),
):
    items = run_pipeline()
    ids = _region_ids(region)
    if ids is not None:
        items = [s for s in items if s.region_id in ids]
    if asset_id:
        items = [s for s in items if s.asset_id == asset_id]
    if tier:
        wanted = {t.strip().upper() for t in tier.split(",")}
        items = [s for s in items if s.tier in wanted]
    elif not include_stable:
        items = [s for s in items if s.tier != "STABLE"]
    if bbox:
        try:
            x0, y0, x1, y1 = (float(v) for v in bbox.split(","))
        except ValueError:
            raise HTTPException(400, "bbox must be min_lon,min_lat,max_lon,max_lat")
        items = [s for s in items if x0 <= s.lon <= x1 and y0 <= s.lat <= y1]
    items = sorted(items, key=lambda s: (-s.rpi, s.site_id))[:limit]
    return {"count": len(items), "sites": [views.site_summary(s) for s in items]}


@router.get("/sites/{site_id}")
def site(site_id: str):
    s = views.site_by_id().get(site_id)
    if not s:
        raise HTTPException(404, "Unknown site")
    return views.site_detail(s)


@router.get("/sites/{site_id}/timeseries")
def site_timeseries(site_id: str):
    if site_id not in views.site_by_id():
        raise HTTPException(404, "Unknown site")
    return views.site_timeseries(site_id)


@router.get("/agent/status")
def agent_status():
    from app.services.agent import service

    return service.status()


@router.post("/sites/{site_id}/workorder", dependencies=[Depends(limit(12, 60)), Depends(require_role("analyst"))])
def work_order(site_id: str, mode: str = Query("auto", pattern="^(auto|template)$"), refresh: bool = False):
    """Generate the inspection work order (Gemini function-calling, validated; template fallback)."""
    from app.services.agent import service

    try:
        return service.generate_work_order(site_id, mode=mode, refresh=refresh)  # type: ignore[arg-type]
    except KeyError:
        raise HTTPException(404, "Unknown site")


@router.get("/context/events")
def context_events(
    bbox: str = Query(..., description="min_lon,min_lat,max_lon,max_lat"),
    min_mag: float = Query(2.5, ge=0, le=9),
    limit: int = Query(1500, ge=1, le=5000),
):
    """Earthquakes from the stored public datasets for the map layer (context only)."""
    from app.services.intel import context

    try:
        x0, y0, x1, y1 = (float(v) for v in bbox.split(","))
    except ValueError:
        raise HTTPException(400, "bbox must be min_lon,min_lat,max_lon,max_lat")
    return context.events_in_bbox(x0, y0, x1, y1, min_mag, limit)


@router.get("/points")
def points(
    bbox: str = Query(..., description="min_lon,min_lat,max_lon,max_lat"),
    limit: int = Query(4000, ge=1, le=8000),
):
    """Raw scatterers for the current viewport (site-level zoom only; never the full dataset)."""
    try:
        x0, y0, x1, y1 = (float(v) for v in bbox.split(","))
    except ValueError:
        raise HTTPException(400, "bbox must be min_lon,min_lat,max_lon,max_lat")
    df = views.point_index()
    sel = df[(df["lon"] >= x0) & (df["lon"] <= x1) & (df["lat"] >= y0) & (df["lat"] <= y1)]
    truncated = len(sel) > limit
    sel = sel.sort_values("velocity_mm_yr").head(limit)
    return views.clean(
        {
            "count": len(sel),
            "truncated": truncated,
            "points": sel[
                ["point_id", "lat", "lon", "velocity_mm_yr", "coherence", "last_disp_mm", "site_id", "tier"]
            ].to_dict("records"),
        }
    )
