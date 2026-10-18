"""BigQuery schema as data: tables, partitioning, clustering, views.

Design notes
  * Observations are partitioned by date and clustered by the keys the pipeline filters on, so a daily
    refresh scans days of data, not the whole archive.
  * Geometry is stored as GEOGRAPHY and clustered, so ST_DWITHIN against asset corridors prunes storage blocks.
  * BigQuery has no linear referencing (ST_LINELOCATEPOINT), so each asset is pre-segmented into chainage
    bins (``asset_segments``) and points are assigned to the nearest segment inside the buffer.
  * Dataset and project names are injected, never hard-coded.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Table:
    name: str
    columns: tuple[tuple[str, str], ...]  # (name, BigQuery type)
    key: tuple[str, ...] = ()
    partition_by: str | None = None  # a DATE column
    cluster_by: tuple[str, ...] = ()
    description: str = ""
    # columns computed in SQL when loading from staging (name -> expression using alias S)
    computed: dict[str, str] = field(default_factory=dict)

    @property
    def load_columns(self) -> tuple[tuple[str, str], ...]:
        """Columns supplied by Python (everything except SQL-computed ones)."""
        return tuple(c for c in self.columns if c[0] not in self.computed)


POINTS = Table(
    "points",
    (
        ("point_id", "STRING"),
        ("lat", "FLOAT64"),
        ("lon", "FLOAT64"),
        ("velocity_mm_yr", "FLOAT64"),
        ("coherence", "FLOAT64"),
        ("region_id", "STRING"),
        ("source", "STRING"),
        ("geom", "GEOGRAPHY"),
    ),
    key=("point_id",),
    cluster_by=("geom", "region_id"),
    description="InSAR scatterers (one row per measurement point).",
    computed={"geom": "ST_GEOGPOINT(S.lon, S.lat)"},
)

TIMESERIES = Table(
    "timeseries",
    (("point_id", "STRING"), ("date", "DATE"), ("disp_mm", "FLOAT64")),
    key=("point_id", "date"),
    partition_by="date",
    cluster_by=("point_id",),
    description="Line-of-sight displacement per scatterer per satellite epoch (mm).",
)

RAIN = Table(
    "rain",
    (("region_id", "STRING"), ("date", "DATE"), ("precip_mm", "FLOAT64")),
    key=("region_id", "date"),
    partition_by="date",
    cluster_by=("region_id",),
    description="Daily precipitation per region (mm).",
)

ASSETS = Table(
    "assets",
    (
        ("asset_id", "STRING"),
        ("name", "STRING"),
        ("asset_type", "STRING"),
        ("region_id", "STRING"),
        ("criticality", "FLOAT64"),
        ("consequence_note", "STRING"),
        ("buffer_m", "FLOAT64"),
        ("geometry_json", "STRING"),
        ("geom", "GEOGRAPHY"),
    ),
    key=("asset_id",),
    cluster_by=("geom",),
    description="Linear infrastructure assets (GeoJSON LineString / MultiLineString).",
    computed={"geom": "ST_GEOGFROMGEOJSON(S.geometry_json)"},
)

ASSET_SEGMENTS = Table(
    "asset_segments",
    (
        ("asset_id", "STRING"),
        ("seg_idx", "INT64"),
        ("chainage_start_m", "FLOAT64"),
        ("chainage_end_m", "FLOAT64"),
        ("buffer_m", "FLOAT64"),
        ("geom_wkt", "STRING"),
        ("geom", "GEOGRAPHY"),
    ),
    key=("asset_id", "seg_idx"),
    cluster_by=("geom", "asset_id"),
    description="Assets cut into 250 m chainage bins (BigQuery has no linear referencing).",
    computed={"geom": "ST_GEOGFROMTEXT(S.geom_wkt)"},
)

REGIONS = Table(
    "regions",
    (
        ("region_id", "STRING"),
        ("parent_id", "STRING"),
        ("name", "STRING"),
        ("level", "STRING"),
        ("center_lon", "FLOAT64"),
        ("center_lat", "FLOAT64"),
        ("zoom", "FLOAT64"),
    ),
    key=("region_id",),
    description="Region hierarchy (country > state > district).",
)

SITE_SNAPSHOTS = Table(
    "site_snapshots",
    (
        ("as_of", "DATE"),
        ("site_id", "STRING"),
        ("asset_id", "STRING"),
        ("region_id", "STRING"),
        ("tier", "STRING"),
        ("state", "STRING"),
        ("rpi", "FLOAT64"),
        ("rate_mm_month", "FLOAT64"),
        ("eta_low_days", "INT64"),
        ("eta_high_days", "INT64"),
        ("confidence", "FLOAT64"),
        ("saved_at", "TIMESTAMP"),
    ),
    key=("as_of", "site_id"),
    partition_by="as_of",
    cluster_by=("region_id", "tier"),
    description="Daily ranked-site snapshot written by the daily job (history for trends and alerts).",
)

ALERT_ACTIONS = Table(
    "alert_actions",
    (
        ("alert_id", "STRING"),
        ("action", "STRING"),
        ("actor", "STRING"),
        ("note", "STRING"),
        ("assignee", "STRING"),
        ("at", "TIMESTAMP"),
    ),
    key=("alert_id", "at"),
    cluster_by=("alert_id",),
    description="Append-only audit log of acknowledge / assign / escalate / resolve actions.",
)

DATASETS = Table(
    "datasets",
    (
        ("dataset_id", "STRING"),
        ("kind", "STRING"),
        ("name", "STRING"),
        ("source_type", "STRING"),
        ("source_ref", "STRING"),
        ("rows", "INT64"),
        ("date_min", "DATE"),
        ("date_max", "DATE"),
        ("mode", "STRING"),
        ("notes", "STRING"),
        ("added_at", "TIMESTAMP"),
    ),
    key=("dataset_id",),
    description="Provenance registry: what was loaded, from where and when.",
)

TABLES: dict[str, Table] = {t.name: t for t in (POINTS, TIMESERIES, RAIN, ASSETS, ASSET_SEGMENTS, REGIONS, SITE_SNAPSHOTS, ALERT_ACTIONS, DATASETS)}


def fq(project: str, dataset: str, name: str) -> str:
    """Fully-qualified, back-ticked table / view name."""
    return f"`{project}.{dataset}.{name}`"


def _ident(name: str) -> str:
    """Quote column / partition identifiers so reserved words (``at``, ``as_of``) stay valid SQL."""
    return f"`{name}`"


def create_table_ddl(t: Table, project: str, dataset: str) -> str:
    cols = ",\n  ".join(f"{_ident(n)} {typ}" for n, typ in t.columns)
    parts = [f"CREATE TABLE IF NOT EXISTS {fq(project, dataset, t.name)} (\n  {cols}\n)"]
    if t.partition_by:
        parts.append(f"PARTITION BY {_ident(t.partition_by)}")
    if t.cluster_by:
        parts.append("CLUSTER BY " + ", ".join(_ident(c) for c in t.cluster_by))
    if t.description:
        parts.append("OPTIONS (description = " + repr(t.description) + ")")
    return "\n".join(parts)


def view_ddls(project: str, dataset: str) -> list[tuple[str, str]]:
    f = lambda n: fq(project, dataset, n)  # noqa: E731
    return [
        (
            "v_point_assignment",
            f"""CREATE OR REPLACE VIEW {f('v_point_assignment')} AS
SELECT point_id, asset_id, seg_idx, chainage_start_m, offset_m
FROM (
  SELECT
    p.point_id,
    s.asset_id,
    s.seg_idx,
    s.chainage_start_m,
    ST_DISTANCE(p.geom, s.geom) AS offset_m,
    ROW_NUMBER() OVER (PARTITION BY p.point_id, s.asset_id ORDER BY ST_DISTANCE(p.geom, s.geom)) AS rn
  FROM {f('points')} AS p
  JOIN {f('asset_segments')} AS s
    ON ST_DWITHIN(p.geom, s.geom, s.buffer_m)
)
WHERE rn = 1""",
        ),
        (
            "v_latest_snapshot",
            f"""CREATE OR REPLACE VIEW {f('v_latest_snapshot')} AS
SELECT *
FROM {f('site_snapshots')}
WHERE as_of = (SELECT MAX(as_of) FROM {f('site_snapshots')})""",
        ),
        (
            "v_act_list",
            f"""CREATE OR REPLACE VIEW {f('v_act_list')} AS
SELECT *
FROM {f('v_latest_snapshot')}
WHERE tier IN ('CRITICAL', 'ELEVATED')
ORDER BY rpi DESC""",
        ),
        (
            "v_region_tier_daily",
            f"""CREATE OR REPLACE VIEW {f('v_region_tier_daily')} AS
SELECT
  as_of,
  region_id,
  COUNTIF(tier = 'CRITICAL') AS critical_sites,
  COUNTIF(tier = 'ELEVATED') AS elevated_sites,
  COUNTIF(tier = 'WATCH') AS watch_sites,
  COUNT(*) AS total_sites,
  MAX(rpi) AS max_rpi
FROM {f('site_snapshots')}
GROUP BY as_of, region_id""",
        ),
    ]


def setup_statements(project: str, dataset: str, location: str) -> list[str]:
    stmts = [f"CREATE SCHEMA IF NOT EXISTS `{project}.{dataset}` OPTIONS (location = '{location}')"]
    stmts += [create_table_ddl(t, project, dataset) for t in TABLES.values()]
    stmts += [sql for _, sql in view_ddls(project, dataset)]
    return stmts
