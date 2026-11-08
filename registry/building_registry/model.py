"""What the registry stores. Plain dataclasses ↔ JSON, the same shape in every backend."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


@dataclass
class AddressRef:
    key: str                          # normalize(label): the offline lookup key
    label: str                        # as registered, or BAN's official label
    source: str = "manual"            # ban | manual | cache
    ban_id: Optional[str] = None      # BAN cle_interop, e.g. 75109_6358_00009
    ban_uuid: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "AddressRef":
        return cls(**{k: d.get(k) for k in cls.__dataclass_fields__ if k in d})


@dataclass
class BuildingRecord:
    building_id: str                  # RNB id (national, stable) or a manual id for test buildings
    id_kind: str                      # rnb | manual
    name: str
    provenance: str                   # architect | rebuilt_from_posted_plan | fictional
    provenance_fr: str                # shown on every screen
    exercise: bool = False            # « exercice »: test or demo entry, never a real intervention
    addresses: list[AddressRef] = field(default_factory=list)
    rnb_ids: list[str] = field(default_factory=list)
    model: dict[str, Any] = field(default_factory=dict)   # extractor, versions, hashes, stats, checks, files
    registered_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "BuildingRecord":
        d = dict(d)
        d["addresses"] = [AddressRef.from_dict(a) for a in d.get("addresses") or []]
        return cls(**{k: d[k] for k in cls.__dataclass_fields__ if k in d})


@dataclass
class AccessEntry:
    at: str
    actor: str                        # who read: « seraph », « registry-cli », a user id in production
    action: str                       # lookup | get_model | register | add_address
    result: str                       # hit | miss | ok | error
    building_id: Optional[str] = None
    incident_id: Optional[str] = None
    query: Optional[str] = None       # the normalized address asked for

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "AccessEntry":
        return cls(**{k: d.get(k) for k in cls.__dataclass_fields__})
