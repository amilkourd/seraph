"""Devin CLI on this laptop (docs.devin.ai/cli): `devin -p` runs in the repo root, so Devin reads the kit, the rules,
the examples, the state and the references from disk and writes the view into silex/runtime/build/. No tunnel."""
from __future__ import annotations

import asyncio
import json
import shutil
import time
from collections import deque
from pathlib import Path
from typing import Optional

from .config import PLAYBOOKS, REPO, RUNTIME, settings

RULES = PLAYBOOKS / "cli-config.json"         # Silex's permission rules for Devin
CONFIG = RUNTIME / "cli-config.json"          # what `--config` gets: the user's config (org id) + those rules


def write_config() -> Path:
    """`--config` replaces ~/.config/devin/config.json, which holds the org: merge, never print it."""
    user = Path.home() / ".config" / "devin" / "config.json"
    try:
        cfg = json.loads(user.read_text())
    except (OSError, ValueError):
        cfg = {}
    cfg["permissions"] = json.loads(RULES.read_text())["permissions"]
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps(cfg, indent=1))
    CONFIG.chmod(0o600)
    return CONFIG


def binary() -> Optional[str]:
    found = shutil.which("devin")
    if found:
        return found
    local = Path.home() / ".local" / "bin" / "devin"
    return str(local) if local.exists() else None


class Run:
    """One `devin -p` process. Keeps the last lines of its output for the dashboard."""

    def __init__(self, run_id: str, log_path: Path, export_path: Optional[Path] = None) -> None:
        self.run_id = run_id
        self.log_path = log_path
        self.export_path = export_path        # ATIF trace, written by the CLI when the run ends
        self.tail: deque[str] = deque(maxlen=12)
        self.proc: Optional[asyncio.subprocess.Process] = None
        self.started = time.time()
        self.returncode: Optional[int] = None
        self.offset = log_path.stat().st_size if log_path.exists() else 0

    def output(self) -> str:
        """Everything this run printed (its final reply included)."""
        try:
            with self.log_path.open("r", encoding="utf-8", errors="replace") as f:
                f.seek(self.offset)
                return f.read()
        except OSError:
            return ""

    async def start(self, prompt_file: Path, resume: Optional[str]) -> None:
        args = [binary() or "devin", "--model", settings.devin_model, "--permission-mode", settings.devin_permission_mode,
                "--config", str(write_config()), "--respect-workspace-trust", "false"]
        if resume:
            args += ["-r", resume]
        if self.export_path:
            args += ["--export", str(self.export_path)]
        args += ["-p", "--prompt-file", str(prompt_file)]
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.proc = await asyncio.create_subprocess_exec(*args, cwd=str(REPO), stdin=asyncio.subprocess.DEVNULL,
                                                         stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)

    async def wait(self, timeout: float) -> Optional[int]:
        assert self.proc and self.proc.stdout
        with self.log_path.open("a", encoding="utf-8") as log:
            async def pump() -> None:
                async for raw in self.proc.stdout:
                    line = raw.decode("utf-8", "replace").rstrip()
                    log.write(line + "\n")
                    log.flush()
                    if line.strip():
                        self.tail.append(line[:200])
            try:
                await asyncio.wait_for(pump(), timeout=timeout)
                self.returncode = await self.proc.wait()
            except asyncio.TimeoutError:
                self.kill()
                self.returncode = None
        return self.returncode

    def kill(self) -> None:
        if self.proc and self.proc.returncode is None:
            try:
                self.proc.kill()
            except ProcessLookupError:
                pass


async def latest_session(since: float) -> Optional[str]:
    """The id of the newest CLI session in the repo root started after `since` (`devin list --format json`)."""
    if not binary():
        return None
    proc = await asyncio.create_subprocess_exec(binary(), "list", "--format", "json", cwd=str(REPO),
                                                stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE,
                                                stderr=asyncio.subprocess.DEVNULL)
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=15)
    except asyncio.TimeoutError:
        proc.kill()
        return None
    try:
        data = json.loads(out.decode("utf-8", "replace") or "[]")
    except ValueError:
        return None
    items = data if isinstance(data, list) else data.get("sessions") or data.get("items") or []

    def ts(it: dict) -> float:
        for k in ("last_activity_at", "updated_at", "created_at", "started_at"):
            v = it.get(k)
            if isinstance(v, (int, float)):
                return v / 1000 if v > 1e12 else v
            if isinstance(v, str):
                try:
                    from datetime import datetime
                    return datetime.fromisoformat(v.replace("Z", "+00:00")).timestamp()
                except ValueError:
                    continue
        return 0.0

    items = [it for it in items if isinstance(it, dict)]
    items.sort(key=ts, reverse=True)
    for it in items:
        sid = it.get("id") or it.get("session_id") or it.get("name")
        if sid and (ts(it) == 0.0 or ts(it) >= since - 5):
            return str(sid)
    return None


def read_export(path: Optional[Path]) -> tuple[Optional[str], list[dict]]:
    """The CLI session id and Devin's steps (what it read, wrote, ran, said) from an ATIF export."""
    try:
        d = json.loads(path.read_text(encoding="utf-8")) if path else {}
    except (OSError, ValueError):
        return None, []
    steps = []
    for st in d.get("steps") or []:
        if st.get("source") != "agent":
            continue
        t = st.get("timestamp") or ""
        results = {r.get("source_call_id"): str(r.get("content") or "") for r in ((st.get("observation") or {}).get("results") or [])}
        for call in st.get("tool_calls") or []:
            name, args = call.get("function_name") or "?", call.get("arguments") or {}
            target = args.get("file_path") or args.get("path") or args.get("command") or args.get("pattern") or ""
            target = str(target).replace(str(REPO) + "/", "")
            out = results.get(call.get("tool_call_id"), "")
            code = out.rsplit("Exit code:", 1)[1].strip().split()[0] if "Exit code:" in out else None
            lines = [l for l in out.replace("Output from command in shell", "").splitlines()[1:] if l.strip() and not l.startswith("Exit code")]
            steps.append({"t": t, "tool": name, "target": target[:160], "code": code, "out": "\n".join(lines[:6])[:400]})
        msg = (st.get("message") or "").strip()
        if msg:
            steps.append({"t": t, "tool": "say", "target": msg[:300], "code": None, "out": ""})
    return d.get("session_id"), steps


def build_dir(view_id: str) -> Path:
    return RUNTIME / "build" / view_id
