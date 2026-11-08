"""Local backend: a folder. Default, offline, what the demo runs on (no venue Wi-Fi needed).

    registry/data/
      index.json                       every BuildingRecord (addresses included), one JSON file
      buildings/<building_id>/         building.json, levels/L<n>.svg, report.txt, source.ifc, ids.yaml
      access.log.jsonl                 who read which building, when, for which incident (append-only, not in git)
"""
from __future__ import annotations

import fcntl
import json
import os
import shutil
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

from ..base import BuildingRegistry, RegistryError
from ..config import REGISTRY_DIR, env
from ..model import AccessEntry, AddressRef, BuildingRecord, now_iso

FORMAT = 1


class LocalRegistry(BuildingRegistry):
    name = "local"

    def __init__(self, root: Optional[Path] = None, online: Optional[bool] = None):
        super().__init__(online)
        self.root = Path(root or env("REGISTRY_DIR", str(REGISTRY_DIR / "data")))
        self.root.mkdir(parents=True, exist_ok=True)

    # ───────── storage ─────────
    @property
    def index_path(self) -> Path:
        return self.root / "index.json"

    def _read(self) -> dict:
        if not self.index_path.exists():
            return {"format": FORMAT, "buildings": {}}
        return json.loads(self.index_path.read_text(encoding="utf-8"))

    def _write(self, data: dict) -> None:
        tmp = self.index_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(tmp, self.index_path)

    @contextmanager
    def _locked(self):
        with open(self.root / ".lock", "w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def _records(self) -> dict[str, BuildingRecord]:
        return {k: BuildingRecord.from_dict(v) for k, v in self._read().get("buildings", {}).items()}

    def folder(self, building_id: str) -> Path:
        p = (self.root / "buildings" / building_id).resolve()
        if (self.root / "buildings").resolve() not in p.parents:
            raise RegistryError(f"bad building id {building_id!r}")
        return p

    # ───────── reads ─────────
    def get(self, building_id: str) -> Optional[BuildingRecord]:
        return self._records().get(building_id)

    def list(self) -> list[BuildingRecord]:
        return sorted(self._records().values(), key=lambda r: r.building_id)

    def find_key(self, key: str) -> Optional[str]:
        for r in self._records().values():
            if any(a.key == key for a in r.addresses):
                return r.building_id
        return None

    def find_ban(self, ban_id: str) -> Optional[str]:
        for r in self._records().values():
            if any(a.ban_id == ban_id for a in r.addresses):
                return r.building_id
        return None

    def find_rnb(self, rnb_id: str) -> Optional[str]:
        for r in self._records().values():
            if rnb_id == r.building_id or rnb_id in r.rnb_ids:
                return r.building_id
        return None

    def read_file(self, building_id: str, rel: str) -> bytes:
        p = (self.folder(building_id) / rel).resolve()
        if self.folder(building_id) not in p.parents:
            raise RegistryError(f"bad path {rel!r}")
        return p.read_bytes()

    def materialize(self, building_id: str, dest: Optional[Path] = None) -> Path:
        if dest is None:   # the stored folder is already a ready-to-serve folder
            if self.get(building_id) is None:
                raise RegistryError(f"unknown building {building_id}")
            return self.folder(building_id)
        return super().materialize(building_id, dest)

    # ───────── writes ─────────
    def put(self, record: BuildingRecord, files: dict[str, bytes]) -> None:
        with self._locked():
            folder = self.folder(record.building_id)
            tmp = folder.with_name(folder.name + ".new")
            shutil.rmtree(tmp, ignore_errors=True)
            for rel, data in files.items():
                p = tmp / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(data)
            old = folder.with_name(folder.name + ".old")
            shutil.rmtree(old, ignore_errors=True)
            if folder.exists():
                folder.rename(old)
            tmp.rename(folder)
            shutil.rmtree(old, ignore_errors=True)
            data = self._read()
            data["format"] = FORMAT
            data.setdefault("buildings", {})[record.building_id] = record.to_dict()
            self._write(data)

    def put_address(self, building_id: str, address: AddressRef) -> None:
        with self._locked():
            data = self._read()
            rec = data.get("buildings", {}).get(building_id)
            if rec is None:
                raise RegistryError(f"unknown building {building_id}")
            for other_id, other in data["buildings"].items():
                if other_id != building_id and any(a["key"] == address.key for a in other.get("addresses", [])):
                    raise RegistryError(f"address {address.label!r} already belongs to {other_id}")
            addrs = [a for a in rec.get("addresses", []) if a["key"] != address.key]
            addrs.append(AddressRef.from_dict(address.__dict__).__dict__)
            rec["addresses"] = addrs
            rec["updated_at"] = now_iso()
            self._write(data)

    def delete(self, building_id: str) -> None:
        with self._locked():
            data = self._read()
            data.get("buildings", {}).pop(building_id, None)
            self._write(data)
            shutil.rmtree(self.folder(building_id), ignore_errors=True)

    # ───────── access log ─────────
    @property
    def log_path(self) -> Path:
        return self.root / "access.log.jsonl"

    def write_log(self, entry: AccessEntry) -> None:
        with open(self.log_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")

    def access_log(self, building_id: Optional[str] = None, incident_id: Optional[str] = None,
                   limit: int = 100) -> list[AccessEntry]:
        if not self.log_path.exists():
            return []
        out = []
        for line in reversed(self.log_path.read_text(encoding="utf-8").splitlines()):
            if not line.strip():
                continue
            e = AccessEntry.from_dict(json.loads(line))
            if building_id and e.building_id != building_id:
                continue
            if incident_id and e.incident_id != incident_id:
                continue
            out.append(e)
            if len(out) >= limit:
                break
        return out
