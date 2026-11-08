"""ViewRequest → Devin (warm pool) → validated → served → ViewReady to Seraph. Mock mode serves the kit examples."""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import shutil
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import httpx

from . import cli, context
from .config import KIT, REPO, RUNTIME, VIEWS, settings
from .devin import Devin, DevinError
from .validate import check_view, renderer, static_checks

log = logging.getLogger("silex")

POLL_S = 4
RUNS: dict[str, "cli.Run"] = {}       # session id → its current Devin CLI process (for the dashboard tail)
WAITING = ("waiting_for_user", "finished")
MAX_REFS = 6


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + f"{datetime.now(timezone.utc).microsecond // 1000:03d}Z"


def _hash(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()


@dataclass
class Session:
    id: str
    url: Optional[str]
    role: str                      # warm | cold | mock
    status: str                    # warming | idle | building | fixing | ready | failed | ended
    purpose: str
    started_at: str
    t0: float
    kind: str = "view"             # view | endpoint
    request_id: Optional[str] = None
    view_id: Optional[str] = None
    mock: bool = False
    note: str = ""
    transport: str = "api"         # api | cli | mock
    resume: Optional[str] = None   # Devin CLI session id (`devin -r`)
    summary: str = ""              # Devin's line on its last view
    refs: list = field(default_factory=list)   # [{image, took, url, caption}]: what it took from each screenshot

    def public(self) -> dict:
        run = RUNS.get(self.id)
        return {"id": self.id, "session_id": self.resume or self.id, "url": self.url, "kind": self.kind,
                "role": self.role, "transport": self.transport, "model": settings.devin_model if self.transport == "cli" else None,
                "status": self.status, "purpose": self.purpose, "started_at": self.started_at,
                "elapsed_s": round(time.time() - self.t0), "request_id": self.request_id, "view_id": self.view_id,
                "label": "mock" if self.mock else "devin", "note": self.note,
                "tail": list(run.tail)[-6:] if run else [], "summary": self.summary, "refs": self.refs}

    @property
    def live(self) -> bool:
        return self.status in ("warming", "idle", "building", "fixing")


@dataclass
class Job:
    vr: dict
    request_id: str
    moment: str
    view_id: str
    t0: float
    requested_at: str
    status: str = "building"       # building | validating | ready | failed
    session_id: Optional[str] = None
    attempt: int = 0
    late: bool = False
    errors: list[str] = field(default_factory=list)
    rejected: list[str] = field(default_factory=list)
    ready_at: Optional[str] = None
    request_to_view_ms: Optional[int] = None
    first_answer_ms: Optional[int] = None
    warm: bool = False
    note: str = ""

    def public(self) -> dict:
        d = {k: v for k, v in asdict(self).items() if k not in ("vr", "rejected", "t0")}
        d["purpose_fr"] = self.vr.get("purpose_fr")
        d["deadline_s"] = self.vr.get("deadline_s")
        d["elapsed_s"] = round(time.time() - self.t0) if not self.ready_at else round((self.request_to_view_ms or 0) / 1000)
        return d


class Silex:
    def __init__(self) -> None:
        self.sessions: dict[str, Session] = {}
        self.jobs: dict[str, Job] = {}
        self.devin = Devin()
        self.kit_urls: list[str] = []
        self.lock = asyncio.Lock()
        self.tasks: set[asyncio.Task] = set()
        self.incident_status: Optional[str] = None
        self._load()

    # ───────── persistence (a restart keeps the warm sessions and the history) ─────────
    def _load(self) -> None:
        p = RUNTIME / "sessions.json"
        if not p.exists():
            return
        try:
            d = json.loads(p.read_text())
            self.sessions = {s["id"]: Session(**s) for s in d.get("sessions", [])}
            self.kit_urls = d.get("kit_urls", [])
            for j in d.get("jobs", []):
                j.setdefault("rejected", [])
                job = Job(**j)
                if job.status not in ("ready", "failed"):
                    job.status, job.note = "failed", "Silex redémarré"
                self.jobs[job.request_id] = job
            for s in self.sessions.values():
                if s.status in ("building", "fixing"):
                    s.status, s.request_id = "idle", None
        except Exception as e:
            log.warning("sessions.json unreadable: %s", e)

    def _save(self) -> None:
        RUNTIME.mkdir(parents=True, exist_ok=True)
        d = {"sessions": [asdict(s) for s in self.sessions.values()], "kit_urls": self.kit_urls,
             "jobs": [asdict(j) for j in self.jobs.values()]}
        (RUNTIME / "sessions.json").write_text(json.dumps(d, ensure_ascii=False, indent=1))

    def spawn(self, coro) -> asyncio.Task:
        t = asyncio.get_running_loop().create_task(coro)
        self.tasks.add(t)
        t.add_done_callback(self.tasks.discard)
        return t

    # ───────── public API ─────────
    def request(self, vr: dict) -> dict:
        moment = vr.get("moment") or "commander_request"
        rid = vr.get("request_id") or f"req_{int(time.time() * 1000)}"
        if rid in self.jobs and self.jobs[rid].status in ("building", "validating", "ready"):
            j = self.jobs[rid]
            return {"request_id": rid, "status": "building" if j.status != "ready" else "ready", "view_id": j.view_id}
        job = Job(vr={**vr, "request_id": rid, "moment": moment}, request_id=rid, moment=moment,
                  view_id=self._next_view_id(moment), t0=time.time(), requested_at=now_iso())
        self.jobs[rid] = job
        self._save()
        log.info("request %s %s → %s", rid, moment, job.view_id)
        self.spawn(self._deadline(job))
        if settings.mock:
            self.spawn(self._mock_build(job))
        elif settings.active_transport == "cli":
            self.spawn(self._cli_build(job))
        else:
            self.spawn(self._devin_build(job))
        return {"request_id": rid, "status": "building", "view_id": job.view_id}

    def list_sessions(self) -> list[dict]:
        return [s.public() for s in sorted(self.sessions.values(), key=lambda s: s.t0, reverse=True)]

    def list_jobs(self) -> list[dict]:
        return [j.public() for j in sorted(self.jobs.values(), key=lambda j: j.t0, reverse=True)]

    def _next_view_id(self, moment: str) -> str:
        used = {p.name for p in VIEWS.glob(f"view_{moment}_*")} | {j.view_id for j in self.jobs.values()}
        n = 1
        while f"view_{moment}_{n}" in used:
            n += 1
        return f"view_{moment}_{n}"

    # ───────── Seraph ─────────
    async def push(self, body: dict) -> None:
        try:
            async with httpx.AsyncClient(timeout=5) as c:
                await c.post(f"{settings.seraph_url}/silex/views", json=body)
        except httpx.HTTPError as e:
            log.warning("Seraph unreachable for ViewReady %s: %s", body.get("status"), type(e).__name__)

    async def _state(self, vr: dict) -> dict:
        for url in (vr.get("sample_state_url"), f"{settings.seraph_url}/state"):
            if not url:
                continue
            try:
                async with httpx.AsyncClient(timeout=5) as c:
                    r = await c.get(url)
                    r.raise_for_status()
                    return r.json()
            except (httpx.HTTPError, ValueError):
                continue
        return json.loads((REPO / "contracts" / "fixtures" / "state-sample.json").read_text())

    async def _deadline(self, job: Job) -> None:
        await asyncio.sleep(float(job.vr.get("deadline_s") or 300))
        if job.status in ("building", "validating"):
            job.late = True
            job.note = f"délai dépassé ({job.vr.get('deadline_s')} s), Devin continue"
            self._save()
            await self.push({"request_id": job.request_id, "status": "failed", "note": job.note,
                             "devin_session_url": self._session_url(job)})

    def _session_url(self, job: Job) -> Optional[str]:
        s = self.sessions.get(job.session_id or "")
        return s.url if s else None

    # ───────── validation and publishing ─────────
    async def validate(self, view_id: str, html: str, state: dict) -> list[str]:
        stage = RUNTIME / "staging" / view_id
        stage.mkdir(parents=True, exist_ok=True)
        (stage / "index.html").write_text(html, encoding="utf-8")
        errors = static_checks(html) + await check_view(stage / "index.html")
        errors += await renderer.render(f"http://127.0.0.1:{settings.port}/_staging/{view_id}/", state, stage / "preview.png")
        return list(dict.fromkeys(errors))

    async def publish(self, job: Job, html: str, notes: str, built_by: str, refs_used: Optional[list] = None) -> None:
        s = self.sessions.get(job.session_id or "")
        out = VIEWS / job.view_id
        out.mkdir(parents=True, exist_ok=True)
        (out / "index.html").write_text(html, encoding="utf-8")
        used = []
        for r in refs_used or []:                    # the screenshots the view was drawn from, next to it
            src = REPO / r["path"] if r.get("path") else None
            if src and src.exists():
                (out / "refs").mkdir(exist_ok=True)
                shutil.copy(src, out / "refs" / src.name)
                used.append({"image": src.name, "image_id": r.get("image_id"), "caption": r.get("caption"),
                             "side": r.get("side"), "took": r.get("took", ""),
                             "url": f"{settings.public_url}/views/{job.view_id}/refs/{src.name}"})
        shot = RUNTIME / "staging" / job.view_id / "preview.png"
        if shot.exists():
            shutil.copy(shot, out / "preview.png")
        job.ready_at = now_iso()
        job.request_to_view_ms = int((time.time() - job.t0) * 1000)
        job.status = "ready"
        purpose = job.vr.get("purpose_fr") or ""
        meta = {"view_id": job.view_id, "moment": job.moment, "title_fr": purpose.split(":")[0].strip(),
                "purpose_fr": purpose, "data_keys": job.vr.get("data_keys") or [],
                "references": [r.get("image_id") for r in job.vr.get("references") or []],
                "built_by": built_by, "devin_session_url": s.url if s and not s.mock else None,
                "transport": s.transport if s else None, "model": settings.devin_model if s and s.transport == "cli" else None,
                "devin_cli_session": s.resume if s else None,
                "created_at": job.ready_at, "request_id": job.request_id,
                "request_to_view_ms": job.request_to_view_ms, "attempts": max(job.attempt, 1), "late": job.late,
                "notes": notes, "references_used": used}
        (out / "view.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
        if s:
            s.summary, s.refs = notes, used
            s.status = "ready" if s.mock else "idle"     # a Devin session keeps its context: reusable
            s.note = f"{job.view_id} en {job.request_to_view_ms / 1000:.0f} s"
            s.request_id = None if not s.mock else s.request_id
        self._save()
        log.info("ready %s in %d ms (%s, attempts %d)", job.view_id, job.request_to_view_ms, built_by, job.attempt)
        await self.push({"request_id": job.request_id, "status": "ready", "view_id": job.view_id,
                         "url": f"{settings.public_url}/views/{job.view_id}/",
                         "devin_session_url": meta["devin_session_url"],
                         "note": "mock" if built_by == "mock" else (notes or "")[:200]})

    async def fail(self, job: Job, note: str) -> None:
        job.status, job.note = "failed", note
        s = self.sessions.get(job.session_id or "")
        if s and s.live:
            s.status, s.request_id, s.note = "idle", None, note
        self._save()
        log.warning("failed %s: %s", job.request_id, note)
        await self.push({"request_id": job.request_id, "status": "failed", "note": note,
                         "devin_session_url": s.url if s else None})

    # ───────── mock ─────────
    async def _mock_build(self, job: Job) -> None:
        s = Session(id=f"mock-{job.view_id}", url=None, role="mock", status="building", mock=True, transport="mock",
                    purpose=job.vr.get("purpose_fr") or job.moment, started_at=now_iso(), t0=time.time(),
                    request_id=job.request_id, view_id=job.view_id, note="mock")
        self.sessions[s.id] = s
        job.session_id = s.id
        self._save()
        state = await self._state(job.vr)
        await asyncio.sleep(settings.mock_delay_s)
        src = KIT / "examples" / f"{context.EXAMPLE_FOR.get(job.moment, 'approach')}.html"
        html = re.sub(r'data-view-id="[^"]*"', f'data-view-id="{job.view_id}"', src.read_text(encoding="utf-8"), count=1)
        job.status, job.attempt = "validating", 1
        errors = await self.validate(job.view_id, html, state)
        if errors:
            s.status = "failed"
            return await self.fail(job, "mock : l'exemple du kit ne passe pas — " + "; ".join(errors[:3]))
        await self.publish(job, html, "mock: kit example served as if Devin built it", "mock")

    # ───────── Devin: warm pool ─────────
    async def kit_attachments(self) -> list[str]:
        if self.kit_urls:
            return self.kit_urls
        urls = []
        for name, ctype in context.KIT_FILES:
            urls.append(await self.devin.upload(Path(name).name, (KIT / name).read_bytes(), ctype))
        self.kit_urls = urls
        self._save()
        return urls

    async def ensure_warm(self) -> dict:
        if settings.mock or not settings.devin_ready:
            return {"warm": 0, "reason": "mock" if settings.mock else "no Devin key"}
        async with self.lock:
            created = 0
            tr = settings.active_transport
            while True:
                warm = [s for s in self.sessions.values() if s.transport == tr and s.status in ("warming", "idle")]
                live = [s for s in self.sessions.values() if s.transport == tr and s.live]
                if len(warm) >= settings.warm or len(live) >= settings.max_sessions:
                    break
                try:
                    if settings.active_transport == "cli":
                        await self._create_warm_cli()
                    else:
                        await self._create_warm()
                    created += 1
                except (DevinError, OSError) as e:
                    log.warning("warm session failed: %s", e)
                    break
        return {"warm": len([s for s in self.sessions.values() if s.transport == tr and s.status in ("warming", "idle")]),
                "created": created, "transport": tr}

    async def _create_warm(self) -> Session:
        kit = await self.kit_attachments()
        d = await self.devin.create_session(context.warm_prompt(kit), title="Silex · vues Halo (warm)",
                                            tags=["seraph", "silex", "warm"], schema=context.VIEW_SCHEMA,
                                            attachment_urls=kit)
        s = Session(id=d["session_id"], url=d.get("url"), role="warm", status="warming",
                    purpose="Contexte chargé, attend une vue", started_at=now_iso(), t0=time.time(), transport="api")
        self.sessions[s.id] = s
        self._save()
        log.info("warm session %s", s.id)
        self.spawn(self._watch_warm(s))
        return s

    async def _watch_warm(self, s: Session) -> None:
        """warming → idle once Devin has read the context and waits for a request."""
        stop = time.time() + 900
        while s.status == "warming" and time.time() < stop:
            await asyncio.sleep(POLL_S + 1)
            try:
                d = await self.devin.get_session(s.id)
            except DevinError:
                continue
            if d.get("status") in ("exit", "error"):
                s.status, s.note = "ended", f"Devin {d.get('status')}"
            elif d.get("status_detail") in WAITING and s.status == "warming":
                s.status, s.note = "idle", f"prêt en {time.time() - s.t0:.0f} s"
            self._save()

    async def refresh_sessions(self) -> None:
        """After a restart: drop the sessions Devin has ended (a CLI run did not survive the restart)."""
        for s in list(self.sessions.values()):
            if s.mock or not s.live:
                continue
            if s.transport == "cli":
                if s.status != "idle" or not s.resume:
                    s.status, s.note = "ended", "Silex redémarré"
                continue
            try:
                d = await self.devin.get_session(s.id)
            except DevinError:
                continue
            if d.get("status") in ("exit", "error"):
                s.status = "ended"
            elif s.status == "warming":
                self.spawn(self._watch_warm(s))
        self._save()

    def _take(self, transport: str = "api") -> Optional[Session]:
        if transport == "cli":       # a CLI session is usable once its warm run is over and its id is known
            free = [s for s in self.sessions.values() if s.transport == "cli" and s.status == "idle" and s.resume]
            free.sort(key=lambda s: s.t0)
            return free[0] if free else None
        # a Devin session refuses messages (HTTP 400) until it has started: only idle ones take a request
        free = [s for s in self.sessions.values() if s.transport == "api" and s.kind == "view" and s.status == "idle"]
        free.sort(key=lambda s: s.t0)
        return free[0] if free else None

    async def _take_api(self, wait_s: float = 40) -> Optional[Session]:
        """An idle warm session; if the pool is still warming, wait for it rather than boot a cold one."""
        stop = time.time() + wait_s
        while True:
            s = self._take("api")
            if s or time.time() > stop or not any(x.transport == "api" and x.status == "warming" for x in self.sessions.values()):
                return s
            await asyncio.sleep(2)

    async def stop_all(self) -> int:
        n = 0
        for s in self.sessions.values():
            if not s.mock and s.live:
                if s.transport == "cli":
                    run = RUNS.get(s.id)
                    if run:
                        run.kill()
                else:
                    try:
                        await self.devin.terminate(s.id)
                    except DevinError:
                        pass
                s.status, n = "ended", n + 1
        self._save()
        return n

    # ───────── Devin: one view ─────────
    async def _refs(self, job: Job) -> list[dict]:
        refs = list(job.vr.get("references") or [])
        shots = [r for r in refs if r.get("side") != "plan"][:4]
        plans = [r for r in refs if r.get("side") == "plan"]
        plans.sort(key=lambda r: (r.get("image_id") not in ("ifc-L0",), r.get("image_id", "")))
        out = []
        folder = VIEWS / "_refs" / job.request_id
        folder.mkdir(parents=True, exist_ok=True)
        for r in (shots + plans)[:MAX_REFS]:
            url = r.get("url") or ""
            name = Path(url.split("?")[0]).name or f"{r.get('image_id')}.jpg"
            item = {**r, "name": name, "attached": False}
            try:
                async with httpx.AsyncClient(timeout=6) as c:
                    resp = await c.get(url)
                    resp.raise_for_status()
                (folder / name).write_bytes(resp.content)
                item["devin_url"] = await self.devin.upload(name, resp.content, resp.headers.get("content-type", "application/octet-stream"))
                item["attached"] = True
            except (httpx.HTTPError, DevinError, ValueError) as e:
                log.info("reference %s not attached: %s", url, type(e).__name__)
            out.append(item)
        return out

    async def _devin_build(self, job: Job) -> None:
        if not settings.devin_ready:
            return await self.fail(job, "pas de clé Devin")
        try:
            state = await self._state(job.vr)
            folder = VIEWS / "_refs" / job.request_id
            folder.mkdir(parents=True, exist_ok=True)
            (folder / "state.json").write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
            (folder / "request.json").write_text(json.dumps(job.vr, ensure_ascii=False, indent=1), encoding="utf-8")
            state_url = await self.devin.upload("state.json", json.dumps(state, ensure_ascii=False).encode(), "application/json")
            refs = await self._refs(job)
            attach = [state_url] + [r["devin_url"] for r in refs if r.get("devin_url")]
            s = await self._take_api()
            if s:
                s.status, s.request_id, s.view_id, s.purpose = "building", job.request_id, job.view_id, job.vr.get("purpose_fr") or job.moment
                try:
                    await self.devin.send_message(s.id, context.request_message(job.vr, job.view_id, state, refs, cold=False), attach)
                    job.warm = True
                except DevinError as e:
                    log.warning("warm session %s refused the request (%s): cold session", s.id, str(e)[:80])
                    s.status, s.request_id, s.note = "ended", None, "a refusé la demande"
                    s = None
            if not s:
                kit = await self.kit_attachments()
                prompt = context.warm_prompt(kit) + "\n\n" + context.request_message(job.vr, job.view_id, state, refs, cold=True)
                d = await self.devin.create_session(prompt, title=f"Silex · {job.moment} · {job.view_id}",
                                                    tags=["seraph", "silex", job.moment], schema=context.VIEW_SCHEMA,
                                                    attachment_urls=kit + attach)
                s = Session(id=d["session_id"], url=d.get("url"), role="cold", status="building",
                            purpose=job.vr.get("purpose_fr") or job.moment, started_at=now_iso(), t0=time.time(),
                            request_id=job.request_id, view_id=job.view_id, transport="api")
                self.sessions[s.id] = s
            job.session_id = s.id
            job.attempt = 1
            self._save()
        except DevinError as e:
            return await self.fail(job, f"Devin injoignable : {str(e)[:120]}")
        await self.push({"request_id": job.request_id, "status": "building", "view_id": job.view_id,
                         "devin_session_url": s.url})
        self.spawn(self.ensure_warm())                    # top the pool up for the next moment
        await self._poll(job, s, state)

    async def _poll(self, job: Job, s: Session, state: dict) -> None:
        hard_stop = job.t0 + max(3 * float(job.vr.get("deadline_s") or 300), 900)
        sent_at, nudged, api_errors = time.time(), False, 0
        while time.time() < hard_stop:
            await asyncio.sleep(POLL_S)
            try:
                d = await self.devin.get_session(s.id)
                api_errors = 0
            except DevinError as e:
                api_errors += 1
                if api_errors >= 15:
                    return await self.fail(job, f"Devin injoignable : {str(e)[:120]}")
                continue
            st, det = d.get("status"), d.get("status_detail")
            so = d.get("structured_output") or {}
            html = so.get("html") if so.get("request_id") == job.request_id else None
            notes = so.get("notes") or ""
            idle_long = det in WAITING and time.time() - sent_at > 40
            if not html and idle_long:
                html = await self._html_from_messages(s.id, sent_at)
            if html and _hash(html) not in job.rejected:
                if job.first_answer_ms is None:
                    job.first_answer_ms = int((time.time() - job.t0) * 1000)
                job.status, s.status = "validating", "fixing" if job.attempt > 1 else "building"
                errors = await self.validate(job.view_id, html, state)
                if not errors:
                    return await self.publish(job, html, notes, "devin")
                job.rejected.append(_hash(html))
                job.errors = errors
                log.info("attempt %d of %s rejected: %s", job.attempt, job.view_id, errors)
                if job.attempt >= settings.max_tries:
                    return await self.fail(job, f"vue refusée après {job.attempt} essais : {errors[0][:100]}")
                job.attempt += 1
                job.status, s.status = "building", "fixing"
                self._save()
                try:
                    await self.devin.send_message(s.id, context.fix_message(job.request_id, job.view_id, job.attempt, errors))
                except DevinError:
                    pass
                sent_at, nudged = time.time(), False
                continue
            if st in ("exit", "error"):
                s.status = "ended"
                return await self.fail(job, f"session Devin terminée ({st})")
            if st == "suspended" and det not in ("inactivity", "user_request", None):
                s.status = "ended"
                return await self.fail(job, f"session Devin suspendue ({det})")
            if (idle_long or st == "suspended") and not nudged:
                try:
                    await self.devin.send_message(s.id, context.nudge_message(job.request_id, job.view_id))
                except DevinError:
                    pass
                nudged = True
        await self.fail(job, "Devin n'a rien rendu")

    async def _html_from_messages(self, session_id: str, since: float) -> Optional[str]:
        """Devin sometimes answers in chat instead of the structured output: take the last full html block."""
        try:
            items = await self.devin.messages(session_id)
        except DevinError:
            return None
        for m in reversed(items):
            if m.get("source") != "devin" or (m.get("created_at") or 0) < since - 5:
                continue
            found = re.findall(r"```html\s*(<!doctype[\s\S]*?</html>)\s*```", m.get("message") or "", re.I)
            if found:
                return found[-1]
        return None

    # ───────── Devin CLI (local, Opus): warm sessions resumed with `-r`, files on disk ─────────
    def _taken_resume_ids(self) -> set[str]:
        return {s.resume for s in self.sessions.values() if s.resume}

    async def _create_warm_cli(self) -> Session:
        s = Session(id=f"cli-warm-{int(time.time() * 1000)}", url=None, role="warm", status="warming",
                    purpose="Contexte chargé, attend une vue", started_at=now_iso(), t0=time.time(), transport="cli")
        folder = RUNTIME / "cli" / s.id
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "prompt.md").write_text(context.cli_warm_prompt(), encoding="utf-8")
        run = cli.Run(s.id, folder / "out.log")
        RUNS[s.id] = run
        self.sessions[s.id] = s
        self._save()
        await run.start(folder / "prompt.md", None)
        log.info("warm CLI session %s", s.id)
        # one warm run at a time: its session id is read back from `devin list` when it ends
        rc = await run.wait(timeout=600)
        sid = await cli.latest_session(s.t0)
        if rc == 0 and sid and sid not in self._taken_resume_ids():
            s.resume, s.status, s.note = sid, "idle", f"prêt en {time.time() - s.t0:.0f} s"
        else:
            s.status, s.note = "ended", f"warm échoué (code {rc}, session {sid or '?'})"
        self._save()
        return s

    async def _resolve_refs(self, job: Job, state: dict, folder: Path) -> list[dict]:
        """Every reference as a file Devin can open: Rosetta's shots (by url, else /shots/<id>.jpg) and the IFC
        plans of the ground floor and the fire floor. A reference that can't be fetched stays listed, without a path."""
        refs = list(job.vr.get("references") or [])
        shots = [r for r in refs if r.get("side") != "plan"][:6]
        fire_level = ((state.get("incident") or {}).get("origin") or {}).get("floor")
        want = {"ifc-L0", f"ifc-L{fire_level}"}
        plans = [r for r in refs if r.get("side") == "plan" and r.get("image_id") in want][:2]
        folder.mkdir(parents=True, exist_ok=True)
        out = []
        async with httpx.AsyncClient(timeout=6) as c:
            for r in shots + plans:
                iid = r.get("image_id") or "ref"
                urls = [u for u in (r.get("url"), None if r.get("side") == "plan" else f"{settings.rosetta_url}/shots/{iid}.jpg") if u]
                item = {**r, "path": None}
                for url in dict.fromkeys(urls):
                    try:
                        resp = await c.get(url)
                        resp.raise_for_status()
                    except httpx.HTTPError:
                        continue
                    ext = ".svg" if "svg" in resp.headers.get("content-type", "") or url.endswith(".svg") else ".jpg"
                    (folder / f"{iid}{ext}").write_bytes(resp.content)
                    item["path"] = str((folder / f"{iid}{ext}").relative_to(REPO))
                    break
                out.append(item)
        log.info("references for %s: %d/%d files", job.view_id, sum(1 for r in out if r["path"]), len(out))
        return out

    @staticmethod
    def _read_notes(path: Path, refs: list[dict]) -> tuple[dict, list[str]]:
        """notes.json must say, for every image Devin was given, what it took from it."""
        try:
            notes = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}, [f"write {path.relative_to(REPO)}: {{summary, references:[{{image, took}}]}}"]
        took = {}
        for e in notes.get("references") or []:
            if isinstance(e, dict) and e.get("image"):
                took[Path(str(e["image"])).name] = str(e.get("took") or "").strip()
        errors = []
        for r in refs:
            if not r.get("path"):
                continue
            name = Path(r["path"]).name
            t = took.get(name) or took.get(r.get("image_id") or "")
            if not t or len(t) < 12:
                errors.append(f"notes.json: say what you took from {name} (open it and name a concrete feature)")
            r["took"] = t or ""
        return notes, errors

    async def _cli_build(self, job: Job) -> None:
        state = await self._state(job.vr)
        build = cli.build_dir(job.view_id)
        shutil.rmtree(build, ignore_errors=True)
        build.mkdir(parents=True, exist_ok=True)
        (build / "state.json").write_text(json.dumps(context.trim_state(state), ensure_ascii=False, indent=1), encoding="utf-8")
        (build / "request.json").write_text(json.dumps(job.vr, ensure_ascii=False, indent=1), encoding="utf-8")
        refs = await self._resolve_refs(job, state, build / "refs")
        out, notes_path = build / "index.html", build / "notes.json"
        rel = lambda p: str(p.relative_to(REPO))

        s = self._take("cli")
        cold = s is None
        if s:
            job.warm = True
            s.status, s.request_id, s.view_id = "building", job.request_id, job.view_id
            s.purpose = job.vr.get("purpose_fr") or job.moment
        else:
            s = Session(id=f"cli-{job.view_id}", url=None, role="cold", status="building", transport="cli",
                        purpose=job.vr.get("purpose_fr") or job.moment, started_at=now_iso(), t0=time.time(),
                        request_id=job.request_id, view_id=job.view_id)
            self.sessions[s.id] = s
        s.refs = [{"image": Path(r["path"]).name, "caption": r.get("caption"), "took": ""} for r in refs if r.get("path")]
        s.summary = ""
        job.session_id = s.id
        self._save()
        await self.push({"request_id": job.request_id, "status": "building", "view_id": job.view_id})
        self.spawn(self.ensure_warm())                    # top the pool up for the next moment

        prompt = context.cli_request_prompt(job.vr, job.view_id, rel(out), rel(notes_path), rel(build / "state.json"), refs, cold)
        hard_stop = job.t0 + max(3 * float(job.vr.get("deadline_s") or 300), 900)
        folder = RUNTIME / "cli" / s.id
        folder.mkdir(parents=True, exist_ok=True)
        job.attempt = 1
        while True:
            pf = folder / f"{job.view_id}-{job.attempt}.md"
            pf.write_text(prompt, encoding="utf-8")
            run = cli.Run(f"{s.id}-{job.attempt}", folder / "out.log")
            RUNS[s.id] = run
            t_run = time.time()
            try:
                await run.start(pf, s.resume)
            except OSError as e:
                return await self.fail(job, f"Devin CLI ne démarre pas : {e}")
            rc = await run.wait(timeout=max(30.0, hard_stop - time.time()))
            if not s.resume:
                sid = await cli.latest_session(t_run)
                if sid and sid not in self._taken_resume_ids():
                    s.resume = sid
            if rc is None:
                return await self.fail(job, "Devin CLI n'a pas fini à temps")
            if job.first_answer_ms is None:
                job.first_answer_ms = int((time.time() - job.t0) * 1000)
            html = out.read_text(encoding="utf-8") if out.exists() else ""
            if not html:                                  # it answered in its reply instead of writing the file
                found = re.findall(r"```html\s*(<!doctype[\s\S]*?</html>)\s*```", run.output(), re.I)
                html = found[-1] if found else ""
            job.status = "validating"
            errors = await self.validate(job.view_id, html, state) if html else \
                [f"no file at {rel(out)}: write the whole view there with your file write tool (code {rc})"]
            notes, note_errors = self._read_notes(notes_path, refs)
            s.refs = [{"image": Path(r["path"]).name, "caption": r.get("caption"), "took": r.get("took", "")}
                      for r in refs if r.get("path")]
            errors += note_errors
            if not errors:
                summary = notes.get("summary") or (run.tail[-1] if run.tail else "")
                return await self.publish(job, html, summary, "devin", [r for r in refs if r.get("path")])
            job.rejected.append(_hash(html))
            job.errors = errors
            log.info("CLI attempt %d of %s rejected: %s", job.attempt, job.view_id, errors)
            if job.attempt >= settings.max_tries or time.time() > hard_stop:
                return await self.fail(job, f"vue refusée après {job.attempt} essais : {errors[0][:100]}")
            job.attempt += 1
            job.status, s.status = "building", "fixing"
            self._save()
            fix = context.cli_fix_prompt(job.request_id, job.view_id, rel(out), rel(notes_path), job.attempt, errors)
            prompt = fix if s.resume else context.cli_request_prompt(
                job.vr, job.view_id, rel(out), rel(notes_path), rel(build / "state.json"), refs, True) + "\n\n" + fix

    # ───────── Seraph's incident start → warm the pool ─────────
    async def watch_seraph(self) -> None:
        while True:
            try:
                async with httpx.AsyncClient(timeout=httpx.Timeout(10, read=None)) as c:
                    async with c.stream("GET", f"{settings.seraph_url}/stream", params={"client": "dashboard"}) as r:
                        event = ""
                        async for line in r.aiter_lines():
                            if line.startswith("event:"):
                                event = line[6:].strip()
                            elif line.startswith("data:") and event == "state":
                                self._on_state(line[5:])
            except (httpx.HTTPError, asyncio.TimeoutError):
                pass
            await asyncio.sleep(5)

    def _on_state(self, data: str) -> None:
        try:
            st = (json.loads(data).get("incident") or {}).get("status")
        except ValueError:
            return
        if not st:
            return
        prev = self.incident_status
        self.incident_status = st
        if prev is not None and prev != st and prev in ("idle", "closed") and st not in ("idle", "closed"):
            log.info("incident %s → %s: warming Devin", prev, st)
            self.spawn(self.ensure_warm())


silex = Silex()
