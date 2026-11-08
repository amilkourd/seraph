"""Rosetta — FastAPI :8001. Screens without API → endpoints, run by our own Holo agent loop on Playwright."""

from __future__ import annotations

import asyncio
import re
import statistics
import time
from contextlib import asynccontextmanager
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from . import endpoints  # noqa: F401  (registers the endpoints)
from .config import SHOTS, TRACES, settings
from .core import ENDPOINTS, Run, browsers, cache, cam, now_iso, runner
from .skills import learned


@asynccontextmanager
async def lifespan(_: FastAPI):
    runner.start()
    yield
    await browsers.close()


app = FastAPI(title="Rosetta", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class RunIn(BaseModel):
    run_id: Optional[str] = None
    endpoint: str
    params: dict[str, Any] = Field(default_factory=dict)
    priority: int = 5
    allow_cache: bool = True


def new_id() -> str:
    import secrets
    return f"run_{int(time.time() * 1000):x}{secrets.token_hex(3)}"


@app.post("/run")
async def run(body: RunIn) -> dict:
    if body.endpoint not in ENDPOINTS:
        raise HTTPException(404, f"unknown endpoint {body.endpoint}")
    if body.endpoint == "report.fill" and not body.params.get("gate_id"):
        raise HTTPException(403, "report.fill needs params.gate_id (gate « send_report » confirmed)")
    r = Run(run_id=body.run_id or new_id(), endpoint=body.endpoint, params=body.params, priority=body.priority,
            allow_cache=body.allow_cache)
    await runner.submit(r)
    return {"run_id": r.run_id, "status": "queued"}


def masked(res: dict) -> dict:
    out = res.get("output") or {}
    if "occupants" in out:   # numbers only go to Seraph (push), never to other readers
        res = {**res, "output": {**out, "occupants": [{**o, "phone_e164": mask(o.get("phone_e164", ""))}
                                                      for o in out["occupants"]]}}
    return res


def mask(p: str) -> str:
    return p[:4] + "•" * max(0, len(p) - 6) + p[-2:] if len(p) > 6 else "••"


@app.get("/runs/{run_id}")
async def get_run(run_id: str) -> dict:
    r = runner.runs.get(run_id)
    if not r:
        raise HTTPException(404, "unknown run")
    return masked(r.result())


@app.get("/runs/{run_id}/trace")
async def get_trace(run_id: str) -> dict:
    r = runner.runs.get(run_id)
    if r:
        return masked(r.trace())
    f = TRACES / f"{run_id}.json"
    if f.exists():
        import json
        return masked(json.loads(f.read_text()))
    raise HTTPException(404, "unknown run")


@app.get("/runs")
async def list_runs(limit: int = 30) -> list[dict]:
    rs = list(runner.runs.values())[-limit:]
    return [{"run_id": r.run_id, "endpoint": r.endpoint, "status": r.status, "live": r.live,
             "duration_ms": r.result().get("duration_ms"), "steps": len(r.steps), "error": r.error} for r in rs][::-1]


@app.get("/shots/{name}.jpg")
async def shot(name: str):
    if not re.fullmatch(r"[\w.\-]+", name):
        raise HTTPException(400, "bad name")
    p = SHOTS / f"{name}.jpg"
    if not p.exists():
        raise HTTPException(404, "no such screenshot")
    return FileResponse(p, media_type="image/jpeg", headers={"Cache-Control": "no-cache"})


def _stat(xs: list[int]) -> dict:
    if not xs:
        return {"n": 0}
    return {"n": len(xs), "last_ms": xs[-1], "median_ms": int(statistics.median(xs)), "min_ms": min(xs)}


@app.get("/endpoints")
async def list_endpoints() -> list[dict]:
    cached = {(c["endpoint"]): c for c in cache.listing()}
    out = [{"name": e.name, "kind": e.kind, "verified": e.verified, "access": e.access, "timeout_s": e.timeout_s,
            "cache": e.cache, "params": e.params, "source": {"kind": e.source_kind, "label": e.source_label},
            "timings": {"live": _stat(e.stats["live"]), "cache": _stat(e.stats["cache"]), "failed": e.stats["failed"],
                        "runs": e.stats["runs"]},
            "golden_path": cached.get(e.name)} for e in ENDPOINTS.values() if e.name != "explore"]
    for s in learned():
        m = s["meta"]
        out.append({"name": m.get("name", s["file"][:-3]), "kind": "learned", "verified": m.get("verified") == "true",
                    "access": "read", "timeout_s": int(m.get("timeout_s", 60) or 60), "cache": None,
                    "params": m.get("params"), "source": {"kind": "learned", "label": "source non vérifiée"},
                    "timings": {}, "golden_path": None})
    return out


@app.get("/health")
async def health() -> dict:
    return {"ok": True, "service": "rosetta", "mock": settings.mock, "model": settings.holo_model, "agent_models": settings.agent_models, "point_models": settings.point_models, "rpm_per_model": settings.holo_rpm,
            "h_api_key": bool(settings.h_api_key), "headless": settings.headless,
            "parallel": settings.max_parallel, "active": runner.active, "queued": runner.queue.qsize(),
            "endpoints": len([n for n in ENDPOINTS if n != "explore"]) + len(learned()), "cache": len(cache.listing())}


@app.post("/admin/cache/clear")
async def cache_clear() -> dict:
    return {"ok": True, "cleared": cache.clear()}


@app.get("/admin/cache")
async def cache_list() -> list[dict]:
    return cache.listing()


class ExploreIn(BaseModel):
    question_fr: str
    hints: Optional[str] = None
    run_id: Optional[str] = None


@app.post("/explore")
async def explore(body: ExploreIn) -> dict:
    r = Run(run_id=body.run_id or new_id(), endpoint="explore", params={"question_fr": body.question_fr,
            "hints": body.hints or ""}, priority=6, allow_cache=False)
    await runner.submit(r)
    return {"run_id": r.run_id, "status": "queued"}


@app.websocket("/ws/cam")
async def ws_cam(ws: WebSocket) -> None:
    await ws.accept()
    q = cam.subscribe()
    try:
        while True:                      # keepalive = uvicorn's WS pings; every message is a frame
            await ws.send_json(await q.get())
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        cam.unsubscribe(q)


def main() -> None:
    import uvicorn
    uvicorn.run("rosetta.app:app", host="0.0.0.0", port=settings.port, log_level="info")


if __name__ == "__main__":
    main()
