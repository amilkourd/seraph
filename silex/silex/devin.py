"""Devin API v3 client (docs.devin.ai/api-reference/v3). Every call has a timeout; errors raise DevinError."""
from __future__ import annotations

from typing import Any, Optional

import httpx

from .config import settings

BASE = "https://api.devin.ai/v3/organizations"


class DevinError(RuntimeError):
    pass


def _devin_id(session_id: str) -> str:
    return session_id if session_id.startswith("devin-") else f"devin-{session_id}"


class Devin:
    def __init__(self) -> None:
        self.base = f"{BASE}/{settings.devin_org_id}"
        self.headers = {"Authorization": f"Bearer {settings.devin_api_key}"}

    async def _call(self, method: str, path: str, timeout: float = 20, **kw: Any) -> Any:
        try:
            async with httpx.AsyncClient(timeout=timeout, headers=self.headers) as c:
                r = await c.request(method, f"{self.base}{path}", **kw)
        except httpx.HTTPError as e:
            raise DevinError(f"{method} {path}: {type(e).__name__}") from e
        if r.status_code >= 400:
            detail = r.text[:300]
            raise DevinError(f"{method} {path}: HTTP {r.status_code} {detail}")
        return r.json() if r.content else {}

    async def create_session(self, prompt: str, title: str, tags: list[str], schema: Optional[dict] = None,
                             attachment_urls: Optional[list[str]] = None) -> dict:
        body: dict[str, Any] = {"prompt": prompt, "title": title, "tags": tags, "max_acu_limit": settings.max_acu}
        if schema:
            body["structured_output_schema"] = schema
        if attachment_urls:
            body["attachment_urls"] = attachment_urls
        return await self._call("POST", "/sessions", json=body, timeout=40)

    async def get_session(self, session_id: str) -> dict:
        return await self._call("GET", f"/sessions/{_devin_id(session_id)}")

    async def send_message(self, session_id: str, message: str, attachment_urls: Optional[list[str]] = None) -> dict:
        body: dict[str, Any] = {"message": message}
        if attachment_urls:
            body["attachment_urls"] = attachment_urls
        return await self._call("POST", f"/sessions/{_devin_id(session_id)}/messages", json=body, timeout=30)

    async def messages(self, session_id: str) -> list[dict]:
        d = await self._call("GET", f"/sessions/{_devin_id(session_id)}/messages", params={"first": 100})
        return d.get("items", [])

    async def upload(self, name: str, content: bytes, content_type: str) -> str:
        d = await self._call("POST", "/attachments", files={"file": (name, content, content_type)}, timeout=40)
        return d["url"]

    async def terminate(self, session_id: str) -> None:
        await self._call("DELETE", f"/sessions/{_devin_id(session_id)}")
