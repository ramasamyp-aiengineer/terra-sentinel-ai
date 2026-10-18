"""Data Hub end-to-end: upload -> validate -> workspace -> pipeline -> provenance -> reset."""
from __future__ import annotations

import io
import json

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.services.data import connectors
from app.services.data.generate_demo import generate

client = TestClient(app)


@pytest.fixture(autouse=True)
def _demo(workspace):
    generate(settings.data_dir)
    from app.services import runtime

    runtime.refresh_all()
    yield


EPOCHS = pd.date_range("2026-01-01", periods=16, freq="12D")


def wide_csv(n_per_site: int = 6, sites: int = 4, hot_site: int = 2) -> bytes:
    """A synthetic 'real-looking' EGMS-style file along a 1 km line near Bengaluru."""
    lines = ["pid,latitude,longitude,mean_velocity,temporal_coherence," + ",".join(e.strftime("%Y%m%d") for e in EPOCHS)]
    n = 0
    for s in range(sites):
        for k in range(n_per_site):
            lon = 77.5900 + (s * 250 + k * 35) / 111_320 / 0.974
            lat = 12.9700 + (k % 2) * 0.00005
            rate = -1.4 if s == hot_site else -0.02  # mm per epoch
            disp = [round(rate * i * (1 + 0.15 * i / 15 if s == hot_site else 1), 2) for i in range(len(EPOCHS))]
            lines.append(f"R{n:03d},{lat:.6f},{lon:.6f},{rate * 30:.1f},0.88," + ",".join(map(str, disp)))
            n += 1
    return ("\n".join(lines) + "\n").encode()


ASSET = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "properties": {"name": "Bengaluru Test Road", "asset_type": "HIGHWAY", "region_id": "BLR", "criticality": 0.8, "asset_id": "BLR-ROAD"},
            "geometry": {"type": "LineString", "coordinates": [[77.5895, 12.97015], [77.6005, 12.97015]]},
        }
    ],
}


def post_file(path, name, content, **data):
    return client.post(path, files={"file": (name, io.BytesIO(content), "application/octet-stream")}, data=data)


def test_status_describes_demo_baseline():
    j = client.get("/api/data/status").json()
    assert j["data_source"] == "DEMO-SYNTHETIC" and not j["workspace_active"]
    assert j["counts"]["assets"] == 4 and j["counts"]["points"] > 1000
    assert {d["kind"] for d in j["datasets"]} == {"points", "timeseries", "rain", "assets", "regions"}
    assert j["bigquery"]["configured"] is False and j["bigquery"]["active"] is False


def test_validate_is_a_dry_run_and_writes_nothing():
    r = post_file("/api/data/validate", "egms.csv", wide_csv(), kind="auto")
    assert r.status_code == 200 and r.json()["ok"] is True
    st = client.get("/api/data/status").json()
    assert not st["workspace_active"] and st["counts"]["points"] > 1000 and st["counts"]["points"] < 1500


def test_full_workflow_region_asset_insar_then_reset():
    base_sites = client.get("/api/meta").json()["sites"]

    r = client.post("/api/data/regions", json={"region_id": "BLR", "name": "Bengaluru", "parent_id": "IN", "level": "district", "center_lon": 77.59, "center_lat": 12.97, "zoom": 12})
    assert r.status_code == 200, r.text
    assert any(g["region_id"] == "BLR" for g in client.get("/api/regions").json())

    r = post_file("/api/data/upload", "asset.geojson", json.dumps(ASSET).encode())
    assert r.status_code == 200 and r.json()["applied"] is True, r.text
    # an asset without InSAR points must be called out, not silently ignored
    assert any("no scatterers" in c["message"] for c in r.json()["post_checks"])

    r = post_file("/api/data/upload", "egms.csv", wide_csv(), default_region="BLR")
    j = r.json()
    assert r.status_code == 200 and j["applied"] is True, j
    assert set(j["written"]) == {"points", "timeseries"}
    assert any("monitored site" in c["message"] for c in j["post_checks"])

    meta = client.get("/api/meta").json()
    assert meta["sites"] > base_sites
    assert meta["data_source"] == "mixed"  # demo + uploaded coexist: never labelled all-synthetic or all-real

    sites = client.get("/api/sites?asset_id=BLR-ROAD&include_stable=true").json()["sites"]
    assert len(sites) >= 3
    hot = max(sites, key=lambda s: s["rpi"])
    assert hot["tier"] in ("WATCH", "ELEVATED", "CRITICAL") and hot["rate_recent_mm_month"] < -1

    st = client.get("/api/data/status").json()
    assert st["workspace_active"] and st["counts"]["assets"] == 5
    uploaded = [d for d in st["datasets"] if d["source_type"] == "upload"]
    assert {d["kind"] for d in uploaded} >= {"assets", "points", "timeseries"}

    # the demo hero site is untouched by the merge
    assert client.get("/api/sites/NH58-DEMO-010").status_code == 200

    reset = client.post("/api/data/reset-demo")
    assert reset.status_code == 200 and reset.json()["workspace_removed"] is True
    after = client.get("/api/meta").json()
    assert after["sites"] == base_sites and after["data_source"] == "DEMO-SYNTHETIC"
    assert client.get("/api/sites/NH58-DEMO-010").status_code == 200


def test_replace_mode_drops_orphaned_timeseries():
    post_file("/api/data/upload", "a.geojson", json.dumps(ASSET).encode())
    client.post("/api/data/regions", json={"region_id": "BLR", "name": "Bengaluru", "parent_id": "IN", "level": "district", "center_lon": 77.59, "center_lat": 12.97, "zoom": 12})
    r = post_file("/api/data/upload", "egms.csv", wide_csv(), default_region="BLR", mode="replace")
    assert r.status_code == 200 and r.json()["applied"]
    body = r.json()
    assert body["written"]["points"]["orphan_timeseries_dropped"] > 0
    assert any("time-series row(s) were removed" in c["message"] for c in body["post_checks"])
    st = client.get("/api/data/status").json()
    assert st["counts"]["points"] == 24  # replace means replace: the demo scatterers are gone
    ts = pd.read_csv(settings.workspace_dir / "insar_timeseries.csv")
    assert set(ts["point_id"]) <= set(pd.read_csv(settings.workspace_dir / "insar_points.csv")["point_id"].astype(str))


def test_bad_file_is_reported_and_changes_nothing():
    r = post_file("/api/data/upload", "junk.csv", b"foo,bar\n1,2\n")
    assert r.status_code == 400 and "Could not tell" in r.json()["detail"]
    r2 = post_file("/api/data/upload", "p.csv", b"point_id,lat,lon\nA,999,80\nB,999,80\nC,999,80\n", kind="points")
    assert r2.status_code == 200 and r2.json()["applied"] is False and r2.json()["ok"] is False
    assert not client.get("/api/data/status").json()["workspace_active"]


def test_upload_guards(monkeypatch):
    assert post_file("/api/data/upload", "x.csv", b"point_id,lat,lon\nA,1,2\n", kind="bogus").status_code == 422
    assert post_file("/api/data/upload", "x.csv", b"", kind="points").status_code == 400
    assert post_file("/api/data/upload", "x.xlsx", b"PK\x03\x04").status_code == 400
    monkeypatch.setattr(settings, "max_upload_mb", 1)
    assert post_file("/api/data/upload", "big.csv", b"a" * (1024 * 1024 + 10), kind="points").status_code == 413


def test_fetch_url_goes_through_validation(monkeypatch):
    monkeypatch.setattr(connectors, "fetch_url", lambda url: ("rain.csv", b"region_id,date,precip_mm\nIN-UK-CHM,2026-10-12,20\nIN-UK-CHM,2026-10-13,30\n"))
    r = client.post("/api/data/fetch-url", json={"url": "https://data.example.org/rain.csv", "kind": "rain"})
    assert r.status_code == 200 and r.json()["applied"] and r.json()["fetched_as"] == "rain.csv"
    ds = client.get("/api/data/status").json()["datasets"]
    assert any(d["source_type"] == "url" and d["source_ref"].endswith("rain.csv") for d in ds)  # provenance records the link

    dry = client.post("/api/data/fetch-url", json={"url": "https://data.example.org/rain.csv", "dry_run": True})
    assert dry.status_code == 200 and "applied" not in dry.json()

    monkeypatch.undo()
    blocked = client.post("/api/data/fetch-url", json={"url": "https://127.0.0.1/secrets.csv"})
    assert blocked.status_code == 400 and "private" in blocked.json()["detail"]


def test_fetch_rain_by_region_updates_provenance_and_label(monkeypatch):
    def fake(lon, lat, region_id, days=60, **kw):
        return pd.DataFrame({"region_id": region_id, "date": pd.date_range("2026-10-01", "2026-10-12"), "precip_mm": 10.0})

    monkeypatch.setattr(connectors, "fetch_rain", fake)
    r = client.post("/api/data/fetch-rain", json={"region_id": "IN-UK-CHM", "days": 30})
    j = r.json()
    assert r.status_code == 200 and j["rows"] == 12 and j["total_mm"] == 120.0
    assert j["overlap_days_in_assessment_window"] > 0
    detail = client.get("/api/sites/NH58-DEMO-010").json()
    assert detail["rain"]["source"] == "observed"  # real rainfall is labelled as such, not as demo
    assert client.post("/api/data/fetch-rain", json={"region_id": "NOPE"}).status_code == 400


def test_fetch_rain_warns_when_it_cannot_affect_the_ranking(monkeypatch):
    def old(lon, lat, region_id, days=60, **kw):
        return pd.DataFrame({"region_id": region_id, "date": pd.date_range("2024-01-01", "2024-01-10"), "precip_mm": 5.0})

    monkeypatch.setattr(connectors, "fetch_rain", old)
    j = client.post("/api/data/fetch-rain", json={"region_id": "IN-UK-CHM"}).json()
    assert j["overlap_days_in_assessment_window"] == 0 and j["warnings"]


def test_templates_and_exports():
    for kind in ("insar", "points", "timeseries", "rain", "regions", "assets"):
        r = client.get(f"/api/data/templates/{kind}")
        assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    assert client.get("/api/data/templates/nope").status_code == 404
    pts = client.get("/api/data/export/points")
    assert pts.status_code == 200 and pts.text.splitlines()[0].startswith("point_id,lat,lon")
    gj = client.get("/api/data/export/assets").json()
    assert len(gj["features"]) == 4
    assert client.get("/api/data/export/nope").status_code == 400


def test_bigquery_actions_fail_clearly_without_credentials():
    r = client.post("/api/data/sync-bigquery")
    assert r.status_code == 400 and "TS_GCP_PROJECT" in r.json()["detail"]


def test_provenance_keeps_demo_entries_until_a_kind_is_replaced():
    client.post("/api/data/regions", json={"region_id": "BLR", "name": "Bengaluru", "parent_id": "IN", "level": "district", "center_lon": 77.59, "center_lat": 12.97, "zoom": 12})
    post_file("/api/data/upload", "a.geojson", json.dumps(ASSET).encode())  # merge: demo assets stay underneath

    by_kind = {}
    for d in client.get("/api/data/status").json()["datasets"]:
        by_kind.setdefault(d["kind"], []).append(d["source_type"])
    assert set(by_kind) == {"points", "timeseries", "rain", "assets", "regions"}
    assert sorted(by_kind["assets"]) == ["demo", "upload"]  # both are in use
    assert by_kind["points"] == ["demo"]

    post_file("/api/data/upload", "egms.csv", wide_csv(), default_region="BLR", mode="replace")
    after = {}
    for d in client.get("/api/data/status").json()["datasets"]:
        after.setdefault(d["kind"], []).append(d["source_type"])
    assert "demo" not in after["points"]  # replaced: the demo scatterers are gone, so are not listed
