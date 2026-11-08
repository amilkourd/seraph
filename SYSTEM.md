# Seraph — the whole system on one page

If you read one file, read this one. Details live in `contracts/` and `docs/`; this file decides.

## In one minute
A fire is declared in a building (an EXERCICE: a real architect's IFC, TU Wien, placed at the exercise address). While the crew drives, **Rosetta**'s H
agents read every screen that matters (Google Maps/Earth, Géorisques, the plan posted at the door, the dispatch
software, the building manager's occupant list). **Seraph** adds the building's **IFC model** (walls, doors, stairs, materials,
fire ratings) and turns it all into one picture, picks the best entrance,
and **Gabriel** gives the crew a 20-second briefing on the radio while **Halo**, the phone on the firefighter's
forearm, draws the way in. Gabriel phones every occupant and takes the incident's 112 calls; each call becomes a
line on the radio and a dot on the building. When an occupant heads down the only stair into smoke, Seraph proposes
to keep them home, door closed, on their balcony (a ladder point), and the commander says « confirme »; Halo marks that balcony as a ladder point. Teams show on the building as positions.
Every Halo screen is built for that moment by **Devin**, through **Silex**. At the end, the report writes itself in
the legacy report software.

## What we keep, what we cut
| Keep (core demo) | Roadmap (only once the core is green) | Cut |
|---|---|---|
| Talkie crew channel + Gabriel on the radio | Learning a new source live (`/explore` → new endpoint) | Holographic helmet |
| Gabriel call agents: web calls guaranteed, real phone calls if SIP works | `weather.wind` (Météo-France) | Victim register / SINUS-style tracking |
| Rosetta: 7 endpoints (below) with the agent cam | `inside_route` view (beyond the 2 core views) | Hazmat |
| Seraph: state, catches, gates, routes, moments | Spanish on calls (fr + en are core) | Multiple incidents |
| Silex + Devin: 2 views built live (`approach`, `occupants` with the ladder points) | | Native apps, real fire-service systems |
| Halo shell, kit, fallback view | | ARI air tracking (exit time, T-5 alarm, `team_engaged` « Mon air » view): roadmap, Seraph keeps it behind `ARI_ENABLED` (off) |
| Dashboard on the projector | | |
| Report written by Rosetta in the replica, gated | | |
| Building model: a real architect's IFC (TU Wien, `ifc/`) → routes, level plans, ladder points, 3D on the dashboard | The venue's own IFC | 3D on Halo |

## The parts
| Part | One line |
|---|---|
| **Seraph** (`seraph/`) | The brain. Holds the incident state, turns speech and screens into events, runs the catches, gates every order through the commander, computes routes, decides what Halo shows. |
| **Gabriel** (`gabriel/`) | The voice. One agent on the crew radio channel, one agent per phone call. Listens with Gladia, speaks with TTS, never decides. |
| **Rosetta** (`rosetta/`) | Computer use. Our own H agent loop operates websites and legacy apps that have no API, points at things on screenshots, streams its screen to the dashboard. |
| **Silex** (`silex/`) | Tool creation. Sends Seraph's view requests to Devin and serves the views Devin builds. |
| **Halo** (`halo/`) | Phone A on the forearm. Shows the current view, feeds it live data, shows alerts, falls back to a plain list. |
| Talkie (`talkie/`) | Phone B: push-to-talk crew radio. Also the web-call page for occupants. |
| Replicas (`replicas/`) | Dispatch, report, building manager: old-school web apps with no API, standing for what fire services and building managers run. |
| Dashboard (`dashboard/`) | The projector: everything, live. |
| Building model (`ifc/`) | The building's IFC turned, once and offline, into the routing graph, rooms, doors, materials, one plan per level and a 3D model. A file, not computer use. |

## Websites and software Rosetta touches (the allowlist)
| Endpoint | Site / software | What the agent does on screen | What we get | Real? | Access |
|---|---|---|---|---|---|
| `dispatch.read` | Dispatch replica `:8101` | logs in, opens the open incident | address, nature, level, caller notes | replica | read |
| `maps.building` | google.com/maps (Street View) + earth.google.com (3D) | searches the address, Street View front and sides, orbits the block in Earth 3D, top view | 5–7 screenshots, storeys, the IFC's entrances found outside, hydrant, truck spot (pointed by Holo) | **real** | read |
| `georisques.risks` | georisques.gouv.fr | types the address, picks the suggestion, reads the risks | risks near the address | **real** | read |
| `plan.read` | the plan posted at the door (demo: the IFC's R-1 plan rendered, `ifc/out/levels/L-1.svg`) | opens the image, Holo points at the stair, lift, rooms, cut-offs (for buildings without IFC; in the demo it cross-checks the IFC) | named points + zones (computed by code) | **real photo** | vision |
| `occupants.list` | Building manager replica `:8103` | logs in, opens the building, reads the occupant table | names, level, room, phone, language | replica | read |
| `dispatch.write_112` | Dispatch replica | opens the incident, types a main-courante entry, adds it | each call logged on the incident | replica | write |
| `report.fill` | Report replica `:8102` | fills the 4 sections, saves, sends | the finished report | replica | write, gated |
| `weather.wind` | meteofrance.com | searches the town, reads wind | direction, speed | **real** | read |
Never on our own apps. Public sites read-only. Writes only in replicas.
A question no endpoint covers (`/explore`): **Linkup** finds the official pages, the H agent opens one and reads the
answer on screen, « source non vérifiée »; Devin can then compile it into a new endpoint.

Not computer use: the building's **IFC** (`docs/10-ifc.md`), the file the fire service would hold. « L'IFC donne
l'intérieur, Rosetta donne tout le reste. » No open IFC of a real French building exists: a venue's would be rebuilt
from its posted plans; the demo uses a real architect's IFC (TU Wien, CC BY 4.0) placed at the exercise address, labelled
on every screen.

## How the H agents work (Rosetta)
1. Seraph calls `POST /run {endpoint, params}`. Rosetta opens a headed Chromium (Playwright) on the laptop.
2. Loop, max 30 steps: take a screenshot → send it to **Holo** (H's API, OpenAI-compatible) with the skill's goal
   and hints → Holo answers one action in JSON (`click x,y` on a 0–1000 grid, `type_text`, `scroll`, `drag`,
   `go_back`, `answer`) → Rosetta executes it → wait 800 ms → next screenshot. Only the last 3 screenshots stay in
   the context. Errors are sent back so Holo corrects itself.
3. On `answer`, **code** checks the page and extracts the data itself (it never trusts text the model typed).
4. **Pointing:** for screenshots that matter, a second Holo call: « find the side door (from the IFC's list of
   external doors), the hydrant, a place to park
   a fire engine » → points on the 0–1000 grid. For the plan, Holo points at stair A, the lift, each room; code
   flood-fills the zones.
5. Every screenshot is saved and returned. They feed the dashboard and become **Devin's visual references**.
6. Each step is pushed to the dashboard's **agent cam** (screenshot, action, short thought).
7. Up to 4 browsers in parallel. The last good live result for the reference address (`DEMO_ADDRESS`) is cached;
   a cached answer is always labelled « cache ». No fake steps, ever.

## How Seraph works
A loop: **input → event → state → rules → actions → stream.**
- **Inputs:** the building model loaded at start (`ifc/out/building.json`, no incident in it: fire and smoke come only
  from the alert record, calls and the radio), radio transcripts and call facts (from Gabriel), endpoint results (Rosetta), view news (Silex),
  dashboard clicks, Halo taps.
- **Events:** an LLM with a strict JSON schema turns each radio line into one event (`question`, `hazard`,
  `team_update`, `view_request`, `order_to_occupants`, `confirm`, `cancel`, `report_request`, `sitrep_request`,
  `chatter`). Call facts arrive already structured.
- **State:** one `IncidentState` (building, hazards, occupants, calls, teams, routes, gates, Halo, timeline).
- **Computed by code, never by a model:** best entrance (no fire between it and the stair; with one stair, the fire decides), routes (shortest path on
  the IFC's graph avoiding smoke and fire, ladder points as rescue targets), every position on Halo.
- **Catches (rules):** occupant heading into smoke → gate (another stair if there is one; one stair: stay home,
  door closed, balcony = ladder point) · wheelchair or injury → alert · no answer → « sans
  nouvelles » · team announcing a route through smoke → warning · entrance now blocked →
  new approach.
- **Building questions:** materials, fire doors, what's on a level → read from the IFC, source « IFC »; absent →
  « pas dans la maquette ». Never guessed. Radio and calls override the model (a blocked door is blocked).
- **Gates:** the standing instruction (stay put), any order to occupants (flat by flat, or everyone at once), any
  reroute, sending the report. Seraph asks on the radio, acts on « Seraph,
  confirme » or the dashboard button, drops on « annule » or after 2 min.
- **Moments:** dispatch → `approach` view; calls with facts → `occupants` view (floors, people, ladder points) (roadmap:
  `inside_route`, anything the commander asks). `team_engaged` is cut with ARI.
- **Actions:** `say` to the crew or to one/many calls, `place_calls`, Rosetta runs, view requests, dispatch log
  entries, the report.

## How Gabriel works
- **Radio agent** on the LiveKit room `crew`: Gladia transcribes each push-to-talk turn (the talkie sends
  « end of transmission »), sends it to Seraph, speaks Seraph's replies when the channel is free. Call sign: Seraph.
- **Call agents**, one per call (room `call-<id>`): first sentence « Exercice. Bonjour, ici Gabriel, l'assistant
  vocal des pompiers. » in the caller's language; asks where they are, how many, smoke, injuries, what they're doing;
  sends facts to Seraph after each answer; says only questions, « je transmets », « restez en ligne », the standing
  instruction the commander confirmed, and Seraph's gated messages. Never promises help.
- Outbound to opted-in participants, inbound on the incident's number; web calls from the talkie if SIP fails.
- **Gladia, used fully** (`docs/06-gabriel.md`): fr/en/es with code-switching, custom vocabulary (fire jargon, the
  building's ids, the occupants' names), custom spelling for the formatted radio formulas, audio enhancer, radio + 6
  calls in parallel, and **live emotion analysis on calls**: distress, fear or pain in a caller's voice raises that
  call's urgency (computed by Seraph code, « selon la voix »), never an instruction.

## How Silex builds the schemes (Halo views)
1. Seraph decides a moment and sends `ViewRequest`: the purpose in one French sentence, which state fields to read,
   the Rosetta screenshots and the IFC level plans to use as references, the interactions, a deadline (5 min for `approach`).
2. Silex copies the references to a public URL, snapshots the current state, and sends Devin one message built from
   `silex/devin/view-playbook.md`: « copy `halo/kit/examples/approach.html`, use only the Halo kit, draw from these
   state fields, take shapes from these screenshots, never compute a position, send `seraph:ready` ».
3. Devin writes `views/<id>/index.html` (~150 lines: a few kit calls like `Halo.block`, `Halo.street`,
   `Halo.marker`, `Halo.arrow`). Silex checks it (only the kit, no network, small), serves it, tells Seraph.
4. Halo swaps to it. From then on the view moves by itself with every state update; no rebuild.
5. Speed: Devin takes minutes. That's why the request is sent **at dispatch** (the drive is the build window) and
   why Silex keeps a warm Devin session. Until the view lands, Halo shows the fallback list, labelled.
Example, `approach`: building block from above, boulevard Bessières, the truck at the truck spot, a flowing arrow to E1,
the hydrant, E2 crossed out because the ramp leads into the garage on fire, each element with its source tag; every
point on the same top view (`earth-top-01`).

## Halo, on the wrist
One idea at a time, huge, phosphor green on black, amber warnings, red danger. Top bar EXERCICE + clock. Alerts
vibrate and cover the view for 8 s. Status line « Vue construite par Devin à 00:31 » or « Vue de secours », plus the building model's provenance.

## The dashboard (projector, live)
Fed by Seraph's event stream, Rosetta's agent cam, Silex's session list. 1920×1080, dark, readable from 5 m.
| Zone | What it shows |
|---|---|
| Top bar | EXERCICE, incident, address, clock, status, one health dot per service |
| Left: radio and calls | Crew channel transcript (speaker, time, text; Seraph in another colour) · one card per call (who, language, status, one-line summary) · **pending gates on top** with the exact sentence and Confirmer / Annuler |
| Center: the building | **3D model from the IFC**, levels slightly apart, slow orbit: rooms coloured by smoke/fire, people dots by status (safe, sheltering, moving, needs help, no news), teams on their level, provenance label (side view as fallback) · under it, the live **Halo mirror** with « construite par Devin à … » |
| Right: computer use | **Agent cam** tiles (live screenshot, action, thought, LIVE/CACHE, seconds) · counter « 7 sources sans API → 7 endpoints » · Devin sessions (purpose, elapsed, link) · the screenshots sent to Devin |
| Bottom | Measured latencies (voice → answer, call → crew, request → view) · alerts ticker |
Controls: Déclencher, Appeler maintenant, Réinitialiser, Rejouer; keys `Space` confirm, `Esc` cancel, `V C F G R`
fallbacks, `1–5` force a Halo moment.

## One incident, end to end
| When | What happens |
|---|---|
| T-15 | The TU Wien IFC is already loaded (levels, one stair, doors, ladder points). Amil clicks « Déclencher ». Rosetta: dispatch.read → then maps.building, plan.read, georisques.risks, occupants.list in parallel (agent cams light up). Seraph asks the COS to confirm the standing instruction (stay put). |
| T-14 | Occupants listed → Gabriel calls everyone. Maps done → Seraph picks E1, Gabriel briefs the crew, Silex asks Devin for the `approach` view. |
| T-10 → T-1 | Calls bring facts (3.12 two people, smoke under the door; 2.01 wheelchair; no answer in 1.11; witness: smoke out of the garage ramp…); dots appear; Devin's view lands on Halo. |
| Live run | « Quelle entrée ? » → spoken answer + arrow · a participant's phone rings, live call → radio line · Tom starts down the smoky stair → « Je lui dis de rester dans son logement, porte fermée, et d'aller sur le balcon ? » → « Confirme » → ladder point 2.17 · « Levée du confinement : dis à tous les occupants de sortir par l'escalier A » → « Confirme » → every caller at once · « Fais le rapport » → « Confirme » → Rosetta fills it on screen · « La porte du garage est coupe-feu ? » → « EI2 30-C-Sm, source maquette ». |

## What can break, and what we do
| Breaks | Fallback (always labelled) |
|---|---|
| Gabriel's voice on phones | Laptop speaker |
| SIP / real calls | Web call page from the QR |
| Devin late | Halo fallback list « vue de secours » |
| A live site (captcha, Earth 3D) | Golden-path cache « cache » |
| A live line missed on stage | Replay that fixture line (`R`) |
| TU Wien model fails to load | Fictional R+5 (`ifc/out-dev`) « bâtiment fictif » |
| 3D too heavy on the projector | Level plans only |

## Where the details are
`CLAUDE.md` rules and ownership · `contracts/types.ts` every message · `contracts/api.md` every endpoint ·
`contracts/rosetta-endpoints.md` · `contracts/halo-views.md` · `docs/01-architecture.md` flows ·
`docs/02-scenario.md` building and people · `docs/10-ifc.md` building model · `docs/07-safety-rules.md` · `docs/03-demo-script.md` ·
`briefs/<session>.md` your job.
