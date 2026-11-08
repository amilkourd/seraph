# Seraph

AI copilot for firefighters. One talkie and a wrist screen (Halo) for the crew. Behind them: **Seraph** decides,
**Gabriel** speaks on the radio and calls everyone in the building, **Rosetta** turns screens without API into an API
(H computer use), **Silex** has Devin build the right tool for the moment.

> « Seraph transforme n'importe quel écran en API, et met la bonne information sur le poignet du pompier, au bon
> moment, à la voix et à l'image. »

Built in one night, solo, for the H Company × 42AI computer-use hackathon (Paris, Nov 2026). Everything is an
EXERCICE: fictional incident, fictional occupants, replicas of the software fire services use.

## Read in this order
0. `SYSTEM.md` — the whole system on one page: what we keep, which sites, how each part works (it decides)
1. `CLAUDE.md` — rules, names, ownership, stack, ports
2. `docs/00-vision.md` — problem, pitch, why computer use is the moat
3. `docs/01-architecture.md` — parts, flows, mock mode
4. `docs/02-scenario.md` — the building, occupants, crew, timeline
5. `docs/07-safety-rules.md` — what makes it trustworthy (product requirements)
6. `contracts/` — `types.ts`, `api.md`, `rosetta-endpoints.md`, `halo-views.md`, `fixtures/`
7. `docs/04-rosetta.md`, `docs/05-halo.md`, `docs/06-gabriel.md`, `docs/10-ifc.md` — design of each hard part
8. `docs/03-demo-script.md`, `docs/08-timeline.md`, `docs/09-research.md`, `docs/seraph-build-map.html` (visual overview; its "Who builds what" table predates this repo — `CLAUDE.md` is authoritative for folders and sessions)
9. `briefs/<session>.md` — your job
10. `LAUNCH.md` — how Amil starts everything

## Layout
```
seraph/     brain (FastAPI :8000)          gabriel/   voice + calls (LiveKit Agents)
rosetta/    computer use (FastAPI :8001)    silex/     Devin bridge (FastAPI :8002) + views/
halo/       wrist shell + kit (Next :3001)  talkie/    crew radio + web calls (Next :3000)
dashboard/  projector (Next :3002)          replicas/  dispatch :8101, report :8102, occupants :8103
ifc/        building model (IFC, offline)   eval/      numbers
tools/      ifc_inspect.py                  contracts/ docs/ briefs/ status/
```
