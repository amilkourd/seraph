"""Gabriel's call agents: one LiveKit Agents job per call (room `call-<id>`, agent name `gabriel-call`), each in its
own process so calls never block each other or the radio (docs/06-gabriel.md « Call agents »).

- First sentence, in the caller's language: « Exercice. Bonjour, ici Gabriel, l'assistant vocal des pompiers. »
- After every caller turn, `report_facts` (a forced tool call on the LLM over the conversation) extracts the facts
  → `call_facts` to Seraph. Code then picks what to say from a fixed list: « je transmets » + the next question not
  yet answered (where, how many, smoke, injured, what are you doing), or « je transmets votre question aux pompiers,
  restez en ligne » when the caller asks what to do. No model ever writes what the caller hears on its own, so it can
  never give an instruction or promise help; the phrases are pre-generated (fast) in fr/en/es.
- Gladia live emotion analysis on the caller → `facts.voice` (the plugin is extended with sentiment, see below).
- Seraph's `say` for this call (gated orders, the confirmed standing instruction) interrupts and is spoken as is,
  translated faithfully when `translate:true`.

Run: `uv run gabriel-calls dev` (hot reload) or `uv run gabriel-calls start`. Web calls arrive by explicit dispatch
from the talkie's `/api/call-token` with metadata `{call_id, occupant_id, direction, channel, lang}`.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import Any, AsyncIterable, Optional

import aiohttp
from livekit import rtc
from livekit.agents import Agent, AgentServer, AgentSession, JobContext, JobProcess, cli, room_io
from livekit.plugins import gladia, silero
from livekit.plugins.gladia import stt as gladia_stt
from openai import AsyncOpenAI

from . import config, gladia_live
from .seraph_link import SeraphLink, mask, now_iso
from .tts import SR as TTS_SR, TTS

log = logging.getLogger("gabriel.calls")

LANGS = ("fr", "en", "es")
GREETING = {
    "fr": "Exercice. Bonjour, ici Gabriel, l'assistant vocal des pompiers. Où êtes-vous en ce moment ?",
    "en": "Exercise. Hello, this is Gabriel, the fire service's voice assistant. Where are you right now?",
    "es": "Ejercicio. Hola, soy Gabriel, el asistente de voz de los bomberos. ¿Dónde está ahora mismo?",
}
# The only things the agent says on its own (docs/07-safety-rules.md rule 1): questions, « je transmets », « restez en ligne ».
PHRASES = {
    "fr": {"where": "Où êtes-vous en ce moment ?", "people": "Combien de personnes êtes-vous ?",
           "smoke": "Y a-t-il de la fumée ou de la chaleur près de vous ?",
           "hurt": "Quelqu'un est-il blessé, ou ne peut pas marcher ?", "action": "Que faites-vous en ce moment ?",
           "ack": "Je transmets.", "done": "Je transmets aux pompiers. Restez en ligne.",
           "asked": "Je transmets votre question aux pompiers. Restez en ligne.", "hold": "Restez en ligne."},
    "en": {"where": "Where are you right now?", "people": "How many people are with you, including you?",
           "smoke": "Is there any smoke or heat near you?", "hurt": "Is anyone hurt, or unable to walk?",
           "action": "What are you doing right now?", "ack": "Got it, I'm passing it on.",
           "done": "I'm passing this to the firefighters. Stay on the line.",
           "asked": "I'm passing your question to the firefighters. Stay on the line.", "hold": "Stay on the line."},
    "es": {"where": "¿Dónde está ahora mismo?", "people": "¿Cuántas personas son, contándose usted?",
           "smoke": "¿Hay humo o calor cerca de usted?", "hurt": "¿Hay alguien herido, o que no pueda caminar?",
           "action": "¿Qué está haciendo ahora mismo?", "ack": "Lo transmito.",
           "done": "Lo transmito a los bomberos. Quédese en línea.",
           "asked": "Transmito su pregunta a los bomberos. Quédese en línea.", "hold": "Quédese en línea."},
}
QUESTIONS = ("where", "people", "smoke", "hurt", "action")
FOLLOW = {  # said after the immediate « je transmets »
    "fr": {"asked": "Et votre question aussi. Restez en ligne."},
    "en": {"asked": "And your question too. Stay on the line."},
    "es": {"asked": "Y su pregunta también. Quédese en línea."},
}

EXTRACT = """You fill the report_facts form for firefighters from a phone call during a fire EXERCISE.
Use only what the CALLER says (any language). Set a field when the caller states it or clearly implies it; null otherwise.
Never set a boolean to false unless the caller says so.
- level: the floor where the CALLER is, never where the fire is (« the fire on the third floor » → null). « deuxième / 2e » = 2, « fourth floor » = 4,
  « quinto piso » = 5, ground floor / RDC / planta baja = 0. Caller outside the building → null.
- room: only a room id like "3.12" (level, dot, two digits) if said (« salle 3.12 » → "3.12", « bureau 2.01 » → "2.01");
  « au deuxième » alone is level 2, not a room. A number close to a valid id (« 2.1 », « deux zéro trois » → 2.01, 2.03)
  → pick that id with room_sure false: the agent will read it back to the caller.
- people_count: people together including the caller (« avec un collègue » = 2, « seul(e) » / « I'm alone » = 1,
  a single person speaking only about themself = 1).
- smoke_seen: true if they see smoke near them, false if they say no smoke (« no veo humo » = false).
- mobility_issue: true for wheelchair / cannot walk / cannot go down alone.
- injuries: in French, « aucun » if they say nobody is hurt.
- current_action: staying (in a room, waiting, « on n'ose pas sortir »), moving (heading somewhere, going down),
  outside (out of the building), unknown.
- heading_to: south stairs = "stair:B", north stairs = "stair:A".
- asks_what_to_do: true if the caller's LAST turn asks what to do or for instructions.
- free_text_fr: other useful facts, French, one short line.
- confidence: 0-1."""


def all_phrases() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for lang, p in PHRASES.items():
        lines = [GREETING[lang], p["done"], p["asked"], p["hold"], p["ack"], FOLLOW[lang]["asked"]]
        for q in QUESTIONS:
            lines += [p[q], f"{p['ack']} {p[q]}"]
        out[lang] = lines
    return out


REPORT_FACTS = {
    "type": "function",
    "function": {
        "name": "report_facts",
        "description": "Send what the caller said so far to the firefighters (Seraph). Only what the caller said.",
        "parameters": {
            "type": "object",
            "properties": {
                "level": {"type": ["integer", "null"], "description": "floor: 0 = ground floor (RDC), 3 = 3rd"},
                "room": {"type": ["string", "null"], "description": "room id as said, e.g. 3.12, 2.01"},
                "people_count": {"type": ["integer", "null"],
                                 "description": "people with the caller, caller included (« avec un collègue » = 2, « seul » = 1)"},
                "smoke_seen": {"type": ["boolean", "null"]},
                "fire_seen": {"type": ["boolean", "null"]},
                "heat": {"type": ["boolean", "null"]},
                "mobility_issue": {"type": ["boolean", "null"], "description": "someone cannot walk or go down alone"},
                "injuries": {"type": ["string", "null"], "description": "in French; « aucun » when the caller says nobody is hurt"},
                "current_action": {"type": ["string", "null"], "enum": ["staying", "moving", "outside", "unknown", None]},
                "heading_to": {"type": ["string", "null"],
                               "description": "stair:A, stair:B, exit:E1, exit:E2… south stairs = stair:B, north stairs = stair:A"},
                "free_text_fr": {"type": ["string", "null"], "description": "anything else useful, in French, one short line"},
                "asks_what_to_do": {"type": "boolean",
                                    "description": "the caller's LAST turn asks what to do / for instructions / for help"},
                "confidence": {"type": "number", "description": "0-1"},
            },
            "required": ["level", "room", "people_count", "smoke_seen", "fire_seen", "heat", "mobility_issue",
                         "injuries", "current_action", "heading_to", "free_text_fr", "asks_what_to_do", "confidence"],
            "additionalProperties": False,
        },
        "strict": True,
    },
}

NUM_ES = ["cero", "uno", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho", "nueve"]
CONFIRM_ROOM = {"fr": "Appartement {spoken}, c'est bien ça ?", "en": "Flat {spoken}, is that right?",
                "es": "Apartamento {spoken}, ¿es correcto?"}


def spoken_room(room: str, lang: str) -> str:
    """« 2.01 » said digit by digit in the caller's language (TTS reads ids badly)."""
    digits = [c for c in room if c.isdigit()]
    words = {"fr": gladia_live.NUM_FR, "en": gladia_live.NUM_EN, "es": NUM_ES}[lang]
    out = [words[int(d)] for d in digits]
    if lang == "en":
        out = ["oh" if w == "zero" and i > 0 else w for i, w in enumerate(out)]
    return " ".join(out)


def facts_tool(room_ids: list[str]) -> dict:
    """report_facts with `room` restricted to the building's ids (or null) and a `room_sure` flag."""
    tool = json.loads(json.dumps(REPORT_FACTS))
    props = tool["function"]["parameters"]["properties"]
    if room_ids:
        props["room"] = {"type": ["string", "null"], "enum": sorted(room_ids) + [None],
                         "description": "one of the building's room ids, only if the caller's words match it; else null"}
    props["room_sure"] = {"type": "boolean", "description": "true only if the caller said this room id clearly; "
                          "false if you picked the closest id from a partial or garbled number"}
    tool["function"]["parameters"]["required"].append("room_sure")
    return tool


VOICE_RAISE = {"distress", "fear", "pain"}

# ───────── Gladia sentiment: extend the plugin's live session (it does not expose it, docs/06-gabriel.md) ─────────
_SENTIMENT_HOOKS: list = []
_orig_build = gladia_stt._build_streaming_config
_orig_process = gladia_stt.SpeechStream._process_gladia_message


def _build_with_sentiment(opts: Any) -> dict:
    cfg = _orig_build(opts)
    cfg.setdefault("realtime_processing", {})["sentiment_analysis"] = True
    cfg.setdefault("messages_config", {})["receive_realtime_processing_events"] = True
    return cfg


def _process_with_sentiment(self: Any, data: dict) -> None:
    if data.get("type") == "sentiment_analysis":
        for cb in list(_SENTIMENT_HOOKS):
            try:
                cb(data)
            except Exception:
                log.exception("sentiment hook")
        return
    return _orig_process(self, data)


gladia_stt._build_streaming_config = _build_with_sentiment
gladia_stt.SpeechStream._process_gladia_message = _process_with_sentiment


# ───────── helpers ─────────
def known_rooms(extra: Optional[str] = None) -> set[str]:
    rooms: set[str] = {extra} if extra else set()
    for p in (config.ROOT / config.env("BUILDING_JSON", "ifc/out/building.json"), config.FIXTURES / "building.json"):
        try:
            b = json.loads(p.read_text(encoding="utf-8"))
            rooms |= {r["id"] for r in b.get("building", b).get("rooms", []) or [] if r.get("id")}
        except Exception:
            pass
    try:
        rooms |= {o["room"] for o in json.loads((config.FIXTURES / "occupants.json").read_text(encoding="utf-8"))
                  .get("occupants", []) if o.get("room")}
    except Exception:
        pass
    return rooms


def norm_room(room: Optional[str], rooms: set[str], listed: Optional[str] = None) -> Optional[str]:
    """Speech often drops a zero (« 2.01 » → "2.1"): pick the known room that fits, the listed one first."""
    if not room or room in rooms:
        return room
    m = re.fullmatch(r"(\d+)[.,](\d)", room.strip())
    if m:
        cands = [f"{m[1]}.0{m[2]}", f"{m[1]}.{m[2]}0"]
        for c in ([listed] if listed in cands else []) + cands:
            if c in rooms:
                return c
    return room


def norm_lang(code: Optional[str], default: str = "fr") -> str:
    c = (code or "").lower()[:2]
    return c if c in LANGS else default


async def occupant(occ_id: Optional[str]) -> dict:
    """Name, language, level, room, masked phone: Seraph's state first, the fixture second."""
    if not occ_id:
        return {}
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=1.5)) as s:
            async with s.get(f"{config.SERAPH_URL}/state") as r:
                st = await r.json()
        for o in st.get("occupants", []):
            if o.get("id") == occ_id:
                return o
    except Exception as e:
        log.info("seraph /state unavailable (%s), using fixture", type(e).__name__)
    try:
        fx = json.loads((config.FIXTURES / "occupants.json").read_text(encoding="utf-8"))
        for o in fx.get("occupants", []):
            if o.get("id") == occ_id:
                o = dict(o)
                o["phone_masked"] = mask(o.pop("phone_e164", ""))
                return o
    except Exception:
        pass
    return {}


class Call:
    def __init__(self, ctx: JobContext, meta: dict, http: aiohttp.ClientSession) -> None:
        self.ctx = ctx
        self.call_id: str = meta.get("call_id") or ctx.room.name.removeprefix("call-")
        self.occ_id: Optional[str] = meta.get("occupant_id")
        self.direction: str = meta.get("direction") or ("out" if self.occ_id else "in")
        self.channel: str = meta.get("channel") or "web"
        self.lang = norm_lang(meta.get("lang"))
        self.occ: dict = {}
        self.link = SeraphLink(self.on_seraph, name=f"call {self.call_id}")
        self.tts = TTS(http)
        self.session: Optional[AgentSession] = None
        self.lines: list[tuple[str, str]] = []           # (role, text)
        self.facts: dict = {}                            # what we know (cumulative)
        self.sent: dict = {}
        self.voice: Optional[dict] = None
        self.voice_sent_at = 0.0
        self.asked: dict[str, int] = {}
        self.pending: list[str] = []
        self.turn_timer: Optional[asyncio.TimerHandle] = None
        self.turn_task: Optional[asyncio.Task] = None
        self.last_final_at = 0.0
        self.done_said = False
        self.seraph_speaking = False
        self.oai = AsyncOpenAI(base_url=config.LLM_BASE_URL, api_key=config.LLM_API_KEY, timeout=4)
        self.ended = False
        self.room_list = gladia_live.rooms()
        self.rooms = {r["id"] for r in self.room_list} or known_rooms()
        self.tool = facts_tool(sorted(self.rooms))
        self.rooms_prompt = "Valid room ids (choose one or null, never another value): " + "; ".join(
            f"level {lv}: " + ", ".join(f"{r['id']} {r.get('use') or ''}".strip() for r in self.room_list if r.get("level") == lv)
            for lv in sorted({r.get("level") for r in self.room_list if r.get("level") is not None})) if self.room_list else ""
        self.confirm_room: Optional[str] = None       # a room to read back before sending it
        self.room_asked: set[str] = set()

    def number(self) -> str:
        return self.occ.get("phone_masked") or ("web" if self.channel == "web" else "••")

    def event(self, ev: str) -> None:
        self.link.send({"kind": "call_event", "call_id": self.call_id, "event": ev, "direction": self.direction,
                        "channel": self.channel, "occupant_id": self.occ_id, "number_masked": self.number(),
                        "lang": self.lang, "at": now_iso()})

    # ───── speaking ─────
    def audio(self, text: str, lang: str) -> AsyncIterable[rtc.AudioFrame]:
        """Cached PCM when the phrase is fixed, ElevenLabs stream otherwise; 20 ms frames at 24 kHz."""
        async def gen():
            step = TTS_SR // 50 * 2
            buf = b""
            async for chunk in self.tts.stream(text, lang):
                buf += chunk
                while len(buf) >= step:
                    yield rtc.AudioFrame(buf[:step], TTS_SR, 1, step // 2)
                    buf = buf[step:]
            if len(buf) >= 2:
                buf = buf[:len(buf) - len(buf) % 2]
                yield rtc.AudioFrame(buf, TTS_SR, 1, len(buf) // 2)
        return gen()

    def say(self, text: str, lang: Optional[str] = None, interruptible: bool = True) -> Any:
        assert self.session is not None
        lang = lang or self.lang
        self.lines.append(("gabriel", text))
        log.info("%s gabriel: %s", self.call_id, text)
        return self.session.say(text, audio=self.audio(text, lang), allow_interruptions=interruptible)

    # ───── Seraph → this call ─────
    def for_me(self, target: dict) -> bool:
        return target.get("call_id") == self.call_id or self.call_id in (target.get("call_ids") or [])

    async def on_seraph(self, msg: dict) -> None:
        kind = msg.get("kind")
        if kind == "end_call" and msg.get("call_id") == self.call_id:
            await self.end("seraph")
        if kind != "say" or not self.for_me(msg.get("target") or {}) or not self.session:
            return
        t0 = time.perf_counter()
        lang = norm_lang(msg.get("lang"), self.lang)
        text = msg.get("text") or ""
        if msg.get("translate") and lang != "fr":
            text = await self.translate(msg.get("text_fr") or text, lang)
        log.info("%s Seraph say (%s)", self.call_id, lang)
        self.seraph_speaking = True
        self.session.interrupt()
        handle = self.say(text, lang, interruptible=False)
        self.link.metric("call_say_queued", (time.perf_counter() - t0) * 1000, call_id=self.call_id,
                         say_id=msg.get("say_id"))
        try:
            await handle
        finally:
            self.seraph_speaking = False

    async def translate(self, text_fr: str, lang: str) -> str:
        try:
            r = await self.oai.chat.completions.create(
                model=config.LLM_MODEL, reasoning_effort="none", service_tier="priority",
                messages=[{"role": "system", "content": "Translate this firefighters' instruction from French to "
                           f"{ {'en': 'English', 'es': 'Spanish'}[lang] }. Faithful: add nothing, remove nothing, "
                           "no comment. Output only the translation."},
                          {"role": "user", "content": text_fr}])
            return (r.choices[0].message.content or "").strip() or text_fr
        except Exception as e:
            log.warning("%s translate failed (%s): saying French", self.call_id, type(e).__name__)
            return text_fr

    # ───── caller turns ─────
    def on_transcribed(self, ev: Any) -> None:
        if not ev.is_final or not (ev.transcript or "").strip():
            return
        log.debug("%s final: %s", self.call_id, ev.transcript)
        if ev.language:
            self.lang = norm_lang(str(ev.language), self.lang)
        self.pending.append(ev.transcript.strip())
        self.last_final_at = time.perf_counter()
        # A caller often says two sentences with a short pause: wait a moment for the next final.
        if self.turn_timer:
            self.turn_timer.cancel()
        self.turn_timer = asyncio.get_running_loop().call_later(0.2, self.kick_turn)

    def kick_turn(self) -> None:
        if self.turn_task and not self.turn_task.done():
            self.turn_timer = asyncio.get_running_loop().call_later(0.2, self.kick_turn)
            return
        text = " ".join(self.pending)
        self.pending = []
        if text:
            self.turn_task = asyncio.create_task(self.on_turn(text))

    async def on_turn(self, text: str) -> None:
        t0 = time.perf_counter()
        self.lines.append(("appelant", text))
        log.info("%s caller (%s): %s", self.call_id, self.lang, text)
        p = PHRASES[self.lang]
        # Something was said: acknowledge at once (cached audio) while report_facts runs.
        acked = len(text.split()) >= 3 and not self.seraph_speaking
        if acked:
            self.say(p["ack"])
            self.link.metric("call_ack", (time.perf_counter() - self.last_final_at) * 1000, call_id=self.call_id)
        facts = await self.report_facts()
        t1 = time.perf_counter()
        if self.seraph_speaking or self.ended or self.pending:   # Seraph has the line, or the caller kept talking
            return
        new = facts.pop("_new", False)
        if self.confirm_room:
            room, self.confirm_room = self.confirm_room, None
            self.room_asked.add(room)
            text = CONFIRM_ROOM[self.lang].format(spoken=spoken_room(room, self.lang))
            self.lines.append(("gabriel", CONFIRM_ROOM[self.lang].format(spoken=room)))
            log.info("%s gabriel: %s", self.call_id, text)
            assert self.session is not None
            self.session.say(text, audio=self.audio(text, self.lang))
            return
        if facts.get("asks_what_to_do"):
            line = FOLLOW[self.lang]["asked"] if acked else p["asked"]
        else:
            nxt = self.next_question()
            if nxt:
                self.asked[nxt] = self.asked.get(nxt, 0) + 1
                line = p[nxt] if acked or not new else f"{p['ack']} {p[nxt]}"
            elif new or not self.done_said:
                self.done_said = True
                line = p["hold"] if acked else p["done"]
            else:
                line = p["hold"]
        self.say(line)
        self.link.metric("call_turn", (time.perf_counter() - self.last_final_at) * 1000, call_id=self.call_id,
                         report_facts_ms=round((t1 - t0) * 1000))

    def next_question(self) -> Optional[str]:
        f = self.facts
        known = {
            "where": f.get("level") is not None or bool(f.get("room")) or f.get("current_action") == "outside",
            "people": f.get("people_count") is not None,
            "smoke": any(f.get(k) is not None for k in ("smoke_seen", "fire_seen", "heat"))
                     or f.get("current_action") == "outside",
            "hurt": f.get("mobility_issue") is not None or bool(f.get("injuries")),
            "action": f.get("current_action") not in (None, "unknown") or bool(f.get("heading_to")),
        }
        for q in QUESTIONS:
            if not known[q] and self.asked.get(q, 0) < 2:
                return q
        return None

    async def report_facts(self) -> dict:
        """Forced `report_facts` tool call over the conversation → `call_facts` to Seraph when something changed."""
        convo = "\n".join(f"{'CALLER' if r == 'appelant' else 'AGENT'}: {t}" for r, t in self.lines[-16:])
        try:
            r = await self.oai.chat.completions.create(
                model=config.LLM_MODEL, reasoning_effort="none", service_tier="priority",
                tools=[self.tool], tool_choice={"type": "function", "function": {"name": "report_facts"}},
                messages=[{"role": "system", "content": f"{EXTRACT}\n{self.rooms_prompt}"},
                          {"role": "user", "content": convo}])
            calls = r.choices[0].message.tool_calls or []
            got = json.loads(calls[0].function.arguments) if calls else {}
        except Exception as e:
            log.warning("%s report_facts failed: %s", self.call_id, e)
            return {}
        asks = bool(got.pop("asks_what_to_do", False))
        got = {k: v for k, v in got.items() if v is not None}
        sure = bool(got.pop("room_sure", False))
        if got.get("room"):
            got["room"] = norm_room(got["room"], self.rooms, self.occ.get("room"))
            room = got["room"]
            if room not in self.rooms:                  # never send a free-form number
                got.pop("room")
            elif room != self.facts.get("room") and not sure and room not in self.room_asked:
                got.pop("room")                         # unsure: read it back once before sending it
                self.confirm_room = room
        changed = {k: v for k, v in got.items() if k != "confidence" and self.facts.get(k) != v}
        self.facts.update({k: v for k, v in got.items() if k != "confidence"})
        voice_new = bool(self.voice) and self.voice.get("at") != self.sent.get("_voice_at")
        if changed or voice_new:
            out = dict(got)
            if self.voice:
                out["voice"] = self.voice
                self.sent["_voice_at"] = self.voice.get("at")
            out.setdefault("confidence", 0.7)
            if asks:
                out["free_text_fr"] = (out.get("free_text_fr") or "").rstrip(". ") + (". " if out.get("free_text_fr") else "") \
                    + "Demande quoi faire."
            self.send_facts(out)
            log.info("%s report_facts: %s", self.call_id, {k: v for k, v in out.items() if k != "voice"})
        return {**self.facts, "asks_what_to_do": asks, "_new": bool(changed)}

    def send_facts(self, facts: dict) -> None:
        excerpt = " ".join(t for r, t in self.lines if r == "appelant")[-400:]
        self.link.send({"kind": "call_facts", "call_id": self.call_id, "occupant_id": self.occ_id, "lang": self.lang,
                        "facts": facts, "transcript_excerpt": excerpt, "at": now_iso()})

    def on_sentiment(self, data: dict) -> None:
        if not getattr(self, "_logged_sentiment", False):
            self._logged_sentiment = True
            log.info("%s first Gladia sentiment event: %s", self.call_id,
                     json.dumps((data.get("data") or {}).get("results"), ensure_ascii=False)[:400])
        for res in (data.get("data") or {}).get("results") or []:
            emo = res.get("emotion") or "neutral"
            v = {"emotion": emo, "sentiment": res.get("sentiment") or "unknown", "text": (res.get("text") or "").strip(),
                 "at": now_iso()}
            self.voice = v
            # Fear, distress or pain with no new fact: tell Seraph now (it raises urgency, « selon la voix »).
            if emo in VOICE_RAISE and time.time() - self.voice_sent_at > 5:
                self.voice_sent_at = time.time()
                self.sent["_voice_at"] = v["at"]
                self.send_facts({"voice": v, "confidence": 0.6})
                log.info("%s voice: %s/%s", self.call_id, emo, v["sentiment"])

    async def end(self, why: str) -> None:
        if self.ended:
            return
        self.ended = True
        self.event("ended")
        log.info("%s ended (%s)", self.call_id, why)
        await asyncio.sleep(0.3)          # let the event leave
        self.ctx.shutdown(reason=why)


def prewarm(proc: JobProcess) -> None:
    proc.userdata["vad"] = silero.VAD.load()


async def warm_phrases() -> None:
    async with TTS() as t:
        await t.warm(all_phrases())


server = AgentServer(num_idle_processes=int(config.env("GABRIEL_IDLE_PROCS", "6")), setup_fnc=prewarm,
                     load_threshold=0.95, port=int(config.env("GABRIEL_HTTP_PORT", "0")))   # 8081 is taken here


@server.rtc_session(agent_name=config.CALL_AGENT_NAME)
async def call_agent(ctx: JobContext) -> None:
    meta = json.loads(ctx.job.metadata or "{}")
    http = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20, sock_connect=4))
    call = Call(ctx, meta, http)
    call.link.start()
    call.occ = await occupant(call.occ_id)
    if call.occ.get("language"):
        call.lang = norm_lang(call.occ["language"], call.lang)
    _SENTIMENT_HOOKS.append(call.on_sentiment)
    await ctx.connect()
    log.info("%s %s %s, lang %s, occupant %s", call.call_id, call.direction, call.channel, call.lang,
             call.occ.get("name") or "-")
    caller = await ctx.wait_for_participant()
    call.event("answered")

    session = AgentSession(
        stt=gladia.STT(languages=list(LANGS), code_switching=True, endpointing=0.15, maximum_duration_without_endpointing=10,
                       custom_vocabulary=gladia_live.vocabulary([call.occ.get("name", "")] + [
                           r["id"] for r in call.room_list if r.get("level") == call.occ.get("level")]),
                       custom_spelling=gladia_live.SPELLING, pre_processing_audio_enhancer=True, http_session=http),
        vad=ctx.proc.userdata["vad"],
    )
    call.session = session
    session.on("user_input_transcribed", call.on_transcribed)

    @ctx.room.on("participant_disconnected")
    def _gone(p: rtc.RemoteParticipant) -> None:
        if p.identity == caller.identity:
            asyncio.create_task(call.end("caller hung up"))

    async def _cleanup() -> None:
        if not call.ended:
            call.ended = True
            call.event("ended")
            await asyncio.sleep(0.2)
        if call.on_sentiment in _SENTIMENT_HOOKS:
            _SENTIMENT_HOOKS.remove(call.on_sentiment)
        await call.link.stop()
        await http.close()

    ctx.add_shutdown_callback(_cleanup)
    await session.start(room=ctx.room, agent=Agent(instructions="Gabriel (call agent, scripted)."),
                        room_options=room_io.RoomOptions(participant_identity=caller.identity, close_on_disconnect=True))
    call.say(GREETING[call.lang], interruptible=False)


def main() -> None:
    import sys
    if len(sys.argv) > 1 and sys.argv[1] in ("dev", "start"):
        asyncio.run(warm_phrases())     # pre-generate every fixed phrase once (skips what is on disk)
    cli.run_app(server)


if __name__ == "__main__":
    main()
