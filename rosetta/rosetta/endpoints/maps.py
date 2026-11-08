"""maps.building — Google Maps, satellite top view, Street View. Holo searches and points; code checks and computes.

Every point Halo draws (entrances, hydrant, truck spot) is on the one top view `earth-top-01`. Points found on Street
View go in `evidence` only. The address is checked against the national address base (BAN) first: no golden path
on an address that does not exist.
"""

from __future__ import annotations

import io
import math
import re
import time
from typing import Optional

import httpx
from PIL import Image, ImageDraw
from pydantic import BaseModel, Field

from ..core import Run, RunFailed, endpoint, is_demo_address, short
from ..holo import ask_json, check_blocked, gather_limited, locate
from .common import agent, deadline

SIDE_FR = {"front": "façade avant, côté rue", "left": "côté gauche", "right": "côté droit", "rear": "arrière"}


async def ban(address: str) -> Optional[dict]:
    """Code, not computer use: the national address base says whether the address exists, and where."""
    try:
        async with httpx.AsyncClient(timeout=6) as c:
            r = await c.get("https://api-adresse.data.gouv.fr/search/", params={"q": address, "limit": 1})
            f = r.json().get("features") or []
    except Exception:
        return None
    if not f:
        return None
    p = f[0]["properties"]
    lng, lat = f[0]["geometry"]["coordinates"]
    return {"label": p.get("label"), "score": p.get("score", 0), "type": p.get("type"), "lat": lat, "lng": lng}


def metres(a: tuple[float, float], b: tuple[float, float]) -> float:
    dy = (a[0] - b[0]) * 111_320
    dx = (a[1] - b[1]) * 111_320 * math.cos(math.radians(a[0]))
    return math.hypot(dx, dy)


def bearing(a: tuple[float, float], b: tuple[float, float]) -> float:
    la1, la2 = math.radians(a[0]), math.radians(b[0])
    dl = math.radians(b[1] - a[1])
    x = math.sin(dl) * math.cos(la2)
    y = math.cos(la1) * math.sin(la2) - math.sin(la1) * math.cos(la2) * math.cos(dl)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def place_coords(url: str) -> Optional[tuple[float, float]]:
    m = re.search(r"!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)", url)
    if m:
        return float(m.group(1)), float(m.group(2))
    return None


def is_sv(url: str) -> bool:
    """Street View layer in the URL: `@lat,lng,3a,75y,…t/data=!3m…!1e1…`."""
    return bool(re.search(r"@-?\d+\.\d+,-?\d+\.\d+,[\d.]+a,[\d.]+y", url)) and "!1e1" in url


def view_coords(url: str) -> Optional[tuple[float, float]]:
    m = re.search(r"@(-?\d+\.\d+),(-?\d+\.\d+)", url)
    return (float(m.group(1)), float(m.group(2))) if m else None


def ring(img: bytes, at: tuple[float, float]) -> bytes:
    im = Image.open(io.BytesIO(img)).convert("RGB")
    d = ImageDraw.Draw(im)
    x, y = at[0] * im.width, at[1] * im.height
    d.ellipse([x - 11, y - 11, x + 11, y + 11], outline=(255, 0, 0), width=4)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=88)
    return buf.getvalue()


# Google Maps UI drawn over the satellite image (1280×800 viewport): never part of a roof
UI_BOXES = [(0, 0, 72, 800), (72, 0, 1280, 62), (72, 62, 470, 180), (80, 690, 180, 790), (1110, 640, 1280, 800),
            (420, 780, 1280, 800)]


def roof_outline(img: bytes, seed: tuple[int, int], near: Optional[tuple[int, int]]) -> Optional[list[list[int]]]:
    """Code, not a model: from Holo's one point on the roof, flood-fill the roof's colour (textures flattened first),
    close small gaps, simplify to ≤ 16 vertices. None when the region is implausible."""
    import cv2
    import numpy as np
    bgr = cv2.imdecode(np.frombuffer(img, np.uint8), cv2.IMREAD_COLOR)
    h, w = bgr.shape[:2]
    sm = cv2.pyrMeanShiftFiltering(bgr, 12, 22)
    mask = np.zeros((h + 2, w + 2), np.uint8)
    sx, sy = w / 1280, h / 800
    for x0, y0, x1, y1 in UI_BOXES:
        mask[int(y0 * sy) + 1:int(y1 * sy) + 1, int(x0 * sx) + 1:int(x1 * sx) + 1] = 1
    px, py = int(seed[0] / 1000 * w), int(seed[1] / 1000 * h)
    if mask[py + 1, px + 1]:
        return None
    cv2.floodFill(sm, mask, (px, py), (0, 0, 0), (12, 12, 12), (12, 12, 12), 4 | cv2.FLOODFILL_MASK_ONLY | (255 << 8))
    m = (mask[1:-1, 1:-1] == 255).astype(np.uint8)
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (41, 41)))
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9)))
    cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cnts:
        return None
    c = max(cnts, key=cv2.contourArea)
    frac = cv2.contourArea(c) / (h * w)
    if not 0.005 <= frac <= 0.2:                      # a speck or half the city: not this building
        return None
    if near is not None:                              # the address (E1) must sit on or near this roof
        d = cv2.pointPolygonTest(c, (near[0] / 1000 * w, near[1] / 1000 * h), True)
        if d < -0.06 * max(w, h):
            return None
    eps = 0.004 * cv2.arcLength(c, True)
    poly = cv2.approxPolyDP(c, eps, True)
    while len(poly) > 16:
        eps *= 1.3
        poly = cv2.approxPolyDP(c, eps, True)
    return [[int(round(x / w * 1000)), int(round(y / h * 1000))] for x, y in poly[:, 0, :]]


class Storeys(BaseModel):
    storeys: int = Field(description="number of storeys above ground including the ground floor, 0 if no building is visible")


@endpoint(name="maps.building", kind="real", access="read + vision", timeout_s=90, cache="golden", site="google",
          source_kind="maps", source_label="Maps",
          params={"address": "string", "expected_entrances": "{id, label, side?}[]?"},
          cache_key=lambda p: str(p.get("address") or ""),
          cache_scope=lambda p: is_demo_address(p.get("address")))
async def maps_building(run: Run) -> dict:
    page = run.page
    address = str(run.params.get("address") or "").strip()
    expected = run.params.get("expected_entrances") or [{"id": "E1", "label": "Entrée principale", "side": "front"}]
    end = deadline(run, 3)
    notes: list[str] = []

    b = await ban(address)
    await run.frame("vérifie l'adresse (BAN, calcul)", f"{address} → {b['label'] if b else 'introuvable'}"
                    + (f" ({b['score']:.2f})" if b else ""))
    if not b or b["score"] < 0.75 or b["type"] not in ("housenumber", "street"):
        run.extra["cacheable"] = False
        raise RunFailed(f"adresse introuvable dans la Base Adresse Nationale ({address}"
                        + (f" ; plus proche : {b['label']}" if b else "") + ")")
    target = (b["lat"], b["lng"])

    # 1. Holo searches the address on Google Maps (consent refused once, cookies kept per site)
    await page.goto("https://www.google.com/maps?hl=fr", wait_until="domcontentloaded", timeout=15000)
    await page.wait_for_timeout(1200)
    task = (f"Find the address « {address} » on Google Maps. If a cookie consent page is shown, click « Tout refuser » "
            "first. Then click the search box, type the address, press Enter, and answer when the place for this "
            "address is shown on the map.")

    async def verify(_: str):
        await page.wait_for_timeout(600)
        pc = place_coords(page.url)
        if "/maps/place/" not in page.url or not pc:
            return False, "the place page for the address is not open (no place in the URL)"
        d = metres(pc, target)
        return d < 250, f"place at {d:.0f} m from the BAN address"

    await agent(run, task, verify, max_steps=10, hints="", until=time.time() + 40)
    pin = place_coords(page.url) or target
    run.source["url"] = page.url.split("/data=")[0]

    # 2. Top view (satellite, north up): the one image every drawn point lives on
    await page.goto(f"https://www.google.com/maps/@{pin[0]},{pin[1]},70m/data=!3m1!1e3?hl=fr",
                    wait_until="domcontentloaded", timeout=15000)
    await page.wait_for_timeout(3500)
    await check_blocked(page)
    top = await page.screenshot(type="jpeg", quality=85)
    run.add_shot("earth-top-01", top, "Vue du dessus, nord en haut (Google Maps satellite)", "top")
    await run.frame("vue du dessus (satellite)", "le bâtiment au centre, nord en haut", top)

    # Holo's copy only: a red ring on the address point (BAN, on the street façade); the stored shot stays raw
    ringed = ring(top, (0.5, 0.5))
    centre = "the building whose street façade has the red ring (the ring marks the address)"

    async def on_top() -> dict:
        # from above a door is not visible: Holo points where the entrance's façade meets the street
        targets = {e["id"]: (f"the {e.get('label', e['id'])} of {centre}, on its "
                             f"{SIDE_FR.get(e.get('side') or 'front', 'façade')}") for e in expected}
        targets["H1"] = f"a fire hydrant (small red or yellow post on the sidewalk) near {centre}, not a map icon"
        targets["roof"] = f"the middle of the roof of {centre}"
        targets["truck"] = ("a point on the traffic lanes of the street nearest to the red ring: dark asphalt with white "
                            "lane markings, not the sidewalk, not a roof, not a map label")
        keys = list(targets)
        absent_ok = {"H1"} | {e["id"] for e in expected if (e.get("side") or "front") != "front"}
        res = await gather_limited([locate(ringed, targets[k], may_be_absent=k in absent_ok) for k in keys], limit=10)
        return dict(zip(keys, res))

    top_pts = await on_top()
    for k, p in top_pts.items():
        if isinstance(p, tuple):
            await run.frame(f"point ({p[0]},{p[1]}) {k}", "sur la vue du dessus", top)
    footprint = None                                   # Holo points once at the roof; code draws the outline
    if isinstance(top_pts.get("roof"), tuple):
        e1 = top_pts.get(expected[0]["id"]) if expected else None
        poly = roof_outline(top, top_pts["roof"], e1 if isinstance(e1, tuple) else None)
        if poly:
            footprint = {"image_id": "earth-top-01", "polygon": poly,
                         "source": "toit pointé par Holo, contour calculé (remplissage)"}
            await run.frame(f"contour du toit : {len(poly)} sommets (calcul)", "depuis le point de Holo sur le toit", top)
        else:
            notes.append("contour du toit non retenu (calcul)")

    # 3. Street View: code computes the heading from the panorama to the address; Holo points (evidence only)
    shots_sv: dict[str, bytes] = {}
    if time.time() < end - 25:
        try:
            pano = None
            for dn, de in [(0, 0), (-18, 0), (0, 18), (18, 0), (0, -18)]:   # metres: a street pano, not a photo sphere
                if time.time() > end - 30:
                    break
                vp = (target[0] + dn / 111_320, target[1] + de / (111_320 * math.cos(math.radians(target[0]))))
                await page.goto(f"https://www.google.com/maps/@?api=1&map_action=pano&viewpoint={vp[0]},{vp[1]}"
                                f"&heading=0&pitch=5&fov=90", wait_until="domcontentloaded", timeout=15000)
                try:                                   # Maps rewrites the URL once the panorama is chosen
                    await page.wait_for_url(lambda u: "!2e" in u, timeout=9000)
                except Exception:
                    pass
                await page.wait_for_timeout(1500)
                await check_blocked(page)
                if is_sv(page.url) and "!2e0" in page.url:
                    pano = view_coords(page.url)
                    break
                await run.frame("panorama écarté (photo d'utilisateur)" if "!2e10" in page.url else "pas de panorama ici",
                                "on cherche une vue Street View de la rue", None)
            if pano and is_sv(page.url):
                sv_url = page.url
                h0 = bearing(pano, target)
                for image_id, dh, side, cap in [("sv-front-01", 0, "front", "Façade côté rue (Street View)"),
                                                ("sv-left-01", -55, "left", "Vers la gauche (Street View)"),
                                                ("sv-right-01", 55, "right", "Vers la droite (Street View)")]:
                    if time.time() > end - 14:
                        break
                    h = (h0 + dh) % 360
                    url = re.sub(r",[\d.]+y,(?:[\d.]+h,)?[\d.]+t", f",90y,{h:.1f}h,90t", sv_url, count=1)
                    await page.goto(url, wait_until="domcontentloaded", timeout=12000)
                    await page.wait_for_timeout(2600)
                    if not is_sv(page.url):
                        notes.append(f"{image_id} : Street View n'a pas chargé")
                        continue
                    img = await page.screenshot(type="jpeg", quality=85)
                    shots_sv[image_id] = img
                    run.add_shot(image_id, img, cap, side)
                    await run.frame(f"Street View cap {h:.0f}°", f"cap calculé vers l'adresse ({metres(pano, target):.0f} m)", img)
            else:
                notes.append("Street View indisponible à cette adresse")
        except RunFailed:
            raise
        except Exception as exc:
            notes.append(f"Street View : {type(exc).__name__}")
    else:
        notes.append("Street View sauté (temps)")

    evidence: list[dict] = []
    storeys = None
    if "sv-front-01" in shots_sv and time.time() < end - 6:
        img = shots_sv["sv-front-01"]
        jobs = [locate(img, f"the entrance door of the building in this street photo ({e.get('label', e['id'])})") for e in expected]
        jobs.append(locate(img, "a fire hydrant (red or yellow post) on the sidewalk"))
        jobs.append(ask_json(img, "Count the storeys of the building in the middle of this street photo.", Storeys))
        res = await gather_limited(jobs, limit=6)
        for e, p in zip(expected, res[: len(expected)]):
            if isinstance(p, tuple):
                evidence.append({"of": e["id"], "point": {"image_id": "sv-front-01", "x": p[0], "y": p[1]}})
                await run.frame(f"point ({p[0]},{p[1]}) {e['id']}", "preuve sur Street View", img)
        if isinstance(res[len(expected)], tuple):
            p = res[len(expected)]
            evidence.append({"of": "H1", "point": {"image_id": "sv-front-01", "x": p[0], "y": p[1]}})
        st = res[-1]
        if isinstance(st, Storeys) and 0 < st.storeys < 60:
            storeys = st.storeys

    entrances = []
    for e in expected:
        p = top_pts.get(e["id"])
        if isinstance(p, tuple):
            entrances.append({"id": e["id"], "label": e.get("label", e["id"]), "side": e.get("side") or "front",
                              "point": {"image_id": "earth-top-01", "x": p[0], "y": p[1]}})
        else:
            notes.append(f"{e['id']} non vu d'en haut")
    hydrants = []
    if isinstance(top_pts.get("H1"), tuple):
        p = top_pts["H1"]
        hydrants.append({"id": "H1", "label": "Poteau incendie (vu d'en haut)",
                         "point": {"image_id": "earth-top-01", "x": p[0], "y": p[1]}})
    else:
        notes.append("poteau incendie non vu d'en haut")
    truck = None
    if isinstance(top_pts.get("truck"), tuple):
        p = top_pts["truck"]
        truck = {"label": "Voie devant l'entrée", "point": {"image_id": "earth-top-01", "x": p[0], "y": p[1]}}
    out = {"storeys_estimate": storeys, "footprint": footprint, "entrances": entrances, "hydrants": hydrants, "truck_spot": truck,
           "evidence": evidence, "obstacles": [], "address_ban": b["label"],
           "location": {"lat": round(pin[0], 6), "lng": round(pin[1], 6)}}
    notes.append("Earth 3D non utilisé : vue du dessus Google Maps satellite")
    out["notes"] = notes
    run.error = "; ".join(notes)                      # status stays ok (contract §2)
    run.extra["summary"] = short(f"{len(entrances)} entrées, {len(hydrants)} poteau, camion {'oui' if truck else 'non'}, "
                                 f"{len(run.screenshots)} vues")
    return out
