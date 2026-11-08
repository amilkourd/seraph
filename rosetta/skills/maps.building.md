---
name: maps.building
kind: real
verified: true
start_url: https://www.google.com/maps
params: { address: string, expected_entrances?: { id, label, side? }[] }
timeout_s: 90
---
## Goal
See the building from outside: where its entrances are, where the engine stops, whether a hydrant is visible.

## Steps
- If the consent page shows, click « Tout refuser ».
- Click the search box, type the address, pick the suggestion.

## Success check
Code checks the address in the BAN first (refuses an address that does not exist), then that the place URL's pin is within 250 m of the BAN point.

## Extraction
Top view (Maps satellite, north up) = `earth-top-01`: Holo points each expected entrance, the truck spot, the hydrant, with a red ring on Holo's copy marking the address. Street View: code computes the heading from the panorama to the address, skips user photo spheres (`!2e10`), takes front / left / right; points there go to `evidence` only.

## Known traps
Street View needs headed Chrome (headless never resolves the panorama). Earth 3D not used (time); said in `error`, status stays ok. Any CAPTCHA → stop, cache.
