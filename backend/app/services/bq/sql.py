"""SQL builders: upserts (staging + MERGE) and the read queries the repository issues."""
from __future__ import annotations

from app.services.bq.schema import TABLES, Table, fq


def merge_sql(t: Table, project: str, dataset: str, staging: str) -> str:
    """MERGE a staging table into ``t`` on its key. Computed columns (GEOGRAPHY) are derived from staging."""
    target = fq(project, dataset, t.name)
    stg = f"`{project}.{dataset}.{staging}`"
    def qi(n: str) -> str:
        return f"`{n}`"

    on = " AND ".join(f"T.{qi(k)} = S.{qi(k)}" for k in t.key)
    names = [n for n, _ in t.columns]

    def src(n: str) -> str:
        return t.computed.get(n, f"S.{qi(n)}")

    non_key = [n for n in names if n not in t.key]
    update = ",\n    ".join(f"{qi(n)} = {src(n)}" for n in non_key)
    cols = ", ".join(qi(n) for n in names)
    vals = ", ".join(src(n) for n in names)
    stmt = f"MERGE {target} AS T\nUSING {stg} AS S\nON {on}\n"
    if non_key:
        stmt += f"WHEN MATCHED THEN UPDATE SET\n    {update}\n"
    stmt += f"WHEN NOT MATCHED THEN INSERT ({cols})\nVALUES ({vals})"
    return stmt


def insert_from_staging_sql(t: Table, project: str, dataset: str, staging: str) -> str:
    """Plain INSERT used after TRUNCATE (replace mode) and for append-only tables."""
    target = fq(project, dataset, t.name)
    stg = f"`{project}.{dataset}.{staging}`"
    names = [n for n, _ in t.columns]
    exprs = ", ".join(t.computed.get(n, f"S.`{n}`") for n in names)
    return f"INSERT INTO {target} ({', '.join(f'`{n}`' for n in names)})\nSELECT {exprs}\nFROM {stg} AS S"


def truncate_sql(name: str, project: str, dataset: str) -> str:
    return f"TRUNCATE TABLE {fq(project, dataset, name)}"


def delete_orphan_timeseries_sql(project: str, dataset: str) -> str:
    f = lambda n: fq(project, dataset, n)  # noqa: E731
    return f"DELETE FROM {f('timeseries')} AS ts\nWHERE NOT EXISTS (SELECT 1 FROM {f('points')} AS p WHERE p.point_id = ts.point_id)"


# ---------------------------------------------------------------------------------------- reads


def read_queries(project: str, dataset: str) -> dict[str, str]:
    f = lambda n: fq(project, dataset, n)  # noqa: E731
    return {
        "regions": f"SELECT region_id, parent_id, name, level, center_lon, center_lat, zoom FROM {f('regions')} ORDER BY region_id",
        "assets": f"SELECT asset_id, name, asset_type, region_id, criticality, consequence_note, buffer_m, geometry_json FROM {f('assets')} ORDER BY asset_id",
        # Spatial pre-filter: only scatterers inside some asset corridor are pulled into the pipeline.
        "points": f"""SELECT p.point_id, p.lat, p.lon, p.velocity_mm_yr, p.coherence, p.region_id, p.source
FROM {f('points')} AS p
WHERE p.point_id IN (SELECT point_id FROM {f('v_point_assignment')})""",
        "timeseries": f"""SELECT ts.point_id, ts.date, ts.disp_mm
FROM {f('timeseries')} AS ts
WHERE ts.point_id IN (SELECT point_id FROM {f('v_point_assignment')})
ORDER BY ts.point_id, ts.date""",
        "rain": f"SELECT region_id, date, precip_mm FROM {f('rain')} ORDER BY region_id, date",
        "counts": f"""SELECT
  (SELECT COUNT(*) FROM {f('regions')}) AS regions,
  (SELECT COUNT(*) FROM {f('assets')}) AS assets,
  (SELECT COUNT(*) FROM {f('points')}) AS points,
  (SELECT COUNT(*) FROM {f('timeseries')}) AS timeseries_rows,
  (SELECT COUNT(DISTINCT date) FROM {f('timeseries')}) AS epochs,
  (SELECT COUNT(*) FROM {f('rain')}) AS rain_rows,
  (SELECT MIN(date) FROM {f('timeseries')}) AS date_min,
  (SELECT MAX(date) FROM {f('timeseries')}) AS date_max""",
        "source_label": f"SELECT COUNTIF(STARTS_WITH(UPPER(source), 'DEMO')) AS demo_points, COUNT(*) AS total_points FROM {f('points')}",
        "list_datasets": f"SELECT * FROM {f('datasets')} ORDER BY added_at DESC",
        "list_actions": f"SELECT alert_id, action, actor, note, assignee, `at` FROM {f('alert_actions')} ORDER BY `at`",
        "list_snapshots": f"SELECT `as_of`, MAX(saved_at) AS saved_at, COUNT(*) AS sites FROM {f('site_snapshots')} GROUP BY `as_of` ORDER BY `as_of`",
    }


def all_statements(project: str, dataset: str) -> list[tuple[str, str]]:
    """Every SQL string the platform can issue with fixed text (for syntax checks and cost review)."""
    out: list[tuple[str, str]] = []
    for name, sql in read_queries(project, dataset).items():
        out.append((f"read:{name}", sql))
    for t in TABLES.values():
        out.append((f"merge:{t.name}", merge_sql(t, project, dataset, f"{t.name}_stg")))
        out.append((f"insert:{t.name}", insert_from_staging_sql(t, project, dataset, f"{t.name}_stg")))
        out.append((f"truncate:{t.name}", truncate_sql(t.name, project, dataset)))
    out.append(("delete:orphan_timeseries", delete_orphan_timeseries_sql(project, dataset)))
    return out
