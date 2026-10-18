"""Generate the DEMONSTRATION dataset.

IMPORTANT: this data is synthetic. It follows the same schema as pre-processed
InSAR products (e.g. Copernicus EGMS / COMET-LiCSAR point time series) so a real
file can replace it without code changes (see loader / ingest docs).
Every output row is tagged source="DEMO-SYNTHETIC" and the UI shows a
"Demonstration data" label. Real coordinates are used only for geographic
context; the motion values are NOT real measurements.

Usage:  python -m app.services.data.generate_demo
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
from shapely.geometry import LineString

from app.core.config import settings
from app.services.detection.engine import CHAINAGE_BIN_M, _meters_per_deg, _project_line

SEED = 42
LAST_EPOCH = pd.Timestamp("2026-10-10")
N_EPOCHS = 46
STEP_DAYS = 12
AS_OF = pd.Timestamp("2026-10-16")
DAYS_PER_MONTH = 30.4375
SOURCE = "DEMO-SYNTHETIC"

DATES = pd.DatetimeIndex([LAST_EPOCH - pd.Timedelta(days=STEP_DAYS * i) for i in range(N_EPOCHS)][::-1])


# ---- motion scenarios: return displacement (mm, negative = away) per epoch ---


def _integrate(v_mm_month: np.ndarray) -> np.ndarray:
    dt = np.diff(np.concatenate([[0], np.arange(len(DATES)) * STEP_DAYS])) / DAYS_PER_MONTH
    return -np.cumsum(v_mm_month * dt)


def _date_f(d: str) -> float:
    return float((pd.Timestamp(d) - DATES[0]).days)


def _t() -> np.ndarray:
    return np.array([(d - DATES[0]).days for d in DATES], dtype=float)


def sc_stable() -> np.ndarray:
    return _integrate(np.full(len(DATES), 0.08))


def sc_seasonal() -> np.ndarray:
    t = _t()
    bump = np.zeros_like(t)
    for peak in ("2025-08-10", "2026-08-10"):
        bump += np.exp(-0.5 * ((t - _date_f(peak)) / 35.0) ** 2)
    return -9.0 * bump


def sc_creep(v: float) -> np.ndarray:
    return _integrate(np.full(len(DATES), v))


def sc_ramp(base: float, ramp_start: str, v_end: float) -> np.ndarray:
    """Constant base speed, then linear ramp to v_end at the last epoch."""
    t = _t()
    t0, t1 = _date_f(ramp_start), t[-1]
    v = np.where(t < t0, base, base + (v_end - base) * (t - t0) / (t1 - t0))
    return _integrate(v)


# ---- geometry ----------------------------------------------------------------

ASSET_DEFS = [
    {
        "asset_id": "NH58-DEMO",
        "name": "NH-58 Himalayan Corridor (demo)",
        "type": "HIGHWAY",
        "region_id": "IN-UK-CHM",
        "criticality": 0.95,
        "consequence_note": "Sole arterial access to the upper valley; high daily transit volume.",
        "coords": [(79.535, 30.535), (79.560, 30.545), (79.575, 30.565), (79.600, 30.575)],
        "sites": {
            1: ("stable", {}),
            3: ("stable", {}),
            5: ("seasonal", {}),
            7: ("creep", {"v": 2.7}),
            10: ("ramp", {"base": 1.2, "start": "2026-06-01", "end": 5.8}),  # hero (rain -> CRITICAL)
            13: ("ramp", {"base": 1.5, "start": "2026-03-01", "end": 7.2}),  # nearing threshold
            16: ("degraded", {}),
            19: ("stable", {}),
            22: ("stable", {}),
            25: ("stable", {}),
        },
    },
    {
        "asset_id": "SR12-DEMO",
        "name": "State Road 12 - alternate route (demo)",
        "type": "HIGHWAY",
        "region_id": "IN-UK-CHM",
        "criticality": 0.40,
        "consequence_note": "Low-traffic alternate route; detour available.",
        "coords": [(79.540, 30.515), (79.570, 30.528), (79.598, 30.545), (79.625, 30.552)],
        "sites": {
            2: ("stable", {}),
            6: ("ramp", {"base": 1.2, "start": "2026-06-01", "end": 5.8}),  # same motion, low consequence
            9: ("stable", {}),
            12: ("seasonal", {}),
            15: ("stable", {}),
            18: ("stable", {}),
        },
    },
    {
        "asset_id": "METRO4-DEMO",
        "name": "Urban Metro Line 4 Tunnel Corridor - Chennai (demo)",
        "type": "METRO",
        "region_id": "IN-TN-CHN",
        "criticality": 0.90,
        "consequence_note": "Four-lane arterial road and mid-rise commercial buildings above the tunnel drive.",
        "coords": [(80.2650, 13.0790), (80.2720, 13.0830), (80.2790, 13.0850), (80.2880, 13.0880)],
        "sites": {
            0: ("stable", {}),
            2: ("stable", {}),
            4: ("ramp", {"base": 1.0, "start": "2026-07-10", "end": 9.0}),  # settlement trough
            6: ("creep", {"v": 1.9}),
            8: ("stable", {}),
            9: ("stable", {}),
        },
    },
    {
        "asset_id": "DAM-DEMO",
        "name": "Tailings Dam Crest (demo)",
        "type": "DAM",
        "region_id": "IN-JH-DHN",
        "criticality": 0.95,
        "consequence_note": "Downstream community and haul road within the breach runout zone.",
        "coords": [(86.405, 23.735), (86.412, 23.738), (86.420, 23.737)],
        "sites": {
            0: ("stable", {}),
            2: ("ramp", {"base": 0.9, "start": "2026-07-01", "end": 2.6}),
            4: ("stable", {}),
        },
    },
]

REGIONS = [
    {"region_id": "IN", "parent_id": None, "name": "India", "level": "country", "center": [79.0, 22.0], "zoom": 4.2},
    {"region_id": "IN-UK", "parent_id": "IN", "name": "Uttarakhand", "level": "state", "center": [79.57, 30.55], "zoom": 8.5},
    {"region_id": "IN-UK-CHM", "parent_id": "IN-UK", "name": "Chamoli District", "level": "district", "center": [79.575, 30.545], "zoom": 11.2},
    {"region_id": "IN-TN", "parent_id": "IN", "name": "Tamil Nadu", "level": "state", "center": [80.2, 13.0], "zoom": 8.5},
    {"region_id": "IN-TN-CHN", "parent_id": "IN-TN", "name": "Chennai Metropolitan Area", "level": "district", "center": [80.275, 13.083], "zoom": 13.0},
    {"region_id": "IN-JH", "parent_id": "IN", "name": "Jharkhand", "level": "state", "center": [86.4, 23.75], "zoom": 8.5},
    {"region_id": "IN-JH-DHN", "parent_id": "IN-JH", "name": "Dhanbad Mining Belt", "level": "district", "center": [86.412, 23.737], "zoom": 13.2},
]


def _point_on_line(line_m: LineString, chain_m: float, offset_m: float) -> tuple[float, float]:
    p = line_m.interpolate(chain_m)
    p2 = line_m.interpolate(min(chain_m + 2, line_m.length))
    p1 = line_m.interpolate(max(chain_m - 2, 0))
    dx, dy = p2.x - p1.x, p2.y - p1.y
    n = math.hypot(dx, dy) or 1.0
    return p.x + (-dy / n) * offset_m, p.y + (dx / n) * offset_m


def _to_lonlat(x: float, y: float, lon0: float, lat0: float, mx: float, my: float) -> tuple[float, float]:
    return lon0 + x / mx, lat0 + y / my


def _scenario(kind: str, args: dict) -> np.ndarray:
    if kind == "stable":
        return sc_stable()
    if kind == "seasonal":
        return sc_seasonal()
    if kind == "creep":
        return sc_creep(args["v"])
    if kind == "ramp":
        return sc_ramp(args["base"], args["start"], args["end"])
    if kind == "degraded":
        return sc_creep(2.5)
    raise ValueError(kind)


def generate(out_dir: Path | None = None) -> dict:
    rng = np.random.default_rng(SEED)
    out = Path(out_dir or settings.data_dir)
    out.mkdir(parents=True, exist_ok=True)

    points, series, features = [], [], []
    pid = 0
    projected: list[tuple[LineString, float, float, float, float]] = []

    for a in ASSET_DEFS:
        line_ll = LineString(a["coords"])
        line_m, lon0, lat0 = _project_line(line_ll)
        mx, my = _meters_per_deg(line_ll.centroid.y)
        length_m = line_m.length
        projected.append((line_m, lon0, lat0, mx, my))
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "asset_id": a["asset_id"],
                    "name": a["name"],
                    "asset_type": a["type"],
                    "region_id": a["region_id"],
                    "criticality": a["criticality"],
                    "consequence_note": a["consequence_note"],
                    "length_km": round(length_m / 1000, 2),
                    "source": SOURCE,
                },
                "geometry": {"type": "LineString", "coordinates": [list(c) for c in a["coords"]]},
            }
        )

        n_bins = int(length_m // CHAINAGE_BIN_M)
        for b in range(n_bins + 1):
            kind, args = a["sites"].get(b, ("stable", {}))
            base = _scenario(kind, args)
            degraded = kind == "degraded"
            n_pts = 3 if degraded else int(rng.integers(8, 13))
            common_atmo = rng.normal(0, 0.35, len(DATES))  # shared atmospheric noise

            for _ in range(n_pts):
                chain = min(b * CHAINAGE_BIN_M + rng.uniform(15, CHAINAGE_BIN_M - 15), length_m - 1)
                off = rng.uniform(-60, 60)
                x, y = _point_on_line(line_m, chain, off)
                lon, lat = _to_lonlat(x, y, lon0, lat0, mx, my)
                scale = rng.uniform(0.85, 1.15)
                noise_sd = 3.2 if degraded else 0.35
                disp = base * scale + common_atmo + rng.normal(0, noise_sd, len(DATES))
                disp -= disp[0]
                coh = rng.uniform(0.28, 0.48) if degraded else rng.uniform(0.72, 0.95)
                slope = np.polyfit(_t(), disp, 1)[0] * 365
                pid += 1
                point_id = f"P{pid:05d}"
                points.append(
                    {
                        "point_id": point_id,
                        "lat": round(lat, 6),
                        "lon": round(lon, 6),
                        "velocity_mm_yr": round(float(slope), 2),
                        "coherence": round(float(coh), 3),
                        "region_id": a["region_id"],
                        "source": SOURCE,
                    }
                )
                for d, v in zip(DATES, disp):
                    series.append({"point_id": point_id, "date": d.date().isoformat(), "disp_mm": round(float(v), 2)})

    # Background scatterers + an unmonitored moving hillside (no asset nearby -> no alert)
    bg_defs = [
        ("IN-UK-CHM", (79.50, 30.50, 79.66, 30.62), 260, (79.640, 30.600)),
        ("IN-TN-CHN", (80.24, 13.05, 80.32, 13.11), 160, None),
        ("IN-JH-DHN", (86.38, 23.72, 86.44, 23.76), 90, None),
    ]
    from shapely.geometry import Point

    def near_asset(lon: float, lat: float, min_m: float = 350.0) -> bool:
        for line_m, lon0, lat0, mx, my in projected:
            if line_m.distance(Point((lon - lon0) * mx, (lat - lat0) * my)) < min_m:
                return True
        return False

    for region, (x0, y0, x1, y1), n, moving_center in bg_defs:
        for i in range(n):
            moving = moving_center is not None and i < 24
            while True:
                if moving:
                    lon = moving_center[0] + rng.normal(0, 0.003)
                    lat = moving_center[1] + rng.normal(0, 0.003)
                else:
                    lon, lat = rng.uniform(x0, x1), rng.uniform(y0, y1)
                # Keep background scatterers out of asset buffers so scripted sites stay clean
                if not near_asset(lon, lat):
                    break
            base = sc_creep(3.5) if moving else sc_stable()
            disp = base + rng.normal(0, 0.4, len(DATES))
            disp -= disp[0]
            slope = np.polyfit(_t(), disp, 1)[0] * 365
            pid += 1
            point_id = f"P{pid:05d}"
            points.append(
                {
                    "point_id": point_id,
                    "lat": round(float(lat), 6),
                    "lon": round(float(lon), 6),
                    "velocity_mm_yr": round(float(slope), 2),
                    "coherence": round(float(rng.uniform(0.6, 0.92)), 3),
                    "region_id": region,
                    "source": SOURCE,
                }
            )
            for d, v in zip(DATES, disp):
                series.append({"point_id": point_id, "date": d.date().isoformat(), "disp_mm": round(float(v), 2)})

    pd.DataFrame(points).to_csv(out / "insar_points.csv", index=False)
    pd.DataFrame(series).to_csv(out / "insar_timeseries.csv", index=False)
    (out / "assets.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": features}, indent=1))
    (out / "regions.json").write_text(json.dumps(REGIONS, indent=1))

    # Demo rainfall (labelled demonstration): heavy late-Sep/early-Oct event in Chamoli
    rain_rows = []
    days = pd.date_range(AS_OF - pd.Timedelta(days=120), AS_OF, freq="D")
    profiles = {
        "IN-UK-CHM": dict(base=4.0, event=(AS_OF - pd.Timedelta(days=11), 9, 22.0)),
        "IN-TN-CHN": dict(base=2.5, event=(AS_OF - pd.Timedelta(days=6), 4, 12.0)),
        "IN-JH-DHN": dict(base=1.5, event=(AS_OF - pd.Timedelta(days=9), 3, 6.0)),
    }
    for region, p in profiles.items():
        ev_start, ev_len, ev_mm = p["event"]
        for d in days:
            mm = max(0.0, rng.gamma(1.2, p["base"] / 1.2) * (0.6 if d.month in (10, 11) else 1.0))
            if ev_start <= d < ev_start + pd.Timedelta(days=ev_len):
                mm += ev_mm * rng.uniform(0.7, 1.3)
            rain_rows.append({"region_id": region, "date": d.date().isoformat(), "precip_mm": round(float(mm), 1)})
    pd.DataFrame(rain_rows).to_csv(out / "rain_demo.csv", index=False)

    (out / "PROVENANCE.md").write_text(
        "# Demo dataset provenance\n\n"
        "**All motion values in this folder are SYNTHETIC (source = DEMO-SYNTHETIC).**\n"
        "They follow the schema of pre-processed InSAR point products (Copernicus EGMS, "
        "COMET-LiCSAR) so real files can replace them. Coordinates are real geography used "
        "for context only. Rainfall in rain_demo.csv is also synthetic.\n\n"
        f"Generated with seed {SEED}; last epoch {LAST_EPOCH.date()}; {N_EPOCHS} epochs at "
        f"{STEP_DAYS}-day cadence (mimicking Sentinel-1).\n"
    )
    return {"points": len(points), "series_rows": len(series), "assets": len(features)}


if __name__ == "__main__":
    print(generate())
