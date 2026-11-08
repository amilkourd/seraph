"""Replaying all fixtures gives the expected events, catches, gates and lines (briefs/seraph.md « Done when »)."""
from __future__ import annotations

import asyncio

import pytest

from harness import CALLS, RADIO, make_brain, play_call, radio, scenario
from seraph import rules
from seraph.config import settings


@pytest.fixture(autouse=True)
def loop():
    asyncio.set_event_loop(asyncio.new_event_loop())
    yield


@pytest.fixture(autouse=True)
def rules_only(monkeypatch):
    # the fixtures must pass on rules alone (LLM off)
    monkeypatch.setattr(type(settings), "llm_enabled", property(lambda self: False))


@pytest.mark.parametrize("line", RADIO, ids=[l["id"] for l in RADIO])
def test_radio_rules_event(line):
    p = rules.parse(line["text"], line["speaker"])
    assert p.events, line["id"]
    assert p.events[0].type == line["expected"]["event"]


def test_radio_fields():
    by = {l["id"]: rules.parse(l["text"], l["speaker"]).events for l in RADIO}
    h = by["R02"][0].data["hazard"]
    assert h == {"kind": "smoke", "where": {"level": 3}, "severity": "medium"}
    t = by["R03"][0].data["team"]
    assert t == {"id": "B1", "status": "engaged", "pressure_bar_start": 300, "location": {"stair": "A"}}
    t4, h4 = by["R04"]
    assert t4.data["team"]["id"] == "B1" and t4.data["team"]["location"] == {"level": 3}
    assert h4.data["hazard"] == {"kind": "smoke", "where": {"level": 3, "room": "corridor"}, "severity": "high"}
    assert by["R06"][0].data["purpose_fr"] == "Position des binômes par étage"
    assert by["R11"][0].data["topic"] == "unknown_source"
    o = by["R09"][0].data
    assert (o["room"], o["status"], o["heading_to"], o["team"]) == ("3.12", "moving", "stair:A", "B1")


def test_confirm_cancel_variants_never_need_a_model():
    for t in ["Seraph, confirme.", "Seraph de COS, je confirme", "Confirmé.", "Seraph, affirmatif", "ok confirme"]:
        assert rules.parse(t, "COS").events[0].type == "confirm", t
    for t in ["Seraph, annule.", "Annulez", "Seraph, négatif.", "Seraph, on annule"]:
        assert rules.parse(t, "COS").events[0].type == "cancel", t
    # long lines with « confirme » inside are not a confirmation
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
    }
    for text, (ev, topic) in cases.items():
        e = rules.parse(text, "COS").events[0]
        assert e.type == ev, text
        if topic:
            assert e.data["topic"] == topic, text


def test_full_replay():
    b = make_brain()
    scenario(b)
    # approach: computed by code, E2
    assert b.state.building.approach.best_entrance_id == "E2"
    # calls: urgency per fixture
    for fx in CALLS:
        c = b.call(fx["call_id"])
        assert c and c.urgency, fx["call_id"]
        exp = fx["expected_urgency"]
        assert c.urgency.level == exp["level"], (fx["call_id"], c.urgency)
        assert c.urgency.raised_by_voice == exp["raised_by_voice"], fx["call_id"]
        voice_reasons = [r for r in exp["reasons_fr"] if "voix" in r]
        for r in voice_reasons:
            assert r in c.urgency.reasons_fr, (fx["call_id"], c.urgency.reasons_fr)
    # catches: Tom → reroute gate; Inès → alert; Karim → no news
    gates = {g.kind: g for g in b.state.gates}
    assert "reroute_occupant" in gates
    assert "Tom Becker" in gates["reroute_occupant"].summary_fr and "escalier A" in gates["reroute_occupant"].summary_fr
    alerts = [a.text_fr for a in b.state.alerts]
    assert "Personne à mobilité réduite au 2e (2.01)" in alerts
    assert "Sans nouvelles : Karim Benali, 3.10" in alerts
    crew = [s["text"] for s in b.say_log if s["target"] == {"room": "crew"}]
    assert any(t.startswith("Appel Léa Martin : deux personnes salle 3.12, fumée sous la porte") for t in crew)
    assert any(t.startswith("Appel Inès Rahmani : 2e") and "Aide nécessaire" in t for t in crew)
    assert any("Lucía García, espagnol" in t and "demande quoi faire" in t for t in crew)

    says = {}
    for line in RADIO:
        r = radio(b, line)
        says[line["id"]] = [s for s in r["says"]]
        exp = line["expected"]
        assert r["events"][0]["type"] == exp["event"], line["id"]
        crew_says = [s["text"] for s in r["says"] if s["target"] == {"room": "crew"}]
        if exp.get("say_crew") is None and exp["event"] == "chatter":
            assert not r["says"], line["id"]
        elif exp["event"] not in ("confirm", "cancel"):
            assert crew_says, line["id"]
        assert r["ms"] < 3000, (line["id"], r["ms"])

    assert says["R01"][0]["text"].startswith("Tête de Seraph : entrée par E2")
    assert b.state.halo.current_view.moment in ("team_engaged", "commander_request", "approach")
    assert "sortie prévue à" in says["R03"][0]["text"] and "Calcul simplifié" in says["R03"][0]["text"]
    team = b.team("B1", create=False)
    assert team and team.exit_by and team.pressure_bar_start == 300
    assert says["R04"][0]["text"].startswith("Binôme 1 de Seraph : reçu. En 3.12, deux personnes signalées par appel, fumée sous la porte")
    assert any(r["moment"] == "team_engaged" for r in b.views)
    assert any(r["moment"] == "commander_request" and r["purpose_fr"] == "Position des binômes par étage" for r in b.views)
    # R07 confirms the latest pending gate (Tom) → told in English
    tom = [s for s in says["R07"] if s["target"].get("call_id") == "CALL-02"]
    assert tom and tom[0]["lang"] == "en" and "stairway A" in tom[0]["text"]
    assert any(g.kind == "reroute_occupant" and g.status == "confirmed" and g.resolved_by == "voice" for g in b.state.gates)
    # R08 cancels the next pending one
    assert any(g.status == "cancelled" for g in b.state.gates)
    # R09 evacuation route from 3.12, computed on the graph
    ev = next(r for r in b.state.routes if r.purpose == "evacuation")
    assert ev.from_ == "room:3.12" and ev.to == "outside"
    assert ev.via[1:] == ["corridor:3", "level:3", "stair:A", "entrance:E2", "outside"]
    assert ev.path and len(ev.path) >= 2 and ev.path_image_id == "plan-l3-01"
    assert says["R09"][0]["text"] == "Reçu, deux victimes 3.12 avec binôme 1, descente par A."
    # R10 report gate
    assert says["R10"][0]["text"] == "COS de Seraph : rapport prêt, confirmez l'envoi."
    assert any(g.kind == "send_report" and g.status == "pending" for g in b.state.gates)
    # R11 learning
    assert says["R11"][0]["text"] == "Je cherche, source non vérifiée." and b.explored
    # R12 sitrep
    t = says["R12"][0]["text"]
    assert t.startswith("COS de Seraph : six occupants listés.")
    for part in ["un sans réponse, Karim Benali 3.10", "Deux personnes en 3.12 avec binôme 1",
                 "Inès Rahmani au 2e en fauteuil, aide nécessaire", "Escalier B enfumé"]:
        assert part in t, (part, t)


def test_report_after_confirm():
    b = make_brain()
    scenario(b)
    radio(b, next(l for l in RADIO if l["id"] == "R10"))
    g = next(g for g in b.state.gates if g.kind == "send_report")
    b.resolve_gate(g.gate_id, True, "dashboard")
    assert any("rapport transmis, CR-0001" in s["text"] for s in b.say_log)
    assert b.state.incident.status == "closing"


def test_standing_instruction_after_confirm():
    b = make_brain()
    b.start_incident()
    g = next(g for g in b.state.gates if g.kind == "relay_order")
    b.resolve_gate(g.gate_id, True, "voice")
    from harness import drain_calls
    drain_calls(b)
    lea = [s for s in b.say_log if s["target"].get("call_id") == "CALL-01"]
    assert lea and lea[0]["text"].startswith("Restez dans la pièce, porte fermée")
    tom = [s for s in b.say_log if s["target"].get("call_id") == "CALL-02"]
    assert not tom  # Tom has no smoke at his door: nothing said without the COS


def test_air_alarm():
    from datetime import datetime, timedelta, timezone
    b = make_brain()
    scenario(b)
    radio(b, next(l for l in RADIO if l["id"] == "R03"))
    t = b.team("B1", create=False)
    t.exit_by = (datetime.now(timezone.utc) + timedelta(seconds=10)).isoformat().replace("+00:00", "Z")
    b.tick()
    assert any(s["text"] == "Binôme 1 de Seraph, sortie dans 5 minutes." for s in b.say_log)


def test_order_readback_is_gated():
    b = make_brain()
    scenario(b)
    r = radio(b, {"id": "X", "speaker": "COS", "text": "Seraph, dis à Lucía de rester sur place."})
    assert r["events"][0]["type"] == "order_to_occupants"
    g = b.pending_gate()
    assert g.kind == "relay_order" and "Restez sur place." in g.summary_fr
    assert not [s for s in r["says"] if s["target"].get("call_id")]  # nothing to the caller before « confirme »
    r2 = radio(b, {"id": "Y", "speaker": "COS", "text": "Seraph, confirme."})
    to_lucia = [s for s in r2["says"] if s["target"].get("call_id") == "CALL-05"]
    assert to_lucia and to_lucia[0]["text"] == "Quédese donde está."


def test_approach_changes_when_entrance_blocked():
    b = make_brain()
    scenario(b)
    radio(b, {"id": "X", "speaker": "Tête", "text": "Seraph de Tête, porte E2 bloquée."})
    assert b.state.building.approach.best_entrance_id == "E1"
    assert any("changement d'approche" in s["text"] for s in b.say_log)


def test_no_building_model():
    from seraph.brain import Brain
    from seraph.registry import NoBuildingRegistry
    b = Brain(registry=NoBuildingRegistry())
    b.run_rosetta = lambda *a: None
    b.start_incident()
    assert b.state.building.name == "Pas de maquette"
    assert b.state.routes == []


IFC_DEV = __import__("pathlib").Path(__file__).resolve().parents[2] / "ifc" / "out-dev" / "building.json"


@pytest.mark.skipif(not IFC_DEV.exists(), reason="no IFC extractor output yet")
def test_full_replay_on_ifc_building():
    from seraph.registry import LocalRegistry
    b = make_brain()
    b.registry = LocalRegistry(IFC_DEV)
    b.reset()
    assert b.kit.adj and b.state.building.model
    scenario(b)
    assert b.state.building.approach.best_entrance_id == "E2"
    assert any(g.kind == "reroute_occupant" for g in b.state.gates)
    for line in RADIO:
        r = radio(b, line)
        assert r["events"][0]["type"] == line["expected"]["event"], line["id"]
    ev = next(r for r in b.state.routes if r.purpose == "evacuation")
    assert ev.via[0] == "room:3.12" and ev.via[-1] == "outside" and "stair:A" in ev.via
    assert ev.path and ev.path_image_id == "ifc-L3" and len(ev.path) >= 3
    r = radio(b, {"id": "X", "speaker": "COS", "text": "Seraph, la porte du local technique est coupe-feu ?"})
    assert "source maquette" in r["says"][0]["text"] or "pas dans la maquette" in r["says"][0]["text"]
