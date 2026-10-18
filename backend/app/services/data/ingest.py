"""Parse, validate and normalise uploaded / fetched data into the canonical schema.

Supported inputs
  insar       wide CSV, one row per scatterer, one column per epoch (EGMS / LiCSAR style)
              -> produces BOTH a points table and a time-series table
  points      CSV: point_id, lat, lon [, velocity_mm_yr, coherence, region_id, source]
  timeseries  CSV (long): point_id, date, disp_mm
  rain        CSV: region_id, date, precip_mm
  assets      GeoJSON FeatureCollection of (Multi)LineStrings
  regions     JSON list or CSV: region_id, parent_id, name, level, center_lon, center_lat [, zoom]

Rules
  * Nothing is written here; this module only returns normalised data + a report.
  * Bad rows are dropped *and reported*; if too many are bad the whole file is refused.
  * Anything defaulted (coherence, criticality...) is called out in ``warnings`` so no
    assumption is ever silent.
"""
from __future__ import annotations

import io
import json
import math
import re
from dataclasses import asdict, dataclass, field

import numpy as np
import pandas as pd
from shapely.geometry import LineString, MultiLineString, mapping, shape
from shapely.ops import linemerge

from app.core.config import settings

MAX_ERRORS = 25
MAX_REJECT_RATIO = 0.20
# Do not assign a point/asset to a region whose centre is farther than this (stops
# non-India AOIs silently joining Chamoli/Chennai leaves).
MAX_NEAREST_REGION_KM = 250.0
ASSET_TYPES = ("HIGHWAY", "METRO", "DAM")
DEFAULT_COHERENCE = 0.70
DEFAULT_CRITICALITY = 0.50
DEFAULT_ZOOM = {"country": 4.2, "state": 8.5, "district": 11.5, "city": 12.0}

POINT_ALIASES = {
    "point_id": ["point_id", "pid", "id", "ps_id", "mp_id", "code", "point"],
    "lat": ["lat", "latitude", "y", "lat_deg"],
    "lon": ["lon", "lng", "long", "longitude", "x", "lon_deg"],
    "velocity_mm_yr": ["velocity_mm_yr", "velocity", "mean_velocity", "mean_velocity_mm_yr", "vel", "vel_mm_yr", "los_velocity"],
    "coherence": ["coherence", "temporal_coherence", "coh", "tcoh", "avg_coherence"],
    "region_id": ["region_id", "region"],
    "source": ["source"],
}
TS_ALIASES = {
    "point_id": POINT_ALIASES["point_id"],
    "date": ["date", "epoch", "acquisition_date", "datetime", "time"],
    "disp_mm": ["disp_mm", "displacement", "displacement_mm", "disp", "d_mm", "los_displacement"],
}
RAIN_ALIASES = {
    "region_id": ["region_id", "region"],
    "date": ["date", "day", "time"],
    "precip_mm": ["precip_mm", "precipitation", "precipitation_sum", "rain_mm", "rain", "precip", "prcp"],
}
REGION_ALIASES = {
    "region_id": ["region_id", "id", "code"],
    "parent_id": ["parent_id", "parent"],
    "name": ["name", "title", "label"],
    "level": ["level", "type", "admin_level"],
    "center_lon": ["center_lon", "lon", "longitude", "lng"],
    "center_lat": ["center_lat", "lat", "latitude"],
    "zoom": ["zoom"],
}
TYPE_ALIASES = {
    "HIGHWAY": {"highway", "road", "motorway", "trunk", "primary", "secondary", "national_highway", "nh", "expressway", "mountain_road", "street"},
    "METRO": {"metro", "subway", "tunnel", "rail", "railway", "light_rail", "tram", "underground", "mrt"},
    "DAM": {"dam", "tailings", "embankment", "reservoir", "levee", "dyke", "dike", "weir", "tsf"},
}
_ALIAS_TO_TYPE = {a: t for t, als in TYPE_ALIASES.items() for a in als} | {t.lower(): t for t in ASSET_TYPES}
_REGION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_\-]{0,63}$")


# ---------------------------------------------------------------------------
# result types
# ---------------------------------------------------------------------------


@dataclass
class ValidationReport:
    kind: str
    ok: bool = False
    detected_format: str = ""
    rows_in: int = 0
    rows_ok: int = 0
    rows_rejected: int = 0
    errors: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    mapped_columns: dict = field(default_factory=dict)
    summary: dict = field(default_factory=dict)
    preview: list[dict] = field(default_factory=list)
    blocked_reason: str | None = None

    def err(self, row, fld: str, msg: str) -> None:
        if len(self.errors) < MAX_ERRORS:
            self.errors.append({"row": row, "field": fld, "message": msg})

    def finish(self) -> "ValidationReport":
        if self.blocked_reason is None:
            if self.rows_ok == 0:
                self.blocked_reason = "No valid rows found."
            elif self.rows_in and self.rows_rejected / self.rows_in > MAX_REJECT_RATIO:
                pct = round(100 * self.rows_rejected / self.rows_in)
                self.blocked_reason = f"{pct}% of rows are invalid (limit {int(MAX_REJECT_RATIO * 100)}%). Fix the file and retry."
        self.ok = self.blocked_reason is None
        return self

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ParseResult:
    reports: list[ValidationReport]
    payloads: dict = field(default_factory=dict)  # kind -> DataFrame | list[dict]

    @property
    def ok(self) -> bool:
        return bool(self.reports) and all(r.ok for r in self.reports)

    def to_dict(self) -> dict:
        return {"ok": self.ok, "reports": [r.to_dict() for r in self.reports]}


@dataclass
class ParseContext:
    filename: str = "upload"
    regions: list[dict] = field(default_factory=list)
    default_region: str | None = None

    @property
    def source_label(self) -> str:
        return f"UPLOAD:{self.filename}"[:120]


class IngestError(ValueError):
    """The file cannot be parsed at all (wrong type, unreadable, too large)."""


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _norm(c) -> str:
    return re.sub(r"[^0-9a-z]+", "_", str(c).strip().lower()).strip("_")


def _canon(df: pd.DataFrame, aliases: dict[str, list[str]]) -> tuple[pd.DataFrame, dict]:
    by_norm: dict[str, str] = {}
    for c in df.columns:
        by_norm.setdefault(_norm(c), c)
    mapped: dict[str, str] = {}
    for canon, als in aliases.items():
        for a in als:
            if a in by_norm and by_norm[a] not in mapped.values():
                mapped[canon] = by_norm[a]
                break
    out = df[list(mapped.values())].rename(columns={v: k for k, v in mapped.items()}).copy()
    return out, mapped


def _row_no(idx) -> int:
    return int(idx) + 2  # 1-based, plus the header row


def _preview(df: pd.DataFrame, n: int = 5) -> list[dict]:
    return json.loads(df.head(n).to_json(orient="records", date_format="iso"))


def _haversine_km(lon1, lat1, lon2, lat2) -> float:
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _leaf_regions(regions: list[dict]) -> list[dict]:
    parents = {r.get("parent_id") for r in regions}
    leaves = [r for r in regions if r["region_id"] not in parents]
    return leaves or regions


def nearest_region(
    lon: float,
    lat: float,
    regions: list[dict],
    max_km: float = MAX_NEAREST_REGION_KM,
) -> tuple[str | None, float | None]:
    """Return (region_id, distance_km), or (None, distance) when farther than ``max_km``."""
    best, best_d = None, None
    for r in _leaf_regions(regions):
        d = _haversine_km(lon, lat, r["center"][0], r["center"][1])
        if best_d is None or d < best_d:
            best, best_d = r["region_id"], d
    if best is None or best_d is None:
        return None, None
    if best_d > max_km:
        return None, best_d
    return best, best_d


def _line_km(coords) -> float:
    return sum(_haversine_km(a[0], a[1], b[0], b[1]) for a, b in zip(coords[:-1], coords[1:]))


def _read_csv(content: bytes) -> pd.DataFrame:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise IngestError(
            "This CSV is not UTF-8. Re-export it as UTF-8 from Excel or your GIS tool and try again."
        ) from exc
    head = text.splitlines()[0] if text else ""
    sep = ";" if head.count(";") > head.count(",") else ("\t" if head.count("\t") > head.count(",") else ",")
    try:
        df = pd.read_csv(io.StringIO(text), sep=sep, low_memory=False)
    except Exception as exc:  # noqa: BLE001 - surface any parser failure as a user-facing error
        raise IngestError(f"Could not read the CSV: {exc}") from exc
    if df.empty or len(df.columns) < 2:
        raise IngestError("The CSV is empty or has fewer than two columns.")
    return df


_DATE_HEADER = [
    (re.compile(r"^(\d{8})$"), "%Y%m%d"),
    (re.compile(r"^d_?(\d{8})$"), "%Y%m%d"),
    (re.compile(r"^(\d{4}_\d{2}_\d{2})$"), "%Y_%m_%d"),
    (re.compile(r"^d_?(\d{4}_\d{2}_\d{2})$"), "%Y_%m_%d"),
]


def _parse_date_header(raw: str) -> pd.Timestamp | None:
    # Excel round-trips epoch headers like 20250105 → 20250105.0
    s = str(raw).strip()
    if re.fullmatch(r"\d{8}\.0+", s):
        s = s.split(".", 1)[0]
    norm = _norm(s)
    if re.fullmatch(r"\d{8}_0+", norm):
        norm = norm.split("_", 1)[0]
    for rx, fmt in _DATE_HEADER:
        m = rx.match(norm)
        if m:
            try:
                return pd.to_datetime(m.group(1), format=fmt)
            except ValueError:
                return None
    return None


def _date_columns(df: pd.DataFrame) -> dict[str, pd.Timestamp]:
    out = {}
    for c in df.columns:
        d = _parse_date_header(c)
        if d is not None:
            out[c] = d
    return out


# ---------------------------------------------------------------------------
# kind: points
# ---------------------------------------------------------------------------


def parse_points(df: pd.DataFrame, ctx: ParseContext, fmt: str = "csv") -> tuple[pd.DataFrame, ValidationReport]:
    rep = ValidationReport("points", detected_format=fmt, rows_in=len(df))
    work, mapped = _canon(df, POINT_ALIASES)
    rep.mapped_columns = mapped
    missing = [c for c in ("point_id", "lat", "lon") if c not in work]
    if missing:
        rep.blocked_reason = f"Missing required column(s): {', '.join(missing)}. Accepted names: point_id/pid, lat/latitude, lon/longitude."
        return pd.DataFrame(), rep.finish()

    work["point_id"] = work["point_id"].astype(str).str.strip()
    work["lat"] = pd.to_numeric(work["lat"], errors="coerce")
    work["lon"] = pd.to_numeric(work["lon"], errors="coerce")
    bad = (
        work["point_id"].isin(["", "nan", "None"])
        | work["lat"].isna()
        | work["lon"].isna()
        | ~work["lat"].between(-90, 90)
        | ~work["lon"].between(-180, 180)
    )
    for idx in work.index[bad][:MAX_ERRORS]:
        rep.err(_row_no(idx), "lat/lon/point_id", "Missing or out-of-range value.")
    work = work[~bad].copy()
    rep.rows_rejected = int(bad.sum())

    dup = int(work["point_id"].duplicated().sum())
    if dup:
        rep.warnings.append(f"{dup} duplicate point_id row(s); the last occurrence of each is kept.")
        work = work.drop_duplicates("point_id", keep="last")

    if "velocity_mm_yr" in work:
        work["velocity_mm_yr"] = pd.to_numeric(work["velocity_mm_yr"], errors="coerce")
    else:
        work["velocity_mm_yr"] = np.nan
    if "coherence" in work:
        coh = pd.to_numeric(work["coherence"], errors="coerce")
        out_of_range = int((coh.notna() & ~coh.between(0, 1)).sum())
        if out_of_range:
            rep.warnings.append(f"{out_of_range} coherence value(s) outside 0-1 were treated as missing.")
        coh = coh.where(coh.between(0, 1))
        n_missing = int(coh.isna().sum())
        if n_missing:
            rep.warnings.append(
                f"{n_missing} point(s) have no coherence; assumed {DEFAULT_COHERENCE:.2f}. "
                "Confidence for those sites is NOT derived from real data."
            )
        work["coherence"] = coh.fillna(DEFAULT_COHERENCE)
    else:
        rep.warnings.append(
            f"No coherence column; assumed {DEFAULT_COHERENCE:.2f} for every point. "
            "Confidence scores are NOT derived from real data - supply temporal coherence if you have it."
        )
        work["coherence"] = DEFAULT_COHERENCE

    if "region_id" not in work:
        work["region_id"] = None
    need = work["region_id"].isna() | (work["region_id"].astype(str).str.strip() == "")
    if need.any():
        if ctx.default_region:
            work.loc[need, "region_id"] = ctx.default_region
        elif ctx.regions:
            assigned, far = 0, 0
            for idx, lo, la in zip(work.loc[need].index, work.loc[need, "lon"], work.loc[need, "lat"]):
                rid, dist = nearest_region(float(lo), float(la), ctx.regions)
                if rid is None:
                    work.at[idx, "region_id"] = "UNASSIGNED"
                    far += 1
                else:
                    work.at[idx, "region_id"] = rid
                    assigned += 1
            if assigned:
                rep.warnings.append(
                    f"{assigned} point(s) had no region_id; assigned to the nearest region within {MAX_NEAREST_REGION_KM:.0f} km."
                )
            if far:
                rep.warnings.append(
                    f"{far} point(s) had no region_id and were farther than {MAX_NEAREST_REGION_KM:.0f} km from every "
                    "region centre; set to UNASSIGNED. Pass a default region or add a region_id column."
                )
        else:
            work.loc[need, "region_id"] = "UNASSIGNED"
    work["source"] = work["source"].fillna(ctx.source_label) if "source" in work else ctx.source_label

    work = work[["point_id", "lat", "lon", "velocity_mm_yr", "coherence", "region_id", "source"]].reset_index(drop=True)
    rep.rows_ok = len(work)
    rep.summary = {
        "points": len(work),
        "bbox": [round(float(work["lon"].min()), 5), round(float(work["lat"].min()), 5), round(float(work["lon"].max()), 5), round(float(work["lat"].max()), 5)] if len(work) else None,
        "velocity_supplied": bool(work["velocity_mm_yr"].notna().any()),
    }
    rep.preview = _preview(work)
    return work, rep.finish()


# ---------------------------------------------------------------------------
# kind: timeseries (long)
# ---------------------------------------------------------------------------


def parse_timeseries(df: pd.DataFrame, ctx: ParseContext, fmt: str = "csv") -> tuple[pd.DataFrame, ValidationReport]:
    rep = ValidationReport("timeseries", detected_format=fmt, rows_in=len(df))
    work, mapped = _canon(df, TS_ALIASES)
    rep.mapped_columns = mapped
    missing = [c for c in ("point_id", "date", "disp_mm") if c not in work]
    if missing:
        rep.blocked_reason = f"Missing required column(s): {', '.join(missing)}. Accepted names: point_id/pid, date/epoch, disp_mm/displacement."
        return pd.DataFrame(), rep.finish()

    work["point_id"] = work["point_id"].astype(str).str.strip()
    work["date"] = pd.to_datetime(work["date"], errors="coerce")
    work["disp_mm"] = pd.to_numeric(work["disp_mm"], errors="coerce")
    bad = work["date"].isna() | work["disp_mm"].isna() | work["point_id"].isin(["", "nan"]) | (work["disp_mm"].abs() > 5000)
    for idx in work.index[bad][:MAX_ERRORS]:
        rep.err(_row_no(idx), "date/disp_mm", "Unparseable date, missing value, or |displacement| > 5000 mm.")
    rep.rows_rejected = int(bad.sum())
    work = work[~bad]
    dup = int(work.duplicated(["point_id", "date"]).sum())
    if dup:
        rep.warnings.append(f"{dup} duplicate (point_id, date) row(s) were averaged.")
        work = work.groupby(["point_id", "date"], as_index=False)["disp_mm"].mean()
    work = work[["point_id", "date", "disp_mm"]].sort_values(["point_id", "date"]).reset_index(drop=True)
    rep.rows_ok = len(work)
    _ts_summary(work, rep)
    rep.preview = _preview(work)
    return work, rep.finish()


def _ts_summary(ts: pd.DataFrame, rep: ValidationReport) -> None:
    if ts.empty:
        return
    epochs = ts.groupby("point_id")["date"].nunique()
    dates = np.sort(ts["date"].unique())
    cadence = float(np.median(np.diff(dates).astype("timedelta64[D]").astype(float))) if len(dates) > 1 else None
    rep.summary = {
        "points": int(ts["point_id"].nunique()),
        "epochs": int(len(dates)),
        "date_min": str(pd.Timestamp(dates[0]).date()),
        "date_max": str(pd.Timestamp(dates[-1]).date()),
        "cadence_days": round(cadence, 1) if cadence else None,
        "median_epochs_per_point": int(epochs.median()),
    }
    if int(epochs.median()) < 8:
        rep.warnings.append("Fewer than 8 epochs per point: velocity and acceleration estimates will be unreliable.")
    if cadence and cadence > 30:
        rep.warnings.append(f"Median cadence is {cadence:.0f} days; early warning needs a revisit of ~6-12 days to be useful.")


# ---------------------------------------------------------------------------
# kind: insar (wide) -> points + timeseries
# ---------------------------------------------------------------------------


def parse_insar_wide(df: pd.DataFrame, ctx: ParseContext) -> tuple[pd.DataFrame, pd.DataFrame, list[ValidationReport]]:
    prep = ValidationReport("points", detected_format="wide (EGMS-style)", rows_in=len(df))
    trep = ValidationReport("timeseries", detected_format="wide (EGMS-style)")
    dcols = _date_columns(df)
    if len(dcols) < 3:
        prep.blocked_reason = (
            "Wide InSAR needs at least 3 epoch columns named as dates (YYYYMMDD or YYYY_MM_DD). "
            "Excel often turns 20250105 into 20250105.0 — that form is accepted; if none were found, "
            "re-export the headers as text or pick 'Points only' / 'Time series only'."
        )
        return pd.DataFrame(), pd.DataFrame(), [prep.finish()]
    attrs = df[[c for c in df.columns if c not in dcols]]
    points, prep = parse_points(attrs, ctx, "wide (EGMS-style)")
    if points.empty or prep.blocked_reason and prep.rows_ok == 0:
        return pd.DataFrame(), pd.DataFrame(), [prep.finish()]

    n_est = len(points) * len(dcols)
    if settings.data_backend.lower() != "bigquery" and n_est > settings.max_local_timeseries_rows:
        prep.blocked_reason = (
            f"This file expands to ~{n_est:,} time-series rows, above the local limit of "
            f"{settings.max_local_timeseries_rows:,}. Use the BigQuery backend for data this large."
        )
        return pd.DataFrame(), pd.DataFrame(), [prep.finish()]

    id_col = prep.mapped_columns["point_id"]
    keep = df.loc[df[id_col].astype(str).str.strip().isin(points["point_id"])].drop_duplicates(id_col, keep="last")
    keep = keep.set_index(keep[id_col].astype(str).str.strip())
    ordered = sorted(dcols, key=lambda c: dcols[c])
    vals = keep.loc[points["point_id"], ordered].apply(pd.to_numeric, errors="coerce")
    dates = [dcols[c] for c in ordered]

    # Rebase each series to its first valid epoch (EGMS is relative to the first acquisition).
    base = vals.bfill(axis=1).iloc[:, 0]
    rebased = vals.sub(base, axis=0)
    trep.warnings.append("Each series was rebased so its first valid epoch is 0 mm.")

    wide = rebased.copy()
    wide.columns = pd.to_datetime(dates)
    long = wide.stack().rename("disp_mm").reset_index()
    long.columns = ["point_id", "date", "disp_mm"]
    long = long[long["disp_mm"].abs() <= 5000]
    trep.rows_in = int(vals.size)
    trep.rows_ok = len(long)
    trep.rows_rejected = int(vals.size - len(long))
    trep.mapped_columns = {"point_id": id_col, "date_columns": len(dcols)}
    _ts_summary(long, trep)
    trep.preview = _preview(long)

    if not prep.summary.get("velocity_supplied"):
        x = np.array([(d - dates[0]).days for d in dates], dtype=float)
        y = rebased.to_numpy(dtype=float)
        m = ~np.isnan(y)
        n, sx = m.sum(1), (m * x).sum(1)
        sy = np.where(m, y, 0).sum(1)
        sxx, sxy = (m * x * x).sum(1), (np.where(m, y, 0) * x).sum(1)
        den = n * sxx - sx**2
        with np.errstate(divide="ignore", invalid="ignore"):
            slope = np.where(den > 0, (n * sxy - sx * sy) / den, np.nan)
        points = points.assign(velocity_mm_yr=np.round(slope * 365.25, 2))
        prep.warnings.append("No velocity column; mean LOS velocity was computed from the time series (linear fit).")
        prep.summary["velocity_supplied"] = True
    return points, long, [prep.finish(), trep.finish()]


# ---------------------------------------------------------------------------
# kind: rain
# ---------------------------------------------------------------------------


def parse_rain(df: pd.DataFrame, ctx: ParseContext, fmt: str = "csv") -> tuple[pd.DataFrame, ValidationReport]:
    rep = ValidationReport("rain", detected_format=fmt, rows_in=len(df))
    work, mapped = _canon(df, RAIN_ALIASES)
    rep.mapped_columns = mapped
    if "region_id" not in work:
        if ctx.default_region:
            work["region_id"] = ctx.default_region
            rep.warnings.append(f"No region column; every row assigned to {ctx.default_region}.")
        else:
            rep.blocked_reason = "No region_id column and no target region selected."
            return pd.DataFrame(), rep.finish()
    missing = [c for c in ("date", "precip_mm") if c not in work]
    if missing:
        rep.blocked_reason = f"Missing required column(s): {', '.join(missing)}. Accepted: date, precip_mm/precipitation."
        return pd.DataFrame(), rep.finish()

    work["date"] = pd.to_datetime(work["date"], errors="coerce")
    work["precip_mm"] = pd.to_numeric(work["precip_mm"], errors="coerce")
    work["region_id"] = work["region_id"].astype(str).str.strip()
    bad = work["date"].isna() | work["precip_mm"].isna() | (work["precip_mm"] < 0) | (work["precip_mm"] > 600)
    for idx in work.index[bad][:MAX_ERRORS]:
        rep.err(_row_no(idx), "date/precip_mm", "Unparseable date, or rainfall outside 0-600 mm/day.")
    rep.rows_rejected = int(bad.sum())
    work = work[~bad].drop_duplicates(["region_id", "date"], keep="last")[["region_id", "date", "precip_mm"]].reset_index(drop=True)
    rep.rows_ok = len(work)
    known = {r["region_id"] for r in ctx.regions}
    unknown = sorted(set(work["region_id"]) - known) if known else []
    if unknown:
        rep.warnings.append(f"Unknown region(s) {', '.join(unknown[:5])}: rainfall for them will not be used until the region exists.")
    if len(work):
        rep.summary = {
            "regions": int(work["region_id"].nunique()),
            "date_min": str(work["date"].min().date()),
            "date_max": str(work["date"].max().date()),
            "total_mm": round(float(work["precip_mm"].sum()), 1),
        }
    rep.preview = _preview(work)
    return work, rep.finish()


# ---------------------------------------------------------------------------
# kind: assets (GeoJSON)
# ---------------------------------------------------------------------------


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").upper()[:40] or "ASSET"


def _prop(props: dict, names: list[str]):
    low = {_norm(k): v for k, v in props.items()}
    for n in names:
        if n in low and low[n] not in (None, ""):
            return low[n]
    return None


def parse_assets(obj, ctx: ParseContext) -> tuple[list[dict], ValidationReport]:
    rep = ValidationReport("assets", detected_format="GeoJSON")
    if isinstance(obj, dict) and obj.get("type") == "Feature":
        feats = [obj]
    elif isinstance(obj, dict) and obj.get("type") == "FeatureCollection":
        feats = obj.get("features") or []
    elif isinstance(obj, list):
        feats = obj
    else:
        rep.blocked_reason = "Not a GeoJSON FeatureCollection."
        return [], rep.finish()
    rep.rows_in = len(feats)
    out: list[dict] = []
    seen: set[str] = set()
    defaulted_crit = 0

    for i, f in enumerate(feats):
        row = i + 1
        try:
            geom = shape(f["geometry"])
        except Exception:  # noqa: BLE001
            rep.err(row, "geometry", "Missing or invalid geometry.")
            continue
        if isinstance(geom, MultiLineString):
            merged = linemerge(geom)
            if isinstance(merged, MultiLineString):
                merged = max(merged.geoms, key=lambda g: g.length)
                rep.warnings.append(f"Feature {row}: disconnected parts; kept the longest segment.")
            geom = merged
        if not isinstance(geom, LineString):
            rep.err(row, "geometry", f"Expected LineString or MultiLineString, got {geom.geom_type}. Assets are linear (road, rail, tunnel, embankment crest).")
            continue
        coords = [[round(c[0], 6), round(c[1], 6)] for c in geom.coords]
        if len(coords) < 2 or any(not (-180 <= x <= 180 and -90 <= y <= 90) for x, y in coords):
            rep.err(row, "geometry", "Needs 2+ points and longitude/latitude (WGS84) coordinates.")
            continue
        length_km = _line_km(coords)
        if length_km < 0.05:
            rep.err(row, "geometry", "Asset is shorter than 50 m.")
            continue

        props = f.get("properties") or {}
        name = _prop(props, ["name", "title", "label"])
        aid = _prop(props, ["asset_id", "id", "ref", "code"])
        if not aid:
            if not name:
                rep.err(row, "asset_id", "Needs asset_id (or a name to derive one from).")
                continue
            aid = _slug(str(name))
        aid = str(aid).strip()
        if aid in seen:
            rep.err(row, "asset_id", f"Duplicate asset_id {aid} in this file.")
            continue
        seen.add(aid)
        raw_type = _prop(props, ["asset_type", "type", "kind", "class", "highway", "railway", "category"])
        atype = _ALIAS_TO_TYPE.get(_norm(raw_type or ""))
        if atype is None and raw_type:
            atype = next((t for a, t in _ALIAS_TO_TYPE.items() if _norm(raw_type).startswith(a)), None)
        if atype is None:
            rep.err(row, "asset_type", f"Unknown asset type {raw_type!r}. Use one of: {', '.join(ASSET_TYPES)}.")
            continue

        crit = _prop(props, ["criticality", "importance"])
        try:
            crit_v = float(crit) if crit is not None else None
        except (TypeError, ValueError):
            crit_v = None
        if crit_v is None:
            crit_v = DEFAULT_CRITICALITY
            defaulted_crit += 1
        crit_v = min(1.0, max(0.0, crit_v))

        region = _prop(props, ["region_id", "region"]) or ctx.default_region
        if not region and ctx.regions:
            c = geom.centroid
            rid, dist = nearest_region(c.x, c.y, ctx.regions)
            if rid is None and dist is not None:
                rep.warnings.append(
                    f"Feature {row}: nearest region centre is {dist:.0f} km away "
                    f"(limit {MAX_NEAREST_REGION_KM:.0f} km); left UNASSIGNED. Set region_id or a default region."
                )
            region = rid
        region = region or "UNASSIGNED"

        out.append(
            {
                "type": "Feature",
                "properties": {
                    "asset_id": aid,
                    "name": clean_text(name or aid, 120) or aid,
                    "asset_type": atype,
                    "region_id": str(region),
                    "criticality": round(crit_v, 2),
                    "consequence_note": clean_text(_prop(props, ["consequence_note", "consequence", "description"]) or "", 400),
                    "length_km": round(length_km, 2),
                    "source": ctx.source_label,
                },
                "geometry": mapping(LineString(coords)),
            }
        )

    rep.rows_ok = len(out)
    rep.rows_rejected = rep.rows_in - len(out)
    if defaulted_crit:
        rep.warnings.append(f"{defaulted_crit} asset(s) had no criticality; assumed {DEFAULT_CRITICALITY}. Set it (0-1) so ranking reflects consequence.")
    known = {r["region_id"] for r in ctx.regions}
    missing_regions = sorted({a["properties"]["region_id"] for a in out} - known) if known else []
    if missing_regions:
        rep.warnings.append(f"Region(s) not defined yet: {', '.join(missing_regions[:5])}. Add them under Regions so they appear in the selector.")
    if out:
        rep.summary = {
            "assets": len(out),
            "total_km": round(sum(a["properties"]["length_km"] for a in out), 2),
            "types": {t: sum(1 for a in out if a["properties"]["asset_type"] == t) for t in ASSET_TYPES if any(a["properties"]["asset_type"] == t for a in out)},
        }
    rep.preview = [a["properties"] for a in out[:5]]
    return out, rep.finish()


# ---------------------------------------------------------------------------
# kind: regions
# ---------------------------------------------------------------------------


def parse_regions(obj, ctx: ParseContext, fmt: str = "JSON") -> tuple[list[dict], ValidationReport]:
    rep = ValidationReport("regions", detected_format=fmt)
    if isinstance(obj, dict):
        obj = obj.get("regions", [obj])
    if isinstance(obj, pd.DataFrame):
        df, rep.mapped_columns = _canon(obj, REGION_ALIASES)
        rows = json.loads(df.to_json(orient="records"))
    else:
        rows = [
            {k: v for k, v in (
                ("region_id", _prop(r, REGION_ALIASES["region_id"])),
                ("parent_id", _prop(r, REGION_ALIASES["parent_id"])),
                ("name", _prop(r, REGION_ALIASES["name"])),
                ("level", _prop(r, REGION_ALIASES["level"])),
                ("center_lon", r["center"][0] if isinstance(r.get("center"), (list, tuple)) and len(r["center"]) == 2 else _prop(r, REGION_ALIASES["center_lon"])),
                ("center_lat", r["center"][1] if isinstance(r.get("center"), (list, tuple)) and len(r["center"]) == 2 else _prop(r, REGION_ALIASES["center_lat"])),
                ("zoom", _prop(r, REGION_ALIASES["zoom"])),
            )}
            for r in obj
            if isinstance(r, dict)
        ]
    rep.rows_in = len(rows)
    existing = {r["region_id"]: r for r in ctx.regions}
    out: list[dict] = []
    for i, r in enumerate(rows):
        row = i + 1
        rid = str(r.get("region_id") or "").strip()
        if not _REGION_ID.match(rid):
            rep.err(row, "region_id", "Required; letters, digits, '-' or '_' only (max 64).")
            continue
        try:
            lon, lat = float(r["center_lon"]), float(r["center_lat"])
        except (KeyError, TypeError, ValueError):
            rep.err(row, "center", "Needs center_lon and center_lat.")
            continue
        if not (-180 <= lon <= 180 and -90 <= lat <= 90):
            rep.err(row, "center", "Longitude/latitude out of range.")
            continue
        level = clean_text(r.get("level") or "district", 20).lower() or "district"
        parent = r.get("parent_id")
        parent = None if parent in (None, "", "null") or (isinstance(parent, float) and math.isnan(parent)) else str(parent).strip()
        try:
            zoom = float(r.get("zoom")) if r.get("zoom") not in (None, "") and not (isinstance(r.get("zoom"), float) and math.isnan(r["zoom"])) else DEFAULT_ZOOM.get(level, 10.0)
        except (TypeError, ValueError):
            zoom = DEFAULT_ZOOM.get(level, 10.0)
        out.append({"region_id": rid, "parent_id": parent, "name": clean_text(r.get("name") or rid, 80) or rid, "level": level, "center": [round(lon, 5), round(lat, 5)], "zoom": zoom})

    combined = {**existing, **{r["region_id"]: r for r in out}}
    valid: list[dict] = []
    for r in out:
        p = r["parent_id"]
        if p is not None and p not in combined:
            rep.err(r["region_id"], "parent_id", f"Parent region {p!r} does not exist (add it in the same file or first).")
            continue
        if p == r["region_id"]:
            rep.err(r["region_id"], "parent_id", "A region cannot be its own parent.")
            continue
        cur, hops, cyc = p, 0, False
        while cur is not None and hops < 20:
            cur = combined.get(cur, {}).get("parent_id")
            hops += 1
            cyc = cyc or cur == r["region_id"]
        if cyc:
            rep.err(r["region_id"], "parent_id", "Parent chain forms a cycle.")
            continue
        valid.append(r)
    rep.rows_ok = len(valid)
    rep.rows_rejected = rep.rows_in - len(valid)
    rep.summary = {"regions": len(valid), "levels": sorted({r["level"] for r in valid})}
    rep.preview = valid[:5]
    return valid, rep.finish()


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------


def detect_kind_from_columns(df: pd.DataFrame) -> str | None:
    norm = {_norm(c) for c in df.columns}
    if len(_date_columns(df)) >= 3:
        return "insar"
    has = lambda aliases: any(a in norm for a in aliases)  # noqa: E731
    if has(TS_ALIASES["date"]) and has(TS_ALIASES["disp_mm"]) and has(POINT_ALIASES["point_id"]):
        return "timeseries"
    if has(RAIN_ALIASES["precip_mm"]):
        return "rain"
    if "region_id" in norm and ("center_lon" in norm or "center" in norm or "level" in norm) and "name" in norm:
        return "regions"
    if has(POINT_ALIASES["point_id"]) and has(POINT_ALIASES["lat"]) and has(POINT_ALIASES["lon"]):
        return "points"
    return None


def clean_text(value, limit: int = 200) -> str:
    """Display text from untrusted input: printable characters only (no NUL/control/format codes), single-spaced, bounded."""
    text = "".join(" " if ch in "\t\r\n" else ch for ch in str(value) if ch.isprintable() or ch in "\t\r\n")
    return " ".join(text.split())[:limit]


def clean_filename(name: str | None) -> str:
    """A display-safe file name: no path, no control characters, bounded length (it is stored as provenance)."""
    base = re.split(r"[\\/]", name or "upload")[-1]
    base = "".join(ch for ch in base if ch.isprintable() and ch not in "<>\"\x27`")
    return (base.strip() or "upload")[:120]


def parse_upload(filename: str, content: bytes, kind: str | None, ctx: ParseContext | None = None) -> ParseResult:
    """Parse one file. ``kind`` of None means auto-detect."""
    filename = clean_filename(filename)
    ctx = ctx or ParseContext(filename=filename)
    ctx.filename = filename
    if len(content) > settings.max_upload_mb * 1024 * 1024:
        raise IngestError(f"File is larger than the {settings.max_upload_mb} MB upload limit.")
    if not content.strip():
        raise IngestError("The file is empty.")
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext in {"xlsx", "xls", "zip", "gz", "shp", "kml", "tif", "tiff", "nc", "h5"}:
        raise IngestError(f".{ext} is not supported. Export to CSV (tabular data) or GeoJSON (assets).")

    is_json = ext in {"json", "geojson"} or content.lstrip()[:1] in (b"{", b"[")
    if is_json:
        try:
            obj = json.loads(content.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise IngestError(f"Invalid JSON: {exc}") from exc
        except (RecursionError, MemoryError) as exc:  # hostile or broken nesting must be a 400, never a crash
            raise IngestError("The JSON is nested too deeply to read.") from exc
        if kind is None:
            if isinstance(obj, dict) and obj.get("type") in ("FeatureCollection", "Feature"):
                kind = "assets"
            elif isinstance(obj, (list, dict)):
                kind = "regions"
        if kind == "assets":
            feats, rep = parse_assets(obj, ctx)
            return ParseResult([rep], {"assets": feats} if rep.ok else {})
        if kind == "regions":
            regs, rep = parse_regions(obj, ctx)
            return ParseResult([rep], {"regions": regs} if rep.ok else {})
        raise IngestError(f"JSON files can hold assets (GeoJSON) or regions, not {kind!r}.")

    df = _read_csv(content)
    kind = kind or detect_kind_from_columns(df)
    if kind is None:
        raise IngestError(
            "Could not tell what this file contains. Columns found: "
            + ", ".join(map(str, df.columns[:12]))
            + ". Pick the data type explicitly, or download a template."
        )
    if kind == "insar":
        if len(_date_columns(df)) < 3:
            raise IngestError(
                "This file was marked as a wide InSAR product but no epoch date columns were found "
                "(expected headers like 20250105 or 2025_01_05). Re-export without Excel rewriting the dates, "
                "or pick Points / Time series separately."
            )
        pts, ts, reps = parse_insar_wide(df, ctx)
        payloads = {"points": pts, "timeseries": ts} if all(r.ok for r in reps) else {}
        return ParseResult(reps, payloads)
    if kind == "points":
        pts, rep = parse_points(df, ctx)
        return ParseResult([rep], {"points": pts} if rep.ok else {})
    if kind == "timeseries":
        ts, rep = parse_timeseries(df, ctx)
        return ParseResult([rep], {"timeseries": ts} if rep.ok else {})
    if kind == "rain":
        rn, rep = parse_rain(df, ctx)
        return ParseResult([rep], {"rain": rn} if rep.ok else {})
    if kind == "regions":
        regs, rep = parse_regions(df, ctx, "CSV")
        return ParseResult([rep], {"regions": regs} if rep.ok else {})
    raise IngestError(f"CSV files cannot hold {kind!r} data. Use GeoJSON for assets.")


# ---------------------------------------------------------------------------
# downloadable templates
# ---------------------------------------------------------------------------

TEMPLATES = {
    "insar": (
        "pid,latitude,longitude,mean_velocity,temporal_coherence,20250105,20250117,20250129,20250210,20250222,20250306,20250318,20250330\n"
        "EG0001,13.0841,80.2750,-4.2,0.82,0,-0.4,-0.9,-1.3,-1.8,-2.1,-2.7,-3.0\n"
        "EG0002,13.0852,80.2761,-0.3,0.91,0,0.1,-0.1,0.0,-0.2,0.1,-0.1,-0.2\n",
        "insar_wide_template.csv",
    ),
    "points": (
        "point_id,lat,lon,velocity_mm_yr,coherence,region_id\nP1,13.0841,80.2750,-4.2,0.82,IN-TN-CHN\nP2,13.0852,80.2761,-0.3,0.91,IN-TN-CHN\n",
        "points_template.csv",
    ),
    "timeseries": (
        "point_id,date,disp_mm\nP1,2025-01-05,0\nP1,2025-01-17,-0.4\nP1,2025-01-29,-0.9\nP2,2025-01-05,0\nP2,2025-01-17,0.1\n",
        "timeseries_template.csv",
    ),
    "rain": (
        "region_id,date,precip_mm\nIN-TN-CHN,2026-10-01,0.0\nIN-TN-CHN,2026-10-02,12.4\nIN-TN-CHN,2026-10-03,31.0\n",
        "rain_template.csv",
    ),
    "regions": (
        "region_id,parent_id,name,level,center_lon,center_lat,zoom\nIN-KA,IN,Karnataka,state,76.6,14.6,7.5\nIN-KA-BLR,IN-KA,Bengaluru,district,77.59,12.97,11.5\n",
        "regions_template.csv",
    ),
    "assets": (
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {
                            "asset_id": "NH-EXAMPLE",
                            "name": "Example highway segment",
                            "asset_type": "HIGHWAY",
                            "region_id": "IN-UK-CHM",
                            "criticality": 0.8,
                            "consequence_note": "Sole access road; high daily traffic.",
                        },
                        "geometry": {"type": "LineString", "coordinates": [[79.535, 30.535], [79.56, 30.545], [79.575, 30.565]]},
                    }
                ],
            },
            indent=1,
        ),
        "assets_template.geojson",
    ),
}
