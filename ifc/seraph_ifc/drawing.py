"""Floor plans the way an architect draws them, from any IFC: a horizontal cut through the model above each floor.

Per level, in world metres (plans.py turns them into the 0–1000 frame):
- walls, columns, curtain walls, windows: the real cross-section 1.10 m above the floor (door and window openings
  are already cut out of the walls by the geometry engine), walls classed façade / structure / partition by
  IsExternal and real thickness;
- railings: cut 0.60 m above the floor (balconies);
- doors: leaf + swing arc from the door's placement, width and operation type (IFC convention: the leaf swings
  towards the door's local +y; hinge on the left or right as seen along +y). Unknown type → no swing drawn;
- stairs: the treads of the flight going up from this level (up-facing faces of the stair, its flights and parts),
  solid below the cut, dashed above, and the walking line with its arrow towards the top;
- ramps: outline and an arrow up the slope (fitted plane).
Nothing is drawn that the model does not contain.
"""
from __future__ import annotations

import math
import multiprocessing
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np
from shapely.geometry import LineString, MultiPolygon, Polygon
from shapely.ops import linemerge, unary_union

import ifcopenshell
import ifcopenshell.geom
import ifcopenshell.util.element as E
import ifcopenshell.util.placement
import ifcopenshell.util.unit

from .props import pset_value

CUT_H = 1.10
RAIL_H = 0.60
PARTITION_T = 0.15        # m: thinner walls are partitions
SWING_TYPES = {"SINGLE_SWING_LEFT", "SINGLE_SWING_RIGHT", "DOUBLE_DOOR_SINGLE_SWING", "DOUBLE_SWING_LEFT",
               "DOUBLE_SWING_RIGHT", "DOUBLE_DOOR_DOUBLE_SWING", "SWING_FIXED_LEFT", "SWING_FIXED_RIGHT"}
SLIDE_TYPES = {"SLIDING_TO_LEFT", "SLIDING_TO_RIGHT", "DOUBLE_DOOR_SLIDING"}


@dataclass
class Mesh:
    v: np.ndarray            # (n, 3) world metres
    f: np.ndarray            # (m, 3) vertex indices

    @property
    def zmin(self) -> float:
        return float(self.v[:, 2].min())

    @property
    def zmax(self) -> float:
        return float(self.v[:, 2].max())


@dataclass
class LevelDrawing:
    level: int
    walls: list[tuple[Polygon, str]] = field(default_factory=list)      # (section, facade|structure|partition)
    columns: list[Polygon] = field(default_factory=list)
    windows: list[Polygon] = field(default_factory=list)
    railings: list[Any] = field(default_factory=list)                    # polygons or lines
    doors: list[dict] = field(default_factory=list)                      # {"leaves": [...], "arcs": [...]}
    stairs: list[dict] = field(default_factory=list)                     # {"below", "above", "path"}
    ramps: list[dict] = field(default_factory=list)                      # {"outline", "arrow"}
    shafts: list[Polygon] = field(default_factory=list)


# ───────── meshes ─────────
def meshes(f: ifcopenshell.file, elements: list) -> dict[int, Mesh]:
    out: dict[int, Mesh] = {}
    if not elements:
        return out
    s = ifcopenshell.geom.settings()
    s.set("use-world-coords", True)
    it = ifcopenshell.geom.iterator(s, f, max(1, multiprocessing.cpu_count() - 1), include=elements)
    if not it.initialize():
        return out
    while True:
        sh = it.get()
        v = np.array(sh.geometry.verts, dtype=float).reshape(-1, 3)
        fc = np.array(sh.geometry.faces, dtype=int).reshape(-1, 3)
        if len(v) and len(fc):
            out[sh.id] = Mesh(v, fc)
        if not it.next():
            break
    return out


def section(m: Mesh, z: float) -> tuple[list[Polygon], list[LineString]]:
    """Cut a closed mesh with the plane at height z → cross-section polygons (holes by even-odd), open bits."""
    z = z + 1e-5
    d = m.v[:, 2] - z
    tri = m.f
    side = d[tri] > 0
    mixed = side.any(axis=1) & ~side.all(axis=1)
    segs = []
    for t in tri[mixed]:
        pts = []
        for i, j in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0])):
            if (d[i] > 0) != (d[j] > 0):
                a, b = (i, j) if i < j else (j, i)        # same formula on both triangles sharing the edge
                k = d[a] / (d[a] - d[b])
                p = m.v[a] + k * (m.v[b] - m.v[a])
                pts.append((round(p[0], 6), round(p[1], 6)))
        if len(pts) == 2 and pts[0] != pts[1]:
            segs.append(LineString(pts))
    if not segs:
        return [], []
    merged = linemerge(segs)
    lines = list(merged.geoms) if hasattr(merged, "geoms") else [merged]
    polys, opened = [], []
    for ln in lines:
        if ln.is_ring and len(ln.coords) >= 4:
            p = Polygon(ln.coords)
            if p.is_valid and p.area > 1e-5:
                polys.append(p)
            elif not p.is_valid:
                p = p.buffer(0)
                if p.area > 1e-5:
                    polys += list(p.geoms) if hasattr(p, "geoms") else [p]
        else:
            opened.append(ln)
    if len(polys) > 1:          # even-odd: inner rings of one solid are its holes
        acc = None
        for p in sorted(polys, key=lambda p: -p.area):
            acc = p if acc is None else acc.symmetric_difference(p)
        polys = [g for g in (acc.geoms if hasattr(acc, "geoms") else [acc]) if isinstance(g, Polygon) and g.area > 1e-5]
    return polys, opened


def up_faces(m: Mesh, nz_min: float, nz_max: float = 1.01) -> list[tuple[float, Polygon, np.ndarray]]:
    """Upward-facing triangles whose normal's z is in [nz_min, nz_max] → (mean z, projected triangle, normal)."""
    a, b, c = m.v[m.f[:, 0]], m.v[m.f[:, 1]], m.v[m.f[:, 2]]
    n = np.cross(b - a, c - a)
    ln = np.linalg.norm(n, axis=1)
    ok = ln > 1e-9
    n[ok] /= ln[ok, None]
    out = []
    for i in np.nonzero(ok & (n[:, 2] >= nz_min) & (n[:, 2] <= nz_max))[0]:
        p = Polygon([a[i, :2], b[i, :2], c[i, :2]])
        if p.is_valid and p.area > 1e-6:
            out.append((float((a[i, 2] + b[i, 2] + c[i, 2]) / 3), p, n[i]))
    return out


def with_parts(el) -> list:
    """The element and, recursively, the parts it aggregates (IfcRelAggregates: IfcBuildingElementPart, flights,
    landings). Archicad exports layered walls, slabs, stairs and ramps as parts and gives the element no body of its
    own. Openings (IfcFeatureElement) and the doors and windows filling them are not parts."""
    out, todo = [el], [el]
    while todo:
        cur = todo.pop()
        for rel in getattr(cur, "IsDecomposedBy", None) or []:
            for p in rel.RelatedObjects:
                if p.is_a("IfcFeatureElement") or p.is_a("IfcSpatialElement"):
                    continue
                out.append(p)
                todo.append(p)
    return out


# ───────── per element kind ─────────
def _wall_class(el, poly: Polygon) -> str:
    psets = E.get_psets(el)
    if el.is_a("IfcCurtainWall") or (psets.get("Pset_WallCommon") or {}).get("IsExternal") is True:
        return "facade"
    t = 2 * poly.area / max(poly.length, 1e-6)
    return "structure" if t >= PARTITION_T else "partition"


def _operation(door) -> Optional[str]:
    """The door's operation type: on the door (IFC4) or on its type (IfcDoorType / IfcDoorStyle)."""
    op = getattr(door, "OperationType", None)
    if not op or op in ("NOTDEFINED", "USERDEFINED"):
        t = E.get_type(door)
        op = getattr(t, "OperationType", None) if t is not None else None
    return op if op not in (None, "NOTDEFINED", "USERDEFINED") else None


def _door_symbol(door, m: Mesh, scale: float) -> Optional[dict]:
    op = _operation(door)
    M = np.array(ifcopenshell.util.placement.get_local_placement(door.ObjectPlacement), dtype=float)
    R, t = M[:3, :3], M[:3, 3] * scale
    loc = (m.v - t) @ R                       # door-local coordinates (metres)
    x0, x1 = float(loc[:, 0].min()), float(loc[:, 0].max())
    yface = float(loc[:, 1].max())            # the wall face on the swing side (+y)
    width = float(door.OverallWidth) * scale if getattr(door, "OverallWidth", None) else x1 - x0
    if x1 - x0 > 0.2:
        width = min(width, x1 - x0) if width > 0.2 else x1 - x0
    xa, xb = (x0, x0 + width) if abs((x0 + width) - x1) < abs(x0 - (x1 - width)) else (x1 - width, x1)
    mirrored = np.linalg.det(R) < 0
    left, right = (xa, xb) if not mirrored else (xb, xa)

    def world(x: float, y: float) -> tuple[float, float]:
        p = t + R @ np.array([x, y, 0.0])
        return float(p[0]), float(p[1])

    yback = float(loc[:, 1].min())            # the other face (double-acting doors swing both ways)

    def swing(hinge: float, free: float, radius: float, sign: float = 1.0) -> tuple[list, list]:
        """Open leaf (hinge → hinge + radius·sign·y) and the quarter arc from the closed leaf's tip to it."""
        y0 = yface if sign > 0 else yback
        r = abs(free - hinge)
        arc = [world(hinge + (free - hinge) * math.cos(k / 12 * math.pi / 2), y0 + sign * r * math.sin(k / 12 * math.pi / 2))
               for k in range(13)]
        return [world(hinge, y0), world(hinge, y0 + sign * radius)], arc

    sym = {"leaves": [], "arcs": [], "slides": [], "op": op, "jamb": [world(xa, yface), world(xb, yface)],
           "fire_rating": pset_value(door, "Pset_DoorCommon", "FireRating")}
    if op in ("SINGLE_SWING_LEFT", "SWING_FIXED_LEFT"):
        leaf, arc = swing(left, right, width)
        sym["leaves"].append(leaf)
        sym["arcs"].append(arc)
    elif op in ("SINGLE_SWING_RIGHT", "SWING_FIXED_RIGHT"):
        leaf, arc = swing(right, left, width)
        sym["leaves"].append(leaf)
        sym["arcs"].append(arc)
    elif op in ("DOUBLE_DOOR_SINGLE_SWING",):
        mid = (left + right) / 2
        for h in (left, right):
            leaf, arc = swing(h, mid, width / 2)
            sym["leaves"].append(leaf)
            sym["arcs"].append(arc)
    elif op in ("DOUBLE_SWING_LEFT", "DOUBLE_SWING_RIGHT", "DOUBLE_DOOR_DOUBLE_SWING"):
        hinges = [left] if op == "DOUBLE_SWING_LEFT" else [right] if op == "DOUBLE_SWING_RIGHT" else [left, right]
        for h in hinges:
            free = (right if h == left else left) if len(hinges) == 1 else (left + right) / 2
            r = abs(free - h)
            for sgn in (1.0, -1.0):
                leaf, arc = swing(h, free, r, sgn)
                sym["leaves"].append(leaf)
                sym["arcs"].append(arc)
    elif op in SLIDE_TYPES:
        sym["slides"].append([world(xa, yface), world(xb, yface)])
    elif not sym["fire_rating"]:
        return None           # unknown operation and nothing to say: the wall's opening is enough
    return sym


def _stair_drawing(meshes_: list[Mesh], z_floor: float, z_next: Optional[float], z_cut: float) -> Optional[dict]:
    """Treads of the flight going up from this floor + the walking line, from the up-facing faces."""
    top = (z_next - 0.05) if z_next is not None else z_floor + 4.0
    bins: dict[float, list[Polygon]] = defaultdict(list)
    for m in meshes_:
        for z, p, _ in up_faces(m, 0.95):
            if z_floor + 0.06 < z < top:
                bins[round(z / 0.02) * 0.02].append(p)
    if not bins:
        return None
    treads = []
    for z, ps in sorted(bins.items()):
        u = unary_union(ps).buffer(0.002).buffer(-0.002)
        for g in (u.geoms if hasattr(u, "geoms") else [u]):
            if isinstance(g, Polygon) and g.area > 0.03:
                treads.append((z, g.simplify(0.005)))
    if len(treads) < 3:          # a flight has treads; 2 stray faces (a landing edge, a nosing) are not one
        return None
    path = []
    for z, g in treads:
        c = g.centroid
        if not path or math.hypot(c.x - path[-1][0], c.y - path[-1][1]) > 0.05:
            path.append((c.x, c.y))
    return {"below": [g for z, g in treads if z <= z_cut], "above": [g for z, g in treads if z > z_cut],
            "path": _straighten(path)}


def _straighten(path: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Keep the turning points of the walking line only."""
    if len(path) < 3:
        return path
    out = [path[0]]
    for a, b, c in zip(path, path[1:], path[2:]):
        v1 = (b[0] - a[0], b[1] - a[1])
        v2 = (c[0] - b[0], c[1] - b[1])
        cross = v1[0] * v2[1] - v1[1] * v2[0]
        n = math.hypot(*v1) * math.hypot(*v2)
        if n and abs(cross) / n > 0.25:
            out.append(b)
    out.append(path[-1])
    return out


def _ramp_drawing(meshes_: list[Mesh]) -> Optional[dict]:
    faces = [(z, p, n) for m in meshes_ for z, p, n in up_faces(m, 0.30, 0.995)]
    if not faces:
        return None
    outline = unary_union([p for _, p, _ in faces]).buffer(0.01).buffer(-0.01)
    pts = np.array([(p.centroid.x, p.centroid.y, z) for z, p, _ in faces])
    A = np.c_[pts[:, 0], pts[:, 1], np.ones(len(pts))]
    (gx, gy, _), *_ = np.linalg.lstsq(A, pts[:, 2], rcond=None)
    g = math.hypot(gx, gy)
    if g < 1e-4:
        return None
    ux, uy = gx / g, gy / g
    c = outline.centroid
    half = 0.35 * max(outline.bounds[2] - outline.bounds[0], outline.bounds[3] - outline.bounds[1])
    return {"outline": outline, "arrow": [(c.x - ux * half, c.y - uy * half), (c.x + ux * half, c.y + uy * half)],
            "slope_pct": round(100 * g, 1)}


# ───────── all levels ─────────
def build(f: ifcopenshell.file, elevation: dict[int, float], shafts: dict[int, list[Polygon]]) -> dict[int, LevelDrawing]:
    scale = ifcopenshell.util.unit.calculate_unit_scale(f)
    levels = sorted(elevation)
    nxt = {n: (elevation[levels[i + 1]] if i + 1 < len(levels) else None) for i, n in enumerate(levels)}
    walls = list(f.by_type("IfcWall")) + list(f.by_type("IfcCurtainWall"))
    columns = list(f.by_type("IfcColumn"))
    windows = list(f.by_type("IfcWindow"))
    railings = list(f.by_type("IfcRailing"))
    doors = list(f.by_type("IfcDoor"))
    stairs = list(f.by_type("IfcStair"))
    ramps = list(f.by_type("IfcRamp"))

    stair_parts = {s.id(): with_parts(s) for s in stairs}
    ramp_parts = {r.id(): with_parts(r) for r in ramps}
    loose_flights = [x for x in f.by_type("IfcStairFlight") if not any(x in v for v in stair_parts.values())]
    solid = {el.id(): with_parts(el) for el in walls + columns + windows + railings}   # layered walls → parts
    everything = [x for v in solid.values() for x in v] + doors + \
        [x for v in stair_parts.values() for x in v] + [x for v in ramp_parts.values() for x in v] + loose_flights
    ms = meshes(f, list({e.id(): e for e in everything}.values()))

    def cut(el, z: float) -> tuple[list[Polygon], list[LineString]]:
        """Section of an element at z: its own body, or the union of its parts' (one wall, all its layers)."""
        polys, lines = [], []
        for part in solid[el.id()]:
            m = ms.get(part.id())
            if m is not None and m.zmin <= z <= m.zmax:
                p, l = section(m, z)
                polys += p
                lines += l
        if len(polys) > 1:
            u = unary_union([p.buffer(0.001, join_style="mitre") for p in polys]).buffer(-0.001, join_style="mitre")
            polys = [g for g in (u.geoms if hasattr(u, "geoms") else [u]) if isinstance(g, Polygon) and g.area > 1e-5]
        return polys, lines

    out = {n: LevelDrawing(level=n, shafts=list(shafts.get(n, []))) for n in levels}
    for n in levels:
        z0 = elevation[n]
        zc, zr = z0 + CUT_H, z0 + RAIL_H
        d = out[n]
        for el in walls:
            for p in cut(el, zc)[0]:
                d.walls.append((p, _wall_class(el, p)))
        for el in columns:
            d.columns += cut(el, zc)[0]
        for el in windows:
            d.windows += cut(el, zc)[0]
        for el in railings:
            polys, lines = cut(el, zr)
            d.railings += polys + lines
        for el in doors:
            m = ms.get(el.id())
            if m is None or not (z0 - 0.35 <= m.zmin <= z0 + 0.5):
                continue
            sym = _door_symbol(el, m, scale)
            if sym:
                d.doors.append(sym)
        prev = max((m for m in levels if m < n), default=None)
        for sid, els in stair_parts.items():
            mm = [ms[e.id()] for e in els if e.id() in ms]
            st = _stair_drawing(mm, z0, nxt[n], zc) if mm else None
            if st:
                d.stairs.append(st)
        if not d.stairs and prev is not None:
            # Top floor: no flight goes up from here, so draw the flights arriving (seen from above, all solid).
            for sid, els in stair_parts.items():
                mm = [ms[e.id()] for e in els if e.id() in ms]
                arr = _stair_drawing(mm, elevation[prev], z0, z0 + 10.0) if mm else None
                if arr:
                    d.stairs.append(arr)
        for el in loose_flights:
            m = ms.get(el.id())
            st = _stair_drawing([m], z0, nxt[n], zc) if m is not None else None
            if st:
                d.stairs.append(st)
        for rid, els in ramp_parts.items():
            mm = [ms[e.id()] for e in els if e.id() in ms]
            if not mm:
                continue
            lo = min(m.zmin for m in mm)
            if z0 - 0.4 <= lo < (nxt[n] if nxt[n] is not None else z0 + 4.0) - 0.4:   # the ramp starts in this storey
                r = _ramp_drawing(mm)
                if r:
                    d.ramps.append(r)
    return out
