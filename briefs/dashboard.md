# Brief — `dashboard` session · `dashboard/` · Next.js :3002 (the projector)

Read first: `CLAUDE.md`, `docs/01-architecture.md`, `docs/03-demo-script.md`, `contracts/api.md` (SSE events,
Rosetta cam WS, Silex sessions), `contracts/types.ts`.

## Goal
In 3 minutes the jury must see: the radio becomes facts, the people inside become dots, Rosetta's agents working real
screens, Devin building the wrist view, and the commander deciding. 1920×1080, dark, French, readable from 5 m
(min 20 px body). Data: `EventSource(SERAPH_URL/stream?client=dashboard)` + `GET /state` on load,
`WS ROSETTA_URL/ws/cam`, `GET SILEX_URL/sessions` (poll 2 s).

## Layout
- **Top bar:** « EXERCICE — Feu de local technique, R+3 », address, clock, incident status, health dots for every
  service (green/amber/red, `GET /health`).
- **Left column (30%) — Radio et appels:** crew channel transcript (speaker chip, time, text; Seraph's lines in a
  different colour, spoken source « selon l'appel ») · calls board (one card per call: occupant, language flag,
  status ringing/active/ended/no answer, live one-line summary; sorted by `urgency.level`, 3 first, then
  fact-urgent before `raised_by_voice`, then newest; urgency chip « urgent / à suivre / hors danger »; when
  `voice.emotion` is distress, fear or pain, a tag « détresse / peur / douleur · selon la voix » in the inferred style, Gladia as source) · pending gates pinned on top with big
  « Confirmer » / « Annuler » buttons and the exact sentence that will be said.
- **Center (40%) — Le bâtiment:** 3D building from `building.model.glb_url` (three.js + GLTFLoader; levels slightly apart, slow orbit, rooms coloured by
  hazard, people dots and teams on their level, provenance label; the side-view floor stack is the fallback) and, below,
  the Halo mirror (`HALO_URL/mirror` in an iframe, phone-shaped frame) with « Vue construite par Devin à … ».
- **Right (30%) — Rosetta et Silex:** agent cam tiles (one per running endpoint: live screenshot, action, thought,
  LIVE or CACHE badge, duration) · the endpoint counter « 8 sources sans API → 8 endpoints » · Silex/Devin sessions
  (kind, purpose, elapsed, link) · the screenshots gallery (references sent to Devin).
- **Bottom strip:** metrics (voice → crew X s, call → crew X s, request → view X min), alerts ticker.

## Controls
« Déclencher l'incident » (`POST /incident/start`), « Appeler maintenant » (re-place calls to opted-in visitors),
« Réinitialiser » (`/admin/reset` everywhere), « Rejouer » (fixtures replay). Keys from `docs/03-demo-script.md`:
`V C F G R`, plus `Space` = confirm the latest gate, `Esc` = cancel it, `1–5` force a Halo moment (`/admin/moment`).

## Pages
`/` the main screen · `/eval` reads `eval/results.json` · `/qr` big QR to `/inscription`.

## Done when
Seraph's fixture replay animates every panel correctly; with live services, agent cams move and the Halo mirror
swaps when a Devin view lands; it reads well on the venue projector.

## IFC — `docs/10-ifc.md`
Load `building.glb` from `GET {SERAPH_URL}/building/files/building.glb`; storey nodes are named `L<n>`. Colour rooms
from `state.building.hazards`; show `building.model.provenance_fr` under the model. Fallback: the side view.
