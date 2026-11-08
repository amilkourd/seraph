"""Settings from the root `.env` (never printed). Process env wins over the file."""
from __future__ import annotations

import os
import re
import socket
from dataclasses import dataclass
from pathlib import Path

PKG_DIR = Path(__file__).resolve().parent
SERVICE_DIR = PKG_DIR.parent                 # <repo>/silex
REPO = SERVICE_DIR.parent                    # <repo>
KIT = REPO / "halo" / "kit"
LEARNED = REPO / "rosetta" / "skills" / "learned"
PLAYBOOKS = SERVICE_DIR / "devin"


def _load_dotenv(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip().removeprefix("export ").strip()
        val = val.strip()
        if val[:1] in ("'", '"') and val[-1:] == val[:1] and len(val) >= 2:
            val = val[1:-1]
        elif val.startswith("#"):
            val = ""
        else:
            val = re.split(r"\s+#", val, maxsplit=1)[0].strip()
        out[key] = val
    return out


_FILE = _load_dotenv(REPO / ".env")
# a second instance (tests) points these elsewhere so it never touches the live one's files
VIEWS = Path(os.environ.get("SILEX_VIEWS") or REPO / "views")
RUNTIME = Path(os.environ.get("SILEX_RUNTIME") or SERVICE_DIR / "runtime")   # sessions.json, staging, builds (gitignored)


def env(key: str, default: str = "") -> str:
    v = os.environ.get(key)
    if v is None:
        v = _FILE.get(key, "")
    return v if v != "" else default


def lan_ip() -> str:
    """The laptop's address on the LAN: what the phone uses to reach Silex when there is no public URL."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.2)
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "127.0.0.1"


@dataclass(frozen=True)
class Settings:
    mock: bool
    port: int
    public_url: str            # base URL the phone and the dashboard load views from
    kit_url: str               # empty = <origin of the request>/kit, served by Silex from halo/kit
    seraph_url: str
    rosetta_url: str
    devin_api_key: str
    devin_org_id: str
    warm: int                  # warm Devin sessions kept ready
    max_sessions: int          # live Devin sessions at once (warm + building)
    max_tries: int             # Devin attempts per view (first + fixes)
    max_acu: int               # ACU cap per Devin session
    mock_delay_s: float
    transport: str             # cli: local `devin -p` (Opus, sees the repo) · api: Devin cloud API v3
    devin_model: str
    devin_permission_mode: str
    ref_wait_s: float          # how long a build waits for Rosetta shots that are still being taken

    @property
    def active_transport(self) -> str:
        """cli when asked for and installed; else the API when its key is set (fallback); else none."""
        from .cli import binary
        if self.transport == "cli" and binary():
            return "cli"
        return "api" if self.devin_api_key and self.devin_org_id else "none"

    @property
    def devin_ready(self) -> bool:
        return self.active_transport != "none"


def load() -> Settings:
    port = int(env("SILEX_PORT", "8002"))
    return Settings(
        mock=env("MOCK", "0") in ("1", "true", "yes"),
        port=port,
        public_url=env("SILEX_PUBLIC_URL", f"http://{lan_ip()}:{port}").rstrip("/"),
        kit_url=env("SILEX_KIT_URL", "").rstrip("/"),
        seraph_url=env("SERAPH_URL", "http://localhost:8000").rstrip("/"),
        rosetta_url=env("ROSETTA_URL", "http://localhost:8001").rstrip("/"),
        devin_api_key=env("DEVIN_API_KEY"),
        devin_org_id=env("DEVIN_ORG_ID"),
        warm=int(env("SILEX_WARM", "2")),
        max_sessions=int(env("SILEX_MAX_SESSIONS", "4")),
        max_tries=int(env("SILEX_MAX_TRIES", "3")),
        max_acu=int(env("SILEX_MAX_ACU", "10")),
        mock_delay_s=float(env("SILEX_MOCK_DELAY_S", "6")),
        transport=env("DEVIN_TRANSPORT", "cli").lower(),
        devin_model=env("SILEX_DEVIN_MODEL", "opus"),
        devin_permission_mode=env("SILEX_DEVIN_PERMISSION_MODE", "accept-edits"),
        ref_wait_s=float(env("SILEX_REF_WAIT_S", "45")),
    )


settings = load()
