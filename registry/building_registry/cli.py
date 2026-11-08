"""`registry` command line. Backend from REGISTRY_BACKEND or --backend.

    registry list
    registry lookup ["address"] [--incident INC-0001]        (no address: DEMO_ADDRESS from .env)
    registry show <building_id>
    registry register <file.ifc> --address "…" [--address "…"] [--demo-address] [--building-id ID]
                      [--ids ids.yaml] [--exercise] [--offline] [--provenance …] [--name …]
    registry add-address <building_id> --address "…" | --demo-address [--exercise]
    registry log [--building ID] [--incident ID] [--limit N]
    registry copy --to supabase [building_id …]               (local → another backend, e.g. after adding keys)
    registry export <building_id> <folder>                    (building.json + levels/, ready to serve)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

from . import open_registry
from .address import normalize
from .base import RegistryError
from .config import env


def _demo_address() -> str:
    a = env("DEMO_ADDRESS")
    if not a:
        raise SystemExit("DEMO_ADDRESS is not set (root .env)")
    return a


def _addresses(args) -> list[str]:
    out = list(args.address or [])
    if getattr(args, "demo_address", False):
        out.append(_demo_address())
    return out


def main(argv: Optional[list[str]] = None) -> None:
    ap = argparse.ArgumentParser(prog="registry", description="Seraph building registry")
    ap.add_argument("--backend", help="local | supabase | fire_service (default: REGISTRY_BACKEND or local)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list")
    p = sub.add_parser("lookup")
    p.add_argument("address", nargs="?")
    p.add_argument("--incident")
    p.add_argument("--offline", action="store_true")
    p = sub.add_parser("show")
    p.add_argument("building_id")
    p = sub.add_parser("register")
    p.add_argument("ifc", type=Path)
    p.add_argument("--address", action="append")
    p.add_argument("--demo-address", action="store_true", help="also register DEMO_ADDRESS from .env")
    p.add_argument("--building-id")
    p.add_argument("--ids", type=Path)
    p.add_argument("--exercise", action="store_true", help="test/demo entry: no BAN/RNB link, labelled exercice")
    p.add_argument("--offline", action="store_true")
    p.add_argument("--provenance", choices=["architect", "rebuilt_from_posted_plan", "fictional"])
    p.add_argument("--provenance-fr")
    p.add_argument("--name")
    p = sub.add_parser("add-address")
    p.add_argument("building_id")
    p.add_argument("--address", action="append")
    p.add_argument("--demo-address", action="store_true")
    p.add_argument("--exercise", action="store_true", help="no BAN link (made-up address)")
    p.add_argument("--offline", action="store_true")
    p = sub.add_parser("log")
    p.add_argument("--building")
    p.add_argument("--incident")
    p.add_argument("--limit", type=int, default=30)
    p = sub.add_parser("copy")
    p.add_argument("--to", required=True)
    p.add_argument("building_ids", nargs="*")
    p = sub.add_parser("export")
    p.add_argument("building_id")
    p.add_argument("folder", type=Path)

    args = ap.parse_args(argv)
    try:
        reg = open_registry(args.backend)
        _run(reg, args)
    except RegistryError as e:
        report = getattr(e, "report", "")
        if report:
            sys.stderr.write(report)
        sys.stderr.write(f"registry: {e}\n")
        sys.exit(1)


def _run(reg, args) -> None:
    if args.cmd == "list":
        for r in reg.list():
            tag = "  [exercice]" if r.exercise else ""
            print(f"{r.building_id:24} {r.id_kind:6} {r.name}{tag}")
            print(f"{'':24} {r.provenance_fr}")
            for a in r.addresses:
                print(f"{'':24} · {a.label}" + (f"  (BAN {a.ban_id})" if a.ban_id else "") + f"  [{a.source}]")
        return
    if args.cmd == "lookup":
        address = args.address or _demo_address()
        rec = reg.lookup(address, incident_id=args.incident, actor="registry-cli",
                         online=False if args.offline else None)
        if rec is None:
            print(f"pas de maquette  ({normalize(address)!r})")
            sys.exit(2)
        print(f"{rec.building_id}  {rec.name}  ·  {rec.provenance_fr}")
        print(reg.model_path(rec.building_id, incident_id=args.incident, actor="registry-cli"))
        return
    if args.cmd == "show":
        rec = reg.get(args.building_id)
        if rec is None:
            raise RegistryError(f"unknown building {args.building_id}")
        print(json.dumps(rec.to_dict(), ensure_ascii=False, indent=1))
        return
    if args.cmd == "register":
        from .ingest import register
        r = register(reg, args.ifc, _addresses(args), building_id=args.building_id, ids_path=args.ids,
                     exercise=args.exercise, online=False if args.offline else None, provenance=args.provenance,
                     provenance_fr=args.provenance_fr, name=args.name)
        print(f"{r.status}: {r.record.building_id}  {r.record.name}")
        for a in r.record.addresses:
            print(f"  · {a.label}  [{a.source}]")
        return
    if args.cmd == "add-address":
        addrs = _addresses(args)
        if not addrs:
            raise RegistryError("give --address or --demo-address")
        for a in addrs:
            refs = reg.add_address(args.building_id, a, online=False if args.offline else None,
                                   link_ban=not args.exercise)
            for ref in refs:
                print(f"{args.building_id} ← {ref.label}  [{ref.source}]")
        return
    if args.cmd == "log":
        for e in reg.access_log(building_id=args.building, incident_id=args.incident, limit=args.limit):
            print(f"{e.at}  {e.actor:14} {e.action:11} {e.result:5} {e.building_id or '-':24} "
                  f"{e.incident_id or '-':10} {e.query or ''}")
        return
    if args.cmd == "copy":
        from .ingest import copy_building
        dst = open_registry(args.to)
        for bid in args.building_ids or [r.building_id for r in reg.list()]:
            copy_building(reg, dst, bid)
            print(f"{bid} → {dst.name}")
        return
    if args.cmd == "export":
        folder = reg.materialize(args.building_id, args.folder)
        print(folder)
        return


if __name__ == "__main__":
    main()
