# TerraSentinel UI / UX Plan v2 (enterprise level)

Status: plan first, then build. Supersedes the dark-theme layout in `UX_UI_DESIGN_SYSTEM.md` (tokens there are being migrated to the light theme below).
This plan is written from four seats: the layperson, the daily operator, the hackathon judge, and the architect.

---

## 1. The four lenses

### 1.1 Layperson (30-second test)
A person who has never heard of InSAR opens the app. Within 30 seconds they must be able to say:

1. "This watches roads, metro lines and dams for slow ground movement using satellites."
2. "These few places need a person to go and look. Red is worst."
3. "It tells me roughly how many days until a place reaches its safety limit, as a range, not a prediction."

What this demands:
- **Answer first.** The first screen leads with "N sites need action today", not a map of dots.
- **Plain words everywhere, jargon on demand.** Visible label "Risk score" with a hover/tap explanation "Risk Priority Index (RPI)". Visible "Speed 6.4 mm/month", not "LOS velocity".
- **Honest uncertainty.** Outlooks are always ranges and always say "if the current trend continues".
- **A way in.** First-run "How to read this" card (3 steps) and a Help entry in the sidebar; every chart has a one-line caption saying what to notice.

### 1.2 Operator (the daily job: control room / asset engineer)
Job to be done: "Which places do I send a crew to today, what changed since yesterday, and who owns it?"

- Morning loop (target under 2 minutes): Command Center -> new-since-last-pass strip -> Act List -> open a site -> Work order -> assign.
- Triage loop for alerts: filter -> acknowledge / assign / escalate / resolve, with history so a shift handover loses nothing.
- Needs: keyboard-first search (`/`), deep links to share a site with a colleague, print / PDF for the morning brief and work orders, stable ordering (the list must not reshuffle under the cursor).

### 1.3 Judge (3-minute demo, scored on impact, technical depth, Google Cloud use, UX, feasibility)
The UI must make each criterion visible without narration:

| Criterion | Where a judge sees it |
|---|---|
| Real problem and impact | Command Center headline, corridor "Why it matters", Portfolio exposure |
| Technical depth | Early Warning (band from two regimes, what-if), Trends (reproducible passes), Methodology page |
| Google Cloud + Gemini | Data source chip (BigQuery), Data Hub BigQuery panel, work order "Gemini + numbers verified against tools" badge, Morning Brief |
| Trustworthy AI | "Numbers verified against tools (N)" chip, evidence table with sources, deterministic fallback notice |
| Product completeness | Ten real pages, upload / link / rainfall fetch, alert workflow, empty / error states, responsive |
| Feasibility | Methodology limitations, Data Hub validation reports, cost guard note |

Demo script (3 min): Command Center (10 s) -> click critical site (Outlook tab, band) (40 s) -> Early Warning what-if slider (30 s) -> Alerts assign (20 s) -> Work order with verified-numbers badge (30 s) -> Data Hub upload with validation (30 s) -> Portfolio (20 s).

### 1.4 Architect (what makes it enterprise-grade, not a dashboard)
- One **information architecture** driven by a single `NAV` list (sidebar, router, titles, breadcrumbs, command palette).
- **URL is state** (region, selected site, filters) so every view is linkable and the back button works.
- **Every data-bound component has all five states**: loading, empty, error (with retry), partial/stale, success.
- **Server-state cache keys are a contract** (`['alerts', region, status, severity]` etc.) so mutations invalidate precisely.
- **Provenance is a first-class UI object**: data source, as-of, dataset registry, tool-verified numbers.
- **Accessible by construction**: WCAG 2.2 AA, risk never encoded by colour alone, full keyboard path, reduced motion.
- **Performance budgets**: first useful paint < 2 s on cached data, route chunks lazy-loaded, map points capped and clustered, no list > 200 rows without virtualisation or paging.

---

## 2. Design principles

1. **Answer, then evidence, then action.** Each page opens with the answer, offers evidence one click away, and ends with an action.
2. **One primary action per screen.** Everything else is secondary or ghost.
3. **Risk = colour + word + number.** `CRITICAL` text in the badge, not just red.
4. **Calm by default.** White surfaces, thin borders, colour reserved for risk and the single brand accent. Alert fatigue is a product risk.
5. **The map is the only dark/rich surface.** Satellite imagery stays; the application chrome is white.
6. **No dead ends.** Every empty state says why and what to do next (usually a link to the Data Hub).
7. **Never hide uncertainty.** Bands, confidence labels, "not a failure prediction" wording.

---

## 3. Information architecture

```
Monitor        Command Center  /            map + KPIs + Act List + what changed
               Alerts          /alerts      changes between passes, workflow
               Morning Brief   /brief       one printable page
Intelligence   Early Warning   /early-warning   time-to-threshold board + what-if
               Trends & History /trends     risk across passes, risers / fallers, site timeline
               Corridors       /corridors   asset -> chainage strip -> worst sites
               Portfolio       /portfolio   regions, asset types, rain, data health
Operate        Work Orders     /workorders  queue + grounded ticket (print)
Data           Data Hub        /data        upload, link, rainfall, regions, datasets, export, cloud
Reference      Methodology     /methodology rules, thresholds, limitations
```

Global chrome: sidebar (grouped nav, open-critical badge on Alerts) Â· top bar (region scope, global search, data-source chip, as-of, alert bell) Â· site drawer (works from any page; tabs Now / Trend / History / Outlook / Action).

Region is a **global scope**: changing it re-scopes every page. The top bar always shows which region and which data (Demo / Workspace / BigQuery) you are looking at.

---

## 4. Core journeys and acceptance

| # | Journey | Steps | Acceptance |
|---|---|---|---|
| J1 | Morning triage | Open app -> read headline KPIs -> "new since last pass" -> open top site -> work order | Reachable in <= 5 clicks, no scrolling on 1440x900 |
| J2 | Alert handling | Alerts -> filter open -> assign with owner -> history shows entry | Assign without an owner is blocked; history persists after reload |
| J3 | Explore the outlook | Early Warning -> bucket filter -> what-if slider | Scenario updates within 1 s; engine band always shown as authoritative |
| J4 | Bring my own data | Data Hub -> drop file -> Check -> read report -> Import | Import disabled until check passes; row-level errors listed with row numbers; nothing saved before Import |
| J5 | Fetch from a link | Data Hub -> paste https URL -> Check -> Fetch & import | Private / internal URLs rejected with a clear message |
| J6 | Add a region and its rainfall | Regions -> add -> Rainfall -> fetch | New region appears in the top-bar picker without reload |
| J7 | Executive view | Portfolio -> click a region -> Command Center scoped | Region changes everywhere |
| J8 | Share a finding | Copy URL of a site / alert view | URL reopens the same view (deep link) |

---

## 5. Page specifications

Each page: purpose -> the one question it answers -> key content -> states.

- **Command Center.** "What needs doing today?" Left: region header + tier bar, 4 KPIs, "new since last pass" (max 3), Act List (ranked, stable). Right: satellite map with tier layer, corridors, zoom HUD, legend. Empty: "All clear".
- **Alerts.** "What changed?" Summary stats, status + severity filters, grouped by satellite pass date, card per alert with tier move, RPI, owner, actions, collapsible history. Empty: "Nothing changed enough to alert on".
- **Morning Brief.** "Brief me." Headline, tier bar, sections of bullets generated from computed values, top actions, print / save PDF. Narrow reading column.
- **Early Warning.** "How long do we have?" Bucket tiles (0-30, 31-60, 61-120, 121-365, exceeded) as filters, table with progress to threshold, 0-365 d band, outlook, delta RPI, expandable what-if with assumptions.
- **Trends & History.** "Is it getting better or worse?" Five stat deltas vs oldest pass, tier trend, RPI trend, risers / fallers, per-site timeline.
- **Corridors.** "Where along the line?" Asset list with tier bars, chainage strip (250 m bins, click to inspect), worst sites, assessment profile, "View on map".
- **Portfolio.** "Where is risk concentrated?" Totals, by-region / asset-type tables with tier bars, rain trigger table, stale-data warning, top sites.
- **Work Orders.** "What do I hand to the crew?" Queue (drafted / not drafted), ticket with evidence table, checklist, limitations, print. Mode notice: Gemini vs template.
- **Data Hub.** "Is my data in, and can I trust it?" Counts, tabs: Import (file + link side by side), Rainfall, Regions, Datasets (provenance), Templates & export, Cloud & workspace (BigQuery status / sync, reset to demo with confirm).
- **Methodology.** "Why should I believe it?" Pipeline, tier rules, RPI formula and guards, per-asset profiles, alert rules, limitations.

---

## 6. Design system (light theme)

### 6.1 Colour tokens
| Role | Token | Value |
|---|---|---|
| App background | `--bg-app` | `#FFFFFF` |
| Page canvas (behind cards) | `--bg-canvas` | `#F5F7FA` |
| Subtle fill / hover | `--bg-subtle` / `--bg-hover` | `#F1F4F8` / `#EBF0F5` |
| Border / strong border | `--border` / `--border-strong` | `#E1E6EC` / `#C7D0DA` |
| Text primary / secondary / muted | `--text-*` | `#14202B` / `#46566A` / `#5E6C7E` (all >= 4.5:1 on white) |
| Brand (single accent) | `--brand` | `#0F766E` (hover `#0B5F58`, soft `#E6F4F2`) |
| Risk: critical / elevated / watch / stable / weak | `--tier-*` | `#C62828` / `#B85209` / `#B58900` / `#2A7F4F` / `#6B7785` |
| Status: ok / warn / bad / info (+ soft fills) | `--ok --warn --bad --info` | `#1F7A4A` `#9A5B00` `#B3261E` `#1D6FA5` |

Rules: brand teal is for actions and selection only; red/orange/amber/green only for risk and status; never use a risk colour for decoration.

### 6.2 Type and space
- IBM Plex Sans (UI) and IBM Plex Mono (numbers, ids, dates). Base 14 px / 1.45. Scale 11 (labels) Â· 12 (meta) Â· 14 Â· 16 (card titles) Â· 22 (page titles) Â· 26 (stat values).
- 4 px spacing grid; card padding 16 px; page gutter 24 px (16 px on mobile); max content width 1280 px, reading pages 880 px.
- Radius 6 / 10 px. Shadows only on overlays (drawer, popovers).

### 6.3 Components (all in `components/ui.tsx`)
PageHeader Â· Card Â· Stat Â· Chip (neutral / brand / ok / warn / bad / info) Â· Btn (primary / secondary / ghost / danger, loading) Â· Segmented Â· Field Â· DataTable Â· Empty Â· Loading Â· ErrorBox Â· Notice Â· TierBadge Â· TierBar Â· EtaBand Â· ChainageStrip Â· Sparkline.

### 6.4 Charts
Tier colours only for tier series; one teal for "motion"; grey for baseline; blue for rain. Direct labels or legends plus accessible `aria-label` summaries on every SVG. Axis labels >= 11 px.

### 6.5 States matrix (each data component)
Loading (spinner + what is loading) Â· Empty (reason + next step) Â· Error (message + Retry) Â· Success Â· Stale (data older than N days: warning banner, never silent).

---

## 7. Enterprise capabilities

| Area | Plan | Status |
|---|---|---|
| Navigation | Grouped sidebar, global search (`/`), region scope, deep-linkable hash routes | Built; **deep-link of region/site: planned** |
| Auditability | Alert action history with actor, timestamp, note; dataset provenance registry; tool-call list on work orders | Built |
| Data governance | Validate-before-import, row-level errors, replace requires explicit confirm, reset to demo requires confirm | Built |
| Security | Sign-in, roles, SSRF-safe fetch with DNS pinning, CSRF header, security headers, rate limits, secrets only in `.env` | Built; see `docs/SECURITY.md` |
| Accessibility | Skip link, landmarks, `aria-current`, `aria-pressed`, combobox pattern, focus-visible, reduced motion, text + colour | Built; **audit with axe: planned** |
| Responsive | Sidebar collapses to a menu, tables scroll horizontally, drawer full-screen on mobile, 2-col grids stack | Planned in CSS |
| Print | Morning Brief and work order print cleanly (chrome hidden) | Planned in CSS |
| Roles (viewer / analyst / admin) | Enforced by the server; the UI hides what a role cannot use and explains why (section 7.1) | Built |
| i18n | Strings centralised later; numbers/dates already via helpers | Future |

### 7.1 Sign-in, account and access

- **Sign-in page.** Split layout: a brand panel that states the product promise in three lines (ranked by consequence, honest outlooks, traceable) and a form card. Labelled fields with correct `autocomplete` values, show/hide password, Caps Lock hint, empty-form message, wrong-password and lockout messages in plain language, a "your session ended" notice when the server ends a session, and a retry when the server cannot be reached. The brand panel collapses to a short header on narrow screens. Submit is not disabled when the form is empty, so keyboard users get an explanation instead of a dead button.
- **No flash of app content.** The app renders a neutral loading state until the server confirms who you are. Sign-in and sign-out clear every cached record and reset the open site, so nothing from one person's session shows for the next.
- **Account menu** (top bar): name, username and role; change password (dialog, native `<dialog>` so focus is trapped and Escape closes); sign out.
- **Role-aware screens.** Viewers see Alerts and work orders read-only. Analysts act on alerts and draft work orders. Data Hub shows import, rainfall and regions to admins only; everyone sees Public data, Datasets and the cloud status. The "Users & access" page is in the menu for admins only and shows an explanation if opened by link by anyone else.
- **Users & access (admin).** People table (role, status, last sign-in, reset password, disable), add a person with a suggested temporary password shown once, a plain description of each role, and recent security activity.

### 7.2 Public data and context

Data Hub, **Public data**: a catalog of open earthquake datasets (USGS) with publisher, license, stored size and date range, fingerprint, stale badge, preview of the largest events and delete. Admins download or refresh worldwide feeds and fetch the catalog around one region. In the site drawer, **Earthquakes nearby (context)** states recent counts, the largest recent and historic events and the nearest distance, and always says that earthquakes are not part of the risk score. Cloud and workspace has **Connection checks** for BigQuery (read-only, with the exact fix for each failure).

---

## 8. Frontend architecture

```
src/
  api/        client.ts (typed fetch + ApiError, CSRF header, session-lost event), types.ts
  lib/        router.ts (NAV with optional role, hash router), auth.ts (useAuth, useCan, login/logout), tier.ts, format.ts
  store.ts    UI-only state (region, selection, map target). Server data lives in react-query.
  components/ ui.tsx (design system), Sidebar, TopBar, GlobalSearch, SiteDrawer, MapView, charts, ...
  pages/      one lazy-loaded file per route
```
- Server state: react-query, `staleTime` 60 s; mutations invalidate by key prefix.
- Routes are `React.lazy` chunks; the map library only loads on the Command Center.
- Error boundary per route; API errors show human messages (`ApiError`), network failure says "Is the backend running?".
- No business logic in the UI: thresholds, tiers, outlooks and verification all come from the API.

---

## 9. Delivery order and exit criteria

1. Light-theme tokens + `App.css` (all shared components styled). *Exit:* every page renders without unstyled elements at 1440 and 390 px.
2. App shell + 10 pages compile (`tsc -b`, `eslint`) with zero errors.
3. Browser verification of each page against real API data (DOM assertions + screenshots).
4. Data Hub flows verified end to end (file, link, rainfall, region, reset).
5. Deep links (region + site in the URL) and "How to read this" first-run card.
6. Accessibility pass (axe) and keyboard walkthrough; responsive pass.
7. Update `TEST_CHECKLIST.md`; tick only what was verified.
