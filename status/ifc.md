# ifc — status
Updated: 04:15

Owns `ifc/` (IFC → `building.json`) and `registry/` (the building registry Seraph looks addresses up in).

## Plan
1. `ifc/` uv project (`ifcopenshell`, `numpy`, `shapely`, `pyyaml`), package `seraph_ifc`. No glb (dashboard draws its own 3D).
2. Dev building: `ifc/dev/trace.yaml` = the fictional R+5 of `contracts/fixtures/` in metres, laid out so the extracted
   level-3 zones land on the fixture's 0–1000 zones. `author.py` → `ifc/dev/dev.ifc` (IFC4, spaces, walls, doors,
   stairs, `Seraph_Provenance`). Ids match `contracts/fixtures/building.json` (`stair:A/B`, `entrance:E1/E2`,
   `level:<n>`, `corridor:<n>`, `room:3.10`…). Extra rooms for the occupants' rooms (2.01, 4.02, 4.05, 5.01).
3. `extract.py any.ifc → out/`: `building.json` (Building contract: levels, stairs, entrances, rooms + zones, doors,
   materials only when the IFC has them, graph in metres, model provenance), `levels/L<n>.svg`, `report.txt`.
   Drops furniture, sanitary, MEP, wall layers.
4. Checks (exit 1): ≥ 2 escape routes per occupied level, every room reachable from `outside`, every door links 2 nodes,
   stairs serve the levels they claim.
5. `registry/`: package `building_registry` — `BuildingRegistry` (`lookup`, `get_model`, `list`, access log),
   backends `local` (default, offline), `supabase` (Postgres + Storage, migrations, RLS, service key server-side),
   `fire_service` (documented stub). `REGISTRY_BACKEND` env var. Keys: RNB id for the building, BAN id + normalized
   label for addresses; offline = exact normalized match; unknown → None.
6. CLI `registry register <file.ifc> --address …` (extract + checks + store + upsert, idempotent, extractor version),
   `lookup`, `list`, `log`.
7. Seraph imports `building_registry` (no extra deps for the local backend). Agree with @seraph.
8. pytest: extract, checks, one contract suite run against every backend. READMEs.
9. Venue building if photos or an IFC land in `ifc/venue/`.

## Running
- nothing (offline tools, no port)

## Done
-

## In progress
- steps 1–2

## Blocked
-

## Requests (to other sessions or Amil)
-

## Facts I verified (API names, model ids, gotchas)
-
