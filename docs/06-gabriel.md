# Gabriel — radio and calls

## Radio agent (room `crew`)
- LiveKit Agents worker joins `crew` as identity `Seraph` (that's the call sign the crew uses).
- One Gladia live STT stream per speaking participant (`livekit-plugins-gladia`): languages fr, en, es with
  code-switching; custom vocabulary from the glossary in `CLAUDE.md` + building words (escalier A/B, 3.12, binôme,
  ARI, colonne sèche, E1/E2).
- An utterance = from the talkie's `talking=true` to its `eot` data message (topic `ptt`). On `eot`, finalize and send
  `radio_transcript` to Seraph. Never transcribe Gabriel's own track.
- Speaking: queue per room; `priority:"alert"` jumps the queue; wait until nobody has `talking=true`, set own
  `talking=true`, short chirp, TTS, release. Publish the spoken text on data topic `seraph` (phones display it).
- Voice: TTS provider from `.env` (`TTS_PROVIDER`), French voice for the crew; must also speak English and Spanish
  for calls.

## Gladia, used fully (radio and calls)
Every listening path is Gladia live (`solaria-1`, region `eu-west`). Options, all set in code:
| Option | Setting | Why |
|---|---|---|
| Languages + code-switching | `languages=["fr","en","es"]`, `code_switching=True` | callers switch language mid-sentence |
| Custom vocabulary | `custom_vocabulary`: the glossary in `CLAUDE.md` (COS, CODIS, ARI, binôme, VSAV, FPT, EPA, colonne sèche, PEI, ETARE, « reçu »), the building's ids (rooms, stairs, entrances from `BUILDING_JSON`), the occupants' names from `occupants.list` | jargon and names come out right |
| Custom spelling | `custom_spelling`: one written form per radio formula (below) | Seraph's extraction gets the same string every time |
| Audio enhancer | `pre_processing_audio_enhancer=True` | engines, sirens, a phone in a smoky room |
| Sentiment + emotion | `realtime_processing.sentiment_analysis=true`, `messages_config.receive_realtime_processing_events=true` | calls only: the caller's voice raises the call's urgency |
| Many streams at once | one stream per radio speaker + one per call | radio + 6 calls in parallel |

**Radio formulas.** Fire-service radio is formatted (« <dest> de <émetteur> : … », « reçu », « binôme engagé, N bars »).
Custom spelling maps what Gladia may hear to one written form, e.g. « Seraph de Tête » ← séraphe de tête · « Binôme 1 »
← binôme un · « ARI » ← a r i · « escalier B » ← escalier bé · « E2 » ← e deux · « 3.12 » ← trois douze · « reçu » ←
resu. Build both lists at startup from the glossary and `BUILDING_JSON`; add the occupants' names when
`occupants.list` returns. Gabriel speaks in the same formulas (`seraph` sends them already formatted).

**Emotion → urgency.**
- `livekit-plugins-gladia` does not expose sentiment analysis (checked 03:10 Sunday on its reference: it has
  `custom_vocabulary`, `custom_spelling`, `code_switching`, translation, `pre_processing_audio_enhancer`, nothing else).
  So either open a second Gladia live session fed with the same call audio, or extend the plugin's session config with
  `realtime_processing.sentiment_analysis`. Gabriel's choice; write it in `status/gabriel.md`.
- Gladia returns, per sentence, a sentiment (positive, negative, neutral, mixed, unknown) and an emotion (25 labels:
  `distress`, `fear`, `pain`, `confusion`, `relief`…; `GladiaEmotion` in `contracts/types.ts`). The live event's exact
  shape isn't in the docs we read: log the first raw event and write it in `status/gabriel.md`.
- Attach the latest signal to the next `call_facts` as `facts.voice` (`VoiceSignal`). When the emotion turns to
  `distress`, `fear` or `pain` with no new fact, send a `call_facts` with only `voice` (and `confidence`).
- Calls only. The radio is not scored: a firefighter shouting on the radio is normal.
- Seraph turns it into `calls[].urgency` (code, `briefs/seraph.md`). The voice never changes an instruction.
- Mock: the mock CLI sends `caller_voice[i]` from `contracts/fixtures/calls.jsonl` as `facts.voice` with line i.

**Not used, and why:** translation in the call `AgentSession` (LiveKit's doc warns each target language adds a
transcript to the LLM history; the LLM writes `free_text_fr`) · named entities (the extraction is already structured).

## Call agents (rooms `call-<id>`)
- One `AgentSession` per call: Gladia STT (language detected on the first sentence), an OpenAI-compatible LLM
  (`LLM_*` env, fast model), multilingual TTS.
- **Identity, always first:** « Exercice. Bonjour, ici Gabriel, l'assistant vocal des pompiers. » (in the caller's
  language). Callers must know they talk to an automated assistant.
- Questions, short, one at a time, adapted to what was already said: where are you (level, room) · how many people
  with you · smoke or heat near you · anyone injured or unable to walk · what are you doing now.
- After every new fact: tool `report_facts(CallFacts)` → Seraph (`call_facts`). Keep the line open.
- **What the agent may say on its own:** questions, « je transmets aux pompiers », « restez en ligne », reassurance
  without promises. **Never** an instruction about moving, staying or a route, except: (a) a standing instruction the
  COS confirmed (see `contracts/fixtures/calls.jsonl` CALL-01 note), (b) a `say` from Seraph after a gate. Never
  « les secours arrivent » unless Seraph says so.
- Seraph can push `say` to one call or many (`call_ids`); the agent says it promptly, in the caller's language
  (Seraph sends the text already translated, or French + `lang` and the agent translates faithfully).

## Telephony (do this first: it takes time)
- **Outbound** (Gabriel calls occupants): LiveKit SIP outbound trunk on Twilio Elastic SIP Trunking → for each
  `place_calls` entry, create room `call-<id>`, dispatch a call agent, `CreateSIPParticipant` to the number.
- **Inbound** (the incident's 112 line): a Twilio number → LiveKit SIP inbound trunk → dispatch rule → new room
  `call-<id>` + call agent; Gabriel sends `call_event` (direction `in`).
- Twilio trial accounts only call verified numbers: use a paid account, or verify the judges' numbers, or fall back
  to web calls.
- Exact steps change: follow LiveKit's telephony docs via Context7 and write what you did in `status/gabriel.md`.
- **Fallback:** web calls. The talkie's `/call?occ=…` page joins `call-<id>` from the judge's browser; same agent.

## Metrics to log
`eot → transcript sent` · `call fact → crew say` · `say queued → spoken`. Seraph turns them into `metric` events.
