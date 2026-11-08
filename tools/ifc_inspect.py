"""Is this IFC good enough for Seraph? Run: pip install ifcopenshell && python tools/ifc_inspect.py building.ifc

GO if: >= 3 storeys, >= 2 stairs, doors and spaces present and named, materials on walls.
Nice to have: FireRating values, escape-route psets, space boundaries (makes the route graph automatic).
"""
import sys
from collections import Counter

import ifcopenshell
import ifcopenshell.util.element as E


def material_names(el):
    m = E.get_material(el, should_skip_usage=True)
    if m is None:
        return []
    if m.is_a("IfcMaterial"):
        return [m.Name]
    if m.is_a("IfcMaterialLayerSet"):
        return [l.Material.Name for l in m.MaterialLayers if l.Material]
    if m.is_a("IfcMaterialConstituentSet"):
        return [c.Material.Name for c in (m.MaterialConstituents or []) if c.Material]
    if m.is_a("IfcMaterialProfileSet"):
        return [p.Material.Name for p in (m.MaterialProfiles or []) if p.Material]
    if m.is_a("IfcMaterialList"):
        return [x.Name for x in m.Materials]
    return [m.is_a()]


def main(path):
    f = ifcopenshell.open(path)
    print(f"schema {f.schema} · file {path}")
    for b in f.by_type("IfcBuilding"):
        print(f"building: {b.Name!r} {getattr(b, 'LongName', None)!r}")

    print("\nstoreys")
    for s in sorted(f.by_type("IfcBuildingStorey"), key=lambda s: s.Elevation or 0):
        print(f"  {s.Name!r:30} elev {s.Elevation}")

    print("\ncounts")
    for t in ["IfcSpace", "IfcDoor", "IfcWindow", "IfcStair", "IfcStairFlight", "IfcRamp",
              "IfcWall", "IfcSlab", "IfcColumn", "IfcTransportElement", "IfcZone",
              "IfcRelSpaceBoundary", "IfcFireSuppressionTerminal", "IfcAlarm"]:
        try:
            print(f"  {t:28} {len(f.by_type(t))}")
        except RuntimeError:
            print(f"  {t:28} (not in schema)")

    spaces = f.by_type("IfcSpace")
    print(f"\nspaces (first 15 of {len(spaces)})")
    for sp in spaces[:15]:
        st = E.get_container(sp) or E.get_aggregate(sp)
        print(f"  {sp.Name!r:12} {sp.LongName!r:30} on {getattr(st, 'Name', None)!r}")

    walls = f.by_type("IfcWall")
    mats, fire, ext = Counter(), Counter(), Counter()
    for w in walls:
        for n in material_names(w):
            mats[n] += 1
        common = E.get_psets(w).get("Pset_WallCommon", {})
        fire[str(common.get("FireRating"))] += 1
        ext[str(common.get("IsExternal"))] += 1
    print(f"\nwall materials (top 10 of {len(mats)}): {mats.most_common(10)}")
    print(f"wall FireRating values: {fire.most_common(8)}")
    print(f"wall IsExternal: {dict(ext)}")

    doors = f.by_type("IfcDoor")
    dfire = Counter(str(E.get_psets(d).get("Pset_DoorCommon", {}).get("FireRating")) for d in doors)
    print(f"door FireRating values: {dfire.most_common(8)}")

    pset_names = Counter()
    for el in f.by_type("IfcProduct"):
        for name in E.get_psets(el):
            pset_names[name] += 1
    hits = [(n, c) for n, c in pset_names.items()
            if any(k in n.lower() for k in ("escape", "flucht", "fire", "brand", "evac", "egress", "rescue"))]
    print(f"\nfire/escape psets: {hits or 'none'}")
    print(f"all psets (top 25): {pset_names.most_common(25)}")


if __name__ == "__main__":
    main(sys.argv[1])
