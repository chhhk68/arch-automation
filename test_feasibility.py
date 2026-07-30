import pytest
from mass.feasibility import (FeasibilityInput, analyze_feasibility,
                              format_feasibility)


def base_input(**over):
    d = dict(
        gfa=1000,
        land_area=400,
        land_price_per_sqm=5_000_000,      # 토지 20억
        construction_cost_per_sqm=2_500_000,  # 공사비 25억
        sale_price_per_sqm=8_000_000,      # 분양수입 80억
    )
    d.update(over)
    return FeasibilityInput(**d)


def test_cost_components():
    r = analyze_feasibility(base_input(overhead_ratio=0.20))
    assert r["land_cost"] == 400 * 5_000_000          # 20억
    assert r["construction_cost"] == 1000 * 2_500_000  # 25억
    assert r["overhead_cost"] == 25_0000_0000 * 0.20   # 5억
    assert r["total_cost"] == 20_0000_0000 + 25_0000_0000 + 5_0000_0000


def test_revenue_and_profit():
    r = analyze_feasibility(base_input(overhead_ratio=0.20))
    assert r["revenue"] == 1000 * 8_000_000            # 80억
    # 이익 = 80억 - 50억 = 30억
    assert r["profit"] == 30_0000_0000
    assert r["feasible"] is True


def test_profit_and_margin_rates():
    r = analyze_feasibility(base_input(overhead_ratio=0.20))
    # 수익률 = 30억/50억 = 60%, 이익률 = 30억/80억 = 37.5%
    assert r["profit_rate"] == 60.0
    assert r["margin_rate"] == 37.5


def test_sale_rate_reduces_revenue():
    full = analyze_feasibility(base_input())
    half = analyze_feasibility(base_input(sale_rate=0.5))
    assert half["revenue"] == full["revenue"] / 2


def test_land_cost_override():
    r = analyze_feasibility(base_input(land_cost=10_0000_0000))
    assert r["land_cost"] == 10_0000_0000


def test_construction_area_override_for_basement():
    # 지하 포함 시공면적이 크면 공사비 증가
    r = analyze_feasibility(base_input(construction_area=1500))
    assert r["construction_cost"] == 1500 * 2_500_000


def test_loss_case_not_feasible():
    r = analyze_feasibility(base_input(sale_price_per_sqm=1_000_000))
    assert r["profit"] < 0
    assert r["feasible"] is False


def test_cost_breakdown_sums_to_100():
    r = analyze_feasibility(base_input())
    b = r["cost_breakdown"]
    assert abs(b["land"] + b["construction"] + b["overhead"] - 100.0) < 0.5


def test_invalid_inputs():
    with pytest.raises(ValueError):
        analyze_feasibility(base_input(gfa=0))
    with pytest.raises(ValueError):
        analyze_feasibility(base_input(sale_rate=1.5))
    with pytest.raises(ValueError):
        analyze_feasibility(base_input(land_price_per_sqm=-1))


def test_format_runs():
    out = format_feasibility(analyze_feasibility(base_input()))
    assert "사업성" in out
    assert "총사업비" in out
