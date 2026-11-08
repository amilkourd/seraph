"""Settings from the repo root .env (CLAUDE.md rule 7). Already-set environment variables win."""
from __future__ import annotations

import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "contracts" / "fixtures"


def _load_env() -> None:
    p = ROOT / ".env"
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = re.split(r"\s+#", v, maxsplit=1)[0].strip().strip('"').strip("'")
        os.environ.setdefault(k.strip(), v)


_load_env()


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default) or default


def live_env(name: str, default: str = "") -> str:
    """The root .env value now (filled in while running, no restart), else the process env."""
    p = ROOT / ".env"
    try:
        for line in p.read_text(encoding="utf-8").splitlines():
            k, sep, v = line.strip().partition("=")
            if sep and k.strip() == name:
                v = re.split(r"\s+#", v, 1)[0].strip().strip('"').strip("'")
                if v:
                    return v
    except OSError:
        pass
    return env(name, default)


MOCK = env("MOCK", "0") == "1"
LIVEKIT_URL = env("LIVEKIT_URL")
LIVEKIT_API_KEY = env("LIVEKIT_API_KEY")
LIVEKIT_API_SECRET = env("LIVEKIT_API_SECRET")
GLADIA_API_KEY = env("GLADIA_API_KEY")
TTS_PROVIDER = env("TTS_PROVIDER", "elevenlabs")
TTS_API_KEY = env("TTS_API_KEY")
LLM_BASE_URL = env("LLM_BASE_URL", "https://api.openai.com/v1")
LLM_API_KEY = env("LLM_API_KEY")
LLM_MODEL = env("LLM_MODEL", "gpt-5.4-mini")
SERAPH_URL = env("SERAPH_URL", "http://localhost:8000")
SERAPH_WS = env("SERAPH_WS_URL", "ws://localhost:8000").rstrip("/") + "/ws/gabriel"

# ElevenLabs: flash for latency, one multilingual voice for fr/en/es (override per env).
TTS_MODEL = env("GABRIEL_TTS_MODEL", "eleven_flash_v2_5")
TTS_VOICE = env("GABRIEL_TTS_VOICE", "")
TTS_SAMPLE_RATE = 24000

RADIO_ROOM = "crew"
RADIO_IDENTITY = "Seraph"
CALL_AGENT_NAME = "gabriel-call"

# LiveKit Agents plugins read these names.
os.environ.setdefault("ELEVEN_API_KEY", TTS_API_KEY)
os.environ.setdefault("OPENAI_API_KEY", LLM_API_KEY)
