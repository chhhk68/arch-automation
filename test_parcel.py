from mass.parcel import lookup

api_key = "481D8237-0003-38A2-945A-487993C360EA"
address = "서울특별시 강남구 테헤란로 152"

info = lookup(address, api_key)
print()
print(f"주소   : {info.address}")
print(f"PNU    : {info.pnu}")
print(f"면적   : {info.area} m²")
print(f"크기   : {info.width}m × {info.depth}m")
print(f"용도지역: {info.zone}")
