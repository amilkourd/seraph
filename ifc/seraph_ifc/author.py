"""trace.yaml → IFC4, for buildings we rebuild from posted plans (or the fictional dev building).

    uv run ifc-author dev/trace.yaml -o dev/dev.ifc

Writes storeys, one IfcSpace per room (extruded polygon), walls on room edges (each shared edge once),
IfcDoor per door, IfcStair per stair and level, one slab per level, IfcMaterial + Pset_*Common.FireRating /
IsExternal only when the trace gives them, and Pset `Seraph_Provenance {method, date, from}` on the building.
Polygons are in metres. Rooms on a level are expected to tile it (shared edges), like a traced plan.
"""
from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Optional

import numpy as np
import yaml

import ifcopenshell
import ifcopenshell.api as api
import ifcopenshell.api.aggregate
import ifcopenshell.api.context
import ifcopenshell.api.feature
import ifcopenshell.api.geometry
import ifcopenshell.api.material
import ifcopenshell.api.project
import ifcopenshell.api.pset
import ifcopenshell.api.root
import ifcopenshell.api.spatial
import ifcopenshell.api.unit
from ifcopenshell.util.shape_builder import ShapeBuilder

DOOR_HEIGHT = 2.1
EPS = 1e-6


@dataclass
class Space:
    level: int
    name: str
    long_name: str
    use: Optional[str]
    polygon: list[tuple[float, float]]
    stair: Optional[str] = None
    enclosure: Optional[str] = None


@dataclass
class Door:
    level: int
    name: str
    at: tuple[float, float]
    width: float
    description: Optional[str] = None
    external: bool = False
    fire_rating: Optional[str] = None


def _fmt(s: Any, n: int) -> Any:
    return s.replace("{n}", str(n)) if isinstance(s, str) else s


def read_trace(path: Path) -> tuple[dict, list[Space], list[Door]]:
    t = yaml.safe_load(path.read_text(encoding="utf-8"))
    spaces: list[Space] = []
    doors: list[Door] = []
    core = t.get("core") or {}
    for lv in t["levels"]:
        n = lv["level"]
        here = (t.get("plan") or {}).get(n) or {}
        for s in list(core.get("spaces", [])) + list(here.get("spaces", [])):
            spaces.append(Space(level=n, name=_fmt(s["name"], n), long_name=_fmt(s.get("long_name", ""), n),
                                use=s.get("use"), polygon=[(float(x), float(y)) for x, y in s["polygon"]],
                                stair=s.get("stair"), enclosure=s.get("enclosure")))
        for d in list(core.get("doors", [])) + list(here.get("doors", [])):
            doors.append(Door(level=n, name=_fmt(d["name"], n), at=(float(d["at"][0]), float(d["at"][1])),
                              width=float(d.get("width", 0.9)), description=d.get("description"),
                              external=bool(d.get("external", False)), fire_rating=d.get("fire_rating")))
    return t, spaces, doors


# ───────── Walls from room edges ─────────
def _edges(poly: list[tuple[float, float]]):
    for i in range(len(poly)):
        yield poly[i], poly[(i + 1) % len(poly)]


def _on_segment(p, a, b) -> bool:
    (px, py), (ax, ay), (bx, by) = p, a, b
    cross = (bx - ax) * (py - ay) - (by - ay) * (px - ax)
    if abs(cross) > 1e-6:
        return False
    dot = (px - ax) * (bx - ax) + (py - ay) * (by - ay)
    return -EPS <= dot <= (bx - ax) ** 2 + (by - ay) ** 2 + EPS


def wall_segments(spaces: list[Space]) -> list[tuple[tuple[float, float], tuple[float, float], list[Space]]]:
    """Every room edge split at every vertex lying on it, deduplicated → (a, b, spaces sharing it)."""
    verts = {p for s in spaces for p in s.polygon}
    seen: dict[tuple, list[Space]] = {}
    for s in spaces:
        for a, b in _edges(s.polygon):
            on = sorted((p for p in verts if _on_segment(p, a, b)),
                        key=lambda p: (p[0] - a[0]) ** 2 + (p[1] - a[1]) ** 2)
            for p, q in zip(on, on[1:]):
                key = tuple(sorted((tuple(round(c, 4) for c in p), tuple(round(c, 4) for c in q))))
                if key[0] == key[1]:
                    continue
                seen.setdefault(key, [])
                if s not in seen[key]:
                    seen[key].append(s)
    return [(k[0], k[1], v) for k, v in seen.items()]


def classify_wall(owners: list[Space]) -> str:
    if len(owners) == 1:
        return "facade"
    if any(o.stair for o in owners):
        return "stair"
    for o in owners:
        if o.enclosure:
            return o.enclosure
    return "partition"


# ───────── IFC helpers ─────────
def _matrix(origin: tuple[float, float, float], x_dir: tuple[float, float] = (1.0, 0.0)) -> np.ndarray:
    m = np.eye(4)
    dx, dy = x_dir
    m[0:3, 0] = [dx, dy, 0.0]
    m[0:3, 1] = [-dy, dx, 0.0]
    m[0:3, 3] = origin
    return m


def _pset(f, product, name: str, props: dict[str, Any]) -> None:
    props = {k: v for k, v in props.items() if v is not None}
    if props:
        api.pset.edit_pset(f, pset=api.pset.add_pset(f, product=product, name=name), properties=props)


def build(trace_path: Path, out: Path) -> Path:
    t, spaces, doors = read_trace(trace_path)
    meta = t["building"]
    h = float(t.get("storey_height", 3.0))
    wt = float(t.get("wall_thickness", 0.2))
    st = float(t.get("slab_thickness", 0.2))
    mats_spec: dict[str, dict] = t.get("materials") or {}

    f = api.project.create_file(version="IFC4")
    project = api.root.create_entity(f, ifc_class="IfcProject", name=meta["name"])
    length = api.unit.add_si_unit(f, unit_type="LENGTHUNIT")
    area = api.unit.add_si_unit(f, unit_type="AREAUNIT")
    volume = api.unit.add_si_unit(f, unit_type="VOLUMEUNIT")
    api.unit.assign_unit(f, units=[length, area, volume])
    model = api.context.add_context(f, context_type="Model")
    body = api.context.add_context(f, context_type="Model", context_identifier="Body", target_view="MODEL_VIEW",
                                   parent=model)
    sb = ShapeBuilder(f)

    site = api.root.create_entity(f, ifc_class="IfcSite", name="Site")
    bldg = api.root.create_entity(f, ifc_class="IfcBuilding", name=meta["name"])
    api.aggregate.assign_object(f, products=[site], relating_object=project)
    api.aggregate.assign_object(f, products=[bldg], relating_object=site)
    _pset(f, bldg, "Seraph_Provenance", {
        "method": meta.get("method", "authored from trace.yaml"),
        "date": date.today().isoformat(),
        "from": meta.get("from", str(trace_path)),
        "provenance": meta.get("provenance"),
        "provenance_fr": meta.get("provenance_fr"),
        "front": meta.get("front"),
    })

    materials: dict[str, Any] = {}

    def material(key: str):
        spec = mats_spec.get(key)
        if not spec or not spec.get("material"):
            return None, None
        if key not in materials:
            materials[key] = api.material.add_material(f, name=spec["material"])
        return materials[key], spec.get("fire_rating")

    storeys: dict[int, Any] = {}
    for lv in sorted(t["levels"], key=lambda x: x["elevation"]):
        s = api.root.create_entity(f, ifc_class="IfcBuildingStorey", name=lv["name"])
        s.Elevation = float(lv["elevation"])
        api.aggregate.assign_object(f, products=[s], relating_object=bldg)
        api.geometry.edit_object_placement(f, product=s, matrix=_matrix((0, 0, float(lv["elevation"]))))
        storeys[lv["level"]] = (s, float(lv["elevation"]))

    for n, (storey, z) in storeys.items():
        here = [s for s in spaces if s.level == n]

        # Slab (floor of the level).
        outline = _outline(here)
        if outline:
            slab = api.root.create_entity(f, ifc_class="IfcSlab", predefined_type="FLOOR", name=f"Dalle {storey.Name}")
            api.geometry.edit_object_placement(f, product=slab, matrix=_matrix((0, 0, z - st)))
            rep = sb.get_representation(body, sb.extrude(sb.profile(sb.polyline(outline, closed=True)), magnitude=st))
            api.geometry.assign_representation(f, product=slab, representation=rep)
            api.spatial.assign_container(f, products=[slab], relating_structure=storey)
            m, fr = material("slab")
            if m:
                api.material.assign_material(f, products=[slab], type="IfcMaterial", material=m)
            _pset(f, slab, "Pset_SlabCommon", {"FireRating": fr})

        # Spaces.
        for s in here:
            sp = api.root.create_entity(f, ifc_class="IfcSpace", name=s.name)
            sp.LongName = s.long_name or None
            sp.ObjectType = s.use or None
            api.aggregate.assign_object(f, products=[sp], relating_object=storey)
            api.geometry.edit_object_placement(f, product=sp, matrix=_matrix((0, 0, z)))
            rep = sb.get_representation(body, sb.extrude(sb.profile(sb.polyline(s.polygon, closed=True)),
                                                         magnitude=h - st))
            api.geometry.assign_representation(f, product=sp, representation=rep)

        # Stairs: one IfcStair per stair and level, filling the stair space.
        for s in here:
            if not s.stair:
                continue
            stair = api.root.create_entity(f, ifc_class="IfcStair", predefined_type="NOTDEFINED",
                                           name=f"Escalier {s.stair}")
            api.geometry.edit_object_placement(f, product=stair, matrix=_matrix((0, 0, z)))
            inner = _shrink(s.polygon, wt / 2 + 0.05)
            rep = sb.get_representation(body, sb.extrude(sb.profile(sb.polyline(inner, closed=True)), magnitude=h))
            api.geometry.assign_representation(f, product=stair, representation=rep)
            api.spatial.assign_container(f, products=[stair], relating_structure=storey)

        # Walls on room edges.
        walls_by_seg: dict[tuple, Any] = {}
        for a, b, owners in wall_segments(here):
            kind = classify_wall(owners)
            dx, dy = b[0] - a[0], b[1] - a[1]
            L = math.hypot(dx, dy)
            if L < 0.05:
                continue
            w = api.root.create_entity(f, ifc_class="IfcWall", name=f"Mur {kind}")
            api.geometry.edit_object_placement(f, product=w, matrix=_matrix((a[0], a[1], z), (dx / L, dy / L)))
            rep = api.geometry.add_wall_representation(f, context=body, length=L, height=h - st, thickness=wt,
                                                       offset=-wt / 2)
            api.geometry.assign_representation(f, product=w, representation=rep)
            api.spatial.assign_container(f, products=[w], relating_structure=storey)
            walls_by_seg[(a, b)] = w
            m, fr = material(kind)
            if m:
                api.material.assign_material(f, products=[w], type="IfcMaterial", material=m)
            _pset(f, w, "Pset_WallCommon", {"IsExternal": kind == "facade", "FireRating": fr})

        # Doors, oriented along the wall they sit on.
        segs = wall_segments(here)
        for d in (d for d in doors if d.level == n):
            seg = next(((a, b) for a, b, _ in segs if _on_segment(d.at, a, b)), None)
            if seg is None:
                raise SystemExit(f"door {d.name} at {d.at} is not on a room edge (level {n})")
            (ax, ay), (bx, by) = seg
            L = math.hypot(bx - ax, by - ay)
            ux, uy = (bx - ax) / L, (by - ay) / L
            ox = d.at[0] - ux * d.width / 2 + uy * wt / 2
            oy = d.at[1] - uy * d.width / 2 - ux * wt / 2
            door = api.root.create_entity(f, ifc_class="IfcDoor", name=d.name)
            door.Description = d.description or None
            door.OverallWidth = d.width
            door.OverallHeight = DOOR_HEIGHT
            door.OperationType = "DOUBLE_DOOR_SINGLE_SWING" if d.width >= 1.4 else "SINGLE_SWING_LEFT"
            api.geometry.edit_object_placement(f, product=door, matrix=_matrix((ox, oy, z), (ux, uy)))
            host = walls_by_seg.get(seg)
            if host is not None:      # the opening in the wall, filled by the door (plans cut through it)
                opening = api.root.create_entity(f, ifc_class="IfcOpeningElement", name=f"Baie {d.name}")
                api.geometry.edit_object_placement(f, product=opening, matrix=_matrix((ox, oy, z), (ux, uy)))
                prof = sb.profile(sb.rectangle(size=(d.width + 0.02, wt + 0.1), position=(-0.01, -0.05)))
                api.geometry.assign_representation(f, product=opening, representation=sb.get_representation(
                    body, sb.extrude(prof, magnitude=DOOR_HEIGHT)))
                api.feature.add_feature(f, feature=opening, element=host)
                api.feature.add_filling(f, opening=opening, element=door)
            rep = api.geometry.add_door_representation(
                f, context=body, overall_height=DOOR_HEIGHT, overall_width=d.width,
                lining_properties={"LiningDepth": wt, "LiningThickness": 0.05})
            if rep is not None:
                api.geometry.assign_representation(f, product=door, representation=rep)
            api.spatial.assign_container(f, products=[door], relating_structure=storey)
            _pset(f, door, "Pset_DoorCommon", {"IsExternal": True if d.external else None,
                                               "FireRating": d.fire_rating})

    out.parent.mkdir(parents=True, exist_ok=True)
    f.write(str(out))
    return out


def _outline(spaces: list[Space]) -> list[tuple[float, float]]:
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    if not spaces:
        return []
    u = unary_union([Polygon(s.polygon).buffer(0.001, join_style="mitre") for s in spaces]).buffer(
        -0.001, join_style="mitre")
    if u.geom_type != "Polygon":
        u = max(u.geoms, key=lambda g: g.area)
    return [(round(x, 4), round(y, 4)) for x, y in list(u.exterior.coords)[:-1]]


def _shrink(poly: list[tuple[float, float]], d: float) -> list[tuple[float, float]]:
    from shapely.geometry import Polygon
    g = Polygon(poly).buffer(-d, join_style="mitre")
    return [(round(x, 4), round(y, 4)) for x, y in list(g.exterior.coords)[:-1]]


def main(argv: Optional[list[str]] = None) -> None:
    ap = argparse.ArgumentParser(description="trace.yaml → IFC4")
    ap.add_argument("trace", type=Path)
    ap.add_argument("-o", "--out", type=Path, help="output .ifc (default: next to the trace)")
    args = ap.parse_args(argv)
    out = args.out or args.trace.with_suffix(".ifc")
    print(build(args.trace, out))


if __name__ == "__main__":
    main()
