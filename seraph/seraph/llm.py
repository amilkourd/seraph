"""LLM fallback for radio lines the rules did not match. Returns the event JSON only, never French to say.
Never used for confirm / cancel. Off when LLM_* is empty (visible on /health)."""
from __future__ import annotations

import json
import time
from typing import Any, Optional

import httpx

from .config import settings

EVENT_TYPES = ["question", "hazard", "team_update", "occupants_update", "view_request", "order_to_occupants",
               "report_request", "sitrep_request", "chatter"]

PROMPT = """Fire radio line → one JSON event. French fire service. No prose.
Types: question{topic: approach|hydrant|riser|wind|risks|building|air|stair|occupants|unknown_source}, hazard{kind: smoke|fire|heat|gas|structure|electric, where:{level?,room?,stair?,entrance?}, severity: low|medium|high},
team_update{team:{id:"B1",status?: engaged|exiting|out, pressure_bar_start?, location?:{level?,room?,stair?}}},
occupants_update{count?, room?, level?, status: moving|safe_outside, heading_to?}, view_request{purpose_fr},
order_to_occupants{target_text, order_fr}, report_request, sitrep_request, chatter.
Stairs are "A" or "B". Rooms like "3.12". Team ids "B<n>". Output: {"type": ..., ...fields}."""

state = {"last_ms": None, "last_error": None, "calls": 0}


async def extract(text: str, speaker: str, context: list[str], timeout_s: float = 2.5) -> Optional[dict[str, Any]]:
    if not settings.llm_enabled:
        return None
    url = settings.llm_base_url.rstrip("/") + "/chat/completions"
    body = {
        "model": settings.llm_model,
        "messages": [
            {"role": "system", "content": PROMPT},
            {"role": "user", "content": json.dumps({"speaker": speaker, "text": text, "recent": context[-10:]},
                                                   ensure_ascii=False)},
        ],
        "response_format": {"type": "json_object"},
        "reasoning_effort": "none",
        "service_tier": "priority",
    }
    t0 = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=timeout_s) as c:
            r = await c.post(url, json=body, headers={"Authorization": f"Bearer {settings.llm_api_key}"})
            r.raise_for_status()
            content = r.json()["choices"][0]["message"]["content"]
        ev = json.loads(content)
        state["calls"] += 1
        state["last_ms"] = int((time.perf_counter() - t0) * 1000)
        state["last_error"] = None
        if not isinstance(ev, dict) or ev.get("type") not in EVENT_TYPES:
            return None
        return _normalize(ev)
    except Exception as e:  # timeout, HTTP, JSON: the radio never waits on this
        state["last_error"] = type(e).__name__
        state["last_ms"] = int((time.perf_counter() - t0) * 1000)
        return None


def _normalize(ev: dict[str, Any]) -> dict[str, Any]:
    team = ev.get("team")
    if isinstance(team, dict) and team.get("id") is not None:
        digits = "".join(ch for ch in str(team["id"]) if ch.isdigit())
        team["id"] = f"B{digits}" if digits else None
    return ev
