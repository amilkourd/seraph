# Silex → Devin: build one Halo view

You build **Halo views** for Seraph, an AI copilot for firefighters (hackathon demo, an EXERCISE). Halo is a phone
strapped to a firefighter's forearm, in landscape (874×402). A view is one self-contained HTML file that draws one
simple scheme for one moment of the intervention (« Par où j'entre », « Mon air »…) with the **Halo kit**, and
redraws itself on every live state update. The firefighter glances at it for one second, wearing gloves.

You cannot reach our laptop. Everything you need is in this message and in the attachments:
`halo-kit.js` and `halo.css` (the kit), `check-view.mjs` (our validator), `examples/*.html` (four reference views),
and, per request, `state.json` (the full live `IncidentState`) and reference images.

## How to work (speed matters: the crew is driving to the fire, the view must land in minutes)
1. Start from the closest example (`approach.html` for « approach », `team_engaged.html` for « team_engaged »,
   `occupants.html` / `inside_route.html` otherwise). Copy it, then adapt it to the request. Do not start from scratch.
2. Use only the kit (global `Halo`, API in the README below). No other library, no network, no style of your own.
3. Draw only from the state: every position, route, stair, entrance, level and person comes from `state`. Never
   invent one, never hard-code an id from an example (the building changes: today it has **one stair, A**; there is
   no stair B). If a field is missing, draw less, never guess.
4. Keep `{{HALO_KIT_URL}}` exactly as is in the two kit tags; Silex replaces it when serving.
5. Check it yourself before answering: put `halo-kit.js`, `halo.css`, `check-view.mjs` next to your file and run
   `node check-view.mjs index.html` (must print ✓). If you can, open it in a browser with the kit and post
   `{type:"seraph:state", state}` from `state.json` to make sure it draws without a JS error. Don't spend more than
   a minute or two on checks.
6. Answer through the **structured output** `{request_id, view_id, html, notes}`: `html` is the whole file,
   `notes` one short English line on what you drew. Don't open a PR, don't create a repository, don't ask questions:
   if something is unclear, pick the simplest option that follows the rules and say it in `notes`.

## Contract (from contracts/halo-views.md)
- Loads `{{HALO_KIT_URL}}/halo-kit.js` and `{{HALO_KIT_URL}}/halo.css`, nothing else from the network.
- Listens with `Halo.onState(fn)` and calls `Halo.ready()` once mounted (it posts `seraph:ready`). The view must
  survive repeated state updates (`f.clear()` then redraw, or update in place) and partial states.
- Taps: `tap: {kind, id}` options on kit calls (`kind` ∈ level, room, stair, entrance, team, occupant, hydrant).
  The view never calls Seraph directly.
- Positions and routes exactly as given in the state (`building.*.plan_point`, `building.rooms[].zone`,
  `building.stairs[].zones`, `routes[].path` on the frame `routes[].path_image_id`, level `path_level`).
- UI text in French, radio style: short, imperative, no politeness. Tags only (`E1`, `3.12`, `B1 · R+3`).
- File size well under 200 KB (aim for ~150 lines).

## Legibility at arm's length (from Amil's review of the first views)
- The route is the main shape: draw the arrow wide (`width` ≥ 16 on the 874×402 screen) and long enough to read
  in one glance, from the truck or the street to the door.
- No tag ever covers the arrow, its shaft or its head: put the entrance tag on the side away from the route
  (`at` = the side opposite the arrow), and keep tags off the target outline when you can.
