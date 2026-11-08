"""Synchronous harness: Rosetta answers from fixtures at once, place_calls plays calls.jsonl at once."""
from __future__ import annotations

import json

from seraph.brain import Brain
from seraph.config import FIXTURES
from seraph.io import fixture_result
from seraph.models import now_iso

CALLS = [json.loads(l) for l in (FIXTURES / "calls.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
RADIO = [json.loads(l) for l in (FIXTURES / "radio.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]


def play_call(b: Brain, fx: dict) -> None:
    cid = fx["call_id"]
    base = {"kind": "call_event", "call_id": cid, "direction": fx.get("direction", "out"),
            "channel": fx.get("channel", "phone"), "occupant_id": fx.get("occupant_id"), "number_masked": "•••",
            "lang": fx.get("lang")}
    if fx.get("direction") == "in":
        b.on_call_event({**base, "event": "answered", "at": now_iso()})
    else:
        b.on_call_event({**base, "event": "ringing", "at": now_iso()})
        if not fx.get("caller_says"):
            b.on_call_event({**base, "event": "no_answer", "at": now_iso()})
            return
        b.on_call_event({**base, "event": "answered", "at": now_iso()})
    says, voices = fx.get("caller_says") or [], fx.get("caller_voice") or []
    for i, line in enumerate(says):
        last = i == len(says) - 1
        facts = dict(fx.get("expected_facts") or {}) if last else {"confidence": 0.5}
        v = voices[i] if i < len(voices) else {"emotion": "neutral", "sentiment": "neutral"}
        facts["voice"] = {**v, "text": line, "at": now_iso()}
        b.on_call_facts({"kind": "call_facts", "call_id": cid, "occupant_id": fx.get("occupant_id"),
                         "lang": fx.get("lang", "fr"), "facts": facts, "transcript_excerpt": " ".join(says[: i + 1]),
                         "at": now_iso()})


def make_brain(play_calls: bool = True, building=None) -> Brain:
    from seraph.registry import LocalRegistry
    b = Brain(registry=LocalRegistry(building or FIXTURES / "building.json"))
    b.sent: list[dict] = []  # type: ignore[attr-defined]
    b.views: list[dict] = []  # type: ignore[attr-defined]
    b.explored: list[str] = []  # type: ignore[attr-defined]

    def run(run_id, endpoint, params, priority):
        r = fixture_result(endpoint, run_id)
        b.on_rosetta_result(r or {"run_id": run_id, "endpoint": endpoint, "status": "failed", "screenshots": []})

    pending_calls: list[dict] = []

    def send(msg):
        b.sent.append(msg)
        if msg["kind"] == "place_calls" and play_calls:
            pending_calls.extend(msg["calls"])

    b.run_rosetta = run
    b.send_gabriel = send
    b.request_view_out = lambda vr: b.views.append(vr)
    b.explore = lambda run_id, q: b.explored.append(q)
    b.pending_calls = pending_calls  # type: ignore[attr-defined]
    return b


def drain_calls(b: Brain) -> None:
    played: dict[str, int] = {}
    while b.pending_calls:  # type: ignore[attr-defined]
        c = b.pending_calls.pop(0)  # type: ignore[attr-defined]
        fx = next((x for x in CALLS if x.get("occupant_id") == c["occupant_id"]), None)
        if fx and played.get(fx["call_id"], 0) < 2:
            played[fx["call_id"]] = played.get(fx["call_id"], 0) + 1
            play_call(b, fx)


def scenario(b: Brain) -> None:
    b.start_incident()
    drain_calls(b)
    play_call(b, next(x for x in CALLS if x["call_id"] == "CALL-03"))


def radio(b: Brain, line: dict):
    import asyncio
    t = now_iso()
    return asyncio.get_event_loop().run_until_complete(b.on_radio(
        {"kind": "radio_transcript", "utterance_id": line["id"], "room": "crew", "speaker": line["speaker"],
         "lang": line.get("lang", "fr"), "text": line["text"], "start": t, "end": t}))
