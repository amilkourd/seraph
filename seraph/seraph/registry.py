"""Where Seraph gets a building model. One interface; the local backend reads BUILDING_JSON.
Production swaps in the fire service's registry. `lookup` returning None = « pas de maquette »: Seraph runs on
Rosetta (maps.building, plan.read) alone."""
from __future__ import annotations

from pathlib import Path
from typing import Optional, Protocol

from . import building as B
from .config import building_json
from .models import Building


class BuildingRegistry(Protocol):
    def lookup(self, address: str) -> Optional[B.BuildingKit]: ...


class LocalRegistry:
    """Demo backend: one building file (BUILDING_JSON, else the dev fixture) answers for every address."""

    def __init__(self, path: Optional[Path] = None):
        self.path = path

    def lookup(self, address: str) -> Optional[B.BuildingKit]:
        path = self.path or building_json()
        if not path.exists():
            return None
        return B.load(path)


class NoBuildingRegistry:
    def lookup(self, address: str) -> Optional[B.BuildingKit]:
        return None


def empty_kit() -> B.BuildingKit:
    return B.BuildingKit(building=Building(name="Pas de maquette"), path=Path(""), files_dir=Path(""))
