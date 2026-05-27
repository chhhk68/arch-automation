# 건축 자동화 도구

건축 설계 실무에서 자주 쓰이는 면적·비용 계산을 자동화하는 Python 유틸리티입니다.

## 기능

- 방 면적 계산 (가로 × 세로)
- 평 ↔ 제곱미터 단위 변환
- 공사비 추정 (면적 × 단가)

## 사용법

```python
from calc import room_area, pyeong_to_sqm, estimate_cost

# 방 면적
area = room_area(4.5, 3.2)  # 14.4 m²

# 단위 변환
sqm = pyeong_to_sqm(25)     # 약 82.6 m²

# 공사비 추정
cost = estimate_cost(82.6, 1_500_000)  # 123,900,000 원
```

## 실행 요건

- Python 3.8 이상
