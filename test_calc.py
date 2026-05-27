import pytest
from calc import room_area, pyeong_to_sqm, sqm_to_pyeong, estimate_cost


def test_room_area_basic():
    assert room_area(4.0, 3.0) == 12.0


def test_room_area_invalid():
    with pytest.raises(ValueError):
        room_area(-1, 3)
    with pytest.raises(ValueError):
        room_area(4, 0)


def test_pyeong_to_sqm():
    assert abs(pyeong_to_sqm(1) - 3.305785) < 0.0001


def test_sqm_to_pyeong_roundtrip():
    original = 30.0
    assert abs(sqm_to_pyeong(pyeong_to_sqm(original)) - original) < 0.0001


def test_estimate_cost():
    assert estimate_cost(100.0, 1_500_000) == 150_000_000.0


def test_estimate_cost_invalid():
    with pytest.raises(ValueError):
        estimate_cost(0, 1_000_000)
    with pytest.raises(ValueError):
        estimate_cost(100, -1)


from calc import floor_area_ratio, building_coverage_ratio


def test_floor_area_ratio():
    assert floor_area_ratio(660, 330) == 200.0


def test_floor_area_ratio_invalid():
    with pytest.raises(ValueError):
        floor_area_ratio(100, 0)
    with pytest.raises(ValueError):
        floor_area_ratio(-1, 100)


def test_building_coverage_ratio():
    assert building_coverage_ratio(165, 330) == 50.0


def test_building_coverage_ratio_invalid():
    with pytest.raises(ValueError):
        building_coverage_ratio(100, 0)
