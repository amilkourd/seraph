# talkie — status
Updated: 05:40

## Running
- talkie on http://localhost:3000 (`cd talkie && npm run dev`, binds 0.0.0.0) · public: none yet · transport: **mock**
- `GET /health` → `{ok:true, mock:true, service:"talkie", transport:"mock"}` (dashboard health dot)

## Done
- `/` crew radio: call-sign picker (COS, Tête, Binôme 1, Binôme 2, free text, remembered) → « Rejoindre le canal »
  (unlocks Web Audio + speech inside the tap) → one screen: CANAL CREW + call sign + EXERCICE, round hold-to-talk
  button. **No text from Seraph on screen** (Amil, 03:25): you hear it, the button says « Seraph parle… ».
  Tap the call sign to change it.
- **Black and white only, no art direction** (Amil, 03:15): black background, white buttons. States by shape:
  idle white outline « Maintenir pour parler » · on air filled white « En émission » + timer · receiving dashed +
  lock « Seraph parle… » / « Tête parle… » (locked, a press plays a busy tone) · offline dashed, turning
  « Connexion… / Reconnexion… ».
- Sounds, all Web Audio, no files: chirp on press, roger beep on release, squelch open/close + faint hiss while
  receiving, busy tone. `radioFilter(ctx)` (band-pass 300–3000 Hz + soft clip) ready for received audio.
- Wake Lock, no zoom, no long-press callout, pointer capture, release on blur/hide, 60 s max on air, Space = PTT.
- `/call?occ=OCC-07` (direction out) and `/call` (incoming 112, direction in): « Appeler les pompiers (exercice) »
  → Connexion… → « Vous parlez à Gabriel, assistant vocal (exercice) » + timer + « Raccrocher » → Rappeler.
  Failed → « Appel impossible » + reason + Réessayer.
- `/qr`: big QR to `OCCUPANTS_PUBLIC_URL` + `/inscription` (read at request time from the root `.env`).
  Unset → placeholder QR, labelled. `/qr?url=https://…` overrides on stage.
- Mock transport replays `contracts/fixtures/radio.jsonl` (scenario v2, TU Wien, R00–R15, resynced 05:40): others talk (browser French voice), Seraph answers
  with `say_crew` (`<HH:MM>` filled with now + 15 min / 10). When you transmit ≥ 0.6 s, Seraph answers your next line.
- `?dev=1`: panel (Dev, bottom right): Repos, Émission 4 s, Seraph parle, Tête parle, Coupure 5 s, Coupure,
  Reconnecter, every fixture line, auto replay and voice toggles, a log of what would go on the wire.
  `?dev=1&join=Tête&state=tx|rx|seraph|off` joins and holds a state with no tap (rehearsals, screenshots; no audio on iOS).
  `/call?dev=1`: phase buttons.
- Tested: Chrome 390×844 all states; **iOS Safari (simulator « Talkie 17e », 390 pt)** idle/tx/rx/off/seraph
  render right. `npm run build`, `tsc`, `eslint` clean.

- Touch-tested in the iOS Simulator (« Talkie 17e », prod build): one tap joins; hold → « En émission » + timer with no
  magnifier/callout; release → eot → Seraph answers your line; a press while Seraph talks stays locked; web call
  tap → in call → Raccrocher → Rappeler. Safari shows its "playing audio" icon while the mock speaks.
- Gotcha seen in testing: two taps on different buttons < ~300 ms apart → iOS drops the second (double-tap window).
  The PTT uses pointer events, so it is not affected.

## Not verified
- Actual sound quality (chirp, roger, squelch) by ear, and the mic: only a real phone tells. Do it on phone B.

## Radio interface (for the Gabriel session: fill `talkie/lib/radio/livekit.ts`, nothing else)
The UI only imports `@/lib/radio` (`createRadio`, `createCall`, types). Transport choice: `TALKIE_TRANSPORT=livekit`
in the root `.env` (default mock; `MOCK=1` forces mock; `?mock=1` / `?transport=livekit` override per page).
Every `on*` replays the current value on subscribe — use `Signal` from `lib/radio/signal.ts` (the stub already does).

`RadioTransport` (room `crew`, identity = call sign):
| Member | Must do |
|---|---|
| `join(callSign, {audioContext})` | token for `crew`, connect, publish the mic **muted** (iOS mic prompt happens here, press is then instant), link `connecting → connected`; reject on failure (UI shows « Canal indisponible » + Réessayer + « Mode local » = `?mock=1`). Use the given unlocked `AudioContext` (`new Room({ webAudioMix: { audioContext } })`). |
| `leave()` | disconnect, link `offline`. |
| `startTalking(): Promise<boolean>` | false if not connected or `remote !== null` (first press wins). Else unmute, `local=true`, then `setAttributes({talking:"true", talking_since})` **without awaiting** (setAttributes waits up to 5 s for the echo). |
| `stopTalking()` | mute, `local=false`, `talking:"false"`, `publishData(encodeEot(callSign), {reliable:true, topic:"ptt"})` → `{"kind":"eot","speaker":"Tête"}`. |
| `onState(cb)` | `"offline" \| "connecting" \| "connected" \| "reconnecting"` (RoomEvent ConnectionStateChanged / Reconnecting / Reconnected / Disconnected). |
| `onLocalTalking(cb)` | true/false; also false when the transport ends it (disconnect, lost collision). The UI's chirp/roger follow it. |
| `onRemoteTalking(cb)` | identity of the remote participant with attribute `talking === "true"`, else null (ParticipantAttributesChanged, ParticipantDisconnected, recompute after a full reconnect). Gabriel's identity `Seraph` shows « Seraph parle… ». |

Collision rule (two presses within the attribute round trip): the earlier `talking_since` keeps the floor
(tie: smaller identity); the loser mutes, sends its eot, `local=false`.
Received audio: `RemoteAudioTrack.setWebAudioPlugins(radioFilter(ctx))` from `lib/audio/sounds.ts` (marked
`@internal` in the SDK docs — if it misbehaves, drop the filter, never the audio). The UI adds hiss and squelch itself.

`CallTransport` (room `call-<callId>`, full duplex, no PTT): `startCall(occId?, {audioContext})` — `occId` → direction
`out`, none → `in` (112); status `connecting` (with `callId`) → `in_call` (with `startedAt`) when the Gabriel call agent
is in the room → `ended` / `failed` (with French `reason`; no agent after 15 s → « Gabriel ne répond pas. »).
`hangUp()`, `onCallState(cb)`.
Route handlers to add in `talkie/app/api/`: `token` (crew; needs `canUpdateOwnMetadata` for setAttributes) and
`call-token` (room + agent dispatch + `call_event` to Seraph). Full TODOs with the LiveKit calls are in `livekit.ts`.

## Requests (to other sessions or Amil)
- @gabriel: `talkie/lib/radio/livekit.ts` + `talkie/app/api/{token,call-token}` are yours (agreed split). Please
  confirm the radio agent sets attribute `talking` while it speaks. The talkie ignores data topic `seraph`.

## Facts I verified (API names, model ids, gotchas)
- Next 16.4.5 with `cacheComponents`: `useSearchParams` pages wrapped in `<Suspense>`; `/qr` reads env after `await connection()`.
- livekit-client (Context7): `setAttributes(Record<string,string>)` waits ≤ 5 s for the server echo;
  `publishData(bytes, {reliable, topic})`; `RoomEvent.DataReceived(payload, participant, kind, topic)`;
  `RoomEvent.ParticipantAttributesChanged(changed, participant)`; `RoomOptions.webAudioMix: { audioContext }`;
  `RemoteAudioTrack.setWebAudioPlugins(nodes)` (@internal); `room.startAudio()` needs a user gesture.
- iOS: Web Audio follows the silent switch unless `navigator.audioSession.type = "playback"` (Safari 17+, set in
  `unlockAudio`). Wake Lock may need a tap first; the hook retries on the next pointerdown. Keep auto-lock off on phone B anyway.
- `scripts/sync.mjs` (predev/prebuild) copies `radio.jsonl` →
  `lib/radio/fixtures/radio.json`; copies are kept so the app builds alone (Vercel).
