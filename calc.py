"""건축 면적 및 비용 계산 유틸리티"""


def room_area(width: float, height: float) -> float:
    """방의 면적을 계산합니다 (단위: m²)"""
    if width <= 0 or height <= 0:
        raise ValueError("가로, 세로는 양수여야 합니다")
    return width * height


def pyeong_to_sqm(pyeong: float) -> float:
    """평을 제곱미터로 변환합니다"""
    if pyeong < 0:
        raise ValueError("평수는 음수일 수 없습니다")
    return pyeong * 3.305785


def sqm_to_pyeong(sqm: float) -> float:
    """제곱미터를 평으로 변환합니다"""
    if sqm < 0:
        raise ValueError("면적은 음수일 수 없습니다")
    return sqm / 3.305785


def estimate_cost(area_sqm: float, cost_per_sqm: float) -> float:
    """면적과 단가로 공사비를 추정합니다"""
    if area_sqm <= 0:
        raise ValueError("면적은 양수여야 합니다")
    if cost_per_sqm <= 0:
        raise ValueError("단가는 양수여야 합니다")
    return area_sqm * cost_per_sqm


def floor_area_ratio(total_floor_area: float, land_area: float) -> float:
    """용적률을 계산합니다 (단위: %)

    용적률 = 연면적 / 대지면적 × 100
    """
    if total_floor_area < 0:
        raise ValueError("연면적은 음수일 수 없습니다")
    if land_area <= 0:
        raise ValueError("대지면적은 양수여야 합니다")
    return (total_floor_area / land_area) * 100


def building_coverage_ratio(building_area: float, land_area: float) -> float:
    """건폐율을 계산합니다 (단위: %)

    건폐율 = 건축면적 / 대지면적 × 100
    """
    if building_area < 0:
        raise ValueError("건축면적은 음수일 수 없습니다")
    if land_area <= 0:
        raise ValueError("대지면적은 양수여야 합니다")
    return (building_area / land_area) * 100
