import pytest
from mass.schedule import build_area_schedule, schedule_to_csv, format_schedule


# 3층 건물, 각 층 10×20 = 200m² 풋프린트
FOOTPRINTS = [(0, 0, 10, 20), (0, 0, 10, 20), (0, 0, 10, 20)]


def test_gross_floor_area():
    s = build_area_schedule(FOOTPRINTS)
    assert s["gross_floor_area"] == 600.0
    assert s["floor_count"] == 3
    assert s["building_area"] == 200.0


def test_bcr_far_with_site_area():
    s = build_area_schedule(FOOTPRINTS, site_area=400)
    assert s["bcr"] == 50.0     # 200 / 400
    assert s["far"] == 150.0    # 600 / 400


def test_no_site_area_yields_none():
    s = build_area_schedule(FOOTPRINTS)
    assert s["bcr"] is None
    assert s["far"] is None


def test_floor_rows_and_cumulative():
    s = build_area_schedule(FOOTPRINTS, floor_height=3.0)
    rows = s["floors"]
    assert [r["floor"] for r in rows] == [1, 2, 3]
    assert rows[-1]["cumulative_sqm"] == 600.0
    assert rows[0]["height_top"] == 3.0
    assert rows[2]["height_top"] == 9.0


def test_step_back_building_area_is_max():
    # 상층 축소(step-back) 시 건축면적은 최대층(1층) 기준
    fps = [(0, 0, 10, 20), (0, 0, 10, 15), (0, 0, 10, 10)]
    s = build_area_schedule(fps, site_area=400)
    assert s["building_area"] == 200.0
    assert s["gross_floor_area"] == 450.0


def test_zero_area_floor_skipped():
    fps = [(0, 0, 10, 20), (0, 0, 10, 0)]
    s = build_area_schedule(fps)
    assert s["floor_count"] == 1


def test_invalid_site_area():
    with pytest.raises(ValueError):
        build_area_schedule(FOOTPRINTS, site_area=0)


def test_csv_contains_header_and_totals():
    s = build_area_schedule(FOOTPRINTS, site_area=400)
    csv_text = schedule_to_csv(s)
    assert "바닥면적(m²)" in csv_text
    assert "연면적(m²)" in csv_text
    assert "600" in csv_text
    assert "용적률(%)" in csv_text


def test_format_schedule_runs():
    s = build_area_schedule(FOOTPRINTS, site_area=400)
    out = format_schedule(s)
    assert "면적 산정표" in out
    assert "건폐율" in out
