"""Mock Gabriel over the real WebSocket: sends fixture lines as Gabriel would and prints every message back.
  uv run python -m seraph.mock_gabriel radio R01 R07      # radio lines
  uv run python -m seraph.mock_gabriel call CALL-02        # one call (events + facts)
  uv run python -m seraph.mock_gabriel say "Seraph, quelle entrée ?" [speaker]
  uv run python -m seraph.mock_gabriel listen              # print says only"""
from __future__ import annotations

import asyncio
import json
import sys
import time

import websockets

from .config import FIXTURES, settings
from .models import now_iso


def _lines(name: str) -> list[dict]:
    return [json.loads(l) for l in (FIXTURES / name).read_text(encoding="utf-8").splitlines() if l.strip()]


async def main(argv: list[str]) -> None:
    url = (settings.seraph_url.replace("http", "ws", 1)) + "/ws/gabriel"
    async with websockets.connect(url) as ws:
        async def reader():
            async for m in ws:
                d = json.loads(m)
                print(f"{time.strftime('%H:%M:%S')} ← {d.get('kind')} {d.get('target', '')} {d.get('text', '') or d.get('calls', '')}")
        rt = asyncio.create_task(reader())
        cmd = argv[0] if argv else "listen"
        if cmd == "radio":
            for line in _lines("radio.jsonl"):
                if len(argv) > 1 and line["id"] not in argv[1:]:
                    continue
                t = now_iso()
                await ws.send(json.dumps({"kind": "radio_transcript", "utterance_id": f"mock_{line['id']}", "room": "crew",
                                          "speaker": line["speaker"], "lang": "fr", "text": line["text"], "start": t, "end": t}))
                print(f"{time.strftime('%H:%M:%S')} → {line['id']} {line['text']}")
                await asyncio.sleep(1.5)
        elif cmd == "say":
            t = now_iso()
            await ws.send(json.dumps({"kind": "radio_transcript", "utterance_id": f"mock_{int(time.time())}", "room": "crew",
                                      "speaker": argv[2] if len(argv) > 2 else "COS", "lang": "fr", "text": argv[1], "start": t, "end": t}))
            await asyncio.sleep(4)
        elif cmd == "call":
            for fx in _lines("calls.jsonl"):
                if fx["call_id"] not in argv[1:]:
                    continue
                base = {"kind": "call_event", "call_id": fx["call_id"], "direction": fx.get("direction", "out"),
                        "channel": fx.get("channel", "phone"), "occupant_id": fx.get("occupant_id"), "number_masked": "•••",
                        "lang": fx.get("lang")}
                await ws.send(json.dumps({**base, "event": "ringing", "at": now_iso()}))
                if not fx.get("caller_says"):
                    await ws.send(json.dumps({**base, "event": "no_answer", "at": now_iso()}))
                    continue
                await ws.send(json.dumps({**base, "event": "answered", "at": now_iso()}))
                says, voices = fx["caller_says"], fx.get("caller_voice") or []
                for i, line in enumerate(says):
                    last = i == len(says) - 1
                    facts = dict(fx.get("expected_facts") or {}) if last else {"confidence": 0.5}
                    facts["voice"] = {**(voices[i] if i < len(voices) else {"emotion": "neutral", "sentiment": "neutral"}),
                                      "text": line, "at": now_iso()}
                    await ws.send(json.dumps({"kind": "call_facts", "call_id": fx["call_id"], "occupant_id": fx.get("occupant_id"),
                                              "lang": fx.get("lang", "fr"), "facts": facts,
                                              "transcript_excerpt": " ".join(says[: i + 1]), "at": now_iso()}))
                    await asyncio.sleep(1)
            await asyncio.sleep(3)
        else:
            await rt
        rt.cancel()


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:]))
