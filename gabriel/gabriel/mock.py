"""MOCK=1 stand-in for Gabriel: no LiveKit, no audio. Sends fixture lines to Seraph as Gabriel would and prints every
`say` it receives (and speaks crew says on the laptop speaker with `--speak`).

  uv run gabriel-mock radio R01 R03         radio_transcript from contracts/fixtures/radio.jsonl
  uv run gabriel-mock call CALL-01          call_event answered + call_facts from contracts/fixtures/calls.jsonl
  uv run gabriel-mock say "Seraph, point de situation." COS
  uv run gabriel-mock listen [--speak]      print (and speak) Seraph's says
"""
from __future__ import annotations

import asyncio
import json
import sys
import time

from . import config
from .seraph_link import SeraphLink, mask, now_iso


def fixture(name: str) -> list[dict]:
    return [json.loads(l) for l in (config.FIXTURES / name).read_text(encoding="utf-8").splitlines() if l.strip()]


async def amain(args: list[str]) -> None:
    speak = "--speak" in args
    args = [a for a in args if a != "--speak"]
    tts = None
    if speak:
        from .tts import TTS
        tts = await TTS().__aenter__()

    async def on_msg(msg: dict) -> None:
        if msg.get("kind") == "say":
            print(f"SAY {json.dumps(msg.get('target'), ensure_ascii=False)} [{msg.get('lang')}, {msg.get('priority')}] {msg.get('text')}")
            if tts and msg.get("target", {}).get("room") == "crew":
                from .radio import play_local
                play_local(await tts.full(msg["text"], msg.get("lang", "fr")))
        elif msg.get("kind") == "place_calls":
            print("PLACE_CALLS", [(c.get("occupant_id"), mask(c.get("phone_e164", ""))) for c in msg.get("calls", [])])
        else:
            print(msg.get("kind"), json.dumps(msg, ensure_ascii=False)[:200])

    link = SeraphLink(on_msg, name="mock").start()
    await asyncio.wait_for(link.connected.wait(), 5)
    cmd, rest = (args[0], args[1:]) if args else ("listen", [])
    if cmd == "radio":
        lines = {l["id"]: l for l in fixture("radio.jsonl")}
        for rid in rest or list(lines):
            l = lines[rid]
            link.send({"kind": "radio_transcript", "utterance_id": f"mock_{rid}_{int(time.time())}", "room": "crew",
                       "speaker": l["speaker"], "lang": l.get("lang", "fr"), "text": l["text"], "start": now_iso(),
                       "end": now_iso()})
            print(f"→ {l['speaker']}: {l['text']}")
            await asyncio.sleep(3)
    elif cmd == "say":
        text, speaker = rest[0], (rest[1] if len(rest) > 1 else "COS")
        link.send({"kind": "radio_transcript", "utterance_id": f"mock_{int(time.time())}", "room": "crew",
                   "speaker": speaker, "lang": "fr", "text": text, "start": now_iso(), "end": now_iso()})
        await asyncio.sleep(3)
    elif cmd == "call":
        calls = {c["call_id"]: c for c in fixture("calls.jsonl")}
        for cid in rest:
            c = calls[cid]
            base = {"call_id": cid, "direction": c.get("direction", "out"), "channel": c.get("channel", "phone"),
                    "occupant_id": c.get("occupant_id"), "number_masked": "+33 1•• •• •• 0" + cid[-1], "lang": c.get("lang")}
            if not c.get("caller_says"):
                link.send({"kind": "call_event", "event": "no_answer", "at": now_iso(), **base})
                continue
            link.send({"kind": "call_event", "event": "answered", "at": now_iso(), **base})
            for i, line in enumerate(c["caller_says"]):
                await asyncio.sleep(2)
                last = i == len(c["caller_says"]) - 1
                facts = dict(c.get("expected_facts") or {}) if last else {"confidence": 0.5}
                v = (c.get("caller_voice") or [{}] * (i + 1))[i]
                facts["voice"] = {"emotion": v.get("emotion", "neutral"), "sentiment": v.get("sentiment", "neutral"),
                                  "text": line, "at": now_iso()}
                link.send({"kind": "call_facts", "call_id": cid, "occupant_id": c.get("occupant_id"), "lang": c["lang"],
                           "facts": facts, "transcript_excerpt": " ".join(c["caller_says"][: i + 1]), "at": now_iso()})
                print(f"→ {cid}: {line}")
        await asyncio.sleep(4)
    else:
        await asyncio.Event().wait()
    await asyncio.sleep(0.5)


def main() -> None:
    try:
        asyncio.run(amain(sys.argv[1:]))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
