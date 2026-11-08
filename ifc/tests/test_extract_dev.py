"""The dev building (fictional R+5) round-trips trace → IFC → building.json with the ids of the v1 fixture."""
import json

from seraph_ifc import extract

# The R+5's route graph as contracts/fixtures/building.json had it in v1 (the fixture is now the TU Wien building);
# `truck` left out: it is outside the building, Rosetta finds it, the IFC does not have it.
R5_NODES = {"outside", "entrance:E1", "entrance:E2", "stair:A", "stair:B", "level:0", "level:1", "level:2", "level:3",
            "level:4", "level:5", "corridor:3", "room:3.10", "room:3.12", "room:3.14", "room:3.T"}
R5_EDGES = {("entrance:E1", "outside"), ("entrance:E2", "outside"), ("entrance:E1", "stair:B"),
            ("entrance:E2", "stair:A"), ("corridor:3", "level:3"), ("corridor:3", "room:3.10"),
            ("corridor:3", "room:3.12"), ("corridor:3", "room:3.14"), ("corridor:3", "room:3.T")} | \
    {(f"level:{n}", f"stair:{s}") for n in range(6) for s in "AB"}


def node_set(b):
    return set(b["graph"]["nodes"])


def edge_set(b):
    return {tuple(sorted(e[:2])) for e in b["graph"]["edges"]}


def test_checks_pass(dev):
    assert dev.ok, [c for c in dev.checks if not c.ok]


def test_fixture_ids_are_kept(dev):
    assert R5_NODES <= node_set(dev.building)
    assert R5_EDGES <= edge_set(dev.building)


def test_graph_has_metre_lengths(dev):
    for a, b, length in dev.building["graph"]["edges"]:
        assert isinstance(length, float) and length >= 0, (a, b)
    lengths = {tuple(sorted(e[:2])): e[2] for e in dev.building["graph"]["edges"]}
    # 3 storeys of 3 m up stair A, walked at 2 m per metre of rise, plus the way to its door.
    assert 18 < lengths[("level:3", "stair:A")] < 25


def test_rooms_stairs_entrances(dev):
    b = dev.building
    rooms = {r["id"]: r for r in b["rooms"]}
    for rid in ("3.10", "3.12", "3.14", "3.T", "2.01", "4.02", "4.05", "5.01", "corridor:3"):
        assert rid in rooms
    assert rooms["3.T"]["level"] == 3 and rooms["3.T"]["label"] == "3.T Local technique"
    stairs = {s["id"]: s for s in b["stairs"]}
    assert set(stairs) == {"A", "B"} and stairs["A"]["levels"] == [0, 1, 2, 3, 4, 5]
    assert all(s["status"] == "unknown" for s in b["stairs"])          # live state never comes from the model
    e = {x["id"]: x for x in b["entrances"]}
    assert e["E1"]["leads_to"] == "stair:B" and e["E1"]["side"] == "front"
    assert e["E2"]["leads_to"] == "stair:A" and e["E2"]["side"] == "left"


def test_materials_only_from_the_ifc(dev):
    mats = dev.building["materials"]
    names = {m["material"] for m in mats}
    assert names == {"Pierre de taille", "Béton armé", "Plaque de plâtre sur ossature métallique", "Bloc béton"}
    tech = [m for m in mats if m.get("room") == "3.T"]
    assert tech and tech[0]["fire_rating"] == "EI 60"
    assert not any(m["material"] == "Pierre de taille" and m.get("fire_rating") for m in mats)
    doors = {d["id"]: d for d in dev.building["doors"]}
    assert doors["P-3.T"]["fire_rating"] == "EI 30"
    assert "fire_rating" not in doors["P-3.12"]


def test_slab_outlines(dev):
    for lv in dev.building["levels"]:
        assert lv["outline_source"] == "slab" and lv["slab_thickness_m"] == 0.2
        holes = sum(len(p["holes"]) for p in lv["outline"])
        assert holes == (0 if lv["level"] == 0 else 3)       # stair A, stair B, lift shaft
        assert len(lv["outline_m"]) == len(lv["outline"])


def test_plan_frame_and_zones(dev):
    frame = dev.building["model"]["plan_frame"]
    assert frame["rotation_deg"] == 0.0 and frame["width_m"] == 26.4
    z = {r["id"]: r["zone"] for r in dev.building["rooms"]}
    xs = [p[0] for p in z["3.12"]]
    ys = [p[1] for p in z["3.12"]]
    assert (min(xs), max(xs), min(ys), max(ys)) == (620, 940, 160, 460)   # same place as the fixture's plan


def test_level_plans(dev):
    assert set(dev.svgs) == {f"levels/L{n}.svg" for n in range(6)}
    svg = dev.svgs["levels/L3.svg"]
    assert svg.startswith("<svg") and "ESC A" in svg and "ESC B" in svg and "ASC" in svg
    assert dev.building["model"]["level_plans"][3]["image_id"] == "ifc-L3"


def test_extraction_is_deterministic(dev_ifc, dev):
    again = extract.extract(dev_ifc)
    assert json.dumps(again.building, sort_keys=True) == json.dumps(dev.building, sort_keys=True)
