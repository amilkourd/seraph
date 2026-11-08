"""POST /admin/replay: inject the fixtures as if live (Rosetta and calls from fixtures, says still go out)."""
from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Optional

from .config import FIXTURES
from .models import now_iso

if TYPE_CHECKING:
    from .brain import Brain
    from .io import MockGabriel

RADIO_GAP_S = 6.0


def radio_lines() -> list[dict]:
    return [json.loads(l) for l in (FIXTURES / "radio.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]


def radio_msg(line: dict) -> dict:
    t = now_iso()
    return {"kind": "radio_transcript", "utterance_id": f"utt_{line['id']}_{t}", "room": "crew",
            "speaker": line["speaker"], "lang": line.get("lang", "fr"), "text": line["text"], "start": t, "end": t}


class Replayer:
    def __init__(self, brain: "Brain", gabriel: "MockGabriel") -> None:
        self.brain = brain
        self.gabriel = gabriel
        self.task: Optional[asyncio.Task] = None
        self.status = "idle"

    def start(self, fixture: str, speed: float) -> None:
        if self.task and not self.task.done():
            self.task.cancel()
        self.task = asyncio.get_running_loop().create_task(self._run(fixture, max(1.0, min(speed, 20.0))))

    async def _run(self, fixture: str, speed: float) -> None:
        b = self.brain
        b.replay_mode = True
        b.mock_speed = speed
        self.status = f"running:{fixture}"
        try:
            if fixture in ("all", "radio") and b.state.incident.status in ("idle", "closed"):
                b.start_incident()
                # wait for occupants + maps (or 30 s), so the radio lines find their facts
                for _ in range(int(30 * 10 / speed) + 1):
                    if b.occupants_loaded and b.b.approach:
                        break
                    await asyncio.sleep(0.1)
            if fixture == "all":
                # calls were placed by occupants.list → mock Gabriel plays them; wait until all are through
                for _ in range(int(40 * 10 / speed) + 1):
                    if self._calls_done():
                        break
                    await asyncio.sleep(0.1)
                await self.play_call("CALL-03", speed)
            if fixture == "calls":
                for fx in self.gabriel.calls:
                    if fx.get("occupant_id") and not b.occ(fx["occupant_id"]):
                        continue
                    await self.gabriel.play(fx)
                    await asyncio.sleep(1.0 / speed)
            if fixture in ("all", "radio"):
                await asyncio.sleep(RADIO_GAP_S / speed)
                for line in radio_lines():
                    await b.on_radio(radio_msg(line))
                    await asyncio.sleep(RADIO_GAP_S / speed)
            self.status = "done"
        except asyncio.CancelledError:
            self.status = "cancelled"
            raise
        finally:
            b.replay_mode = False
            b.mock_speed = 1.0

    def _calls_done(self) -> bool:
        b = self.brain
        want = {fx["call_id"] for fx in self.gabriel.calls if fx.get("occupant_id") and b.occ(fx["occupant_id"])}
        done = {cid for cid, n in self.gabriel.plays.items() if n >= 1}
        settled = all((c := b.call(cid)) is not None and (c.summary_fr or c.status == "no_answer") for cid in want)
        return want <= done and settled

    async def play_call(self, call_id: str, speed: float = 1.0) -> bool:
        fx = next((x for x in self.gabriel.calls if x["call_id"] == call_id), None)
        if not fx:
            return False
        await self.gabriel.play(fx)
        return True

    async def line(self, line_id: str) -> Optional[dict]:
        """Replay one fixture line (dashboard key R): a radio line R.. or a call CALL-.."""
        for l in radio_lines():
            if l["id"] == line_id:
                return await self.brain.on_radio(radio_msg(l))
        if line_id.startswith("CALL"):
            prev = self.brain.replay_mode
            self.brain.replay_mode = True
            try:
                ok = await self.play_call(line_id)
            finally:
                self.brain.replay_mode = prev
            return {"ok": ok}
        return None
