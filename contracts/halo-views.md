# Halo views — the contract between Seraph, Silex, Devin and Halo

Halo shows **the right thing at the right moment**. Nothing is prebuilt except the plain fallback. Seraph decides
the moment, Silex has Devin build the view, Halo displays it and feeds it live state.

## Lifecycle
1. Seraph detects a moment (`types.ts → Moment`) and sends Silex a `ViewRequest` with: purpose, the state paths it
   needs, Rosetta screenshots as **visual references**, interactions, and a deadline.
2. Meanwhile Halo shows the **fallback view** for that moment (built into the Halo shell: a clean list of the facts,
   labelled « vue de secours »). The crew is never without information.
3. Devin writes `views/<view_id>/index.html` (+ `view.json`). Silex serves it and tells Seraph `ready`.
4. Seraph sets `halo.current_view`; Halo swaps the iframe (short flash + vibration), sends the current state.
5. The view updates itself on every `seraph:state` message. No rebuild for data changes. A new Devin build only
   happens for a new moment or when the commander asks for something different (« ajoute la pression »).

## A view = one folder
```
views/<view_id>/
  index.html     self-contained: inline CSS/JS, loads the kit from {{HALO_KIT_URL}} (Silex replaces it when serving)
  view.json      { view_id, moment, title_fr, purpose_fr, data_keys, references: [image_id], built_by: "devin",
                   devin_session_url, created_at }
```
Rules for every view:
- Loads `{{HALO_KIT_URL}}/halo-kit.js` and `{{HALO_KIT_URL}}/halo.css`, nothing else from the network.
- Listens to `message` events: `ShellToView` (`types.ts`). Sends `{type:"seraph:ready"}` once mounted.
- Renders a **simple animated scheme**, not raw data: blocks, a street, stairs, floors, people, smoke, an arrow.
  Uses the screenshots only as a reference for shapes and layout (the facade's proportions, where the side door
  is), never as a background photo, except `plan` views which may show the plan image dimmed under the zones.
- **Draws positions and routes exactly as given in the state** (`building.*.point`, `building.rooms[].zone`,
  `routes[]`). It never invents a position or a path.
- Every element shows its `source.label` (small tag), and inferred facts (`confirmed:false`) look different.
- Taps send `{type:"seraph:tap", target}`; the view never calls Seraph directly.
- Phone A in portrait, ~390×844, held on the forearm: one idea per screen, readable at arm's length, huge type,
  high contrast, works in sunlight and smoke. No scrolling. No text paragraphs.

## The Halo kit (`halo/kit/`, owned by the `halo` session)
The kit gives Devin ready primitives so a view is ~150 lines and looks consistent. `halo/kit/README.md` is the
authoritative API; this is the minimum it must offer:

| Primitive | Draws |
|---|---|
| `Halo.frame(el, {title, subtitle})` | the screen frame, header, clock, source legend |
| `Halo.street(svg, opts)`, `Halo.block(svg, opts)` | street and building footprint, top view |
| `Halo.facade(svg, {levels, entrances})` | building front, simplified, from the reference proportions |
| `Halo.floorStack(svg, {levels, occupantsByLevel, hazards, highlight})` | side view, one band per level |
| `Halo.plan(svg, {image_url, zones, points, dim})` | plan view with zones |
| `Halo.arrow(svg, pathPoints, {animate:true})` | animated route arrow along given points |
| `Halo.marker(svg, kind, point, label)` | door, hydrant, truck, person, team, stair, riser |
| `Halo.smoke(svg, zoneOrBox)`, `Halo.fire(...)` | hazard shading |
| `Halo.teamCard(el, team)`, `Halo.countdown(el, exit_by)` | ARI team tracking, exit countdown (cut from the demo with ARI) |
| `Halo.tag(el, source)` | source tag (confirmed vs inferred style) |
| `Halo.onState(fn)`, `Halo.tap(target)`, `Halo.ready()` | messaging helpers |
| `Halo.project(point, box)` | maps an `ImagePoint` (0–1000) into an SVG box |

Look: Pip-Boy spirit (phosphor green on near-black, monospace caps), but legibility first: amber for warnings, red
for danger, white for key numbers. Large hit areas.

## Moments and what the view should show (guidance for Seraph's `purpose_fr`)
| Moment | Trigger | The one idea on the wrist |
|---|---|---|
| `approach` | first good `maps.building` + `approach` computed | « Par où j'entre » : block, street, truck spot, arrow to the chosen entrance, hydrant |
| `inside_route` | IFC level plan or `plan.read` ready + a route to a victim or level | « Par où je monte » : plan zones, smoke shaded, arrow along the route, stair status |
| `occupants` | 2+ calls with facts | « Qui est où » : floor stack, people per level, trapped/needs help highlighted, active ladder point (`to` of an evacuation route ending in `ladder:`) |
| `team_engaged` | **cut** (ARI air tracking, roadmap; `ARI_ENABLED` off) | was « Mon air » : team cards, countdown to exit_by, alarm at T-5 min |
| `commander_request` | radio « Seraph, il me faut … sur Halo » | whatever was asked, same rules |
