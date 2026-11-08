"""Where Seraph gets a building model. One interface, three backends:
- RegistryBacked: the building registry (`registry/`, REGISTRY_BACKEND=local|supabase|fire_service). Default.
  Every lookup and model read lands in the registry's access log with the incident id.
- LocalRegistry: one file (BUILDING_JSON, else the dev fixture) for every address. Tests, and fallback.
- NoBuildingRegistry.
`lookup` returning None = « pas de maquette »: Seraph runs on Rosetta (maps.building, plan.read) alone."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional, Protocol

from . import building as B
from .config import REPO, building_json, env
from .models import Building


class BuildingRegistry(Protocol):
    def lookup(self, address: str, incident_id: Optional[str] = None) -> Optional[B.BuildingKit]: ...


class LocalRegistry:
    """One building file (BUILDING_JSON, else the dev fixture) answers for every address."""

    def __init__(self, path: Optional[Path] = None):
        self.path = path

    def lookup(self, address: str, incident_id: Optional[str] = None) -> Optional[B.BuildingKit]:
        path = self.path or building_json()
        if not path.exists():
            return None
        return B.load(path)


class NoBuildingRegistry:
    def lookup(self, address: str, incident_id: Optional[str] = None) -> Optional[B.BuildingKit]:
        return None


class RegistryBacked:
    def __init__(self) -> None:
        try:
            from building_registry import open_registry
        except ImportError:
            sys.path.insert(0, str(REPO / "registry"))
            from building_registry import open_registry
        self.reg = open_registry()
        self.last: Optional[object] = None

    def lookup(self, address: str, incident_id: Optional[str] = None) -> Optional[B.BuildingKit]:
        rec = self.reg.lookup(address, incident_id=incident_id, actor="seraph")
        self.last = rec
        if rec is None:
            return None
        return B.load(Path(self.reg.model_path(rec.building_id, incident_id=incident_id, actor="seraph")))


def default_registry() -> BuildingRegistry:
    """SERAPH_REGISTRY=registry (default) | file. The registry failing to open falls back to the file, visibly."""
    if env("SERAPH_REGISTRY", "registry") == "file":
        return LocalRegistry()
    try:
        return RegistryBacked()
    except Exception as e:
        print(f"building registry unavailable ({type(e).__name__}: {e}); using BUILDING_JSON")
        return LocalRegistry()


def empty_kit() -> B.BuildingKit:
    return B.BuildingKit(building=Building(name="Pas de maquette"), path=Path(""), files_dir=Path(""))
