"""One SVG plan per level, 1000×1000, the same frame as `rooms[].zone` (image_id `ifc-L<n>`).
Thick outlines, room ids, doors, stairs, entrances. Black on white, like the plan posted at the door."""
from __future__ import annotations

from dataclasses import dataclass
from html import escape
from typing import Any

from shapely.geometry import Polygon
from shapely.ops import polylabel

SIZE = 1000
MARGIN = 60


@dataclass(frozen=True)
class Frame:
    """Building footprint (metres) → 0–1000 plan frame, y down, aspect kept, centred."""
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def scale(self) -> float:
        return (SIZE - 2 * MARGIN) / max(self.x1 - self.x0, self.y1 - self.y0, 1e-6)

    def to_plan(self, x: float, y: float) -> tuple[int, int]:
        s = self.scale
        ox = (SIZE - (self.x1 - self.x0) * s) / 2
        oy = (SIZE - (self.y1 - self.y0) * s) / 2
        return round(ox + (x - self.x0) * s), round(oy + (self.y1 - y) * s)

    def polygon(self, coords) -> list[list[int]]:
        out: list[list[int]] = []
        for x, y in coords:
            p = list(self.to_plan(x, y))
            if not out or out[-1] != p:
                out.append(p)
        if len(out) > 1 and out[0] == out[-1]:
            out.pop()
        return out


def _pts(poly: list[list[int]]) -> str:
    return " ".join(f"{x},{y}" for x, y in poly)


def _centre(poly: list[list[int]]) -> tuple[float, float]:
    """Label point inside the polygon (pole of inaccessibility: the middle of an L, not its corner)."""
    g = Polygon(poly)
    p = g.centroid if g.area > 0.95 * g.convex_hull.area else polylabel(g, tolerance=2)
    return p.x, p.y


def _font(poly: list[list[int]], text: str, biggest: int) -> int:
    """Largest font ≤ biggest that fits the label in the zone's width and height."""
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    w, h = max(xs) - min(xs), max(ys) - min(ys)
    return int(max(12, min(biggest, (w - 16) / (0.62 * max(len(text), 1)), h * 0.5)))


def level_svg(level: dict[str, Any], rooms: list[dict], stairs: list[dict], doors: list[dict],
              entrances: list[dict]) -> str:
    n = level["level"]
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {SIZE} {SIZE}" width="{SIZE}" height="{SIZE}">',
           f'  <!-- Seraph · plan from the IFC · level {n} ({escape(level["label"])}) · frame = rooms[].zone -->',
           f'  <rect width="{SIZE}" height="{SIZE}" fill="#ffffff"/>',
           f'  <text x="40" y="70" font-family="Arial" font-size="44" font-weight="bold" fill="#000">'
           f'{escape(level["label"])}</text>',
           '  <g fill="none" stroke="#000" stroke-width="8" stroke-linejoin="miter">']
    for r in rooms:
        if r.get("zone"):
            out.append(f'    <polygon points="{_pts(r["zone"])}"/>')
    for s in stairs:
        for z in s.get("zones", []):
            if z["level"] == n:
                out.append(f'    <polygon points="{_pts(z["zone"])}"/>')
    out.append("  </g>")

    # Stair hatching: horizontal treads across each stair zone.
    out.append('  <g stroke="#000" stroke-width="3">')
    for s in stairs:
        for z in s.get("zones", []):
            if z["level"] != n:
                continue
            xs = [p[0] for p in z["zone"]]
            ys = [p[1] for p in z["zone"]]
            x0, x1, y0, y1 = min(xs) + 12, max(xs) - 12, min(ys), max(ys)
            step = max(18, (y1 - y0) / 8)
            y = y0 + step
            while y < y1 - step / 2:
                out.append(f'    <line x1="{x0:.0f}" y1="{y:.0f}" x2="{x1:.0f}" y2="{y:.0f}"/>')
                y += step
    out.append("  </g>")

    # Doors: a white gap across the outline, with a short black jamb tick on each side.
    out.append('  <g>')
    for d in doors:
        p = d.get("plan_point")
        if not p or d["level"] != n:
            continue
        w = max(26, d.get("plan_width", 30))
        horiz = d.get("plan_axis", "x") == "x"
        x, y = p["x"], p["y"]
        if horiz:
            out.append(f'    <rect x="{x - w / 2:.0f}" y="{y - 7:.0f}" width="{w:.0f}" height="14" fill="#fff"/>')
        else:
            out.append(f'    <rect x="{x - 7:.0f}" y="{y - w / 2:.0f}" width="14" height="{w:.0f}" fill="#fff"/>')
        if d.get("fire_rating"):
            out.append(f'    <circle cx="{x}" cy="{y}" r="6" fill="#c00000"/>')
    out.append("  </g>")

    out.append('  <g font-family="Arial" fill="#000" text-anchor="middle">')
    for r in rooms:
        if not r.get("zone"):
            continue
        cx, cy = _centre(r["zone"])
        rid = str(r["id"])
        if rid.startswith("corridor:"):
            text, weight = r["label"].upper(), "normal"
        elif r.get("use") == "ascenseur":
            text, weight = "ASC.", "bold"
        else:
            text, weight = rid, "bold"
        size = _font(r["zone"], text, 22 if weight == "normal" else 30)
        out.append(f'    <text x="{cx:.0f}" y="{cy + size / 3:.0f}" font-size="{size}" font-weight="{weight}">'
                   f'{escape(text)}</text>')
    for s in stairs:
        for z in s.get("zones", []):
            if z["level"] == n:
                cx, cy = _centre(z["zone"])
                out.append(f'    <text x="{cx:.0f}" y="{cy + 14:.0f}" font-size="40" font-weight="bold" '
                           f'paint-order="stroke" stroke="#fff" stroke-width="10">{escape(s["id"])}</text>')
    for e in entrances:
        p = e.get("plan_point")
        if p and e.get("level") == n:
            out.append(f'    <text x="{p["x"]}" y="{p["y"]}" font-size="30" font-weight="bold" fill="#000" '
                       f'paint-order="stroke" stroke="#fff" stroke-width="10" dy="10">{escape(e["id"])}</text>')
    out.append("  </g>")
    out.append("</svg>")
    return "\n".join(out) + "\n"
