"""BigQuery connection doctor: every failure mode names a cause and the exact next step. Offline, with a fake client."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core.config import settings
from app.services.bq import doctor
from app.services.bq import client as bqc
from app.services.bq.schema import TABLES


class FakeBQ:
    def __init__(self, *, query_error=None, dataset_error=None, location="US", tables=None, rows=1000, write_error=None):
        self.query_error, self.dataset_error, self.location = query_error, dataset_error, location
        self.tables = list(TABLES) if tables is None else tables
        self.rows, self.write_error = rows, write_error
        self.queries: list[str] = []

    def query(self, sql, job_config=None):
        self.queries.append(sql)
        assert job_config is not None and job_config.dry_run, "the doctor must never run a real query"
        if sql.startswith("CREATE") and self.write_error:
            raise self.write_error
        if self.query_error and not sql.startswith("CREATE"):
            raise self.query_error
        return SimpleNamespace(total_bytes_processed=0)

    def get_dataset(self, ref, timeout=None):
        if self.dataset_error:
            raise self.dataset_error
        return SimpleNamespace(location=self.location)

    def list_tables(self, ds, max_results=None):
        return [SimpleNamespace(table_id=t) for t in self.tables]

    def get_table(self, ref):
        return SimpleNamespace(num_rows=self.rows)


@pytest.fixture(autouse=True)
def cfg(monkeypatch):
    monkeypatch.setattr(settings, "gcp_project", "demo-proj")
    monkeypatch.setattr(settings, "bq_location", "US")
    monkeypatch.setattr(settings, "data_backend", "bigquery")


def by_id(checks):
    return {c.id: c for c in checks}


def test_everything_ready():
    checks = doctor.run_checks(FakeBQ(), creds_description="service account ci@demo-proj.iam")
    assert {c.status for c in checks} == {doctor.PASS}
    s = doctor.summarise(checks)
    assert s["state"] == "ready" and "connected" in s["headline"]


def test_the_doctor_only_ever_dry_runs():
    fake = FakeBQ()
    doctor.run_checks(fake)
    assert fake.queries and all(q.startswith(("SELECT 1", "CREATE TABLE IF NOT EXISTS")) for q in fake.queries)


def test_missing_credentials_explains_that_a_gemini_key_is_not_enough(monkeypatch):
    def none():
        raise bqc.BigQueryUnavailable("No Google credentials found.")

    monkeypatch.setattr(doctor, "load_credentials", none)
    checks = doctor.run_checks()
    c = by_id(checks)["credentials"]
    assert c.status == doctor.FAIL and "Gemini API key" in c.fix and "gcloud auth application-default login" in c.fix
    assert checks[-1].id == "credentials"  # stops there: later checks would only add noise
    assert doctor.summarise(checks)["state"] == "blocked"


def test_missing_project_is_reported(monkeypatch):
    monkeypatch.setattr(settings, "gcp_project", "")
    checks = doctor.run_checks(FakeBQ(), project="")
    # BigQuery mode with an empty project fails immediately on mode (not half-checked).
    c = by_id(checks)["mode"]
    assert c.status == doctor.FAIL and "TS_GCP_PROJECT" in (c.detail + c.fix)
    assert "project" not in by_id(checks)
    assert doctor.summarise(checks)["state"] == "blocked"


def test_missing_project_in_local_mode_is_still_named(monkeypatch):
    monkeypatch.setattr(settings, "data_backend", "local")
    monkeypatch.setattr(settings, "gcp_project", "")
    c = by_id(doctor.run_checks(FakeBQ(), project=""))["project"]
    assert c.status == doctor.FAIL and "TS_GCP_PROJECT" in c.fix


@pytest.mark.parametrize(
    "error,needle",
    [
        (Exception("403 BigQuery API has not been used in project demo-proj before or it is disabled"), "gcloud services enable"),
        (Exception("403 Access Denied: User does not have bigquery.jobs.create"), "roles/bigquery.jobUser"),
        (Exception("404 Not found: Project nope"), "project ID"),
        (Exception("Billing has not been enabled for this project"), "sandbox"),
    ],
)
def test_api_failures_name_the_fix(error, needle):
    c = by_id(doctor.run_checks(FakeBQ(query_error=error)))["api"]
    assert c.status == doctor.FAIL and needle in (c.fix + c.detail)


def test_missing_dataset_points_to_setup():
    checks = by_id(doctor.run_checks(FakeBQ(dataset_error=Exception("404 Not found: Dataset demo-proj:terrasentinel"))))
    assert checks["dataset"].status == doctor.FAIL and "bq.setup" in checks["dataset"].fix


def test_location_mismatch_names_the_right_setting():
    c = by_id(doctor.run_checks(FakeBQ(location="EU")))["dataset"]
    assert c.status == doctor.FAIL and "TS_BQ_LOCATION=EU" in c.fix


def test_missing_tables_are_listed():
    names = [t for t in TABLES if t not in ("regions", "alert_actions")]
    c = by_id(doctor.run_checks(FakeBQ(tables=names)))["tables"]
    assert c.status == doctor.FAIL and "regions" in c.detail and "alert_actions" in c.detail


def test_empty_tables_suggest_loading_demo_data():
    c = by_id(doctor.run_checks(FakeBQ(rows=0)))["data"]
    assert c.status == doctor.WARN and "--load-demo" in c.fix


def test_no_write_permission_is_a_failure_but_unknown_is_a_warning():
    denied = by_id(doctor.run_checks(FakeBQ(write_error=Exception("403 Access Denied"))))["write"]
    assert denied.status == doctor.FAIL and "dataEditor" in denied.fix
    unsure = by_id(doctor.run_checks(FakeBQ(write_error=Exception("Syntax oddity"))))["write"]
    assert unsure.status == doctor.WARN


def test_local_mode_is_a_note_not_a_failure(monkeypatch):
    monkeypatch.setattr(settings, "data_backend", "local")
    s = doctor.summarise(doctor.run_checks(FakeBQ()))
    assert s["state"] == "ready-not-active"


def test_report_never_contains_key_material(monkeypatch, tmp_path):
    key = tmp_path / "key.json"
    key.write_text('{"private_key": "-----BEGIN PRIVATE KEY-----SECRETSECRET", "client_email": "x@y.iam.gserviceaccount.com"}')
    monkeypatch.setattr(settings, "google_credentials_file", str(key))
    with pytest.raises(bqc.BigQueryUnavailable) as e:
        bqc.load_credentials()
    assert "SECRETSECRET" not in str(e.value) and "not a valid" in str(e.value)


def test_credentials_file_that_does_not_exist_is_named_without_its_directory(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "google_credentials_file", str(tmp_path / "secret-dir" / "gone.json"))
    with pytest.raises(bqc.BigQueryUnavailable) as e:
        bqc.load_credentials()
    assert "gone.json" in str(e.value) and "secret-dir" not in str(e.value)


def test_status_probe_is_cached_so_a_bad_config_does_not_slow_every_poll(monkeypatch):
    from app.services.data import service

    calls = []
    monkeypatch.setattr(bqc, "probe", lambda: (calls.append(1), {"reachable": False, "detail": "no creds"})[1])
    service.clear_bigquery_probe()
    for _ in range(5):
        service.bigquery_status()
    assert len(calls) == 1
    service.clear_bigquery_probe()
    service.bigquery_status()
    assert len(calls) == 2
