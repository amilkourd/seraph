"""The extractor on a real architect's IFC (TU Wien, Archicad, CC BY 4.0). Skipped when the file is not there."""
import re


def test_checks_pass(tuwien):
    assert tuwien.ok, [c.details for c in tuwien.checks if not c.ok]


def test_one_stair_and_the_declared_second_route(tuwien):
    b = tuwien.building
    assert [s["id"] for s in b["stairs"]] == ["A"]
    assert b["stairs"][0]["levels"] == [-1, 0, 1, 2, 3]
    assert b["model"]["second_route"]["kind"] == "facade_ladder"
    assert b["model"]["ladder_points"]["3"] == ["ladder:3.04", "ladder:3.08", "ladder:3.07"]
    escape = next(c for c in tuwien.checks if c.name.startswith("≥ 2 escape"))
    assert any("R+3: 1 escape route(s) + façade" in d for d in escape.details)


def test_scenario_ids_and_entrances(tuwien):
    b = tuwien.building
    rooms = {r["id"]: r for r in b["rooms"]}
    assert rooms["3.T"]["label"] == "3.T Buanderie" and rooms["3.T"]["ifc_name"] == "HW"
    assert rooms["3.12"]["label"] == "3.12 Chambre" and rooms["3.10"]["level"] == 3
    e = {x["id"]: x for x in b["entrances"]}
    assert e["E1"]["leads_to"] == "corridor:0" and e["E1"]["side"] == "front"
    assert e["E2"]["leads_to"] == "room:-1.03" and e["E2"]["level"] == -1
    flat = next(u for u in b["units"] if u["level"] == 3)
    assert {"3.10", "3.12", "3.T"} <= set(flat["rooms"]) and flat["entry"] == ["P3-72"]


def test_no_placeholder_or_invented_fire_rating(tuwien):
    ratings = {d.get("fire_rating") for d in tuwien.building["doors"]} | \
              {m.get("fire_rating") for m in tuwien.building["materials"]}
    ratings.discard(None)
    assert "ND" not in ratings
    assert all(re.match(r"^R?EI", r) for r in ratings), ratings


def test_balconies_are_never_exits(tuwien):
    g = tuwien.building["graph"]
    for a, b, _ in g["edges"]:
        if "outside" in (a, b):
            other = b if a == "outside" else a
            assert other.startswith("entrance:") or other.startswith("room:0."), other


def test_slabs_are_the_levels(tuwien):
    levels = {lv["level"]: lv for lv in tuwien.building["levels"]}
    assert levels[0]["outline_source"] == "slab" and sum(len(p["holes"]) for p in levels[0]["outline"]) >= 1
    assert all(lv["outline_source"] in ("slab", "spaces") and lv["outline"] for lv in levels.values())
    assert abs(tuwien.building["model"]["plan_frame"]["rotation_deg"]) > 1     # turned onto the building's axes


def test_real_plans(tuwien):
    svg = tuwien.svgs["levels/L1.svg"]
    assert "ESC A" in svg and "ASC" in svg and "#d0021b" in svg               # stair, lift, red fire symbols
    assert svg.count("<path") > 50                                            # walls, doors, treads: a drawing


# Ids the scenario (contracts/fixtures, docs/02-scenario.md) is written on. Door ids are positional (door order in
# the IFC): if an extractor change moves one, this fails before the demo does. Regenerate the fixtures after any
# deliberate change: cd seraph && uv run python ../contracts/gen_fixtures_v2.py
SCENARIO_ROOMS = "3.12 3.07 2.16 2.17 2.01 1.11 1.01 0.19 0.20 -1.11 -1.03 -1.06 -1.08".split()
SCENARIO_DOORS = {"P-1-5": ["room:-1.11", "corridor:-1"], "P2-69": ["room:2.16", "room:2.17"],
                  "P3-75": ["room:3.12", "room:3.07"], "E1": ["outside", "corridor:0"],
                  "E2": ["outside", "room:-1.03"]}


def test_scenario_ids_are_stable(tuwien):
    b = tuwien.building
    assert set(SCENARIO_ROOMS) <= {r["id"] for r in b["rooms"]}
    assert {"ladder:2.17", "ladder:3.07", "corridor:-1", "corridor:3", "stair:A"} <= set(b["graph"]["nodes"])
    assert {"U2.2", "U3.1"} <= {u["id"] for u in b["units"]}
    doors = {d["id"]: d["between"] for d in b["doors"]}
    for did, between in SCENARIO_DOORS.items():
        assert sorted(doors.get(did, [])) == sorted(between), did
