# replicas — status
Updated: 10:25

## Running
- dispatch « Alerte / Interventions » on http://localhost:8101 · public: none · MOCK n/a (local SQLite)
- report « Comptes rendus » on http://localhost:8102 · public: none
- occupants « Gestion des occupants » on http://localhost:8103 · public: only `/inscription` (via `OCCUPANTS_PUBLIC_URL`)
- Run all three: `cd replicas && uv run python run.py` (or `uv run python run.py occupants` for one). Binds 127.0.0.1
  (`REPLICAS_HOST=0.0.0.0` to open the LAN; off-host requests still only reach `/inscription`).
- Test the four Rosetta flows: `cd replicas && uv run python tests/flows.py [shots_dir]` (resets before and after,
  occupants with `scope=all`: never during a rehearsal). To test without touching the live replicas, run a copy with
  `REPLICAS_DATA=<dir>` on other ports and point the test at it with `DISPATCH_URL` / `REPORT_URL` / `OCCUPANTS_URL`.

## Done
- Three server-rendered apps (FastAPI + Jinja2 + SQLite in `replicas/data/*.db`), no JSON API. Login `operateur` /
  `REPLICA_PASSWORD` (root `.env`, re-read on each request). « EXERCICE — données fictives » band on every page.
- Look copied from the real software (no brand): dispatch = Windows-XP-era alert software (blue title bar
  « Intervention N° INC-0001 - [SUIVI] », groupboxes Sinistre / Localisation / Demandeur, navy « INTERVENTIONS EN
  COURS » bands, main courante box); report = 2012 operations portal (blue gradient, pill nav, dark-blue
  « RAPPORT D'INTERVENTION » band, uppercase section bands, grey read-only fields, red required labels);
  occupants = property-manager intranet « PATRIMOINE ». References: Systel STARTOPS manuals and SDIS 63 CRSS
  procedure on enasis.fr.
- Seed (scenario v2, TU Wien building, 05:10): INC-0001 « En cours » with `DEMO_ADDRESS` and the fixture's nature
  (« Feu de véhicule en parking souterrain… »), level -1 and 3 caller notes; 6 main-courante entries written from
  those notes and the building's levels (next is MC-0007) + 5 closed incidents; reports: 5 old « Transmis » (next is
  CR-0001); occupants: building « Immeuble d'habitation (maquette TU Wien) », R-1 à R+3, the 6 from
  `contracts/fixtures/occupants.json`. Everything is read from the fixtures and `BUILDING_JSON` at each reset.
- `/inscription` « Pièce » is a list of the building's bedrooms and living rooms grouped by floor (RDC to R+3), with
  the IFC room ids (`BUILDING_JSON`, else the fixture), so every visitor lands in a room Seraph can place. The floor is
  taken from the room.
- **Visitor's incident (07:10):** « Nouvelle intervention » (`/interventions/nouvelle`) creates an « En cours » incident
  with a free address, nature, level and caller notes (one per line). It gets the next number (INC-0002 after a
  reset), is declared now, so it is the first row of `#interventions tr.inc.open`: Rosetta's `dispatch.read` without
  `incident_id` reads it. Commune is taken from the address's postcode when left empty. `/admin/reset` brings back
  INC-0001 at `DEMO_ADDRESS` as the only open incident. Checked in `tests/flows.py` (« incident du juge »).
- **Report follows the incident (10:25):** « Nouveau compte rendu » (`#btn-nouveau`) opens
  `/comptes-rendus/nouveau?intervention=<newest « En cours » in dispatch>` (no id if none is open), no more fixed
  INC-0001. An id unknown to dispatch is refused: the form answers 404 with « Intervention INC-0099 inconnue dans le
  logiciel d'alerte. » and « Enregistrer » refuses it too. Checked in `tests/flows.py`.
- `/admin/reset`: GET = page with button, POST = restore seed; answers JSON `{ok:true}` (HTML if `Accept: text/html`).
  `GET /health` → `{ok, mock:false, service}` on each app.
- `/inscription` (no login): name, phone, floor, room, language, required consent checkbox with the brief's exact
  sentence. Checked at 390 px wide: no horizontal scroll, consent enforced, private pages 404 from outside.
- Playwright run passes: `dispatch.read`, `dispatch.write_112` (MC-0007), `occupants.list` (6 rows, full E.164 read
  from the DOM), `report.fill` (CR-0001 → Brouillon → Transmis), `/inscription` on a phone viewport.
- **Holo run passes (05:00), `holo4-35b-a3b`, H's agent-loop recipe, code logs in, Holo navigates, code verifies:**
  `dispatch.read` 2 steps / 6 s · `occupants.list` 2 / 4 s · `dispatch.write_112` 5 / 11 s ·
  `report.fill` 12 / 24 s (fills 4 sections, scrolls, Enregistrer, Transmettre; texts match exactly).
  Rerun on the v2 seed (05:10): all four pass (report.fill 12 steps / 68 s; the H API was slower).
  Rerun: `cd replicas && uv run --with openai python tests/holo_probe.py holo4-35b-a3b /tmp/holo-shots`.

## In progress
-

## Blocked
-

## Requests (to other sessions or Amil)
- @Amil: `.env` has `DEMO_ADDRESS="2 rue Madame, 64000 Pau"` but `DEMO_TOWN=Paris 9e`. The replicas take the
  commune from the address's postcode (« Pau »); `weather.wind` uses `DEMO_TOWN`, so fix one of them.
- @seraph @Amil: occupants `POST /admin/reset` **keeps the visitors' `/inscription` sign-ups** by default, so a
  rehearsal reset doesn't wipe them before the pitch. `POST /admin/reset?scope=all` wipes them too. Dispatch and report
  always restore everything.
- @rosetta (Amil): phone numbers. The occupant table shows the full E.164 in the DOM text (`inner_text` of
  `td.c-tel` = `+33100000001`), but the middle digits are CSS-blurred on screen, so agent-cam screenshots on the
  projector show them masked (safety rule 5). Read the number from the DOM, never from the screenshot.

- @rosetta (Amil): **let code log in, not Holo.** Told to type a password placeholder, `holo4-35b-a3b` drops the
  braces or ignores it and starts guessing passwords (« password », « azerty », « admin »…, 25 steps, never in).
  With Playwright filling `#username` / `#password` and clicking `#btn-connexion` first, every flow passes. The model
  then never sees the password either.

- @seraph: `start_incident` calls `dispatch.read` with `incident_id: inc.id` (default « INC-0001 »), so Rosetta opens
  INC-0001 even when a visitor's newer incident is open. Call it without `incident_id` to read the newest « En cours ».

- @rosetta: `report.fill` should carry the id: start at `/comptes-rendus/nouveau?intervention=<incident_id>` and check
  `#cr-intervention` = incident_id on the saved report. The list's « Nouveau compte rendu » only follows the newest
  open incident.

## Facts I verified (API names, model ids, gotchas)
- H API `GET /v1/models` (05:00): `holo3-1-35b-a3b`, `holo3-122b-a10b`, `holo4-27b`, `holo4-35b-a3b`. `HOLO_MODEL` is
  empty in `.env`. Agent loop per hub.hcompany.ai/agent-loop: Step schema `{note, thought, tool_call}` in the system
  prompt's `<output_format>` and in `extra_body={"structured_outputs": {"json": schema}}`; clicks on a 0–1000 grid;
  keep the last 3 screenshots. Works with `holo4-35b-a3b`, temperature 0.6, JPEG screenshots.
- DOM anchors for Rosetta's success checks and extraction (all plain visible text, stable ids):
  - Login (all three): `/login`, labels « Identifiant » `#username`, « Mot de passe » `#password`, button
    « Connexion ». Any private URL redirects to `/login?next=…` and back after login.
  - `dispatch.read`: list `/interventions`, `#interventions tr.inc.open` (newest first), link text = `INC-0001`.
    Page `/interventions/INC-0001`: `#f-numero`, `#f-adresse`, `#f-commune`, `#f-nature`, `#f-niveau`,
    `#f-declaree time[datetime]` (ISO UTC), `#notes-appelant li` (caller notes), `#f-moyens`. `#f-niveau` is the
    integer (`-1`); `#f-niveau-libelle` shows « R-1 » / « RDC » / « R+3 » next to it.
  - New incident: `/interventions/nouvelle`, labels « Adresse » `#adresse`, « Commune » `#commune` (optional),
    « Niveau » `#niveau` (integer, default 0), « Nature » `#nature`, « Moyens » `#moyens`, « Appelant » `#appelant`,
    « Renseignements » `#renseignements` (one caller note per line), button « Déclencher » `#btn-creer` →
    `/interventions/INC-000N`, `#flash` = « Intervention INC-000N créée. »
  - `dispatch.write_112`: same page, textarea label « Message » `#mc-texte` (name `texte`), button « Ajouter ».
    After: `#flash` = « Entrée MC-0007 ajoutée à la main courante. », URL `?ajout=MC-0007`, first row of
    `#main-courante-liste tbody` has `data-id="MC-0007"` and `.c-texte` = the entry.
  - `occupants.list`: `/batiments` → link « Bâtiment d'exercice » → `/batiments/1`. Rows
    `#occupants tbody tr[data-id]` with `.c-nom`, `.c-niveau`, `.c-local`, `.c-tel`, `.c-langue` (fr/en/es),
    `.c-notes`, `.c-origine` (« Gestionnaire » or « Inscription QR »). Each view is written to `/journal`.
  - `report.fill`: `/comptes-rendus/nouveau?intervention=<id>` (identification pre-filled from dispatch, grey;
    unknown id → 404 + `#form-error`). Start there with the incident id rather than from the list's button.
    Textareas labelled « Chronologie : », « Moyens engagés : », « Victimes : », « Observations : » (names
    `chronologie`, `moyens`, `victimes`, `observations`). « Enregistrer » (`#btn-enregistrer`, also at the top) →
    `/comptes-rendus/CR-0001`, `#cr-etat` = « Brouillon » → « Transmettre » (`#btn-transmettre`) → `#cr-etat` =
    « Transmis », `#flash` = « Compte rendu CR-0001 transmis le … », `#cr-numero` = report id. « Transmettre »
    refuses if a section is empty (`#view-error`).
- Off-host guard: requests with `X-Forwarded-For` / `CF-Connecting-IP` / `X-Real-IP` / `Forwarded` headers or a
  non-loopback client only reach `/inscription` and `/static` (everything else 404; `/` → `/inscription`).
  `REPLICAS_ALLOW_REMOTE=1` disables the guard.
- Cookies on localhost are shared across ports, so each app has its own session cookie name.
- FastAPI here has no `add_event_handler`: use `lifespan`. Starlette's TestClient needs `httpx2`, so the tests run
  against the live servers. Playwright 1.64 expects chromium-1248; the test uses the system Chrome
  (`channel="chrome"`) and falls back to the bundled one.
