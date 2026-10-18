"""Trends & history: how the portfolio and individual sites evolved across past satellite passes."""
from __future__ import annotations

from app.services.detection import views
from app.services.detection.tiering import TIER_RANK
from app.services.intel import snapshots

TIERS = ("CRITICAL", "ELEVATED", "WATCH", "STABLE", "WEAK")


def _in_region(row: dict, ids: set[str] | None) -> bool:
    return ids is None or row["region_id"] in ids


def portfolio(region: str | None = None) -> dict:
    ids = views.descendants(region) if region else None
    series = []
    for p in reversed(snapshots.passes()):  # oldest -> newest for charting
        rows = [r for r in snapshots.table_for(p).values() if _in_region(r, ids)]
        counts = {t: sum(1 for r in rows if r["tier"] == t) for t in TIERS}
        act = [r for r in rows if r["tier"] in ("CRITICAL", "ELEVATED")]
        series.append(
            {
                "as_of": p.as_of,
                "pass_index": p.index,
                "counts": counts,
                "act_sites": len(act),
                "max_rpi": max((r["rpi"] for r in rows), default=0.0),
                "mean_act_rpi": round(sum(r["rpi"] for r in act) / len(act), 1) if act else 0.0,
                "accelerating": sum(1 for r in rows if r["state"] in ("accelerating", "threshold_approach")),
                "approaching_60d": sum(1 for r in act if r["eta_low_days"] is not None and r["eta_low_days"] <= 60),
            }
        )
    return {"region": region, "series": series, "passes": len(series)}


def site(site_id: str) -> dict:
    out = []
    for p in reversed(snapshots.passes()):
        r = snapshots.table_for(p).get(site_id)
        if r is None:
            continue
        out.append(
            {
                "as_of": p.as_of,
                "tier": r["tier"],
                "rpi": r["rpi"],
                "state": r["state"],
                "rate_mm_month": r["rate_mm_month"],
                "accel_ratio": r["accel_ratio"],
                "eta_low_days": r["eta_low_days"],
                "eta_high_days": r["eta_high_days"],
                "progress_mm": r["progress_mm"],
            }
        )
    return {"site_id": site_id, "history": out}


def movers(region: str | None = None, limit: int = 8) -> dict:
    """Largest RPI change between the oldest available pass and now."""
    ps = snapshots.passes()
    if len(ps) < 2:
        return {"since": None, "risers": [], "fallers": []}
    ids = views.descendants(region) if region else None
    new_t, old_t = snapshots.table_for(ps[0]), snapshots.table_for(ps[-1])
    rows = []
    for sid, n in new_t.items():
        o = old_t.get(sid)
        if o is None or not _in_region(n, ids):
            continue
        rows.append(
            {
                "site_id": sid,
                "label": n["label"],
                "asset_name": n["asset_name"],
                "tier": n["tier"],
                "previous_tier": o["tier"],
                "rpi": n["rpi"],
                "previous_rpi": o["rpi"],
                "delta_rpi": round(n["rpi"] - o["rpi"], 1),
                "tier_change": TIER_RANK[n["tier"]] - TIER_RANK[o["tier"]],
            }
        )
    risers = sorted([r for r in rows if r["delta_rpi"] > 0], key=lambda r: -r["delta_rpi"])[:limit]
    fallers = sorted([r for r in rows if r["delta_rpi"] < 0], key=lambda r: r["delta_rpi"])[:limit]
    return {"since": ps[-1].as_of, "risers": risers, "fallers": fallers}
