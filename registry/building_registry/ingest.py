"""Register an IFC: extract, check, store the IFC and its outputs, upsert the record. Idempotent.

    registry register ifc/dev/dev.ifc --building-id dev-r5-exercice --address "…" --exercise

- The extractor (seraph_ifc) runs and its checks must pass, or nothing is stored.
- The building id is the RNB id found at the address (via BAN), or the id given with --building-id (test
  buildings, or an address the RNB does not know). Exercise buildings at made-up addresses get no BAN/RNB link,
  so they can never shadow a real building.
- Same IFC + same extractor version + same ids.yaml as the stored model → « unchanged »: only the addresses are
  merged. Anything else re-extracts and replaces the stored files.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .address import id_kind
from .base import BuildingRegistry, RegistryError, merge_addresses, resolve_address
from .model import BuildingRecord, now_iso


class RegistrationRefused(RegistryError):
    def __init__(self, message: str, report: str = ""):
        super().__init__(message)
        self.report = report


@dataclass
class Registration:
    record: BuildingRecord
    status: str                 # created | updated | unchanged
    report: str


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def register(reg: BuildingRegistry, ifc: Path, addresses: list[str], *, building_id: Optional[str] = None,
             ids_path: Optional[Path] = None, exercise: bool = False, online: Optional[bool] = None,
             provenance: Optional[str] = None, provenance_fr: Optional[str] = None, name: Optional[str] = None,
             base_url: Optional[str] = None, actor: str = "registry-cli") -> Registration:
    from seraph_ifc import __version__ as extractor_version
    from seraph_ifc.extract import DEFAULT_BASE_URL, EXTRACTOR, extract, load_ids

    if not addresses:
        raise RegistryError("at least one --address is needed")
    online = reg.online if online is None else online
    ifc_bytes = ifc.read_bytes()
    ids_bytes = ids_path.read_bytes() if ids_path else b""

    # Addresses → keys, BAN ids, RNB candidates.
    refs, rnb = [], []
    for a in addresses:
        r, cands = resolve_address(a, online=online, link_ban=not exercise)
        refs += r
        rnb += [c for c in cands if c["rnb_id"] not in {x["rnb_id"] for x in rnb}]
    rnb_ids = [c["rnb_id"] for c in rnb]
    if building_id:
        kind = id_kind(building_id)
        if kind is None:
            raise RegistryError(f"bad building id {building_id!r}: an RNB id (12 chars, A-Z0-9) or a manual id "
                                f"(lowercase, digits, dashes)")
    elif rnb_ids:
        building_id, kind = rnb_ids[0], "rnb"
    else:
        raise RegistryError("no RNB building found at this address (offline, exercise, or unknown to the RNB): "
                            "pass --building-id <manual-id>")

    old = reg.get(building_id)
    for ref in refs:
        owner = reg.find_key(ref.key)
        if owner and owner != building_id:
            raise RegistryError(f"address {ref.label!r} already belongs to {owner}")

    same = (old is not None and old.model.get("ifc_sha256") == sha256(ifc_bytes)
            and old.model.get("extractor", {}).get("version") == extractor_version
            and old.model.get("ids_sha256") == (sha256(ids_bytes) if ids_bytes else None))
    if same:
        for ref in refs:
            reg.put_address(building_id, ref)
        reg._log(actor, "register", "ok", building_id, None, refs[0].key)
        return Registration(reg.get(building_id), "unchanged", "")

    result = extract(ifc, ids=load_ids(ids_path), base_url=base_url or DEFAULT_BASE_URL, provenance=provenance,
                     provenance_fr=provenance_fr, name=name)
    if not result.ok:
        reg._log(actor, "register", "error", building_id, None, refs[0].key)
        raise RegistrationRefused("checks failed: " + ", ".join(c.name for c in result.checks if not c.ok),
                                  result.report)

    b = result.building
    building_json = (json.dumps(b, ensure_ascii=False, indent=1) + "\n").encode("utf-8")
    files: dict[str, bytes] = {"building.json": building_json, "report.txt": result.report.encode("utf-8"),
                               "source.ifc": ifc_bytes}
    files.update({rel: svg.encode("utf-8") for rel, svg in result.svgs.items()})
    if ids_bytes:
        files["ids.yaml"] = ids_bytes
    now = now_iso()
    record = BuildingRecord(
        building_id=building_id, id_kind=kind, name=b["name"], provenance=b["model"]["provenance"],
        provenance_fr=b["model"]["provenance_fr"], exercise=exercise,
        addresses=merge_addresses(old.addresses if old else [], refs),
        rnb_ids=sorted(set((old.rnb_ids if old else []) + rnb_ids)),
        model={
            "extractor": {"name": EXTRACTOR, "version": extractor_version},
            "ifc_file": ifc.name, "ifc_sha256": sha256(ifc_bytes), "ifc_bytes": len(ifc_bytes),
            "ifc_schema": b["model"]["source_ifc"]["schema"],
            "ids_sha256": sha256(ids_bytes) if ids_bytes else None,
            "building_sha256": sha256(building_json),
            "stats": b["model"]["stats"], "checks": b["model"]["checks"],
            "levels": [lv["level"] for lv in b["levels"]],
            "files": sorted(files),
            **({"credit": b["model"]["source_ifc"]["credit"]} if b["model"]["source_ifc"].get("credit") else {}),
        },
        registered_at=old.registered_at if old else now, updated_at=now)
    reg.put(record, files)
    reg._log(actor, "register", "ok", building_id, None, refs[0].key)
    return Registration(record, "updated" if old else "created", result.report)


def copy_building(src: BuildingRegistry, dst: BuildingRegistry, building_id: str) -> None:
    """Copy one building (record + every file) from one backend to another, e.g. local → supabase."""
    record = src.get(building_id)
    if record is None:
        raise RegistryError(f"unknown building {building_id}")
    files = {rel: src.read_file(building_id, rel) for rel in record.model.get("files", [])}
    dst.put(record, files)
