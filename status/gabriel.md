# gabriel — status
Updated: 05:24

## Running
Needs Seraph on :8000 (both reconnect by themselves if it restarts) and the talkie on :3000 for web calls.
- radio: `cd gabriel && uv run gabriel-radio` — joins LiveKit `crew` as `Seraph`, restarts itself after a crash or a
  lost room; a second radio takes over and the first stops (never two). Fallback: `GABRIEL_LOCAL_SPEAKER=1` also
  plays every crew say on the laptop speaker.
- calls: `cd gabriel && uv run gabriel-calls start` (`dev` = hot reload, don't use it for the demo) — LiveKit Agents
  worker, agent name `gabriel-call`, 6 warm processes (`GABRIEL_IDLE_PROCS`), one process per call, health server on a
  random port (`GABRIEL_HTTP_PORT`; 8081 is taken by a node process here).
- talkie on LiveKit: `TALKIE_TRANSPORT=livekit` in the root `.env` + restart talkie, or per page `?transport=livekit`
  (`http://localhost:3000/?transport=livekit`, `http://localhost:3000/call?occ=OCC-05&transport=livekit`).
- mock (`MOCK=1`, no LiveKit): `uv run gabriel-mock radio R01 R03` · `call CALL-01` · `say "Seraph, quelle entrée ?" Tête`
  · `listen [--speak]`.
- tests without phones: `uv run python -m gabriel.fake_talkie "Seraph de Tête, quelle entrée ?"` ·
  `uv run python -m gabriel.fake_caller OCC-04 en "Hello?" "I'm on the fourth floor, heading down the south stairs."`
  (`-` instead of `OCC-…` = inbound 112).
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
- Gladia, all paths: solaria-1, eu-west, fr/en/es + code-switching, custom vocabulary (glossary + building ids from
  `BUILDING_JSON` + occupant names, ≤100), custom spelling (Seraph, Binôme 1/2, ARI, COS, escalier A/B, E1/E2, 3.12…),
  audio enhancer. Calls: + live sentiment/emotion.
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
- **Rooms:** only the building's room ids (BUILDING_JSON, people rooms only) ever reach Seraph. Gladia gets them in the
  vocabulary (caller's level first) and as custom spelling (« deux zéro un », « two oh one » → 2.01); `report_facts`
  has `room` as an enum of those ids + `room_sure`. An unsure room is read back once (« Appartement deux zéro un,
  c'est bien ça ? ») and sent only after. Live: « chambre deux point un » → read-back → « oui » → 2.01.
- Seraph's `say` for a call (`call_id` / `call_ids`) interrupts and is spoken as is; `translate:true` → faithful LLM
  translation of `text_fr`. Verified: the confirmed standing instruction reached CALL-01-style call after « fumée sous la
  porte ». `end_call` hangs up.
- **Emotion:** Gladia sentiment added to the plugin's live session (I patch its config builder + message handler; the
  plugin does not expose it). Latest signal rides on every `call_facts` as `facts.voice`; `distress`/`fear`/`pain`
  sends a voice-only `call_facts` at once (≤ 1 per 5 s). Seen live: « Il y a de la fumée sous la porte » → fear/negative.
- **Parallel:** 3 web calls (fr wheelchair, es, inbound 112 en) + a radio turn at once: calls answer 0.76–1.37 s after
  the caller stops, radio release → audio 0.96 s, no interference.
- `place_calls`: logged with masked numbers, not dialed (SIP not wired, Amil's decision). Numbers are masked everywhere.
- Metrics to Seraph (`{kind:"metric"}`): `eot_to_transcript`, `say_to_audio` (+`wait_ms`), `release_to_audio`,
  `call_ack`, `call_turn` (+`report_facts_ms`), `call_say_queued`.

- **Scenario v2 (TU Wien, 96 boulevard Bessières, one stair A):** vocabulary without « escalier B », with rampe,
  parking, désenfumé, levée du confinement, balcon, terrasse, boulevard Bessières; `report_facts` maps « the stairs »
  to `stair:A`, the garage ramp to `exit:E2`, and « ma chambre » / « chez moi » to the caller's listed room. Offline
  against `calls.jsonl` v2 (twice): CALL-01/02/03/04/07 exact; CALL-05 gives `current_action:"unknown"` (Lucía never
  says what she's doing; Gabriel asks).

## In progress
- Nothing. Next if wanted: SIP/Twilio for `place_calls` and the 112 number (stubbed), a real-phone check of the mic.

## Blocked
-

## Requests (to other sessions or Amil)
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
- The in-app browser pane blocks the mic; Chromium with `--use-file-for-fake-audio-capture=<wav>` works for tests.
