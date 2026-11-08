"""MOCK=1: fixtures only. Placeholder frames say MOCK, the cam says « MOCK — aucun agent ». No fake agent steps."""

from __future__ import annotations

import asyncio
import io
import json

from PIL import Image, ImageDraw, ImageFont

from .config import FIXTURES, SHOTS
from .core import Endpoint, Run, now_iso, shot_url

DELAY = {"dispatch.read": 1.2, "maps.building": 5.0, "georisques.risks": 3.0, "weather.wind": 2.5,
         "plan.read": 4.0, "occupants.list": 2.0, "dispatch.write_112": 1.5, "report.fill": 6.0}


def placeholder(caption: str, w: int = 1280, h: int = 800) -> bytes:
    im = Image.new("RGB", (w, h), (58, 58, 58))
    d = ImageDraw.Draw(im)
    try:
        big = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 120)
        small = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 40)
    except Exception:
        big = small = ImageFont.load_default()
    d.text((w / 2, h / 2 - 60), "MOCK", fill=(230, 230, 230), font=big, anchor="mm")
    d.text((w / 2, h / 2 + 70), caption[:60], fill=(200, 200, 200), font=small, anchor="mm")
    d.text((w / 2, h / 2 + 130), "aucun agent · fixture", fill=(160, 160, 160), font=small, anchor="mm")
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=80)
    return buf.getvalue()


async def run(r: Run, ep: Endpoint) -> dict:
    f = FIXTURES / "endpoints" / f"{ep.name}.json"
    if not f.exists():
        return {"error": f"mock : pas de fixture pour {ep.name}"}
    fx = json.loads(f.read_text())
    img = placeholder(f"{ep.name}")
    (SHOTS / f"{r.run_id}-s00.jpg").write_bytes(img)
    from .core import cam
    cam.push({"run_id": r.run_id, "endpoint": ep.name, "step": 0, "action": "MOCK — aucun agent",
              "thought": "fixture contracts/fixtures", "shot_url": shot_url(f"{r.run_id}-s00"), "page_url": "",
              "at": now_iso(), "live": False})
    await asyncio.sleep(DELAY.get(ep.name, 1.5))
    for s in fx.get("screenshots", []):
        name = f"mock-{s['image_id']}"                     # never mixed with real screenshots
        p = SHOTS / f"{name}.jpg"
        if not p.exists():
            p.write_bytes(placeholder(s.get("caption", s["image_id"]), s.get("width", 1280), s.get("height", 800)))
        r.screenshots.append({**s, "url": shot_url(name), "taken_at": now_iso(), "_file": name})
    if fx.get("source"):
        r.source = {**fx["source"], "at": now_iso()}
    r.extra["summary"] = "MOCK — fixture"
    return {"output": fx.get("output"), "live": False}
