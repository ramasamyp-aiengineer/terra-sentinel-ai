# Data upload production audit · 17 Oct 2026

Scope: will a real Data Hub upload work? What is ready vs not for a shared/production deployment.

## Verdict

**Local Data Hub upload is production-capable for a single-admin pilot** (CSV / GeoJSON / wide InSAR, validate-then-import, provenance, transactional workspace, reset).

**Not yet production-ready as a multi-tenant Cloud Run service** until Cloud Run is live, BigQuery is proven on a real project, and sessions are shared across instances.

## What we verified live (this machine)

| Check | Result |
| --- | --- |
| Admin login + CSRF header | Pass |
| Template download (points, rain, assets, insar) | Pass |
| Validate → Import (merge) | Pass |
| Refuse `.xlsx` with plain-language error | Pass |
| Replace points drops orphan time series (no silent mix) | Pass |
| Post-import warnings when rankings would be empty | Pass (strengthened) |
| Open-Meteo fetch-rain for Chamoli | Pass (30 days, 14-day overlap) |
| Provenance row for open-meteo / upload / demo seed | Pass |
| Reset to demo restores workspace | Pass |
| Automated: ingest + data API (incl. region cap, Excel float dates, empty InSAR, UTF-8 refuse, orphan replace) | **31 passed** (focused); full suite previously green |

## How upload works (short)

1. Admin only: Check file (`/api/data/validate`) then Import (`/api/data/upload`).
2. Parser detects kind (or uses the form), refuses unsupported formats, reports row errors.
3. First write creates a transactional workspace copy of demo; merge or replace one kind.
4. Provenance is recorded; caches refresh; `post_checks` say whether sites will appear.
5. Prefer the **wide InSAR template** when you have points + epochs together.

## Fix shipped in this audit

- After a points **replace**, orphan time-series rows were already dropped (correct). The UI/API response now states that clearly and tells the user to upload matching epochs or use the wide template.
- Data Hub copy explains the same rule before import.
- Nearest-region attach capped at **250 km** (far points land in `UNASSIGNED` with a warning).
- Wide InSAR detection accepts Excel float date headers (`20250105.0`); explicit `insar` kind refuses files with no epoch columns.
- Non-UTF-8 CSV is refused with a plain-language error.

## Deploy target (chosen)

| Field | Value |
| --- | --- |
| GCP account | `ramasamy.p2105@gmail.com` |
| Project | **My First Project** · `project-3c4cd22c-ff1e-405d-803` |
| Billing account | **My Billing Account** · `01E250-7520CE-291BFA` |
| Link status | Linked (`billingAccountName` set) |
| Billing open | **No** (`open: false`, `billingEnabled: false`) — blocks Cloud Run / Artifact Registry / Cloud Build |
| Reopen | https://console.cloud.google.com/billing/01E250-7520CE-291BFA?project=project-3c4cd22c-ff1e-405d-803 |
| Deploy command (after reopen) | `.\scripts\deploy_cloud_run.ps1 -KeepWarm -EnableBigQuery` |

Deploy posture when billing is open: `max-instances=1`, GCS-mounted `data/state`, `TS_TRUST_PROXY=true`, secrets for admin + Gemini.

## Still open (honest)

| Item | Why it matters |
| --- | --- |
| Public Cloud Run URL | Blocked until billing account is **reopened** in console (CLI cannot reopen) |
| BigQuery on a real GCP project | **Live:** doctor OK, demo loaded, 87 sites from BQ pipeline. App `.env` uses `TS_DATA_BACKEND=bigquery`. Cloud Run still blocked on closed billing |
| Multi-instance sessions | Mitigated for Cup: deploy script forces `max-instances=1` + GCS state volume |
| Analyst role cannot upload | By design (admin only); add analysts carefully |

## Safe demo path for judges

1. Sign in as admin.
2. Data Hub → Get a template (wide InSAR) or Check → Import rain / link.
3. Or: Fetch rainfall for Chamoli (live Open-Meteo works).
4. If rankings go empty after a points-only replace, that is expected — import time series next, then Reset to demo to restore the pitch dataset.
