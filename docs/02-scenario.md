# Scenario — EXERCICE (fictional fire, every screen says so)

**« EXERCICE — Feu de local technique, 3e étage, bâtiment R+5 »** at the hackathon venue's address
(`DEMO_ADDRESS` in `.env`; Amil fills it from the Luma page). The jury sits in the building that is "on fire".
For development, everything below exists in `contracts/fixtures/` so nobody needs the venue.

## The building (`fixtures/building.json`, `fixtures/plan-level3.svg`)
- R+5: levels 0 (RDC) to 5. Two stairs: **A** (north, left on the plan) and **B** (south, right, next to the
  technical room). Elevator next to stair A (not to be used).
- Entrances: **E1** main entrance on the boulevard, opens on the hall of stair B. **E2** side door on the side
  street, opens directly on stair A.
- Level 3: open space 3.10, meeting room 3.12, kitchen 3.14, technical room 3.T (**fire origin**), corridor. Dry
  riser (colonne sèche) in stair A. Gas cut-off in 3.14.
- Hydrant H1 on the side street, ~40 m from E2. Truck spot: side street, in front of E2.
- **Best entrance (computed): E2** — « E2 donne directement sur l'escalier A, dégagé ; E1 donne sur le hall de
  l'escalier B, enfumé. »
- Wind: west, ~20 km/h. Géorisques: a couple of natural risks (mock), nothing industrial.

**Switching to the venue (`docs/10-ifc.md`).** This fictional R+5 is the dev building (`ifc/dev/`). When the venue's
IFC passes its checks, its `ifc/out/building.json` replaces the fixture and Amil rewrites rooms, occupants, radio and
call lines on the real layout. The real layout must give: two escape routes (stair A clear, stair B the one in
smoke — or two exits), the fire in a room next to B, the same ids where possible (`stair:A`, `stair:B`, `E1`, `E2`).
The entrance photo still feeds `plan.read`.

## Occupants (`fixtures/occupants.json`, seeded in the occupants replica)
| Id | Name | Level / room | Language | What the call will say (fixtures/calls.jsonl) |
|---|---|---|---|---|
| OCC-01 | Léa Martin | 3 / 3.12 | fr | In 3.12 with a colleague, smoke under the door, staying put |
| OCC-02 | Karim Benali | 3 / 3.10 | fr | No answer |
| OCC-03 | Sophie Durand | 4 / 4.05 | fr | Safe, sheltering in 4.05, no smoke |
| OCC-04 | Tom Becker | 4 / 4.02 | en | Going down the south stairs (= B, smoke) → **the catch** |
| OCC-05 | Inès Rahmani | 2 / 2.01 | fr | Wheelchair user, cannot go down alone → needs help |
| OCC-06 | Lucía García | 5 / 5.01 | es | No smoke, asks what to do → « restez en ligne, je transmets » |
| JUDGE-n | (opt-in via QR) | any | any | Live: whatever they say |

## The crew (LiveKit room `crew`)
COS (Amil, phone B talkie) · Tête (chef d'agrès FPT) · Binôme 1 (B1) · Binôme 2 (B2). In the demo, Amil voices the
COS and, if needed, Tête/Binôme lines; a judge can hold the talkie too.

## Timeline of the incident (real time, compressed for the demo)
| T | What happens | Who |
|---|---|---|
| T-15 min | Amil starts the incident from the dashboard (= dispatch). Rosetta runs 6 endpoints; Silex starts the `approach` view; Gabriel calls every occupant | Seraph |
| T-14 → T-1 | "The drive": Devin builds the approach view; calls come in; facts land on the floor stack | all |
| T0 (pitch starts) | Halo already shows the approach; dashboard shows the Devin session that built it | — |
| demo | Tête asks « quelle entrée ? » → spoken answer + arrow on Halo | Seraph, Gabriel |
| demo | A judge's phone rings (or calls 112): live call → facts → crew summary | Gabriel |
| demo | Tom heads to stair B → gate « je lui dis de prendre A ? » → « confirme » → told in English | Seraph, Gabriel |
| demo | « Binôme 1 engagé, 300 bars » → Halo switches to air tracking (Devin) → countdown | Seraph, Silex |
| demo | « Seraph, fais le rapport » → gate → `report.fill` on screen | Rosetta |
| optional | « Seraph, il y a une crèche dans la rue ? » → Rosetta explores live → new endpoint | Rosetta, Silex |

## ARI air (simplified, labelled « calcul simplifié » on every screen)
`exit_by = entered_at + (pressure_bar_start − 60) / 8 bar·min⁻¹ × 0.5` (half the usable air to go in, half to come
out). With 300 bar: (300−60)/8 = 30 min → exit after 15 min. Demo factor `ARI_TIME_FACTOR` (default 10) compresses
time so the T-5 min alarm happens during the pitch. This is a demo rule, not the real ARI procedure.
