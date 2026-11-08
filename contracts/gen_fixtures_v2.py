"""Scenario v2 (TU Wien): regenerate the JSON fixtures from ifc/out/building.json + the scenario (docs/02-scenario.md).
Writes building.json, levels/*.svg, occupants.json, state-sample.json, endpoints/{dispatch.read, maps.building,
plan.read, occupants.list, georisques.risks, weather.wind}.json. calls.jsonl and radio.jsonl are written by hand.
Re-run after the ifc session re-extracts (routes come from Seraph's own graph code, used read-only):
  cd seraph && uv run python ../contracts/gen_fixtures_v2.py
"""
from __future__ import annotations

import copy
import json
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FX = REPO / "contracts" / "fixtures"
IFC = REPO / "ifc" / "out"
sys.path.insert(0, str(REPO / "seraph"))

T0 = "2026-11-08T00:00:00Z"


def src(kind, label, at="2026-11-08T00:40:00Z", confirmed=True, url=None):
    s = {"kind": kind, "label": label, "confirmed": confirmed, "at": at}
    if url:
        s["url"] = url
    return s


def shot(image_id, caption, side, w=1280, h=800, at=T0):
    return {"image_id": image_id, "url": f"http://localhost:8001/shots/{image_id}.jpg", "caption": caption,
            "side": side, "width": w, "height": h, "taken_at": at}


def pt(image_id, x, y):
    return {"image_id": image_id, "x": x, "y": y}


def _fmt(o, ind=0):
    pad, pad1 = "  " * ind, "  " * (ind + 1)
    flat = json.dumps(o, ensure_ascii=False, separators=(", ", ": "))
    if isinstance(o, list) and (not o or all(isinstance(x, (int, float)) or (isinstance(x, list) and all(isinstance(y, (int, float)) for y in x)) for x in o)):
        return flat                                   # coordinates and polygons on one line
    if isinstance(o, dict) and o and len(flat) <= 110 and all(not isinstance(v, (dict, list)) or v == [] for v in o.values()):
        return flat
    if isinstance(o, dict):
        return "{}" if not o else "{\n" + ",\n".join(f"{pad1}{json.dumps(k, ensure_ascii=False)}: {_fmt(v, ind + 1)}" for k, v in o.items()) + "\n" + pad + "}"
    if isinstance(o, list):
        return "[\n" + ",\n".join(pad1 + _fmt(x, ind + 1) for x in o) + "\n" + pad + "]"
    return flat


def dump(path: Path, obj):
    path.write_text(_fmt(obj) + "\n", encoding="utf-8")


def jsonl(path: Path, rows):
    path.write_text("".join(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n" for r in rows), encoding="utf-8")


ifc = json.loads((IFC / "building.json").read_text(encoding="utf-8"))
ROOMS = {r["id"]: r for r in ifc["rooms"]}
for rid in ["-1.11", "-1.03", "-1.06", "-1.08", "3.12", "3.07", "2.16", "2.17", "2.01", "1.11", "1.01", "0.19", "0.20"]:
    assert rid in ROOMS, rid
for n in ["ladder:2.17", "ladder:3.07", "stair:A", "entrance:E1", "entrance:E2", "corridor:-1", "corridor:3"]:
    assert n in ifc["graph"]["nodes"], n
assert {d["id"] for d in ifc["doors"]} >= {"P-1-5", "P-1-6", "P2-69", "P3-75", "E1", "E2"}

# ───────── outside facts (Rosetta, maps.building): every approach point on the SAME top view ─────────
TOP = "earth-top-01"
SHOTS_MAPS = [
    shot("sv-front-01", "Façade boulevard Bessières, porte d'entrée E1 (Street View)", "front"),
    shot("sv-left-01", "Côté gauche, rampe du garage E2 (Street View)", "left"),
    shot("earth-left-01", "Côté gauche, rampe du garage (Google Earth 3D)", "left"),
    shot("earth-rear-01", "Arrière, balcons et terrasses (Google Earth 3D)", "rear"),
    shot(TOP, "Vue du dessus, boulevard Bessières (Google Earth)", "top"),
]
# Mock placement of the IFC on the top view (live: Rosetta points on the real image). The IFC frame already has E1's
# façade at the bottom: scale it to ~21 % of the 1280×800 image (k px per plan unit) and put door E1 on (500, 585).
# The 0–1000 grid is per axis, so x and y scale differently. 1 m ≈ 14 px: the hydrant sits ~30 m from E1.
TOP_W, TOP_H, K = 1280, 800, 0.4
E1_PLAN = next(d for d in ifc["doors"] if d["id"] == "E1")["plan_point"]


def to_top(x, y):
    return [round(500 + K * (x - E1_PLAN["x"]) * 1000 / TOP_W), round(585 + K * (y - E1_PLAN["y"]) * 1000 / TOP_H)]


ROOF = next(lv for lv in ifc["levels"] if lv["level"] == 1)["outline"][0]["outer"]   # largest upper floor = the roof seen from above
FOOTPRINT = {"image_id": TOP, "polygon": [to_top(x, y) for x, y in ROOF]}
E2_PLAN = next(d for d in ifc["doors"] if d["id"] == "E2")["plan_point"]
ENTRANCE_POINTS = {"E1": pt(TOP, *to_top(E1_PLAN["x"], E1_PLAN["y"])), "E2": pt(TOP, *to_top(E2_PLAN["x"], E2_PLAN["y"]))}
HYDRANT = {"id": "H1", "label": "Poteau incendie, trottoir du boulevard Bessières", "distance_m": 30, "point": pt(TOP, 831, 635)}
TRUCK = {"label": "Boulevard Bessières, devant E1", "point": pt(TOP, 500, 712)}
EVIDENCE = [  # per-photo pointing, kept as evidence only (Halo draws from the top view)
    {"of": "E1", "point": pt("sv-front-01", 508, 642)},
    {"of": "E2", "point": pt("sv-left-01", 362, 690)},
    {"of": "E2", "point": pt("earth-left-01", 296, 704)},
    {"of": "H1", "point": pt("sv-front-01", 846, 758)},
]

# ───────── plan.read on the IFC's R-1 plan (rendered from ifc/out/levels/L-1.svg, same frame as ifc-L-1) ─────────
PLAN_ID = "plan-l-1-01"
def interior(poly):
    """A point inside the polygon: the middle of the widest span on the scanline through the vertex-mean y."""
    ys = sorted(y for _, y in poly)
    best = None
    for y in [sum(ys) / len(ys), (ys[0] + ys[-1]) / 2]:
        xs = []
        for (x0, y0), (x1, y1) in zip(poly, poly[1:] + poly[:1]):
            if (y0 <= y < y1) or (y1 <= y < y0):
                xs.append(x0 + (y - y0) * (x1 - x0) / (y1 - y0))
        xs.sort()
        for i in range(0, len(xs) - 1, 2):
            w = xs[i + 1] - xs[i]
            if not best or w > best[0]:
                best = (w, (xs[i] + xs[i + 1]) / 2, y)
    return round(best[1]), round(best[2])


STAIR_M1 = next(z["zone"] for z in ifc["stairs"][0]["zones"] if z["level"] == -1)
E2_DOOR = next(d for d in ifc["doors"] if d["id"] == "E2")["plan_point"]
el = interior(ROOMS["-1.06"]["zone"])
PLAN_POINTS = [
    ("stair:A", "Escalier A", interior(STAIR_M1)),
    ("elevator", "Ascenseur", interior(ROOMS["-1.02"]["zone"])),
    ("exit:E2", "E2 Porte de garage", (E2_DOOR["x"], E2_DOOR["y"])),
    ("room:-1.03", "-1.03 Rampe d'accès", interior(ROOMS["-1.03"]["zone"])),
    ("room:-1.11", "-1.11 Garage", interior(ROOMS["-1.11"]["zone"])),
    ("room:-1.01", "-1.01 Caves", interior(ROOMS["-1.01"]["zone"])),
    ("room:-1.04", "-1.04 Local poussettes", interior(ROOMS["-1.04"]["zone"])),
    ("room:-1.06", "-1.06 Local électrique", el),
    ("room:-1.08", "-1.08 Local technique", interior(ROOMS["-1.08"]["zone"])),
    ("corridor", "Circulation", interior(ROOMS["corridor:-1"]["zone"])),
    ("electric_cutoff", "Coupure électrique", (el[0], el[1] + 12)),
]
plan_points = [{"name": n, "label": l, "point": pt(PLAN_ID, x, y)} for n, l, (x, y) in PLAN_POINTS]
plan_zones = [{"name": "stair:A", "polygon": next(z["zone"] for z in ifc["stairs"][0]["zones"] if z["level"] == -1)}]
for rid in ["-1.01", "-1.02", "-1.03", "-1.04", "-1.06", "-1.08", "-1.11", "corridor:-1"]:
    name = "elevator" if rid == "-1.02" else ("corridor" if rid.startswith("corridor") else f"room:{rid}")
    plan_zones.append({"name": name, "polygon": ROOMS[rid]["zone"]})
PLAN_SHOT = shot(PLAN_ID, "Plan affiché niveau R-1 (maquette IFC, rendu)", "plan", 1000, 1000)

HAZARDS_INITIAL = [
    {"id": "HZ-1", "kind": "fire", "where": {"level": -1, "room": "-1.11"}, "severity": "high"},
    {"id": "HZ-2", "kind": "smoke", "where": {"stair": "A"}, "severity": "high"},
]
APPROACH_REASON = "E1 donne sur le hall de l'escalier A ; E2, la rampe, passe par le garage en feu."

# ───────── building.json fixture ─────────
fb = copy.deepcopy(ifc)
fb.pop("hazards", None)
fb.pop("approach", None)
fb.pop("screenshots", None)
for e in fb["entrances"]:
    e["point"] = ENTRANCE_POINTS[e["id"]]
fb["hydrants"] = [HYDRANT]
fb["truck_spot"] = TRUCK
fb["footprint"] = FOOTPRINT
fb["plan"] = {"image_id": PLAN_ID, "level": -1, "file": "levels/L-1.svg", "points": plan_points, "zones": plan_zones}
out = {"name": fb.pop("name"), "address_placeholder": "DEMO_ADDRESS (.env: « 96 Boulevard Bessières, 75017 Paris », maquette TU Wien placée à cette adresse, exercice)"}
out.update(fb)
out["hazards_initial"] = HAZARDS_INITIAL
out["approach_expected"] = {"best_entrance_id": "E1", "reason": APPROACH_REASON}
dump(FX / "building.json", out)
(FX / "levels").mkdir(exist_ok=True)
for f in (IFC / "levels").glob("L*.svg"):
    shutil.copy(f, FX / "levels" / f.name)

# ───────── occupants ─────────
OCC = [
    ("OCC-01", "Léa Martin", 3, "3.12", "fr"),
    ("OCC-02", "Karim Benali", 1, "1.11", "fr"),
    ("OCC-03", "Sophie Durand", 1, "1.01", "fr"),
    ("OCC-04", "Tom Becker", 2, "2.16", "en"),
    ("OCC-05", "Inès Rahmani", 2, "2.01", "fr"),
    ("OCC-06", "Lucía García", 0, "0.19", "es"),
]
occ_rows = [{"id": i, "name": n, "phone_e164": f"+3310000000{i[-1]}", "level": lv, "room": r, "language": lg}
            for i, n, lv, r, lg in OCC]
dump(FX / "occupants.json", {
    "_comment": "Seed data for the occupants replica (building manager software). Fictional people and NON-DIALABLE numbers. Real calls only go to judges who opt in through /inscription. Rooms are real ids of the TU Wien IFC (ifc/out/building.json).",
    "building": "Immeuble d'habitation (maquette TU Wien)",
    "occupants": occ_rows,
})

# ───────── endpoints ─────────
def result(endpoint, output, shots, source, duration_ms=1200):
    return {"run_id": f"run_mock_{endpoint.replace('.', '_')}", "endpoint": endpoint, "status": "ok", "live": False,
            "output": output, "screenshots": shots, "source": source, "duration_ms": duration_ms,
            "started_at": T0, "ended_at": T0}

EP = FX / "endpoints"
DISPATCH_URL = "http://localhost:8101/interventions/INC-0001"
NATURE = "Feu de véhicule en parking souterrain, fumée dans l'escalier"
CALLER_NOTES = ["Fumée dans la cage d'escalier", "Fumée qui sort de la rampe du parking", "Habitants bloqués dans les étages"]
dump(EP / "dispatch.read.json", result("dispatch.read", {
    "incident_id": "INC-0001", "address": "DEMO_ADDRESS", "nature": NATURE, "level": -1,
    "declared_at": T0, "caller_notes": CALLER_NOTES},
    [shot("dispatch-01", "Fiche intervention INC-0001 (logiciel d'alerte)", "top")],
    src("dispatch", "alerte", T0, url=DISPATCH_URL)))
dump(EP / "maps.building.json", result("maps.building", {
    "storeys_estimate": 4,
    "entrances": [{"id": e["id"], "label": e["label"], "side": e["side"], "point": ENTRANCE_POINTS[e["id"]]} for e in ifc["entrances"]],
    "hydrants": [{k: v for k, v in HYDRANT.items() if k != "distance_m"}],
    "truck_spot": TRUCK,
    "footprint": FOOTPRINT,
    "evidence": EVIDENCE,
    "obstacles": ["Voitures garées le long du boulevard Bessières"]},
    SHOTS_MAPS, src("earth", "Maps / Earth", T0, url="https://earth.google.com/")))
dump(EP / "plan.read.json", result("plan.read", {
    "level": -1, "image_id": PLAN_ID, "points": plan_points, "zones": plan_zones},
    [PLAN_SHOT], src("plan", "plan", T0)))
dump(EP / "occupants.list.json", result("occupants.list", {"occupants": occ_rows},
    [shot("occupants-01", "Liste des occupants (logiciel du gestionnaire)", "top")],
    src("occupants", "gestionnaire", T0, url="http://localhost:8103/batiments/1")))
RISKS = [{"label": "Séisme : zone 1 (très faible)", "category": "naturel"},
         {"label": "Retrait-gonflement des argiles", "category": "naturel"}]
dump(EP / "georisques.risks.json", result("georisques.risks", {"risks": RISKS, "url": "https://www.georisques.gouv.fr/"},
    [shot("georisques-01", "Résultats Géorisques pour l'adresse", "top")],
    src("georisques", "Géorisques", T0, url="https://www.georisques.gouv.fr/")))
dump(EP / "weather.wind.json", result("weather.wind", {
    "dir_deg": 270, "dir_label": "ouest", "speed_kmh": 20, "observed_at": T0, "url": "https://meteofrance.com/"},
    [shot("meteo-01", "Météo-France, Paris", "top")], src("meteo", "Météo-France", T0, url="https://meteofrance.com/")))

# ───────── state-sample.json (mid-incident, ~00:40: Tom told to stay + balcony, Lucía's order pending) ─────────
from seraph import building as B          # read-only use of Seraph's graph code
from seraph.models import Hazard, Source

kit = B.load(FX / "building.json")
AT = "2026-11-08T00:40:00Z"
hazards = [
    {"id": "HZ-1", "kind": "fire", "where": {"level": -1, "room": "-1.11"}, "severity": "high",
     "source": src("dispatch", "alerte"), "reported_at": "2026-11-08T00:25:00Z"},
    {"id": "HZ-2", "kind": "smoke", "where": {"stair": "A"}, "severity": "high",
     "source": src("dispatch", "alerte"), "reported_at": "2026-11-08T00:25:00Z"},
    {"id": "HZ-3", "kind": "smoke", "where": {"entrance": "E2"}, "severity": "medium",
     "source": src("radio", "Tête"), "reported_at": "2026-11-08T00:33:00Z"},
    {"id": "HZ-4", "kind": "smoke", "where": {"level": 3, "room": "corridor"}, "severity": "high",
     "source": src("radio", "Binôme 1"), "reported_at": "2026-11-08T00:38:00Z"},
]
hz_models = [Hazard.model_validate(h) for h in hazards]


def route(rid, purpose, a, b, via=None, at=AT):
    if via is None:
        res = B.shortest_path(kit, a, b, hz_models)
        assert res, (a, b)
        via, avoided = res
    else:
        _, _, ids = B.node_costs(hz_models)
        avoided = sorted({h for n, hs in ids.items() if n not in via and any(n in kit.adj.get(p, {}) for p in via) for h in hs})
    r = {"id": rid, "purpose": purpose, "from": a, "to": b, "via": via, "avoids": avoided, "computed_at": at,
         "source": src("seraph", "calcul" if not b.startswith("ladder:") else "calcul · échelle", at)}
    pp = B.plan_path(kit, via)
    if pp and len(pp[0]) >= 2:
        r["path"], r["path_image_id"], r["path_level"] = [[round(x), round(y)] for x, y in pp[0]], pp[1], pp[2]
    return r


routes = [
    route("RT-1", "approach", "outside", "level:-1"),
    route("RT-2", "to_victim", "level:3", "room:3.12"),
    route("RT-3", "evacuation", "room:2.16", "ladder:2.17", via=["room:2.16", "room:2.17", "ladder:2.17"], at="2026-11-08T00:39:40Z"),
]
assert routes[0]["via"][:3] == ["outside", "entrance:E1", "corridor:0"], routes[0]["via"]

sb = copy.deepcopy(out)
for k in ("address_placeholder", "hazards_initial", "approach_expected"):
    sb.pop(k)
sb.pop("plan")
sb["stairs"][0]["status"] = "smoke"
sb["stairs"][0]["source"] = src("dispatch", "alerte")
for e in sb["entrances"]:
    e["status"] = "usable" if e["id"] == "E1" else "unknown"
    e["source"] = src("earth", "Earth")
sb["hydrants"][0]["source"] = src("earth", "Earth")
sb["truck_spot"]["source"] = src("earth", "Earth")
sb["footprint"]["source"] = src("earth", "Earth")
sb["plan"] = {"image_id": PLAN_ID, "url": f"http://localhost:8001/shots/{PLAN_ID}.jpg", "level": -1, "points": plan_points}
sb["hazards"] = hazards
sb["approach"] = {"best_entrance_id": "E1", "reason": APPROACH_REASON, "source": src("seraph", "calcul")}
sb["screenshots"] = SHOTS_MAPS + [PLAN_SHOT]
building_state = {"name": sb.pop("name")}
building_state.update(sb)


def occ(i, status, at=AT, **kw):
    o = next(r for r in occ_rows if r["id"] == i)
    d = {"id": i, "name": o["name"], "phone_masked": f"+3310•••••0{i[-1]}", "level": o["level"], "room": o["room"],
         "status": status, "language": o["language"], "last_update": at}
    d.update(kw)
    if "source" not in d:
        d["source"] = src("call", f"appel {o['name']}", at)
    return d


occupants = [
    occ("OCC-01", "sheltering", people_count=2, smoke_seen=True, mobility_issue=False, call_id="CALL-01"),
    occ("OCC-02", "no_answer", mobility_issue=False, source=src("occupants", "gestionnaire")),
    occ("OCC-03", "sheltering", people_count=1, smoke_seen=False, mobility_issue=False, call_id="CALL-07"),
    occ("OCC-04", "sheltering", "2026-11-08T00:39:40Z", people_count=1, smoke_seen=True, mobility_issue=False,
        heading_to="ladder:2.17", call_id="CALL-02"),
    occ("OCC-05", "needs_help", people_count=1, smoke_seen=False, mobility_issue=True, call_id="CALL-04"),
    occ("OCC-06", "sheltering", people_count=1, smoke_seen=False, mobility_issue=False, call_id="CALL-05"),
]


def call(cid, occ_id, lang, status, voice=None, urgency=None, direction="out", channel="phone", summary=None, number=None):
    c = {"call_id": cid, "direction": direction, "number_masked": number or f"+3310•••••0{occ_id[-1]}",
         "channel": channel, "status": status, "language": lang, "started_at": "2026-11-08T00:32:00Z"}
    if occ_id and direction == "out":
        c["occupant_id"] = occ_id
    if summary:
        c["summary_fr"] = summary
    if voice:
        c["voice"] = {"emotion": voice[0], "sentiment": voice[1], "text": voice[2], "at": voice[3]}
    if urgency:
        c["urgency"] = {"level": urgency[0], "reasons_fr": urgency[1], "raised_by_voice": urgency[2],
                        "computed_at": "2026-11-08T00:34:00Z"}
    return c


calls = [
    call("CALL-01", "OCC-01", "fr", "active",
         ("fear", "negative", "Il y a de la fumée sous la porte, on n'ose pas sortir.", "2026-11-08T00:33:20Z"),
         (3, ["fumée sous la porte", "peur dans la voix"], False),
         summary="Appel Léa Martin : deux personnes chambre 3.12, fumée sous la porte, restent sur place."),
    call("CALL-02", "OCC-04", "en", "active",
         ("neutral", "neutral", "I'm on the second floor, I'm going down the stairs right now. There's some smoke.", "2026-11-08T00:33:30Z"),
         (3, ["descend vers l'escalier A, enfumé", "fumée signalée"], False),
         summary="Appel Tom Becker, anglais : 2e, fumée signalée, descend par l'escalier A."),
    call("CALL-03", None, "en", "active",
         ("negative_surprise", "negative", "There's thick smoke coming out of the garage ramp.", "2026-11-08T00:34:10Z"),
         (1, ["dehors"], False), direction="in", channel="web", number="web",
         summary="Appel 112, anglais : témoin dehors, fumée épaisse qui sort de la rampe du parking."),
    call("CALL-04", "OCC-05", "fr", "active",
         ("distress", "negative", "Je suis en fauteuil roulant, je ne peux pas descendre seule.", "2026-11-08T00:33:40Z"),
         (3, ["fauteuil roulant, ne peut pas descendre seule", "détresse dans la voix"], False),
         summary="Appel Inès Rahmani : 2e, chambre 2.01, en fauteuil, ne peut pas descendre seule. Aide nécessaire."),
    call("CALL-05", "OCC-06", "es", "active",
         ("fear", "negative", "Estoy en la planta baja, no veo humo. ¿Qué tengo que hacer?", "2026-11-08T00:33:50Z"),
         (3, ["RDC, pas de fumée", "peur dans la voix"], True),
         summary="Appel Lucía García, espagnol : RDC, séjour-cuisine 0.19, pas de fumée, demande quoi faire. Consigne ?"),
    call("CALL-06", "OCC-02", "fr", "no_answer", None, (2, ["sans nouvelles"], False)),
    call("CALL-07", "OCC-03", "fr", "active",
         ("relief", "positive", "Je suis chez moi, porte fermée. Pas de fumée chez moi.", "2026-11-08T00:33:15Z"),
         (2, ["1er, pas de fumée"], False),
         summary="Appel Sophie Durand : 1er, chambre 1.01, pas de fumée, reste sur place."),
]

STANDING_FR = "Consigne par défaut aux occupants : si fumée dans l'escalier ou devant la porte, rester chez soi, porte fermée."
TOM_GATE = "Tom Becker, 2e, descend par l'escalier A, enfumé, seul escalier. Je lui dis de rester dans son logement, porte fermée, et d'aller sur le balcon ?"
LUCIA_GATE = "Je dis à Lucía García : « Sortez par la terrasse. »"
gates = [
    {"gate_id": "gate_00", "kind": "relay_order", "summary_fr": STANDING_FR, "confirmer": "COS", "status": "confirmed",
     "created_at": "2026-11-08T00:25:05Z", "resolved_at": "2026-11-08T00:25:40Z", "resolved_by": "voice"},
    {"gate_id": "gate_01", "kind": "reroute_occupant", "summary_fr": TOM_GATE, "confirmer": "COS", "status": "confirmed",
     "created_at": "2026-11-08T00:39:30Z", "resolved_at": "2026-11-08T00:39:40Z", "resolved_by": "voice"},
    {"gate_id": "gate_02", "kind": "relay_order", "summary_fr": LUCIA_GATE, "confirmer": "COS", "status": "pending",
     "created_at": "2026-11-08T00:40:00Z"},
]

ENDPOINT_STATUS = [
    ("dispatch.read", "replica", True, 6200), ("maps.building", "real", True, 71000), ("georisques.risks", "real", False, 1200),
    ("weather.wind", "real", True, 18000), ("plan.read", "real", True, 24000), ("occupants.list", "replica", True, 9400),
    ("dispatch.write_112", "replica", True, 7800), ("report.fill", "replica", True, 0),
]
state = {
    "incident": {"id": "INC-0001", "address": "DEMO_ADDRESS", "nature": NATURE, "origin": {"floor": -1, "room": "-1.11"},
                 "declared_at": "2026-11-08T00:25:00Z", "status": "on_scene", "exercise": True},
    "building": building_state,
    "occupants": occupants,
    "calls": calls,
    "crew": {"teams": [
        {"id": "B1", "label": "Binôme 1", "status": "engaged", "entered_at": "2026-11-08T00:36:00Z", "pressure_bar_start": 300,
         "exit_by": "2026-11-08T00:51:00Z", "location": {"level": 3, "room": "corridor"}, "last_update": "2026-11-08T00:38:00Z"},
        {"id": "B2", "label": "Binôme 2", "status": "standby", "last_update": "2026-11-08T00:36:00Z"},
    ]},
    "environment": {
        "wind": {"dir_deg": 270, "dir_label": "ouest", "speed_kmh": 20, "source": src("meteo", "Météo-France")},
        "risks": [{**r, "source": src("georisques", "Géorisques")} for r in RISKS],
    },
    "routes": routes,
    "gates": gates,
    "halo": {
        "current_view": {"view_id": "view_approach_1", "url": "http://localhost:8002/views/view_approach_1/",
                         "moment": "approach", "built_by": "devin", "since": "2026-11-08T00:31:00Z"},
        "requests": [
            {"request_id": "req_01", "moment": "approach", "purpose_fr": "Par où j'entre", "status": "ready",
             "view_id": "view_approach_1", "url": "http://localhost:8002/views/view_approach_1/",
             "devin_session_url": "https://app.devin.ai/sessions/example", "requested_at": "2026-11-08T00:26:00Z",
             "ready_at": "2026-11-08T00:31:00Z"},
            {"request_id": "req_02", "moment": "team_engaged", "purpose_fr": "Mon air", "status": "building",
             "requested_at": "2026-11-08T00:36:10Z"},
        ],
    },
    "rosetta": {
        "endpoints": [{"name": n, "kind": k, "verified": True, "status": "ok", "last_live": live, "last_duration_ms": d}
                      for n, k, live, d in ENDPOINT_STATUS],
        "counter": {"sources_without_api": 8, "endpoints": 8},
    },
    "timeline": [
        {"t": "2026-11-08T00:25:00Z", "kind": "seraph", "text_fr": "Incident INC-0001 déclenché (exercice)."},
        {"t": "2026-11-08T00:25:40Z", "kind": "gate", "text_fr": "Confirmé par le COS (voix) : " + STANDING_FR},
        {"t": "2026-11-08T00:27:10Z", "kind": "rosetta", "text_fr": "Plan R-1 lu : escalier A, garage, local électrique, rampe E2."},
        {"t": "2026-11-08T00:28:30Z", "kind": "radio", "text_fr": "Seraph → Tête : entrée par E1, évitez E2 (garage en feu), seul escalier enfumé, hydrant à 30 m."},
        {"t": "2026-11-08T00:33:40Z", "kind": "call", "text_fr": "Appel Léa Martin : deux personnes chambre 3.12, fumée sous la porte."},
        {"t": "2026-11-08T00:39:30Z", "kind": "gate", "text_fr": "Proposition : " + TOM_GATE},
        {"t": "2026-11-08T00:39:40Z", "kind": "gate", "text_fr": "Confirmé par le COS (voix) : Tom Becker reste dans son logement, balcon 2.17, point échelle."},
        {"t": "2026-11-08T00:40:00Z", "kind": "gate", "text_fr": "Proposition : " + LUCIA_GATE},
    ],
    "alerts": [
        {"alert_id": "al_01", "level": "warning", "text_fr": "Personne à mobilité réduite au 2e (2.01)", "created_at": "2026-11-08T00:35:00Z", "spoken": True},
        {"alert_id": "al_02", "level": "warning", "text_fr": "Sans nouvelles : Karim Benali, 1.11", "created_at": "2026-11-08T00:37:00Z", "spoken": True},
        {"alert_id": "al_03", "level": "warning", "text_fr": "Échelle : balcon 2.17, 2e, Tom Becker", "created_at": "2026-11-08T00:39:40Z", "spoken": True},
    ],
}
dump(FX / "state-sample.json", state)
print("ok", {r["id"]: r["via"] for r in routes})
