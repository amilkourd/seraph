# The building model (IFC)

Decision, 02:00 Sunday: Seraph knows the inside of the building from an **IFC file**: walls, doors, stairs, rooms,
materials and fire ratings, as a firefighter would get it in the real use case. Computer use keeps everything
the IFC doesn't have: the street, the hydrant, the truck spot, the risks, dispatch, occupants, the report.

> « L'IFC donne l'intérieur, Rosetta donne tout le reste. »

## Why
- **Real geometry instead of a guess.** Routes, stairs, doors, rooms come from the building model. Seraph routes on
  a graph built from it (code, never a model).
- **Materials and fire ratings.** « Porte coupe-feu EI30 », « cloison légère », « façade pierre » — when the IFC has
  them. When it doesn't, Seraph says « pas dans la maquette ». Never guessed.
- **One source for three views:** the route graph (Seraph), one plan per level (Halo, and Devin's references), a
  3D model (dashboard).
- **It is where the law is going.** Since Grenfell, England requires the responsible person of residential
  buildings of 18 m+ or 7+ storeys to give the fire service **electronic floor plans** and the **design and
  materials of the external walls**, plus a secure information box with paper plans on site (Fire Safety (England)
  Regulations 2022, in force 23 January 2023). In France, public buildings (ERP) post a paper plan for firefighters
  at each entrance; there is no national database (see `docs/09-research.md`). Our assumption for the real use
  case: the fire service holds the IFC of the buildings on its ground, from the architect or the building manager.

## Which building: a French one, the reference venue
We need a French address: Géorisques is France-only and the demo happens in the venue. **No real French building
with an openly downloadable IFC was found** (searched: OSArch AEC open data directory, opensourceBIM/IFC-files,
buildingSMART samples, awesome-bim-datasets, French BIM teaching pages; everything is fictional, foreign, or not
downloadable). The best real one is in Vienna (TU Wien, below), so it is out.

So the demo building is **the reference venue, La Maison by Motier Ventures (Paris 9e)**. In order of preference:
1. **The venue's own plans.** Ask the venue team whether the building manager or the architect has
   IFC / Revit / DWG / PDF plans. IFC or Revit (export IFC4) → use as is. DWG or PDF → trace (option 2).
2. **Rebuilt from the posted plans.** Photograph the evacuation / intervention plan posted on each floor (ask
   first). The `ifc` session traces them into `ifc/venue/trace.yaml` and generates `venue.ifc` with IfcOpenShell.
   Dimensions from the plan's scale, or paced on site. Materials and fire ratings only where the plan shows them
   (fire door symbol, legend) or the venue tells us; everything else absent.
   Every screen says: **« Maquette IFC reconstruite depuis le plan affiché — exercice »**.
3. **Fallback:** the fictional R+5 (`ifc/out-dev`, labelled « bâtiment fictif »).

**Decision: the demo runs on the real TU Wien IFC** (`ifc/out`, one stair, façade ladders as the second way
out) at a fictional address. Scenario: `docs/02-scenario.md`. `contracts/fixtures/building.json` is built from it.

Never publish the venue's plans in posts or the public README without their OK.

## Pipeline (session `ifc`, folder `ifc/`, run offline once — nothing parses IFC live)
```
plans (photo/PDF/DWG) ─trace→ ifc/venue/trace.yaml ─author.py→ ifc/venue/venue.ifc ┐
                                         (or the venue's own .ifc) ───────────────┤
                                                                                 ▼
                                           extract.py  →  ifc/out/building.json   (Building contract)
                                                       →  ifc/out/levels/L<n>.svg (one plan per level, 1000×1000)
                                                       →  ifc/out/building.glb    (3D, < 15 MB)
                                                       →  ifc/out/report.txt      (tools/ifc_inspect.py output + checks)
```
- `tools/ifc_inspect.py <file.ifc>`: storeys, counts, rooms, wall materials, fire ratings, escape psets. Run it on
  any candidate first.
- `author.py`: IFC4 via `ifcopenshell.api`: storeys, `IfcSpace` per room (extruded polygon), walls along room edges
  (shared edges once, 0.2 m), `IfcDoor` per door, `IfcStair` per stair and level, `IfcMaterial` +
  `Pset_WallCommon.FireRating` / `Pset_DoorCommon.FireRating` / `IsExternal` only when given, and a custom pset
  `Seraph_Provenance {method, date, from}`.
- `extract.py` works on **any** IFC (the venue's, the rebuilt one, a real foreign one for testing):
  - levels from `IfcBuildingStorey` (name, elevation); rooms from `IfcSpace` (Name, LongName, area, footprint);
  - doors: each `IfcDoor` links the two spaces whose footprints are within 0.5 m of the door centre (or
    `IfcRelSpaceBoundary` when present); a door touching only one space and `IsExternal` (or on the outer wall) is an
    entrance `E<n>` linked to `outside`;
  - stairs: `IfcStair` / stair spaces become `stair:<A|B|…>` nodes linked to the space they open on, on every level
    they serve;
  - materials: per wall/slab/door/facade, from `IfcMaterial*`, with `FireRating` when set; grouped per level;
  - graph: nodes `outside`, `entrance:E1`, `stair:A`, `room:<id>`, edges with length in metres;
  - plans: one SVG per level, same transform for all levels (building footprint → 0–1000), thick outlines, room
    ids, doors, stairs; room zones in `building.json` use the same 0–1000 frame (`image_id: "ifc-L<n>"`);
  - glb: `ifcopenshell.geom` world coords, no furniture, coloured by class (walls grey, slabs dark, doors amber,
    stairs green, external walls 40 % transparent), one node per storey named `L<n>` so the dashboard can explode
    levels and colour rooms.
- **Checks (fail = don't ship):** ≥ 2 escape routes from every occupied level · every room reachable from
  `outside` · every door links 2 nodes · stairs serve every level they claim · glb < 15 MB.
- Names: keep the scenario ids when the building allows (`stair:A`, `E1` street entrance, `E2` the other,
  `ladder:<room>` for balconies and terraces). Map them in `ifc/<building>/ids.yaml` (TU Wien: `ifc/tuwien/ids.yaml`).

## Who uses what
| Consumer | Uses | How |
|---|---|---|
| Seraph | `building.json` (graph, rooms, doors, materials, model) | loads at start (`BUILDING_JSON`); routes, best entrance, answers « c'est quoi la porte du 3 ? » with source `ifc` |
| Rosetta | `building.entrances` | `maps.building` gets the IFC's external doors as hints: Holo finds them on Street View / Earth (`expected_entrances`) |
| Rosetta | — | `plan.read` stays: for buildings without IFC (most of them) and, in the demo, it cross-checks the IFC on the door photo |
| Silex / Devin | `ifc/out/levels/L<n>.svg` | added to the view request's references, next to the Rosetta screenshots |
| Halo | level plans, rooms, doors | `Halo.plan` draws from `building.rooms` zones on the level SVG |
| Dashboard | `building.glb` + state | 3D building in the centre zone: levels slightly apart, rooms coloured by hazard, people dots and teams on their level, slow orbit; side view as fallback |

Seraph serves the outputs: `GET /building/files/{path}` → `ifc/out/{path}` (CORS open) so Halo, Silex, the
dashboard and Devin's views use the same URLs.

## Safety
- Building facts come from the IFC or a screen, never from a model. Unknown stays « inconnu » / « pas dans la
  maquette ».
- The model's provenance is always on screen (« IFC architecte », « reconstruite depuis le plan affiché »,
  « bâtiment fictif »), on the dashboard and Halo's status line.
- A model is not the building on the day: hazards and blocked doors reported on the radio or by calls override it.

## Real IFC used only to test the extractor
TU Wien « Real-World Escape Route Test Model » — a real approved project in Vienna, IFC4 (Archicad 26), CC BY 4.0,
12.9 MB, standard properties + escape-route properties. Download on the laptop (the cloud sandbox can't reach it):
https://researchdata.tuwien.ac.at/records/2heb4-xqb83 (a newer version exists at `/latest`). Running `extract.py`
on it proves the pipeline works on an architect's file, not only on ours. Credit TU Wien if mentioned.
