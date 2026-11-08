"""Settings from the root `.env` (never printed). Process env wins over the file."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

PKG_DIR = Path(__file__).resolve().parent
SERVICE_DIR = PKG_DIR.parent                 # <repo>/seraph
REPO = SERVICE_DIR.parent                    # <repo>
FIXTURES = REPO / "contracts" / "fixtures"


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


def env(key: str, default: str = "") -> str:
    v = os.environ.get(key)
    if v is None:
        v = _FILE.get(key, "")
    return v if v != "" else default


def _repo_path(p: str) -> Path:
    path = Path(p)
    return path if path.is_absolute() else REPO / path


@dataclass(frozen=True)
class Settings:
    mock: bool
    demo_address: str
    demo_town: str
    building_json: Path
    plan_image_path: Path
    ari_time_factor: float
    llm_base_url: str
    llm_api_key: str
    llm_model: str
    seraph_url: str
    seraph_public_url: str
    rosetta_url: str
    silex_url: str
    halo_url: str
    view_moments: frozenset[str]
    replicas: dict[str, str]

    @property
    def llm_enabled(self) -> bool:
        return bool(self.llm_base_url and self.llm_model)


def building_json() -> Path:
    """BUILDING_JSON when the file exists (checked on every reset, so the IFC can land while Seraph runs)."""
    bj = _repo_path(env("BUILDING_JSON", "ifc/out/building.json"))
    return bj if bj.exists() else FIXTURES / "building.json"


def load() -> Settings:
    bj = building_json()
    return Settings(
        mock=env("MOCK", "0") == "1",
        demo_address=env("DEMO_ADDRESS"),
        demo_town=env("DEMO_TOWN", "Paris 9e"),
        building_json=bj,
        plan_image_path=_repo_path(env("PLAN_IMAGE_PATH", "contracts/fixtures/plan-level3.svg")),
        ari_time_factor=float(env("ARI_TIME_FACTOR", "10") or 10),
        llm_base_url=env("LLM_BASE_URL"),
        llm_api_key=env("LLM_API_KEY"),
        llm_model=env("LLM_MODEL"),
        seraph_url=env("SERAPH_URL", "http://localhost:8000"),
        seraph_public_url=env("SERAPH_PUBLIC_URL"),
        rosetta_url=env("ROSETTA_URL", "http://localhost:8001"),
        silex_url=env("SILEX_URL", "http://localhost:8002"),
        halo_url=env("HALO_URL", "http://localhost:3001"),
        # Moments Seraph asks Devin to build. Core = 2 + the commander's requests; stretch via env.
        view_moments=frozenset(
            m.strip() for m in env("SERAPH_VIEW_MOMENTS", "approach,team_engaged,commander_request").split(",") if m.strip()
        ),
        replicas={
            "dispatch": env("DISPATCH_URL", "http://localhost:8101"),
            "report": env("REPORT_URL", "http://localhost:8102"),
            "occupants": env("OCCUPANTS_URL", "http://localhost:8103"),
        },
    )


settings = load()
