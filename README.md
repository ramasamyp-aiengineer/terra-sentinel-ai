# TerraSentinel AI

**Early warning for ground movement under roads, metros and dams.**

Satellite radar (InSAR) measures how the ground moves to the millimetre. TerraSentinel ranks sites by what they could affect, flags acceleration, and gives an outlook as a **time-to-threshold band that assumes today’s trend continues — never a failure date.**

Built for the **Google Cloud AI Builder Cup 2026 (JAPAC · Sustainability)**.

**Live demo (Cloud Run + BigQuery):**  
https://terrasentinel-598899050820.asia-southeast1.run.app

---

## What it does

| Layer | Does | Never does |
| --- | --- | --- |
| **Maths** (Python; SQL on BigQuery) | Detection, ranking, outlook bands — every number | Invent a date of failure |
| **Gemini** | Reasons, summarises, drafts an inspection ticket from tool results only | Invent or compute a number (rejected by a guard) |
| **Public data** (USGS earthquakes) | Context beside a site | Change a risk score or tier |

Decision support for qualified engineers. Not a certified safety system. Bundled data is **synthetic demonstration data**, labelled in the UI.

### Product surfaces

- **Command Center** — map, ranked sites, what to do today  
- **Alerts · Morning Brief · Early Warning · Trends · Corridors · Portfolio · Work Orders**  
- **Data Hub** — validate-then-import uploads, links, rainfall fetch, provenance, reset to demo  
- **Users & access** — admin / analyst / viewer roles  

---

## Upload your own data (Data Hub)

Nothing is saved until validation passes and you press **Import**.

1. Sign in as **admin**.
2. Open **Data Hub → Import**.
3. Choose kind (or leave auto-detect): points, time series, rain, assets (GeoJSON), regions, or **wide InSAR** (points + epochs together — preferred).
4. Press **1. Check file** → see row errors / warnings immediately (`POST /api/data/validate`).
5. Press **2. Import** (merge or replace). Provenance is recorded; rankings refresh.
6. Optional: **Fetch rainfall** for a region (Open-Meteo), or import from a public HTTPS link.
7. Prefer the downloadable templates in Data Hub. `.xlsx` is refused — export CSV / GeoJSON.

**Guards:** UTF-8 only · nearest-region attach capped at 250 km · replace points drops orphan time series · post-import warnings if rankings would go empty.

---

## Run locally

Requirements: Python 3.12, Node 22+.

```powershell
# Backend
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
copy .env.example .env          # set TS_ADMIN_PASSWORD; optional TS_GEMINI_API_KEY
.\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000

# Frontend (dev — proxies /api to :8000)
cd ..\frontend
npm ci
npm run dev                     # http://localhost:5173
```

Or `npm run build` in `frontend`, then open `http://127.0.0.1:8000/`.

### Configuration (`backend/.env`)

| Setting | Purpose |
| --- | --- |
| `TS_ADMIN_USER` / `TS_ADMIN_PASSWORD` | First-run administrator |
| `TS_GEMINI_API_KEY` | Work-order narratives (template fallback if empty) |
| `TS_DATA_BACKEND=bigquery` + `TS_GCP_PROJECT` | Optional BigQuery storage (needs GCP credentials — a Gemini key is **not** enough) |
| `TS_TRUST_PROXY` / `TS_PROXY_HOPS` | Only behind a proxy you control (e.g. Cloud Run) |

See `docs/BIGQUERY.md` and `docs/SECURITY.md`.

---

## Deploy (Google Cloud)

```powershell
.\scripts\deploy_cloud_run.ps1 -KeepWarm -EnableBigQuery
```

Builds with Cloud Build, deploys one Cloud Run service (`max-instances=1`, GCS state volume, Secret Manager for admin + Gemini). Details: `docs/DEPLOY.md`.

---

## Tests

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q
```

Checklist and honesty limits: `docs/TEST_CHECKLIST.md` · security audit: `docs/AUDIT_2026-10.md`.

---

## Repository layout

```
backend/app/     API, detection, Data Hub ingest, Gemini agent, BigQuery, auth
backend/tests/   pytest (engine, ingest, auth, hardening, BigQuery fake runner)
frontend/src/    React + MapLibre UI
data/demo/       Synthetic demonstration dataset (read-only)
docs/            BIGQUERY · SECURITY · DEPLOY · pitch deck / demo assets
scripts/         Cloud Run deploy
```

---

## License / competition note

Demo dataset is synthetic. Outlooks are time-to-threshold bands under a continuing-regime assumption — not collapse predictions.
