"""Outbound phone calls for Seraph's `place_calls` (docs/06-gabriel.md « Telephony »). For each number: a new room
`call-<id>` with the call agent `gabriel-call` dispatched into it, the number in the job metadata. The agent dials it
through the LiveKit SIP outbound trunk (`LIVEKIT_SIP_OUTBOUND_TRUNK_ID`) and sends ringing / answered / no_answer /
failed / ended to Seraph (`calls.Call.dial`).

Never dialed: the registry's fictional seed numbers (+3310000…), anything that is not E.164, and every number while no
outbound trunk is set. Those occupants keep the web call (`/call?occ=…`)."""
from __future__ import annotations

import json
import logging
import random
import re
import string
from typing import Optional

from livekit import api

from . import config
from .seraph_link import SeraphLink, mask, now_iso

log = logging.getLogger("gabriel.dial")

SEED = re.compile(r"^\+3310000")            # demo occupants: fictional numbers, stay stubbed or web call
E164 = re.compile(r"^\+[1-9]\d{7,14}$")


def trunk() -> str:
    return config.live_env("LIVEKIT_SIP_OUTBOUND_TRUNK_ID")


def why_not(phone: str) -> Optional[str]:
    if not trunk():
        return "no outbound trunk (LIVEKIT_SIP_OUTBOUND_TRUNK_ID empty)"
    if SEED.match(phone):
        return "registry seed number (fictional)"
    if not E164.match(phone):
        return "not an E.164 number"
    return None


def new_call_id() -> str:
    return "CALL-P" + "".join(random.choices(string.ascii_uppercase + string.digits, k=5))


class Dialer:
    def __init__(self, link: SeraphLink) -> None:
        self.link = link
        self._api: Optional[api.LiveKitAPI] = None

    def lk(self) -> api.LiveKitAPI:
        if not self._api:
            self._api = api.LiveKitAPI(config.LIVEKIT_URL.replace("wss://", "https://"), config.LIVEKIT_API_KEY,
                                       config.LIVEKIT_API_SECRET)
        return self._api

    async def place(self, calls: list[dict]) -> None:
        for c in calls:
            occ, phone = c.get("occupant_id"), re.sub(r"[\s.-]", "", c.get("phone_e164") or "")
            why = why_not(phone)
            if why:
                log.warning("place_calls %s %s not dialed: %s → web call /call?occ=%s", occ, mask(phone), why, occ)
                continue
            call_id = new_call_id()
            meta = {"call_id": call_id, "occupant_id": occ, "direction": "out", "channel": "phone",
                    "lang": c.get("language_hint"), "name": c.get("name"), "phone_e164": phone}
            try:
                await self.lk().agent_dispatch.create_dispatch(api.CreateAgentDispatchRequest(
                    agent_name=config.CALL_AGENT_NAME, room=f"call-{call_id}", metadata=json.dumps(meta)))
                log.info("place_calls %s %s → %s dispatched", occ, mask(phone), call_id)
            except Exception as e:
                log.error("place_calls %s %s dispatch failed: %s", occ, mask(phone), type(e).__name__)
                self.link.send({"kind": "call_event", "call_id": call_id, "event": "failed", "direction": "out",
                                "channel": "phone", "occupant_id": occ, "number_masked": mask(phone),
                                "lang": c.get("language_hint"), "at": now_iso()})

    async def close(self) -> None:
        if self._api:
            await self._api.aclose()
