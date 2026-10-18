# TerraSentinel AI · 3-minute demo video script

**Target length:** 2:50–3:00  
**Audience:** Google Cloud AI Builder Cup 2026 judges (JAPAC · Sustainability)  
**Tone:** Calm, engineer-first. Never claim failure dates. Say “demo data” once early.  
**File to ship:** `docs/pitch/TerraSentinel-AI-Demo-3min.mp4` + YouTube/Drive upload

---

## One-line story the judge must remember

> A satellite leaves 1,355 moving points. TerraSentinel ranks the few that matter. Gemini reasons, summarises, and creates the ticket — every number checked.

---

## Shot list (what appears on screen)

| Time | Screen | Action |
| --- | --- | --- |
| 0:00–0:12 | Title card | Logo + “Which 250 m should an engineer inspect today?” |
| 0:12–0:28 | Command Center · India | Map loads; show CRITICAL 3 / ELEVATED 4 / Act today |
| 0:28–0:48 | Data Hub | Open Data Hub; show provenance; upload / validate panel; “synthetic demo” label |
| 0:48–1:08 | Command Center · Chamoli | Switch region; zoom map; hover CRITICAL NH-58 |
| 1:08–1:35 | Site · NH-58 Now + Trend | Open site; show RPI 86, speed, rain; flip to Trend (61 → 86) |
| 1:35–1:50 | Trends & History | Portfolio lines: action sites 3 → 7; highest RPI rises |
| 1:50–2:35 | Work Orders · Gemini ticket | Open live ticket; scroll evidence → outlook → action → checklist; show “numbers verified” |
| 2:35–2:50 | Architecture card / Methodology | Quick flash: engine computes · Gemini narrates · guard |
| 2:50–3:00 | End card | Team Agent Ram · Google Cloud · Ask: demo + repo |

---

## Narration (speak this)

### 0:00–0:12 · Open
**Voice:**  
“Which 250 metres should an engineer inspect today?  
Satellites see the ground move. TerraSentinel ranks what matters. Gemini tells the engineer where to go first.”

**On screen:** Title card → cut to Command Center.

---

### 0:12–0:28 · The problem, in product
**Voice:**  
“After one pass on our demonstration dataset — labelled synthetic — we have sixty-two thousand displacement observations, cut into eighty-seven sites of 250 metres. Only seven are Critical or Elevated. Four need a crew today.”

**On screen:** India Command Center; point at Act today list and tier counts.

---

### 0:28–0:48 · Data Hub (upload / provenance)
**Voice:**  
“Everything starts in Data Hub. Engineers upload InSAR points, time series, assets and rainfall — or import from a link. Every file is validated in plain language before it enters the model. Provenance is kept for every dataset. Bad formats are refused.”

**On screen:** Data Hub — datasets list, provenance, validation / upload UI. Briefly show Add / Upload affordance. Do **not** paste secrets.

---

### 0:48–1:08 · Rank on the map
**Voice:**  
“Zoom to Chamoli. Sixty-nine sites along the Himalayan corridor. The map is not a heat-map of every moving point — it is the ranked shortlist. Rain alone never raises the alarm. Earthquakes are context only; they never move the score.”

**On screen:** Region = Chamoli; map with CRITICAL / ELEVATED markers; open NH-58 callout if visible.

---

### 1:08–1:35 · One site, end to end
**Voice:**  
“Open NH-58, kilometre 3.25 to 3.50. Risk Priority Index eighty-six — Critical. Moving 6.2 millimetres a month, twice the baseline. Two hundred and thirteen millimetres of rain in fourteen days amplifies motion; it is not the hazard by itself.  
The outlook is a threshold-crossing window of thirty-five to sixty-four days **if this trend continues** — not a failure date.”

**On screen:** Site panel Now tab; highlight RPI, speed, rain, outlook band. Switch to Trend: show the rise.

---

### 1:35–1:50 · What changed across passes
**Voice:**  
“Trends and History replays sixteen satellite passes from the same data. Action sites rose from three to seven. This site itself climbed from sixty-one to eighty-six. History is recomputed — every past score is reproducible.”

**On screen:** Trends & History page / charts.

---

### 1:50–2:35 · Gemini (the AI moment)
**Voice:**  
“Now the generative AI. Gemini does **not** compute risk. The engine already did that.  
Gemini investigates with seven read-only tools — metrics, history, outlook, rain, earthquakes, exposure, data quality. It reasons over those facts, summarises what is happening, and creates the inspection ticket: recommended action and a field checklist.  
A guard verifies every millimetre and every day against the tool results. Unsupported numbers and failure-date language are rejected. On this live ticket: six tool calls, seven numbers verified. Recommendation: dispatch an inspection crew within twenty-four hours.”

**On screen:** Work Orders — full ticket. Scroll slowly: header → evidence → outlook → action → checklist. Pause on “numbers verified” / guard language if visible.

---

### 2:35–2:50 · Trust + Google Cloud
**Voice:**  
“Built for Google Cloud: Cloud Run, BigQuery-ready storage, Vertex AI or AI Studio for Gemini. Deterministic maths. Tool-grounded narration. Auditable decisions.”

**On screen:** Brief methodology / architecture flash, or end-card icons: Gemini · BigQuery · Cloud Run.

---

### 2:50–3:00 · Close
**Voice:**  
“TerraSentinel AI — Team Agent Ram. Review the live demo, this video, and the repository. Thank you.”

**On screen:** End card with logo, team, contact email (optional), Cup branding.

---

## Words you must NOT say

- “will fail / collapse / fail in N days”
- “AI predicts landslides with X% accuracy”
- “we have a paying customer” (unless true)
- Secret keys, admin passwords, `.env` contents

## Words you should say once

- “demonstration / synthetic data”
- “threshold window / if the trend continues — not a failure date”
- “Gemini never computes the risk score”

---

## Recording checklist (when filming live)

1. Backend on `:8000`, frontend on `:5173`, signed in as analyst/admin.
2. Region starts on **India**, then **Chamoli**.
3. Have Work Order for Metro Line 4 or NH-58 already generated (or generate live if Gemini key is set).
4. Cursor large; zoom 110% in Edge if text is small.
5. Capture **1680×1000** or **1920×1080**, 30 fps.
6. Upload to YouTube **unlisted** or public Drive; paste link in the Cup submission form.
7. Keep a local copy at `docs/pitch/TerraSentinel-AI-Demo-3min.mp4`.

---

## Fallback if live Gemini is slow

Use the already-drafted work order on screen and say:  
“This ticket was drafted by Gemini with tool calling; seven numbers verified by the guard.”  
Do not pretend a new call is happening if the spinner stalls.
