"""샘플 실행 — 대지 20x30, 제2종일반주거지역"""

from pathlib import Path
from mass import Site, plot_mass, export_obj, export_ifc

site = Site(
    width=20, depth=30,
    zone="제2종일반주거지역",
    setback_n=0.5, setback_s=0.5, setback_e=0.5, setback_w=0.5,
)

result = site.check()
footprints = result.floor_footprints()

print(result.summary())

Path("output").mkdir(exist_ok=True)
obj_path = export_obj(footprints, "output/mass.obj")
ifc_path = export_ifc(footprints, site.zone, "output/mass.ifc")
print(f"\nOBJ → {obj_path}")
print(f"IFC → {ifc_path}")

plot_mass(site, footprints, result.summary())
