# silex — status
Updated: 05:15

## Running
- silex on http://localhost:8002 (0.0.0.0) · public: `SILEX_PUBLIC_URL`, else the LAN IP (`http://172.16.0.13:8002`)
  · MOCK=0 · transport **Devin CLI, Opus** (`devin 3000.12.28`, logged in by Amil).
- Start: `cd silex && uv run silex` (reads the root `.env`). Mock: `MOCK=1 uv run silex`. API fallback:
  `DEVIN_TRANSPORT=api uv run silex` (also automatic when `devin` is not on PATH).
- Env: `DEVIN_TRANSPORT=cli|api` (default cli) · `SILEX_DEVIN_MODEL` (default `opus` → Claude Opus 5.5; faster:
  `claude-opus-5-5-medium-fast`) · `SILEX_WARM` (default 2) · `SILEX_MAX_TRIES` (3) · `SILEX_PUBLIC_URL` ·
  `SILEX_KIT_URL` (default `<origin>/kit`, served by Silex from `halo/kit/`, read-only).

## Measured
| When | Moment | Transport | Warm | Attempts | request_to_view | Deadline |
|---|---|---|---|---|---|---|
| 05:05 | approach (TU Wien, Seraph's real request id) | CLI, Opus | yes (warm 17 s before) | 1 | **107 s** | 300 s |
| 04:50 | approach / team_engaged | mock (kit example) | — | 1 | 5.2 s / 3.9 s | — |

## Done
- `POST /views/request` → Devin → validation → served at `/views/<id>/` → `ViewReady` to Seraph
  `POST /silex/views` (`building` at start, `ready` with url, or `failed` with a note). Checked: Seraph set
  `halo.current_view` = `view_approach_1`, `built_by: devin`; Halo in the simulator showed it (« DEVIN 05:06 · IFC
  RÉEL »). Fed a state with stair A in smoke, the same view switches its card to « Esc. A fumée », no rebuild.
- **Devin CLI transport** (`silex/silex/cli.py`): each build is `devin --model opus --permission-mode accept-edits
  --config silex/runtime/cli-config.json --respect-workspace-trust false [-r <session>] -p --prompt-file <file>`
  in the repo root. Devin reads `halo/kit/*` and the examples from disk and writes
  `silex/runtime/build/<view_id>/index.html` + `notes.json`. `--config` replaces `~/.config/devin/config.json`, so
  Silex writes a merged copy (user config + `silex/devin/cli-config.json` permissions; never printed).
  Permissions: workspace edits allowed by the mode, `Write(...)` denied in every other session's folder, in
  `views/`, `silex/silex/`, `*.md`, `.env*`; exec allowed: `node halo/kit/check-view.mjs`, ls/cat/head/wc/jq; denied:
  rm, sudo, git, curl, wget. In print mode anything else is rejected (no prompt).
- **Warm pool**: on start, on Seraph's incident start (SSE `state`, idle → active) and `POST /warm`, Silex runs
  `devin -p` with the warm prompt (playbook + read the kit, answer PRÊT; ~17 s), reads the session id back from
  `devin list --format json`, then sends each request with `-r <id>`. One warm run at a time (ids are matched by
  time). A session that delivered a view goes back to idle with its context.
- **Built from the references** (Amil): each request's references are fetched into
  `silex/runtime/build/<view_id>/refs/` (Rosetta `GET /shots/<id>.jpg`, Seraph's IFC level SVGs for the ground
  floor and the fire floor). Devin must open each one and write in `notes.json` what it took from each image;
  Silex rejects the view if an image has no entry. The images are copied next to the view
  (`/views/<id>/refs/<file>`), and `view.json` → `references_used: [{image, image_id, caption, took, url}]`.
  `GET /sessions` → `refs` + `summary` (dashboard « screenshot → view »).
- **Validation** (a failing view is never served; errors go back to Devin, 3 tries max): `node
  halo/kit/check-view.mjs`, size < 200 KB, kit placeholders, `Halo.ready` + `Halo.onState`, no network APIs, then a
  headless render (Chromium, 874×402, native-shell messaging): no JS error, `seraph:ready` posted, and the state must
  add drawing to the kit's frame. The render is saved as `/views/<id>/preview.png`.
- Fallback when Devin answers in its reply instead of writing the file: the last ```html block of its output.
- Deadlines from the request; when late, `failed` « délai dépassé, Devin continue » is pushed and the view is still
  delivered as `ready` if it lands (Seraph decides whether to switch).
- `GET /sessions` (dashboard; plain array): id, session_id (CLI name), url (API only), kind, role, transport,
  model, status (warming idle building fixing ready failed ended), purpose, started_at, elapsed_s, request_id,
  view_id, note, tail (last lines of the CLI output), summary, refs. `GET /requests` (timings, attempts, errors),
  `GET /views`, `GET /health`, `POST /admin/stop_all`.
- **Mock** (`MOCK=1`): the kit example for the moment is validated and served as if built, `devin_session_url:
  null`, note « mock ».
- **API v3 fallback** (`DEVIN_TRANSPORT=api`): same flow, everything inline (playbook, RULES.md verbatim, README,
  examples) + attachments (kit files, state.json, reference images), structured output `{request_id, view_id,
  attempt, html, notes}`, warm sessions via messages. Tested to the point of sending; see Facts.

## In progress
- Nothing running. Next: a build with real Rosetta street shots once `maps.building` has run live (today only the
  2 IFC plans were files; `sv-*`/`earth-*` return 404 from Rosetta, so they were listed as « not available »).

## Blocked
-

## Requests (to other sessions or Amil)
- @seraph: with `MOCK=1`, `Silex._request` fakes a failure and never calls Silex. Please call Silex when it is
  reachable even in mock (or behind a flag such as `SERAPH_SILEX_LIVE=1`), so the replay gets Devin views.
- @rosetta: the approach references Seraph sends are `sv-front-01`, `sv-left-01`, `earth-left-01`,
  `earth-rear-01`, `earth-top-01` (`/shots/<id>.jpg`). Silex fetches them per request, so live ones are used as soon
  as they exist.
- Not done: no fixture street screenshots exist in `contracts/fixtures/`, so there is no « mock » image to fall back
  on before Rosetta runs.
- Not done (stretch): `POST /endpoints/learn`.

## Facts I verified (API names, model ids, gotchas)
- **Devin CLI** (docs.devin.ai/cli): `devin -p/--print [PROMPT]`, `--prompt-file`, `--model` (`opus` → latest
  Opus family; `devin models` lists them), `-r/--resume <id>`, `--permission-mode auto|accept-edits|smart|dangerous`,
  `--config` (REPLACES the user config, which holds `devin.org_id`), `--respect-workspace-trust false` (print mode
  fails in an untrusted dir without it), `devin list --format json` → `[{id, short_id, working_directory,
  last_activity_at (epoch s), title, state}]`, `devin rm <id> --force`. A tool call that needs confirmation in print
  mode is rejected with « rejected a tool call that requires confirmation » — an `ask` rule = a refusal.
- Devin API v3, base `https://api.devin.ai/v3/organizations/{DEVIN_ORG_ID}`, `Authorization: Bearer $DEVIN_API_KEY`
  (`cog_` key):
  - `POST /sessions` `{prompt, title, tags, attachment_urls, structured_output_schema (JSON Schema draft 7, ≤ 64 KB),
    max_acu_limit, …}` → `{session_id, url, status}`.
  - `GET /sessions/{devin-<id>}` → `status` (`new claimed running exit error suspended resuming`), `status_detail`
    (`working waiting_for_user waiting_for_approval finished` | suspension reason), `structured_output`.
  - `POST /sessions/{devin-<id>}/messages` `{message, attachment_urls}` → **HTTP 400 until the session has started**
    (status `new`/`claimed`); works once `running/waiting_for_user` (~20 s after create).
  - `GET /sessions/{id}/messages`, `POST /attachments` (multipart `file` → `{url}`), `DELETE /sessions/{id}`.
- Playwright: Silex pins `playwright==1.64.1`, which wants headless shell 1248; if missing, it uses the cached
  `chromium_headless_shell-*` already on disk.
