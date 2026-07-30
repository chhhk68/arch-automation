# 건축 자동화 도구

건축 설계 실무에서 자주 쓰이는 면적·비용 계산을 자동화하는 Python 유틸리티입니다.

## 기능

**기초 계산 (`calc.py`)**
- 방 면적 계산 (가로 × 세로)
- 평 ↔ 제곱미터 단위 변환
- 공사비 추정 (면적 × 단가)
- 용적률·건폐율 계산

**법규 검토 + 3D 매스 (`mass/`)**
- 용도지역별 건폐율·용적률·일조권 검토, 층별 매스 생성 (OBJ/IFC)
- **주차대수 산정** — 주용도별 법정 주차, 장애인주차, 소요 주차면적 개략
- **면적 산정표** — 층별 바닥면적·연면적·용적률/건폐율, CSV 출력
- **사업성(수지) 분석** — 토지비·공사비·부대비·분양수입·사업이익·수익률 개략

## 사용법

### 기초 계산

```python
from calc import room_area, pyeong_to_sqm, estimate_cost

area = room_area(4.5, 3.2)              # 14.4 m²
sqm  = pyeong_to_sqm(25)                # 약 82.6 m²
cost = estimate_cost(82.6, 1_500_000)   # 123,900,000 원
```

### 법규 검토 → 면적표 · 주차 · 수지분석

```python
from mass import (Site, calc_parking, default_use_type_for_zone,
                  FeasibilityInput, analyze_feasibility)

site   = Site(width=20, depth=30, zone="제2종일반주거지역", actual_area=400)
result = site.check()

# 면적 산정표 (층별 바닥면적·연면적·용적률/건폐율)
schedule = result.area_schedule(default_use_type_for_zone(site.zone))
gfa = schedule["gross_floor_area"]

# 주차대수 산정
parking = calc_parking(gfa, "업무시설")   # {'required': ..., 'disabled': ..., 'est_area': ...}

# 사업성(수지) 분석
fi = FeasibilityInput(gfa=gfa, land_area=site.area,
                      land_price_per_sqm=15_000_000,
                      construction_cost_per_sqm=2_500_000,
                      sale_price_per_sqm=8_000_000)
result = analyze_feasibility(fi)          # {'total_cost': ..., 'profit': ..., 'profit_rate': ...}
```

### CLI · 웹앱

```bash
python main.py            # 법규 검토 + 면적표 + 주차 + (선택)수지분석 + 3D 뷰
python app.py             # 웹앱 (지도·필지 조회) — flask, requests 만 있으면 구동
```

웹 API: `POST /api/check` 응답에 `schedule` 포함, `GET /api/schedule.csv`(면적표 CSV
다운로드), `POST /api/feasibility`(수지분석).

## 실행 요건

- Python 3.8 이상
- 웹앱/기본 기능: `flask`, `requests` (`pip install -r requirements.txt`)
- 3D 시각화(`main.py`)만 추가로: `pip install plotly` (선택)

## 테스트

```bash
pip install pytest
pytest test_calc.py test_parking.py test_schedule.py test_feasibility.py
```

> ⚠️ 법규 데이터·주차/조경 기준·수지 추정치는 계획 초기 **개략치**입니다.
> 실제 인허가는 지구단위계획·지자체 조례·토지이음 확인이 필요합니다.
