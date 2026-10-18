# TerraSentinel test checklist

Legend: `[x]` verified (by an automated test or by checking it in the running app); `[ ]` not verified. A trailing note says how, or why not. Last full run: backend `pytest` 349 passed; frontend `tsc -b`, `oxlint` and `vite build` clean.

## A. Automated suites

- [x] Backend: 349 tests pass (`cd backend; .\.venv\Scripts\python.exe -m pytest -q`).
- [x] Frontend type-check clean (`npx tsc -b`).
- [x] Frontend lint clean (`npm run lint`, 0 warnings).
- [x] Frontend production build succeeds (`npm run build`).
- [ ] Frontend unit or component tests. None written; the UI was verified by hand-driven browser checks (section E).
- [ ] End-to-end browser suite (Playwright or similar). Not set up.

## B. Backend and API (covered by pytest)

- [x] Detection maths: state classification, velocity and acceleration, outlook bands (`test_detection`).
- [x] Pipeline and intelligence: ranking, early warning, what-if, passes (`test_pipeline`, `test_intel`).
- [x] API contract for core endpoints (`test_api`).
- [x] Data management API: provenance keeps demo entries until a kind is replaced; replace/append; reset (`test_data_api`).
- [x] Ingest validation: bad columns, bad dates, duplicates, units, plain-language findings (`test_ingest`).
- [x] Connectors: link import, rainfall fetch, SSRF guard (private/loopback hosts refused) (`test_connectors`).
- [x] Alert workflow: acknowledge, assign, escalate, resolve, reopen, history, persisted in `data/state`.
- [x] Detection engine properties and messy input: no crashes, deterministic, flat series never alarming, unusable data never outranks clean signal, monotonic in criticality and speed, finite projections (`test_engine_properties`).

## B2. Access control (pytest, plus live API and browser checks)

- [x] Passwords hashed with scrypt; wrong-password and unknown-user are indistinguishable; sessions store only a token hash; HttpOnly SameSite cookie (`test_auth`).
- [x] Role rules enforced on the server for every mutating route: viewer 403 on alert action and public fetch, analyst 200 on export and 403 on admin routes (checked live against the running API as well).
- [x] CSRF: a POST without the `X-Requested-With` header gets 403 (test and live).
- [x] Lockout after repeated wrong passwords, per username and address; audit entries for sign-in, failure, lockout, sign-out, account changes.
- [x] Changing a role, disabling an account or resetting a password ends that person's sessions (test; live: disabling an account made the open browser tab return to the sign-in page with "Your session ended").
- [x] Alert actor comes from the session, not the request body (`test_auth`).

## B3. Hardening (pytest)

- [x] Link fetch: private, loopback, link-local, CGNAT and IPv6-embedded-IPv4 addresses refused; DNS pinned to the checked address; each redirect re-resolved (`test_connectors`).
- [x] Workspace writes are transactional: failed import leaves data untouched, interrupted write recovered, concurrent imports do not lose rows (`test_hardening`).
- [x] Hostile input: deeply nested JSON, control characters in names and file names, non-positive limits, bad bounding boxes, unknown API paths return clean JSON errors.
- [x] Client address helper behaves with and without a trusted proxy; requests work with proxy trust switched on.
- [x] Rate limiter memory stays bounded when many clients are active.
- [x] Security headers and request id present (`test_auth`).

## B4. Public data store (pytest, plus live download)

- [x] Catalog, CSV storage, provenance, stale detection, preview, delete, seismic context per site, Gemini tool and template line (`test_public_data`).
- [x] Live: real USGS downloads stored as CSV (worldwide 30-day feed 1,904 events; 5-year M5+ feed; one region) and shown in the Data Hub and in the site drawer, labelled as context only.
- [x] Reset to demo keeps public dataset records.

## C. BigQuery

- [x] DDL and query SQL parse as valid BigQuery dialect (`sqlglot`, 82 tests in `test_bigquery`).
- [x] Repository logic gives the same results as the local backend, using the fake runner.
- [x] Cost guard sets `maximum_bytes_billed`; queries are parameterised.
- [x] Status endpoint degrades gracefully when no project is configured.
- [x] Connection doctor (`python -m app.services.bq.doctor` and Data Hub, Connection checks): correct ordering and fixes, read-only (`test_bq_doctor`). Live: run against this machine with no credentials, it reports "Google credentials: Fix" with the exact remedy and the note that a Gemini key is not a Google Cloud credential.
- [ ] Live: `setup --dry-run`, `setup --load-demo` against a real project. Needs Google Cloud credentials (not available: only a Gemini API key exists, which cannot authenticate BigQuery). Start with the doctor.
- [ ] Live: API served from BigQuery matches local output.
- [ ] Live: bytes billed for a full refresh is well under the guard.
- [ ] Live: daily job completes and records a pass.

Procedure: `docs/BIGQUERY.md`, section 6.

## D. Gemini

- [x] API key stored in the gitignored `backend/.env`; `.env.example` has no secret.
- [x] Key validated once with a plain `generateContent` call (model answered).
- [x] Provider selection (API key preferred over Vertex), model fallback on 404/429/5xx, forced-tool first round, bounded loop, budget cap, non-transient errors surfaced (`test_gemini_chain`, fake client, 11 tests).
- [x] Narrative guard rejects numbers or claims not supplied by tools; deterministic template fallback (`test_agent`).
- [x] Work order falls back to the template when the model chain fails, and says so in the `generated_by` field.
- [ ] Live: a full tool-grounded work order from Gemini. Not verified. The free tier allows about 20 requests per day per model and the primary model's daily quota was used up while testing; other models returned 503/429 or declined to call tools. Retry after the quota resets, or enable billing, then generate a work order for one CRITICAL site and compare its numbers with the site panel.

## E. UI pages (checked in the browser against real API data)

- [x] Command Center: KPIs, "New since last pass", prioritised action list, map, first-run guide.
- [x] Alerts: filters, acknowledge/assign/escalate/resolve/reopen, history.
- [x] Daily Brief renders.
- [x] Early Warning: time-to-threshold buckets, board, what-if sliders update the outlook.
- [x] Trends: site picker, chart renders.
- [x] Corridors and Portfolio render with data.
- [x] Work Orders: list, panel, notice states Gemini configured or not.
- [x] Methodology renders.
- [x] Sign-in page: renders, empty-form message, wrong-password message, successful sign-in lands on the Command Center, sign-out returns to sign-in and clears the cached data.
- [x] Session-ended path: an open tab whose session was ended by an admin shows the sign-in page with the session-ended notice on the next request.
- [x] Account menu: opens, shows name and role; change-password dialog opens with focus inside, Escape closes it. Submitting a new password through the dialog was not exercised in the browser (the endpoint is covered by `test_auth`).
- [x] Role gating in the UI: viewer sees no "Users & access" link, gets the "Not available for your role" message at the direct link, sees Public data, Datasets and Cloud tabs only in the Data Hub, and sees alerts as read-only.
- [x] Users & access (admin): people table, role selector, add-person form, role descriptions and activity list render with live data. Adding a person, resetting a password and the role selector were not clicked through in the browser (the API is covered by `test_auth`; the first-time account creation was done by script).
- [x] Data Hub, Public data: catalog cards with real stored data, preview toggle, scope filter.
- [x] Data Hub, Cloud and workspace: Connection checks run and display the doctor result.
- [x] Site drawer: "Earthquakes nearby (context)" shows real counts, nearest distance and largest historic event.
- [x] Served build (`http://127.0.0.1:8000/` from `frontend/dist`) works under the Content-Security-Policy: sign-in, map and satellite tiles render.
- [x] Data Hub: upload, validate with plain-language report, import; region rainfall fetch (Open-Meteo); regions; datasets and provenance; templates and export; reset to demo.
- [x] Link import: private-address and bad-URL attempts produce clear refusal messages.
- [x] Site drawer opens from list and map, closes on navigation.
- [x] Deep links: `#/path?region=..&site=..` restores region and open site.
- [x] Per-route error boundary keeps the shell alive.

## F. UX, accessibility, responsive

- [x] Light theme: white app background, MapLibre satellite map retained.
- [x] Contrast (WCAG AA 4.5:1, computed from the token values): body, secondary and muted text on white, canvas and subtle fills; white on brand; all tier badges; status and severity text on their soft fills. Fixes made: ELEVATED fill darkened to `#B85209`; severity labels use a darker `text` shade.
- [x] DOM accessibility audit: landmarks, skip link, heading order (work order headings fixed), labelled controls, no empty buttons.
- [x] Mobile layout at 390 px: off-canvas sidebar with menu button, no horizontal overflow (Trends fixed).
- [x] Reduced-motion rules present.
- [x] Sign-in form: labelled fields, `autocomplete` values, invalid state and described-by on errors, show/hide toggle with `aria-pressed` (read from the accessibility snapshot).
- [ ] Downloading from Public data, deleting a dataset and the region seismicity form were not clicked through in the browser as admin (API covered by `test_public_data`).
- [ ] Caps Lock hint and the "server unreachable" sign-in state were not triggered.
- [ ] Automated axe audit. Not run; the audit above was a hand-written DOM check.
- [ ] Full keyboard-only walkthrough. Not done.
- [ ] Screen-reader pass. Not done.
- [ ] Tablet (768 px) visual check. Only desktop and 390 px were checked.
- [ ] Map colour-blind check. Tier colours are paired with text labels in lists, not verified on the map.

## G. Performance and operations

- [x] Route-level code splitting; production build produces separate chunks.
- [ ] Map chunk is about 1 MB (`CommandCenter`, MapLibre) and the main bundle about 690 kB; not yet optimised.
- [ ] First Alerts or Trends view can take about 10 s until passes warm up in the background. Known; not fixed.
- [ ] Load or soak test. Not done.
- [ ] Cloud Run deployment. Not done.
- [ ] Docker image build and run. The `Dockerfile` has not been built (Docker is not installed on the development machine).
- [ ] Dependency vulnerability scan (`pip-audit -r backend/requirements.lock`). Blocked on the development machine; run it in CI.
- [ ] More than one server process. Accounts, sessions, lockouts and rate limits are per process by design (`docs/SECURITY.md`, section 9).
