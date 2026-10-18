"""Single place that knows every in-process cache.

Any change to the underlying data (upload, fetch, reset, BigQuery sync) must call
``refresh_all()`` so rankings, charts, work orders and snapshots never show stale
numbers next to fresh data.
"""
from __future__ import annotations


def refresh_all() -> None:
    # Imports are local on purpose: this module sits below everything it clears.
    from app.services.agent import service as agent_service
    from app.services.data import repo as repo_mod
    from app.services.detection import pipeline, views
    from app.services.intel import snapshots

    repo_mod.get_repo.cache_clear()
    pipeline.clear_cache()
    views.series_for.cache_clear()
    views.point_index.cache_clear()
    snapshots.clear()
    agent_service.clear_cache()
