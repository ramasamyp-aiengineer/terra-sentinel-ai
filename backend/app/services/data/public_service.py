"""Orchestration for the public data store: fetch -> store CSV -> record provenance -> invalidate dependents.

Unlike a workspace import this does NOT recompute the detection pipeline: public context never feeds the risk
score, so only the caches that display it (seismic context, drafted work orders) are cleared.
"""
from __future__ import annotations

from app.services.data import public_catalog as pc
from app.services.data.public_catalog import PublicDataError
from app.services.data.repo import get_repo
from app.services.data.service import DataError
from app.services.data.state import get_state, now_iso
from app.services.intel import context


def _invalidate() -> None:
    from app.services.agent import service as agent_service

    context.clear_cache()
    agent_service.clear_cache()  # a drafted work order may quote seismic context that just changed


def _register(meta: dict) -> None:
    """One provenance row per public dataset: a re-fetch replaces the row instead of piling up duplicates."""
    state = get_state()
    key = f"public-{meta['id']}"
    rows = [d for d in state.list_datasets() if d.get("dataset_id") != key]
    rows.append(
        {
            "dataset_id": key,
            "kind": "events",
            "name": meta["title"],
            "source_type": "public",
            "source_ref": meta["source_url"],
            "rows": meta["rows"],
            "date_min": meta["date_min"],
            "date_max": meta["date_max"],
            "mode": "cache",
            "notes": [f"{meta['publisher']}. {meta['license']}"],
            "added_at": now_iso(),
        }
    )
    state.reset_datasets(rows)


def _run(fn, *args, **kwargs) -> dict:
    try:
        meta = fn(*args, **kwargs)
    except PublicDataError as exc:
        raise DataError(str(exc)) from exc
    _register(meta)
    _invalidate()
    return meta


def catalog() -> dict:
    return {"datasets": pc.listing(), "attribution": pc.USGS_CITE}


def fetch(dataset_id: str) -> dict:
    return _run(pc.fetch_catalog_entry, dataset_id)


def fetch_seismicity(region_id: str, radius_km: float, days: int, min_mag: float) -> dict:
    region = next((r for r in get_repo().regions() if r["region_id"] == region_id), None)
    if region is None:
        raise DataError(f"Unknown region {region_id!r}.")
    lon, lat = region["center"][0], region["center"][1]
    return _run(pc.fetch_region_seismicity, region_id, lat, lon, radius_km, days, min_mag)


def preview(dataset_id: str) -> dict:
    try:
        return pc.preview(dataset_id)
    except PublicDataError as exc:
        raise DataError(str(exc)) from exc


def remove(dataset_id: str) -> dict:
    try:
        gone = pc.delete(dataset_id)
    except PublicDataError as exc:
        raise DataError(str(exc)) from exc
    if not gone:
        raise DataError("That dataset is not stored.")
    state = get_state()
    state.reset_datasets([d for d in state.list_datasets() if d.get("dataset_id") != f"public-{dataset_id}"])
    _invalidate()
    return {"ok": True}
