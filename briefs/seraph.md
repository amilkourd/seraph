# Brief — `seraph` session (the brain) · `seraph/` · FastAPI :8000

Read first: `CLAUDE.md`, `docs/01-architecture.md`, `docs/02-scenario.md`, `docs/07-safety-rules.md`, all of
`contracts/`, then this brief.

## Goal
Hold the incident state, turn speech and screens into events, catch what humans miss, gate every decision through
the commander, compute routes in code, decide what Halo shows, and tell Gabriel what to say. Everything the jury
sees flows through you, so mock mode and replay must work first.

## Build order
1. Pydantic models mirroring `contracts/types.ts` (same names). In-memory state + JSON snapshot on every change
   (`seraph/state.json`), reload at start. `POST /admin/reset`.
2. SSE `/stream` (events in `contracts/api.md`), `GET /state`. Throttle `state` to 4/s.
3. `POST /admin/replay` reading `contracts/fixtures/radio.jsonl`, `calls.jsonl`, `endpoints/*.json` as if live, at
   a chosen speed. **This unblocks dashboard and Halo; ship it in the first hour.**
4. WS `/ws/gabriel` in/out. Then Rosetta and Silex clients. Then catches, gates, routes, moments.

## Incident start (`POST /incident/start`)
1. Status `dispatched`. Halo fallback view for `dispatch` immediately.
2. Rosetta: `dispatch.read` (priority 10) → with the address: `maps.building`, `plan.read` (image: env
   `PLAN_IMAGE_PATH`, default the fixture), `georisques.risks`, `weather.wind`, `occupants.list` in parallel.
3. Propose the standing instruction gate to the COS on the radio: « COS de Seraph : consigne par défaut aux
   occupants, si fumée devant la porte, rester dans la pièce porte fermée. Confirmez ? »
4. When `occupants.list` returns: `place_calls` to Gabriel for every occupant with a phone.
5. When `maps.building` returns: choose the approach (below), say the briefing on `crew`, send the `approach`
   ViewRequest to Silex with the screenshots as references.

## Extraction (radio)
LLM (`LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`) with a JSON schema, input = transcript + speaker + last 10 timeline
entries + compact state. Output one of: `question{topic}` · `hazard` · `team_update` · `occupants_update` ·
`view_request{purpose_fr}` · `order_to_occupants{target, text_fr}` · `confirm` · `cancel` · `report_request` ·
`sitrep_request` · `chatter`. Test against `contracts/fixtures/radio.jsonl` (pytest, every `expected.event` must
match). Call facts arrive already structured from Gabriel.

## Code, not models
- **Approach:** score each entrance: usable (+), `leads_to` a stair whose status is `clear` (+3), leads to a hazard
  (−5), near the truck spot (+1). Best wins; `reason` in plain French. Fixture result: E2.
- **Routes:** BFS on `building.graph` (`BUILDING_JSON`: `ifc/out/building.json` when present, else
  `contracts/fixtures/building.json`; use edge lengths when given), removing nodes with a `high` hazard
  (fire room, smoke stair). Purposes: `approach` (truck → target level), `to_victim`, `evacuation` (room → outside).
  Store in `routes[]` with `source.kind="seraph"`, label « calcul ».
- **ARI:** `exit_by` per `docs/02-scenario.md`, with `ARI_TIME_FACTOR`. Label « calcul simplifié ».
- **Positions** come only from Rosetta points/zones. Never let an LLM produce coordinates.
- **Urgency (per call, `calls[].urgency`):** recompute on every `call_facts` and call event.
  3 « urgent »: mobility issue, injuries, trapped, `heading_to` a hazard node, smoke or fire seen while inside, or no
  answer on the fire level · 2 « à suivre »: inside with no smoke, no answer elsewhere, unknown · 1 « hors danger »:
  outside. Then the voice (`facts.voice`, from Gladia): emotion `distress`, `fear` or `pain` with a negative or mixed
  sentiment raises the level by one (max 3), sets `raised_by_voice` when it changed the level, and adds « détresse /
  peur / douleur dans la voix » to `reasons_fr`. The voice never lowers a level (Tom is calm and urgent). Copy
  `facts.voice` to `calls[].voice`. Urgency orders attention only: it never creates, changes or skips a gate, an order
  or a route. Sitreps list urgent calls first; when Seraph mentions the voice it says « selon la voix ».
  Fixtures: `expected_urgency` in `contracts/fixtures/calls.jsonl` (CALL-05 is the case the voice raises).

## Catches (run on every state change; each → alert and/or gate, spoken)
| Catch | Condition | Action |
|---|---|---|
| Occupant into smoke | occupant `heading_to` a stair/entrance with a hazard | gate `reroute_occupant`: « COS de Seraph : Tom Becker, 4e, descend par B. B est enfumé. Je lui dis de prendre A ? » → on confirm: `say` to that call, in its language |
| Needs help | `mobility_issue` or `injuries` | alert warning + crew line |
| No news | `no_answer` twice or no call after 3 min | alert « Sans nouvelles : … » + crew line |
| Team into hazard | a team announces a route through a hazard node | alert danger on crew: « Binôme 1, escalier B enfumé, passez par A. » (information, not an order) |
| Air | now ≥ `exit_by − 5 min` (scaled) | alert + crew: « Binôme 1 de Seraph, sortie dans 5 minutes. » + Halo vibrate |
| Approach blocked | chosen entrance leads to a hazard stair (new hazard) | recompute, say the change |

## Gates
`Gate` objects; confirmer COS; resolved by radio (« Seraph, confirme » / « annule » → latest pending) or the
dashboard. Expire after 2 min (say it). Kinds: `relay_order`, `reroute_occupant`, `send_report`, `learn_source`.
Orders the COS gives on the radio are read back and gated too (protects against transcription errors).

## Moments → Halo
| Moment | When | ViewRequest.purpose_fr (example) | data_keys |
|---|---|---|---|
| approach | approach computed | « Par où j'entre : bloc vu du dessus, rue, camion, flèche vers E2, hydrant, E1 barrée (fumée) » | building.entrances, building.approach, building.hydrants, building.truck_spot, routes |
| inside_route | plan ready + team engaged or victim located | « Par où je monte : plan niveau 3, zones, fumée, flèche E2 → A → 3.12 » | building.plan, building.rooms, building.hazards, routes |
| occupants | ≥ 2 calls with facts | « Qui est où : étages, personnes, aide nécessaire, sans nouvelles » | occupants, building.levels, building.hazards |
| team_engaged | first team engaged | « Mon air : binômes, compte à rebours de sortie » | crew.teams |
| commander_request | radio view_request | the COS's words, cleaned | chosen by the LLM from the state paths |
`deadline_s` 300 by default (the "drive"), 120 for team_engaged. While building: fallback. When ready: switch
`halo.current_view` unless a higher-priority view is showing (air alarm > occupants > inside_route > approach).
Radio « Seraph, montre … sur Halo » switches to an existing view without Devin.

## Speech
Templates in French for the crew (short, radio style: « <dest> de Seraph : … »), English/Spanish for calls. Say the
source when it matters (« selon l'appel », « selon le plan »). Sitrep: counts by status + needs-help + no-news +
hazards (fixture R12).

## Dispatch log and report
Every call summary → `dispatch.write_112` (Rosetta). Report: assemble chronologie/moyens/victimes/observations from
the timeline → gate `send_report` → `report.fill`.

## Learning
Unknown question → say « Je cherche, source non vérifiée » → Rosetta `/explore` → speak the answer tagged → gate
`learn_source` (« Ajouter cette source à Seraph ? ») → on confirm, Silex `/endpoints/learn`.

## Metrics (`metric` SSE)
`voice_to_say` (radio end → say queued), `call_fact_to_crew`, `request_to_view`, per-endpoint duration live/cache.

## Done when
Replaying all fixtures produces the expected events, catches, gates and says; dashboard and Halo animate from
replay; live: a radio question gets a spoken answer in < 3 s; the stair-B gate works by voice.

## Building model (IFC) — `docs/10-ifc.md`
- Load `BUILDING_JSON` at start; serve `ifc/out/` at `GET /building/files/{path}` (CORS open).
- Questions on materials, fire doors, levels → answer from `building.materials` / `building.doors` with source
  `ifc`; absent → « pas dans la maquette ». Radio/call facts override the model.
- Pass `building.entrances` as `expected_entrances` to `maps.building`; add the relevant level plan URL to view requests.
