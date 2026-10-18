"""Boards that aggregate sites: assets / corridors, portfolio roll-up, morning brief, search."""
from __future__ import annotations

import pandas as pd

from app.core.config import PROFILES, profile_for
from app.services.data.repo import get_repo
from app.services.detection import views
from app.services.detection.engine import SiteAssessment, _project_line
from app.services.detection.pipeline import as_of_date, rain_context, run_pipeline
from app.services.detection.tiering import TIER_RANK
from app.services.intel import alerts, snapshots

TIERS = ("CRITICAL", "ELEVATED", "WATCH", "STABLE", "WEAK")


def _tier_counts(sites: list[SiteAssessment]) -> dict:
    return {t: sum(1 for s in sites if s.tier == t) for t in TIERS}


def _worst(sites: list[SiteAssessment]) -> SiteAssessment | None:
    return max(sites, key=lambda s: (TIER_RANK[s.tier], s.rpi), default=None)


def _earliest_eta(sites: list[SiteAssessment]) -> int | None:
    etas = [s.outlook.eta_low_days for s in sites if s.outlook.eta_low_days is not None and s.tier in ("ELEVATED", "CRITICAL")]
    return min(etas) if etas else None


# ---------------------------------------------------------------------------- assets


def assets(region: str | None = None) -> dict:
    repo = get_repo()
    ids = views.descendants(region) if region else None
    sites = run_pipeline()
    names = {r["region_id"]: r["name"] for r in repo.regions()}
    out = []
    for a in repo.assets():
        if ids and a.region_id not in ids:
            continue
        mine = [s for s in sites if s.asset_id == a.asset_id]
        line_m, *_ = _project_line(a.geometry)
        worst = _worst(mine)
        moving = [s for s in mine if s.tier in ("WATCH", "ELEVATED", "CRITICAL")]
        out.append(
            views.clean(
                {
                    "asset_id": a.asset_id,
                    "name": a.name,
                    "asset_type": a.asset_type,
                    "type_label": profile_for(a.asset_type).label,
                    "region_id": a.region_id,
                    "region_name": names.get(a.region_id, a.region_id),
                    "criticality": a.criticality,
                    "consequence_note": a.consequence_note,
                    "length_km": round(line_m.length / 1000, 1),
                    "sites": len(mine),
                    "points": sum(s.n_points for s in mine),
                    "tier_counts": _tier_counts(mine),
                    "worst_tier": worst.tier if worst else "STABLE",
                    "max_rpi": worst.rpi if worst else 0,
                    "earliest_eta_days": _earliest_eta(mine),
                    "moving_sites": len(moving),
                    "mean_moving_rate_mm_month": round(sum(abs(s.metrics.rate_recent_mm_month) for s in moving) / len(moving), 2) if moving else 0.0,
                    "center": [a.geometry.centroid.x, a.geometry.centroid.y],
                    "bbox": list(a.geometry.bounds),
                }
            )
        )
    out.sort(key=lambda r: (-TIER_RANK[r["worst_tier"]], -r["max_rpi"]))
    return {"count": len(out), "assets": out}


def asset_detail(asset_id: str) -> dict:
    board = {a["asset_id"]: a for a in assets()["assets"]}
    if asset_id not in board:
        raise KeyError(asset_id)
    mine = sorted([s for s in run_pipeline() if s.asset_id == asset_id], key=lambda s: s.chainage_start_km)
    strip = [
        {
            "site_id": s.site_id,
            "km_start": s.chainage_start_km,
            "km_end": s.chainage_end_km,
            "tier": s.tier,
            "rpi": s.rpi,
            "state": s.state,
            "rate_mm_month": round(s.metrics.rate_recent_mm_month, 2),
            "n_points": s.n_points,
        }
        for s in mine
    ]
    top = sorted(mine, key=lambda s: -s.rpi)[:6]
    return {
        **board[asset_id],
        "strip": strip,
        "top_sites": [views.site_summary(s) for s in top if s.tier not in ("STABLE",)],
        "profile": {
            "buffer_m": profile_for(board[asset_id]["asset_type"]).buffer_m,
            "threshold_mm": profile_for(board[asset_id]["asset_type"]).threshold_mm,
            "window_days": profile_for(board[asset_id]["asset_type"]).threshold_window_days,
            "mechanism_hint": profile_for(board[asset_id]["asset_type"]).mechanism_hint,
        },
    }


# ------------------------------------------------------------------------- portfolio


def portfolio(region: str | None = None) -> dict:
    repo = get_repo()
    root = region
    ids = views.descendants(region) if region else None
    sites = [s for s in run_pipeline() if ids is None or s.region_id in ids]
    regions = repo.regions()
    names = {r["region_id"]: r["name"] for r in regions}

    # roll up by the direct children of the selected region (or top-level regions)
    parents = [r for r in regions if r["parent_id"] == root] if root else [r for r in regions if not r["parent_id"]]
    if root and not parents:
        parents = [r for r in regions if r["region_id"] == root]
    # a lone parent (e.g. a single country) tells the reader nothing: drill to the level where it splits
    while len(parents) == 1:
        kids = [r for r in regions if r["parent_id"] == parents[0]["region_id"]]
        if not kids:
            break
        parents = kids
    by_region = []
    for r in parents:
        rids = views.descendants(r["region_id"])
        rs = [s for s in sites if s.region_id in rids]
        worst = _worst(rs)
        act = [s for s in rs if s.tier in ("CRITICAL", "ELEVATED")]
        by_region.append(
            {
                "region_id": r["region_id"],
                "name": r["name"],
                "level": r["level"],
                "sites": len(rs),
                "tier_counts": _tier_counts(rs),
                "worst_tier": worst.tier if worst else "STABLE",
                "max_rpi": worst.rpi if worst else 0,
                "act_sites": len(act),
                "exposure": round(sum(s.criticality for s in act), 2),
                "earliest_eta_days": _earliest_eta(rs),
            }
        )
    by_region.sort(key=lambda r: (-TIER_RANK[r["worst_tier"]], -r["max_rpi"]))

    by_type = []
    for t, p in PROFILES.items():
        ts_ = [s for s in sites if s.asset_type == t]
        if ts_:
            by_type.append({"asset_type": t, "label": p.label, "sites": len(ts_), "tier_counts": _tier_counts(ts_), "act_sites": sum(1 for s in ts_ if s.tier in ("CRITICAL", "ELEVATED"))})

    pts = repo.points()
    as_of = as_of_date(repo)
    last_epoch = repo.counts()["date_max"]
    age = (as_of - pd.Timestamp(last_epoch)).days if last_epoch else None
    ids_set = ids
    rc = {r["region_id"]: rain_context(repo, r["region_id"], as_of) for r in regions}
    rain = [
        {"region_id": rid, "name": names[rid], "rain_14d_mm": c.rain_14d_mm, "peak_day_mm": c.peak_day_mm, "trigger_score": c.trigger_score}
        for rid, c in rc.items()
        if c and (ids_set is None or rid in ids_set) and c.rain_14d_mm > 0
    ]
    rain.sort(key=lambda r: -r["trigger_score"])
    act = sorted([s for s in sites if s.tier in ("CRITICAL", "ELEVATED")], key=lambda s: -s.rpi)
    return views.clean(
        {
            "region": root,
            "as_of": str(as_of.date()),
            "data_source": repo.data_source(),
            "totals": {
                "sites": len(sites),
                "assets": len({s.asset_id for s in sites}),
                "points": int(len(pts)),
                "tier_counts": _tier_counts(sites),
                "act_sites": len(act),
                "exposure": round(sum(s.criticality for s in act), 2),
                "earliest_eta_days": _earliest_eta(sites),
            },
            "by_region": by_region,
            "by_asset_type": by_type,
            "rain": rain[:8],
            "top_sites": [views.site_summary(s) for s in act[:10]],
            "data_health": {
                "last_epoch": last_epoch,
                "days_since_last_epoch": age,
                "epochs": repo.counts()["epochs"],
                "weak_sites": sum(1 for s in sites if s.tier == "WEAK"),
                "mean_confidence": round(sum(s.confidence.score for s in sites) / len(sites), 2) if sites else None,
                "fresh": age is not None and age <= 14,
            },
        }
    )


# ----------------------------------------------------------------------------- brief


def brief(region: str | None = None) -> dict:
    """Deterministic morning brief. Written from computed numbers only; labelled as such in the UI."""
    repo = get_repo()
    ids = views.descendants(region) if region else None
    sites = [s for s in run_pipeline() if ids is None or s.region_id in ids]
    as_of = as_of_date(repo)
    counts = _tier_counts(sites)
    act = sorted([s for s in sites if s.tier in ("CRITICAL", "ELEVATED")], key=lambda s: -s.rpi)
    items = alerts.list_alerts(region_ids=ids, include_info=False)
    new = [a for a in items if a["pass_index"] == 0]
    escalations = [a for a in new if a["kind"].startswith("ESCALATED") or a["kind"] == "THRESHOLD_EXCEEDED"]
    soon = [s for s in act if s.outlook.eta_low_days is not None and s.outlook.eta_low_days <= 60]
    region_name = next((r["name"] for r in repo.regions() if r["region_id"] == region), "All regions") if region else "All regions"

    if act:
        headline = f"{len(act)} site{'s' if len(act) != 1 else ''} need attention: {counts['CRITICAL']} critical, {counts['ELEVATED']} elevated."
    else:
        headline = "No site needs action today. Ground motion is within normal bounds."
    sections = []
    changed = []
    if new:
        changed.append(f"{len(new)} new alert{'s' if len(new) != 1 else ''} since the previous satellite pass" + (f", {len(escalations)} of them escalations." if escalations else "."))
    else:
        changed.append("No new alerts since the previous satellite pass.")
    for a in new[:4]:
        changed.append(f"{a['title']} - {a['detail']}")
    sections.append({"title": "What changed", "bullets": changed})

    if act:
        bullets = []
        for s in act[:5]:
            eta = f"; {s.outlook.threshold_mm:.0f} mm in {s.outlook.eta_low_days}-{s.outlook.eta_high_days} days if the regime continues" if s.outlook.eta_low_days is not None else ""
            bullets.append(f"{snapshots.label(s)} ({s.tier}, RPI {s.rpi:.0f}): {abs(s.metrics.rate_recent_mm_month):.1f} mm/month{eta}.")
        sections.append({"title": "Act first", "bullets": bullets})
    if soon:
        sections.append({"title": "Closest to threshold", "bullets": [f"{len(soon)} elevated/critical site(s) have an outlook of 60 days or less; earliest {min(s.outlook.eta_low_days for s in soon)} days."]})

    rain_lines = []
    for r in repo.regions():
        if ids is not None and r["region_id"] not in ids:
            continue
        c = rain_context(repo, r["region_id"], as_of)
        if c and c.trigger_score >= 40:
            rain_lines.append(f"{r['name']}: {c.rain_14d_mm:.0f} mm in 14 days (peak {c.peak_day_mm:.0f} mm/day).")
    if rain_lines:
        sections.append({"title": "Rainfall context", "bullets": rain_lines[:4] + ["Rain amplifies risk on moving ground; it does not raise a stable site."]})

    caveats = []
    last_epoch = repo.counts()["date_max"]
    if last_epoch:
        age = (as_of - pd.Timestamp(last_epoch)).days
        caveats.append(f"Latest satellite epoch: {last_epoch} ({age} days before this assessment).")
    weak = counts["WEAK"]
    if weak:
        caveats.append(f"{weak} site(s) have data too weak to assess and are excluded from rankings.")
    if repo.data_source() != "observed":
        caveats.append(f"Data source: {repo.data_source()}.")
    sections.append({"title": "Caveats", "bullets": caveats})

    return views.clean(
        {
            "as_of": str(as_of.date()),
            "region": region,
            "region_name": region_name,
            "headline": headline,
            "counts": counts,
            "sections": sections,
            "top_actions": [views.site_summary(s) for s in act[:5]],
            "generated_by": "deterministic",
            "note": "Generated directly from computed values. Gemini work orders add grounded engineering context per site.",
        }
    )


# ---------------------------------------------------------------------------- search


def search(q: str, limit: int = 12) -> dict:
    q = (q or "").strip().lower()
    if len(q) < 2:
        return {"query": q, "results": []}
    repo = get_repo()
    results = []
    for r in repo.regions():
        if q in r["name"].lower() or q in r["region_id"].lower():
            results.append({"type": "region", "id": r["region_id"], "title": r["name"], "subtitle": f"Region ({r['level']})", "lon": r["center"][0], "lat": r["center"][1], "zoom": r["zoom"]})
    for a in repo.assets():
        if q in a.name.lower() or q in a.asset_id.lower():
            c = a.geometry.centroid
            results.append({"type": "asset", "id": a.asset_id, "title": a.name, "subtitle": profile_for(a.asset_type).label, "lon": c.x, "lat": c.y, "zoom": 10})
    for s in run_pipeline():
        label = snapshots.label(s)
        if q in s.site_id.lower() or q in label.lower():
            results.append({"type": "site", "id": s.site_id, "title": label, "subtitle": f"{s.tier} - RPI {s.rpi:.0f}", "lon": s.lon, "lat": s.lat, "zoom": 14})
        if len(results) >= limit * 3:
            break
    order = {"region": 0, "asset": 1, "site": 2}
    results.sort(key=lambda r: (order[r["type"]], r["title"]))
    return {"query": q, "results": results[:limit]}
