"""건축 매스·법규 검토 패키지.

경량 모듈(site·zone_use·schedule·feasibility·exporter)은 즉시 import 가능하며,
plotly 가 필요한 3D 시각화(plot_mass)는 접근 시점에 지연 로딩한다.
→ requirements 경량 구성(flask+requests)에서도 웹앱(app.py)이 구동된다.
  (기존에는 __init__ 이 plotly 를 즉시 import 해 경량 환경에서 앱이 기동 실패했음)
"""

from .site import Site
from .exporter import export_obj, export_ifc
from .zone_use import (get_zone_uses, calc_parking, calc_landscape,
                       calc_public_space, default_use_type_for_zone)
from .schedule import build_area_schedule, schedule_to_csv, format_schedule
from .feasibility import (FeasibilityInput, analyze_feasibility,
                          format_feasibility)

__all__ = [
    "Site", "export_obj", "export_ifc",
    "get_zone_uses", "calc_parking", "calc_landscape",
    "calc_public_space", "default_use_type_for_zone",
    "build_area_schedule", "schedule_to_csv", "format_schedule",
    "FeasibilityInput", "analyze_feasibility", "format_feasibility",
    "plot_mass",
]


def __getattr__(name):
    # plotly 의존 시각화는 필요할 때만 로딩 (PEP 562)
    if name == "plot_mass":
        from .visualizer import plot_mass
        return plot_mass
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
