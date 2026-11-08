# silex — status
Updated: 07:15

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
| 06:40 | commander_request « Position des binômes par étage » (end-to-end recording, Seraph's request) | CLI, Opus | yes | 1 | **120 s** | — |
| 06:38 | approach (recording, live shots, 6/6 refs) | CLI, Opus | yes | 1 | **182 s** | 300 s |
| 06:38 | occupants (recording) | CLI, Opus | yes | 1 | **154 s** | — |
| 06:2x | approach (Seraph's request) | CLI, Opus | yes | 1 | **151 s** | 300 s |
| 05:57 | approach, test id, kit rule 16 (hazards from the state), fire reported in the garage R-1 | CLI, Opus | yes | 1 | **146 s** | 300 s |
| 05:41 | approach, test id, real façade shots + Rosetta footprint on earth-top-01 (6/6 refs) | CLI, Opus | yes | 1 | **219 s** | 300 s |
| 05:16 | approach, test id, live Rosetta shots (6/8 refs as files, 24 s of it waiting for Rosetta) | CLI, Opus | yes | 1 | **140 s** | 300 s |
| 05:10 | approach, sent by Seraph itself at dispatch (refs: IFC plans only, shots not taken yet) | CLI, Opus | yes | 1 | **102 s** | 300 s |
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
- **Watch Devin build** (for the judges): local CLI sessions have no app.devin.ai link (only `--cloud` ones do), so
  Silex serves its own live page `GET /sessions/<id>?view=<view_id>` and sends it as `devin_session_url` (in the
  `building` ViewReady already, then `ready`/`failed`); `GET /sessions` → `url` is that page for CLI sessions. The
  page polls `/sessions/<id>/data`: Silex's timeline (request, references, Devin started, « Devin écrit la vue (N
  lignes) » from a build-folder watcher, end of each attempt, check-view / render A-B results, served), the view
  as Devin writes it (`/sessions/<id>/wip`, fed with the build's `state.json`, then the served view), each reference
  with what Devin took from it, Devin's own steps (read / write / exec with exit code / what it said) from the
  CLI's `--export` ATIF trace (written when each run ends, not streamed), and the prompt.
- The CLI session id for `-r` now comes from each run's `--export` (`session_id`), not from `devin list` (no race
  when two runs start together).
- `GET /sessions` (dashboard; plain array): id, session_id (CLI name), url (API only), kind, role, transport,
  model, status (warming idle building fixing ready failed ended), purpose, started_at, elapsed_s, request_id,
  view_id, note, tail (last lines of the CLI output), summary, refs. `GET /requests` (timings, attempts, errors),
  `GET /views`, `GET /health`, `POST /admin/stop_all`.
- **Mock** (`MOCK=1`): the kit example for the moment is validated and served as if built, `devin_session_url:
  null`, note « mock ».
- **API v3 fallback** (`DEVIN_TRANSPORT=api`): same flow, everything inline (playbook, RULES.md verbatim, README,
  examples) + attachments (kit files, state.json, reference images), structured output `{request_id, view_id,
  attempt, html, notes}`, warm sessions via messages. Tested to the point of sending; see Facts.

- Screenshot → view, checked with live Rosetta shots (05:16, `view_approach_3`): Devin opened each image and
  said what it took. `earth-top-01` → the street band along the façade E1 opens on; IFC L0 → the footprint; IFC L3
  → one stair A. The three `sv-*` Street View shots are an **indoor panorama of the 42 Paris campus** (no façade),
  and Devin said so and took nothing from them (@rosetta told).
- Façade shots fixed by Rosetta (05:35). Test build `view_approach_4` (05:41) on a state with Rosetta's footprint:
  Devin drew on the street frame `earth-top-01` (footprint, boulevard band, truck → E1) and named what it took from
  each image (sv-front: white panelled façade, pavement and railing → short straight arrow across the pavement;
  sv-left: glazed lobby on the boulevard → E1; sv-right: no vehicle access on that side; earth-top: the boulevard
  band; IFC L0/L3: stair A behind E1, fire R+3). Every request now tells Devin to draw on ONE frame (`earth-top-01`
  for the street side, `ifc-L<n>` inside) and to prefer the street side when `building.footprint` exists.
- Amil's rule in the playbook and in every request, word for word: « Never write a hazard, level or room as literal
  text. Every fact in the card comes from the live state via Halo.onState at runtime, with its source tag. No
  hazard in the state means no fire in the view. » Every request also says: re-read `halo/kit/RULES.md` and
  `README.md` now (warm sessions read them at warm-up and the kit changes), use `Halo.fire/smoke(…, {hazard})` and
  `Halo.hazardLine(state, h)` (kit rule 16). The API path re-uploads the kit when its files change and puts
  RULES.md verbatim in each request.
- **Live-bound check** (headless render): after the live state, the view gets state A (nothing reported, no stair in
  smoke) and state B (a fire reported by the crew in the incident's room). A must show no feu/fumée/fire/smoke;
  for approach / inside_route / occupants, B must change the drawing or the card. Devin builds once per moment;
  data changes never trigger a rebuild.
- `view_approach_5` (05:57, Devin CLI, 146 s, 1 attempt): passes the new check-view (rule 16) and both states;
  card « Entrez par E1 / Montez esc. A / Feu signalé R-1 » from `Halo.hazardLine`, E2 crossed (it opens into the
  garage fire). Views 1–4 were built before rule 16 and now fail check-view: `GET /views` → `passes_kit:false`.
  Seraph builds a fresh view at each incident, so they are not what Halo shows.
- A build waits up to `SILEX_REF_WAIT_S` (45 s) for shots that are missing while Rosetta reports active runs.
- `GET /sessions` → `request_to_view_ms` of the session's last view (request reaching Silex → view served).
- Playbook + every request: arrow width ≥ 16, no tag over the arrow (Amil's review of view_approach_2).
- `team_engaged.html` is parked (ARI cut): dropped from the kit attachments, both warm prompts and the playbook
  (API warm-up would have raised FileNotFoundError); a `team_engaged` request starts from `occupants.html`.
  Takes effect at the next :8002 restart (playbook: at the next warm session).

## In progress
- Nothing running. Watch: 219 s on the last build (100–140 s before) is close to the 300 s deadline. If it gets
  tight: `SILEX_DEVIN_MODEL=claude-opus-5-5-medium-fast` (listed by `devin models`, not tried yet).

## Blocked
-

## Requests (to other sessions or Amil)
- (done by @seraph) A live `maps.building` result with approach shots no earlier request carried → a new approach
  ViewRequest (new request_id, every shot as reference); Halo switches to the latest ready view of the moment.
- (done by @seraph) Seraph calls Silex in mock too: its 05:10 dispatch request was built by Devin in 102 s.
- @rosetta: the approach references Seraph sends are `sv-front-01`, `sv-left-01`, `earth-left-01`,
  `earth-rear-01`, `earth-top-01` (`/shots/<id>.jpg`). Silex fetches them per request, so live ones are used as soon
  as they exist.
- Not done: no fixture street screenshots exist in `contracts/fixtures/`, so there is no « mock » image to fall back
  on before Rosetta runs.
- Not done (stretch): `POST /endpoints/learn`.

## Facts I verified (API names, model ids, gotchas)
- `--model opus` resolves to **Claude Opus 5 Medium** (`devin models`: family `claude-opus-5`, alias `opus`), not
  Opus 5.5 (`claude-opus-5-5-medium`, listed separately, no alias). The ATIF export says « You are powered by
  Claude Opus 5 Medium ».
- `--export <path>` writes ATIF JSON `{schema_version, session_id, agent, steps:[{source: system|user|agent,
  message, tool_calls:[{function_name: read|write|exec…, arguments}], observation:{results:[{content}]}}]}` when the
  run ends (checked by polling: nothing during the run). `--verbosity` changes nothing in `-p` output.
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
