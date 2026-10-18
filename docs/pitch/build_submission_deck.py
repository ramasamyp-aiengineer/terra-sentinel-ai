"""Fill the official AI Builder Cup submission PPTX with TerraSentinel content
from docs/pitch/index.html — denser, more technical, demo-value heavy.

Usage:
  python docs/pitch/build_submission_deck.py
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import nsmap
from pptx.oxml.ns import qn
from pptx.util import Emu, Pt
from lxml import etree

PITCH = Path(__file__).resolve().parent
SHOTS = PITCH / "shots"
TEMPLATE = Path(r"C:\Users\Magiz Creations 01\Downloads\Submission Template _ AI Builder Cup.pptx")
OUT_PPTX = PITCH / "TerraSentinel-AI-Builder-Cup-Submission.pptx"
OUT_PDF = PITCH / "TerraSentinel-AI-Builder-Cup-Submission.pdf"

SLIDE_W, SLIDE_H = 9144000, 5143500
# Under Google header (~507k) + our title band
L, R, B = 220_000, 220_000, 160_000
TOP = 1_100_000  # after we replace template titles with compact kickers
W = SLIDE_W - L - R

INK = RGBColor(0x0F, 0x1D, 0x1B)
MUTED = RGBColor(0x47, 0x58, 0x54)
BRAND = RGBColor(0x0F, 0x76, 0x6E)
BRAND2 = RGBColor(0x0D, 0x94, 0x88)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
SOFT = RGBColor(0xE7, 0xF4, 0xF1)
SOFT2 = RGBColor(0xF4, 0xF7, 0xF6)
LINE = RGBColor(0xCD, 0xD7, 0xD4)
BAD = RGBColor(0xC6, 0x28, 0x28)
BAD_SOFT = RGBColor(0xFD, 0xEC, 0xEC)
WARN = RGBColor(0xB4, 0x53, 0x09)
WARN_SOFT = RGBColor(0xFD, 0xF2, 0xE3)
OK = RGBColor(0x15, 0x80, 0x3D)
OK_SOFT = RGBColor(0xE8, 0xF5, 0xEC)
BLUE = RGBColor(0x1D, 0x4E, 0xD8)
BLUE_SOFT = RGBColor(0xE8, 0xEE, 0xFC)
SLATE = RGBColor(0x64, 0x74, 0x8B)


def _round_rect(shape):
    """Softer corners on rounded rectangles."""
    try:
        prstGeom = shape._element.spPr.prstGeom
        if prstGeom is not None:
            avLst = prstGeom.get_or_add_avLst()
            for gd in list(avLst):
                avLst.remove(gd)
            gd = etree.SubElement(avLst, qn("a:gd"))
            gd.set("name", "adj")
            gd.set("fmla", "val 12000")
    except Exception:
        pass


def card(slide, left, top, width, height, fill=SOFT, border=LINE, accent=None, accent_w=45000):
    sh = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Emu(left), Emu(top), Emu(width), Emu(height))
    _round_rect(sh)
    sh.fill.solid()
    sh.fill.fore_color.rgb = fill
    sh.line.color.rgb = border
    sh.line.width = Pt(0.75)
    if accent:
        bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Emu(left), Emu(top), Emu(accent_w), Emu(height))
        bar.fill.solid()
        bar.fill.fore_color.rgb = accent
        bar.line.fill.background()
    return sh


def tb(slide, left, top, width, height, lines, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP):
    """lines: list of (text, size, bold, color) or dict with optional space_after."""
    box = slide.shapes.add_textbox(Emu(left), Emu(top), Emu(width), Emu(height))
    tf = box.text_frame
    tf.word_wrap = True
    tf.auto_size = None
    try:
        tf._txBody.bodyPr.set("anchor", {MSO_ANCHOR.TOP: "t", MSO_ANCHOR.MIDDLE: "ctr", MSO_ANCHOR.BOTTOM: "b"}[anchor])
    except Exception:
        pass
    tf.clear()
    for i, item in enumerate(lines):
        if isinstance(item, dict):
            text, size, bold, color = item["t"], item.get("s", 12), item.get("b", False), item.get("c", INK)
            space = item.get("after", 3)
        else:
            text, size, bold, color = item
            space = 3
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.space_after = Pt(space)
        p.space_before = Pt(0)
        run = p.add_run()
        run.text = text
        run.font.size = Pt(size)
        run.font.bold = bold
        run.font.color.rgb = color or INK
        run.font.name = "Calibri"
    return box


def bullets(slide, left, top, width, height, items, size=11, color=INK, bold_first=False):
    box = slide.shapes.add_textbox(Emu(left), Emu(top), Emu(width), Emu(height))
    tf = box.text_frame
    tf.word_wrap = True
    tf.clear()
    for i, item in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.space_after = Pt(2)
        run = p.add_run()
        run.text = f"•  {item}"
        run.font.size = Pt(size)
        run.font.bold = bold_first and i == 0
        run.font.color.rgb = color
        run.font.name = "Calibri"
    return box


def chip(slide, left, top, width, height, text, fill=SOFT, ink=BRAND):
    sh = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Emu(left), Emu(top), Emu(width), Emu(height))
    _round_rect(sh)
    sh.fill.solid()
    sh.fill.fore_color.rgb = fill
    sh.line.color.rgb = LINE
    sh.line.width = Pt(0.5)
    tf = sh.text_frame
    tf.word_wrap = False
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    run = p.add_run()
    run.text = text
    run.font.size = Pt(9)
    run.font.bold = True
    run.font.color.rgb = ink
    run.font.name = "Calibri"
    try:
        tf._txBody.bodyPr.set("anchor", "ctr")
    except Exception:
        pass
    return sh


def img(slide, path: Path, left, top, width, height):
    if not path.exists():
        return None
    return slide.shapes.add_picture(str(path), Emu(left), Emu(top), Emu(width), Emu(height))


def replace_title(slide, kicker: str, headline: str):
    """Replace the template section-title text box with a compact brand kicker + headline."""
    for sh in list(slide.shapes):
        if not sh.has_text_frame:
            continue
        t = sh.text_frame.text.strip()
        # Template titles / prompts
        markers = (
            "Brief about",
            "Opportunities",
            "List of features",
            "Process flow",
            "Wireframes",
            "Architecture",
            "Technologies",
            "Estimated implementation",
            "Snapshots",
            "Prototype Performance",
            "Additional Details",
            "Provide links",
            "Team Details",
            "download this template",
            "Note: Please",
        )
        if any(m.lower() in t.lower() for m in markers) or (sh.top and sh.top < 2_000_000 and len(t) < 220):
            # Keep chrome pictures; rewrite text boxes in the title zone
            if sh.top is not None and sh.top < 2_200_000 and sh.has_text_frame:
                sh.text_frame.clear()
                # shrink height by moving — we rewrite in place
                lines = []
                if kicker:
                    lines.append((kicker.upper(), 9, True, BRAND))
                lines.append((headline, 16 if len(headline) < 90 else 13, True, INK))
                # Rebuild
                tf = sh.text_frame
                for i, (text, size, bold, color) in enumerate(lines):
                    p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
                    p.space_after = Pt(2)
                    run = p.add_run()
                    run.text = text
                    run.font.size = Pt(size)
                    run.font.bold = bold
                    run.font.color.rgb = color
                    run.font.name = "Calibri"
                return True
    # Fallback: draw our own title band
    tb(slide, L, 560_000, W, 480_000, [((kicker or "").upper(), 9, True, BRAND), (headline, 15, True, INK)])
    return False


def hide_template_titles(slide):
    """Blank leftover prompt-only title boxes that we already replaced poorly."""
    pass


# ─── Slides ───────────────────────────────────────────────────────────────────


def s01_team(slide):
    # Keep hero image on top; rewrite team text at bottom
    for sh in slide.shapes:
        if sh.has_text_frame and ("Team" in sh.text_frame.text or "Problem" in sh.text_frame.text):
            tf = sh.text_frame
            tf.clear()
            rows = [
                ("TEAM DETAILS  ·  AI BUILDER CUP 2026  ·  JAPAC  ·  SUSTAINABILITY", 10, True, BRAND),
                ("", 4, False, MUTED),
                ("Team name:  Agent Ram", 15, True, INK),
                ("Team leader:  Ramasamy P", 13, False, INK),
                ("Product:  TerraSentinel AI — ground-motion early warning for roads, metros & dams", 12, True, BRAND),
                ("", 4, False, MUTED),
                (
                    "Problem statement: After each Sentinel-1 pass, operators still face thousands of InSAR points "
                    "with no consequence ranking. TerraSentinel cuts motion into 250 m sites, ranks who inspects "
                    "today (RPI × tier), reports honest time-to-threshold bands (never failure dates), and uses "
                    "Gemini to draft a number-verified inspection ticket.",
                    11,
                    False,
                    INK,
                ),
            ]
            for i, (text, size, bold, color) in enumerate(rows):
                p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
                p.space_after = Pt(2)
                run = p.add_run()
                run.text = text
                run.font.size = Pt(size)
                run.font.bold = bold
                run.font.color.rgb = color
                run.font.name = "Calibri"
            return


def s02_cover(slide):
    replace_title(slide, "TerraSentinel AI", "Satellites see the ground move. Gemini tells engineers where to go first.")
    # Clear instruction note if still present
    for sh in slide.shapes:
        if sh.has_text_frame and "download this template" in sh.text_frame.text.lower():
            tf = sh.text_frame
            tf.clear()
            rows = [
                ("TerraSentinel AI", 20, True, BRAND),
                ("Which 250 metres should an engineer inspect today?", 13, True, INK),
                ("", 4, False, MUTED),
                (
                    "Roads, metro tunnels and dams can sink by a few millimetres for months before anything visible. "
                    "TerraSentinel ranks sites after every pass and Gemini writes the ticket — every number checked.",
                    11,
                    False,
                    MUTED,
                ),
            ]
            for i, (text, size, bold, color) in enumerate(rows):
                p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
                p.space_after = Pt(3)
                run = p.add_run()
                run.text = text
                run.font.size = Pt(size)
                run.font.bold = bold
                run.font.color.rgb = color
                run.font.name = "Calibri"

    # Stats strip over bottom of decorative area
    stats = [
        ("87 → 7", "sites to the few that need a crew", BRAND),
        ("RPI 86", "NH-58 CRITICAL · 35–64 day band", BAD),
        ("Gemini", "ticket from verified tool numbers", BRAND2),
        ("GCP", "Cloud Run · BigQuery · Vertex AI", BLUE),
    ]
    sw = (W - 90_000) // 4
    y = 3_650_000
    for i, (big, small, c) in enumerate(stats):
        x = L + i * (sw + 30_000)
        card(slide, x, y, sw, 900_000, SOFT, accent=c)
        tb(slide, x + 70_000, y + 80_000, sw - 100_000, 750_000, [(big, 18, True, c), (small, 10, False, MUTED)])


def s03_idea(slide):
    replace_title(slide, "Brief about the idea", "Ground creeps for months. Nobody ranks which creep matters — so crews go to the wrong place.")
    # Left: assets + one decision
    card(slide, L, TOP, 3_100_000, 1_050_000, BAD_SOFT, accent=BAD)
    tb(slide, L + 90_000, TOP + 60_000, 2_900_000, 950_000, [
        ("Mountain highways · NH-58", 11, True, BAD),
        ("Sole valley access. One slope slip cuts towns, pilgrims, supply.", 10, False, INK),
    ])
    card(slide, L, TOP + 1_120_000, 3_100_000, 900_000, WARN_SOFT, accent=WARN)
    tb(slide, L + 90_000, TOP + 1_180_000, 2_900_000, 800_000, [
        ("Metro tunnels · Chennai", 11, True, WARN),
        ("Settlement under roads & buildings. Tight tolerances, dense exposure.", 10, False, INK),
    ])
    card(slide, L, TOP + 2_100_000, 3_100_000, 900_000, SOFT2, accent=SLATE)
    tb(slide, L + 90_000, TOP + 2_160_000, 2_900_000, 800_000, [
        ("Dams & tailings · mining belt", 11, True, SLATE),
        ("Crest settlement / toe motion with severe downstream consequence.", 10, False, INK),
    ])
    card(slide, L, TOP + 3_080_000, 3_100_000, 700_000, SOFT, accent=BRAND)
    tb(slide, L + 90_000, TOP + 3_130_000, 2_900_000, 600_000, [
        ("The one decision we support", 9, True, BRAND),
        ("After this pass: which 250 m needs an engineer, why, and how soon?", 11, True, INK),
    ])

    # Right: fails today + we do/refuse
    card(slide, L + 3_250_000, TOP, W - 3_250_000, 2_050_000, WHITE)
    tb(slide, L + 3_350_000, TOP + 60_000, W - 3_450_000, 400_000, [("Today’s options fail the decision", 12, True, INK)])
    bullets(slide, L + 3_350_000, TOP + 420_000, W - 3_450_000, 1_550_000, [
        "Raw InSAR portal — thousands of points, no asset link, no “who goes today”",
        "Rainfall alarm — treats the trigger as the hazard; fires over stable ground",
        "Generic AI chatbot — fluent text that invents mm and failure dates",
        "Scheduled walk-over — calendar ignores which segment is accelerating now",
    ], size=10)

    card(slide, L + 3_250_000, TOP + 2_150_000, (W - 3_350_000) // 2, 1_650_000, OK_SOFT, accent=OK)
    tb(slide, L + 3_350_000, TOP + 2_210_000, (W - 3_550_000) // 2, 300_000, [("We do", 11, True, OK)])
    bullets(slide, L + 3_350_000, TOP + 2_520_000, (W - 3_550_000) // 2, 1_150_000, [
        "Progressive creep on linear assets",
        "Rank, explain, track between passes",
        "Threshold-crossing window + assumptions",
    ], size=10)

    rx = L + 3_250_000 + (W - 3_350_000) // 2 + 100_000
    card(slide, rx, TOP + 2_150_000, (W - 3_350_000) // 2, 1_650_000, BAD_SOFT, accent=BAD)
    tb(slide, rx + 100_000, TOP + 2_210_000, (W - 3_550_000) // 2 - 50_000, 300_000, [("We refuse", 11, True, BAD)])
    bullets(slide, rx + 100_000, TOP + 2_520_000, (W - 3_550_000) // 2 - 50_000, 1_150_000, [
        "Failure dates / collapse prediction",
        "Sudden events between 6–12 day passes",
        "Certified safety decisions",
    ], size=10)


def s04_opportunities(slide):
    replace_title(slide, "Opportunities · differentiation · USP", "Not another InSAR viewer — a decision layer with honest outlooks and guarded GenAI.")
    cols = [
        ("How different?", BRAND, [
            "250 m chainage sites on corridor geometry — not a heat-map of every scatterer",
            "RPI = hazard × consequence × confidence (deterministic Python / BigQuery)",
            "Pass-to-pass alerts = diffs; Act list = today’s state",
            "Rain amplifies only (capped +50%); USGS quakes never score",
            "Gemini narrates tool results; engine owns every number",
        ]),
        ("How it solves it", WARN, [
            "Ingest → validate → locate on assets → measure speed/accel/progress",
            "Classify with WEAK data guard (weak radar can never be CRITICAL)",
            "Rank Act-today shortlist for engineers",
            "Outlook = [ETA_const, ETA_accel] band ≤ 365 d — never a date",
            "Work order: summary · hypothesis · urgency · field checklist",
        ]),
        ("USP", BAD, [
            "Honest ETA bands with continuing-regime assumption spelled out",
            "Number guard rejects invented mm / “will collapse” language",
            "Same maths local CSV XOR BigQuery (TS_DATA_BACKEND)",
            "Production GCP posture: Cloud Run, Secret Manager, GCS state",
            "Demo value: 62,330 obs → 87 sites → 7 action → 4 Act today",
        ]),
    ]
    cw = (W - 120_000) // 3
    for i, (title, accent, items) in enumerate(cols):
        x = L + i * (cw + 60_000)
        card(slide, x, TOP, cw, 3_700_000, WHITE, accent=accent)
        tb(slide, x + 100_000, TOP + 80_000, cw - 160_000, 350_000, [(title, 13, True, accent)])
        bullets(slide, x + 80_000, TOP + 420_000, cw - 140_000, 3_150_000, items, size=10)


def s05_features(slide):
    replace_title(slide, "Features offered by the solution", "Command Center to Work Order — every surface ships a decision, not a dashboard toy.")
    feats = [
        ("Command Center", "Map + KPIs + Act today. CRITICAL/ELEVATED ranked by consequence, not raw mm."),
        ("Site drawer", "RPI, speed vs baseline, rain trigger, outlook band, trend across passes."),
        ("Alerts", "What changed between satellite passes — not a duplicate of the Act list."),
        ("Brief · Early Warning · Trends · Portfolio", "Planning views; history recomputed from data so past scores reproduce."),
        ("Work Orders + Gemini", "Template-first ticket; Gemini polishes via 7 tools; guard verifies numbers."),
        ("Data Hub", "Validate-then-import CSV/GeoJSON; Open-Meteo rain; provenance; BigQuery sync."),
        ("Access & audit", "admin / analyst / viewer RBAC · sessions · CSRF · audit log."),
        ("Methodology", "Published formulae so every score is auditable by an engineer."),
    ]
    cols, rows = 4, 2
    cw = (W - 90_000) // cols
    ch = 1_650_000
    for i, (t, b) in enumerate(feats):
        c, r = i % cols, i // cols
        x = L + c * (cw + 30_000)
        y = TOP + r * (ch + 80_000)
        card(slide, x, y, cw, ch, SOFT if (c + r) % 2 == 0 else WHITE, accent=BRAND)
        tb(slide, x + 80_000, y + 70_000, cw - 140_000, ch - 120_000, [
            (t, 11, True, BRAND),
            ("", 4, False, MUTED),
            (b, 10, False, INK),
        ])


def s06_process(slide):
    replace_title(slide, "Process / use-case flow", "One satellite pass: from space to a crew at the right 250 metres.")
    steps = [
        ("1 · Pass", "Every 6–12 days", "Sentinel-1 measures mm motion through cloud & night"),
        ("2 · Map", "Onto the asset", "1,355 points → highway / metro / dam → 87×250 m sites"),
        ("3 · Rank", "What matters", "Fast + accelerating + critical + good data rises; rain alone never alarms"),
        ("4 · Gemini", "Ticket", "Tools → reason → JSON → number guard → checklist"),
        ("5 · Next", "Keep watching", "Crew acts; next pass shows calm-down or worse"),
    ]
    sw = (W - 100_000) // 5
    for i, (a, b, c) in enumerate(steps):
        x = L + i * (sw + 25_000)
        card(slide, x, TOP, sw, 2_000_000, SOFT if i % 2 == 0 else WHITE, accent=BRAND)
        tb(slide, x + 50_000, TOP + 70_000, sw - 100_000, 1_850_000, [
            (a, 11, True, BRAND),
            (b, 12, True, INK),
            ("", 4, False, MUTED),
            (c, 9, False, MUTED),
        ], align=PP_ALIGN.CENTER)

    # Funnel strip
    card(slide, L, TOP + 2_150_000, W, 1_550_000, SOFT2)
    tb(slide, L + 80_000, TOP + 2_220_000, W - 160_000, 300_000, [("One pass on the demo dataset (labelled synthetic)", 10, True, BRAND)])
    funnel = [("62,330", "disp. obs"), ("1,355", "radar pts"), ("87", "250 m sites"), ("7", "CRIT/ELEV"), ("4", "Act today")]
    fw = (W - 200_000) // 5
    for i, (n, lab) in enumerate(funnel):
        x = L + 100_000 + i * fw
        tb(slide, x, TOP + 2_600_000, fw - 40_000, 900_000, [
            (n, 22, True, BAD if i >= 3 else BRAND),
            (lab, 10, False, MUTED),
        ], align=PP_ALIGN.CENTER)


def s07_wireframes(slide):
    replace_title(slide, "Product UI (live prototype)", "Not wireframes — the running product judges can open today.")
    shots = [
        (SHOTS / "c-command.png", "Command Center · Act list"),
        (SHOTS / "c-site-now.png", "Site Now · RPI & outlook"),
        (SHOTS / "c-workorder-ai.png", "Gemini work order"),
        (SHOTS / "c-datahub.png", "Data Hub · validate→import"),
    ]
    for i, (p, _) in enumerate(shots):
        if not p.exists() or p.stat().st_size < 40_000:
            alt = [SHOTS / "01-command-center.png", SHOTS / "04-nh58-site.png", SHOTS / "c-workorder.png", SHOTS / "app-datahub.png"][i]
            shots[i] = (alt, shots[i][1])
    cw = (W - 90_000) // 2
    ch = 1_600_000
    for i, (path, cap) in enumerate(shots):
        c, r = i % 2, i // 2
        x = L + c * (cw + 90_000)
        y = TOP + r * (ch + 70_000)
        img(slide, path, x, y, cw, ch - 90_000)
        card(slide, x, y + ch - 85_000, cw, 85_000, SOFT)
        tb(slide, x + 40_000, y + ch - 75_000, cw - 80_000, 70_000, [(cap, 10, True, BRAND)])


def s08_architecture(slide):
    replace_title(slide, "Architecture on Google Cloud", "One container · two storage backends · the same tested maths.")
    layers = [
        ("EDGE", "Cloud Run · HTTPS · CSP/HSTS · rate limits · session cookie · GCS state volume", INK),
        ("UI", "React 19 · MapLibre · React Query · role-aware screens", BLUE),
        ("API", "FastAPI · RBAC viewer/analyst/admin · CSRF · SSRF-safe fetch · audit", BRAND2),
        ("ENGINE", "numpy · pandas · shapely — metrics, RPI, tiers, ETA bands, alerts, pass replay", BRAND),
        ("GENAI", "Gemini tool loop · number guard · model fallback · AI Studio or Vertex (ADC)", WARN),
        ("DATA", "BigQuery (GEOGRAPHY, partitions) XOR local · USGS store · provenance", SLATE),
    ]
    lh = 480_000
    for i, (name, body, accent) in enumerate(layers):
        y = TOP + i * (lh + 25_000)
        card(slide, L, y, W, lh, WHITE, accent=accent, accent_w=60_000)
        tb(slide, L + 120_000, y + 70_000, 1_100_000, lh - 100_000, [(name, 11, True, accent)])
        tb(slide, L + 1_300_000, y + 70_000, W - 1_450_000, lh - 100_000, [(body, 11, False, INK)])


def s09_tech(slide):
    replace_title(slide, "Technologies", "Google Cloud end-to-end. Gemini turns a risk score into an action.")
    # Flow
    nodes = [
        ("Ingest", "Cloud Run\nData Hub validate"),
        ("Store", "BigQuery\nGIS join · history"),
        ("Compute", "Cloud Run\nrisk engine"),
        ("Explain", "Gemini\nVertex / Studio"),
        ("Act", "Engineers\nmap · ticket · audit"),
    ]
    nw = (W - 120_000) // 5
    for i, (t, b) in enumerate(nodes):
        x = L + i * (nw + 30_000)
        fill = SOFT if i != 3 else RGBColor(0x0F, 0x76, 0x6E)
        ink = WHITE if i == 3 else INK
        card(slide, x, TOP, nw, 1_150_000, fill, accent=BRAND if i != 3 else BRAND2)
        tb(slide, x + 40_000, TOP + 60_000, nw - 80_000, 1_000_000, [
            (t, 11, True, BRAND2 if i != 3 else WHITE),
            (b, 9, False, ink),
        ], align=PP_ALIGN.CENTER)

    # Two columns below
    card(slide, L, TOP + 1_300_000, W // 2 - 40_000, 2_400_000, WHITE, accent=BRAND)
    tb(slide, L + 90_000, TOP + 1_360_000, W // 2 - 200_000, 300_000, [("Gemini (what GenAI does)", 11, True, BRAND)])
    bullets(slide, L + 90_000, TOP + 1_700_000, W // 2 - 200_000, 1_850_000, [
        "7 read-only tools: metrics, history, outlook, rain, seismic, exposure, quality",
        "Round 0 MUST call tools → investigate → write JSON → guard",
        "Rejects inventing mm/days; rejects “will collapse” / failure dates",
        "Temp 0.1 · budget · fallback flash-latest → lite on 429/5xx",
        "Live proof: 6 tool calls · 7 numbers verified · “inspect within 24h”",
    ], size=9)

    card(slide, L + W // 2 + 40_000, TOP + 1_300_000, W // 2 - 40_000, 2_400_000, WHITE, accent=BLUE)
    tb(slide, L + W // 2 + 130_000, TOP + 1_360_000, W // 2 - 250_000, 300_000, [("GCP services & why", 11, True, BLUE)])
    bullets(slide, L + W // 2 + 130_000, TOP + 1_700_000, W // 2 - 250_000, 1_850_000, [
        "Vertex AI / AI Studio — Gemini for production & dev",
        "BigQuery — 9 tables, partitions, ST_DWITHIN join, bytes-billed cap",
        "Cloud Run — one image: SPA + API + engine + agent",
        "Secret Manager · GCS state · IAM via ADC (no key files)",
        "Open-Meteo + USGS egress through SSRF-safe fetcher",
    ], size=9)


def s10_cost(slide):
    replace_title(slide, "Estimated implementation cost (optional)", "Cup-scale economics: GenAI only on tickets; ranking stays deterministic.")
    items = [
        ("Cloud Run", "1–2 vCPU / 2 GiB · min-instances=1 while judging · scales to 0 off-hours", "low tens USD/mo warm"),
        ("BigQuery", "~62k TS rows · in-process TTL cache · maximum_bytes_billed on every job", "pennies–low USD demos"),
        ("Gemini Flash", "Work-order path only · template fallback · not on hot ranking path", "per-ticket, optional"),
        ("Secrets + GCS", "Admin/Gemini secrets · state volume for sessions/audit", "pennies"),
        ("Scale path", "Materialize assignment · raise instances · keep engine CPU-bound", "linear with corridors"),
    ]
    for i, (t, b, c) in enumerate(items):
        y = TOP + i * 680_000
        card(slide, L, y, W, 620_000, SOFT if i % 2 == 0 else WHITE, accent=BRAND)
        tb(slide, L + 100_000, y + 80_000, 2_200_000, 450_000, [(t, 12, True, BRAND)])
        tb(slide, L + 2_400_000, y + 80_000, 4_200_000, 450_000, [(b, 10, False, INK)])
        tb(slide, L + 6_700_000, y + 80_000, W - 6_900_000, 450_000, [(c, 10, True, MUTED)])


def s11_snapshots(slide):
    replace_title(slide, "Snapshots of the prototype", "Demo value on screen — Chamoli corridors, NH-58 CRITICAL, guarded ticket.")
    shots = [
        (SHOTS / "c-hero-map.png", "Chamoli · 69 sites · 4 act today"),
        (SHOTS / "c-map-chamoli.png", "Ranked map — not every scatterer"),
        (SHOTS / "c-site-now.png", "NH-58 · RPI 86 · 35–64 day band"),
        (SHOTS / "c-workorder-ai.png", "Gemini · numbers verified"),
    ]
    cw = (W - 90_000) // 2
    ch = 1_600_000
    for i, (path, cap) in enumerate(shots):
        if not path.exists():
            continue
        c, r = i % 2, i // 2
        x = L + c * (cw + 90_000)
        y = TOP + r * (ch + 70_000)
        img(slide, path, x, y, cw, ch - 90_000)
        card(slide, x, y + ch - 85_000, cw, 85_000, RGBColor(0x0F, 0x1D, 0x1B))
        tb(slide, x + 40_000, y + ch - 75_000, cw - 80_000, 70_000, [(cap, 10, True, WHITE)])


def s12_performance(slide):
    replace_title(slide, "Prototype performance / benchmarking", "NH-58 KM 3.25–3.50 end-to-end — same numbers in UI, tools, and work order.")
    # Left calculation
    card(slide, L, TOP, 4_600_000, 3_700_000, WHITE, accent=BAD)
    tb(slide, L + 90_000, TOP + 60_000, 4_400_000, 350_000, [("Worked example · CRITICAL · RPI 86", 12, True, BAD)])
    bullets(slide, L + 90_000, TOP + 420_000, 4_400_000, 3_100_000, [
        "Inputs: 6.2 vs 2.8 mm/mo · 2.2× accel · 29.7/40 mm progress · 213 mm rain · crit 0.95 · conf 0.97",
        "kin = 100×(.4·0.62 + .3·0.40 + .3·0.74) = 59.4",
        "hazard = 59.4 × (1 + 0.5×1.0) rain-capped = 89.1",
        "RPI = 89.1 × 0.975 × 0.985 ≈ 85.7 → CRITICAL (threshold approach)",
        "Outlook: 51 d const · 44 d accel · widened → 35–64 days if trend continues — NOT a failure date",
        "History: this site 61→86 RPI · portfolio action sites 3→7 over 16 recomputed passes",
        "What-if: minor road → 57 ELEVATED · poor radar → ≤15 WEAK · rain on stable → ≈1 STABLE",
    ], size=10)

    # Right image + latency
    img(slide, SHOTS / "c-site-trend.png", L + 4_800_000, TOP, W - 4_800_000, 2_200_000)
    card(slide, L + 4_800_000, TOP + 2_300_000, W - 4_800_000, 1_400_000, SOFT, accent=BRAND)
    tb(slide, L + 4_900_000, TOP + 2_360_000, W - 5_100_000, 1_250_000, [
        ("Live Cloud Run + BigQuery (warm)", 10, True, BRAND),
        ("summary ~0.4 s · sites ~0.3 s · alerts ~2 s", 10, False, INK),
        ("Hot-path prefetch before history warm", 10, False, INK),
        ("Integrity: GenAI never computes RPI/tier/ETA", 10, True, INK),
    ])


def s13_future(slide):
    replace_title(slide, "Additional details / future development", "Engineering invariants stay fixed. Scale the data plane — not the honesty rules.")
    card(slide, L, TOP, W // 2 - 40_000, 3_700_000, WHITE, accent=BRAND)
    tb(slide, L + 90_000, TOP + 70_000, W // 2 - 220_000, 300_000, [("Roadmap", 12, True, BRAND)])
    bullets(slide, L + 90_000, TOP + 400_000, W // 2 - 220_000, 3_100_000, [
        "Production InSAR providers on the same Data Hub schema",
        "Materialize point-assignment for national corridors",
        "Multi-region HA once session store leaves single-process files",
        "Field checklist / offline packet for crews",
        "OIDC / IAP sign-in for enterprise buyers",
        "Deeper rain/geology as amplifiers only",
    ], size=11)

    card(slide, L + W // 2 + 40_000, TOP, W // 2 - 40_000, 3_700_000, SOFT, accent=WARN)
    tb(slide, L + W // 2 + 130_000, TOP + 70_000, W // 2 - 250_000, 300_000, [("Buyer · ask · honesty", 12, True, WARN)])
    bullets(slide, L + W // 2 + 130_000, TOP + 400_000, W // 2 - 250_000, 3_100_000, [
        "Buyer: asset-integrity / geotech teams (highway, metro, dam, mine)",
        "What they buy: engineer attention — 1,355 points → 7 sites",
        "Ask: live demo + 3-min video + repository",
        "Outlook bands ≠ collapse dates — always",
        "Gemini narrates tools only — always",
        "Synthetic demo data labelled in UI — always",
    ], size=11)


def s14_links(slide):
    replace_title(slide, "Submission links", "GitHub · 3-minute demo video · live product.")
    links = [
        ("GitHub public repository", "https://github.com/ramasamyp-aiengineer/terra-sentinel-ai", BRAND),
        ("Demo video (3 minutes)", "docs/pitch/TerraSentinel-AI-Demo-3min.mp4 — upload to Drive/YouTube for the portal", WARN),
        ("Final product (live)", "https://terrasentinel-598899050820.asia-southeast1.run.app", BLUE),
    ]
    for i, (t, u, c) in enumerate(links):
        y = TOP + i * 1_050_000
        card(slide, L, y, W, 950_000, WHITE, accent=c, accent_w=70_000)
        tb(slide, L + 150_000, y + 120_000, W - 300_000, 700_000, [
            (t, 14, True, c),
            (u, 12, False, INK),
        ])
    tb(slide, L, TOP + 3_250_000, W, 500_000, [
        ("Sign-in: username + password are shown on the login page (judge demo hint).  Judge walk: docs/JUDGE.md", 11, False, MUTED),
    ])


def s15_engine_formulas(slide):
    """Use spare chrome slide for the core maths from the HTML engine slide."""
    tb(slide, L, 560_000, W, 450_000, [
        ("RISK ENGINE · DETERMINISTIC", 9, True, BRAND),
        ("Measure → Score → Project. Plain rules first, then the exact maths.", 14, True, INK),
    ])
    # Three columns
    cw = (W - 100_000) // 3
    blocks = [
        ("1 · Measure", BRAND, [
            "Recent speed: slope last 60 d (mm/mo)",
            "Baseline: 270→90 d ago",
            "Accel = |recent| / max(|base|, 0.5)",
            "Persistence · seasonal recovery",
            "Site series = median in 250 m bin",
            "conf = .30coh+.15ep+.20pts+.20agr+.15SNR",
            "Weak data capped — never CRITICAL",
        ]),
        ("2 · Score", WARN, [
            "kin = 100·(.4 speed + .3 accel + .3 prog)",
            "hazard = kin·(1 + 0.5·rain14d/200)",
            "RPI = hazard × (0.5+0.5·crit)",
            "        × (0.5+0.5·conf)",
            "Slow/far: ×0.2 · Seasonal: ×0.35",
            "WEAK cap 15 · quakes never scored",
            "CRITICAL / ELEVATED / WATCH rules",
        ]),
        ("3 · Project", BAD, [
            "ETA_const = remaining ÷ speed",
            "ETA_accel = root of a·t²+b·t+c = T",
            "band = [min,max] ≤ 365 d",
            "close? → [.75, 1.35]·mid",
            "Highway 40 mm/180 d · creep 2.0",
            "Metro 25 mm · Dam 30 mm (demo)",
            "ALWAYS a band — NEVER a date",
        ]),
    ]
    for i, (title, accent, items) in enumerate(blocks):
        x = L + i * (cw + 50_000)
        card(slide, x, TOP, cw, 3_700_000, WHITE, accent=accent)
        tb(slide, x + 80_000, TOP + 70_000, cw - 140_000, 300_000, [(title, 12, True, accent)])
        bullets(slide, x + 70_000, TOP + 400_000, cw - 120_000, 3_150_000, items, size=10)


def s16_thanks(slide):
    # Full-bleed thank you over template end art where possible
    card(slide, L, 900_000, W, 3_600_000, WHITE, accent=BRAND, accent_w=80_000)
    logo = SHOTS / "logo-mark.jpg"
    if logo.exists():
        img(slide, logo, L + 150_000, 1_050_000, 550_000, 550_000)
    tb(slide, L + 800_000, 1_100_000, W - 1_000_000, 600_000, [
        ("TerraSentinel AI", 20, True, BRAND),
        ("Thank you — Team Agent Ram", 16, True, INK),
    ])
    tb(slide, L + 150_000, 1_800_000, W - 400_000, 1_800_000, [
        ("Which 250 metres should an engineer inspect today?", 14, True, INK),
        ("The engine ranks them. Gemini writes the ticket. Every number is checked.", 12, False, MUTED),
        ("", 8, False, MUTED),
        ("Ramasamy P  ·  ramp21052000@gmail.com  ·  +91 90250 32130", 12, False, BRAND),
        ("Live demo + GitHub + 3-min video  ·  Google Cloud AI Builder Cup 2026 · Sustainability", 11, False, MUTED),
        ("", 6, False, MUTED),
        ("Gemini · Vertex AI   ·   BigQuery   ·   Cloud Run   ·   Sentinel-1 InSAR", 11, True, INK),
    ])


def export_pdf(pptx: Path, pdf: Path) -> bool:
    try:
        import win32com.client  # type: ignore
    except ImportError:
        print("pywin32 missing — open PPTX and export PDF manually", file=sys.stderr)
        return False
    app = win32com.client.Dispatch("PowerPoint.Application")
    app.Visible = 1
    try:
        pres = app.Presentations.Open(str(pptx.resolve()), WithWindow=False)
        # ppSaveAsPDF = 32; also try export for better fidelity
        if pdf.exists():
            pdf.unlink()
        pres.SaveAs(str(pdf.resolve()), 32)
        pres.Close()
        print(f"Wrote {pdf}")
        return True
    finally:
        app.Quit()


def main() -> int:
    if not TEMPLATE.exists():
        print(f"Template not found: {TEMPLATE}", file=sys.stderr)
        return 1
    shutil.copy2(TEMPLATE, OUT_PPTX)
    prs = Presentation(str(OUT_PPTX))
    fillers = [
        s01_team,
        s02_cover,
        s03_idea,
        s04_opportunities,
        s05_features,
        s06_process,
        s07_wireframes,
        s08_architecture,
        s09_tech,
        s10_cost,
        s11_snapshots,
        s12_performance,
        s13_future,
        s14_links,
        s15_engine_formulas,
        s16_thanks,
    ]
    for i, fn in enumerate(fillers):
        if i < len(prs.slides):
            fn(prs.slides[i])
    prs.save(str(OUT_PPTX))
    print(f"Wrote {OUT_PPTX}")
    export_pdf(OUT_PPTX, OUT_PDF)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
