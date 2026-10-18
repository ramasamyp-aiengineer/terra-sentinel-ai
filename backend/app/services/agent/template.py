"""Deterministic work-order assembly + fallback narrative.

Used in two ways:
  * as the *always-available* fallback when Gemini is unavailable or fails validation
  * as the assembler for the Gemini path (evidence/checklist/limitations are always
    deterministic; only the Narrative fields come from the model)
"""
from __future__ import annotations

from app.services.agent.schema import (
    ChecklistItem,
    EvidenceLine,
    Narrative,
    Validation,
    WorkOrder,
)

PRIORITY = {
    "CRITICAL": "TIER 1 - URGENT FIELD INVESTIGATION",
    "ELEVATED": "TIER 2 - PLAN INSPECTION",
    "WATCH": "TIER 3 - ADVISORY",
    "STABLE": "NO ACTION REQUIRED",
    "WEAK": "DATA QUALITY - VERIFY BEFORE ACTING",
}

CHECKLISTS: dict[str, list[tuple[str, str]]] = {
    "HIGHWAY": [
        ("Inspect the cut face and road shoulder for fresh tension cracks running parallel to the slope.", "Cracks parallel to the cut indicate active downslope movement."),
        ("Check culverts and side drains in the chainage range for silt blockage or diverted discharge.", "Blocked drainage raises pore-water pressure in the slope."),
        ("Look for recent excavation, hill-cutting or toe removal near the carriageway.", "Toe unloading removes lateral support of the slope."),
        ("Inspect retaining walls and breast walls for bulging, tilt or weep-hole staining.", "Structural distress shows load transfer from the moving mass."),
        ("Install crack gauges or tell-tales across the upper scarp where safe to access.", "Creates ground truth to confirm the satellite signal."),
    ],
    "METRO": [
        ("Run a digital-level survey across street cross-sections in the chainage range.", "Confirms the settlement trough shape and magnitude."),
        ("Inspect the road surface and kerb lines for longitudinal tensile cracking.", "Surface cracking marks the edge of the settlement trough."),
        ("Review TBM grout-injection volumes and face-pressure logs for the rings under this chainage.", "Over-excavation or tail-void grouting deficit is a leading cause of settlement."),
        ("Check adjacent buildings for new facade cracks, door/window binding or tilt.", "Differential settlement damages structures within the trough."),
        ("Check for water-main or utility leaks and pressure drops near the alignment.", "Leaks can wash fines into the tunnel and accelerate settlement."),
    ],
    "DAM": [
        ("Survey crest levels and compare against the as-built reference.", "Crest settlement is a primary early indicator of embankment distress."),
        ("Inspect the downstream face and toe for bulging, wet patches or new seepage.", "Seepage and bulging precede internal erosion and slope failure."),
        ("Review piezometer and seepage-weir readings for the section.", "Instrument data shows whether pore pressures are rising."),
        ("Check drain outlets for turbidity or sediment carry-over.", "Cloudy discharge can indicate internal erosion."),
        ("Verify freeboard and spillway condition ahead of the next heavy-rain window.", "Rainfall loads the embankment and raises the phreatic surface."),
    ],
}

STATE_NOTE = {
    "accelerating": "Motion is speeding up relative to its own recent baseline.",
    "threshold_approach": "Cumulative displacement is approaching the operational inspection threshold.",
    "persistent_creep": "Steady creep without acceleration.",
    "seasonal": "Pattern is consistent with a seasonal cycle that largely recovers.",
    "stable": "No meaningful motion above baseline noise.",
    "data_degraded": "Measurements are too weak to support a reliable assessment.",
}


def outlook_text(d: dict) -> str:
    o = d["outlook"]
    thr, prog = o["threshold_mm"], o["progress_mm"]
    win = d["thresholds"]["window_days"]
    if o["status"] == "threshold_exceeded":
        return f"The {thr:.0f} mm operational threshold has already been exceeded ({prog:.1f} mm over the {win}-day window)."
    if o["status"] == "approaching":
        return (
            f"If the current motion regime continues, the {thr:.0f} mm operational threshold may be reached in about "
            f"{o['eta_low_days']}-{o['eta_high_days']} days ({prog:.1f} mm of {thr:.0f} mm accumulated over the {win}-day window). "
            "This projects the current trend; it is not a failure prediction."
        )
    if o["status"] == "no_crossing_expected":
        return "No threshold crossing is expected within 12 months at the current rate of movement."
    return "No outlook issued: data quality is insufficient or there is no sustained motion."


def evidence_lines(d: dict) -> list[EvidenceLine]:
    m, c = d["metrics"], d["confidence_detail"]
    ev = [
        EvidenceLine(
            label="Recent speed",
            value=f"{abs(m['rate_recent_mm_month']):.1f} mm/month (baseline {abs(m['rate_baseline_mm_month']):.1f} mm/month; {m['accel_ratio']:.1f}x)",
            source="get_site_metrics",
        ),
        EvidenceLine(label="Last 60 days", value=f"{abs(m['d60_mm']):.1f} mm cumulative displacement", source="get_site_metrics"),
        EvidenceLine(
            label=f"Threshold window ({d['thresholds']['window_days']} days)",
            value=f"{abs(m['d_window_mm']):.1f} mm of {d['thresholds']['operational_threshold_mm']:.0f} mm operational threshold",
            source="get_outlook",
        ),
        EvidenceLine(label="Persistence", value=f"{m['persistence']} consecutive epochs in the same direction", source="get_site_metrics"),
    ]
    r = d.get("rain")
    if r:
        ev.append(
            EvidenceLine(
                label="Rainfall (14 days)",
                value=f"{r['rain_14d_mm']:.0f} mm (peak day {r['peak_day_mm']:.0f} mm; {r['source']})",
                source="get_rainfall_context",
            )
        )
    else:
        ev.append(EvidenceLine(label="Rainfall", value="Unavailable - confidence reduced", source="get_rainfall_context"))
    sm = d.get("seismic") or {}
    if sm.get("available") and sm.get("recent_count"):
        ev.append(
            EvidenceLine(
                label="Earthquakes nearby (context)",
                value=(
                    f"{sm['recent_count']} event(s) of M{sm['recent']['min_magnitude']:.1f}+ within {sm['recent']['radius_km']:.0f} km "
                    f"in the last {sm['recent']['window_days']} days; largest M{sm['recent_max_magnitude']:.1f}"
                ),
                source="get_seismic_context",
            )
        )
    ev.append(
        EvidenceLine(
            label="Data quality",
            value=f"confidence {c['label']} ({c['score']:.2f}); coherence {d['coherence_mean']:.2f}; {d['n_points']} scatterers",
            source="get_data_quality",
        )
    )
    ev.append(
        EvidenceLine(
            label="Exposure",
            value=f"{d['asset_name']} (criticality {d['criticality']:.2f}) - {d['consequence_note']}",
            source="get_asset_exposure",
        )
    )
    return ev


def limitations(d: dict) -> list[str]:
    out = [
        "Single line-of-sight (LOS) measurement: vertical and east-west motion cannot be separated.",
        "Satellite revisit is every 6-12 days; fast events between passes (e.g. flash debris flows) are not captured.",
        "The outlook assumes the current regime continues and is not a prediction of failure.",
        "Decision-support for qualified engineers; not a certified safety system. Field verification is required.",
    ]
    if d["data_source"].startswith("DEMO"):
        out.insert(0, "DEMONSTRATION DATA: motion and rainfall values are synthetic and not real measurements.")
    if d["state"] == "data_degraded":
        out.append(
            f"Low measurement quality (coherence {d['coherence_mean']:.2f}, {d['n_points']} scatterers): "
            "no forecast is issued and the site is excluded from escalation."
        )
    if not d.get("rain"):
        out.append("Rainfall context unavailable; trigger assessment not performed.")
    return out


def template_narrative(d: dict) -> Narrative:
    """Deterministic narrative that satisfies the same guard as LLM output."""
    m, o, tier, state = d["metrics"], d["outlook"], d["tier"], d["state"]
    asset = d["asset_name"].split(" (")[0]
    km = f"KM {d['chainage_start_km']:.2f}-{d['chainage_end_km']:.2f}"
    hint = d["thresholds"]["mechanism_hint"]
    r = d.get("rain")
    rain_s = (
        f" Rainfall over the last 14 days was {r['rain_14d_mm']:.0f} mm, which can amplify slope movement."
        if r
        else ""
    )

    if state == "data_degraded":
        summary = (
            f"The signal at {asset} {km} cannot be relied on: measurement quality is insufficient "
            f"(coherence {d['coherence_mean']:.2f} across {d['n_points']} scatterers). No forecast is issued."
        )
        mech = "No mechanism can be proposed from data of this quality; this is a hypothesis-free flag to verify the measurements."
        action = "Do not act on this signal alone. Verify data quality and consider a ground-based measurement before any dispatch."
        return Narrative(summary=summary, mechanism_hypothesis=mech + " It could be noise rather than real movement.", recommended_action=action)

    if state in ("accelerating", "threshold_approach"):
        summary = (
            f"Ground motion at {asset} {km} has risen from {abs(m['rate_baseline_mm_month']):.1f} to "
            f"{abs(m['rate_recent_mm_month']):.1f} mm/month ({m['accel_ratio']:.1f}x), with {abs(m['d60_mm']):.1f} mm "
            f"recorded over the last 60 days.{rain_s} {outlook_text(d)}"
        )
    elif state == "persistent_creep":
        summary = (
            f"{asset} {km} shows steady creep of {abs(m['rate_recent_mm_month']):.1f} mm/month with no acceleration "
            f"({abs(m['d60_mm']):.1f} mm over the last 60 days).{rain_s}"
        )
    elif state == "seasonal":
        summary = (
            f"{asset} {km} shows a seasonal movement cycle (peak excursion {m['peak_excursion_mm']:.1f} mm) "
            "that largely recovers over twelve months. No sustained trend is present."
        )
    else:
        summary = f"{asset} {km} shows no meaningful motion above baseline noise."

    mech = (
        f"Possible {hint}. The measurements are consistent with this but do not confirm it; "
        "field inspection is required to establish the actual mechanism."
    )

    if tier == "CRITICAL":
        action = "Dispatch a field inspection crew within 48 hours and review temporary access or traffic restrictions for heavy-rain periods."
    elif tier == "ELEVATED":
        window = f" before the lower end of the projected window ({o['eta_low_days']} days)" if o["eta_low_days"] else ""
        action = f"Schedule a field inspection{window} and install monitoring gauges where safe."
    elif tier == "WATCH":
        action = "No dispatch needed. Keep on the watch list and re-check after the next satellite pass."
    else:
        action = "No action required. Continue routine monitoring."
    return Narrative(summary=summary, mechanism_hypothesis=mech, recommended_action=action)


def build_work_order(
    d: dict,
    narrative: Narrative,
    generated_by: str,
    validation: Validation,
    model: str | None = None,
    tool_calls: list[dict] | None = None,
) -> WorkOrder:
    base = CHECKLISTS.get(d["asset_type"], CHECKLISTS["HIGHWAY"])
    checklist = [ChecklistItem(item=i, why=w) for i, w in base]
    if d["tier"] in ("CRITICAL", "ELEVATED"):
        checklist += [ChecklistItem(item=t) for t in narrative.site_specific_checks[:3]]
    if d["tier"] == "WEAK":
        checklist = [
            ChecklistItem(item="Verify the satellite measurement quality before dispatching a crew.", why="Coherence is too low for a reliable reading."),
            ChecklistItem(item="Check whether a newer satellite pass improves coherence at this location."),
            ChecklistItem(item="If the asset is critical, arrange a ground-based reading to confirm or dismiss the signal."),
        ]
    if d["tier"] in ("STABLE", "WATCH"):
        checklist = checklist[:2]

    as_of = d["as_of"].replace("-", "")
    citations = [
        f"site {d['site_id']}",
        f"satellite epoch {d['metrics']['last_epoch']}",
        f"{d['n_points']} scatterers (point ids on request)",
        f"as of {d['as_of']}",
    ]
    return WorkOrder(
        ticket_id=f"TS-{d['region_id']}-{d['site_id']}-{as_of}",
        site_id=d["site_id"],
        tier=d["tier"],
        priority_label=PRIORITY[d["tier"]],
        asset_name=d["asset_name"],
        chainage=f"KM {d['chainage_start_km']:.2f} - {d['chainage_end_km']:.2f}",
        lat=d["lat"],
        lon=d["lon"],
        as_of=d["as_of"],
        data_source=d["data_source"],
        consequence=d["consequence_note"],
        evidence=evidence_lines(d),
        outlook_text=outlook_text(d),
        summary=narrative.summary,
        mechanism_hypothesis=narrative.mechanism_hypothesis,
        recommended_action=narrative.recommended_action,
        checklist=checklist,
        limitations=limitations(d),
        citations=citations,
        generated_by=generated_by,
        model=model,
        validation=validation,
        tool_calls=tool_calls or [],
    )
