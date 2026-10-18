"""Fill the official AI Builder Cup submission PPTX template with TerraSentinel content.

Usage:
  python docs/pitch/build_submission_deck.py

Writes:
  docs/pitch/TerraSentinel-AI-Builder-Cup-Submission.pptx
  docs/pitch/TerraSentinel-AI-Builder-Cup-Submission.pdf  (via PowerPoint COM if available)
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN
from pptx.util import Emu, Inches, Pt

ROOT = Path(__file__).resolve().parents[2]
PITCH = Path(__file__).resolve().parent
SHOTS = PITCH / "shots"
TEMPLATE = Path(r"C:\Users\Magiz Creations 01\Downloads\Submission Template _ AI Builder Cup.pptx")
OUT_PPTX = PITCH / "TerraSentinel-AI-Builder-Cup-Submission.pptx"
OUT_PDF = PITCH / "TerraSentinel-AI-Builder-Cup-Submission.pdf"

# Cup template is 10" × 5.625" (16:9)
SLIDE_W = 9144000
SLIDE_H = 5143500
# Safe content band under the Google header + section title
CONTENT_TOP = 1_320_000
CONTENT_LEFT = 280_000
CONTENT_RIGHT = 280_000
CONTENT_BOTTOM = 220_000
# Slide 4 title block is taller ("Opportunities" + three prompts)
CONTENT_TOP_WIDE = 1_900_000
INK = RGBColor(0x0F, 0x1D, 0x1B)
MUTED = RGBColor(0x47, 0x58, 0x54)
BRAND = RGBColor(0x0F, 0x76, 0x6E)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
SOFT = RGBColor(0xE7, 0xF4, 0xF1)
LINE = RGBColor(0xCD, 0xD7, 0xD4)


def _set_runs(tf, lines: list[tuple[str, int, bool, RGBColor | None]], align=PP_ALIGN.LEFT) -> None:
    """Replace text-frame content with (text, size_pt, bold, color) paragraphs."""
    tf.clear()
    for i, (text, size, bold, color) in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.space_after = Pt(4)
        run = p.add_run()
        run.text = text
        run.font.size = Pt(size)
        run.font.bold = bold
        run.font.color.rgb = color or INK
        run.font.name = "Calibri"


def _add_textbox(slide, left, top, width, height, lines, align=PP_ALIGN.LEFT):
    box = slide.shapes.add_textbox(Emu(left), Emu(top), Emu(width), Emu(height))
    _set_runs(box.text_frame, lines, align=align)
    box.text_frame.word_wrap = True
    return box


def _add_card(slide, left, top, width, height, fill=SOFT):
    shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Emu(left), Emu(top), Emu(width), Emu(height))
    shape.fill.solid()
    shape.fill.fore_color.rgb = fill
    shape.line.color.rgb = LINE
    shape.line.width = Pt(0.75)
    return shape


def _add_bullets(slide, left, top, width, height, items: list[str], size=13):
    box = slide.shapes.add_textbox(Emu(left), Emu(top), Emu(width), Emu(height))
    tf = box.text_frame
    tf.word_wrap = True
    tf.clear()
    for i, item in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.level = 0
        p.space_after = Pt(3)
        run = p.add_run()
        run.text = f"•  {item}"
        run.font.size = Pt(size)
        run.font.color.rgb = INK
        run.font.name = "Calibri"
    return box


def _img(slide, path: Path, left, top, width, height):
    if not path.exists():
        return None
    return slide.shapes.add_picture(str(path), Emu(left), Emu(top), Emu(width), Emu(height))


def _clear_body_keep_chrome(slide, keep_names_substr=("Google Shape",)):
    """Remove non-chrome shapes we may have added on a previous run — template shapes stay."""
    # We always start from a fresh template copy, so no-op.
    return


def fill_team(slide):
    # Replace the team-details text box content
    for sh in slide.shapes:
        if not sh.has_text_frame:
            continue
        if "Team Details" in sh.text_frame.text or "Team name" in sh.text_frame.text:
            _set_runs(
                sh.text_frame,
                [
                    ("Team Details", 22, True, BRAND),
                    ("", 8, False, MUTED),
                    ("Team name:  Agent Ram", 16, True, INK),
                    ("Team leader:  Ramasamy P", 15, False, INK),
                    ("Track:  Sustainability · Google Cloud AI Builder Cup 2026 (JAPAC)", 14, False, MUTED),
                    ("", 8, False, MUTED),
                    (
                        "Problem:  Operators receive millimetre-scale InSAR motion, but not a ranked, "
                        "consequence-aware shortlist of which 250 m corridor segment to inspect today — "
                        "with an honest time-to-threshold band (never a failure date) and a traceable ticket.",
                        13,
                        False,
                        INK,
                    ),
                    ("", 6, False, MUTED),
                    ("Product:  TerraSentinel AI — ground-motion early warning for roads, metros and dams.", 13, True, BRAND),
                ],
            )
            return
    _add_textbox(
        slide,
        CONTENT_LEFT,
        2_950_000,
        SLIDE_W - CONTENT_LEFT - CONTENT_RIGHT,
        1_900_000,
        [
            ("Team Details", 20, True, BRAND),
            ("Team name: Agent Ram · Leader: Ramasamy P · Track: Sustainability", 14, False, INK),
            (
                "Problem: Rank InSAR ground motion into inspect-today decisions with honest outlook bands.",
                13,
                False,
                MUTED,
            ),
        ],
    )


def fill_note_slide(slide):
    """Slide 2 is the download-instruction card — turn it into a title / one-liner."""
    # Cover the instruction note with our product one-liner (keep decorative images).
    for sh in slide.shapes:
        if sh.has_text_frame and "download this template" in sh.text_frame.text.lower():
            _set_runs(
                sh.text_frame,
                [
                    ("TerraSentinel AI", 26, True, BRAND),
                    ("", 6, False, MUTED),
                    ("Which 250 metres should an engineer inspect today?", 16, True, INK),
                    ("", 6, False, MUTED),
                    (
                        "Satellites measure motion. TerraSentinel ranks consequence. "
                        "Gemini drafts the ticket — every number from tools, never invented.",
                        13,
                        False,
                        MUTED,
                    ),
                    ("", 8, False, MUTED),
                    ("Live · BigQuery · Cloud Run · labelled synthetic demo data", 12, False, BRAND),
                ],
            )
            return


def fill_idea(slide):
    _add_bullets(
        slide,
        CONTENT_LEFT,
        CONTENT_TOP,
        SLIDE_W - CONTENT_LEFT - CONTENT_RIGHT,
        3_600_000,
        [
            "Idea: turn InSAR point clouds into a consequence-ranked Act list for critical infrastructure.",
            "Maths (Python / BigQuery SQL) compute speed, acceleration, progress, RPI, tier and ETA bands.",
            "Gemini reasons and drafts inspection tickets from tool results only — a number guard rejects ungrounded figures.",
            "Rain amplifies hazard; it never creates a tier alone. USGS earthquakes are context only.",
            "Outlook = time-to-threshold band if today’s trend continues — never a collapse / failure date.",
            "Shipped: FastAPI + React/MapLibre on Cloud Run, optional BigQuery warehouse, Data Hub validate-then-import.",
            "Honesty: bundled corridors are synthetic demonstration data, labelled in the UI.",
        ],
        size=14,
    )


def fill_opportunities(slide):
    top = CONTENT_TOP_WIDE
    card_h = SLIDE_H - top - CONTENT_BOTTOM - 80_000
    w = (SLIDE_W - CONTENT_LEFT - CONTENT_RIGHT - 120_000) // 3
    cards = [
        (
            "Differentiation",
            [
                "Not another InSAR viewer",
                "250 m chainage sites + RPI",
                "Consequence × hazard × confidence",
                "Pass-to-pass alerts (diffs)",
                "Gemini narrates; engine decides",
            ],
        ),
        (
            "How it solves it",
            [
                "Ingest → locate → measure",
                "Classify + WEAK data guard",
                "Rank Act-today shortlist",
                "Outlook band (const + accel)",
                "Work order with verified numbers",
            ],
        ),
        (
            "USP",
            [
                "Honest ETA bands, not dates",
                "Number-guarded GenAI tickets",
                "Same maths: local or BigQuery",
                "Production posture on GCP",
                "Judge can sign in and act",
            ],
        ),
    ]
    for i, (title, bullets) in enumerate(cards):
        left = CONTENT_LEFT + i * (w + 60_000)
        _add_card(slide, left, top, w, card_h)
        _add_textbox(slide, left + 80_000, top + 60_000, w - 160_000, 320_000, [(title, 14, True, BRAND)])
        _add_bullets(slide, left + 50_000, top + 360_000, w - 100_000, card_h - 420_000, bullets, size=11)


def fill_features(slide):
    _add_bullets(
        slide,
        CONTENT_LEFT,
        CONTENT_TOP,
        SLIDE_W - CONTENT_LEFT - CONTENT_RIGHT,
        3_700_000,
        [
            "Command Center — map, KPIs, Act today list (CRITICAL / ELEVATED ranked by consequence)",
            "Site drawer — RPI, speed, rain trigger, outlook band, trend across satellite passes",
            "Alerts — what changed between passes (not a duplicate of the Act list)",
            "Morning Brief · Early Warning · Trends · Corridors · Portfolio",
            "Work Orders — template-first ticket; optional Gemini polish; tool-grounded numbers",
            "Data Hub — validate-then-import (CSV/GeoJSON), rainfall fetch, provenance, BigQuery sync, reset to demo",
            "Access — admin / analyst / viewer RBAC, session auth, audit log",
            "Methodology page — published formulae so every score is reproducible",
        ],
        size=13,
    )


def fill_process(slide):
    steps = [
        ("1 Ingest", "Points, series,\nrain, assets"),
        ("2 Locate", "250 m bins on\ncorridor geometry"),
        ("3 Measure", "Speed · accel\nprogress · noise"),
        ("4 Classify", "State + WEAK\ndata guard"),
        ("5 Rank", "RPI × tier\nAct list"),
        ("6 Outlook", "ETA band\n(not a date)"),
        ("7 Explain", "Gemini ticket\n+ number guard"),
    ]
    n = len(steps)
    gap = 40_000
    usable = SLIDE_W - CONTENT_LEFT - CONTENT_RIGHT - gap * (n - 1)
    w = usable // n
    top = CONTENT_TOP + 40_000
    h = 2_000_000
    for i, (title, body) in enumerate(steps):
        left = CONTENT_LEFT + i * (w + gap)
        _add_card(slide, left, top, w, h, SOFT if i % 2 == 0 else WHITE)
        _add_textbox(
            slide,
            left + 30_000,
            top + 80_000,
            w - 60_000,
            h - 140_000,
            [(title, 11, True, BRAND), ("", 4, False, MUTED), (body, 10, False, INK)],
            align=PP_ALIGN.CENTER,
        )
    _add_textbox(
        slide,
        CONTENT_LEFT,
        top + h + 80_000,
        SLIDE_W - CONTENT_LEFT - CONTENT_RIGHT,
        700_000,
        [
            (
                "Use-case: Corridor engineer opens Command Center → selects CRITICAL NH-58 KM 3.25–3.50 "
                "→ reads 35–64 day threshold band if trend continues → generates inspection work order.",
                11,
                False,
                MUTED,
            )
        ],
    )


def fill_wireframes(slide):
    # Real product screenshots instead of wireframes
    imgs = [
        (SHOTS / "01-command-center.png", "Command Center"),
        (SHOTS / "04-nh58-site.png", "Site · NH-58"),
        (SHOTS / "c-workorder.png", "Work Order"),
        (SHOTS / "c-datahub.png", "Data Hub"),
    ]
    # Prefer higher-quality captures when present
    alts = [
        SHOTS / "app-command.png",
        SHOTS / "app-site.png",
        SHOTS / "c-workorder-ai.png",
        SHOTS / "app-datahub.png",
    ]
    for i, alt in enumerate(alts):
        if alt.exists() and alt.stat().st_size > 50_000:
            imgs[i] = (alt, imgs[i][1])

    gap = 60_000
    usable = SLIDE_W - CONTENT_LEFT - CONTENT_RIGHT - gap
    w = usable // 2
    avail_h = SLIDE_H - CONTENT_TOP - CONTENT_BOTTOM - 60_000
    h = (avail_h - 80_000) // 2
    positions = [
        (CONTENT_LEFT, CONTENT_TOP),
        (CONTENT_LEFT + w + gap, CONTENT_TOP),
        (CONTENT_LEFT, CONTENT_TOP + h + 80_000),
        (CONTENT_LEFT + w + gap, CONTENT_TOP + h + 80_000),
    ]
    for (path, cap), (left, top) in zip(imgs, positions):
        _img(slide, path, left, top, w, h - 70_000)
        _add_textbox(slide, left, top + h - 60_000, w, 60_000, [(cap, 10, True, BRAND)])


def fill_architecture(slide):
    layers = [
        ("L5 Edge", "Cloud Run · HTTPS · CSP · CSRF · rate limits · sessions · GCS state"),
        ("L4 Experience", "React SPA · MapLibre · React Query · RBAC UI"),
        ("L3 API", "FastAPI · auth · audit · SSRF-safe fetch · Data Hub ingest"),
        ("L2 Intelligence", "Detection engine · RPI · tiers · ETA bands · alerts"),
        ("L1 GenAI", "Gemini tool-calling · number guard · template fallback"),
        ("L0 Data", "Local workspace XOR BigQuery · USGS public context (never scores)"),
    ]
    avail = SLIDE_H - CONTENT_TOP - CONTENT_BOTTOM - 40_000
    row_h = avail // len(layers) - 30_000
    for i, (title, body) in enumerate(layers):
        top = CONTENT_TOP + i * (row_h + 30_000)
        _add_card(slide, CONTENT_LEFT, top, SLIDE_W - CONTENT_LEFT - CONTENT_RIGHT, row_h)
        _add_textbox(
            slide,
            CONTENT_LEFT + 100_000,
            top + 50_000,
            SLIDE_W - CONTENT_LEFT - CONTENT_RIGHT - 200_000,
            row_h - 80_000,
            [(f"{title}   —   {body}", 11, False, INK)],
        )


def fill_tech(slide):
    cols = [
        (
            "Google Cloud",
            [
                "Cloud Run (max-instances=1)",
                "Cloud Build + Artifact Registry",
                "BigQuery (partitioned InSAR)",
                "Secret Manager",
                "Cloud Storage (state volume)",
                "Gemini API (work orders)",
            ],
        ),
        (
            "Application",
            [
                "Python 3.12 · FastAPI",
                "Deterministic detection engine",
                "React · Vite · MapLibre",
                "TanStack Query",
                "Session auth + RBAC",
                "Validate-then-import Data Hub",
            ],
        ),
        (
            "Data & integrity",
            [
                "Synthetic demo (labelled)",
                "Open-Meteo rainfall fetch",
                "USGS seismicity (context)",
                "Number guard on Gemini",
                "Provenance registry",
                "pytest + security checklist",
            ],
        ),
    ]
    w = (SLIDE_W - CONTENT_LEFT - CONTENT_RIGHT - 120_000) // 3
    for i, (title, items) in enumerate(cols):
        left = CONTENT_LEFT + i * (w + 60_000)
        _add_card(slide, left, CONTENT_TOP, w, 3_550_000)
        _add_textbox(slide, left + 80_000, CONTENT_TOP + 80_000, w - 160_000, 400_000, [(title, 14, True, BRAND)])
        _add_bullets(slide, left + 60_000, CONTENT_TOP + 420_000, w - 120_000, 3_000_000, items, size=12)


def fill_cost(slide):
    _add_bullets(
        slide,
        CONTENT_LEFT,
        CONTENT_TOP,
        SLIDE_W - CONTENT_LEFT - CONTENT_RIGHT,
        3_700_000,
        [
            "Cup demo posture (kept warm): Cloud Run 1 vCPU / 2 GiB, min-instances=1 during judging — small continuous cost.",
            "BigQuery: demo dataset ~62k time-series rows; queries cached in-process (TTL); hard max-bytes-billed guard.",
            "Gemini Flash: work-order narratives only; template fallback if quota/latency — no GenAI on the hot ranking path.",
            "Secret Manager + GCS state: pennies at demo scale.",
            "Scale path: raise instances, materialize point-assignment, keep engine deterministic so GenAI spend stays optional.",
            "Estimated Cup-month ops (order of magnitude): low tens of USD if kept warm; near-zero if scaled to zero off-hours.",
        ],
        size=13,
    )


def fill_snapshots(slide):
    imgs = [
        (SHOTS / "c-hero-map.png", "Map · corridor risk"),
        (SHOTS / "c-map-chamoli.png", "Chamoli · ranked sites"),
        (SHOTS / "c-site-now.png", "Site Now · RPI / outlook"),
        (SHOTS / "c-workorder-ai.png", "Gemini work order"),
    ]
    for i, p in enumerate(imgs):
        if not p[0].exists():
            fallback = [SHOTS / "02-map-nh58.png", SHOTS / "03-command-chamoli.png", SHOTS / "05-outlook.png", SHOTS / "c-workorder.png"]
            imgs[i] = (fallback[i], p[1])
    gap = 60_000
    usable = SLIDE_W - CONTENT_LEFT - CONTENT_RIGHT - gap
    w = usable // 2
    avail_h = SLIDE_H - CONTENT_TOP - CONTENT_BOTTOM - 60_000
    h = (avail_h - 80_000) // 2
    positions = [
        (CONTENT_LEFT, CONTENT_TOP),
        (CONTENT_LEFT + w + gap, CONTENT_TOP),
        (CONTENT_LEFT, CONTENT_TOP + h + 80_000),
        (CONTENT_LEFT + w + gap, CONTENT_TOP + h + 80_000),
    ]
    for (path, cap), (left, top) in zip(imgs, positions):
        _img(slide, path, left, top, w, h - 70_000)
        _add_textbox(slide, left, top + h - 60_000, w, 60_000, [(cap, 10, True, BRAND)])


def fill_performance(slide):
    _add_bullets(
        slide,
        CONTENT_LEFT,
        CONTENT_TOP,
        SLIDE_W - CONTENT_LEFT - CONTENT_RIGHT,
        3_700_000,
        [
            "Demo corpus: 1,355 scatterers · ~62,330 displacement rows · 87 sites of 250 m · 7 CRITICAL/ELEVATED on latest pass.",
            "Worked site NH-58 KM 3.25–3.50: RPI 86 · ~6.2 mm/month · outlook band 35–64 days if trend continues.",
            "Integrity: GenAI never computes RPI/tier/ETA; template path always available; synthetic data labelled.",
            "Latency (live Cloud Run + BigQuery, warm): region summary ~0.4 s · sites ~0.3 s · alerts ~2 s (after hot-path prefetch).",
            "Cold start mitigated: startup prefetch of BigQuery frames + current rankings before historical warm.",
            "Security: CSRF header, cookie sessions, rate limits, RBAC, audit events, no secrets in git.",
            "Tests: pytest suite covering engine, ingest, auth hardening, BigQuery fake runner.",
        ],
        size=13,
    )


def fill_future(slide):
    _add_bullets(
        slide,
        CONTENT_LEFT,
        CONTENT_TOP,
        SLIDE_W - CONTENT_LEFT - CONTENT_RIGHT,
        3_700_000,
        [
            "Connect production InSAR providers (same schema; Data Hub validate-then-import already in place).",
            "Materialize spatial point-assignment in BigQuery for national-scale corridors.",
            "Multi-region HA and horizontal Cloud Run when session store moves off single-process files.",
            "Operator workflows: assign/escalate SLAs, mobile field checklist, offline packet export.",
            "Deeper rain + geology covariates as amplifiers only — never sole drivers of tier.",
            "Keep the non-negotiable: outlook bands ≠ failure dates; GenAI narrates tools only.",
        ],
        size=13,
    )


def fill_links(slide):
    _add_textbox(
        slide,
        CONTENT_LEFT,
        CONTENT_TOP,
        SLIDE_W - CONTENT_LEFT - CONTENT_RIGHT,
        3_600_000,
        [
            ("Submission links", 16, True, BRAND),
            ("", 8, False, MUTED),
            ("GitHub public repository", 13, True, INK),
            ("https://github.com/ramasamyp-aiengineer/terra-sentinel-ai", 12, False, BRAND),
            ("", 8, False, MUTED),
            ("Demo video (3 minutes)", 13, True, INK),
            ("See repo: docs/pitch/TerraSentinel-AI-Demo-3min.mp4  (upload to Drive/YouTube for the portal)", 12, False, MUTED),
            ("", 8, False, MUTED),
            ("Final product (live)", 13, True, INK),
            ("https://terrasentinel-598899050820.asia-southeast1.run.app", 12, False, BRAND),
            ("Sign-in: username + password are shown on the login page (judge demo hint).", 12, False, MUTED),
            ("", 8, False, MUTED),
            ("Judge walkthrough: docs/JUDGE.md in the repository.", 12, False, MUTED),
        ],
    )


def fill_closing(slide, title: str, body: list[str]):
    _add_textbox(
        slide,
        CONTENT_LEFT,
        CONTENT_TOP + 200_000,
        SLIDE_W - CONTENT_LEFT - CONTENT_RIGHT,
        3_400_000,
        [(title, 22, True, BRAND), ("", 10, False, MUTED)]
        + [(line, 14, False, INK) for line in body],
    )


def export_pdf(pptx: Path, pdf: Path) -> bool:
    try:
        import win32com.client  # type: ignore
    except ImportError:
        print("pywin32 not available — install or open the PPTX and File > Export > PDF", file=sys.stderr)
        return False
    pptx_abs = str(pptx.resolve())
    pdf_abs = str(pdf.resolve())
    app = win32com.client.Dispatch("PowerPoint.Application")
    app.Visible = 1
    try:
        pres = app.Presentations.Open(pptx_abs, WithWindow=False)
        # 32 = ppSaveAsPDF
        pres.SaveAs(pdf_abs, 32)
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
    assert len(prs.slides) >= 14, f"unexpected slide count {len(prs.slides)}"

    fillers = [
        fill_team,  # 1
        fill_note_slide,  # 2
        fill_idea,  # 3
        fill_opportunities,  # 4
        fill_features,  # 5
        fill_process,  # 6
        fill_wireframes,  # 7
        fill_architecture,  # 8
        fill_tech,  # 9
        fill_cost,  # 10
        fill_snapshots,  # 11
        fill_performance,  # 12
        fill_future,  # 13
        fill_links,  # 14
    ]
    for i, fn in enumerate(fillers):
        fn(prs.slides[i])

    # Slides 15–16: closing / thank you (template has chrome only)
    if len(prs.slides) >= 15:
        fill_closing(
            prs.slides[14],
            "Honesty rules (non-negotiable)",
            [
                "Outlooks are time-to-threshold bands under a continuing-regime assumption — not collapse predictions.",
                "Gemini narrates tool numbers only; it does not invent scores, ETAs or tiers.",
                "Demo / synthetic data is labelled in the product.",
                "Secrets stay in .env / Secret Manager — never in git.",
            ],
        )
    if len(prs.slides) >= 16:
        fill_closing(
            prs.slides[15],
            "Thank you — Team Agent Ram",
            [
                "TerraSentinel AI · Google Cloud AI Builder Cup 2026 · Sustainability",
                "Live demo + GitHub + this deck · Ask us to walk Command Center → Work Order → Data Hub.",
                "Ramasamy P · ramasamy.p2105@gmail.com",
            ],
        )

    prs.save(str(OUT_PPTX))
    print(f"Wrote {OUT_PPTX}")
    export_pdf(OUT_PPTX, OUT_PDF)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
