"""WebSocket to Seraph (ws://…/ws/gabriel). Reconnects forever; every socket gets every SeraphToGabriel message,
so each worker filters on `target` itself. Outgoing messages wait in a small queue while the link is down."""
from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Optional, Union

import websockets

from . import config

log = logging.getLogger("gabriel.seraph")
Handler = Callable[[dict], Union[None, Awaitable[None]]]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def mask(number: str) -> str:
    """+33612345678 → +33 6•• •• •• 78. Never log a full number."""
    d = re.sub(r"\D", "", number or "")
    if len(d) < 4:
        return "••"
    return f"+{d[:2]} {d[2:3]}•• •• •• {d[-2:]}"


_PHONE = re.compile(r"\+\d[\d ]{6,16}\d")
_STD = set(vars(logging.LogRecord("", 0, "", 0, "", None, None))) | {"message", "asctime"}


def mask_logs() -> None:
    """Mask phone numbers in every log record of this process, extras included (livekit.agents logs SIP callers as
    `participant: sip_+33…`)."""
    if getattr(logging.Logger.makeRecord, "_masked", False):
        return
    make = logging.Logger.makeRecord

    def scrub(s: str) -> str:
        return _PHONE.sub(lambda m: mask(m.group()), s)

    def make_masked(self, *a, **kw):
        rec = make(self, *a, **kw)
        try:
            if rec.args:
                rec.msg, rec.args = rec.getMessage(), ()
            if isinstance(rec.msg, str):
                rec.msg = scrub(rec.msg)
            for k, v in list(vars(rec).items()):
                if k not in _STD and isinstance(v, str):
                    setattr(rec, k, scrub(v))
        except Exception:
            pass
        return rec

    make_masked._masked = True
    logging.Logger.makeRecord = make_masked


class SeraphLink:
    def __init__(self, on_message: Optional[Handler] = None, name: str = "gabriel") -> None:
        self.on_message = on_message
        self.name = name
        self.connected = asyncio.Event()
        self._out: asyncio.Queue[str] = asyncio.Queue(maxsize=500)
        self._task: Optional[asyncio.Task] = None

    def start(self) -> "SeraphLink":
        self._task = asyncio.create_task(self._run())
        return self

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()

    def send(self, msg: dict[str, Any]) -> None:
        try:
            self._out.put_nowait(json.dumps(msg, ensure_ascii=False))
        except asyncio.QueueFull:
            log.warning("seraph queue full, dropping %s", msg.get("kind"))

    def metric(self, name: str, value_ms: float, **extra: Any) -> None:
        self.send({"kind": "metric", "name": name, "value_ms": round(value_ms, 1), "at": now_iso(), "by": self.name, **extra})

    async def _run(self) -> None:
        backoff = 0.5
        while True:
            try:
                async with websockets.connect(config.SERAPH_WS, open_timeout=4, ping_interval=15, max_size=2**22) as ws:
                    self.connected.set()
                    backoff = 0.5
                    log.info("%s: Seraph link up (%s)", self.name, config.SERAPH_WS)
                    sender = asyncio.create_task(self._send_loop(ws))
                    try:
                        async for raw in ws:
                            try:
                                msg = json.loads(raw)
                            except json.JSONDecodeError:
                                continue
                            if msg.get("kind") == "error":
                                log.warning("seraph error: %s", msg.get("error"))
                                continue
                            if self.on_message:
                                r = self.on_message(msg)
                                if asyncio.iscoroutine(r):
                                    asyncio.create_task(r)
                    finally:
                        sender.cancel()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.warning("%s: Seraph link down (%s), retry in %.1fs", self.name, type(e).__name__, backoff)
            self.connected.clear()
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 5)

    async def _send_loop(self, ws: Any) -> None:
        while True:
            item = await self._out.get()
            try:
                await ws.send(item)
            except Exception:
                # put it back for the next connection, then let the reader notice the drop
                try:
                    self._out.put_nowait(item)
                except asyncio.QueueFull:
                    pass
                raise
