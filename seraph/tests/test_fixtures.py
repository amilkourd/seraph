"""Replaying all fixtures (scenario v2, TU Wien) gives the expected events, catches, gates and lines
(briefs/seraph.md « Done when »). Generic two-stair cases run on the dev building (ifc/out-dev)."""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from harness import CALLS, RADIO, drain_calls, make_brain, play_call, radio
from seraph import building as B
from seraph import rules
from seraph.config import settings

R = {l["id"]: l for l in RADIO}
IFC_DEV = Path(__file__).resolve().parents[2] / "ifc" / "out-dev" / "building.json"


@pytest.fixture(autouse=True)
def loop():
    asyncio.set_event_loop(asyncio.new_event_loop())
    yield


@pytest.fixture(autouse=True)
def rules_only(monkeypatch):
    # the fixtures must pass on rules alone (LLM off)
    monkeypatch.setattr(type(settings), "llm_enabled", property(lambda self: False))


def v2(confirm_standing: bool = True):
    """Incident start → R00 (COS confirms the standing instruction, as in the v2 timeline) → calls → 112 witness."""
    b = make_brain()
    b.start_incident()
    if confirm_standing:
        r = radio(b, R["R00"])
        assert crew(r["says"]) == [R["R00"]["expected"]["say_crew"]]
        assert next(g for g in b.state.gates if g.kind == "relay_order").status == "confirmed"
    drain_calls(b)
    play_call(b, next(x for x in CALLS if x["call_id"] == "CALL-03"))
    return b


def crew(says):
    return [s["text"] for s in says if s["target"] == {"room": "crew"}]


@pytest.mark.parametrize("line", RADIO, ids=[l["id"] for l in RADIO])
def test_radio_rules_event(line):
    p = rules.parse(line["text"], line["speaker"])
    assert p.events, line["id"]
    exp = line["expected"]["event"]
    got = p.events[0].type
    assert got == exp or (exp == "hazard" and got == "hazard_cleared" and "hazard_cleared" in line["expected"]), line["id"]


def test_radio_fields():
    by = {l["id"]: rules.parse(l["text"], l["speaker"]).events for l in RADIO}
    t = by["R03"][0].data["team"]
    assert t == R["R03"]["expected"]["team"]
    t4, h4 = by["R04"]
    assert t4.data["team"]["location"] == {"level": 3}
    assert h4.data["hazard"] == {"kind": "smoke", "where": {"level": 3, "room": "corridor"}, "severity": "high"}
    assert by["R06"][0].data["purpose_fr"] == "Position des binômes par étage"
    o = by["R09"][0].data
    assert (o["room"], o["status"], o["heading_to"], o["team"]) == ("3.12", "moving", "stair:A", "B1")
    assert by["R13"][0].data == {"kind": "smoke", "where": {"stair": "A"}}
    assert by["R14"][0].data["lift"] is True


def test_confirm_cancel_variants_never_need_a_model():
    for t in ["Seraph, confirme.", "Seraph de COS, je confirme", "Confirmé.", "Seraph, affirmatif", "ok confirme"]:
        assert rules.parse(t, "COS").events[0].type == "confirm", t
    for t in ["Seraph, annule.", "Annulez", "Seraph, négatif.", "Seraph, on annule"]:
        assert rules.parse(t, "COS").events[0].type == "cancel", t
    ev = rules.parse("Seraph, binôme 1 confirme la progression vers le 3e étage par l'escalier A", "COS").events
    assert not ev or ev[0].type != "confirm"


def test_variants():
    cases = {
        "Seraph de Tête, par où on rentre ?": ("question", "approach"),
        "Seraph, où est l'hydrant ?": ("question", "hydrant"),
        "Seraph, fais-moi le point": ("sitrep_request", None),
        "Seraph, bilan ?": ("sitrep_request", None),
        "Seraph, prépare le compte rendu": ("report_request", None),
        "Seraph, binôme 2 engagé, 280 bars": ("team_update", None),
        "Seraph, escalier B enfumé": ("hazard", None),
        "Seraph, dis à Tom de prendre l'escalier A": ("order_to_occupants", None),
        "Seraph, montre l'approche sur Halo": ("view_request", None),
        "Seraph, plus de fumée dans l'escalier A": ("hazard_cleared", None),
    }
    for text, (ev, topic) in cases.items():
        e = rules.parse(text, "COS").events[0]
        assert e.type == ev, text
        if topic:
            assert e.data["topic"] == topic, text


def test_calls_v2():
    b = v2()
    assert b.state.building.approach.best_entrance_id == "E1"
    for fx in CALLS:
        c = b.call(fx["call_id"])
        assert c and c.urgency, fx["call_id"]
        exp = fx["expected_urgency"]
        assert c.urgency.level == exp["level"], (fx["call_id"], c.urgency)
        assert c.urgency.raised_by_voice == exp["raised_by_voice"], fx["call_id"]
        for r in exp["reasons_fr"]:
            if "voix" in r or r in ("dehors", "sans nouvelles", "fumée sous la porte", "fumée signalée"):
                assert r in c.urgency.reasons_fr, (fx["call_id"], c.urgency.reasons_fr)
    lines = crew(b.say_log)
    for cid in ("CALL-01", "CALL-03", "CALL-04", "CALL-05", "CALL-07"):
        exp = next(x for x in CALLS if x["call_id"] == cid)["expected_crew"]
        assert exp in lines, (cid, exp, lines)
    assert "Karim Benali, 1.11 : pas de réponse." in lines
    alerts = [a.text_fr for a in b.state.alerts]
    assert "Personne à mobilité réduite au 2e (2.01)" in alerts and "Sans nouvelles : Karim Benali, 1.11" in alerts
    # standing instruction only to Léa (at home, smoke); not to Sophie (no smoke) nor Inès (no smoke)
    to_calls = {s["target"].get("call_id") for s in b.say_log if s["target"].get("call_id")}
    assert to_calls == {"CALL-01"}
    lea = next(s for s in b.say_log if s["target"].get("call_id") == "CALL-01")
    assert lea["text"].startswith("Restez chez vous, porte fermée. Ne prenez pas l'escalier")
    # Tom: single smoky stair → stay + balcony gate
    g = next(g for g in b.state.gates if g.kind == "reroute_occupant")
    exp = next(x for x in CALLS if x["call_id"] == "CALL-02")["expected_catch"]["gate"]["summary_fr"]
    assert g.summary_fr == exp


def test_full_replay_v2():
    b = v2()
    says = {}
    for line in RADIO:
        if line["id"] == "R00":
            continue                     # already played by v2(), right after the incident start
        r = radio(b, line)
        says[line["id"]] = r["says"]
        if line["id"] == "R02":
            after_r02 = [h.model_copy(deep=True) for h in b.state.building.hazards]
        exp = line["expected"]
        got = r["events"][0]["type"]
        assert got == exp["event"] or (got == "hazard_cleared" and "hazard_cleared" in exp), line["id"]
        if exp["event"] == "chatter":
            assert not r["says"], line["id"]
        assert r["ms"] < 3000, (line["id"], r["ms"])

    assert crew(says["R01"]) == [R["R01"]["expected"]["say_crew"]]
    assert crew(says["R02"]) == [R["R02"]["expected"]["say_crew"]]
    hz = {(h.kind, tuple(sorted(h.where.items()))): h for h in after_r02}
    for exp_h in R["R02"]["expected"]["hazards"]:
        h = hz[(exp_h["kind"], tuple(sorted(exp_h["where"].items())))]
        assert h.source.confirmed and h.source.label == "Tête" and h.severity == exp_h["severity"]
    assert crew(says["R03"]) == [R["R03"]["expected"]["say_crew"]]      # air tracking off (ARI_ENABLED=0)
    assert b.team("B1", create=False).exit_by is None
    assert not [a for a in b.state.alerts if a.text_fr.startswith("Binôme 1, escalier A")]   # single stair: no « passez par »
    assert crew(says["R04"]) == [R["R04"]["expected"]["say_crew"]]
    assert not any(v["moment"] == "team_engaged" for v in b.views)
    occ = [v for v in b.views if v["moment"] == "occupants"]
    assert len(occ) == 1 and "building.model.ladder_points" in occ[0]["data_keys"]   # second core Devin view
    assert any(v["moment"] == "commander_request" and v["purpose_fr"] == "Position des binômes par étage" for v in b.views)
    # R07 → Tom's gate: English, balcony, ladder point 2.17
    tom = [s for s in says["R07"] if s["target"].get("call_id") == "CALL-02"]
    assert tom and tom[0]["lang"] == "en" and tom[0]["text"].startswith("The firefighters ask you to go back into your flat now")
    o = b.occ("OCC-04")
    assert (o.status, o.heading_to) == ("sheltering", "ladder:2.17")
    assert any(r.purpose == "evacuation" and r.via == ["room:2.16", "room:2.17", "ladder:2.17"] for r in b.state.routes)
    assert "Échelle : balcon 2.17, 2e, Tom Becker" in [a.text_fr for a in b.state.alerts]
    assert "Reçu. Tom Becker reste dans son logement, balcon 2.17 : point échelle." in crew(says["R07"])
    # R09: evacuation from 3.12 on the graph, no gate for Léa (with a team)
    ev = next(r for r in b.state.routes if r.purpose == "evacuation" and r.from_ == "room:3.12")
    assert ev.via == R["R09"]["expected"]["route"]["via"]
    assert ev.path and ev.path_level == 3
    assert not [g for g in b.state.gates if g.kind == "reroute_occupant" and "Léa" in g.summary_fr]
    assert crew(says["R09"]) == [R["R09"]["expected"]["say_crew"]]
    assert crew(says["R08"]) == ["Rien à annuler."]
    assert crew(says["R10"]) == [R["R10"]["expected"]["say_crew"]]
    assert crew(says["R11"]) == ["Je cherche, source non vérifiée."] and b.explored
    assert crew(says["R12"]) == [R["R12"]["expected"]["say_crew"]]
    # R13 clears the smoke on stair A
    assert crew(says["R13"]) == ["Reçu, escalier A désenfumé."]
    assert next(s for s in b.state.building.stairs if s.id == "A").status == "clear"
    # R14 lift for everyone except Inès (wheelchair) and Léa (with B1)
    assert crew(says["R14"]) == [R["R14"]["expected"]["say_crew"]]
    # R15 every caller, every language
    exp = R["R15"]["expected"]["say_calls"]
    to = {s["target"]["call_id"]: s for s in says["R15"] if s["target"].get("call_id")}
    assert to["CALL-02"]["text"] == exp["en"] and to["CALL-05"]["text"] == exp["es"] and to["CALL-07"]["text"] == exp["fr"]
    assert "CALL-04" not in to and "CALL-01" not in to
    assert crew(says["R15"]) == [R["R15"]["expected"]["say_crew"]]
    assert not b.standing_confirmed


def test_level_focus():
    b = v2()
    for line in RADIO[1:5]:
        radio(b, line)
    f = {lv.level: lv for lv in b.state.building.levels}
    assert "feu" in f[-1].focus_reasons
    assert "B1" in f[3].focus_reasons and "occupants" in f[3].focus_reasons
    assert f[2].focus and "personnes" in f[2].focus_reasons          # Tom into the smoky stair, Inès
    b2 = make_brain()
    assert not any(lv.focus for lv in b2.state.building.levels)       # idle: nothing special anywhere


def test_report_after_confirm():
    b = v2()
    radio(b, R["R10"])
    g = next(g for g in b.state.gates if g.kind == "send_report")
    b.resolve_gate(g.gate_id, True, "dashboard")
    assert any("rapport transmis, CR-0001" in s["text"] for s in b.say_log)
    assert b.state.incident.status == "closing"


def test_no_standing_instruction_without_the_cos():
    b = v2(confirm_standing=False)
    assert not [s for s in b.say_log if s["target"].get("call_id")]


def test_air_alarm_when_enabled(monkeypatch):
    from datetime import datetime, timedelta, timezone
    monkeypatch.setattr(type(settings), "ari_enabled", property(lambda self: True), raising=False)
    b = v2()
    radio(b, R["R03"])
    t = b.team("B1", create=False)
    assert t.exit_by and t.pressure_bar_start == 300
    t.exit_by = (datetime.now(timezone.utc) + timedelta(seconds=10)).isoformat().replace("+00:00", "Z")
    b.tick()
    assert any(s["text"] == "Binôme 1 de Seraph, sortie dans 5 minutes." for s in b.say_log)


def test_order_readback_is_gated():
    b = v2()
    r = radio(b, {"id": "X", "speaker": "COS", "text": "Seraph, dis à Lucía de rester chez elle."})
    assert r["events"][0]["type"] == "order_to_occupants"
    assert not [s for s in r["says"] if s["target"].get("call_id")]  # nothing to the caller before « confirme »
    r2 = radio(b, {"id": "Y", "speaker": "COS", "text": "Seraph, confirme."})
    assert [s for s in r2["says"] if s["target"].get("call_id") == "CALL-05"]


def test_building_question_from_the_model():
    b = v2()
    r = radio(b, {"id": "X", "speaker": "COS", "text": "Seraph, la porte du garage est coupe-feu ?"})
    assert "source maquette" in crew(r["says"])[0] or "pas dans la maquette" in crew(r["says"])[0]


def test_routes_never_through_ladders_or_lifts():
    b = v2()
    res = B.shortest_path(b.kit, "room:3.12", "outside", b.state.building.hazards)
    assert res and "stair:A" in res[0] and not set(res[0]) & b.kit.no_route


@pytest.mark.skipif(not IFC_DEV.exists(), reason="no dev IFC")
def test_two_stairs_reroute_on_dev_building():
    b = make_brain(building=IFC_DEV)
    b.start_incident()
    b.state.building.hazards = []
    radio(b, {"id": "X", "speaker": "Tête", "text": "Seraph de Tête, escalier B enfumé."})
    occ = next(o for o in b.state.occupants if o.level is not None and o.level >= 1)
    play_call(b, {"call_id": "CALL-90", "direction": "out", "occupant_id": occ.id, "lang": "en",
                  "caller_says": ["I'm going down the south stairs."], "caller_voice": [],
                  "expected_facts": {"level": occ.level, "current_action": "moving", "heading_to": "stair:B", "confidence": 0.9}})
    g = b.pending_gate()
    assert g.kind == "reroute_occupant" and "prendre l'escalier A" in g.summary_fr
    radio(b, {"id": "Y", "speaker": "COS", "text": "Seraph, confirme."})
    assert any(s["target"].get("call_id") == "CALL-90" and "stairway A" in s["text"] for s in b.say_log)


@pytest.mark.skipif(not IFC_DEV.exists(), reason="no dev IFC")
def test_approach_changes_when_entrance_blocked_on_dev_building():
    b = make_brain(building=IFC_DEV)
    b.start_incident()
    b.state.building.hazards = []
    radio(b, {"id": "X", "speaker": "Tête", "text": "Seraph de Tête, escalier B enfumé."})
    first = b.state.building.approach.best_entrance_id
    radio(b, {"id": "Y", "speaker": "Tête", "text": f"Seraph de Tête, porte {first} bloquée."})
    assert b.state.building.approach.best_entrance_id != first
    assert any("changement d'approche" in s["text"] for s in b.say_log)


def test_no_building_model():
    from seraph.brain import Brain
    from seraph.registry import NoBuildingRegistry
    b = Brain(registry=NoBuildingRegistry())
    b.run_rosetta = lambda *a: None
    b.start_incident()
    assert b.state.building.name == "Pas de maquette"
    assert b.state.routes == []


def test_misheard_room_never_overwrites_a_known_room():
    b = v2()
    ines = b.occ("OCC-05")
    assert ines.room == "2.01"
    assert B.resolve_room(b.kit, "2.1", 2) == "2.01" and B.resolve_room(b.kit, "201", 2) == "2.01"
    assert B.resolve_room(b.kit, "deux zéro un", 2) == "2.01" and B.resolve_room(b.kit, "2", 2) is None
    n = len(b.say_log)
    b.on_call_facts({"kind": "call_facts", "call_id": "CALL-04", "occupant_id": "OCC-05", "lang": "fr",
                     "facts": {"level": 2, "room": "2", "confidence": 0.6}, "transcript_excerpt": "Au deuxième bureau", "at": "2026-11-08T00:00:00Z"})
    assert ines.room == "2.01"                                           # « 2 » is not a room: kept 2.01
    assert not any("salle 2 " in s["text"] or s["text"].endswith("salle 2.") for s in b.say_log[n:])
    b.on_call_facts({"kind": "call_facts", "call_id": "CALL-04", "occupant_id": "OCC-05", "lang": "fr",
                     "facts": {"level": 2, "room": "2.1", "confidence": 0.6}, "transcript_excerpt": "bureau 2.1", "at": "2026-11-08T00:00:00Z"})
    assert ines.room == "2.01"
    # a caller with no known room and an unknown one → « pièce à confirmer »
    play_call(b, {"call_id": "CALL-91", "direction": "in", "lang": "fr", "caller_says": ["Je suis au deuxième, salle 2."],
                  "caller_voice": [], "expected_facts": {"level": 2, "room": "2", "current_action": "staying", "confidence": 0.5}})
    assert any("pièce à confirmer" in s["text"] for s in b.say_log)


def test_live_maps_with_new_shots_asks_devin_again():
    b = v2()
    n = len([v for v in b.views if v["moment"] == "approach"])
    assert n == 1                                            # first request on the (cached) result
    from seraph.io import fixture_result
    b.runs["run_live_2"] = {"endpoint": "maps.building", "params": {}, "started": 0, "done": False,
                            "incident_id": b.state.incident.id, "incident_t0": b.incident_t0}
    res = fixture_result("maps.building", "run_live_2")
    res["live"] = True
    res["screenshots"] = res["screenshots"] + [dict(res["screenshots"][0], image_id="sv-live-77")]
    b.on_rosetta_result(res)
    assert len([v for v in b.views if v["moment"] == "approach"]) == 2
    assert "sv-live-77" in [r["image_id"] for r in b.views[-1]["references"]]
    b.runs["run_live_2"]["done"] = False
    b.on_rosetta_result(res)                                 # same shots again → no third request
    assert len([v for v in b.views if v["moment"] == "approach"]) == 2


def test_no_news_only_after_a_call_rang():
    import time as _t
    b = make_brain(play_calls=False)            # Gabriel logs place_calls, dials nobody (SIP off)
    b.start_incident()
    assert all(o.status == "unknown" for o in b.state.occupants)
    b.called_at = {k: v - 600 for k, v in b.called_at.items()}
    b.tick()
    assert not [a for a in b.state.alerts if a.text_fr.startswith("Sans nouvelles")]
    b.on_call_event({"kind": "call_event", "call_id": "CALL-X", "event": "ringing", "direction": "out", "channel": "phone",
                     "occupant_id": "OCC-03", "number_masked": "•••", "at": "2026-11-08T00:00:00Z"})
    b.called_at["OCC-03"] = _t.time() - 600
    b.tick()
    assert "Sans nouvelles : Sophie Durand, 1.01" in [a.text_fr for a in b.state.alerts]


def test_hazards_only_from_a_source():
    b = make_brain()
    assert b.state.building.hazards == []                    # a reset starts with zero hazards, whatever the model
    b.start_incident()                                        # dispatch.read: the 112 callers' words
    hz = b.state.building.hazards
    assert hz and all(h.source.kind == "dispatch" and h.source.label == "alerte" and not h.source.confirmed for h in hz)
    fire = next(h for h in hz if h.kind == "fire")
    assert fire.where == {"level": -1, "room": "-1.11"}
    radio(b, R["R02"])                                        # the crew sees it → confirmed, « selon Tête »
    fire = next(h for h in b.state.building.hazards if h.kind == "fire")
    assert fire.source.confirmed and fire.source.label == "Tête"
    radio(b, {"id": "X", "speaker": "Tête", "text": "Seraph de Tête, levée de doute, pas de fumée à l'entrée E2."})
    assert not [h for h in b.state.building.hazards if h.where.get("entrance") == "E2"]


def test_stale_rosetta_result_after_reset_never_reaches_the_state():
    from seraph.io import fixture_result
    b = make_brain()
    b.run_rosetta = lambda *a: None                          # Rosetta answers late
    b.start_incident()
    old_run = next(r for r, v in b.runs.items() if v["endpoint"] == "dispatch.read")
    b.reset()
    assert b.state.building.hazards == [] and b.state.building.screenshots == []
    res = fixture_result("dispatch.read", old_run)
    b.on_rosetta_result(res)                                  # the run from before the reset arrives now
    assert b.state.incident.nature == "" and b.state.building.hazards == []
    assert any("Résultat périmé ignoré" in e.text_fr for e in b.state.timeline)
    # and a new incident ignores it too
    b.start_incident()
    b.on_rosetta_result(fixture_result("dispatch.read", old_run))
    assert b.state.building.hazards == []


def test_reported_until_a_firefighter_says_it():
    b = v2()
    tom = b.occ("OCC-04")
    assert tom.source.kind == "call" and not tom.source.confirmed
    e2 = next(h for h in b.state.building.hazards if h.where == {"entrance": "E2"})
    assert not e2.source.confirmed                            # the ramp smoke stays « signalé »: no crew line on it
    radio(b, R["R02"])
    st = next(h for h in b.state.building.hazards if h.where == {"stair": "A"})
    assert (st.source.kind, st.source.label, st.source.confirmed) == ("radio", "Tête", True)
    radio(b, R["R03"]); radio(b, R["R04"])
    cor = next(h for h in b.state.building.hazards if h.where.get("room") == "corridor")
    assert cor.source.confirmed and cor.source.label == "Binôme 1"
