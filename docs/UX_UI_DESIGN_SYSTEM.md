# TerraSentinel — UX / UI Design System

> **Superseded for colour and layout.** The app now uses a light theme (white app background, satellite map kept). The current tokens, navigation and page designs are in `UX_UI_PLAN_V2.md`; the source of truth in code is `frontend/src/index.css` and `frontend/src/lib/tier.ts`. The dark palette below is kept only as history. The risk-tier meanings and "colour means risk only" rule still hold.

**Goal:** Simple, fast decision UI. Not a science dashboard. Not generic AI chrome.  
**Rule:** Satellite map is the stage. Ranked actions are the script. Color means risk status only.

---

## 1. Design thesis

> Calm control-room product. Zoom the satellite map to inspect. Use the side panel to decide.

| Do | Don’t |
|---|---|
| Dark shell + bright satellite map | Purple gradients / neon glow |
| Flat panels, 1px borders | Heavy cards, multi-shadow stacks |
| Tier color = only strong accent | Rainbow decoration everywhere |
| One primary action per panel | Competing CTAs and pill clusters |
| Evidence next to AI text | Chatbot floating with no numbers |

---

## 2. Color palette

### 2.1 App shell

| Token | Hex | Use |
|---|---|---|
| `--bg-app` | `#0F1419` | Page background |
| `--bg-panel` | `#171D25` | Side panels, drawers |
| `--bg-panel-2` | `#1E2630` | Table headers, nested blocks |
| `--bg-elevated` | `#262F3B` | Hover / selected row |
| `--border` | `#2E3947` | Dividers, input borders |
| `--border-strong` | `#3D4B5C` | Active edge / focus container |

### 2.2 Text

| Token | Hex | Use |
|---|---|---|
| `--text-primary` | `#E8EEF4` | Titles, key numbers |
| `--text-secondary` | `#9AA8B8` | Labels, secondary info |
| `--text-muted` | `#6B7A8C` | Timestamps, hints |
| `--text-inverse` | `#0F1419` | Text on bright badges |

### 2.3 Brand (sparse)

| Token | Hex | Use |
|---|---|---|
| `--brand` | `#3D8B7A` | Logo, links, focus ring |
| `--brand-soft` | `#1A3330` | Soft selected chip |

Field teal — institutional, not “AI purple.”

### 2.4 Risk tiers (system meaning)

| Tier | Label | Hex | Meaning |
|---|---|---|---|
| T0 | Stable | `#3F9C6B` | No action |
| T1 | Watch | `#C4A035` | Monitor |
| T2 | Elevated | `#D97706` | Plan inspection |
| T3 | Critical | `#C4473A` | Act today |
| — | Data weak | `#7A8494` | Do not over-trust |

**Rules**
- Only these colors encode risk on map pins, rows, and badges.
- Never use Critical red for decoration.
- Acceleration arrow uses same tier color as the site.

### 2.5 Semantic extras

| Token | Hex | Use |
|---|---|---|
| `--info` | `#3B82A0` | Info tips, tool citations |
| `--success` | `#3F9C6B` | Ticket closed / ack OK |
| `--warning` | `#D97706` | Forecast invalidated |
| `--danger` | `#C4473A` | Critical alert only |

### 2.6 Chart / motion series

| Token | Hex | Use |
|---|---|---|
| `--series-motion` | `#5BA4A0` | Displacement line |
| `--series-baseline` | `#6B7A8C` | Normal band |
| `--series-rain` | `#3B82A0` | Rain bars (secondary axis) |
| `--series-threshold` | `#C4473A` | Threshold guide line (dashed) |

### 2.7 Map overlays

| Layer | Color / style |
|---|---|
| Satellite basemap | Real imagery (no tint) |
| Corridor line stable | `#3F9C6B` @ 80% |
| Corridor elevated/critical | Tier color @ 90%, 3–4px |
| InSAR point stable | `#3F9C6B` |
| InSAR point watch/elevated/critical | Matching tier |
| Cluster badge | Dark pill `#171D25` + tier dot |
| Selected site ring | `#E8EEF4` 2px outer ring |
| Buffer polygon | `#3D8B7A` fill 12%, stroke 40% |

---

## 3. Typography

**Fonts**
- UI / body: `IBM Plex Sans` (clear, engineering, not Inter/Roboto default cliché)
- Numbers / chainage / mm values: `IBM Plex Mono`

| Role | Size | Weight | Color |
|---|---|---|---|
| App title | 16px | 600 | primary |
| Panel title | 14px | 600 | primary |
| Section label | 11px | 600 | muted, uppercase, 0.04em tracking |
| Body | 13px | 400 | secondary |
| Key metric | 22–28px | 600 | primary + mono |
| Table cell | 12–13px | 400 | primary/secondary |
| Badge text | 11px | 600 | inverse or primary |

**Line height:** 1.4 UI text, 1.25 metrics.

---

## 4. Spacing & radius

| Token | Value |
|---|---|
| Base unit | 4px |
| Panel padding | 12–16px |
| Row gap | 8px |
| Section gap | 16px |
| Radius small | 4px (badges, inputs) |
| Radius panel | 8px (drawers, modals) |
| Radius map controls | 6px |
| No giant rounded “pills” for primary nav |

Borders: `1px solid var(--border)` only.  
Shadows: none, or single soft `0 8px 24px rgba(0,0,0,0.35)` for drawers only.

---

## 5. Layout (every main screen)

```text
┌─ Top bar (48px): logo | region select | search | time window | user ─┐
├──────────── 360px ────────────┬──────────── flex map ────────────────┤
│ Decision panel                │ Satellite map (full zoom)            │
│ • KPIs                        │ • overlays by zoom                   │
│ • Act list / alerts           │ • click → select site                │
│ • filters                     │                                      │
└───────────────────────────────┴──────────────────────────────────────┘
│ Optional bottom/site drawer: Now | Trend | History | Outlook | Action │
└──────────────────────────────────────────────────────────────────────┘
```

**Split:** ~36% decisions / ~64% map on desktop.  
**Mobile field mode:** work order first; map collapsed to pin preview.

---

## 6. Components (keep few)

### 6.1 Tier badge
- Height 20px, radius 4px, padding 0 8px
- Background = tier hex, text = `--text-inverse`
- Label: `STABLE` / `WATCH` / `ELEVATED` / `CRITICAL`

### 6.2 Act list row
- Left: tier badge  
- Main: site name + chainage  
- Meta: velocity, trend arrow, ETA band  
- Right: primary ghost button `Open`  
- Selected: `--bg-elevated` + left 2px `--brand`

### 6.3 KPI chip
- Quiet: label muted, number primary mono  
- No colorful KPI boxes — number turns tier-colored only if that KPI is Critical count

### 6.4 Buttons
| Type | Style |
|---|---|
| Primary | Fill `--brand`, text inverse |
| Danger | Fill `--danger` (Escalate / Critical only) |
| Secondary | Border `--border-strong`, text primary |
| Ghost | Text secondary, hover elevated |

One primary button per panel.

### 6.5 Tabs (Site Intelligence)
`Now · Trend · History · Outlook · Action`  
Active = bottom 2px `--brand`, text primary. Inactive = muted.

### 6.6 Work order panel
- Monospace-friendly block for ticket header  
- Checklist as simple squares, not fancy cards  
- Uncertainty block: muted border, `--info` label `LIMITATIONS`

### 6.7 Alert card
- Left tier stripe 3px  
- Title + one evidence line  
- Actions: Acknowledge · Assign · Escalate  

---

## 7. Map UX (coordinated with UI)

| Zoom | Show |
|---|---|
| Far | Corridor colors by worst tier |
| Mid | Clusters + alert badges |
| Near | Chainage + pins |
| Site | Points + optional heatmap + select ring |

Controls (top-right on map), compact dark glass:
- Basemap  
- Motion / Heat / Assets toggles  
- Fit region · Fit corridor · Fit site  

Search bar in top app bar: `NH-58 KM 74.2`

---

## 8. Icon & motion rules

- Icons: simple line set (Lucide), 16–18px, `--text-secondary`
- No emoji in product UI
- Motion: only 2–3 uses  
  1. Map fly-to (300–500ms)  
  2. Drawer slide-in  
  3. Critical pin soft pulse (opacity only, slow)

---

## 9. Content tone in UI

| Bad | Good |
|---|---|
| “AI Insights” | “Evidence summary” |
| “Predicted collapse” | “Approaching threshold (4–8 weeks)” |
| “Autonomous defense” | “Inspection priority” |
| Generic chatbot empty state | “Select a site on the map or Act list” |

AI block label: **Grounded brief** (with source timestamps).

---

## 10. Persona → chrome

| Persona | Default accent emphasis |
|---|---|
| Control room | Alert inbox + Critical count |
| Engineer | Corridor + site tabs |
| Field | Work order checklist (light text, big tap targets) |
| Director | KPI strip + region compare (no clutter) |

Same palette; different default landing widgets.

---

## 11. CSS variables (copy-ready)

```css
:root {
  --bg-app: #0F1419;
  --bg-panel: #171D25;
  --bg-panel-2: #1E2630;
  --bg-elevated: #262F3B;
  --border: #2E3947;
  --border-strong: #3D4B5C;

  --text-primary: #E8EEF4;
  --text-secondary: #9AA8B8;
  --text-muted: #6B7A8C;
  --text-inverse: #0F1419;

  --brand: #3D8B7A;
  --brand-soft: #1A3330;

  --tier-stable: #3F9C6B;
  --tier-watch: #C4A035;
  --tier-elevated: #D97706;
  --tier-critical: #C4473A;
  --tier-weak: #7A8494;

  --info: #3B82A0;
  --series-motion: #5BA4A0;
  --series-rain: #3B82A0;

  --radius-sm: 4px;
  --radius-md: 8px;
  --font-ui: "IBM Plex Sans", "Segoe UI", sans-serif;
  --font-mono: "IBM Plex Mono", ui-monospace, monospace;
}
```

---

## 12. Quick checklist before demo

- [ ] Map readable at country and site zoom  
- [ ] Act list and map selection stay in sync  
- [ ] Only tier colors used for risk  
- [ ] Work order visible without hunting  
- [ ] Uncertainty always shown on Critical sites  
- [ ] No purple glow, no emoji, no decorative cards  

---

## 13. One-line UI promise

**Dark, simple shell. Satellite zoom to verify. Green→red only for risk. Panel tells you what to do today.**
