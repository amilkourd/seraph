# halo — status
Updated: 06:00

## Running
- Kit preview (dev only): `python3 -m http.server 3091 --bind 127.0.0.1 --directory <repo>` →
  http://localhost:3091/halo/kit/examples/ (gallery + live controls) · `?v=approach|inside_route|occupants|team_engaged`
  shows one scheme full screen (phone / simulator). MOCK: fixture state, times made live.
- Native preview on the simulator: `halo/dev/ios-preview/build.sh` → full-screen WKWebView app (`fr.seraph.halo-preview`),
  `SIMCTL_CHILD_HALO_URL=<url> xcrun simctl launch <udid> fr.seraph.halo-preview`.
- Live: `?live=http://localhost:8000` on the preview follows Seraph's SSE (`state`, `halo_view`); in single view
  mode the screen follows Seraph's moment. Checked with `/admin/replay` on the simulator.
- **Halo native app** `halo/app/` (Expo SDK 58, RN 0.88): `cd halo/app && npx expo start --port 8083 --lan` →
  Expo Go `exp://<laptop LAN IP>:8083` (here 172.16.0.13). Finds Seraph (:8000) and the kit server (:3001) on the
  same host as Metro; override with EXPO_PUBLIC_SERAPH_URL / EXPO_PUBLIC_KIT_URL.
- **Kit server** `node halo/server.mjs` → :3001 on every interface: `/kit/*` (CORS open) and `/views/<moment>/`
  (kit example served like Silex: `{{HALO_KIT_URL}}` replaced) = stand-in views until Silex serves Devin's.

## Done
- Halo scheme design language, from Amil's reference (dot-matrix ground, white outlines, black label tags, lit
  halftone target), landscape iPhone. Colour = SITAC code: red fire, blue water, green people, orange risks, amber
  warning, white structure/crews. Inferred = dotted + `~`.
- `halo/kit/halo.css` (tokens, landscape frame, motion), `halo/kit/halo-kit.js` (contract primitives + `warn`
  blinking triangle, `ping`, `cross`, `wind`, `north`, `scene` rotation, halftone `fire`/`smoke` gradients,
  `countdown` dial), `halo/kit/README.md` (API for Devin).
- Reference schemes from `contracts/fixtures/state-sample.json`: `examples/approach.html`, `inside_route.html`,
  `occupants.html`, `team_engaged.html`. Checked in the built-in browser at 874×402 and in iOS Simulator Safari
  (iPhone 17 Pro, landscape).

- 03:20 redo after Amil's review: **full screen, no text panel**, tags only, approach turned 45° like the reference,
  bigger shapes, organic dot ground, the drawing always fits. Kit speaks to a React Native WebView
  (`window.ReactNativeWebView.postMessage`, string messages). Checked on the iPhone 17 Pro simulator in the native
  preview app, all four schemes.

- 04:50 native shell, checked on the iPhone 17 Pro simulator in Expo Go against live Seraph (replay, TU Wien
  building): SSE state ≤ 4/s streams into the WebView (`postMessage` JSON string on each state change); `fallback://`
  → native « vue de secours » (big one-line facts per moment); with stand-ins on (default, long-press the status
  line to toggle) the kit example for the moment swaps in (crossfade 300 ms + haptic on `seraph:ready`); the view
  follows Seraph's moment; alert banner 8 s + haptics + sound, list behind a tap on the top bar; taps reach Seraph
  (timeline « Halo : tap occupant OCC-01 »). Landscape lock, keep-awake, status bar hidden, no zoom/bounce.
  Top bar EXERCICE · clock · connection dot (white = live, red ring = offline); status line « Vue de secours » /
  « Exemple » / « Devin HH:MM » · provenance (« IFC réel » / « bâtiment fictif »).
- Kit views adapted to the IFC building (`building.model`): approach draws the real footprint (hull of ground-floor
  zones), entrances at `plan_point`, stair zones, the fire room; inside_route uses IFC zones, stair zones per level,
  cuts multi-level paths at the stair, dims terraces. Both still work on the fixture building.

- 05:00 approach redone after Amil's review (relayed): one frame per drawing, never mixed (IFC ground-floor frame:
  `levels[0].outline` [{outer, holes}], doors at `plan_point`; truck/hydrant drawn only if on that frame, else words
  in the card); big animated arrow from outside onto the chosen door; no interior on the top view (stair and fire go
  in the card); other entrances dimmed, crossed only if blocked or leading to a hazard; key line 28 px white.
  Kit: tags never overlap (slide, else dropped), at most 16 per screen. inside_route: a team on a stair shares its tag.
  Checked on the simulator with the TU Wien building.

- 05:05 after Amil: text never blinks (card, air dial numbers); only the first drawing animates in (redraws on
  state updates are still: texts were flashing 4×/s); card shows without fade (WebKit left it stuck at opacity 0);
  no black box behind plans; occupants redone (people in a row per floor, most urgent first, room tag each, hazards
  as one pictogram, team on the stair shaft); floors with nothing special are grey: `Halo.focusLevels(state)` reads
  `building.levels[].focus` when Seraph sends it, else fire/smoke, people inside, engaged team, route target.
  The app no longer flashes the vue de secours while a view loads; view JS errors are logged in Metro.

- 05:20 scenario v2 (TU Wien, fixture 1327e74): approach on ONE frame (the truck spot's top view, earth-top-01; only
  points on that image; building = `building.footprint` on that image if Seraph sends it, else a block through the
  doors), framed on doors/truck/hydrant so the arrow is big; E2 crossed (smoke on E2). Ladder points: kit
  `Halo.ladderPoints(state, level)` (+ `ladder` pictogram), dim, white when an evacuation route ends there;
  occupants shows « 2.16 → échelle »; inside_route draws Seraph's per-level path as is. Seraph's
  `levels[].focus` is read by `Halo.focusLevels`. Checked on the simulator (native preview) with the fixture.

- 05:50 Amil's rule (relayed): fire and smoke only once reported, always with their source. Kit: `Halo.fire/smoke(svg,
  zone, {hazard})` (reported = dotted, softer, « ~ » tag; confirmed = solid), `Halo.hazardsAt`, `hazardTag`
  (« confirmé · Tête »), `hazardSource` (« Tête », « B1 », « appel », « alerte »), `hazardLine(state, h)` for card text.
  Stair smoke only from a hazard, not from `stairs[].status`. RULES.md 16; check-view rejects a fire/smoke drawn
  without its hazard and any typed « Feu », « Fumée » or level name. Tags also avoid marker discs; cap 16.
  Native vue de secours builds hazard lines the same way.

- 06:00 air tracking cut (scenario v2, 806c92a): `team_engaged` example parked in `halo/kit/examples/parked/`,
  removed from the preview harness and the app's stand-ins; the vue de secours shows a team as a position only.
  `Halo.countdown` / `teamCard` stay in the kit, unused.

## In progress
- **Phone A**: not run yet on the real phone (needs Amil): Expo Go from the App Store, same Wi-Fi as the laptop,
  open `exp://172.16.0.13:8083` (or scan the QR), allow « Local Network ». Plain http over the LAN is fine in Expo Go
  (its ATS allows it; `app.json` sets NSAllowsArbitraryLoads + NSAllowsLocalNetworking for a dev build). No
  cloudflared needed on the same Wi-Fi. A signed dev build (`npx expo run:ios --device`) needs Amil's Apple ID in
  Xcode: not tried. **The blue gear is Expo Go's dev-tools button**: it does not exist outside Expo Go. For the demo, either
  hide it from Expo Go's dev menu (shake the phone → tools button setting; not verified here), or install a real
  build: `cd halo/app && npx expo run:ios --device --configuration Release` (needs Amil's Apple ID in Xcode).

## Blocked
-

## Requests (to other sessions or Amil)
- @dashboard: the native app has no /mirror URL. Render `halo.current_view.url` yourself with the same protocol:
  iframe/WebView of the url, post `{"type":"seraph:state","state":…}` (object or JSON string) on every state change,
  listen for `seraph:ready` / `seraph:tap`; for `fallback://<moment>` either show your own facts or load the kit
  stand-in `http://<host>:3001/views/<moment>/` (what the phone shows while Silex is down). Your current approach
  (`halo/kit/examples/index.html?v=<moment>&live=…`) keeps working.
- @seraph: on the IFC building, `routes[].path` mixes frames (evacuation tail ends at the fixture's (130,260)) and
  spans levels while `path_level` is one level; the approach path doesn't start at the chosen entrance. Halo copes
  (cuts at the stair, falls back to door → stair) but a per-level path would be cleaner. `building.plan` is still
  the fixture plan while `building.model` is set: Halo ignores it then.
- @Amil: `docs/05-halo.md` (Look) and `contracts/halo-views.md` (Look line) still say « Pip-Boy phosphor green,
  portrait 390×844 ». The kit now implements: black + dot-matrix + white outlines, SITAC colours, landscape iPhone.
  Please update those lines (now: full screen, landscape, no text panel); `halo/kit/README.md` has the wording.
- (done by @seraph) `routes[].path` + `path_level`: `inside_route` draws it as is; falls back to the evacuation route
  when there is no `to_victim` route.
- @silex: put `halo/kit/RULES.md` verbatim in every Devin message (Amil's hard rules), point Devin at
  `halo/kit/README.md` + the four `examples/*.html`, and run `node halo/kit/check-view.mjs views/<id>/index.html`
  before serving: exit 1 = send the errors back to Devin, never serve it.

## Facts I verified (API names, model ids, gotchas)
- Chromium blocks an opaque-origin iframe (`sandbox="allow-scripts"`) from loading scripts from another localhost
  origin (private network access). Not an issue over HTTPS tunnels or on iOS Safari. Harness uses
  `allow-same-origin`.
- One shared SVG mask with a 5000×5000 dot pattern renders nothing in Chromium; masks are sized per element.
- `env(safe-area-inset-*)` is 0 inside an iframe: the shell must keep the iframe in the safe area.
- iOS Safari landscape toolbar leaves ~297 pt of height on an iPhone 17 Pro; the kit's compact mode (`max-height:
  340px`) keeps all rail facts visible. Standalone (home screen) gives the full 402 pt.
