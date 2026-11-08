# Halo — the wrist

The contract is `contracts/halo-views.md`. This file is about the experience.

## What it is
Phone A, strapped on the forearm with a running armband, screen up. A firefighter in gloves glances at it for one
second. It shows **one idea**, the one that matters now, as a simple animated drawing, and Gabriel says the same
thing in the ear. Audio and visual, same message, same moment.

## Who builds what
- `halo` session: the **shell** (iframe host, state feed, alerts, fallback view, vibration) and the **kit**
  (primitives Devin uses so every view is short and consistent).
- `silex` session: has **Devin** build each view on Seraph's request, from the kit, the live state and Rosetta's
  screenshots as references.
- `seraph` session: decides the moment and computes every position/route the view draws.

## The moments (what a view is for)
| Moment | The one idea | Example drawing |
|---|---|---|
| approach | « Par où j'entre » | Block seen from above, the street, the truck spot, a pulsing arrow to E1, the hydrant, E2 crossed out (ramp into the garage on fire); all points on one top view |
| inside_route | « Par où je monte » | R+3 IFC plan zones, stair A and landing shaded (smoke), arrow E1 → stair A → 3.12, terrace 3.07 marked as ladder point |
| occupants | « Qui est où » | Side view of the building, one band per level, dots for people, red ring = needs help, ? = no answer, ladder pictogram on an active ladder point (`ladder:2.17`) |
| team_engaged | **cut** (ARI air tracking, roadmap; `ARI_ENABLED` off) | — |
| commander_request | what was asked | same rules |

## The shell's own UI (no Devin needed)
- Top bar: EXERCICE · incident · clock · connection dot.
- Alert banner over any view (amber/red), vibration + short sound, auto-hides after 8 s, stays in a list.
- **Fallback view** for every moment: big text lines of the relevant facts with their source tags, labelled
  « vue de secours ». It is what Halo shows while Devin builds.
- A tiny status line: « Vue construite par Devin à 00:41 » or « Vue de secours — en construction ».

## Look
Pip-Boy spirit: near-black background, phosphor green lines, monospace caps for labels, amber for warnings, red for
danger, white for the key number. Thick strokes, no thin lines, no small text (min 22 px), big touch targets,
high contrast. Animations slow and meaningful (the arrow flows, smoke breathes), never decorative.
