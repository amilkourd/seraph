"""Outbound IO: SSE bus, Gabriel sockets, Rosetta and Silex clients, mock Gabriel. Every external call has a timeout
and a fixture fallback that is labelled (live:false → « cache »)."""
from __future__ import annotations

import asyncio
import json
import time
from typing import TYPE_CHECKING, Any, Optional

import httpx
from fastapi import WebSocket

from .config import FIXTURES, settings
from .models import dump, now_iso

if TYPE_CHECKING:
    from .brain import Brain

TIMEOUTS = {"dispatch.read": 30, "maps.building": 90, "georisques.risks": 45, "weather.wind": 45, "plan.read": 60,
            "occupants.list": 30, "dispatch.write_112": 30, "report.fill": 120, "explore": 120}
MOCK_DELAY = {"dispatch.read": 1.2, "maps.building": 5.0, "georisques.risks": 3.0, "weather.wind": 2.5,
              "plan.read": 4.0, "occupants.list": 2.0, "dispatch.write_112": 1.5, "report.fill": 6.0}
HALO_EVENTS = {"state", "alert", "halo_view"}


class Bus:
    """SSE fan-out. `state` is coalesced and sent at most 4/s by `state_loop`."""

    def __init__(self) -> None:
        self.clients: list[tuple[asyncio.Queue, str]] = []

    def subscribe(self, client: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=2000)
        self.clients.append((q, client))
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self.clients = [(x, c) for x, c in self.clients if x is not q]

    def publish(self, event: str, data: Any) -> None:
        payload = json.dumps(data, ensure_ascii=False, default=str)
        for q, client in self.clients:
            if client == "halo" and event not in HALO_EVENTS:
                continue
            try:
                q.put_nowait((event, payload))
            except asyncio.QueueFull:
                pass


class GabrielHub:
    """Every connected Gabriel socket gets every SeraphToGabriel message; workers filter on `target`."""

    def __init__(self) -> None:
        self.sockets: set[WebSocket] = set()
        self.last_seen: Optional[float] = None

    @property
    def connected(self) -> int:
        return len(self.sockets)

    def send(self, msg: dict) -> None:
        text = json.dumps(msg, ensure_ascii=False)
        for ws in list(self.sockets):
            asyncio.get_running_loop().create_task(self._send(ws, text))

    async def _send(self, ws: WebSocket, text: str) -> None:
        try:
            await ws.send_text(text)
        except Exception:
            self.sockets.discard(ws)


def fixture_result(endpoint: str, run_id: str) -> Optional[dict]:
    p = FIXTURES / "endpoints" / f"{endpoint}.json"
    if not p.exists():
        return None
    r = json.loads(p.read_text(encoding="utf-8"))
    r["run_id"] = run_id
    r["live"] = False
    t = now_iso()
    r["started_at"] = r["ended_at"] = t
    if r.get("source"):
        r["source"]["at"] = t
    for s in r.get("screenshots") or []:
        s["taken_at"] = t
    return r


class Rosetta:
    def __init__(self, brain: "Brain") -> None:
        self.brain = brain
        self.reachable: Optional[bool] = None

    def use_mock(self) -> bool:
        return settings.mock or self.brain.replay_mode

    def run(self, run_id: str, endpoint: str, params: dict, priority: int) -> None:
        asyncio.get_running_loop().create_task(self._run(run_id, endpoint, params, priority))

    async def _run(self, run_id: str, endpoint: str, params: dict, priority: int) -> None:
        if self.use_mock():
            await asyncio.sleep(MOCK_DELAY.get(endpoint, 1.5) / max(self.brain.mock_speed, 1.0))
            self._fallback(run_id, endpoint, "mock")
            return
        body = {"run_id": run_id, "endpoint": endpoint, "params": params, "priority": priority, "allow_cache": True}
        try:
            async with httpx.AsyncClient(timeout=5) as c:
                r = await c.post(f"{settings.rosetta_url}/run", json=body)
                r.raise_for_status()
            self.reachable = True
        except Exception as e:
            self.reachable = False
            self.brain.log("rosetta", f"Rosetta injoignable pour {endpoint} ({type(e).__name__}) : cache.")
            self._fallback(run_id, endpoint, "unreachable")
            return
        await asyncio.sleep(TIMEOUTS.get(endpoint, 60))
        run = self.brain.runs.get(run_id)
        if run and not run.get("done"):
            self.brain.log("rosetta", f"Rosetta {endpoint} : délai dépassé ({TIMEOUTS.get(endpoint)} s), cache.")
            self._fallback(run_id, endpoint, "timeout")

    def _fallback(self, run_id: str, endpoint: str, why: str) -> None:
        if endpoint == "report.fill" and why != "mock":
            self.brain.on_rosetta_result({"run_id": run_id, "endpoint": endpoint, "status": "failed", "live": False,
                                          "screenshots": [], "error": why, "started_at": now_iso()})
            return
        r = fixture_result(endpoint, run_id)
        if r is None:
            self.brain.on_rosetta_result({"run_id": run_id, "endpoint": endpoint, "status": "failed", "live": False,
                                          "screenshots": [], "error": why, "started_at": now_iso()})
            return
        self.brain.on_rosetta_result(r)

    def explore(self, run_id: str, question_fr: str) -> None:
        asyncio.get_running_loop().create_task(self._explore(run_id, question_fr))

    async def _explore(self, run_id: str, question_fr: str) -> None:
        fail = {"run_id": run_id, "endpoint": "explore", "status": "failed", "live": False, "screenshots": [],
                "started_at": now_iso()}
        if self.use_mock():
            await asyncio.sleep(1.0)
            self.brain.on_rosetta_result({**fail, "error": "mock: pas d'exploration en mode fixtures"})
            return
        try:
            async with httpx.AsyncClient(timeout=5) as c:
                r = await c.post(f"{settings.rosetta_url}/explore", json={"question_fr": question_fr})
                r.raise_for_status()
                remote_id = r.json().get("run_id")
            if remote_id and remote_id != run_id:
                self.brain.runs[remote_id] = self.brain.runs.pop(run_id)
                self.brain.runs[remote_id]["run_id"] = remote_id
                run_id = remote_id
        except Exception as e:
            self.brain.on_rosetta_result({**fail, "error": f"Rosetta injoignable ({type(e).__name__})"})
            return
        await asyncio.sleep(TIMEOUTS["explore"])
        run = self.brain.runs.get(run_id)
        if run and not run.get("done"):
            self.brain.on_rosetta_result({**fail, "run_id": run_id, "error": "délai dépassé"})


class Silex:
    def __init__(self, brain: "Brain") -> None:
        self.brain = brain
        self.reachable: Optional[bool] = None

    def request(self, vr: dict) -> None:
        asyncio.get_running_loop().create_task(self._request(vr))

    async def _request(self, vr: dict) -> None:
        if settings.mock:
            await asyncio.sleep(0.5)
            self.brain.on_view_ready({"request_id": vr["request_id"], "status": "failed",
                                      "note": "mock : pas de Devin, vue de secours"})
            return
        try:
            async with httpx.AsyncClient(timeout=8) as c:
                r = await c.post(f"{settings.silex_url}/views/request", json=vr)
                r.raise_for_status()
            self.reachable = True
            self.brain.on_view_ready({"request_id": vr["request_id"], "status": "building"})
        except Exception as e:
            self.reachable = False
            self.brain.on_view_ready({"request_id": vr["request_id"], "status": "failed",
                                      "note": f"Silex injoignable ({type(e).__name__})"})

    def learn(self, body: dict) -> None:
        asyncio.get_running_loop().create_task(self._learn(body))

    async def _learn(self, body: dict) -> None:
        if settings.mock:
            return
        try:
            async with httpx.AsyncClient(timeout=8) as c:
                await c.post(f"{settings.silex_url}/endpoints/learn", json=body)
        except Exception as e:
            self.brain.log("silex", f"Silex injoignable pour l'apprentissage ({type(e).__name__}).")


class MockGabriel:
    """Plays contracts/fixtures/calls.jsonl for place_calls when MOCK=1 (or replay) and no Gabriel is connected.
    Each call: ringing → answered → call_facts (expected_facts + last voice), or ringing → no_answer."""

    def __init__(self, brain: "Brain", hub: GabrielHub) -> None:
        self.brain = brain
        self.hub = hub
        self.calls = [json.loads(l) for l in (FIXTURES / "calls.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
        self.plays: dict[str, int] = {}

    def active(self) -> bool:
        return (settings.mock or self.brain.replay_mode) and (self.hub.connected == 0 or self.brain.replay_mode)

    def on_place_calls(self, calls: list[dict]) -> None:
        if not self.active():
            return
        loop = asyncio.get_event_loop()
        for i, c in enumerate(calls):
            fx = next((x for x in self.calls if x.get("occupant_id") == c["occupant_id"]), None)
            if fx:
                loop.create_task(self.play(fx, delay=1.0 + i * 2.5))
            else:
                loop.create_task(self.ring_only(c, delay=1.0 + i * 2.5))

    async def ring_only(self, c: dict, delay: float) -> None:
        await asyncio.sleep(delay / self.speed)
        cid = f"CALL-{c['occupant_id']}"
        self.brain.on_call_event({"kind": "call_event", "call_id": cid, "event": "ringing", "direction": "out",
                                  "channel": "phone", "occupant_id": c["occupant_id"],
                                  "number_masked": _mask(c.get("phone_e164", "")), "lang": c.get("language_hint"), "at": now_iso()})

    @property
    def speed(self) -> float:
        return max(self.brain.mock_speed, 1.0)

    async def play(self, fx: dict, delay: float = 0.0) -> None:
        await asyncio.sleep(delay / self.speed)
        b = self.brain
        cid = fx["call_id"]
        self.plays[cid] = self.plays.get(cid, 0) + 1
        occ = b.occ(fx.get("occupant_id"))
        num = _mask(b.phones.get(fx.get("occupant_id", ""), "")) if fx.get("occupant_id") else "112 (web)"
        base = {"kind": "call_event", "call_id": cid, "direction": fx.get("direction", "out"),
                "channel": fx.get("channel", "phone"), "occupant_id": fx.get("occupant_id"),
                "number_masked": num, "lang": fx.get("lang")}
        if fx.get("direction") == "in":
            b.on_call_event({**base, "event": "answered", "at": now_iso()})
        else:
            b.on_call_event({**base, "event": "ringing", "at": now_iso()})
            await asyncio.sleep(1.5 / self.speed)
            if not fx.get("caller_says"):
                b.on_call_event({**base, "event": "no_answer", "at": now_iso()})
                return
            b.on_call_event({**base, "event": "answered", "at": now_iso()})
        says = fx.get("caller_says") or []
        voices = fx.get("caller_voice") or []
        for i, line in enumerate(says):
            await asyncio.sleep(2.0 / self.speed)
            v = voices[i] if i < len(voices) else {"emotion": "neutral", "sentiment": "neutral"}
            last = i == len(says) - 1
            facts = dict(fx.get("expected_facts") or {}) if last else {"confidence": 0.5}
            facts["voice"] = {**v, "text": line, "at": now_iso()}
            b.on_call_facts({"kind": "call_facts", "call_id": cid, "occupant_id": fx.get("occupant_id"),
                             "lang": fx.get("lang", "fr"), "facts": facts,
                             "transcript_excerpt": " ".join(says[: i + 1]), "at": now_iso()})
            if not last:
                pass


def _mask(phone: str) -> str:
    return phone[:5] + "•••••" + phone[-2:] if len(phone) > 7 else "•••"
