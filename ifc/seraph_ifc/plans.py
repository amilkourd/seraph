"""One SVG plan per level, 1000×1000, the same frame as `rooms[].zone` (image_id `ifc-L<n>`).
Thick outlines, room ids, doors, stairs, entrances. Black on white, like the plan posted at the door."""
from __future__ import annotations

import math
from dataclasses import dataclass
from html import escape
from typing import Any, Optional

from shapely.affinity import rotate
from shapely.geometry import Polygon
from shapely.ops import polylabel, unary_union

SIZE = 1000
MARGIN = 60


@dataclass(frozen=True)
class Frame:
    """World plan coordinates (metres) → the 0–1000 frame shared by every level, every zone and every consumer.

    The building is turned by `theta` (radians, counter-clockwise) around (cx, cy) so that its walls run along the
    axes and its front façade (E1) is at the bottom, then fitted in 1000×1000 with a 60-unit margin, y down, aspect
    kept. `to_m` gives the same turned coordinates in metres, origin at the bottom-left of the building."""
    theta: float
    cx: float
    cy: float
    x0: float
    y0: float
    x1: float
    y1: float

    @classmethod
    def fit(cls, polys, theta: float = 0.0, centre: Optional[tuple[float, float]] = None) -> "Frame":
        u = unary_union(list(polys))
        cx, cy = centre or (u.centroid.x, u.centroid.y)
        x0, y0, x1, y1 = rotate(u, theta, origin=(cx, cy), use_radians=True).bounds
        return cls(theta, cx, cy, x0, y0, x1, y1)

    def rot(self, x: float, y: float) -> tuple[float, float]:
        c, s = math.cos(self.theta), math.sin(self.theta)
        dx, dy = x - self.cx, y - self.cy
        return self.cx + c * dx - s * dy, self.cy + s * dx + c * dy

    @property
    def scale(self) -> float:
        return (SIZE - 2 * MARGIN) / max(self.x1 - self.x0, self.y1 - self.y0, 1e-6)

    @property
    def offset(self) -> tuple[float, float]:
        s = self.scale
        return (SIZE - (self.x1 - self.x0) * s) / 2, (SIZE - (self.y1 - self.y0) * s) / 2

    def to_plan_f(self, x: float, y: float) -> tuple[float, float]:
        xr, yr = self.rot(x, y)
        ox, oy = self.offset
        return ox + (xr - self.x0) * self.scale, oy + (self.y1 - yr) * self.scale

    def to_plan(self, x: float, y: float) -> tuple[int, int]:
        px, py = self.to_plan_f(x, y)
        return round(px), round(py)

    def to_m(self, x: float, y: float) -> tuple[float, float]:
        xr, yr = self.rot(x, y)
        return round(xr - self.x0, 2), round(yr - self.y0, 2)

    def polygon(self, coords) -> list[list[int]]:
        out: list[list[int]] = []
        for x, y in coords:
            p = list(self.to_plan(x, y))
            if not out or out[-1] != p:
                out.append(p)
        if len(out) > 1 and out[0] == out[-1]:
            out.pop()
        return out

    def polygon_m(self, coords) -> list[list[float]]:
        out = [list(self.to_m(x, y)) for x, y in coords]
        if len(out) > 1 and out[0] == out[-1]:
            out.pop()
        return out

    def side(self, x: float, y: float) -> str:
        """Which side of the turned building a point is on: bottom (front), top, left or right."""
        xr, yr = self.rot(x, y)
        d = {"bottom": yr - self.y0, "top": self.y1 - yr, "left": xr - self.x0, "right": self.x1 - xr}
        return min(d, key=d.get)

    def info(self) -> dict[str, Any]:
        """How to go from metres (`*_m` fields) to the 0–1000 frame: x = origin_x + x_m·px_per_m,
        y = origin_y − y_m·px_per_m."""
        ox, oy = self.offset
        return {"size": SIZE, "px_per_m": round(self.scale, 4), "rotation_deg": round(math.degrees(self.theta), 2),
                "origin_px": [round(ox, 2), round(oy + (self.y1 - self.y0) * self.scale, 2)],
                "width_m": round(self.x1 - self.x0, 2), "depth_m": round(self.y1 - self.y0, 2)}


def dominant_angle(polys) -> float:
    """Rotation (radians) that brings the building's main wall direction onto the x axis: length-weighted
    histogram of polygon edge directions, modulo 90°."""
    hist: dict[float, float] = {}
    for p in polys:
        cs = list(p.exterior.coords)
        for (ax, ay), (bx, by) in zip(cs, cs[1:]):
            length = math.hypot(bx - ax, by - ay)
            if length < 0.3:
                continue
            a = round((math.degrees(math.atan2(by - ay, bx - ax)) % 90.0) * 2) / 2 % 90.0
            hist[a] = hist.get(a, 0.0) + length
    if not hist:
        return 0.0
    best = max(hist, key=hist.get)
    num = den = 0.0
    for a, w in hist.items():
        d = ((a - best + 45) % 90) - 45
        if abs(d) <= 1.0:
            num += (best + d) * w
            den += w
    ang = num / den
    if ang > 45:
        ang -= 90
    return -math.radians(ang)


def front_turn(frame: Frame, x: float, y: float) -> float:
    """Extra quarter turns so that the façade holding (x, y) ends at the bottom of the plan."""
    return {"bottom": 0.0, "top": math.pi, "left": math.pi / 2, "right": -math.pi / 2}[frame.side(x, y)]


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
