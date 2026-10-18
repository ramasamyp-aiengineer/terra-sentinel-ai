"""Operational state that is not raw observation data.

  * dataset registry  - what was loaded, from where, when (provenance)
  * alert actions     - acknowledge / assign / escalate / resolve history
  * daily snapshots   - ranked-site rows saved by the daily job

Local mode keeps small JSON files under ``settings.state_dir``; BigQuery mode uses
the ``datasets``, ``alert_actions`` and ``site_snapshots`` tables (see app.services.bq).
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from app.core.config import settings

_LOCK = threading.Lock()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class LocalState:
    def __init__(self, root: Path | None = None):
        self.root = Path(root or settings.state_dir)

    def _path(self, name: str) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        return self.root / name

    def _load(self, name: str, default):
        p = self._path(name)
        if not p.exists():
            return default
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return default  # a corrupt state file must never take the API down

    def _save(self, name: str, obj) -> None:
        p = self._path(name)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(obj, indent=1), encoding="utf-8")
        tmp.replace(p)  # atomic on the same volume

    # -- dataset registry
    def list_datasets(self) -> list[dict]:
        return self._load("datasets.json", [])

    def add_dataset(self, entry: dict) -> None:
        with _LOCK:
            rows = self.list_datasets()
            rows.append(entry)
            self._save("datasets.json", rows)

    def reset_datasets(self, seed: list[dict]) -> None:
        with _LOCK:
            self._save("datasets.json", seed)

    # -- alert actions
    def list_actions(self) -> list[dict]:
        return self._load("alert_actions.json", [])

    def add_action(self, action: dict) -> None:
        with _LOCK:
            rows = self.list_actions()
            rows.append(action)
            self._save("alert_actions.json", rows)

    # -- snapshots
    def save_snapshot(self, as_of: str, rows: list[dict]) -> int:
        with _LOCK:
            snaps = self._load("snapshots.json", {})
            snaps[as_of] = {"saved_at": now_iso(), "rows": rows}
            self._save("snapshots.json", snaps)
        return len(rows)

    def list_snapshots(self) -> list[dict]:
        snaps = self._load("snapshots.json", {})
        return [{"as_of": k, "saved_at": v["saved_at"], "sites": len(v["rows"])} for k, v in sorted(snaps.items())]


@lru_cache(maxsize=1)
def get_state():
    if settings.data_backend.lower() == "bigquery":
        from app.services.bq.state import BigQueryState

        return BigQueryState()
    return LocalState()


def clear_state_cache() -> None:
    get_state.cache_clear()
