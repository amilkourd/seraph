"""Settings from the root `.env` (never printed). Real environment variables win over the file."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]          # repo root
HERE = Path(__file__).resolve().parents[1]          # rosetta/
SHOTS = HERE / "shots"
CACHE = HERE / "cache"
PROFILES = HERE / "profiles"
SKILLS = HERE / "skills"
LEARNED = SKILLS / "learned"
TRACES = HERE / "traces"
FIXTURES = ROOT / "contracts" / "fixtures"


def _load_env() -> dict[str, str]:
    out: dict[str, str] = {}
    p = ROOT / ".env"
    if not p.exists():
        return out
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = re.split(r"\s+#", v, 1)[0].strip()     # inline comments
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            v = v[1:-1]
        out[k.strip()] = v
    return out


_FILE = _load_env()


def env(key: str, default: str = "") -> str:
    v = os.environ.get(key)
    if v is None or v == "":
        v = _FILE.get(key, "")
    return v if v != "" else default


@dataclass(frozen=True)
class Settings:
    mock: bool
    port: int
    public_url: str
    seraph_url: str
    h_api_key: str
    h_base_url: str
    holo_model: str
    max_parallel: int
    headless: bool
    demo_address: str
    replica_password: str
    dispatch_url: str
    report_url: str
    occupants_url: str


def load() -> Settings:
    return Settings(
        mock=env("MOCK", "0") == "1",
        port=int(env("ROSETTA_PORT", "8001")),
        public_url=env("ROSETTA_URL", "http://localhost:8001").rstrip("/"),
        seraph_url=env("SERAPH_URL", "http://localhost:8000").rstrip("/"),
        h_api_key=env("H_API_KEY"),
        h_base_url=env("H_API_BASE_URL", "https://api.hcompany.ai/v1/"),
        holo_model=env("HOLO_MODEL", "holo4-35b-a3b"),
        max_parallel=int(env("ROSETTA_MAX_PARALLEL", "4")),
        headless=env("ROSETTA_HEADLESS", "0") == "1",
        demo_address=env("DEMO_ADDRESS"),
        replica_password=env("REPLICA_PASSWORD"),
        dispatch_url=env("DISPATCH_URL", "http://localhost:8101").rstrip("/"),
        report_url=env("REPORT_URL", "http://localhost:8102").rstrip("/"),
        occupants_url=env("OCCUPANTS_URL", "http://localhost:8103").rstrip("/"),
    )


settings = load()
for d in (SHOTS, CACHE, PROFILES, TRACES):
    d.mkdir(parents=True, exist_ok=True)
