---
name: occupants.list
kind: replica
verified: true
start_url: http://localhost:8103/batiments
params: { building: string }
timeout_s: 30
---
## Goal
Open the building in the building manager's software and show its occupant table.

## Steps
- The building list is a table; the building name is a link.

## Success check
URL `/batiments/<n>` of the building code picked (exact name, else the only one, else the one named « exercice »), rows `#occupants tbody tr[data-id]`.

## Extraction
`.c-nom`, `.c-niveau`, `.c-local`, `.c-tel` (full E.164 in the DOM, blurred on screen), `.c-langue`, `.c-notes`, `.c-origine`.

## Known traps
Phone numbers go only to Seraph; `/runs/{id}` and traces mask them.
