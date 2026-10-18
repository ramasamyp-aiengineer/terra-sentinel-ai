"""Data Hub API: upload, validate, fetch by link, fetch rainfall by region, export, reset, BigQuery sync."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from pydantic import BaseModel, Field

from app.api.deps import require_role
from app.core.config import settings
from app.core.ratelimit import limit
from app.services.data import ingest, public_service, service
from app.services.data.service import DataError

router = APIRouter(prefix="/api/data", tags=["data"])
Kind = Literal["points", "timeseries", "rain", "assets", "regions", "insar"]


def _kind(kind: str | None) -> str | None:
    if kind in (None, "", "auto"):
        return None
    if kind not in ("points", "timeseries", "rain", "assets", "regions", "insar"):
        raise HTTPException(422, f"Unknown data kind {kind!r}.")
    return kind


async def _read(file: UploadFile) -> bytes:
    limit_b = settings.max_upload_mb * 1024 * 1024
    buf = bytearray()
    while chunk := await file.read(1024 * 1024):
        buf.extend(chunk)
        if len(buf) > limit_b:
            raise HTTPException(413, f"File is larger than the {settings.max_upload_mb} MB limit.")
    if not buf:
        raise HTTPException(400, "The uploaded file is empty.")
    return bytes(buf)


def _wrap(fn, *a, **kw):
    try:
        out = fn(*a, **kw)
        if fn in _MUTATING and settings.warm_on_change:
            from app.services.intel import snapshots

            snapshots.warm_in_background()
        return out
    except DataError as exc:
        raise HTTPException(400, str(exc))
    except ingest.IngestError as exc:
        raise HTTPException(400, str(exc))


_MUTATING = {service.ingest_file, service.ingest_url, service.fetch_region_rain, service.add_region, service.reset_to_demo, service.sync_to_bigquery}


@router.get("/status")
def status():
    return service.status()


@router.post("/validate", dependencies=[Depends(limit(30, 60)), Depends(require_role("admin"))])
async def validate(
    file: UploadFile = File(...),
    kind: str | None = Form(None),
    default_region: str | None = Form(None),
):
    content = await _read(file)
    return _wrap(service.validate, file.filename or "upload", content, _kind(kind), default_region)


@router.post("/upload", dependencies=[Depends(limit(20, 60)), Depends(require_role("admin"))])
async def upload(
    file: UploadFile = File(...),
    kind: str | None = Form(None),
    mode: str = Form("merge"),
    default_region: str | None = Form(None),
):
    content = await _read(file)
    return _wrap(service.ingest_file, file.filename or "upload", content, _kind(kind), mode, default_region)


class FetchUrlBody(BaseModel):
    url: str = Field(min_length=8, max_length=2000)
    kind: str | None = None
    mode: Literal["merge", "replace"] = "merge"
    default_region: str | None = None
    dry_run: bool = False


@router.post("/fetch-url", dependencies=[Depends(limit(10, 60)), Depends(require_role("admin"))])
def fetch_url(body: FetchUrlBody):
    if body.dry_run:
        from app.services.data import connectors

        try:
            filename, content = connectors.fetch_url(body.url)
        except connectors.FetchError as exc:
            raise HTTPException(400, str(exc))
        out = _wrap(service.validate, filename, content, _kind(body.kind), body.default_region)
        out["fetched_as"] = filename
        out["bytes"] = len(content)
        return out
    return _wrap(service.ingest_url, body.url, _kind(body.kind), body.mode, body.default_region)


class FetchRainBody(BaseModel):
    region_id: str
    days: int = Field(60, ge=7, le=92)


@router.post("/fetch-rain", dependencies=[Depends(limit(10, 60)), Depends(require_role("admin"))])
def fetch_rain(body: FetchRainBody):
    return _wrap(service.fetch_region_rain, body.region_id, body.days)


class RegionBody(BaseModel):
    region_id: str | None = Field(None, max_length=40)
    name: str = Field(min_length=2, max_length=80)
    parent_id: str | None = None
    level: str = Field("district", max_length=20)
    center_lon: float = Field(ge=-180, le=180)
    center_lat: float = Field(ge=-90, le=90)
    zoom: float = Field(9, ge=1, le=18)


@router.post("/regions", dependencies=[Depends(limit(20, 60)), Depends(require_role("admin"))])
def add_region(body: RegionBody):
    return _wrap(service.add_region, body.model_dump())


@router.get("/templates/{kind}")
def template(kind: str):
    if kind not in ingest.TEMPLATES:
        raise HTTPException(404, "Unknown template")
    content, filename = ingest.TEMPLATES[kind]
    media = "application/geo+json" if filename.endswith("geojson") else "text/csv"
    return Response(content, media_type=media, headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/export/{kind}", dependencies=[Depends(require_role("analyst"))])
def export(kind: str):
    filename, media, data = _wrap(service.export, kind)
    return Response(data, media_type=media, headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.post("/reset-demo", dependencies=[Depends(limit(5, 60)), Depends(require_role("admin"))])
def reset_demo():
    return _wrap(service.reset_to_demo)


# ---- public data store (open datasets kept as CSV) --------------------------------------------------------


@router.get("/public")
def public_catalog():
    return public_service.catalog()


@router.get("/public/{dataset_id}/preview")
def public_preview(dataset_id: str):
    return _wrap(public_service.preview, dataset_id)


@router.post("/public/{dataset_id}/fetch", dependencies=[Depends(limit(6, 60)), Depends(require_role("admin"))])
def public_fetch(dataset_id: str):
    return _wrap(public_service.fetch, dataset_id)


class SeismicityBody(BaseModel):
    region_id: str = Field(max_length=60)
    radius_km: float = Field(300, ge=10, le=1000)
    days: int = Field(365, ge=7, le=3650)
    min_mag: float = Field(2.5, ge=0, le=9)


@router.post("/public/seismicity", dependencies=[Depends(limit(6, 60)), Depends(require_role("admin"))])
def public_seismicity(body: SeismicityBody):
    return _wrap(public_service.fetch_seismicity, body.region_id, body.radius_km, body.days, body.min_mag)


@router.delete("/public/{dataset_id}", dependencies=[Depends(limit(10, 60)), Depends(require_role("admin"))])
def public_delete(dataset_id: str):
    return _wrap(public_service.remove, dataset_id)


@router.get("/bigquery/doctor", dependencies=[Depends(limit(6, 60)), Depends(require_role("admin"))])
def bigquery_doctor():
    """Step-by-step connection checks (credentials, API, dataset, tables, permissions) with the exact fix for each."""
    from app.services.bq import doctor

    return doctor.summarise(doctor.run_checks())


@router.post("/sync-bigquery", dependencies=[Depends(limit(3, 60)), Depends(require_role("admin"))])
def sync_bigquery():
    return _wrap(service.sync_to_bigquery)
