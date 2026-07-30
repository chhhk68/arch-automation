import matplotlib; matplotlib.use("Agg")
from mass.site import Site
from mass.visualizer import plot_mass
from mass.exporter import export_obj, export_ifc
from pathlib import Path

# 테헤란로 152 실제 필지 데이터 (VWorld API 조회 결과)
site = Site(width=139.6, depth=149.9, zone="일반상업지역",
            setback_n=0.5, setback_s=0.5, setback_e=0.5, setback_w=0.5)

result = site.check()
fps = result.floor_footprints()
print(result.summary())
print(f"\n층수: {len(fps)}층")

Path("output").mkdir(exist_ok=True)
print(export_obj(fps, "output/mass_teheran.obj"))
print(export_ifc(fps, site.zone, "output/mass_teheran.ifc"))

plot_mass(site, fps, result.summary())
