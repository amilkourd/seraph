# Halo kit

Building blocks for Halo schemes (the views Devin builds through Silex). Vanilla JS, no build step, global `Halo`.
A view loads `{{HALO_KIT_URL}}/halo-kit.js` and `{{HALO_KIT_URL}}/halo.css` and nothing else.

**Read `RULES.md` first.** Every view must pass `node halo/kit/check-view.mjs <view.html>`.

Start from an example, never from scratch: `examples/approach.html`, `inside_route.html`, `occupants.html`,
`team_engaged.html`. Preview: `examples/index.html` (all four, with live state buttons) or `?v=<view>` full screen.

## The look

**Full screen, landscape, one scheme, almost no text.** A grainy dark ground, clean shapes with thin white outlines,
small black tags (`E2`, `3.12`, `B1 · R+3`). **Where we go is plain white** with a soft glow. Grain only on the ground
and inside fire/smoke; never on shapes or roads. Draw inside `Halo.AREA`; the right side holds the instruction card. The approach is turned 45° like the reference (`Halo.scene`). Gabriel says the words;
the screen shows the picture.

| Colour (SITAC) | Used for |
|---|---|
| white | structure, our route, our crews, numbers |
| red | fire, danger, person who needs help, crossed-out entrance |
| amber | smoke, warning, inferred (`~`, dotted) |
| orange | gas, electricity |
| blue | hydrant, dry riser |
| green | people |
| grey | unknown, no news |

Motion only where something happens: chevrons flow along the route · rings ping on the one place to go · triangles
blink on dangers (amber slow, red fast) · fire flickers · smoke drifts · the air dial's ticks go dark. Buildings, roads,
the lit target and the ground never move (outlines draw once on arrival, that's all).

Rules: tags only, short, ≥ 22 px · one instruction card, 2–4 lines, one line each, imperative (« Entrez par E2 ») · positions and routes come from the state ·
inferred = dotted + `~`.

## API

```js
const f = Halo.frame(document.body, { title: "Par où j'entre" });   // full screen; { svg, W: 874, H: 402, panel(), clear() }
Halo.scene(f.svg, { rotate: -45 });                                   // optional: diagonal composition
Halo.onState(state => { f.clear(); /* draw in Halo.AREA */ f.panel([{ icon: 'door', text: 'Entrez par E2' }]); });
Halo.ready();
```
Draw in scene coordinates (874×402). The drawing always fits the screen; the ground fills it edge to edge. With a
scene rotation, streets/blocks/hazards/routes turn; markers and tags stay upright.

| Call | Draws |
|---|---|
| `street(svg, {from, to, width})` | flat grey band, thin kerbs |
| `block(svg, area, {state, label, at, big, tap})` | footprint: `normal` · `target` (lit) · `inferred` · `dim` |
| `plan(svg, {image_url, zones, points, box})` | level plan on the 0–1000 frame; returns `{project(p), zone(id)}` |
| `floorStack(svg, {box, levels, stairs, highlight})` | side section; returns `{band(level), shaft(id)}` |
| `facade(svg, {box, levels, entrances})` | front elevation |
| `fire(svg, area)` · `smoke(svg, area)` | animated grainy gradients |
| `arrow(svg, points, {tone, width, gap})` | route; `gap` stops short of the marker at the tip |
| `marker(svg, kind, point, tag, {tone, ring, ping, blink, crossed, big, at, r, tap})` | pictogram: `door stair elevator riser hydrant truck person wheelchair team gas elec fire smoke unknown` |
| `warn(svg, point, {level: 'warn'|'danger'})` | blinking triangle |
| `ping` · `cross` · `north` · `wind` | « here » rings · crossed out · north arrow · wind chevrons |
| `label(svg, point, text, {big, tone, source})` | black tag |
| `countdown(svg, exit_by, {start, label})` | air dial, white → amber T-5 → red « SORTEZ » |

Areas: `[[x,y]…]`, `{x,y,w,h}` or `{cx,cy,r}`. Helpers: `project`, `byId`, `levelLabel`, `time`, `tap`, `onAlert`.

## Shell

Works in an `<iframe>` (web) and in a React Native WebView (native): the kit reads string or object messages and
posts back with `window.ReactNativeWebView.postMessage` when it exists. `halo/dev/ios-preview/` is a native
full-screen WebView app for the simulator (`build.sh`).
