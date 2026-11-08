# registry — an address in, the building's model out

When an incident comes in, Seraph has an address. A fire service keeps a registry of the buildings on its ground;
this is that registry: Seraph looks the address up and gets the building's model (`building.json` and its level
plans), or **None**, in which case Seraph runs without a model (« pas de maquette ») on what Rosetta reads from
screens. In production the registry is the fire service's own: swap one backend (below), nothing else changes.

```python
from building_registry import open_registry

reg = open_registry()                                    # REGISTRY_BACKEND = local | supabase | fire_service
rec = reg.lookup(address, incident_id="INC-0001", actor="seraph")      # BuildingRecord | None
path = reg.model_path(rec.building_id, incident_id="INC-0001")         # …/building.json, levels/L<n>.svg beside it
```

`lookup` · `get_model` · `model_path` · `list` · `access_log`, and for writable backends `register`
(CLI / `ingest.py`) and `add_address`. **Every lookup and model read is logged**: who, when, which building, for
which incident, hit or miss.

## Registered now

| building_id | What | Address |
|---|---|---|
| `tuwien-escape-route-v2` | **The demo building.** TU Wien « Real-World Escape Route Test Model » v2.0.0 (IFC4, Archicad, **CC BY 4.0**, credit *TU Wien, Research Unit Digital Building Process*, https://researchdata.tuwien.ac.at/records/wzp90-dmf60). Provenance « Maquette IFC réelle (TU Wien, CC BY 4.0) — adresse d'exercice ». | `DEMO_ADDRESS`, now « 96 Boulevard Bessières, 75017 Paris » (exercise address: this model is not the building there) |
| `dev-r5-exercice` | The fictional R+5, « bâtiment fictif » fallback. | 1 rue de l'Exercice, 75009 Paris (placeholder, exercice) |

Look up the demo building with `DEMO_ADDRESS` (in `.env`), in any spelling: `registry lookup "96 bd Bessieres 75017 PARIS"`.
Both are on the local backend and on Supabase.

## Why it is keyed this way

- **Building = RNB id.** The Référentiel National des Bâtiments gives every French building a stable 12-character id
  (`7RE2ZT12JGFM`), independent of how anyone spells the address. An address can hold several buildings and a
  building several addresses, so the address is not the key.
- **Address = BAN id.** The Base Adresse Nationale (`api-adresse.data.gouv.fr`) turns any spelling into the official
  address and its id (`cle_interop`, e.g. `75109_6358_00009`); the RNB API then lists the buildings at that address
  (`/api/alpha/buildings/?cle_interop_ban=…`). Both verified live on 2026-11-08.
- **Offline first.** Each registered address is also stored as a normalized key (« 35, Bd Haussmann » →
  « 35 boulevard haussmann »), matched exactly with no network: the demo never depends on venue Wi-Fi. Only an
  unknown spelling triggers BAN → RNB (3 s timeouts), and a hit is cached as a new key.
- **Test buildings** that no national registry knows (and real models placed at made-up addresses) get a manual id
  (lowercase, `tuwien-escape-route-v2`), are flagged `exercise`, and get **no BAN/RNB link**, so they can never
  shadow a real building.

## Add a building

```bash
cd registry && uv sync
uv run registry register ../ifc/<file>.ifc --address "12 rue X, 69001 Lyon"                 # id from BAN → RNB
uv run registry register ../ifc/<file>.ifc --address "…" --building-id my-test-01 --exercise # test building, offline
uv run registry register ../ifc/test/tuwien/RealWorldTestModel-EscapeRouteAnalysis-ZDB-v2.ifc \
    --ids ../ifc/tuwien/ids.yaml --building-id tuwien-escape-route-v2 --demo-address --exercise
```

`register` runs the extractor and its checks (a failed check refuses the building), stores the IFC, `building.json`,
the plans, the report and `ids.yaml`, and upserts the record with the extractor version and hashes. It is
idempotent: same IFC + same extractor + same `ids.yaml` → « unchanged » (addresses merged); anything else
re-extracts.

**Move the demo building to a new address** (DEMO_ADDRESS read from `.env`, never hardcoded), then drop the old one:

```bash
uv run registry add-address tuwien-escape-route-v2 --demo-address --exercise
uv run registry remove-address tuwien-escape-route-v2 --address "<old address>"
```

Other commands: `registry list`, `registry show <id>`, `registry lookup [address] [--incident ID]`, `registry remove-address`,
`registry log [--building ID] [--incident ID]`, `registry export <id> <folder>`, `registry copy --to supabase`.

## Backends

| `REGISTRY_BACKEND` | Where | Use |
|---|---|---|
| `local` (default) | `registry/data/`: `index.json` + one folder per building + `access.log.jsonl` | Demo, offline, no dependency (stdlib only: Seraph imports it as is) |
| `supabase` | Postgres + Storage, project `seraph` (ref `awddwjzozoqyxpyblpsi`, eu-west-1) | Shared, durable registry |
| `fire_service` | A fire service's own registry over HTTP, read-only | Production |

**Supabase.** Schema in `supabase/migrations/` (applied): `registry_buildings`, `registry_addresses`,
`registry_access_log`, private bucket `building-models`. Row-level security is on with **no policy** and privileges
are revoked from `anon` / `authenticated`: the publishable key reads nothing (the advisor's « RLS enabled, no
policy » notice is intended). Only the server, with the secret key, reads and writes; the access log cannot be
updated or deleted even with it. Env: `SUPABASE_URL`, `SUPABASE_SECRET_KEY` (new `sb_secret_…`, sent on the `apikey`
header only) or `SUPABASE_SERVICE_ROLE_KEY` (legacy JWT). Copy the local registry up with `registry copy --to supabase` (done: both buildings are there). Checked on
the live project: the publishable key gets `401 permission denied` on every table and `400` on every file.

**Swap in a fire service's registry.** `backends/fire_service.py` is a working read-only adapter for a minimal REST
contract (search by normalized address, BAN id or RNB id; fetch a building; fetch its files; post access-log lines).
Map it onto the real system by editing its three marked methods (paths and field names) and set
`REGISTRY_BACKEND=fire_service`, `FIRE_SERVICE_REGISTRY_URL`, `FIRE_SERVICE_REGISTRY_TOKEN`. If that registry holds
IFC files rather than `building.json`, run `ifc-extract` on its side or in a nightly job: Seraph never parses IFC
during an intervention. Any other system: subclass `BuildingRegistry` (`base.py`) and implement its seven reads.

Env, all optional: `REGISTRY_BACKEND`, `REGISTRY_DIR`, `REGISTRY_CACHE_DIR`, `REGISTRY_ONLINE` (`MOCK=1` forces
offline), `REGISTRY_BUCKET`.

## Tests

```bash
cd registry && uv run pytest
```

One contract suite, run against every backend: `local` (temp folder), `supabase` (the real backend code against an
in-memory PostgREST + Storage), `supabase-live` (the real project, when `SUPABASE_URL` and a secret key are set; it
cleans up after itself; 35 tests pass with it), and `fire_service` (the adapter against a fake fire-service API; read-only). Registration
runs the real extractor on the fictional R+5. Plus address normalization and id rules. The extractor's own tests
are in `ifc/`.
