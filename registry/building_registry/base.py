"""The one interface every backend implements. Seraph only ever talks to this.

    reg = open_registry()                                  # REGISTRY_BACKEND=local | supabase | fire_service
    rec = reg.lookup("2 rue Madame, 64000 Pau", incident_id="INC-0001", actor="seraph")
    if rec is None: ...                                    # « pas de maquette »: Seraph runs on Rosetta alone
    path = reg.model_path(rec.building_id, incident_id="INC-0001", actor="seraph")   # → …/building.json

How an address is resolved, in order:
1. its normalized form is a known key (exact match, offline, always tried first);
2. online only: the Base Adresse Nationale gives the official address id (BAN `cle_interop`), matched against the
   registered BAN ids; then the RNB gives the building ids at that address, matched against the registered RNB ids.
   A hit is cached as a new key, so the next lookup of that spelling is offline.
Anything else is a miss → None. Every lookup and every model read is written to the access log.
"""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Iterable, Optional

from .address import geocode, normalize, rnb_buildings
from .config import env, flag
from .model import AccessEntry, AddressRef, BuildingRecord, now_iso

MODEL_FILE = "building.json"


class RegistryError(Exception):
    pass


class ReadOnlyRegistry(RegistryError):
    """The backend is someone else's registry: we read it, we never write to it."""


class BuildingRegistry(ABC):
    name = "abstract"
    writable = True

    def __init__(self, online: Optional[bool] = None):
        self.online = (flag("REGISTRY_ONLINE", True) and not flag("MOCK", False)) if online is None else online

    # ───────── what a backend implements ─────────
    @abstractmethod
    def get(self, building_id: str) -> Optional[BuildingRecord]:
        """The record, without logging (internal and admin use)."""

    @abstractmethod
    def list(self) -> list[BuildingRecord]:
        ...

    @abstractmethod
    def find_key(self, key: str) -> Optional[str]:
        """building_id for a normalized address key."""

    @abstractmethod
    def find_ban(self, ban_id: str) -> Optional[str]:
        ...

    @abstractmethod
    def find_rnb(self, rnb_id: str) -> Optional[str]:
        ...

    @abstractmethod
    def read_file(self, building_id: str, rel: str) -> bytes:
        """A stored file of the building: building.json, levels/L3.svg, report.txt, source.ifc."""

    @abstractmethod
    def write_log(self, entry: AccessEntry) -> None:
        ...

    @abstractmethod
    def access_log(self, building_id: Optional[str] = None, incident_id: Optional[str] = None,
                   limit: int = 100) -> list[AccessEntry]:
        """Most recent first."""

    def put(self, record: BuildingRecord, files: dict[str, bytes]) -> None:
        """Create or replace a building: its record and all its files (written before the record)."""
        raise ReadOnlyRegistry(f"{self.name} registry is read-only")

    def put_address(self, building_id: str, address: AddressRef) -> None:
        raise ReadOnlyRegistry(f"{self.name} registry is read-only")

    def delete_address(self, building_id: str, key: str) -> bool:
        raise ReadOnlyRegistry(f"{self.name} registry is read-only")

    # ───────── the interface ─────────
    def lookup(self, address: str, *, incident_id: Optional[str] = None, actor: str = "seraph",
               online: Optional[bool] = None) -> Optional[BuildingRecord]:
        key = normalize(address)
        building_id = self.find_key(key) if key else None
        if building_id is None and key and (self.online if online is None else online):
            building_id = self._resolve_online(address, key)
        record = self.get(building_id) if building_id else None
        self._log(actor, "lookup", "hit" if record else "miss", building_id if record else None, incident_id, key)
        return record

    def get_model(self, building_id: str, *, incident_id: Optional[str] = None, actor: str = "seraph") -> dict:
        try:
            data = json.loads(self.read_file(building_id, MODEL_FILE).decode("utf-8"))
        except Exception:
            self._log(actor, "get_model", "error", building_id, incident_id, None)
            raise
        self._log(actor, "get_model", "ok", building_id, incident_id, None)
        return data

    def model_path(self, building_id: str, *, incident_id: Optional[str] = None, actor: str = "seraph",
                   dest: Optional[Path] = None) -> Path:
        """Local path of building.json with its level plans next to it (levels/L<n>.svg), as Seraph serves them
        at /building/files/. Remote backends download into a cache folder first."""
        folder = self.materialize(building_id, dest)
        self._log(actor, "get_model", "ok", building_id, incident_id, None)
        return folder / MODEL_FILE

    def materialize(self, building_id: str, dest: Optional[Path] = None) -> Path:
        record = self.get(building_id)
        if record is None:
            raise RegistryError(f"unknown building {building_id}")
        sha = (record.model.get("building_sha256") or "model")[:12]
        folder = dest or (cache_dir() / self.name / building_id / sha)
        if not (folder / MODEL_FILE).exists():
            tmp = folder.with_name(folder.name + ".part")
            for rel in record.model.get("files", []):
                if rel == "source.ifc":
                    continue
                p = tmp / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(self.read_file(building_id, rel))
            tmp.rename(folder) if not folder.exists() else None
        return folder

    def add_address(self, building_id: str, address: str, *, online: Optional[bool] = None,
                    link_ban: bool = True, actor: str = "registry-cli") -> list[AddressRef]:
        """Make one more address resolve to this building (e.g. the final demo address). Idempotent."""
        record = self.get(building_id)
        if record is None:
            raise RegistryError(f"unknown building {building_id}")
        refs = resolve_address(address, online=self.online if online is None else online, link_ban=link_ban)[0]
        for ref in refs:
            self.put_address(building_id, ref)
        self._log(actor, "add_address", "ok", building_id, None, refs[0].key)
        return refs

    def remove_address(self, building_id: str, address: str, *, actor: str = "registry-cli") -> bool:
        """Stop resolving this address to this building (re-addressed building, old test address). The building
        and its other addresses stay. → True if the address was there."""
        key = normalize(address)
        gone = self.delete_address(building_id, key)
        self._log(actor, "remove_address", "ok" if gone else "miss", building_id, None, key)
        return gone

    # ───────── helpers ─────────
    def _resolve_online(self, address: str, key: str) -> Optional[str]:
        ban = geocode(address)
        if ban is None:
            return None
        building_id = self.find_ban(ban.ban_id)
        if building_id is None:
            for b in rnb_buildings(ban.ban_id):
                building_id = self.find_rnb(b["rnb_id"])
                if building_id:
                    break
        if building_id and self.writable:
            try:   # cache the spelling: next time it resolves offline
                self.put_address(building_id, AddressRef(key=key, label=address, source="cache", ban_id=ban.ban_id,
                                                         ban_uuid=ban.ban_uuid, lat=ban.lat, lon=ban.lon))
            except RegistryError:
                pass
        return building_id

    def _log(self, actor: str, action: str, result: str, building_id: Optional[str], incident_id: Optional[str],
             query: Optional[str]) -> None:
        try:
            self.write_log(AccessEntry(at=now_iso(), actor=actor, action=action, result=result,
                                       building_id=building_id, incident_id=incident_id, query=query))
        except Exception:
            pass   # a log failure never blocks an intervention


def resolve_address(address: str, *, online: bool, link_ban: bool = True) -> tuple[list[AddressRef], list[dict]]:
    """Address as typed → the keys to store (as typed, plus BAN's official label) and the RNB candidates.
    With link_ban=False (exercise buildings at made-up addresses) nothing national is attached."""
    raw = AddressRef(key=normalize(address), label=address.strip(), source="manual")
    if not online or not link_ban:
        return [raw], []
    ban = geocode(address)
    if ban is None:
        return [raw], []
    raw.ban_id, raw.ban_uuid, raw.lat, raw.lon = ban.ban_id, ban.ban_uuid, ban.lat, ban.lon
    refs = [raw]
    official = AddressRef(key=normalize(ban.label), label=ban.label, source="ban", ban_id=ban.ban_id,
                          ban_uuid=ban.ban_uuid, lat=ban.lat, lon=ban.lon)
    if official.key != raw.key:
        refs.append(official)
    return refs, rnb_buildings(ban.ban_id)


def merge_addresses(old: Iterable[AddressRef], new: Iterable[AddressRef]) -> list[AddressRef]:
    out: dict[str, AddressRef] = {a.key: a for a in old}
    for a in new:
        out[a.key] = a
    return list(out.values())


def cache_dir() -> Path:
    from .config import REGISTRY_DIR
    return Path(env("REGISTRY_CACHE_DIR", str(REGISTRY_DIR / ".cache")))
