"""Helpers shared by the endpoints: the agent loop wired to the agent cam, replica login, deadlines."""

from __future__ import annotations

import time
from typing import Optional

from ..config import settings
from ..core import ENDPOINTS, Run, RunFailed
from ..holo import AgentResult, Guard, Step, Verify, run_agent
from ..skills import hints as skill_hints


def deadline(run: Run, margin_s: float = 4) -> float:
    return run.started_at + ENDPOINTS[run.endpoint].timeout_s - margin_s


async def agent(run: Run, task: str, verify: Verify, *, params: Optional[dict[str, str]] = None,
                max_steps: int = 30, hints: Optional[str] = None, until: Optional[float] = None,
                guard: Optional[Guard] = None, forbid: frozenset = frozenset()) -> AgentResult:
    async def on_step(i: int, step: Step, action: str, img: bytes) -> str:
        return await run.frame(action, step.thought, img, step=i)

    res = await run_agent(run.page, task, on_step=on_step, verify=verify,
                          hints=skill_hints(run.endpoint) if hints is None else hints, params=params,
                          max_steps=min(max_steps, 30 - run.step_n), deadline=until or deadline(run),
                          first_step=run.step_n, guard=guard, forbid=forbid)
    run.extra["answer"] = res.answer
    if not res.ok:
        raise RunFailed(f"agent: {res.detail} après {res.steps} étapes")
    return res


async def replica_login(run: Run, base: str, start: str) -> None:
    """Code logs in (the model never sees nor types the password), then hands the page to Holo."""
    page = run.page
    await page.goto(base + start, wait_until="domcontentloaded", timeout=10000)
    if "/login" in page.url:
        await run.frame("connexion (code, pas le modèle)", "Identifiants saisis par le code")
        await page.fill("#username", "operateur")
        await page.fill("#password", settings.replica_password)
        await page.click("#btn-connexion")
        await page.wait_for_load_state("domcontentloaded")
        if "/login" in page.url:
            raise RunFailed("connexion refusée par le logiciel")


async def text(page, sel: str, timeout: int = 1500) -> str:
    return (await page.locator(sel).first.inner_text(timeout=timeout)).strip()


def elapsed(run: Run) -> float:
    return time.time() - (run.started_at or time.time())
