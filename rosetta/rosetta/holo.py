"""Holo on H's OpenAI-compatible API: our own agent loop (navigate) and element localization (point).

Agent loop per hub.hcompany.ai/agent-loop: Step {note, thought, tool_call} in the system prompt and in
`structured_outputs`, clicks on a 0–1000 grid, only the 3 latest screenshots in context, tool errors fed back.
Localization per hub.hcompany.ai/element-localization: single turn, temperature 0, thinking off.
The model navigates and points; code verifies pages and reads data.
"""

from __future__ import annotations

import asyncio
import base64
import collections
import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Literal, Optional, Union

from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from .config import settings

W, H = 1280, 800
SETTLE_MS = 800

_client: Optional[AsyncOpenAI] = None


def client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.h_api_key, base_url=settings.h_base_url, max_retries=0)
    return _client


# ───────── tools (0–1000 grid) ─────────
class Click(BaseModel):
    """Click at (x, y)"""
    tool_name: Literal["click"]
    element: str = Field(description="Short description of the UI element to click")
    x: int = Field(description="X coordinate as integer in [0, 1000]")
    y: int = Field(description="Y coordinate as integer in [0, 1000]")


class DoubleClick(BaseModel):
    """Double-click at (x, y)"""
    tool_name: Literal["double_click"]
    element: str
    x: int
    y: int


class Write(BaseModel):
    """Type text into the focused element (click it first)"""
    tool_name: Literal["write"]
    content: str
    press_enter: bool = False


class TypeParam(BaseModel):
    """Type the exact value of a named task parameter into the focused element (click it first)"""
    tool_name: Literal["type_param"]
    name: str = Field(description="Name of the parameter whose value to type")
    press_enter: bool = False


class PressKey(BaseModel):
    """Press a key: Enter, Escape, Tab, ArrowDown, ArrowUp, ArrowLeft, ArrowRight, PageDown, PageUp"""
    tool_name: Literal["press_key"]
    key: str


class Scroll(BaseModel):
    """Scroll the page"""
    tool_name: Literal["scroll"]
    direction: Literal["up", "down"]


class Drag(BaseModel):
    """Drag from (x1, y1) to (x2, y2)"""
    tool_name: Literal["drag"]
    x1: int
    y1: int
    x2: int
    y2: int


class Wait(BaseModel):
    """Wait for the page to load"""
    tool_name: Literal["wait"]
    seconds: int = Field(default=2, description="1 to 5")


class GoBack(BaseModel):
    """Go back to the previous page"""
    tool_name: Literal["go_back"]


class Answer(BaseModel):
    """Finish: the task is done"""
    tool_name: Literal["answer"]
    content: str


ToolCall = Union[Click, DoubleClick, Write, TypeParam, PressKey, Scroll, Drag, Wait, GoBack, Answer]


class Step(BaseModel):
    note: Optional[str] = Field(default=None, description="Task-relevant information from the previous observation. Empty if nothing new.")
    thought: str = Field(description="Reasoning about next steps")
    tool_call: ToolCall


STEP_SCHEMA = Step.model_json_schema()
SYSTEM = f"""You are a computer-use agent operating a web browser ({W}x{H}).
Each turn you see a screenshot. Choose exactly one tool call. Coordinates are on a 0-1000 grid of the screenshot.
To type into a field, first click it, then use write (or type_param for a named parameter's exact value).
When the task is done, call answer. If you see a CAPTCHA or a bot check, do not try to solve it: answer "CAPTCHA".

<output_format>
```json
{json.dumps(STEP_SCHEMA)}
```
</output_format>"""


class Pacer:
    """H's quota is per model (~30 calls per minute window, measured 06:05: 429 « Too Many Requests for <model> »).
    Calls go to the first model of the list with room in its window; a 429 closes that model's window for a while."""

    def __init__(self, rpm: int) -> None:
        self.rpm = rpm
        self.hits: dict[str, collections.deque] = collections.defaultdict(collections.deque)
        self.closed_until: dict[str, float] = {}

    def _room(self, m: str, now: float) -> bool:
        q = self.hits[m]
        while q and now - q[0] > 60:
            q.popleft()
        return now >= self.closed_until.get(m, 0) and len(q) < self.rpm

    async def take(self, models: list[str], t_end: float) -> str:
        while True:
            now = time.time()
            for m in models:
                if self._room(m, now):
                    self.hits[m].append(now)
                    return m
            if now > t_end - 3:
                raise TimeoutError("quota H épuisé sur " + ", ".join(models))
            await asyncio.sleep(0.5)

    def close(self, m: str, seconds: float = 15) -> None:
        self.closed_until[m] = time.time() + seconds


pacer = Pacer(settings.holo_rpm)
_inflight: Optional[asyncio.Semaphore] = None


async def complete(budget_s: float, per_call_s: float, models: Optional[list[str]] = None, **kw):
    """One chat completion, paced per model, under a cap on in-flight calls. A hung call is cut at `per_call_s`
    (05:50: one call stalled 40 s); a 429 moves to the next model; retries while the run's budget lasts."""
    global _inflight
    if _inflight is None:
        _inflight = asyncio.Semaphore(settings.holo_max_inflight)
    models = models or settings.agent_models
    t_end = time.time() + budget_s
    while True:
        model = await pacer.take(models, t_end)
        async with _inflight:
            left = t_end - time.time()
            try:
                return await client().chat.completions.create(model=model, timeout=max(3.0, min(per_call_s, left)), **kw)
            except Exception as exc:
                name = type(exc).__name__
                if name not in ("APITimeoutError", "APIConnectionError", "InternalServerError", "RateLimitError") \
                        or t_end - time.time() < 4:
                    raise
                if name == "RateLimitError":
                    pacer.close(model)
        await asyncio.sleep(0.3)


def describe(call: ToolCall) -> str:
    """Action line for the agent cam. Clicks keep `(x,y)` on the 0–1000 grid: the dashboard draws the crosshair."""
    n = call.tool_name
    if n in ("click", "double_click"):
        return f"{n} ({call.x},{call.y}) {call.element}"[:120]
    if n == "write":
        return f"write « {call.content[:60]} »" + (" ⏎" if call.press_enter else "")
    if n == "type_param":
        return f"type_param {call.name}" + (" ⏎" if call.press_enter else "")
    if n == "press_key":
        return f"press_key {call.key}"
    if n == "scroll":
        return f"scroll {call.direction}"
    if n == "drag":
        return f"drag ({call.x1},{call.y1}) → ({call.x2},{call.y2})"
    if n == "wait":
        return f"wait {call.seconds}s"
    if n == "go_back":
        return "go_back"
    return f"answer « {call.content[:80]} »"


class Blocked(Exception):
    """CAPTCHA / bot check: stop the run, never try to pass it."""


CAPTCHA_URL = re.compile(r"google\.[a-z.]+/sorry/|/recaptcha/|captcha|challenge-platform|hcaptcha", re.I)
CAPTCHA_TEXT = re.compile(r"unusual traffic|trafic exceptionnel|not a robot|pas un robot|verify you are human|"
                          r"vérifiez que vous êtes humain|recaptcha|hcaptcha|captcha", re.I)


async def check_blocked(page) -> None:
    if CAPTCHA_URL.search(page.url or ""):
        raise Blocked(f"bot check at {page.url[:80]}")
    try:
        frames = [f.url for f in page.frames]
        if any(re.search(r"recaptcha/api2/(anchor|bframe)|hcaptcha\.com/captcha", u) for u in frames):
            raise Blocked("captcha iframe on the page")
        txt = await page.evaluate("() => (document.body && document.body.innerText || '').slice(0, 4000)")
        if CAPTCHA_TEXT.search(txt) and len(txt) < 3000:
            raise Blocked("captcha text on the page")
    except Blocked:
        raise
    except Exception:
        pass


@dataclass
class AgentResult:
    answered: bool
    answer: Optional[str]
    steps: int
    ok: bool
    detail: str = ""
    history: list[dict] = field(default_factory=list)


OnStep = Callable[[int, Step, str, bytes], Awaitable[Optional[str]]]   # → shot_url
Verify = Callable[[str], Awaitable[tuple[bool, str]]]
Guard = Callable[["ToolCall"], Awaitable[Optional[str]]]   # → error fed back instead of running the action


def _img(b: bytes) -> dict:
    return {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(b).decode()}}


def _trim(messages: list, keep: int = 3) -> None:
    seen = 0
    for m in reversed(messages):
        if isinstance(m.get("content"), list):
            seen += 1
            if seen > keep:
                m["content"] = "<observation>[older screenshot omitted]</observation>"


async def run_agent(page, task: str, *, on_step: OnStep, verify: Verify, hints: str = "",
                    params: Optional[dict[str, str]] = None, max_steps: int = 30, deadline: float = 0,
                    first_step: int = 0, guard: Optional[Guard] = None, forbid: frozenset = frozenset()) -> AgentResult:
    """Screenshot → Holo → one action → settle → next. On `answer`, code verifies; a failed check is fed back."""
    params = params or {}
    user = f"Task: {task}"
    if hints:
        user += f"\n\nHints:\n{hints}"
    if params:
        user += ("\n\nParameters (type one exactly with type_param and its name; never retype them with write): "
                 + "; ".join(f"{k} = « {v[:40]}{'…' if len(v) > 40 else ''} »" for k, v in params.items()))
    messages: list[dict] = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]
    history: list[dict] = []
    last_answer: Optional[str] = None
    for i in range(first_step, first_step + max_steps):
        if deadline and time.time() > deadline:
            return AgentResult(last_answer is not None, last_answer, i - first_step, False, "timeout", history)
        await check_blocked(page)
        img = await page.screenshot(type="jpeg", quality=80)
        messages.append({"role": "user", "content": [{"type": "text", "text": "<observation>\n"}, _img(img),
                                                     {"type": "text", "text": "\n</observation>"}]})
        _trim(messages)
        remaining = (deadline - time.time()) if deadline else 60
        resp = await complete(max(5, remaining), 15, settings.agent_models, messages=messages, temperature=0.6,
                              extra_body={"structured_outputs": {"json": STEP_SCHEMA}})
        raw = resp.choices[0].message.content or ""
        try:
            step = Step.model_validate_json(raw)
        except Exception as exc:
            messages.append({"role": "assistant", "content": raw[:2000]})
            messages.append({"role": "user", "content": f"<tool_output>ERROR: invalid step JSON ({str(exc)[:200]})</tool_output>"})
            continue
        messages.append({"role": "assistant", "content": step.model_dump_json()})
        call = step.tool_call
        action = describe(call)
        shot_url = await on_step(i, step, action, img)
        history.append({"step": i, "thought": step.thought, "note": step.note, "action": action, "shot_url": shot_url,
                        "page_url": page.url, "at": time.time()})
        if call.tool_name == "answer":
            last_answer = call.content
            if re.search(r"\bcaptcha\b", call.content, re.I):
                raise Blocked("the agent reported a CAPTCHA")
            ok, detail = await verify(call.content)
            if ok:
                return AgentResult(True, call.content, i - first_step + 1, True, detail, history)
            messages.append({"role": "user", "content": f'<tool_output tool="answer">\nERROR: not done yet, the page check failed: {detail}\n</tool_output>'})
            continue
        try:
            err = f"the {call.tool_name} tool is not allowed in this task" if call.tool_name in forbid else None
            if err is None and guard is not None:
                err = await guard(call)
            if err:
                result = f"ERROR: {err}"
            else:
                await execute(page, call, params)
                result = f"ok, url={page.url}"
        except Exception as exc:
            result = f"ERROR: {type(exc).__name__}: {str(exc)[:240]}"
        messages.append({"role": "user", "content": f'<tool_output tool="{call.tool_name}">\n{result}\n</tool_output>'})
    return AgentResult(last_answer is not None, last_answer, max_steps, False, "max steps", history)


async def execute(page, call: ToolCall, params: dict[str, str]) -> None:
    px = lambda x: max(0, min(W - 1, x / 1000 * W))   # noqa: E731
    py = lambda y: max(0, min(H - 1, y / 1000 * H))   # noqa: E731
    n = call.tool_name
    if n == "click":
        await page.mouse.click(px(call.x), py(call.y))
    elif n == "double_click":
        await page.mouse.dblclick(px(call.x), py(call.y))
    elif n == "write":
        await page.keyboard.type(call.content, delay=8)
        if call.press_enter:
            await page.keyboard.press("Enter")
    elif n == "type_param":
        if call.name not in params:
            raise ValueError(f"unknown parameter {call.name!r}; known: {', '.join(params)}")
        await page.keyboard.type(params[call.name], delay=4)
        if call.press_enter:
            await page.keyboard.press("Enter")
    elif n == "press_key":
        await page.keyboard.press(call.key)
    elif n == "scroll":
        await page.mouse.move(W / 2, H / 2)
        await page.mouse.wheel(0, 500 if call.direction == "down" else -500)
    elif n == "drag":
        await page.mouse.move(px(call.x1), py(call.y1))
        await page.mouse.down()
        await page.mouse.move(px(call.x2), py(call.y2), steps=12)
        await page.mouse.up()
    elif n == "wait":
        await page.wait_for_timeout(1000 * max(1, min(5, call.seconds)))
    elif n == "go_back":
        await page.go_back()
    await page.wait_for_timeout(SETTLE_MS)
    try:
        await page.wait_for_load_state("domcontentloaded", timeout=5000)
    except Exception:
        pass


# ───────── pointing ─────────
class Located(BaseModel):
    found: bool = Field(description="false if the target is not visible on the image")
    x: int = Field(ge=0, le=1000, description="X coordinate as integer in [0, 1000]")
    y: int = Field(ge=0, le=1000, description="Y coordinate as integer in [0, 1000]")


class Point(BaseModel):
    x: int = Field(ge=0, le=1000, description="X coordinate as integer in [0, 1000]")
    y: int = Field(ge=0, le=1000, description="Y coordinate as integer in [0, 1000]")


async def locate(img: bytes, target: str, *, may_be_absent: bool = True, timeout: float = 25) -> Optional[tuple[int, int]]:
    """One localization call. Returns a point on the 0–1000 grid of `img`, or None when Holo says it isn't there."""
    schema = (Located if may_be_absent else Point).model_json_schema()
    prompt = ("Localize an element on the image according to the provided target and output a click position.\n"
              + (" If the target is not visible on the image, set found to false.\n" if may_be_absent else "")
              + f" * You must output a valid JSON following the format: {json.dumps(schema)}\n"
              f" Your target is:\n{target}")
    resp = await complete(timeout, 8, settings.point_models, temperature=0.0,
        messages=[{"role": "user", "content": [_img(img), {"type": "text", "text": prompt}]}],
        extra_body={"structured_outputs": {"json": schema}, "chat_template_kwargs": {"enable_thinking": False}})
    raw = resp.choices[0].message.content or "{}"
    if may_be_absent:
        p = Located.model_validate_json(raw)
        return (p.x, p.y) if p.found else None
    p = Point.model_validate_json(raw)
    return (p.x, p.y)


async def ask_json(img: bytes, question: str, model: type[BaseModel], timeout: float = 40) -> BaseModel:
    """Single-turn visual question with a JSON schema (reading labels on a plan photo, etc.)."""
    schema = model.model_json_schema()
    resp = await complete(timeout, 15, settings.point_models, temperature=0.0,
        messages=[{"role": "user", "content": [_img(img), {"type": "text", "text":
                  f"{question}\nYou must output a valid JSON following the format: {json.dumps(schema)}"}]}],
        extra_body={"structured_outputs": {"json": schema}, "chat_template_kwargs": {"enable_thinking": False}})
    return model.model_validate_json(resp.choices[0].message.content or "{}")


async def gather_limited(coros: list[Awaitable[Any]], limit: int = 6) -> list[Any]:
    sem = asyncio.Semaphore(limit)

    async def one(c):
        async with sem:
            try:
                return await c
            except Exception as exc:  # one failed point never sinks the run
                return exc
    return await asyncio.gather(*(one(c) for c in coros))
