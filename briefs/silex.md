# Brief — `silex` session (tool creation) · `silex/`, `views/`, `rosetta/skills/learned/` · FastAPI :8002

Read first: `CLAUDE.md`, `contracts/halo-views.md` (what a view must be), `contracts/types.ts` (ViewRequest,
ViewReady), `contracts/api.md` (Silex), `docs/05-halo.md`, `docs/04-rosetta.md` (skill format), `halo/kit/README.md`
once the halo session publishes it.

## Goal
Turn Seraph's requests into real tools, built by **Devin**, fast enough to land before the crew needs them:
1. **Halo views** for a moment (`POST /views/request`).
2. **New Rosetta endpoints** from an exploration trace (`POST /endpoints/learn`).

## Views
- On request: copy the reference screenshots into `views/_refs/<request_id>/` and expose them at
  `SILEX_PUBLIC_URL` (Devin must be able to open them). Snapshot the current state to
  `views/_refs/<request_id>/state.json`.
- Start a Devin session (API v3; check current docs) with the prompt built from `silex/devin/view-playbook.md` (you
  write it): the purpose, data_keys, the state snapshot URL, the reference image URLs, the kit README and the
  example view (`halo/kit/examples/approach.html`), the rules from `contracts/halo-views.md`, and the output:
  `views/<view_id>/index.html` + `view.json` on a branch `view/<view_id>`, or the HTML in the structured output if
  that is faster. Ask for a structured output `{view_id, branch, files[], notes}`.
- **Speed:** keep 1–2 warm Devin sessions open from incident start (context already loaded) and send each request
  as a message to a warm session if the API allows it; otherwise start new ones in parallel. Measure
  `request_to_view` and put it in `status/silex.md`.
- On delivery: fetch the files, validate (loads only `{{HALO_KIT_URL}}`, sends `seraph:ready`, size < 200 KB, no
  network calls), replace `{{HALO_KIT_URL}}`, serve at `/views/<view_id>/`, push `ViewReady` to Seraph with the
  `devin_session_url`.
- Deadline: if not ready by `deadline_s`, push `failed`/timed out; Seraph keeps the fallback. Keep the session
  running and deliver late if it finishes (Seraph decides whether to switch).
- `GET /sessions` for the dashboard (id, url, kind, status, started_at, elapsed).

## Endpoints (learning)
- Get the trace from Rosetta (`GET /runs/{id}/trace`), start a Devin session with `silex/devin/endpoint-playbook.md`:
  write `rosetta/skills/learned/<name>.md` in the skill format + extraction code + a test, `verified:false`.
- When the test passes, merge into the working tree, tell Seraph `POST /silex/endpoints` (ready) — Rosetta
  hot-reloads.

## Mock mode
Serves `halo/kit/examples/*.html` as if Devin had built them, after a delay, with `devin_session_url: null` and the
label « mock ».

## Done when
A `ViewRequest` for `approach` returns a Devin-built view that Halo displays and that moves with live state; the
dashboard shows the Devin session; a learned endpoint lands from a trace.

## IFC level plans — `docs/10-ifc.md`
References also include the IFC level plans (`building.model.level_plans`, served by Seraph): pass the relevant
level's SVG URL to Devin next to the Rosetta screenshots.
