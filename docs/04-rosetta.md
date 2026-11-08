# Rosetta — how computer use works here

Endpoint list and output shapes: `contracts/rosetta-endpoints.md`. This file is the engineering design.

## The agent loop (our own, inspired by Lantern's, verified against H's docs)
- Client: OpenAI SDK pointed at H: `AsyncOpenAI(api_key=H_API_KEY, base_url=H_API_BASE_URL)` with
  `H_API_BASE_URL=https://api.hcompany.ai/v1/` and `HOLO_MODEL` from `.env`. Check H's docs (Context7 / H hub, e.g. the
  agent-loop recipe) for the latest Holo model id and the structured-output parameter. Lantern used
  `extra_body={"structured_outputs": {"json": <schema>}}` with Holo 3.1; Holo 4 may differ — verify, then write
  what works in `status/rosetta.md`.
- Browser: Playwright Chromium, **headed** (`headless=False`, so Google Earth's WebGL renders and the agent cam is
  real), viewport 1280×800, one context per run, cookies persisted per site (`rosetta/profiles/<site>/`) so consent
  banners are accepted once.
- Each turn: screenshot (JPEG q80) wrapped in `<observation>`, the task, the skill's hints, a short history.
  **Keep only the 3 most recent screenshots**; older ones become a one-line note.
- Model output schema: `Step { note: str, thought: str, tool_call: { tool_name, arguments } }`.
- Tools: `goto_url(url)`, `click(x, y)` and `double_click`, `type_text(text, submit?)`, `press_key(key)`,
  `scroll(dy)`, `drag(x1,y1,x2,y2)` (orbiting Earth), `wait(ms)`, `go_back()`, `answer(content)`.
  Coordinates on a **0–1000 grid**, scaled to the viewport by code.
- Tool errors go back as `<tool_output>ERROR: …</tool_output>` so the model corrects itself. 800 ms settle per
  step. Limits per run: 30 steps and the endpoint timeout.
- **The model navigates; code reads.** On `answer`, code checks the page (URL pattern, a DOM text that must be
  there) and extracts the data itself (selectors, `inner_text`, or a text-LLM extraction with a JSON schema over
  the page text). Never trust a value or URL the model typed.

## Pointing (vision)
- For each screenshot that needs it, one Holo call: image + list of things to find (`entrance`, `side door`,
  `gate`, `hydrant`, `place where a fire engine can stop`, `stair A`, `room 3.12`…) → `{items:[{name, found, x, y,
  label}]}` on the 0–1000 grid. Use H's element-localization endpoint if the docs offer one; otherwise this prompt
  with a schema. Points are stored with the screenshot's `image_id`.
- Plans: Holo points; **code** draws the zones: grayscale → threshold walls → dilate (close door gaps) → flood-fill
  from each point → contour → simplified polygon → 0–1000 grid. Lantern's rule: models point well, they box badly.

## Screenshots are a product, not a log
Every run stores its screenshots under `rosetta/shots/` and returns them in `RosettaResult.screenshots`. Seraph keeps
them in `building.screenshots`, and they go to Silex as **visual references** for Halo views (the facade's
proportions, where the side door is, the plan). The dashboard shows them too.

## Agent cam
After each step, push a frame on `WS /ws/cam`: `{run_id, endpoint, step, action, thought (≤ 80 chars),
shot_url, page_url, at}`. The dashboard shows one tile per running endpoint. This is where Rosetta's work is visible.

## Concurrency, priority, cache
- Up to `ROSETTA_MAX_PARALLEL` (default 4) browsers. Priority queue (Seraph sends priorities: dispatch.read 10,
  maps.building 9, plan.read 9, occupants.list 8, others 5).
- Golden path cache: after each good live run for the reference address (`DEMO_ADDRESS`), store output + screenshots in `rosetta/cache/`.
  If a live run fails or times out and `allow_cache`, return the cache with `live:false`. The UI always says
  « cache ». Never invent steps.
- `POST /admin/cache/clear` for the real live demo run.

## Learning a source (`POST /explore`)
- Goal: answer a question from an **official** source. **Linkup** (web search API for agents) searches first,
  restricted to official hosts (`gouv.fr`, `service-public.fr`, `paris.fr`…), and its top 4 pages head the start
  page; the H agent opens one and reads the answer on screen. The fixed list in `rosetta/skills/_explore_start.md`
  (service-public.fr, data.gouv.fr, annuaire de l'éducation, the city's site…) follows, and is all there is without
  `LINKUP_API_KEY` or when Linkup fails (12 s timeout). The result says `found_by: linkup | liste`. Avoid search
  engines that show captchas.
- Saves a full trace (`GET /runs/{id}/trace`). The answer goes back to Seraph tagged `learned`, `verified:false`.
- Silex then has Devin turn the trace into `rosetta/skills/learned/<name>.md` (+ extraction code + test). Rosetta
  hot-loads new skill files; the endpoint counter goes up.

## Skill file format (`rosetta/skills/<endpoint>.md`)
```
---
name: georisques.risks
kind: real            # real | replica | learned
verified: true
start_url: https://www.georisques.gouv.fr/
params: { address: string }
timeout_s: 45
---
## Goal
## Steps (hints for the model, not a script)
## Success check (what code verifies on the page)
## Extraction (what code reads, and how)
## Known traps (consent banner, autocomplete must be clicked, …)
```

## Real-site traps to expect
Google consent page (accept once, persist profile) · Earth 3D needs WebGL (headed, GPU on) and time to load ·
Street View: drag to turn, arrows to move · Géorisques address field needs an autocomplete click · Météo-France
popups · any captcha → stop, return cache, say so in `error`.

## Mock mode (`MOCK=1`)
Returns `contracts/fixtures/endpoints/<name>.json` after a short delay, with placeholder JPEGs generated with Pillow
(grey, caption written on them). The agent cam shows « MOCK — aucun agent » frames, clearly. Never fake steps.
