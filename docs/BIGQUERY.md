# BigQuery setup and operations

TerraSentinel runs on local files by default. BigQuery is an opt-in backend: same API, same detection maths, different storage. The maths (detection, early-warning bands) never runs inside Gemini.

> **Verification status (18 Oct 2026).** Live against project `project-3c4cd22c-ff1e-405d-803` / dataset `terrasentinel` (Cloud Run + BigQuery). Demo: 1,355 points / **46 epochs** / 62,330 timeseries rows; pipeline matches local (3 CRITICAL, 4 ELEVATED). **Important:** BigQuery sandbox default **60-day partition expiration** deletes older InSAR epochs and forces every site to WEAK — clear with `ALTER TABLE … SET OPTIONS (partition_expiration_days = NULL)` (see `scripts/bq_clear_partition_expiry.sql`) before `--load-demo`.

## 1. Prerequisites

- A Google Cloud project with billing enabled and the BigQuery API turned on.
- Google Cloud credentials (see section 2b). **A Gemini API key from AI Studio is not one of them**: it only authorises the Gemini API and BigQuery will refuse it.
- IAM roles for the identity running the backend and the daily job:
  - `roles/bigquery.dataEditor` on the dataset (create/replace tables, load rows).
  - `roles/bigquery.jobUser` on the project (run queries and load jobs).
  - Setup creates the dataset, so the one-off setup identity also needs `roles/bigquery.dataOwner` (or `bigquery.datasets.create`).

## 2. Environment variables (`backend/.env`)

| Variable | Default | Meaning |
| --- | --- | --- |
| `TS_DATA_BACKEND` | `local` | Set to `bigquery` to switch storage. |
| `TS_GCP_PROJECT` | empty | Project that owns the dataset and is billed for queries. |
| `TS_BQ_DATASET` | `terrasentinel` | Dataset name. |
| `TS_BQ_LOCATION` | `US` | Dataset location. Must match where the data lives. |
| `TS_BQ_MAX_GB_BILLED` | `10` | Hard cost guard: a query that would scan more fails instead of billing. |

| `TS_GOOGLE_CREDENTIALS_FILE` | empty | Path to a service-account key JSON, kept outside the repository. Empty means Application Default Credentials. |

`TS_GCP_PROJECT` is also read by the Gemini integration. If `TS_GEMINI_API_KEY` is set, Gemini uses the API key and ignores the project; the project then only affects BigQuery.

## 2b. Credentials: pick one

1. **Your own login (quickest for a laptop).** Install the Google Cloud CLI, then run `gcloud auth application-default login` and sign in with an account that has the roles above.
2. **A service-account key.** In the console create a service account with `BigQuery Data Editor` and `BigQuery Job User`, download a JSON key, store it outside the repo (keys are gitignored by name, but do not rely on that), and set `TS_GOOGLE_CREDENTIALS_FILE=C:\keys\terrasentinel-bq.json` in `backend/.env`.
3. **On Cloud Run or a VM.** Attach the service account to the service; no key file is needed.

No billing account? The BigQuery **sandbox** lets you query and store small amounts for free without a card. It expires tables after 60 days, which is fine for a trial.

## 2c. Check the connection (read-only)

```powershell
cd backend
.\.venv\Scripts\python.exe -m app.services.bq.doctor          # human-readable
.\.venv\Scripts\python.exe -m app.services.bq.doctor --json   # for scripts
```

The same checks run from the Data Hub: **Cloud & workspace, Connection checks** (administrators only). They cover the client library, project, credentials, API access, dataset, tables and permissions, using dry-run queries only, so nothing is created or billed. Each failure prints the exact fix. Without credentials the checks can take up to about half a minute, because the Google auth library probes for a metadata server before giving up.

## 3. Create tables

```powershell
cd backend
# Print the DDL only, touch nothing
.\.venv\Scripts\python.exe -m app.services.bq.setup --dry-run
# Create dataset and tables
.\.venv\Scripts\python.exe -m app.services.bq.setup --project YOUR_PROJECT
# Same, and load the synthetic demo data (labelled synthetic in the UI)
.\.venv\Scripts\python.exe -m app.services.bq.setup --project YOUR_PROJECT --load-demo
```

Then set `TS_DATA_BACKEND=bigquery` and restart the API. The Data Hub "Cloud and workspace" panel shows the active backend.

## 4. Daily job

```powershell
.\.venv\Scripts\python.exe -m app.jobs.daily                       # recompute from stored data
.\.venv\Scripts\python.exe -m app.jobs.daily --fetch-rain --region IN
```

The job refreshes derived tables and records a new pass, which feeds "New since last pass" and alert history. Schedule it with Cloud Scheduler plus Cloud Run Jobs once the smoke test passes.

## 5. Cost guard and limits

- Every query sets `maximum_bytes_billed` from `TS_BQ_MAX_GB_BILLED`; over-budget queries error out rather than bill.
- Results are cached in-process for `bq_cache_ttl_s` (300 s).
- SQL is built from fixed templates with query parameters; user values are never interpolated into SQL text.
- Known limitations:
  - SQL is parse-checked only; semantic or permission errors surface on the first live run.
  - Link import resolves the host once, refuses anything that is not a public address (including IPv6 forms that embed a private IPv4), and then connects to that exact address, so DNS cannot be switched between the check and the fetch. An egress policy on the host is still sensible defence in depth.
  - Public earthquake data (Data Hub, Public data) is kept as CSV files on the server. In BigQuery mode the per-site seismic context still reads those local files; it is not copied to BigQuery.
  - Uploads and the workspace reset are local-workspace features: in BigQuery mode, reset is refused and tables are managed from the console or the loader.

## 6. Smoke test checklist (run once with real credentials)

1. `setup --dry-run` output looks right.
2. `setup --load-demo` finishes without error; tables visible in the console.
3. API starts with `TS_DATA_BACKEND=bigquery`; Data Hub, Cloud and workspace shows the project as reachable and the backend as active.
4. Command Center shows the same site count and top sites as the local backend.
5. Bytes billed for one full refresh stay far below `TS_BQ_MAX_GB_BILLED`.
6. Daily job completes and a new pass appears in Alerts.

Tick these off in `docs/TEST_CHECKLIST.md` section C when done.
