---
name: dispatch.read
kind: replica
verified: true
start_url: http://localhost:8101/interventions
params: { incident_id?: string }
timeout_s: 30
---
## Goal
Open the open incident in the dispatch software and read it.

## Steps
- The list « Interventions en cours » shows one row per incident; the number (INC-…) is a link.
- Click the incident number to open its detail page.

## Success check
URL `/interventions/<INC-id>` and `#f-numero` present; the id is the one asked (or the newest « En cours », read by code from `#interventions tr.inc.open a`).

## Extraction
`#f-numero`, `#f-adresse`, `#f-commune`, `#f-nature`, `#f-niveau`, `#f-declaree time[datetime]`, `#notes-appelant li`.

## Known traps
Code logs in (`#username`, `#password`, `#btn-connexion`); the model never sees the password.
