"""건축 법규 검토 + 3D Mass 생성 도구

사용법:
    python main.py              # 수동 입력 모드
    python main.py --parcel     # 주소로 필지 자동 조회
"""

import sys
from pathlib import Path
from mass import Site, plot_mass, export_obj, export_ifc
from mass.regulations import ZONING

ZONES = list(ZONING.keys())


def pick_zone(current: str = "") -> str:
    print("\n  용도지역 선택:")
    for i, z in enumerate(ZONES, 1):
        marker = " ◀ 현재" if z == current else ""
        print(f"    {i:2}. {z}{marker}")
    default = ZONES.index(current) + 1 if current in ZONES else 4
    idx = int(input(f"  번호 입력 [기본 {default}]: ").strip() or default) - 1
    return ZONES[idx]


def manual_mode():
    print("\n대지 정보를 입력하세요 (엔터 = 기본값)\n")
    width = float(input("  대지 폭 E-W (m) [20]: ").strip() or 20)
    depth = float(input("  대지 깊이 S-N (m) [30]: ").strip() or 30)
    zone = pick_zone("제2종일반주거지역")
    return width, depth, zone


def parcel_mode():
    """VWorld API로 필지 자동 조회"""
    from mass.parcel import lookup

    # API 키 로드
    cfg_path = Path("config.json")
    if cfg_path.exists():
        import json
        api_key = json.loads(cfg_path.read_text(encoding="utf-8")).get("vworld_key", "")
    else:
        api_key = ""

    if not api_key:
        print("\n  VWorld API 키가 필요합니다.")
        print("  https://api.vworld.kr 에서 무료 발급 후 config.json에 입력하세요.")
        print("  예시: {\"vworld_key\": \"여기에API키입력\"}\n")
        api_key = input("  API 키를 직접 입력하세요: ").strip()
        if not api_key:
            print("  키 없이 수동 모드로 전환합니다.")
            return manual_mode()

    address = input("\n  주소 입력 (예: 서울특별시 강남구 테헤란로 152): ").strip()
    if not address:
        return manual_mode()

    try:
        info = lookup(address, api_key)
    except Exception as e:
        print(f"\n  필지 조회 실패: {e}")
        print("  수동 모드로 전환합니다.")
        return manual_mode()

    print(f"\n  조회 결과: {info.address}")
    print(f"  면적 {info.area:.1f} m²  |  {info.width}m × {info.depth}m")

    # 용도지역이 자동 조회됐으면 확인, 없으면 선택
    if info.zone:
        confirm = input(f"  용도지역 '{info.zone}' 으로 진행합니까? [Y/n]: ").strip().lower()
        zone = info.zone if confirm != "n" else pick_zone(info.zone)
    else:
        zone = pick_zone()

    return info.width, info.depth, zone


def run():
    print("━━━ 건축 법규 검토 + 3D Mass 생성 ━━━")

    use_parcel = "--parcel" in sys.argv or \
        input("\n  필지 자동 조회 모드? [y/N]: ").strip().lower() == "y"

    if use_parcel:
        width, depth, zone = parcel_mode()
    else:
        width, depth, zone = manual_mode()

    sn = float(input("\n  북측 이격거리 (m) [0.5]: ").strip() or 0.5)
    ss = float(input("  남측 이격거리 (m) [0.5]: ").strip() or 0.5)
    se = float(input("  동측 이격거리 (m) [0.5]: ").strip() or 0.5)
    sw = float(input("  서측 이격거리 (m) [0.5]: ").strip() or 0.5)

    site = Site(width=width, depth=depth, zone=zone,
                setback_n=sn, setback_s=ss, setback_e=se, setback_w=sw)
    result = site.check()
    footprints = result.floor_footprints()

    print("\n" + result.summary())

    out = Path("output"); out.mkdir(exist_ok=True)
    obj_path = export_obj(footprints, str(out / "mass.obj"))
    ifc_path = export_ifc(footprints, zone, str(out / "mass.ifc"))
    print(f"\n  OBJ (SketchUp / Rhino) → {obj_path}")
    print(f"  IFC (Revit)            → {ifc_path}")

    print("\n  브라우저에서 3D 뷰가 열립니다...")
    print("  마우스 조작: 왼쪽 드래그=궤도회전 / 오른쪽 드래그=이동 / 스크롤=확대축소")
    plot_mass(site, footprints, result.summary())


if __name__ == "__main__":
    run()
