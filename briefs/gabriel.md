# Brief — `gabriel` session (voice) · `gabriel/` · LiveKit Agents workers

Read first: `CLAUDE.md`, `docs/06-gabriel.md` (the design), `contracts/types.ts` (GabrielToSeraph /
SeraphToGabriel), `contracts/README.md` (rooms, data topics), `contracts/fixtures/calls.jsonl`, `docs/07-safety-rules.md`.

## Goal
Two kinds of workers: the **radio agent** on `crew`, and **call agents**, one per phone call. Both talk to Seraph over
`ws://…/ws/gabriel`. Gladia does all the listening.

## Build order
1. Radio agent: join `crew`, transcribe per speaker with Gladia, segment on the talkie's `eot`, send
   `radio_transcript`. Speak Seraph's `say` with TTS. → **Gate 1 (03:00)**.
   Gladia options from the start (`docs/06-gabriel.md` « Gladia, used fully »): languages + code-switching, custom
   vocabulary, custom spelling for the radio formulas, audio enhancer. They are constructor arguments.
2. Call agent on a **web call** first (room `call-<id>` joined from talkie `/call`): identity line, questions,
   `report_facts` tool → `call_facts`, obey `say` for that call. Test with `contracts/fixtures/calls.jsonl` lines
   spoken by you in fr/en/es.
3. Telephony: outbound via LiveKit SIP + Twilio for `place_calls`; inbound number for the incident's 112 line.
   Follow LiveKit's current telephony docs (Context7). Write the exact setup in `status/gabriel.md`.
4. Many calls at once (target 6 in parallel) without blocking the radio agent.
5. Emotion on calls: Gladia sentiment + emotion → `facts.voice` (`VoiceSignal`). Not in the LiveKit plugin: see
   `docs/06-gabriel.md`. After step 2 works, before the 10:00 freeze.

## Rules that matter
- Callers hear first, in their language: « Exercice. Bonjour, ici Gabriel, l'assistant vocal des pompiers. »
- The call agent never gives an instruction to move, stay or take a route on its own. Allowed: questions,
  « je transmets », « restez en ligne », the COS-confirmed standing instruction (only when the condition holds),
  and Seraph's `say`. Never promise that help is coming.
- Never transcribe your own TTS. Never show or log full phone numbers (mask them).
- `priority:"alert"` says go first on the radio.

## Mock mode (`MOCK=1`)
A small CLI that sends `radio_transcript` / `call_event` / `call_facts` from the fixtures to Seraph, and prints every
`say` it receives. Lets Seraph be tested without LiveKit.

## Done when
A talkie utterance reaches Seraph in < 1 s after release and Seraph's reply is heard on the talkie; a web call and a
real phone call both produce `call_facts` and hear a gated `say`; 3 calls + radio run at the same time. A caller who
sounds frightened produces `facts.voice` with `fear` or `distress`.

## Fallbacks
Voice output through the laptop speaker (`say` printed and played locally) · web calls instead of SIP.
