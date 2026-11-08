"""The building model: load, hazards → graph nodes, routes (code, never a model), approach scoring, plan paths."""
from __future__ import annotations

import heapq
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional

from .config import FIXTURES, REPO, settings
from .models import Approach, Building, Entrance, Hazard, Room, Source

CORRIDOR_WORDS = ("corridor", "circulation", "couloir")
IMPASSABLE_KINDS = ("fire", "structure")
PENALTY = {"high": 50.0, "medium": 10.0, "low": 2.0}


@dataclass
class Zone:
    node: str
    level: int
    polygon: list[list[float]]
    image_id: str

    @property
    def box(self) -> tuple[float, float, float, float]:
        xs = [p[0] for p in self.polygon]
        ys = [p[1] for p in self.polygon]
        return min(xs), min(ys), max(xs), max(ys)

    @property
    def center(self) -> tuple[float, float]:
        pts = self.polygon
        a = cx = cy = 0.0
        for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]):
            c = x0 * y1 - x1 * y0
            a += c
            cx += (x0 + x1) * c
            cy += (y0 + y1) * c
        if abs(a) < 1e-9:
            bx0, by0, bx1, by1 = self.box
            return (bx0 + bx1) / 2, (by0 + by1) / 2
        return cx / (3 * a), cy / (3 * a)


@dataclass
class BuildingKit:
    """Everything Seraph needs about the building beyond the contract's `Building`."""
    building: Building
    path: Path
    files_dir: Path                      # served at /building/files/
    base_stair_status: dict[str, str] = field(default_factory=dict)
    adj: dict[str, dict[str, float]] = field(default_factory=dict)
    zones: dict[str, Zone] = field(default_factory=dict)
    level_zones: dict[tuple[str, int], Zone] = field(default_factory=dict)     # stairs: one zone per level (IFC)
    door_points: dict[tuple[frozenset, int], tuple[float, float]] = field(default_factory=dict)  # IFC door centres
    points: dict[str, tuple[float, float, str]] = field(default_factory=dict)  # node → (x, y, image_id)
    no_route: set[str] = field(default_factory=set)  # never walk people through: elevators, façade rescue points


def room_node(room: str, level: Optional[int]) -> str:
    r = room.strip()
    if r.lower().split(":")[0] in CORRIDOR_WORDS:
        return f"corridor:{level}" if level is not None else "corridor"
    return r if r.startswith("room:") else f"room:{r}"


def plan_name_to_node(name: str, level: int) -> Optional[str]:
    if name.startswith("exit:"):              # plan.read names doors « exit:<id> »; the graph calls them entrances
        return "entrance:" + name[5:]
    if name.startswith(("stair:", "entrance:", "room:")):
        return name
    if name.lower() in CORRIDOR_WORDS:
        return f"corridor:{level}"
    return None


def hazard_nodes(h: Hazard) -> list[str]:
    w = h.where or {}
    out: list[str] = []
    if w.get("stair"):
        out.append(f"stair:{w['stair']}")
    if w.get("entrance"):
        out.append(f"entrance:{w['entrance']}")
    if w.get("room"):
        out.append(room_node(str(w["room"]), w.get("level")))
    if not out and w.get("level") is not None:
        out.append(f"level:{w['level']}")
    return out


def load(path: Optional[Path] = None) -> BuildingKit:
    path = path or settings.building_json
    raw = json.loads(path.read_text(encoding="utf-8"))
    is_fixture = path.resolve().parent == FIXTURES.resolve()
    files_dir = FIXTURES if is_fixture else path.parent
    raw.pop("hazards_initial", None)     # a building model never carries hazards: they come from dispatch, calls, radio
    raw.pop("approach_expected", None)
    raw.pop("address_placeholder", None)

    plan_raw = raw.pop("plan", None)
    plan_zones = []
    if plan_raw:
        plan_zones = plan_raw.get("zones", []) or []
        url = plan_raw.get("url") or (
            f"{settings.seraph_url}/building/files/{plan_raw['file']}" if plan_raw.get("file") else ""
        )
        raw["plan"] = {"image_id": plan_raw["image_id"], "url": url, "level": plan_raw["level"],
                       "points": plan_raw.get("points", [])}
    raw.pop("hazards", None)
    raw.pop("approach", None)
    b = Building.model_validate(raw)

    kit = BuildingKit(building=b, path=path, files_dir=files_dir)
    for s in b.stairs:
        kit.base_stair_status[s.id] = s.status if s.status in ("clear", "unknown") else "unknown"
        s.status = kit.base_stair_status[s.id]

    model_src = Source(kind="ifc", label="maquette" if b.model else "bâtiment fictif", confirmed=True)
    for e in b.entrances:
        e.source = e.source or model_src
    for s in b.stairs:
        s.source = s.source or model_src

    # Rooms: IFC gives them; the fixture only has plan zones → derive rooms from them.
    if not b.rooms and plan_raw:
        labels = {p["name"]: p["label"] for p in plan_raw.get("points", [])}
        for z in plan_zones:
            name = z["name"]
            if name.startswith("room:") or name.lower() in CORRIDOR_WORDS:
                rid = name.removeprefix("room:")
                b.rooms.append(Room(id=rid, level=plan_raw["level"], label=labels.get(name, rid),
                                    use="circulation" if name.lower() in CORRIDOR_WORDS else None,
                                    zone=z["polygon"], source=Source(kind="plan", label="plan")))

    _index_graph(kit)
    _index_no_route(kit)
    _index_geometry(kit, plan_zones)
    for e in b.entrances:
        if not e.leads_to:
            e.leads_to = _guess_leads_to(kit, e)
    return kit


def _index_graph(kit: BuildingKit) -> None:
    g = kit.building.graph
    if not g:
        return
    for n in g.nodes:
        kit.adj.setdefault(n, {})
    for e in g.edges:
        a, b = str(e[0]), str(e[1])
        w = float(e[2]) if len(e) > 2 and e[2] is not None else 1.0
        kit.adj.setdefault(a, {})[b] = w
        kit.adj.setdefault(b, {})[a] = w


def _index_no_route(kit: BuildingKit) -> None:
    """Elevators (fire) and dead-end exterior spaces (balconies, terraces = ladder rescue points) are not routes."""
    b = kit.building
    for r in b.rooms:
        kind = (r.model_extra or {}).get("kind")
        node = room_node(r.id, r.level)
        if kind == "elevator" or (kind == "exterior" and "outside" not in kit.adj.get(node, {})):
            kit.no_route.add(node)
    if b.model:
        extra = b.model.model_extra or {}
        for key in ("ladder_points", "facade_rescue_points"):          # ladder rescue points (renamed once)
            for nodes in (extra.get(key) or {}).values():
                kit.no_route.update(nodes)
    kit.no_route.update(n for n in kit.adj if n.startswith(("ladder:", "facade:")))


def room_level(kit: BuildingKit, node: str) -> Optional[int]:
    if node.startswith("level:"):
        try:
            return int(node.split(":", 1)[1])
        except ValueError:
            return None
    if node.startswith("corridor:"):
        try:
            return int(node.split(":", 1)[1])
        except ValueError:
            return None
    if node.startswith("ladder:"):
        node = "room:" + node.split(":", 1)[1]
    rid = node.split(":", 1)[1] if node.startswith("room:") else node
    r = next((r for r in kit.building.rooms if r.id == rid), None)
    return r.level if r else None


DIGIT_WORDS = {"zero": "0", "un": "1", "une": "1", "deux": "2", "trois": "3", "quatre": "4", "cinq": "5", "six": "6",
               "sept": "7", "huit": "8", "neuf": "9", "dix": "10", "onze": "11", "douze": "12"}


def resolve_room(kit: BuildingKit, room: Optional[str], level: Optional[int]) -> Optional[str]:
    """A room as heard (« 2.1 », « 201 », « 2-01 », « deux zéro un », « 3.t ») → the building's room id, only when
    exactly one room of that level matches. None = not in the model (never guessed)."""
    if room is None:
        return None
    if not kit.building.rooms:
        return str(room)                 # no model: keep what was said
    import unicodedata
    raw = "".join(c for c in unicodedata.normalize("NFD", str(room).lower()) if unicodedata.category(c) != "Mn")
    raw = " ".join(DIGIT_WORDS.get(w, w) for w in raw.replace(",", ".").split())
    ids = [r.id for r in kit.building.rooms if level is None or r.level == level]
    if str(room) in ids:
        return str(room)
    low = {i.lower(): i for i in ids}
    if raw.strip() in low:
        return low[raw.strip()]
    import re as _re
    m = _re.fullmatch(r"\s*(-?\d)\s*[.\-_ ]?\s*(\d{1,2}|t)\s*", raw) or _re.fullmatch(r"\s*(-?\d)(\d{2})\s*", raw.replace(" ", ""))
    cands: list[str] = []
    if m:
        lvl_s, num_s = m.group(1), m.group(2)
        forms = {f"{lvl_s}.{num_s}", f"{lvl_s}.{num_s.zfill(2)}"} if num_s != "t" else {f"{lvl_s}.T"}
        cands = [i for i in ids if i in forms or i.lower() in {f.lower() for f in forms}]
    return cands[0] if len(cands) == 1 else None


def room_word(kit: BuildingKit, room_id: Optional[str]) -> str:
    """« 3.12 Chambre » → « chambre » ; unknown → « salle »."""
    if not room_id:
        return "salle"
    r = next((r for r in kit.building.rooms if r.id == room_id), None)
    if not r:
        return "salle"
    lab = r.label.strip()
    if lab.startswith(r.id):
        lab = lab[len(r.id):].strip()
    return (lab[:1].lower() + lab[1:]) if lab else "salle"


def unit_of(kit: BuildingKit, room_id: Optional[str]) -> Optional[dict[str, Any]]:
    for u in (kit.building.model_extra or {}).get("units") or []:
        if room_id in (u.get("rooms") or []) or room_id in (u.get("outdoor") or []):
            return u
    return None


def ladder_for(kit: BuildingKit, room_id: Optional[str], hazards: Iterable[Hazard]) -> Optional[tuple[str, str, list[str]]]:
    """The ladder point of the occupant's flat reachable from their room (shortest, avoiding hazards).
    → (ladder node, outdoor room id, path)."""
    u = unit_of(kit, room_id)
    if not u or not room_id:
        return None
    src = room_node(room_id, None)
    best = None
    for out in u.get("outdoor") or []:
        lad = f"ladder:{out}"
        if lad not in kit.adj:
            continue
        res = shortest_path(kit, src, lad, hazards)
        if res and (best is None or path_length(kit, res[0]) < path_length(kit, best[2])):
            best = (lad, out, res[0])
    return best


def path_length(kit: BuildingKit, path: list[str]) -> float:
    return sum(kit.adj.get(a, {}).get(b, 1.0) for a, b in zip(path, path[1:]))


def _level_image(kit: BuildingKit, level: int) -> Optional[str]:
    m = kit.building.model
    if m:
        for lp in m.level_plans:
            if lp.level == level:
                return lp.image_id
    p = kit.building.plan
    if p and p.level == level:
        return p.image_id
    return None


def _index_geometry(kit: BuildingKit, plan_zones: list[dict[str, Any]]) -> None:
    b = kit.building
    for r in b.rooms:
        if r.zone:
            node = room_node(r.id, r.level)
            img = _level_image(kit, r.level) or (b.plan.image_id if b.plan else "")
            kit.zones[node] = Zone(node, r.level, r.zone, img)
    for st in b.stairs:
        for z in (st.model_extra or {}).get("zones") or []:
            lvl = int(z["level"])
            img = _level_image(kit, lvl) or ""
            kit.level_zones[(f"stair:{st.id}", lvl)] = Zone(f"stair:{st.id}", lvl, z["zone"], img)
    for e in b.entrances:
        pp = (e.model_extra or {}).get("plan_point")
        if pp:
            kit.points[f"entrance:{e.id}"] = (float(pp["x"]), float(pp["y"]), pp.get("image_id", ""))
    for d in b.doors or []:
        pp = (d.model_extra or {}).get("plan_point")
        if pp and len(d.between) == 2:
            kit.door_points[(frozenset(d.between), d.level)] = (float(pp["x"]), float(pp["y"]))
    if b.plan:
        for z in plan_zones:
            node = plan_name_to_node(z["name"], b.plan.level)
            if node and node not in kit.zones:
                kit.zones[node] = Zone(node, b.plan.level, z["polygon"], b.plan.image_id)
        for p in b.plan.points:
            node = plan_name_to_node(p.name, b.plan.level)
            if node:
                kit.points[node] = (p.point.x, p.point.y, p.point.image_id)


def _guess_leads_to(kit: BuildingKit, e: Entrance) -> Optional[str]:
    nbrs = [n for n in kit.adj.get(f"entrance:{e.id}", {}) if n not in ("outside", "truck")]
    stairs = [n for n in nbrs if n.startswith("stair:")]
    return (stairs or nbrs or [None])[0]


def stair_status(kit: BuildingKit, stair_id: str, hazards: Iterable[Hazard]) -> str:
    status = kit.base_stair_status.get(stair_id, "unknown")
    for h in hazards:
        if h.where.get("stair") == stair_id:
            if h.kind in IMPASSABLE_KINDS and h.severity == "high":
                return "blocked"
            status = "smoke"
    return status


# ───────── Routing ─────────
def node_costs(hazards: Iterable[Hazard]) -> tuple[dict[str, float], set[str], dict[str, list[str]]]:
    """→ (penalty per node, impassable nodes, hazard ids per node)."""
    pen: dict[str, float] = {}
    blocked: set[str] = set()
    ids: dict[str, list[str]] = {}
    for h in hazards:
        for n in hazard_nodes(h):
            ids.setdefault(n, []).append(h.id)
            if h.kind in IMPASSABLE_KINDS and h.severity == "high" and not n.startswith("level:"):
                blocked.add(n)
            else:
                p = PENALTY.get(h.severity, 10.0)
                pen[n] = pen.get(n, 0.0) + (p / 2 if n.startswith("level:") else p)
    return pen, blocked, ids


def shortest_path(kit: BuildingKit, src: str, dst: str, hazards: Iterable[Hazard],
                  extra_blocked: Iterable[str] = ()) -> Optional[tuple[list[str], list[str]]]:
    """Dijkstra on the building graph. Fire rooms are removed, smoke costs a lot. → (path, hazard ids avoided)."""
    if src not in kit.adj or dst not in kit.adj:
        return None
    hazards = list(hazards)
    pen, blocked, ids = node_costs(hazards)
    blocked |= set(extra_blocked) | kit.no_route
    for end in (src, dst):           # a ladder point is reached through its own balcony / terrace only
        blocked.discard(end)
        if end.startswith(("ladder:", "facade:")):
            blocked -= set(kit.adj.get(end, {}))
    dist = {src: 0.0}
    prev: dict[str, str] = {}
    heap = [(0.0, src)]
    while heap:
        d, n = heapq.heappop(heap)
        if n == dst:
            break
        if d > dist.get(n, float("inf")):
            continue
        for m, w in kit.adj[n].items():
            if m in blocked:
                continue
            nd = d + w + pen.get(m, 0.0)
            if nd < dist.get(m, float("inf")):
                dist[m] = nd
                prev[m] = n
                heapq.heappush(heap, (nd, m))
    if dst not in dist:
        return None
    path = [dst]
    while path[-1] != src:
        path.append(prev[path[-1]])
    path.reverse()
    on_path = set(path)
    avoided: list[str] = []
    for n, hz in ids.items():
        if n in on_path:
            continue
        if any(n in kit.adj.get(p, {}) for p in path):
            avoided += [h for h in hz if h not in avoided]
    return path, avoided


def path_hazards(path: list[str], hazards: Iterable[Hazard]) -> list[Hazard]:
    on = set(path)
    return [h for h in hazards if any(n in on for n in hazard_nodes(h))]


def plan_path(kit: BuildingKit, nodes: list[str]) -> Optional[tuple[list[list[float]], str, int]]:
    """The route on ONE level plan's 0–1000 frame (the level holding most of the route's rooms), computed in code.
    Stops are zones (rooms, corridors, the stair on that level) and points (an entrance's door). Between two stops:
    the IFC door centre when the model has it (straight door to door), else the gap between the zones, walking
    along each zone's long axis (dev building). Nodes on other levels are left out: the path ends at the stair."""
    single = [kit.zones[n] for n in nodes if n in kit.zones]
    by_level: dict[int, int] = {}
    for z in single:
        by_level[z.level] = by_level.get(z.level, 0) + 1
    if not by_level:
        return None
    level = max(by_level, key=lambda k: by_level[k])
    image = next(z.image_id for z in single if z.level == level)
    stops: list[tuple[str, Any]] = []          # ("zone", Zone) | ("point", (node, x, y))
    for n in nodes:
        z = kit.zones.get(n) if n in kit.zones and kit.zones[n].level == level else kit.level_zones.get((n, level))
        if z and z.image_id == image:
            stops.append(("zone", z))
        elif n in kit.points and kit.points[n][2] == image and not n.startswith(("room:", "corridor:")):
            stops.append(("point", (n, kit.points[n][0], kit.points[n][1])))
    if not stops:
        return None
    pts: list[tuple[float, float]] = []
    k0, v0 = stops[0]
    pts.append((v0[1], v0[2]) if k0 == "point" else _anchor(kit, v0))
    for i, ((ka, a), (kb, bb)) in enumerate(zip(stops, stops[1:])):
        na = a.node if ka == "zone" else a[0]
        nb = bb.node if kb == "zone" else bb[0]
        door = kit.door_points.get((frozenset((na, nb)), level))
        if kb == "point":
            door = (bb[1], bb[2])
        elif ka == "point" and not door:
            door = (a[1], a[2])
        if door:
            if ka == "zone":
                pts += _inside(a, pts[-1], door)
            pts.append(door)
        elif kit.door_points:                  # IFC without this door: middle of the shared wall, stay inside
            d = _poly_gap(a, bb)
            pts += _inside(a, pts[-1], d) + [d]
        else:                                  # dev building without door coordinates: gap between zones
            d = _door(a, bb)
            pts += [_on_axis(a, d), d, _on_axis(bb, d)]
    kl, vl = stops[-1]
    if len(stops) > 1 and kl == "zone":
        end_pt = _anchor(kit, vl)
        pts += _inside(vl, pts[-1], end_pt)
        pts.append(end_pt)
    out: list[list[float]] = []
    for p in pts:
        q = [round(p[0]), round(p[1])]
        if not out or out[-1] != q:
            out.append(q)
    return out, image, level


def _point_in(poly: list[list[float]], x: float, y: float) -> bool:
    inside = False
    for (x0, y0), (x1, y1) in zip(poly, poly[1:] + poly[:1]):
        if (y0 > y) != (y1 > y) and x < (x1 - x0) * (y - y0) / (y1 - y0) + x0:
            inside = not inside
    return inside


def _dist_to_edges(poly: list[list[float]], x: float, y: float) -> float:
    best = float("inf")
    for (x0, y0), (x1, y1) in zip(poly, poly[1:] + poly[:1]):
        dx, dy = x1 - x0, y1 - y0
        L = dx * dx + dy * dy
        t = 0.0 if L == 0 else max(0.0, min(1.0, ((x - x0) * dx + (y - y0) * dy) / L))
        best = min(best, ((x0 + t * dx - x) ** 2 + (y0 + t * dy - y) ** 2) ** 0.5)
    return best


def _seg_inside(z: Zone, a: tuple[float, float], b: tuple[float, float], tol: float = 6.0) -> bool:
    for i in range(1, 25):
        t = i / 25
        x, y = a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t
        if not _point_in(z.polygon, x, y) and _dist_to_edges(z.polygon, x, y) > tol:
            return False
    return True


def _closest_on_edges(poly: list[list[float]], x: float, y: float) -> tuple[float, float, float]:
    best = (float("inf"), x, y)
    for (x0, y0), (x1, y1) in zip(poly, poly[1:] + poly[:1]):
        dx, dy = x1 - x0, y1 - y0
        L = dx * dx + dy * dy
        t = 0.0 if L == 0 else max(0.0, min(1.0, ((x - x0) * dx + (y - y0) * dy) / L))
        px, py = x0 + t * dx, y0 + t * dy
        d = ((px - x) ** 2 + (py - y) ** 2) ** 0.5
        if d < best[0]:
            best = (d, px, py)
    return best


def _poly_gap(a: Zone, b: Zone) -> tuple[float, float]:
    """Middle of the wall two zones share: the points of each polygon within 2 units of the closest gap, averaged."""
    pairs = []
    for z1, z2 in ((a, b), (b, a)):
        for i, (x0, y0) in enumerate(z1.polygon):
            x1, y1 = z1.polygon[(i + 1) % len(z1.polygon)]
            for t in (0.0, 0.25, 0.5, 0.75):
                x, y = x0 + (x1 - x0) * t, y0 + (y1 - y0) * t
                d, px, py = _closest_on_edges(z2.polygon, x, y)
                pairs.append((d, (x + px) / 2, (y + py) / 2))
    m = min(p[0] for p in pairs)
    near = [p for p in pairs if p[0] <= m + 2]
    return sum(p[1] for p in near) / len(near), sum(p[2] for p in near) / len(near)


def _inside(z: Zone, a: tuple[float, float], b: tuple[float, float]) -> list[tuple[float, float]]:
    """Via points so that a → b stays inside the zone (L / U-shaped corridors): none, one or two pulled-in vertices."""
    if _seg_inside(z, a, b):
        return []
    cx, cy = z.center
    cands = [(cx, cy)]
    for vx, vy in z.polygon:
        dx, dy = cx - vx, cy - vy
        n = (dx * dx + dy * dy) ** 0.5 or 1.0
        p = (vx + dx / n * 12, vy + dy / n * 12)
        if _point_in(z.polygon, *p):
            cands.append(p)
    for c in cands:
        if _seg_inside(z, a, c) and _seg_inside(z, c, b):
            return [c]
    for c1 in cands:
        if not _seg_inside(z, a, c1):
            continue
        for c2 in cands:
            if _seg_inside(z, c1, c2) and _seg_inside(z, c2, b):
                return [c1, c2]
    return []


def _anchor(kit: BuildingKit, z: Zone) -> tuple[float, float]:
    p = kit.points.get(z.node)
    if p and p[2] == z.image_id:
        return p[0], p[1]
    return z.center


def _overlap(a0: float, a1: float, b0: float, b1: float) -> Optional[float]:
    lo, hi = max(a0, b0), min(a1, b1)
    return (lo + hi) / 2 if lo <= hi else None


def _door(a: Zone, b: Zone) -> tuple[float, float]:
    ax0, ay0, ax1, ay1 = a.box
    bx0, by0, bx1, by1 = b.box
    x = _overlap(ax0, ax1, bx0, bx1)
    y = _overlap(ay0, ay1, by0, by1)
    if x is None:
        x = (ax1 + bx0) / 2 if ax1 < bx0 else (bx1 + ax0) / 2
    if y is None:
        y = (ay1 + by0) / 2 if ay1 < by0 else (by1 + ay0) / 2
    return x, y


def _on_axis(z: Zone, d: tuple[float, float]) -> tuple[float, float]:
    x0, y0, x1, y1 = z.box
    cx, cy = z.center
    if (x1 - x0) >= (y1 - y0):
        return min(max(d[0], x0), x1), cy
    return cx, min(max(d[1], y0), y1)


# ───────── Approach (code) ─────────
STATUS_FR = {"clear": "dégagé", "smoke": "enfumé", "blocked": "bloqué", "unknown": "pas de fumée signalée"}


def choose_approach(kit: BuildingKit, hazards: list[Hazard], b: Optional[Building] = None,
                    target: Optional[str] = None) -> Optional[tuple[Approach, dict[str, Any]]]:
    """Score each entrance: usable, the stair behind it clear, no hazard on the way, reaches the fire level on the
    graph (shorter is better), near the truck spot."""
    b = b or kit.building
    if not b.entrances:
        return None
    _, _, hz_ids = node_costs(hazards)
    truck_label = (b.truck_spot.label if b.truck_spot else "") or ""
    why_out: dict[str, str] = {}
    single_stair = len(b.stairs) == 1              # same stair for every entrance: the stair can't decide
    scored = []
    for e in b.entrances:
        s = 0.0
        s += {"usable": 2, "unknown": 1}.get(e.status, -10)
        lt = e.leads_to
        st_status = None
        node = f"entrance:{e.id}"
        if target and node in kit.adj and target in kit.adj:
            res = shortest_path(kit, node, target, hazards, extra_blocked=("outside", "truck"))  # stay inside
            if res:
                stairs_on = [n for n in res[0] if n.startswith("stair:")]
                if stairs_on and not (lt or "").startswith("stair:"):
                    lt = stairs_on[0]
                s += 1 - 0.05 * min(path_length(kit, res[0]), 100)
                if [h for h in path_hazards(res[0][1:-1], hazards) if not (single_stair and h.where.get("stair"))]:
                    s -= 3
            else:
                s -= 20                                # cut off by fire: never the way in
                free = shortest_path(kit, node, target, [], extra_blocked=("outside", "truck"))
                fire = [h for h in path_hazards(free[0], hazards) if h.kind in IMPASSABLE_KINDS] if free else []
                if fire and fire[0].where.get("room"):
                    rid = str(fire[0].where["room"])
                    why_out[e.id] = _cut_off_phrase(e, room_word(kit, rid), rid) + " " + selon(fire[0].source)
        if lt and lt.startswith("stair:"):
            st_status = stair_status(kit, lt.split(":", 1)[1], hazards)
            if st_status == "clear":
                s += 3
            elif st_status == "unknown" and lt not in hz_ids:
                s += 2
        if lt and lt in hz_ids and not (single_stair and lt.startswith("stair:")):
            s -= 5
        if f"entrance:{e.id}" in hz_ids:
            s -= 5
        if e.id and e.id in truck_label:
            s += 0.5
        if ((e.model_extra or {}).get("level") or 0) < 0:      # basement / garage ramp: not the way in
            s -= 1
        scored.append((s, e, st_status, lt))
    scored.sort(key=lambda t: -t[0])
    best_s, best, best_st, best_lt = scored[0]
    parts = [_entrance_phrase(best, best_st, best=True, lt=best_lt)]
    for s, e, st, lt in scored[1:]:
        parts.append(f"{e.id}, {why_out[e.id]}" if e.id in why_out else _entrance_phrase(e, st, best=False, lt=lt))
    reason = " ; ".join(p for p in parts if p) + "."
    appr = Approach(best_entrance_id=best.id, reason=reason, source=Source(kind="seraph", label="calcul"))
    detail = {"scores": {e.id: s for s, e, _, _ in scored}, "best": best, "best_stair_status": best_st,
              "best_leads_to": best_lt, "others": [(e, st) for _, e, st, _ in scored[1:]],
              "others_leads_to": {e.id: lt for _, e, _, lt in scored[1:]}, "why_out": why_out}
    return appr, detail


ARTICLE = {"rampe": ("la", "à la"), "porte": ("la", "à la"), "cour": ("la", "à la"), "terrasse": ("la", "à la"),
           "garage": ("le", "au"), "parking": ("le", "au"), "hall": ("le", "au"), "jardin": ("le", "au"),
           "sous-sol": ("le", "au"), "local": ("le", "au")}


def selon(src: Optional[Source]) -> str:
    """Every hazard is said with its source: « selon l'alerte », « selon l'appel », « selon Tête »."""
    if not src:
        return ""
    return {"dispatch": "selon l'alerte", "call": "selon l'appel", "ifc": "selon la maquette",
            "plan": "selon le plan"}.get(src.kind, f"selon {src.label}")


def place_fr(kit: BuildingKit, where: dict[str, Any]) -> str:
    """« au garage », « escalier A », « entrée E2 », « circulation 3e », « 3e »."""
    from .speech import level_fr
    if where.get("stair"):
        return f"escalier {where['stair']}"
    if where.get("entrance"):
        return f"entrée {where['entrance']}"
    r = where.get("room")
    if r == "corridor":
        return f"circulation {level_fr(where.get('level'))}"
    if r:
        w = room_word(kit, str(r))
        art = ARTICLE.get(w.split()[0].lower()) if w else None
        return f"{art[1]} {w}" if art else f"en {r}"
    if where.get("level") is not None:
        return level_fr(where["level"])
    return ""


def _cut_off_phrase(e: Entrance, room_w: str, rid: str) -> str:
    """« la rampe mène au garage en feu » from the entrance label (« Porte de garage, rampe (sous-sol) ») and the room."""
    import re as _re
    tail = e.label.split(",")[-1] if "," in e.label else ""
    tail = _re.sub(r"\(.*?\)", "", tail).strip().lower()
    head = tail.split()[0] if tail else ""
    rw = room_w.split()[0].lower() if room_w else ""
    if head in ARTICLE and rw in ARTICLE:
        return f"{ARTICLE[head][0]} {tail} mène {ARTICLE[rw][1]} {room_w} en feu"
    return f"feu sur le chemin, {room_w} {rid}"


def _entrance_phrase(e: Entrance, st_status: Optional[str], best: bool, lt: Optional[str] = None) -> str:
    direct = (e.leads_to or "").startswith("stair:")
    lt = lt or e.leads_to or ""
    if lt.startswith("stair:"):
        sid = lt.split(":", 1)[1]
        verb = ("donne directement sur" if direct else "mène à") if best else ("donne sur" if direct else "mène à")
        return f"{e.id} {verb} l'escalier {sid}, {STATUS_FR.get(st_status or 'unknown', 'état inconnu')}"
    if e.status in ("locked", "blocked"):
        return f"{e.id} {'verrouillée' if e.status == 'locked' else 'bloquée'}"
    return f"{e.id} {e.label.lower()}"


def files_path(kit: BuildingKit, rel: str) -> Optional[Path]:
    """Static file under ifc/out (or the fixtures for the dev building). No path escape."""
    bases = [kit.files_dir] if str(kit.files_dir) not in ("", ".") else []
    for base in bases + [REPO / "ifc" / "out"]:
        p = (base / rel).resolve()
        if p.is_file() and base.resolve() in p.parents:
            return p
    return None
