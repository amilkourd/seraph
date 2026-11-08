# ifc — status
Updated: 05:00

Owns `ifc/` (any IFC → `building.json`, level plans, checks) and `registry/` (the building registry Seraph looks
addresses up in).

## Running
- Nothing serves (offline tools). Seraph imports `registry/` as a package (`building_registry`), no port.
- Demo building: `registry lookup` → TU Wien at `DEMO_ADDRESS` (local backend, offline).

## Done
- `ifc/` (extractor 1.2.0): `extract.py` works on any IFC. TU Wien real model (13.5 MB, Archicad IFC4) → all 4 checks
  pass in ~3 s; dev R+5 too. Real space footprints, doors via IfcRelSpaceBoundary + 0.5 m rule, openings via
  IfcVirtualElement boundaries, stairs stacked into one `stair:A`, outdoor spaces (balconies = ladder points, never
  exits), shafts dropped, flats (`units`), French labels + ids from `ifc/tuwien/ids.yaml`, materials and fire
  ratings only from the IFC (« ND » placeholders dropped), per-level slab outlines, plan frame on the building's
  axes with E1 at the bottom.
- `ifc/out/` = TU Wien (Seraph's `BUILDING_JSON`), `ifc/out-dev/` = fictional R+5 (fixture ids). Each has
  `building.json`, `levels/L<n>.svg`, `report.txt`, `building.md`.
- `registry/`: `BuildingRegistry` (lookup / get_model / model_path / list / access log), backends `local` (default,
  offline), `supabase` (written + migration applied on project `seraph`, ref `awddwjzozoqyxpyblpsi`, eu-west-1:
  tables `registry_buildings`, `registry_addresses`, `registry_access_log`, private bucket `building-models`, RLS on with
  no policy = closed to anon/publishable keys), `fire_service` (read-only adapter for an SDIS registry). CLI `registry`
  (register / lookup / add-address / log / copy / export), idempotent registration.
- Registered (local): `tuwien-escape-route-v2` at `DEMO_ADDRESS` (exercice) and `dev-r5-exercice` at « 1 rue de
  l'Exercice, 75009 Paris » (exercice, « bâtiment fictif » fallback). Unknown address → None. Checked with Seraph's
  own loader (`seraph.building.load` + `shortest_path`).

## In progress
- Section-cut level plans (real walls, flights + up arrow, door swings, windows, shafts, NF S 60-303 symbols).
- Tests (pytest: extract, checks, one contract suite for every backend), READMEs.

## Blocked
- Supabase data copy: needs `SUPABASE_URL` + `SUPABASE_SECRET_KEY` in `.env` (Amil). Then
  `cd registry && uv run registry copy --to supabase` copies both buildings. Tables and bucket already exist.

## Requests (to other sessions or Amil)
- Amil: paste in `.env` (server-side only, never in a client): `SUPABASE_URL=https://awddwjzozoqyxpyblpsi.supabase.co`
  and `SUPABASE_SECRET_KEY` (Settings → API Keys → secret key; a legacy `SUPABASE_SERVICE_ROLE_KEY` also works).
  New env names (also in `.env.example`): `REGISTRY_BACKEND` (local | supabase | fire_service, default local),
  `REGISTRY_DIR`, `REGISTRY_CACHE_DIR`, `REGISTRY_ONLINE` (1: BAN/RNB lookups for unknown spellings, default 1;
  `MOCK=1` forces offline), `REGISTRY_BUCKET`, `SUPABASE_URL`, `SUPABASE_SECRET_KEY` / `SUPABASE_SERVICE_ROLE_KEY`,
  `FIRE_SERVICE_REGISTRY_URL`, `FIRE_SERVICE_REGISTRY_TOKEN`.
- Amil (contracts/types.ts, `Building`): optional fields the extractor now writes, to add to the contract:
  `levels[].outline` / `outline_m` (`{outer, holes}[]`, 0–1000 frame / metres), `levels[].outline_source`
  ("slab" | "spaces"), `levels[].slab_thickness_m`, `levels[].ifc_name`; `rooms[].kind`
  (room | corridor | elevator | exterior), `rooms[].ifc_name`, `rooms[].ifc_guid`; `stairs[].levels`,
  `stairs[].zones` (`{level, zone}[]`); `entrances[].leads_to`, `entrances[].level`, `entrances[].plan_point`
  (on the IFC plan, not Street View); `doors[].plan_point`; `units[]` (flats: `{id, level, label, rooms, outdoor,
  entry}`); `model.ladder_points` (`{level: node[]}`), `model.second_route` (`{kind, reason}`),
  `model.plan_frame`, `model.extractor`, `model.source_ifc`, `model.checks`. Node prefixes: `ladder:<id>`.
- @seraph: done — integration snippet sent; serve `/building/files` from `kit.files_dir` first.

## Facts I verified (API names, model ids, gotchas)
- ifcopenshell 0.9.0: import api submodules explicitly (`import ifcopenshell.api.root` …); geometry via
  `ifcopenshell.geom.iterator(settings, f, threads, include=[...])`, `settings.set("use-world-coords", True)`.
- TU Wien IFC: spaces mostly unnamed (LongName German), stair = 150 IfcBuildingElementPart under IfcStair (no body
  of its own), door OperationType on the IfcDoorType, slabs belong to the storey BELOW (match by top elevation),
  slabs carry their stair/lift/shaft holes, `Pset_SpaceFireSafetyRequirements` on 103 spaces, model rotated ~50°.
- BAN: `GET https://api-adresse.data.gouv.fr/search/?q=…&limit=1` → `properties.id` = cle_interop
  (75109_6358_00009), `banId` UUID, `score`, `type`. RNB: `GET https://rnb-api.beta.gouv.fr/api/alpha/buildings/?cle_interop_ban=…`
  → `results[].rnb_id` (12 chars); one address can have several RNB buildings.
- Supabase new keys: `sb_secret_…` goes in the `apikey` header only (a Bearer non-JWT is rejected); legacy
  service_role JWT goes in both `apikey` and `Authorization`.

## The demo building (TU Wien), for the scenario session
**Immeuble d'habitation (maquette TU Wien)** — Maquette IFC réelle (TU Wien, CC BY 4.0) — adresse fictive, exercice
Source: `RealWorldTestModel-EscapeRouteAnalysis-ZDB-v2.ifc` (TU Wien, Research Unit Digital Building Process — CC BY 4.0).

| | |
|---|---|
| `stair:A` | Escalier A, levels -1, 0, 1, 2, 3 |
| Lift | `room:-1.02`, `room:0.03`, `room:1.02`, `room:2.02`, `room:3.01` (one per level, not a route) |
| `entrance:E1` | Porte d'entrée, hall de l'escalier — level 0, front, opens on `corridor:0` |
| `entrance:E2` | Porte de garage, rampe (sous-sol) — level -1, left, opens on `room:-1.03` |
| Second route | Un seul escalier, encloisonné et mis en surpression ; second moyen de sauvetage par la façade (balcons, terrasses) avec les échelles des pompiers. |

**R-1** (level -1, -3.3 m, IFC storey UG1)
- Common circulation: `corridor:-1`
- Locaux `U-1.1` (door P-1-2): -1.01 Caves
- Locaux `U-1.2` (door P-1-5): -1.03 Rampe d'accès, -1.05 Place de parking, -1.07 Place de parking, -1.09 Place de parking, -1.10 Place de parking, -1.11 Garage, -1.12 Place de parking, -1.13 Place de parking, -1.14 Place de parking, -1.15 Place de parking
- Locaux `U-1.3` (door P-1-1): -1.04 Local poussettes
- Locaux `U-1.4` (door P-1-6): -1.06 Local électrique, -1.08 Local technique
- Technical / risk rooms: -1.06 Local électrique, -1.08 Local technique, -1.11 Garage
- Fire-rated doors: EI2 30-C-Sm (-1.04 Local poussettes, -1.01 Caves, -1.06 Local électrique ×2, -1.11 Garage)
- Materials: facade Béton armé (dalle du garage) REI 90; facade Béton armé (mur) REI 90; facade Béton armé (mur du garage) REI 90; slab Béton armé (dalle); wall Aluminium; wall Béton armé (mur) REI 90

**RDC** (level 0, -0.22 m, IFC storey EG)
- Common circulation: `corridor:0`
- Logement `U0.1` (door P0-18): 0.02 Chambre, 0.04 Salle de bain, 0.06 Entrée, 0.07 Buanderie, 0.09 Séjour-cuisine; outdoor 0.01, 0.14
- Logement `U0.2` (door P0-17): 0.08 Salle de bain, 0.10 Buanderie, 0.11 Salle de bain, 0.12 WC, 0.13 Entrée, 0.15 Chambre, 0.16 Circulation, 0.17 Chambre, 0.18 Chambre, 0.19 Séjour-cuisine; outdoor 0.20
- Technical / risk rooms: 0.05 Local poubelles
- Fire-rated doors: EI2 30-C-Sm (0.13 Entrée, 0.06 Entrée); EI 30 (Porte-fenêtre 0.20 Terrasse ×7, Porte-fenêtre 0.14 Terrasse, Porte-fenêtre 0.01 Terrasse); EI2 30-C (E1)
- Materials: facade Aluminium; facade Béton armé (mur) REI 90; slab Béton armé (dalle); slab Béton armé (dalle du garage); wall Béton armé (mur); wall Béton armé (mur) REI 90

**R+1** (level 1, 2.74 m, IFC storey OG1)
- Common circulation: `corridor:1`
- Logement `U1.1` (door P1-48): 1.01 Chambre, 1.03 Salle de bain, 1.04 Entrée, 1.06 Buanderie, 1.08 Séjour-cuisine; outdoor 1.05
- Logement `U1.2` (door P1-49): 1.07 Salle de bain, 1.09 Buanderie, 1.10 Salle de bain, 1.11 Chambre, 1.12 WC, 1.13 Entrée, 1.14 Circulation, 1.15 Chambre, 1.16 Chambre, 1.17 Séjour-cuisine; outdoor 1.18
- Ladder rescue points: `ladder:1.05`, `ladder:1.18`
- Fire-rated doors: EI 30 (Porte-fenêtre 1.05 Balcon, Porte-fenêtre 1.18 Balcon ×2); EI2 30-C-Sm (1.04 Entrée, 1.13 Entrée)
- Materials: slab Béton armé (dalle); wall Béton armé (mur) REI 90

**R+2** (level 2, 5.7 m, IFC storey DG1)
- Common circulation: `corridor:2`
- Logement `U2.1` (door P2-67): 2.01 Chambre, 2.03 Salle de bain, 2.04 Entrée, 2.06 Buanderie, 2.08 Séjour-cuisine; outdoor 2.05
- Logement `U2.2` (door P2-59): 2.07 Salle de bain, 2.09 Buanderie, 2.10 Salle de bain, 2.11 WC, 2.12 Entrée, 2.13 Chambre, 2.14 Circulation, 2.15 Chambre, 2.16 Séjour-cuisine; outdoor 2.17
- Ladder rescue points: `ladder:2.05`, `ladder:2.17`
- Fire-rated doors: EI 30 (Porte-fenêtre 2.05 Balcon, Porte-fenêtre 2.17 Balcon); EI2 30-C-Sm (2.12 Entrée, 2.04 Entrée)
- Materials: roof Béton armé (toiture) REI 90; roof Béton armé (dalle) REI 90; slab Béton armé (dalle); wall Béton armé (mur) REI 90

**R+3** (level 3, 8.66 m, IFC storey DG2)
- Common circulation: `corridor:3`
- Logement `U3.1` (door P3-72): 3.02 Chambre, 3.03 Circulation, 3.05 WC, 3.06 Salle de bain, 3.10 Séjour-cuisine, 3.12 Chambre, 3.T Buanderie; outdoor 3.04, 3.07, 3.08
- Ladder rescue points: `ladder:3.04`, `ladder:3.08`, `ladder:3.07`
- Fire-rated doors: EI2 30-C-Sm (3.03 Circulation); EI 30 (Porte-fenêtre 3.08 Terrasse, Porte-fenêtre 3.07 Terrasse, Porte-fenêtre 3.04 Terrasse)
- Materials: roof Béton armé (toiture) REI 90; roof Béton armé (dalle) REI 90; wall Béton armé (mur) REI 90
