"""Seraph FastAPI service on :8000. `uv run seraph` (or uvicorn seraph.app:app --port 8000)."""
from __future__ import annotations

import asyncio
import json
import time
from contextlib import asynccontextmanager
from typing import Any, Optional

from fastapi import Body, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from . import building as B
from . import llm
from .brain import Brain
from .config import SERVICE_DIR, settings
from .io import Bus, GabrielHub, MockGabriel, Rosetta, Silex
from .models import dump
from .replay import Replayer

SNAPSHOT = SERVICE_DIR / "state.json"

brain = Brain()
bus = Bus()
hub = GabrielHub()
rosetta = Rosetta(brain)
silex = Silex(brain)
mock_gabriel = MockGabriel(brain, hub)
replayer = Replayer(brain, mock_gabriel)


def _send_gabriel(msg: dict) -> None:
    hub.send(msg)
    if msg.get("kind") == "place_calls":
        mock_gabriel.on_place_calls(msg["calls"])


brain.publish = bus.publish
brain.send_gabriel = _send_gabriel
brain.run_rosetta = rosetta.run
brain.explore = rosetta.explore
brain.request_view_out = silex.request
brain.learn_out = silex.learn


async def state_loop() -> None:
    """state SSE ≤ 4/s, timers every second, snapshot on change (≤ 1/s)."""
    sent = saved = -1
    last_tick = last_save = 0.0
    while True:
        await asyncio.sleep(0.25)
        now = time.monotonic()
        if now - last_tick >= 1.0:
            last_tick = now
            try:
                brain.tick()
            except Exception as e:  # a timer bug must never stop the stream
                print("tick error", repr(e))
        if brain.version != sent:
            sent = brain.version
            bus.publish("state", dump(brain.state))
        if brain.version != saved and now - last_save >= 1.0:
            saved, last_save = brain.version, now
            try:
                tmp = SNAPSHOT.with_suffix(".tmp")
                tmp.write_text(json.dumps(brain.snapshot(), ensure_ascii=False), encoding="utf-8")
                tmp.replace(SNAPSHOT)
            except Exception as e:
                print("snapshot error", repr(e))


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if SNAPSHOT.exists():
        try:
            brain.restore(json.loads(SNAPSHOT.read_text(encoding="utf-8")))
        except Exception as e:
            print("snapshot ignored", repr(e))
    task = asyncio.create_task(state_loop())
    yield
    task.cancel()


app = FastAPI(title="Seraph", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"], allow_credentials=False)


@app.get("/health")
async def health() -> dict:
    return {"ok": True, "mock": settings.mock, "service": "seraph",
            "llm": {"enabled": settings.llm_enabled, "model": settings.llm_model if settings.llm_enabled else None,
                    "last_ms": llm.state["last_ms"], "last_error": llm.state["last_error"], "calls": llm.state["calls"]},
            "gabriel": {"connected": hub.connected, "mock_calls": mock_gabriel.active()},
            "rosetta": {"reachable": rosetta.reachable, "mock": settings.mock},
            "silex": {"reachable": silex.reachable, "mock": settings.mock},
            "building": {"source": str(brain.kit.path.name) if brain.kit.path.name else None,
                         "model": brain.state.building.model.provenance if brain.state.building.model else
                         ("fixture" if brain.kit.adj else "none"),
                         "name": brain.state.building.name},
            "replay": replayer.status, "incident": brain.state.incident.status,
            "view_moments": sorted(settings.view_moments)}


@app.get("/state")
async def get_state() -> JSONResponse:
    return JSONResponse(dump(brain.state))


@app.get("/stream")
async def stream(request: Request, client: str = "dashboard") -> StreamingResponse:
    q = bus.subscribe(client)

    async def gen():
        try:
            yield f"retry: 2000\nevent: state\ndata: {json.dumps(dump(brain.state), ensure_ascii=False)}\n\n"
            cv = brain.state.halo.current_view
            if cv:
                yield f"event: halo_view\ndata: {json.dumps({'view_id': cv.view_id, 'url': cv.url, 'moment': cv.moment, 'built_by': cv.built_by})}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event, payload = await asyncio.wait_for(q.get(), timeout=15)
                    yield f"event: {event}\ndata: {payload}\n\n"
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            bus.unsubscribe(q)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"})


@app.post("/incident/start")
async def incident_start(body: Optional[dict] = Body(default=None)) -> JSONResponse:
    brain.start_incident((body or {}).get("incident_id"))
    return JSONResponse(dump(brain.state))


@app.get("/building/files/{path:path}")
async def building_files(path: str) -> FileResponse:
    p = B.files_path(brain.kit, path)
    if not p:
        raise HTTPException(404, "not found")
    return FileResponse(p)


@app.post("/rosetta/results")
async def rosetta_results(res: dict) -> dict:
    brain.on_rosetta_result(res)
    return {"ok": True}


@app.post("/silex/views")
async def silex_views(vr: dict) -> dict:
    brain.on_view_ready(vr)
    return {"ok": True}


@app.post("/silex/endpoints")
async def silex_endpoints(body: dict) -> dict:
    name = body.get("name", "")
    st = body.get("status")
    eps = brain.state.rosetta.endpoints
    ep = next((e for e in eps if e.name == name), None)
    if st == "ready" and not ep:
        from .models import EndpointStatus
        eps.append(EndpointStatus(name=name, kind="learned", verified=False, status="idle"))
        brain._count_endpoints()
    brain.publish("silex", body)
    brain.log("silex", f"Endpoint appris {name} : {st}" + (" (test OK)" if body.get("test_passed") else "") + ".")
    brain.touch()
    return {"ok": True}


@app.post("/halo/tap")
async def halo_tap(target: dict) -> dict:
    brain.log("seraph", f"Halo : tap {target.get('kind')} {target.get('id')}.")
    brain.publish("halo_tap", target)
    return {"ok": True}


@app.post("/gates/{gate_id}/confirm")
async def gate_confirm(gate_id: str) -> dict:
    g = brain.resolve_gate(gate_id, True, "dashboard")
    if not g:
        raise HTTPException(404, "no pending gate with this id")
    return {"ok": True}


@app.post("/gates/{gate_id}/cancel")
async def gate_cancel(gate_id: str) -> dict:
    g = brain.resolve_gate(gate_id, False, "dashboard")
    if not g:
        raise HTTPException(404, "no pending gate with this id")
    return {"ok": True}


@app.post("/say")
async def say(body: dict) -> dict:
    brain.say(body["text"], target=body.get("target"), lang=body.get("lang", "fr"))
    return {"ok": True}


@app.post("/ask")
async def ask(body: dict) -> dict:
    """A question typed on the dashboard / eval: same path as a radio line from the COS."""
    t = time.monotonic()
    text = body.get("question_fr") or body.get("text") or ""
    res = await brain.on_radio({"kind": "radio_transcript", "utterance_id": f"ask_{int(t * 1000)}", "room": "crew",
                                "speaker": body.get("speaker", "COS"), "lang": "fr",
                                "text": text if text.lower().startswith("seraph") else f"Seraph, {text}"})
    return {"ok": True, **res}


@app.post("/admin/reset")
async def admin_reset() -> dict:
    if replayer.task and not replayer.task.done():
        replayer.task.cancel()
    brain.reset()
    replayer.status = "idle"
    mock_gabriel.plays.clear()
    import httpx
    async with httpx.AsyncClient(timeout=2) as c:
        for url in settings.replicas.values():
            try:
                await c.post(f"{url}/admin/reset")
            except Exception:
                pass
    return {"ok": True}


@app.post("/admin/replay")
async def admin_replay(body: Optional[dict] = Body(default=None)) -> dict:
    body = body or {}
    fixture = body.get("fixture", "all")
    if fixture not in ("all", "radio", "calls"):
        raise HTTPException(400, "fixture must be radio, calls or all")
    replayer.start(fixture, float(body.get("speed", 1)))
    return {"ok": True, "fixture": fixture}


@app.post("/admin/replay_line")
async def admin_replay_line(body: dict) -> dict:
    res = await replayer.line(body.get("id", ""))
    if res is None:
        raise HTTPException(404, "unknown fixture line id (R01…R12 or CALL-01…CALL-06)")
    return {"ok": True, **res}


@app.post("/admin/call_now")
async def admin_call_now(body: Optional[dict] = Body(default=None)) -> dict:
    ids = (body or {}).get("occupant_ids")
    calls = [{"occupant_id": o.id, "phone_e164": brain.phones[o.id], "name": o.name, "language_hint": o.language or "fr"}
             for o in brain.state.occupants if o.id in brain.phones and (not ids or o.id in ids)]
    if calls:
        brain.place_calls(calls)
    return {"ok": True, "count": len(calls)}


@app.post("/admin/moment")
async def admin_moment(body: dict) -> dict:
    ok = brain.show_moment(body["moment"], explicit=True)
    return {"ok": ok}


@app.websocket("/ws/gabriel")
async def ws_gabriel(ws: WebSocket) -> None:
    await ws.accept()
    hub.sockets.add(ws)
    brain.log("seraph", f"Gabriel connecté ({hub.connected}).")
    try:
        while True:
            raw = await ws.receive_text()
            hub.last_seen = time.time()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await ws.send_text(json.dumps({"kind": "error", "error": "bad json"}))
                continue
            kind = msg.get("kind")
            try:
                if kind == "radio_transcript":
                    await brain.on_radio(msg)
                elif kind == "call_event":
                    brain.on_call_event(msg)
                elif kind == "call_facts":
                    brain.on_call_facts(msg)
                elif kind == "metric":   # Gabriel's own timings (eot → transcript, say → spoken)
                    brain.publish("metric", msg)
                else:
                    await ws.send_text(json.dumps({"kind": "error", "error": f"unknown kind {kind}"}))
            except Exception as e:
                print("ws handler error", kind, repr(e))
                await ws.send_text(json.dumps({"kind": "error", "error": type(e).__name__}))
    except WebSocketDisconnect:
        pass
    finally:
        hub.sockets.discard(ws)
        brain.log("seraph", f"Gabriel déconnecté ({hub.connected}).")


def main() -> None:
    import uvicorn
    uvicorn.run("seraph.app:app", host="0.0.0.0", port=8000, log_level="info", timeout_graceful_shutdown=2)
