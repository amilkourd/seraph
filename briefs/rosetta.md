# Brief — `rosetta` session (computer use) · `rosetta/` · FastAPI :8001

Read first: `CLAUDE.md`, `docs/04-rosetta.md` (the design), `contracts/rosetta-endpoints.md` (what each endpoint
returns), `contracts/types.ts` (RosettaRun, RosettaResult, Screenshot, ImagePoint), `contracts/api.md` (Rosetta),
`docs/07-safety-rules.md`. You do not write in `rosetta/skills/learned/` (Silex does).

## Goal
Make 8 screens without API behave like an API, live and visible. This is what the command post shows: the agent cam
on the big screen, Holo clicking through real sites and legacy software, and pointing at doors and stairs.

## Build order
1. FastAPI skeleton + mock mode (fixtures, placeholder JPEGs, cam frames labelled MOCK). Push results to Seraph
   `POST /rosetta/results` on every status change.
2. The agent loop (`docs/04-rosetta.md`) against **the replicas first** (`dispatch.read`, `occupants.list`,
   `dispatch.write_112`) — easiest, and they prove the loop. Agent cam WS.
3. `plan.read`: pointing on the fixture plan (render `contracts/fixtures/plan-level3.svg` to PNG) + zone code.
   Compare with `building.json` points/zones.
4. `maps.building` on the demo address: Street View + Earth + pointing. Hardest; budget time, keep the golden path.
5. `georisques.risks`, `weather.wind`, then `report.fill`.
6. `/explore` + traces for learning; hot-reload `rosetta/skills/learned/*.md`.

## Must
- Holo via H's OpenAI-compatible API, our own loop on Playwright (headed), 0–1000 grid, last 3 screenshots, tool
  errors fed back, code verifies pages and extracts data. Look up the current Holo model id and structured-output
  syntax in H's docs; record them in `status/rosetta.md`.
- Every result: `screenshots` (stored, served at `/shots/<id>.jpg`), `source`, `live`, `duration_ms`.
- Public sites read-only. Writes only on replicas. `report.fill` only when Seraph says the gate passed (Seraph only
  calls it then; refuse if `params.gate_id` is missing).
- Golden-path cache per endpoint for the reference address (`DEMO_ADDRESS`), always marked `live:false`.
- Max 4 browsers in parallel, priority queue, per-endpoint timeouts from the contract.
- Measure and log time per endpoint, live vs cache; expose in `GET /endpoints`.

## Done when
From Seraph's `/incident/start`, 6 endpoints run in parallel, the dashboard shows their cams, results land in the
state with screenshots and points; plan zones match the fixture within a few percent; one real-site run is live.

## IFC — `docs/10-ifc.md`
`maps.building` takes `expected_entrances` (from the IFC): ask Holo to find each one on Street View / Earth and return
a point per entrance id. `plan.read` stays: buildings without IFC, and the cross-check in the demo.
