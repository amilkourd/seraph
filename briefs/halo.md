# Brief — `halo` session · `halo/` · Next.js :3001 (phone A on the forearm)

Read first: `CLAUDE.md`, `docs/05-halo.md`, `contracts/halo-views.md` (the contract you implement), `contracts/types.ts`
(IncidentState, ShellToView, ViewToShell), `contracts/api.md` (Seraph SSE for `client=halo`).

## Goal
The shell that shows, on the wrist, the view Silex/Devin built for this moment, fed live — and the **kit** that lets
Devin build those views fast and consistently. You do not build the views themselves (except the fallback).

## Shell (`/`)
- SSE `GET {SERAPH_PUBLIC_URL}/stream?client=halo` (the phone is not on localhost) → `state`, `alert`, `halo_view`.
  Seraph must allow CORS for the Halo origin (ask @seraph).
- Current view in a sandboxed `<iframe sandbox="allow-scripts">` loading `halo_view.url` (Silex). On load and on
  every `state`: `postMessage({type:"seraph:state", state}, "*")`. Listen for `seraph:ready` and `seraph:tap`
  (→ `POST {SERAPH_URL}/halo/tap`).
- View swap: crossfade 300 ms, short vibration, tiny status line « Vue construite par Devin à HH:MM ».
- **Fallback view** (built in, React): for the current moment, the relevant facts as big lines with source tags,
  labelled « vue de secours ». Shown when there is no Devin view yet, or the iframe fails or stays silent 5 s.
- Alerts: banner over everything (amber/red), vibration + sound, 8 s, list behind a tap.
- Top bar: EXERCICE · incident id · clock · connection dot. Wake Lock, fullscreen on first tap, portrait,
  no zoom, works over HTTPS (`HALO_PUBLIC_URL`).
- `/mirror`: same shell, read-only, no sound, for the dashboard.
- `/dev`: loads `GET /state` from a replayed Seraph and lets you switch moments; for building without Devin.

## Kit (`halo/kit/`) — Devin's building blocks
- `halo-kit.js` (vanilla JS, no build step, global `Halo`), `halo.css` (tokens + base), `README.md` (the API, with
  one complete example view). Served at `/kit/*` with CORS open.
- Minimum API: see the table in `contracts/halo-views.md` (`frame`, `street`, `block`, `facade`, `floorStack`,
  `plan`, `arrow` with animation, `marker`, `smoke`, `fire`, `teamCard`, `countdown`, `tag`, `onState`, `tap`,
  `ready`, `project`). SVG-based, 390×844 portrait, thick strokes, min 22 px text.
- Look: Pip-Boy phosphor green on near-black, amber warnings, red danger, white key numbers, monospace caps.
- Write `examples/approach.html` using only the kit and `contracts/fixtures/state-sample.json`: it is the reference
  Devin copies. It must
  draw E2, the arrow, the truck, the hydrant and E1 crossed out from `contracts/fixtures/` data.

## Done when
On phone A: replayed state streams in; the fallback view shows; `examples/approach.html` served as if from Silex
swaps in and animates; an alert vibrates and shows; taps reach Seraph.

## IFC level plans — `docs/10-ifc.md`
`Halo.plan` must accept an IFC level plan SVG URL (`building.model.level_plans`) and draw `building.rooms[].zone` on
the same 0–1000 frame. The status line shows `building.model.provenance_fr`.
