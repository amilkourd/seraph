---
name: report.fill
kind: replica
verified: true
start_url: http://localhost:8102/comptes-rendus
params: { incident_id: string, gate_id: string, sections: { chronologie, moyens, victimes, observations } }
timeout_s: 120
---
## Goal
Write and send the incident report, only after the commander confirmed (gate `send_report`).

## Steps
- « Nouveau compte rendu » opens the form for the incident.
- Click each section's text area, then type_param with the section's name.
- « Enregistrer » saves a draft; on the draft page, « Transmettre » sends it.

## Success check
`#cr-etat` = « Transmis » and each `#cr-<section>` equals what Seraph sent.

## Extraction
`#cr-numero` → `report_id`, page URL.

## Known traps
Refused without `gate_id` (HTTP 403 at /run, and again in the run). `write` is disabled. Code blocks the click on « Transmettre » while the draft's sections differ from Seraph's texts (first test: the model typed the section names and sent them).
