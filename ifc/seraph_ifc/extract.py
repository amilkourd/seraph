"""Any IFC → what Seraph uses. Offline, once per building; nothing parses IFC live.

    uv run ifc-extract dev/dev.ifc -o out-dev/
    → out-dev/building.json      the `Building` contract (contracts/types.ts): levels, stairs, entrances, rooms with
                                 plan zones, doors, materials, route graph in metres, model provenance
    → out-dev/levels/L<n>.svg    one plan per level, 1000×1000, same frame as rooms[].zone (image_id "ifc-L<n>")
    → out-dev/report.txt         what was found, what was ignored, the checks

Exit code 1 when a check fails (seraph_ifc/checks.py): such a model is not shipped and the registry refuses it.

Kept: storeys, spaces, doors, stairs, and the materials / fire ratings of walls, slabs, roofs and doors. Ignored on
purpose: furniture, sanitary fittings, MEP, wall layers (a layered wall reports its set name or its main layer),
shafts. A material or a fire rating that is not in the IFC is absent from the output. Never guessed.

How spaces become a graph:
- a door links the 2 spaces whose footprint is within 0.5 m of its centre (IfcRelSpaceBoundary first when present);
- an opening without a door (IfcVirtualElement boundary, or a stair space touching a corridor) links its 2 spaces;
- a space lying inside another one (parking bays in a garage) is linked to it;
- an outdoor space (terrace, balcony: IsExternal or by name) on the ground level opens on `outside`; above the
  ground it is a façade rescue point (fire-service ladders), never an exit;
- an external door on the ground level or below is an entrance `entrance:E<n>`; above, it is a façade door;
- stair spaces stacked in plan are one stair `stair:<X>`; on each level it lands on `level:<n>`, which links to what
  its door or opening gives on. Edge lengths in metres; a stair counts 2 m walked per metre of rise.
`ids.yaml` (optional) maps ids (rooms, stairs, entrances, by GlobalId or IFC name), translates labels, names the
front façade and records the building's second escape route when it is the façade (see ifc/README.md).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import yaml
from shapely.geometry import Point, Polygon
from shapely.ops import unary_union

import ifcopenshell
import ifcopenshell.util.element as E
import ifcopenshell.util.placement
import ifcopenshell.util.unit

from . import __version__, checks, drawing, plans
from .drawing import with_parts
from .geometry import Shape, main_polygon, shapes

EXTRACTOR = "seraph_ifc.extract"
DEFAULT_BASE_URL = "http://localhost:8000/building/files"   # Seraph serves out/ there (contracts/api.md)

STAIR_RE = re.compile(r"(escalier|stair|treppe|stiege|cage d.escalier)", re.I)
CIRC_RE = re.compile(r"(circulation|couloir|corridor|d[ée]gagement|palier|landing|flur|korridor|gang\b)", re.I)
ELEVATOR_RE = re.compile(r"(ascenseur|elevator|lift\b|aufzug)", re.I)
SHAFT_RE = re.compile(r"(schacht|gaine|shaft|\bvide\b|\bvoid\b)", re.I)
EXTERIOR_RE = re.compile(r"(terrasse|terrace|balkon|balcon|balcony|loggia)", re.I)
STAIR_LETTER_RE = re.compile(r"(?:escalier|stair(?:case|well)?|treppe(?:nhaus)?|esc\.?)\s*([A-Z0-9]{1,2})\b", re.I)
ENTRANCE_NAME_RE = re.compile(r"^E\d+$")
SHORT_ID_RE = re.compile(r"^[\w.\-]{1,8}$")

DOOR_TOL = 0.5          # m: a door links the spaces whose footprint is this close to its centre (docs/10-ifc.md)
FACADE_TOL = 0.7        # m: a door this close to the level outline is on the outer wall
NESTED = 0.6            # a space with this share of its area inside another space is part of it
STAIR_FACTOR = 2.0      # m walked on a stair per m of rise (flights + landings), for edge lengths only
SIDE_FR = {"front": "façade principale", "left": "côté gauche", "right": "côté droit", "rear": "arrière"}
IGNORED = ["IfcFurnishingElement", "IfcFurniture", "IfcSanitaryTerminal", "IfcFlowTerminal", "IfcFlowSegment",
           "IfcFlowFitting", "IfcDistributionElement", "IfcBuildingElementProxy", "IfcCovering", "IfcRailing",
           "IfcWindow", "IfcColumn", "IfcBeam", "IfcMember", "IfcPlate"]
KIND_USE = {"corridor": "circulation", "elevator": "ascenseur", "stair": "escalier", "exterior": "extérieur"}


@dataclass
class Sp:
    el: Any
    level: int
    name: str
    long_name: str                 # as in the IFC
    display: str                   # long name translated by ids.yaml `labels`
    use: Optional[str]
    poly: Polygon
    kind: str                      # room | corridor | stair | elevator | exterior   (shafts are dropped)
    stair_key: Optional[str] = None
    node: str = ""
    room_id: str = ""

    @property
    def centre(self) -> tuple[float, float]:
        c = self.poly.centroid
        if not self.poly.contains(c):
            c = self.poly.representative_point()
        return c.x, c.y

    @property
    def label(self) -> str:
        if self.room_id.startswith("corridor:"):
            return self.display or "Circulation"
        if not self.display or self.display == self.room_id:
            return self.room_id
        return f"{self.room_id} {self.display}"


@dataclass
class Result:
    building: dict[str, Any]
    svgs: dict[str, str]
    report: str
    checks: list[checks.Check]
    unlinked: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(c.ok for c in self.checks)


# ───────── IFC reading helpers ─────────
def storey_of(el) -> Any:
    cur, hops = el, 0
    while cur is not None and hops < 12:
        if cur.is_a("IfcBuildingStorey"):
            return cur
        cur = E.get_container(cur) or E.get_aggregate(cur)
        hops += 1
    return None


from .props import NOT_A_VALUE, pset_value  # noqa: E402,F401  (« ND » = nicht definiert is not a fire rating)


def material_name(el) -> Optional[str]:
    m = E.get_material(el, should_skip_usage=True)
    if m is None:
        return None
    if m.is_a("IfcMaterial"):
        return m.Name
    if m.is_a("IfcMaterialLayerSet"):
        if m.LayerSetName:
            return m.LayerSetName
        layers = [l for l in (m.MaterialLayers or []) if l.Material]
        return max(layers, key=lambda l: l.LayerThickness or 0).Material.Name if layers else None
    if m.is_a("IfcMaterialConstituentSet"):
        cs = [c for c in (m.MaterialConstituents or []) if c.Material]
        return m.Name or (cs[0].Material.Name if cs else None)
    if m.is_a("IfcMaterialProfileSet"):
        ps = [p for p in (m.MaterialProfiles or []) if p.Material]
        return m.Name or (ps[0].Material.Name if ps else None)
    if m.is_a("IfcMaterialList"):
        return m.Materials[0].Name if m.Materials else None
    return None


def header_time(f: ifcopenshell.file) -> str:
    """The IFC's own timestamp: extraction output stays identical for the same file (idempotent registry)."""
    try:
        ts = f.header.file_name.time_stamp
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat(
            timespec="seconds").replace("+00:00", "Z")
    except Exception:
        return "1970-01-01T00:00:00Z"


def level_label(n: int) -> str:
    return "RDC" if n == 0 else (f"R+{n}" if n > 0 else f"R{n}")


def classify(name: str, long_name: str, use: Optional[str], external: bool = False) -> str:
    texts = [use] if use else [long_name, name]
    for t in texts:
        if not t:
            continue
        if STAIR_RE.search(t):
            return "stair"
        if ELEVATOR_RE.search(t):
            return "elevator"
        if SHAFT_RE.search(t):
            return "shaft"
        if EXTERIOR_RE.search(t):
            return "exterior"
        if CIRC_RE.search(t):
            return "corridor"
    return "exterior" if external else "room"


def translate(text: str, labels: dict[str, str]) -> str:
    """Display label from ids.yaml `labels` (exact match first, then the first word): « Zimmer » → « Chambre »."""
    t = (text or "").strip()
    if not labels or not t:
        return t
    if t in labels:
        return labels[t]
    first, _, rest = t.partition(" ")
    return f"{labels[first]} {rest}".strip() if first in labels else t


def stair_letter(sp: Sp) -> Optional[str]:
    if re.fullmatch(r"[A-Z0-9]{1,2}", sp.name or ""):
        return sp.name
    for t in (sp.long_name, sp.name):
        m = STAIR_LETTER_RE.search(t or "")
        if m:
            return m.group(1).upper()
    return None


def _round(x: float) -> float:
    return round(x, 1)


# ───────── Extraction ─────────
def extract(path: Path, ids: Optional[dict] = None, base_url: str = DEFAULT_BASE_URL,
            provenance: Optional[str] = None, provenance_fr: Optional[str] = None,
            name: Optional[str] = None) -> Result:
    ids = ids or {}
    labels: dict[str, str] = ids.get("labels") or {}
    f = ifcopenshell.open(str(path))
    scale = ifcopenshell.util.unit.calculate_unit_scale(f)
    at = header_time(f)
    src = {"kind": "ifc", "label": "maquette", "confirmed": True, "at": at}
    notes: list[str] = []

    # Provenance: CLI > ids.yaml > Seraph_Provenance pset (our authored files) > « IFC architecte ».
    bldg = (f.by_type("IfcBuilding") or [None])[0]
    prov_pset = E.get_psets(bldg).get("Seraph_Provenance", {}) if bldg else {}
    provenance = provenance or ids.get("provenance") or prov_pset.get("provenance") or "architect"
    provenance_fr = provenance_fr or ids.get("provenance_fr") or prov_pset.get("provenance_fr") or {
        "architect": "Maquette IFC architecte",
        "rebuilt_from_posted_plan": "Maquette IFC reconstruite depuis le plan affiché — exercice",
        "fictional": "Bâtiment fictif — maquette IFC d'exercice",
    }.get(provenance, "Maquette IFC")
    name = name or ids.get("name")

    # Geometry for the elements we keep.
    spaces_el = f.by_type("IfcSpace")
    doors_el = f.by_type("IfcDoor")
    stairs_el = f.by_type("IfcStair") or f.by_type("IfcStairFlight")
    walls_el = f.by_type("IfcWall") + f.by_type("IfcCurtainWall")
    slabs_el = [p for sl in f.by_type("IfcSlab") for p in with_parts(sl)]      # layered slabs: geometry on parts
    geo = shapes(f, list({e.id(): e for e in list(spaces_el) + list(doors_el) + list(stairs_el) + slabs_el +
                          (list(walls_el) if len(walls_el) < 5000 else [])}.values()))

    def elev(s) -> float:
        if s.Elevation is not None:
            return float(s.Elevation) * scale
        try:
            return float(ifcopenshell.util.placement.get_local_placement(s.ObjectPlacement)[2][3]) * scale
        except Exception:
            return 0.0

    all_storeys = sorted(f.by_type("IfcBuildingStorey"), key=elev)

    # Spaces, classified. Shafts are dropped (nobody is in a shaft).
    raw: list[tuple[Any, Optional[Polygon], Any, str, str, Optional[str], str]] = []
    shafts_raw: list[tuple[Any, Polygon, Any]] = []
    for el in spaces_el:
        g = geo.get(el.id())
        poly = main_polygon(g.footprint) if g else None
        nm = (el.Name or "").strip()
        ln = (getattr(el, "LongName", None) or "").strip()
        use = (el.ObjectType or "").strip() or None
        ext = pset_value(el, "Pset_SpaceCommon", "IsExternal") is True
        kind = classify(nm, ln, use, ext)
        if kind == "shaft":                      # not a place, not a route: drawn on the plan only
            if poly is not None:
                shafts_raw.append((el, poly, g))
            continue
        if poly is None or poly.area < 0.5:
            notes.append(f"space {nm or ln or el.GlobalId!r} skipped: no usable footprint")
            continue
        raw.append((el, poly, g, nm, ln, use, kind))

    # Storeys → levels: only storeys holding a room, corridor or stair; ground = elevation closest to 0.
    used = {storey_of(el) for el, *_rest, kind in raw if kind in ("room", "corridor", "stair", "exterior")}
    storeys = [s for s in all_storeys if s in used] or all_storeys
    dropped = [s for s in all_storeys if s not in storeys]
    ground = min(range(len(storeys)), key=lambda i: (abs(elev(storeys[i])), -elev(storeys[i]))) if storeys else 0
    level_of_storey = {s.id(): i - ground for i, s in enumerate(storeys)}
    elevation = {i - ground: elev(s) for i, s in enumerate(storeys)}

    def level_of(el, shape: Optional[Shape]) -> Optional[int]:
        s = storey_of(el)
        if s is not None and s.id() in level_of_storey:
            return level_of_storey[s.id()]
        if s is not None and s not in storeys:
            return None
        if shape is not None and elevation:
            cands = [n for n, z in elevation.items() if z <= shape.zmin + 0.3]
            return max(cands) if cands else min(elevation)
        return None

    sps: list[Sp] = []
    for el, poly, g, nm, ln, use, kind in raw:
        lv = level_of(el, g)
        if lv is None:
            notes.append(f"space {nm or ln!r} skipped: on a storey that is not a level")
            continue
        disp = translate(ln or nm, labels)
        sps.append(Sp(el=el, level=lv, name=nm, long_name=ln, display=disp,
                      use=use or (disp.lower() if disp else None), poly=poly, kind=kind))

    # Stairs: stair spaces stacked in plan are one stair. Without stair spaces, the IfcStair bodies are used.
    if not any(s.kind == "stair" for s in sps) and stairs_el:
        notes.append("no stair spaces: stairs taken from IfcStair bodies, linked to the spaces they touch")
        for el in stairs_el:
            g = geo.get(el.id())
            poly = main_polygon(g.footprint) if g else None
            if poly is None:
                continue
            levels = [n for n, z in elevation.items() if g.zmin - 0.5 <= z <= g.zmax + 0.1] or [level_of(el, g)]
            for n in levels:
                if n is not None:
                    sps.append(Sp(el=el, level=n, name=el.Name or "", long_name=el.Name or "",
                                  display=translate(el.Name or "", labels), use="escalier", poly=poly, kind="stair"))
    groups: list[list[Sp]] = []
    for sp in sorted((s for s in sps if s.kind == "stair"), key=lambda s: s.level):
        for g_ in groups:
            if any(_overlap(o.poly, sp.poly) > 0.3 for o in g_) and not any(o.level == sp.level for o in g_):
                g_.append(sp)
                break
        else:
            groups.append([sp])
    stair_map = ids.get("stairs") or {}
    taken: set[str] = set()
    named: list[tuple[list[Sp], Optional[str]]] = []
    for g_ in groups:
        letter = None
        for s in g_:
            letter = stair_map.get(s.el.GlobalId) or stair_map.get(s.name) or letter
        letter = letter or next((stair_letter(s) for s in g_ if stair_letter(s)), None)
        if letter in taken:
            letter = None
        if letter:
            taken.add(letter)
        named.append((g_, letter))
    spare = (c for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ" if c not in taken)
    for g_, letter in sorted(named, key=lambda t: (t[0][0].poly.centroid.x, -t[0][0].poly.centroid.y)):
        letter = letter or next(spare)
        for s in g_:
            s.stair_key = letter
            s.node = f"stair:{letter}"

    # Ids. Main corridor of a level = `corridor:<n>`; other circulations are rooms. Room ids: the IFC name when
    # short and unique (« 3.12 »), else `<level>.<nn>` in reading order; ids.yaml `rooms` overrides (GlobalId/name).
    room_map: dict[str, str] = {str(k): str(v) for k, v in (ids.get("rooms") or {}).items()}
    by_level: dict[int, list[Sp]] = defaultdict(list)
    for s in sps:
        by_level[s.level].append(s)
    for n, here in by_level.items():
        # The common circulation: flagged FireExit in the IFC, else the one the stair opens on, else the largest.
        stairs_here = [o for o in here if o.kind == "stair"]
        cs = sorted((s for s in here if s.kind == "corridor"), key=lambda s: (
            pset_value(s.el, "Pset_SpaceFireSafetyRequirements", "FireExit") is not True,
            not any(o.poly.distance(s.poly) <= DOOR_TOL for o in stairs_here),
            -s.poly.area))
        if cs:
            cs[0].room_id = cs[0].node = f"corridor:{n}"
            for s in cs[1:]:
                s.kind = "room"
    names = Counter(s.name for s in sps if s.kind != "stair" and not s.room_id)
    reserved = set(room_map.values())
    for n, here in sorted(by_level.items()):
        k = 0
        for s in sorted((s for s in here if s.kind != "stair" and not s.room_id),
                        key=lambda s: (-round(s.poly.centroid.y), s.poly.centroid.x)):
            mapped = room_map.get(s.el.GlobalId) or (room_map.get(s.name) if s.name else None)
            if mapped:
                s.room_id = mapped
            elif s.name and SHORT_ID_RE.match(s.name) and names[s.name] == 1:
                s.room_id = s.name
            else:
                while True:
                    k += 1
                    rid = f"{n}.{k:02d}"
                    if rid not in reserved:
                        break
                s.room_id = rid
            s.node = s.room_id if s.room_id.startswith("corridor:") else f"room:{s.room_id}"

    # Plan frame, step 1: the building's own axes (step 2, the front at the bottom, needs E1: see Entrances).
    footprint = unary_union([s.poly for s in sps]) if sps else None
    if footprint is None or footprint.is_empty:
        raise SystemExit(f"{path}: no spaces with geometry — nothing to route on")
    theta0 = plans.dominant_angle([s.poly for s in sps])
    centre = (footprint.centroid.x, footprint.centroid.y)
    outlines = {n: unary_union([s.poly for s in here]).buffer(0.3, join_style="mitre")
                for n, here in by_level.items()}

    # Doors → links.
    boundaries: dict[int, list] = defaultdict(list)
    virtual: dict[int, list] = defaultdict(list)
    for rel in f.by_type("IfcRelSpaceBoundary"):
        el = rel.RelatedBuildingElement
        if el is not None and el.is_a("IfcDoor"):
            boundaries[el.id()].append(rel.RelatingSpace)
        elif el is not None and el.is_a("IfcVirtualElement"):
            virtual[el.id()].append(rel.RelatingSpace)
    sp_of_el = {s.el.id(): s for s in sps if s.el.is_a("IfcSpace")}

    links: list[dict[str, Any]] = []
    unlinked: list[str] = []
    for el in doors_el:
        g = geo.get(el.id())
        lv = level_of(el, g)
        dname = (el.Name or el.GlobalId).strip()
        if g is None or lv is None:
            if storey_of(el) in dropped:
                continue
            unlinked.append(f"{dname}: no geometry or storey")
            continue
        p = Point(g.center)
        here = by_level.get(lv, [])
        cands = [s for _, s in sorted(((s.poly.distance(p), s) for s in here if s.poly.distance(p) <= DOOR_TOL),
                                      key=lambda t: t[0])]
        bsp = [sp_of_el[b.id()] for b in boundaries.get(el.id(), []) if b.id() in sp_of_el]
        sides: list[Sp] = []
        for s in bsp + cands:                       # one space per node: same stair or room twice counts once
            if s.node not in {o.node for o in sides}:
                sides.append(s)
        is_ext = pset_value(el, "Pset_DoorCommon", "IsExternal") is True
        on_facade = lv in outlines and outlines[lv].exterior.distance(p) <= FACADE_TOL
        width = float(el.OverallWidth) * scale if getattr(el, "OverallWidth", None) else None
        info = {"el": el, "name": dname, "level": lv, "point": g.center, "width": width,
                "fire_rating": pset_value(el, "Pset_DoorCommon", "FireRating"),
                "description": (el.Description or "").strip() or None}
        inside = [s for s in sides if s.kind != "exterior"]
        outdoor = [s for s in sides if s.kind == "exterior"]
        if inside and outdoor:
            links.append({**info, "a": inside[0], "b": outdoor[0], "external": False})
        elif outdoor and not inside and (is_ext or on_facade):
            links.append({**info, "a": outdoor[0], "b": None, "external": True, "outdoor_only": True,
                          "facade_only": lv > 0})          # bin store, shed: a door to the street, not an entrance
        elif inside and (is_ext or (len(inside) == 1 and on_facade)):
            links.append({**info, "a": inside[0], "b": None, "external": True,
                          "facade_only": lv > 0})          # above ground: a façade door, not an exit
        elif len(sides) >= 2:
            links.append({**info, "a": sides[0], "b": sides[1], "external": False})
        else:
            unlinked.append(f"{dname} (level {lv}): touches {len(sides)} space(s)")

    opened: set[tuple] = set()

    def opening(a: Sp, b: Sp, kind: str) -> None:
        key = (a.level, *sorted((a.node, b.node)))
        if key in opened:
            return
        opened.add(key)
        inter = a.poly.buffer(0.3).intersection(b.poly.buffer(0.3))
        q = inter.centroid if not inter.is_empty else a.poly.centroid
        links.append({"el": None, "name": f"{kind}:{a.node}|{b.node}", "level": a.level, "point": (q.x, q.y),
                      "width": None, "fire_rating": None, "description": None, "a": a, "b": b,
                      "external": False, "adjacency": kind})

    # Openings without a door: virtual boundaries shared by 2 spaces.
    for members in virtual.values():
        ss = [sp_of_el[m.id()] for m in members if m.id() in sp_of_el]
        for i in range(len(ss)):
            for j in range(i + 1, len(ss)):
                if ss[i].level == ss[j].level and ss[i].node != ss[j].node:
                    opening(ss[i], ss[j], "opening")
    # Spaces inside another space (parking bays in a garage).
    for here in by_level.values():
        for s in here:
            if s.kind == "stair":
                continue
            hosts = [o for o in here if o is not s and o.kind != "stair" and o.poly.area > s.poly.area and
                     o.poly.intersection(s.poly).area >= NESTED * s.poly.area]
            if hosts:
                opening(s, min(hosts, key=lambda o: o.poly.area), "inside")
    # Stairs with no door or opening on a level: linked to the circulation they touch.
    linked_levels: dict[str, set[int]] = defaultdict(set)
    reached = {(l["a"].node, l["level"]) for l in links} | {(l["b"].node, l["level"]) for l in links if l["b"]}
    for s in (s for s in sps if s.kind == "stair"):
        if (s.node, s.level) in reached:
            continue
        touch = [o for o in by_level[s.level] if o.kind not in ("stair", "exterior")
                 and o.poly.distance(s.poly) <= DOOR_TOL]
        touch = [o for o in touch if o.kind == "corridor"] or sorted(
            touch, key=lambda o: -o.poly.boundary.intersection(s.poly.buffer(DOOR_TOL)).length)[:1]
        for o in touch:
            opening(s, o, "touch")
    for l in links:
        for s in (l["a"], l["b"]):
            if l.get("adjacency") and s is not None and s.kind == "stair":
                linked_levels[s.stair_key].add(s.level)

    # Entrances: ids from the door name (E1…) or ids.yaml. E1 is the main entrance: its façade is the front, and the
    # plan is turned so the front is at the bottom (frame step 2). Others: numbered front → left → right → rear.
    ext = [l for l in links if l["external"] and not l.get("facade_only") and not l.get("outdoor_only")]
    emap = {str(k): str(v) for k, v in (ids.get("entrances") or {}).items()}
    used_e: set[str] = set()
    for l in ext:
        eid = emap.get(l["el"].GlobalId) or emap.get(l["name"]) or \
            (l["name"] if ENTRANCE_NAME_RE.match(l["name"]) else None)
        l["eid"] = eid if eid not in used_e else None
        if l["eid"]:
            used_e.add(l["eid"])
    frame0 = plans.Frame.fit([s.poly for s in sps], theta0, centre)
    main = next((l for l in ext if l["eid"] == "E1"), None) or (
        max(ext, key=lambda l: (l["level"] == 0, l["width"] or 0)) if ext else None)
    theta = theta0 + (plans.front_turn(frame0, *main["point"]) if main else 0.0)
    frame = plans.Frame.fit([s.poly for s in sps], theta, centre)
    side_of = {"bottom": "front", "left": "left", "right": "right", "top": "rear"}
    for l in ext:
        l["side"] = side_of[frame.side(*l["point"])]
    order = {"front": 0, "left": 1, "right": 2, "rear": 3}
    k = 1
    for l in sorted((l for l in ext if not l["eid"]), key=lambda l: (order[l["side"]], -(l["width"] or 0))):
        while f"E{k}" in used_e:
            k += 1
        l["eid"] = f"E{k}"
        used_e.add(l["eid"])

    # Graph (metres).
    stair_base: dict[str, float] = {}
    for s in sps:
        if s.kind == "stair":
            stair_base[s.stair_key] = min(stair_base.get(s.stair_key, 1e9), elevation.get(s.level, 0.0))
    edges: dict[tuple[str, str], float] = {}

    def edge(a: str, b: str, length: float) -> None:
        if a == b:
            return
        key = tuple(sorted((a, b)))
        edges[key] = min(edges.get(key, math.inf), _round(length))

    def dist(p, q) -> float:
        return math.hypot(p[0] - q[0], p[1] - q[1])

    def rise(s: Sp) -> float:
        return STAIR_FACTOR * max(0.0, elevation.get(s.level, 0.0) - stair_base.get(s.stair_key, 0.0))

    door_ids = Counter(l["name"] for l in links if not l.get("adjacency"))
    for i, l in enumerate(links):
        if not l.get("adjacency"):
            l["id"] = l.get("eid") if l.get("eid") else (
                l["name"] if door_ids[l["name"]] == 1 and not ENTRANCE_NAME_RE.match(l["name"])
                else f"P{l['level']}-{i + 1}")
    facade_nodes: dict[int, list[str]] = defaultdict(list)
    for l in links:
        a, b, pt = l["a"], l["b"], l["point"]
        if l["external"]:
            if l.get("outdoor_only"):
                if not l.get("facade_only"):
                    edge("outside", a.node, 0.0)
                continue
            if l.get("facade_only"):
                node = f"ladder:{l['id']}"           # French window above ground: ladder rescue point
                edge(a.node, node, dist(pt, a.centre))
                facade_nodes[l["level"]].append(node)
                continue
            eid = l["eid"]
            edge("outside", f"entrance:{eid}", 0.0)
            edge(f"entrance:{eid}", a.node, dist(pt, a.centre) + (rise(a) if a.kind == "stair" else 0.0))
            continue
        if a.kind == "stair" and b.kind == "stair":
            edge(a.node, b.node, dist(a.centre, pt) + dist(pt, b.centre))
            continue
        if b.kind == "stair":
            a, b = b, a
        if a.kind == "stair":
            edge(a.node, f"level:{a.level}", rise(a) + dist(a.centre, pt))
            edge(f"level:{a.level}", b.node, dist(pt, b.centre))
        else:
            edge(a.node, b.node, dist(a.centre, pt) + dist(pt, b.centre))
    for s in sps:
        if s.kind == "exterior":
            if s.level == 0:
                edge(s.node, "outside", 0.0)       # a ground-floor terrace is outdoors
            else:                                  # balcony / terrace above ground: ladder rescue point, dead end
                edge(s.node, f"ladder:{s.room_id}", 0.0)
                facade_nodes[s.level].append(f"ladder:{s.room_id}")
    for n in elevation:
        if any(f"level:{n}" in k_ for k_ in edges):
            continue
        hub = [s for s in by_level.get(n, []) if s.kind == "corridor"] or \
            sorted((s for s in by_level.get(n, []) if s.kind == "room"), key=lambda s: -s.poly.area)[:1]
        for s in hub:
            edge(f"level:{n}", s.node, 0.0)

    node_order = {"outside": 0, "entrance": 1, "stair": 2, "level": 3, "corridor": 4, "room": 5, "ladder": 6}
    nodes = sorted({n for k_ in edges for n in k_} | {s.node for s in sps} | {"outside"},
                   key=lambda n: (node_order.get(n.split(":")[0], 9), _natural(n)))
    graph = {"nodes": nodes, "edges": [[a, b, l] for (a, b), l in sorted(edges.items(), key=lambda t: (
        node_order.get(t[0][0].split(":")[0], 9), _natural(t[0][0]), _natural(t[0][1])))]}

    # Contract objects.
    levels_out = []
    outline_world: dict[int, list] = {}
    for n, z in sorted(elevation.items()):
        outline, source, thickness = _level_outline(n, z, slabs_el, geo, sps, elevation)
        outline_world[n] = outline
        levels_out.append({
            "level": n, "label": level_label(n), "elevation_m": round(z, 2),
            "ifc_name": next((s.Name for s in storeys if level_of_storey[s.id()] == n), None),
            "outline": [{"outer": frame.polygon(p.exterior.coords),
                         "holes": [frame.polygon(h.coords) for h in p.interiors]} for p in outline],
            "outline_m": [{"outer": frame.polygon_m(p.exterior.coords),
                           "holes": [frame.polygon_m(h.coords) for h in p.interiors]} for p in outline],
            "outline_source": source,
            **({"slab_thickness_m": thickness} if thickness else {}),
        })
    rooms_out = []
    for s in sorted((s for s in sps if s.kind != "stair"), key=lambda s: (s.level, _natural(s.room_id))):
        rooms_out.append({"id": s.room_id, "level": s.level, "label": s.label, "area_m2": round(s.poly.area, 1),
                          "use": KIND_USE.get(s.kind) if s.kind != "room" else s.use, "kind": s.kind,
                          "zone": frame.polygon(s.poly.exterior.coords), "source": src,
                          **({"ifc_name": s.long_name} if s.long_name and s.long_name != s.display else {}),
                          "ifc_guid": s.el.GlobalId})
    stairs_out = []
    for letter in sorted({s.stair_key for s in sps if s.kind == "stair"}):
        mine = sorted((s for s in sps if s.stair_key == letter), key=lambda s: s.level)
        label = (ids.get("stair_labels") or {}).get(letter) or f"Escalier {letter}"
        own = next((s.display for s in mine if s.display and re.search(r"escalier", s.display, re.I) and
                    re.search(rf"\b{letter}\b", s.display)), None)
        stairs_out.append({"id": letter, "label": own or label, "status": "unknown", "source": src,
                           "levels": sorted({s.level for s in mine}),
                           "zones": [{"level": s.level, "zone": frame.polygon(s.poly.exterior.coords)} for s in mine],
                           **({"linked_levels": sorted(linked_levels[letter])} if linked_levels.get(letter) else {})})

    def plan_point(n: int, pt) -> dict[str, Any]:
        x, y = frame.to_plan(*pt)
        return {"image_id": f"ifc-L{n}", "x": x, "y": y}

    def axis(l) -> str:
        """Which way the door's wall runs on the plan (x or y), from the edge of its first space."""
        q = Point(l["point"])
        ext_ = list(l["a"].poly.exterior.coords)
        best = min(zip(ext_, ext_[1:]), key=lambda e: Point(e[0]).distance(q) + Point(e[1]).distance(q) -
                   Point(e[0]).distance(Point(e[1])))
        (ax_, ay_), (bx_, by_) = frame.to_plan_f(*best[0]), frame.to_plan_f(*best[1])
        return "x" if abs(bx_ - ax_) >= abs(by_ - ay_) else "y"

    entrances_out, doors_out = [], []
    for l in links:
        if l.get("adjacency"):
            continue
        a, b, n = l["a"], l["b"], l["level"]
        common = {"plan_point": plan_point(n, l["point"]), "plan_axis": axis(l),
                  "plan_width": round((l["width"] or 0.9) * frame.scale)}
        fr = {"fire_rating": l["fire_rating"]} if l["fire_rating"] else {}
        if l.get("outdoor_only"):
            doors_out.append({"id": l["id"], "level": n, "label": f"Porte {a.label}", "between": ["outside", a.node],
                              "external": True, **fr, "source": src, **common})
            continue
        if l["external"] and l.get("facade_only"):
            doors_out.append({"id": l["id"], "level": n, "label": f"Porte-fenêtre {a.label}",
                              "between": [a.node, f"ladder:{l['id']}"], "external": True, **fr, "source": src,
                              **common})
            continue
        if l["external"]:
            eid = l["eid"]
            cx, cy = centre
            vx, vy = l["point"][0] - cx, l["point"][1] - cy
            norm = math.hypot(vx, vy) or 1
            out_pt = (l["point"][0] + vx / norm * 1.2, l["point"][1] + vy / norm * 1.2)
            label = (ids.get("entrance_labels") or {}).get(eid) or l["description"] or (
                l["name"] if not ENTRANCE_NAME_RE.match(l["name"]) and not re.match(r"^(tür|door|porte)\b",
                                                                                     l["name"], re.I)
                else f"Entrée {SIDE_FR[l['side']]}")
            entrances_out.append({"id": eid, "label": label, "side": l["side"], "status": "unknown",
                                  "leads_to": a.node, "level": n, "source": src,
                                  "plan_point": plan_point(n, out_pt)})
            doors_out.append({"id": eid, "level": n, "label": label, "between": ["outside", a.node],
                              "external": True, **fr, "source": src, **common})
            continue
        doors_out.append({"id": l["id"], "level": n, "label": l["description"] or _door_label(a, b, n),
                          "between": [a.node, b.node], **fr, "source": src, **common})
    entrances_out.sort(key=lambda e: _natural(e["id"]))

    materials_out = _materials(f, geo, sps, links, level_of, src, ids.get("materials"))

    level_plans = [{"level": lv["level"], "url": f"{base_url.rstrip('/')}/levels/L{lv['level']}.svg",
                    "image_id": f"ifc-L{lv['level']}"} for lv in levels_out]
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    second_route = ids.get("second_route")
    building = {
        "name": name or (bldg.Name if bldg and bldg.Name and bldg.Name != "Building" else path.stem),
        "levels": levels_out,
        "stairs": stairs_out,
        "entrances": entrances_out,
        "hydrants": [],
        "truck_spot": None,
        "rooms": rooms_out,
        "plan": None,
        "hazards": [],
        "approach": None,
        "screenshots": [],
        "doors": doors_out,
        "materials": materials_out,
        "graph": graph,
        "model": {
            "provenance": provenance,
            "provenance_fr": provenance_fr,
            "level_plans": level_plans,
            "stats": {"levels": len(levels_out), "stairs": len(stairs_out), "doors": len(doors_out),
                      "rooms": len([r for r in rooms_out if r["kind"] in ("room", "elevator")])},
            "extractor": {"name": EXTRACTOR, "version": __version__},
            "plan_frame": frame.info(),
            "source_ifc": {"file": path.name, "sha256": sha, "schema": f.schema, "bytes": path.stat().st_size,
                           **({"credit": ids["credit"]} if ids.get("credit") else {}),
                           **({"url": ids["source_url"]} if ids.get("source_url") else {})},
            **({"second_route": second_route} if second_route else {}),
            "ladder_points": {str(n): v for n, v in sorted(facade_nodes.items())},
        },
        "units": _units(sps, links),
    }
    results = checks.run_all(building, unlinked)
    building["model"]["checks"] = {"passed": all(c.ok for c in results),
                                   "failed": [c.name for c in results if not c.ok]}
    shafts_by_level: dict[int, list] = defaultdict(list)
    for el, poly, g in shafts_raw:
        lv_ = level_of(el, g)
        if lv_ is not None:
            shafts_by_level[lv_].append(poly)
    drawings = drawing.build(f, elevation, shafts_by_level)
    north = _true_north(f)
    svgs = {f"levels/L{lv['level']}.svg": plans.level_svg(
        lv, frame, [r for r in rooms_out if r["level"] == lv["level"]], stairs_out,
        [d for d in doors_out if d["level"] == lv["level"]], entrances_out, drawing=drawings.get(lv["level"]),
        outline=outline_world.get(lv["level"]), ladders=facade_nodes.get(lv["level"]), north=north)
        for lv in levels_out}
    report = _report(f, path, sha, building, results, unlinked, notes, dropped, elev, links)
    return Result(building=building, svgs=svgs, report=report, checks=results, unlinked=unlinked)


def _true_north(f) -> tuple[float, float]:
    """Direction of true north in the model's plan coordinates (IfcGeometricRepresentationContext.TrueNorth)."""
    for c in f.by_type("IfcGeometricRepresentationContext"):
        if not c.is_a("IfcGeometricRepresentationSubContext") and getattr(c, "TrueNorth", None) is not None:
            r = c.TrueNorth.DirectionRatios
            return float(r[0]), float(r[1])
    return 0.0, 1.0


def _level_outline(n: int, z: float, slabs_el, geo, sps: list[Sp], elevation: dict[int, float]):
    """The level's floor as it is: the union of the slabs whose top is at the level's elevation (with their own
    openings), or the union of the level's spaces when the IFC has no such slab. Stair and lift shafts that go on
    from the level below are cut out (a no-op where the slab already has the hole).
    → (polygons, "slab" | "spaces", median slab thickness in m or None)."""
    found, depths = [], []
    for el in slabs_el:
        g = geo.get(el.id())
        if g is None or g.footprint is None or not (z - 0.30 <= g.zmax <= z + 0.10):
            continue
        found.append(g.footprint)
        depths.append(g.zmax - g.zmin)
    here = [s for s in sps if s.level == n]
    if found:
        floor, source = unary_union(found), "slab"
    else:   # spaces stop at the wall faces: close the wall gaps (≤ 0.6 m) to get the floor
        floor = unary_union([s.poly for s in here]).buffer(0.3, join_style="mitre").buffer(-0.3, join_style="mitre")
        source = "spaces"
    below = [s for s in sps if s.level == n - 1]
    for s in here:
        if s.kind not in ("stair", "elevator"):
            continue
        if any(o.kind == s.kind and o.poly.intersection(s.poly).area > 0.5 * s.poly.area for o in below):
            floor = floor.difference(s.poly.buffer(-0.05, join_style="mitre"))
    floor = floor.buffer(0.01, join_style="mitre").buffer(-0.01, join_style="mitre").simplify(0.02)
    polys = [p for p in (floor.geoms if hasattr(floor, "geoms") else [floor]) if p.area >= 0.5]
    depths.sort()
    thickness = round(depths[len(depths) // 2], 2) if depths else None
    return sorted(polys, key=lambda p: -p.area), source, thickness


UNIT_HOME_RE = re.compile(r"(chambre|s[ée]jour|cuisine|salon|bedroom|living|kitchen|zimmer|wohn)", re.I)


def _units(sps: list[Sp], links: list[dict]) -> list[dict[str, Any]]:
    """Groups of rooms behind one door from the common circulation (a flat, a set of cellars). Computed from the
    door topology only: « Logement » when it has a bedroom or a living room, « Locaux » otherwise."""
    rooms = {s.node: s for s in sps if s.kind in ("room", "exterior")}
    adj: dict[str, set[str]] = defaultdict(set)
    entry: dict[str, set[str]] = defaultdict(set)
    for l in links:
        a, b = l["a"], l["b"]
        if b is None:
            continue
        if a.node in rooms and b.node in rooms:
            adj[a.node].add(b.node)
            adj[b.node].add(a.node)
        for x, y in ((a, b), (b, a)):
            if x.node in rooms and y.kind in ("corridor", "stair"):
                entry[x.node].add(l.get("id") or l["name"])
    seen: set[str] = set()
    out = []
    for level in sorted({s.level for s in rooms.values()}):
        k = 0
        for start in sorted((n for n, s in rooms.items() if s.level == level), key=lambda n: _natural(n)):
            if start in seen:
                continue
            comp, stack = [], [start]
            while stack:
                n = stack.pop()
                if n in seen:
                    continue
                seen.add(n)
                comp.append(n)
                stack += [m for m in adj[n] if m not in seen]
            members = [rooms[n] for n in comp]
            inside = [s for s in members if s.kind == "room"]
            if not inside:
                continue
            k += 1
            home = any(UNIT_HOME_RE.search(s.display or "") for s in inside)
            out.append({"id": f"U{level}.{k}", "level": level, "label": "Logement" if home else "Locaux",
                        "rooms": sorted((s.room_id for s in inside), key=_natural),
                        "outdoor": sorted((s.room_id for s in members if s.kind == "exterior"), key=_natural),
                        "entry": sorted({d for s in inside for d in entry[s.node]}, key=_natural)})
    return out


def _overlap(a: Polygon, b: Polygon) -> float:
    inter = a.intersection(b).area
    return inter / max(min(a.area, b.area), 1e-9)


def _natural(s: str) -> list:
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", s)]


def _door_label(a: Sp, b: Sp, n: int) -> str:
    for s in (a, b):
        if s.kind == "stair":
            return f"Porte escalier {s.stair_key} ({level_label(n)})"
    for s in (a, b):
        if s.kind == "exterior":
            return f"Porte-fenêtre {s.label}"
    for s in (a, b):
        if s.kind in ("room", "elevator"):
            return f"Porte {s.label}"
    return f"Porte {a.label} – {b.label}"


def _materials(f, geo, sps: list[Sp], links, level_of, src, names: Optional[dict] = None) -> list[dict[str, Any]]:
    """Per element kind and level, what the IFC says it is made of, with FireRating when set."""
    groups: dict[tuple, list] = defaultdict(list)
    rooms_by_level: dict[int, list[Sp]] = defaultdict(list)
    for s in sps:
        if s.kind in ("room", "elevator"):
            rooms_by_level[s.level].append(s)

    def add(kind: str, el, touched: Optional[set[str]]):
        mat = material_name(el)
        if not mat:
            return
        lv = level_of(el, geo.get(el.id()))
        if lv is None:
            return
        pset = {"door": "Pset_DoorCommon", "slab": "Pset_SlabCommon", "roof": "Pset_RoofCommon"}.get(
            kind, "Pset_CurtainWallCommon" if el.is_a("IfcCurtainWall") else "Pset_WallCommon")
        fr = pset_value(el, pset, "FireRating")
        if kind == "roof" and fr is None and el.is_a("IfcSlab"):
            fr = pset_value(el, "Pset_SlabCommon", "FireRating")
        groups[(kind, lv, mat, fr)].append(touched)

    for el in f.by_type("IfcWall") + f.by_type("IfcCurtainWall"):
        ext = el.is_a("IfcCurtainWall") or pset_value(el, "Pset_WallCommon", "IsExternal") is True
        g = geo.get(el.id())
        touched = None
        if g is not None and g.footprint is not None:
            lv = level_of(el, g)
            touched = {s.room_id for s in rooms_by_level.get(lv, []) if s.poly.intersection(g.footprint).area > 0.05}
        add("facade" if ext else "wall", el, touched)
    for el in f.by_type("IfcSlab"):
        add("roof" if el.PredefinedType == "ROOF" else "slab", el, None)
    for el in f.by_type("IfcRoof"):
        add("roof", el, None)
    door_room = {}
    for l in links:
        if l.get("el") is not None:
            rs = [s.room_id for s in (l["a"], l["b"]) if s is not None and s.kind in ("room", "elevator")]
            door_room[l["el"].id()] = set(rs[:1]) if rs else set()
    for el in f.by_type("IfcDoor"):
        add("door", el, door_room.get(el.id(), set()))

    out = []
    for (kind, lv, mat, fr), touched in sorted(groups.items(), key=lambda t: (
            t[0][1], t[0][0], t[0][2], t[0][3] or "")):
        common = None
        if touched and all(t is not None for t in touched):
            common = set.intersection(*touched)
        shown = (names or {}).get(mat, mat)
        m = {"element": kind, "level": lv, "material": shown, **({"ifc_material": mat} if shown != mat else {}),
             **({"fire_rating": fr} if fr else {}), "source": src}
        if common and len(common) == 1:
            m["room"] = next(iter(common))
        out.append(m)
    return out


def _report(f, path, sha, b, results, unlinked, notes, dropped, elev, links) -> str:
    L = []
    w = L.append
    w(f"Seraph IFC extraction — {EXTRACTOR} {__version__}")
    w(f"file      {path.name}  ({path.stat().st_size / 1e6:.2f} MB, {f.schema}, sha256 {sha[:16]}…)")
    w(f"building  {b['name']}  ·  {b['model']['provenance_fr']}")
    w("")
    w("CHECKS")
    for c in results:
        w(f"  [{'ok' if c.ok else 'FAIL'}] {c.name}")
        for d in c.details:
            w(f"         {d}")
    w("")
    w("LEVELS")
    for lv in b["levels"]:
        n = lv["level"]
        w(f"  {lv['label']:5} elev {lv['elevation_m']:6.2f} m  ifc {lv.get('ifc_name')!r}")
        for r in (r for r in b["rooms"] if r["level"] == n):
            w(f"        {r['id']:12} {r['label']:34} {r['kind']:9} {r['area_m2']:7.1f} m²  {r['ifc_guid']}")
    for s in dropped:
        w(f"  (storey {s.Name!r} at {elev(s):.2f} m holds no room, corridor or stair: not a level)")
    w("")
    w("STAIRS")
    for s in b["stairs"]:
        w(f"  stair:{s['id']:3} {s['label']!r:28} levels {s['levels']}"
          + (f"  (linked without a door on {s['linked_levels']})" if s.get("linked_levels") else ""))
    w("")
    w("ENTRANCES")
    for e in b["entrances"]:
        w(f"  entrance:{e['id']:4} {e['label']!r:34} side {e['side']:5}  level {e['level']}  → {e['leads_to']}")
    fp = b["model"].get("ladder_points") or {}
    if fp:
        w("LADDER POINTS (balconies, terraces, French windows above the ground: rescue by ladder, never exits)")
        for n, nodes in fp.items():
            w(f"  level {n}: {', '.join(nodes)}")
    w("")
    w("UNITS (rooms reached through one door from the common circulation)")
    for u in b.get("units", []):
        w(f"  {u['id']:8} {u['label']:9} L{u['level']:<3} entry {', '.join(u['entry']) or '-':16} "
          f"rooms {', '.join(u['rooms'])}" + (f"  · outdoor {', '.join(u['outdoor'])}" if u['outdoor'] else ""))
    w("")
    opens = [l for l in links if l.get("adjacency")]
    w(f"DOORS ({len(b['doors'])} linked, {len(unlinked)} unlinked) + {len(opens)} openings without a door")
    for d in b["doors"]:
        w(f"  {d['id']:10} L{d['level']:<3} {d['between'][0]:>16} ↔ {d['between'][1]:<18} "
          f"{d.get('fire_rating') or '':12} {d['label']}")
    for l in opens:
        w(f"  {l['adjacency']:10} L{l['level']:<3} {l['a'].node:>16} ↔ {l['b'].node}")
    for u in unlinked:
        w(f"  UNLINKED   {u}")
    w("")
    w("MATERIALS (from the IFC only; absent = absent)")
    if not b["materials"]:
        w("  none in the file")
    for m in b["materials"]:
        w(f"  L{m['level']}  {m['element']:6} {m['material']!r:44} {m.get('fire_rating') or '':12} "
          f"{('room ' + m['room']) if m.get('room') else ''}")
    w("")
    g = b["graph"]
    w(f"GRAPH  {len(g['nodes'])} nodes, {len(g['edges'])} edges (lengths in m; stairs ×{STAIR_FACTOR} rise)")
    w("")
    w("IGNORED (not needed by a firefighter)")
    counts = {c: len(f.by_type(c)) for c in IGNORED}
    w("  " + (", ".join(f"{c} {n}" for c, n in counts.items() if n) or "nothing"))
    esc = Counter(p for el in f.by_type("IfcSpace") + f.by_type("IfcDoor") for p in E.get_psets(el)
                  if re.search(r"(escape|flucht|evacu|fire|brand)", p, re.I))
    w(f"  escape / fire psets present: {dict(esc) or 'none'}")
    if notes:
        w("")
        w("NOTES")
        for n, c in Counter(notes).items():
            w(f"  {n}" + (f"  (×{c})" if c > 1 else ""))
    return "\n".join(L) + "\n"


def write(result: Result, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "levels").mkdir(exist_ok=True)
    for old in (out / "levels").glob("L*.svg"):
        if f"levels/{old.name}" not in result.svgs:
            old.unlink()
    (out / "building.json").write_text(json.dumps(result.building, ensure_ascii=False, indent=1) + "\n",
                                       encoding="utf-8")
    for rel, svg in result.svgs.items():
        (out / rel).write_text(svg, encoding="utf-8")
    (out / "report.txt").write_text(result.report, encoding="utf-8")


def load_ids(path: Optional[Path]) -> Optional[dict]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) if path else None


def main(argv: Optional[list[str]] = None) -> None:
    ap = argparse.ArgumentParser(description="any IFC → building.json + level plans + report (exit 1 if a check fails)")
    ap.add_argument("ifc", type=Path)
    ap.add_argument("-o", "--out", type=Path, default=Path("out"))
    ap.add_argument("--ids", type=Path, help="ids.yaml: id mapping, French labels, front façade, second route")
    ap.add_argument("--base-url", default=DEFAULT_BASE_URL, help="where level plans will be served")
    ap.add_argument("--provenance", choices=["architect", "rebuilt_from_posted_plan", "fictional"])
    ap.add_argument("--provenance-fr")
    ap.add_argument("--name")
    args = ap.parse_args(argv)
    r = extract(args.ifc, ids=load_ids(args.ids), base_url=args.base_url, provenance=args.provenance,
                provenance_fr=args.provenance_fr, name=args.name)
    write(r, args.out)
    sys.stdout.write(r.report)
    if not r.ok:
        sys.stderr.write("checks failed: this model must not be shipped\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
