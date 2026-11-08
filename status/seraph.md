# seraph — status
Updated: 05:05

## Plan
1. `seraph/` uv project (Python 3.12, FastAPI, uvicorn, httpx, pydantic). Root `.env` loader. ✅
2. Pydantic models mirroring `contracts/types.ts` (same names, snake_case), extra fields allowed. ✅
3. In-memory `IncidentState` + snapshot `seraph/state.json` (reloaded at start), `POST /admin/reset`. ✅
4. `GET /state`, SSE `/stream?client=dashboard|halo` (state ≤ 4/s, typed events), `GET /health`, CORS open. ✅
5. `POST /admin/replay` (+ `/admin/replay_line`, `/admin/call_now`) from `contracts/fixtures/` at speed 1–20. ✅ dashboard + halo told
6. WS `/ws/gabriel` (GabrielToSeraph in, SeraphToGabriel out) + mock Gabriel (fixtures) when `MOCK=1`. ✅
7. Radio: text rules first (confirm/cancel never touch a model), LLM fallback only for unmatched lines, templates for every sentence. ✅
8. Building: `BUILDING_JSON` via a registry interface, approach scoring, routes on `building.graph`, `routes[].path`. ✅
9. Catches, gates (voice + dashboard, 2 min expiry), ARI `exit_by` + air alarm, urgency per call, moments → Silex. ✅
10. Dispatch log + report via Rosetta, learning flow, `metric` SSE, pytest on `radio.jsonl` + `calls.jsonl`. ✅ 22 tests

## Running
- seraph on http://localhost:8000 · public: none · **MOCK=1** (dev run, started by hand:
  `cd seraph && MOCK=1 uv run uvicorn seraph.app:app --host 0.0.0.0 --port 8000`). Live: `uv run seraph` (reads MOCK from `.env`).
- Tests: `cd seraph && uv run pytest -q` (rules alone, LLM forced off).
- Mock Gabriel over the real WS: `uv run python -m seraph.mock_gabriel radio R01 R07` · `call CALL-02` · `say "Seraph, quelle entrée ?" Tête` · `listen`.

## Done
- Every endpoint in `contracts/api.md` for Seraph, plus `/admin/replay_line`, `/admin/call_now`.
- Replay `all` = incident start → 6 Rosetta fixtures (labelled `live:false`) → `place_calls` → mock Gabriel plays
  `calls.jsonl` (CALL-06 no answer twice → « sans nouvelles ») → CALL-03 inbound → radio R01…R12. Says still go to Gabriel.
- Radio: rules for confirm/cancel/report/sitrep/Halo/orders/questions (approach, hydrant, riser, cutoffs, wind,
  risks, building/IFC, air, stair, occupants)/occupants found/team/hazard/chatter, then LLM fallback. All 12 fixture
  lines match on rules alone. Measured: rules path 0.2–1 ms, LLM path ~0.8 s (`gpt-5.4-mini`, `reasoning_effort:"none"`,
  `service_tier:"priority"`, 2.5 s timeout). The approach answer and the sitrep are precomputed on every state change.
- Code, never a model: approach score (E2 on the fixture), Dijkstra on `building.graph` (fire high = impassable,
  smoke = cost), `exit_by` (`ARI_TIME_FACTOR`), call urgency (all 6 fixture levels + `raised_by_voice` right),
  `routes[].path` on the plan frame.
- Catches: occupant into smoke → reroute gate (said in the caller's language on « confirme »), needs help → alert,
  no answer ×2 or 3 min → « sans nouvelles », team on a smoky stair → danger line, air T-5 and T-0, approach changes
  when an entrance or stair is lost. COS orders (« dis à Lucía de rester sur place ») are read back and gated.
- Standing instruction gate at incident start. Once confirmed, Seraph sends it to calls with smoke at the door.
- Moments → `ViewRequest` to Silex (`approach`, `team_engaged`, `commander_request` by default). Mock or unreachable
  Silex → request `failed`, Halo stays on `fallback://<moment>`.
- Report: R10 → gate → `report.fill` (sections assembled from the timeline) → « rapport transmis ».
- Learning: unknown question → « Je cherche, source non vérifiée » → Rosetta `/explore` → answer + gate `learn_source`.

- IFC building (tested on `ifc/out-dev/building.json`, pytest `test_full_replay_on_ifc_building`): reads
  `stairs[].zones` (one per level), `doors[].plan_point` (paths go through real door centres), room zones on `ifc-L<n>`,
  edge lengths in metres, no `truck` node (approach starts at `outside`). Door / material questions answer from the
  model (« porte 3.T Local technique : coupe-feu EI 30, source maquette »). The IFC zones win over `plan.read`
  (the photo only cross-checks). The IFC has no incident, so the starting hazards (fire 3.T, smoke stair B) come from
  the scenario fixture, kept only where those ids exist in the model, with source « alerte ». A stair with no report
  is said « pas de fumée signalée », never « dégagé ».
- `BUILDING_JSON` is checked again on every `POST /admin/reset`: when `ifc/out/building.json` lands, a reset loads it.
- `DEMO_ADDRESS` = « 2 rue Madame, 64000 Pau » is read (empty `KEY=   # comment` lines now read as empty).

- Confirmed by the other sessions: the dashboard runs live on :8000 (state, stream, gates, replay, call_now) and
  draws `routes[].path`. The Halo kit preview follows `/stream?client=halo`. Replicas reset from `/admin/reset`.

## In progress
- Nothing blocking. Next: live run with Rosetta (Amil) and Gabriel once their WS is up.

## Blocked
-

## Interfaces other sessions use
- **Building registry** (for the registry session): `seraph/seraph/registry.py`
  `class BuildingRegistry(Protocol): def lookup(self, address: str) -> Optional[BuildingKit]`.
  `LocalRegistry` reads `BUILDING_JSON` (fallback `contracts/fixtures/building.json`). `lookup` returning None means
  « Pas de maquette »: no graph, no routes, approach from Rosetta's entrances only. `Brain(registry=…)`. Today
  Seraph calls `lookup(DEMO_ADDRESS)` at reset. Build a `BuildingKit` with `building.load(path)`, or match its
  fields (`building`, `adj`, `zones`, `points`, `hazards_initial`, `base_stair_status`).
- **Gabriel WS** `ws://localhost:8000/ws/gabriel`: every connected socket gets every `SeraphToGabriel` (filter on
  `target`). `say` to a call may carry `text_fr` + `translate:true` when `text` is French but the caller's `lang`
  is not: translate it faithfully. Reroute, standing-instruction and common orders are already translated (en, es).
  Seraph also accepts `{kind:"metric", name, value_ms}` from Gabriel and forwards it on SSE.
- **Halo**: `halo.current_view.url = "fallback://<moment>"` with `built_by:"fallback"` = draw the built-in fallback.
- **SSE extras** beyond `api.md`: `calls_placed`, `halo_tap`. `metric voice_to_say` carries
  `{path:"rules"|"llm", stages:{rules_ms|llm_ms, compute_ms, queue_ms}, since_eot_ms}`.

## Answers to requests
- @dashboard: `POST /admin/call_now {occupant_ids?}` ✅ · `POST /admin/replay_line {"id":"R07"|"CALL-02"}` ✅ (key R)
  · `plan.points` keeps `stair:*` and `room:<id>` (and IFC rooms keep their zones) ✅ · `routes[].path` ✅ (below).
  inside_route: Seraph detects it (team engaged on a level + victim route + plan). It asks Devin only if
  `SERAPH_VIEW_MOMENTS` includes `inside_route`. Halo priority stays as the brief says (team_engaged above it).
- @halo: `routes[].path: [x,y][]` ✅ on the 0–1000 frame of `routes[].path_image_id` (`plan-l3-01` / `ifc-L<n>`),
  level `path_level`. It goes through the gap between consecutive zones, along each zone's long axis. Only set when
  it has 2+ points. Schematic: there are no door coordinates in the contract yet.

## Requests (to other sessions or Amil)
- Amil (`contracts/types.ts`): add `Route.path?: [number, number][]`, `path_image_id?: string`, `path_level?: number`
  (already served). Optionally `Door.point?: ImagePoint` from the IFC so paths go through real doors.
- Amil (`contracts/fixtures/calls.jsonl`): no call for OCC-03 Sophie Durand, but R12's expected sitrep counts « cinq
  joints ». Replay honestly says « quatre joints, un sans réponse, Karim Benali 3.10, un en attente », and Sophie
  becomes « sans nouvelles » after 3 min. Add a CALL line for OCC-03 if you want five.
- Amil (`radio.jsonl` order): R07 confirms the latest pending gate (Tom's reroute), so R08 then cancels the
  standing-instruction gate. That is correct by the rule, but confirm the standing instruction early in the live demo.
- Amil (`contracts/api.md`): document `/admin/replay_line`, `/admin/call_now`, SSE `calls_placed`, `halo_tap`.
- @gabriel: open `ws://localhost:8000/ws/gabriel`; send `call_event` with the `occupant_id` from `place_calls`.

## Facts I verified (API names, model ids, gotchas)
- LLM: `gpt-5.4-mini` with `reasoning_effort:"none"` + `service_tier:"priority"` ≈ 0.8 s on our lines (OpenAI-compatible
  `/chat/completions`, `response_format: json_object`). Team ids from the model come back as "binôme1" / "1": normalised to `B1`.
- FastAPI sync handlers run in a worker thread: anything that calls `asyncio.get_running_loop()` must be `async def`.
- Root `.env` has inline `# comments` after values: Seraph's loader strips them (`\s+#`).
