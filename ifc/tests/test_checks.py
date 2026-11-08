"""Each check fails when it must: these are the rules that stop a model from shipping."""
import copy

import pytest

from seraph_ifc import checks
from seraph_ifc.props import NOT_A_VALUE


def building(stairs=("A", "B")) -> dict:
    """Two levels, a corridor and an office each, one entrance per stair."""
    nodes, edges, doors = ["outside"], [], []
    for s in stairs:
        nodes += [f"entrance:E{s}", f"stair:{s}"]
        edges += [["outside", f"entrance:E{s}", 0.0], [f"entrance:E{s}", f"stair:{s}", 2.0]]
        doors.append({"id": f"E{s}", "level": 0, "between": ["outside", f"stair:{s}"]})
    rooms = []
    for n in (0, 1):
        nodes += [f"level:{n}", f"corridor:{n}", f"room:{n}.01"]
        edges += [[f"level:{n}", f"corridor:{n}", 2.0], [f"corridor:{n}", f"room:{n}.01", 5.0]]
        doors.append({"id": f"P{n}", "level": n, "between": [f"corridor:{n}", f"room:{n}.01"]})
        rooms += [{"id": f"corridor:{n}", "level": n, "kind": "corridor", "use": "circulation"},
                  {"id": f"{n}.01", "level": n, "kind": "room", "use": "bureaux"}]
        for s in stairs:
            edges.append([f"stair:{s}", f"level:{n}", 3.0 + 6 * n])
            doors.append({"id": f"S{s}{n}", "level": n, "between": [f"stair:{s}", f"corridor:{n}"]})
    return {"levels": [{"level": 0, "label": "RDC"}, {"level": 1, "label": "R+1"}],
            "stairs": [{"id": s, "levels": [0, 1]} for s in stairs], "rooms": rooms, "doors": doors,
            "graph": {"nodes": nodes, "edges": edges}, "model": {}}


def test_good_building_passes():
    assert all(c.ok for c in checks.run_all(building()))


def test_one_stair_fails_the_escape_check():
    c = checks.escape_routes(building(stairs=("A",)))
    assert not c.ok and any("R+1: 1" in d for d in c.details)


def test_facade_second_route_counts_only_when_declared():
    b = building(stairs=("A",))
    b["graph"]["nodes"].append("entrance:EX")                  # the ground floor has its own second exit
    b["graph"]["edges"] += [["outside", "entrance:EX", 0.0], ["entrance:EX", "room:0.01", 2.0]]
    b["graph"]["nodes"] += ["room:1.02", "ladder:1.02"]
    b["graph"]["edges"] += [["room:1.01", "room:1.02", 3.0], ["room:1.02", "ladder:1.02", 0.0]]
    b["rooms"].append({"id": "1.02", "level": 1, "kind": "exterior", "use": "extérieur"})
    b["model"]["ladder_points"] = {"1": ["ladder:1.02"]}
    assert not checks.escape_routes(b).ok                       # balcony present, not declared
    b["model"]["second_route"] = {"kind": "facade_ladder", "reason": "test"}
    assert checks.escape_routes(b).ok
    b2 = copy.deepcopy(b)
    b2["model"]["ladder_points"] = {}
    assert not checks.escape_routes(b2).ok                      # declared, but no ladder point on that level


def test_unreachable_room_fails():
    b = building()
    b["graph"]["nodes"].append("room:1.99")
    b["rooms"].append({"id": "1.99", "level": 1, "kind": "room"})
    c = checks.rooms_reachable(b)
    assert not c.ok and "room:1.99" in c.details[0]


def test_balcony_and_lift_need_not_be_reachable():
    b = building()
    b["graph"]["nodes"] += ["room:1.98"]
    b["rooms"].append({"id": "1.98", "level": 1, "kind": "elevator"})
    assert checks.rooms_reachable(b).ok


def test_door_must_link_two_known_nodes():
    b = building()
    b["doors"].append({"id": "X", "level": 1, "between": ["corridor:1", "room:nowhere"]})
    assert not checks.doors_linked(b).ok
    assert not checks.doors_linked(building(), unlinked=["Tür-007 (level 1): touches 1 space(s)"]).ok


def test_stair_must_have_a_door_on_each_of_its_levels():
    b = building()
    b["doors"] = [d for d in b["doors"] if d["id"] != "SA1"]
    c = checks.stairs_serve_levels(b)
    assert not c.ok and "stair:A is on level 1" in c.details[0]


@pytest.mark.parametrize("v", ["ND", "nd", "-", "n/a", ""])
def test_placeholders_are_not_values(v):
    assert v.strip().lower() in NOT_A_VALUE
