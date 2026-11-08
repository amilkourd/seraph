"""weather.wind — meteofrance.com. Holo searches the town; code reads the « Maintenant » wind from the DOM."""

from __future__ import annotations

import re
from datetime import datetime, timezone

from ..core import Run, RunFailed, endpoint, now_iso
from .common import agent

DIRS = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSO", "SO", "OSO", "O", "ONO", "NO", "NNO"]
FR = {"N": "nord", "E": "est", "S": "sud", "O": "ouest"}


def label_fr(code: str) -> str:
    """« SO » → « sud-ouest », « OSO » → « ouest-sud-ouest »."""
    return "-".join(FR[c] for c in code)


@endpoint(name="weather.wind", kind="real", access="read", timeout_s=45, cache="30min", site="meteofrance",
          source_kind="meteo", source_label="Météo-France", params={"town": "string"},
          cache_key=lambda p: str(p.get("town") or ""))
async def weather_wind(run: Run) -> dict:
    page = run.page
    town = str(run.params.get("town") or "").strip()
    if not town:
        raise RunFailed("town requis")
    await page.goto("https://meteofrance.com/", wait_until="domcontentloaded", timeout=15000)
    await page.wait_for_timeout(1000)
    task = (f"Open the weather forecast of « {town} » on Météo-France. If a cookie banner is shown, refuse the "
            "cookies first (« Refuser » / « Continuer sans accepter »). Click the search field, type the town name, "
            "click the matching suggestion, and answer when the town's forecast page is shown.")
    wind = page.locator("#atmogramme_slider li.wind p.wind-speed").first

    async def verify(_: str):
        await page.wait_for_timeout(800)
        if "/previsions-meteo-france/" not in page.url:
            return False, "the town's forecast page is not open"
        name = town.split()[0].lower()
        if name not in page.url.lower():
            return False, f"the forecast is not for {town}"
        return await wind.count() > 0, "wind block"

    await agent(run, task, verify, max_steps=12)
    img = await page.screenshot(type="jpeg", quality=85)
    run.add_shot("meteo-01", img, f"Météo-France, {town}", "top")
    code = (await wind.locator("img").get_attribute("title") or "").replace("Vent", "").strip().upper().replace("W", "O")
    speed = re.sub(r"\D", "", await wind.locator("strong").inner_text())
    if code not in DIRS or not speed:
        raise RunFailed(f"vent illisible sur la page ({code!r}, {speed!r})")
    hhmm = (await page.locator("#atmogramme_time_picker .period").first.inner_text()).strip()
    observed = now_iso()
    if re.fullmatch(r"\d{1,2}:\d{2}", hhmm):
        observed = datetime.now(timezone.utc).astimezone().replace(
            hour=int(hhmm[:-3]), minute=int(hhmm[-2:]), second=0, microsecond=0).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    run.source["url"] = page.url
    run.extra["summary"] = f"vent {code} {speed} km/h"
    # direction = where the wind comes FROM (meteorological convention, as Météo-France shows it)
    return {"dir_deg": DIRS.index(code) * 22.5, "dir_label": label_fr(code), "dir_code": code,
            "speed_kmh": int(speed), "observed_at": observed, "url": page.url}
