"""건축 사업성(수지) 분석 — 개략 사업비·분양수입·사업이익 추정

계획 초기 단계의 개략 수지분석(pro-forma)이다. 감정평가·PF 금융심사용 정밀
사업성 검토와 달리, 확정 전 빠른 의사결정을 돕기 위한 추정치이다.

용어(부동산개발 실무):
- 총사업비 = 토지비 + 공사비(직접) + 부대비용(간접)
- 부대비용 : 설계·감리, 인허가, 금융이자, 분양·마케팅, 제세공과, 예비비 등
             (통상 공사비의 20~30% — overhead_ratio)
- 분양수입 = 분양면적 × 분양단가 × 분양률
- 사업이익 = 분양수입 − 총사업비
- 사업수익률(원가대비) = 사업이익 / 총사업비 × 100
- 분양이익률(수입대비) = 사업이익 / 분양수입 × 100

⚠️ 금융비용을 부대비용률에 개략 포함했을 뿐 별도 PF 이자 모델은 없다.
   실제 사업성은 설계 확정·시공 견적·금융조건·분양 시나리오에 따라 달라진다.
"""

from dataclasses import dataclass

SQM_PER_PYEONG = 3.305785


@dataclass
class FeasibilityInput:
    """수지분석 입력값 (금액 단위: 원, 면적 단위: m²)"""
    gfa: float                       # 지상 연면적
    land_area: float                 # 대지면적
    land_price_per_sqm: float        # 토지 단가 (원/m²)
    construction_cost_per_sqm: float # 공사비 단가 (원/m²)
    sale_price_per_sqm: float        # 분양 단가 (원/m²)
    construction_area: float = 0.0   # 총 시공면적 (0이면 gfa 사용 — 지하 포함 시 지정)
    saleable_area: float = 0.0       # 분양면적 (0이면 gfa 사용 — 분양효율 반영 시 지정)
    overhead_ratio: float = 0.25     # 부대비용률 (공사비 대비)
    sale_rate: float = 1.0           # 분양률 (0~1)
    land_cost: float = 0.0           # 토지비 직접 지정 (0이면 land_area×land_price)


def analyze_feasibility(inp: FeasibilityInput) -> dict:
    """개략 수지분석을 수행하고 결과 dict 를 반환한다."""
    if inp.gfa <= 0:
        raise ValueError("연면적은 양수여야 합니다")
    if inp.land_area <= 0:
        raise ValueError("대지면적은 양수여야 합니다")
    for name, v in (("토지 단가", inp.land_price_per_sqm),
                    ("공사비 단가", inp.construction_cost_per_sqm),
                    ("분양 단가", inp.sale_price_per_sqm)):
        if v < 0:
            raise ValueError(f"{name}는 음수일 수 없습니다")
    if not 0 <= inp.sale_rate <= 1:
        raise ValueError("분양률은 0~1 사이여야 합니다")
    if inp.overhead_ratio < 0:
        raise ValueError("부대비용률은 음수일 수 없습니다")

    construction_area = inp.construction_area or inp.gfa
    saleable_area = inp.saleable_area or inp.gfa

    land_cost = inp.land_cost or (inp.land_area * inp.land_price_per_sqm)
    construction_cost = construction_area * inp.construction_cost_per_sqm
    overhead_cost = construction_cost * inp.overhead_ratio
    total_cost = land_cost + construction_cost + overhead_cost

    revenue = saleable_area * inp.sale_price_per_sqm * inp.sale_rate
    profit = revenue - total_cost

    profit_rate = (profit / total_cost * 100) if total_cost > 0 else 0.0
    margin_rate = (profit / revenue * 100) if revenue > 0 else 0.0

    return {
        "land_cost": round(land_cost),
        "construction_cost": round(construction_cost),
        "overhead_cost": round(overhead_cost),
        "total_cost": round(total_cost),
        "revenue": round(revenue),
        "profit": round(profit),
        "profit_rate": round(profit_rate, 2),   # 원가(총사업비) 대비 사업수익률 %
        "margin_rate": round(margin_rate, 2),    # 분양수입 대비 이익률 %
        "construction_area": round(construction_area, 2),
        "saleable_area": round(saleable_area, 2),
        "sale_rate": inp.sale_rate,
        "overhead_ratio": inp.overhead_ratio,
        # 비용 구성비 (총사업비 대비)
        "cost_breakdown": {
            "land": round(land_cost / total_cost * 100, 1) if total_cost else 0.0,
            "construction": round(construction_cost / total_cost * 100, 1) if total_cost else 0.0,
            "overhead": round(overhead_cost / total_cost * 100, 1) if total_cost else 0.0,
        },
        "feasible": profit > 0,
    }


def _won(v: float) -> str:
    """금액을 '1,234,000,000원 (약 12.3억)' 형태로 포맷."""
    eok = v / 1_0000_0000  # 1억 = 10^8
    return f"{v:,.0f}원 (약 {eok:,.1f}억)"


def format_feasibility(result: dict) -> str:
    """수지분석 결과를 CLI 출력용 텍스트로 변환."""
    b = result["cost_breakdown"]
    verdict = "사업성 양호(이익)" if result["feasible"] else "사업성 부족(손실)"
    lines = [
        "━━━ 사업성(수지) 분석 ━━━",
        f"  [비용]",
        f"    토지비     : {_won(result['land_cost'])}  ({b['land']}%)",
        f"    공사비     : {_won(result['construction_cost'])}  ({b['construction']}%)",
        f"    부대비용   : {_won(result['overhead_cost'])}  ({b['overhead']}%)",
        f"    ─────────────────────────────",
        f"    총사업비   : {_won(result['total_cost'])}",
        f"",
        f"  [수입]",
        f"    분양수입   : {_won(result['revenue'])}"
        f"  (분양률 {result['sale_rate']*100:.0f}%)",
        f"",
        f"  [결과]  {verdict}",
        f"    사업이익   : {_won(result['profit'])}",
        f"    사업수익률 : {result['profit_rate']:.2f} %  (총사업비 대비)",
        f"    분양이익률 : {result['margin_rate']:.2f} %  (분양수입 대비)",
    ]
    return "\n".join(lines)
