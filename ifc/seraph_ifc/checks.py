"""Checks a building.json must pass before anyone routes on it. Any failure = don't ship (exit 1, no register).

1. every door links 2 nodes (space ↔ space, or space ↔ outside)
2. every room is reachable from `outside`
3. every occupied level has ≥ 2 independent escape routes (node-disjoint paths to `outside`). The second one may be
   the façade (balconies reached by fire-service ladders) only when the building's ids.yaml declares it
   (`second_route: facade_ladder`, e.g. a single-stair dwelling) and the level has a façade rescue point
4. every stair serves (has a door or an opening on) every level it is on
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any, Iterable

NOT_OCCUPIED_USES = {"circulation", "escalier", "ascenseur"}
NOT_OCCUPIED_KINDS = {"corridor", "elevator", "exterior", "stair"}
MUST_REACH_KINDS = {"room", "corridor", None}        # elevators and balconies may have no door on a level
INF = 10**9


@dataclass
class Check:
    name: str
    ok: bool
    details: list[str] = field(default_factory=list)


def room_node(room: dict[str, Any]) -> str:
    rid = str(room["id"])
    return rid if rid.startswith(("corridor:", "room:")) else f"room:{rid}"


def adjacency(graph: dict[str, Any]) -> dict[str, set[str]]:
    adj: dict[str, set[str]] = {n: set() for n in graph.get("nodes", [])}
    for e in graph.get("edges", []):
        a, b = str(e[0]), str(e[1])
        adj.setdefault(a, set()).add(b)
        adj.setdefault(b, set()).add(a)
    return adj


def doors_linked(building: dict[str, Any], unlinked: Iterable[str] = ()) -> Check:
    bad = list(unlinked)
    nodes = set(building.get("graph", {}).get("nodes", []))
    for d in building.get("doors") or []:
        between = d.get("between") or []
        if len(between) != 2 or between[0] == between[1] or any(n not in nodes for n in between):
            bad.append(f"{d.get('id')} between {between}")
    return Check("every door links 2 nodes", not bad, bad)


def rooms_reachable(building: dict[str, Any]) -> Check:
    adj = adjacency(building.get("graph") or {})
    if "outside" not in adj:
        return Check("every room reachable from outside", False, ["no `outside` node"])
    seen = {"outside"}
    q = deque(["outside"])
    while q:
        n = q.popleft()
        for m in adj[n]:
            if m not in seen:
                seen.add(m)
                q.append(m)
    bad = [f"{room_node(r)} {r.get('label', '')} (level {r['level']})" for r in building.get("rooms", [])
           if room_node(r) not in seen and r.get("kind") in MUST_REACH_KINDS]
    return Check("every room reachable from outside", not bad, bad)


def escape_routes(building: dict[str, Any], minimum: int = 2) -> Check:
    adj = adjacency(building.get("graph") or {})
    rooms = building.get("rooms", [])
    model = building.get("model") or {}
    facade_ok = (model.get("second_route") or {}).get("kind") == "facade_ladder"
    facade = model.get("ladder_points") or {}
    details: list[str] = []
    ok = True
    for lv in building.get("levels", []):
        n = lv["level"]
        here = [r for r in rooms if r["level"] == n]
        if not any(r.get("kind") not in NOT_OCCUPIED_KINDS and (r.get("use") or "") not in NOT_OCCUPIED_USES
                   for r in here):
            details.append(f"{lv['label']}: not occupied, skipped")
            continue
        sources = {room_node(r) for r in here} | {f"level:{n}"}
        k = disjoint_paths(adj, sources & set(adj), "outside")
        pts = len(facade.get(str(n), []))
        if k >= minimum:
            details.append(f"{lv['label']}: {k} independent escape route(s)")
        elif k == minimum - 1 and facade_ok and pts:
            details.append(f"{lv['label']}: {k} escape route(s) + façade, {pts} ladder rescue point(s) "
                           f"(second_route: facade_ladder)")
        else:
            ok = False
            details.append(f"{lv['label']}: {k} independent escape route(s)"
                           + (f", {pts} façade point(s) (declare second_route to count them)" if pts else ""))
    return Check(f"≥ {minimum} escape routes from every occupied level", ok, details)


def stairs_serve_levels(building: dict[str, Any]) -> Check:
    bad = []
    doors = building.get("doors") or []
    for s in building.get("stairs", []):
        node = f"stair:{s['id']}"
        served = {d["level"] for d in doors if node in (d.get("between") or [])}
        served |= set(s.get("linked_levels", []))      # stairs found without doors, linked by adjacency
        for n in s.get("levels", []):
            if n not in served:
                bad.append(f"{node} is on level {n} but has no door there")
    return Check("stairs serve every level they are on", not bad, bad)


def run_all(building: dict[str, Any], unlinked_doors: Iterable[str] = ()) -> list[Check]:
    return [doors_linked(building, unlinked_doors), rooms_reachable(building), escape_routes(building),
            stairs_serve_levels(building)]


def disjoint_paths(adj: dict[str, set[str]], sources: set[str], sink: str) -> int:
    """Max number of node-disjoint paths from any source to `sink` (sources share nothing but themselves).
    Node splitting + Edmonds–Karp; the graphs are small (a few hundred nodes)."""
    if sink not in adj or not sources:
        return 0
    cap: dict[str, dict[str, int]] = {}

    def add(u: str, v: str, c: int) -> None:
        cap.setdefault(u, {}).setdefault(v, 0)
        cap[u][v] += c
        cap.setdefault(v, {}).setdefault(u, 0)

    for n in adj:
        add(f"{n}#in", f"{n}#out", INF if n in sources or n == sink else 1)
    for n, ms in adj.items():
        for m in ms:
            add(f"{n}#out", f"{m}#in", 1)
    for s in sources:
        add("S", f"{s}#in", INF)
    t = f"{sink}#out"
    flow = 0
    while True:
        prev = {"S": None}
        q = deque(["S"])
        while q and t not in prev:
            u = q.popleft()
            for v, c in cap[u].items():
                if c > 0 and v not in prev:
                    prev[v] = u
                    q.append(v)
        if t not in prev:
            return flow
        v = t
        while prev[v] is not None:
            u = prev[v]
            cap[u][v] -= 1
            cap[v][u] += 1
            v = u
        flow += 1
        if flow > 50:
            return flow
