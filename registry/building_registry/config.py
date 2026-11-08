"""Settings from the process env, then the repo's root `.env`. Keys are never printed."""
from __future__ import annotations

import os
import re
from pathlib import Path

PKG_DIR = Path(__file__).resolve().parent
REGISTRY_DIR = PKG_DIR.parent                  # <repo>/registry
REPO = REGISTRY_DIR.parent                     # <repo>


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
        else:
            val = re.split(r"\s+#", val, maxsplit=1)[0].strip()
        out[key] = val
    return out


_FILE = _load_dotenv(REPO / ".env")


def env(key: str, default: str = "") -> str:
    v = os.environ.get(key)
    if v is None:
        v = _FILE.get(key, "")
    return v if v != "" else default


def flag(key: str, default: bool) -> bool:
    v = env(key, "1" if default else "0").lower()
    return v in ("1", "true", "yes", "on")
