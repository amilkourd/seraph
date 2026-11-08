"""building.json → a short Markdown map of the building (per level: flats, rooms, balconies, ladder points, stair,
lift, entrances, technical rooms, fire ratings, materials). Everything printed comes from the file.

    uv run python -m seraph_ifc.describe out/building.json > out/building.md
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

TECH_RE = re.compile(r"(technique|électrique|electrique|chaufferie|tgbt|garage|poubelles|transfo)", re.I)


def describe(b: dict) -> str:
    rooms = {r["id"]: r for r in b["rooms"]}
    by_level = defaultdict(list)
    for r in b["rooms"]:
        by_level[r["level"]].append(r)
    units = defaultdict(list)
    for u in b.get("units", []):
        units[u["level"]].append(u)
    ladders = (b.get("model") or {}).get("ladder_points") or {}
    doors = b.get("doors") or []
    m = b.get("model") or {}
    L = []
    w = L.append
    w(f"**{b['name']}** — {m.get('provenance_fr', '')}")
    src = m.get("source_ifc") or {}
    if src.get("credit"):
        w(f"Source: `{src.get('file')}` ({src.get('credit')}).")
    w("")
    w("| | |")
    w("|---|---|")
    for s in b["stairs"]:
        w(f"| `stair:{s['id']}` | {s['label']}, levels {', '.join(str(x) for x in s['levels'])} |")
    lifts = [r for r in b["rooms"] if r.get("kind") == "elevator"]
    if lifts:
        w(f"| Lift | {', '.join('`room:' + r['id'] + '`' for r in lifts)} (one per level, not a route) |")
    for e in b["entrances"]:
        w(f"| `entrance:{e['id']}` | {e['label']} — level {e['level']}, {e['side']}, opens on `{e['leads_to']}` |")
    second = m.get("second_route")
    if second:
        w(f"| Second route | {second.get('reason', second.get('kind'))} |")
    w("")
    for lv in b["levels"]:
        n = lv["level"]
        w(f"**{lv['label']}** (level {n}, {lv['elevation_m']} m, IFC storey {lv.get('ifc_name')})")
        corridor = [r for r in by_level[n] if r.get("kind") == "corridor"]
        if corridor:
            w(f"- Common circulation: `{corridor[0]['id']}`")
        for u in units[n]:
            names = ", ".join(f"{rid} {rooms[rid]['label'].split(' ', 1)[-1] if ' ' in rooms[rid]['label'] else ''}"
                              .strip() for rid in u["rooms"])
            out = f"; outdoor {', '.join(u['outdoor'])}" if u["outdoor"] else ""
            w(f"- {u['label']} `{u['id']}` (door {', '.join(u['entry'])}): {names}{out}")
        if ladders.get(str(n)):
            w(f"- Ladder rescue points: {', '.join('`' + x + '`' for x in ladders[str(n)])}")
        tech = [r for r in by_level[n] if TECH_RE.search(r["label"])]
        if tech:
            w(f"- Technical / risk rooms: {', '.join(r['id'] + ' ' + r['label'].split(' ', 1)[-1] for r in tech)}")
        rated = [d for d in doors if d["level"] == n and d.get("fire_rating")]
        if rated:
            groups: dict[str, dict[str, int]] = defaultdict(dict)
            for d in rated:
                name = d["id"] if re.fullmatch(r"E\d+", d["id"]) else d["label"].removeprefix("Porte ")
                groups[d["fire_rating"]][name] = groups[d["fire_rating"]].get(name, 0) + 1
            w("- Fire-rated doors: " + "; ".join(
                f"{fr} ({', '.join(k + (f' ×{c}' if c > 1 else '') for k, c in v.items())})"
                for fr, v in groups.items()))
        mats = [x for x in b.get("materials") or [] if x.get("level") == n]
        if mats:
            w("- Materials: " + "; ".join(
                f"{x['element']} {x['material']}" + (f" {x['fire_rating']}" if x.get("fire_rating") else "")
                + (f" (room {x['room']})" if x.get("room") else "") for x in mats))
        w("")
    return "\n".join(L).rstrip() + "\n"


def main() -> None:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "out/building.json")
    sys.stdout.write(describe(json.loads(path.read_text(encoding="utf-8"))))


if __name__ == "__main__":
    main()
