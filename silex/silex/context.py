"""What Devin is told: the warm context (playbook, rules, kit, examples), the request message, the fix message."""
from __future__ import annotations

import copy
import json
from typing import Any

from .config import KIT, PLAYBOOKS, REPO

EXAMPLE_FOR = {"approach": "approach", "team_engaged": "team_engaged", "occupants": "occupants",
               "inside_route": "inside_route", "commander_request": "occupants"}

# structured output Devin fills for every request (JSON Schema draft 7, self-contained)
VIEW_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "request_id": {"type": "string", "description": "the request_id of the VIEW REQUEST you answer"},
        "view_id": {"type": "string"},
        "attempt": {"type": "integer", "description": "1 for the first answer, +1 for each VIEW FIX"},
        "html": {"type": "string", "description": "the whole index.html"},
        "notes": {"type": "string", "description": "one short English line"},
    },
    "required": ["request_id", "view_id", "html"],
}

# Amil's rule, word for word, repeated in every request (warm sessions read the playbook only once)
LIVE_FACTS = "« Never write a hazard, level or room as literal text. Every fact in the card comes from the live state via Halo.onState at runtime, with its source tag. No hazard in the state means no fire in the view. »"

# every point carries the image it is on; a view draws on one frame
FRAMES_NOTE = """- frames: every point names its image (`image_id`). Draw one view on ONE frame, never mix two:
  the street side = `earth-top-01` (Rosetta: `building.footprint.polygon`, `entrances[].point`, `truck_spot.point`,
  `hydrants[].point`); the inside = the IFC plans `ifc-L<n>` (`entrances[].plan_point`, `rooms[].zone`,
  `stairs[].zones`, `routes[].path`). For « Par où j'entre », prefer the street side when `building.footprint`
  exists: footprint white, street, truck, arrow truck → chosen door. Points on Street View photos (`sv-*`,
  `evidence`) are not drawing coordinates."""

KIT_FILES = [("halo-kit.js", "text/javascript"), ("halo.css", "text/css"), ("check-view.mjs", "text/javascript"),
             ("examples/approach.html", "text/html"), ("examples/team_engaged.html", "text/html"),
             ("examples/occupants.html", "text/html"), ("examples/inside_route.html", "text/html")]


def _read(p) -> str:
    return p.read_text(encoding="utf-8")


def warm_prompt(kit_attachments: list[str]) -> str:
    """Context loaded once per warm session. Devin reads it, answers PRÊT and waits for a VIEW REQUEST."""
    files = "\n".join(f"- `{name}`" for name, _ in KIT_FILES)
    return f"""{_read(PLAYBOOKS / "view-playbook.md")}

## RULES.md — hard rules (verbatim, non-negotiable; `check-view.mjs` enforces them)
{_read(KIT / "RULES.md")}

## Kit README (the API)
{_read(KIT / "README.md")}

## Example `examples/approach.html` (verbatim)
```html
{_read(KIT / "examples" / "approach.html")}
```

## Example `examples/team_engaged.html` (verbatim)
```html
{_read(KIT / "examples" / "team_engaged.html")}
```

## Attachments in this message
{files}

## Now
Download the attachments into one folder (`halo-kit.js`, `halo.css`, `check-view.mjs`, `examples/`), read the kit
source and the examples so you know the API by heart, check that `node check-view.mjs examples/approach.html` prints
✓, then reply with one word: PRÊT. Do not build anything yet. Requests arrive as messages starting with
« VIEW REQUEST »; each one is a new view, answered through the structured output.
"""


def trim_state(state: dict) -> dict:
    """The state inline in the message: everything a view draws, without the bulky logs (the full one is attached)."""
    s = copy.deepcopy(state)
    s["timeline"] = (s.get("timeline") or [])[-3:]
    for k in ("gates", "rosetta"):
        s.pop(k, None)
    b = s.get("building") or {}
    for k in ("doors", "materials", "graph"):
        b.pop(k, None)
    for r in b.get("rooms") or []:
        for k in ("ifc_guid", "ifc_name"):
            r.pop(k, None)
    for c in s.get("calls") or []:
        for k in ("transcript", "transcript_excerpt"):
            c.pop(k, None)
    return s


def request_message(vr: dict, view_id: str, state: dict, refs: list[dict], cold: bool) -> str:
    example = EXAMPLE_FOR.get(vr.get("moment", ""), "approach")
    ref_lines = "\n".join(
        f"- `{r['name']}` — {r.get('caption') or r.get('image_id')} ({r.get('side') or '?'}"
        + (f", {r['width']}×{r['height']}" if r.get("width") else "") + ")"
        + ("" if r.get("attached") else " — not attached (unreachable), described only")
        for r in refs) or "- none"
    inter = "\n".join(f"- {i}" for i in vr.get("interactions") or []) or "- none beyond the kit's taps"
    stairs = ", ".join(st.get("id", "?") for st in (state.get("building") or {}).get("stairs") or []) or "none"
    head = "" if not cold else "(Context above. No need to reply PRÊT: build this view right away.)\n\n"
    return f"""{head}VIEW REQUEST {vr['request_id']}

- request_id: `{vr['request_id']}`
- view_id: `{view_id}` (put it in `<html data-view-id="{view_id}">`)
- moment: `{vr.get('moment')}` — start from `examples/{example}.html`
- purpose (French, from Seraph): « {vr.get('purpose_fr', '')} »
- data_keys (the state paths the view reads): {', '.join(f'`{k}`' for k in vr.get('data_keys') or []) or 'see purpose'}
- interactions:
{inter}
- deadline: {vr.get('deadline_s')} s from now. Aim to answer in under {max(60, int(vr.get('deadline_s') or 300) * 2 // 3)} s.
- this building's stairs: {stairs}. Draw only what the state has.
{FRAMES_NOTE}
- live facts: {LIVE_FACTS} The snapshot may be stale. Silex renders the view twice more, with no hazard (any fire
  or smoke left = rejected) and with a reported fire (the drawing or the card must change). Kit rule 16: hazards
  only with `Halo.fire/smoke(svg, zone, {{hazard}})`, card lines with `Halo.hazardLine(state, h)`, never type
  « Feu », « Fumée » or a level name.
- the kit changes during the night: re-read `halo/kit/RULES.md` and `halo/kit/README.md` now, before writing.

References (attached; use them only for shapes and proportions, never as a background image):
{ref_lines}

State snapshot (`state.json` is attached in full; below it is trimmed: no doors, materials, graph, old timeline):
```json
{json.dumps(trim_state(state), ensure_ascii=False, separators=(",", ":"))}
```

RULES.md as of now (it changes during the night; this version wins over the one in your context):
{_read(KIT / "RULES.md")}

Answer with the structured output: request_id `{vr['request_id']}`, view_id `{view_id}`, attempt 1, html, notes.
"""


def fix_message(request_id: str, view_id: str, attempt: int, errors: list[str]) -> str:
    errs = "\n".join(f"- {e}" for e in errors)
    return f"""VIEW FIX {request_id} — attempt {attempt}

Silex rejected `{view_id}` (it is never served while it fails). Fix exactly these and nothing else:
{errs}

Run `node check-view.mjs index.html` again, then update the structured output: request_id `{request_id}`,
view_id `{view_id}`, attempt {attempt}, the whole html, notes.
"""


def nudge_message(request_id: str, view_id: str) -> str:
    return (f"Silex has not received the view for {request_id}. Put the whole file in the structured output now "
            f"(request_id `{request_id}`, view_id `{view_id}`, html, notes), even if it is not perfect.")


# ───────── Devin CLI (local, in the repo root: files instead of inline text) ─────────
def cli_warm_prompt() -> str:
    return f"""{_read(PLAYBOOKS / "view-playbook.md")}

## You run on the team's laptop, in the repository root (Devin CLI)
Ignore the « attachments » wording above: every file is on disk. Read, in this order:
`halo/kit/RULES.md` (hard rules, non-negotiable), `halo/kit/README.md` (the API), `halo/kit/halo-kit.js` (the
source), `halo/kit/examples/approach.html`, `halo/kit/examples/team_engaged.html`, `halo/kit/examples/occupants.html`,
`halo/kit/examples/inside_route.html`, `halo/kit/check-view.mjs`.

Use your file read tool to read files (it opens images too: .jpg screenshots, .svg plans) and your file write
tool to write. Write only inside `silex/runtime/build/`. Never touch any other file of the repository, never read
`.env`, never run git. The only command you need is `node halo/kit/check-view.mjs <file>`.

## Now
Read those files so you know the kit by heart, then answer one word: PRÊT. Do not build anything yet. Requests
arrive as « VIEW REQUEST » prompts in this same session.
"""


def cli_request_prompt(vr: dict, view_id: str, out: str, notes: str, state_path: str, refs: list[dict], cold: bool) -> str:
    example = EXAMPLE_FOR.get(vr.get("moment", ""), "approach")
    shots = [r for r in refs if r.get("path") and r.get("side") != "plan"]
    plans = [r for r in refs if r.get("path") and r.get("side") == "plan"]
    missing = [r for r in refs if not r.get("path")]
    line = lambda r: (f"- `{r['path']}` — {r.get('caption') or r.get('image_id')} (side: {r.get('side') or '?'}"
                      + (", MOCK" if r.get("mock") else "") + ")")
    shot_lines = "\n".join(line(r) for r in shots) or "- none yet (Rosetta has not taken them)"
    plan_lines = "\n".join(line(r) for r in plans) or "- none"
    miss_lines = "".join(f"\n- not available: {r.get('image_id')} — {r.get('caption') or ''}" for r in missing)
    inter = "\n".join(f"- {i}" for i in vr.get("interactions") or []) or "- none beyond the kit's taps"
    stairs = ", ".join("stair " + st.get("id", "?") for st in ((json_load(state_path).get("building") or {}).get("stairs") or [])) or "no stair listed"
    head = cli_warm_prompt().split("## Now")[0] + "\n" if cold else ""
    bmap = ("\nThe building in one page (stairs, entrances, rooms, fire doors per level): `ifc/out/building.md` — read it first."
            if (REPO / "ifc" / "out" / "building.md").exists() else "")
    return f"""{head}VIEW REQUEST {vr['request_id']}

- view_id: `{view_id}` (put it in `<html data-view-id="{view_id}">`)
- moment: `{vr.get('moment')}` — start from a copy of `halo/kit/examples/{example}.html`
- purpose (French, from Seraph): « {vr.get('purpose_fr', '')} »
- data_keys (the state paths the view reads): {', '.join(f'`{k}`' for k in vr.get('data_keys') or []) or 'see purpose'}
- interactions:
{inter}
- live state: `{state_path}` (the IncidentState right now, without doors/materials/graph/old timeline). Read it with
  your file read tool. Draw only what it has: this building has {stairs}.
- deadline: {vr.get('deadline_s')} s from now. Be fast: copy the example, adapt it, check, done.
- legibility at arm's length: the arrow is the main shape (`width` ≥ 16, long); no tag over the arrow's shaft or
  head (put the entrance tag on the side away from the route).
{FRAMES_NOTE}
- live facts: {LIVE_FACTS} The snapshot may be stale. Silex renders the view twice more, with no hazard (any fire
  or smoke left = rejected) and with a reported fire (the drawing or the card must change). Kit rule 16: hazards
  only with `Halo.fire/smoke(svg, zone, {{hazard}})`, card lines with `Halo.hazardLine(state, h)`, never type
  « Feu », « Fumée » or a level name.
- the kit changes during the night: re-read `halo/kit/RULES.md` and `halo/kit/README.md` now, before writing.

## Build it FROM these images (open and look at every one of them with your read tool)
Screenshots Rosetta's H agent took of the real address during the drive (Street View, Google Earth):
{shot_lines}
The building's IFC level plans (source of truth for the building's shape; French intervention-plan conventions:
walls, door swings, stair flights, green circulation, risk triangles, E1/E2 access arrows, ladder points). They
share the 0–1000 frame of `building.rooms[].zone`, `doors[].plan_point` and `routes[].path`:
{plan_lines}{miss_lines}{bmap}

How to use them:
- The street context (which side the street runs along, where the façade and the doors are, the approach from the
  truck) comes from the screenshots. The building's footprint and inner shape come from the IFC plan. The demo
  address may not match the IFC building exactly: when they disagree, the IFC wins for the building, the
  screenshots win for the street.
- Images are references for shapes and layout only: never put a photo in the view, never load an image.
- Every position (entrances, stair, route, truck, hydrant) still comes from the state, never from an image.

## Output
1. Write the whole view to `{out}` with your file write tool.
2. Run `node halo/kit/check-view.mjs {out}` until it prints ✓.
3. Write `{notes}`: {{"summary": "<one English line: what the view shows>", "references": [{{"image": "<file name>",
   "took": "<what you took from that image, concrete: e.g. street runs along the south edge, side door on the left
   of the façade, ramp down on the left>"}}]}} — one entry per image listed above, each « took » naming a real
   feature you saw in it. Silex rejects the view if an image has no entry.
4. Answer with the summary line. Silex validates the view again and renders it with the live state before serving.
"""


def cli_fix_prompt(request_id: str, view_id: str, out: str, notes: str, attempt: int, errors: list[str]) -> str:
    errs = "\n".join(f"- {e}" for e in errors)
    return f"""VIEW FIX {request_id} — attempt {attempt}

Silex rejected `{out}` ({view_id}); it is never served while it fails. Fix exactly these and nothing else:
{errs}

Rewrite `{out}` (and `{notes}` if needed) with your file write tool, run `node halo/kit/check-view.mjs {out}` until ✓,
answer one short line.
"""


def json_load(path: str) -> dict:
    try:
        return json.loads((REPO / path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
