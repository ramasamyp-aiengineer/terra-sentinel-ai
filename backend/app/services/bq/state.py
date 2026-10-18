"""BigQuery implementation of the operational state store (datasets, alert actions, daily snapshots)."""
from __future__ import annotations

import json

import pandas as pd

from app.services.bq import loader, sql
from app.services.bq.client import Runner, get_runner
from app.services.bq.schema import TABLES


def _ts(v) -> str:
    return pd.Timestamp(v).isoformat(timespec="seconds")


class BigQueryState:
    def __init__(self, runner: Runner | None = None):
        self._runner = runner

    @property
    def runner(self) -> Runner:
        return self._runner or get_runner()

    def _q(self, name: str) -> pd.DataFrame:
        return self.runner.query_df(sql.read_queries(self.runner.project, self.runner.dataset)[name], label=f"read:{name}")

    # -- dataset registry
    def list_datasets(self) -> list[dict]:
        out = []
        for r in self._q("list_datasets").to_dict("records"):
            out.append(
                {
                    "dataset_id": r["dataset_id"],
                    "kind": r["kind"],
                    "name": r["name"],
                    "source_type": r["source_type"],
                    "source_ref": r["source_ref"],
                    "rows": int(r["rows"]),
                    "date_min": None if pd.isna(r["date_min"]) else str(pd.Timestamp(r["date_min"]).date()),
                    "date_max": None if pd.isna(r["date_max"]) else str(pd.Timestamp(r["date_max"]).date()),
                    "mode": r["mode"],
                    "notes": json.loads(r["notes"]) if r["notes"] else [],
                    "added_at": _ts(r["added_at"]),
                }
            )
        return out

    def add_dataset(self, entry: dict) -> None:
        loader.register_dataset(entry, self.runner)

    def reset_datasets(self, seed: list[dict]) -> None:
        self.runner.execute(sql.truncate_sql("datasets", self.runner.project, self.runner.dataset), label="truncate:datasets")
        for e in seed:
            self.add_dataset(e)

    # -- alert actions
    def list_actions(self) -> list[dict]:
        return [
            {
                "alert_id": r["alert_id"],
                "action": r["action"],
                "actor": r["actor"],
                "note": r["note"] or "",
                "assignee": None if pd.isna(r["assignee"]) else r["assignee"],
                "at": _ts(r["at"]),
            }
            for r in self._q("list_actions").to_dict("records")
        ]

    def add_action(self, action: dict) -> None:
        df = pd.DataFrame([{**action, "at": pd.to_datetime(action["at"], utc=True)}])
        loader.append_rows("alert_actions", df[[n for n, _ in TABLES["alert_actions"].load_columns]], self.runner)

    # -- snapshots
    def save_snapshot(self, as_of: str, rows: list[dict]) -> int:
        saved = pd.Timestamp.now(tz="UTC")
        df = pd.DataFrame(
            [
                {
                    "as_of": pd.Timestamp(as_of).date(),
                    "site_id": r["site_id"],
                    "asset_id": r["asset_id"],
                    "region_id": r["region_id"],
                    "tier": r["tier"],
                    "state": r["state"],
                    "rpi": r["rpi"],
                    "rate_mm_month": r["rate_mm_month"],
                    "eta_low_days": r.get("eta_low_days"),
                    "eta_high_days": r.get("eta_high_days"),
                    "confidence": r["confidence"],
                    "saved_at": saved,
                }
                for r in rows
            ]
        )
        df["eta_low_days"] = df["eta_low_days"].astype("Int64")
        df["eta_high_days"] = df["eta_high_days"].astype("Int64")
        loader.merge_rows("site_snapshots", df, self.runner)
        return len(rows)

    def list_snapshots(self) -> list[dict]:
        return [{"as_of": str(pd.Timestamp(r["as_of"]).date()), "saved_at": _ts(r["saved_at"]), "sites": int(r["sites"])} for r in self._q("list_snapshots").to_dict("records")]
