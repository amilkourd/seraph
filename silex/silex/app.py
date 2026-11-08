"""Silex HTTP service, :8002. Serves the views Devin built and the Halo kit they load. Contract: contracts/api.md."""
from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response

from . import cli
from .config import KIT, RUNTIME, VIEWS, settings
from .validate import renderer
from .views import silex

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
logging.getLogger("httpx").setLevel(logging.WARNING)      # its request lines carry the org id
NO_STORE = {"Cache-Control": "no-store"}
SAFE_ID = set("abcdefghijklmnopqrstuvwxyz0123456789_-")


@asynccontextmanager
async def lifespan(app: FastAPI):
    VIEWS.mkdir(parents=True, exist_ok=True)
    RUNTIME.mkdir(parents=True, exist_ok=True)
    if not settings.mock and settings.devin_ready:
        await silex.refresh_sessions()
        silex.spawn(silex.ensure_warm())
        silex.spawn(silex.watch_seraph())
    yield
    await renderer.close()


app = FastAPI(title="silex", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def _kit_url(request: Request) -> str:
    return settings.kit_url or str(request.base_url).rstrip("/") + "/kit"


def _view_dir(root: Path, view_id: str) -> Path:
    if not view_id or set(view_id) - SAFE_ID or view_id.startswith("_"):
        raise HTTPException(404, "no such view")
    return root / view_id


def _serve_html(path: Path, request: Request) -> HTMLResponse:
    if not path.exists():
        raise HTTPException(404, "no such view")
    html = path.read_text(encoding="utf-8").replace("{{HALO_KIT_URL}}", _kit_url(request))
    return HTMLResponse(html, headers=NO_STORE)


@app.get("/health")
async def health() -> dict:
    sess = [s for s in silex.sessions.values() if not s.mock]
    return {"ok": True, "mock": settings.mock, "service": "silex", "public_url": settings.public_url,
            "devin": {"configured": settings.devin_ready, "transport": settings.active_transport,
                      "asked": settings.transport, "cli_installed": cli.binary() is not None,
                      "model": settings.devin_model if settings.active_transport == "cli" else None,
                      "warm_idle": sum(s.status == "idle" for s in sess),
                      "warming": sum(s.status == "warming" for s in sess), "live": sum(s.live for s in sess)},
            "renderer": renderer.available, "views": len(list(VIEWS.glob("*/view.json")))}


# ───────── views ─────────
@app.post("/views/request")
async def views_request(vr: dict) -> dict:
    return silex.request(vr)


_KIT_CHECK: dict[str, tuple[float, bool]] = {}     # view_id → (mtime of view + kit rules, passes today's kit)


def _passes_kit(view_id: str) -> bool:
    """The kit's rules change during the night: a view built earlier may no longer pass check-view.mjs."""
    import subprocess
    p = VIEWS / view_id / "index.html"
    stamp = max(p.stat().st_mtime, (KIT / "check-view.mjs").stat().st_mtime)
    hit = _KIT_CHECK.get(view_id)
    if hit and hit[0] == stamp:
        return hit[1]
    ok = subprocess.run(["node", str(KIT / "check-view.mjs"), str(p)], capture_output=True, timeout=20).returncode == 0
    _KIT_CHECK[view_id] = (stamp, ok)
    return ok


def _list_views() -> list[dict]:
    out = []
    for p in sorted(VIEWS.glob("*/view.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            meta = json.loads(p.read_text())
        except ValueError:
            continue
        meta["url"] = f"{settings.public_url}/views/{meta['view_id']}/"
        meta["passes_kit"] = _passes_kit(meta["view_id"])
        out.append(meta)
    return out


@app.get("/views")
async def views_list() -> list[dict]:
    return _list_views()


@app.get("/views/{view_id}")
async def view_noslash(view_id: str) -> RedirectResponse:
    return RedirectResponse(f"/views/{view_id}/")


@app.get("/views/{view_id}/")
async def view_index(view_id: str, request: Request) -> HTMLResponse:
    return _serve_html(_view_dir(VIEWS, view_id) / "index.html", request)


@app.get("/views/{view_id}/{name}")
async def view_file(view_id: str, name: str, request: Request) -> Response:
    if name == "index.html":
        return _serve_html(_view_dir(VIEWS, view_id) / "index.html", request)
    if name not in ("view.json", "preview.png"):
        raise HTTPException(404, "no such file")
    p = _view_dir(VIEWS, view_id) / name
    if not p.exists():
        raise HTTPException(404, "no such file")
    return FileResponse(p, headers=NO_STORE)


@app.get("/views/{view_id}/refs/{name}")
async def view_ref(view_id: str, name: str) -> FileResponse:
    """The screenshots and plans the view was drawn from (dashboard: « screenshot → view »)."""
    p = _view_dir(VIEWS, view_id) / "refs" / Path(name).name
    if not p.is_file():
        raise HTTPException(404, "no such reference")
    return FileResponse(p, headers=NO_STORE)


@app.get("/_staging/{view_id}/")
async def staging(view_id: str, request: Request) -> HTMLResponse:
    """A candidate view, for Silex's own headless render. Never what Halo loads."""
    return _serve_html(_view_dir(RUNTIME / "staging", view_id) / "index.html", request)


@app.get("/kit/{path:path}")
async def kit(path: str) -> FileResponse:
    p = (KIT / path).resolve()
    if not str(p).startswith(str(KIT.resolve())) or not p.is_file():
        raise HTTPException(404, "not in the kit")
    return FileResponse(p, headers=NO_STORE)


# ───────── Devin sessions ─────────
@app.get("/sessions")
async def sessions() -> list[dict]:
    return silex.list_sessions()


@app.get("/requests")
async def requests() -> list[dict]:
    return silex.list_jobs()


@app.post("/warm")
async def warm() -> dict:
    return await silex.ensure_warm()


@app.post("/admin/stop_all")
async def stop_all() -> dict:
    return {"terminated": await silex.stop_all()}


def main() -> None:
    import uvicorn
    uvicorn.run("silex.app:app", host="0.0.0.0", port=settings.port, proxy_headers=True, forwarded_allow_ips="*")


if __name__ == "__main__":
    main()
