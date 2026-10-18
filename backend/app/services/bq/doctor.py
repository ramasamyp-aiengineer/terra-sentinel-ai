"""Connection doctor: tells an operator exactly what stands between this app and a working BigQuery.

    python -m app.services.bq.doctor            # human-readable report, exit 0 only when ready
    python -m app.services.bq.doctor --json     # same, machine-readable

Each check says what it looked at, what it found and the exact next command. Nothing here writes to BigQuery;
the write-permission check is a dry run. The same checks power the "Run checks" button in Data Hub.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass

from app.core.config import settings
from app.services.bq import schema
from app.services.bq.client import BigQueryUnavailable, load_credentials

PASS, WARN, FAIL, SKIP = "pass", "warn", "fail", "skip"


@dataclass
class Check:
    id: str
    label: str
    status: str
    detail: str
    fix: str = ""


def _short(exc: Exception) -> str:
    text = str(exc).strip().splitlines()
    return f"{exc.__class__.__name__}: {text[0][:200]}" if text else exc.__class__.__name__


def _api_failure(exc: Exception, project: str) -> tuple[str, str]:
    t = str(exc)
    if "has not been used" in t or "accessNotConfigured" in t or "SERVICE_DISABLED" in t:
        return "The BigQuery API is not enabled for this project.", f"gcloud services enable bigquery.googleapis.com --project {project}"
    if "403" in t or "Access Denied" in t or "permission" in t.lower():
        return "This identity may not run BigQuery jobs in the project.", f"Grant roles/bigquery.jobUser on project {project} to the identity named above."
    if "404" in t or "Not found" in t:
        return f"Project {project!r} was not found.", "Check TS_GCP_PROJECT is the project ID (not the display name or number)."
    if "billing" in t.lower():
        return "Billing is not enabled for this project.", "Enable billing, or use the free BigQuery sandbox (no card needed, tables expire after 60 days)."
    return _short(exc), "See the message above; run the same query in the BigQuery console to compare."


def run_checks(client=None, project: str | None = None, creds_description: str | None = None) -> list[Check]:
    """Run every check. ``client`` (a google-cloud-bigquery style object) is injectable for tests."""
    out: list[Check] = []
    project = project or settings.gcp_project
    dataset, location = settings.bq_dataset, settings.bq_location

    # 1. library ------------------------------------------------------------------------------------------
    try:
        import google.cloud.bigquery as bq_lib  # noqa: F401

        out.append(Check("library", "BigQuery client library", PASS, "google-cloud-bigquery is installed."))
    except ImportError:
        out.append(Check("library", "BigQuery client library", FAIL, "google-cloud-bigquery is not installed.", "pip install -r backend/requirements.txt"))
        return out

    # 2. configuration --------------------------------------------------------------------------------------
    mode = settings.data_backend.lower()
    if mode == "bigquery" and not project:
        out.append(
            Check(
                "mode", "Data backend", FAIL,
                "TS_DATA_BACKEND=bigquery but TS_GCP_PROJECT is not set — the API cannot serve data.",
                "Set TS_GCP_PROJECT=your-project-id in backend/.env, or set TS_DATA_BACKEND=local.",
            )
        )
        return out
    out.append(
        Check(
            "mode", "Data backend", PASS if mode == "bigquery" else WARN,
            f"TS_DATA_BACKEND={mode}. " + ("The app reads and writes BigQuery." if mode == "bigquery" else "The app is serving local files; BigQuery is optional."),
            "" if mode == "bigquery" else "Set TS_DATA_BACKEND=bigquery in backend/.env once every check below passes, then restart the API.",
        )
    )

    # 3. credentials ----------------------------------------------------------------------------------------------
    creds = None
    if client is None:
        try:
            creds, creds_description = load_credentials()
            out.append(Check("credentials", "Google credentials", PASS, f"Found {creds_description}."))
        except BigQueryUnavailable as exc:
            out.append(
                Check(
                    "credentials", "Google credentials", FAIL, str(exc),
                    "Either run `gcloud auth application-default login`, or create a service-account key and set "
                    "TS_GOOGLE_CREDENTIALS_FILE=C:\\path\\to\\key.json in backend/.env. "
                    "NOTE: a Gemini API key from AI Studio is not a Google Cloud credential and cannot be used for BigQuery.",
                )
            )
            return out
    else:
        out.append(Check("credentials", "Google credentials", PASS, f"Using {creds_description or 'an injected client'}."))

    # 4. project ------------------------------------------------------------------------------------------------------
    if not project:
        out.append(
            Check(
                "project", "Project", FAIL, "TS_GCP_PROJECT is not set.",
                "Set TS_GCP_PROJECT=your-project-id in backend/.env.",
            )
        )
        return out
    out.append(Check("project", "Project", PASS, f"Project {project}, dataset {dataset}, location {location}."))

    # 5. client + API ----------------------------------------------------------------------------------------------------------
    if client is None:
        try:
            from google.cloud import bigquery

            client = bigquery.Client(project=project, location=location, credentials=creds)
        except Exception as exc:  # noqa: BLE001
            out.append(Check("client", "BigQuery client", FAIL, _short(exc), "Check the credentials and project above."))
            return out
    try:
        from google.cloud import bigquery

        job = client.query("SELECT 1 AS ok", job_config=bigquery.QueryJobConfig(dry_run=True, use_query_cache=False))
        out.append(Check("api", "BigQuery API and job permission", PASS, f"A dry-run query was accepted ({job.total_bytes_processed or 0} bytes)."))
    except Exception as exc:  # noqa: BLE001
        detail, fix = _api_failure(exc, project)
        out.append(Check("api", "BigQuery API and job permission", FAIL, detail, fix))
        return out

    out.append(
        Check(
            "cost_guard", "Cost guard", PASS,
            f"Every query is capped at {settings.bq_max_gb_billed:g} GB billed (TS_BQ_MAX_GB_BILLED); results are cached for {settings.bq_cache_ttl_s} s.",
        )
    )

    # 6. dataset and tables ---------------------------------------------------------------------------------------------------------
    ref = f"{project}.{dataset}"
    try:
        ds = client.get_dataset(ref, timeout=15)
    except Exception as exc:  # noqa: BLE001
        t = str(exc)
        if "404" in t or "Not found" in t:
            out.append(Check("dataset", "Dataset", FAIL, f"Dataset {ref} does not exist yet.", "python -m app.services.bq.setup --load-demo"))
        else:
            detail, fix = _api_failure(exc, project)
            out.append(Check("dataset", "Dataset", FAIL, detail, fix))
        return out
    ds_loc = getattr(ds, "location", None)
    if ds_loc and ds_loc.upper() != location.upper():
        out.append(
            Check("dataset", "Dataset", FAIL, f"Dataset {ref} is in {ds_loc} but TS_BQ_LOCATION is {location}.", f"Set TS_BQ_LOCATION={ds_loc} in backend/.env.")
        )
    else:
        out.append(Check("dataset", "Dataset", PASS, f"{ref} exists" + (f" in {ds_loc}." if ds_loc else ".")))

    try:
        found = {t.table_id for t in client.list_tables(ds, max_results=200)}
    except Exception as exc:  # noqa: BLE001
        out.append(Check("tables", "Tables", WARN, _short(exc), ""))
        found = set()
    else:
        expected = set(schema.TABLES)
        missing = sorted(expected - found)
        if missing:
            out.append(Check("tables", "Tables", FAIL, f"{len(found & expected)}/{len(expected)} tables present; missing: {', '.join(missing)}.", "python -m app.services.bq.setup"))
        else:
            out.append(Check("tables", "Tables", PASS, f"All {len(expected)} tables are present."))

    # 7. data ----------------------------------------------------------------------------------------------------------------------------
    if {"insar_points", "insar_timeseries"} <= found or {"points", "timeseries"} <= found:
        counts = {}
        for name, table in schema.TABLES.items():
            if name in found and name in ("points", "timeseries", "insar_points", "insar_timeseries"):
                try:
                    counts[name] = int(client.get_table(f"{ref}.{name}").num_rows or 0)
                except Exception:  # noqa: BLE001
                    pass
        total = sum(counts.values())
        out.append(
            Check(
                "data", "Data loaded", PASS if total else WARN,
                ", ".join(f"{k}: {v:,} rows" for k, v in counts.items()) or "Row counts unavailable.",
                "" if total else "python -m app.services.bq.setup --load-demo   (or sync from Data Hub, Cloud and workspace)",
            )
        )
    else:
        out.append(Check("data", "Data loaded", SKIP, "Tables missing, so there is nothing to count yet."))

    # 8. write permission (dry run only) ------------------------------------------------------------------------------------------------------
    try:
        from google.cloud import bigquery

        client.query(
            f"CREATE TABLE IF NOT EXISTS `{ref}._ts_doctor_probe` (x INT64)",
            job_config=bigquery.QueryJobConfig(dry_run=True),
        )
        out.append(Check("write", "Table write permission (dry run)", PASS, "A table-creating statement was accepted in dry-run mode."))
    except Exception as exc:  # noqa: BLE001
        if "403" in str(exc) or "Access Denied" in str(exc):
            out.append(Check("write", "Table write permission (dry run)", FAIL, "This identity cannot create or change tables.", f"Grant roles/bigquery.dataEditor on dataset {ref}."))
        else:
            out.append(Check("write", "Table write permission (dry run)", WARN, "Could not confirm write access by dry run.", "Run `python -m app.services.bq.setup` and watch for errors."))
    return out


def summarise(checks: list[Check]) -> dict:
    failed = [c for c in checks if c.status == FAIL]
    warned = [c for c in checks if c.status == WARN]
    if failed:
        state, headline = "blocked", f"{len(failed)} problem(s) to fix. Start with: {failed[0].label}."
    elif any(c.id == "mode" and c.status == WARN for c in checks):
        state, headline = "ready-not-active", "BigQuery is reachable. The app is still serving local files."
    elif warned:
        state, headline = "ready-with-notes", "BigQuery works, with a few notes."
    else:
        state, headline = "ready", "BigQuery is connected and serving the app."
    return {"state": state, "headline": headline, "checks": [asdict(c) for c in checks]}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    result = summarise(run_checks())
    if args.json:
        print(json.dumps(result, indent=1))
    else:
        mark = {PASS: "[ OK ]", WARN: "[warn]", FAIL: "[FAIL]", SKIP: "[skip]"}
        for c in result["checks"]:
            print(f"{mark[c['status']]} {c['label']}: {c['detail']}")
            if c["fix"] and c["status"] in (FAIL, WARN):
                print(f"         -> {c['fix']}")
        print(f"\n{result['headline']}")
    return 0 if result["state"] in ("ready", "ready-not-active", "ready-with-notes") else 1


if __name__ == "__main__":
    sys.exit(main())
