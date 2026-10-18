"""Failure modes found in the end-to-end audit: partial writes, concurrent writers, hostile input."""
from __future__ import annotations

import threading
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.services.data import ingest, repo as repo_mod, service
from app.services.data.service import DataError

client = TestClient(app)


def _points_csv(ids, region="IN-UK-CHM"):
    rows = "\n".join(f"{i},30.5{n % 9},79.5{n % 9},-3.0,0.8,{region}" for n, i in enumerate(ids))
    return ("point_id,lat,lon,velocity_mm_yr,coherence,region_id\n" + rows + "\n").encode()


# ---- all-or-nothing imports ----------------------------------------------------------------------------


def test_failed_import_leaves_the_workspace_exactly_as_it_was(workspace, monkeypatch):
    service.ingest_file("a.csv", _points_csv(["BASE1", "BASE2"]), "points", "merge", None)
    before = repo_mod.get_repo().points().copy()

    real_write = repo_mod.LocalRepo.write

    def fail_on_timeseries(self, kind, payload, mode="merge"):
        if kind == "timeseries":
            raise RuntimeError("disk full")
        return real_write(self, kind, payload, mode)

    monkeypatch.setattr(repo_mod.LocalRepo, "write", fail_on_timeseries)
    wide = (
        "pid,latitude,longitude,mean_velocity,temporal_coherence,20260105,20260117,20260129\n"
        "WIDE1,30.51,79.51,-4.0,0.8,0,-0.4,-0.9\nWIDE2,30.52,79.52,-1.0,0.9,0,0.1,0.0\n"
    ).encode()
    with pytest.raises(RuntimeError):
        service.ingest_file("wide.csv", wide, "insar", "merge", "IN-UK-CHM")

    monkeypatch.undo()
    repo_mod.get_repo.cache_clear()
    after = repo_mod.get_repo().points()
    assert list(after["point_id"]) == list(before["point_id"])  # WIDE points were rolled back
    assert not repo_mod._backup_dir().exists()


def test_rollback_when_no_workspace_existed_before(workspace):
    assert not repo_mod.workspace_exists()
    with pytest.raises(ValueError):
        with repo_mod.workspace_transaction():
            repo_mod.ensure_workspace()
            raise ValueError("boom")
    assert not Path(settings.workspace_dir).exists()


def test_interrupted_import_is_recovered_from_the_backup(workspace):
    service.ingest_file("a.csv", _points_csv(["KEEP1"]), "points", "merge", None)
    ws = Path(settings.workspace_dir)
    import shutil

    shutil.copytree(ws, repo_mod._backup_dir())  # what a crash mid-write leaves behind
    (ws / "insar_points.csv").write_text("corrupt,half,written\n", encoding="utf-8")
    assert repo_mod.recover_workspace() is True
    assert "KEEP1" in set(pd.read_csv(ws / "insar_points.csv", dtype=str)["point_id"])
    assert not repo_mod._backup_dir().exists()
    assert repo_mod.recover_workspace() is False


def test_concurrent_imports_do_not_lose_each_others_rows(workspace):
    errors: list[Exception] = []

    def worker(n: int):
        try:
            service.ingest_file(f"p{n}.csv", _points_csv([f"T{n}-{k}" for k in range(5)]), "points", "merge", None)
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert not errors, errors
    ids = set(repo_mod.get_repo().points()["point_id"].astype(str))
    expected = {f"T{n}-{k}" for n in range(8) for k in range(5)}
    assert expected <= ids


# ---- hostile input ----------------------------------------------------------------------------------------


@pytest.mark.parametrize("depth", [5_000, 200_000])
def test_deeply_nested_json_is_a_clean_400(depth):
    r = client.post("/api/data/validate", files={"file": ("x.geojson", b"[" * depth)})
    assert r.status_code == 400
    assert "nested" in r.json()["detail"] or "JSON" in r.json()["detail"]
    assert client.get("/healthz").status_code == 200  # the server survived


@pytest.mark.parametrize("name,expected", [
    ("../../etc/passwd", "passwd"),
    ("C:\\Users\\x\\data.csv", "data.csv"),
    ("a<b>.csv", "ab.csv"),("a<script>x</script>.csv", "script.csv"),
    ("evil\x00\x1b[31m.csv", "evil[31m.csv"),
    ("", "upload"),
    ("x" * 500 + ".csv", "x" * 120),
])
def test_filenames_are_cleaned_before_they_become_provenance(name, expected):
    assert ingest.clean_filename(name) == expected


def test_unprintable_names_never_reach_the_registry(workspace):
    service.ingest_file("../../evil\x1b[31m.csv", _points_csv(["Z1"]), "points", "merge", None)
    names = [d["name"] for d in service.status()["datasets"]]
    assert all("/" not in n and "\x1b" not in n and ".." not in n.split("evil")[0] for n in names)


@pytest.mark.parametrize("path", [
    "/api/sites?limit=-5", "/api/sites?limit=0", "/api/points?bbox=0,0,1,1&limit=-1", "/api/points?bbox=0,0,1,1&limit=0",
])
def test_non_positive_limits_are_rejected_not_silently_misread(path):
    assert client.get(path).status_code == 422


def test_bad_bbox_values_are_client_errors():
    for bb in ("1,2,3", "a,b,c,d", "1,2,3,4,5"):
        assert client.get("/api/sites", params={"bbox": bb}).status_code == 400
    assert client.get("/api/sites", params={"bbox": "nan,nan,nan,nan"}).status_code == 200  # selects nothing, no crash


def test_unknown_region_on_list_endpoints_is_404_not_empty():
    for path in ("/api/sites", "/api/corridors"):
        r = client.get(path, params={"region": "NOPE"})
        assert r.status_code == 404
        assert "Unknown region" in r.json()["detail"]
    # A real region still filters (may be empty of sites; must not 404).
    ok = client.get("/api/sites", params={"region": "IN-UK-CHM"})
    assert ok.status_code == 200 and "sites" in ok.json()
    assert client.get("/api/corridors", params={"region": "IN-UK-CHM"}).status_code == 200


def test_unknown_api_paths_are_json_404_not_the_app_shell():
    r = client.get("/api/definitely-not-a-route")
    assert r.status_code == 404
    assert "html" not in r.headers.get("content-type", "")


def test_mode_must_be_known(workspace):
    with pytest.raises(DataError):
        service.ingest_file("a.csv", _points_csv(["Q1"]), "points", "obliterate", None)


def test_control_characters_never_reach_stored_region_names(workspace):
    region = service.add_region({"name": "Okay\x00 Dis\x07trict\u202e", "center_lon": 79.0, "center_lat": 30.0, "level": "district\x00"})
    assert region["name"].isprintable() and "\x00" not in region["name"]
    assert region["name"] == "Okay District"
    assert region["level"] == "district"


@pytest.mark.parametrize("raw,expected", [("a\tb\nc", "a b c"), ("  x   y ", "x y"), ("\x00\x1f", ""), ("\u200bzero", "zero")])
def test_clean_text(raw, expected):
    assert ingest.clean_text(raw) == expected


def test_reset_to_demo_keeps_public_dataset_provenance(workspace):
    from app.services.data.state import get_state

    get_state().reset_datasets([{"dataset_id": "public-x", "kind": "events", "name": "x", "source_type": "public", "source_ref": "u", "rows": 1, "mode": "cache", "notes": [], "added_at": "now"}])
    service.add_region({"name": "Temp", "center_lon": 79.0, "center_lat": 30.0})
    service.reset_to_demo()
    kept = [d["dataset_id"] for d in get_state().list_datasets()]
    assert kept == ["public-x"]


class _Req:
    def __init__(self, xff: str | None, host: str = "10.0.0.9"):
        self.headers = {"x-forwarded-for": xff} if xff else {}
        self.client = type("C", (), {"host": host})()


def test_client_ip_ignores_forwarded_header_unless_proxy_is_trusted(monkeypatch):
    from app.core.net import client_ip

    monkeypatch.setattr(settings, "trust_proxy", False)
    assert client_ip(_Req("6.6.6.6")) == "10.0.0.9"


def test_client_ip_behind_proxy_uses_the_entry_the_proxy_appended(monkeypatch):
    from app.core.net import client_ip

    monkeypatch.setattr(settings, "trust_proxy", True)
    monkeypatch.setattr(settings, "proxy_hops", 1)
    # An attacker prepends a forged address; the trusted proxy appends the real one on the right.
    assert client_ip(_Req("1.2.3.4, 203.0.113.7")) == "203.0.113.7"
    monkeypatch.setattr(settings, "proxy_hops", 2)
    assert client_ip(_Req("1.2.3.4, 203.0.113.7, 10.1.1.1")) == "203.0.113.7"
    assert client_ip(_Req(None)) == "10.0.0.9"  # no header at all: fall back to the socket peer


def test_requests_work_with_proxy_trust_switched_on(monkeypatch):
    monkeypatch.setattr(settings, "trust_proxy", True)
    with TestClient(app) as c:
        r = c.get("/api/meta", headers={"X-Forwarded-For": "198.51.100.5", "X-Forwarded-Proto": "https"})
        assert r.status_code == 200


def test_rate_limiter_memory_is_bounded_even_when_every_key_is_active(monkeypatch):
    from app.core import ratelimit

    ratelimit.reset()
    monkeypatch.setattr(ratelimit, "_MAX_KEYS", 100)
    for i in range(500):  # 500 distinct clients, all inside their window, so none is "idle"
        assert ratelimit.allow(f"client-{i}", 5, 60)
    assert len(ratelimit._hits) <= 101
    # a client that is still being limited stays limited (the newest keys are the ones kept)
    for _ in range(5):
        ratelimit.allow("busy", 5, 60)
    assert ratelimit.allow("busy", 5, 60) is False
    ratelimit.reset()
