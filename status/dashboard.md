# dashboard — status
Updated: 10:53

## Running
- dashboard on http://localhost:3002 · public: none · **live on Seraph :8000** (`npm run dev`, root `.env` MOCK=0);
  fixtures only with `npm run dev:mock`; Seraph unreachable → fixtures, labelled « Seraph hors ligne »
- public replay (Vercel, deployed by the review session): `MOCK=1`, root directory `dashboard/`, files outside root
  on; `npm run build` copies the fixtures first. Tested as a clean copy (dashboard/ + contracts/, no .env) on :3012.

## Done
- v2, after Amil's review (« trop de bazar ») — minimal, like the reference image:
  - Left: one paper panel — ✱ and 4 controls, the incident as a big title, 2 rows of chips (EXERCICE, origin,
    T+ / clock), the COS decision card only when a gate is pending (Confirmer / Annuler, Space / Esc), then three
    cards: Binôme | Alertes, À l'intérieur (personnes · aide · sans nouvelles), Vues Halo (Seraph → Devin → Halo
    node diagram).
  - Map: the building scheme drawn **with the Halo kit itself** (`halo/kit/`, served read-only at `/api/kit/*`):
    the « Qui est où » floor stack — bands per level, stair shafts, SITAC pictograms, fire/smoke halftone, our
    route up stair A to 3.12. `public/scheme.html`, fed `seraph:state` like a Halo view. Provenance line under it.
  - Bottom: the last 2 radio lines as black-tag captions · Halo as a **landscape** phone (874×402, iPhone in
    landscape): live → `HALO_URL/mirror`; mock → the kit's example for the current moment, labelled « mock ».
  - Top right: the reference's 3 squares (link to Seraph, services, COS).
- v3 (Amil: no metallic gradients, no background squares, no "+" marks): crosses removed everywhere; panel cards
  are flat grey fields; the scheme is flat (kit sheens switched off by CSS in `public/scheme.html`: no `h-g-block`
  fill, no blur/bloom, no smooth fire/smoke layer — halftone dots only); ground = organic dithered pixels, no grid.
- v5 (Amil: exploded axonometric, all levels open and well apart, little text, rotate with the mouse): the centre
  is a three.js exploded axonometric (`components/Building3D.tsx`), built from the state until `building.glb`
  exists — one open floor plate per level (STEP 9 apart), black with thick white edges (fat lines), rooms as low
  black blocks where zones exist, fire room flat red, target room lit, stair cores as small squares on every plate
  (smoky = flat amber), our route as a continuous white line on the target level, people as flat pastilles in their
  room (else along the plate's front edge), tags only « PMR », « ×2 », B1, A/B. Orthographic, no auto-rotation:
  OrbitControls (drag to rotate, wheel to zoom, no pan). Full-height column x 560–1360; radio over Halo on the right.
  No provenance line under it (Amil: no useless text); the Halo phone is captioned « Halo » only.
- v6 (Amil): walls are 2D on each plate (room outlines as flat lines; fire / target / smoke as flat floor fills, no
  extruded blocks); stair shafts run through every plate (4 vertical edges from RDC to the top, white A, amber B),
  plus a flat square on each plate.
- DA pass (brand/index.html, tokens.css): plain black background (Amil removed the ring: nothing behind). Surfaces dark (`.panel`/`.dark` flip the paper tokens: #0b0a0a,
  raised #161514, hairlines), chips and buttons are pills, colours by module: fire/danger Seraph 500, smoke Seraph
  300, people Silex 400, decision Gabriel 400, Rosetta's cards and agents Rosetta 400, structure Halo white.
- Type: title Archivo 520 / wdth 108 / −0.035em (`.t-display`), text Geist 400, labels and figures **JetBrains Mono**
  500 (`.label`, `.t-num`) in **sentence case** — Amil's call, overriding the brand's Geist Mono caps: no forced
  capitals anywhere. No bullets before labels. Custom classes live in `@layer components` so Tailwind utilities
  override them.
- Route line removed from the 3D: `routes[].via` is a list of nodes, and joining them straight crossed walls
  (rule 2). The target room stays lit; the path will be drawn from a computed path when the contract has one.
- Mock: keys 1–4 now switch `halo.current_view.moment`, so the phone shows the kit's view for that moment
  (3 = inside_route: level plan, « Allez en 3.12 par esc. A »). Checked in the browser.
- Callouts after Amil's reference (square marker on the spot, elbow leader, framed label with a light title bar, an
  index, two mono caps lines), in a column right of the building, re-laid out every frame so they follow the
  rotation without overlapping. At most 5: fire, people to reach (needs help / in the target room), a caller heading
  into smoke, engaged teams. The old short tags (×2, B1, PMR) are gone.
  Leaders are light, and dark where they cross the lit room (a dark copy clipped to the room projected on screen).
- Top right: one 64 px screen button (monitor pictogram, status square: grey in mock, red if a core service is down,
  amber if the stream dropped). It switches to the **split view** (Amil's 2nd reference): top half = the 3D framed on
  the level that matters (+ a glimpse of the levels around), title, COS decision card, ≤ 4 callouts; bottom half =
  the six Rosetta screens (`components/RosettaGrid.tsx`: agent-cam frame or last screenshot, pointing crosshair,
  status Live·étape / Terminé / Cache / Échec, duration, thought). Pressing it again goes back. `/#rosetta` opens the
  split view directly. Controls moved to keys: D déclencher, Shift+R rejouer les fixtures, X twice réinitialiser.
  The panel has no logo and no control icons any more; title 78 px; no ↗ arrows. Confirmer: blue pill; Annuler:
  rectangle.
- Fix: the Halo phone got `seraph:state` on every render (each clock tick) → the view redrew every second and
  its animations restarted (« ça clignote »). Now posted only when the state changes (checked: 0 posts in 6 s idle).
- Server routes: `/api/proxy/<service>/...` (SSE passthrough, tested), `/api/health`, `/api/config`,
  `/api/fixtures/...`, `/api/kit/...` (reads `halo/kit/`, fills `{{HALO_KIT_URL}}` in examples).

- Wired to Seraph (05:20): state + SSE through the proxy, verified with `/admin/replay all`. Keys: R = next radio
  line (`/admin/replay_line {id: R01…R12}`), Shift+R = whole incident, A = `/admin/call_now`, D = start, X×2 = reset.
  Seraph's computed `routes[].path` is drawn on `path_level` (white = our way, Silex green = evacuation, dark casing);
  teams on a stair sit on it (« Esc. A »); idle incident shows « En attente d'incident ».

- IFC building (TU Wien, from Seraph 05:40): plates R-1…R+3 each draw their real rooms (terraces dimmer), stair A
  from `stairs[].zones` (outline per level + shaft through all plates), corridors = rooms `corridor:<n>`, teams and
  smoke matched to them.
- Halo phone (live), Halo's protocol: loads `halo.current_view.url` and posts `{type: "seraph:state"}` on each
  state change; `fallback://<moment>` → `HALO_URL/views/<moment>/`; no view yet → the kit's live preview.
- Slabs are the plans (Amil, via the Seraph review): each level is extruded from its real outline
  (`levels[].outline`, list of `{outer, holes}` — also accepts one loop, loops, or one `{outer, holes}`), else the
  union of its room zones (raster union + closing, shafts cut out), never a square. Real scale from
  `model.plan_frame.px_per_m` (1 unit = 1 m; 50 px/m without it); levels spaced by `elevation_m` + 4 m. Stair shaft
  edges run through the holes. The camera fits the model left of the callout column (main view) or centred (split).
  Checked live on TU Wien R-1…R+3, both views.
- Quiet levels are grey (Amil, via the Seraph review): a level with nothing going on has grey slab edges, grey walls,
  a grey label, no fills, no people, no callouts; an active level is full white with its fills and callouts. Active =
  `levels[].focus` when Seraph sends it, else fire/smoke on the level, someone still inside, an engaged team, or a
  route's target (`level:N` / `room:X`). A level that becomes active fades up from grey in 600 ms (lines, fills,
  tags, its callouts). Computed routes are drawn even on a grey level. Checked live and with a forced change.
- Scenario v2 (TU Wien): the active ladder point (the `to` of an evacuation route ending at `ladder:<room>`) is a flat
  Silex-green balcony with a callout « Échelle · <who is heading there> → 2.17 · Balcon »; the other ladder points
  stay plain. Key R walks R00…R15. Seraph's `levels[].focus` is live and used.
- Nobody is drawn outside the building: a person or team whose room is not on the plan (none, or mis-heard like
  « 2 ») goes in their level's corridor, else next to the stair core, else the middle of the slab, spread 1.2 m apart
  while still on the slab; the pastille gets « ? », a callout is titled « Pièce à confirmer ». Checked on the mock
  state (Inès with room « 2 », Sophie with an unknown room): every level's fallback spot is on its slab.
- Fire and smoke only as reported (Amil, via the Seraph review): no hazard in the state → nothing red. A hazard with
  `source.confirmed: false` is a soft fill (fire 35 %, smoke 20 %, smoky stair 35 %) and its callout reads
  « → signalé · <source> »; once confirmed it is solid, « → confirmé · <source> ». No dotted fills (Amil's 3D rule).
- Read from 5 m (Amil, via the Seraph review): a quiet level (focus false, and every level at idle) shows only its
  slab edge, stair core and lift shafts, no room walls. An active level shows faint walls (1 px grey) except the rooms
  that matter: fire/smoke rooms, rooms with people or an engaged team, a route's target or ladder balcony, and the
  entrance halls (`entrances[].leads_to`): full walls (2 px white, red for fire, green for the ladder) and their fills.
  Weights: slab 3.2–3.5 > stair core 2.6 > lift 2.2 > key rooms 2 > other walls 1. Checked at 1920×1080 at idle
  (live) and on the Scenario v2 end state (mock state, R+1 forced quiet); not by a live replay on the shared Seraph.
- Occupant statuses (bug from the first live run, all six showed « sans nouvelles »): `unknown` = « à joindre »
  (listed, no call yet), `calling` = « appel en cours », `no_answer` = « sans nouvelles » (a call rang, no answer).
  Panel « À l'intérieur »: Personnes · Aide · À joindre · Sans nouvelles; only Sans nouvelles turns amber. 3D: à joindre
  = small grey ring, appel en cours = grey ring, sans nouvelles = amber ring. Checked live (6 à joindre, 0 sans nouvelles).
- No air tracking (Amil: « oublie l'air »): no exit time, countdown or « sortie prévue » anywhere. Binôme card = team
  id, level, stair (or room); team callouts read « → engagé ». « Vues Halo » skips team_engaged requests; keys 1–4
  force a Halo moment (team_engaged gone); the mock no longer speaks R03's exit-time line. Air alarms only ever came
  from Seraph's alerts, which Seraph stops sending.
- Jury booth (Amil's plan, via the Seraph review): key E swaps the left panel for « Essayez »: the 5 phrases, the QR
  to the occupants' `/inscription` (from `OCCUPANTS_PUBLIC_URL`; « Lien absent » box when it is empty, never a fake
  QR), the COS decision card if a gate is pending, and each speaker's last line (most recent first, 3 max): the
  transcript, Règles / LLM / Non reconnu and the time from end of speech to Seraph's answer (`metric` voice_to_say:
  `path`, `since_eot_ms`, else `value_ms`, matched by `utterance_id`), the event types when the metric carries
  `events`, and Seraph's answer. The building stays visible; E again goes back.
  Seraph's `events` (d4bb42b, every radio line) show in French: danger signalé ×2, vue Halo, point de situation,
  échange d'équipe…; `said: false` shows « écoute seule » instead of a time.
- LIVE vs REJEU: a pill left of the screen button, always on screen in both views: Live (green) · Rejeu (amber,
  amber border: Seraph /health `replay` is anything but "idle", i.e. from a replay's start until the next reset) ·
  Mock · Hors ligne · Connexion. `/api/health` passes Seraph's `replay` through. The panel's old Mock chip is gone.
- « Lancer l'incident » (Amil, for the demo): a white pill under the title, only while `incident.status` is idle or
  closed; POST Seraph `/incident/start` `{}` (same as key D), gone as soon as the incident is declared. Rendered
  live at idle; not clicked against the shared Seraph (rehearsals).
- « Ce que fait Seraph » (Amil, for the jury): a panel top right of the main view (x 1592–1896, under the badge,
  right of the callout column). First what runs now, pulsing: Rosetta endpoints `running` (said in French per
  endpoint), Gabriel's calls in one line (« En ligne avec 6 personnes, appelle Léa Martin… »), Silex view requests
  `requested`/`building`. Then Seraph's `timeline` newest first, radio lines left out (the captions show them),
  each tagged with its module (call → Gabriel, gate → COS, alert → Alerte). Hidden while there is nothing. Checked
  with the fixture state through a temporary hook (removed).
- Fix (Amil: « une barre noire » at the right when zooming the 3D): the main view's canvas covered only x 560–1360,
  so a zoomed model stopped dead at 1360. `Building3D` takes `full` (the area the canvas covers) apart from `box`
  (where the model is framed); the main view passes the whole stage, framing unchanged. Zoomed, the model now runs
  on under the panel and Halo.
- Public replay link (Amil, via the Seraph review): the dashboard plays the fixtures with no service and no repo
  around it. `scripts/replay-files.mjs` copies what mock loads (state-sample, radio, calls, endpoints) from
  contracts/fixtures to `public/fixtures/` before every build (`npm run build`; gitignored). `--snapshot` (by hand,
  `npm run snapshot`) copies the Halo kit to `public/halo-kit/` and the first shot of each endpoint fixture from
  rosetta/shots to `public/shots/` (committed: halo/ and rosetta/ are not deployed). In mock: `/api/config` says
  where the fixtures are (`/api/fixtures` when contracts/ is beside the app, else `/fixtures`) and gives no service
  URL; `/api/health` asks no service; Rosetta shots are rewritten to `/shots/…` (dispatch.write_112's has no file:
  « Pas d'image »); Halo plays `/halo-kit/examples/<moment>.html` for the three kit moments, else « Vue de secours »;
  the badge says « Rejeu » (amber); no QR in the booth; if the fixtures fail the panel says « Rejeu indisponible »
  instead of waiting. next.config.ts untouched (a change restarts the projector's dev server).
- Fix (Amil: « l'UI est cassée », the replay's panel): « Feu de véhicule en parking souterrain » took 4 lines at
  78 px and, over a pending decision, pushed « Vues Halo » 76 px out of the panel. The title is now fitted on
  mount, on a new title and whenever another panel block changes size: 78 px down to 48 px (2 px steps) until it
  holds in 3 lines, no word is wider than the panel and the last card ends inside; still too long at 48 px → cut at
  3 lines (…). Parking fire: 64 px, 3 lines. « Feu d'appartement »: 68 px (at 78 px « d'appartement » ran past the
  panel's right edge). Booth (E): three turns under a decision ran 246 px out; the turns list now takes the room
  left and shows whole cards only, newest first (column-wrap + overflow hidden). Checked on a mock copy (:3012,
  fixture state, then a 94-char title, « Désincarcération », three seeded turns) and live on :3002.

- Judges' tour (Amil, from the « Démo avec les jurys » session, 13:05): `components/Tour.tsx` + `components/Flamme.tsx`.
  First visit in a browser on the public replay → « Bienvenue sur Seraph », then 9 steps; white corner target that
  breathes; the flame (Bloub engine, MIT, copied in `lib/bloub/`, flame body in `flamme.ts`) takes each module's
  colour, eyes always wide open and on the cursor. Live projector: only with `?tour` or key T. Anchors: `data-tour`
  on the panel title, every `Card` (by title), Radio, HaloPhone, ScreenButton, Activity — keep them.

## In progress
- Click-to-expand layouts (details per card / per level) — to design with Amil.

## Blocked
-

## Requests (to other sessions or Amil)
- Amil (`contracts/types.ts`): add what Seraph already serves and the dashboard reads — `Route.path?: [x, y][]`,
  `path_level?`, `path_image_id?`; `rooms[].kind` (room|corridor|elevator|exterior); `stairs[].zones` ({level, zone}[]);
  `levels[].outline?: {outer, holes}[]`, `levels[].focus?: boolean`, `focus_reasons?: string[]`;
  `building.model.plan_frame.px_per_m`.
- Amil (`contracts/api.md`): document `/admin/replay_line`, `/admin/call_now` (used on keys R and A).
- Amil / @replicas: the booth QR needs `OCCUPANTS_PUBLIC_URL` in the root `.env` (empty now; talkie's /qr shows a
  placeholder too). The occupants replica listens on 127.0.0.1 only, so a LAN URL would not work either.

## Facts I verified (API names, model ids, gotchas)
- Files outside the Next project (../contracts) reach a Vercel function only through `outputFileTracingRoot` +
  `outputFileTracingIncludes` (Next docs, output.mdx). Not used: static copies under public/ need no tracing and no
  next.config change.
- Next 16 dev blocks `/_next/hmr` and dev fonts for any origin but localhost: opened by the LAN address
  (projector, phone) the page never hydrates and stays on « Connexion à Seraph… ». Fixed with `allowedDevOrigins` =
  this machine's IPv4 addresses + hostname + `*.local` (next.config.ts; the dev server restarts by itself).
  `/api/config` swaps `localhost` for the Host header the browser used, so Seraph / Halo / Rosetta URLs work remotely.
- Headless Chrome `--virtual-time-budget` never finishes on the live page: the open SSE keeps it busy. Use the
  browser pane, or `/#rosetta` + mock for stills.
- Right after a dev-server restart the first proxied POST can fail while the route compiles; the 502 now carries
  `detail`.
- Next 16.4 + `cacheComponents`: no `Date.now()` during render of client components (prerender error).
- `RouteContext<"/api/...">` types need `next typegen` (or `next dev`) before `tsc`.
- `create-next-app` runs `git init` inside the app: removed `dashboard/.git`.
- Halo kit labels clamp to the kit's scene (`Halo.W × Halo.H`): draw in that frame and scale the SVG, never a
  bigger viewBox.
