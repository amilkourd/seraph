"""Geometry from any IFC, in world coordinates and metres (the geometry engine converts units)."""
from __future__ import annotations

import multiprocessing
from dataclasses import dataclass

import numpy as np
from shapely.geometry import MultiPolygon, Polygon
from shapely.ops import unary_union

import ifcopenshell
import ifcopenshell.geom


@dataclass
class Shape:
    footprint: Polygon | MultiPolygon | None   # plan projection (x, y)
    zmin: float
    zmax: float
    center: tuple[float, float]                # bbox centre in plan


def shapes(f: ifcopenshell.file, elements: list) -> dict[int, Shape]:
    """id → Shape for every element that has a body. Elements without geometry are left out."""
    out: dict[int, Shape] = {}
    if not elements:
        return out
    s = ifcopenshell.geom.settings()
    s.set("use-world-coords", True)
    it = ifcopenshell.geom.iterator(s, f, max(1, multiprocessing.cpu_count() - 1), include=elements)
    if not it.initialize():
        return out
    while True:
        sh = it.get()
        v = np.array(sh.geometry.verts, dtype=float).reshape(-1, 3)
        faces = np.array(sh.geometry.faces, dtype=int).reshape(-1, 3)
        if len(v):
            lo, hi = v.min(axis=0), v.max(axis=0)
            out[sh.id] = Shape(footprint=_project(v, faces), zmin=float(lo[2]), zmax=float(hi[2]),
                               center=(float(lo[0] + hi[0]) / 2, float(lo[1] + hi[1]) / 2))
        if not it.next():
            break
    return out


def _project(v: np.ndarray, faces: np.ndarray) -> Polygon | MultiPolygon | None:
    tris = []
    for a, b, c in faces:
        p = Polygon([v[a, :2], v[b, :2], v[c, :2]])
        if p.is_valid and p.area > 1e-6:
            tris.append(p)
    if not tris:
        return None
    g = unary_union(tris).buffer(0.005, join_style="mitre").buffer(-0.005, join_style="mitre")
    g = g.simplify(0.01, preserve_topology=True)
    return g if not g.is_empty else None


def main_polygon(g) -> Polygon | None:
    if g is None or g.is_empty:
        return None
    if isinstance(g, Polygon):
        return g
    return max(g.geoms, key=lambda p: p.area)
