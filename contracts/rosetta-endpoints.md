# Rosetta endpoints (8) — the allowlist

Rule: Rosetta only operates software we don't own. Public sites are **read-only**. Writes happen only in replicas,
and `report.fill` only after the « confirmez » gate. Every result carries `source`, `screenshots`, `live`.
Points use H's 0–1000 grid on the screenshot they refer to (`ImagePoint`).

| # | Endpoint | Software | Kind | Access | Timeout | Cache |
|---|---|---|---|---|---|---|
| 1 | `dispatch.read` | Dispatch replica (:8101) | replica | read | 30 s | none |
| 2 | `maps.building` | Google Maps, Street View, Google Earth (web) | real | read + vision | 90 s | golden path |
| 3 | `georisques.risks` | georisques.gouv.fr | real | read | 45 s | golden path |
| 4 | `weather.wind` | meteofrance.com | real | read | 45 s | 30 min |
| 5 | `plan.read` | Photo of the plan posted at the door (image file) | real photo | vision | 60 s | golden path |
| 6 | `occupants.list` | Building manager replica (:8103) | replica | read | 30 s | none |
| 7 | `dispatch.write_112` | Dispatch replica | replica | write | 30 s | none |
| 8 | `report.fill` | Report replica (:8102) | replica | write, gated | 120 s | none |

"Golden path" = the last good **live** result for the demo address is cached; a cached answer is always marked
`live:false` and shown as « cache » on the dashboard. Learned endpoints are added under
`rosetta/skills/learned/` by Silex, start as `verified:false`, and Seraph says « source non vérifiée » when using one.

---

## 1. `dispatch.read`
params `{ incident_id?: string }` (none = most recent open incident)
output
```json
{ "incident_id": "INC-0001", "address": "…", "nature": "Feu de véhicule en parking souterrain, fumée dans l'escalier",
  "level": -1, "declared_at": "…", "caller_notes": ["Fumée dans la cage d'escalier", "Habitants bloqués dans les étages"] }
```
Steps: log in → incident list → open the newest « En cours » → read the fields. Code reads the DOM text after Holo
reaches the page (never trust a value the model typed in its answer).

## 2. `maps.building`
params `{ address: string, expected_entrances?: { id: string; label: string; side?: string }[] }` — the entrances come
from the IFC; Holo looks for each one on Street View / Earth and returns a point per id.
Does: Google Maps search → Street View at the front → turn left/right (2–3 headings) → Google Earth web 3D view of
the block (orbit: front, both sides, rear when visible) → one top view. Takes a screenshot at each stop.
Holo then **points** on each screenshot at: entrances (with side), gates/fences, hydrant if visible, a place where a
fire engine can stop, overhead obstacles.
output
```json
{ "storeys_estimate": 4,
  "entrances": [{"id":"E1","label":"Porte d'entrée, hall de l'escalier","side":"front","point":{"image_id":"earth-top-01","x":500,"y":585}},
                {"id":"E2","label":"Porte de garage, rampe (sous-sol)","side":"left","point":{"image_id":"earth-top-01","x":395,"y":352}}],
  "hydrants": [{"id":"H1","label":"Poteau incendie, trottoir rue Madame","point":{"image_id":"earth-top-01","x":831,"y":635}}],
  "truck_spot": {"label":"Rue Madame, devant E1","point":{"image_id":"earth-top-01","x":500,"y":712}},
  "footprint": {"image_id":"earth-top-01","polygon":[[422,468],[422,360],[625,360], …]},
  "evidence": [{"of":"E1","point":{"image_id":"sv-front-01","x":508,"y":642}}, …],
  "obstacles": ["Voitures garées le long de la rue Madame"] }
```
**Every point Halo draws (entrances, hydrant, truck spot) is on the same top view, `earth-top-01`.** Points found on
other photos (Street View, Earth sides) go in `evidence` (`{of, point}`): proof for the dashboard, never drawn
together on one scheme. Optional `footprint` (`{image_id, polygon}`, same top view): the building's roof outline,
so Halo draws the real block instead of a schematic one. Holo points once at the roof; **code** computes the polygon
(threshold + flood fill from that point, simplified to ≤ 16 vertices), as for `plan.read` zones. Seraph copies it
to `building.footprint` (with `source`). Absent = Halo keeps its schematic block through the entrances.
Screenshots: `sv-front-01`, `sv-left-01`, `sv-right-01`, `earth-front-01`, `earth-left-01`, `earth-rear-01`,
`earth-top-01` (whatever was reachable). Accept cookie consent first. If Earth's 3D doesn't render, keep Street View
and Maps satellite only and say so in `error` (status stays `ok`).

## 3. `georisques.risks`
params `{ address: string }`
Does: Géorisques → « Connaître les risques près de chez moi » → type the address → results page → read the list.
output `{ "risks": [{"label":"Inondation par remontée de nappe","category":"naturel"}, …], "url": "…" }`

## 4. `weather.wind`
params `{ town: string }` (e.g. "Paris 9e")
output `{ "dir_deg": 270, "dir_label": "ouest", "speed_kmh": 20, "observed_at": "…", "url": "…" }`

## 5. `plan.read`
params `{ image_path: string, level: number }` — the plan posted at the door. Demo (TU Wien): the IFC's R-1 plan
`ifc/out/levels/L-1.svg` (copy in `contracts/fixtures/levels/`) rendered to PNG at 1000×1000, so its 0–1000 frame is
the frame of `ifc-L-1`; the IFC zones win, the plan cross-checks them.
Does: opens the image in the browser at full size, Holo points at named elements. Names: `stair:<id>`,
`exit:<id>`, `room:<label>`, `riser` (colonne sèche), `gas_cutoff`, `electric_cutoff`, `extinguisher`, `elevator`,
`you_are_here`. Then **code** computes zones: threshold the image, close door gaps (dilate walls), flood-fill from
each room/stair point → polygon (0–1000 grid). Models point; code draws.
output
```json
{ "level": -1, "image_id": "plan-l-1-01",
  "points": [{"name":"stair:A","label":"Escalier A","point":{"image_id":"plan-l-1-01","x":600,"y":685}}, …],
  "zones":  [{"name":"room:-1.11","polygon":[[852,940],[824,939],[824,551], …]}, …] }
```

## 6. `occupants.list`
params `{ building: string }`
output `{ "occupants": [{"id":"OCC-01","name":"…","phone_e164":"+33…","level":3,"room":"3.12","language":"fr","notes":""}] }`
Phone numbers go only to Gabriel (`place_calls`). Screens show them masked.

## 7. `dispatch.write_112`
params `{ incident_id, entry_fr: string }` — e.g. « 01:12 Appel Léa Martin : deux personnes chambre 3.12, fumée
sous la porte. » Does: incident page → « Main courante » → type → « Ajouter ». Verifies the entry appears in the list.
output `{ "ok": true, "entry_id": "…" }`

## 8. `report.fill`
params `{ incident_id, gate_id, sections: { chronologie: string, moyens: string, victimes: string, observations: string } }`
(Rosetta refuses the run without a `gate_id`.)
Only called after gate `send_report` is confirmed. Fills each section, « Enregistrer », then « Transmettre ».
Verifies the status « Transmis ». output `{ "ok": true, "report_id": "CR-…", "url": "…" }`
