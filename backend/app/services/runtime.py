"""Single place that knows every in-process cache.

Any change to the underlying data (upload, fetch, reset, BigQuery sync) must call
``refresh_all()`` so rankings, charts, work orders and snapshots never show stale
numbers next to fresh data.
"""
from __future__ import annotations

import logging
import threading

log = logging.getLogger("terrasentinel.runtime")
_prefetch_thread: threading.Thread | None = None


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


def prefetch_hot_path() -> None:
    """Load live rankings into memory so Command Center is not blocked by the first BigQuery round-trip."""
    from app.services.data.repo import get_repo
    from app.services.detection.pipeline import run_pipeline

    repo = get_repo()
    # Touch every hot table once (BigQueryRepo caches the frames).
    _ = repo.regions()
    _ = repo.assets()
    _ = repo.points()
    _ = repo.timeseries()
    _ = repo.rain()
    sites = run_pipeline()
    log.info("Hot path ready: backend=%s sites=%s", repo.backend, len(sites))
    # Latest-pass alert diffs (Command Center / top bar hit this next).
    try:
        from app.services.intel import alerts

        n = len(alerts.list_alerts())
        log.info("Alert events ready: %s", n)
    except Exception:  # noqa: BLE001
        log.exception("alert prefetch failed")


def prefetch_in_background() -> None:
    """Run ``prefetch_hot_path`` then historical snapshot warm (deferred so UI wins the lock first)."""
    global _prefetch_thread
    if _prefetch_thread and _prefetch_thread.is_alive():
        return

    def _run() -> None:
        try:
            prefetch_hot_path()
        except Exception:  # noqa: BLE001
            log.exception("hot-path prefetch failed")
            return
        try:
            from app.core.config import settings
            from app.services.intel import snapshots

            if settings.warm_on_change:
                snapshots.warm(snapshots.warm_passes())
        except Exception:  # noqa: BLE001
            log.exception("snapshot warm failed")

    _prefetch_thread = threading.Thread(target=_run, daemon=True, name="ts-prefetch")
    _prefetch_thread.start()
