# halo — status
Updated: 04:25

## Running
- Kit preview (dev only): `python3 -m http.server 3091 --bind 127.0.0.1 --directory <repo>` →
  http://localhost:3091/halo/kit/examples/ (gallery + live controls) · `?v=approach|inside_route|occupants|team_engaged`
  shows one scheme full screen (phone / simulator). MOCK: fixture state, times made live.
- Native preview on the simulator: `halo/dev/ios-preview/build.sh` → full-screen WKWebView app (`fr.seraph.halo-preview`),
  `SIMCTL_CHILD_HALO_URL=<url> xcrun simctl launch <udid> fr.seraph.halo-preview`.
- Live: `?live=http://localhost:8000` on the preview follows Seraph's SSE (`state`, `halo_view`); in single view
  mode the screen follows Seraph's moment. Checked with `/admin/replay` on the simulator.
- Halo shell (native app, React Native): not started. Must handle `fallback://<moment>` (« vue de secours »),
  POST /halo/tap, and send state to the WebView as a JSON string (the kit parses strings).

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

## In progress
- Nothing. Next for the halo session: the native shell (React Native, WebView host, SSE, fallback view, alerts).

## Blocked
-

## Requests (to other sessions or Amil)
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
