# Rosetta — screens without API → endpoints

FastAPI on :8001. Our own Holo agent loop (H API, OpenAI-compatible) on headed Playwright Chrome.

    cd rosetta && uv sync && uv run uvicorn rosetta.app:app --host 0.0.0.0 --port 8001

- Headed by default: Street View only resolves a panorama with a real GPU window. `ROSETTA_HEADLESS=1` for dev.
- `MOCK=1`: contract fixtures, placeholder frames labelled MOCK, no agent.
- Live check: `uv run python tests_live.py dispatch.read occupants.list` (params in the file; a JSON object as the last arg overrides them).
- Plan zones vs the IFC: `uv run python eval_plan.py <run_id>`.
- Skills (hints for the model + what code checks): `skills/<endpoint>.md`. `skills/learned/` belongs to Silex.
- Golden-path cache: `cache/<endpoint>/<key>/`, filled only by good live runs, served `live:false`. `POST /admin/cache/clear`.
