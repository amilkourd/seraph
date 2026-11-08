"""ElevenLabs streaming TTS → raw PCM16 mono at 24 kHz, with a cache for fixed phrases (pre-generated at startup)."""
from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from pathlib import Path
from typing import AsyncIterator, Optional

import aiohttp

from . import config

log = logging.getLogger("gabriel.tts")

CACHE_DIR = Path(__file__).resolve().parents[1] / ".cache" / "tts"
VOICE = config.TTS_VOICE or "rgFgMEXfdGwXCYio7I0J"   # Olivier D, calm French male; flash v2.5 speaks en/es with it too
SR = config.TTS_SAMPLE_RATE
CHUNK = SR // 50 * 2                                   # 20 ms of PCM16 mono

# Fixed phrases, said often: generated once at startup, served from disk after that.
FIXED = {
    "fr": ["Reçu.", "Je transmets.", "Restez en ligne.", "Restez en ligne, je transmets aux pompiers.",
           "Exercice. Bonjour, ici Gabriel, l'assistant vocal des pompiers.",
           "Exercice. Bonjour, ici Gabriel, l'assistant vocal des pompiers. Où êtes-vous en ce moment ?"],
    "en": ["Stay on the line.", "Stay on the line, I'm passing this to the firefighters.",
           "Exercise. Hello, this is Gabriel, the fire service's voice assistant.",
           "Exercise. Hello, this is Gabriel, the fire service's voice assistant. Where are you right now?"],
    "es": ["Quédese en línea.", "Quédese en línea, estoy transmitiendo su situación a los bomberos.",
           "Ejercicio. Hola, soy Gabriel, el asistente de voz de los bomberos.",
           "Ejercicio. Hola, soy Gabriel, el asistente de voz de los bomberos. ¿Dónde está ahora mismo?"],
}


def _key(text: str, lang: str) -> Path:
    h = hashlib.sha1(f"{VOICE}|{config.TTS_MODEL}|{lang}|{text}".encode()).hexdigest()[:16]
    return CACHE_DIR / f"{h}.pcm"


class TTS:
    def __init__(self, session: Optional[aiohttp.ClientSession] = None) -> None:
        self._session = session
        self._own = session is None

    async def __aenter__(self) -> "TTS":
        if self._session is None:
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20, sock_connect=4))
        return self

    async def __aexit__(self, *exc) -> None:
        if self._own and self._session:
            await self._session.close()

    def cached(self, text: str, lang: str) -> Optional[bytes]:
        p = _key(text, lang)
        return p.read_bytes() if p.exists() else None

    async def stream(self, text: str, lang: str = "fr") -> AsyncIterator[bytes]:
        """PCM16 chunks as they arrive. Cached phrases come from disk."""
        data = self.cached(text, lang)
        if data is not None:
            for i in range(0, len(data), CHUNK):
                yield data[i:i + CHUNK]
            return
        assert self._session is not None
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE}/stream?output_format=pcm_{SR}"
        body = {"text": text, "model_id": config.TTS_MODEL, "language_code": lang if lang in ("fr", "en", "es") else None,
                "voice_settings": {"stability": 0.6, "similarity_boost": 0.8, "speed": 1.08}}
        body = {k: v for k, v in body.items() if v is not None}
        t0 = time.perf_counter()
        first = True
        buf = b""
        async with self._session.post(url, json=body, headers={"xi-api-key": config.TTS_API_KEY}) as r:
            if r.status != 200:
                raise RuntimeError(f"elevenlabs {r.status}: {(await r.text())[:200]}")
            async for part in r.content.iter_any():
                if first:
                    log.info("tts first byte %.0f ms (%s)", (time.perf_counter() - t0) * 1000, text[:40])
                    first = False
                buf += part
                n = len(buf) - len(buf) % 2
                if n:
                    yield buf[:n]
                    buf = buf[n:]

    async def full(self, text: str, lang: str = "fr") -> bytes:
        out = bytearray()
        async for c in self.stream(text, lang):
            out += c
        return bytes(out)

    async def warm(self, phrases: Optional[dict[str, list[str]]] = None) -> None:
        """Pre-generate fixed phrases (default FIXED; skips the ones already on disk)."""
        phrases = phrases or FIXED
        CACHE_DIR.mkdir(parents=True, exist_ok=True)

        async def one(text: str, lang: str) -> None:
            p = _key(text, lang)
            if p.exists():
                return
            try:
                p.write_bytes(await self.full(text, lang))
            except Exception as e:
                log.warning("tts warm failed for %r: %s", text, e)

        sem = asyncio.Semaphore(6)

        async def limited(text: str, lang: str) -> None:
            async with sem:
                await one(text, lang)

        await asyncio.gather(*(limited(t, l) for l, lines in phrases.items() for t in lines))


async def _selftest() -> None:
    logging.basicConfig(level=logging.INFO)
    async with TTS() as t:
        t0 = time.perf_counter()
        pcm = await t.full("Tête de Seraph : entrée conseillée E2, côté rue. Escalier A dégagé.", "fr")
        print(f"full {len(pcm) / 2 / SR:.1f}s audio in {(time.perf_counter() - t0) * 1000:.0f} ms")
        t0 = time.perf_counter()
        await t.warm()
        print(f"warm {(time.perf_counter() - t0) * 1000:.0f} ms, {len(list(CACHE_DIR.glob('*.pcm')))} cached")


if __name__ == "__main__":
    asyncio.run(_selftest())
