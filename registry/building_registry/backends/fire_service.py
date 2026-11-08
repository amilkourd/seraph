"""Fire-service adapter: how a fire service's own building registry plugs in. Read-only.

A French SDIS keeps its own records of the buildings on its ground (ETARE pre-plans, ERP files, prévision). Seraph
does not replace that database: in production this adapter talks to it, and nothing else in Seraph changes.

This file is a working adapter for a minimal REST contract. Map it onto the real system by editing the three
`_…` methods below (endpoint paths, field names); the rest of Seraph only sees `BuildingRegistry`.

    GET {FIRE_SERVICE_REGISTRY_URL}/buildings?address_key=<normalized address>   → [ {building} ]
    GET {FIRE_SERVICE_REGISTRY_URL}/buildings?ban_id=<cle_interop>               → [ {building} ]
    GET {FIRE_SERVICE_REGISTRY_URL}/buildings?rnb_id=<RNB id>                    → [ {building} ]
    GET {FIRE_SERVICE_REGISTRY_URL}/buildings/<id>                               → {building}
    GET {FIRE_SERVICE_REGISTRY_URL}/buildings/<id>/files/<path>                  → bytes (building.json, levels/…)
    POST {FIRE_SERVICE_REGISTRY_URL}/access-log                                   ← {at, actor, action, …}

    {building} = {"id", "name", "rnb_ids", "addresses": [{"label", "ban_id"}], "model_status", "files": [...],
                  "provenance", "provenance_fr", "updated_at"}

If the fire service stores IFC files and not building.json, run `seraph_ifc.extract` on its side (or in a nightly
job here) and serve the outputs at `files/`: Seraph never parses IFC during an intervention.

Env: FIRE_SERVICE_REGISTRY_URL, FIRE_SERVICE_REGISTRY_TOKEN (bearer, server-side only).
"""
from __future__ import annotations

from typing import Any, Optional

from ..address import id_kind, normalize
from ..base import BuildingRegistry, RegistryError
from ..config import env
from ..model import AccessEntry, AddressRef, BuildingRecord

TIMEOUT_S = 5.0


class FireServiceRegistry(BuildingRegistry):
    name = "fire_service"
    writable = False

    def __init__(self, url: Optional[str] = None, token: Optional[str] = None, online: Optional[bool] = None,
                 transport: Any = None):
        super().__init__(online)
        import httpx

        self.url = (url or env("FIRE_SERVICE_REGISTRY_URL")).rstrip("/")
        if not self.url:
            raise RegistryError("fire_service backend needs FIRE_SERVICE_REGISTRY_URL")
        token = token or env("FIRE_SERVICE_REGISTRY_TOKEN")
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        self.http = httpx.Client(base_url=self.url, headers=headers, timeout=TIMEOUT_S, transport=transport)

    # ───────── the 3 places to adapt to the real system ─────────
    def _search(self, **params: str) -> list[dict]:
        r = self.http.get("/buildings", params=params)
        self._check(r)
        return r.json()

    def _fetch(self, building_id: str) -> Optional[dict]:
        r = self.http.get(f"/buildings/{building_id}")
        if r.status_code == 404:
            return None
        self._check(r)
        return r.json()

    def _to_record(self, b: dict) -> BuildingRecord:
        bid = str(b["id"])
        return BuildingRecord(
            building_id=bid, id_kind=id_kind(bid) or "manual", name=b.get("name", bid),
            provenance=b.get("provenance", "architect"), provenance_fr=b.get("provenance_fr", "Maquette du SDIS"),
            exercise=bool(b.get("exercise", False)),
            addresses=[AddressRef(key=normalize(a["label"]), label=a["label"], source="ban" if a.get("ban_id")
                                  else "manual", ban_id=a.get("ban_id")) for a in b.get("addresses", [])],
            rnb_ids=list(b.get("rnb_ids", [])), model={"files": b.get("files", []), "status": b.get("model_status")},
            registered_at=b.get("updated_at", ""), updated_at=b.get("updated_at", ""))

    # ───────── BuildingRegistry ─────────
    def get(self, building_id: str) -> Optional[BuildingRecord]:
        b = self._fetch(building_id)
        return self._to_record(b) if b else None

    def list(self) -> list[BuildingRecord]:
        return [self._to_record(b) for b in self._search()]

    def find_key(self, key: str) -> Optional[str]:
        hits = self._search(address_key=key)
        return str(hits[0]["id"]) if hits else None

    def find_ban(self, ban_id: str) -> Optional[str]:
        hits = self._search(ban_id=ban_id)
        return str(hits[0]["id"]) if hits else None

    def find_rnb(self, rnb_id: str) -> Optional[str]:
        hits = self._search(rnb_id=rnb_id)
        return str(hits[0]["id"]) if hits else None

    def read_file(self, building_id: str, rel: str) -> bytes:
        r = self.http.get(f"/buildings/{building_id}/files/{rel}")
        self._check(r)
        return r.content

    def write_log(self, entry: AccessEntry) -> None:
        r = self.http.post("/access-log", json=entry.to_dict())
        self._check(r)

    def access_log(self, building_id: Optional[str] = None, incident_id: Optional[str] = None,
                   limit: int = 100) -> list[AccessEntry]:
        params = {k: v for k, v in {"building_id": building_id, "incident_id": incident_id,
                                    "limit": str(limit)}.items() if v}
        r = self.http.get("/access-log", params=params)
        self._check(r)
        return [AccessEntry.from_dict(e) for e in r.json()]

    @staticmethod
    def _check(r) -> None:
        if r.status_code >= 400:
            raise RegistryError(f"fire-service registry {r.request.method} {r.request.url.path} → {r.status_code}")
