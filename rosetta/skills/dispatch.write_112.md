---
name: dispatch.write_112
kind: replica
verified: true
start_url: http://localhost:8101/interventions/<incident_id>
params: { incident_id: string, entry_fr: string }
timeout_s: 30
---
## Goal
Log one 112 call in the incident's « Main courante ».

## Steps
- The « Main courante » box is on the incident page; its text field is labelled « Message ».
- Type the entry with type_param entry_fr (never retype it), then click « Ajouter ».

## Success check
A new first row in `#main-courante-liste tbody` (different `data-id` from before) whose `.c-texte` equals the entry exactly.

## Extraction
`data-id` of that row → `entry_id`.

## Known traps
`write` is disabled in this skill: the text is typed by code where Holo clicked.
