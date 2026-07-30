"""용도지역별 허용 용도, 주차기준, 조경기준, 공개공지 기준"""

import math
from .regulations import ZONING

# ── 용도지역별 권장·가능 용도 (건축법 시행령 별표 기준) ──────────────
ZONE_USES = {
    "제1종전용주거지역": {
        "recommended": ["단독주택", "다가구주택", "제1종 근린생활시설 (1,000m² 미만)"],
        "possible":    ["노유자시설", "종교시설", "초·중·고등학교"],
        "note": "단독주택 위주의 저밀 주거지역 — 공동주택 불가"
    },
    "제2종전용주거지역": {
        "recommended": ["단독주택", "다세대주택", "연립주택 (4층 이하)"],
        "possible":    ["제1종 근린생활시설", "노유자시설", "종교시설"],
        "note": "공동주택(아파트 제외) 건축 가능한 저밀 주거지역"
    },
    "제1종일반주거지역": {
        "recommended": ["단독주택", "공동주택 (4층 이하)", "다가구·다세대"],
        "possible":    ["제1·2종 근린생활시설", "의원·치과의원", "종교시설"],
        "note": "4층 이하 중저층 주거중심 지역"
    },
    "제2종일반주거지역": {
        "recommended": ["아파트", "오피스텔 (소규모)", "단독·다세대"],
        "possible":    ["제1·2종 근린생활시설", "종교시설", "교육연구시설"],
        "note": "중층 아파트 개발에 적합한 일반 주거지역"
    },
    "제3종일반주거지역": {
        "recommended": ["고층 아파트", "오피스텔"],
        "possible":    ["제1·2종 근린생활시설", "업무시설 (소규모)", "판매시설 (일부)"],
        "note": "층수 제한 없는 고층 주거 가능 지역"
    },
    "준주거지역": {
        "recommended": ["업무시설", "주거복합 (주상복합)", "판매시설", "근린생활시설"],
        "possible":    ["의료시설", "문화집회시설", "숙박시설", "교육연구시설"],
        "note": "주거 + 상업 복합개발에 최적, 광범위한 용도 허용"
    },
    "근린상업지역": {
        "recommended": ["근린생활시설", "판매시설", "업무시설", "숙박시설"],
        "possible":    ["공동주택 (복합)", "의료시설", "문화집회시설"],
        "note": "생활권 내 근린 상업시설 중심"
    },
    "일반상업지역": {
        "recommended": ["업무시설 (오피스빌딩)", "판매시설", "주상복합", "숙박시설"],
        "possible":    ["문화집회시설", "의료시설", "교육연구시설", "운동시설"],
        "note": "고용적률 상업·업무 복합개발 최적 — 도심 오피스에 유리"
    },
    "중심상업지역": {
        "recommended": ["업무시설 (초고층)", "대형 판매시설", "관광숙박", "주상복합"],
        "possible":    ["문화집회시설", "의료시설", "전시시설"],
        "note": "도심 핵심 상권, 최고밀도 개발 가능"
    },
    "준공업지역": {
        "recommended": ["공장 (경공업)", "물류창고·유통시설", "업무시설"],
        "possible":    ["공동주택 (복합)", "근린생활시설", "판매시설 (일부)"],
        "note": "경공업 + 주거·상업 복합 가능"
    },
}

# ── 주용도별 주차 기준 (서울특별시 주차장 조례 + 주차장법 시행령) ────────
PARKING_STD = {
    "업무시설":     {"per_m2": 1/150,  "label": "연면적 150m²당 1대"},
    "판매시설":     {"per_m2": 1/200,  "label": "연면적 200m²당 1대"},
    "공동주택":     {"per_m2": 1/85,   "label": "전용 85m²당 1대 (세대 기준)"},
    "숙박시설":     {"per_m2": 1/200,  "label": "연면적 200m²당 1대"},
    "근린생활시설": {"per_m2": 1/200,  "label": "연면적 200m²당 1대"},
    "문화집회시설": {"per_m2": 1/150,  "label": "연면적 150m²당 1대"},
    "의료시설":     {"per_m2": 1/150,  "label": "연면적 150m²당 1대"},
    "교육연구시설": {"per_m2": 1/200,  "label": "연면적 200m²당 1대"},
    "기타":         {"per_m2": 1/200,  "label": "연면적 200m²당 1대"},
}

# ── 조경면적 기준 (건축법 시행령 제27조, 대지면적 대비) ────────────────
# 연면적 2,000m² 이상이거나 대지면적 200m² 이상인 건축물에 적용
LANDSCAPE_RATIO = {
    "제1종전용주거지역": 0.20,
    "제2종전용주거지역": 0.20,
    "제1종일반주거지역": 0.15,
    "제2종일반주거지역": 0.15,
    "제3종일반주거지역": 0.15,
    "준주거지역":        0.15,
    "근린상업지역":      0.10,
    "일반상업지역":      0.10,
    "중심상업지역":      0.10,
    "준공업지역":        0.10,
}

# ── 공개공지 의무 대상 용도지역 (건축법 제43조) ──────────────────────
PUBLIC_SPACE_ZONES = {"중심상업지역", "일반상업지역", "근린상업지역", "준주거지역"}
PUBLIC_SPACE_MIN_GFA = 5000  # 연면적 5,000m² 이상
PUBLIC_SPACE_RATIO = 0.05    # 대지면적의 5% 이상 (최대 10%)


def get_zone_uses(zone: str) -> dict:
    return ZONE_USES.get(zone, {"recommended": [], "possible": [], "note": "데이터 없음"})


def calc_parking(gfa: float, use_type: str = "업무시설") -> dict:
    """주차대수 계산 (서울시 주차장 조례 기준)

    공동주택: 전용면적(GFA×0.65) 기준 85m²당 1대 — 세대 기준
              (주차장법 시행령 별표 1 + 서울시 주차장 조례)
    단독주택: 소규모(연면적 150m² 미만) 면제, 이상은 1대
    근린생활시설: 전용 300m² 미만 면제 (서울시 조례)
    기타: 연면적 기준
    """
    std = PARKING_STD.get(use_type, PARKING_STD["기타"])

    if use_type == "공동주택":
        # 세대 구성 확정 전 개략치: 전용률 75% 적용 → 전용 85m²당 1대
        # (실제는 주택건설기준·지자체 조례상 세대당 기준: 전용 60m² 초과 1대,
        #  60m² 이하 0.7~0.8대 등 — 세대 구성 확정 후 재산정 필요)
        net_area = gfa * 0.75
        required = max(1, math.ceil(net_area / 85))
        label = f"전용 85m²당 1대 개략 (전용 {net_area:.0f}m² 기준 — 세대구성 확정 후 재산정)"
    elif use_type == "단독주택":
        required = 0 if gfa < 150 else 1
        label = "연면적 150m² 미만 면제 (1가구 1대)"
    elif use_type == "근린생활시설":
        required = 0 if gfa < 300 else max(1, math.ceil(gfa / 200))
        label = "연면적 300m² 미만 면제 / 이상 200m²당 1대"
    else:
        required = max(1, math.ceil(gfa * std["per_m2"]))
        label = std["label"]

    return {
        "required": required,
        "standard": label,
        "use_type": use_type,
        "gfa": round(gfa, 1),
    }


def calc_landscape(site_area: float, zone: str, gfa: float = 0.0) -> dict:
    """조경면적 계산

    건축법 §42: 대지면적 200m² 이상인 대지에 건축 시 조경 의무.
    → 면제 기준은 '대지면적 200m² 미만' (기존의 연면적 2,000m² 기준은 오류 — 수정)
    비율은 지자체 건축조례로 정함 (연면적 1,500m² 미만 완화 등은 조례 확인).
    """
    if site_area < 200:
        return {
            "required_area": 0.0, "ratio": 0.0,
            "exempt": True,
            "note": "조경 의무 면제 (대지면적 200m² 미만 — 건축법 §42)"
        }
    ratio = LANDSCAPE_RATIO.get(zone, 0.10)
    required = round(site_area * ratio, 1)
    return {
        "required_area": required,
        "ratio": ratio * 100,
        "exempt": False,
        "note": f"대지면적의 {ratio*100:.0f}% 이상 ({required} m²)"
    }


def calc_public_space(site_area: float, gfa: float, zone: str) -> dict:
    """공개공지 면적 계산"""
    if gfa < PUBLIC_SPACE_MIN_GFA or zone not in PUBLIC_SPACE_ZONES:
        return {
            "required_area": 0.0,
            "exempt": True,
            "note": "공개공지 의무 해당없음"
        }
    min_area = round(site_area * PUBLIC_SPACE_RATIO, 1)
    max_area = round(site_area * 0.10, 1)
    return {
        "required_area": min_area,
        "exempt": False,
        "note": f"대지면적의 5~10% ({min_area}~{max_area} m²)"
    }


def default_use_type_for_zone(zone: str) -> str:
    """용도지역에 따른 기본 주용도 반환"""
    if "주거" in zone:
        return "공동주택"
    if "공업" in zone:
        return "업무시설"
    return "업무시설"
