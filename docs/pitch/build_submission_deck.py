"""Build the official AI Builder Cup submission deck — safe layouts, no overlap.

Layout rules (EMU, 10\" × 5.625\"):
  Google header image ends ~507k
  Section title band: 560k → 1,220k
  CONTENT starts at 1,280k
  FOOTER chrome starts ~5,072k → content ends by 4,920k
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Pt
from lxml import etree

try:
    from PIL import Image as PILImage
except ImportError:
    PILImage = None  # type: ignore

PITCH = Path(__file__).resolve().parent
SHOTS = PITCH / "shots"
TEMPLATE = Path(r"C:\Users\Magiz Creations 01\Downloads\Submission Template _ AI Builder Cup.pptx")
OUT_PPTX = PITCH / "TerraSentinel-AI-Builder-Cup-Submission.pptx"
OUT_PDF = PITCH / "TerraSentinel-AI-Builder-Cup-Submission.pdf"

SLIDE_W, SLIDE_H = 9_144_000, 5_143_500

# ── Safe canvas (never draw outside) ─────────────────────────────────────────
MARGIN_X = 260_000
TITLE_BOTTOM = 1_260_000          # below template title text
FOOTER_TOP = 4_920_000            # above Google footer bar
CONTENT_TOP = TITLE_BOTTOM + 40_000
CONTENT_H = FOOTER_TOP - CONTENT_TOP
CONTENT_W = SLIDE_W - 2 * MARGIN_X
GAP = 70_000

# ── Unified palette (matches HTML deck) ──────────────────────────────────────
INK = RGBColor(0x0F, 0x1D, 0x1B)
MUTED = RGBColor(0x47, 0x58, 0x54)
BRAND = RGBColor(0x0F, 0x76, 0x6E)
BRAND2 = RGBColor(0x0D, 0x94, 0x88)
SOFT = RGBColor(0xE7, 0xF4, 0xF1)
PANEL = RGBColor(0xF4, 0xF7, 0xF6)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
LINE = RGBColor(0xCD, 0xD7, 0xD4)
BAD = RGBColor(0xC6, 0x28, 0x28)
BAD_BG = RGBColor(0xFD, 0xEC, 0xEC)
WARN = RGBColor(0xB4, 0x53, 0x09)
WARN_BG = RGBColor(0xFD, 0xF2, 0xE3)
OK = RGBColor(0x15, 0x80, 0x3D)
OK_BG = RGBColor(0xE8, 0xF5, 0xEC)
BLUE = RGBColor(0x1D, 0x4E, 0xD8)
BLUE_BG = RGBColor(0xE8, 0xEE, 0xFC)
SLATE = RGBColor(0x64, 0x74, 0x8B)


def _corners(shape, adj="8000"):
    try:
        geom = shape._element.spPr.prstGeom
        if geom is None:
            return
        av = geom.get_or_add_avLst()
        for g in list(av):
            av.remove(g)
        gd = etree.SubElement(av, qn("a:gd"))
        gd.set("name", "adj")
        gd.set("fmla", f"val {adj}")
    except Exception:
        pass


def card(slide, x, y, w, h, fill=PANEL, border=LINE, accent=None):
    sh = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Emu(x), Emu(y), Emu(w), Emu(h))
    _corners(sh)
    sh.fill.solid()
    sh.fill.fore_color.rgb = fill
    sh.line.color.rgb = border
    sh.line.width = Pt(0.75)
    if accent:
        bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Emu(x), Emu(y), Emu(36_000), Emu(h))
        bar.fill.solid()
        bar.fill.fore_color.rgb = accent
        bar.line.fill.background()
    return sh


def text(slide, x, y, w, h, lines, align=PP_ALIGN.LEFT):
    """lines: (str, size_pt, bold, color) — kept short so nothing overflows the box."""
    box = slide.shapes.add_textbox(Emu(x), Emu(y), Emu(w), Emu(h))
    tf = box.text_frame
    tf.word_wrap = True
    try:
        tf._txBody.bodyPr.set("anchor", "t")
    except Exception:
        pass
    tf.clear()
    for i, (t, size, bold, color) in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.space_after = Pt(2)
        p.space_before = Pt(0)
        run = p.add_run()
        run.text = t
        run.font.size = Pt(size)
        run.font.bold = bold
        run.font.color.rgb = color
        run.font.name = "Calibri"
    return box


def bullets(slide, x, y, w, h, items, size=10):
    box = slide.shapes.add_textbox(Emu(x), Emu(y), Emu(w), Emu(h))
    tf = box.text_frame
    tf.word_wrap = True
    tf.clear()
    for i, item in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.space_after = Pt(3)
        run = p.add_run()
        run.text = f"•  {item}"
        run.font.size = Pt(size)
        run.font.color.rgb = INK
        run.font.name = "Calibri"
    return box


def set_title(slide, kicker: str, headline: str):
    """Rewrite the template title text box only — do not add a second title."""
    for sh in slide.shapes:
        if not sh.has_text_frame:
            continue
        if sh.top is None or sh.top > 1_800_000:
            continue
        # Title / instruction boxes live under the header
        t = (sh.text_frame.text or "").strip()
        if not t and sh.height and sh.height < 200_000:
            continue
        markers = (
            "Brief", "Opportunities", "List of", "Process", "Wireframe", "Architecture",
            "Technologies", "Estimated", "Snapshots", "Prototype", "Additional",
            "Provide links", "Team Details", "download", "Note:", "TerraSentinel",
            "PRODUCT", "RISK", "Submission", "How different",
        )
        if any(m.lower() in t.lower() for m in markers) or (sh.left and sh.left < 500_000 and sh.width and sh.width > 7_000_000):
            tf = sh.text_frame
            tf.clear()
            tf.word_wrap = True
            p0 = tf.paragraphs[0]
            p0.space_after = Pt(2)
            r0 = p0.add_run()
            r0.text = kicker.upper()
            r0.font.size = Pt(9)
            r0.font.bold = True
            r0.font.color.rgb = BRAND
            r0.font.name = "Calibri"
            p1 = tf.add_paragraph()
            p1.space_after = Pt(0)
            r1 = p1.add_run()
            # Keep headline short enough for one/two lines in the title band
            r1.text = headline[:110]
            r1.font.size = Pt(14 if len(headline) < 80 else 12)
            r1.font.bold = True
            r1.font.color.rgb = INK
            r1.font.name = "Calibri"
            return
    # Fallback title inside safe zone (rare)
    text(slide, MARGIN_X, 580_000, CONTENT_W, 600_000, [
        (kicker.upper(), 9, True, BRAND),
        (headline[:110], 13, True, INK),
    ])


def pic(slide, path: Path, x, y, max_w, max_h):
    """Place image preserving aspect ratio; never stretch/collapse."""
    if not path.exists():
        return None, 0, 0
    if PILImage is not None:
        with PILImage.open(path) as im:
            iw, ih = im.size
    else:
        iw, ih = 16, 9
    aspect = iw / max(ih, 1)
    w = max_w
    h = int(w / aspect)
    if h > max_h:
        h = max_h
        w = int(h * aspect)
    # Center in the allotted cell
    ox = x + (max_w - w) // 2
    oy = y + (max_h - h) // 2
    slide.shapes.add_picture(str(path), Emu(ox), Emu(oy), Emu(w), Emu(h))
    return path, w, h


def shot_cell(slide, path: Path, x, y, w, h, caption: str):
    """Screenshot cell: frame + aspect-correct image; caption sits BELOW the frame (no overlap)."""
    CAP = 120_000
    PAD = 36_000
    frame_h = h - CAP - 24_000
    if frame_h < 400_000:
        frame_h = max(h - 80_000, 400_000)
        CAP = h - frame_h - 24_000
    card(slide, x, y, w, frame_h, WHITE, LINE)
    pic(slide, path, x + PAD, y + PAD, w - 2 * PAD, frame_h - 2 * PAD)
    # Caption outside the card — never on the border
    text(
        slide,
        x + 20_000,
        y + frame_h + 20_000,
        w - 40_000,
        max(CAP - 20_000, 80_000),
        [(caption, 10, True, BRAND)],
    )


def grid(cols: int, rows: int, gap: int = GAP):
    """Return list of (x,y,w,h) cells filling the safe content area."""
    cell_w = (CONTENT_W - gap * (cols - 1)) // cols
    cell_h = (CONTENT_H - gap * (rows - 1)) // rows
    cells = []
    for r in range(rows):
        for c in range(cols):
            cells.append((
                MARGIN_X + c * (cell_w + gap),
                CONTENT_TOP + r * (cell_h + gap),
                cell_w,
                cell_h,
            ))
    return cells


# ─── Slides ───────────────────────────────────────────────────────────────────


def s01_team(slide):
    """Fill the Cup team box near the top of the white band — nothing under footer."""
    # Template white text shape sits at ~2.90M; keep that position, shorten height.
    target = None
    for sh in slide.shapes:
        if not sh.has_text_frame:
            continue
        # Prefer the Cup placeholder (was shrunk to 1×1 on prior builds) or any team text
        name = (sh.name or "").lower()
        body = sh.text_frame.text or ""
        if "google shape;54" in name or "Team" in body or "TEAM" in body or "Problem" in body:
            target = sh
            break
        if sh.top and 2_700_000 < sh.top < 3_300_000 and sh.width and sh.width > 1_000_000:
            target = sh
            break

    if target is None:
        # Fallback: add our own box high in the white band
        text(slide, 146_600, 2_920_000, 8_760_000, 1_700_000, [
            ("TEAM DETAILS  ·  AI BUILDER CUP 2026  ·  JAPAC  ·  SUSTAINABILITY", 11, True, BRAND),
            ("", 6, False, MUTED),
            ("Team: Agent Ram   ·   Leader: Ramasamy P   ·   Product: TerraSentinel AI", 14, True, INK),
            ("", 8, False, MUTED),
            ("Satellites leave 1,355 moving points. The engine ranks the few that matter.", 13, True, BRAND),
            ("Gemini writes the ticket — every number checked. Live on Cloud Run + BigQuery.", 13, True, BRAND),
            ("", 8, False, MUTED),
            ("Problem: InSAR portals give points, not who goes today. Chatbots invent mm.", 12, False, INK),
            ("Solution: 250 m sites · RPI · honest ETA bands · Gemini number guard.", 12, False, INK),
        ])
        return

    # Restore template geometry if a prior build collapsed the shape
    target.left = 146_600
    target.top = 2_850_000  # just under Cup hero art
    target.width = 8_760_000
    target.height = 1_450_000  # ends ~4.30M — well clear of footer at 5.09M

    tf = target.text_frame
    tf.clear()
    tf.word_wrap = True
    tf.auto_size = None
    try:
        tf.vertical_anchor = MSO_ANCHOR.TOP
    except Exception:
        pass
    rows = [
        ("TEAM DETAILS  ·  AI BUILDER CUP 2026  ·  JAPAC  ·  SUSTAINABILITY", 11, True, BRAND),
        ("", 6, False, MUTED),
        ("Team: Agent Ram   ·   Leader: Ramasamy P   ·   Product: TerraSentinel AI", 14, True, INK),
        ("", 8, False, MUTED),
        ("Satellites leave 1,355 moving points. The engine ranks the few that matter.", 13, True, BRAND),
        ("Gemini writes the ticket — every number checked. Live on Cloud Run + BigQuery.", 13, True, BRAND),
        ("", 8, False, MUTED),
        ("Problem: InSAR portals give points, not who goes today. Chatbots invent mm.", 12, False, INK),
        ("Solution: 250 m sites · RPI · honest ETA bands · Gemini number guard.", 12, False, INK),
    ]
    for i, (t, size, bold, color) in enumerate(rows):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.space_after = Pt(2)
        p.space_before = Pt(0)
        run = p.add_run()
        run.text = t
        run.font.size = Pt(size)
        run.font.bold = bold
        run.font.color.rgb = color
        run.font.name = "Calibri"


def s02_cover(slide):
    """Strong left column (big proofs) + hero map. No 5-step row."""
    for sh in slide.shapes:
        if sh.has_text_frame and sh.top and 800_000 < sh.top < 4_000_000:
            try:
                sh.text_frame.clear()
            except Exception:
                pass

    panel_y = 380_000
    panel_h = FOOTER_TOP - panel_y - 20_000
    card(slide, MARGIN_X, panel_y, CONTENT_W, panel_h, WHITE, LINE, BRAND)

    left_w = int(CONTENT_W * 0.46)
    right_x = MARGIN_X + left_w + 80_000
    right_w = CONTENT_W - left_w - 80_000 - 40_000
    pad = 70_000

    text(slide, MARGIN_X + pad, panel_y + 70_000, left_w - 2 * pad, 620_000, [
        ("TERRASENTINEL AI", 11, True, BRAND),
        ("Satellites see the ground move.", 18, True, INK),
        ("Gemini tells engineers where to go first.", 13, True, BRAND),
    ])

    # Three tall proof blocks — fill the left column, no empty strip
    proofs = [
        ("62,330 → 4", "Observations become act-today sites", BRAND, SOFT),
        ("RPI 86 · CRITICAL", "NH-58 · 35–64 day outlook if trend continues", BAD, BAD_BG),
        ("Gemini · verified", "6 tools · 7 numbers checked · 24h dispatch", BRAND, SOFT),
    ]
    stack_top = panel_y + 780_000
    stack_bot = panel_y + panel_h - 80_000
    gap_s = 50_000
    ph = (stack_bot - stack_top - 2 * gap_s) // 3
    for i, (big, small, accent, fill) in enumerate(proofs):
        y = stack_top + i * (ph + gap_s)
        card(slide, MARGIN_X + pad, y, left_w - 2 * pad, ph, fill, LINE, accent)
        text(slide, MARGIN_X + pad + 60_000, y + int(ph * 0.22), left_w - 2 * pad - 100_000, int(ph * 0.56), [
            (big, 20, True, accent),
            (small, 12, False, INK),
        ])

    hero = SHOTS / "c-hero-map.png"
    if hero.exists():
        pic(slide, hero, right_x, panel_y + 80_000, right_w, panel_h - 160_000)


def s03_idea(slide):
    set_title(slide, "Problem & decision", "Ground creeps for months. Nobody ranks which creep matters — crews go to the wrong place.")
    # Top two columns
    top_h = int(CONTENT_H * 0.72)
    lx, ly, lw = MARGIN_X, CONTENT_TOP, int(CONTENT_W * 0.42)
    rows = [
        (BAD_BG, BAD, "NH-58 mountain highway", "Sole valley access. One slip cuts towns, pilgrims, supply."),
        (WARN_BG, WARN, "Chennai metro tunnels", "Settlement under roads & buildings. Tight tolerances."),
        (PANEL, SLATE, "Dams & tailings", "Crest/toe motion · severe downstream consequence."),
        (SOFT, BRAND, "The one decision", "After this pass: which 250 m, why, and how soon?"),
    ]
    rh = (top_h - 3 * 40_000) // 4
    for i, (bg, accent, title, body) in enumerate(rows):
        y = ly + i * (rh + 40_000)
        card(slide, lx, y, lw, rh, bg, LINE, accent)
        text(slide, lx + 70_000, y + 35_000, lw - 100_000, rh - 50_000, [
            (title, 10, True, accent),
            (body, 9, False, INK),
        ])

    rx = lx + lw + GAP
    rw = CONTENT_W - lw - GAP
    card(slide, rx, ly, rw, int(top_h * 0.55), WHITE, LINE, BRAND)
    text(slide, rx + 70_000, ly + 35_000, rw - 100_000, 220_000, [("Today fails the decision", 11, True, INK)])
    bullets(slide, rx + 60_000, ly + 280_000, rw - 100_000, int(top_h * 0.55) - 300_000, [
        "Raw InSAR portal — thousands of points, no asset link, no who-goes-today",
        "Rainfall alarm — treats the trigger as the hazard; fires on stable ground",
        "Generic AI chatbot — invents mm and failure dates; nothing to audit",
        "Scheduled walk-over — calendar ignores which segment is accelerating now",
    ], size=9)

    by = ly + int(top_h * 0.55) + GAP
    bh = top_h - int(top_h * 0.55) - GAP
    half = (rw - GAP) // 2
    card(slide, rx, by, half, bh, OK_BG, LINE, OK)
    text(slide, rx + 50_000, by + 30_000, half - 80_000, 180_000, [("We do", 10, True, OK)])
    bullets(slide, rx + 40_000, by + 200_000, half - 70_000, bh - 220_000, [
        "Progressive creep on linear assets",
        "Rank · explain · track between passes",
        "Threshold window + assumptions stated",
    ], size=8)

    card(slide, rx + half + GAP, by, half, bh, BAD_BG, LINE, BAD)
    text(slide, rx + half + GAP + 50_000, by + 30_000, half - 80_000, 180_000, [("We refuse", 10, True, BAD)])
    bullets(slide, rx + half + GAP + 40_000, by + 200_000, half - 70_000, bh - 220_000, [
        "Failure / collapse dates",
        "Sudden events between 6–12 d passes",
        "Certified safety decisions",
    ], size=8)

    # Funnel proof strip
    fy = CONTENT_TOP + top_h + GAP
    fh = CONTENT_H - top_h - GAP
    card(slide, MARGIN_X, fy, CONTENT_W, fh, SOFT, LINE, BRAND)
    text(slide, MARGIN_X + 60_000, fy + 25_000, 2_200_000, fh - 40_000, [("One pass · demo data", 9, True, BRAND)])
    funnel = [("62,330", "observations"), ("1,355", "radar points"), ("87", "250 m sites"), ("7", "CRIT/ELEV"), ("4", "Act today")]
    fw = (CONTENT_W - 2_400_000) // 5
    for i, (n, lab) in enumerate(funnel):
        x = MARGIN_X + 2_300_000 + i * fw
        text(slide, x, fy + 40_000, fw - 20_000, fh - 60_000, [
            (n, 14, True, BRAND),
            (lab, 8, False, MUTED),
        ], align=PP_ALIGN.CENTER)


def s04_opportunities(slide):
    set_title(slide, "Why we win", "Not another InSAR viewer — a consequence-ranked decision layer with guarded GenAI.")
    cols = [
        ("Differentiation", BRAND, [
            "250 m chainage sites on corridor geometry — not a heat-map of every scatterer",
            "RPI = hazard × consequence × confidence (deterministic Python / BigQuery)",
            "Act list = today’s state; Alerts = what changed between passes",
            "Rain amplifies only (+50% cap); USGS quakes never move a score",
            "Gemini narrates tool results; the engine owns every number",
            "WEAK radar guard — bad data can never become CRITICAL",
        ]),
        ("How it solves it", WARN, [
            "Validate → locate on assets → measure speed / accel / progress",
            "Classify with data-quality gate; rank Act-today shortlist",
            "Outlook = [ETA_const, ETA_accel] band ≤ 365 d — never a date",
            "Work order: summary · hypothesis · urgency · field checklist",
            "Same maths locally or in BigQuery (TS_DATA_BACKEND flag)",
            "History is re-run from data — every past score is reproducible",
        ]),
        ("USP · live proof", BAD, [
            "Honest continuing-regime bands with assumptions spelled out",
            "Number guard rejects invented mm and “will collapse” language",
            "Live Cloud Run + BigQuery + Secret Manager + GCS state",
            "Demo funnel: 62,330 obs → 87 sites → 7 action → 4 Act today",
            "Gemini live: 6 tool calls · 7 numbers verified · 24h dispatch",
            "Judge can sign in now — credentials on the login page",
        ]),
    ]
    cells = grid(3, 1)
    for (title, accent, items), (x, y, w, h) in zip(cols, cells):
        card(slide, x, y, w, h, WHITE, LINE, accent)
        text(slide, x + 60_000, y + 50_000, w - 100_000, 260_000, [(title, 12, True, accent)])
        bullets(slide, x + 50_000, y + 320_000, w - 90_000, h - 360_000, items, size=9)


def s05_features(slide):
    set_title(slide, "Product surfaces", "Every screen ships a decision an engineer can act on today.")
    feats = [
        ("Command Center", "Map + KPIs + Act today — ranked by consequence, not raw mm"),
        ("Site drawer", "RPI, speed vs baseline, rain trigger, outlook band, pass trend"),
        ("Alerts", "Pass-to-pass diffs — what changed, not a duplicate Act list"),
        ("Trends · Portfolio", "16 passes recomputed from data; action sites 3→7 tracked"),
        ("Work Orders", "Template-first ticket; Gemini polish; number guard on every figure"),
        ("Data Hub", "Validate-then-import · Open-Meteo rain · provenance · BQ sync"),
        ("Access & audit", "admin/analyst/viewer · CSRF · sessions · full audit log"),
        ("Methodology", "Published formulae — every score auditable by a geotech"),
    ]
    cells = grid(4, 2, gap=55_000)
    for (title, body), (x, y, w, h) in zip(feats, cells):
        card(slide, x, y, w, h, SOFT if ((x // 100_000) + (y // 100_000)) % 2 == 0 else WHITE, LINE, BRAND)
        text(slide, x + 50_000, y + 45_000, w - 80_000, h - 70_000, [
            (title, 11, True, BRAND),
            ("", 2, False, MUTED),
            (body, 9, False, INK),
        ])


def s06_process(slide):
    set_title(slide, "Story & process flow", "One satellite pass — from space to a crew at the right 250 metres.")
    steps = [
        ("1 · Pass", "Every 6–12 days", "Sentinel-1 measures mm motion through cloud & night"),
        ("2 · Map", "Onto the corridor", "1,355 points matched to highway / metro / dam → 87×250 m sites"),
        ("3 · Rank", "What matters", "Fast + accelerating + critical + good data rises; rain alone never alarms"),
        ("4 · Gemini", "Write the ticket", "7 tools → reason → JSON → number guard → field checklist"),
        ("5 · Next", "Keep watching", "Crew acts; next pass shows calm-down or worse"),
    ]
    top_h = int(CONTENT_H * 0.48)
    sw = (CONTENT_W - 4 * GAP) // 5
    for i, (a, b, c) in enumerate(steps):
        x = MARGIN_X + i * (sw + GAP)
        card(slide, x, CONTENT_TOP, sw, top_h, SOFT if i % 2 == 0 else WHITE, LINE, BRAND)
        text(slide, x + 30_000, CONTENT_TOP + 50_000, sw - 60_000, top_h - 80_000, [
            (a, 10, True, BRAND),
            (b, 11, True, INK),
            ("", 3, False, MUTED),
            (c, 8, False, MUTED),
        ], align=PP_ALIGN.CENTER)

    # Funnel + who benefits
    fy = CONTENT_TOP + top_h + GAP
    fh = CONTENT_H - top_h - GAP
    left_w = int(CONTENT_W * 0.58)
    card(slide, MARGIN_X, fy, left_w, fh, PANEL, LINE, BRAND)
    text(slide, MARGIN_X + 70_000, fy + 40_000, left_w - 120_000, 200_000, [
        ("Demo funnel (labelled synthetic)", 10, True, BRAND),
    ])
    funnel = [("62,330", "obs"), ("1,355", "pts"), ("87", "sites"), ("7", "action"), ("4", "Act today")]
    fw = (left_w - 140_000) // 5
    for i, (n, lab) in enumerate(funnel):
        x = MARGIN_X + 70_000 + i * fw
        text(slide, x, fy + 280_000, fw - 20_000, fh - 320_000, [
            (n, 16, True, BRAND),
            (lab, 9, False, MUTED),
        ], align=PP_ALIGN.CENTER)

    rx = MARGIN_X + left_w + GAP
    rw = CONTENT_W - left_w - GAP
    card(slide, rx, fy, rw, fh, WHITE, LINE, BRAND)
    text(slide, rx + 60_000, fy + 40_000, rw - 100_000, 200_000, [("Who it serves", 10, True, BRAND)])
    bullets(slide, rx + 50_000, fy + 260_000, rw - 90_000, fh - 300_000, [
        "Public: find problems while small — keep roads open",
        "Engineers: short list + ticket (what / where / why)",
        "Leaders: spend crews where risk is rising",
    ], size=9)


def s07_ui(slide):
    set_title(slide, "Product UI (live)", "What judges open today — Command Center → site → Gemini ticket → Data Hub.")
    # Prefer landscape captures so cells fill without tall letterboxing
    shots = [
        (SHOTS / "c-command.png", "Command Center · Act list"),
        (SHOTS / "c-site.png" if (SHOTS / "c-site.png").exists() else SHOTS / "04-nh58-site.png", "Site · RPI & outlook"),
        (SHOTS / "c-workorder-ai.png", "Gemini work order"),
        (SHOTS / "c-datahub.png", "Data Hub · validate then import"),
    ]
    for i, (p, cap) in enumerate(shots):
        if not p.exists() or p.stat().st_size < 20_000:
            alt = [SHOTS / "01-command-center.png", SHOTS / "04-nh58-site.png", SHOTS / "c-workorder.png", SHOTS / "app-datahub.png"][i]
            shots[i] = (alt, cap)
    cells = grid(2, 2, gap=100_000)
    for (path, cap), (x, y, w, h) in zip(shots, cells):
        shot_cell(slide, path, x, y, w, h, cap)


def s08_architecture(slide):
    set_title(slide, "Architecture story", "Ingest → Store → Compute → Snapshot → Serve. One container. GenAI never owns the maths.")
    # Top: horizontal data-plane story
    flow = [
        ("Ingest", "Data Hub validates\nfiles & HTTPS links"),
        ("Store", "BigQuery or local\nGIS join · history"),
        ("Compute", "Detection engine\nRPI · tier · band"),
        ("Snapshot", "Pass replay\nalerts · trends"),
        ("Serve", "UI + Gemini ticket\naudit trail"),
    ]
    top_h = int(CONTENT_H * 0.36)
    nw = (CONTENT_W - 4 * GAP) // 5
    for i, (t, b) in enumerate(flow):
        x = MARGIN_X + i * (nw + GAP)
        fill = BRAND if i == 4 else (SOFT if i % 2 == 0 else WHITE)
        card(slide, x, CONTENT_TOP, nw, top_h, fill, LINE, BRAND)
        text(slide, x + 30_000, CONTENT_TOP + 50_000, nw - 60_000, top_h - 80_000, [
            (t, 11, True, WHITE if i == 4 else BRAND),
            (b, 8, False, WHITE if i == 4 else MUTED),
        ], align=PP_ALIGN.CENTER)

    # Bottom: layers (unified brand accents — not rainbow)
    layers = [
        ("EDGE", "Cloud Run · HTTPS · CSP/HSTS · rate limits · sessions · GCS state"),
        ("UI + API", "React/MapLibre · FastAPI · RBAC · CSRF · SSRF-safe fetch · audit"),
        ("ENGINE", "Deterministic RPI / tiers / ETA bands / alerts — GenAI never computes these"),
        ("GENAI", "Gemini tools → number guard → template fallback (Vertex or AI Studio)"),
        ("DATA", "BigQuery partitions/GEOGRAPHY XOR local · USGS context only · provenance"),
    ]
    bot_y = CONTENT_TOP + top_h + GAP
    bot_h = CONTENT_H - top_h - GAP
    rh = (bot_h - 4 * 30_000) // 5
    for i, (name, body) in enumerate(layers):
        y = bot_y + i * (rh + 30_000)
        card(slide, MARGIN_X, y, CONTENT_W, rh, WHITE, LINE, BRAND)
        text(slide, MARGIN_X + 80_000, y + 30_000, 1_500_000, rh - 40_000, [(name, 10, True, BRAND)])
        text(slide, MARGIN_X + 1_650_000, y + 30_000, CONTENT_W - 1_800_000, rh - 40_000, [(body, 9, False, INK)])


def s09_tech(slide):
    set_title(slide, "GenAI on Google Cloud", "Without GenAI: a number. With Gemini + guard: a ticket an engineer can trust.")
    card(slide, MARGIN_X, CONTENT_TOP, CONTENT_W, 500_000, SOFT, LINE, BRAND)
    text(slide, MARGIN_X + 70_000, CONTENT_TOP + 50_000, CONTENT_W - 140_000, 400_000, [
        (
            "LIVE PROOF: Gemini drafted a Metro Line 4 ticket with 6 tool calls and 7 numbers verified. "
            "Recommendation: “Dispatch an inspection crew within 24 hours…” — every millimetre from tools, not free text.",
            10,
            True,
            INK,
        ),
    ])

    mid_y = CONTENT_TOP + 500_000 + GAP
    mid_h = int((CONTENT_H - 500_000 - GAP) * 0.38)
    nodes = [
        ("Ingest", "Cloud Run\nData Hub"),
        ("Store", "BigQuery\nGIS + history"),
        ("Compute", "Engine\nRPI · tier · band"),
        ("Explain", "Gemini\n+ number guard"),
        ("Act", "Map · ticket\n· audit"),
    ]
    nw = (CONTENT_W - 4 * GAP) // 5
    for i, (t, b) in enumerate(nodes):
        x = MARGIN_X + i * (nw + GAP)
        fill = BRAND if i == 3 else WHITE
        card(slide, x, mid_y, nw, mid_h, fill, LINE, BRAND)
        text(slide, x + 25_000, mid_y + 35_000, nw - 50_000, mid_h - 50_000, [
            (t, 11, True, WHITE if i == 3 else BRAND),
            (b, 8, False, WHITE if i == 3 else MUTED),
        ], align=PP_ALIGN.CENTER)

    bot_y = mid_y + mid_h + GAP
    bot_h = FOOTER_TOP - bot_y - 20_000
    third = (CONTENT_W - 2 * GAP) // 3
    blocks = [
        ("Gemini loop", [
            "7 tools: metrics, history, outlook, rain, seismic, exposure, quality",
            "Round 0 MUST call tools → investigate → write JSON",
            "Temp 0.1 · model fallback on 429/5xx",
        ]),
        ("Number guard", [
            "Rejects any mm/days/% not in a tool result",
            "Rejects “will collapse”, “failure date”, “no risk”",
            "On failure: labelled template still ships",
        ]),
        ("GCP stack", [
            "Cloud Run — SPA + API + engine + agent",
            "BigQuery — partitions, ST_DWITHIN, bytes cap",
            "Vertex/AI Studio · Secrets · GCS · ADC",
        ]),
    ]
    for i, (title, items) in enumerate(blocks):
        x = MARGIN_X + i * (third + GAP)
        card(slide, x, bot_y, third, bot_h, WHITE, LINE, BRAND)
        text(slide, x + 50_000, bot_y + 35_000, third - 80_000, 180_000, [(title, 10, True, BRAND)])
        bullets(slide, x + 40_000, bot_y + 220_000, third - 70_000, bot_h - 250_000, items, size=8)


def s10_cost(slide):
    set_title(slide, "Estimated cost (optional)", "GenAI only on tickets; ranking stays deterministic CPU.")
    rows = [
        ("Cloud Run", "1–2 vCPU / 2 GiB · min=1 while judging", "low tens USD/mo warm"),
        ("BigQuery", "~62k rows · TTL cache · max bytes billed", "pennies–low USD demos"),
        ("Gemini Flash", "Work-order path only · template fallback", "per-ticket, optional"),
        ("Secrets + GCS", "Admin/Gemini secrets · state volume", "pennies"),
        ("Scale path", "Materialize assignment · raise instances", "linear with corridors"),
    ]
    rh = (CONTENT_H - 4 * GAP) // 5
    for i, (a, b, c) in enumerate(rows):
        y = CONTENT_TOP + i * (rh + GAP)
        card(slide, MARGIN_X, y, CONTENT_W, rh, SOFT if i % 2 == 0 else WHITE, LINE, BRAND)
        text(slide, MARGIN_X + 80_000, y + 50_000, 2_000_000, rh - 80_000, [(a, 11, True, BRAND)])
        text(slide, MARGIN_X + 2_200_000, y + 50_000, 4_200_000, rh - 80_000, [(b, 10, False, INK)])
        text(slide, MARGIN_X + 6_500_000, y + 50_000, CONTENT_W - 6_700_000, rh - 80_000, [(c, 9, True, MUTED)])


def s11_snapshots(slide):
    set_title(slide, "Prototype snapshots", "Winning proof on screen — Chamoli Act list, NH-58 CRITICAL, verified Gemini ticket.")
    shots = [
        (SHOTS / "c-hero-map.png", "Chamoli · 69 sites · 4 act today"),
        (SHOTS / "c-map-chamoli.png", "Ranked map — not every scatterer"),
        (SHOTS / "c-site.png" if (SHOTS / "c-site.png").exists() else SHOTS / "c-site-now.png", "NH-58 · RPI 86 · 35-64 day band"),
        (SHOTS / "c-workorder.png" if (SHOTS / "c-workorder.png").exists() else SHOTS / "c-workorder-ai.png", "Gemini · numbers verified"),
    ]
    cells = grid(2, 2, gap=100_000)
    for (path, cap), (x, y, w, h) in zip(shots, cells):
        if path.exists():
            shot_cell(slide, path, x, y, w, h, cap)


def s12_performance(slide):
    set_title(slide, "Worked proof", "NH-58 KM 3.25–3.50 — same numbers in UI, tools, and Gemini work order.")
    cells = grid(2, 1, gap=GAP)
    lx, ly, lw, lh = cells[0]
    card(slide, lx, ly, lw, lh, WHITE, LINE, BAD)
    text(slide, lx + 60_000, ly + 40_000, lw - 100_000, 260_000, [("CRITICAL · RPI 86 · band 35–64 d", 11, True, BAD)])
    bullets(slide, lx + 50_000, ly + 320_000, lw - 90_000, lh - 360_000, [
        "Inputs: 6.2 vs 2.8 mm/mo · 2.2× · 29.7/40 mm · rain 213 mm · crit 0.95 · conf 0.97",
        "kin = 100×(.4·0.62 + .3·0.40 + .3·0.74) = 59.4",
        "hazard = 59.4×(1+0.5×1.0) = 89.1 (rain capped)",
        "RPI = 89.1×0.975×0.985 ≈ 85.7 → CRITICAL (threshold approach)",
        "Outlook: 51 d const · 44 d accel → widened 35–64 d if trend continues",
        "History: this site 61→86 · portfolio action sites 3→7 over 16 passes",
        "What-if: minor road→57 ELEV · weak radar→≤15 WEAK · rain on stable→≈1",
        "Integrity: GenAI never computes RPI / tier / ETA — tools only",
    ], size=8)

    rx, ry, rw, rh = cells[1]
    img_band = int(rh * 0.55)
    shot_cell(slide, SHOTS / "c-site-trend.png", rx, ry, rw, img_band, "Site trend · displacement + rain")
    lat_y = ry + img_band + 80_000
    lat_h = rh - img_band - 80_000
    card(slide, rx, lat_y, rw, lat_h, SOFT, LINE, BRAND)
    text(slide, rx + 50_000, lat_y + 40_000, rw - 80_000, lat_h - 60_000, [
        ("Live Cloud Run + BigQuery (warm)", 10, True, BRAND),
        ("summary ~0.4s · sites ~0.3s · alerts ~2s", 9, False, INK),
        ("Hot-path prefetch before history warm", 9, False, INK),
        ("Gemini: 6 tool calls · 7 numbers verified", 9, True, BRAND),
    ])


def s13_future(slide):
    set_title(slide, "Ask · buyer · roadmap", "Sustainability impact today. Scale tomorrow. Honesty rules never move.")
    # Top ask bar
    card(slide, MARGIN_X, CONTENT_TOP, CONTENT_W, 520_000, BRAND, BRAND, None)
    text(slide, MARGIN_X + 80_000, CONTENT_TOP + 60_000, CONTENT_W - 160_000, 400_000, [
        ("THE ASK: Review the live demo, the 3-minute video, and the repository.", 12, True, WHITE),
        ("Buyer: asset-integrity / geotech teams. They buy engineer attention — 1,355 points become 7 sites.", 10, False, WHITE),
    ])

    bot_y = CONTENT_TOP + 520_000 + GAP
    bot_h = CONTENT_H - 520_000 - GAP
    half = (CONTENT_W - GAP) // 2
    card(slide, MARGIN_X, bot_y, half, bot_h, WHITE, LINE, BRAND)
    text(slide, MARGIN_X + 60_000, bot_y + 40_000, half - 100_000, 220_000, [("Roadmap", 11, True, BRAND)])
    bullets(slide, MARGIN_X + 50_000, bot_y + 280_000, half - 90_000, bot_h - 310_000, [
        "Production InSAR providers on the same Data Hub schema",
        "Materialize spatial assignment for national corridors",
        "HA when session store leaves single-process files",
        "OIDC / IAP · field offline packet · deeper amplifiers only",
    ], size=9)

    card(slide, MARGIN_X + half + GAP, bot_y, half, bot_h, SOFT, LINE, BAD)
    text(slide, MARGIN_X + half + GAP + 60_000, bot_y + 40_000, half - 100_000, 220_000, [("Non-negotiable honesty", 11, True, BAD)])
    bullets(slide, MARGIN_X + half + GAP + 50_000, bot_y + 280_000, half - 90_000, bot_h - 310_000, [
        "Outlook bands ≠ collapse / failure dates — always",
        "Gemini narrates tool numbers only — always",
        "Synthetic demo data labelled in the UI — always",
        "Secrets in Secret Manager / .env — never in git",
    ], size=9)


def s14_links(slide):
    set_title(slide, "Judge path · links", "Sign in → Command Center → NH-58 site → Work Order → Data Hub (5 minutes).")
    links = [
        (BRAND, "1 · GitHub", "https://github.com/ramasamyp-aiengineer/terra-sentinel-ai"),
        (WARN, "2 · Demo video (3 min)", "docs/pitch/TerraSentinel-AI-Demo-3min.mp4 — upload to Drive/YouTube for the portal"),
        (BLUE, "3 · Live product", "https://terrasentinel-598899050820.asia-southeast1.run.app"),
    ]
    rh = (CONTENT_H - 2 * GAP - 520_000) // 3
    for i, (accent, title, url) in enumerate(links):
        y = CONTENT_TOP + i * (rh + GAP)
        card(slide, MARGIN_X, y, CONTENT_W, rh, WHITE, LINE, accent)
        text(slide, MARGIN_X + 90_000, y + 50_000, CONTENT_W - 160_000, rh - 80_000, [
            (title, 12, True, accent),
            (url, 11, False, INK),
        ])
    card(slide, MARGIN_X, CONTENT_TOP + 3 * (rh + GAP), CONTENT_W, 450_000, SOFT, LINE, BRAND)
    text(slide, MARGIN_X + 80_000, CONTENT_TOP + 3 * (rh + GAP) + 50_000, CONTENT_W - 160_000, 360_000, [
        ("Credentials are shown on the sign-in page (judge demo hint).", 11, True, BRAND),
        ("Look for: Act list · outlook band (not a date) · “numbers verified” on the work order.", 10, False, INK),
    ])


def s15_engine(slide):
    set_title(slide, "Risk engine maths", "Measure → Score → Project. Deterministic, tested, explainable.")
    blocks = [
        (BRAND, "1 · Measure", [
            "Recent speed: slope last 60 d",
            "Baseline: 270 to 90 d ago",
            "Accel = |recent|/max(|base|,0.5)",
            "Persistence · seasonal recovery",
            "Site = median in 250 m bin",
            "conf mixes coh·epochs·pts·SNR",
            "Weak data can never be CRITICAL",
        ]),
        (WARN, "2 · Score", [
            "kin=100*(.4s+.3a+.3p)",
            "hazard=kin*(1+0.5*rain/200)",
            "RPI=hazard*(0.5+0.5*crit)",
            "      *(0.5+0.5*conf)",
            "Slow/far x0.2 · seasonal x0.35",
            "WEAK cap 15 · quakes never scored",
            "CRITICAL / ELEVATED / WATCH",
        ]),
        (BAD, "3 · Project", [
            "ETA_const = remaining / speed",
            "ETA_accel = quadratic root",
            "band=[min,max] <= 365 d",
            "Highway 40 mm / 180 d demo",
            "Metro 25 mm · Dam 30 mm",
            "ALWAYS a band",
            "NEVER a failure date",
        ]),
    ]
    cells = grid(3, 1)
    for (accent, title, items), (x, y, w, h) in zip(blocks, cells):
        card(slide, x, y, w, h, WHITE, LINE, accent)
        text(slide, x + 60_000, y + 50_000, w - 100_000, 260_000, [(title, 12, True, accent)])
        bullets(slide, x + 50_000, y + 330_000, w - 90_000, h - 380_000, items, size=10)


def s16_thanks(slide):
    """Leave the official Builder Cup end slide untouched."""
    return


def export_pdf(pptx: Path, pdf: Path) -> bool:
    try:
        import win32com.client  # type: ignore
    except ImportError:
        print("pywin32 missing", file=sys.stderr)
        return False
    app = win32com.client.Dispatch("PowerPoint.Application")
    app.Visible = 1
    try:
        pres = app.Presentations.Open(str(pptx.resolve()), WithWindow=False)
        if pdf.exists():
            try:
                pdf.unlink()
            except OSError:
                pass
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
        s01_team, s02_cover, s03_idea, s04_opportunities, s05_features, s06_process,
        s07_ui, s08_architecture, s09_tech, s10_cost, s11_snapshots, s12_performance,
        s13_future, s14_links, s15_engine, s16_thanks,
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
