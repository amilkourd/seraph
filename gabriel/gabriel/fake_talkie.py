"""Scripted crew member for testing the radio loop without a phone: joins `crew`, says a line (TTS), sends eot
like the talkie, and measures release → first Seraph audio.  `uv run python -m gabriel.fake_talkie "Seraph de Tête, quelle entrée ?"`"""
from __future__ import annotations

import asyncio
import json
import sys
import time

import aiohttp
import numpy as np
from livekit import api, rtc

from . import config
from .tts import TTS, SR


async def run(lines: list[str], identity: str = "Tête") -> None:
    grants = api.VideoGrants(room_join=True, room="crew", can_publish=True, can_subscribe=True, can_publish_data=True,
                             can_update_own_metadata=True)
    tok = api.AccessToken(config.LIVEKIT_API_KEY, config.LIVEKIT_API_SECRET).with_identity(identity).with_grants(grants).to_jwt()
    room = rtc.Room()
    heard = asyncio.Event()
    state = {"release": 0.0, "seraph_talking_at": 0.0}

    async def listen(track: rtc.Track) -> None:
        async for ev in rtc.AudioStream.from_track(track=track, sample_rate=24000, num_channels=1):
            a = np.frombuffer(ev.frame.data, dtype=np.int16)
            if state["release"] and not heard.is_set() and np.abs(a).max() > 300:
                print(f"  first Seraph audio {(time.perf_counter() - state['release']) * 1000:.0f} ms after release")
                heard.set()

    def on_attr(changed: dict, p: rtc.Participant) -> None:
        if p.identity == "Seraph" and "talking" in changed:
            if changed["talking"] == "true" and state["release"]:
                print(f"  Seraph talking=true {(time.perf_counter() - state['release']) * 1000:.0f} ms after release")
            elif changed["talking"] == "false":
                print("  Seraph talking=false")

    room.on("track_subscribed", lambda t, pub, p: t.kind == rtc.TrackKind.KIND_AUDIO and asyncio.create_task(listen(t)))
    room.on("participant_attributes_changed", on_attr)
    room.on("data_received", lambda pkt: pkt.topic == "seraph" and print("  topic seraph:", pkt.data.decode()[:160]))
    await room.connect(config.LIVEKIT_URL, tok)
    src = rtc.AudioSource(SR, 1)
    await room.local_participant.publish_track(rtc.LocalAudioTrack.create_audio_track("mic", src),
                                               rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE))
    async with aiohttp.ClientSession() as http:
        tts = TTS(http)
        for line in lines:
            pcm = await tts.full(line, "fr")
            await asyncio.sleep(1.0)
            heard.clear()
            state["release"] = 0.0
            print(f"{identity}: {line}")
            await room.local_participant.set_attributes({"talking": "true", "talking_since": str(int(time.time() * 1000))})
            step = SR // 50 * 2
            for i in range(0, len(pcm) - len(pcm) % 2, step):
                c = pcm[i:i + step]
                await src.capture_frame(rtc.AudioFrame(c, SR, 1, len(c) // 2))
            await src.wait_for_playout()
            state["release"] = time.perf_counter()
            await room.local_participant.set_attributes({"talking": "false"})
            await room.local_participant.publish_data(json.dumps({"kind": "eot", "speaker": identity}), reliable=True, topic="ptt")
            try:
                await asyncio.wait_for(heard.wait(), 8)
            except asyncio.TimeoutError:
                print("  no Seraph audio within 8 s")
            await asyncio.sleep(6)
    await room.disconnect()


if __name__ == "__main__":
    args = sys.argv[1:] or ["Seraph de Tête, on est à deux minutes, quelle entrée ?"]
    asyncio.run(run(args))
