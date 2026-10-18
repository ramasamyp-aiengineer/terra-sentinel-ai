"""Work-order orchestration: Gemini (grounded) -> validate -> else deterministic template.

The demo can never show a blank or an unvalidated number:
  1. If Gemini is configured (API key or Vertex), run the Gemini function-calling agent.
  2. Validate its narrative against the tool data (one retry with feedback).
  3. On any failure, use the deterministic template (which passes the same guard).
"""
from __future__ import annotations

import logging
from typing import Literal

from app.core.config import settings
from app.services.agent import gemini
from app.services.agent.guard import validate_narrative
from app.services.agent.schema import Validation, WorkOrder
from app.services.agent.template import build_work_order, template_narrative
from app.services.agent.tools import TOOLS, get_site_metrics  # noqa: F401
from app.services.detection import views

log = logging.getLogger("terrasentinel.agent")
_CACHE: dict[tuple, WorkOrder] = {}


def _truth_results(site_id: str) -> list:
    return [fn(site_id) for fn in TOOLS]


def status() -> dict:
    return {
        "gemini_configured": gemini.is_configured(),
        "provider": gemini.provider(),
        "project": settings.gcp_project or None,
        "region": settings.gcp_region,
        "model": settings.gemini_model,
        "mode": "gemini" if gemini.is_configured() else "template-fallback",
    }


def generate_work_order(site_id: str, mode: Literal["auto", "template"] = "auto", refresh: bool = False) -> WorkOrder:
    site = views.site_by_id().get(site_id)
    if site is None:
        raise KeyError(site_id)
    d = views.site_detail(site)
    key = (site_id, d["as_of"], mode, gemini.is_configured())
    if key in _CACHE and not refresh:
        return _CACHE[key]

    truth = _truth_results(site_id)
    wo: WorkOrder | None = None

    if mode == "auto" and gemini.is_configured():
        feedback: list[str] | None = None
        # Fast path: one Gemini call with tools already run (avoids multi-round function calling).
        for attempt in range(2):
            try:
                narrative, calls, _, used_model = gemini.run_agent_fast(site_id, truth, feedback)
                v = validate_narrative(narrative, truth, d["tier"], site_id)
                if v.passed:
                    wo = build_work_order(d, narrative, "gemini", v, used_model, calls)
                    break
                feedback = v.issues
                log.warning("Gemini fast narrative rejected (attempt %d): %s", attempt + 1, v.issues)
            except Exception as exc:  # noqa: BLE001
                log.warning("Gemini fast path failed (%s); trying function-calling once", exc)
                try:
                    narrative, calls, _, used_model = gemini.run_agent(site_id, feedback)
                    v = validate_narrative(narrative, truth, d["tier"], site_id)
                    if v.passed:
                        wo = build_work_order(d, narrative, "gemini", v, used_model, calls)
                except Exception as exc2:  # noqa: BLE001
                    log.exception("Gemini agent failed: %s", exc2)
                break

    if wo is None:
        narrative = template_narrative(d)
        v = validate_narrative(narrative, truth, d["tier"], site_id)
        if not v.passed:  # template must itself be valid; surface issues rather than hide them
            log.error("Template narrative failed validation: %s", v.issues)
        wo = build_work_order(d, narrative, "template", v)

    _CACHE[key] = wo
    return wo


def cached_orders() -> dict[str, dict]:
    """Work orders already generated for the current assessment (site_id -> light summary)."""
    out: dict[str, dict] = {}
    for (site_id, as_of, _mode, _cfg), wo in _CACHE.items():
        out[site_id] = {"ticket_id": wo.ticket_id, "generated_by": wo.generated_by, "as_of": as_of}
    return out


def clear_cache() -> None:
    _CACHE.clear()
