# TerraSentinel AI

**Early warning for ground movement under roads, metros and dams.**

Satellite radar (InSAR) measures how the ground moves to the millimetre. TerraSentinel ranks sites by what they could affect, flags acceleration, and gives an outlook as a **time-to-threshold band that assumes today’s trend continues — never a failure date.**

Built for the **Google Cloud AI Builder Cup 2026 (JAPAC · Sustainability)**.

| | |
| --- | --- |
| **Live demo** | https://terrasentinel-598899050820.asia-southeast1.run.app |
| **Sign-in** | Username and password are **shown on the login page** (judge demo hint) |
| **Judge guide** | [`docs/JUDGE.md`](docs/JUDGE.md) — five-minute walk + production story |
| **Cup submission deck** | [`docs/pitch/TerraSentinel-AI-Builder-Cup-Submission.pdf`](docs/pitch/TerraSentinel-AI-Builder-Cup-Submission.pdf) · [`.pptx`](docs/pitch/TerraSentinel-AI-Builder-Cup-Submission.pptx) (official template filled) |
| **Source** | https://github.com/ramasamyp-aiengineer/terra-sentinel-ai |

---

## Why it exists

Operators already receive InSAR point clouds. They do **not** get a short, consequence-ranked list of where to send an engineer *today*, with an honest planning band and a traceable ticket.

TerraSentinel is that decision layer:

- **Maths first** — detection, ranking and outlook bands are deterministic Python (and SQL on BigQuery). Every number is reproducible.
- **Gemini second** — drafts reasons and inspection tickets from **tool results only**. Invented numbers are rejected by a guard; if the model is slow or down, a template still ships.
- **Public context** — USGS earthquakes can sit beside a site. They never change a risk score or tier.

Decision support for qualified engineers. **Not** a certified safety system. Bundled corridors are **synthetic demonstration data**, labelled in the UI.

---

## Product surfaces

| Surface | Job |
| --- | --- |
| **Command Center** | Map, KPIs, Act list — what to do today |
| **Alerts** | What *changed* between satellite passes |
| **Morning Brief · Early Warning · Trends · Corridors · Portfolio** | Planning and narrative views |
| **Work Orders** | Inspection tickets (template → optional Gemini polish) |
| **Data Hub** | Validate-then-import, rainfall fetch, provenance, BigQuery sync, reset to demo |
| **Users & access** | admin / analyst / viewer · audit log |

---

## For judges (production story)

Read **[`docs/JUDGE.md`](docs/JUDGE.md)** first. Short version:

1. Open the live URL → credentials are on the sign-in card → sign in.
2. **Command Center** → open a CRITICAL/ELEVATED site → read the outlook **band** (not a failure date).
3. Generate a **Work Order** → confirm numbers match the site, not free text.
4. Skim **Data Hub** provenance and **Methodology** for the formulae.

**Production posture on Cloud Run:** one service (`max-instances=1`), Secret Manager for admin + Gemini, GCS volume for state, BigQuery backend for the live demo, CSRF + rate limits + sessions. See `docs/DEPLOY.md` and `docs/SECURITY.md`.

---

## Upload your own data (Data Hub)

Nothing is saved until validation passes and you press **Import**.

1. Sign in as **admin**.
2. Open **Data Hub → Import**.
3. Choose kind (or leave auto-detect): points, time series, rain, assets (GeoJSON), regions, or **wide InSAR** (points + epochs together — preferred).
4. Press **1. Check file** → row errors / warnings (`POST /api/data/validate`).
5. Press **2. Import** (merge or replace). Provenance is recorded; rankings refresh.
6. Optional: **Fetch rainfall** (Open-Meteo), import from a public HTTPS link, or **sync to BigQuery**.
7. Prefer the downloadable templates. `.xlsx` is refused — export CSV / GeoJSON.

**Guards:** UTF-8 only · nearest-region attach capped at 250 km · replace points drops orphan time series · post-import warnings if rankings would go empty.

---

## Run locally

Requirements: **Python 3.12**, **Node 22+**.

```powershell
# Backend
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
copy .env.example .env
# Edit .env: set TS_ADMIN_PASSWORD (required). Optional: TS_GEMINI_API_KEY, TS_SHOW_LOGIN_HINT=true
.\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000

# Frontend (dev — proxies /api to :8000)
cd ..\frontend
npm ci
npm run dev                     # http://localhost:5173
```

Or `npm run build` in `frontend`, then open `http://127.0.0.1:8000/` (API serves the built SPA).

### Configuration (`backend/.env`)

| Setting | Purpose |
| --- | --- |
| `TS_ADMIN_USER` / `TS_ADMIN_PASSWORD` | First-run administrator |
| `TS_SHOW_LOGIN_HINT=true` | Show username + password on the sign-in page (Cup / demos only) |
| `TS_GEMINI_API_KEY` | Work-order narratives (template fallback if empty) |
| `TS_DATA_BACKEND=bigquery` + `TS_GCP_PROJECT` | BigQuery storage (needs GCP credentials — a Gemini key is **not** enough) |
| `TS_TRUST_PROXY` / `TS_PROXY_HOPS` | Only behind a proxy you control (e.g. Cloud Run) |

More: `docs/BIGQUERY.md` · `docs/SECURITY.md` · `docs/DEPLOY.md`.

---

## Deploy (Google Cloud)

```powershell
.\scripts\deploy_cloud_run.ps1 -KeepWarm -EnableBigQuery
```

Cloud Build → Artifact Registry → Cloud Run (`min-instances=1` with `-KeepWarm`, GCS state volume, Secret Manager, optional BigQuery). Prerequisites and IAM: `docs/DEPLOY.md`.

---

## Tests

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q
```

Honesty / product checklist: `docs/TEST_CHECKLIST.md` · security notes: `docs/AUDIT_2026-10.md`.

---

## Repository layout

```
backend/app/     API, detection, Data Hub, Gemini agent, BigQuery, auth
backend/tests/   pytest (engine, ingest, auth, hardening, BigQuery fakes)
frontend/src/    React + MapLibre UI
data/demo/       Synthetic demonstration dataset (read-only)
docs/            JUDGE · BIGQUERY · SECURITY · DEPLOY · pitch assets
scripts/         Cloud Run deploy · BigQuery maintenance SQL
```

---

## Honesty rules (non-negotiable)

- Outlooks are **time-to-threshold bands under a continuing-regime assumption** — not collapse predictions.
- Gemini **narrates tool numbers only**; it does not invent scores, ETAs or tiers.
- Demo / synthetic data is **labelled** in the product.
- Secrets stay in `.env` / Secret Manager — never in git.

## License / competition note

Demo dataset is synthetic. Built for the Google Cloud AI Builder Cup 2026.
