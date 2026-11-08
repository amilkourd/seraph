"""Shared plumbing for the three replicas: env, login, layout, SQLite, reset, health, public guard.

The replicas stand for software we don't own. HTML only, no JSON API: Rosetta reads them through the screen.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import sqlite3
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Iterator
from urllib.parse import quote
from zoneinfo import ZoneInfo

from dotenv import dotenv_values
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]  # repo root (seraph/)
DATA = HERE.parent / "data"
FIXTURES = ROOT / "contracts" / "fixtures"
PARIS = ZoneInfo("Europe/Paris")
USER = "operateur"

LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost", "::ffff:127.0.0.1", "testclient"}
PROXY_HEADERS = ("x-forwarded-for", "x-forwarded-host", "x-real-ip", "forwarded", "cf-connecting-ip")


def env(name: str, default: str = "") -> str:
    """Process env first, then the root .env, re-read each call so a value filled in mid-night counts at the next reset."""
    value = os.environ.get(name)
    if value:
        return value
    path = ROOT / ".env"
    if path.exists():
        value = dotenv_values(path).get(name)
    return value or default


def demo_address() -> str:
    return env("DEMO_ADDRESS") or "ADRESSE NON RENSEIGNÉE (DEMO_ADDRESS)"


def demo_commune() -> str:
    """The town from the address's postcode (« 2 rue X, 64000 Pau » → Pau), else DEMO_TOWN."""
    match = re.search(r"\b\d{5}\s+([^,\d][^,]*)$", env("DEMO_ADDRESS").strip())
    return match.group(1).strip() if match else env("DEMO_TOWN", "Paris 9e")


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


# ---------- time ----------

def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def fmt_local(value: str | None, pattern: str = "%d/%m/%Y %H:%M") -> str:
    if not value:
        return ""
    return parse_iso(value).astimezone(PARIS).strftime(pattern)


def ago(minutes: float) -> str:
    return iso(utcnow() - timedelta(minutes=minutes))


# ---------- phone ----------

def mask_phone(e164: str) -> str:
    """+33100000001 -> +3310•••••01 (same shape as contracts/fixtures/state-sample.json)."""
    if len(e164) < 8:
        return "•" * len(e164)
    return e164[:5] + "•" * (len(e164) - 7) + e164[-2:]


def normalize_phone(raw: str) -> str | None:
    """French or international input -> E.164, or None if it doesn't look like a phone number."""
    digits = "".join(ch for ch in raw if ch.isdigit() or ch == "+")
    if digits.startswith("00"):
        digits = "+" + digits[2:]
    if digits.startswith("0") and len(digits) == 10:
        digits = "+33" + digits[1:]
    if digits.startswith("+33") and len(digits) == 13 and digits[3] == "0":
        digits = "+33" + digits[4:]
    if not digits.startswith("+") or "+" in digits[1:]:
        return None
    if not 9 <= len(digits) - 1 <= 15:
        return None
    return digits


# ---------- SQLite ----------

class Store:
    """One SQLite file per replica. `schema` drops and recreates; `seed(conn, keep)` fills it."""

    def __init__(self, name: str, schema: str, seed: Callable[[sqlite3.Connection, bool], None]):
        self.path = DATA / f"{name}.db"
        self.schema = schema
        self.seed = seed

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=5)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def ensure(self) -> None:
        DATA.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            empty = conn.execute("SELECT count(*) FROM sqlite_master WHERE type='table'").fetchone()[0] == 0
        if empty:
            self.reset()

    def reset(self, keep_public: bool = False) -> None:
        with self.connect() as conn:
            self.seed(conn, keep_public)

    def next_id(self, conn: sqlite3.Connection, key: str) -> int:
        row = conn.execute("SELECT v FROM meta WHERE k=?", (key,)).fetchone()
        value = int(row["v"]) if row else 1
        conn.execute("INSERT OR REPLACE INTO meta (k, v) VALUES (?, ?)", (key, str(value + 1)))
        return value


# ---------- app factory ----------

class LoginRequired(Exception):
    def __init__(self, path: str):
        self.path = path


def is_local(request: Request) -> bool:
    if env("REPLICAS_ALLOW_REMOTE") == "1":
        return True
    host = request.client.host if request.client else ""
    return host in LOCAL_HOSTS and not any(h in request.headers for h in PROXY_HEADERS)


templates = Jinja2Templates(directory=str(HERE / "templates"))
templates.env.filters["local"] = fmt_local
templates.env.filters["mask"] = mask_phone
templates.env.globals["now_local"] = lambda pattern="%d/%m/%Y %H:%M": datetime.now(PARIS).strftime(pattern)


class Replica:
    """A FastAPI app with the shared login, layout context, /health and /admin/reset."""

    def __init__(self, name: str, product: str, home: str, store: Store,
                 public_paths: tuple[str, ...] = (), reset_scopes: bool = False):
        self.name = name
        self.product = product
        self.home = home
        self.store = store
        self.public_paths = public_paths
        self.reset_scopes = reset_scopes
        @asynccontextmanager
        async def lifespan(_app: FastAPI):
            store.ensure()
            yield

        self.app = FastAPI(title=product, docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
        self.app.add_middleware(SessionMiddleware, secret_key=secrets.token_hex(32),
                                session_cookie=f"{name}_session", same_site="lax")
        self.app.mount("/static", StaticFiles(directory=str(HERE / "static")), name="static")
        self.app.middleware("http")(self._public_guard)
        self.app.add_exception_handler(LoginRequired, self._to_login)
        self._routes()

    # --- auth ---

    def operator(self, request: Request) -> str:
        user = request.session.get("user")
        if not user:
            path = request.url.path + (f"?{request.url.query}" if request.url.query else "")
            raise LoginRequired(path)
        return user

    async def _to_login(self, request: Request, exc: LoginRequired) -> Response:
        return RedirectResponse(f"/login?next={quote(exc.path)}", status_code=303)

    async def _public_guard(self, request: Request, call_next):
        """Through a tunnel or from the LAN, only the public paths exist."""
        if is_local(request):
            return await call_next(request)
        path = request.url.path
        if path.startswith("/static/") or any(path == p or path.startswith(p + "/") for p in self.public_paths):
            return await call_next(request)
        if path == "/" and self.public_paths:
            return RedirectResponse(self.public_paths[0], status_code=303)
        return HTMLResponse("<h1>404</h1>", status_code=404)

    # --- rendering ---

    def render(self, request: Request, template: str, status_code: int = 200, **ctx) -> HTMLResponse:
        ctx.setdefault("user", request.session.get("user"))
        ctx.setdefault("flash", request.session.pop("flash", None))
        return templates.TemplateResponse(request, template, {"app": self, **ctx}, status_code=status_code)

    def flash(self, request: Request, message: str) -> None:
        request.session["flash"] = message

    # --- shared routes ---

    def _routes(self) -> None:
        app = self.app

        @app.get("/health")
        def health() -> JSONResponse:
            ok = True
            try:
                with self.store.connect() as conn:
                    conn.execute("SELECT 1 FROM meta LIMIT 1")
            except sqlite3.Error:
                ok = False
            return JSONResponse({"ok": ok, "mock": False, "service": self.name},
                                headers={"Access-Control-Allow-Origin": "*"})

        @app.get("/login", response_class=HTMLResponse)
        def login_page(request: Request, next: str = ""):
            return self.render(request, "login.html", next=next, error=None, username="")

        @app.post("/login", response_class=HTMLResponse)
        def login(request: Request, username: str = Form(""), password: str = Form(""), next: str = Form("")):
            expected = env("REPLICA_PASSWORD")
            if expected and username.strip().lower() == USER and secrets.compare_digest(password, expected):
                request.session["user"] = USER
                target = next if next.startswith("/") and not next.startswith("//") else self.home
                return RedirectResponse(target, status_code=303)
            error = "Mot de passe non configuré sur le serveur." if not expected else "Identifiant ou mot de passe incorrect."
            return self.render(request, "login.html", status_code=401, next=next, error=error, username=username)

        @app.get("/logout")
        def logout(request: Request):
            request.session.clear()
            return RedirectResponse("/login", status_code=303)

        @app.get("/", include_in_schema=False)
        def root(request: Request):
            return RedirectResponse(self.home if request.session.get("user") else "/login", status_code=303)

        @app.get("/admin/reset", response_class=HTMLResponse)
        def reset_page(request: Request):
            return self.render(request, "reset.html", done=None)

        @app.post("/admin/reset")
        def reset(request: Request, scope: str = "", form_scope: str = Form("", alias="scope")):
            keep = (scope or form_scope or "seed") != "all" if self.reset_scopes else False
            self.store.reset(keep_public=keep)
            if "text/html" in request.headers.get("accept", ""):
                return self.render(request, "reset.html", done=datetime.now(PARIS).strftime("%H:%M:%S"), kept=keep)
            return JSONResponse({"ok": True, "service": self.name, "kept_public": keep},
                                headers={"Access-Control-Allow-Origin": "*"})
