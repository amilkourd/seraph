# ifc — a building's IFC, turned into what firefighters need

Seraph knows the inside of a building from its **IFC** (the open BIM format architects export): rooms, doors,
stairs, materials, fire ratings. This folder turns any IFC into one small file, `building.json`, plus one plan per
level. It runs once per building, offline: nothing parses IFC during an intervention.

```
any.ifc ──ifc-extract──▶ out/building.json      rooms, doors, stairs, entrances, flats, materials + fire ratings,
                                                route graph in metres, slab outline per level  (the `Building` contract)
                     ──▶ out/levels/L<n>.svg    the plan of each level, cut 1.10 m above the floor
                     ──▶ out/report.txt         what was found, what was ignored, the checks
                     ──▶ exit 1                 if a check fails: the model is not shipped
```

| Folder | What |
|---|---|
| `out/` | **The demo building**: TU Wien's real model (below), at a fictional address. Seraph's `BUILDING_JSON`. |
| `out-dev/` | The fictional R+5 of the first scenario (`dev/trace.yaml` → `dev/dev.ifc`), the « bâtiment fictif » fallback. |
| `tuwien/ids.yaml` | How the TU Wien model maps onto Seraph: entrance and scenario ids, French labels, declared second route. |
| `seraph_ifc/` | `extract.py` (any IFC), `checks.py`, `drawing.py` + `plans.py` (level plans), `author.py` (trace → IFC), `describe.py` (building → text map). |

## The demo building

**TU Wien, « Real-World Escape Route Test Model » v2.0.0** — a real, approved residential project in Vienna, IFC4
exported from Archicad, 13.5 MB, licensed **CC BY 4.0**. Credit: *TU Wien, Research Unit Digital Building Process*,
https://researchdata.tuwien.ac.at/records/wzp90-dmf60. No open IFC of a real French building could be found, so the
demo places this real model at a **fictional address** (`DEMO_ADDRESS`); every screen says « Maquette IFC réelle
(TU Wien, CC BY 4.0) — adresse fictive, exercice ». The IFC itself is not in git:

```bash
mkdir -p ifc/test/tuwien   # then download the IFC from the record above into it
cd ifc && uv sync && uv run ifc-extract test/tuwien/RealWorldTestModel-EscapeRouteAnalysis-ZDB-v2.ifc --ids tuwien/ids.yaml -o out/
```

What it gives: 5 levels (garage −1 to R+3), one pressurised stairwell (`stair:A`), 2 entrances (street door `E1`,
garage ramp `E2`), 7 flats, balconies and terraces as ladder rescue points, 81 doors with their real EN fire classes
(`EI2 30-C-Sm`, `EI 30`), walls and roofs `REI 90`. Readable map: `out/building.md`.

## How a model becomes a graph (works on any IFC)

- **Levels**: storeys holding a room, corridor or stair; ground = elevation closest to 0.
- **Rooms**: `IfcSpace` footprints from the real geometry. Stairs, lifts, shafts, corridors and outdoor spaces are
  recognised from the space's type or name (French, English, German). Room ids: the IFC name when short (`3.12`),
  else `<level>.<nn>` in reading order; `ids.yaml` can rename any room by GlobalId.
- **Doors**: an `IfcDoor` links the two spaces within 0.5 m of its centre (`IfcRelSpaceBoundary` first when present).
  **Openings** without a door come from virtual space boundaries. Parking bays nested in a garage are linked to it.
- **Stairs**: stair spaces stacked in plan are one stair `stair:<X>`, landing on `level:<n>` at each floor.
- **Outside**: an external door on the ground floor or below is an entrance `entrance:E<n>`. A balcony or terrace
  above the ground is a **ladder rescue point** `ladder:<id>`, a dead end, never an exit.
- **Edge lengths** in metres (door to room centre; a stair counts 2 m walked per metre of rise).
- **Flats** (`units`): rooms behind one door from the common corridor.
- **Slabs** (`levels[].outline`): the slabs whose top is at the level, with their real holes; else the level's spaces.
- **Frame**: plans and zones share one 0–1000 frame, turned onto the building's own axes with E1 at the bottom;
  `model.plan_frame` converts to metres.
- Elements Archicad exports as layers (walls, slabs, stairs, ramps as `IfcBuildingElementPart`) are read through
  their parts.

**Never invented.** A material or a fire rating absent from the IFC is absent from `building.json` (placeholders
like `ND` are dropped). Stair and entrance status is `unknown`: live state comes from the radio and calls.

## Checks (any failure = exit 1, no registration)

1. every door links 2 nodes · 2. every room is reachable from outside · 3. **≥ 2 independent escape routes from
every occupied level** (node-disjoint paths to `outside`); the façade counts as the second one only when the
building's `ids.yaml` declares it (`second_route: facade_ladder`: a single-stair dwelling, as TU Wien's) and the
level has a ladder rescue point · 4. every stair has a door or an opening on each level it serves.

## Level plans

Cut 1.10 m above each floor from the real geometry: walls by class and real thickness, windows, railings, door
leaves and swings from the IFC operation types, stair treads with the walking line and its up arrow, ramps with their
slope, lifts, shafts. Drawn with French intervention-plan conventions — **NF S 60-303** (cited by the ERP
regulation, MS 41) was replaced in 2013 by **NF X 08-070** (2023). Neither text is free; the conventions follow
public legends that reproduce them (Monaco fire brigade guide 2025, INRS ED 6230, Oise prefecture example plan):
white ground, black walls, common corridors pale green, stairs darker green « ESC A » with the arrow going up, lift
as a white box with an X and « ASC », risk rooms as a yellow triangle (lightning bolt = electrical room), fire doors
as a red sawtooth with their rating, fire-service access as a red arrow (main) or red disc (other), plan oriented to
the main access, graphic scale, north arrow. Ladder rescue points: a red ladder (no standard symbol exists).

## Other commands

```bash
uv run ifc-author dev/trace.yaml -o dev/dev.ifc            # a traced plan (YAML, metres) → IFC4 via IfcOpenShell
uv run python -m seraph_ifc.describe out/building.json      # one-page text map of a building
uv run pytest                                               # extractor, checks, TU Wien (skipped if not downloaded)
```

Rebuilding a building from posted plans: trace it into a `trace.yaml` (rooms as polygons in metres, doors, the
materials the plan states), `ifc-author` it, then extract like any IFC. Provenance « Maquette IFC reconstruite
depuis le plan affiché — exercice ».

Buildings reach Seraph through the registry (`registry/`), not by path: register the IFC there.
