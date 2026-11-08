"""Supabase backend: Postgres (records, addresses, access log) + Storage (the files), server-side only.

Schema: registry/supabase/migrations/. Every table has RLS on and no policy, and the bucket is private: the anon and
publishable keys read nothing. Only this backend, with the secret key held by the server, reads or writes.

Env: SUPABASE_URL, SUPABASE_SECRET_KEY (new `sb_secret_…` key) or SUPABASE_SERVICE_ROLE_KEY (legacy JWT),
REGISTRY_BUCKET (default `building-models`). Keys are never logged or printed.
"""
from __future__ import annotations

import json
import urllib.parse
from typing import Any, Optional

from ..base import BuildingRegistry, RegistryError
from ..config import env
from ..model import AccessEntry, AddressRef, BuildingRecord

TIMEOUT_S = 8.0


class SupabaseRegistry(BuildingRegistry):
    name = "supabase"

    def __init__(self, url: Optional[str] = None, key: Optional[str] = None, bucket: Optional[str] = None,
                 online: Optional[bool] = None, transport: Any = None):
        super().__init__(online)
        import httpx

        self.url = (url or env("SUPABASE_URL")).rstrip("/")
        key = key or env("SUPABASE_SECRET_KEY") or env("SUPABASE_SERVICE_ROLE_KEY")
        if not self.url or not key:
            raise RegistryError("supabase backend needs SUPABASE_URL and SUPABASE_SECRET_KEY "
                                "(or SUPABASE_SERVICE_ROLE_KEY) in the environment")
        self.bucket = bucket or env("REGISTRY_BUCKET", "building-models")
        headers = {"apikey": key}
        if key.startswith("eyJ"):       # legacy service_role JWT; new sb_secret_ keys go on `apikey` only
            headers["Authorization"] = f"Bearer {key}"
        self.http = httpx.Client(base_url=self.url, headers=headers, timeout=TIMEOUT_S, transport=transport)

    # ───────── PostgREST helpers ─────────
    def _select(self, table: str, query: dict[str, str]) -> list[dict]:
        r = self.http.get(f"/rest/v1/{table}", params={"select": "*", **query})
        self._check(r)
        return r.json()

    def _upsert(self, table: str, rows: list[dict] | dict, on_conflict: str) -> None:
        r = self.http.post(f"/rest/v1/{table}", params={"on_conflict": on_conflict}, json=rows,
                           headers={"Prefer": "resolution=merge-duplicates,return=minimal"})
        self._check(r)

    @staticmethod
    def _check(r) -> None:
        if r.status_code >= 400:
            raise RegistryError(f"supabase {r.request.method} {r.request.url.path} → {r.status_code}: "
                                f"{r.text[:200]}")

    @staticmethod
    def _record(row: dict, addresses: list[dict]) -> BuildingRecord:
        return BuildingRecord(
            building_id=row["building_id"], id_kind=row["id_kind"], name=row["name"],
            provenance=row["provenance"], provenance_fr=row["provenance_fr"], exercise=row["exercise"],
            addresses=[AddressRef(key=a["key"], label=a["label"], source=a["source"], ban_id=a.get("ban_id"),
                                  ban_uuid=a.get("ban_uuid"), lat=a.get("lat"), lon=a.get("lon"))
                       for a in addresses],
            rnb_ids=row.get("rnb_ids") or [], model=row.get("model") or {},
            registered_at=row["registered_at"], updated_at=row["updated_at"])

    # ───────── reads ─────────
    def get(self, building_id: str) -> Optional[BuildingRecord]:
        rows = self._select("registry_buildings", {"building_id": f"eq.{building_id}"})
        if not rows:
            return None
        return self._record(rows[0], self._select("registry_addresses", {"building_id": f"eq.{building_id}"}))

    def list(self) -> list[BuildingRecord]:
        rows = self._select("registry_buildings", {"order": "building_id"})
        addrs = self._select("registry_addresses", {})
        return [self._record(r, [a for a in addrs if a["building_id"] == r["building_id"]]) for r in rows]

    def find_key(self, key: str) -> Optional[str]:
        rows = self._select("registry_addresses", {"key": f"eq.{key}"})
        return rows[0]["building_id"] if rows else None

    def find_ban(self, ban_id: str) -> Optional[str]:
        rows = self._select("registry_addresses", {"ban_id": f"eq.{ban_id}", "limit": "1"})
        return rows[0]["building_id"] if rows else None

    def find_rnb(self, rnb_id: str) -> Optional[str]:
        rows = self._select("registry_buildings", {"or": f"(building_id.eq.{rnb_id},rnb_ids.cs.{{{rnb_id}}})",
                                                   "limit": "1"})
        return rows[0]["building_id"] if rows else None

    def read_file(self, building_id: str, rel: str) -> bytes:
        path = urllib.parse.quote(f"{building_id}/{rel}")
        r = self.http.get(f"/storage/v1/object/authenticated/{self.bucket}/{path}")
        self._check(r)
        return r.content

    # ───────── writes ─────────
    def put(self, record: BuildingRecord, files: dict[str, bytes]) -> None:
        for rel, data in files.items():
            path = urllib.parse.quote(f"{record.building_id}/{rel}")
            r = self.http.post(f"/storage/v1/object/{self.bucket}/{path}", content=data,
                               headers={"x-upsert": "true", "Content-Type": _content_type(rel)})
            self._check(r)
        self._upsert("registry_buildings", {
            "building_id": record.building_id, "id_kind": record.id_kind, "name": record.name,
            "provenance": record.provenance, "provenance_fr": record.provenance_fr, "exercise": record.exercise,
            "rnb_ids": record.rnb_ids, "model": record.model, "registered_at": record.registered_at,
            "updated_at": record.updated_at}, "building_id")
        for a in record.addresses:
            self.put_address(record.building_id, a)

    def put_address(self, building_id: str, address: AddressRef) -> None:
        owner = self.find_key(address.key)
        if owner and owner != building_id:
            raise RegistryError(f"address {address.label!r} already belongs to {owner}")
        self._upsert("registry_addresses", {"key": address.key, "building_id": building_id, "label": address.label,
                                            "source": address.source, "ban_id": address.ban_id,
                                            "ban_uuid": address.ban_uuid, "lat": address.lat, "lon": address.lon},
                     "key")

    def delete(self, building_id: str) -> None:
        """Remove a building (record, addresses by cascade, files). The access log keeps its lines."""
        record = self.get(building_id)
        if record is None:
            return
        paths = [f"{building_id}/{rel}" for rel in record.model.get("files", [])]
        if paths:
            r = self.http.request("DELETE", f"/storage/v1/object/{self.bucket}", json={"prefixes": paths})
            self._check(r)
        r = self.http.delete("/rest/v1/registry_buildings", params={"building_id": f"eq.{building_id}"})
        self._check(r)

    # ───────── access log ─────────
    def write_log(self, entry: AccessEntry) -> None:
        r = self.http.post("/rest/v1/registry_access_log", json=entry.to_dict(),
                           headers={"Prefer": "return=minimal"})
        self._check(r)

    def access_log(self, building_id: Optional[str] = None, incident_id: Optional[str] = None,
                   limit: int = 100) -> list[AccessEntry]:
        q = {"order": "at.desc", "limit": str(limit)}
        if building_id:
            q["building_id"] = f"eq.{building_id}"
        if incident_id:
            q["incident_id"] = f"eq.{incident_id}"
        return [AccessEntry.from_dict(r) for r in self._select("registry_access_log", q)]


def _content_type(rel: str) -> str:
    return {"json": "application/json", "svg": "image/svg+xml", "txt": "text/plain", "yaml": "text/yaml",
            "ifc": "application/x-step"}.get(rel.rsplit(".", 1)[-1], "application/octet-stream")


def dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False)
