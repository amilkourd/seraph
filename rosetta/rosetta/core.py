"""Runs: shots store, agent cam hub, golden-path cache, priority queue (≤ N browsers), push to Seraph."""

from __future__ import annotations

import asyncio
import io
import itertools
import json
import re
import shutil
import time
import traceback
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Optional

import httpx
from PIL import Image

from .config import CACHE, PROFILES, SHOTS, TRACES, settings


def now_iso(t: Optional[float] = None) -> str:
    d = datetime.fromtimestamp(t or time.time(), tz=timezone.utc)
    return d.strftime("%Y-%m-%dT%H:%M:%S.") + f"{d.microsecond // 1000:03d}Z"


def slug(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:80] or "x"


def shot_url(name: str, v: str = "") -> str:
    return f"{settings.public_url}/shots/{name}.jpg" + (f"?v={v}" if v else "")


def to_jpeg(img: bytes) -> tuple[bytes, int, int]:
    im = Image.open(io.BytesIO(img))
    w, h = im.size
    if im.format == "JPEG":
        return img, w, h
    buf = io.BytesIO()
    im.convert("RGB").save(buf, "JPEG", quality=85)
    return buf.getvalue(), w, h


# ───────── agent cam ─────────
class CamHub:
    def __init__(self) -> None:
        self.clients: set[asyncio.Queue] = set()
        self.last: dict[str, dict] = {}            # run_id → last frame (late joiners get the running ones)

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=200)
        self.clients.add(q)
        for f in list(self.last.values())[-12:]:
            q.put_nowait(f)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self.clients.discard(q)

    def push(self, frame: dict) -> None:
        self.last[frame["run_id"]] = frame
        if len(self.last) > 40:
            self.last.pop(next(iter(self.last)))
        for q in list(self.clients):
            try:
                q.put_nowait(frame)
            except asyncio.QueueFull:
                pass


cam = CamHub()


# ───────── a run ─────────
@dataclass
class Run:
    run_id: str
    endpoint: str
    params: dict
    priority: int = 5
    allow_cache: bool = True
    status: str = "queued"
    live: bool = True
    output: Optional[dict] = None
    screenshots: list[dict] = field(default_factory=list)
    source: Optional[dict] = None
    error: Optional[str] = None
    queued_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    ended_at: Optional[float] = None
    steps: list[dict] = field(default_factory=list)
    step_n: int = 0
    extra: dict = field(default_factory=dict)
    page: Any = None
    context: Any = None

    # screenshots that are part of the result (the product, not the log)
    def add_shot(self, image_id: str, img: bytes, caption: str, side: Optional[str] = None) -> dict:
        data, w, h = to_jpeg(img)
        name = f"{self.run_id}--{image_id}"
        (SHOTS / f"{name}.jpg").write_bytes(data)
        s = {"image_id": image_id, "url": shot_url(name), "caption": caption, "width": w, "height": h,
             "taken_at": now_iso(), "_file": name}
        if side:
            s["side"] = side
        self.screenshots = [x for x in self.screenshots if x["image_id"] != image_id] + [s]
        return s

    def shot_bytes(self, image_id: str) -> bytes:
        s = next(x for x in self.screenshots if x["image_id"] == image_id)
        return (SHOTS / f"{s['_file']}.jpg").read_bytes()

    async def frame(self, action: str, thought: str = "", img: Optional[bytes] = None, step: Optional[int] = None) -> str:
        """One agent-cam frame: the screenshot the action refers to, the action, a short thought."""
        if step is None:
            step = self.step_n
        self.step_n = max(self.step_n, step + 1)
        url = ""
        if img is None and self.page is not None:
            try:
                img = await self.page.screenshot(type="jpeg", quality=70)
            except Exception:
                img = None
        if img is not None:
            name = f"{self.run_id}-s{step:02d}"
            (SHOTS / f"{name}.jpg").write_bytes(to_jpeg(img)[0])
            url = shot_url(name)
        page_url = ""
        try:
            page_url = self.page.url if self.page is not None else ""
        except Exception:
            pass
        f = {"run_id": self.run_id, "endpoint": self.endpoint, "step": step, "action": action,
             "thought": short(thought), "shot_url": url, "page_url": page_url, "at": now_iso(),
             "live": self.live}
        self.steps.append({**f, "thought_full": thought})
        cam.push(f)
        return url

    def result(self) -> dict:
        shots = [{k: v for k, v in s.items() if not k.startswith("_")} for s in self.screenshots]
        r = {"run_id": self.run_id, "endpoint": self.endpoint, "status": self.status, "live": self.live,
             "screenshots": shots, "source": self.source or {}, "started_at": now_iso(self.started_at or self.queued_at)}
        if self.output is not None:
            r["output"] = self.output
        if self.error:
            r["error"] = self.error
        if self.ended_at:
            r["ended_at"] = now_iso(self.ended_at)
            r["duration_ms"] = int(1000 * (self.ended_at - (self.started_at or self.queued_at)))
        r.update({k: v for k, v in self.extra.items() if k in ("cached_at", "cache_reason")})
        return r

    def trace(self) -> dict:
        return {"run_id": self.run_id, "endpoint": self.endpoint, "params": redact(self.params), "status": self.status,
                "live": self.live, "steps": self.steps, "answer": self.extra.get("answer"),
                "output": self.output, "error": self.error, "screenshots": self.result()["screenshots"]}


def short(t: str, n: int = 80) -> str:
    t = re.sub(r"\s+", " ", t or "").strip()
    return t if len(t) <= n else t[: n - 1].rstrip() + "…"


def redact(p: dict) -> dict:
    return {k: ("…" if re.search(r"pass|token|secret|key", k, re.I) else v) for k, v in p.items()}


# ───────── golden-path cache ─────────
class Cache:
    """Last good LIVE result per endpoint and key (the demo address). Served with live:false, always."""

    def path(self, endpoint: str, key: str):
        return CACHE / endpoint / slug(key)

    def put(self, run: Run, key: str) -> None:
        d = self.path(run.endpoint, key)
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True)
        for s in run.screenshots:
            shutil.copy(SHOTS / f"{s['_file']}.jpg", d / f"{s['image_id']}.jpg")
        (d / "result.json").write_text(json.dumps({"key": key, "cached_at": now_iso(), "result": run.result(),
                                                   "steps": len(run.steps)}, ensure_ascii=False, indent=1))

    def get(self, endpoint: str, key: str, max_age_s: Optional[float] = None) -> Optional[dict]:
        f = self.path(endpoint, key) / "result.json"
        if not f.exists():
            return None
        c = json.loads(f.read_text())
        if max_age_s is not None and time.time() - f.stat().st_mtime > max_age_s:
            return None
        return c

    def restore_shots(self, endpoint: str, key: str) -> None:
        d = self.path(endpoint, key)
        for p in d.glob("*.jpg"):
            shutil.copy(p, SHOTS / p.name)

    def clear(self) -> int:
        n = 0
        for d in CACHE.iterdir():
            if d.is_dir():
                n += sum(1 for _ in d.glob("*/result.json"))
                shutil.rmtree(d)
        return n

    def listing(self) -> list[dict]:
        out = []
        for f in CACHE.glob("*/*/result.json"):
            c = json.loads(f.read_text())
            out.append({"endpoint": f.parent.parent.name, "key": c["key"], "cached_at": c["cached_at"],
                        "duration_ms": c["result"].get("duration_ms"), "steps": c.get("steps")})
        return out


cache = Cache()


# ───────── endpoints registry ─────────
@dataclass
class Endpoint:
    name: str
    kind: str                      # real | replica | learned
    access: str                    # read | write | vision | write, gated
    timeout_s: int
    cache: Optional[str]           # "golden" | "30min" | None
    source_kind: str
    source_label: str
    params: dict
    fn: Callable[[Run], Awaitable[dict]]
    cache_key: Optional[Callable[[dict], str]] = None
    cache_scope: Optional[Callable[[dict], bool]] = None   # False → no golden path for these params (any other address)
    cache_rank: Optional[Callable[[dict], int]] = None     # a live output ranked lower never replaces the golden path
    site: str = ""               # profile name (cookies persisted per site)
    verified: bool = True
    needs_browser: bool = True
    stats: dict = field(default_factory=lambda: {"live": [], "cache": [], "failed": 0, "runs": 0})


ENDPOINTS: dict[str, Endpoint] = {}


def in_scope(ep: Endpoint, params: dict) -> bool:
    return ep.cache_scope is None or bool(ep.cache_scope(params))


def is_demo_address(a) -> bool:
    """The golden path exists only for the reference address: any other address is live or failed, never cache."""
    return bool(settings.demo_address) and slug(str(a or "")) == slug(settings.demo_address)


def is_demo_town(t) -> bool:
    return bool(settings.demo_town) and slug(str(t or "")) == slug(settings.demo_town)


def endpoint(**kw):
    def deco(fn):
        ENDPOINTS[kw["name"]] = Endpoint(fn=fn, **kw)
        return fn
    return deco


# ───────── browser ─────────
class Browsers:
    def __init__(self) -> None:
        self.pw = None
        self.browser = None
        self.lock = asyncio.Lock()

    async def get(self):
        async with self.lock:
            if self.browser is None or not self.browser.is_connected():
                from playwright.async_api import async_playwright
                if self.pw is None:
                    self.pw = await async_playwright().start()
                args = ["--disable-blink-features=AutomationControlled", "--lang=fr-FR",
                        "--enable-gpu-rasterization", "--ignore-gpu-blocklist"]
                try:
                    self.browser = await self.pw.chromium.launch(channel="chrome", headless=settings.headless, args=args)
                except Exception:
                    self.browser = await self.pw.chromium.launch(headless=settings.headless, args=args)
            return self.browser

    async def context(self, site: str):
        b = await self.get()
        state = PROFILES / f"{site}.json"
        ctx = await b.new_context(viewport={"width": 1280, "height": 800}, locale="fr-FR", timezone_id="Europe/Paris",
                                  storage_state=str(state) if site and state.exists() else None,
                                  device_scale_factor=1)
        return ctx

    async def save(self, ctx, site: str) -> None:
        if site:
            try:
                await ctx.storage_state(path=str(PROFILES / f"{site}.json"))
            except Exception:
                pass

    async def close(self) -> None:
        if self.browser:
            await self.browser.close()
        if self.pw:
            await self.pw.stop()


browsers = Browsers()


# ───────── Seraph push ─────────
async def push_seraph(run: Run, final: bool = False) -> None:
    body = run.result()
    for attempt in range(3 if final else 1):
        try:
            async with httpx.AsyncClient(timeout=3) as c:
                r = await c.post(f"{settings.seraph_url}/rosetta/results", json=body)
                r.raise_for_status()
            return
        except Exception:
            if attempt < 2 and final:
                await asyncio.sleep(0.5 * (attempt + 1))


# ───────── runner ─────────
class Runner:
    def __init__(self) -> None:
        self.queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self.runs: dict[str, Run] = {}
        self.seq = itertools.count()
        self.workers: list[asyncio.Task] = []
        self.active = 0

    def start(self) -> None:
        for _ in range(max(1, settings.max_parallel)):
            self.workers.append(asyncio.create_task(self._worker()))

    async def submit(self, run: Run) -> None:
        self.runs[run.run_id] = run
        if len(self.runs) > 400:
            self.runs.pop(next(iter(self.runs)))
        await self.queue.put((-run.priority, next(self.seq), run))
        asyncio.create_task(push_seraph(run))

    async def _worker(self) -> None:
        while True:
            _, _, run = await self.queue.get()
            self.active += 1
            try:
                await self.execute(run)
            except Exception:
                traceback.print_exc()
            finally:
                self.active -= 1

    async def execute(self, run: Run) -> None:
        from . import mock
        ep = ENDPOINTS.get(run.endpoint)
        run.started_at = time.time()
        run.status = "running"
        if ep is None:
            return await self._finish(run, None, error=f"endpoint inconnu : {run.endpoint}")
        ep.stats["runs"] += 1
        run.source = {"kind": ep.source_kind, "label": ep.source_label, "confirmed": True, "at": now_iso()}
        await push_seraph(run)
        if settings.mock:
            return await self._finish(run, ep, **await mock.run(run, ep))
        try:
            if ep.needs_browser:
                run.context = await browsers.context(ep.site)
                run.page = await run.context.new_page()
            out = await asyncio.wait_for(ep.fn(run), timeout=ep.timeout_s)
            await self._finish(run, ep, output=out)
        except asyncio.TimeoutError:
            await self._finish(run, ep, error=f"délai dépassé ({ep.timeout_s} s)")
        except Exception as exc:
            from .holo import Blocked
            msg = f"captcha / contrôle anti-robot : arrêt ({exc})" if isinstance(exc, Blocked) else f"{type(exc).__name__}: {str(exc)[:300]}"
            if not isinstance(exc, (Blocked, RunFailed)):
                traceback.print_exc()
            await self._finish(run, ep, error=msg)
        finally:
            if run.context is not None:
                await browsers.save(run.context, ep.site if ep else "")
                try:
                    await run.context.close()
                except Exception:
                    pass
                run.context = run.page = None

    async def _finish(self, run: Run, ep: Optional[Endpoint], output: Optional[dict] = None, error: Optional[str] = None,
                      live: bool = True) -> None:
        run.ended_at = time.time()
        if run.source:
            run.source["at"] = now_iso()
        if error is None and output is not None:
            run.status, run.output, run.live = "ok", output, live
            if live:
                # urls point at this run's own files (never overwritten: another address can't replace the reference
                # address's pictures). The stable /shots/<image_id>.jpg = the golden path, updated only in cache scope.
                demo = ep is not None and in_scope(ep, run.params)
                if demo and ep.cache and ep.cache_key and ep.cache_rank:
                    old = cache.get(ep.name, ep.cache_key(run.params))
                    if old and ep.cache_rank(output) < ep.cache_rank(old["result"].get("output") or {}):
                        demo = False       # this run stays live; the golden path keeps the better result and pictures
                for s in run.screenshots:
                    if demo:
                        shutil.copy(SHOTS / f"{s['_file']}.jpg", SHOTS / f"{s['image_id']}.jpg")
                if ep and ep.cache and ep.cache_key and run.extra.get("cacheable", True) and demo:
                    cache.put(run, ep.cache_key(run.params))
            if ep:
                ep.stats["live" if live else "cache"].append(int(1000 * (run.ended_at - run.started_at)))
            await run.frame(f"terminé · {'live' if live else 'cache'}", run.extra.get("summary", ""), step=run.step_n)
            self._trace(run)
            return await push_seraph(run, final=True)
        # failed: the labelled cache if allowed, never a fake step
        run.error = error
        if ep:
            ep.stats["failed"] += 1
        await run.frame("échec", error or "", step=run.step_n)
        self._trace(run)
        if ep and ep.cache and ep.cache_key and run.allow_cache and in_scope(ep, run.params):
            key = ep.cache_key(run.params)
            c = cache.get(ep.name, key, 1800 if ep.cache == "30min" else None)
            if c:
                r = c["result"]
                served = Run(run_id=run.run_id, endpoint=run.endpoint, params=run.params, priority=run.priority)
                served.started_at, served.ended_at = run.started_at, time.time()
                served.status, served.live, served.output = "ok", False, r.get("output")
                served.screenshots = []
                for s in r.get("screenshots", []):
                    name = f"cache--{slug(ep.name)}--{slug(key)[:40]}--{s['image_id']}"
                    src = cache.path(ep.name, key) / f"{s['image_id']}.jpg"
                    if src.exists():
                        shutil.copy(src, SHOTS / f"{name}.jpg")
                    served.screenshots.append({**s, "url": shot_url(name), "_file": name})
                served.source = {**(r.get("source") or run.source or {}), "at": now_iso()}
                served.error = f"live: {error} → cache du {c['cached_at'][:16].replace('T', ' ')}"
                served.extra = {"cached_at": c["cached_at"], "cache_reason": error}
                ep.stats["cache"].append(int(1000 * (served.ended_at - served.started_at)))
                self.runs[run.run_id] = served
                served.steps = run.steps
                cam.push({"run_id": run.run_id, "endpoint": run.endpoint, "step": run.step_n + 1,
                          "action": "cache", "thought": short(f"résultat en cache du {c['cached_at'][:16]}"),
                          "shot_url": served.screenshots[0]["url"] if served.screenshots else "",
                          "page_url": "", "at": now_iso(), "live": False})
                return await push_seraph(served, final=True)
        run.status = "failed"
        await push_seraph(run, final=True)

    def _trace(self, run: Run) -> None:
        try:
            (TRACES / f"{run.run_id}.json").write_text(json.dumps(run.trace(), ensure_ascii=False, indent=1, default=str))
        except Exception:
            pass


class RunFailed(Exception):
    """The page check failed: code could not verify what the agent did."""


runner = Runner()
