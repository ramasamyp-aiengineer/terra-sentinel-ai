"""Create the BigQuery dataset, tables and views; optionally load the demo data.

    python -m app.services.bq.setup --dry-run                 # print every statement, touch nothing
    python -m app.services.bq.setup                           # create dataset, tables, views
    python -m app.services.bq.setup --load-demo               # ... and load data/demo into BigQuery

Safe to re-run: every statement is CREATE ... IF NOT EXISTS / CREATE OR REPLACE VIEW.
"""
from __future__ import annotations

import argparse
import sys

from app.core.config import settings
from app.services.bq.schema import setup_statements


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", default=settings.gcp_project)
    ap.add_argument("--dataset", default=settings.bq_dataset)
    ap.add_argument("--location", default=settings.bq_location)
    ap.add_argument("--dry-run", action="store_true", help="print the SQL and exit")
    ap.add_argument("--load-demo", action="store_true", help="load data/demo (synthetic) after creating tables")
    args = ap.parse_args(argv)

    project = args.project or "YOUR_PROJECT"
    stmts = setup_statements(project, args.dataset, args.location)

    if args.dry_run:
        if not args.project:
            print(
                "Note: TS_GCP_PROJECT is empty; statements use YOUR_PROJECT as a placeholder. "
                "Set TS_GCP_PROJECT or pass --project before running without --dry-run.",
                file=sys.stderr,
            )
        print(f"-- TerraSentinel BigQuery setup for {project}.{args.dataset} ({args.location}) -- {len(stmts)} statements\n")
        for s in stmts:
            print(s + ";\n")
        return 0

    if not args.project:
        print("TS_GCP_PROJECT (or --project) is required. Use --dry-run to preview.", file=sys.stderr)
        return 2

    from app.services.bq.client import BigQueryUnavailable, BQRunner

    try:
        runner = BQRunner(args.project, args.dataset, args.location)
        for i, s in enumerate(stmts, 1):
            head = s.splitlines()[0][:90]
            print(f"[{i}/{len(stmts)}] {head}")
            runner.execute(s)
        if args.load_demo:
            from app.services.bq.loader import sync_repo
            from app.services.data.repo import LocalRepo

            print("Loading demo data (replaces table contents)...")
            res = sync_repo(LocalRepo(settings.data_dir), runner)
            for k, v in res["tables"].items():
                print(f"  {k}: {v['total']:,} rows")
    except BigQueryUnavailable as exc:
        print(f"BigQuery error: {exc}", file=sys.stderr)
        return 1
    print("Done. Set TS_DATA_BACKEND=bigquery to serve from BigQuery.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
