"""Thin BigQuery runner.

The rest of the package talks to a ``Runner`` (three methods), never to google-cloud-bigquery
directly. That keeps the SQL reviewable, lets tests swap in an in-memory fake, and puts the cost
guard (maximum bytes billed) and error translation in one place.
"""
from __future__ import annotations

from typing import Protocol

import pandas as pd

from app.core.config import settings


class BigQueryUnavailable(RuntimeError):
    """BigQuery is not configured, credentials are missing, or the service is unreachable."""


class Runner(Protocol):
    project: str
    dataset: str

    def execute(self, sql: str, params: dict | None = None, label: str | None = None) -> None: ...

    def query_df(self, sql: str, params: dict | None = None, label: str | None = None) -> pd.DataFrame: ...

    def load_df(self, df: pd.DataFrame, table: str, schema: list[tuple[str, str]], replace: bool = False) -> None: ...


class BQRunner:
    """Real runner. Imports google-cloud-bigquery lazily so the app starts without it configured."""

    def __init__(self, project: str | None = None, dataset: str | None = None, location: str | None = None, client=None):
        self.project = (project if project is not None else settings.gcp_project) or ""
        self.dataset = (dataset if dataset is not None else settings.bq_dataset) or ""
        self.location = location or settings.bq_location
        if not self.project.strip():
            raise BigQueryUnavailable(
                "TS_GCP_PROJECT is not set. Set TS_GCP_PROJECT=your-project-id in backend/.env "
                "(or pass --project). See docs/BIGQUERY.md."
            )
        if not self.dataset.strip():
            raise BigQueryUnavailable("TS_BQ_DATASET is not set. Set TS_BQ_DATASET=terrasentinel in backend/.env.")
        self._client = client

    @property
    def client(self):
        if self._client is None:
            try:
                from google.cloud import bigquery

                creds, _ = load_credentials()
                self._client = bigquery.Client(project=self.project, location=self.location, credentials=creds)
            except Exception as exc:  # noqa: BLE001
                raise BigQueryUnavailable(_explain(exc)) from exc
        return self._client

    def _job_config(self, params: dict | None):
        from google.cloud import bigquery

        cfg = bigquery.QueryJobConfig(maximum_bytes_billed=int(settings.bq_max_gb_billed * 1024**3))
        if params:
            cfg.query_parameters = [_param(k, v) for k, v in params.items()]
        return cfg

    def execute(self, sql: str, params: dict | None = None, label: str | None = None) -> None:
        try:
            self.client.query(sql, job_config=self._job_config(params)).result()
        except BigQueryUnavailable:
            raise
        except Exception as exc:  # noqa: BLE001
            raise BigQueryUnavailable(_explain(exc)) from exc

    def query_df(self, sql: str, params: dict | None = None, label: str | None = None) -> pd.DataFrame:
        try:
            return self.client.query(sql, job_config=self._job_config(params)).result().to_dataframe(create_bqstorage_client=False)
        except BigQueryUnavailable:
            raise
        except Exception as exc:  # noqa: BLE001
            raise BigQueryUnavailable(_explain(exc)) from exc

    def load_df(self, df: pd.DataFrame, table: str, schema: list[tuple[str, str]], replace: bool = False) -> None:
        from google.cloud import bigquery

        cfg = bigquery.LoadJobConfig(
            schema=[bigquery.SchemaField(n, t) for n, t in schema],
            write_disposition="WRITE_TRUNCATE" if replace else "WRITE_APPEND",
        )
        try:
            self.client.load_table_from_dataframe(df, f"{self.project}.{self.dataset}.{table}", job_config=cfg).result()
        except Exception as exc:  # noqa: BLE001
            raise BigQueryUnavailable(_explain(exc)) from exc

    def drop_table(self, table: str) -> None:
        self.execute(f"DROP TABLE IF EXISTS `{self.project}.{self.dataset}.{table}`")


def _param(name: str, value):
    from google.cloud import bigquery

    if isinstance(value, bool):
        return bigquery.ScalarQueryParameter(name, "BOOL", value)
    if isinstance(value, int):
        return bigquery.ScalarQueryParameter(name, "INT64", value)
    if isinstance(value, float):
        return bigquery.ScalarQueryParameter(name, "FLOAT64", value)
    return bigquery.ScalarQueryParameter(name, "STRING", str(value))


def _explain(exc: Exception) -> str:
    """Turn the SDK's long errors into one line an operator can act on."""
    name = exc.__class__.__name__
    text = str(exc)
    if name == "DefaultCredentialsError" or "default credentials" in text.lower():
        return "No Google credentials found. Run `gcloud auth application-default login` or set GOOGLE_APPLICATION_CREDENTIALS."
    if "bytes billed" in text.lower():
        return f"Query blocked by the cost guard (limit {settings.bq_max_gb_billed:g} GB, TS_BQ_MAX_GB_BILLED)."
    if "billingNotEnabled" in text or "Billing has not been enabled" in text:
        return (
            "Billing is not open on this GCP project. BigQuery DDL/load can work in the sandbox, "
            "but DML (MERGE/TRUNCATE/INSERT…SELECT) and Cloud Run need an open billing account. "
            "Reopen billing, then re-run setup --load-demo (or use the sandbox-friendly replace loader)."
        )
    if "403" in text or "Access Denied" in text or "Forbidden" in text:
        return "Access denied: the account needs BigQuery Data Editor and Job User on the project (and open billing for DML)."
    if "404" in text or "Not found" in text:
        return "Dataset or table not found. Run `python -m app.services.bq.setup` first."
    return f"{name}: {text.splitlines()[0][:200]}" if text else name


def load_credentials():
    """Return (credentials, description). ``TS_GOOGLE_CREDENTIALS_FILE`` wins; otherwise Application Default Credentials.

    If ADC is missing (common on Windows before ``gcloud auth application-default login``), fall back to the
    already-authenticated ``gcloud`` user via short-lived access tokens. That covers org policies that block
    service-account key download. The description names the kind of identity but never includes key material.
    """
    scopes = ["https://www.googleapis.com/auth/bigquery"]
    if settings.google_credentials_file:
        from pathlib import Path

        path = Path(settings.google_credentials_file).expanduser()
        if not path.is_file():
            raise BigQueryUnavailable(f"TS_GOOGLE_CREDENTIALS_FILE points to a file that does not exist: {path.name}")
        from google.oauth2 import service_account

        try:
            creds = service_account.Credentials.from_service_account_file(str(path), scopes=scopes)
        except Exception as exc:  # noqa: BLE001
            raise BigQueryUnavailable("TS_GOOGLE_CREDENTIALS_FILE is not a valid service-account key file.") from exc
        return creds, f"service account {creds.service_account_email}"
    import google.auth

    try:
        creds, _project = google.auth.default(scopes=scopes)
    except Exception as adc_exc:  # noqa: BLE001
        try:
            return _gcloud_user_credentials(scopes), "your gcloud user (access token via gcloud auth)"
        except Exception:  # noqa: BLE001
            raise BigQueryUnavailable(_explain(adc_exc)) from adc_exc
    who = getattr(creds, "service_account_email", None)
    kind = f"service account {who}" if who and who != "default" else "your gcloud user (Application Default Credentials)"
    return creds, kind


def _gcloud_user_credentials(scopes: list[str]):
    """Build refreshable credentials from ``gcloud auth print-access-token`` (user already logged in)."""
    import shutil
    import subprocess
    from datetime import datetime, timedelta, timezone

    from google.auth import credentials as ga_credentials
    from google.oauth2 import credentials as oauth2

    gcloud = shutil.which("gcloud.cmd") or shutil.which("gcloud")
    if not gcloud:
        raise BigQueryUnavailable("gcloud CLI not found on PATH; install Google Cloud SDK or set Application Default Credentials.")

    class _GcloudTokenCreds(oauth2.Credentials, ga_credentials.CredentialsWithQuotaProject):
        def refresh(self, request):  # noqa: ARG002
            token = subprocess.check_output([gcloud, "auth", "print-access-token"], text=True, stderr=subprocess.DEVNULL).strip()
            if not token:
                raise BigQueryUnavailable("gcloud auth print-access-token returned empty; run `gcloud auth login`.")
            self.token = token
            self.expiry = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=45)

    creds = _GcloudTokenCreds(token=None, scopes=scopes)
    creds.refresh(None)
    if settings.gcp_project:
        creds = creds.with_quota_project(settings.gcp_project)
    return creds


_runner: Runner | None = None


def get_runner() -> Runner:
    global _runner
    if _runner is None:
        _runner = BQRunner()
    return _runner


def set_runner(runner: Runner | None) -> None:
    """Inject a runner (tests, notebooks)."""
    global _runner
    _runner = runner


def probe() -> dict:
    """Is BigQuery usable right now? Never raises."""
    try:
        r = BQRunner()
        ds = r.client.get_dataset(f"{r.project}.{r.dataset}", timeout=10)
        tables = sorted(t.table_id for t in r.client.list_tables(ds, max_results=50))
        return {"reachable": True, "detail": f"{len(tables)} table/view(s) in {r.dataset}", "tables": tables}
    except BigQueryUnavailable as exc:
        return {"reachable": False, "detail": str(exc)}
    except Exception as exc:  # noqa: BLE001
        return {"reachable": False, "detail": _explain(exc)}
