import pytest
from mass.zone_use import calc_parking, PARKING_UNIT_AREA


def test_office_parking_basic():
    # 업무시설: 연면적 150m²당 1대 → 1500m² = 10대
    r = calc_parking(1500, "업무시설")
    assert r["required"] == 10
    assert r["use_type"] == "업무시설"


def test_parking_rounds_up():
    # 200m²당 1대 기준, 201m² → 2대 (ceil)
    r = calc_parking(201, "판매시설")
    assert r["required"] == 2


def test_parking_minimum_one():
    # 아주 작은 면적이라도 최소 1대 (기타 용도)
    r = calc_parking(10, "기타")
    assert r["required"] == 1


def test_detached_house_exempt():
    # 단독주택 150m² 미만 면제
    assert calc_parking(120, "단독주택")["required"] == 0
    assert calc_parking(160, "단독주택")["required"] == 1


def test_neighborhood_facility_exempt():
    # 근린생활시설 300m² 미만 면제
    assert calc_parking(250, "근린생활시설")["required"] == 0
    assert calc_parking(400, "근린생활시설")["required"] == 2


def test_estimated_parking_area():
    # 소요 주차면적 = 대수 × 대당면적
    r = calc_parking(1500, "업무시설")
    assert r["est_area"] == round(r["required"] * PARKING_UNIT_AREA, 1)
    assert r["unit_area"] == PARKING_UNIT_AREA


def test_disabled_parking_for_commercial():
    # 상업·업무: 부설주차의 4%, 최소 1대
    r = calc_parking(3000, "업무시설")  # 20대
    assert r["disabled"] == max(1, round(20 * 0.04))


def test_disabled_parking_excluded_for_housing():
    # 공동주택은 장애인주차 개략산정에서 제외(0)
    r = calc_parking(1000, "공동주택")
    assert r["disabled"] == 0
