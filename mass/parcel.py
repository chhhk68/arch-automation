"""
VWorld API를 이용한 필지 정보 자동 조회
API 키: https://api.vworld.kr 에서 무료 발급
"""

import json
import math
import urllib.request
import urllib.parse
from dataclasses import dataclass

VWORLD = "https://api.vworld.kr/req"

# VWorld 용도지역 코드 → 한글 이름
ZONE_CODE_MAP = {
    "UQA110": "제1종전용주거지역",
    "UQA120": "제2종전용주거지역",
    "UQA131": "제1종일반주거지역",
    "UQA132": "제2종일반주거지역",
    "UQA133": "제3종일반주거지역",
    "UQA140": "준주거지역",
    "UQA210": "중심상업지역",
    "UQA220": "일반상업지역",
    "UQA230": "근린상업지역",
    "UQA240": "유통상업지역",
    "UQA310": "전용공업지역",
    "UQA320": "일반공업지역",
    "UQA330": "준공업지역",
    "UQA410": "보전녹지지역",
    "UQA420": "생산녹지지역",
    "UQA430": "자연녹지지역",
}


@dataclass
class ParcelInfo:
    address: str
    pnu: str
    area: float      # m²
    zone: str        # 용도지역
    width: float     # 동서 폭 (m, bounding box 근사)
    depth: float     # 남북 깊이 (m, bounding box 근사)
    lon: float = 0.0      # 경도 — 지오코딩 주소점 (WGS84)
    lat: float = 0.0      # 위도 — 지오코딩 주소점 (WGS84)
    mid_lon: float = 0.0  # 경도 — 필지 폴리곤 bbox 중심 (WGS84)
    mid_lat: float = 0.0  # 위도 — 필지 폴리곤 bbox 중심 (WGS84)
    polygon: list = None  # [[lon,lat], ...] 실제 필지 경계 좌표 (WGS84)


def _get(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "arch-automation/1.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _haversine(lon1, lat1, lon2, lat2) -> float:
    """두 좌표 간 거리 (m)"""
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dl/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def geocode(address: str, api_key: str) -> tuple[float, float]:
    """주소 → (경도, 위도)"""
    def _call(addr_type: str) -> dict:
        url = VWORLD + "/address?" + urllib.parse.urlencode({
            "service": "address", "request": "getCoord", "version": "2.0",
            "crs": "epsg:4326", "address": address,
            "format": "json", "type": addr_type, "key": api_key,
        })
        return _get(url)

    data = _call("road")
    if data.get("response", {}).get("status", "") != "OK":
        data = _call("parcel")  # 도로명 실패 시 지번으로 재시도
    if data.get("response", {}).get("status", "") != "OK":
        raise ValueError(f"주소를 찾을 수 없습니다: {address}")

    pt = data["response"]["result"]["point"]
    return float(pt["x"]), float(pt["y"])


def get_parcel(lon: float, lat: float, api_key: str) -> tuple[str, float, float, float, float, float]:
    """좌표 → (PNU, 면적m², 동서폭m, 남북깊이m)"""
    url = VWORLD + "/data?" + urllib.parse.urlencode({
        "request": "GetFeature",
        "data": "LP_PA_CBND_BUBUN",
        "key": api_key,
        "geometry": "true",
        "attribute": "true",
        "format": "json",
        "size": "1",
        "page": "1",
        "geomFilter": f"POINT({lon} {lat})",
        "crs": "EPSG:4326",
    })
    data = _get(url)
    features = (data.get("response", {})
                    .get("result", {})
                    .get("featureCollection", {})
                    .get("features", []))
    if not features:
        raise ValueError("해당 위치의 필지를 찾을 수 없습니다")

    feat = features[0]
    props = feat.get("properties", {})
    pnu = props.get("pnu", "")

    # 면적: API에서 제공되면 사용, 없으면 geometry에서 계산
    area_str = props.get("area", "") or props.get("shapeArea", "")
    area = float(area_str) if area_str else 0.0

    # Bounding box → 폭/깊이
    geom = feat.get("geometry", {})
    coords_raw = geom.get("coordinates", [[]])
    geom_type = geom.get("type", "")
    if geom_type == "MultiPolygon":
        ring = coords_raw[0][0]  # 첫 번째 폴리곤의 외곽 링
    else:
        ring = coords_raw[0]     # Polygon 외곽 링
    lons = [c[0] for c in ring]
    lats = [c[1] for c in ring]
    mid_lat = (min(lats) + max(lats)) / 2
    mid_lon = (min(lons) + max(lons)) / 2
    width = round(_haversine(min(lons), mid_lat, max(lons), mid_lat), 1)
    depth = round(_haversine(mid_lon, min(lats), mid_lon, max(lats)), 1)

    if area <= 0:
        # Shoelace formula로 면적 계산 (근사)
        n = len(ring)
        s = sum(ring[i][0]*ring[(i+1)%n][1] - ring[(i+1)%n][0]*ring[i][1]
                for i in range(n))
        # 경위도 → m² 변환 (근사)
        area = abs(s) / 2 * (math.cos(math.radians(mid_lat)) * 111320) * 111320

    # 실제 필지 폴리곤 좌표 (GeoJSON [lon,lat] 형식)
    poly_coords = [[float(c[0]), float(c[1])] for c in ring]
    if poly_coords and poly_coords[0] != poly_coords[-1]:
        poly_coords.append(poly_coords[0])  # 링 닫기

    return pnu, round(area, 1), width, depth, mid_lat, mid_lon, poly_coords


def get_zone(lon: float, lat: float, api_key: str) -> str:
    """용도지역 자동 조회 (VWorld APP 키는 용도지역 WFS 미지원 — 수동 선택 필요)"""
    return ""


def lookup(address: str, api_key: str) -> ParcelInfo:
    """주소 → ParcelInfo (전체 파이프라인)"""
    print(f"  주소 검색 중...")
    lon, lat = geocode(address, api_key)
    print(f"  좌표: 경도 {lon:.5f}, 위도 {lat:.5f}")

    print(f"  필지 경계 조회 중...")
    pnu, area, width, depth, mid_lat, mid_lon, polygon = get_parcel(lon, lat, api_key)
    print(f"  PNU: {pnu}  |  면적: {area:.1f} m²  |  {width}m × {depth}m")
    print(f"  bbox 중심: 위도 {mid_lat:.6f}, 경도 {mid_lon:.6f}")
    print(f"  폴리곤 좌표 {len(polygon)}점")

    zone = ""  # 용도지역은 사용자가 선택 (VWorld APP 키 미지원)

    return ParcelInfo(
        address=address, pnu=pnu,
        area=area, zone=zone,
        width=width, depth=depth,
        lon=lon, lat=lat,
        mid_lon=mid_lon, mid_lat=mid_lat,
        polygon=polygon,
    )
