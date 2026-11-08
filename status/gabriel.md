# gabriel — status
Updated: 10:50

## Running
Needs Seraph on :8000 (both reconnect by themselves if it restarts) and the talkie on :3000 for web calls.
- radio: `cd gabriel && uv run gabriel-radio` — joins LiveKit `crew` as `Seraph`, restarts itself after a crash or a
  lost room; a second radio takes over and the first stops (never two). Fallback: `GABRIEL_LOCAL_SPEAKER=1` also
  plays every crew say on the laptop speaker.
- calls: `cd gabriel && uv run gabriel-calls start` (`dev` = hot reload, don't use it for live runs) — LiveKit Agents
  worker, agent name `gabriel-call`, 6 warm processes (`GABRIEL_IDLE_PROCS`), one process per call, health server on a
  random port (`GABRIEL_HTTP_PORT`; 8081 is taken by a node process here). Takes web calls and real phone calls.
  Keep it in `start` and keep the agent name `gabriel-call`: the SIP dispatch rule points at it. It reports unavailable
  above 95 % CPU (`load_threshold=0.95`); a phone call arriving then gets no agent.
- talkie on LiveKit: `TALKIE_TRANSPORT=livekit` in the root `.env` + restart talkie, or per page `?transport=livekit`
  (`http://localhost:3000/?transport=livekit`, `http://localhost:3000/call?occ=OCC-05&transport=livekit`).
- mock (`MOCK=1`, no LiveKit): `uv run gabriel-mock radio R01 R03` · `call CALL-01` · `say "Seraph, quelle entrée ?" Tête`
  · `listen [--speak]`.
- tests without phones: `uv run python -m gabriel.fake_talkie "Seraph de Tête, quelle entrée ?"` ·
  `uv run python -m gabriel.fake_caller OCC-T01 en "Hello?" "I'm on the fourth floor, heading down the stairs."`
  (`-` instead of `OCC-…` = inbound 112; a line starting with `>` is said while Gabriel is still talking).
- I am running both right now (calls in `start` mode), logs in `gabriel/logs/`.
- Test callers use test occupant ids (`OCC-T01`…) so they never overwrite the demo occupants in Seraph's state.

## Done
- **Gate 1 (radio), measured on LiveKit Cloud:** eot → `radio_transcript` at Seraph 410–530 ms · release → Seraph
  `talking=true` 470–600 ms · release → Seraph's first audio heard in the room 890–960 ms. Tested with a scripted
  speaker and with the real talkie page in Chromium (fake mic WAV): « Seraph, point de situation. » transcribed from
  the page; the button locks on « Seraph parle… » while Gabriel speaks.
- **iOS Safari (simulator « Talkie 17e »):** join with the mic prompt, « Maintenir pour parler », press → on air → eot
  reaches Gabriel, and « Seraph parle… » + lock while Gabriel's audio plays (Safari's audio icon on). The simulator mic
  gave silence from the Mac speaker, so **speaking from iOS still needs a real phone to confirm**.
- Two iOS bugs fixed in `livekit.ts`: the UI's `audioSession.type = "playback"` blocks the mic on iOS (« AudioSession
  category is not compatible with audio capture ») → set `play-and-record` before the mic; two tabs with the same
  call sign kicked each other forever → no auto-rejoin after a `DUPLICATE_IDENTITY` kick.
- Radio listen: one Gladia live session per push-to-talk turn per speaker (opens on `talking=true` with 0.6 s pre-roll,
  closed by the eot on topic `ptt` with `stop_recording`; `talking=false` without eot → cut after 1.2 s). Only remote
  tracks are subscribed: Gabriel never hears its own TTS.
- Radio speak: `say` for `{room:"crew"}` → queue (`alert` first) → waits for a free floor → `talking=true` +
  `talking_since` → ElevenLabs PCM → `talking=false`. Text also on topic `seraph`. Yields on a press collision.
- Gladia, all paths: solaria-1, eu-west, fr/en/es + code-switching, custom vocabulary (glossary + building labels
  from `BUILDING_JSON` + occupant names, ≤100, **no numeric ids**), custom spelling (Seraph, Binôme 1/2, ARI, COS,
  escalier A, E1/E2, every room id), audio enhancer. Calls: + live sentiment/emotion.
- Talkie wiring (`talkie/lib/radio/livekit.ts`, `talkie/app/api/token`, `talkie/app/api/call-token`): mic published muted
  at join, unmute on press, `talking`/`talking_since` without awaiting, eot on release, collision rule (earlier
  `talking_since` wins, tie = smaller identity), `radioFilter` on received audio through the given `AudioContext`,
  auto-rejoin after a full disconnect. Calls: 15 s « Gabriel ne répond pas. », agent leaving → ended. Routes read
  process.env, else the root `.env` at request time (a dev server started before the keys still works).
- **Web calls** (`/call?occ=…` and `/call` for 112): explicit dispatch with `{call_id, occupant_id, direction, channel,
  lang}` (lang = browser language, the occupant's language from Seraph wins). The agent sends `call_event answered`
  when the caller is in the room, `ended` when they leave. First sentence in the caller's language: « Exercice. Bonjour,
  ici Gabriel, l'assistant vocal des pompiers. Où êtes-vous en ce moment ? » (en, es too).
- **Call flow, decided by code:** after each caller turn, an immediate « Je transmets. » (cached) while
  `report_facts` (forced tool call, gpt-5.4-mini, ~0.8 s) extracts the facts → `call_facts`; then the next question not
  yet answered (where → how many → smoke → injured → what are you doing), or « Et votre question aussi. Restez en
  ligne. » when the caller asks what to do. **No model writes what the caller hears**, so Gabriel can never give an
  instruction or promise help on its own; every phrase is pre-generated in fr/en/es.
- **Rooms:** only the building's room ids (BUILDING_JSON, people rooms only) ever reach Seraph; `report_facts` has
  `room` as an enum of those ids + `room_sure` + `room_heard` (the number as transcribed).
  - **« -1.xx » fixed at the source:** the room ids in Gladia's custom vocabulary (« -1.04 », « -1.11 Garage »…) made
    Gladia write every spoken door number in that shape: « deux onze », « deux point onze », « deux cent onze » all came
    out « -1.11 ». Numbers are now out of the vocabulary, and custom spelling (applied after Gladia's number
    formatting) maps the shapes Gladia writes: « 2-11 », « 211 », « 2,11 » → 2.11, « 3D » (trois dix) → 3.10, « 019 »
    → 0.19. Same TTS lines through Gladia, before → after: « toilettes, 2.11 » -1.11 → 2.11; « appartement 3.10 »
    310 → 3.10; « trois dix » 3D → 3.10; « chambre deux zéro un » → 2.01. The radio uses the same vocabulary.
  - When the number heard does not fit the caller's level (« -1.11 » from someone on the 2nd), the next line is
    « Le numéro de la porte, chiffre par chiffre ? » (once per call; en/es too), and « 2, 1, 1 » → 2.11 sure. An unsure
    room that fits is read back once (« Appartement deux un un, c'est bien ça ? »).
- **Caller talking over Gabriel is kept:** LiveKit Agents fed silence to the STT during non-interruptible speech
  (`discard_audio_if_uninterruptible`, default on) and during the first 3 s of agent speech (`aec_warmup_duration`).
  Both off now, so what a caller says over the greeting or over Seraph's guidance is transcribed and goes through
  `report_facts` (Gabriel keeps talking). Live: « Je suis blessé à la jambe, je ne peux pas marcher » over the
  greeting → `injuries` + `mobility_issue`; « ma fille est avec moi » over Seraph's guidance → `people_count` 2. Echo
  guard: a transcript made mostly of the words Gabriel is saying is dropped (`echo dropped` in the log).
- **No repeated questions:** never the same question twice in a row (the greeting counts as « where »), except right
  after a turn with no content (« Allô ? », « Pardon ? »); a turn with no new fact while Gabriel is still talking
  gets no reply (« Allô ? » over the greeting).
- Seraph's `say` for a call (`call_id` / `call_ids`) interrupts and is spoken as is; `translate:true` → faithful LLM
  translation of `text_fr`. Verified: the confirmed standing instruction reached CALL-01-style call after « fumée sous la
  porte ». `end_call` hangs up.
- **Emotion:** Gladia sentiment added to the plugin's live session (I patch its config builder + message handler; the
  plugin does not expose it). Latest signal rides on every `call_facts` as `facts.voice`; `distress`/`fear`/`pain`
  sends a voice-only `call_facts` at once (≤ 1 per 5 s). Seen live: « Il y a de la fumée sous la porte » → fear/negative.
- **Parallel:** 3 web calls (fr wheelchair, es, inbound 112 en) + a radio turn at once: calls answer 0.76–1.37 s after
  the caller stops, radio release → audio 0.96 s, no interference.
- **Real phone calls, inbound (09:48):** LiveKit Phone Number +1 646 357 5046 (`PN_PPN_Mr7J4H9szQnV`, US, inbound
  only); Amil forwards his French mobile to it, so callers dial a French number. Dispatch rule `SDR_S8H3HrNSvi3j`
  « seraph-112 » (any trunk) → room `call-<callee>_<random>`, agent `gabriel-call`, metadata
  `{"direction":"in","channel":"phone"}`. Same agent and flow as web calls: first call `_16463575046_zEQFiPcaNRHd`,
  in/phone/fr, read-back confirmed 3.10, Seraph summary « Appel 112 : quatre personnes séjour-cuisine 3.10… ». Set up
  in the walkthrough session, no code change needed.
- Phone numbers: the SIP caller's number goes to Seraph only masked (`number_masked` « +33 7•• •• •• 72 », from the
  participant's `sip.phoneNumber`). Every log line of the call worker is masked too, framework extras included
  (livekit.agents logs `participant: sip_+33…`).
- **Outbound phone calls for `place_calls`: code done, waiting for a trunk.** The radio gets `place_calls`; for each
  number `dial.py` creates room `call-CALL-P<5>` and dispatches `gabriel-call` with `{call_id, occupant_id,
  direction:"out", channel:"phone", lang: language_hint, name, phone_e164}`. The agent sends `ringing`, dials with
  `CreateSIPParticipant` (trunk `LIVEKIT_SIP_OUTBOUND_TRUNK_ID`, caller id = the trunk's number or
  `LIVEKIT_SIP_OUTBOUND_NUMBER`, 30 s ring, `wait_until_answered`, number hidden from participant attributes), then
  `answered` and the usual flow, or `no_answer` (SIP 408/480/486/487/600/603) / `failed` (anything else). Numbers are
  masked in every event and log line. Both ids are read from `.env` at dial time: no restart after filling them in.
  Tested offline with LiveKit mocked (busy → `no_answer` and hang-up, answer → `answered`); **never dialed for real**.
- **Who is dialed:** `place_calls` carries no consent flag, so Gabriel dials only E.164 numbers outside `+3310000…`
  (the registry's fictional seed numbers, demo occupants OCC-01…06, plus +33100000098/99). Numbers registered
  through `/inscription` are real and consented; those are the ones dialed. Seed occupants keep the web call
  (`/call?occ=…`). With no trunk set, nobody is dialed (log line « not dialed: no outbound trunk »).
- Phone calls (in and out) now hang up the line when Gabriel ends the call (`end_call` from Seraph deletes the room;
  before, the agent left and the caller stayed on a silent line).
- A greeting-only turn (« Allô ? », which Gladia returns as English « Hello? ») no longer switches the call to
  English: the language changes only on a turn with 3+ words besides allô/hello/oui/yes.
- Metrics to Seraph (`{kind:"metric"}`): `eot_to_transcript`, `say_to_audio` (+`wait_ms`), `release_to_audio`,
  `call_ack`, `call_turn` (+`report_facts_ms`), `call_say_queued`.

- **Scenario v2 (TU Wien, 96 boulevard Bessières, one stair A):** vocabulary without « escalier B », with rampe,
  parking, désenfumé, levée du confinement, balcon, terrasse, boulevard Bessières; `report_facts` maps « the stairs »
  to `stair:A`, the garage ramp to `exit:E2`, and « ma chambre » / « chez moi » to the caller's listed room. Offline
  against `calls.jsonl` v2 (twice): CALL-01/02/03/04/07 exact; CALL-05 gives `current_action:"unknown"` (Lucía never
  says what she's doing; Gabriel asks).

## In progress
- Outbound calls: blocked on the trunk below, then Amil's own test call. Also open: a real-phone check of the talkie mic.

## Blocked
- **Outbound SIP trunk does not exist.** The LiveKit project has 0 outbound and 0 inbound trunks (checked 10:05);
  inbound works through the LiveKit Phone Number, which cannot dial out. `LIVEKIT_SIP_OUTBOUND_TRUNK_ID` is empty.

## Requests (to other sessions or Amil)
- **Amil — create the outbound trunk (≈15 min), then put its id in `.env`.** Telnyx requires a paid account.
  1. Telnyx portal, a number: use a Telnyx number you own (caller id). None yet: buy one; a US number is instant, a
     French one needs regulatory documents.
  2. Telnyx » Voice » Outbound Voice Profiles » Create: traffic type Conversational, service plan Global, and **add
     France to the allowed destinations** (otherwise calls to +33 are refused).
  3. Telnyx » Voice » SIP Trunking » Create SIP connection, type **FQDN**: FQDN = the LiveKit project's SIP URI
     (LiveKit dashboard » Settings » Project » SIP URI, without `sip:`), port 5060. « Outbound calls authentication »:
     pick a username and a password. Inbound settings: number formats `+E.164`, transport TCP. Outbound settings:
     the voice profile from step 2. Link the number from step 1.
  4. LiveKit dashboard » Telephony » SIP trunks » Create » Outbound (or `lk sip outbound create trunk.json`):
     ```json
     {"trunk": {"name": "telnyx-out", "address": "sip.telnyx.com", "numbers": ["+<Telnyx number>"],
                "auth_username": "<username>", "auth_password": "<password>",
                "headers": {"X-Telnyx-Username": "<username>"}}}
     ```
     The username header makes Telnyx always challenge for the password (LiveKit's Telnyx page). It sits in
     `headers`, the outbound trunk's field for custom INVITE headers; the page says `headers_to_attributes`, which
     maps received headers to attributes.
  5. `.env`: `LIVEKIT_SIP_OUTBOUND_TRUNK_ID=ST_…` (shown after step 4). Optional `LIVEKIT_SIP_OUTBOUND_NUMBER=+…` if
     the trunk has several numbers. No restart needed.
  6. Test: register your own number on `/inscription`, start an incident: Seraph's `place_calls` → your phone rings
     from the Telnyx number, « Exercice. Bonjour, ici Gabriel… ». `gabriel/logs/calls.log` shows the SIP code on failure.
- Amil — phone B needs HTTPS for the mic. `cloudflared` is not installed: `brew install cloudflared` then
  `cloudflared tunnel --url http://localhost:3000` (and set `TALKIE_PUBLIC_URL`), or deploy `talkie/` to Vercel with
  `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`, `TALKIE_TRANSPORT=livekit`. Gabriel itself needs no tunnel.
- Amil — to switch the talkie to LiveKit for everyone: `TALKIE_TRANSPORT=livekit` in `.env`, then restart the talkie.
- @talkie: I added `livekit-client` ^2.23 and `livekit-server-sdk` ^2.19 to `talkie/package.json` (needed by `livekit.ts`
  and the routes). Please commit `package.json` + `package-lock.json`.
- @seraph: while a Gabriel socket is connected your MockGabriel no longer plays `calls.jsonl` on `place_calls`
  (`hub.connected > 0`). Real phone calls are stubbed, so outbound calls only happen as web calls for now.
- @seraph: web call ids look like `CALL-W<5 chars>`; `call_facts` carry `occupant_id` when the call came from
  `/call?occ=…`. When the caller asks what to do, `free_text_fr` ends with « Demande quoi faire. ».

## Facts I verified (API names, model ids, gotchas)
- Gladia live v2: `POST https://api.gladia.io/v2/live?region=eu-west` (region is a **query param**: in the body it fails
  « property region should not exist »). Binary PCM on the WS; `{"type":"stop_recording"}` → final in 0.4–0.55 s, then
  an ack `stop_recording`, `speech_end`, `post_transcript`, `post_final_transcript`. A turn whose speaker was already
  quiet ends on the ack (no speech open) instead of waiting for post-processing.
- Gladia `sentiment_analysis` live event: `data.results[] = {text, sentiment, emotion, start, end, channel}`, one per
  sentence, ~0.5–1.5 s after it. Needs `realtime_processing.sentiment_analysis:true` and
  `messages_config.receive_realtime_processing_events:true`.
- livekit-plugins-gladia 1.8.11 builds its config in module function `_build_streaming_config` and handles messages in
  `SpeechStream._process_gladia_message`: both patched in `gabriel/calls.py` for sentiment.
- ElevenLabs `POST /v1/text-to-speech/{voice}/stream?output_format=pcm_24000`, `eleven_flash_v2_5`, first byte 140–200 ms.
  Voice « Olivier D » `rgFgMEXfdGwXCYio7I0J` (French, speaks en/es too), override `GABRIEL_TTS_VOICE`.
- livekit-agents 1.8.11: `AgentServer(num_idle_processes, setup_fnc)`, `@server.rtc_session(agent_name=…)`,
  `AgentSession(stt, vad)` without LLM/TTS works; `session.say(text, audio=frames)` plays our own PCM. In `dev`, a job
  can land on an idle process started before a code change: restart the worker to be sure.
- An LLM turn (Agents pipeline: Gladia final + EOU + LLM + TTS) took 2.6–3.5 s on calls; the code-driven flow takes
  0.8–1.5 s. gpt-5.4-mini with `reasoning_effort:"none"` misses facts unless the extraction prompt spells out the
  mappings (« fourth floor » = 4, « avec un collègue » = 2…).
- livekit (python rtc) 1.2: `participant_attributes_changed(changed, participant)`, `data_received(DataPacket)` with
  `.topic`; `AccessToken.with_attributes()`. Two coroutines calling `AudioSource.capture_frame` at once → InvalidState.
- Phone audio logs once per call « transcript arrives after turn has been committed » (livekit.agents suggests
  `min_delay`). Harmless here: the call flow runs on Gladia finals (`user_input_transcribed`), not on the session's
  turn commit, and the session has no LLM.
- `lk number update --sip-dispatch-rule-id` fails with invalid_argument; an any-trunk dispatch rule routes the number
  anyway.
- Gladia custom vocabulary biases number formatting: a vocabulary with « -1.04 »-style ids turns « deux onze » into
  « -1.11 ». Custom spelling runs after number formatting, so its variants must be Gladia's written shapes (« 2-11 »,
  « 3D »), not spoken words.
- livekit-agents 1.8.11: `AgentSession(turn_handling={"interruption": {"discard_audio_if_uninterruptible": False}},
  aec_warmup_duration=None)` keeps the STT hearing the user during non-interruptible speech and the first 3 s of it.
- The in-app browser pane blocks the mic; Chromium with `--use-file-for-fake-audio-capture=<wav>` works for tests.
