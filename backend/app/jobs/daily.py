"""Daily job (Cloud Run Job / Cloud Scheduler / cron friendly).

    python -m app.jobs.daily [--fetch-rain] [--region ID ...]

  1. optionally refresh rainfall for each region from Open-Meteo (a failed region is logged, never fatal)
  2. rebuild the analysis
  3. save today's ranked-site snapshot (BigQuery table in bigquery mode, JSON locally)
  4. print a one-line JSON summary (and exit non-zero only if the analysis itself failed)

Idempotent: re-running on the same day overwrites that day's snapshot.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys

log = logging.getLogger("terrasentinel.daily")


def run(fetch_rain: bool = False, regions: list[str] | None = None) -> dict:
    from app.services import runtime
    from app.services.data import service
    from app.services.data.repo import get_repo
    from app.services.data.state import get_state
    from app.services.intel import alerts, snapshots

    rain: dict[str, str] = {}
    if fetch_rain:
        repo = get_repo()
        targets = regions or [r["region_id"] for r in repo.regions() if not any(c["parent_id"] == r["region_id"] for c in repo.regions())]
        for rid in targets:
            try:
                res = service.fetch_region_rain(rid, days=30)
                rain[rid] = f"ok {res['rows']} rows"
            except Exception as exc:  # noqa: BLE001 - one region failing must not stop the job
                log.warning("rain fetch failed for %s: %s", rid, exc)
                rain[rid] = f"failed: {exc}"
    runtime.refresh_all()

    ps = snapshots.passes()
    if not ps:
        raise RuntimeError("Not enough satellite epochs to run an assessment.")
    today = snapshots.table_for(ps[0])
    saved = get_state().save_snapshot(ps[0].as_of, list(today.values()))
    counts = {t: sum(1 for r in today.values() if r["tier"] == t) for t in ("CRITICAL", "ELEVATED", "WATCH", "STABLE", "WEAK")}
    return {
        "as_of": ps[0].as_of,
        "snapshot_rows": saved,
        "tiers": counts,
        "open_alerts": alerts.counts()["open"],
        "rain": rain,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fetch-rain", action="store_true")
    ap.add_argument("--region", action="append", dest="regions")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        print(json.dumps(run(args.fetch_rain, args.regions)))
        return 0
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
