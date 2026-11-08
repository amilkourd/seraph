# rosetta — status
Updated: 06:35

## Running
- rosetta on http://localhost:8001 · public: none · MOCK=0 · **headed Chrome** (Street View needs it)
  `cd rosetta && uv run uvicorn rosetta.app:app --host 0.0.0.0 --port 8001` (dev: `ROSETTA_HEADLESS=1`, `SERAPH_URL=http://localhost:8999` to keep test runs out of Seraph).
- Pushes every status change to `SERAPH_URL/rosetta/results`. Agent cam `ws://localhost:8001/ws/cam`.

## Done
- Service: `POST /run` (priority queue, ≤ `ROSETTA_MAX_PARALLEL`=4 browsers, contract timeouts), `GET /runs/{id}`,
  `/runs/{id}/trace`, `/runs`, `/shots/<id>.jpg`, `GET /endpoints` (live / cache timings + golden path),
  `GET /health`, `POST /admin/cache/clear`, `GET /admin/cache`, `WS /ws/cam`, `MOCK=1` (fixtures, placeholder JPEGs
  « MOCK », cam « MOCK — aucun agent »).
- Agent loop (`rosetta/holo.py`): Holo 4 Step schema, 0–1000 grid, last 3 screenshots, tool errors fed back,
  ≤ 30 steps; on `answer` code verifies the page and a failed check goes back to the model. Tools: click,
  double_click, write, type_param (code types a parameter's exact value where Holo clicked), press_key, scroll,
  drag, wait, go_back, answer. Per-skill `forbid` (no `write` in writes) and `guard` (code blocks an irreversible
  click). CAPTCHA / bot check (URL, iframe, page text, or the model saying so) → run stops, failed, cache.
- Pointing: H element-localization recipe, `{found,x,y}` when the target may be absent.
- Every result: `screenshots` (stable `/shots/<image_id>.jpg` = last good live run), `source`, `live`,
  `duration_ms`. Cam frame per step: `{run_id, endpoint, step, action, thought ≤ 80, shot_url, page_url, at, live}`;
  click actions carry `(x,y)` on the 0–1000 grid (the dashboard draws its crosshair from it).
- Golden-path cache: only from good live runs, served `live:false` with `cached_at`, `cache_reason`, and
  `error` = « live: … → cache du … ». Replicas: no cache (contract). Not cached when the address fails the BAN.
- Phone numbers: full E.164 only in the push to Seraph; `/runs/{id}` and traces mask them.

| Endpoint | Live result | Time (live) | Notes |
|---|---|---|---|
| `dispatch.read` | ✅ INC-0001, address, nature, level, notes from the DOM | 10 s, 2 Holo steps | code logs in |
| `occupants.list` | ✅ 6 occupants | 9 s | building matched by code (exact name, else the only one, else « exercice ») |
| `dispatch.write_112` | ✅ MC-0007, text exact | 10 s | `write` disabled, `type_param entry_fr` |
| `report.fill` | ✅ CR transmis, 4 sections exact | 25–57 s | 403 without `gate_id`; guard on « Transmettre » |
| `plan.read` | ✅ 19 points on `plan-l-1-01` (L-1.svg) | 7 s | zones IoU vs IFC: -1.01 0.96, -1.04 0.97, -1.06 0.91, -1.08 0.95, -1.11 0.86 (garage + ramp + places in one region); stair 0.15 (hatching), lift 0.46 |
| `maps.building` | ✅ 96 bd Bessières: E1 (496,500), truck (600,530) on `earth-top-01`; sv-front/left/right; 5 storeys | 32–42 s | no hydrant visible (honest: empty); E2 (the IFC's garage ramp) has no match at 42, Holo still points something; `footprint` = Holo points the roof once, code flood-fills (mean-shift, Maps UI masked, ≤ 16 vertices, kept only if 0.5–20 % of the image and E1 on/near it): 14 vertices on 42's roof |
| `georisques.risks` | ✅ 8 risks (inondation, séisme, mouvements de terrain, argiles, radon, ICPE, canalisations, pollution des sols) | 22 s | Holo refuses cookies, picks the suggestion |
| `weather.wind` | ✅ Paris: S, 5 km/h | 12–16 s | 30 min cache |
| `/explore` | ✅ « crèche ou école dans la rue ? » → paris.fr, « groupe scolaire Bessière » | 39 s, 16 steps | `verified:false`, source « source non vérifiée », trace for Silex |

**Seraph's dispatch fan-out, all six in parallel, live (06:00, `uv run python fanout.py`)**: occupants.list 6.3 s ·
dispatch.read 7.1 s · plan.read 13.0 s · weather.wind 12.5 s · georisques.risks 16.2 s · maps.building 38.6 s →
**all done in 40 s**, none from cache. Golden path rebuilt from that run (`GET /admin/cache`).

**End-to-end from Seraph `/incident/start` (06:04, Seraph MOCK=0), all live, results in Seraph's state and timeline**:
dispatch.read 5.2 s → in parallel occupants.list 4.9 s · plan.read 6.2 s (level -1, L-1) · weather.wind 13.2 s ·
georisques.risks 18.1 s · maps.building 37.9 s (2 entrances, 4 views → « Approche calculée : E1 … »). A first start
just before: 9.3 / 4.2 / 8.8 / 19.6 / 20.0 / 41.6 s, all live. Cams on the dashboard grid (checked live).

## In progress
- `/explore` + Linkup (written by Amil's main session, committed here): no `LINKUP_API_KEY` in `.env` yet, so Linkup
  says « pas de clé » and the fixed list of official sites is used. Live check of that path (06:30, test instance
  :8011 pinned to holo4-27b to leave holo4-35b-a3b's quota to the live INC-0001): start page OK, Holo opens paris.fr
  and searches, but **holo4-27b never answers in 24 steps** (max steps → failed). The same question passed on
  holo4-35b-a3b in 16 steps (05:40). The Linkup path itself is not yet run live. When the key is in: R11 on :8011 with
  the default models, then restart :8001 between incidents.

## Blocked
-

## Requests (to other sessions or Amil)
- @seraph: pass `level` -1 for the R-1 plan (dispatch replica still says level 3).
- Amil / H staff: the H key's quota is ~30 calls per minute window **per model** (measured). Rosetta paces each model
  and spreads load (agent: holo4-35b-a3b then holo4-27b; pointing: holo4-27b, holo3-1-35b-a3b). A higher quota on
  holo4-35b-a3b would make the stage run safer, especially if another session uses the same key.
- Amil (`.env`): `PLAN_IMAGE_PATH` is still `contracts/fixtures/plan-level3.svg`; scenario v2 wants `ifc/out/levels/L-1.svg`.
- @replicas: the dispatch seed still says « Feu de local technique », level 3 (scenario v2: vehicle fire, level -1).

## Facts I verified (API names, model ids, gotchas)
- H API `GET /v1/models` (04:55): `holo3-1-35b-a3b`, `holo3-122b-a10b`, `holo4-27b`, `holo4-35b-a3b`. Using `holo4-35b-a3b`.
- Agent loop: `extra_body={"structured_outputs": {"json": <Step schema>}}`, temperature 0.6, JPEG q80 screenshots.
- Element localization (hub.hcompany.ai/element-localization): single turn, image then prompt, schema `{x, y}` in
  `structured_outputs`, `chat_template_kwargs: {enable_thinking: false}`, temperature 0. ~1–2 s per point, 10 in parallel fine.
- A coordinate hint in the prompt (« around x=500, y=500 ») makes Holo answer exactly that point: don't. A red ring
  drawn on Holo's copy of the image (stored shot stays raw) marks the address instead.
- Holo 4 told to fill report sections typed the section *names* and sent the report; fixed with `type_param`,
  `write` disabled and a code guard on « Transmettre ».
- Google consent: `consent.google.com` « Tout refuser »; cookies persisted per site in `rosetta/profiles/` (gitignored).
- Street View: `maps/@?api=1&map_action=pano&viewpoint=lat,lng` → URL becomes `@lat,lng,<n>a,90y,…t/data=…!1e1…!2e0…`.
  `!2e10` = a user photo sphere (42's indoor 360): skipped, viewpoint moved 18 m. Headless Chrome never resolves the
  panorama (stays on a thumbnail URL): run headed. Turning = rewrite `,<h>h,` in that URL (keeps the pano id).
- Maps satellite top view: `maps/@lat,lng,70m/data=!3m1!1e3`. Place pin from the place URL `!3d<lat>!4d<lng>`.
- BAN (`api-adresse.data.gouv.fr/search`): « 2 rue Madame, 64000 Pau » → « 2 rue de Méon », score 0.60 → refused.
  96 bd Bessières → 0.98.
- Géorisques report URL: `/mes-risques/connaitre-les-risques-pres-de-chez-moi/rapport2?…&lon=…&lat=…`.
- Météo-France: `#atmogramme_slider li.wind p.wind-speed` → `img[title="Vent S"]` + `strong` km/h; « Maintenant » time in `#atmogramme_time_picker .period`.
- The `rosetta` console script doesn't resolve the package (hatch layout); start with uvicorn.
- **H quota: ~30 calls / minute window per model** (06:05: 30 OK in 13 s, then 429 « Too Many Requests for
  holo4-35b-a3b »; holo4-27b and holo3-1 still answered → separate quotas). No rate-limit headers. Concurrency itself
  is fine (12 parallel calls: 0.3–1.7 s). One call stalled 40 s once under load: calls are cut at 15 s (agent) / 8 s
  (pointing) and retried inside the run's budget.
- Pointing accuracy on the R-1 plan (error in 0–1000 units, 6 targets): holo4-27b 3–13, holo3-1-35b-a3b 4–36.
- Street View shots before 05:35 were 42's indoor 360 (user photo sphere); since then `!2e10` panoramas are skipped.
- holo4-27b as the *agent* is weaker on open-ended tasks: on /explore it wandered 24 steps without answering. Fine as
  overflow for short flows; exploration should stay on holo4-35b-a3b.
- Pacing env: `HOLO_RPM` (26 per model), `HOLO_MAX_INFLIGHT` (6), `HOLO_POINT_MODELS`.
