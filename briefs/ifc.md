# Brief — `ifc` session · `ifc/` · Python, offline (no port)

Read first: `SYSTEM.md`, `CLAUDE.md`, `docs/10-ifc.md` (the design you implement), `contracts/types.ts` (`Building`,
`Source`), `contracts/fixtures/building.json` (the shape everyone already codes against), `docs/02-scenario.md`.

## Goal
Turn a building's IFC into what the rest of Seraph uses: `ifc/out/building.json` (the `Building` contract, with
`graph`, `doors`, `materials`, `model`), one SVG plan per level, a 3D `building.glb`. And, since no open IFC of a
real French building exists, produce the IFC of the reference venue from its posted plans.

## Steps
1. `uv` project in `ifc/` with `ifcopenshell`, `trimesh`, `numpy`, `pyyaml`, `shapely`.
2. **Dev building first** (don't wait for the venue): write `ifc/dev/trace.yaml` reproducing the fictional R+5 of
   `docs/02-scenario.md` (2 stairs, E1/E2, level 3 rooms 3.10, 3.12, 3.14, 3.T, corridor; other levels: one open
   space + corridor). `author.py` → `ifc/dev/dev.ifc`. `extract.py` → `ifc/out-dev/`. Its `building.json` must match
   the ids of `contracts/fixtures/building.json`. Tell @seraph @halo @dashboard @silex when it's there.
3. `author.py trace.yaml → .ifc` (IFC4, `ifcopenshell.api`): storeys, `IfcSpace` per room, walls along room edges
   (shared edges once), `IfcDoor`, `IfcStair`, materials and `FireRating` / `IsExternal` only when the trace gives
   them, pset `Seraph_Provenance {method, date, from}`. Polygons in metres.
4. `extract.py any.ifc → out/`: levels, rooms, doors (door ↔ the 2 nearest space footprints within 0.5 m, or
   `IfcRelSpaceBoundary`), entrances, stairs, materials, graph with metre lengths, level SVGs (one shared transform
   → 0–1000), glb (no furniture, coloured by class, one node per storey `L<n>`), `report.txt`.
5. Checks in `extract.py` (exit 1 if any fails): ≥ 2 escape routes from every occupied level, every room reachable
   from `outside`, every door links 2 nodes, glb < 15 MB.
6. **Venue:** when Amil drops plan photos in `ifc/venue/photos/` (or the venue's own file), trace them into
   `ifc/venue/trace.yaml` (read the photos; use the plan's scale), map ids in `ifc/venue/ids.yaml`
   (`stair:A`/`stair:B`, `E1`/`E2`), generate, extract to `ifc/out/`. Put provenance « Maquette IFC reconstruite
   depuis le plan affiché — exercice » in `model.provenance_fr`.
7. Test `extract.py` on the TU Wien IFC if Amil downloads it (`ifc/test/`, git-ignored): it must not crash; record
   what it found in your status file.

## Rules
- Never invent a material or a fire rating. Absent = absent.
- Don't edit `contracts/` — if `Building` needs a field, write it under Requests and tell Amil.
- `ifc/out/` is committed (small). Source photos and third-party IFCs are not (`.gitignore`).

## Done when
`ifc/out-dev/` and then `ifc/out/` exist and pass the checks; Seraph routes on the new graph; the glb loads in a
three.js page; `report.txt` shows levels, stairs, doors, rooms, materials found.
