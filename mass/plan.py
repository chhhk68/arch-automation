# -*- coding: utf-8 -*-
"""계획설계(SD) 개략 평면 → DXF 내보내기 모듈 (SD ver2)

프론트엔드에서 생성한 층별 실(室) 사각형 목록을 받아 AutoCAD R12(AC1009)
DXF로 변환한다. 층 평면들은 좌→우로 나란히 배치된다.

입력 형식 (JSON):
  floors: [{floor:1, label:"1F 근린생활시설", bw:20.0, bd:12.0,
            rooms:[{name:"세대 84.0㎡", cat:"unit", x:0,y:0,w:8.4,h:10.2}]}]
  - 좌표계: 프론트(SVG)와 동일하게 y가 아래로 증가 → DXF에서 y축 반전 처리
"""

# 실 분류 → DXF 레이어/색상 (AutoCAD color index)
_CAT_LAYER = {
    "core":  ("CORE",     1),   # 빨강
    "corr":  ("CORRIDOR", 2),   # 노랑
    "lobby": ("LOBBY",    6),   # 마젠타
    "retail":("RETAIL",   3),   # 초록
    "mech":  ("MECH",     8),   # 회색
    "unit":  ("UNIT",     5),   # 파랑
    "park":  ("PARKING",  4),   # 청록 (주차 구획)
    "ramp":  ("RAMP",    30),   # 주황 (주차 램프)
    "aisle": ("AISLE",    9),   # 밝은 회색 (차로)
}
_GAP = 8.0          # 층 평면 사이 간격 (m)
_TEXT_H = 0.45      # 실명 문자 높이 (m)
_TITLE_H = 1.0      # 층 제목 문자 높이 (m)


def _e(code, value):
    """DXF 그룹코드 한 쌍"""
    return f"{code}\n{value}\n"


def _polyline(layer, pts, closed=True):
    s = _e(0, "POLYLINE") + _e(8, layer) + _e(66, 1) + _e(70, 1 if closed else 0)
    for (x, y) in pts:
        s += _e(0, "VERTEX") + _e(8, layer) + _e(10, round(x, 3)) + _e(20, round(y, 3))
    s += _e(0, "SEQEND")
    return s


def _text(layer, x, y, h, content):
    return (_e(0, "TEXT") + _e(8, layer) +
            _e(10, round(x, 3)) + _e(20, round(y, 3)) +
            _e(40, h) + _e(1, content))


def plan_to_dxf(floors: list, title: str = "") -> bytes:
    """층별 평면 목록 → DXF 바이트(cp949 — 한글 AutoCAD 호환)"""
    ents = ""
    ox = 0.0
    for f in floors:
        bw = float(f.get("bw", 0) or 0)
        bd = float(f.get("bd", 0) or 0)
        if bw <= 0 or bd <= 0:
            continue
        # 층 제목
        ents += _text("TITLE", ox, bd + 1.2, _TITLE_H, str(f.get("label", "")))
        # 외곽선
        ents += _polyline("OUTLINE", [(ox, 0), (ox + bw, 0), (ox + bw, bd), (ox, bd)])
        # 실 (y축 반전: SVG y-down → DXF y-up)
        for r in f.get("rooms", []):
            try:
                x = float(r["x"]); y = float(r["y"])
                w = float(r["w"]); h = float(r["h"])
            except (KeyError, TypeError, ValueError):
                continue
            layer, _ci = _CAT_LAYER.get(str(r.get("cat", "unit")), _CAT_LAYER["unit"])
            dy = bd - y - h              # 반전된 하단 y
            ents += _polyline(layer, [(ox + x, dy), (ox + x + w, dy),
                                      (ox + x + w, dy + h), (ox + x, dy + h)])
            name = str(r.get("name", ""))
            if name and w > 1.2 and h > 1.0:
                ents += _text("TEXT", ox + x + 0.3, dy + h / 2 - _TEXT_H / 2,
                              _TEXT_H, name)
        ox += bw + _GAP

    if title:
        ents = _text("TITLE", 0, -3.0, _TITLE_H, title) + ents

    # 레이어 테이블 (색상 지정)
    layers = ""
    layer_defs = ([("OUTLINE", 7), ("TITLE", 7), ("TEXT", 7)] +
                  [v for v in _CAT_LAYER.values()])
    for (nm, ci) in layer_defs:
        layers += (_e(0, "LAYER") + _e(2, nm) + _e(70, 0) +
                   _e(62, ci) + _e(6, "CONTINUOUS"))

    dxf = (
        _e(0, "SECTION") + _e(2, "HEADER") +
        _e(9, "$ACADVER") + _e(1, "AC1009") +
        _e(0, "ENDSEC") +
        _e(0, "SECTION") + _e(2, "TABLES") +
        _e(0, "TABLE") + _e(2, "LAYER") + _e(70, len(layer_defs)) +
        layers +
        _e(0, "ENDTAB") + _e(0, "ENDSEC") +
        _e(0, "SECTION") + _e(2, "ENTITIES") +
        ents +
        _e(0, "ENDSEC") + _e(0, "EOF")
    )
    return dxf.encode("cp949", errors="replace")
