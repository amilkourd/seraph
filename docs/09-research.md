# Research (what we checked, with sources)

## Grenfell Tower (London, 14 June 2017) — the hook
- 72 dead. Phase 1 inquiry: the London Fire Brigade did not know how combustible the cladding was; communications
  failed and command and control had serious deficiencies; the way caller information was processed and shared with
  ground commanders was criticised; « stay put » was not lifted while the stairs were passable, which cost lives;
  no evacuation plan was a "major omission".
- Sources: https://en.wikipedia.org/wiki/Grenfell_Tower_Inquiry_Phase_1 ·
  https://theconversation.com/grenfell-tower-inquiry-expert-explains-four-main-findings-and-how-emergency-services-must-improve-126163

## Lantern — 1st overall, {Tech: Europe} × VEED, London, 22 Aug 2026 (H Company was a partner)
- Pitch: « Know the building before you go through the door. » The inside of the house is already online in the old
  sale listing, the 999 call says where the fire is, « nobody has ever connected the two ».
- Flow: 999 call transcribed → address, fire room, victim → in parallel: Street View + satellite read by GPT-5,
  and a Holo agent that finds the Rightmove listing (photos + floor plan) → floor plan: the model **points** at room
  labels on a grid, code computes room areas by flood fill (« VLMs point far more reliably than they box ») → route by
  BFS in code avoiding fire rooms → crew card with a source tag on every fact → fal video walkthrough.
- H usage: Holo 3.1 via `https://api.hcompany.ai/v1/` with the OpenAI SDK, their own loop on Playwright (screenshot
  each turn, keep the last 3, structured tool calls on a 0–1000 grid, errors fed back), the model only navigates and
  **code reads the page** (« the model's URL can be hallucinated »).
- Weak spots: one site (Rightmove), demo replayed from cache with stub agent steps, agent screen never shown.
- What we take: pointing + code geometry; code routes; source tags; own agent loop; golden-path cache.
  What we do better: computer use visible and central (agent cam, 8 endpoints, writes, learning), the people inside
  (calls both ways), the wrist device, Devin building views live.
- Source: https://github.com/omorros/Lantern · event https://luma.com/london-summer-lock-in

## Firefighter / emergency hackathon winners (patterns)
| Event | Project | Prize | Idea |
|---|---|---|---|
| Cal Hacks 13 (Oct 2026) | Standard Response | 7 prizes | Voice agent calls every home in a wildfire zone; Eaton Fire replay 641/662 vs 39 households; « never says help is coming until a driver accepts » |
| UC Berkeley AI (Jun 2026) | FireflAI | Fetch.ai | Listing link + 911 call → 3D interior + route |
| TreeHacks (Feb 2026) | ContainOS | OpenAI track | Wildfire commander copilot, physics checks the AI |
| GenAI Zürich (2026) | Onics | 3rd | Building plans → fire-brigade orientation plans (Swiss standard) |
| Reboot the Earth (2025) | FireForm | 1st | Firefighters speak, AI fills CAL FIRE paperwork |
| ElevenLabs Global (Dec 2025) | Sentinel | Global winner | Disaster distress-call voice agent, multilingual |
| UC Berkeley AI (2024) | DispatchAI | Grand prize | 911 copilot, human makes the final call |
| Runner H (H × DEV, 2025) | CrisisCopilot | $500 | The only computer-use winner found, small |
Patterns: real disaster + hard number; judges take part; two screens (field + command); human in charge enforced in
code; sponsor stacking. Computer use is almost absent → our opening.
Sources: devpost.com/software/standard-response · /fireflai · /containos · /onics · /dispatch-ai ·
news.ucsc.edu/2025/11/ai-solutions-wildfire-mitigation-reboot-the-earth-hackathon/ ·
dev.to/devteam/congrats-to-the-runner-h-ai-agent-prompting-challenge-winners-3aap

## Building plans for firefighters in France
- No public national database. ETARE pre-plans are shared between the operator and the fire service and not meant
  to be distributed. Public buildings (categories 1–4) must post a simplified plan for firefighters at each entrance
  (service-public.fr). A building-industry blog says an arrêté of 1 Dec 2025 extends this to all public buildings
  from 1 Jan 2026, paper only — **not verified on Légifrance; check before quoting**.
- BatiFire (SDIS de l'Ain, BatiSafe Digital): app with plans and data sheets reached by a QR code on the facade;
  special mention, Oscars de la sécurité incendie 2021 — shows the need, stuck in one department.
- Sources: https://entreprendre.service-public.gouv.fr/vosdroits/F31684 ·
  https://www.construires.fr/erp-plan-intervention-obligatoire-2026-arrete-decembre-2025/ ·
  https://securite-civile.gouv.nc/sites/default/files/documents/Guide_ETARE.pdf

## Other facts we may use
- French fire services: 4,754,811 interventions in 2024, 256,379 firefighters, 78% volunteers (DGSCGC 2025 edition,
  from earlier research in the Win Plan doc).
- GDPR allows processing to protect someone's vital interests (Art. 6(1)(d)) — the legal basis for calling
  occupants during an incident; keep it incident-only and logged.

## IFC and digital building information (searched 02:00 Sunday)
- **England, post-Grenfell:** Fire Safety (England) Regulations 2022, in force 23 Jan 2023. For residential buildings
  of 18 m+ or 7+ storeys the responsible person must give the fire and rescue service up-to-date **electronic floor
  plans**, put paper plans and a one-page building plan in a **secure information box**, give the **design and
  materials of the external wall system** (and notify changes), and install wayfinding signage readable in smoke.
  Sources: https://www.gov.uk/government/publications/fire-safety-england-regulations-2022/fact-sheet-overview ·
  https://www.legislation.gov.uk/uksi/2022/547/made
- **France:** paper plan at each ERP entrance, no national database (above). No open IFC of a real French building
  found: OSArch AEC open data directory (https://wiki.osarch.org/aec-open-data-directory/) lists portals only;
  opensourceBIM/IFC-files (CC BY-ND, no named real building); awesome-bim-datasets (only France entry: Paris-Lille-3D
  point cloud); HMD Solution article (no named building, no files); académie de Lille BIM page (not readable by our
  tools). TUM GNI-BIM dataset = student projects (CC BY 4.0, https://github.com/ZijianWang-ZW/GNI-BIM-Dataset).
- **Real IFC, abroad (test only):** TU Wien « Real-World Escape Route Test Model », Vienna, IFC4 (Archicad 26),
  CC BY 4.0, 12.9 MB, standard + escape-route properties; building use not stated.
  https://researchdata.tuwien.ac.at/records/2heb4-xqb83 · https://b2find.dkrz.de/dataset/dd9e4c07-dcb7-5286-b9b0-3b0cba995c75
- **IFC fields we read:** `IfcBuildingStorey`, `IfcSpace`, `IfcDoor`, `IfcStair`, `IfcWall` + `IfcMaterial*`,
  `Pset_WallCommon.FireRating` / `IsExternal`, `Pset_DoorCommon.FireRating`, `IfcRelSpaceBoundary` (often missing).
  Tooling: IfcOpenShell 0.8+ (`ifcopenshell.api`, `ifcopenshell.util.element`, `ifcopenshell.geom`), trimesh → glb.
