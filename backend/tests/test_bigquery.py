"""BigQuery backend, verified offline.

What is proven here: the SQL is syntactically valid BigQuery, only uses approved spatial functions, matches the
declared schema; the loader is idempotent and cleans up; a BigQuery-backed repository produces *exactly* the
same analysis as the local one; the setup CLI previews without credentials; errors are actionable.

What is NOT proven here (needs a real project): execution of the SQL in BigQuery, IAM, and cost. Those are
covered by docs/BIGQUERY.md and the live smoke checklist.
"""
from __future__ import annotations

import io
import json

import pandas as pd
import pytest
import sqlglot
from fake_bq import FakeRunner
from fastapi.testclient import TestClient
from sqlglot import exp

from app.core.config import settings
from app.main import app
from app.services import runtime
from app.services.bq import client as bqc
from app.services.bq import loader, segments, sql
from app.services.bq import setup as bq_setup
from app.services.bq.repo import BigQueryRepo
from app.services.bq.schema import TABLES, setup_statements
from app.services.bq.state import BigQueryState
from app.services.data import repo as repo_mod
from app.services.data import state as state_mod
from app.services.data.generate_demo import generate
from app.services.data.repo import LocalRepo
from app.services.detection import pipeline
from app.services.detection.engine import assign_chainage, CHAINAGE_BIN_M
from app.core.config import profile_for

P, D = "test-project", "terrasentinel"
ALLOWED_ST = {"ST_GEOGPOINT", "ST_GEOGFROMGEOJSON", "ST_GEOGFROMTEXT", "ST_DWITHIN", "ST_DISTANCE"}


@pytest.fixture(scope="module", autouse=True)
def _demo():
    generate(settings.data_dir)
    yield


@pytest.fixture(scope="module")
def loaded_fake():
    fake = FakeRunner()
    loader.sync_repo(LocalRepo(settings.data_dir), fake)
    return fake


# ------------------------------------------------------------------------------- SQL text


def all_sql() -> list[tuple[str, str]]:
    return [(f"ddl:{i}", s) for i, s in enumerate(setup_statements(P, D, "US"))] + sql.all_statements(P, D)


@pytest.mark.parametrize("label,statement", all_sql(), ids=lambda v: v if isinstance(v, str) and ":" in v and len(v) < 40 else None)
def test_every_statement_parses_as_bigquery(label, statement):
    tree = sqlglot.parse_one(statement, read="bigquery")
    if label.startswith("truncate"):
        return  # TRUNCATE TABLE is carried as a raw command by sqlglot; the text is trivially checked below
    assert not isinstance(tree, exp.Command), f"{label} was not fully understood by the BigQuery parser"


def test_truncate_statements_are_exactly_truncate_table():
    for label, s in sql.all_statements(P, D):
        if label.startswith("truncate"):
            assert s.startswith("TRUNCATE TABLE `test-project.terrasentinel.")


def test_only_approved_spatial_functions_are_used():
    """BigQuery has no linear referencing: guard against someone 'fixing' chainage with a function that does not exist."""
    used: set[str] = set()
    for _, s in all_sql():
        for node in sqlglot.parse_one(s, read="bigquery").find_all(exp.Anonymous, exp.Func):
            name = (node.name if isinstance(node, exp.Anonymous) else node.sql_name()).upper()
            if name.startswith("ST_"):
                used.add(name)
        used |= {m for m in ("ST_LINELOCATEPOINT", "ST_LINESUBSTRING") if m in s.upper()}
    assert used and used <= ALLOWED_ST, used - ALLOWED_ST


def test_schema_is_internally_consistent():
    for t in TABLES.values():
        names = [n for n, _ in t.columns]
        assert len(names) == len(set(names))
        assert set(t.key) <= set(names), t.name
        assert set(t.cluster_by) <= set(names), t.name
        if t.partition_by:
            assert dict(t.columns)[t.partition_by] == "DATE", t.name
        assert set(t.computed) <= set(names)
        for col in t.computed:
            assert dict(t.columns)[col] == "GEOGRAPHY"
    # big observation tables must be partitioned: a daily refresh must not scan the archive
    assert TABLES["timeseries"].partition_by == "date" and TABLES["rain"].partition_by == "date"
    assert "geom" in TABLES["points"].cluster_by  # spatial pruning


def test_merge_sql_matches_the_schema():
    for t in TABLES.values():
        tree = sqlglot.parse_one(sql.merge_sql(t, P, D, f"{t.name}_stg"), read="bigquery")
        inserted = [c.name for c in tree.find(exp.Insert).this.expressions] if tree.find(exp.Insert) else []
        whens = tree.args["whens"].expressions if "whens" in tree.args else []
        insert_cols = [c.name for w in whens for c in (w.args.get("then").this.expressions if isinstance(w.args.get("then"), exp.Insert) and w.args["then"].this else [])]
        assert (inserted or insert_cols) == [n for n, _ in t.columns], t.name
        k = t.key[0]
        assert f"T.`{k}` = S.`{k}`" in sql.merge_sql(t, P, D, "stg")


def test_geography_is_built_in_sql_not_in_python():
    s = sql.merge_sql(TABLES["points"], P, D, "points_stg")
    assert "ST_GEOGPOINT(S.lon, S.lat)" in s
    assert "ST_GEOGFROMGEOJSON(S.geometry_json)" in sql.merge_sql(TABLES["assets"], P, D, "a_stg")


def test_reads_prefilter_to_asset_corridors_in_bigquery():
    q = sql.read_queries(P, D)
    assert "v_point_assignment" in q["points"] and "v_point_assignment" in q["timeseries"]
    view = dict(__import__("app.services.bq.schema", fromlist=["x"]).view_ddls(P, D))["v_point_assignment"]
    assert "ST_DWITHIN(p.geom, s.geom, s.buffer_m)" in view and "ROW_NUMBER()" in view


# ------------------------------------------------------------------------------- setup CLI


def test_setup_dry_run_needs_no_credentials(capsys, monkeypatch):
    monkeypatch.setattr(settings, "gcp_project", "")
    assert bq_setup.main(["--dry-run"]) == 0
    captured = capsys.readouterr()
    out, err = captured.out, captured.err
    assert out.count("CREATE TABLE IF NOT EXISTS") == len(TABLES)
    assert "CREATE SCHEMA IF NOT EXISTS" in out and "v_act_list" in out and "YOUR_PROJECT" in out
    assert "TS_GCP_PROJECT is empty" in err and "YOUR_PROJECT" in err


def test_setup_without_project_explains_itself(capsys, monkeypatch):
    monkeypatch.setattr(settings, "gcp_project", "")
    assert bq_setup.main([]) == 2
    assert "TS_GCP_PROJECT" in capsys.readouterr().err


# ------------------------------------------------------------------------------- segments


def test_segments_agree_with_the_engine_chainage_bins():
    """The SQL assigns a point to the nearest pre-cut segment; the engine measures true chainage. They must agree."""
    rep = LocalRepo(settings.data_dir)
    pts = rep.points()
    total = agree = 0
    for a in rep.assets():
        prof = profile_for(a.asset_type)
        engine = assign_chainage(pts, a, prof)
        segs = segments.segment_geometry(a.geometry, a.asset_type, None, a.asset_id)
        assert segs[0]["chainage_start_m"] == 0 and abs(segs[-1]["chainage_end_m"] - segs[-1]["chainage_end_m"]) < 1e-9
        assert all(abs(s["chainage_end_m"] - s["chainage_start_m"]) <= CHAINAGE_BIN_M + 1e-6 for s in segs)
        # emulate nearest-segment assignment
        from shapely import wkt
        import numpy as np

        for r in engine.itertuples():
            best, best_d = None, 1e18
            for s in segs:
                line = wkt.loads(s["geom_wkt"])
                mx, my = 111_320.0 * np.cos(np.radians(line.centroid.y)), 110_540.0
                from shapely.geometry import Point

                d = line.distance(Point(r.lon, r.lat))  # degrees; only the argmin matters
                d_m = d * ((mx + my) / 2)
                if d_m < best_d:
                    best, best_d = s["seg_idx"], d_m
            total += 1
            agree += int(best == int(r.chainage_m // CHAINAGE_BIN_M))
    assert total > 500
    assert agree / total >= 0.97, f"only {agree}/{total} agree"


def test_segment_rows_cover_the_whole_line():
    a = LocalRepo(settings.data_dir).assets()[0]
    rows = segments.segment_geometry(a.geometry, a.asset_type, None, a.asset_id)
    assert [r["seg_idx"] for r in rows] == list(range(len(rows)))
    assert all(r["buffer_m"] == profile_for(a.asset_type).buffer_m for r in rows)
    assert all(r["geom_wkt"].startswith("LINESTRING") for r in rows)


# ------------------------------------------------------------------------------- loader


def test_sync_loads_every_table_and_cleans_up_staging(loaded_fake):
    T = loaded_fake.tables
    local = LocalRepo(settings.data_dir)
    assert len(T["points"]) == len(local.points()) and len(T["timeseries"]) == len(local.timeseries())
    assert len(T["assets"]) == 4 and len(T["asset_segments"]) > 20 and len(T["regions"]) == 7
    assert loaded_fake.staging_tables() == []  # no orphaned staging tables left in the dataset


def test_merge_is_idempotent_and_updates_in_place():
    fake = FakeRunner()
    pts = LocalRepo(settings.data_dir).points().head(50)
    a = loader.upsert("points", pts, "merge", fake)
    b = loader.upsert("points", pts, "merge", fake)  # same file uploaded twice
    assert a["total"] == b["total"] == 50
    changed = pts.copy()
    changed["velocity_mm_yr"] = -99.0
    loader.upsert("points", changed, "merge", fake)
    assert len(fake.tables["points"]) == 50 and set(fake.tables["points"]["velocity_mm_yr"]) == {-99.0}
    assert fake.staging_tables() == []


def test_replace_swaps_content_and_drops_orphan_timeseries():
    fake = FakeRunner()
    local = LocalRepo(settings.data_dir)
    loader.upsert("points", local.points(), "merge", fake)
    loader.upsert("timeseries", local.timeseries(), "merge", fake)
    keep = local.points().head(10)
    loader.upsert("points", keep, "replace", fake)
    assert len(fake.tables["points"]) == 10
    assert set(fake.tables["timeseries"]["point_id"]) <= set(keep["point_id"])  # no orphans


def test_reuploading_an_asset_rebuilds_its_segments_without_duplicates():
    fake = FakeRunner()
    feats = LocalRepo(settings.data_dir).assets_geojson()["features"]
    loader.upsert("assets", feats, "merge", fake)
    n1 = len(fake.tables["asset_segments"])
    loader.upsert("assets", feats[:1], "merge", fake)
    assert len(fake.tables["asset_segments"]) == n1
    assert fake.tables["asset_segments"].duplicated(["asset_id", "seg_idx"]).sum() == 0


def test_a_failed_statement_still_drops_staging():
    class Boom(FakeRunner):
        def execute(self, sql, params=None, label=None):
            if label and label.startswith("merge:"):
                raise bqc.BigQueryUnavailable("boom")
            super().execute(sql, params, label)

    fake = Boom()
    with pytest.raises(bqc.BigQueryUnavailable):
        loader.upsert("regions", LocalRepo(settings.data_dir).regions(), "merge", fake)
    assert fake.staging_tables() == []


# ------------------------------------------------------------------------------- repository equivalence


def _bigquery_backend(monkeypatch, fake):
    monkeypatch.setattr(settings, "data_backend", "bigquery")
    bqc.set_runner(fake)
    state_mod.clear_state_cache()
    runtime.refresh_all()


def _restore():
    bqc.set_runner(None)
    state_mod.clear_state_cache()
    runtime.refresh_all()


def test_bigquery_repo_produces_exactly_the_same_analysis_as_local(monkeypatch, loaded_fake):
    runtime.refresh_all()
    local_sites = {s.site_id: (s.tier, s.rpi, s.state, s.outlook.eta_low_days, s.outlook.eta_high_days) for s in pipeline.run_pipeline()}
    local_counts = repo_mod.get_repo().counts()
    local_source = repo_mod.get_repo().data_source()

    _bigquery_backend(monkeypatch, loaded_fake)
    try:
        repo = repo_mod.get_repo()
        assert isinstance(repo, BigQueryRepo) and repo.backend == "bigquery"
        bq_sites = {s.site_id: (s.tier, s.rpi, s.state, s.outlook.eta_low_days, s.outlook.eta_high_days) for s in pipeline.run_pipeline()}
        assert bq_sites == local_sites
        assert repo.counts() == local_counts and repo.data_source() == local_source
        assert [r["region_id"] for r in repo.regions()] == sorted(r["region_id"] for r in LocalRepo(settings.data_dir).regions())
        assert {f["properties"]["asset_id"] for f in repo.assets_geojson()["features"]} == {a.asset_id for a in LocalRepo(settings.data_dir).assets()}
    finally:
        monkeypatch.undo()
        _restore()


def test_reads_are_cached_until_ttl_and_writes_invalidate(loaded_fake):
    repo = BigQueryRepo(loaded_fake, ttl_s=300)
    before = loaded_fake.count_reads("read:points")
    repo.points(), repo.points(), repo.points()
    assert loaded_fake.count_reads("read:points") == before + 1
    repo.write("rain", LocalRepo(settings.data_dir).rain().head(5), "merge")
    repo.points()
    assert loaded_fake.count_reads("read:points") == before + 2  # write invalidated the cache
    zero = BigQueryRepo(loaded_fake, ttl_s=0)
    zero.points(), zero.points()
    assert loaded_fake.count_reads("read:points") == before + 4


def test_only_corridor_points_leave_the_warehouse(loaded_fake):
    fake = FakeRunner()
    local = LocalRepo(settings.data_dir)
    far = local.points().head(5).copy()
    far["point_id"] = [f"FAR{i}" for i in range(5)]
    far["lat"], far["lon"] = 60.0, 10.0  # nowhere near any asset
    loader.upsert("regions", local.regions(), "merge", fake)
    loader.upsert("assets", local.assets_geojson()["features"], "merge", fake)
    loader.upsert("points", pd.concat([local.points(), far]), "merge", fake)
    loader.upsert("timeseries", local.timeseries(), "merge", fake)
    repo = BigQueryRepo(fake)
    ids = set(repo.points()["point_id"])
    assert not (ids & set(far["point_id"]))
    assert len(fake.tables["points"]) == len(local.points()) + 5  # stored, just not pulled into the pipeline
    assert set(repo.timeseries()["point_id"]) <= ids


# ------------------------------------------------------------------------------- state


def test_bigquery_state_round_trips():
    fake = FakeRunner()
    st = BigQueryState(fake)
    st.add_dataset({"dataset_id": "d1", "kind": "points", "name": "x.csv", "source_type": "upload", "source_ref": "x.csv", "rows": 5, "date_min": None, "date_max": "2026-01-02", "mode": "merge", "notes": ["a", "b"], "added_at": "2026-02-01T10:00:00+00:00"})
    ds = st.list_datasets()
    assert ds[0]["notes"] == ["a", "b"] and ds[0]["date_max"] == "2026-01-02" and ds[0]["date_min"] is None
    st.add_action({"alert_id": "a|b|c", "action": "acknowledge", "actor": "ram", "note": "", "assignee": None, "at": "2026-02-01T10:00:00+00:00"})
    st.add_action({"alert_id": "a|b|c", "action": "assign", "actor": "ram", "note": "n", "assignee": "Team B", "at": "2026-02-01T11:00:00+00:00"})
    acts = st.list_actions()
    assert [a["action"] for a in acts] == ["acknowledge", "assign"] and acts[0]["assignee"] is None and acts[1]["assignee"] == "Team B"


def test_snapshot_save_is_idempotent_per_day():
    fake = FakeRunner()
    st = BigQueryState(fake)
    rows = [
        {"site_id": "S1", "asset_id": "A", "region_id": "R", "tier": "CRITICAL", "state": "accelerating", "rpi": 80.0, "rate_mm_month": -4.0, "eta_low_days": 30, "eta_high_days": 50, "confidence": 0.9},
        {"site_id": "S2", "asset_id": "A", "region_id": "R", "tier": "STABLE", "state": "stable", "rpi": 1.0, "rate_mm_month": 0.1, "eta_low_days": None, "eta_high_days": None, "confidence": 0.9},
    ]
    st.save_snapshot("2026-10-16", rows)
    st.save_snapshot("2026-10-16", rows)  # the daily job re-ran
    assert len(fake.tables["site_snapshots"]) == 2
    assert st.list_snapshots()[0]["sites"] == 2


# ------------------------------------------------------------------------------- API in BigQuery mode


def test_api_runs_on_the_bigquery_backend_and_writes_through(monkeypatch):
    fake = FakeRunner()
    loader.sync_repo(LocalRepo(settings.data_dir), fake)
    _bigquery_backend(monkeypatch, fake)
    try:
        c = TestClient(app)
        meta = c.get("/api/meta").json()
        assert meta["backend"] == "bigquery" and meta["sites"] == 87
        assert c.get("/api/sites/NH58-DEMO-010").json()["tier"] == "CRITICAL"

        before = len(fake.tables["rain"])
        csv = b"region_id,date,precip_mm\nIN-UK-CHM,2026-10-14,12\nIN-UK-CHM,2026-10-15,30\n"
        r = c.post("/api/data/upload", files={"file": ("rain.csv", io.BytesIO(csv), "text/csv")}, data={"kind": "rain"})
        assert r.status_code == 200 and r.json()["applied"], r.text
        assert len(fake.tables["rain"]) >= before and fake.staging_tables() == []
        assert c.get("/api/data/status").json()["backend"] == "bigquery"
        assert any(d["source_type"] == "upload" for d in c.get("/api/data/status").json()["datasets"])  # registry written to BigQuery

        reset = c.post("/api/data/reset-demo")
        assert reset.status_code == 400 and "BigQuery" in reset.json()["detail"]
    finally:
        monkeypatch.undo()
        _restore()


def test_alert_actions_persist_in_bigquery_mode(monkeypatch):
    fake = FakeRunner()
    loader.sync_repo(LocalRepo(settings.data_dir), fake)
    _bigquery_backend(monkeypatch, fake)
    try:
        c = TestClient(app)
        aid = c.get("/api/alerts?severity=critical").json()["alerts"][0]["alert_id"]
        r = c.post("/api/alerts/action", json={"alert_id": aid, "action": "assign", "assignee": "Team B", "actor": "ram"})
        assert r.status_code == 200 and r.json()["status"] == "assigned"
        assert len(fake.tables["alert_actions"]) == 1
    finally:
        monkeypatch.undo()
        _restore()


# ------------------------------------------------------------------------------- client / errors


def test_runner_without_project_is_unavailable_not_a_crash(monkeypatch):
    monkeypatch.setattr(settings, "gcp_project", "")
    with pytest.raises(bqc.BigQueryUnavailable, match="TS_GCP_PROJECT"):
        bqc.BQRunner()
    assert bqc.probe()["reachable"] is False


def test_runner_without_dataset_is_unavailable(monkeypatch):
    monkeypatch.setattr(settings, "gcp_project", "demo-proj")
    monkeypatch.setattr(settings, "bq_dataset", "")
    with pytest.raises(bqc.BigQueryUnavailable, match="TS_BQ_DATASET"):
        bqc.BQRunner()


@pytest.mark.parametrize(
    "exc,needle",
    [
        (type("DefaultCredentialsError", (Exception,), {})("x"), "credentials"),
        (Exception("403 Access Denied: Table"), "Access denied"),
        (Exception("404 Not found: Dataset"), "setup"),
        (Exception("Query exceeded limit for bytes billed: 1"), "cost guard"),
    ],
)
def test_errors_are_translated_to_actions(exc, needle):
    assert needle in bqc._explain(exc)


def test_status_reports_bigquery_as_not_configured_by_default(monkeypatch):
    monkeypatch.setattr(settings, "gcp_project", "")
    s = TestClient(app).get("/api/data/status").json()["bigquery"]
    assert s["configured"] is False and s["reachable"] is False and "TS_GCP_PROJECT" in s["detail"]


def test_status_names_half_configured_bigquery_backend(monkeypatch):
    from app.services.data import service as data_service

    monkeypatch.setattr(settings, "gcp_project", "")
    monkeypatch.setattr(settings, "data_backend", "bigquery")
    s = data_service.bigquery_status()
    assert s["active"] is True and s["configured"] is False
    assert "TS_DATA_BACKEND=bigquery" in s["detail"] and "TS_GCP_PROJECT" in s["detail"]


def test_readyz_rejects_bigquery_without_project(monkeypatch):
    monkeypatch.setattr(settings, "gcp_project", "")
    monkeypatch.setattr(settings, "data_backend", "bigquery")
    r = TestClient(app).get("/readyz")
    assert r.status_code == 503
    assert "TS_GCP_PROJECT" in r.json()["reason"]


# ------------------------------------------------------------------------------- daily job


def test_daily_job_is_idempotent_locally(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "state_dir", tmp_path / "state")
    state_mod.clear_state_cache()
    runtime.refresh_all()
    from app.jobs import daily

    a = daily.run()
    b = daily.run()
    assert a["snapshot_rows"] == b["snapshot_rows"] == 87 and a["tiers"]["CRITICAL"] == 3
    snaps = state_mod.get_state().list_snapshots()
    assert len(snaps) == 1 and snaps[0]["sites"] == 87  # re-run overwrote, did not duplicate
    state_mod.clear_state_cache()


def test_daily_job_writes_a_bigquery_snapshot(monkeypatch):
    fake = FakeRunner()
    loader.sync_repo(LocalRepo(settings.data_dir), fake)
    _bigquery_backend(monkeypatch, fake)
    try:
        from app.jobs import daily

        daily.run()
        daily.run()
        assert len(fake.tables["site_snapshots"]) == 87
    finally:
        monkeypatch.undo()
        _restore()
