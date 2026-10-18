# Judge story — production lens (AI Builder Cup)

How to evaluate TerraSentinel as a **production-shaped** sustainability product, not a slide deck.

**Live:** https://terrasentinel-598899050820.asia-southeast1.run.app  
**Credentials:** shown on the sign-in page (username + password). Sign in as admin for the full tour.  
**Cup submission deck (official template):** [`TerraSentinel-AI-Builder-Cup-Submission.pdf`](pitch/TerraSentinel-AI-Builder-Cup-Submission.pdf) · [`.pptx`](pitch/TerraSentinel-AI-Builder-Cup-Submission.pptx)  
Rebuild: `python docs/pitch/build_submission_deck.py`

---

## The story in one minute

Mountain roads, metros and dams fail slowly before they fail suddenly. InSAR satellites already measure ground motion to the millimetre — but operators still get **lists of points**, not **ranked decisions**.

TerraSentinel turns those measurements into:

1. **What to inspect today** (consequence × hazard × confidence)
2. **An honest outlook** — a time-to-threshold *band* if today’s trend continues — **never a failure date**
3. **An inspection ticket** drafted by Gemini from tool results only (no invented numbers)

Bundled corridor data is **synthetic demonstration data**, labelled in the product. The pipeline, auth, Data Hub and Cloud Run posture are what you are judging for production readiness.

---

## Five-minute walk (signed in)

| Step | Where | What to notice |
| --- | --- | --- |
| 1 | **Command Center** | Map + Act list. Red/elevated sites are ranked by consequence, not by raw millimetres. |
| 2 | Open one **CRITICAL / ELEVATED** site | Outlook is a **range of days**, with the continuing-regime assumption spelled out. |
| 3 | **Work Orders → Generate** | Ticket appears in seconds (template first). Gemini may refine wording; numbers still come from tools. |
| 4 | **Data Hub** | Provenance, validate-then-import, rainfall fetch, BigQuery sync. Reset to demo is available. |
| 5 | **Alerts / Morning Brief** | Diffs between satellite passes — what *changed*, not a duplicate of the Act list. |

Optional depth: **Methodology** (formulae), **Trends**, **Portfolio**, **Users & access** (RBAC + audit).

---

## Production layer (what is “real”)

| Layer | Production claim | Honesty limit |
| --- | --- | --- |
| **Edge** | Cloud Run, HTTPS, CSP, CSRF, rate limits, sessions, GCS-backed state, `max-instances=1` | Not multi-region HA |
| **API** | FastAPI + RBAC (admin / analyst / viewer) + audit log | Single-process topology |
| **Detection** | Deterministic Python engine; BigQuery warehouse optional | Demo InSAR is synthetic |
| **GenAI** | Gemini tool-calling; number guard; template fallback | Narrates only — does not invent scores |
| **Data Hub** | Validate → import; templates; public seismicity context | USGS does not change tiers |

Architecture detail: `docs/pitch/ARCHITECTURE_LAYERS.md` · deploy: `docs/DEPLOY.md` · security: `docs/SECURITY.md`.

---

## What “good” looks like for this Cup

- **Sustainability fit** — early warning for critical infrastructure under climate/geohazard stress  
- **GCP fit** — Cloud Run + BigQuery + Secret Manager + (optional) Gemini  
- **Integrity** — outlooks never claim a collapse date; synthetic data is labelled  
- **Operability** — a judge can sign in, act on a site, and see how data enters the system  

---

## Offline / local

```powershell
# backend/.env — for a local judge demo with credentials on the login page:
# TS_ADMIN_USER=admin
# TS_ADMIN_PASSWORD=your-demo-password
# TS_SHOW_LOGIN_HINT=true
```

Full run instructions: root `README.md`.
