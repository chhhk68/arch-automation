"""대지 정보 및 법규 검토"""

import math
from dataclasses import dataclass, field
from typing import Optional
from .regulations import get_regulations, max_height_at_north_distance, FLOOR_HEIGHT, MIN_SETBACK


@dataclass
class Site:
    """대지 정보"""
    width: float        # 동서 방향 폭 (m) — 이격/건물 형상 계산용
    depth: float        # 남북 방향 깊이 (m) — 이격/건물 형상 계산용
    zone: str           # 용도지역
    setback_n: float = MIN_SETBACK   # 북측 이격 (m)
    setback_s: float = MIN_SETBACK   # 남측 이격 (m)
    setback_e: float = MIN_SETBACK   # 동측 이격 (m)
    setback_w: float = MIN_SETBACK   # 서측 이격 (m)
    actual_area: Optional[float] = None  # 지적도 실제 면적 (m²) — 제공 시 BCR/FAR 계산에 우선 사용
    region: str = ""    # 시·도 (예: "대전광역시") — 지자체 도시계획조례 BCR/FAR 적용

    @property
    def area(self) -> float:
        """규제 계산용 대지면적
        지적도 실제 면적(actual_area)이 있으면 그것을 사용.
        없으면 가로×세로 바운딩 박스로 대체.
        건축법 제56조(건폐율)/제55조(용적률) 계산 기준.
        """
        return self.actual_area if (self.actual_area and self.actual_area > 0) \
               else self.width * self.depth

    @property
    def regs(self) -> dict:
        return get_regulations(self.zone, self.region)

    @property
    def footprint_width(self) -> float:
        return max(0.0, self.width - self.setback_e - self.setback_w)

    @property
    def footprint_depth(self) -> float:
        return max(0.0, self.depth - self.setback_n - self.setback_s)

    @property
    def footprint_area(self) -> float:
        return self.footprint_width * self.footprint_depth

    def check(self) -> "RegulationResult":
        return RegulationResult(self)


@dataclass
class RegulationResult:
    site: Site
    _max_floors: Optional[int] = field(default=None, init=False)

    def __post_init__(self):
        self._compute()

    def _compute(self):
        regs = self.site.regs
        s = self.site

        # 건폐율 적용 → 실제 바닥면적 (대지면적 기준)
        self.max_ground_area = s.area * regs["bcr"] / 100
        # 실제 건물 풋프린트: (이격 적용 가로×세로)와 건폐 한도 중 작은 값
        self.actual_ground_area = min(s.footprint_area, self.max_ground_area)

        # 허용 연면적 (용적률 × 대지면적)
        self.max_total_area = s.area * regs["far"] / 100

        # 높이 제한
        self.height_limit = regs["max_height"]  # None이면 제한 없음

        # 층수 계산
        max_h = self.height_limit if self.height_limit else 999
        max_floors_by_height = int(max_h // FLOOR_HEIGHT)
        # 용도지역 층수 제한 (예: 제1종일반주거지역 4층 이하 — 국토계획법 시행령 별표4)
        max_floors_by_zone = regs.get("max_floors") or 9999
        # ceil 사용: GFA를 최대 연면적까지 채우려면 최소 ceil(FAR면적/건폐면적)층이 필요
        # (예: 647m²÷194m²=3.33→4층 필요, 3층으로는 582m²밖에 못 채움)
        max_floors_by_far = (math.ceil(self.max_total_area / self.actual_ground_area)
                             if self.actual_ground_area > 0 else 0)
        self._max_floors = min(max_floors_by_height, max_floors_by_far, max_floors_by_zone)
        self.max_floors_zone = regs.get("max_floors")          # None이면 층수 제한 없음
        self.floors_basis    = regs.get("floors_basis", "")

        # 일조권 사선제한 적용 여부 (건축법 시행령 제86조)
        self.apply_solar = regs["solar"]

    @property
    def max_floors(self) -> int:
        return self._max_floors

    def floor_footprints(self) -> list[tuple[float, float, float, float]]:
        """
        층별 (x0, y0, width, depth) 반환.
        하층은 건폐율 최대 면적으로 채우고, 최상층은 FAR 잔여 면적만 채움.
        건축개념: 1~(N-1)층은 max_ground_area 크기, N층은 나머지 GFA.
        일조권 사선제한 적용 시 상층부 step-back.
        좌표계: (0,0) = 대지 남서 모서리
        """
        s = self.site
        x0_base = s.setback_w
        y0_base = s.setback_s
        w_base = s.footprint_width
        d_base = s.footprint_depth

        # 건폐율 적용 최대 깊이
        d_bcr = self.actual_ground_area / w_base if w_base > 0 else d_base
        d_bcr = min(d_bcr, d_base)

        footprints = []
        cumulative_area = 0.0

        for floor in range(self._max_floors):
            if self.apply_solar:
                h_top = (floor + 1) * FLOOR_HEIGHT
                # 허용 높이 h_top을 위해 필요한 정북 이격거리 (건축법 시행령 §86)
                d_north_needed = h_top / 1.5 if h_top <= 9.0 else h_top / 2.0
                extra_setback = max(0.0, d_north_needed - s.setback_n)
                d_solar = max(0.0, d_base - extra_setback)
                d_floor = min(d_solar, d_bcr)
            else:
                d_floor = d_bcr

            floor_area = w_base * d_floor
            # 남은 FAR 면적이 전층 면적보다 적으면 최상층 축소
            if cumulative_area + floor_area > self.max_total_area:
                remaining = self.max_total_area - cumulative_area
                d_floor = remaining / w_base if w_base > 0 else 0
                floor_area = w_base * d_floor

            if floor_area <= 0:
                break

            footprints.append((x0_base, y0_base, w_base, d_floor))
            cumulative_area += floor_area

        return footprints

    def area_schedule(self, use_type: str = "") -> dict:
        """이 검토 결과의 층별 풋프린트로 면적 산정표를 생성한다.

        건폐율·용적률(%)은 대지면적(site.area) 기준으로 함께 계산된다.
        """
        from .schedule import build_area_schedule
        return build_area_schedule(self.floor_footprints(),
                                   site_area=self.site.area,
                                   floor_height=FLOOR_HEIGHT,
                                   use_type=use_type)

    def summary(self) -> str:
        s = self.site
        regs = s.regs
        lines = [
            f"━━━ 법규 검토 결과 ━━━",
            f"용도지역     : {s.zone}",
            f"대지면적     : {s.area:.1f} m²  (지적도 {'실측' if s.actual_area else '가로×세로 추산'})",
            f"",
            f"[건폐율]  허용 {regs['bcr']}% → 최대 건축면적 {self.max_ground_area:.1f} m²",
            f"[용적률]  허용 {regs['far']}% → 최대 연면적 {self.max_total_area:.1f} m²",
            f"[높이]    {'제한없음' if regs['max_height'] is None else str(regs['max_height']) + 'm'}",
            f"[일조권]  {'적용' if self.apply_solar else '미적용'}",
            f"",
            f"이격 거리    : N={s.setback_n}m / S={s.setback_s}m / E={s.setback_e}m / W={s.setback_w}m",
            f"실 바닥면적  : {self.actual_ground_area:.1f} m²",
            f"최대 층수    : {self.max_floors}층",
        ]
        return "\n".join(lines)
