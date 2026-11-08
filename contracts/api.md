# API (all of it)

Types are in `types.ts`. JSON bodies, snake_case. Every service exposes `GET /health` → `{ok:true, mock:bool}`.

## Seraph (:8000) — served by `seraph`
| Method | Path | Caller | Body → Response |
|---|---|---|---|
| WS | `/ws/gabriel` | gabriel | in: `GabrielToSeraph`, out: `SeraphToGabriel` |
| POST | `/incident/start` | dashboard, eval | `{incident_id?}` → `IncidentState` (reads dispatch through Rosetta) |
| GET | `/state` | all | → `IncidentState` |
| GET | `/building/files/{path}` | halo, dashboard, silex, Devin views | static files from `ifc/out/` (level SVGs, `building.glb`), CORS open — `docs/10-ifc.md` |
| GET | `/stream?client=dashboard\|halo` | dashboard, halo | SSE, see below |
| POST | `/rosetta/results` | rosetta | `RosettaResult` → `{ok}` (called on every status change) |
| POST | `/silex/views` | silex | `ViewReady` → `{ok}` |
| POST | `/silex/endpoints` | silex | `{name, status:"building"\|"ready"\|"failed", devin_session_url?, test_passed?}` → `{ok}` |
| POST | `/halo/tap` | halo | `ViewToShell["seraph:tap"]["target"]` → `{ok}` |
| POST | `/gates/{gate_id}/confirm` | dashboard | → `{ok}` (resolved_by: dashboard) |
| POST | `/gates/{gate_id}/cancel` | dashboard | → `{ok}` |
| POST | `/say` | dashboard (manual) | `{target, text, lang}` → `{ok}` |
| POST | `/ask` | dashboard, eval | `{question_fr}` → spoken answer path; may trigger learning |
| POST | `/admin/reset` | dashboard | clears state, calls replicas' reset |
| POST | `/admin/replay` | dashboard, eval | `{fixture:"radio"\|"calls"\|"all", speed:1..20}` injects fixtures as if live |
| POST | `/admin/moment` | dashboard | `{moment}` forces a Halo moment (rehearsal) |

### SSE `/stream` events (`event:` name → `data:` JSON)
| event | data | throttle |
|---|---|---|
| `state` | full `IncidentState` | max 4/s |
| `timeline` | `TimelineEntry` | each |
| `radio` | `GabrielToSeraph` radio_transcript | each |
| `say` | `SeraphToGabriel` say | each |
| `call` | `Call` | each change |
| `rosetta` | `RosettaResult` | each change |
| `silex` | `ViewRequestStatus` or endpoint status | each change |
| `gate` | `Gate` | each change |
| `alert` | `Alert` | each |
| `metric` | `{name, value_ms, at}` e.g. `voice_to_say`, `call_to_crew`, `request_to_view` | each |
Halo clients (`client=halo`) receive only `state`, `alert` and `halo_view` (`{view_id,url,moment}`).

## Rosetta (:8001) — served by `rosetta`
| Method | Path | Caller | Body → Response |
|---|---|---|---|
| GET | `/endpoints` | seraph, dashboard | → list with kind, verified, params schema |
| POST | `/run` | seraph | `RosettaRun` → `{run_id, status:"queued"}`; results pushed to Seraph `/rosetta/results` |
| GET | `/runs/{run_id}` | all | → `RosettaResult` |
| POST | `/explore` | seraph | `{question_fr, hints?}` → `{run_id}` exploratory session (learning) |
| GET | `/runs/{run_id}/trace` | silex | → full trace: steps (thought, action, screenshot url, page url), final answer |
| GET | `/shots/{image_id}.jpg` | all | screenshot file |
| WS | `/ws/cam` | dashboard | frames `{run_id, endpoint, step, action, thought, shot_url, page_url, at}` |
| POST | `/admin/cache/clear` | dashboard | clears golden-path cache |

## Silex (:8002) — served by `silex`
| Method | Path | Caller | Body → Response |
|---|---|---|---|
| POST | `/views/request` | seraph | `ViewRequest` → `{request_id, status:"building"}`; then pushes `ViewReady` to Seraph |
| GET | `/views/{view_id}/` | halo (iframe) | the view's `index.html` (static, plus its assets) |
| GET | `/views` | dashboard | list with meta (`view.json`) |
| POST | `/endpoints/learn` | seraph | `{run_id, name_hint, question_fr}` → `{status:"building"}`; then pushes to Seraph `/silex/endpoints` |
| GET | `/sessions` | dashboard | Devin sessions: id, url, kind (view/endpoint), status, started_at |

## Halo (:3001) — served by `halo`
| Path | What |
|---|---|
| `/` | the shell (phone A) |
| `/kit/halo-kit.js`, `/kit/halo.css`, `/kit/README.md` | the kit Devin's views load (CORS open) |
| `/mirror` | same shell, read-only, for the dashboard to embed |

## Talkie (:3000) — served by `talkie`
| Path | What |
|---|---|
| `/` | crew push-to-talk (room `crew`) |
| `/call?occ=OCC-07` | web call for an occupant (joins `call-<id>` via `/api/call-token`) |
| `/qr` | QR code to the occupants replica's public page `/inscription` (judges opt in: name, phone, floor, room, language). Rosetta then reads them back through the screen with `occupants.list` |
| `/api/token` | LiveKit token for `crew` |
| `/api/call-token` | LiveKit token for a call room + tells Gabriel a web call started |

## Replicas — served by `replicas` (HTML only, **no JSON API**, on purpose)
- Dispatch :8101 — login, list of incidents, incident page (address, nature, level, notes), « Main courante » form
  to add an entry (used by `dispatch.write_112`).
- Report :8102 — login, « Nouveau compte rendu » multi-section form, « Enregistrer » then « Transmettre ».
- Occupants :8103 — login, building list, building page with an occupant table (name, floor, room, phone), add form,
  and a public opt-in page `/inscription` (no login, consent checkbox) used by judges through the QR code.
- Each has `/admin/reset` (HTML button + POST) that restores `contracts/fixtures/` seed data.
