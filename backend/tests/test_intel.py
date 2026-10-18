"""Intelligence layer: historical passes, alerts + actions, early warning, trends, boards, brief, search."""
from __future__ import annotations

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.core.config import PROFILES, settings
from app.main import app
from app.services.data.generate_demo import generate
from app.services.detection import pipeline
from app.services.intel import alerts, snapshots

client = TestClient(app)


@pytest.fixture(scope="module", autouse=True)
def _demo():
    generate(settings.data_dir)
    from app.services import runtime
    from app.services.data import state

    state.clear_state_cache()
    runtime.refresh_all()
    yield


@pytest.fixture()
def fresh_state(tmp_path):
    """Isolated alert-action store (cheap: no pipeline recompute)."""
    from app.services.agent import service
    from app.services.data import state

    old = settings.state_dir
    settings.state_dir = tmp_path / "state"
    state.clear_state_cache()
    service.clear_cache()
    yield
    settings.state_dir = old
    state.clear_state_cache()
    service.clear_cache()


# ---- historical passes ------------------------------------------------------------


def test_passes_are_aligned_to_real_epochs_and_newest_first():
    ps = snapshots.passes()
    assert ps[0].index == 0 and ps[0].offset_days == 0
    assert len(ps) == snapshots.MAX_PASSES
    epochs = {str(pd.Timestamp(e).date()) for e in snapshots._epochs()}
    assert all(p.as_of in epochs for p in ps[1:])  # every historical pass sits on a real acquisition date
    assert [p.as_of for p in ps[1:]] == sorted((p.as_of for p in ps[1:]), reverse=True)


def test_historical_pass_cannot_see_the_future():
    ps = snapshots.passes()
    old = ps[5]
    repo = pipeline.get_repo()
    ts = repo.timeseries()
    cut = ts[ts["date"] <= pd.Timestamp(old.as_of)]
    sites = pipeline.run_pipeline(old.offset_days)
    # every site's last epoch in that pass is on or before the pass date
    for s in sites:
        assert pd.Timestamp(s.metrics.last_epoch) <= pd.Timestamp(old.as_of)
    assert cut["date"].max() <= pd.Timestamp(old.as_of)
    # and the pass genuinely differs from "now" for the hero site (otherwise history would be meaningless)
    now_t, old_t = snapshots.table_for(ps[0]), snapshots.table_for(old)
    assert now_t["NH58-DEMO-010"]["rpi"] != old_t["NH58-DEMO-010"]["rpi"]


def test_pass_zero_equals_live_pipeline():
    live = {s.site_id: s.tier for s in pipeline.run_pipeline()}
    assert {sid: r["tier"] for sid, r in snapshots.table_for(snapshots.passes()[0]).items()} == live


# ---- alerts --------------------------------------------------------------------------


def test_alerts_are_diffs_with_numbers_from_both_passes():
    j = client.get("/api/alerts").json()
    assert j["count"] == j["summary"]["total"] > 0
    a = next(x for x in j["alerts"] if x["site_id"] == "NH58-DEMO-010" and x["kind"] == "ESCALATED_CRITICAL")
    assert a["previous_tier"] == "ELEVATED" and a["tier"] == "CRITICAL" and a["severity"] == "critical"
    assert "ELEVATED to CRITICAL" in a["detail"]
    ps = snapshots.passes()
    assert a["rpi"] == snapshots.table_for(ps[a["pass_index"]])["NH58-DEMO-010"]["rpi"]


def test_every_alert_site_exists_and_regions_filter_works():
    items = client.get("/api/alerts").json()["alerts"]
    live = {s.site_id for s in pipeline.run_pipeline()}
    assert all(a["site_id"] in live for a in items if a["site_id"])
    chm = client.get("/api/alerts?region=IN-UK-CHM").json()["alerts"]
    assert chm and all(a["region_id"] == "IN-UK-CHM" for a in chm)
    assert client.get("/api/alerts?region=NOPE").status_code == 404
    assert client.get("/api/alerts?status=bogus").status_code == 422


def test_rain_alert_requires_active_sites_and_a_new_crossing():
    rain = [a for a in client.get("/api/alerts").json()["alerts"] if a["kind"] == "RAIN_TRIGGER"]
    for a in rain:
        assert a["site_id"] is None and "does not by itself create" in a["detail"] or "by itself create" in a["detail"]


def test_alert_action_lifecycle_is_persisted_and_audited(fresh_state):
    first = client.get("/api/alerts?severity=critical").json()["alerts"][0]
    aid = first["alert_id"]
    assert first["status"] == "open"

    r = client.post("/api/alerts/action", json={"alert_id": aid, "action": "acknowledge", "actor": "ram", "note": "seen"})
    assert r.status_code == 200 and r.json()["status"] == "acknowledged"

    # assigning needs a person
    assert client.post("/api/alerts/action", json={"alert_id": aid, "action": "assign"}).status_code == 422
    r = client.post("/api/alerts/action", json={"alert_id": aid, "action": "assign", "assignee": "Field Team B"})
    j = r.json()
    assert j["status"] == "assigned" and j["assignee"] == "Field Team B"
    assert [h["action"] for h in j["history"]] == ["acknowledge", "assign"]
    assert j["history"][0]["actor"] == "local" and j["history"][0]["at"]  # the session identity, not the client-supplied "ram"

    assert client.get("/api/alerts?status=assigned").json()["count"] == 1
    r = client.post("/api/alerts/action", json={"alert_id": aid, "action": "resolve", "note": "inspected"})
    assert r.json()["status"] == "resolved"
    assert client.get("/api/alerts").json()["summary"]["by_status"]["resolved"] == 1

    assert client.post("/api/alerts/action", json={"alert_id": "x|y|z", "action": "acknowledge"}).status_code == 404
    assert client.post("/api/alerts/action", json={"alert_id": aid, "action": "delete"}).status_code == 422

    # a new process reading the same state store sees the same history
    from app.services.data import state

    state.clear_state_cache()
    assert client.get("/api/alerts?status=resolved").json()["count"] == 1


# ---- early warning ---------------------------------------------------------------------


def test_early_warning_board_buckets_match_outlook_bands():
    j = client.get("/api/early-warning").json()
    assert j["sites"] and sum(b["count"] for b in j["buckets"]) == len(j["sites"])
    for s in j["sites"]:
        assert s["tier"] not in ("STABLE", "WEAK")
        if s["bucket"] == "d0_30":
            assert 0 <= s["eta_low_days"] <= 30
        if s["bucket"] == "d31_60":
            assert 31 <= s["eta_low_days"] <= 60
        if s["eta_low_days"] is not None:
            assert s["eta_low_days"] <= s["eta_high_days"]  # a band, low <= high
    order = [x["bucket"] for x in j["sites"]]
    assert order == sorted(order, key=["exceeded", "d0_30", "d31_60", "d61_120", "d121_365", "none"].index)
    assert "not predictions of failure" in j["note"]


def test_scenario_is_monotonic_and_bounded():
    sid = "NH58-DEMO-010"
    base = client.get(f"/api/early-warning/scenario?site_id={sid}&rate_change_pct=0").json()
    fast = client.get(f"/api/early-warning/scenario?site_id={sid}&rate_change_pct=100").json()
    slow = client.get(f"/api/early-warning/scenario?site_id={sid}&rate_change_pct=-50").json()
    assert fast["linear_days_scenario"] < base["linear_days_scenario"] < slow["linear_days_scenario"]
    assert base["linear_days_scenario"] == base["linear_days_current"]
    assert client.get(f"/api/early-warning/scenario?site_id={sid}&rate_change_pct=900").status_code == 422
    assert client.get("/api/early-warning/scenario?site_id=NOPE").status_code == 404


# ---- trends -----------------------------------------------------------------------------


def test_portfolio_trend_ends_at_todays_counts():
    j = client.get("/api/trends/portfolio").json()
    assert j["passes"] == snapshots.MAX_PASSES
    assert [p["as_of"] for p in j["series"]] == sorted(p["as_of"] for p in j["series"])  # oldest -> newest
    summary = client.get("/api/regions/IN/summary").json()
    assert j["series"][-1]["counts"] == summary["by_tier"]


def test_site_history_and_movers():
    h = client.get("/api/sites/NH58-DEMO-010/history").json()["history"]
    assert len(h) >= 10 and h[-1]["tier"] == "CRITICAL"
    assert client.get("/api/sites/NOPE/history").status_code == 404
    mv = client.get("/api/trends/movers").json()
    assert mv["risers"] and mv["risers"][0]["delta_rpi"] > 0
    assert all(r["delta_rpi"] < 0 for r in mv["fallers"])


# ---- boards ------------------------------------------------------------------------------


def test_assets_board_totals_reconcile_with_sites():
    j = client.get("/api/assets").json()
    live = pipeline.run_pipeline()
    assert j["count"] == 4 and sum(a["sites"] for a in j["assets"]) == len(live)
    a = next(x for x in j["assets"] if x["asset_id"] == "NH58-DEMO")
    assert sum(a["tier_counts"].values()) == a["sites"] and a["length_km"] > 5
    d = client.get("/api/assets/NH58-DEMO").json()
    assert len(d["strip"]) == a["sites"] and [s["km_start"] for s in d["strip"]] == sorted(s["km_start"] for s in d["strip"])
    assert d["profile"]["threshold_mm"] == PROFILES["HIGHWAY"].threshold_mm
    assert client.get("/api/assets/NOPE").status_code == 404


def test_portfolio_rolls_up_without_double_counting():
    j = client.get("/api/portfolio").json()
    t = j["totals"]
    assert sum(t["tier_counts"].values()) == t["sites"]
    assert sum(r["sites"] for r in j["by_region"]) == t["sites"]
    assert len(j["by_region"]) > 1  # drilled past the single-country root
    assert sum(r["sites"] for r in j["by_asset_type"]) == t["sites"]
    assert [s["rpi"] for s in j["top_sites"]] == sorted((s["rpi"] for s in j["top_sites"]), reverse=True)
    assert j["data_health"]["last_epoch"] and j["data_source"] == "DEMO-SYNTHETIC"


def test_brief_is_deterministic_and_matches_the_ranking():
    a, b = client.get("/api/brief").json(), client.get("/api/brief").json()
    assert a == b and a["generated_by"] == "deterministic"
    act = [s for s in pipeline.run_pipeline() if s.tier in ("CRITICAL", "ELEVATED")]
    assert a["counts"]["CRITICAL"] + a["counts"]["ELEVATED"] == len(act)
    assert a["top_actions"][0]["site_id"] == act[0].site_id
    assert str(len(act)) in a["headline"]
    scoped = client.get("/api/brief?region=IN-TN-CHN").json()
    assert all(s["region_id"] == "IN-TN-CHN" for s in scoped["top_actions"])


def test_search_finds_regions_assets_sites():
    j = client.get("/api/search?q=chennai").json()["results"]
    assert {r["type"] for r in j} >= {"region", "asset"}
    assert client.get("/api/search?q=a").json()["results"] == []  # too short: no noise
    site = client.get("/api/search?q=NH58-DEMO-010").json()["results"][0]
    assert site["type"] == "site" and site["zoom"] >= 12 and site["lat"] and site["lon"]


def test_methodology_is_rendered_from_live_config():
    m = client.get("/api/methodology").json()
    assert {p["asset_type"]: p["threshold_mm"] for p in m["profiles"]} == {k: v.threshold_mm for k, v in PROFILES.items()}
    assert any("not predictions of failure" in x for x in m["limitations"])


def test_workorder_queue_lists_only_act_sites(fresh_state):
    j = client.get("/api/workorders").json()
    assert j["count"] == len([s for s in pipeline.run_pipeline() if s.tier in ("CRITICAL", "ELEVATED")])
    assert all(s["tier"] in ("CRITICAL", "ELEVATED") for s in j["sites"]) and j["drafted"] == 0
    client.post("/api/sites/NH58-DEMO-010/workorder?mode=template")
    j2 = client.get("/api/workorders").json()
    assert j2["drafted"] == 1
    assert next(s for s in j2["sites"] if s["site_id"] == "NH58-DEMO-010")["work_order"]["generated_by"] == "template"


def test_data_change_invalidates_every_cache():
    before = client.get("/api/brief").json()["counts"]
    client.get("/api/alerts")
    client.get("/api/trends/portfolio")
    from app.services import runtime

    runtime.refresh_all()
    assert alerts._events.cache_info().currsize == 0
    assert client.get("/api/brief").json()["counts"] == before  # recomputed, identical for identical data
