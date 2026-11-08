# dashboard — status
Updated: 05:20

## Running
- dashboard on http://localhost:3002 · public: none · **live on Seraph :8000** (`npm run dev`, root `.env` MOCK=0);
  fixtures only with `npm run dev:mock`; Seraph unreachable → fixtures, labelled « Seraph hors ligne »

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
- Mock: keys 1–5 now switch `halo.current_view.moment`, so the phone shows the kit's view for that moment
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
- Rosetta removed from the screen for now (next step). Data layer still has the agent-cam WS for later.
- Server routes: `/api/proxy/<service>/...` (SSE passthrough, tested), `/api/health`, `/api/config`,
  `/api/fixtures/...`, `/api/kit/...` (reads `halo/kit/`, fills `{{HALO_KIT_URL}}` in examples).

- Wired to Seraph (05:20): state + SSE through the proxy, verified with `/admin/replay all`. Keys: R = next radio
  line (`/admin/replay_line {id: R01…R12}`), Shift+R = whole incident, A = `/admin/call_now`, D = start, X×2 = reset.
  Seraph's computed `routes[].path` is drawn on `path_level` (white = our way, Silex green = evacuation, dark casing);
  teams on a stair sit on it (« Esc. A »); idle incident shows « En attente d'incident ».

## In progress
- Click-to-expand layouts (details per card / per level) — to design with Amil.

## Blocked
-

## Requests (to other sessions or Amil)
- @halo: the dashboard draws its scheme with your kit (floorStack, marker, fire, smoke, arrow, label) in the
  874×402 scene. `ground` is no longer exported, so `public/scheme.html` re-draws the same dot matrix full screen;
  if you export `ground(canvas, {box, scale})` again I'll switch to it. Amil rejected smooth gradients and blur
  (« dégradés métalliques ») and the grid of blocks in the ground: the dashboard turns them off on its side; the
  Halo views in the phone mirror still show them.
- Amil / @seraph (same as @halo's request): add `routes[].path` — the route as points on the level plan's 0–1000
  frame, through the door centres, computed in code on the IFC graph. Without it, neither the dashboard nor Halo can
  draw a route that does not cross walls. Seraph should also switch Halo to `inside_route` when a team is engaged on
  a level (briefs/seraph.md « Moments → Halo »).
- @halo: `examples/approach.html` still calls `Halo.big` (removed from the kit) → TypeError in the phone mirror.
- @seraph / Amil: « Appeler maintenant » has no endpoint in `contracts/api.md` (button disabled). Proposal:
  `POST /admin/call_now`.
- @seraph / Amil: key `R` should replay one fixture line; `/admin/replay` only takes `fixture` + `speed`.
- @seraph: with IFC rooms, keep `plan.points` for stairs (`stair:A`…) and `room:<id>` so the scheme can place people.

## Facts I verified (API names, model ids, gotchas)
- Headless Chrome `--virtual-time-budget` never finishes on the live page: the open SSE keeps it busy. Use the
  browser pane, or `/#rosetta` + mock for stills.
- Right after a dev-server restart the first proxied POST can fail while the route compiles; the 502 now carries
  `detail`.
- Next 16.4 + `cacheComponents`: no `Date.now()` during render of client components (prerender error).
- `RouteContext<"/api/...">` types need `next typegen` (or `next dev`) before `tsc`.
- `create-next-app` runs `git init` inside the app: removed `dashboard/.git`.
- Halo kit labels clamp to the kit's scene (`Halo.W × Halo.H`): draw in that frame and scale the SVG, never a
  bigger viewBox.
