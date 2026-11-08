"""Addresses in, stable national ids out.

- `normalize()` turns any spelling into one key, offline: « 35, Bd Haussmann — 75009 PARIS » → « 35 boulevard haussmann
  75009 paris ». The registry keeps these keys, so a known address resolves with no network at all.
- `geocode()` asks the Base Adresse Nationale (api-adresse.data.gouv.fr) for the official address and its BAN id
  (`cle_interop`, e.g. 75109_6358_00009). Optional, short timeout.
- `rnb_buildings()` asks the Référentiel National des Bâtiments which buildings stand at that BAN address and
  returns their RNB ids (12 characters, e.g. 7RE2ZT12JGFM). Optional, short timeout.
"""
from __future__ import annotations

import json
import re
import unicodedata
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Optional

from .config import env

BAN_URL = "https://api-adresse.data.gouv.fr/search/"
RNB_URL = "https://rnb-api.beta.gouv.fr/api/alpha/buildings/"
TIMEOUT_S = 3.0
MIN_SCORE = 0.7

ABBREVIATIONS = {
    "bd": "boulevard", "bld": "boulevard", "blvd": "boulevard", "boul": "boulevard",
    "av": "avenue", "ave": "avenue", "pl": "place", "fbg": "faubourg", "fg": "faubourg",
    "sq": "square", "imp": "impasse", "rte": "route", "che": "chemin", "chem": "chemin",
    "all": "allee", "crs": "cours", "qu": "quai", "pass": "passage", "st": "saint", "ste": "sainte",
}
DROP = {"france", "cedex"}


def normalize(address: str) -> str:
    """Offline key for an address: lowercase, no accents, no punctuation, abbreviations expanded."""
    s = unicodedata.normalize("NFKD", address or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = re.sub(r"[’'`´\-–—_/,;.:()\"]+", " ", s)
    s = re.sub(r"\b(\d+)\s*(bis|ter|quater)\b", r"\1 \2", s)
    words = [ABBREVIATIONS.get(w, w) for w in s.split() if w not in DROP]
    return " ".join(words)


@dataclass
class BanAddress:
    label: str                  # « 9 Rue de Milan 75009 Paris »
    ban_id: str                 # cle_interop « 75109_6358_00009 »
    ban_uuid: Optional[str]
    lat: float
    lon: float
    score: float
    kind: str                   # housenumber | street | locality | municipality


def _get_json(url: str, timeout: float) -> Optional[dict]:
    req = urllib.request.Request(url, headers={"User-Agent": "seraph-building-registry/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:
        return None


def geocode(address: str, timeout: float = TIMEOUT_S) -> Optional[BanAddress]:
    """Best BAN match, only if it is a house number with a good score. None offline or when unsure."""
    url = env("BAN_URL", BAN_URL) + "?" + urllib.parse.urlencode({"q": address, "limit": 1})
    data = _get_json(url, timeout)
    feats = (data or {}).get("features") or []
    if not feats:
        return None
    p = feats[0].get("properties", {})
    lon, lat = feats[0].get("geometry", {}).get("coordinates", [None, None])
    if p.get("type") != "housenumber" or float(p.get("score", 0)) < MIN_SCORE or not p.get("id"):
        return None
    return BanAddress(label=p.get("label", address), ban_id=p["id"], ban_uuid=p.get("banId"), lat=float(lat),
                      lon=float(lon), score=float(p["score"]), kind=p["type"])


def rnb_buildings(ban_id: str, timeout: float = TIMEOUT_S) -> list[dict]:
    """RNB buildings linked to a BAN address: [{rnb_id, lat, lon}], most central first (empty offline)."""
    url = env("RNB_URL", RNB_URL) + "?" + urllib.parse.urlencode({"cle_interop_ban": ban_id})
    data = _get_json(url, timeout)
    out = []
    for b in (data or {}).get("results") or []:
        if b.get("is_active") is False or not b.get("rnb_id"):
            continue
        lon, lat = (b.get("point") or {}).get("coordinates", [None, None])
        out.append({"rnb_id": b["rnb_id"], "lat": lat, "lon": lon, "status": b.get("status")})
    return out


RNB_ID_RE = re.compile(r"^[0-9A-Z]{12}$")
MANUAL_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,62}$")


def id_kind(building_id: str) -> Optional[str]:
    """`rnb` for an RNB id, `manual` for our own lowercase ids (test buildings, no RNB entry), None if invalid."""
    if RNB_ID_RE.match(building_id or ""):
        return "rnb"
    if MANUAL_ID_RE.match(building_id or ""):
        return "manual"
    return None
