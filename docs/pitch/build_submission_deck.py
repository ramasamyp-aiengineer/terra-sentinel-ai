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
    for sh in slide.shapes:
        if sh.has_text_frame and ("Team" in sh.text_frame.text or "Problem" in sh.text_frame.text or "TEAM" in sh.text_frame.text):
            tf = sh.text_frame
            tf.clear()
            rows = [
                ("TEAM DETAILS  ·  AI BUILDER CUP 2026  ·  JAPAC  ·  SUSTAINABILITY", 10, True, BRAND),
                ("", 4, False, MUTED),
                ("Team name:  Agent Ram", 15, True, INK),
                ("Team leader:  Ramasamy P", 13, False, INK),
                ("Product:  TerraSentinel AI — ground-motion early warning", 12, True, BRAND),
                ("", 4, False, MUTED),
                (
                    "Problem: After each Sentinel-1 pass, operators face thousands of InSAR points with no "
                    "consequence ranking. TerraSentinel cuts motion into 250 m sites, ranks who inspects "
                    "today (RPI), reports honest time-to-threshold bands (never failure dates), and uses "
                    "Gemini to draft a number-verified inspection ticket.",
                    11,
                    False,
                    INK,
                ),
            ]
            for i, (t, size, bold, color) in enumerate(rows):
                p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
                p.space_after = Pt(2)
                run = p.add_run()
                run.text = t
                run.font.size = Pt(size)
                run.font.bold = bold
                run.font.color.rgb = color
                run.font.name = "Calibri"
            return


def s02_cover(slide):
    """Slide 2 template is dark — cover it with a light story panel (unified teal palette)."""
    # Hide / blank any leftover instruction text (low-contrast grey on black)
    for sh in slide.shapes:
        if sh.has_text_frame and sh.top and 800_000 < sh.top < 4_000_000:
            try:
                sh.text_frame.clear()
            except Exception:
                pass

    # Full light story panel over the dark art (keeps Google chrome if any)
    panel_y = 420_000
    panel_h = FOOTER_TOP - panel_y - 30_000
    card(slide, MARGIN_X, panel_y, CONTENT_W, panel_h, WHITE, LINE, BRAND)

    text(slide, MARGIN_X + 100_000, panel_y + 80_000, CONTENT_W - 200_000, 700_000, [
        ("TERRASENTINEL AI  ·  STORY", 9, True, BRAND),
        ("Satellites see the ground move. Gemini tells engineers where to go first.", 16, True, INK),
        ("", 4, False, MUTED),
        (
            "Each Sentinel-1 pass → ranked Act list → honest threshold band (never a failure date) → number-verified ticket.",
            11,
            False,
            MUTED,
        ),
    ])

    # Story flow chips (one palette — brand teal only)
    flow = [
        ("1", "Pass", "Sentinel-1 every 6–12 d"),
        ("2", "Map", "Points → 250 m sites"),
        ("3", "Rank", "RPI × consequence"),
        ("4", "Explain", "Gemini + number guard"),
        ("5", "Act", "Crew · next pass"),
    ]
    fy = panel_y + 1_050_000
    fh = 980_000
    fw = (CONTENT_W - 200_000 - 4 * GAP) // 5
    for i, (n, title, body) in enumerate(flow):
        x = MARGIN_X + 100_000 + i * (fw + GAP)
        card(slide, x, fy, fw, fh, SOFT, LINE, BRAND)
        text(slide, x + 40_000, fy + 60_000, fw - 80_000, fh - 100_000, [
            (n, 18, True, BRAND),
            (title, 12, True, INK),
            (body, 9, False, MUTED),
        ], align=PP_ALIGN.CENTER)

    # Value strip — same teal family, no rainbow accents
    stats = [
        ("87 → 7", "sites to Act list"),
        ("RPI 86", "NH-58 CRITICAL band"),
        ("35–64 d", "outlook if trend holds"),
        ("GCP", "Run · BigQuery · Gemini"),
    ]
    sy = fy + fh + 80_000
    sh = panel_y + panel_h - sy - 80_000
    sw = (CONTENT_W - 200_000 - 3 * GAP) // 4
    for i, (big, small) in enumerate(stats):
        x = MARGIN_X + 100_000 + i * (sw + GAP)
        card(slide, x, sy, sw, sh, PANEL, LINE, BRAND)
        text(slide, x + 50_000, sy + 50_000, sw - 80_000, sh - 80_000, [
            (big, 15, True, BRAND),
            (small, 9, False, MUTED),
        ])


def s03_idea(slide):
    set_title(slide, "Brief about the idea", "Ground creeps for months. Nobody ranks which creep matters.")
    cells = grid(2, 1, gap=GAP)
    # Left column: 4 stacked cards
    lx, ly, lw, lh = cells[0]
    rows = [
        (BAD_BG, BAD, "Mountain highways · NH-58", "Sole valley access. One slip cuts towns & supply."),
        (WARN_BG, WARN, "Metro tunnels · Chennai", "Settlement under roads & buildings. Tight tolerance."),
        (PANEL, SLATE, "Dams & tailings", "Crest / toe motion with severe downstream consequence."),
        (SOFT, BRAND, "The decision we own", "Which 250 m needs an engineer, why, and how soon?"),
    ]
    rh = (lh - 3 * 50_000) // 4
    for i, (bg, accent, title, body) in enumerate(rows):
        y = ly + i * (rh + 50_000)
        card(slide, lx, y, lw, rh, bg, LINE, accent)
        text(slide, lx + 80_000, y + 50_000, lw - 120_000, rh - 80_000, [
            (title, 11, True, accent),
            (body, 9, False, INK),
        ])

    # Right: fail options + do/refuse
    rx, ry, rw, rh = cells[1]
    top_h = int(rh * 0.55)
    card(slide, rx, ry, rw, top_h, WHITE, LINE, BRAND)
    text(slide, rx + 80_000, ry + 40_000, rw - 120_000, 280_000, [("Today's options fail the decision", 11, True, INK)])
    bullets(slide, rx + 80_000, ry + 320_000, rw - 120_000, top_h - 360_000, [
        "Raw InSAR portal — no asset link, no who-goes-today",
        "Rainfall alarm — trigger treated as hazard",
        "Generic AI — invents mm and failure dates",
        "Walk-over calendar — ignores acceleration now",
    ], size=9)

    bot_y = ry + top_h + GAP
    bot_h = rh - top_h - GAP
    half = (rw - GAP) // 2
    card(slide, rx, bot_y, half, bot_h, OK_BG, LINE, OK)
    text(slide, rx + 70_000, bot_y + 40_000, half - 100_000, 220_000, [("We do", 11, True, OK)])
    bullets(slide, rx + 70_000, bot_y + 260_000, half - 100_000, bot_h - 300_000, [
        "Creep on linear assets",
        "Rank · explain · track",
        "Threshold window + assumptions",
    ], size=9)

    card(slide, rx + half + GAP, bot_y, half, bot_h, BAD_BG, LINE, BAD)
    text(slide, rx + half + GAP + 70_000, bot_y + 40_000, half - 100_000, 220_000, [("We refuse", 11, True, BAD)])
    bullets(slide, rx + half + GAP + 70_000, bot_y + 260_000, half - 100_000, bot_h - 300_000, [
        "Failure / collapse dates",
        "Sudden inter-pass events",
        "Certified safety claim",
    ], size=9)


def s04_opportunities(slide):
    set_title(slide, "Opportunities · USP", "Not an InSAR viewer — a decision layer with honest outlooks and guarded GenAI.")
    cols = [
        ("How different?", BRAND, [
            "250 m sites on corridor geometry",
            "RPI = hazard x consequence x confidence",
            "Alerts = pass diffs; Act list = today",
            "Rain amplifies only (+50% cap)",
            "USGS quakes: context, never scored",
            "Gemini narrates; engine decides",
        ]),
        ("How it solves it", WARN, [
            "Validate → locate → measure",
            "WEAK guard: bad radar != CRITICAL",
            "Rank Act-today shortlist",
            "Outlook = ETA band, never a date",
            "Ticket: summary · cause · checklist",
            "Same maths: local XOR BigQuery",
        ]),
        ("USP / demo value", BAD, [
            "Honest continuing-regime bands",
            "Number guard rejects invented mm",
            "Production GCP posture (Run + BQ)",
            "62,330 obs → 87 sites → 7 action",
            "4 Act today in Chamoli",
            "Judge can sign in and act live",
        ]),
    ]
    cells = grid(3, 1)
    for (title, accent, items), (x, y, w, h) in zip(cols, cells):
        card(slide, x, y, w, h, WHITE, LINE, accent)
        text(slide, x + 70_000, y + 60_000, w - 110_000, 280_000, [(title, 12, True, accent)])
        bullets(slide, x + 60_000, y + 360_000, w - 100_000, h - 420_000, items, size=10)


def s05_features(slide):
    set_title(slide, "Features", "Every surface ships a decision — not a dashboard toy.")
    feats = [
        ("Command Center", "Map + KPIs + Act today, ranked by consequence"),
        ("Site drawer", "RPI, speed, rain, outlook band, pass trend"),
        ("Alerts", "What changed between passes"),
        ("Brief · Trends · Portfolio", "Planning views; history recomputed from data"),
        ("Work Orders + Gemini", "Template-first; 7 tools; number guard"),
        ("Data Hub", "Validate-then-import; rain fetch; provenance; BQ sync"),
        ("Access & audit", "RBAC · sessions · CSRF · audit log"),
        ("Methodology", "Published formulae — every score auditable"),
    ]
    cells = grid(4, 2, gap=60_000)
    for (title, body), (x, y, w, h) in zip(feats, cells):
        card(slide, x, y, w, h, SOFT if (x // 1000) % 2 == 0 else WHITE, LINE, BRAND)
        text(slide, x + 60_000, y + 50_000, w - 100_000, h - 80_000, [
            (title, 11, True, BRAND),
            ("", 3, False, MUTED),
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
    set_title(slide, "Product UI (live)", "Running product screens — aspect-correct, not stretched wireframes.")
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
    set_title(slide, "Architecture story", "Request flow on Google Cloud — one container, two storage backends, same maths.")
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
    set_title(slide, "Technologies & GenAI flow", "Google Cloud end-to-end. Gemini turns a verified score into an action.")
    # Story sentence
    card(slide, MARGIN_X, CONTENT_TOP, CONTENT_W, 420_000, SOFT, LINE, BRAND)
    text(slide, MARGIN_X + 80_000, CONTENT_TOP + 60_000, CONTENT_W - 160_000, 320_000, [
        (
            "Without GenAI an engineer gets “RPI 86 · CRITICAL”. With Gemini + our guard they get a ticket: "
            "what is happening, likely cause (hypothesis), what to do by when, and a site checklist — every number from tools.",
            10,
            False,
            INK,
        ),
    ])

    mid_y = CONTENT_TOP + 420_000 + GAP
    mid_h = int((CONTENT_H - 420_000 - GAP) * 0.42)
    nodes = [
        ("Ingest", "Cloud Run\nData Hub"),
        ("Store", "BigQuery\nGIS + history"),
        ("Compute", "Engine\nscores sites"),
        ("Explain", "Gemini\n+ number guard"),
        ("Act", "Map · ticket\n· audit"),
    ]
    nw = (CONTENT_W - 4 * GAP) // 5
    for i, (t, b) in enumerate(nodes):
        x = MARGIN_X + i * (nw + GAP)
        fill = BRAND if i == 3 else WHITE
        card(slide, x, mid_y, nw, mid_h, fill, LINE, BRAND)
        text(slide, x + 25_000, mid_y + 40_000, nw - 50_000, mid_h - 60_000, [
            (t, 11, True, WHITE if i == 3 else BRAND),
            (b, 8, False, WHITE if i == 3 else MUTED),
        ], align=PP_ALIGN.CENTER)

    bot_y = mid_y + mid_h + GAP
    bot_h = FOOTER_TOP - bot_y - 20_000
    half = (CONTENT_W - GAP) // 2
    card(slide, MARGIN_X, bot_y, half, bot_h, WHITE, LINE, BRAND)
    text(slide, MARGIN_X + 60_000, bot_y + 40_000, half - 100_000, 200_000, [("Gemini loop", 11, True, BRAND)])
    bullets(slide, MARGIN_X + 50_000, bot_y + 240_000, half - 90_000, bot_h - 270_000, [
        "7 read-only tools (metrics → quality)",
        "Round 0 must call tools → investigate → JSON",
        "Guard rejects invented mm / collapse language",
        "Fallback models; template always ships",
    ], size=9)

    card(slide, MARGIN_X + half + GAP, bot_y, half, bot_h, WHITE, LINE, BRAND)
    text(slide, MARGIN_X + half + GAP + 60_000, bot_y + 40_000, half - 100_000, 200_000, [("GCP services", 11, True, BRAND)])
    bullets(slide, MARGIN_X + half + GAP + 50_000, bot_y + 240_000, half - 90_000, bot_h - 270_000, [
        "Cloud Run — SPA + API + engine + agent",
        "BigQuery — partitions, spatial join, bytes cap",
        "Vertex AI / AI Studio — Gemini",
        "Secret Manager · GCS · ADC (no key files)",
    ], size=9)


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
    set_title(slide, "Prototype snapshots", "Demo value on screen — Chamoli, NH-58 CRITICAL, guarded ticket.")
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
    set_title(slide, "Performance / benchmarking", "NH-58 KM 3.25-3.50 — same numbers in UI, tools, and work order.")
    cells = grid(2, 1, gap=GAP)
    lx, ly, lw, lh = cells[0]
    card(slide, lx, ly, lw, lh, WHITE, LINE, BAD)
    text(slide, lx + 70_000, ly + 50_000, lw - 110_000, 280_000, [("Worked example · CRITICAL · RPI 86", 11, True, BAD)])
    bullets(slide, lx + 70_000, ly + 340_000, lw - 110_000, lh - 400_000, [
        "Inputs: 6.2 vs 2.8 mm/mo · 2.2x · 29.7/40 mm · rain 213 mm",
        "kin = 100*(.4*0.62+.3*0.40+.3*0.74) = 59.4",
        "hazard = 59.4*(1+0.5*1.0) = 89.1 (rain capped)",
        "RPI = 89.1*0.975*0.985 ~ 85.7 → CRITICAL",
        "Outlook 35-64 days if trend continues — NOT a failure date",
        "History: site 61→86 · action sites 3→7 over 16 passes",
        "What-if: minor road 57 ELEV · weak radar ≤15 · rain-only ~1",
    ], size=9)

    rx, ry, rw, rh = cells[1]
    # Reserve clear bands so caption never meets the latency card
    img_band = int(rh * 0.62)
    gap2 = 100_000
    lat_y = ry + img_band + gap2
    lat_h = rh - img_band - gap2
    shot_cell(slide, SHOTS / "c-site-trend.png", rx, ry, rw, img_band, "Site trend · displacement + rain")
    card(slide, rx, lat_y, rw, lat_h, SOFT, LINE, BRAND)
    text(slide, rx + 60_000, lat_y + 50_000, rw - 100_000, lat_h - 80_000, [
        ("Live Cloud Run + BigQuery (warm)", 10, True, BRAND),
        ("summary ~0.4s · sites ~0.3s · alerts ~2s", 9, False, INK),
        ("Hot-path prefetch before history warm", 9, False, INK),
        ("GenAI never computes RPI / tier / ETA", 9, True, INK),
    ])


def s13_future(slide):
    set_title(slide, "Future development", "Scale the data plane — honesty rules stay fixed.")
    cells = grid(2, 1)
    left, right = [
        (BRAND, "Roadmap", [
            "Production InSAR on the same Data Hub schema",
            "Materialize point-assignment for national scale",
            "HA once sessions leave single-process files",
            "Field checklist / offline crew packet",
            "OIDC / IAP for enterprise buyers",
            "Deeper rain/geology as amplifiers only",
        ]),
        (WARN, "Buyer · ask · honesty", [
            "Buyer: asset-integrity / geotech teams",
            "What they buy: attention — 1,355 pts → 7 sites",
            "Ask: live demo + 3-min video + repo",
            "Outlook bands are never collapse dates",
            "Gemini narrates tools only",
            "Synthetic demo data labelled in UI",
        ]),
    ]
    for (accent, title, items), (x, y, w, h) in zip([left, right], cells):
        card(slide, x, y, w, h, SOFT if accent == WARN else WHITE, LINE, accent)
        text(slide, x + 70_000, y + 50_000, w - 110_000, 280_000, [(title, 12, True, accent)])
        bullets(slide, x + 60_000, y + 350_000, w - 100_000, h - 400_000, items, size=10)


def s14_links(slide):
    set_title(slide, "Submission links", "GitHub · 3-minute demo · live product.")
    links = [
        (BRAND, "GitHub public repository", "https://github.com/ramasamyp-aiengineer/terra-sentinel-ai"),
        (WARN, "Demo video (3 minutes)", "docs/pitch/TerraSentinel-AI-Demo-3min.mp4  (upload Drive/YouTube for portal)"),
        (BLUE, "Final product (live)", "https://terrasentinel-598899050820.asia-southeast1.run.app"),
    ]
    rh = (CONTENT_H - 2 * GAP - 280_000) // 3
    for i, (accent, title, url) in enumerate(links):
        y = CONTENT_TOP + i * (rh + GAP)
        card(slide, MARGIN_X, y, CONTENT_W, rh, WHITE, LINE, accent)
        text(slide, MARGIN_X + 100_000, y + 60_000, CONTENT_W - 180_000, rh - 100_000, [
            (title, 13, True, accent),
            (url, 11, False, INK),
        ])
    text(slide, MARGIN_X, FOOTER_TOP - 260_000, CONTENT_W, 220_000, [
        ("Sign-in credentials shown on the login page · Judge walk: docs/JUDGE.md", 10, False, MUTED),
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
    # Full safe-zone panel (template end art may sit behind)
    card(slide, MARGIN_X, CONTENT_TOP, CONTENT_W, CONTENT_H, WHITE, LINE, BRAND)
    logo = SHOTS / "logo-mark.jpg"
    if logo.exists():
        pic(slide, logo, MARGIN_X + 100_000, CONTENT_TOP + 120_000, 480_000, 480_000)
    text(slide, MARGIN_X + 700_000, CONTENT_TOP + 140_000, CONTENT_W - 900_000, 500_000, [
        ("TerraSentinel AI", 20, True, BRAND),
        ("Thank you — Team Agent Ram", 14, True, INK),
    ])
    text(slide, MARGIN_X + 120_000, CONTENT_TOP + 750_000, CONTENT_W - 240_000, 2_400_000, [
        ("Which 250 metres should an engineer inspect today?", 13, True, INK),
        ("The engine ranks them. Gemini writes the ticket. Every number is checked.", 11, False, MUTED),
        ("", 8, False, MUTED),
        ("Ramasamy P  ·  ramp21052000@gmail.com  ·  +91 90250 32130", 11, False, BRAND),
        ("Live demo + GitHub + 3-min video", 10, False, MUTED),
        ("Google Cloud AI Builder Cup 2026 · Sustainability", 10, False, MUTED),
        ("", 6, False, MUTED),
        ("Gemini · Vertex AI    ·    BigQuery    ·    Cloud Run    ·    Sentinel-1", 11, True, INK),
    ])


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
