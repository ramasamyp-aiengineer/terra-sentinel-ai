"""Intelligence API: alerts, early warning, trends, assets, portfolio, brief, search, methodology, work orders."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.deps import require_role
from app.services.agent import service as agent_service
from app.services.auth.service import Principal
from app.services.data.repo import get_repo
from app.services.detection import views
from app.services.detection.pipeline import run_pipeline
from app.services.intel import alerts, boards, early_warning, snapshots, trends
from app.services.intel.methodology import methodology

router = APIRouter(prefix="/api", tags=["intelligence"])


def _region_ids(region: str | None) -> set[str] | None:
    if not region:
        return None
    if not any(r["region_id"] == region for r in get_repo().regions()):
        raise HTTPException(404, "Unknown region")
    return views.descendants(region)


# ---- alerts ---------------------------------------------------------------------


@router.get("/alerts")
def list_alerts(
    status: str | None = Query(None, pattern="^(open|acknowledged|assigned|escalated|resolved)$"),
    severity: str | None = Query(None, pattern="^(critical|high|medium|info)$"),
    region: str | None = None,
):
    ids = _region_ids(region)
    items = alerts.list_alerts(status=status, severity=severity, region_ids=ids)
    return {"count": len(items), "summary": alerts.counts(ids), "alerts": views.clean(items)}


class AlertAction(BaseModel):
    alert_id: str = Field(max_length=200)
    action: Literal["acknowledge", "assign", "escalate", "resolve", "reopen"]
    actor: str = Field("operator", max_length=60)
    note: str = Field("", max_length=500)
    assignee: str | None = Field(None, max_length=60)


@router.post("/alerts/action")
def alert_action(body: AlertAction, who: Principal = Depends(require_role("analyst"))):
    # The actor is the signed-in user, never a name the client chose: the history must be trustworthy.
    try:
        alerts.record_action(body.alert_id, body.action, who.username, body.note, body.assignee)
    except KeyError:
        raise HTTPException(404, "Unknown alert")
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    updated = next((a for a in alerts.list_alerts() if a["alert_id"] == body.alert_id), None)
    return views.clean(updated)


# ---- early warning / trends -------------------------------------------------------


@router.get("/early-warning")
def early_warning_board(region: str | None = None, asset_type: str | None = None):
    _region_ids(region)
    return early_warning.board(region, asset_type)


@router.get("/early-warning/scenario")
def early_warning_scenario(site_id: str, rate_change_pct: float = Query(0, ge=-90, le=300)):
    try:
        return views.clean(early_warning.scenario(site_id, rate_change_pct))
    except KeyError:
        raise HTTPException(404, "Unknown site")


@router.get("/trends/portfolio")
def trends_portfolio(region: str | None = None):
    _region_ids(region)
    return trends.portfolio(region)


@router.get("/trends/movers")
def trends_movers(region: str | None = None, limit: int = Query(8, ge=1, le=25)):
    _region_ids(region)
    return trends.movers(region, limit)


@router.get("/sites/{site_id}/history")
def site_history(site_id: str):
    if site_id not in views.site_by_id():
        raise HTTPException(404, "Unknown site")
    return views.clean(trends.site(site_id))


# ---- assets / portfolio / brief / search -----------------------------------------


@router.get("/assets")
def assets_board(region: str | None = None):
    _region_ids(region)
    return boards.assets(region)


@router.get("/assets/{asset_id}")
def asset_detail(asset_id: str):
    try:
        return boards.asset_detail(asset_id)
    except KeyError:
        raise HTTPException(404, "Unknown asset")


@router.get("/portfolio")
def portfolio(region: str | None = None):
    _region_ids(region)
    return boards.portfolio(region)


@router.get("/brief")
def brief(region: str | None = None):
    _region_ids(region)
    return boards.brief(region)


@router.get("/search")
def search(q: str = Query("", max_length=80), limit: int = Query(12, ge=1, le=30)):
    return boards.search(q, limit)


@router.get("/methodology")
def get_methodology():
    return methodology()


# ---- work orders --------------------------------------------------------------------


@router.get("/workorders")
def work_order_queue(region: str | None = None):
    """Sites that warrant an inspection, with whether a work order has already been drafted."""
    ids = _region_ids(region)
    done = agent_service.cached_orders()
    items = []
    for s in run_pipeline():
        if s.tier not in ("CRITICAL", "ELEVATED") or (ids and s.region_id not in ids):
            continue
        d = views.site_summary(s)
        d["work_order"] = done.get(s.site_id)
        items.append(d)
    items.sort(key=lambda x: -x["rpi"])
    return {"count": len(items), "drafted": sum(1 for i in items if i["work_order"]), "sites": items, "agent": agent_service.status()}


@router.get("/system/warm")
def warm():
    """Pre-compute historical passes (cheap to call; used after data changes)."""
    snapshots.warm_in_background()
    return {"status": "warming", "passes": len(snapshots.passes())}
