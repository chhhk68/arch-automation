"""3D mass를 OBJ / IFC 파일로 내보내기"""

from pathlib import Path
from .regulations import FLOOR_HEIGHT


def _box_vertices_faces(x0, y0, z0, w, d, h):
    """직육면체 꼭짓점 8개, 면 6개(삼각형 12개) 반환"""
    x1, y1, z1 = x0 + w, y0 + d, z0 + h
    v = [
        (x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),  # 0-3 bottom
        (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1),  # 4-7 top
    ]
    f = [
        (0,1,2),(0,2,3),  # bottom
        (4,6,5),(4,7,6),  # top
        (0,1,5),(0,5,4),  # south
        (2,3,7),(2,7,6),  # north
        (1,2,6),(1,6,5),  # east
        (0,3,7),(0,7,4),  # west
    ]
    return v, f


def export_obj(footprints: list, out_path: str, parcel_polygon: list = None) -> str:
    """OBJ 파일 저장 — SketchUp, Rhino에서 바로 열 수 있음
    parcel_polygon: [[lon, lat], ...] 필지 경계 좌표 (옵션) — parcel_boundary 그룹으로 추가
    """
    path = Path(out_path)
    all_verts = []
    all_faces = []

    for floor_idx, (x0, y0, w, d) in enumerate(footprints):
        z0 = floor_idx * FLOOR_HEIGHT
        verts, faces = _box_vertices_faces(x0, y0, z0, w, d, FLOOR_HEIGHT)
        offset = len(all_verts)
        all_verts.extend(verts)
        all_faces.extend([(f[0]+offset+1, f[1]+offset+1, f[2]+offset+1) for f in faces])

    lines = ["# arch-automation mass model", "# OBJ format — import into SketchUp / Rhino", ""]
    lines.append("g mass")
    for v in all_verts:
        lines.append(f"v {v[0]:.4f} {v[2]:.4f} {v[1]:.4f}")  # Y-up for SketchUp
    lines.append("")
    for f in all_faces:
        lines.append(f"f {f[0]} {f[1]} {f[2]}")

    # 필지 경계 (parcel_boundary 그룹)
    if parcel_polygon and len(parcel_polygon) >= 3:
        lines.append("")
        lines.append("g parcel_boundary")
        v_offset = len(all_verts) + 1
        # WGS84 좌표를 로컬 m 단위로 근사 변환 (첫 점 기준 상대 좌표)
        import math
        lon0, lat0 = float(parcel_polygon[0][0]), float(parcel_polygon[0][1])
        cos_lat = math.cos(math.radians(lat0))
        for pt in parcel_polygon:
            dx = (float(pt[0]) - lon0) * 111320 * cos_lat
            dy = (float(pt[1]) - lat0) * 111320
            lines.append(f"v {dx:.4f} 0.0000 {dy:.4f}")
        poly_indices = " ".join(str(v_offset + i) for i in range(len(parcel_polygon)))
        lines.append(f"l {poly_indices}")

    path.write_text("\n".join(lines), encoding="utf-8")
    return str(path)


def export_ifc(footprints: list, zone: str, out_path: str) -> str:
    """
    IFC2x3 파일 저장 — Revit에서 Import IFC로 열 수 있음.
    ifcopenshell이 없으면 간이 IFC 텍스트를 직접 작성.
    """
    try:
        import ifcopenshell
        import ifcopenshell.api
        _export_ifc_full(footprints, zone, out_path)
    except ImportError:
        _export_ifc_minimal(footprints, zone, out_path)
    return out_path


def _export_ifc_minimal(footprints: list, zone: str, out_path: str):
    """ifcopenshell 없이 최소 IFC2x3 작성"""
    import uuid, time

    def guid():
        return str(uuid.uuid4()).replace("-", "")[:22]

    ts = time.strftime("%Y-%m-%dT%H:%M:%S")
    lines = [
        "ISO-10303-21;",
        "HEADER;",
        f"FILE_DESCRIPTION(('ViewDefinition [CoordinationView]'),'2;1');",
        f"FILE_NAME('{Path(out_path).name}','{ts}',('arch-automation'),(''),\
'IfcOpenShell','arch-automation','');",
        "FILE_SCHEMA(('IFC2X3'));",
        "ENDSEC;",
        "DATA;",
    ]

    eid = 1
    proj_id = eid; eid+=1
    site_id = eid; eid+=1
    bldg_id = eid; eid+=1

    lines += [
        f"#{proj_id}=IFCPROJECT('{guid()}',${proj_id+100},'arch-automation',$,$,$,$,$,$);",
        f"#{site_id}=IFCSITE('{guid()}',${site_id+100},'대지',$,$,$,$,$,.ELEMENT.,$,$,$,$,$);",
        f"#{bldg_id}=IFCBUILDING('{guid()}',${bldg_id+100},'건물',$,$,$,$,$,.ELEMENT.,$,$,$);",
    ]

    for floor_idx, (x0, y0, w, d) in enumerate(footprints):
        z = floor_idx * FLOOR_HEIGHT
        slab_id = eid; eid+=1
        name = f"{floor_idx+1}F"
        lines.append(
            f"#{slab_id}=IFCSLAB('{guid()}',${slab_id+100},'{name}',$,$,$,$,$,.FLOOR.);")

    lines += ["ENDSEC;", "END-ISO-10303-21;"]
    Path(out_path).write_text("\n".join(lines), encoding="utf-8")


def _export_ifc_full(footprints, zone, out_path):
    import ifcopenshell
    import ifcopenshell.api as api

    model = ifcopenshell.file(schema="IFC2X3")
    project = api.run("root.create_entity", model, ifc_class="IfcProject", name="arch-automation")
    api.run("unit.assign_unit", model, length={"is_metric": True, "raw": "METRES"})
    ctx = api.run("context.add_context", model, context_type="Model",
                  context_identifier="Body", target_view="MODEL_VIEW")
    site = api.run("root.create_entity", model, ifc_class="IfcSite", name="대지")
    bldg = api.run("root.create_entity", model, ifc_class="IfcBuilding", name="건물")
    api.run("aggregate.assign_object", model, relating_object=project, product=site)
    api.run("aggregate.assign_object", model, relating_object=site, product=bldg)

    for floor_idx, (x0, y0, w, d) in enumerate(footprints):
        z = floor_idx * FLOOR_HEIGHT
        storey = api.run("root.create_entity", model, ifc_class="IfcBuildingStorey",
                         name=f"{floor_idx+1}F")
        api.run("aggregate.assign_object", model, relating_object=bldg, product=storey)
        slab = api.run("root.create_entity", model, ifc_class="IfcSlab", name=f"{floor_idx+1}F_slab")
        api.run("spatial.assign_container", model, relating_structure=storey, product=slab)

        placement = model.createIfcAxis2Placement3D(
            model.createIfcCartesianPoint([x0, y0, z]))
        shape = model.createIfcExtrudedAreaSolid(
            model.createIfcRectangleProfileDef("AREA", None,
                model.createIfcAxis2Placement2D(
                    model.createIfcCartesianPoint([0.0, 0.0])), w, d),
            placement,
            model.createIfcDirection([0.0, 0.0, 1.0]),
            FLOOR_HEIGHT)
        rep = model.createIfcShapeRepresentation(ctx, "Body", "SweptSolid", [shape])
        slab.Representation = model.createIfcProductDefinitionShape(None, None, [rep])

    model.write(out_path)
