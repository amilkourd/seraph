"""One SVG plan per level, 1000×1000, the same frame as `rooms[].zone` (image_id `ifc-L<n>`).

Drawn like a French intervention plan (NF S 60-303, cancelled in 2013 and replaced by NF X 08-070; the conventions
below follow the public legends that reproduce it: Monaco fire brigade guide 2025, INRS ED 6230, Oise prefecture
example plan): white background, black walls cut 1.10 m above the floor, common corridors pale green, stairs darker
green with treads and the arrow going up, lifts as a white box with an X and « ASC », risk rooms as a yellow triangle
(lightning bolt = electrical room), fire doors in red with their rating, fire-service access as a red arrow, plan
oriented to the main access (E1 at the bottom), graphic scale bar, north arrow. Only what the IFC states is drawn."""
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


RED = "#d0021b"
YELLOW = "#ffd200"
GREEN_CORRIDOR = "#d1ff73"      # corridors (Monaco guide, RGB 209 255 115)
GREEN_STAIR = "#7dc95e"         # stairs, a darker green (Monaco uses 56 168 0; lighter here so treads stay legible)
OUTDOOR = "#e9e9e9"
WALL = "#111111"
PARTITION = "#555555"
ELECTRIC_RE = r"(électrique|electrique|tgbt|transfo)"
RISK_RE = r"(technique|chaufferie|électrique|electrique|tgbt|transfo)"


def _f(v: float) -> str:
    return f"{v:.1f}"


class _Pen:
    """World metres → SVG path data in the plan frame."""

    def __init__(self, frame: Frame):
        self.frame = frame

    def pt(self, x: float, y: float) -> str:
        px, py = self.frame.to_plan_f(x, y)
        return f"{_f(px)},{_f(py)}"

    def ring(self, coords) -> str:
        cs = list(coords)
        if len(cs) > 1 and cs[0] == cs[-1]:
            cs = cs[:-1]
        return "M" + " L".join(self.pt(x, y) for x, y in cs) + " Z"

    def poly(self, g) -> str:
        if g is None or g.is_empty:
            return ""
        parts = g.geoms if hasattr(g, "geoms") else [g]
        out = []
        for p in parts:
            if isinstance(p, Polygon):
                out.append(self.ring(p.exterior.coords))
                out += [self.ring(h.coords) for h in p.interiors]
            elif hasattr(p, "coords"):
                out.append("M" + " L".join(self.pt(x, y) for x, y in p.coords))
        return " ".join(out)

    def line(self, pts) -> str:
        return "M" + " L".join(self.pt(x, y) for x, y in pts)


def _zone_d(zone: list[list[int]]) -> str:
    return "M" + " L".join(f"{x},{y}" for x, y in zone) + " Z"


def _bbox(zone: list[list[int]]) -> tuple[int, int, int, int]:
    xs = [p[0] for p in zone]
    ys = [p[1] for p in zone]
    return min(xs), min(ys), max(xs), max(ys)


def _arrow_head(x0: float, y0: float, x1: float, y1: float, size: float) -> str:
    a = math.atan2(y1 - y0, x1 - x0)
    l = (x1 - size * math.cos(a - 0.45), y1 - size * math.sin(a - 0.45))
    r = (x1 - size * math.cos(a + 0.45), y1 - size * math.sin(a + 0.45))
    return f"M{_f(x1)},{_f(y1)} L{_f(l[0])},{_f(l[1])} L{_f(r[0])},{_f(r[1])} Z"


def _risk_triangle(cx: float, cy: float, size: float, electric: bool) -> list[str]:
    h = size * 0.87
    out = [f'<path d="M{_f(cx)},{_f(cy - h / 2)} L{_f(cx + size / 2)},{_f(cy + h / 2)} L{_f(cx - size / 2)},'
           f'{_f(cy + h / 2)} Z" fill="{YELLOW}" stroke="#000" stroke-width="2.5" stroke-linejoin="round"/>']
    if electric:   # lightning bolt
        s = size / 30
        pts = [(1, -9), (-5, 3), (0, 3), (-2, 11), (5, -2), (0, -2), (3, -9)]
        out.append('<path d="M' + " L".join(f"{_f(cx + x * s)},{_f(cy + 2 * s + y * s)}" for x, y in pts) +
                   ' Z" fill="#000"/>')
    return out


def _ladder(cx: float, cy: float, size: float) -> list[str]:
    w, h = size * 0.45, size
    out = [f'<g stroke="{RED}" stroke-width="2.5" stroke-linecap="round">',
           f'<line x1="{_f(cx - w / 2)}" y1="{_f(cy - h / 2)}" x2="{_f(cx - w / 2)}" y2="{_f(cy + h / 2)}"/>',
           f'<line x1="{_f(cx + w / 2)}" y1="{_f(cy - h / 2)}" x2="{_f(cx + w / 2)}" y2="{_f(cy + h / 2)}"/>']
    for k in range(4):
        y = cy - h / 2 + h * (k + 0.5) / 4
        out.append(f'<line x1="{_f(cx - w / 2)}" y1="{_f(y)}" x2="{_f(cx + w / 2)}" y2="{_f(y)}"/>')
    out.append("</g>")
    return out


def _sawtooth(p, q, teeth: int = 6, amp: float = 4.0) -> str:
    (x0, y0), (x1, y1) = p, q
    dx, dy = x1 - x0, y1 - y0
    n = math.hypot(dx, dy) or 1
    nx, ny = -dy / n * amp, dx / n * amp
    pts = []
    for k in range(teeth * 2 + 1):
        t = k / (teeth * 2)
        sgn = 0 if k in (0, teeth * 2) else (1 if k % 2 else -1)
        pts.append(f"{_f(x0 + dx * t + nx * sgn)},{_f(y0 + dy * t + ny * sgn)}")
    return "M" + " L".join(pts)


def level_svg(level: dict[str, Any], frame: Frame, rooms: list[dict], stairs: list[dict], doors: list[dict],
              entrances: list[dict], drawing: Any = None, outline: Optional[list] = None,
              ladders: Optional[list[str]] = None, north: Optional[tuple[float, float]] = None) -> str:
    """The level's plan. `drawing` (seraph_ifc.drawing.LevelDrawing) and `outline` (slab polygons) are in world
    metres; zones, door and entrance points are already in the 0–1000 frame."""
    n = level["level"]
    pen = _Pen(frame)
    o: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {SIZE} {SIZE}" width="{SIZE}" height="{SIZE}" '
        f'font-family="Arial, Helvetica, sans-serif">',
        f'<!-- Seraph · plan {escape(level["label"])} (level {n}) from the IFC · cut 1.10 m above the floor · '
        f'0–1000 frame = rooms[].zone, image_id ifc-L{n} -->',
        f'<rect width="{SIZE}" height="{SIZE}" fill="#fff"/>']

    # Slab: the floor plate as built (balconies, holes).
    if outline:
        o.append(f'<path d="{" ".join(pen.poly(p) for p in outline)}" fill="#f4f4f4" fill-rule="evenodd" '
                 f'stroke="#9a9a9a" stroke-width="1.5"/>')

    # Spaces: rooms white, common corridor pale green, outdoor grey.
    o.append('<g stroke="none">')
    for r in rooms:
        if not r.get("zone"):
            continue
        kind = r.get("kind")
        fill = GREEN_CORRIDOR if kind == "corridor" else OUTDOOR if kind == "exterior" else "#ffffff"
        o.append(f'<path d="{_zone_d(r["zone"])}" fill="{fill}"/>')
    for s in stairs:
        for z in s.get("zones", []):
            if z["level"] == n:
                o.append(f'<path d="{_zone_d(z["zone"])}" fill="{GREEN_STAIR}"/>')
    o.append("</g>")

    if drawing is not None:
        # Ramps: outline + arrow up the slope.
        for r in drawing.ramps:
            o.append(f'<path d="{pen.poly(r["outline"])}" fill="none" stroke="#000" stroke-width="1.2"/>')
            (ax, ay), (bx, by) = [frame.to_plan_f(*p) for p in r["arrow"]]
            o.append(f'<path d="M{_f(ax)},{_f(ay)} L{_f(bx)},{_f(by)}" stroke="#000" stroke-width="2.2"/>')
            o.append(f'<path d="{_arrow_head(ax, ay, bx, by, 14)}" fill="#000"/>')
            o.append(f'<text x="{_f((ax + bx) / 2)}" y="{_f((ay + by) / 2 - 10)}" font-size="16" '
                     f'text-anchor="middle" paint-order="stroke" stroke="#fff" stroke-width="4">'
                     f'Rampe {str(r["slope_pct"]).replace(".", ",")} %</text>')
        # Stairs: treads (dashed above the cut), walking line with the arrow towards the top.
        for st in drawing.stairs:
            if st["below"]:
                o.append(f'<path d="{" ".join(pen.poly(g) for g in st["below"])}" fill="none" stroke="#000" '
                         f'stroke-width="1.2"/>')
            if st["above"]:
                o.append(f'<path d="{" ".join(pen.poly(g) for g in st["above"])}" fill="none" stroke="#000" '
                         f'stroke-width="0.8" stroke-dasharray="5 4"/>')
            if len(st["path"]) >= 2:
                pts = [frame.to_plan_f(*p) for p in st["path"]]
                o.append(f'<path d="M{" L".join(_f(x) + "," + _f(y) for x, y in pts)}" fill="none" stroke="#000" '
                         f'stroke-width="1.8"/>')
                o.append(f'<circle cx="{_f(pts[0][0])}" cy="{_f(pts[0][1])}" r="4.5" fill="#000"/>')
                o.append(f'<path d="{_arrow_head(*pts[-2], *pts[-1], 14)}" fill="#000"/>')
        # Shafts: outline and an X.
        for sh in drawing.shafts:
            o.append(f'<path d="{pen.poly(sh)}" fill="#fff" stroke="#000" stroke-width="1.2"/>')
            x0, y0, x1, y1 = sh.bounds
            o.append(f'<path d="{pen.line([(x0, y0), (x1, y1)])} {pen.line([(x0, y1), (x1, y0)])}" '
                     f'stroke="#000" stroke-width="0.8"/>')
        # Railings, windows, walls, columns.
        if drawing.railings:
            o.append(f'<path d="{" ".join(pen.poly(g) for g in drawing.railings)}" fill="#000" stroke="#000" '
                     f'stroke-width="0.8"/>')
        for g in drawing.windows:   # window: white in the wall, frame outline, a glass line along its length
            o.append(f'<path d="{pen.poly(g)}" fill="#fff" stroke="#000" stroke-width="1.3" fill-rule="evenodd"/>')
            r = g.minimum_rotated_rectangle
            if r.geom_type == "Polygon":
                c = list(r.exterior.coords)[:4]
                e = sorted(((c[i], c[(i + 1) % 4]) for i in range(4)),
                           key=lambda ab: -math.hypot(ab[1][0] - ab[0][0], ab[1][1] - ab[0][1]))
                (a0, a1), (b0, b1) = e[0], e[1]
                m0 = ((a0[0] + b1[0]) / 2, (a0[1] + b1[1]) / 2)
                m1 = ((a1[0] + b0[0]) / 2, (a1[1] + b0[1]) / 2)
                o.append(f'<path d="{pen.line([m0, m1])}" stroke="#000" stroke-width="1.1"/>')
        # One union per class: overlapping layers and corners must not cancel out (even-odd).
        heavy = unary_union([g.buffer(0.002, join_style="mitre") for g, c in drawing.walls if c != "partition"])
        light = unary_union([g.buffer(0.002, join_style="mitre") for g, c in drawing.walls if c == "partition"])
        if not light.is_empty and not heavy.is_empty:
            light = light.difference(heavy)
        if not heavy.is_empty:
            o.append(f'<path d="{pen.poly(heavy)}" fill="{WALL}" fill-rule="evenodd"/>')
        if not light.is_empty:
            o.append(f'<path d="{pen.poly(light)}" fill="{PARTITION}" fill-rule="evenodd"/>')
        if drawing.columns:
            o.append(f'<path d="{" ".join(pen.poly(g) for g in drawing.columns)}" fill="{WALL}"/>')
        # Doors: leaf + swing; fire doors: red sawtooth on the opening + their rating.
        for d in drawing.doors:
            for leaf in d["leaves"]:
                o.append(f'<path d="{pen.line(leaf)}" stroke="#000" stroke-width="1.6"/>')
            for arc in d["arcs"]:
                o.append(f'<path d="{pen.line(arc)}" fill="none" stroke="#000" stroke-width="0.9"/>')
            for sl in d["slides"]:
                o.append(f'<path d="{pen.line(sl)}" stroke="#000" stroke-width="2.6"/>')
            if d.get("fire_rating") and d.get("jamb"):
                p, q = [frame.to_plan_f(*x) for x in d["jamb"]]
                o.append(f'<path d="{_sawtooth(p, q)}" fill="none" stroke="{RED}" stroke-width="2"/>')

    # Lifts: white box with an X and ASC.
    for r in rooms:
        if r.get("kind") == "elevator" and r.get("zone"):
            x0, y0, x1, y1 = _bbox(r["zone"])
            o.append(f'<path d="{_zone_d(r["zone"])}" fill="#fff" stroke="#000" stroke-width="1.6"/>')
            o.append(f'<path d="M{x0},{y0} L{x1},{y1} M{x0},{y1} L{x1},{y0}" stroke="#000" stroke-width="1.2"/>')

    # Labels (room ids and names, ESC) first; symbols are then placed where they hit no label.
    taken: list[tuple[float, float, float, float]] = []

    def free(box: tuple[float, float, float, float]) -> bool:
        x0, y0, x1, y1 = box
        return all(x1 <= a or x0 >= c or y1 <= b or y0 >= d for a, b, c, d in taken)

    def text_box(x: float, y: float, text: str, size: float) -> tuple[float, float, float, float]:
        w = 0.6 * size * len(text)
        return x - w / 2, y - size * 0.8, x + w / 2, y + size * 0.25

    o.append('<g fill="#000" text-anchor="middle" paint-order="stroke" stroke="#fff" stroke-width="5" '
             'stroke-linejoin="round">')
    for r in rooms:
        if not r.get("zone"):
            continue
        cx, cy = _centre(r["zone"])
        rid = str(r["id"])
        kind = r.get("kind")
        if kind == "elevator":
            size = _font(r["zone"], "ASC", 22)
            o.append(f'<text x="{_f(cx)}" y="{_f(cy + size / 3)}" font-size="{size}" font-weight="bold">ASC</text>')
            taken.append(text_box(cx, cy + size / 3, "ASC", size))
            continue
        if rid.startswith("corridor:"):
            continue
        name = r["label"][len(rid):].strip() if r["label"].startswith(rid) else ""
        size = _font(r["zone"], rid, 24)
        x0, y0, x1, y1 = _bbox(r["zone"])
        two_lines = name and (y1 - y0) > 3.2 * size and (x1 - x0) > 0.5 * 15 * len(name)
        dy = -size * 0.35 if two_lines else size / 3
        o.append(f'<text x="{_f(cx)}" y="{_f(cy + dy)}" font-size="{size}" font-weight="bold">{escape(rid)}</text>')
        taken.append(text_box(cx, cy + dy, rid, size))
        if two_lines:
            o.append(f'<text x="{_f(cx)}" y="{_f(cy + dy + size * 0.95)}" font-size="15">{escape(name)}</text>')
            taken.append(text_box(cx, cy + dy + size * 0.95, name, 15))
    for s in stairs:
        for z in s.get("zones", []):
            if z["level"] == n:
                x0, y0, x1, y1 = _bbox(z["zone"])
                cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
                o.append(f'<text x="{_f(cx)}" y="{_f(cy + 9)}" font-size="26" font-weight="bold">'
                         f'ESC {escape(s["id"])}</text>')
                taken.append(text_box(cx, cy + 9, f"ESC {s['id']}", 26))
    o.append("</g>")

    import re as _re

    def place(cands: list[tuple[float, float]], w: float, h: float) -> tuple[float, float]:
        """First candidate centre whose box is free (else the first), then mark it taken."""
        for cx, cy in cands:
            box = (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)
            if free(box) and 0 <= box[0] and box[2] <= SIZE and 0 <= box[1] and box[3] <= SIZE:
                taken.append(box)
                return cx, cy
        cx, cy = cands[0]
        taken.append((cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2))
        return cx, cy

    # Risk rooms: yellow triangle (lightning bolt for electrical rooms), inside the room, clear of its label.
    for r in rooms:
        lab = r.get("label", "")
        if r.get("zone") and _re.search(RISK_RE, lab, _re.I):
            x0, y0, x1, y1 = _bbox(r["zone"])
            size = max(22, min(34, (x1 - x0) * 0.42, (y1 - y0) * 0.42))
            m = size * 0.65
            cands = [(x0 + m, y0 + m), (x1 - m, y0 + m), (x0 + m, y1 - m), (x1 - m, y1 - m),
                     ((x0 + x1) / 2, y0 + m), ((x0 + x1) / 2, y1 - m), (x0 - m, y0 + m), (x1 + m, y0 + m)]
            cx, cy = place(cands, size, size * 0.9)
            o += _risk_triangle(cx, cy, size, bool(_re.search(ELECTRIC_RE, lab, _re.I)))
    # Ladder rescue points (balconies, terraces above ground): on the edge away from the building.
    bx0, by0, bx1, by1 = (min(_bbox(r["zone"])[0] for r in rooms if r.get("zone")),
                          min(_bbox(r["zone"])[1] for r in rooms if r.get("zone")),
                          max(_bbox(r["zone"])[2] for r in rooms if r.get("zone")),
                          max(_bbox(r["zone"])[3] for r in rooms if r.get("zone"))) if rooms else (0, 0, SIZE, SIZE)
    mcx, mcy = (bx0 + bx1) / 2, (by0 + by1) / 2
    for node in ladders or []:
        rid = node.split(":", 1)[1]
        r = next((x for x in rooms if str(x["id"]) == rid and x.get("zone")), None)
        if not r:
            continue
        x0, y0, x1, y1 = _bbox(r["zone"])
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        h = max(18, min(28, (y1 - y0) * 0.7, (x1 - x0) * 0.9))
        dx, dy = cx - mcx, cy - mcy
        ends = [(x0 + h * 0.5, cy), (x1 - h * 0.5, cy)] if (x1 - x0) >= (y1 - y0) else \
            [(cx, y0 + h * 0.6), (cx, y1 - h * 0.6)]          # the two ends of a narrow balcony
        if abs(dx) * (by1 - by0) >= abs(dy) * (bx1 - bx0):
            ex = x1 - h * 0.45 if dx > 0 else x0 + h * 0.45
            cands = [(ex, cy), (ex, cy - h), (ex, cy + h)] + ends + [(cx, cy)]
        else:
            ey = y1 - h * 0.6 if dy > 0 else y0 + h * 0.6
            cands = [(cx, ey), (cx - h, ey), (cx + h, ey)] + ends + [(cx, cy)]
        lx, ly = place(cands, h * 0.6, h)
        o += _ladder(lx, ly, h)
    # Fire-door ratings, next to the door, clear of labels and symbols.
    for d in doors:
        fr = d.get("fire_rating")
        p = d.get("plan_point")
        if fr and p and d["level"] == n:
            short = _re.sub(r"^(EI2?\s*\d+).*$", r"\1", fr)
            w, h = 0.62 * 12 * len(short), 12
            x, y = p["x"], p["y"]
            cands = [(x + w / 2 + 6, y - 9), (x - w / 2 - 6, y - 9), (x + w / 2 + 6, y + 13), (x - w / 2 - 6, y + 13),
                     (x, y - 17), (x, y + 19)]
            tx, ty = place(cands, w, h)
            o.append(f'<text x="{_f(tx)}" y="{_f(ty + 4.5)}" font-size="12" font-weight="bold" fill="{RED}" '
                     f'text-anchor="middle" paint-order="stroke" stroke="#fff" stroke-width="3">{escape(short)}</text>')
    # Fire-service access: red block arrow (E1, main), red disc + arrow (others).
    for e in entrances:
        p = e.get("plan_point")
        if not p or e.get("level") != n:
            continue
        door = next((d for d in doors if d["id"] == e["id"] and d.get("plan_point")), None)
        tx, ty = (door["plan_point"]["x"], door["plan_point"]["y"]) if door else (SIZE / 2, SIZE / 2)
        a = math.atan2(ty - p["y"], tx - p["x"])
        ux, uy = math.cos(a), math.sin(a)
        if e["id"] == "E1":
            L, W = 64, 30
            bx, by = p["x"] - ux * 26, p["y"] - uy * 26            # tail, outside
            hx, hy = bx + ux * L, by + uy * L                        # tip, at the door
            nx, ny = -uy, ux
            pts = [(bx + nx * W / 2, by + ny * W / 2), (bx + ux * (L - 22) + nx * W / 2, by + uy * (L - 22) + ny * W / 2),
                   (bx + ux * (L - 22) + nx * W, by + uy * (L - 22) + ny * W), (hx, hy),
                   (bx + ux * (L - 22) - nx * W, by + uy * (L - 22) - ny * W),
                   (bx + ux * (L - 22) - nx * W / 2, by + uy * (L - 22) - ny * W / 2),
                   (bx - nx * W / 2, by - ny * W / 2)]
            o.append('<path d="M' + " L".join(f"{_f(x)},{_f(y)}" for x, y in pts) + f' Z" fill="{RED}"/>')
            o.append(f'<text x="{_f(bx + ux * 18)}" y="{_f(by + uy * 18 + 7)}" font-size="20" font-weight="bold" '
                     f'fill="#fff" text-anchor="middle">E1</text>')
        else:
            cx, cy = p["x"] - ux * 14, p["y"] - uy * 14
            o.append(f'<circle cx="{_f(cx)}" cy="{_f(cy)}" r="17" fill="{RED}"/>')
            o.append(f'<path d="{_arrow_head(cx, cy, cx + ux * 30, cy + uy * 30, 12)}" fill="{RED}"/>')
            o.append(f'<text x="{_f(cx)}" y="{_f(cy + 6)}" font-size="16" font-weight="bold" fill="#fff" '
                     f'text-anchor="middle">{escape(e["id"])}</text>')

    # Level, north arrow, graphic scale.
    o.append(f'<text x="40" y="72" font-size="48" font-weight="bold" fill="#000">{escape(level["label"])}</text>')
    nx_, ny_ = north or (0.0, 1.0)
    c, s_ = math.cos(frame.theta), math.sin(frame.theta)
    vx, vy = c * nx_ - s_ * ny_, -(s_ * nx_ + c * ny_)        # turned, then y down
    vn = math.hypot(vx, vy) or 1
    vx, vy = vx / vn, vy / vn
    cx, cy = 930, 70
    o.append(f'<circle cx="{cx}" cy="{cy}" r="26" fill="#fff" stroke="#000" stroke-width="1.5"/>')
    o.append(f'<path d="{_arrow_head(cx - vx * 18, cy - vy * 18, cx + vx * 20, cy + vy * 20, 16)}" fill="#000"/>')
    o.append(f'<path d="M{_f(cx - vx * 18)},{_f(cy - vy * 18)} L{_f(cx + vx * 8)},{_f(cy + vy * 8)}" stroke="#000" '
             f'stroke-width="2.5"/>')
    o.append(f'<text x="{_f(cx + vx * 42)}" y="{_f(cy + vy * 42 + 7)}" font-size="20" font-weight="bold" '
             f'text-anchor="middle">N</text>')
    metres = next(m for m in (1, 2, 5, 10, 20, 50) if m * frame.scale >= 110)
    bar = metres * frame.scale
    x0, y0 = SIZE - 40 - bar, SIZE - 34
    o.append(f'<g stroke="#000" stroke-width="2"><line x1="{_f(x0)}" y1="{y0}" x2="{_f(x0 + bar)}" y2="{y0}"/>'
             f'<line x1="{_f(x0)}" y1="{y0 - 7}" x2="{_f(x0)}" y2="{y0 + 7}"/>'
             f'<line x1="{_f(x0 + bar)}" y1="{y0 - 7}" x2="{_f(x0 + bar)}" y2="{y0 + 7}"/></g>')
    o.append(f'<text x="{_f(x0 + bar / 2)}" y="{y0 - 12}" font-size="17" text-anchor="middle">{metres} m</text>')
    o.append("</svg>")
    return "\n".join(o) + "\n"
