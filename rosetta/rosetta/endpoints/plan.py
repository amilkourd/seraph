"""plan.read — the plan posted at the door (a photo or a rendered plan). Holo reads and points; code draws the zones.

The image is shown at its natural size, so the screenshot is the image itself and Holo's 0–1000 grid is the plan's
own frame (for the TU Wien demo: the frame of `ifc-L-1`). Zones: walls by threshold, small marks (text) dropped,
thin gaps closed, flood-fill from each pointed room / stair, outer contour simplified.
"""

from __future__ import annotations

import base64
import io
import re
from pathlib import Path
from typing import Literal, Optional

import cv2
import numpy as np
from PIL import Image
from pydantic import BaseModel, Field

from ..config import ROOT
from ..core import Run, RunFailed, endpoint
from ..holo import ask_json, gather_limited, locate

KINDS = Literal["room", "stair", "elevator", "exit", "electric_cutoff", "gas_cutoff", "riser", "extinguisher",
                "you_are_here", "corridor", "other"]


class Item(BaseModel):
    kind: KINDS
    label: str = Field(description="the text exactly as written on the plan, or a short description for a symbol")


class Reading(BaseModel):
    items: list[Item]


READ_Q = ("This is a fire-service floor plan of one level of a building. List every element it shows: each room "
          "number written on it (e.g. -1.03, 3.12), each stair (ESC A…), lift (ASC), exit marker (E1, E2…), "
          "electric cut-off (lightning symbol), gas cut-off, dry riser (colonne sèche), extinguisher, and the "
          "« vous êtes ici » marker if any. For a room give the number as label. Do not invent anything not drawn.")

SYMBOLS = {  # name → what Holo looks for when the plan uses a symbol rather than text
    "electric_cutoff": "the electric cut-off symbol (yellow triangle with a lightning bolt)",
    "gas_cutoff": "the gas cut-off symbol",
    "riser": "the dry riser (colonne sèche) symbol",
    "extinguisher": "the extinguisher symbol",
    "you_are_here": "the « vous êtes ici » (you are here) marker",
}
FR = {"elevator": "Ascenseur", "electric_cutoff": "Coupure électrique", "gas_cutoff": "Coupure gaz",
      "riser": "Colonne sèche", "extinguisher": "Extincteur", "you_are_here": "Vous êtes ici", "corridor": "Circulation"}


def name_of(it: Item) -> Optional[tuple[str, str, str]]:
    """(name, label_fr, localization target) — names from contracts/rosetta-endpoints.md §5."""
    lab = it.label.strip()
    if it.kind == "room":
        m = re.search(r"-?\d+\.[0-9A-Z]{1,3}\b", lab)
        return (f"room:{m.group(0)}", m.group(0), f"the room number « {m.group(0)} » written on the plan") if m else None
    if it.kind == "stair":
        m = re.search(r"\b([A-H])\s*$", lab.upper())
        sid = m.group(1) if m else "A"
        return f"stair:{sid}", f"Escalier {sid}", f"the stair « {lab} » (stair symbol or label)"
    if it.kind == "exit":
        m = re.search(r"\b(E\d+)\b", lab.upper())
        return (f"exit:{m.group(1)}", f"Sortie {m.group(1)}", f"the exit marker « {m.group(1)} »") if m else None
    if it.kind == "elevator":
        return "elevator", FR["elevator"], f"the lift « {lab} »"
    if it.kind == "corridor":
        return "corridor", FR["corridor"], "the common circulation corridor"
    if it.kind in SYMBOLS:
        return it.kind, FR[it.kind], SYMBOLS[it.kind]
    return None


def rel(path: str) -> str:
    """Cache key: the same plan whether Seraph sends it absolute or relative to the repo."""
    try:
        return str(Path(path).resolve().relative_to(ROOT)) if Path(path).is_absolute() else str(Path(path))
    except ValueError:
        return path


def resolve(path: str) -> Path:
    p = Path(path)
    if not p.is_absolute():
        p = ROOT / p
    p = p.resolve()
    if not p.exists():
        raise RunFailed(f"plan introuvable : {path}")
    return p


def zones(img: bytes, seeds: list[tuple[str, int, int]]) -> list[dict]:
    """Code, not a model: a zone is the region of the seed's fill colour that the walls enclose, from Holo's point."""
    rgb = np.array(Image.open(io.BytesIO(img)).convert("RGB"))
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    h, w = gray.shape
    wall = (gray < 170).astype(np.uint8)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(wall, connectivity=8)
    keep = np.zeros(n, np.uint8)
    keep[1:] = stats[1:, cv2.CC_STAT_AREA] >= 0.0012 * h * w          # drop text and small marks
    wall = cv2.morphologyEx(keep[lab], cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5)))
    free = (1 - wall).astype(np.uint8)
    rgb16 = rgb.astype(np.int16)
    found: list[tuple[np.ndarray, list[tuple[str, int, int]]]] = []
    for name, x, y in seeds:
        px, py = min(w - 1, int(x / 1000 * w)), min(h - 1, int(y / 1000 * h))
        r = 30                       # Holo points at the label: take the window's dominant fill colour, then its nearest pixel
        y0, x0 = max(0, py - r), max(0, px - r)
        win_free = free[y0:py + r + 1, x0:px + r + 1].astype(bool)
        win = rgb16[y0:py + r + 1, x0:px + r + 1]
        if not win_free.any():
            continue
        pix = win[win_free]
        bins = np.unique(pix // 24, axis=0)
        cands = [pix[(pix // 24 == b).all(axis=1)].mean(axis=0) for b in bins]
        score = [int((np.abs(pix - c).max(axis=1) < 40).sum()) for c in cands]
        dom = cands[int(np.argmax(score))]
        near = (np.abs(win - dom).max(axis=2) < 40)
        ys, xs = np.nonzero(win_free & near)
        k = int(np.argmin((xs + x0 - px) ** 2 + (ys + y0 - py) ** 2))
        sx, sy = int(xs[k] + x0), int(ys[k] + y0)
        colour = rgb16[sy, sx]
        same = (np.abs(rgb16 - colour).max(axis=2) < 40).astype(np.uint8)
        same = same if name.startswith("stair:") else same & free     # treads are drawn as dense dark lines
        kk = 25 if name.startswith("stair:") else 9          # stair treads cut the fill into strips: bridge them
        same = cv2.morphologyEx(same, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (kk, kk)))
        same = same if name.startswith("stair:") else same & free
        _, cc = cv2.connectedComponents(same, connectivity=4)
        if cc[sy, sx] == 0:
            continue
        comp = (cc == cc[sy, sx]).astype(np.uint8)
        if comp[0].any() or comp[-1].any() or comp[:, 0].any() or comp[:, -1].any():
            continue                                   # outside the building
        for m, names in found:
            if (m & comp).sum() > 0.9 * min(m.sum(), comp.sum()):
                names.append((name, px, py))
                break
        else:
            found.append((comp, [(name, px, py)]))
    out = []
    for mask, names in found:
        filled = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15)))
        cnts, _ = cv2.findContours(filled, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not cnts:
            continue
        c = max(cnts, key=cv2.contourArea)
        poly = cv2.approxPolyDP(c, 0.003 * (h + w), True)[:, 0, :]
        m = cv2.moments(c)
        cx, cy = m["m10"] / max(m["m00"], 1), m["m01"] / max(m["m00"], 1)
        # one region, several names (parking places in one garage): the zone goes to the name nearest its centre
        names.sort(key=lambda t: (t[1] - cx) ** 2 + (t[2] - cy) ** 2)
        z = {"name": names[0][0], "polygon": [[int(round(x * 1000 / w)), int(round(y * 1000 / h))] for x, y in poly],
             "area_pct": round(100 * float(cv2.contourArea(c)) / (h * w), 2)}
        if len(names) > 1:
            z["also"] = [t[0] for t in names[1:]]
        out.append(z)
    return out


@endpoint(name="plan.read", kind="real", access="vision", timeout_s=60, cache="golden", site="",
          source_kind="plan", source_label="plan affiché", params={"image_path": "string", "level": "number"},
          cache_key=lambda p: f"{rel(str(p.get('image_path') or ''))}|{p.get('level')}")
async def plan_read(run: Run) -> dict:
    path = resolve(str(run.params.get("image_path") or ""))
    level = run.params.get("level")
    level = int(level) if level is not None and re.fullmatch(r"-?\d+", str(level)) else None
    data = path.read_bytes()
    if path.suffix.lower() == ".svg":
        m = re.search(rb'<svg[^>]*\bwidth="(\d+)"[^>]*\bheight="(\d+)"', data)
        w, h = (int(m.group(1)), int(m.group(2))) if m else (1000, 1000)
        mime = "image/svg+xml"
    else:
        w, h = Image.open(io.BytesIO(data)).size
        mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    scale = min(1.0, 1400 / max(w, h))
    vw, vh = int(w * scale), int(h * scale)
    page = run.page
    await page.set_viewport_size({"width": vw, "height": vh})
    await page.set_content(f'<html><body style="margin:0;background:#fff"><img src="data:{mime};base64,'
                           f'{base64.b64encode(data).decode()}" style="display:block;width:{vw}px;height:{vh}px"></body></html>')
    await page.wait_for_timeout(300)
    img = await page.screenshot(type="png")
    image_id = f"plan-l{level}-01" if level is not None else "plan-01"
    run.add_shot(image_id, img, f"Plan affiché, niveau {level}" if level is not None else "Plan affiché", "plan")
    await run.frame("ouvre le plan affiché", f"{path.name}, {w}×{h}", img)

    reading = await ask_json(img, READ_Q, Reading)
    seen: dict[str, tuple[str, str]] = {}
    for it in reading.items:
        t = name_of(it)
        if t and t[0] not in seen:
            seen[t[0]] = (t[1], t[2])
    await run.frame(f"lit le plan : {len(seen)} éléments", ", ".join(list(seen)[:12]), img)
    if not seen:
        raise RunFailed("Holo n'a lu aucun élément sur le plan")

    names = list(seen)
    found = await gather_limited([locate(img, seen[n][1]) for n in names], limit=8)
    points = []
    for n, p in zip(names, found):
        if isinstance(p, Exception) or p is None:
            continue
        points.append({"name": n, "label": seen[n][0], "point": {"image_id": image_id, "x": p[0], "y": p[1]}})
        await run.frame(f"point ({p[0]},{p[1]}) {n}", seen[n][0], img)
    zs = zones(img, [(p["name"], p["point"]["x"], p["point"]["y"]) for p in points
                     if p["name"].startswith(("room:", "stair:", "corridor", "elevator"))])
    run.extra["summary"] = f"{len(points)} points, {len(zs)} zones (calcul)"
    run.source["url"] = run.screenshots[0]["url"]
    return {"level": level, "image_id": image_id, "points": points, "zones": zs,
            "zones_source": "calcul (seuil, remplissage depuis les points de Holo)"}
