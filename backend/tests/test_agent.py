"""Agent safety tests: the guard must catch fabricated numbers and certainty language,
and the template must always produce a valid, complete work order (no Vertex needed)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.agent import service
from app.services.agent.guard import validate_narrative
from app.services.agent.schema import Narrative
from app.services.agent.tools import TOOLS, get_outlook, get_site_metrics
from app.services.data.generate_demo import generate
from app.core.config import settings

client = TestClient(app)
HERO = "NH58-DEMO-010"
DEGRADED = "NH58-DEMO-016"


@pytest.fixture(scope="module", autouse=True)
def _data():
    generate(settings.data_dir)
    from app.services.data import repo
    from app.services.detection import pipeline, views

    repo.get_repo.cache_clear()
    pipeline.clear_cache()
    views.series_for.cache_clear()
    service.clear_cache()
    yield


def truth(site_id):
    return [fn(site_id) for fn in TOOLS]


def narr(**kw):
    base = dict(
        summary="Motion is increasing at this site.",
        mechanism_hypothesis="Possible toe-unloading slip; consistent with the data but unconfirmed.",
        recommended_action="Dispatch a crew within 48 hours.",
    )
    base.update(kw)
    return Narrative(**base)


# ---- guard: must reject ------------------------------------------------------


def test_guard_rejects_fabricated_number():
    m = get_site_metrics(HERO)
    fake = round(abs(m["rate_recent_mm_month"]) + 7.3, 1)
    v = validate_narrative(narr(summary=f"Speed is now {fake} mm/month."), truth(HERO), "CRITICAL", HERO)
    assert not v.passed and any(str(fake) in i for i in v.issues)


def test_guard_accepts_exact_tool_numbers():
    m = get_site_metrics(HERO)
    v = validate_narrative(
        narr(summary=f"Speed is {abs(m['rate_recent_mm_month']):.1f} mm/month ({m['accel_ratio']:.1f}x)."),
        truth(HERO), "CRITICAL", HERO,
    )
    assert v.passed, v.issues


def test_guard_rejects_invented_date():
    v = validate_narrative(narr(summary="It will be critical on 2027-03-14."), truth(HERO), "CRITICAL", HERO)
    assert not v.passed


@pytest.mark.parametrize(
    "text",
    [
        "The slope will collapse next month.",
        "We guarantee the road is safe.",
        "Failure is inevitable.",
        "The exact date of failure is soon.",
        "Imminent collapse expected.",
    ],
)
def test_guard_rejects_certainty_language(text):
    v = validate_narrative(narr(summary=text), truth(HERO), "CRITICAL", HERO)
    assert not v.passed


def test_guard_requires_hedged_mechanism():
    v = validate_narrative(narr(mechanism_hypothesis="The cause is toe excavation."), truth(HERO), "CRITICAL", HERO)
    assert not v.passed


def test_guard_weak_site_must_state_data_limitation():
    v = validate_narrative(narr(summary="Large movement detected, send a crew."), truth(DEGRADED), "WEAK", DEGRADED)
    assert not v.passed


def test_guard_allows_action_timeframes():
    v = validate_narrative(narr(recommended_action="Dispatch a crew within 72 hours."), truth(HERO), "CRITICAL", HERO)
    assert v.passed, v.issues


def test_guard_accepts_eta_band_from_tools():
    o = get_outlook(HERO)
    v = validate_narrative(
        narr(summary=f"The threshold may be reached in {o['eta_low_days']}-{o['eta_high_days']} days."),
        truth(HERO), "CRITICAL", HERO,
    )
    assert v.passed, v.issues


# ---- template: always valid --------------------------------------------------


def all_site_ids():
    return [s["site_id"] for s in client.get("/api/sites?include_stable=true&limit=1000").json()["sites"]]


def test_template_work_order_passes_guard_for_every_site():
    failures = []
    for sid in all_site_ids():
        wo = service.generate_work_order(sid, mode="template", refresh=True)
        if not wo.validation.passed:
            failures.append((sid, wo.validation.issues))
    assert not failures, failures[:3]


def test_work_order_structure_hero():
    wo = service.generate_work_order(HERO, mode="template", refresh=True)
    assert wo.tier == "CRITICAL" and wo.priority_label.startswith("TIER 1")
    assert wo.generated_by == "template"
    assert len(wo.checklist) >= 4 and len(wo.limitations) >= 4
    assert "not a failure prediction" in wo.outlook_text
    assert any("DEMONSTRATION" in l for l in wo.limitations)
    assert wo.ticket_id.startswith("TS-IN-UK-CHM-NH58-DEMO-010-")


def test_degraded_work_order_does_not_escalate_or_forecast():
    wo = service.generate_work_order(DEGRADED, mode="template", refresh=True)
    assert wo.tier == "WEAK"
    assert "No outlook" in wo.outlook_text
    assert any("Verify" in c.item for c in wo.checklist)
    assert "Dispatch" not in wo.recommended_action


def test_endpoint_returns_work_order_with_fallback_when_vertex_not_configured():
    r = client.post(f"/api/sites/{HERO}/workorder")
    assert r.status_code == 200
    j = r.json()
    assert j["generated_by"] == "template" and j["validation"]["passed"] is True


def test_endpoint_404_unknown_site():
    assert client.post("/api/sites/NOPE/workorder").status_code == 404


def test_agent_status_reports_mode():
    j = client.get("/api/agent/status").json()
    assert j["mode"] in ("gemini", "template-fallback")
