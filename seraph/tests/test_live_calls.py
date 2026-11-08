"""Amil's two real 112 calls (2026-11-08 08:48 and 08:54 UTC, INC-0001), replayed at their real timing from
Gabriel's logs (tests/data/live_112_2026-11-08.jsonl): one main courante entry per call, few radio lines, one
person per caller at the right room, no misheard fire, no level-only duplicate."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from harness import make_brain
from seraph.brain import caller_name, injured
from seraph.config import settings

DATA = [json.loads(l) for l in (Path(__file__).parent / "data" / "live_112_2026-11-08.jsonl")
        .read_text(encoding="utf-8").splitlines() if l.strip()]
C1, C2 = "_16463575046_zEQFiPcaNRHd", "_16463575046_GVooPFzZH57b"


@pytest.fixture(autouse=True)
def loop():
    asyncio.set_event_loop(asyncio.new_event_loop())
    yield


@pytest.fixture(autouse=True)
def rules_only(monkeypatch):
    monkeypatch.setattr(type(settings), "llm_enabled", property(lambda self: False))


def replay():
    """Each message at its logged time; tick every second in between, as app.state_loop does."""
    b = make_brain(play_calls=False)
    b.start_incident()
    clock = {"now": 1000.0}
    b.clock = lambda: clock["now"]
    writes: list[dict] = []
    run = b.run_rosetta

    def spy(run_id, endpoint, params, priority):
        if endpoint == "dispatch.write_112":
            writes.append(params)
        run(run_id, endpoint, params, priority)

    b.run_rosetta = spy
    lines: dict[str, list[str]] = {C1: [], C2: []}
    n = len(b.say_log)
    cur = C1
    last = 0.0
    for ev in DATA + [{"t": DATA[-1]["t"] + 10, "msg": None}]:
        while last + 1 <= ev["t"]:
            last += 1
            clock["now"] = 1000 + last
            b.tick()
        clock["now"] = 1000 + ev["t"]
        lines[cur] += [s["text"] for s in b.say_log[n:] if s["target"] == {"room": "crew"}]
        n = len(b.say_log)
        if ev["msg"] is None:
            break
        m = ev["msg"]
        cur = m["call_id"]
        (b.on_call_event if m["kind"] == "call_event" else b.on_call_facts)(m)
    return b, lines, writes


def test_one_main_courante_entry_per_call():
    b, _, writes = replay()
    assert len(writes) == 2, [w["entry_fr"] for w in writes]
    e1, e2 = (w["entry_fr"] for w in writes)
    assert "quatre personnes séjour-cuisine 3.10" in e1 and "aucun" not in e1
    assert "Appel 112, Edouard : 2e, WC 2.11, mobilité réduite, blessé" in e2


def test_few_radio_lines_per_call():
    b, lines, _ = replay()
    for cid in (C1, C2):
        assert 1 <= len(lines[cid]) <= 3, (cid, lines[cid])
    assert lines[C1][-1] == "Appel 112 : quatre personnes séjour-cuisine 3.10, feu visible, restent sur place."
    assert lines[C2][-1] == "Appel 112 : 2e, WC 2.11, mobilité réduite, blessé, feu visible. Aide nécessaire."
    assert not [l for l in lines[C1] + lines[C2] if "aucun" in l or "blessé :" in l]


def test_each_caller_is_one_person_at_the_right_room():
    b, _, _ = replay()
    callers = [o for o in b.state.occupants if o.id.startswith("APP-")]
    assert len(callers) == 2, [o.id for o in callers]
    by_call = {o.call_id: o for o in callers}
    o1, o2 = by_call[C1], by_call[C2]
    assert (o1.level, o1.room, o1.people_count, o1.name, o1.injuries) == (3, "3.10", 4, "Appelant 112", None)
    assert (o2.level, o2.room, o2.name, o2.mobility_issue, o2.status) == (2, "2.11", "Edouard", True, "needs_help")
    for o in (o1, o2):
        assert o.phone_masked is None and o.source.label == "appel 112" and not o.source.confirmed
        assert b.call(o.call_id).occupant_id == o.id
    placed = [c["occupant_id"] for m in b.sent if m["kind"] == "place_calls" for c in m["calls"]]
    assert not [x for x in placed if x.startswith("APP-")]
    assert all("aucun" not in r for r in b.call(C1).urgency.reasons_fr)
    assert "blessé" in b.call(C2).urgency.reasons_fr
    focus = {lv.level: lv.focus for lv in b.state.building.levels}
    assert focus[2] and focus[3]


def test_call_hazards_on_the_callers_level_without_duplicates():
    b, _, _ = replay()
    hz = [h for h in b.state.building.hazards if h.source.kind == "call"]
    assert not [h for h in hz if h.where.get("room") in ("1.10", "-1.10") or h.where.get("level") == 1]
    assert any(h.kind == "fire" and h.where == {"level": 3, "room": "3.10"} for h in hz)
    for h in hz:
        if h.where.get("room"):
            assert not [x for x in hz if x.kind == h.kind and x.where == {"level": h.where["level"]}], h.where
    unconf = [e.text_fr for e in b.state.timeline if "à confirmer" in e.text_fr]
    assert len(unconf) == 1 and "1.10" in unconf[0]


def test_a_name_on_the_list_links_the_call_to_that_occupant():
    b = make_brain(play_calls=False)
    b.start_incident()
    cid = "IN-1"
    b.on_call_event({"kind": "call_event", "call_id": cid, "event": "answered", "direction": "in", "occupant_id": None})
    b.on_call_facts({"kind": "call_facts", "call_id": cid, "lang": "fr", "occupant_id": None,
                     "facts": {"level": 1, "current_action": "staying"}, "transcript_excerpt": "Je suis au premier."})
    assert [o.id for o in b.state.occupants if o.id.startswith("APP-")] == ["APP-1"]
    b.on_call_facts({"kind": "call_facts", "call_id": cid, "lang": "fr", "occupant_id": None,
                     "facts": {"level": 1, "current_action": "staying"},
                     "transcript_excerpt": "Je suis au premier. Je m'appelle Sophie."})
    assert not [o for o in b.state.occupants if o.id.startswith("APP-")]
    assert b.call(cid).occupant_id == "OCC-03" and b.occ("OCC-03").call_id == cid


def test_names_and_injuries_as_said():
    assert caller_name("Je suis bloqué au R3. C'est bon. Au feu.") is None
    assert caller_name("Merci. Je m'appelle Edouard. Du coup, c'était quoi, Yannick ?") == "Edouard"
    assert caller_name("Hello, my name is tom.") == "Tom"
    assert caller_name("Oui, c'est Karim, au premier.") == "Karim"
    assert caller_name("Me llamo Lucía.") == "Lucía"
    for no in ("aucun", "Aucune", "none", "non", "pas de blessé", "rien", "personne"):
        assert not injured({"injuries": no}), no
    for yes in ("blessé", "Moi je suis blessé", "brûlure à la main", "personne blessée"):
        assert injured({"injuries": yes}), yes
