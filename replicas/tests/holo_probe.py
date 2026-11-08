"""Holo agent loop on the replicas (H's agent-loop recipe). Not Rosetta: a probe that the screens work for Holo.

    cd replicas && uv run --with openai python tests/holo_probe.py holo4-35b-a3b /tmp/holo-shots [flow ...]

Code logs in (the model never sees the password); Holo navigates; code verifies the page. Resets before and after.
"""

from __future__ import annotations

import base64
import json
import re
import sys
import time
import urllib.request
from pathlib import Path
from typing import Literal

from openai import OpenAI
from playwright.sync_api import sync_playwright
from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from legacy.common import env, fixture  # noqa: E402

W, H = 1280, 800


class ClickArgs(BaseModel):
    """Click at (x, y) coordinates"""
    tool_name: Literal["click"]
    element: str = Field(description="Detailed description of the target UI element to click on")
    x: int = Field(description="X coordinate as integer in [0, 1000]")
    y: int = Field(description="Y coordinate as integer in [0, 1000]")


class WriteArgs(BaseModel):
    """Type text into the currently focused element without clicking first"""
    tool_name: Literal["write"]
    content: str = Field(description="Content to write")
    press_enter: bool = Field(default=False, description="Whether to press Enter after typing")


class ScrollArgs(BaseModel):
    """Scroll the page"""
    tool_name: Literal["scroll"]
    direction: Literal["up", "down"]


class AnswerArgs(BaseModel):
    """Provide a final answer"""
    tool_name: Literal["answer"]
    content: str = Field(description="The answer content")


class Step(BaseModel):
    note: str | None = Field(default=None, description="Task-relevant information from the previous observation. Empty if nothing new.")
    thought: str = Field(description="Reasoning about next steps")
    tool_call: ClickArgs | WriteArgs | ScrollArgs | AnswerArgs


SCHEMA = Step.model_json_schema()
SYSTEM = f"""You are a computer-use agent operating a web browser (1280x800) on legacy software.
Each turn you see a screenshot. Choose exactly one tool call. Coordinates are on a 0-1000 grid of the screenshot.
To type into a field, first click it, then use write. When the task is done, call answer.

<output_format>
```json
{json.dumps(SCHEMA)}
```
</output_format>"""

LOGIN = "You are already logged in."
ENTRY = "01:12 Appel OCC-03 : 2 personnes salle 3.12, fumée sous la porte."
REPORT = {
    "Chronologie": "00:00 alerte. 00:08 arrivée FPT 1. 00:31 feu éteint.",
    "Moyens engagés": "FPT 1, EPA 1, VSAV 1. Binôme 1 sous ARI.",
    "Victimes": "Aucune victime. 2 personnes mises en sécurité salle 3.12.",
    "Observations": "Local technique 3e étage. Porte coupe-feu efficace.",
}

FLOWS = {
    "dispatch.read": ("http://localhost:8101/interventions",
                      f"{LOGIN} Then open the most recent intervention whose status is « En cours ». "
                      "When its detail page is displayed, answer with its number, address, nature and level."),
    "occupants.list": ("http://localhost:8103/batiments",
                       f"{LOGIN} Then open the building « {fixture('occupants.json')['building']} » and display its occupant table. "
                       "Answer with the number of occupants listed when the table is visible."),
    "dispatch.write_112": ("http://localhost:8101/interventions",
                           f"{LOGIN} Then open intervention INC-0001. In its « Main courante » section, type exactly "
                           f"this entry: {ENTRY} and click « Ajouter ». Answer once the entry appears in the list."),
    "report.fill": ("http://localhost:8102/comptes-rendus",
                    f"{LOGIN} Then create a new compte rendu for intervention INC-0001. Fill the four sections with "
                    "exactly these texts: " + " ; ".join(f"{k} = « {v} »" for k, v in REPORT.items()) +
                    ". Click « Enregistrer », then on the next page click « Transmettre ». "
                    "Answer when the état shows « Transmis »."),
}


def verify(name: str, page) -> tuple[bool, str]:
    """Code checks the page and reads the DOM; never the model's answer."""
    try:
        if name == "dispatch.read":
            want = str(fixture("endpoints/dispatch.read.json")["output"]["level"])
            ok = bool(re.search(r"/interventions/INC-0001$", page.url)) and page.inner_text("#f-niveau") == want
            return ok, f"{page.inner_text('#f-numero')} | {page.inner_text('#f-nature')}"
        if name == "occupants.list":
            n = page.locator("#occupants tbody tr[data-id]").count()
            return page.url.endswith("/batiments/1") and n >= 6, f"{n} rows"
        if name == "dispatch.write_112":
            first = page.locator("#main-courante-liste tbody tr").first
            text = first.locator(".c-texte").inner_text()
            return text == ENTRY, f"{first.get_attribute('data-id')}: {text}"
        if name == "report.fill":
            etat = page.inner_text("#cr-etat")
            got = {k: page.inner_text(f"#cr-{key}") for k, key in
                   zip(REPORT, ["chronologie", "moyens", "victimes", "observations"])}
            diffs = [k for k in REPORT if got[k] != REPORT[k]]
            return etat == "Transmis" and not diffs, f"état={etat} mismatched={diffs}"
    except Exception as exc:
        return False, f"verify error: {exc!r}"[:200]
    return False, "unknown flow"


def trim_images(messages: list, n: int = 3) -> None:
    seen = 0
    for m in reversed(messages):
        if isinstance(m["content"], list):
            seen += 1
            if seen > n:
                m["content"] = "<observation>[older screenshot omitted]</observation>"


def run_flow(client: OpenAI, model: str, browser, name: str, shots: Path) -> dict:
    url, task = FLOWS[name]
    ctx = browser.new_context(viewport={"width": W, "height": H})
    page = ctx.new_page()
    page.goto(url)
    if "/login" in page.url:  # code logs in; the model never sees or types the password
        page.fill("#username", "operateur")
        page.fill("#password", env("REPLICA_PASSWORD"))
        page.click("#btn-connexion")
        page.wait_for_load_state()
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": f"Task: {task}"}]
    t0, steps, answer = time.time(), [], None
    for i in range(25):
        img = page.screenshot(type="jpeg", quality=80)
        (shots / f"{name}-{i:02d}.jpg").write_bytes(img)
        messages.append({"role": "user", "content": [
            {"type": "text", "text": "<observation>\n"},
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(img).decode()}},
            {"type": "text", "text": "\n</observation>"}]})
        trim_images(messages)
        resp = client.chat.completions.create(model=model, messages=messages, temperature=0.6, timeout=90,
                                              extra_body={"structured_outputs": {"json": SCHEMA}})
        step = Step.model_validate_json(resp.choices[0].message.content)
        messages.append({"role": "assistant", "content": step.model_dump_json()})
        call = step.tool_call
        line = f"  {i:02d} {call.tool_name:6} " + {
            "click": lambda c: f"({c.x},{c.y}) {c.element}",
            "write": lambda c: repr(c.content) + (" ⏎" if c.press_enter else ""),
            "scroll": lambda c: c.direction,
            "answer": lambda c: c.content,
        }[call.tool_name](call)
        print(line[:170], flush=True)
        steps.append(line)
        if call.tool_name == "answer":
            answer = call.content
            break
        try:
            if call.tool_name == "click":
                page.mouse.click(call.x / 1000 * W, call.y / 1000 * H)
            elif call.tool_name == "write":
                page.keyboard.type(call.content, delay=5)
                if call.press_enter:
                    page.keyboard.press("Enter")
            elif call.tool_name == "scroll":
                page.mouse.wheel(0, 500 if call.direction == "down" else -500)
            page.wait_for_timeout(800)
            page.wait_for_load_state()
            result = f"ok, url={page.url}"
        except Exception as exc:
            result = f"ERROR: {exc!r}"[:300]
        messages.append({"role": "user", "content": f'<tool_output tool="{call.tool_name}">\n{result}\n</tool_output>'})
    ok, detail = verify(name, page)
    page.screenshot(path=str(shots / f"{name}-final.png"))
    ctx.close()
    return {"pass": ok and answer is not None, "steps": len(steps), "seconds": round(time.time() - t0),
            "verified": detail, "answered": answer is not None}


def reset() -> None:
    for base, q in [("http://localhost:8101", ""), ("http://localhost:8102", ""), ("http://localhost:8103", "?scope=all")]:
        urllib.request.urlopen(urllib.request.Request(base + "/admin/reset" + q, method="POST"), timeout=5).read()


def main() -> None:
    model, shots = sys.argv[1], Path(sys.argv[2])
    names = sys.argv[3:] or list(FLOWS)
    shots.mkdir(parents=True, exist_ok=True)
    client = OpenAI(api_key=env("H_API_KEY"), base_url=env("H_API_BASE_URL", "https://api.hcompany.ai/v1/"))
    reset()
    results = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome")
        for name in names:
            print(f"== {name} ({model})", flush=True)
            try:
                results[name] = run_flow(client, model, browser, name, shots)
            except Exception as exc:
                results[name] = {"pass": False, "error": repr(exc)[:300]}
            print("  ->", json.dumps(results[name], ensure_ascii=False), flush=True)
        browser.close()
    reset()
    print("SUMMARY", json.dumps({k: v["pass"] for k, v in results.items()}))


if __name__ == "__main__":
    main()
