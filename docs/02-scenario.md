# Scenario v2 — EXERCICE on the TU Wien building (every screen says EXERCICE)

**« EXERCICE — Feu de véhicule au parking souterrain, fumée dans l'escalier, immeuble R+3 »** at `DEMO_ADDRESS`
(`.env`: « 96 Boulevard Bessières, 75017 Paris », the venue). The building is a **real architect's IFC** (TU Wien « Real-World Escape Route
Test Model », CC BY 4.0) placed at the exercise address: provenance « Maquette IFC réelle (TU Wien, CC BY 4.0) —
adresse d'exercice » on every screen (the real building at that address is not this one). Everything below exists in `contracts/fixtures/`; ids come from
`ifc/out/building.json` (extractor 1.2.0, building map in `status/ifc.md`).

## The building (`fixtures/building.json` = `ifc/out/building.json` + what Rosetta brings from outside)
- Residential block, **R-1 to R+3**. R-1: garage `-1.11` with parking places, ramp `-1.03`, caves `-1.01`, local
  poussettes `-1.04`, local électrique `-1.06` → local technique `-1.08`, all off the basement circulation
  `corridor:-1`. RDC to R+2: two flats per level. R+3: one flat (`U3.1`) with three terraces.
- **One stairwell, `stair:A`** (levels -1 to 3), plus a lift (`room:-1.02`, `0.03`, `1.02`, `2.02`, `3.01`; never a
  route). The stair opens **without a door** on every common circulation (`corridor:-1` … `corridor:3`).
- **Second way out of each flat = the façade**: balconies and terraces, reached by the fire service's ladders.
  Graph nodes `ladder:<room>` (`model.ladder_points`): R+1 `ladder:1.05`, `ladder:1.18` · R+2 `ladder:2.05`,
  `ladder:2.17` · R+3 `ladder:3.04`, `ladder:3.07`, `ladder:3.08`. A ladder point is never an exit on foot.
- Entrances (from the IFC): **E1** « Porte d'entrée, hall de l'escalier », RDC, front, on boulevard Bessières → `corridor:0`
  (EI2 30-C). **E2** « Porte de garage, rampe (sous-sol) », R-1, left side → ramp `-1.03` → garage `-1.11`.
- Flats (`units`): `U0.1` `U0.2` (RDC, terraces 0.01 / 0.14 / 0.20 open to the garden = exits on foot), `U1.1`
  `U1.2`, `U2.1` `U2.2`, `U3.1`. Each flat door is EI2 30-C-Sm.
- Outside, from Rosetta (`maps.building`; fixture values, all on the top view `earth-top-01`): hydrant **H1**
  « Poteau incendie, trottoir du boulevard Bessières », ~30 m from E1 · truck spot « Boulevard Bessières, devant E1 » · E1 on the front
  façade, E2 at the foot of the ramp, rear-left corner · the roof outline `building.footprint` (optional; in the
  fixture, the IFC's R+1 outline placed with E1 on its point).
- Posted plan (`plan.read`): the R-1 plan, rendered from the IFC (`ifc/out/levels/L-1.svg`), `image_id`
  `plan-l-1-01`, same 0–1000 frame as `ifc-L-1`. It cross-checks the IFC; the IFC zones win.
- Wind: west, ~20 km/h (Météo-France, Paris). Géorisques (mock): séisme zone 1 (très faible), retrait-gonflement des argiles.

## The fire and why the stair is in smoke (geometry, from the IFC)
- **Origin: a car on fire in the underground garage `-1.11`** (R-1). Smoke leaves by the ramp (`-1.03` → E2) and,
  through the garage fire door **P-1-5** (EI2 30-C-Sm, self-closing, found wedged open), fills `corridor:-1`,
  which opens on `stair:A` with no door. The single stair fills with smoke from the bottom up.
- **No hazard is pre-placed.** Fire and smoke appear on a screen only once a source reports them, and every line
  that uses one says its source (« selon l'alerte », « selon l'appel », « selon Tête »). See the table below.
- **Best entrance (code): E1.** E2's path to the stair crosses the garage on fire (impassable); E1 opens on the stair
  hall at RDC. Expected reason: « E1 donne sur le hall de l'escalier A ; E2, la rampe, passe par le garage en feu
  selon l'alerte. »
  The stair is the same for both (one stair, in smoke): the fire decides, not the stair.
- Rescue before attack: B1 goes **up** stair A from E1 under ARI (sauvetages). The attack on the car (B2) can use
  the ramp later; that is not in the demo.

## How each hazard arrives (and is said)
| Hazard | First source | Then | Said as |
|---|---|---|---|
| Fire, garage `{level:-1, room:"-1.11"}` | `dispatch.read`: nature « Feu de véhicule en parking souterrain », level -1 | R02 Tête « feu de véhicule au parking » (crew) | « selon l'alerte », then « selon Tête » |
| Smoke, `stair:A` | `dispatch.read` caller note « Fumée dans la cage d'escalier » | CALL-02 Tom « There's some smoke » · R02 Tête « fumée dans la cage d'escalier » | « selon l'alerte », then « selon Tête » |
| Smoke, `entrance:E2` (ramp) | `dispatch.read` caller note « Fumée qui sort de la rampe du parking » | CALL-03 112 witness | « selon l'alerte », « selon l'appel » |
| Smoke, R+3 `{level:3}` | CALL-01 Léa « fumée sous la porte » | — (stays « signalé ») | « selon l'appel » |
| Smoke, R+3 landing `corridor` (level 3) | R04 Binôme 1 « circulation enfumée » | — | « selon binôme 1 » |
| Stair A cleared | R13 Tête « escalier A désenfumé » | — | « selon Tête » |
Code maps the words to ids: « parking / garage » on level -1 → `-1.11` (IFC label Garage); « cage d'escalier » →
`stair:A` (the only stair); « rampe » → `entrance:E2`. A hazard keeps its latest source; the stair status follows it.
**Signalé vs confirmé:** what the alert centre or a caller reports is « signalé » (`source.confirmed: false`, drawn
as inferred) until a firefighter says it on the radio, which flips it to confirmed (R02 for the fire and the stair).
The ramp smoke stays « signalé » in the story: no crew line confirms it.

## The Grenfell link (say it, show it)
Grenfell Tower had **one staircase**. Residents were told to stay put; the advice was only lifted at 02:47, nearly
two hours after the first call. Seraph does the opposite of guessing:
1. **Stay put is a commander's decision.** At T-15 Seraph proposes the standing instruction (gate `relay_order`):
   « Consigne par défaut aux occupants : si fumée dans l'escalier ou devant la porte, rester chez soi, porte
   fermée. Confirmez ? » Gabriel says it only after « confirme », and only to callers at home who report smoke.
2. **Flat by flat.** Anything else is one gate per flat: Tom going down the smoky stair (stay + balcony), Lucía
   asking what to do (« Consigne ? »), Inès who cannot go down.
3. **Liftable for everyone in one sentence.** « Seraph, levée du confinement : dis à tous les occupants de sortir
   par l'escalier A. » → one read-back → « confirme » → every caller hears it at once, in their language.

## Occupants (`fixtures/occupants.json`, seeded in the occupants replica)
Night (00:25): people are home, mostly in bedrooms. Fictional people, non-dialable numbers.
| Id | Name | Level / room (flat) | Language | What the call says (`fixtures/calls.jsonl`) | Beat |
|---|---|---|---|---|---|
| OCC-01 | Léa Martin | R+3 / 3.12 Chambre (U3.1, terrace 3.07) | fr | With their son, smoke under the door, staying | sheltering, urgent; B1's target |
| OCC-02 | Karim Benali | R+1 / 1.11 Chambre (U1.2) | fr | No answer, twice | « sans nouvelles » |
| OCC-03 | Sophie Durand | R+1 / 1.01 Chambre (U1.1) | fr | At home, door closed, no smoke | safe, sheltering |
| OCC-04 | Tom Becker | R+2 / 2.16 Séjour-cuisine (U2.2, balcony 2.17) | en | Leaving the flat, going down the stairs, some smoke | **the catch** |
| OCC-05 | Inès Rahmani | R+2 / 2.01 Chambre (U2.1) | fr | Wheelchair user, cannot go down alone | needs help |
| OCC-06 | Lucía García | RDC / 0.19 Séjour-cuisine (U0.2, terrace 0.20) | es | No smoke, asks what to do | « restez en ligne, je transmets » |
| LIVE-n | (opt-in via QR) | any | any | Live: whatever they say | — |
Floors are counted the French way (RDC = 0, « second floor » = R+2). Callers name their floor and the kind of room;
the room id comes from the occupant record.

## The key beat (replaces « Tom, stair B → A »)
1. Tom (R+2) answers: « I'm on the second floor, I'm going down the stairs right now. There's some smoke. » →
   facts `heading_to: "stair:A"`, `current_action: "moving"`.
2. Catch (code): an occupant heads into a node with a hazard and **there is no other stair**. Seraph proposes, on
   the radio and on the dashboard (gate `reroute_occupant`):
   « COS de Seraph : Tom Becker, 2e, descend par l'escalier A, enfumé selon l'alerte, seul escalier. Je lui dis de
   rester dans son logement, porte fermée, et d'aller sur le balcon ? » (« selon Tête » once R02 is said)
3. COS: « Seraph, confirme. » → Gabriel tells Tom, in English (below). Seraph sets Tom `sheltering`,
   `heading_to: "ladder:2.17"`, adds route `evacuation` `room:2.16 → room:2.17 → ladder:2.17`, raises an alert
   « Échelle : balcon 2.17, 2e, Tom Becker », and tells the crew « Reçu. Tom Becker reste dans son logement, balcon 2.17 :
   point échelle. »
4. Halo: the alert covers the view; then 2.17 is drawn as an **active ladder point** (the `to` of an evacuation
   route); the other `model.ladder_points` stay dim. Dashboard: callout « Échelle · Tom Becker » on 2.17.
The balcony is chosen by code: the ladder point of the occupant's flat (`units`) reachable from their room
(2.16 → 2.17 through the French window P2-69); if the flat has several, the one off the room they are in.

## Sentences (exact; Seraph templates, Gabriel speaks them)
| Use | fr | en | es |
|---|---|---|---|
| Standing instruction (after « confirme », callers at home with smoke) | Restez chez vous, porte fermée. Ne prenez pas l'escalier, il est enfumé. Calfeutrez le bas de la porte avec un linge mouillé. Les pompiers sont informés de votre position. Restez en ligne. | Stay in your flat with the door closed. Do not use the stairs, there is smoke. Block the gap under the door with a wet towel. The firefighters know where you are. Stay on the line. | Quédese en su casa con la puerta cerrada. No use la escalera, hay humo. Tape la parte de abajo de la puerta con un trapo mojado. Los bomberos saben dónde está. No cuelgue. |
| Stay + balcony (Tom, after « confirme ») | Les pompiers vous demandent de rentrer chez vous tout de suite et de fermer la porte. Ne prenez pas l'escalier, il y a de la fumée. Allez sur votre balcon pour que les pompiers vous voient. Restez en ligne. | The firefighters ask you to go back into your flat now and close the door. Do not use the stairs, there is smoke. Go out on your balcony so the firefighters can see you. Stay on the line. | Los bomberos le piden que vuelva a su casa ahora mismo y cierre la puerta. No use la escalera, hay humo. Salga a su balcón para que los bomberos le vean. No cuelgue. |
| Hold (no order yet) | Restez en ligne, je transmets aux pompiers. | Stay on the line, I am passing this to the firefighters. | Quédese en línea, estoy transmitiendo su situación a los bomberos. |
| Lift, for everyone (after « confirme ») | Sortez par l'escalier A. | Leave the building by stairway A. | Salga del edificio por la escalera A. |
For a terrace (R+3) the stay sentence says « terrasse » / « terrace » / « terraza » instead of balcony.

## The crew (LiveKit room `crew`)
COS (Amil, phone B talkie) · Tête (chef d'agrès FPT) · Binôme 1 (B1) · Binôme 2 (B2). In the demo, Amil voices the
COS and, if needed, Tête/Binôme lines; a participant can hold the talkie too.

## Timeline of the incident (real time, compressed for a live run)
| T | What happens | Who |
|---|---|---|
| T-15 min | Amil starts the incident (= dispatch). Rosetta runs its endpoints; Silex starts the `approach` view; Seraph proposes the standing instruction (stay put) and the COS confirms; Gabriel calls every occupant | Seraph |
| T-14 → T-1 | "The drive": Devin builds the approach view; calls come in (Léa 3.12 smoke under the door, Inès 2.01 wheelchair, Karim no answer, Sophie safe, Lucía asks); the 112 witness: smoke out of the garage ramp | all |
| T0 (run starts) | Halo shows « Qui est où » (the occupants view outranks approach once calls land); « Quelle entrée ? » brings back the approach (E1, E2 crossed: garage on fire); dashboard shows the Devin sessions | — |
| demo | Tête: « quelle entrée ? » → E1, not E2, single stair in smoke, hydrant | Seraph, Gabriel |
| demo | A participant's phone rings (or calls 112): live call → facts → crew summary | Gabriel |
| demo | Tom starts down the smoky stair → « Je lui dis de rester dans son logement, porte fermée, et d'aller sur le balcon ? » → « confirme » → told in English → ladder point 2.17 on Halo | Seraph, Gabriel, Halo |
| demo | Tête: « escalier A désenfumé » · COS: « levée du confinement : dis à tous les occupants de sortir par l'escalier A » → read-back (except Inès, wheelchair) → « confirme » → every caller, every language | Seraph, Gabriel |
| demo | « Seraph, fais le rapport » → gate → `report.fill` on screen | Rosetta |
| optional | « La porte du garage est coupe-feu ? » → « Porte -1.11 Garage : EI2 30-C-Sm, source maquette » | Seraph |
| optional | « Seraph, il y a une crèche ou une école dans la rue ? » → Rosetta explores live → new endpoint | Rosetta, Silex |

## ARI air tracking: cut (roadmap)
Amil cut air tracking from the demo. Teams are positions only (engaged, level, stair, room): « binôme 1 engagé par
l'escalier A, 300 bars » is answered « Reçu, binôme 1 engagé par l'escalier A. », with no exit time, no T-5 alarm and
no `team_engaged` « Mon air » view. Seraph keeps the code behind `ARI_ENABLED` (off). If it comes back: the
simplified rule was `exit_by = entered_at + (pressure_bar_start − 60) / 8 × 0.5` min, labelled « calcul simplifié ».

## What changed from v1 (fictional two-stair R+5)
| v1 | v2 (TU Wien) |
|---|---|
| R+5, levels 0–5, stairs A (clear) and B (smoke) | R-1–R+3, one stair A (smoke), façade ladders as second way out |
| Fire: technical room `3.T`, level 3 | Fire: garage `-1.11`, level -1 (smoke via P-1-5 → `corridor:-1` → stair A) |
| Best entrance E2 (side door on stair A) | Best entrance E1 (stair hall); E2 = garage ramp, through the fire |
| Tom 4.02 down stair B → « prends A ? » | Tom 2.16 down stair A → « reste dans son logement, porte fermée, balcon ? » → `ladder:2.17` |
| Standing: smoke at the door → stay in the room | Standing: smoke in the stair or at the door → stay home, door closed (stay put, by the COS) |
| — | Lift for everyone in one sentence (R13–R15) |
| Karim 3.10, Sophie 4.05, Inès 2.01, Lucía 5.01, Léa 3.12 | Karim 1.11, Sophie 1.01 (now has a call, CALL-07), Inès 2.01, Lucía 0.19, Léa 3.12 |
| Plan photo `plan-level3.svg` (`plan-l3-01`) | IFC R-1 plan rendered (`plan-l-1-01`, frame of `ifc-L-1`) |
