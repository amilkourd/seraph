# Safety rules (product requirements)

These are what make the jury trust Seraph. Each one must be visible in the demo.

1. **The commander decides, Gabriel relays.** Seraph never decides on its own whether people stay or leave, which
   stair they take, or where a team goes. It proposes on the radio (« Je lui dis de rester dans son logement, porte fermée ? ») and acts only
   after « Seraph, confirme » or the dashboard's Confirmer. Standing instructions (e.g. « si fumée dans l'escalier ou
   devant la porte, rester chez soi, porte fermée ») are proposed once at incident start and need the same confirmation.
   At Grenfell, lifting « stay put » too late cost lives: decisions must flow both ways, fast, and stay human.
2. **Code computes positions and routes; models never guess the arrow.** Holo points at things on screenshots;
   code turns points into zones and computes routes on the building graph, avoiding hazards. Halo views only draw
   what the state contains.
3. **Quote, never invent.** Safety facts are read from a source and Seraph names it on the radio when it matters
   (« selon le plan », « selon l'appel »). No fire or smoke is drawn or said before a source reports it (the alert
   record, a call, the crew radio): nothing is pre-placed. What the alert centre or a caller reports stays « signalé »
   (`confirmed: false`) until a firefighter confirms it on the radio. Every element on Halo and the dashboard carries its source tag; inferred
   facts look different from confirmed ones.
   Emotion heard in a caller's voice (Gladia) is inferred: it raises a call's urgency, labelled « selon la voix »,
   and never becomes an instruction, a position or a reason to skip a gate. Learned sources say « source non vérifiée » until Amil approves them.
4. **Computer use only on software we don't own.** Public sites read-only. Writes only in the replicas (dispatch
   main courante, report). Sending the report is gated.
5. **Occupant data only for the incident.** Names and numbers come from the building manager's software through
   Rosetta, are used to call people about this incident, are masked on every screen, and every access is logged.
   Real calls go only to people who opted in (consent checkbox on `/inscription`).
6. **Never fake it.** Cached results are labelled « cache ». Prebuilt fallbacks are labelled « vue de secours » or
   « version préparée ». Agent steps are never simulated. The demo says EXERCICE everywhere.
7. **Fail visibly, never silently.** Every wait shows what it is waiting for. Every timeout has a fallback the crew
   can still use (plain facts list on Halo, laptop speaker for voice, web call page for phones).
8. **ARI timing is a simplified demo rule**, labelled « calcul simplifié », never presented as the real procedure.
9. **The building model is a source, not the truth.** Building facts come from the IFC or a screen, never from a
   model; unknown stays « inconnu » / « pas dans la maquette ». Its provenance is always on screen (« IFC
   architecte », « reconstruite depuis le plan affiché », « bâtiment fictif »). Radio and calls override it.
