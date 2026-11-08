"""Skill files (`rosetta/skills/<endpoint>.md`): frontmatter + sections. The "Steps" section is the model's hints."""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from .config import LEARNED, SKILLS


def parse(text: str) -> dict:
    meta: dict = {}
    body = text
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = re.split(r"\s+#", v.strip(), 1)[0].strip()
        body = m.group(2)
    sections: dict[str, str] = {}
    cur = None
    for line in body.splitlines():
        h = re.match(r"^##\s+(.*)", line)
        if h:
            cur = h.group(1).strip().split(" (")[0]
            sections[cur] = ""
        elif cur:
            sections[cur] += line + "\n"
    return {"meta": meta, "sections": {k: v.strip() for k, v in sections.items()}}


@lru_cache(maxsize=64)
def _load(path: str, mtime: float) -> dict:
    return parse(Path(path).read_text())


def skill(name: str) -> dict:
    for d in (SKILLS, LEARNED):
        p = d / f"{name}.md"
        if p.exists():
            return _load(str(p), p.stat().st_mtime)
    return {"meta": {}, "sections": {}}


def hints(name: str) -> str:
    s = skill(name)["sections"]
    return "\n".join(x for x in (s.get("Steps", ""), s.get("Known traps", "")) if x)


def learned() -> list[dict]:
    out = []
    if LEARNED.exists():
        for p in sorted(LEARNED.glob("*.md")):
            s = _load(str(p), p.stat().st_mtime)
            out.append({"file": p.name, **s})
    return out
