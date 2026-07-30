"""면적 산정표 — 층별 바닥면적·연면적·용적률/건폐율 산정 및 CSV 출력

건축 인허가 도서의 '면적산정표'를 개략 생성한다. 법규 검토(RegulationResult)가
계산한 층별 풋프린트를 입력으로 받아 층별/합계 면적을 정리한다.

근거:
- 건축법 시행령 제119조 (면적·높이 등의 산정방법)
  · 건축면적 = 건축물 외벽 중심선 수평투영면적 (통상 최대층 바닥면적)
  · 연면적   = 각 층 바닥면적의 합계
  · 용적률 산정용 연면적 = 지상층 연면적 (지하층·부속주차장 등 제외)

⚠️ 본 모듈의 풋프린트는 모두 지상층 매스이므로 연면적 = 용적률산정연면적으로 본다.
   지하층·주차장을 별도 반영할 경우 far_floor_area 를 조정해야 한다.
"""

import csv
import io

# 1평 = 3.305785 m² (calc.py 와 동일 상수)
SQM_PER_PYEONG = 3.305785


def _pyeong(sqm: float) -> float:
    return sqm / SQM_PER_PYEONG


def build_area_schedule(footprints, *, site_area=None,
                        floor_height: float = 3.2, use_type: str = "",
                        ground_start: int = 1) -> dict:
    """층별 풋프린트로부터 면적 산정표를 생성한다.

    Args:
        footprints: [(x0, y0, w, d), ...] — 하층부터 순서대로. 각 층 바닥면적 = w×d.
        site_area:  대지면적(m²). 주어지면 건폐율·용적률(%)을 함께 계산.
        floor_height: 층고(m) — 층별 상단 높이 산정용.
        use_type:   주용도(면적표 '용도' 칸 표기용, 선택).
        ground_start: 시작 지상 층번호(기본 1).

    Returns:
        dict — floors(층별 rows), building_area, gross_floor_area,
               far_floor_area, floor_count, site_area, bcr, far, floor_height
    """
    if site_area is not None and site_area <= 0:
        raise ValueError("대지면적은 양수여야 합니다")

    rows = []
    cumulative = 0.0
    for i, fp in enumerate(footprints):
        # (x0, y0, w, d) 형식 — 앞 두 값은 위치, 뒤 두 값이 폭·깊이
        w, d = fp[2], fp[3]
        area = w * d
        if area <= 0:
            continue
        cumulative += area
        floor_no = ground_start + i
        rows.append({
            "floor": floor_no,
            "floor_label": f"{floor_no}층",
            "area_sqm": round(area, 2),
            "area_pyeong": round(_pyeong(area), 2),
            "height_top": round((i + 1) * floor_height, 2),
            "cumulative_sqm": round(cumulative, 2),
            "use": use_type,
        })

    gross = sum(r["area_sqm"] for r in rows)
    # 건축면적: 지상층 중 최대 바닥면적(수평투영) — step-back 시 통상 최하층
    building = max((r["area_sqm"] for r in rows), default=0.0)
    far_area = gross  # 지상층 매스 전제 (지하·주차 제외분 없음)

    bcr = round(building / site_area * 100, 2) if site_area else None
    far = round(far_area / site_area * 100, 2) if site_area else None

    return {
        "floors": rows,
        "building_area": round(building, 2),
        "gross_floor_area": round(gross, 2),
        "far_floor_area": round(far_area, 2),
        "floor_count": len(rows),
        "site_area": round(site_area, 2) if site_area else None,
        "bcr": bcr,
        "far": far,
        "floor_height": floor_height,
    }


def schedule_to_csv(schedule: dict) -> str:
    """면적 산정표를 CSV 문자열로 변환 (엑셀 호환).

    엑셀에서 한글이 깨지지 않도록 파일로 저장할 때는 UTF-8 BOM 을 앞에 붙일 것.
    """
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["층", "바닥면적(m²)", "바닥면적(평)", "상단높이(m)",
                     "누계연면적(m²)", "용도"])
    for r in schedule["floors"]:
        writer.writerow([r["floor_label"], r["area_sqm"], r["area_pyeong"],
                         r["height_top"], r["cumulative_sqm"], r["use"]])
    # 합계 행
    writer.writerow([])
    writer.writerow(["건축면적(m²)", schedule["building_area"]])
    writer.writerow(["연면적(m²)", schedule["gross_floor_area"]])
    writer.writerow(["용적률산정연면적(m²)", schedule["far_floor_area"]])
    if schedule["site_area"]:
        writer.writerow(["대지면적(m²)", schedule["site_area"]])
        writer.writerow(["건폐율(%)", schedule["bcr"]])
        writer.writerow(["용적률(%)", schedule["far"]])
    return buf.getvalue()


def format_schedule(schedule: dict) -> str:
    """면적 산정표를 CLI 출력용 텍스트 표로 변환."""
    lines = ["━━━ 면적 산정표 ━━━",
             f"  {'층':<5}{'바닥면적(m²)':>14}{'(평)':>10}{'상단(m)':>10}{'누계(m²)':>12}"]
    for r in schedule["floors"]:
        lines.append(f"  {r['floor_label']:<5}{r['area_sqm']:>14.2f}"
                     f"{r['area_pyeong']:>10.2f}{r['height_top']:>10.2f}"
                     f"{r['cumulative_sqm']:>12.2f}")
    lines.append("  " + "─" * 50)
    lines.append(f"  건축면적 : {schedule['building_area']:.2f} m²"
                 f"  ({_pyeong(schedule['building_area']):.2f} 평)")
    lines.append(f"  연면적   : {schedule['gross_floor_area']:.2f} m²"
                 f"  ({_pyeong(schedule['gross_floor_area']):.2f} 평)")
    if schedule["site_area"]:
        lines.append(f"  건폐율   : {schedule['bcr']:.2f} %"
                     f"   용적률 : {schedule['far']:.2f} %")
    return "\n".join(lines)
