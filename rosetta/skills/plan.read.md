---
name: plan.read
kind: real
verified: true
start_url: file (the plan posted at the door)
params: { image_path: string, level: number }
timeout_s: 60
---
## Goal
Read the plan posted at the door: name and point every stair, lift, exit, cut-off and room; code draws the zones.

## Steps
- The image is shown at its natural size, so its 0–1000 frame is the plan's own (demo: `ifc-L-1`).
- Holo lists what is written or drawn (one visual question), then points at each element (element localization, in parallel).

## Success check
At least one element read; points on the 0–1000 grid of `plan-l<level>-01`.

## Extraction
Zones by code: dark walls (small marks dropped), region of the seed's fill colour, flood-fill from Holo's point, outer contour simplified. Several names in one region (parking places in the garage) → the zone goes to the name nearest its centre, the others in `also`.

## Known traps
Hatched stairs come out small (treads cut the fill). The IFC zones win; this is the cross-check.
