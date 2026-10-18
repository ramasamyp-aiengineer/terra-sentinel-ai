"""End-to-end pipeline checks on the demo dataset (golden scenario)."""
from __future__ import annotations

import pytest

from app.services.data.generate_demo import generate
from app.services.detection import pipeline


@pytest.fixture(scope="module")
def sites(tmp_path_factory):
    out = tmp_path_factory.mktemp("demo")
    generate(out)
    from app.core.config import settings
    from app.services.data import repo

    settings.data_dir = out
    repo.get_repo.cache_clear()
    pipeline.clear_cache()
    result = pipeline.run_pipeline()
    yield {s.site_id: s for s in result}
    repo.get_repo.cache_clear()
    pipeline.clear_cache()


def test_hero_highway_site_is_critical(sites):
    s = sites["NH58-DEMO-010"]
    assert s.tier == "CRITICAL" and s.state == "accelerating"


def test_nearing_threshold_site_is_critical(sites):
    assert sites["NH58-DEMO-013"].state == "threshold_approach"
    assert sites["NH58-DEMO-013"].tier == "CRITICAL"


def test_metro_settlement_is_critical(sites):
    assert sites["METRO4-DEMO-004"].tier == "CRITICAL"


def test_consequence_asymmetry_same_motion_different_tier(sites):
    assert sites["NH58-DEMO-010"].tier == "CRITICAL"
    assert sites["SR12-DEMO-006"].tier == "ELEVATED"
    assert sites["NH58-DEMO-010"].rpi > sites["SR12-DEMO-006"].rpi


def test_degraded_site_is_weak_with_no_forecast(sites):
    s = sites["NH58-DEMO-016"]
    assert s.tier == "WEAK" and s.rpi <= 15
    assert s.outlook.status == "not_applicable"
    assert s.confidence.label == "low"


def test_unmonitored_moving_hillside_raises_no_alert(sites):
    # The synthetic moving hillside is >3 km from every asset -> no site should be built there
    assert all(s.asset_id.endswith("DEMO") for s in sites.values())
    top = sorted(sites.values(), key=lambda s: -s.rpi)[:3]
    assert all(s.tier == "CRITICAL" for s in top)


def test_ranking_puts_critical_first(sites):
    ranked = sorted(sites.values(), key=lambda s: -s.rpi)
    crit = [s for s in ranked if s.tier == "CRITICAL"]
    assert ranked[: len(crit)] == crit


def test_stable_sites_are_overwhelming_majority(sites):
    stable = sum(1 for s in sites.values() if s.tier == "STABLE")
    assert stable / len(sites) > 0.8  # triage: few sites need attention
