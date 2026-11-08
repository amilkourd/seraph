"""A view is served only if it passes: halo/kit/check-view.mjs, Silex's own static checks, a headless render."""
from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Optional

from .config import KIT, REPO

MAX_BYTES = 200_000
NETWORK = re.compile(r"\bfetch\s*\(|XMLHttpRequest|WebSocket|EventSource|sendBeacon|\bimport\s*\(|importScripts")


async def check_view(path: Path) -> list[str]:
    """halo/kit/check-view.mjs, verbatim errors."""
    proc = await asyncio.create_subprocess_exec("node", str(KIT / "check-view.mjs"), str(path), cwd=str(REPO),
                                                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=20)
    except asyncio.TimeoutError:
        proc.kill()
        return ["check-view.mjs timed out"]
    if proc.returncode == 0:
        return []
    lines = [l.strip() for l in out.decode("utf-8", "replace").splitlines()]
    return [l for l in lines if l and not l.startswith(("✗", "✓"))] or [f"check-view.mjs exit {proc.returncode}"]


def static_checks(html: str) -> list[str]:
    errs = []
    if len(html.encode("utf-8")) > MAX_BYTES:
        errs.append(f"file is {len(html.encode('utf-8')) // 1000} KB, must be under 200 KB")
    if "{{HALO_KIT_URL}}/halo-kit.js" not in html or "{{HALO_KIT_URL}}/halo.css" not in html:
        errs.append("must load {{HALO_KIT_URL}}/halo-kit.js and {{HALO_KIT_URL}}/halo.css (keep the placeholder as is)")
    if "Halo.ready(" not in html:
        errs.append("must call Halo.ready() once mounted")
    if "Halo.onState(" not in html:
        errs.append("must redraw from Halo.onState(fn)")
    m = NETWORK.search(html)
    if m:
        errs.append(f"no network calls: found « {m.group(0)} »")
    return errs


HAZARD_WORDS = re.compile(r"\b(feu|fumée|fumee|incendie|fire|smoke)\b", re.I)
RAW_VALUES = re.compile(r"\b(null|undefined|NaN)\b", re.I)   # a missing field printed as text


def no_hazard(state: dict) -> dict:
    """The same state with nothing reported: no hazard, no stair in smoke."""
    s = json.loads(json.dumps(state))
    b = s.get("building") or {}
    b["hazards"] = []
    for st in b.get("stairs") or []:
        if st.get("status") in ("smoke", "blocked"):
            st["status"] = "unknown"
    for r in b.get("rooms") or []:
        r.pop("hazard", None)
    return s


def with_fire(state: dict) -> dict:
    """The same state with one fire reported by the crew: in the incident's room if the building has it."""
    s = no_hazard(state)
    b = s.get("building") or {}
    origin = (s.get("incident") or {}).get("origin") or {}
    rooms = [r for r in b.get("rooms") or [] if r.get("zone")]
    room = next((r for r in rooms if r.get("id") == origin.get("room")), None) \
        or next((r for r in rooms if r.get("level") == origin.get("floor")), None) or (rooms[0] if rooms else None)
    where = {"level": room.get("level"), "room": room.get("id")} if room else {"level": origin.get("floor", 0)}
    b["hazards"] = [{"id": "HZ-silex-check", "kind": "fire", "where": where, "severity": "high",
                     "source": {"kind": "radio", "label": "Tête", "url": None, "confirmed": True,
                                "at": "2026-11-08T05:00:00Z"}}]
    return s


class Renderer:
    """One headless Chromium for the whole process. Renders the staged view with the live state."""

    def __init__(self) -> None:
        self._pw = None
        self._browser = None
        self._lock = asyncio.Lock()
        self.available: Optional[bool] = None

    async def _ensure(self) -> bool:
        if self._browser:
            return True
        if self.available is False:
            return False
        try:
            from playwright.async_api import async_playwright
            self._pw = await async_playwright().start()
            try:
                self._browser = await self._pw.chromium.launch(headless=True)
            except Exception:
                # another project's Playwright build is already on disk: use it rather than download one
                shells = sorted(Path.home().glob("Library/Caches/ms-playwright/chromium_headless_shell-*/*/chrome-headless-shell"))
                if not shells:
                    raise
                self._browser = await self._pw.chromium.launch(headless=True, executable_path=str(shells[-1]))
            self.available = True
        except Exception:
            self.available = False
        return bool(self.available)

    @staticmethod
    async def _show(page, state: dict) -> tuple[str, int]:
        await page.evaluate("m => window.postMessage(m, '*')", json.dumps({"type": "seraph:state", "state": state}))
        await page.wait_for_timeout(400)
        return await page.evaluate("document.body.innerText"), await page.evaluate("document.querySelectorAll('svg *').length")

    async def render(self, url: str, state: dict, shot: Path, expect_hazards: bool = True) -> list[str]:
        """Loads `url` as the native shell would (string messages, ReactNativeWebView): the live state twice, then
        the same state with nothing reported and with a reported fire."""
        async with self._lock:
            if not await self._ensure():
                return []                    # no browser: static checks only (said in /health)
            page = await self._browser.new_page(viewport={"width": 874, "height": 402}, device_scale_factor=2)
            errors: list[str] = []
            page.on("pageerror", lambda e: errors.append(f"JS error: {str(e)[:200]}"))
            page.on("console", lambda m: errors.append(f"console.error: {m.text[:200]}") if m.type == "error" else None)
            page.on("requestfailed", lambda r: errors.append(f"request failed: {r.url[:120]}"))
            await page.add_init_script("window.__shell=[];window.ReactNativeWebView={postMessage:m=>window.__shell.push(String(m))};")
            try:
                await page.goto(url, wait_until="load", timeout=10_000)
                ground = await page.evaluate("document.querySelectorAll('svg *').length")   # the kit's frame alone
                msg = json.dumps({"type": "seraph:state", "state": state})
                for _ in range(2):           # the view must survive repeated updates
                    await page.evaluate("m => window.postMessage(m, '*')", msg)
                    await page.wait_for_timeout(500)
                shell = await page.evaluate("window.__shell")
                drawn = await page.evaluate("document.querySelectorAll('svg *').length") - ground
                await page.screenshot(path=str(shot))
                text_live = await page.evaluate("document.body.innerText")
                # live-bound: A = nothing reported, B = a fire reported by the crew. A must show no fire or smoke
                # (Amil: they appear only once reported), and a view about the building must change from A to B
                text_a, count_a = await self._show(page, no_hazard(state))
                text_b, count_b = await self._show(page, with_fire(state))
                raw = RAW_VALUES.findall(" ".join((text_live or "", text_a or "", text_b or "")))
                if raw:
                    errors.append(f"the view prints « {raw[0]} »: a field missing from the state is never shown as text "
                                  "(room null → « à confirmer », a null count → no line)")
                left = HAZARD_WORDS.findall(text_a or "")
                if left:
                    errors.append(f"with no hazard in the state the view still shows « {left[0]} »: fire and smoke must come "
                                  "from state.building.hazards (and stair status) at runtime, never from literal text")
                if expect_hazards and text_a == text_b and count_a == count_b:
                    errors.append("the view does not react to a reported fire (same drawing and card with and without "
                                  "building.hazards): draw each hazard live with Halo.fire/smoke(svg, zone, {hazard}) and "
                                  "its card line with Halo.hazardLine(state, h)")
            except Exception as e:
                errors.append(f"render failed: {type(e).__name__}: {str(e)[:160]}")
                shell, drawn = [], 0
                ground = 0
            finally:
                await page.close()
            if not any('"seraph:ready"' in m for m in shell):
                errors.append("never posted seraph:ready (call Halo.ready() once mounted)")
            if drawn < 5:
                errors.append(f"draws nothing with the live state (the state added {drawn} SVG elements to the frame)")
            return list(dict.fromkeys(errors))

    async def close(self) -> None:
        if self._browser:
            await self._browser.close()
        if self._pw:
            await self._pw.stop()


renderer = Renderer()
