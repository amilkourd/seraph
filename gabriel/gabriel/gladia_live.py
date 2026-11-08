"""Minimal Gladia live v2 client (solaria-1, eu-west): one session per utterance on the radio, one per call.

Why not only the LiveKit plugin: the radio cuts utterances on the talkie's eot (stop_recording gives the final at
once), and calls need realtime sentiment/emotion, which livekit-plugins-gladia does not expose (docs/06-gabriel.md).
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import Any, Callable, Optional

import aiohttp

from . import config

log = logging.getLogger("gabriel.gladia")
URL = "https://api.gladia.io/v2/live?region=eu-west"
SR = 16000

# ───────── vocabulary and spelling (docs/06-gabriel.md « Gladia, used fully ») ─────────
GLOSSARY = ["Seraph", "COS", "CODIS", "CTA", "ARI", "binôme", "VSAV", "FPT", "EPA", "colonne sèche", "PEI", "ETARE",
            "ERP", "reçu", "Tête", "Halo", "Gabriel", "escalier A", "E1", "E2", "main courante",
            "point de situation", "confirme", "annule", "engagé", "bars", "hydrant", "fumée", "enfumé", "désenfumé",
            "rampe", "parking", "levée du confinement", "balcon", "terrasse", "boulevard Bessières"]

SPELLING = {
    "Seraph": ["séraphe", "sérafe", "seraphe", "séraf", "seraf", "sérapf", "Séraphin", "séraphine"],
    "Seraph de Tête": ["séraphe de tête", "sérafe de tête"],
    "Binôme 1": ["binôme un", "binome un", "binôme 1", "binome 1"],
    "Binôme 2": ["binôme deux", "binome deux", "binôme 2", "binome 2"],
    "ARI": ["a r i", "a.r.i", "a.r.i."],
    "COS": ["cosse", "c.o.s", "c o s"],
    "escalier A": ["escalier a"],
    "E1": ["e un", "e1", "eu un"],
    "E2": ["e deux", "e2", "eu deux"],
    "boulevard Bessières": ["boulevard bessière", "boulevard besière", "boulevard bessiere"],
    "reçu": ["resu", "ressu"],
    "colonne sèche": ["colonne seiche"],
}


NUM_FR = ["zéro", "un", "deux", "trois", "quatre", "cinq", "six", "sept", "huit", "neuf", "dix", "onze", "douze",
          "treize", "quatorze", "quinze", "seize", "dix-sept", "dix-huit", "dix-neuf", "vingt"]
NUM_EN = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve",
          "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen", "twenty"]
SKIP_USES = {"ascenseur", "circulation", "extérieur", "garage", "place de parking", "rampe d'accès"}


def rooms() -> list[dict]:
    """Rooms people can be in, from BUILDING_JSON (fallback: fixture): {id, level, label, use}."""
    for p in (config.ROOT / config.env("BUILDING_JSON", "ifc/out/building.json"), config.FIXTURES / "building.json"):
        try:
            b = json.loads(p.read_text(encoding="utf-8"))
            out = [r for r in b.get("building", b).get("rooms", []) or []
                   if r.get("id") and re.fullmatch(r"-?\d+\.\d+", r["id"]) and r.get("use") not in SKIP_USES]
            if out:
                return out
        except Exception:
            continue
    return []


def room_spelling(room_list: list[dict]) -> dict[str, list[str]]:
    """« deux zéro un », « deux point zéro un », « two oh one » → "2.01" (Gladia custom spelling)."""
    out: dict[str, list[str]] = {}
    for r in room_list:
        m = re.fullmatch(r"(\d)\.(\d)(\d)", r["id"])
        if not m:
            continue
        lv, a, b = int(m[1]), int(m[2]), int(m[3])
        n = a * 10 + b
        fr_tail = [f"{NUM_FR[a]} {NUM_FR[b]}"] if a == 0 else ([NUM_FR[n]] if n <= 20 else [])
        en_tail = [f"oh {NUM_EN[b]}", f"zero {NUM_EN[b]}"] if a == 0 else ([NUM_EN[n]] if n <= 20 else [])
        heard = [f"{NUM_FR[lv]} {t}" for t in fr_tail] + [f"{NUM_FR[lv]} point {t}" for t in fr_tail] \
            + [f"{NUM_EN[lv]} {t}" for t in en_tail]
        if heard:
            out[r["id"]] = heard
    return out


def building_words() -> list[str]:
    """Ids and labels from BUILDING_JSON (fallback: fixture) and the occupants' names."""
    words: list[str] = []
    path = config.ROOT / config.env("BUILDING_JSON", "ifc/out/building.json")
    for p in (path, config.FIXTURES / "building.json"):
        if p.exists():
            try:
                b = json.loads(p.read_text(encoding="utf-8"))
                b = b.get("building", b)
                for k in ("stairs", "entrances", "rooms"):
                    for it in b.get(k, []) or []:
                        for f in ("id", "label"):
                            v = it.get(f)
                            if isinstance(v, str) and 1 < len(v) < 40:
                                words.append(v)
                break
            except Exception as e:
                log.warning("building words: %s", e)
    try:
        occ = json.loads((config.FIXTURES / "occupants.json").read_text(encoding="utf-8"))
        words += [o["name"] for o in occ.get("occupants", []) if o.get("name")]
    except Exception:
        pass
    return words


def vocabulary(extra: Optional[list[str]] = None) -> list[str]:
    """Glossary, then `extra` (the caller's name and rooms), then the building's ids. Capped at 100."""
    seen: dict[str, None] = {}
    for w in GLOSSARY + (extra or []) + building_words():
        w = w.strip()
        if w and w.lower() not in (k.lower() for k in seen):
            seen[w] = None
    return list(seen)[:100]


def session_config(*, sentiment: bool, extra_vocab: Optional[list[str]] = None, endpointing: float = 0.3,
                   languages: Optional[list[str]] = None) -> dict[str, Any]:
    cfg: dict[str, Any] = {
        "encoding": "wav/pcm", "sample_rate": SR, "bit_depth": 16, "channels": 1,
        "model": "solaria-1",
        "endpointing": endpointing, "maximum_duration_without_endpointing": 15,
        "language_config": {"languages": languages or ["fr", "en", "es"], "code_switching": True},
        "pre_processing": {"audio_enhancer": True, "speech_threshold": 0.5},
        "realtime_processing": {
            "custom_vocabulary": True,
            "custom_vocabulary_config": {"vocabulary": vocabulary(extra_vocab), "default_intensity": 0.5},
            "custom_spelling": True,
            "custom_spelling_config": {"spelling_dictionary": {**room_spelling(rooms()), **SPELLING}},
        },
        "messages_config": {"receive_partial_transcripts": True, "receive_final_transcripts": True,
                            "receive_speech_events": True, "receive_lifecycle_events": False,
                            "receive_realtime_processing_events": sentiment},
    }
    if sentiment:
        cfg["realtime_processing"]["sentiment_analysis"] = True
    return cfg


# ───────── one live session ─────────
class LiveSession:
    """Send PCM16 mono 16 kHz with send(); finals land in .finals; finish() stops and returns the text."""

    def __init__(self, http: aiohttp.ClientSession, cfg: dict[str, Any],
                 on_message: Optional[Callable[[dict], None]] = None, tag: str = "") -> None:
        self.http = http
        self.cfg = cfg
        self.on_message = on_message
        self.tag = tag
        self.finals: list[dict] = []
        self.partial = ""
        self.lang: Optional[str] = None
        self.ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self._q: asyncio.Queue[Optional[bytes]] = asyncio.Queue()
        self._ready = asyncio.Event()
        self._closed = asyncio.Event()
        self._tasks: list[asyncio.Task] = []
        self.failed: Optional[str] = None
        self._last_final_at = 0.0
        self.in_speech = False
        self._stop_acked_at = 0.0

    async def start(self) -> None:
        self._tasks.append(asyncio.create_task(self._run()))

    def send(self, pcm: bytes) -> None:
        if not self._closed.is_set():
            self._q.put_nowait(pcm)

    async def _run(self) -> None:
        t0 = time.perf_counter()
        try:
            async with self.http.post(URL, json=self.cfg, headers={"X-Gladia-Key": config.GLADIA_API_KEY},
                                      timeout=aiohttp.ClientTimeout(total=6)) as r:
                if r.status >= 300:
                    raise RuntimeError(f"gladia init {r.status}: {(await r.text())[:300]}")
                info = await r.json()
            self.ws = await self.http.ws_connect(info["url"], timeout=aiohttp.ClientWSTimeout(ws_receive=None, ws_close=3), heartbeat=20)
            log.debug("%s gladia ready in %.0f ms", self.tag, (time.perf_counter() - t0) * 1000)
            self._ready.set()
            self._tasks.append(asyncio.create_task(self._recv()))
            buf = b""
            while True:
                item = await self._q.get()
                if item is None:
                    if buf:
                        await self.ws.send_bytes(buf)
                    await self.ws.send_str(json.dumps({"type": "stop_recording"}))
                    break
                buf += item
                if len(buf) >= SR // 10 * 2 or self._q.empty() and len(buf) >= SR // 50 * 2:   # ~100 ms, flush when caught up
                    await self.ws.send_bytes(buf)
                    buf = b""
        except Exception as e:
            self.failed = f"{type(e).__name__}: {e}"
            log.warning("%s gladia session failed: %s", self.tag, self.failed)
            self._closed.set()

    async def _recv(self) -> None:
        assert self.ws is not None
        try:
            async for msg in self.ws:
                if msg.type != aiohttp.WSMsgType.TEXT:
                    continue
                data = json.loads(msg.data)
                t = data.get("type")
                if t == "transcript":
                    d = data.get("data") or {}
                    u = d.get("utterance") or {}
                    text = (u.get("text") or "").strip()
                    if u.get("language"):
                        self.lang = u["language"]
                    if d.get("is_final"):
                        if text:
                            self.finals.append({"text": text, "language": u.get("language"), "start": u.get("start"),
                                                "end": u.get("end")})
                        self.partial = ""
                        self._last_final_at = time.perf_counter()
                    else:
                        self.partial = text
                elif t == "speech_start":
                    self.in_speech = True
                elif t == "speech_end":
                    self.in_speech = False
                elif t == "stop_recording":
                    self._stop_acked_at = time.perf_counter()
                elif t == "error":
                    log.warning("%s gladia error: %s", self.tag, str(data)[:300])
                if self.on_message:
                    try:
                        self.on_message(data)
                    except Exception:
                        log.exception("on_message")
                if t in ("post_final_transcript", "end_session"):
                    break
        except Exception as e:
            log.debug("%s gladia recv ended: %s", self.tag, e)
        finally:
            self._closed.set()

    def text(self) -> str:
        parts = [f["text"] for f in self.finals]
        if self.partial:
            parts.append(self.partial)
        return re.sub(r"\s+", " ", " ".join(parts)).strip()

    async def finish(self, settle_s: float = 0.25, timeout_s: float = 1.6) -> str:
        """Stop recording and wait for the last final. Returns finals (+ last partial if the final never came)."""
        self._q.put_nowait(b"\x00\x00" * int(SR * settle_s))   # a little silence closes the last utterance
        self._q.put_nowait(None)
        t0 = time.perf_counter()
        n0 = len(self.finals)
        deadline = t0 + timeout_s
        # Done when: a final arrived after stop and nothing is pending; or Gladia acked the stop while no speech
        # was open (the speaker had already gone quiet); or the socket closed; or timeout.
        while time.perf_counter() < deadline and not self._closed.is_set():
            if self.failed:
                break
            now = time.perf_counter()
            if len(self.finals) > n0 and not self.partial and not self.in_speech and now - self._last_final_at > 0.05:
                break
            if self._stop_acked_at and not self.in_speech and not self.partial and now - self._stop_acked_at > 0.15:
                break
            if not self._ready.is_set() and time.perf_counter() - t0 > 1.0:
                break
            await asyncio.sleep(0.02)
        txt = self.text()
        asyncio.create_task(self.close())
        return txt

    async def close(self) -> None:
        self._closed.set()
        try:
            await asyncio.wait_for(asyncio.shield(asyncio.gather(*self._tasks, return_exceptions=True)), 3)
        except Exception:
            pass
        if self.ws and not self.ws.closed:
            await self.ws.close()
