# replicas — status
Updated: 04:35

## Running
- dispatch « Alerte / Interventions » on http://localhost:8101 · public: none · MOCK n/a (local SQLite)
- report « Comptes rendus » on http://localhost:8102 · public: none
- occupants « Gestion des occupants » on http://localhost:8103 · public: only `/inscription` (via `OCCUPANTS_PUBLIC_URL`)
- Run all three: `cd replicas && uv run python run.py` (or `uv run python run.py occupants` for one). Binds 127.0.0.1
  (`REPLICAS_HOST=0.0.0.0` to open the LAN; off-host requests still only reach `/inscription`).
- Test the four Rosetta flows: `cd replicas && uv run python tests/flows.py [shots_dir]` (resets before and after).

## Done
- Three server-rendered apps (FastAPI + Jinja2 + SQLite in `replicas/data/*.db`), no JSON API. Login `operateur` /
  `REPLICA_PASSWORD` (root `.env`, re-read on each request). « EXERCICE — données fictives » band on every page.
- Look copied from the real software (no brand): dispatch = Windows-XP-era alert software (blue title bar
  « Intervention N° INC-0001 - [SUIVI] », groupboxes Sinistre / Localisation / Demandeur, navy « INTERVENTIONS EN
  COURS » bands, main courante box); report = 2012 operations portal (blue gradient, pill nav, dark-blue
  « RAPPORT D'INTERVENTION » band, uppercase section bands, grey read-only fields, red required labels);
  occupants = property-manager intranet « PATRIMOINE ». References: Systel STARTOPS manuals and SDIS 63 CRSS
  procedure on enasis.fr.
- Seed: INC-0001 « En cours » with `DEMO_ADDRESS`, the fixture's nature / level 3 / caller notes, 6 main-courante
  entries (next is MC-0007, as in the fixture) + 5 closed incidents; reports: 5 old « Transmis » (next is CR-0001);
  occupants: the 6 from `contracts/fixtures/occupants.json`.
- `/admin/reset`: GET = page with button, POST = restore seed; answers JSON `{ok:true}` (HTML if `Accept: text/html`).
  `GET /health` → `{ok, mock:false, service}` on each app.
- `/inscription` (no login): name, phone, floor, room, language, required consent checkbox with the brief's exact
  sentence. Checked at 390 px wide: no horizontal scroll, consent enforced, private pages 404 from outside.
- Playwright run passes: `dispatch.read`, `dispatch.write_112` (MC-0007), `occupants.list` (6 rows, full E.164 read
  from the DOM), `report.fill` (CR-0001 → Brouillon → Transmis), `/inscription` on a phone viewport.

## In progress
-

## Blocked
-

## Requests (to other sessions or Amil)
- @Amil: `.env` has `DEMO_ADDRESS="2 rue Madame, 64000 Pau"` but `DEMO_TOWN=Paris 9e`. The replicas take the
  commune from the address's postcode (« Pau »); `weather.wind` uses `DEMO_TOWN`, so fix one of them.
- @seraph @Amil: occupants `POST /admin/reset` **keeps the judges' `/inscription` sign-ups** by default, so a
  rehearsal reset doesn't wipe them before the pitch. `POST /admin/reset?scope=all` wipes them too. Dispatch and report
  always restore everything.
- @rosetta (Amil): phone numbers. The occupant table shows the full E.164 in the DOM text (`inner_text` of
  `td.c-tel` = `+33100000001`), but the middle digits are CSS-blurred on screen, so agent-cam screenshots on the
  projector show them masked (safety rule 5). Read the number from the DOM, never from the screenshot.

## Facts I verified (API names, model ids, gotchas)
- DOM anchors for Rosetta's success checks and extraction (all plain visible text, stable ids):
  - Login (all three): `/login`, labels « Identifiant » `#username`, « Mot de passe » `#password`, button
    « Connexion ». Any private URL redirects to `/login?next=…` and back after login.
  - `dispatch.read`: list `/interventions`, `#interventions tr.inc.open` (newest first), link text = `INC-0001`.
    Page `/interventions/INC-0001`: `#f-numero`, `#f-adresse`, `#f-commune`, `#f-nature`, `#f-niveau`,
    `#f-declaree time[datetime]` (ISO UTC), `#notes-appelant li` (caller notes), `#f-moyens`.
  - `dispatch.write_112`: same page, textarea label « Message » `#mc-texte` (name `texte`), button « Ajouter ».
    After: `#flash` = « Entrée MC-0007 ajoutée à la main courante. », URL `?ajout=MC-0007`, first row of
    `#main-courante-liste tbody` has `data-id="MC-0007"` and `.c-texte` = the entry.
  - `occupants.list`: `/batiments` → link « Bâtiment d'exercice » → `/batiments/1`. Rows
    `#occupants tbody tr[data-id]` with `.c-nom`, `.c-niveau`, `.c-local`, `.c-tel`, `.c-langue` (fr/en/es),
    `.c-notes`, `.c-origine` (« Gestionnaire » or « Inscription QR »). Each view is written to `/journal`.
  - `report.fill`: `/comptes-rendus/nouveau?intervention=INC-0001` (identification pre-filled from dispatch, grey).
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
