"""Public data store (USGS earthquakes) and the seismic context built from it."""
from __future__ import annotations

import io
from datetime import datetime, timezone

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.services.agent import guard
from app.services.agent.schema import Narrative
from app.services.agent.tools import get_seismic_context
from app.services.data import connectors, public_catalog as pc, public_service
from app.services.data.service import DataError
from app.services.intel import context

NOW = datetime(2026, 10, 16, 12, 0, tzinfo=timezone.utc)
AS_OF = pd.Timestamp("2026-10-14")
SITE = (30.50, 79.50)  # Uttarakhand, where the demo highway sits


def usgs_csv(rows: list[dict]) -> bytes:
    base = {"depth": 10.0, "magType": "mb", "net": "us", "place": "somewhere", "type": "earthquake"}
    df = pd.DataFrame([{**base, "id": f"ev{i}", **r} for i, r in enumerate(rows)])
    return df.to_csv(index=False).encode()


def km_north(km: float) -> float:
    return SITE[0] + km / 111.195


EVENTS = [
    {"time": "2026-10-10T03:00:00.000Z", "latitude": km_north(50), "longitude": SITE[1], "mag": 5.2, "place": "50 km N of site"},
    {"time": "2026-10-02T03:00:00.000Z", "latitude": km_north(90), "longitude": SITE[1], "mag": 4.1, "place": "90 km N"},
    {"time": "2026-10-09T03:00:00.000Z", "latitude": km_north(40), "longitude": SITE[1], "mag": 3.4, "place": "too small"},
    {"time": "2026-10-09T03:00:00.000Z", "latitude": km_north(150), "longitude": SITE[1], "mag": 4.6, "place": "too far for recent"},
    {"time": "2026-09-01T03:00:00.000Z", "latitude": km_north(10), "longitude": SITE[1], "mag": 4.5, "place": "too old for recent"},
    {"time": "2026-10-15T03:00:00.000Z", "latitude": km_north(10), "longitude": SITE[1], "mag": 6.0, "place": "after the assessment date"},
    {"time": "2024-03-05T03:00:00.000Z", "latitude": km_north(180), "longitude": SITE[1], "mag": 6.1, "place": "history"},
    {"time": "2026-10-11T03:00:00.000Z", "latitude": km_north(20), "longitude": SITE[1], "mag": 4.8, "type": "quarry blast", "place": "blast"},
]


@pytest.fixture()
def store(tmp_path):
    old = settings.public_dir
    settings.public_dir = tmp_path / "public"
    context.clear_cache()
    yield
    settings.public_dir = old
    context.clear_cache()


@pytest.fixture()
def fake_usgs(monkeypatch):
    calls: list[str] = []

    def fake_fetch(url, *a, **kw):
        calls.append(url)
        return "q.csv", usgs_csv(EVENTS)

    monkeypatch.setattr(connectors, "fetch_url", fake_fetch)
    return calls


# ---- parsing -----------------------------------------------------------------------------------------


def test_normalise_keeps_only_valid_earthquakes_newest_first():
    rows = EVENTS + [
        {"time": "2026-10-01T00:00:00Z", "latitude": 95.0, "longitude": 10, "mag": 5.0},  # impossible latitude
        {"time": "not a date", "latitude": 1.0, "longitude": 10, "mag": 5.0},
        {"time": "2026-10-01T00:00:00Z", "latitude": 1.0, "longitude": 10, "mag": None},
    ]
    df = pc.normalise_usgs(usgs_csv(rows))
    assert len(df) == len(EVENTS) - 1  # the quarry blast and the three bad rows are gone
    assert "blast" not in set(df["place"])
    assert df["time"].is_monotonic_decreasing
    assert list(df.columns) == pc.EVENT_COLS


def test_normalise_rejects_files_that_are_not_event_lists():
    with pytest.raises(pc.PublicDataError):
        pc.normalise_usgs(b"a,b\n1,2\n")
    with pytest.raises(pc.PublicDataError):
        pc.normalise_usgs(b"")


def test_duplicate_event_ids_are_collapsed():
    df = pc.normalise_usgs(usgs_csv([EVENTS[0], EVENTS[0]]).replace(b"ev1", b"ev0"))
    assert len(df) == 1


# ---- fetching and storage -------------------------------------------------------------------------------


def test_fetch_stores_csv_and_metadata(store, fake_usgs):
    meta = pc.fetch_catalog_entry("usgs-quakes-30d", NOW)
    assert meta["rows"] == len(EVENTS) - 1 and meta["max_magnitude"] == 6.1
    assert (settings.public_dir / "usgs-quakes-30d.csv").exists()
    stored = pd.read_csv(settings.public_dir / "usgs-quakes-30d.csv")
    assert list(stored.columns) == pc.EVENT_COLS
    assert fake_usgs == ["https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/2.5_month.csv"]
    assert meta["license"] and "Geological Survey" in meta["citation"]
    assert not list(settings.public_dir.glob("*.tmp"))  # atomic write left nothing behind


def test_five_year_query_url_is_built_from_today(store, fake_usgs):
    pc.fetch_catalog_entry("usgs-quakes-m5-5y", NOW)
    url = fake_usgs[0]
    assert "minmagnitude=5" in url and "starttime=2021-10-17" in url and "endtime=2026-10-16" in url and "format=csv" in url


def test_region_query_has_the_centre_radius_and_window(store, fake_usgs):
    meta = pc.fetch_region_seismicity("IN-UK-CHM", 30.55, 79.57, radius_km=250, days=90, min_mag=3, now=NOW)
    url = fake_usgs[0]
    for part in ("latitude=30.5500", "longitude=79.5700", "maxradiuskm=250", "minmagnitude=3", "starttime=2026-07-18"):
        assert part in url, url
    assert meta["id"] == "usgs-quakes-in-uk-chm"


@pytest.mark.parametrize("kw", [{"radius_km": 5}, {"radius_km": 5000}, {"days": 2}, {"days": 99999}, {"min_mag": -1}, {"min_mag": 12}])
def test_region_fetch_rejects_silly_parameters(store, fake_usgs, kw):
    with pytest.raises(pc.PublicDataError):
        pc.fetch_region_seismicity("X", 1, 1, now=NOW, **kw)
    assert fake_usgs == []  # nothing was requested


def test_unknown_and_malicious_dataset_ids_are_refused(store):
    for bad in ("nope", "../secrets", "a/b", "..\\x", "UPPER", ""):
        with pytest.raises(pc.PublicDataError):
            pc.fetch_catalog_entry(bad)
    with pytest.raises(pc.PublicDataError):
        pc._csv_path("../../etc/passwd")


def test_upstream_failure_is_a_readable_error_and_stores_nothing(store, monkeypatch):
    def down(url, *a, **kw):
        raise connectors.FetchError("The server answered 503 for that link.")

    monkeypatch.setattr(connectors, "fetch_url", down)
    with pytest.raises(pc.PublicDataError, match="503"):
        pc.fetch_catalog_entry("usgs-quakes-30d", NOW)
    assert pc.stored_ids() == []


def test_empty_answer_is_not_stored(store, monkeypatch):
    monkeypatch.setattr(connectors, "fetch_url", lambda u, *a, **k: ("q.csv", usgs_csv([{**EVENTS[0], "type": "explosion"}])))
    with pytest.raises(pc.PublicDataError, match="no events"):
        pc.fetch_catalog_entry("usgs-quakes-30d", NOW)


def test_downloads_use_the_ssrf_guarded_fetcher(store, monkeypatch):
    seen = []
    monkeypatch.setattr(connectors, "fetch_url", lambda u, *a, **k: (seen.append(u), ("q.csv", usgs_csv(EVENTS)))[1])
    pc.fetch_catalog_entry("usgs-quakes-30d", NOW)
    assert seen and seen[0].startswith("https://earthquake.usgs.gov/")


def test_listing_marks_staleness_and_includes_region_fetches(store, fake_usgs):
    pc.fetch_catalog_entry("usgs-quakes-30d", NOW)
    pc.fetch_region_seismicity("IN-UK-CHM", 30.55, 79.57, now=NOW)
    fresh = {d["id"]: d for d in pc.listing(NOW)}
    assert fresh["usgs-quakes-30d"]["stored"]["stale"] is False
    assert fresh["usgs-quakes-m5-5y"]["stored"] is None
    assert fresh["usgs-quakes-in-uk-chm"]["scope"] == "region"
    later = {d["id"]: d for d in pc.listing(datetime(2026, 10, 25, tzinfo=timezone.utc))}
    assert later["usgs-quakes-30d"]["stored"]["stale"] is True


def test_preview_summarises_without_returning_everything(store, fake_usgs):
    pc.fetch_catalog_entry("usgs-quakes-30d", NOW)
    p = pc.preview("usgs-quakes-30d")
    assert p["largest"][0]["mag"] == 6.1 and len(p["largest"]) <= 12
    assert sum(p["by_magnitude"].values()) <= p["meta"]["rows"]
    with pytest.raises(pc.PublicDataError):
        pc.preview("usgs-quakes-m5-5y")


# ---- context maths ---------------------------------------------------------------------------------------------


def test_distance_is_accurate():
    df = pd.DataFrame({"latitude": [31.0], "longitude": [79.5]})
    import numpy as np

    df["_lat"], df["_lon"] = np.radians(df["latitude"]), np.radians(df["longitude"])
    assert context._distances_km(df, 30.0, 79.5)[0] == pytest.approx(111.19, abs=0.3)


def test_seismic_context_counts_only_what_belongs(store, fake_usgs):
    pc.fetch_catalog_entry("usgs-quakes-30d", NOW)
    s = context.seismic_for(*SITE, AS_OF)
    assert s["available"] is True
    # M4+ within 100 km in the 30 days to 2026-10-14: the 50 km M5.2 and the 90 km M4.1. Not the M3.4, the 150 km
    # one, the September one (outside the window), the post-assessment M6.0 or the quarry blast.
    assert s["recent_count"] == 2 and s["recent_max_magnitude"] == 5.2 and s["recent_nearest_km"] == 50
    assert [e["mag"] for e in s["recent_events"]] == [5.2, 4.1]
    # M5+ within 200 km up to the assessment date: the M5.2 and the 2024 M6.1 (the M6.0 is after as-of)
    assert s["history_count"] == 2 and s["history_largest"]["mag"] == 6.1 and s["history_largest"]["distance_km"] == 180
    assert "not used in the risk score" in s["note"]


def test_no_data_says_so_instead_of_claiming_calm(store):
    s = context.seismic_for(*SITE, AS_OF)
    assert s["available"] is False and "recent_count" not in s and "Fetch" in s["message"]


def test_partial_coverage_is_called_out(store, monkeypatch):
    only_recent = [e for e in EVENTS if e["time"] >= "2026-10-09"]
    monkeypatch.setattr(connectors, "fetch_url", lambda u, *a, **k: ("q.csv", usgs_csv(only_recent)))
    pc.fetch_catalog_entry("usgs-quakes-30d", NOW)
    s = context.seismic_for(*SITE, AS_OF)
    assert any("starts" in w for w in s["warnings"])


def test_stale_data_is_called_out(store, fake_usgs):
    pc.fetch_catalog_entry("usgs-quakes-30d", NOW)
    s = context.seismic_for(*SITE, pd.Timestamp("2026-12-01"))
    assert any("ends" in w for w in s["warnings"])


def test_merged_datasets_do_not_double_count(store, fake_usgs):
    pc.fetch_catalog_entry("usgs-quakes-30d", NOW)
    pc.fetch_catalog_entry("usgs-quakes-m5-5y", NOW)  # same ids again
    assert context.seismic_for(*SITE, AS_OF)["recent_count"] == 2


def test_map_layer_respects_bbox_magnitude_and_limit(store, fake_usgs):
    pc.fetch_catalog_entry("usgs-quakes-30d", NOW)
    box = (SITE[1] - 1, SITE[0] - 3, SITE[1] + 1, SITE[0] + 3)
    all_ = context.events_in_bbox(*box, min_mag=0)
    assert all_["count"] == len(EVENTS) - 1 and not all_["truncated"]
    big = context.events_in_bbox(*box, min_mag=5)
    assert {e["mag"] for e in big["events"]} == {5.2, 6.0, 6.1}
    capped = context.events_in_bbox(*box, min_mag=0, limit=2)
    assert capped["truncated"] and [e["mag"] for e in capped["events"]] == [6.1, 6.0]
    assert context.events_in_bbox(0, 0, 1, 1)["count"] == 0


# ---- wiring: provenance, work-order tool, site detail --------------------------------------------------------------


def test_fetch_records_one_provenance_row_even_after_refetch(workspace, store, fake_usgs):
    public_service.fetch("usgs-quakes-30d")
    public_service.fetch("usgs-quakes-30d")
    from app.services.data import service

    rows = [d for d in service.status()["datasets"] if d["kind"] == "events"]
    assert len(rows) == 1 and rows[0]["source_type"] == "public" and "Public domain" in rows[0]["notes"][0]
    public_service.remove("usgs-quakes-30d")
    assert not [d for d in service.status()["datasets"] if d["kind"] == "events"]
    with pytest.raises(DataError):
        public_service.remove("usgs-quakes-30d")


def test_unknown_region_for_seismicity_is_a_user_error(workspace, store, fake_usgs):
    with pytest.raises(DataError, match="Unknown region"):
        public_service.fetch_seismicity("ZZ-NOPE", 300, 365, 2.5)


def _a_site():
    from app.services.detection.pipeline import run_pipeline

    return run_pipeline()[0]


def test_site_detail_and_tool_carry_seismic_context(workspace, store, fake_usgs):
    from app.services.detection import views

    s = _a_site()
    assert views.site_detail(s)["seismic"]["available"] is False
    assert get_seismic_context(s.site_id)["available"] is False
    public_service.fetch("usgs-quakes-30d")
    assert views.site_detail(s)["seismic"]["available"] is True
    t = get_seismic_context(s.site_id)
    assert t["available"] is True and "recent_count" in t and t["source"]
    assert get_seismic_context("nope")["error"]


def test_guard_accepts_quoting_tool_numbers_and_rejects_invented_ones():
    tool = {"site_id": "S-1", "available": True, "recent_count": 2, "recent_max_magnitude": 5.2, "recent_nearest_km": 50,
            "recent_radius_km": 100, "recent_window_days": 30, "coverage_to": "2026-10-10"}
    ok = Narrative(summary="Two earthquakes within 100 km in 30 days, the largest M5.2 at 50 km.", mechanism_hypothesis="Shaking may have loosened material.",
                   recommended_action="Inspect within 48 hours.", site_specific_checks=[])
    assert guard.validate_narrative(ok, [tool], "ELEVATED", "S-1").passed
    bad = ok.model_copy(update={"summary": "A magnitude 6.8 earthquake struck 12 km away."})
    v = guard.validate_narrative(bad, [tool], "ELEVATED", "S-1")
    assert not v.passed and any("6.8" in i for i in v.issues)


def test_public_data_never_changes_risk_scores(workspace, store, fake_usgs):
    from app.services.detection.pipeline import run_pipeline

    before = [(s.site_id, s.tier, s.rpi) for s in run_pipeline()]
    public_service.fetch("usgs-quakes-30d")
    after = [(s.site_id, s.tier, s.rpi) for s in run_pipeline()]
    assert before == after


# ---- API ---------------------------------------------------------------------------------------------------------------


def test_api_catalog_fetch_preview_delete_roundtrip(workspace, store, fake_usgs):
    c = TestClient(app)
    cat = c.get("/api/data/public").json()
    assert {d["id"] for d in cat["datasets"]} >= {"usgs-quakes-30d", "usgs-quakes-m5-5y"} and "Geological Survey" in cat["attribution"]
    r = c.post("/api/data/public/usgs-quakes-30d/fetch")
    assert r.status_code == 200 and r.json()["rows"] == len(EVENTS) - 1
    assert c.get("/api/data/public/usgs-quakes-30d/preview").json()["largest"][0]["mag"] == 6.1
    ev = c.get("/api/context/events", params={"bbox": f"{SITE[1]-1},{SITE[0]-3},{SITE[1]+1},{SITE[0]+3}", "min_mag": 5}).json()
    assert ev["count"] == 3
    assert c.delete("/api/data/public/usgs-quakes-30d").status_code == 200
    assert c.delete("/api/data/public/usgs-quakes-30d").status_code == 400
    assert c.post("/api/data/public/not-a-dataset/fetch").status_code == 400
    assert c.get("/api/context/events", params={"bbox": "a,b"}).status_code == 400


def test_api_region_seismicity(workspace, store, fake_usgs):
    c = TestClient(app)
    region = c.get("/api/regions").json()[0]["region_id"]
    r = c.post("/api/data/public/seismicity", json={"region_id": region, "radius_km": 200, "days": 60, "min_mag": 3})
    assert r.status_code == 200, r.text
    assert c.post("/api/data/public/seismicity", json={"region_id": region, "radius_km": 5}).status_code == 422
    assert c.post("/api/data/public/seismicity", json={"region_id": "ZZ-NOPE"}).status_code == 400


@pytest.mark.usefixtures("auth_on")
def test_only_admins_can_change_the_public_store(store, fake_usgs):
    admin = TestClient(app)
    assert admin.post("/api/auth/login", json={"username": "admin", "password": "Correct-Horse-Battery-9"}).status_code == 200
    admin.post("/api/auth/users", json={"username": "andy", "role": "analyst", "password": "Sturdy-Passphrase-77"})
    admin.post("/api/auth/users", json={"username": "vera", "role": "viewer", "password": "Sturdy-Passphrase-77"})
    for name in ("andy", "vera"):
        c = TestClient(app)
        c.post("/api/auth/login", json={"username": name, "password": "Sturdy-Passphrase-77"})
        assert c.get("/api/data/public").status_code == 200  # everyone signed in may look
        assert c.post("/api/data/public/usgs-quakes-30d/fetch").status_code == 403
        assert c.delete("/api/data/public/usgs-quakes-30d").status_code == 403
    assert admin.post("/api/data/public/usgs-quakes-30d/fetch").status_code == 200
