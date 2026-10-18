# TerraSentinel — Master Development Checklist (Winning Edition)

**Event:** Google Cloud AI Builder Cup (JAPAC) — deadline **Oct 18, 2026** (confirm exact time on the portal)
**Today:** Oct 16 → treat this as a **~48-hour build**. Priorities below are ruthless on purpose.

Legend: `[ ]` todo · **P0** must ship · **P1** should ship · **P2** only if time remains · 🚩 = risk to watch

---

## 0. Win conditions (read first)

Judging weights: Technical Merit & GenAI **40%** · Impact **25%** · Innovation **25%** · UX **10%**

| Win condition | Proof the judge sees |
|---|---|
| Not a chatbot / RAG wrapper | BigQuery GIS detection → ranked sites → Gemini tool-calling → work order |
| Early warning is honest | "Time-to-threshold band + confidence", never "collapse date" |
| Real, not theater | At least one **real** InSAR dataset loaded; any synthetic data is labeled synthetic |
| Deployed & working | Public Cloud Run URL that survives a cold judge click |
| Operational feel | Region → corridor → site → work order on a satellite map |
| Grounded GenAI | Every number in the brief traceable to a tool response |

**Golden rule:** a working, narrow, honest product beats a broad, half-working one. Cut scope before cutting polish on the demo path.

---

## 1. Compliance & eligibility gate (do first — 15 minutes)

- [ ] **P0** Every team member is 21+, based in JAPAC, not a current student 🚩
- [ ] **P0** Team size 2–4 registered on the Hack2skill portal
- [ ] **P0** Confirm exact submission deadline, timezone, and submission form fields
- [ ] **P0** Confirm "built from scratch after launch" rule — **no pre-existing code**; repo history must start after launch date
- [ ] **P0** Confirm which challenge track to select (Sustainability & Social Impact vs Manufacturing / Industrial Operations)
- [ ] **P0** Confirm required deliverables: public GitHub repo, deployed URL, demo video < 3:00, pitch deck
- [ ] **P0** Confirm Google Cloud credits / billing account access for the whole team
- [ ] **P1** Check any rules on third-party data licensing and open-source licenses

---

## 2. Team roles & working agreement

| Role | Owns |
|---|---|
| **Data/Geo lead** | InSAR ingest, BigQuery schema, spatial queries |
| **Backend/AI lead** | FastAPI, detection/ETA logic, Gemini agent + tools |
| **Frontend lead** | React, map, screens, design system |
| **Product/Pitch lead** | Story, deck, video, README, QA of claims |

- [ ] **P0** Assign one owner per area above (one person can hold two)
- [ ] **P0** Shared repo created (public from day 1, no secrets committed)
- [ ] **P0** Branching: `main` always deployable; short-lived feature branches
- [ ] **P0** Daily 10-minute sync + a single shared task board
- [ ] **P0** Freeze point: **no new features after T-8 hours before deadline**
- [ ] **P1** Decide the "claims list" (what we will / will not say — see §14)

---

## 3. Product scope lock

### 3.1 In scope (P0 — demo path)
- [ ] Satellite basemap with zoom: region → corridor → site
- [ ] InSAR points colored by tier near registered assets
- [ ] Deterministic detection: velocity, 60-day displacement, acceleration
- [ ] Tier assignment (Stable / Watch / Elevated / Critical) + data-weak state
- [ ] Time-to-threshold band with confidence and assumptions
- [ ] Ranked Act List (region-level)
- [ ] Site Intelligence: Now · Trend · History · Outlook · Action
- [ ] Gemini agent with function calling → structured work order
- [ ] Rain context (Open-Meteo) as trigger evidence
- [ ] Two asset types demonstrated on one engine (e.g., mountain highway + urban/metro or mine)
- [ ] Deployed on Cloud Run

### 3.2 Should have (P1)
- [ ] Alert Inbox with Acknowledge / Assign / Escalate / False alarm
- [ ] Morning Brief (grounded, 5 bullets)
- [ ] DEM slope context
- [ ] PDF/print export of work order
- [ ] Role-based landing (control room / engineer / field)
- [ ] Time scrubber (30d / 6m / 18m)
- [ ] Forecast-invalidated state after rain/cut event

### 3.3 Later / pitch-only (P2 — mention as roadmap, don't build)
- [ ] Sentinel-2 toe-cut before/after
- [ ] Earthquake re-trigger (USGS)
- [ ] Pub/Sub event-driven recompute + Scheduler jobs
- [ ] Translation API for local-language work orders
- [ ] Looker Studio exec portfolio
- [ ] Learning loop from inspection feedback
- [ ] Multi-tenant org / admin console

**Rule:** anything in P2 appears in the deck's roadmap slide, not in the build.

---

## 4. Data checklist (highest risk area 🚩)

### 4.1 Real InSAR data
- [ ] **P0** Choose ONE real corridor/area with documented ground motion
  - Options: EGMS (Europe: alpine pass / mining basin), COMET-LiCSAR (Himalaya/Nepal/India), HyP3/ASF on-demand
  - 🚩 Europe has the easiest ready-made point data (EGMS); Himalaya has the strongest story but harder data. Decide in the first 2 hours.
- [ ] **P0** Download a bounded slice (small bbox, a few thousand to ~50k points)
- [ ] **P0** Record provenance: source, product level, download date, license, bbox
- [ ] **P0** Normalize to the schema in §4.3
- [ ] **P0** Validate: no null coordinates, velocity units are mm/yr, dates parse, LOS direction documented
- [ ] **P1** Keep ≥ 12 months of epochs so trend/acceleration logic is real

### 4.2 Honest fallback
- [x] **P0** If real data fails by T+6h, switch to a **clearly labeled** semi-synthetic dataset seeded around real coordinates
- [ ] **P0** Label synthetic data in the UI ("Demonstration data") and README 🚩 — unlabeled fabricated satellite results will destroy credibility
- [ ] **P1** Write a one-paragraph "Data provenance" section in README and deck

### 4.3 Core tables (BigQuery)
- [ ] `insar_points` — point_id, geo, velocity_mm_yr, coherence, los_direction, source
- [ ] `insar_timeseries` — point_id, epoch_date, displacement_mm (long format; easier window functions than JSON)
- [ ] `assets` — asset_id, name, type, region_id, criticality, buffer_m, geometry
- [ ] `regions` — region_id, parent_id, name, level, geometry
- [ ] `site_clusters` — cluster_id, asset_id, centroid, point_count, chainage_km
- [ ] `site_metrics` — cluster_id, as_of_date, velocity, accel_ratio, d60_mm, tier, eta_low_days, eta_high_days, confidence
- [ ] `alerts` — alert_id, cluster_id, type, tier, created_at, status, assigned_to
- [ ] `work_orders` — order_id, cluster_id, json_body, model_version, created_at
- [ ] `rain_cache` — lat_bin, lon_bin, date, precip_mm
- [ ] Partition by date; cluster by geography where useful

### 4.4 Context data
- [x] **P0** Asset geometries (OSM road/rail extract or hand-drawn GeoJSON for demo corridors)
- [x] **P0** Criticality attribute per asset (e.g., sole access road = high)
- [ ] **P0** Rain: Open-Meteo archive + forecast; cache results to avoid rate limits
- [ ] **P1** DEM: Copernicus GLO-30 / SRTM → slope per cluster (Earth Engine or precomputed)
- [ ] **P1** Chainage along asset (linear referencing: `ST_LINELOCATEPOINT` style logic)
- [ ] **P2** Historical landslide inventory, Sentinel-2, USGS quakes

---

## 5. Detection & early-warning engine (deterministic core)

This is the Technical Merit centerpiece. It must be testable and explainable.

### 5.1 Pre-processing
- [x] **P0** Quality gate: coherence ≥ threshold (e.g., 0.6–0.7), minimum epoch count
- [x] **P0** Spatial filter: only points within asset buffer (`ST_DWITHIN`) - _done locally with shapely; BigQuery `ST_DWITHIN` port pending_
- [x] **P0** Cluster nearby moving points into sites (e.g., grid snap or `ST_CLUSTERDBSCAN`); minimum N points agree
- [x] **P0** Remove isolated single-point outliers

### 5.2 Metrics per site
- [x] **P0** Velocity (mm/month and mm/yr) over rolling windows
- [x] **P0** 60-day cumulative displacement
- [x] **P0** Acceleration ratio: recent 30d velocity ÷ prior baseline velocity
- [x] **P0** Persistence: consecutive epochs with same-sign motion
- [x] **P1** Seasonality flag: compare to same season prior year; label Seasonal vs Persistent
- [ ] **P1** Site-specific baseline band ("normal for this site")

### 5.3 State classification
- [x] **P0** States: Stable · Seasonal · Persistent creep · Accelerating · Threshold-approach · Data-degraded
- [x] **P0** Tier mapping documented in one table (state + exposure → tier) - _implemented in `tiering.assign_tier`; standalone doc table pending_
- [x] **P0** Asset-specific thresholds in config (highway ≠ metro ≠ dam/mine)

### 5.4 Forward outlook (time-to-threshold)
- [x] **P0** Two models: constant-velocity and accelerating (e.g., quadratic or exponential-ish fit)
- [x] **P0** Output ETA **band** (low–high days), not a single date
- [x] **P0** Confidence: function of coherence, epoch count, fit residual, point agreement
- [x] **P0** Always attach assumptions string ("if current regime continues; no new extreme rain/excavation")
- [x] **P0** Never output a failure date; copy reviewed for this - _enforced in code/tests; UI + agent copy review pending_
- [ ] **P1** Forecast invalidation flag when a new trigger (rain spike) lands after the forecast date
- [ ] **P1** Backtest on historical window: "ETA generated at month N vs threshold actually crossed" — report honestly, even if modest

### 5.5 Risk Priority Index
- [x] **P0** RPI = f(kinematic score, trigger score, asset criticality, confidence) — document weights
- [x] **P0** Confidence **reduces** rank (a weak signal must not outrank a strong one)
- [x] **P1** Explain-why-ranked-#1 payload for the UI

### 5.6 Tests
- [x] **P0** Unit tests: velocity, acceleration, ETA, tier mapping
- [x] **P0** Golden-case fixtures: stable site, seasonal site, accelerating site, noisy site (must be Data-degraded)
- [x] **P1** Test that low-coherence input never produces Critical

---

## 6. Backend (FastAPI)

### 6.1 Structure
- [x] **P0** `backend/` with modules: `api/`, `services/detection/`, `services/forecast/`, `services/agent/`, `services/data/`, `core/config`
- [ ] **P0** Pydantic models for all responses (Site, Metrics, Outlook, WorkOrder, Alert)
- [x] **P0** Config via env vars; no secrets in repo
- [x] **P0** CORS configured for frontend origin
- [x] **P0** `/healthz` endpoint

### 6.2 Endpoints
- [x] **P0** `GET /regions` · `GET /regions/{id}/summary`
- [x] **P0** `GET /sites?region=&tier=&bbox=&zoom=` (viewport-aware, clustered at low zoom)
- [x] **P0** `GET /sites/{id}` (metrics + outlook + evidence)
- [x] **P0** `GET /sites/{id}/timeseries?window=` - _done (no `window` param yet; returns full history + projection)_ - _done (no `window` param yet)_
- [x] **P0** `GET /sites/{id}/context` (rain, slope, asset exposure) - _rain + exposure merged into `GET /sites/{id}`; slope/DEM pending_
- [x] **P0** `POST /sites/{id}/workorder` (agent)
- [ ] **P1** `GET /alerts` · `PATCH /alerts/{id}` (ack/assign/escalate/false)
- [ ] **P1** `GET /regions/{id}/brief` (Morning Brief)
- [ ] **P1** `GET /workorders/{id}/pdf`

### 6.3 Performance & reliability
- [x] **P0** Viewport queries: never return full dataset; cap points per response
- [x] **P0** Server-side clustering at low zoom
- [x] **P0** Cache hot BigQuery results (in-memory / short TTL) so demo never stalls - _in-memory cache done; BigQuery backend pending_
- [x] **P0** Precompute `site_metrics` in batch; API reads precomputed rows - _precomputed once in memory; persisted table pending_
- [ ] **P0** Timeouts + retries on Open-Meteo and Vertex calls
- [x] **P0** Graceful degradation: if rain API fails, show "rain unavailable" and lower confidence — don't crash - _handled when rain is absent; no live Open-Meteo client yet_
- [ ] **P1** Request logging with correlation IDs

---

## 7. GenAI agent (Vertex AI Gemini)

### 7.1 Agent design
- [ ] **P0** Gemini model selected from currently available Vertex models (verify the model name in your project/region — don't hardcode a retired one) 🚩
- [x] **P0** Function calling with typed tools: - _implemented with google-genai; **live Vertex call not yet verified** (needs GCP credentials)_
  - `get_site_metrics(site_id)`
  - `get_displacement_history(site_id, window)`
  - `get_outlook(site_id)`
  - `get_rainfall_context(lat, lon)`
  - `get_asset_exposure(site_id)`
  - `get_data_quality(site_id)`
- [x] **P0** Tools return JSON from deterministic services only
- [x] **P0** System prompt: role, tier vocabulary, no-fabrication rule, hypothesis-labeling rule, uncertainty-required rule
- [x] **P0** Structured output schema (JSON) → rendered into the work order UI
- [x] **P0** Work order fields: tier, asset/chainage, evidence chain, outlook band, mechanism (hypothesis), field checklist, limitations, source citations (point IDs, dates)

### 7.2 Guardrails
- [x] **P0** Post-validation: every number in the output must match a tool-returned value; reject/regenerate otherwise 🚩 - _guard + 56 tests; retry-with-feedback implemented, untested against live model_
- [x] **P0** Block phrases: "will collapse", "guaranteed", exact failure date
- [x] **P0** If data-degraded, the agent must say so and must not escalate to Critical
- [x] **P0** Temperature low; deterministic where possible
- [x] **P0** Fallback template work order if Vertex errors/times out (demo must never show a blank) - _done and tested; Gemini path itself unverified live_
- [x] **P1** Log every tool call and response for audit - _tool calls recorded on each work order; no persistent log store yet_
- [ ] **P1** Few-shot examples per asset type (highway slope, metro settlement, dam crest)
- [ ] **P1** Mechanism template library (toe-unloading slip, settlement trough, crest bulge, seepage creep) — Gemini selects & adapts as hypothesis

### 7.3 Additional GenAI jobs
- [ ] **P1** Morning Brief writer (input = ranked alert list only)
- [ ] **P1** Uncertainty auditor (lists missing passes, coherence gaps, LOS limits)
- [ ] **P2** Director weekly summary
- [ ] **P2** Local-language work order via Translation API

### 7.4 Evaluation
- [ ] **P0** 5–10 fixed test sites; run agent; manually review for hallucinated numbers
- [x] **P1** Automated check script: extract numbers from output, diff against tool JSON

---

## 8. Frontend (React + TypeScript)

### 8.1 Setup
- [x] **P0** Vite + React + TypeScript
- [x] **P0** Design tokens from `docs/UX_UI_DESIGN_SYSTEM.md` as CSS variables
- [x] **P0** Fonts: IBM Plex Sans / Mono
- [x] **P0** State: lightweight (React Query for data + Zustand/Context for selection)
- [x] **P0** Env-based API URL

### 8.2 Map (core experience)
- [ ] **P0** Satellite basemap (choose a provider whose terms allow your use; Google Maps Platform key restricted by referrer, or MapLibre with an allowed imagery source) 🚩 - _working with Esri World Imagery + visible attribution; **terms of use for a competition/commercial demo NOT yet confirmed**_
- [x] **P0** Smooth zoom/pan: country → region → corridor → site
- [x] **P0** Progressive disclosure by zoom level (see design doc §7)
- [x] **P0** Corridor lines colored by worst tier
- [x] **P0** Point layer (MapLibre native circle layers) colored by tier - _deck.gl dropped: its ScatterplotLayer drew nothing in testing while path layers worked; native layers handle the capped point counts fine and cut ~780 kB of bundle_
- [ ] **P0** Cluster badges at mid zoom
- [x] **P0** Click → select site → open drawer
- [ ] **P0** Map ↔ Act List sync (list filters to viewport; list click flies to site) - _list click → fly-to and map marker click → drawer both verified; **list does not yet filter to the viewport**_
- [ ] **P1** Buffer polygon overlay
- [ ] **P1** Heatmap layer at site zoom
- [ ] **P1** Chainage ticks along corridor
- [ ] **P1** Time scrubber recoloring points
- [ ] **P1** Search by `NH-58 KM 74.2` style query
- [x] **P0** Legend + "Demonstration data" label when synthetic

### 8.3 Screens
- [x] **P0** Region Command Dashboard (KPI strip + Act List + map)
- [x] **P0** Site Intelligence drawer with tabs: Now · Trend · History · Outlook · Action
- [x] **P0** Work Order panel (checklist, limitations, citations)
- [x] **P0** Charts: displacement line with threshold line, baseline band, rain bars
- [ ] **P1** Alert Inbox
- [ ] **P1** Corridor Board (chainage ruler + sorted sites)
- [ ] **P1** Morning Brief panel
- [ ] **P2** Portfolio/Executive view
- [ ] **P2** Admin config

### 8.4 UX quality
- [ ] **P0** Loading skeletons, empty states, error states on every data panel - _plain "Loading..." text exists; skeletons and error states not yet audited panel by panel_
- [x] **P0** Tier badge component used everywhere (single source)
- [x] **P0** "Grounded brief" label with timestamp and sources next to AI text
- [ ] **P0** Uncertainty block always visible on Elevated/Critical
- [ ] **P0** Keyboard focus visible; contrast checked on dark theme
- [ ] **P1** Responsive down to tablet; field work-order view works on phone width
- [ ] **P1** Print stylesheet for work order - _written (`@media print` in App.css), not yet tested in a print preview_

---

## 9. Google Cloud infrastructure

### 9.1 Project setup
- [ ] **P0** GCP project + billing + budget alert (avoid surprise bills) 🚩
- [ ] **P0** Enable APIs: BigQuery, Cloud Run, Artifact Registry, Vertex AI, Cloud Storage, Secret Manager, Cloud Build
- [ ] **P0** Region chosen consistently (Vertex model availability varies by region — verify)
- [ ] **P0** Service accounts with least privilege (BigQuery data viewer/job user, Vertex user, storage object viewer)

### 9.2 Data plane
- [ ] **P0** GCS bucket for raw files + exports
- [ ] **P0** BigQuery dataset + loaded tables from §4.3
- [ ] **P0** Load scripts are re-runnable (idempotent)
- [ ] **P1** Scheduled query / Cloud Run Job to recompute `site_metrics`
- [ ] **P2** Pub/Sub trigger on new file upload → recompute → alerts

### 9.3 Deployment
- [ ] **P0** Dockerfile for backend; Dockerfile (or static build) for frontend
- [ ] **P0** Deploy backend to Cloud Run; set min instances = 1 for the judging window to avoid cold start 🚩
- [ ] **P0** Deploy frontend (Cloud Run or Firebase Hosting)
- [ ] **P0** Public URL works in a fresh incognito window, no login wall
- [ ] **P0** Secrets in Secret Manager, not env files in repo
- [ ] **P0** HTTPS only; CORS locked to the frontend origin
- [ ] **P1** CI: Cloud Build or GitHub Actions deploy on `main`
- [ ] **P1** Cloud Logging dashboards for errors/latency

### 9.4 Cost control
- [ ] **P0** Budget alerts at low thresholds
- [ ] **P0** Cap BigQuery bytes billed on queries; use partition filters
- [ ] **P0** Cache Vertex outputs per site per as-of date

---

## 10. Security & responsible-use

- [ ] **P0** No API keys / credentials in the repo or git history
- [ ] **P0** Rotate any key that was ever pasted into chat/commits
- [x] **P0** Public demo is read-mostly; rate-limit the agent endpoint to prevent abuse and cost blowup 🚩
- [ ] **P0** Input validation on all IDs/bbox params (no SQL injection — parameterized BigQuery queries only)
- [ ] **P0** Disclaimer in UI/README: decision-support for qualified engineers, not a certified safety system
- [ ] **P1** Auth for non-demo roles (Firebase Auth / Identity Platform) — demo can use role switcher
- [ ] **P1** Audit log of alerts and orders

---

## 11. Quality assurance

### 11.1 Functional
- [ ] **P0** Walk the full demo path 5× end-to-end on the deployed URL
- [ ] **P0** Every tier appears at least once in demo data
- [ ] **P0** Data-degraded site demonstrates the system staying honest
- [ ] **P0** Agent output reviewed for numeric fidelity on all demo sites
- [ ] **P0** Test with cold Cloud Run instance and slow network

### 11.2 Cross-checks
- [ ] **P0** Browser: Chrome + one other; screen resolution 1920×1080 and laptop 1366×768
- [ ] **P1** Lighthouse/performance sanity on map page
- [ ] **P1** Accessibility pass on color use (tier also encoded by text/icon, not color alone)

### 11.3 Claims audit
- [ ] **P0** Read every UI string, README line, and deck slide against the claims list (§14)

---

## 12. Documentation & repo (judges read this)

- [ ] **P0** Public GitHub repo, clean structure, meaningful commits from launch date
- [ ] **P0** README: problem, solution, architecture diagram, data provenance, how to run locally, how deployed, GCP services used, limitations, demo URL, video link
- [ ] **P0** Architecture diagram image (clean, labeled with GCP services)
- [ ] **P0** `docs/` includes: design system, data schema, detection logic (formulas), agent tool spec
- [ ] **P0** LICENSE file; data attribution (Copernicus/EGMS, Open-Meteo, etc.)
- [ ] **P1** `make`/script commands: `setup`, `load-data`, `dev`, `deploy`
- [ ] **P1** Sample `.env.example`
- [ ] **P1** Short "Methodology & limitations" doc (InSAR LOS caveat, revisit cadence, what is not predicted)

---

## 13. Pitch assets

### 13.1 Demo video (< 3:00, target 2:45–2:55)
- [ ] **P0** Script locked; one narrator, clean audio
- [ ] **P0** Structure:
  - 0:00–0:25 problem (silent mm creep, alert fatigue)
  - 0:25–0:50 solution (triage + early warning, not prediction)
  - 0:50–1:40 live demo: region → Act List → site → trend → outlook band → work order
  - 1:40–2:20 architecture: BigQuery GIS → deterministic engine → Gemini tool-calling (show real tool JSON)
  - 2:20–2:50 second asset type + impact + close
- [ ] **P0** Recorded against the **deployed** URL, not localhost
- [ ] **P0** 1080p, captions on key numbers, no dead air
- [ ] **P0** Uploaded (unlisted YouTube/Drive) and link tested logged-out
- [ ] **P1** Record a backup take

### 13.2 Pitch deck (8–10 slides)
- [ ] **P0** 1 Problem (with one real incident/stat you can cite)
- [ ] **P0** 2 Why current tools fail (alert fatigue, rainfall false alarms, raw InSAR)
- [ ] **P0** 3 Solution & user workflow
- [ ] **P0** 4 Product screenshots (map + site + work order)
- [ ] **P0** 5 Architecture on Google Cloud
- [ ] **P0** 6 GenAI approach: math detects, Gemini investigates, guardrails
- [ ] **P0** 7 Early-warning method & honest limits
- [ ] **P0** 8 Impact & buyers (highways, rail, metro, mines, dams, insurers)
- [ ] **P0** 9 Roadmap (P2 items, multi-region JAPAC)
- [ ] **P0** 10 Team
- [ ] **P1** Backup Q&A slide (see §14)

### 13.3 Cited facts
- [ ] **P0** Every statistic in the deck has a source you can name
- [ ] **P0** Verify the claims inherited from earlier brainstorming before using them (e.g., the MoRTH Char Dham InSAR announcement, NISAR data availability dates, "80% of slopes creep first" type figures) — treat unverified numbers as unusable 🚩

---

## 14. Claims discipline & judge Q&A

### Say
- [ ] "Early warning and inspection triage for ground motion under critical assets"
- [ ] "ETA band to an operational threshold, if the current trend continues"
- [ ] "Detects progressive creep and settlement; not flash mudflows"
- [ ] "Numbers come from tools; Gemini explains and drafts"

### Never say
- [ ] "Predicts landslides" / exact failure dates
- [ ] "Replaces engineers"
- [ ] "Real-time" for satellite motion (say "near-real-time per satellite pass, 6–12 day cadence")
- [ ] Anything about validated accuracy unless we measured it

### Prepared answers
- [ ] **P0** Why not if-else? → detection is deterministic; GenAI does multi-signal synthesis + actionable orders
- [ ] **P0** What about 6–12 day revisit? → targeting progressive failure; rain as trigger context
- [ ] **P0** Is data real? → show provenance slide and labeled datasets
- [ ] **P0** How do you avoid hallucination? → tool-only numbers + post-validation
- [ ] **P0** What if governments already use InSAR? → they get feeds; we add triage, ETA bands, and work-order workflow
- [ ] **P0** False alarms? → quality gates, clustering, confidence-weighted ranking, data-degraded silence
- [ ] **P1** Business model / buyers / pricing sketch

---

## 15. 48-hour execution timeline

| Block | Focus | Exit criteria |
|---|---|---|
| **T+0–2h** | Compliance gate, team roles, repo, GCP project, data decision | Repo live, APIs enabled, dataset chosen |
| **T+2–8h** | Data load + BigQuery schema + detection engine v1 | Sites with tiers in BigQuery |
| **T+8–14h** | FastAPI endpoints + map shell + Act List | Map shows tiered points, list syncs |
| **T+14–20h** | Site drawer + charts + outlook band | Full Site Intelligence works |
| **T+20–26h** | Gemini agent + guardrails + work order UI | Valid work order on 5 sites |
| **T+26–32h** | Deploy to Cloud Run, fix prod issues, second asset type | Public URL passes demo path |
| **T+32–38h** | P1 features (alerts, brief), polish, QA | Stable; scope **frozen** |
| **T+38–44h** | Video, deck, README, architecture diagram | Drafts complete |
| **T+44–48h** | Final QA, re-record if needed, submit with buffer | **Submitted ≥ 2h early** |

🚩 If behind schedule at T+14h: drop P1 features, keep P0 path intact. If behind at T+26h: drop second asset type before dropping agent guardrails.

---

## 16. Definition of Done (submission gate)

- [ ] Public Cloud Run URL loads in incognito and completes the demo path
- [ ] Satellite map zooms region → site; Act List synced
- [ ] ≥ 5 real/clearly-labeled sites across tiers incl. one Data-degraded
- [ ] Trend + history + outlook band render with threshold line
- [ ] Gemini tool-calling produces a validated work order (and fallback works)
- [ ] No fabricated numbers; synthetic data clearly labeled
- [ ] README, architecture diagram, data provenance, limitations complete
- [ ] Public GitHub repo with clean history and no secrets
- [ ] Demo video < 3:00, link works logged-out
- [ ] Pitch deck exported to PDF
- [ ] Submission form filled and confirmation received
- [ ] Team members all confirmed eligible

---

## 17. Top 10 failure modes (and the fix)

| # | Failure | Prevention |
|---|---|---|
| 1 | No usable real data by deadline | Decide data source in first 2h; labeled fallback ready |
| 2 | Cloud Run cold start in the judge's first click | Min instances = 1; warm before submit |
| 3 | Gemini hallucinated number on camera | Post-validation + fixed demo sites tested |
| 4 | Vertex model name/region mismatch | Verify model availability early |
| 5 | Map slow with many points | Viewport queries + clustering + point caps |
| 6 | Overclaim in Q&A | Claims list rehearsed |
| 7 | Scope creep into 8 datasets | P2 list is roadmap only |
| 8 | Leaked API key / surprise cloud bill | Secret Manager, budget alerts, endpoint rate limit |
| 9 | Demo shows localhost or errors | Record only from deployed URL; backup take |
| 10 | Submission rule violation (eligibility/pre-existing code) | §1 gate done first |

---

## 18. Winning-mindset principles

1. **Narrow and real beats broad and fake.** One corridor done properly outscores five pretend ones.
2. **Show the loop, not the pieces.** Map → ranked list → site evidence → outlook → work order in one flow.
3. **Make the honesty visible.** Confidence, limitations, and data-degraded states are features judges notice.
4. **Math owns truth; Gemini owns language.** Say it, show it, enforce it in code.
5. **Rehearse the demo path until boring.** The 3 minutes are the product.
6. **Submit early.** Last-hour submissions fail on upload quirks, not on features.
