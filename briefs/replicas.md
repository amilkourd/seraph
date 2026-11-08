# Brief — `replicas` session · `replicas/` · three web apps :8101 :8102 :8103

Read first: `CLAUDE.md`, `contracts/api.md` (Replicas), `contracts/rosetta-endpoints.md` (what Rosetta does in
them), `contracts/fixtures/occupants.json`, `contracts/fixtures/endpoints/dispatch.read.json`.

## Goal
Three pieces of software that stand for what fire services and building managers already run: **old-school,
server-rendered, no JSON API on purpose**. Rosetta operates them through the screen. They must look like real,
slightly dated institutional software (dense tables, small forms, a grey header, a login), not a startup app, and
show « EXERCICE — données fictives » on every page. No real brand names or logos.

Stack: Python FastAPI + Jinja2 + SQLite (one app per port, or one app with three sub-apps). Seed from fixtures.
`/admin/reset` restores the seed (HTML button + POST, used by the dashboard).

## 1. Alerte / Interventions (:8101) — dispatch
- `/login` (user `operateur`, password env `REPLICA_PASSWORD`).
- `/interventions`: table (N°, date, adresse, nature, niveau, statut). Seed: INC-0001 « En cours » with the
  `DEMO_ADDRESS` from env and the fixture's nature/notes.
- `/interventions/<id>`: fields + « Main courante » list + form (textarea + « Ajouter »). New entries timestamped.
- `/interventions/nouvelle`: lets Amil create the incident by hand during the demo (optional).

## 2. Comptes rendus (:8102) — report
- `/login`. `/comptes-rendus`: list. `/comptes-rendus/nouveau?intervention=INC-0001`: a long form in sections
  (Chronologie, Moyens engagés, Victimes, Observations), « Enregistrer » then « Transmettre » (status Brouillon →
  Transmis). `/comptes-rendus/<id>` read-only view.

## 3. Gestion des occupants (:8103) — building manager
- `/login`. `/batiments`: one building (« Bâtiment d'exercice »). `/batiments/1`: occupants table (name, level, room,
  phone, language) + add/edit form.
- **`/inscription` (public, no login)**: visitors opt in from the QR code: name, phone, level, room, language, and a
  required consent checkbox « J'accepte d'être appelé(e) par l'assistant vocal pendant la démonstration ». Mobile-
  friendly. Exposed publicly (`OCCUPANTS_PUBLIC_URL`), nothing else of this app needs to be.

## Done when
Each app works by hand in a browser; Rosetta's `dispatch.read`, `occupants.list`, `dispatch.write_112` and
`report.fill` succeed on them; `/admin/reset` restores everything; `/inscription` works on a phone.
