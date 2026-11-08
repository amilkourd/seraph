---
name: georisques.risks
kind: real
verified: true
start_url: https://www.georisques.gouv.fr/
params: { address: string }
timeout_s: 45
---
## Goal
List the natural and technological risks at the address.

## Steps
- If the cookie banner shows, click « Refuser ».
- Click « Adresse exacte », type the address, click the matching suggestion (it must be clicked), then « Accéder à mes risques ».

## Success check
URL `…/connaitre-les-risques-pres-de-chez-moi/rapport2?…` with `lat`/`lon` within 0.01° of the BAN point, risk names on the page.

## Extraction
Headings and card titles that name a known risk family (inondation, séisme, argiles, radon, ICPE, canalisations…), each with its category.

## Known traps
The suggestion list must be clicked; Enter alone does not submit.
