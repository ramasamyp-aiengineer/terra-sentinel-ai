"""Upload parsing and validation: aliases, row-level rejection, EGMS-style wide files, error clarity."""
from __future__ import annotations

import json

import pytest

from app.services.data import ingest
from app.services.data.ingest import IngestError, ParseContext, parse_upload

REGIONS = [
    {"region_id": "IN", "parent_id": None, "name": "India", "level": "country", "center": [79, 22], "zoom": 4},
    {"region_id": "IN-TN-CHN", "parent_id": "IN", "name": "Chennai", "level": "district", "center": [80.27, 13.08], "zoom": 11},
    {"region_id": "IN-UK-CHM", "parent_id": "IN", "name": "Chamoli", "level": "district", "center": [79.57, 30.55], "zoom": 9},
]


def ctx(name="f.csv", default_region=None):
    return ParseContext(filename=name, regions=REGIONS, default_region=default_region)


def csv(*lines):
    return ("\n".join(lines) + "\n").encode()


def test_points_with_aliases_and_nearest_region():
    data = csv("pid,latitude,longitude,mean_velocity,temporal_coherence", "A1,13.081,80.271,-4.2,0.82", "A2,13.082,80.272,-0.3,0.9")
    r = parse_upload("p.csv", data, None, ctx("p.csv"))
    assert r.ok
    pts = r.payloads["points"]
    assert list(pts["point_id"]) == ["A1", "A2"]
    assert set(pts["region_id"]) == {"IN-TN-CHN"}  # nearest region assigned by position
    rep = r.reports[0]
    assert rep.mapped_columns["lat"] == "latitude"
    assert any("region" in w.lower() for w in rep.warnings)  # defaults are surfaced, never silent


def test_out_of_range_rows_rejected_individually():
    rows = ["point_id,lat,lon,velocity_mm_yr,coherence"] + [f"P{i},13.0{i},80.2{i},-1,0.9" for i in range(1, 9)]
    rows += ["BAD1,95.0,80.2,-1,0.9", "BAD2,13.0,80.2,-1,1.7"]
    r = parse_upload("p.csv", csv(*rows), "points", ctx())
    # latitude 95 is rejected (row 9); coherence 1.7 is not a reason to drop a point - it is treated
    # as missing, replaced by the default and flagged so confidence is not silently overstated
    assert r.ok
    rep = r.reports[0]
    assert rep.rows_ok == 9 and rep.rows_rejected == 1
    assert {e["row"] for e in rep.errors} == {10}  # spreadsheet line number: header is line 1
    assert len(r.payloads["points"]) == 9
    assert any("coherence" in w.lower() for w in rep.warnings)


def test_too_many_bad_rows_blocks_the_file():
    rows = ["point_id,lat,lon"] + ["P1,13.0,80.2"] + [f"X{i},999,80.2" for i in range(5)]
    r = parse_upload("p.csv", csv(*rows), "points", ctx())
    assert not r.ok and r.payloads == {}
    assert r.reports[0].blocked_reason


def test_duplicate_point_ids_are_reported():
    r = parse_upload("p.csv", csv("point_id,lat,lon", "A,13.0,80.2", "A,13.1,80.3", "B,13.2,80.1"), "points", ctx())
    assert r.ok and len(r.payloads["points"]) == 2
    assert any("duplicate" in w.lower() for w in r.reports[0].warnings)


def test_wide_insar_creates_points_and_timeseries():
    data = csv(
        "pid,latitude,longitude,mean_velocity,temporal_coherence,20250105,20250117,20250129,20250210",
        "E1,13.081,80.271,-4.2,0.82,0,-0.4,-0.9,-1.3",
        "E2,13.082,80.272,-0.3,0.91,0,0.1,-0.1,0.0",
    )
    r = parse_upload("egms.csv", data, None, ctx("egms.csv"))
    assert r.ok
    assert set(r.payloads) == {"points", "timeseries"}
    ts = r.payloads["timeseries"]
    assert len(ts) == 8 and str(ts["date"].min().date()) == "2025-01-05"
    assert abs(ts[(ts.point_id == "E1") & (ts.date == "2025-01-29")]["disp_mm"].iloc[0] + 0.9) < 1e-9


def test_wide_insar_missing_velocity_is_derived_and_flagged():
    data = csv("point_id,lat,lon,20250105,20250117,20250129,20250210,20250222", "E1,13.08,80.27,0,-1,-2,-3,-4")
    r = parse_upload("w.csv", data, "insar", ctx())
    assert r.ok
    v = r.payloads["points"]["velocity_mm_yr"].iloc[0]
    assert v < 0
    assert any("velocity" in w.lower() for r_ in r.reports for w in r_.warnings)


def test_timeseries_long_format_and_bad_dates():
    data = csv("point_id,date,disp_mm", "A,2025-01-05,0", "A,2025-01-17,-0.4", "A,not-a-date,1", "A,2025-01-29,-0.9", "A,2025-02-10,-1.1", "A,2025-02-22,-1.5")
    r = parse_upload("t.csv", data, "timeseries", ctx())
    assert r.ok and len(r.payloads["timeseries"]) == 5
    assert r.reports[0].rows_rejected == 1


def test_rain_negative_values_rejected_and_region_checked():
    data = csv("region_id,date,precip_mm", "IN-TN-CHN,2026-10-01,0", "IN-TN-CHN,2026-10-02,12.4", "IN-TN-CHN,2026-10-03,-5", "IN-TN-CHN,2026-10-04,3", "IN-TN-CHN,2026-10-05,1", "IN-TN-CHN,2026-10-06,0", "IN-TN-CHN,2026-10-07,2", "IN-TN-CHN,2026-10-08,0", "IN-TN-CHN,2026-10-09,0", "IN-TN-CHN,2026-10-10,0", "IN-TN-CHN,2026-10-11,0")
    r = parse_upload("r.csv", data, "rain", ctx())
    assert r.ok and r.reports[0].rows_rejected == 1
    # rain for a region that does not exist yet is accepted (regions can be added afterwards) but flagged
    unknown = parse_upload("r.csv", csv("region_id,date,precip_mm", "NOPE,2026-10-01,3"), "rain", ctx())
    assert unknown.ok and any("NOPE" in w for w in unknown.reports[0].warnings)


def test_assets_geojson_valid_and_invalid():
    good = {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": {"name": "Test Road", "asset_type": "highway", "region_id": "IN-TN-CHN", "criticality": 0.8}, "geometry": {"type": "LineString", "coordinates": [[80.27, 13.08], [80.28, 13.09]]}},
        ],
    }
    r = parse_upload("a.geojson", json.dumps(good).encode(), None, ctx())
    assert r.ok
    f = r.payloads["assets"][0]["properties"]
    assert f["asset_type"] == "HIGHWAY" and f["asset_id"]

    bad = {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {"name": "Pin"}, "geometry": {"type": "Point", "coordinates": [80, 13]}}]}
    r2 = parse_upload("a.geojson", json.dumps(bad).encode(), None, ctx())
    assert not r2.ok and r2.reports[0].errors


def test_regions_csv_parent_must_exist_and_no_cycles():
    ok = parse_upload("g.csv", csv("region_id,parent_id,name,level,center_lon,center_lat", "IN-KA,IN,Karnataka,state,76.6,14.6"), "regions", ctx())
    assert ok.ok and ok.payloads["regions"][0]["center"] == [76.6, 14.6]
    orphan = parse_upload("g.csv", csv("region_id,parent_id,name,level,center_lon,center_lat", "X,MISSING,Xland,state,1,1"), "regions", ctx())
    assert not orphan.ok


@pytest.mark.parametrize("name", ["data.xlsx", "x.zip", "scene.tif"])
def test_unsupported_formats_get_a_clear_message(name):
    with pytest.raises(IngestError, match="not supported"):
        parse_upload(name, b"abc", None, ctx())


def test_empty_and_unrecognisable_files():
    with pytest.raises(IngestError):
        parse_upload("e.csv", b"   \n", None, ctx())
    with pytest.raises(IngestError, match="Could not tell"):
        parse_upload("e.csv", csv("foo,bar", "1,2"), None, ctx())


def test_templates_round_trip():
    """Every downloadable template must itself pass validation."""
    for kind, (content, filename) in ingest.TEMPLATES.items():
        payload = content if isinstance(content, bytes) else content.encode()
        r = parse_upload(filename, payload, kind, ctx(filename, default_region="IN-TN-CHN"))
        assert r.ok, (kind, [rep.to_dict() for rep in r.reports])


def test_nearest_region_is_capped():
    # London is far from every India leaf — must not silently attach to Chamoli/Chennai.
    data = csv("pid,latitude,longitude,mean_velocity,temporal_coherence", "EU1,51.5074,-0.1278,-1.0,0.9")
    r = parse_upload("p.csv", data, "points", ctx("p.csv"))
    assert r.ok
    assert set(r.payloads["points"]["region_id"]) == {"UNASSIGNED"}
    assert any("farther than" in w.lower() or "unassigned" in w.lower() for w in r.reports[0].warnings)


def test_excel_float_date_headers_still_detect_insar():
    data = csv(
        "pid,latitude,longitude,20250105.0,20250117.0,20250129.0,20250210.0",
        "E1,13.081,80.271,0,-0.4,-0.9,-1.3",
    )
    r = parse_upload("egms.csv", data, None, ctx("egms.csv"))
    assert r.ok and set(r.payloads) == {"points", "timeseries"}
    assert len(r.payloads["timeseries"]) == 4


def test_insar_kind_refuses_file_without_epoch_columns():
    data = csv("pid,latitude,longitude,mean_velocity", "E1,13.081,80.271,-1.0")
    with pytest.raises(IngestError, match="epoch date columns"):
        parse_upload("bad.csv", data, "insar", ctx())


def test_non_utf8_csv_is_refused():
    with pytest.raises(IngestError, match="UTF-8"):
        parse_upload("latin.csv", "point_id,lat,lon\nA,13.0,80.2\n".encode("latin-1") + b"\xff", "points", ctx())
