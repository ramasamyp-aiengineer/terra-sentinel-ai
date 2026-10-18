"""Public data store: fetch open datasets, keep them as CSV, remember where they came from.

Everything here is a *cache of someone else's data*: it can be deleted and re-fetched at any time, and it is
never mixed into the InSAR workspace. Downloads go through ``connectors.fetch_url`` so they get the same
SSRF protection, size cap and timeouts as a user-supplied link.

Current sources (all keyless, all verified reachable when this was written):
  * USGS Earthquake Hazards Program - global feeds and the FDSN event service (public domain).
"""
from __future__ import annotations

import hashlib
import io
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode

import pandas as pd

from app.core.config import settings
from app.services.data import connectors
from app.services.data.connectors import FetchError

USGS_FEED = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary"
USGS_QUERY = "https://earthquake.usgs.gov/fdsnws/event/1/query"
USGS_LICENSE = "Public domain (US Government work). Please credit the USGS."
USGS_CITE = "U.S. Geological Survey, Earthquake Hazards Program (earthquake.usgs.gov)"

EVENT_COLS = ["id", "time", "latitude", "longitude", "depth_km", "mag", "place"]
MAX_EVENTS = 20_000  # the USGS service refuses larger answers anyway
_SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9-]{1,60}$")


class PublicDataError(ValueError):
    """A problem the user can understand (unknown dataset, upstream down, nothing returned)."""


@dataclass(frozen=True)
class CatalogEntry:
    id: str
    title: str
    publisher: str
    license: str
    description: str
    scope: str  # "global" | "region"
    refresh_days: int  # older than this is shown as stale
    url: str = ""

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in ("id", "title", "publisher", "license", "description", "scope", "refresh_days", "url")}


CATALOG: list[CatalogEntry] = [
    CatalogEntry(
        id="usgs-quakes-30d",
        title="Earthquakes M2.5+, last 30 days (global)",
        publisher="USGS Earthquake Hazards Program",
        license=USGS_LICENSE,
        description="Every magnitude 2.5+ event worldwide in the past month. Good for 'did anything shake this site recently?'.",
        scope="global",
        refresh_days=2,
        url=f"{USGS_FEED}/2.5_month.csv",
    ),
    CatalogEntry(
        id="usgs-quakes-m5-5y",
        title="Earthquakes M5.0+, last 5 years (global)",
        publisher="USGS Earthquake Hazards Program",
        license=USGS_LICENSE,
        description="Larger events worldwide over five years: the seismic history around each site.",
        scope="global",
        refresh_days=30,
        url=USGS_QUERY,  # built per request: the window moves every day
    ),
]
_BY_ID = {e.id: e for e in CATALOG}


# ---- storage -----------------------------------------------------------------------------------------


def _dir() -> Path:
    p = Path(settings.public_dir)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _csv_path(dataset_id: str) -> Path:
    if not _SAFE_ID.match(dataset_id):
        raise PublicDataError("Unknown dataset.")
    return _dir() / f"{dataset_id}.csv"


def _meta_path(dataset_id: str) -> Path:
    return _csv_path(dataset_id).with_suffix(".meta.json")


def _atomic_write(path: Path, data: bytes) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)


def stored_meta(dataset_id: str) -> dict | None:
    p = _meta_path(dataset_id)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def stored_ids() -> list[str]:
    return sorted(p.name[: -len(".meta.json")] for p in _dir().glob("*.meta.json") if _SAFE_ID.match(p.name[: -len(".meta.json")]))


def read_events(dataset_id: str) -> pd.DataFrame:
    p = _csv_path(dataset_id)
    if not p.exists():
        return pd.DataFrame(columns=EVENT_COLS)
    df = pd.read_csv(p, dtype={"id": str})
    df["time"] = pd.to_datetime(df["time"], utc=True, errors="coerce")
    return df.dropna(subset=["time", "latitude", "longitude", "mag"])


def delete(dataset_id: str) -> bool:
    gone = False
    for p in (_csv_path(dataset_id), _meta_path(dataset_id)):
        if p.exists():
            p.unlink()
            gone = True
    return gone


# ---- parsing ---------------------------------------------------------------------------------------------


def normalise_usgs(content: bytes) -> pd.DataFrame:
    """USGS CSV -> id,time,latitude,longitude,depth_km,mag,place; earthquakes only, valid coordinates only."""
    try:
        raw = pd.read_csv(io.BytesIO(content), low_memory=False)
    except Exception as exc:  # noqa: BLE001
        raise PublicDataError(f"The service did not return a readable CSV ({exc.__class__.__name__}).") from exc
    need = {"time", "latitude", "longitude", "mag"}
    if not need <= set(raw.columns):
        raise PublicDataError("The file does not look like a USGS event list (missing time, latitude, longitude or mag).")
    if "type" in raw:  # feeds also list quarry blasts, explosions, ice quakes...
        raw = raw[raw["type"].astype(str).str.lower() == "earthquake"]
    df = pd.DataFrame(
        {
            "id": raw["id"].astype(str) if "id" in raw else raw.index.astype(str),
            "time": pd.to_datetime(raw["time"], utc=True, errors="coerce"),
            "latitude": pd.to_numeric(raw["latitude"], errors="coerce"),
            "longitude": pd.to_numeric(raw["longitude"], errors="coerce"),
            "depth_km": pd.to_numeric(raw["depth"], errors="coerce") if "depth" in raw else float("nan"),
            "mag": pd.to_numeric(raw["mag"], errors="coerce"),
            "place": raw["place"].astype(str).str.slice(0, 120) if "place" in raw else "",
        }
    )
    df = df.dropna(subset=["time", "latitude", "longitude", "mag"])
    df = df[df["latitude"].between(-90, 90) & df["longitude"].between(-180, 180)]
    df = df.drop_duplicates("id").sort_values("time", ascending=False).reset_index(drop=True)
    if len(df) > MAX_EVENTS:
        df = df.head(MAX_EVENTS)
    return df


# ---- fetching --------------------------------------------------------------------------------------------


def _source_url(entry: CatalogEntry, today: datetime) -> str:
    if entry.id == "usgs-quakes-m5-5y":
        q = {
            "format": "csv", "orderby": "time", "limit": MAX_EVENTS, "minmagnitude": 5,
            "starttime": (today - timedelta(days=5 * 365)).strftime("%Y-%m-%d"), "endtime": today.strftime("%Y-%m-%d"),
        }
        return f"{USGS_QUERY}?{urlencode(q)}"
    return entry.url


def _store(dataset_id: str, title: str, df: pd.DataFrame, url: str, license_: str, publisher: str, fetched: datetime) -> dict:
    if df.empty:
        raise PublicDataError("The service returned no events for that request.")
    buf = df.to_csv(index=False, date_format="%Y-%m-%dT%H:%M:%SZ").encode("utf-8")
    _atomic_write(_csv_path(dataset_id), buf)
    meta = {
        "id": dataset_id,
        "title": title,
        "publisher": publisher,
        "license": license_,
        "source_url": url,
        "fetched_at": fetched.isoformat(timespec="seconds"),
        "rows": int(len(df)),
        "date_min": str(df["time"].min().date()),
        "date_max": str(df["time"].max().date()),
        "bytes": len(buf),
        "sha256": hashlib.sha256(buf).hexdigest()[:16],
        "max_magnitude": round(float(df["mag"].max()), 1),
        "citation": USGS_CITE,
    }
    _atomic_write(_meta_path(dataset_id), json.dumps(meta, indent=1).encode("utf-8"))
    return meta


def _download(url: str) -> bytes:
    try:
        _, content = connectors.fetch_url(url)
    except FetchError as exc:
        raise PublicDataError(f"Could not download from USGS: {exc}") from exc
    return content


def fetch_catalog_entry(dataset_id: str, now: datetime | None = None) -> dict:
    entry = _BY_ID.get(dataset_id)
    if entry is None:
        raise PublicDataError("Unknown dataset. Pick one from the catalog.")
    now = now or datetime.now(timezone.utc)
    url = _source_url(entry, now)
    df = normalise_usgs(_download(url))
    return _store(entry.id, entry.title, df, url, entry.license, entry.publisher, now)


def fetch_region_seismicity(
    region_id: str, lat: float, lon: float, radius_km: float = 300, days: int = 365, min_mag: float = 2.5, now: datetime | None = None
) -> dict:
    """Earthquakes within ``radius_km`` of a region centre (USGS FDSN). Stored as ``usgs-quakes-<region>``."""
    if not (10 <= radius_km <= 1000):
        raise PublicDataError("Radius must be between 10 and 1000 km.")
    if not (7 <= days <= 3650):
        raise PublicDataError("Look-back must be between 7 days and 10 years.")
    if not (0 <= min_mag <= 9):
        raise PublicDataError("Minimum magnitude must be between 0 and 9.")
    slug = re.sub(r"[^a-z0-9]+", "-", region_id.lower()).strip("-")[:40] or "region"
    dataset_id = f"usgs-quakes-{slug}"
    now = now or datetime.now(timezone.utc)
    q = {
        "format": "csv", "orderby": "time", "limit": MAX_EVENTS, "latitude": f"{lat:.4f}", "longitude": f"{lon:.4f}",
        "maxradiuskm": f"{radius_km:.0f}", "minmagnitude": f"{min_mag:g}",
        "starttime": (now - timedelta(days=days)).strftime("%Y-%m-%d"), "endtime": now.strftime("%Y-%m-%d"),
    }
    url = f"{USGS_QUERY}?{urlencode(q)}"
    df = normalise_usgs(_download(url))
    title = f"Earthquakes M{min_mag:g}+ within {radius_km:.0f} km of {region_id}, last {days} days"
    return _store(dataset_id, title, df, url, USGS_LICENSE, "USGS Earthquake Hazards Program", now)


# ---- listing ---------------------------------------------------------------------------------------------


def _with_status(entry: dict, now: datetime) -> dict:
    meta = stored_meta(entry["id"])
    if meta:
        age = (now - datetime.fromisoformat(meta["fetched_at"])).total_seconds() / 86400
        meta = {**meta, "age_days": round(age, 1), "stale": age > entry.get("refresh_days", 30)}
    return {**entry, "stored": meta}


def listing(now: datetime | None = None) -> list[dict]:
    """Catalog entries plus anything fetched for a region, each with its stored-copy status."""
    now = now or datetime.now(timezone.utc)
    out = [_with_status(e.to_dict(), now) for e in CATALOG]
    known = {e.id for e in CATALOG}
    for sid in stored_ids():
        if sid in known:
            continue
        meta = stored_meta(sid) or {}
        out.append(
            _with_status(
                {
                    "id": sid, "title": meta.get("title", sid), "publisher": meta.get("publisher", ""),
                    "license": meta.get("license", ""), "description": "Fetched for one region.", "scope": "region",
                    "refresh_days": 7, "url": meta.get("source_url", ""),
                },
                now,
            )
        )
    return out


def preview(dataset_id: str, n: int = 12) -> dict:
    meta = stored_meta(dataset_id)
    if meta is None:
        raise PublicDataError("That dataset has not been fetched yet.")
    df = read_events(dataset_id)
    top = df.sort_values("mag", ascending=False).head(n)
    rows = [
        {"time": r.time.strftime("%Y-%m-%d %H:%M"), "mag": round(float(r.mag), 1), "place": r.place,
         "latitude": round(float(r.latitude), 3), "longitude": round(float(r.longitude), 3)}
        for r in top.itertuples()
    ]
    by_band = {
        "M2.5-3.9": int(((df["mag"] >= 2.5) & (df["mag"] < 4)).sum()),
        "M4.0-4.9": int(((df["mag"] >= 4) & (df["mag"] < 5)).sum()),
        "M5.0+": int((df["mag"] >= 5).sum()),
    }
    return {"meta": meta, "largest": rows, "by_magnitude": by_band}
