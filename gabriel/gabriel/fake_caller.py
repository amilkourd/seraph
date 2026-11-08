"""Scripted web caller for testing call agents without a phone. Uses the talkie's /api/call-token like /call does,
then speaks lines (ElevenLabs, a different voice) when Gabriel stops talking.
`uv run python -m gabriel.fake_caller OCC-T01 fr "Allô ? Je suis au deuxième, appartement 2.01." "Il y a de la fumée."`
Use a test occupant id (OCC-T…) so test calls never overwrite the demo occupants in Seraph's state; `-` = inbound 112.
"""
from __future__ import annotations

import asyncio
import sys
import time

import aiohttp
import numpy as np
from livekit import rtc

from . import config, tts as tts_mod

CALLER_VOICE = {"fr": "YwEKgPNrswweXodAZi29", "en": "EXAVITQu4vr4xnSDxMaL", "es": "JBFqnCBsd6RMkjVDRZzb"}


async def run(occ: str | None, lang: str, lines: list[str], hold_s: float = 8.0, tag: str = "") -> None:
    talkie = config.env("TALKIE_URL", "http://localhost:3000")
    async with aiohttp.ClientSession() as http:
        t0 = time.perf_counter()
        async with http.post(f"{talkie}/api/call-token", json={"occ": occ, "lang": lang}) as r:
            tok = await r.json()
        call_id = tok["callId"]
        room = rtc.Room()
        st = {"agent_last_loud": 0.0, "agent_started": 0.0, "agent_in": False, "greet_at": 0.0}

        async def listen(track: rtc.Track) -> None:
            async for ev in rtc.AudioStream.from_track(track=track, sample_rate=24000, num_channels=1):
                if np.abs(np.frombuffer(ev.frame.data, dtype=np.int16)).max() > 400:
                    now = time.perf_counter()
                    if not st["greet_at"]:
                        st["greet_at"] = now
                        print(f"{tag}{call_id}: Gabriel's voice {(now - t0) * 1000:.0f} ms after token request")
                    st["agent_last_loud"] = now

        room.on("track_subscribed", lambda t, pub, p: t.kind == rtc.TrackKind.KIND_AUDIO and asyncio.create_task(listen(t)))
        await room.connect(tok["url"], tok["token"])
        src = rtc.AudioSource(tts_mod.SR, 1, queue_size_ms=60)   # small queue: « stopped » means the audio left
        await room.local_participant.publish_track(rtc.LocalAudioTrack.create_audio_track("mic", src),
                                                   rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE))
        silence = b"\0\0" * (tts_mod.SR // 50)
        q: asyncio.Queue[bytes] = asyncio.Queue()

        async def mic() -> None:   # one writer: queued speech, else silence (a phone mic always sends something)
            while True:
                c = q.get_nowait() if not q.empty() else silence
                await src.capture_frame(rtc.AudioFrame(c, tts_mod.SR, 1, len(c) // 2))

        bg = asyncio.create_task(mic())
        t = tts_mod.TTS(http)
        tts_mod.VOICE = CALLER_VOICE.get(lang, CALLER_VOICE["fr"])
        audio = [await t.full(line, lang) for line in lines]

        async def wait_agent_quiet(q: float = 0.9, timeout: float = 20) -> None:
            end = time.perf_counter() + timeout
            while time.perf_counter() < end:
                if st["greet_at"] and time.perf_counter() - st["agent_last_loud"] > q:
                    return
                await asyncio.sleep(0.05)

        for line, pcm in zip(lines, audio):
            await wait_agent_quiet()
            print(f"{tag}{call_id} caller: {line}")
            step = tts_mod.SR // 50 * 2
            for i in range(0, len(pcm) - len(pcm) % 2, step):
                q.put_nowait(pcm[i:i + step])
            while not q.empty():
                await asyncio.sleep(0.02)
            rel = time.perf_counter()
            print(f"{tag}{call_id}   caller stopped at {time.strftime('%H:%M:%S')}.{int(time.time() * 1000) % 1000:03d}")
            st["agent_last_loud"] = 0.0
            while time.perf_counter() - rel < 10 and st["agent_last_loud"] < rel:
                await asyncio.sleep(0.02)
            if st["agent_last_loud"] >= rel:
                print(f"{tag}{call_id}   Gabriel answers {(st['agent_last_loud'] - rel) * 1000:.0f} ms after caller stops")
        await wait_agent_quiet()
        await asyncio.sleep(hold_s)
        bg.cancel()
        await room.disconnect()
        print(f"{tag}{call_id}: hung up")


if __name__ == "__main__":
    a = sys.argv[1:]
    occ = None if a[0] in ("-", "112") else a[0]
    asyncio.run(run(occ, a[1], a[2:]))
