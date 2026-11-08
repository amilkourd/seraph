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
        x0, y0, x1, y1 = self.box
        return (x0 + x1) / 2, (y0 + y1) / 2


@dataclass
class BuildingKit:
    """Everything Seraph needs about the building beyond the contract's `Building`."""
    building: Building
    path: Path
    files_dir: Path                      # served at /building/files/
    hazards_initial: list[dict[str, Any]] = field(default_factory=list)
    base_stair_status: dict[str, str] = field(default_factory=dict)
    adj: dict[str, dict[str, float]] = field(default_factory=dict)
    zones: dict[str, Zone] = field(default_factory=dict)
    level_zones: dict[tuple[str, int], Zone] = field(default_factory=dict)     # stairs: one zone per level (IFC)
    door_points: dict[tuple[frozenset, int], tuple[float, float]] = field(default_factory=dict)  # IFC door centres
    points: dict[str, tuple[float, float, str]] = field(default_factory=dict)  # node → (x, y, image_id)
    scenario_hazards: bool = False       # hazards_initial taken from the fixture (IFC has none)


def room_node(room: str, level: Optional[int]) -> str:
    r = room.strip()
    if r.lower().split(":")[0] in CORRIDOR_WORDS:
        return f"corridor:{level}" if level is not None else "corridor"
    return r if r.startswith("room:") else f"room:{r}"


def plan_name_to_node(name: str, level: int) -> Optional[str]:
    if name.startswith(("stair:", "entrance:", "room:", "exit:")):
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
    hazards_initial = raw.pop("hazards_initial", []) or []
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

    kit = BuildingKit(building=b, path=path, files_dir=files_dir, hazards_initial=hazards_initial)
    if not hazards_initial and not is_fixture:
        # The IFC carries no incident. The exercise's starting hazards (fire 3.T, smoke stair B) come from the
        # scenario fixture, kept only where the ids exist in this model; source « alerte » (dispatch).
        fx = json.loads((FIXTURES / "building.json").read_text(encoding="utf-8")).get("hazards_initial", [])
        kit.hazards_initial = fx
        kit.scenario_hazards = True
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
    if kit.scenario_hazards:
        kit.hazards_initial = [h for h in kit.hazards_initial
                               if all(n in kit.adj for n in hazard_nodes(Hazard(id=h["id"], kind=h["kind"], where=h.get("where", {}),
                                                                               source=Source(kind="dispatch", label="alerte"))))]
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


def initial_hazards(kit: BuildingKit) -> list[Hazard]:
    out = []
    for h in kit.hazards_initial:
        out.append(Hazard(id=h["id"], kind=h["kind"], where=h.get("where", {}), severity=h.get("severity", "medium"),
                          source=Source(kind="dispatch", label="alerte", confirmed=True)))
    return out


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
    blocked |= set(extra_blocked)
    blocked.discard(src)
    blocked.discard(dst)
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
    """The route on one level plan's 0–1000 frame: zone centres joined through the gap between zones (door),
    walking along each zone's long axis. Schematic, computed in code from the zones only."""
    single = [kit.zones[n] for n in nodes if n in kit.zones]
    by_level: dict[int, int] = {}
    for z in single:
        by_level[z.level] = by_level.get(z.level, 0) + 1
    if not by_level:
        return None
    level = max(by_level, key=lambda k: by_level[k])
    zs: list[Zone] = []
    for n in nodes:
        z = kit.zones.get(n) if n in kit.zones and kit.zones[n].level == level else kit.level_zones.get((n, level))
        if z:
            zs.append(z)
    if not zs:
        return None
    pts: list[tuple[float, float]] = [_anchor(kit, zs[0])]
    for a, b in zip(zs, zs[1:]):
        d = kit.door_points.get((frozenset((a.node, b.node)), level)) or _door(a, b)
        pts += [_on_axis(a, d), d, _on_axis(b, d)]
    if len(zs) > 1:
        pts.append(_anchor(kit, zs[-1]))
    out: list[list[float]] = []
    for p in pts:
        q = [round(p[0]), round(p[1])]
        if not out or out[-1] != q:
            out.append(q)
    return out, zs[0].image_id, level


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


def choose_approach(kit: BuildingKit, hazards: list[Hazard], b: Optional[Building] = None) -> Optional[tuple[Approach, dict[str, Any]]]:
    b = b or kit.building
    if not b.entrances:
        return None
    _, _, hz_ids = node_costs(hazards)
    truck_label = (b.truck_spot.label if b.truck_spot else "") or ""
    scored = []
    for e in b.entrances:
        s = 0.0
        s += {"usable": 2, "unknown": 1}.get(e.status, -10)
        lt = e.leads_to
        st_status = None
        if lt and lt.startswith("stair:"):
            st_status = stair_status(kit, lt.split(":", 1)[1], hazards)
            if st_status == "clear":
                s += 3
            elif st_status == "unknown" and lt not in hz_ids:
                s += 2
        if lt and lt in hz_ids:
            s -= 5
        if f"entrance:{e.id}" in hz_ids:
            s -= 5
        if e.id and e.id in truck_label:
            s += 1
        scored.append((s, e, st_status))
    scored.sort(key=lambda t: -t[0])
    best_s, best, best_st = scored[0]
    parts = [_entrance_phrase(best, best_st, best=True)]
    for s, e, st in scored[1:]:
        parts.append(_entrance_phrase(e, st, best=False))
    reason = " ; ".join(p for p in parts if p) + "."
    appr = Approach(best_entrance_id=best.id, reason=reason, source=Source(kind="seraph", label="calcul"))
    detail = {"scores": {e.id: s for s, e, _ in scored}, "best": best, "best_stair_status": best_st,
              "others": [(e, st) for _, e, st in scored[1:]]}
    return appr, detail


def _entrance_phrase(e: Entrance, st_status: Optional[str], best: bool) -> str:
    lt = e.leads_to or ""
    if lt.startswith("stair:"):
        sid = lt.split(":", 1)[1]
        verb = "donne directement sur" if best else "donne sur"
        return f"{e.id} {verb} l'escalier {sid}, {STATUS_FR.get(st_status or 'unknown', 'état inconnu')}"
    if e.status in ("locked", "blocked"):
        return f"{e.id} {'verrouillée' if e.status == 'locked' else 'bloquée'}"
    return f"{e.id} {e.label.lower()}"


def files_path(kit: BuildingKit, rel: str) -> Optional[Path]:
    """Static file under ifc/out (or the fixtures for the dev building). No path escape."""
    for base in (REPO / "ifc" / "out", kit.files_dir):
        p = (base / rel).resolve()
        if p.is_file() and base.resolve() in p.parents:
            return p
    return None
