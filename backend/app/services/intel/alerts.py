"""Alerts: what *changed* between consecutive satellite passes, plus an action log.

An alert is a diff, not a state. "Highway KM 2.5 is CRITICAL" is on the Act List; "it became CRITICAL
since the previous pass" is an alert. Every number in an alert comes from the two pass rows it compares.
Acknowledge / assign / escalate / resolve are persisted (state store) so the queue survives restarts.
"""
from __future__ import annotations

from functools import lru_cache

import pandas as pd

from app.core.config import profile_for
from app.services.data.repo import get_repo
from app.services.data.state import get_state, now_iso
from app.services.detection.pipeline import rain_context
from app.services.detection.tiering import TIER_RANK
from app.services.intel import snapshots

LOOKBACK_PASSES = 6  # how many past pass-to-pass diffs to turn into alerts


def _lookback() -> int:
    try:
        from app.core.config import settings

        # BigQuery historical passes are expensive; Command Center only needs the latest diffs.
        if settings.data_backend.lower() == "bigquery":
            return 2
    except Exception:  # noqa: BLE001
        pass
    return LOOKBACK_PASSES
SEVERITY_RANK = {"critical": 3, "high": 2, "medium": 1, "info": 0}
ACTIONS = {"acknowledge": "acknowledged", "assign": "assigned", "escalate": "escalated", "resolve": "resolved", "reopen": "open"}
STATUSES = {"open", "acknowledged", "assigned", "escalated", "resolved"}

# priority when one site triggers several rules in the same pass (first wins as the headline)
KIND_PRIORITY = ["THRESHOLD_EXCEEDED", "ESCALATED_CRITICAL", "THRESHOLD_APPROACH", "ACCELERATION_ONSET", "ESCALATED_ELEVATED", "DATA_DEGRADED", "RECOVERY"]
KIND_LABEL = {
    "THRESHOLD_EXCEEDED": "Threshold exceeded",
    "ESCALATED_CRITICAL": "Escalated to CRITICAL",
    "THRESHOLD_APPROACH": "Approaching threshold",
    "ACCELERATION_ONSET": "Acceleration onset",
    "ESCALATED_ELEVATED": "Escalated to ELEVATED",
    "DATA_DEGRADED": "Data quality degraded",
    "RECOVERY": "De-escalated",
    "RAIN_TRIGGER": "Heavy rainfall over active sites",
}
SEVERITY_OF = {
    "THRESHOLD_EXCEEDED": "critical",
    "ESCALATED_CRITICAL": "critical",
    "THRESHOLD_APPROACH": "high",
    "ACCELERATION_ONSET": "high",
    "ESCALATED_ELEVATED": "high",
    "DATA_DEGRADED": "medium",
    "RAIN_TRIGGER": "medium",
    "RECOVERY": "info",
}


def _eta(r: dict) -> str:
    if r["eta_low_days"] is None:
        return ""
    return f" Outlook: {r['threshold_mm']:.0f} mm in {r['eta_low_days']}-{r['eta_high_days']} days if the current regime continues."


def _detail(kind: str, new: dict, old: dict) -> str:
    speed = f"Speed {abs(new['rate_mm_month']):.1f} mm/month (was {abs(old['rate_mm_month']):.1f})."
    if kind == "THRESHOLD_EXCEEDED":
        return f"Accumulated {new['progress_mm']:.1f} mm against the {new['threshold_mm']:.0f} mm operational threshold. {speed}"
    if kind in ("ESCALATED_CRITICAL", "ESCALATED_ELEVATED"):
        return f"{old['tier']} to {new['tier']}; RPI {old['rpi']:.0f} to {new['rpi']:.0f}. {speed}{_eta(new)}"
    if kind == "THRESHOLD_APPROACH":
        return f"{speed}{_eta(new)} Progress {new['progress_mm']:.1f} of {new['threshold_mm']:.0f} mm."
    if kind == "ACCELERATION_ONSET":
        return f"Now {new['accel_ratio']:.1f}x its baseline speed. {speed}"
    if kind == "DATA_DEGRADED":
        return "Confidence or coherence fell below the usable level; the outlook is withheld until data recover."
    return f"{old['tier']} to {new['tier']}; RPI {old['rpi']:.0f} to {new['rpi']:.0f}."


def _site_alert(p_new: snapshots.Pass, new: dict, old: dict) -> dict | None:
    kinds: list[str] = []
    profile = profile_for(new["asset_type"])
    up = TIER_RANK[new["tier"]] > TIER_RANK[old["tier"]]
    if new["outlook_status"] == "threshold_exceeded" and old["outlook_status"] != "threshold_exceeded":
        kinds.append("THRESHOLD_EXCEEDED")
    if up and new["tier"] == "CRITICAL":
        kinds.append("ESCALATED_CRITICAL")
    near_now = new["outlook_status"] == "approaching" and new["eta_low_days"] is not None and new["eta_low_days"] <= profile.approach_days
    near_before = old["outlook_status"] == "approaching" and old["eta_low_days"] is not None and old["eta_low_days"] <= profile.approach_days
    if near_now and not near_before and new["tier"] in ("ELEVATED", "CRITICAL"):
        kinds.append("THRESHOLD_APPROACH")
    if new["state"] in ("accelerating", "threshold_approach") and old["state"] not in ("accelerating", "threshold_approach"):
        kinds.append("ACCELERATION_ONSET")
    if up and new["tier"] == "ELEVATED":
        kinds.append("ESCALATED_ELEVATED")
    if new["tier"] == "WEAK" and old["tier"] != "WEAK":
        kinds.append("DATA_DEGRADED")
    if TIER_RANK[new["tier"]] < TIER_RANK[old["tier"]] and old["tier"] in ("ELEVATED", "CRITICAL") and new["tier"] != "WEAK":
        kinds.append("RECOVERY")
    if not kinds:
        return None
    primary = min(kinds, key=KIND_PRIORITY.index)
    return {
        "alert_id": f"{p_new.as_of}|{new['site_id']}|{primary}",
        "as_of": p_new.as_of,
        "pass_index": p_new.index,
        "kind": primary,
        "also": [k for k in kinds if k != primary],
        "severity": SEVERITY_OF[primary],
        "title": f"{KIND_LABEL[primary]}: {new['label']}",
        "detail": _detail(primary, new, old),
        "site_id": new["site_id"],
        "region_id": new["region_id"],
        "asset_id": new["asset_id"],
        "asset_name": new["asset_name"],
        "tier": new["tier"],
        "previous_tier": old["tier"],
        "rpi": new["rpi"],
        "lat": new["lat"],
        "lon": new["lon"],
    }


def _rain_alerts(p_new: snapshots.Pass, p_old: snapshots.Pass, tbl: dict[str, dict]) -> list[dict]:
    repo = get_repo()
    out = []
    active_regions: dict[str, int] = {}
    for r in tbl.values():
        if r["tier"] in ("ELEVATED", "CRITICAL"):
            active_regions[r["region_id"]] = active_regions.get(r["region_id"], 0) + 1
    names = {r["region_id"]: r["name"] for r in repo.regions()}
    for rid, n_active in active_regions.items():
        now = rain_context(repo, rid, pd.Timestamp(p_new.as_of))
        before = rain_context(repo, rid, pd.Timestamp(p_old.as_of))
        if now is None or now.trigger_score < 60:
            continue
        if before is not None and before.trigger_score >= 60:
            continue
        out.append(
            {
                "alert_id": f"{p_new.as_of}|{rid}|RAIN_TRIGGER",
                "as_of": p_new.as_of,
                "pass_index": p_new.index,
                "kind": "RAIN_TRIGGER",
                "also": [],
                "severity": "medium",
                "title": f"{KIND_LABEL['RAIN_TRIGGER']}: {names.get(rid, rid)}",
                "detail": f"{now.rain_14d_mm:.0f} mm in 14 days (peak day {now.peak_day_mm:.0f} mm) over a region with {n_active} ELEVATED/CRITICAL site(s). Rain amplifies, but does not by itself create, risk.",
                "site_id": None,
                "region_id": rid,
                "asset_id": None,
                "asset_name": None,
                "tier": None,
                "previous_tier": None,
                "rpi": None,
                "lat": None,
                "lon": None,
            }
        )
    return out


@lru_cache(maxsize=1)
def _events() -> tuple[dict, ...]:
    # Do not hold snapshots._LOCK for the whole build — each table_for() locks per pass.
    # Holding the lock across all lookback passes starved Command Center for ~1 minute.
    return _build_events()


def _build_events() -> tuple[dict, ...]:
    ps = snapshots.passes(_lookback() + 1)
    events: list[dict] = []
    for i in range(min(_lookback(), max(len(ps) - 1, 0))):
        new_t, old_t = snapshots.table_for(ps[i]), snapshots.table_for(ps[i + 1])
        for sid, new in new_t.items():
            old = old_t.get(sid)
            if old is None:
                continue
            a = _site_alert(ps[i], new, old)
            if a:
                events.append(a)
        events.extend(_rain_alerts(ps[i], ps[i + 1], new_t))
    return tuple(events)


def clear() -> None:
    _events.cache_clear()


def list_alerts(
    status: str | None = None,
    severity: str | None = None,
    region_ids: set[str] | None = None,
    include_info: bool = True,
) -> list[dict]:
    actions = sorted(get_state().list_actions(), key=lambda x: x["at"])
    history: dict[str, list[dict]] = {}
    for a in actions:
        history.setdefault(a["alert_id"], []).append(a)
    out = []
    for e in _events():
        if region_ids is not None and e["region_id"] not in region_ids:
            continue
        if severity and e["severity"] != severity:
            continue
        if not include_info and e["severity"] == "info":
            continue
        hist = history.get(e["alert_id"], [])
        last = hist[-1] if hist else None
        st = ACTIONS[last["action"]] if last else "open"
        if status and st != status:
            continue
        assignee = next((h["assignee"] for h in reversed(hist) if h["action"] in ("assign", "escalate")), None) if st in ("assigned", "escalated") else None
        out.append({**e, "status": st, "assignee": assignee, "history": hist})
    out.sort(key=lambda a: (a["pass_index"], -SEVERITY_RANK[a["severity"]], -(a["rpi"] or 0)))
    return out


def counts(region_ids: set[str] | None = None) -> dict:
    items = list_alerts(region_ids=region_ids)
    open_ = [a for a in items if a["status"] in ("open", "escalated")]
    return {
        "total": len(items),
        "open": len(open_),
        "open_critical": sum(1 for a in open_ if a["severity"] == "critical"),
        "latest_pass": sum(1 for a in items if a["pass_index"] == 0),
        "by_status": {s: sum(1 for a in items if a["status"] == s) for s in sorted(STATUSES)},
    }


def get(alert_id: str) -> dict | None:
    return next((e for e in _events() if e["alert_id"] == alert_id), None)


def record_action(alert_id: str, action: str, actor: str = "operator", note: str = "", assignee: str | None = None) -> dict:
    if action not in ACTIONS:
        raise ValueError(f"action must be one of {sorted(ACTIONS)}")
    if get(alert_id) is None:
        raise KeyError(alert_id)
    if action in ("assign", "escalate") and not (assignee or "").strip():
        raise ValueError("An assignee is required for assign / escalate.")
    entry = {
        "alert_id": alert_id,
        "action": action,
        "actor": (actor or "operator")[:60],
        "note": (note or "")[:500],
        "assignee": (assignee or "").strip()[:60] or None,
        "at": now_iso(),
    }
    get_state().add_action(entry)
    return entry
