"""Gabriel's radio agent on LiveKit room `crew`, identity `Seraph` (docs/06-gabriel.md).

Listen: one Gladia live session per push-to-talk turn per speaker, from `talking=true` to the talkie's eot (topic
`ptt`), then `radio_transcript` → Seraph. Only remote tracks are subscribed: Gabriel never hears its own TTS.
Speak: Seraph's `say` for `{room:"crew"}` → queue (alerts first) → wait for a free floor → `talking=true` →
ElevenLabs PCM → `talking=false`. The spoken text also goes out on data topic `seraph`.

Run: `uv run gabriel-radio` (standalone process, so calls never block the radio).
"""
from __future__ import annotations

import asyncio
import collections
import json
import logging
import os
import signal
import subprocess
import tempfile
import time
import wave
from dataclasses import dataclass, field
from typing import Optional

import aiohttp
from livekit import api, rtc

from . import config, gladia_live
from .seraph_link import SeraphLink, now_iso
from .tts import TTS

log = logging.getLogger("gabriel.radio")

SR_IN = gladia_live.SR          # 16 kHz to Gladia
SR_OUT = config.TTS_SAMPLE_RATE  # 24 kHz from ElevenLabs
PREROLL_S = 0.6                  # audio kept before `talking=true` (the talkie unmutes before setting it)
EOT_GRACE_S = 1.2                # talking=false and no eot after this → cut anyway
LOCAL_SPEAKER = config.env("GABRIEL_LOCAL_SPEAKER", "0") == "1"   # fallback: also play crew says on the laptop


def token() -> str:
    grants = api.VideoGrants(room_join=True, room=config.RADIO_ROOM, can_publish=True, can_subscribe=True,
                             can_publish_data=True, can_update_own_metadata=True)
    return (api.AccessToken(config.LIVEKIT_API_KEY, config.LIVEKIT_API_SECRET)
            .with_identity(config.RADIO_IDENTITY).with_name("Seraph").with_grants(grants)
            .with_attributes({"talking": "false", "role": "gabriel-radio"})
            .to_jwt())


@dataclass
class Turn:
    utterance_id: str
    speaker: str
    started: str
    session: gladia_live.LiveSession
    t0: float = field(default_factory=time.perf_counter)
    cut_timer: Optional[asyncio.TimerHandle] = None
    ending: bool = False


class Radio:
    def __init__(self) -> None:
        self.room = rtc.Room()
        self.http: Optional[aiohttp.ClientSession] = None
        self.tts: Optional[TTS] = None
        self.link = SeraphLink(self.on_seraph, name="radio")
        self.preroll: dict[str, collections.deque] = {}
        self.turns: dict[str, Turn] = {}
        self.streams: dict[str, asyncio.Task] = {}
        self.n = 0
        self.say_q: list[tuple[int, float, dict]] = []
        self.say_ev = asyncio.Event()
        self.source = rtc.AudioSource(SR_OUT, 1, queue_size_ms=400)
        self.speaking = False
        self.last_eot: Optional[float] = None

    # ───────── floor ─────────
    def floor_holder(self) -> Optional[str]:
        for p in self.room.remote_participants.values():
            if p.attributes.get("talking") == "true":
                return p.identity
        return None

    # ───────── listening ─────────
    def on_track_subscribed(self, track: rtc.Track, pub: rtc.RemoteTrackPublication, p: rtc.RemoteParticipant) -> None:
        if track.kind != rtc.TrackKind.KIND_AUDIO:
            return
        old = self.streams.pop(p.identity, None)
        if old:
            old.cancel()
        self.streams[p.identity] = asyncio.create_task(self.pump(track, p.identity))
        log.info("listening to %s", p.identity)

    async def pump(self, track: rtc.Track, who: str) -> None:
        stream = rtc.AudioStream.from_track(track=track, sample_rate=SR_IN, num_channels=1)
        pre = self.preroll.setdefault(who, collections.deque())
        try:
            async for ev in stream:
                pcm = bytes(ev.frame.data)
                turn = self.turns.get(who)
                if turn and not turn.ending:
                    turn.session.send(pcm)
                else:
                    now = time.perf_counter()
                    pre.append((now, pcm))
                    while pre and now - pre[0][0] > PREROLL_S:
                        pre.popleft()
        except asyncio.CancelledError:
            pass
        finally:
            await stream.aclose()

    def on_attrs(self, changed: dict, p: rtc.Participant) -> None:
        if p.identity == config.RADIO_IDENTITY or "talking" not in changed:
            return
        if changed["talking"] == "true":
            self.begin(p.identity)
        else:
            t = self.turns.get(p.identity)
            if t and not t.ending and not t.cut_timer:
                t.cut_timer = asyncio.get_running_loop().call_later(
                    EOT_GRACE_S, lambda: asyncio.create_task(self.end(p.identity, "no eot")))
        self.say_ev.set()   # floor may be free now

    def begin(self, who: str) -> None:
        if who in self.turns:
            return
        assert self.http is not None
        self.n += 1
        uid = f"utt_{int(time.time())}_{self.n:03d}"
        s = gladia_live.LiveSession(self.http, gladia_live.session_config(sentiment=False, endpointing=0.3), tag=uid)
        turn = Turn(utterance_id=uid, speaker=who, started=now_iso(), session=s)
        self.turns[who] = turn
        asyncio.create_task(s.start())
        for _, pcm in self.preroll.get(who, ()):
            s.send(pcm)
        self.preroll.get(who, collections.deque()).clear()
        log.info("%s on air (%s)", who, uid)

    def on_data(self, pkt: rtc.DataPacket) -> None:
        if pkt.topic != "ptt":
            return
        try:
            msg = json.loads(pkt.data.decode("utf-8"))
        except Exception:
            return
        if msg.get("kind") != "eot":
            return
        who = pkt.participant.identity if pkt.participant else msg.get("speaker", "")
        asyncio.create_task(self.end(who, "eot", speaker_label=msg.get("speaker")))

    async def end(self, who: str, why: str, speaker_label: Optional[str] = None) -> None:
        t = self.turns.get(who)
        if not t or t.ending:
            return
        t.ending = True
        if t.cut_timer:
            t.cut_timer.cancel()
        t_eot = time.perf_counter()
        self.last_eot = t_eot
        text = await t.session.finish()
        self.turns.pop(who, None)
        took = (time.perf_counter() - t_eot) * 1000
        if not text:
            log.info("%s: nothing heard (%s, %s)", who, why, t.session.failed or "silence")
            return
        lang = (t.session.lang or "fr")[:2]
        msg = {"kind": "radio_transcript", "utterance_id": t.utterance_id, "room": "crew",
               "speaker": speaker_label or who, "lang": lang if lang in ("fr", "en", "es", "ar") else "other",
               "text": text, "start": t.started, "end": now_iso()}
        self.link.send(msg)
        self.link.metric("eot_to_transcript", took, utterance_id=t.utterance_id, cut=why)
        log.info("→ Seraph [%s %s, %.0f ms after %s] %s", msg["speaker"], lang, took, why, text)

    def on_participant_disconnected(self, p: rtc.RemoteParticipant) -> None:
        task = self.streams.pop(p.identity, None)
        if task:
            task.cancel()
        if p.identity in self.turns:
            asyncio.create_task(self.end(p.identity, "left"))
        self.say_ev.set()

    # ───────── speaking ─────────
    def on_seraph(self, msg: dict) -> None:
        if msg.get("kind") != "say" or msg.get("target", {}).get("room") != "crew":
            return
        prio = 0 if msg.get("priority") == "alert" else 1
        self.say_q.append((prio, time.perf_counter(), msg))
        self.say_q.sort(key=lambda x: (x[0], x[1]))
        self.say_ev.set()
        log.info("say queued (%s): %s", msg.get("priority"), msg.get("text"))

    async def speak_loop(self) -> None:
        while True:
            if not self.say_q:
                self.say_ev.clear()
                await self.say_ev.wait()
                continue
            # Wait for a free floor: nobody holds `talking=true` and no turn still being transcribed.
            if self.floor_holder() or any(not t.ending for t in self.turns.values()) \
                    or self.room.connection_state != rtc.ConnectionState.CONN_CONNECTED:
                self.say_ev.clear()
                try:
                    await asyncio.wait_for(self.say_ev.wait(), 0.5)
                except asyncio.TimeoutError:
                    pass
                continue
            _, queued_at, msg = self.say_q.pop(0)
            try:
                await self.speak(msg, queued_at)
            except Exception as e:
                log.exception("speak failed: %s", e)
                await self.set_talking(False)

    async def set_talking(self, on: bool) -> None:
        attrs = {"talking": "true" if on else "false"}
        if on:
            attrs["talking_since"] = str(int(time.time() * 1000))
        try:
            await asyncio.wait_for(self.room.local_participant.set_attributes(attrs), 2)
        except Exception as e:
            log.warning("set_attributes %s: %s", attrs, e)

    async def speak(self, msg: dict, queued_at: float) -> None:
        assert self.tts is not None
        text, lang = msg["text"], msg.get("lang", "fr")
        self.speaking = True
        t_start = time.perf_counter()
        attr = asyncio.create_task(self.set_talking(True))
        gen = self.tts.stream(text, lang)
        first: Optional[bytes] = None
        try:
            first = await asyncio.wait_for(gen.__anext__(), 4)
        except (StopAsyncIteration, asyncio.TimeoutError) as e:
            log.warning("tts gave nothing for %r (%s)", text, type(e).__name__)
        await attr
        # Collision: someone pressed in the same instant with an earlier talking_since → yield, retry later.
        mine = int(self.room.local_participant.attributes.get("talking_since", "0") or 0)
        for p in self.room.remote_participants.values():
            if p.attributes.get("talking") == "true" and int(p.attributes.get("talking_since", "0") or 0) <= mine:
                log.info("floor lost to %s, requeue", p.identity)
                await self.set_talking(False)
                self.say_q.insert(0, (0 if msg.get("priority") == "alert" else 1, queued_at, msg))
                self.speaking = False
                return
        asyncio.create_task(self.room.local_participant.publish_data(
            json.dumps({"kind": "say", "say_id": msg.get("say_id"), "text": text, "lang": lang}, ensure_ascii=False),
            reliable=True, topic="seraph"))
        pcm_all = bytearray()
        await self.push(b"\x00\x00" * int(SR_OUT * 0.12))    # lead-in so the phones open squelch before the words
        t_audio = time.perf_counter()
        self.link.metric("say_to_audio", (t_audio - queued_at) * 1000, say_id=msg.get("say_id"),
                         wait_ms=round((t_start - queued_at) * 1000, 1))
        if self.last_eot and t_audio - self.last_eot < 8:
            self.link.metric("release_to_audio", (t_audio - self.last_eot) * 1000, say_id=msg.get("say_id"))
            log.info("release → Seraph audio: %.0f ms", (t_audio - self.last_eot) * 1000)
            self.last_eot = None
        if first:
            pcm_all += first
            await self.push(first)
            async for chunk in gen:
                pcm_all += chunk
                await self.push(chunk)
        await self.source.wait_for_playout()
        await self.set_talking(False)
        self.speaking = False
        log.info("spoke: %s", text)
        if LOCAL_SPEAKER and pcm_all:
            play_local(bytes(pcm_all))

    async def push(self, pcm: bytes) -> None:
        step = SR_OUT // 50 * 2   # 20 ms frames
        for i in range(0, len(pcm) - len(pcm) % 2, step):
            chunk = pcm[i:i + step]
            await self.source.capture_frame(rtc.AudioFrame(chunk, SR_OUT, 1, len(chunk) // 2))

    # ───────── lifecycle ─────────
    async def run(self) -> None:
        self.http = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20, sock_connect=4))
        self.tts = TTS(self.http)
        asyncio.create_task(self.tts.warm())
        self.link.start()
        r = self.room
        r.on("track_subscribed", self.on_track_subscribed)
        r.on("participant_attributes_changed", self.on_attrs)
        r.on("data_received", self.on_data)
        r.on("participant_disconnected", self.on_participant_disconnected)
        r.on("reconnecting", lambda: log.warning("LiveKit reconnecting"))
        r.on("reconnected", lambda: log.info("LiveKit reconnected"))
        await r.connect(config.LIVEKIT_URL, token(), rtc.RoomOptions(auto_subscribe=True))
        log.info("joined %s as %s (%d others)", config.RADIO_ROOM, config.RADIO_IDENTITY, len(r.remote_participants))
        track = rtc.LocalAudioTrack.create_audio_track("seraph-voice", self.source)
        await r.local_participant.publish_track(track, rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE))
        await self.set_talking(False)
        await self.speak_loop()


def play_local(pcm: bytes) -> None:
    """Laptop-speaker fallback (afplay on macOS)."""
    fd, path = tempfile.mkstemp(suffix=".wav")
    with os.fdopen(fd, "wb") as f, wave.open(f, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR_OUT)
        w.writeframes(pcm)
    subprocess.Popen(["afplay", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


async def amain() -> None:
    radio = Radio()
    loop = asyncio.get_running_loop()
    stop = asyncio.Event()
    for s in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(s, stop.set)
    task = asyncio.create_task(radio.run())
    done, _ = await asyncio.wait({task, asyncio.create_task(stop.wait())}, return_when=asyncio.FIRST_COMPLETED)
    if task in done and task.exception():
        log.error("radio crashed: %r", task.exception())
    await radio.room.disconnect()
    if radio.http:
        await radio.http.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    logging.getLogger("livekit").setLevel(logging.WARNING)
    asyncio.run(amain())


if __name__ == "__main__":
    main()
