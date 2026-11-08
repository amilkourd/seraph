"""Seraph building registry: an address in, the building's model out.

    from building_registry import open_registry
    reg = open_registry()                       # REGISTRY_BACKEND = local (default) | supabase | fire_service
    rec = reg.lookup(address, incident_id="INC-0001", actor="seraph")      # BuildingRecord | None
    path = reg.model_path(rec.building_id, incident_id="INC-0001")         # …/building.json (+ levels/*.svg)
"""
from __future__ import annotations

from typing import Optional

from .address import normalize
from .base import BuildingRegistry, ReadOnlyRegistry, RegistryError
from .config import env
from .model import AccessEntry, AddressRef, BuildingRecord

__version__ = "1.0.0"
BACKENDS = ("local", "supabase", "fire_service")


def open_registry(backend: Optional[str] = None, **kwargs) -> BuildingRegistry:
    """The registry chosen by REGISTRY_BACKEND (or `backend`). The local one needs no network and no extra package."""
    name = (backend or env("REGISTRY_BACKEND", "local")).strip().lower()
    if name == "local":
        from .backends.local import LocalRegistry
        return LocalRegistry(**kwargs)
    if name == "supabase":
        from .backends.supabase import SupabaseRegistry
        return SupabaseRegistry(**kwargs)
    if name in ("fire_service", "fire-service", "sdis"):
        from .backends.fire_service import FireServiceRegistry
        return FireServiceRegistry(**kwargs)
    raise RegistryError(f"unknown REGISTRY_BACKEND {name!r} (expected one of {', '.join(BACKENDS)})")


__all__ = ["open_registry", "BuildingRegistry", "BuildingRecord", "AddressRef", "AccessEntry", "RegistryError",
           "ReadOnlyRegistry", "normalize", "BACKENDS"]
