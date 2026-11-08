"""In-memory stand-ins for the remote services, as httpx transports: the backends' real HTTP code runs against them.

- FakeSupabase: the subset of PostgREST + Storage the supabase backend uses (eq / or filters, order, limit,
  upsert on conflict, insert, delete; object upload, authenticated download, bulk delete).
- FakeFireService: the minimal fire-service registry API documented in backends/fire_service.py, served from a
  local registry.
"""
from __future__ import annotations

import json
import re
import urllib.parse

import httpx


class FakeSupabase:
    def __init__(self):
        self.tables: dict[str, list[dict]] = {"registry_buildings": [], "registry_addresses": [],
                                              "registry_access_log": []}
        self.objects: dict[str, bytes] = {}
        self.keys = {"registry_buildings": "building_id", "registry_addresses": "key"}
        self.transport = httpx.MockTransport(self.handle)

    @staticmethod
    def _match(row: dict, col: str, cond: str) -> bool:
        op, _, val = cond.partition(".")
        if op == "eq":
            return str(row.get(col)) == val
        if op == "cs":
            want = set(val.strip("{}").split(",")) - {""}
            return want <= set(row.get(col) or [])
        raise AssertionError(f"filter {op} not faked")

    def handle(self, req: httpx.Request) -> httpx.Response:
        assert req.headers.get("apikey"), "every call carries the apikey header"
        if req.headers["apikey"].startswith("sb_secret_"):
            assert "authorization" not in req.headers, "a new secret key must not be sent as Bearer"
        path = urllib.parse.unquote(req.url.path)
        q = dict(urllib.parse.parse_qsl(req.url.query.decode()))
        m = re.match(r"^/rest/v1/(\w+)$", path)
        if m:
            table = self.tables[m.group(1)]
            if req.method == "GET":
                rows = list(table)
                for col, cond in q.items():
                    if col in ("select", "order", "limit"):
                        continue
                    if col == "or":
                        alts = [a.split(".", 1) for a in re.split(r",(?![^{]*})", cond.strip("()"))]
                        rows = [r for r in rows if any(self._match(r, c, v) for c, v in alts)]
                    else:
                        rows = [r for r in rows if self._match(r, col, cond)]
                if "order" in q:
                    col, _, direction = q["order"].partition(".")
                    rows.sort(key=lambda r: str(r.get(col)), reverse=direction == "desc")
                if "limit" in q:
                    rows = rows[: int(q["limit"])]
                return httpx.Response(200, json=rows)
            if req.method == "POST":
                body = json.loads(req.content)
                rows = body if isinstance(body, list) else [body]
                key = q.get("on_conflict")
                for row in rows:
                    if key:
                        table[:] = [r for r in table if r.get(key) != row.get(key)]
                    else:
                        row = {**row, "id": len(table) + 1}
                    table.append(row)
                return httpx.Response(201)
            if req.method == "DELETE":
                gone = [r for r in table if all(self._match(r, c, v) for c, v in q.items())]
                table[:] = [r for r in table if r not in gone]
                if m.group(1) == "registry_buildings":   # on delete cascade
                    ids = {r["building_id"] for r in gone}
                    self.tables["registry_addresses"][:] = [a for a in self.tables["registry_addresses"]
                                                            if a["building_id"] not in ids]
                if "return=representation" in req.headers.get("prefer", ""):
                    return httpx.Response(200, json=gone)
                return httpx.Response(204)
        m = re.match(r"^/storage/v1/object/(authenticated/)?([\w-]+)/?(.*)$", path)
        if m:
            bucket, obj = m.group(2), m.group(3)
            if req.method == "POST":
                if f"{bucket}/{obj}" in self.objects and req.headers.get("x-upsert") != "true":
                    return httpx.Response(409, json={"error": "Duplicate"})
                self.objects[f"{bucket}/{obj}"] = req.content
                return httpx.Response(200, json={"Key": f"{bucket}/{obj}"})
            if req.method == "GET":
                data = self.objects.get(f"{bucket}/{obj}")
                return httpx.Response(200, content=data) if data is not None else httpx.Response(404)
            if req.method == "DELETE":
                for p in json.loads(req.content)["prefixes"]:
                    self.objects.pop(f"{bucket}/{p}", None)
                return httpx.Response(200, json=[])
        return httpx.Response(404, json={"error": f"not faked: {req.method} {path}"})


class FakeFireService:
    """A fire service's registry, as seen through the documented REST contract."""

    def __init__(self, source):
        self.src = source           # a LocalRegistry holding the buildings
        self.log: list[dict] = []
        self.transport = httpx.MockTransport(self.handle)

    def _b(self, r) -> dict:
        return {"id": r.building_id, "name": r.name, "rnb_ids": r.rnb_ids, "provenance": r.provenance,
                "provenance_fr": r.provenance_fr, "exercise": r.exercise, "updated_at": r.updated_at,
                "addresses": [{"label": a.label, "ban_id": a.ban_id} for a in r.addresses],
                "files": r.model.get("files", []), "model_status": "ok"}

    def handle(self, req: httpx.Request) -> httpx.Response:
        assert req.headers.get("authorization") == "Bearer test-token"
        path = urllib.parse.unquote(req.url.path)
        q = dict(urllib.parse.parse_qsl(req.url.query.decode()))
        if path == "/buildings":
            rs = self.src.list()
            if "address_key" in q:
                rs = [r for r in rs if any(a.key == q["address_key"] for a in r.addresses)]
            if "ban_id" in q:
                rs = [r for r in rs if any(a.ban_id == q["ban_id"] for a in r.addresses)]
            if "rnb_id" in q:
                rs = [r for r in rs if q["rnb_id"] in r.rnb_ids]
            return httpx.Response(200, json=[self._b(r) for r in rs])
        m = re.match(r"^/buildings/([\w-]+)(/files/(.+))?$", path)
        if m:
            r = self.src.get(m.group(1))
            if r is None:
                return httpx.Response(404)
            if m.group(3):
                return httpx.Response(200, content=self.src.read_file(r.building_id, m.group(3)))
            return httpx.Response(200, json=self._b(r))
        if path == "/access-log":
            if req.method == "POST":
                self.log.append(json.loads(req.content))
                return httpx.Response(201)
            rows = [e for e in reversed(self.log) if all(e.get(k) == v for k, v in q.items() if k != "limit")]
            return httpx.Response(200, json=rows[: int(q.get("limit", 100))])
        return httpx.Response(404)
