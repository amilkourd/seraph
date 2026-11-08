# Brief — `talkie` session · `talkie/` · Next.js :3000

Read first: `CLAUDE.md`, `contracts/README.md` (LiveKit rooms, data topics), `contracts/api.md` (talkie section).

## Goal
1. `/` — the crew radio on phone B: one screen, one huge button, it must feel like a radio.
2. `/call?occ=<id>` — web call page for occupants (fallback for real phone calls, and for visitors).
3. `/qr` — shows the QR code to the occupants replica's `/inscription` page (env `OCCUPANTS_PUBLIC_URL`).

## Crew radio (`/`)
- Pick a call sign (COS, Tête, Binôme 1, Binôme 2, or free text) → « Rejoindre le canal » (also unlocks audio on
  iOS) → room `crew` via `/api/token` (`livekit-server-sdk`, env `LIVEKIT_*`).
- Dark full screen. Top: « CANAL CREW » + call sign + EXERCICE. Center: round hold-to-talk button (~60% width).
  Under it: the last thing Seraph said (data topic `seraph`).
- States: idle green « Maintenir pour parler » · talking red « EN ÉMISSION » + seconds · receiving amber « Seraph
  parle… » / « Tête parle… », locked · disconnected grey « Reconnexion… ».
- Hold: unmute mic, set attribute `talking=true`, chirp. Release: mute, `talking=false`, send `{kind:"eot",
  speaker}` on topic `ptt`, roger beep. First press wins: lock when someone else has `talking=true`.
- Received audio through a light radio filter (band-pass 300–3000 Hz + faint noise), squelch click at start/end.
- Wake Lock, no zoom, big targets. Works on iOS Safari and Android Chrome over HTTPS (`TALKIE_PUBLIC_URL`).

## Web call (`/call?occ=…`)
- Big « Appeler les pompiers (exercice) » button → `/api/call-token` creates room `call-<id>`, dispatches a Gabriel
  call agent (LiveKit agent dispatch API), returns a token. Full-duplex audio (not push-to-talk), « Raccrocher »
  button, shows « Vous parlez à Gabriel, assistant vocal (exercice) ».
- Without `occ`: an incoming « 112 » web call (direction `in`).

## Done when
Two phones talk on `crew` with the radio feel and the floor lock; Gabriel's speech arrives and its text shows; a
web call connects to a Gabriel call agent.
