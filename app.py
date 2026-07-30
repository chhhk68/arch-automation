from flask import Flask, render_template, request, jsonify, send_file, make_response
import os, json, urllib.request, urllib.parse, base64, math, re
import xml.etree.ElementTree as ET
from pathlib import Path
from mass.site import Site
from mass.regulations import ZONING, FLOOR_HEIGHT, detect_region
from mass.parcel import lookup
from mass.exporter import export_obj, export_ifc
from mass.zone_use import (get_zone_uses, calc_parking, calc_landscape,
                            calc_public_space, default_use_type_for_zone)
from mass.plan import plan_to_dxf

app = Flask(__name__)
BASE_DIR   = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "output"

_state: dict = {}

ZONE_CODE_MAP = {
    "UQA110": "제1종전용주거지역", "UQA120": "제2종전용주거지역",
    "UQA131": "제1종일반주거지역", "UQA132": "제2종일반주거지역",
    "UQA133": "제3종일반주거지역", "UQA140": "준주거지역",
    "UQA210": "중심상업지역",      "UQA220": "일반상업지역",
    "UQA230": "근린상업지역",      "UQA240": "유통상업지역",
    "UQA310": "전용공업지역",      "UQA320": "일반공업지역",
    "UQA330": "준공업지역",        "UQA410": "보전녹지지역",
    "UQA420": "생산녹지지역",      "UQA430": "자연녹지지역",
}

# ── 도로접면 코드/이름 → 대표 폭(m) 매핑 ─────────────────────────────────
# 개별공시지가 산정기준 도로접면 분류 (국토교통부 고시)
#   광대로: 25m 이상 / 중로: 12~25m / 소로: 8~12m / 세로: 4~8m / 세로(불): <4m 또는 막힘
_ROAD_SIDE_WIDTH: dict = {
    # 숫자 코드 (VWorld ned/data 반환값)
    "0": 0, "1": 3, "2": 6, "3": 6,
    "4": 10, "5": 10, "6": 15, "7": 15, "8": 25, "9": 25,
    # 한글 이름
    "맹지": 0, "세로(불)": 3,
    "세로한면": 6, "세로각지": 6,
    "소로한면": 10, "소로각지": 10,
    "중로한면": 15, "중로각지": 15,
    "광대한면": 25, "광대각지": 25,
    "광대로한면": 25, "광대로각지": 25,
}


def _get_land_char(pnu: str, attr_key: str, luris_key: str = "") -> dict:
    """토지특성 조회 — VWorld ned/data getLandCharInfo → LURIS 순
    반환: land_category, road_side_code, road_side_name, land_shape,
           topography, official_price(원/m²), area_reg(m²), source
    """
    # 1) VWorld ned/data getLandCharacteristics
    #    ⚠️ 기존 'getLandCharInfo'는 존재하지 않는 엔드포인트(URL_TYPE 에러)라 항상
    #    실패해 지목·공시지가가 빈 값으로 나갔음(토지이음과 상이의 원인 중 하나).
    #    또한 이 API는 "연도별(stdrYear)" 레코드를 여러 개 반환하므로 최신 연도를
    #    선택해야 한다(첫 레코드가 2013년인 경우 확인됨 → 옛 공시지가 방지).
    if attr_key and pnu:
        try:
            url = ("https://api.vworld.kr/ned/data/getLandCharacteristics?" +
                   urllib.parse.urlencode({
                       "key": attr_key, "pnu": pnu,
                       "numOfRows": "60", "format": "json",
                   }))
            req = urllib.request.Request(url, headers={"User-Agent": "arch-automation/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                d = json.loads(resp.read().decode("utf-8"))
            # 응답 키: landCharacteristicss (오타 아님 — 실제 API 키명)
            flist = (d.get("landCharacteristicss", {}).get("field") or
                     d.get("landCharacteristics", {}).get("field") or
                     d.get("result", {}).get("field") or [])
            if flist:
                if isinstance(flist, dict):
                    flist = [flist]
                # 최신 기준연도(stdrYear) 레코드 선택
                f = max(flist, key=lambda r: str(r.get("stdrYear", "")))
                return {
                    "land_category": f.get("ldCategoryName") or f.get("lndcgrCodeNm", ""),
                    "road_side_code": str(f.get("roadSideCode") or f.get("rdstCode", "")),
                    "road_side_name": (f.get("roadSideName") or f.get("roadSideCodeNm")
                                       or f.get("rdstCodeNm", "")),
                    "land_shape":     (f.get("landShapeName") or f.get("lndpclShpCodeNm")
                                       or f.get("tpgrphFrmCodeNm", "")),
                    "topography":     (f.get("topogrphyName") or f.get("tpgrphHgCodeNm", "")),
                    "official_price": str(f.get("officialLandPrice") or f.get("pblntfPclnd", "")),
                    "area_reg":       str(f.get("lndpclAr") or f.get("lnpclAr", "")),
                    "std_year":       str(f.get("stdrYear", "")),
                    "source": "VWorld",
                }
        except Exception:
            pass

    # 2) LURIS LandCharService2
    if luris_key and pnu:
        try:
            url = ("https://apis.data.go.kr/1611000/nsdi/LandCharService2/wfs/getLandChar?" +
                   urllib.parse.urlencode({
                       "serviceKey": luris_key, "pnu": pnu,
                       "numOfRows": "1", "format": "json",
                   }))
            req = urllib.request.Request(url, headers={"User-Agent": "arch-automation/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                d = json.loads(resp.read().decode("utf-8"))
            items = d.get("result", {}).get("items", None)
            if items:
                raw = items if isinstance(items, list) else items.get("item", [])
                item = (raw[0] if isinstance(raw, list) and raw
                        else raw if isinstance(raw, dict) else {})
                if item:
                    return {
                        "land_category": item.get("lndcgrCodeNm", ""),
                        "road_side_code": str(item.get("rdstCode", "")),
                        "road_side_name": item.get("rdstCodeNm", ""),
                        "land_shape":     item.get("tpgrphFrmCodeNm", ""),
                        "topography":     item.get("tpgrphHgCodeNm", ""),
                        "official_price": str(item.get("pblntfPclnd", "")),
                        "area_reg":       str(item.get("lnpclAr", "")),
                        "source": "LURIS",
                    }
        except Exception:
            pass

    return {}


def _osm_road_width(lon: float, lat: float) -> tuple:
    """OSM Overpass API — 인접 도로 폭(m)·도로명 추정
    Returns: (width_m: float, road_name: str)
    """
    try:
        cos_lat = math.cos(math.radians(lat))
        r = 40 / 111320   # ~40m 반경 (약간 확대하여 소규모 도로 포함)
        bbox = f"{lat-r},{lon-r/cos_lat},{lat+r},{lon+r/cos_lat}"
        query = f'[out:json][timeout:8];way["highway"]({bbox});out tags;'
        req = urllib.request.Request(
            "https://overpass-api.de/api/interpreter",
            data=("data=" + urllib.parse.quote(query)).encode(),
            headers={"Content-Type": "application/x-www-form-urlencoded",
                     "User-Agent": "arch-automation/1.0"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            d = json.loads(resp.read().decode())

        HW_WIDTH = {
            "motorway": 20, "trunk": 20,
            "primary": 15, "primary_link": 12,
            "secondary": 12, "secondary_link": 10,
            "tertiary": 8,  "tertiary_link": 6,
            "residential": 6, "unclassified": 5,
            "service": 4, "living_street": 3,
        }
        SKIP = {"footway", "path", "steps", "cycleway", "pedestrian", "track"}
        best_w, best_name = 4.0, ""
        for way in d.get("elements", []):
            tags = way.get("tags", {})
            hw = tags.get("highway", "")
            if hw in SKIP:
                continue
            name = tags.get("name:ko") or tags.get("name", "") or hw
            try:
                if "width" in tags:
                    w = float(str(tags["width"]).replace("m", "").split()[0])
                    if w > best_w:
                        best_w, best_name = w, name
                    continue
            except Exception:
                pass
            try:
                if "lanes" in tags:
                    w = int(tags["lanes"]) * 3.5
                    if w > best_w:
                        best_w, best_name = w, name
                    continue
            except Exception:
                pass
            if hw in HW_WIDTH and HW_WIDTH[hw] > best_w:
                best_w, best_name = float(HW_WIDTH[hw]), name

        return (best_w, best_name)
    except Exception:
        return (4.0, "")


# ── 건축선 후퇴 계산 (건축법 제46조, 동법 시행령 제31조) ───────────────────
def _calc_building_setback(road_width: float) -> dict:
    """전면도로 폭에 따른 건축선 후퇴 계산
    Returns: {required: bool, setback_m: float, basis: str}
    """
    if road_width < 4:
        return {
            "required": True,
            "setback_m": round((4 - road_width) / 2, 2),
            "basis": f"건축법§46 — 도로폭 {road_width}m 미만, 도로 중심선에서 2m 이상 건축선 지정",
        }
    elif road_width < 6:
        return {
            "required": True,
            "setback_m": round(road_width / 2 * 0.5, 2),   # ≈ 전면도로폭/2 × 최소비율
            "basis": f"건축법§46 — 도로폭 {road_width}m (4~6m 구간), 지자체 조례 확인 필요",
        }
    else:
        return {
            "required": False,
            "setback_m": 0.0,
            "basis": f"건축법§46 — 도로폭 {road_width}m (6m 이상), 건축선 후퇴 의무 없음",
        }


# ── 접도 요건 계산 (건축법 제44조) ────────────────────────────────────────
def _calc_road_access_requirement(gfa_limit: float, road_width: float) -> dict:
    """연면적·용도별 접도요건 (건축법 제44조)
    Returns: {min_road_width: float, ok: bool, note: str}
    """
    if gfa_limit >= 2000:
        req = 6.0
        ok = road_width >= req
        return {
            "min_road_width_m": req,
            "ok": ok,
            "note": f"연면적 2,000m² 이상 — 6m 이상 도로 접해야 함 (현재 {road_width}m {'✓' if ok else '✗ 부적합'})",
        }
    elif gfa_limit >= 500:
        req = 4.0
        ok = road_width >= req
        return {
            "min_road_width_m": req,
            "ok": ok,
            "note": f"연면적 500m² 이상 — 4m 이상 도로 접해야 함 (현재 {road_width}m {'✓' if ok else '✗ 부적합'})",
        }
    else:
        return {
            "min_road_width_m": 2.0,
            "ok": road_width >= 2.0,
            "note": "소규모 건축물 — 2m 이상 통로·도로 접도 (건축법§44 ①)",
        }


def _get_luris_land_use_detail(pnu: str, luris_key: str, attr_key: str = "") -> dict:
    """LURIS/VWorld 종합 토지이용규제 정보 조회
    Returns: {zones, districts, restrictions, source}
    zones: [{code, name, type, note}]
    """
    # 용도지역 코드 → 구분 분류
    ZONE_TYPE = {
        "UQA1": "주거지역", "UQA2": "상업지역",
        "UQA3": "공업지역", "UQA4": "녹지지역",
    }
    # 규제 유형 분류 (코드 prefix)
    RESTRICTION_PREFIX = {
        "UQB": "용도지구", "UQC": "용도구역", "UQD": "지구단위계획구역",
        "UQE": "개발행위허가제한", "UQF": "농업진흥구역", "UQG": "보전산지",
        "UQH": "군사시설보호구역", "UQI": "자연환경보전지역", "UQJ": "수변구역",
    }

    zones, districts, restrictions = [], [], []

    # 1순위: LURIS getLandUseAttr (data.go.kr)
    if luris_key and pnu:
        try:
            url = ("https://apis.data.go.kr/1611000/nsdi/LandUseService2/wfs/getLandUse?" +
                   urllib.parse.urlencode({
                       "serviceKey": luris_key, "pnu": pnu,
                       "numOfRows": "100", "format": "json",
                   }))
            req = urllib.request.Request(url, headers={"User-Agent": "arch-automation/1.0"})
            with urllib.request.urlopen(req, timeout=12) as resp:
                d = json.loads(resp.read().decode("utf-8"))

            items_raw = d.get("result", {}).get("items", None)
            if items_raw:
                if isinstance(items_raw, list):
                    item_list = items_raw
                elif isinstance(items_raw, dict):
                    raw = items_raw.get("item", [])
                    item_list = [raw] if isinstance(raw, dict) else (raw or [])
                else:
                    item_list = []

                for item in item_list:
                    code = str(item.get("lhCd", ""))
                    name = str(item.get("lhNm", ""))
                    cnflc = item.get("cnflcAt", "1") == "1"  # 포함(1)/인접(0)

                    # 용도지역 (UQA)
                    if code.startswith("UQA"):
                        ztype = ZONE_TYPE.get(code[:4], "기타지역")
                        zones.append({"code": code, "name": name, "type": ztype,
                                       "contained": cnflc})
                    # 용도지구/구역 (UQB~)
                    elif any(code.startswith(p) for p in RESTRICTION_PREFIX):
                        rtype = next((v for k, v in RESTRICTION_PREFIX.items()
                                      if code.startswith(k)), "기타규제")
                        restrictions.append({"code": code, "name": name,
                                              "type": rtype, "contained": cnflc})
                    else:
                        districts.append({"code": code, "name": name,
                                           "contained": cnflc})

                if zones or restrictions or districts:
                    return {"zones": zones, "districts": districts,
                            "restrictions": restrictions, "source": "LURIS"}
        except Exception:
            pass

    # 2순위: VWorld ned/data getLandUseAttr
    if attr_key and pnu:
        try:
            url = ("https://api.vworld.kr/ned/data/getLandUseAttr?" +
                   urllib.parse.urlencode({
                       "key": attr_key, "pnu": pnu,
                       "numOfRows": "100", "output": "json",
                   }))
            req = urllib.request.Request(url, headers={"User-Agent": "arch-automation/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                d = json.loads(resp.read().decode("utf-8"))

            fields = d.get("landUses", {}).get("field", [])
            if isinstance(fields, dict):
                fields = [fields]
            for f in fields:
                code = str(f.get("prposAreaDstrcCode", ""))
                name = str(f.get("prposAreaDstrcCodeNm", ""))
                cnflc = str(f.get("cnflcAt", "1")) == "1"
                if not code and not name:
                    continue
                if code.startswith("UQA"):
                    zones.append({"code": code, "name": name,
                                   "type": ZONE_TYPE.get(code[:4], "기타"), "contained": cnflc})
                elif code:
                    restrictions.append({"code": code, "name": name,
                                          "type": "규제", "contained": cnflc})
            if zones or restrictions:
                return {"zones": zones, "districts": districts,
                        "restrictions": restrictions, "source": "VWorld ned"}
        except Exception:
            pass

    return {"zones": zones, "districts": districts,
            "restrictions": restrictions, "source": ""}


# 1×1 투명 PNG (타일 로드 실패 시 플레이스홀더)
_EMPTY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
)


# config.json 키 ↔ 환경변수 이름 매핑 (GitHub Codespaces Secrets 등에서 주입)
_ENV_KEYS = {
    "vworld_key":      "VWORLD_KEY",
    "vworld_attr_key": "VWORLD_ATTR_KEY",
    "vworld_wfs_key":  "VWORLD_WFS_KEY",
    "luris_key":       "LURIS_KEY",
}


def _cfg() -> dict:
    """API 키 설정을 반환.
    우선순위: config.json(로컬 파일) → 없거나 비어있는 항목은 환경변수로 보완.
    Codespaces 등 config.json이 없는 환경에서는 환경변수만으로 동작한다.
    """
    cfg = {}
    p = BASE_DIR / "config.json"
    if p.exists():
        try:
            cfg = json.loads(p.read_text(encoding="utf-8")) or {}
        except Exception:
            cfg = {}
    for k, env_name in _ENV_KEYS.items():
        if not cfg.get(k):
            v = os.environ.get(env_name, "").strip()
            if v:
                cfg[k] = v
    return cfg


# 설정(API 키) 관리 대상 항목 — 표시 라벨과 용도 설명
_CONFIG_KEYS = [
    ("vworld_key",      "VWorld 지도/타일 키",   "지도 타일·지오코딩·용도지역 조회에 사용"),
    ("vworld_attr_key", "VWorld 속성(WFS) 키",   "용도지역·지구 속성 조회 (미설정 시 vworld_key 사용)"),
    ("vworld_wfs_key",  "VWorld WFS 키",         "주변 건물(WFS) 조회 (미설정 시 vworld_key 사용)"),
    ("luris_key",       "토지이용규제(LURIS) 키", "토지이용계획 규제사항 조회"),
]


def _mask_key(v: str) -> str:
    """API 키를 마스킹해 노출 최소화 (뒤 4자리만 표시)."""
    if not v:
        return ""
    v = str(v)
    return ("•" * max(0, len(v) - 4)) + v[-4:] if len(v) > 4 else "•" * len(v)


# ─── Routes ────────────────────────────────────────────────────────────────


@app.route("/api/config", methods=["GET"])
def api_config_get():
    """현재 설정된 API 키 목록을 마스킹해 반환 (localhost 전용 관리 UI용)."""
    cfg = _cfg()
    items = [{
        "key":   k,
        "label": label,
        "desc":  desc,
        "set":   bool(cfg.get(k)),
        "masked": _mask_key(cfg.get(k, "")),
    } for (k, label, desc) in _CONFIG_KEYS]
    return jsonify({"items": items})


@app.route("/api/config", methods=["POST"])
def api_config_set():
    """전달된 키 값만 config.json에 저장 (빈 값은 무시 → 기존 값 유지)."""
    data = request.get_json(silent=True) or {}
    allowed = {k for (k, _l, _d) in _CONFIG_KEYS}
    try:
        cfg = _cfg()
    except Exception:
        cfg = {}
    changed = []
    for k, v in data.items():
        if k in allowed and isinstance(v, str) and v.strip():
            cfg[k] = v.strip()
            changed.append(k)
    if changed:
        (BASE_DIR / "config.json").write_text(
            json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    return jsonify({"ok": True, "changed": changed})


@app.route("/api/roads")
def api_roads():
    """주변 도로 중심선 (OSM Overpass) — 3D 도로선 오버레이용.
    ESRI World_Transportation 타일은 한국 도로 커버리지가 빈약해 실제 OSM 도로
    geometry를 폴리라인으로 반환한다. (도로선 on/off 기능의 데이터 소스)"""
    try:
        lat = float(request.args.get("lat", 0))
        lon = float(request.args.get("lon", 0))
        r   = min(float(request.args.get("r", 400)), 800)
    except ValueError:
        return jsonify({"roads": []})
    if not lat or not lon:
        return jsonify({"roads": []})
    try:
        cos_lat = math.cos(math.radians(lat))
        dr = r / 111320
        bbox = f"{lat-dr},{lon-dr/cos_lat},{lat+dr},{lon+dr/cos_lat}"
        query = f'[out:json][timeout:10];way["highway"]({bbox});out geom;'
        req = urllib.request.Request(
            "https://overpass-api.de/api/interpreter",
            data=("data=" + urllib.parse.quote(query)).encode(),
            headers={"Content-Type": "application/x-www-form-urlencoded",
                     "User-Agent": "arch-automation/1.0"},
            method="POST")
        with urllib.request.urlopen(req, timeout=12) as resp:
            d = json.loads(resp.read().decode())
        SKIP = {"footway", "path", "steps", "cycleway", "pedestrian", "track"}
        MAJOR = {"motorway", "trunk", "primary", "secondary"}
        roads = []
        for way in d.get("elements", []):
            tags = way.get("tags", {})
            hw = tags.get("highway", "")
            if hw in SKIP:
                continue
            geom = way.get("geometry") or []
            if len(geom) < 2:
                continue
            roads.append({
                "name":  tags.get("name:ko") or tags.get("name", ""),
                "major": hw in MAJOR,
                "coords": [[nd["lon"], nd["lat"]] for nd in geom],
            })
        return jsonify({"roads": roads})
    except Exception as e:
        return jsonify({"roads": [], "error": str(e)})

@app.route("/")
def index():
    cfg = _cfg()
    luris_key = cfg.get("luris_key", "")
    return render_template("index.html",
                           zones=list(ZONING.keys()),
                           vworld_key=cfg.get("vworld_key", ""),
                           luris_key=luris_key,
                           has_luris=bool(luris_key),
                           parking_types=list(__import__(
                               "mass.zone_use", fromlist=["PARKING_STD"]).PARKING_STD.keys()))


@app.route("/api/parcel", methods=["POST"])
def api_parcel():
    data = request.get_json() or {}
    address = data.get("address", "").strip()
    if not address:
        return jsonify({"error": "주소를 입력하세요"}), 400
    try:
        cfg = _cfg()
        info = lookup(address, cfg.get("vworld_key", ""))

        attr_key  = cfg.get("vworld_attr_key", "").strip()
        luris_key = cfg.get("luris_key", "").strip()

        # ── 토지특성 조회 (지목·도로접면·공시지가·형상·지세) ──────────────
        land_char = _get_land_char(info.pnu, attr_key, luris_key) if info.pnu else {}

        # ── 대지면적: 토지대장 면적(lndpclAr — 토지이음 표기 기준) 우선 ─────
        #    지적 폴리곤 계산/도형 면적은 대장 면적과 수 % 차이가 날 수 있어
        #    공부(公簿) 기준인 대장 면적으로 보정 (토지이음과 일치)
        try:
            reg_area = float(land_char.get("area_reg") or 0)
            if reg_area > 0:
                info.area = round(reg_area, 1)
        except (TypeError, ValueError):
            pass

        # ── 토지이용규제 상세 조회 (LURIS/VWorld ned) ──────────────────────
        land_use_detail = {}
        if info.pnu:
            try:
                land_use_detail = _get_luris_land_use_detail(
                    info.pnu, luris_key, attr_key)
            except Exception:
                pass

        # ── 용도지역 확정: PNU 기반 토지이용계획(토지이음과 동일 원천 NSDI)에서
        #    세부 용도지역명을 추출 — 좌표점 기반 감지보다 정확 (경계 필지 오판 방지)
        #    '도시지역' 같은 대분류(UQA001~) 말고 세부 지역(제1종일반주거지역 등) 우선.
        if not info.zone and land_use_detail.get("zones"):
            detail_zone = ""
            for zrec in land_use_detail["zones"]:
                znm = zrec.get("name", "")
                if not zrec.get("contained", True):
                    continue
                if znm in ZONING:                    # 세부 용도지역 (규제 테이블 보유)
                    detail_zone = znm
                    break
                if not detail_zone and znm.endswith("지역") and znm not in (
                        "도시지역", "관리지역", "농림지역", "자연환경보전지역"):
                    detail_zone = znm                # 세부명이지만 테이블 미보유 → 일단 채택
            if detail_zone:
                info.zone = detail_zone

        # ── 전면도로폭 자동 감지 (우선순위: 도로접면코드 > OSM 실측값) ────
        road_width = 4.0
        road_width_source = "기본값(4m)"
        rsc = land_char.get("road_side_code", "")
        rsn = land_char.get("road_side_name", "")

        if rsc in _ROAD_SIDE_WIDTH:
            road_width = float(_ROAD_SIDE_WIDTH[rsc])
            road_width_source = f"도로접면 {rsn or rsc} ({land_char.get('source','')})"
        elif rsn in _ROAD_SIDE_WIDTH:
            road_width = float(_ROAD_SIDE_WIDTH[rsn])
            road_width_source = f"도로접면 {rsn} ({land_char.get('source','')})"
        else:
            # OSM Overpass fallback — 실제 도로 태그에서 폭 추정
            try:
                osm_w, osm_name = _osm_road_width(info.lon, info.lat)
                road_width = osm_w
                road_width_source = f"OSM{(' ' + osm_name) if osm_name else ''}"
            except Exception:
                pass

        # ── 건축선 후퇴 계산 (건축법 §46) ───────────────────────────────
        bldg_setback = _calc_building_setback(road_width)

        return jsonify({
            "address": info.address, "pnu":     info.pnu,
            "area":    info.area,    "width":   info.width,
            "depth":   info.depth,   "zone":    info.zone,
            "lon":     info.lon,     "lat":     info.lat,
            "mid_lon": info.mid_lon, "mid_lat": info.mid_lat,
            "polygon": info.polygon or [],
            "road_width":        road_width,
            "road_width_source": road_width_source,
            "land_char":         land_char,       # 토지특성 (지목·도로접면·공시지가)
            "land_use_detail":   land_use_detail, # LURIS 종합 규제 정보
            "bldg_setback":      bldg_setback,    # 건축선 후퇴 (건축법§46)
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/zone_detect", methods=["POST"])
def api_zone_detect():
    data = request.get_json() or {}
    try:
        lon = float(data["lon"])
        lat = float(data["lat"])
    except (KeyError, TypeError, ValueError):
        return jsonify({"zone": "", "status": "invalid_coords"})

    cfg = _cfg()
    api_key   = cfg.get("vworld_key", "")
    luris_key = cfg.get("luris_key", "").strip()
    attr_key  = cfg.get("vworld_attr_key", "").strip()
    wfs_key   = cfg.get("vworld_wfs_key",  "").strip()

    # 1순위: 공공데이터포털 LURIS API
    if luris_key:
        zone = _try_luris_zone(lon, lat, luris_key)
        if zone:
            uses = get_zone_uses(zone)
            return jsonify({"zone": zone, "status": "ok",
                            "uses": uses, "source": "LURIS"})

    # 2순위: VWorld 토지이용계획 전용키 (속성조회 → WFS 순)
    if attr_key or wfs_key:
        zone = _try_vworld_landuse(lon, lat, attr_key, wfs_key)
        if zone:
            uses = get_zone_uses(zone)
            return jsonify({"zone": zone, "status": "ok",
                            "uses": uses, "source": "VWorld(전용키)"})

    # 3순위: VWorld 일반 APP 키 (권한 제한)
    zone = _try_vworld_zone(lon, lat, api_key)
    if zone:
        uses = get_zone_uses(zone)
        return jsonify({"zone": zone, "status": "ok",
                        "uses": uses, "source": "VWorld"})

    has_any = bool(luris_key or attr_key or wfs_key)
    return jsonify({
        "zone": "",
        "status": "manual_required",
        "has_luris": has_any,
        "message": ("API 응답 없음 — 토지이음에서 직접 확인하세요" if has_any
                    else "API 키 미설정 — config.json에 vworld_attr_key 입력 필요"),
        "eum_url": "https://www.eum.go.kr/web/am/amList.do",
    })


def _try_luris_zone(lon: float, lat: float, luris_key: str) -> str:
    """공공데이터포털 국토교통부 토지이용계획정보서비스(LURIS) API"""
    try:
        # serviceKey는 data.go.kr에서 발급한 Encoding 키 그대로 사용
        url = ("https://apis.data.go.kr/1611000/nsdi/LandUseService2/wfs/getLandUse?"
               f"serviceKey={luris_key}&x={lon}&y={lat}"
               "&srid=4326&numOfRows=10&format=json")
        req = urllib.request.Request(
            url, headers={"User-Agent": "arch-automation/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            d = json.loads(resp.read().decode("utf-8"))

        # 응답 파싱: result.items.item (단건이면 dict, 복수면 list)
        items_raw = d.get("result", {}).get("items", None)
        if not items_raw:
            return ""
        if isinstance(items_raw, list):
            item_list = items_raw
        elif isinstance(items_raw, dict):
            raw = items_raw.get("item", [])
            item_list = [raw] if isinstance(raw, dict) else (raw or [])
        else:
            return ""

        for item in item_list:
            lh_cd = str(item.get("lhCd", ""))
            lh_nm = str(item.get("lhNm", ""))
            # 코드 직접 매칭
            if lh_cd in ZONE_CODE_MAP:
                return ZONE_CODE_MAP[lh_cd]
            # 이름 매칭
            for zone_name in ZONING:
                if zone_name == lh_nm or zone_name in lh_nm:
                    return zone_name
    except Exception:
        pass
    return ""


# ─── VWorld 토지이용계획 전용키 (속성조회 / WFS) ──────────────────────────

def _try_vworld_landuse(lon: float, lat: float, attr_key: str, wfs_key: str) -> str:
    """V-WORLD 토지이용계획 전용키 — ned/data/getLandUseAttr (PNU 기반) 우선"""
    # 1단계: VWorld 역지오코딩으로 좌표 → PNU 변환
    pnu = _reverse_geocode_pnu(lon, lat)

    # 2단계: ned/data 속성조회 키로 용도지역 조회
    if attr_key and pnu:
        z = _try_ned_landuse(pnu, attr_key)
        if z:
            return z

    # 3단계: 10자리 법정동코드만으로 재시도 (부번 오류 대비)
    if attr_key and pnu and len(pnu) >= 10:
        z = _try_ned_landuse(pnu[:10], attr_key)
        if z:
            return z

    # 4단계: WFS — lt_c_lhzone (EPSG:3857 bbox)
    if wfs_key:
        z = _try_vworld_wfs(lon, lat, wfs_key)
        if z:
            return z

    return ""


def _reverse_geocode_pnu(lon: float, lat: float) -> str:
    """VWorld 역지오코딩으로 좌표 → 19자리 PNU 변환"""
    try:
        from .mass.parcel import lookup as _lu  # noqa: 사용 안 함
    except Exception:
        pass
    try:
        # VWorld 주소 역변환 API
        cfg = _cfg()
        key = cfg.get("vworld_key", "")
        url = (f"https://api.vworld.kr/req/address?"
               f"service=address&request=getAddress&version=2.0"
               f"&crs=EPSG:4326&point={lon},{lat}&type=parcel&format=json&key={key}")
        req = urllib.request.Request(url, headers={"User-Agent": "arch-automation/1.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            d = json.loads(resp.read().decode("utf-8"))
        result = d.get("response", {}).get("result", [])
        if not result:
            return ""
        st = result[0].get("structure", {})
        dong_cd  = st.get("level4LC", "")  # 법정동코드 10자리
        lot_raw  = st.get("level5", "")    # 지번 (예: "31", "31-2")
        detail   = st.get("detail", "")
        if not dong_cd or not lot_raw:
            return ""
        # 본번/부번 분리
        parts   = lot_raw.split("-") if "-" in lot_raw else [lot_raw, "0"]
        main_no = parts[0].strip().zfill(4)
        sub_no  = (parts[1].strip() if len(parts) > 1 else (detail.strip() or "0")).zfill(4)
        # PNU = 법정동코드(10) + 지목(1) + 본번(4) + 부번(4)
        pnu = dong_cd + "1" + main_no + sub_no
        return pnu
    except Exception:
        return ""


def _try_ned_landuse(pnu: str, attr_key: str) -> str:
    """ned/data/getLandUseAttr — PNU로 용도지역 UQA 코드 조회"""
    try:
        url = ("https://api.vworld.kr/ned/data/getLandUseAttr?" +
               urllib.parse.urlencode({
                   "key": attr_key, "pnu": pnu,
                   "numOfRows": "100", "output": "json",
               }))
        req = urllib.request.Request(url, headers={"User-Agent": "arch-automation/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            d = json.loads(resp.read().decode("utf-8"))
        fields = d.get("landUses", {}).get("field", [])
        # UQA 코드(용도지역)만 선별, 포함(cnflcAt=1) 우선
        uqa_items = [f for f in fields
                     if str(f.get("prposAreaDstrcCode", "")).startswith("UQA")]
        # 포함 우선 정렬
        uqa_items.sort(key=lambda f: (0 if f.get("cnflcAt") == "1" else 1))
        for item in uqa_items:
            code = str(item.get("prposAreaDstrcCode", ""))
            name = str(item.get("prposAreaDstrcCodeNm", ""))
            if code in ZONE_CODE_MAP:
                return ZONE_CODE_MAP[code]
            for zone_name in ZONING:
                if zone_name == name or zone_name in name:
                    return zone_name
    except Exception:
        pass
    return ""


def _try_vworld_wfs(lon: float, lat: float, key: str) -> str:
    """V-WORLD WFS — lt_c_lhzone, EPSG:3857 bbox"""
    import math
    # 좌표 → EPSG:3857 변환
    x = lon * 20037508.34 / 180.0
    y = math.log(math.tan(math.pi / 4 + lat * math.pi / 360)) * 6378137.0
    d = 3000  # 3km 반경 (넓게)
    bbox = f"{x-d},{y-d},{x+d},{y+d},EPSG:3857"

    for tn in ["lt_c_lhzone", "lt_c_lhelmm"]:
        try:
            url = "https://api.vworld.kr/req/wfs?" + urllib.parse.urlencode({
                "service": "WFS", "version": "2.0.0",
                "request": "GetFeature", "typeName": tn,
                "key": key, "bbox": bbox,
                "outputFormat": "application/json",
                "count": "10",
            })
            req = urllib.request.Request(
                url, headers={"User-Agent": "arch-automation/1.0"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                content = resp.read().decode("utf-8")
            if content.strip().startswith("<"):
                continue
            dr = json.loads(content)
            for feat in dr.get("features", []):
                props = feat.get("properties", {})
                # lt_c_lhzone: zonecode, zonename 필드
                code = str(props.get("zonecode", ""))
                name = str(props.get("zonename", ""))
                if code in ZONE_CODE_MAP:
                    return ZONE_CODE_MAP[code]
                for zone_name in ZONING:
                    if zone_name == name or zone_name in name:
                        return zone_name
                # fallback: 모든 값 순회
                for val in props.values():
                    v = str(val)
                    if v in ZONE_CODE_MAP:
                        return ZONE_CODE_MAP[v]
                    for zone_name in ZONING:
                        if zone_name in v:
                            return zone_name
        except Exception:
            continue
    return ""


def _try_vworld_zone(lon: float, lat: float, api_key: str) -> str:
    """VWorld DATA API 다중 전략 (APP 키 권한 제한으로 대부분 실패)"""
    deltas = [0.0003, 0.001, 0.003]
    layers = ["LT_C_LHELMM", "LT_C_LHZONE", "LT_C_UQYSM"]

    for layer in layers:
        filters = [f"POINT({lon} {lat})"]
        for d in deltas:
            filters.append(f"BOX({lon-d},{lat-d},{lon+d},{lat+d})")
        for gf in filters:
            try:
                url = "https://api.vworld.kr/req/data?" + urllib.parse.urlencode({
                    "request": "GetFeature", "data": layer,
                    "key": api_key, "geometry": "false", "attribute": "true",
                    "format": "json", "size": "5", "page": "1",
                    "geomFilter": gf, "crs": "EPSG:4326",
                })
                req = urllib.request.Request(
                    url, headers={"User-Agent": "arch-automation/1.0"})
                with urllib.request.urlopen(req, timeout=6) as resp:
                    dr = json.loads(resp.read().decode("utf-8"))
                if dr.get("response", {}).get("status", "") in ("ERROR", "NOT_FOUND"):
                    break  # 이 레이어는 접근 불가 → 다음 레이어
                features = (dr.get("response", {}).get("result", {})
                             .get("featureCollection", {}).get("features", []))
                for feat in features:
                    for val in feat.get("properties", {}).values():
                        v = str(val)
                        if v in ZONE_CODE_MAP:
                            return ZONE_CODE_MAP[v]
                        for zone_name in ZONING:
                            if zone_name in v:
                                return zone_name
            except Exception:
                continue
    return ""


# ─── 고도 격자 (Open-Topo-Data SRTM 30m — 무료, 인증 불필요) ───────────────
@app.route("/api/elevation", methods=["POST"])
def api_elevation():
    """n×n 격자 고도 데이터 반환 (대지 중심 기준 상대 고도 m)"""
    data     = request.get_json() or {}
    lat      = float(data.get("lat",    37.5665))
    lon      = float(data.get("lon",   126.9780))
    radius   = float(data.get("radius",  600.0))
    n        = min(int(data.get("n", 9)), 17)   # 최대 17×17=289 ≤ 100/req

    cos_lat = math.cos(math.radians(lat))
    locs = []
    for row in range(n):
        for col in range(n):
            dlat = (row / (n - 1) - 0.5) * 2 * radius / 111320
            dlon = (col / (n - 1) - 0.5) * 2 * radius / (111320 * cos_lat)
            locs.append(f"{lat + dlat:.6f},{lon + dlon:.6f}")

    elevs = []
    for i in range(0, len(locs), 100):
        batch = "|".join(locs[i : i + 100])
        try:
            url = f"https://api.opentopodata.org/v1/srtm30m?locations={batch}"
            req_obj = urllib.request.Request(
                url, headers={"User-Agent": "arch-automation/1.0"})
            with urllib.request.urlopen(req_obj, timeout=12) as resp:
                d = json.loads(resp.read().decode())
            elevs.extend([(r.get("elevation") or 0) for r in d.get("results", [])])
        except Exception:
            elevs.extend([0] * len(locs[i : i + 100]))

    base = min(elevs) if elevs else 0
    elevs_rel = [round(float(e) - base, 2) for e in elevs]
    return jsonify({"n": n, "radius": radius,
                    "base_elev": round(float(base), 1),
                    "elevs": elevs_rel})


# ─── 멀티소스 타일 프록시 ──────────────────────────────────────────────────
# layer 식별자 → (소스유형, URL패턴)
#   vworld  : VWorld WMTS  /{z}/{y}/{x}.png
#   esri    : ESRI ArcGIS  /{z}/{y}/{x}  (JPEG, 인증불필요)
#   osm     : OpenStreetMap /{z}/{x}/{y}.png  (x↔y 순서 다름!)
_TILE_SOURCES = {
    # ESRI World Imagery — 실제 위성사진, 무료
    "esri":       ("esri",   "https://server.arcgisonline.com/ArcGIS/rest/services/"
                             "World_Imagery/MapServer/tile/{z}/{y}/{x}"),
    # ESRI 도로선 오버레이 — 도로망 라인(World_Transportation), 한국 도로 포함, 투명 배경
    # (이전 World_Boundaries_and_Places는 경계·지명 위주라 한국 도로선이 거의 안 보였음)
    "esri_ref":   ("esri",   "https://server.arcgisonline.com/ArcGIS/rest/services/"
                             "Reference/World_Transportation/MapServer/tile/{z}/{y}/{x}"),
    # Carto Positron(light, 라벨 없음) — 라벨 없는 깔끔한 일반지도, OSM 기반이라 한국 고줌까지
    # 도로·건물 커버. VWorld Base는 라벨이 내장되어 라벨 on/off가 불가하므로, 라벨 없는
    # 이 베이스 + VWorld Hybrid 오버레이로 라벨을 토글할 수 있게 한다. (z/x/y 순서)
    # 일반 지도 베이스 — VWorld Base. 라벨 없는 베이스(Carto/ESRI Light Gray)는 한국
    # 고줌에서 'map data not yet available'로 빈 화면이 되어, 전국 전줌을 확실히 커버하는
    # VWorld Base로 되돌림(지도 표시 우선). (라벨 내장)
    "gray_base":  ("vworld", "Base"),
    # OSM 표준 지도
    "osm":        ("osm",    "https://tile.openstreetmap.org/{z}/{x}/{y}.png"),
    # AWS Terrain (Terrarium RGB 인코딩) — 무료, 인증 불필요, zoom 0-15
    # 인코딩: height(m) = (R*256 + G + B/256) - 32768
    "terrain":    ("terrain","https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"),
    # VWorld 레이어 (fallback)
    "vw_base":    ("vworld", "Base"),
    "vw_sat":     ("vworld", "Satellite"),
    "hybrid":     ("vworld", "Hybrid"),
    "base":       ("vworld", "Base"),
    "satellite":  ("vworld", "Satellite"),
    "midnight":   ("vworld", "midnight"),
}

@app.route("/api/tile/<layer>/<int:z>/<int:y>/<int:x>")
def api_tile(layer, z, y, x):
    """멀티소스 타일 프록시 — CORS 우회 & 캐싱"""
    src_type, src_val = _TILE_SOURCES.get(layer.lower(), ("vworld", "Hybrid"))

    if src_type == "esri":
        tile_url = src_val.format(z=z, y=y, x=x)
        referer  = "https://www.arcgis.com/"
    elif src_type == "osm":
        tile_url = src_val.format(z=z, x=x, y=y)   # OSM은 x/y 순서!
        referer  = "https://www.openstreetmap.org/"
    elif src_type == "terrain":
        tile_url = src_val.format(z=z, x=x, y=y)   # AWS: z/x/y 순서
        referer  = "https://www.mapzen.com/"
    else:  # vworld
        cfg = _cfg()
        key = cfg.get("vworld_key", "")
        # Satellite 레이어는 JPEG, 나머지(Base/Hybrid 등)는 PNG
        ext = "jpeg" if src_val.lower() in ("satellite",) else "png"
        tile_url = (f"https://api.vworld.kr/req/wmts/1.0.0/{key}"
                    f"/{src_val}/{z}/{y}/{x}.{ext}")
        referer  = "https://map.vworld.kr/"

    def _fetch(url, ref):
        req_obj = urllib.request.Request(
            url,
            headers={
                "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                               "AppleWebKit/537.36 (KHTML, like Gecko) "
                               "Chrome/120.0 Safari/537.36"),
                "Referer": ref,
                "Accept": "image/webp,image/apng,image/*,*/*;q=0.8",
            })
        with urllib.request.urlopen(req_obj, timeout=10) as resp:
            return resp.read(), resp.headers.get("Content-Type", "image/jpeg")

    def _ok(data, ct, cache="public, max-age=86400"):
        response = make_response(data)
        response.headers["Content-Type"]  = ct
        response.headers["Cache-Control"] = cache
        response.headers["Access-Control-Allow-Origin"] = "*"
        return response

    # ⚠️ VWorld는 커버리지 밖/스로틀 시 HTTP 200 + XML 에러 또는 예외를 반환한다.
    #    위성(satellite) 타일이 빠지면 globe 기본색(남색)이 그대로 노출되어
    #    "파란 사각형"으로 보이므로, 실패 시 ESRI World_Imagery(전세계 커버)로
    #    대체해 영상이 끊기지 않게 한다. 그 외 레이어는 투명 타일 폴백.
    _ESRI_SAT = ("https://server.arcgisonline.com/ArcGIS/rest/services/"
                 f"World_Imagery/MapServer/tile/{z}/{y}/{x}")
    tile_data, ct = None, ""
    try:
        tile_data, ct = _fetch(tile_url, referer)
    except Exception:
        tile_data = None
    if tile_data is None or not ct.lower().startswith("image"):
        if src_type == "vworld" and src_val.lower() == "satellite":
            try:
                tile_data, ct = _fetch(_ESRI_SAT, "https://www.arcgis.com/")
                if ct.lower().startswith("image"):
                    return _ok(tile_data, ct)
            except Exception:
                pass
        return _ok(_EMPTY_PNG, "image/png", "no-cache")
    return _ok(tile_data, ct)


@app.route("/api/check", methods=["POST"])
def api_check():
    data = request.get_json() or {}
    try:
        width    = float(data["width"])
        depth    = float(data["depth"])
        zone     = data["zone"]
        sn       = float(data.get("setback_n", 0.5))
        ss       = float(data.get("setback_s", 0.5))
        se       = float(data.get("setback_e", 0.5))
        sw_      = float(data.get("setback_w", 0.5))
        use_type = data.get("use_type") or default_use_type_for_zone(zone)
        actual_area = float(data.get("actual_area", 0)) or None
        parcel_polygon = data.get("parcel_polygon", [])
        # 지역별 조례 적용 — 주소에서 시·도 감지 (예: 대전 필지 → 대전광역시 도시계획조례)
        region = detect_region(data.get("address", "") or data.get("region", ""))

        site   = Site(width=width, depth=depth, zone=zone,
                      setback_n=sn, setback_s=ss, setback_e=se, setback_w=sw_,
                      actual_area=actual_area, region=region)  # 지적도 실제 면적 우선 사용
        result = site.check()
        fps    = result.floor_footprints()

        OUTPUT_DIR.mkdir(exist_ok=True)
        export_obj(fps, str(OUTPUT_DIR / "mass.obj"), parcel_polygon=parcel_polygon)
        export_ifc(fps, zone, str(OUTPUT_DIR / "mass.ifc"))

        regs         = site.regs
        actual_total = sum(w * d for (_, _, w, d) in fps)
        n_floors     = len(fps)

        parking   = calc_parking(actual_total, use_type)
        landscape = calc_landscape(site.area, zone, actual_total)
        pub_space = calc_public_space(site.area, actual_total, zone)
        zone_uses = get_zone_uses(zone)

        resp = {
            "site_area": actual_area if actual_area else site.area, "zone": zone,
            "bcr_limit": regs["bcr"],  "far_limit": regs["far"],
            "height_limit": regs["max_height"], "solar": regs["solar"],
            "max_floors_zone": regs.get("max_floors"),          # 용도지역 층수 제한 (예: 1종일반 4층)
            "floors_basis": regs.get("floors_basis", ""),
            "floors_note": regs.get("floors_note", ""),         # 조례상 층수제한 가능성 안내
            "region": region,
            "ordinance": regs.get("ordinance", ""),
            "region_matched": regs.get("region_matched", False),
            "ordinance_verified": regs.get("ordinance_verified", False),
            "law_bcr_max": regs.get("law_bcr_max"),   # 상위법(시행령) 상한 — 보정 입력 클램프용
            "law_far_max": regs.get("law_far_max"),
            "max_ground_area":  result.max_ground_area,
            "max_total_area":   result.max_total_area,
            "actual_ground_area": result.actual_ground_area,
            "max_floors":  result.max_floors,
            "actual_total_area": actual_total,
            "actual_height": n_floors * FLOOR_HEIGHT,
            "floor_height":  FLOOR_HEIGHT,
            "footprints": [{"x0": x, "y0": y, "w": w, "d": d} for (x, y, w, d) in fps],
            "site": {"width": width, "depth": depth,
                     "setback_n": sn, "setback_s": ss,
                     "setback_e": se, "setback_w": sw_},
            "parking":   parking,
            "landscape": landscape,
            "pub_space": pub_space,
            "zone_uses": zone_uses,
            "use_type":  use_type,
        }
        _state.update(resp)
        return jsonify(resp)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/plan/dxf", methods=["POST"])
def api_plan_dxf():
    """계획설계 탭의 개략 평면(층별 실 목록) → DXF 도면 다운로드 (SD ver2)"""
    data = request.get_json(silent=True) or {}
    floors = data.get("floors", [])
    if not floors:
        return jsonify({"error": "평면 데이터가 없습니다"}), 400
    try:
        dxf_bytes = plan_to_dxf(floors, data.get("title", ""))
        OUTPUT_DIR.mkdir(exist_ok=True)
        p = OUTPUT_DIR / "plan_sd.dxf"
        p.write_bytes(dxf_bytes)
        return send_file(str(p.resolve()), as_attachment=True,
                         download_name="plan_sd.dxf",
                         mimetype="application/dxf")
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/export/<fmt>")
def api_export(fmt):
    paths = {"obj": OUTPUT_DIR / "mass.obj", "ifc": OUTPUT_DIR / "mass.ifc"}
    if fmt not in paths:
        return jsonify({"error": f"지원하지 않는 형식: {fmt}"}), 400
    p = paths[fmt]
    if not p.exists():
        return jsonify({"error": "먼저 법규 검토를 실행하세요"}), 404
    return send_file(str(p.resolve()), as_attachment=True, download_name=f"mass.{fmt}")


@app.route("/api/cadastral")
def api_cadastral():
    """VWorld LP_PA_CBND_BUBUN 연속지적도 경계 프록시
    주변 필지 경계 GeoJSON 반환 → CesiumJS 지적도 오버레이용
    """
    try:
        lat = float(request.args.get("lat", 37.5665))
        lon = float(request.args.get("lon", 126.9780))
        r   = float(request.args.get("r", 500))

        cos_lat = math.cos(math.radians(lat))
        d_lon   = r / (111320 * cos_lat)
        d_lat   = r / 111320
        bbox_str = f"BOX({lon-d_lon},{lat-d_lat},{lon+d_lon},{lat+d_lat})"

        cfg = _cfg()
        key = cfg.get("vworld_key", "")

        # 페이지네이션으로 최대 3페이지(1500 필지)까지 조회
        all_features_in = []
        seen_geoms = set()  # 중복 필지 제거용 간단 해시
        for _page in range(1, 4):
            url = "https://api.vworld.kr/req/data?" + urllib.parse.urlencode({
                "request":    "GetFeature",
                "data":       "LP_PA_CBND_BUBUN",
                "key":        key,
                "geometry":   "true",
                "attribute":  "false",
                "format":     "json",
                "size":       "500",
                "page":       str(_page),
                "geomFilter": bbox_str,
                "crs":        "EPSG:4326",
            })
            try:
                req_obj = urllib.request.Request(
                    url, headers={"User-Agent": "arch-automation/1.0"})
                with urllib.request.urlopen(req_obj, timeout=10) as resp:
                    raw = resp.read().decode("utf-8")
                page_data = json.loads(raw)
                page_feats = (page_data.get("response", {})
                                       .get("result", {})
                                       .get("featureCollection", {})
                                       .get("features", []))
                for feat in page_feats:
                    # 간단한 중복 제거: geometry 좌표 첫 점으로 해시
                    try:
                        coords0 = feat["geometry"]["coordinates"]
                        ring0 = coords0[0] if feat["geometry"]["type"]=="Polygon" else coords0[0][0]
                        key_ = (round(ring0[0][0],5), round(ring0[0][1],5))
                    except Exception:
                        key_ = None
                    if key_ is None or key_ not in seen_geoms:
                        if key_: seen_geoms.add(key_)
                        all_features_in.append(feat)
                if len(page_feats) < 500:
                    break  # 마지막 페이지
            except Exception:
                break  # 페이지 오류 시 중단

        features_in = all_features_in

        # GeoJSON FeatureCollection 변환
        out_features = []
        for feat in features_in:
            geom = feat.get("geometry")
            if not geom:
                continue
            out_features.append({
                "type": "Feature",
                "geometry": geom,
                "properties": feat.get("properties", {})
            })

        resp_obj = make_response(json.dumps(
            {"type": "FeatureCollection", "features": out_features},
            ensure_ascii=False))
        resp_obj.headers["Content-Type"] = "application/json; charset=utf-8"
        resp_obj.headers["Access-Control-Allow-Origin"] = "*"
        resp_obj.headers["Cache-Control"] = "public, max-age=300"
        return resp_obj

    except Exception as exc:
        return jsonify({"type": "FeatureCollection", "features": [],
                        "error": str(exc)}), 200


@app.route("/api/reverse-geocode")
def api_reverse_geocode():
    """VWorld 역지오코딩 서버사이드 프록시 (브라우저 CORS 우회)"""
    try:
        lat = float(request.args.get("lat", 37.5665))
        lon = float(request.args.get("lon", 126.9780))
        cfg = _cfg()
        key = cfg.get("vworld_key", "")
        url = "https://api.vworld.kr/req/address?" + urllib.parse.urlencode({
            "service": "address", "request": "getAddress", "version": "2.0",
            "crs": "epsg:4326", "point": f"{lon},{lat}",
            "type": "parcel", "format": "json", "key": key,
        })
        req_obj = urllib.request.Request(
            url, headers={"User-Agent": "arch-automation/1.0"})
        with urllib.request.urlopen(req_obj, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return jsonify(data)
    except Exception as exc:
        return jsonify({"response": {"status": "ERROR", "error": str(exc)}}), 200


@app.route("/api/buildings")
def api_buildings():
    """VWorld WFS lt_c_bldginfo 건물정보 프록시 → GeoJSON FeatureCollection 반환
    VWorld WFS 1.1.0 + EPSG:4326 도단위 bbox → GML XML 파싱 방식
    """
    try:
        lat = float(request.args.get("lat", 37.5665))
        lon = float(request.args.get("lon", 126.9780))
        r   = float(request.args.get("r",   800))

        # ── WGS84 도단위 bbox (WFS 1.1.0 + SRSNAME=EPSG:4326) ──────────────
        # WFS 1.1.0 EPSG:4326 축 순서: (lat, lon) = (Y, X)
        # bbox 형식: latMin,lonMin,latMax,lonMax
        d = r / 111320.0 * 1.3     # 미터 → 도(degree), 여유 1.3배
        bbox_4326 = f"{lat-d},{lon-d},{lat+d},{lon+d}"

        cfg = _cfg()
        key = cfg.get("vworld_wfs_key") or cfg.get("vworld_key", "")

        _wfs_headers = {"User-Agent": "arch-automation/1.0",
                        "Referer":    "https://map.vworld.kr/"}

        # ── GML XML → GeoJSON features 파싱 ────────────────────────────────
        def _parse_gml(xml_str: str) -> list:
            # 네임스페이스 URL 동적 추출
            ns_found = {}
            for m in re.finditer(r'xmlns:(\w+)="([^"]+)"', xml_str):
                ns_found[m.group(1)] = m.group(2)
            gml_ns = ns_found.get("gml", "http://www.opengis.net/gml")

            def _coords_text(text: str) -> list:
                """'lon,lat lon,lat ...' 텍스트 → [[lon,lat], ...] 변환"""
                pts = []
                for pair in text.strip().split():
                    parts = pair.split(",")
                    if len(parts) >= 2:
                        try:
                            pts.append([float(parts[0]), float(parts[1])])
                        except ValueError:
                            pass
                return pts

            def _parse_ring(poly_el):
                """Polygon 요소에서 외부링 좌표 추출"""
                ce = poly_el.find(f".//{{{gml_ns}}}coordinates")
                if ce is not None and ce.text:
                    pts = _coords_text(ce.text)
                    return pts if len(pts) >= 3 else None
                # posList 방식 (좌표가 lon lat lon lat ... 순)
                pl = poly_el.find(f".//{{{gml_ns}}}posList")
                if pl is not None and pl.text:
                    nums = [float(x) for x in pl.text.strip().split()]
                    pts = [[nums[i], nums[i+1]] for i in range(0, len(nums)-1, 2)]
                    return pts if len(pts) >= 3 else None
                return None

            def _parse_geom(geom_el):
                """ag_geom 요소 → GeoJSON geometry dict"""
                mp = geom_el.find(f".//{{{gml_ns}}}MultiPolygon")
                if mp is not None:
                    polys = []
                    for pg in mp.iter(f"{{{gml_ns}}}Polygon"):
                        ring = _parse_ring(pg)
                        if ring:
                            polys.append([ring])
                    return {"type": "MultiPolygon", "coordinates": polys} if polys else None
                pg = geom_el.find(f".//{{{gml_ns}}}Polygon")
                if pg is not None:
                    ring = _parse_ring(pg)
                    if ring:
                        return {"type": "Polygon", "coordinates": [ring]}
                return None

            root = ET.fromstring(xml_str)
            features = []
            for member in root.iter(f"{{{gml_ns}}}featureMember"):
                for feat_el in member:
                    props = {}
                    geom = None
                    for child in feat_el:
                        local = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                        if local in ("grnd_flr", "height", "archarea", "totalarea",
                                     "strct_cd", "main_purps_cd_nm", "bld_nm"):
                            if child.text:
                                try:
                                    props[local] = float(child.text)
                                except ValueError:
                                    props[local] = child.text
                        elif local == "ag_geom":
                            geom = _parse_geom(child)
                    if geom:
                        features.append({
                            "type": "Feature",
                            "geometry": geom,
                            "properties": props,
                        })
            return features

        def _fetch_wfs_page(start_idx: int) -> list:
            pu = "https://api.vworld.kr/req/wfs?" + urllib.parse.urlencode({
                "SERVICE":     "WFS",
                "VERSION":     "1.1.0",
                "REQUEST":     "GetFeature",
                "TYPENAME":    "lt_c_bldginfo",   # WFS 1.x: TYPENAME (s 없음)
                "SRSNAME":     "EPSG:4326",
                "BBOX":        bbox_4326,           # 도단위 WGS84 bbox
                "MAXFEATURES": "1000",              # WFS 1.x: MAXFEATURES (최대 1000)
                "startIndex":  str(start_idx),
                "key":         key,
            })
            rq = urllib.request.Request(pu, headers=_wfs_headers)
            with urllib.request.urlopen(rq, timeout=15) as rp:
                raw = rp.read().decode("utf-8")
            if raw.strip().startswith("<"):
                return _parse_gml(raw)              # GML XML → GeoJSON features
            return json.loads(raw).get("features", [])   # JSON fallback

        all_features = _fetch_wfs_page(0)
        if len(all_features) >= 1000:
            try:
                all_features += _fetch_wfs_page(1000)
            except Exception:
                pass
            if len(all_features) >= 2000:
                try:
                    all_features += _fetch_wfs_page(2000)
                except Exception:
                    pass

        if not all_features:
            return jsonify({"type": "FeatureCollection", "features": []}), 200

        # ── 거리 필터: 반경 밖 건물 제거 ────────────────────────────────────
        KOREA_LON_MIN, KOREA_LON_MAX = 124.0, 132.0
        KOREA_LAT_MIN, KOREA_LAT_MAX = 33.0,  39.0

        def _ring_center(geom):
            try:
                if geom["type"] == "Polygon":
                    ring = geom["coordinates"][0]
                elif geom["type"] == "MultiPolygon":
                    ring = geom["coordinates"][0][0]
                else:
                    return None, None
                cx = sum(c[0] for c in ring) / len(ring)
                cy = sum(c[1] for c in ring) / len(ring)
                return cx, cy
            except Exception:
                return None, None

        def _dist_m(lat1, lon1, lat2, lon2):
            cos_l = math.cos(math.radians((lat1 + lat2) / 2))
            return math.sqrt(((lon2 - lon1) * 111320 * cos_l) ** 2 +
                             ((lat2 - lat1) * 111320) ** 2)

        max_dist = r * 1.5
        filtered = []
        for feat in all_features:
            geom = feat.get("geometry")
            if not geom:
                continue
            bx, by = _ring_center(geom)
            if bx is None:
                continue
            if not (KOREA_LON_MIN <= bx <= KOREA_LON_MAX and
                    KOREA_LAT_MIN <= by <= KOREA_LAT_MAX):
                continue
            if _dist_m(lat, lon, by, bx) <= max_dist:
                filtered.append(feat)

        data = {"type": "FeatureCollection", "features": filtered}
        resp_obj = make_response(json.dumps(data, ensure_ascii=False))
        resp_obj.headers["Content-Type"]              = "application/json; charset=utf-8"
        resp_obj.headers["Access-Control-Allow-Origin"] = "*"
        resp_obj.headers["Cache-Control"]             = "public, max-age=300"
        return resp_obj

    except Exception as exc:
        return jsonify({"type": "FeatureCollection", "features": [],
                        "error": str(exc)}), 200


if __name__ == "__main__":
    # 로컬은 127.0.0.1, Codespaces 등 컨테이너 환경은 0.0.0.0 바인딩 (포트 포워딩용)
    host = os.environ.get("FLASK_HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "5000"))
    app.run(debug=True, host=host, port=port, use_reloader=False)
