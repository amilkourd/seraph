# Seraph — read this first (every Claude Code session)

Hackathon: H Company × 42AI "Computer-use agents", Paris, Nov 7–8 2026. Solo builder: Amil.
**Submission Sunday 13:30 (deadline 14:00). Feature freeze 10:00.** Demo = 3 minutes, live, with phones.

## What Seraph is (one paragraph)
Seraph is an AI copilot for firefighters. Firefighters carry one app: a **talkie** (push-to-talk on a phone) and
**Halo**, a phone strapped to the forearm like a Fallout Pip-Boy. Behind it, **Seraph** (the brain) listens and
decides, **Gabriel** speaks on the radio and handles phone calls with the building's occupants (incoming 112 calls
and outgoing calls to everyone listed in the building), **Rosetta** turns screens that have no API into an API
(H computer-use agents on real websites and legacy software), and **Silex** has Devin build a new tool when the
situation needs one — mainly the Halo view for *this* moment, and new Rosetta endpoints.

The pitch line: **« Seraph transforme n'importe quel écran en API, et met la bonne information sur le poignet du
pompier, au bon moment, à la voix et à l'image. »**

## The five parts (use these names everywhere: code, logs, UI, docs)
| Name | Role | Folder |
|---|---|---|
| **Seraph** | The brain: state, events, catches, « confirmez » gate, decides what Halo shows, computes routes | `seraph/` |
| **Gabriel** | Voice: speaks/listens on the crew LiveKit channel; one call agent per phone call (112 in, occupants out) | `gabriel/` |
| **Halo** | Phone A on the forearm: shell that displays the view Silex built for this moment, fed by live state | `halo/` |
| **Rosetta** | Computer use: endpoints over screens without API, run by our own Holo agent loop; screenshots + pointing | `rosetta/` |
| **Silex** | Tool creation with Devin: builds Halo views on Seraph's request; compiles new Rosetta endpoints | `silex/` (+ `views/`, `rosetta/skills/learned/`) |

Supporting parts: `talkie/` (crew push-to-talk app + occupant web-call page), `replicas/` (legacy software we
"don't own": dispatch, report, building manager), `dashboard/` (command post on the projector), `ifc/` (the building's IFC → routing graph, level plans, 3D;
offline), `eval/`.

## Folder ownership — ONE Claude Code session per folder
| Session (`claude -n …`) | Writes only in | Brief |
|---|---|---|
| talkie | `talkie/` | `briefs/talkie.md` |
| gabriel | `gabriel/` | `briefs/gabriel.md` |
| seraph | `seraph/` | `briefs/seraph.md` |
| halo | `halo/` (incl. `halo/kit/`) | `briefs/halo.md` |
| rosetta | `rosetta/` (except `rosetta/skills/learned/`) | `briefs/rosetta.md` |
| silex | `silex/`, `views/`, `rosetta/skills/learned/` | `briefs/silex.md` |
| replicas | `replicas/` | `briefs/replicas.md` |
| dashboard | `dashboard/` | `briefs/dashboard.md` |
| eval | `eval/` | `briefs/eval.md` |
| ifc | `ifc/` | `briefs/ifc.md` |

`contracts/` and `docs/` belong to Amil. **Never edit them.** If a contract is wrong or missing something, write it
under "Requests" in your status file and message the session that owns the other side, and Amil.

## Rules
1. Read, in this order, before writing code: `SYSTEM.md` (what we keep, how it all works) → this file → `docs/01-architecture.md` → `contracts/` (all) → your brief
   → `status/*.md`. Re-read `contracts/` and `status/*.md` before each new task.
2. Write only in your folder(s) and `status/<session>.md` (create it from `status/_TEMPLATE.md`).
3. After each task, update your status file: Running (URL/port) · Done · In progress · Blocked · Requests.
4. Talk to other sessions only when something is ready, blocked, or a contract is wrong: `@ifc @talkie @gabriel @seraph
   @halo @rosetta @silex @replicas @dashboard @eval` (`/peers` lists them). No chatter.
5. Never block on another session: mock it from `contracts/fixtures/`. Every service must run in **mock mode**
   (`MOCK=1`) with fixtures only, so the demo survives any single failure.
6. Commit only your paths: `git add <your folder> status/<you>.md && git commit -m "<session>: …"`. Never commit
   `.env`. Never force-push, never rewrite history.
7. Secrets only from the root `.env` (`.env.example` lists them). Never hardcode keys. Never print them.
8. Demo first. Every external call has a timeout, a cached fallback, and a visible state on the dashboard. Nothing
   ever spins forever: a pending panel says what it is waiting for.
9. UI text in French (radio French: short, no politeness). Code, comments, status files in English.
10. Use Context7 for current docs (LiveKit Agents, Gladia, H API, Devin API, Next.js, FastAPI, Playwright). Do not
    guess an API: look it up, then write it in your status file.
11. Safety rules in `docs/07-safety-rules.md` are product requirements, not suggestions. The two that matter most:
    **the commander decides, Gabriel relays**; **code computes positions and routes, models never guess the arrow**.

## Stack
- Web apps: Next.js (App Router) + TypeScript + Tailwind. `talkie/`, `halo/`, `dashboard/` are separate apps.
- Services: Python 3.12+, FastAPI, uvicorn, `uv`. `seraph/`, `rosetta/`, `silex/`, `replicas/`.
- Voice: LiveKit Cloud + LiveKit Agents (Python) + `livekit-plugins-gladia`; telephony via LiveKit SIP + Twilio.
- Computer use: H API (Holo models, OpenAI-compatible) + Playwright, our own agent loop (see `docs/04-rosetta.md`).
- Tool creation: Devin API v3.
- Building model: IFC4 + IfcOpenShell (Python), processed offline; glTF (`.glb`) for 3D, three.js on the dashboard.
- LLM for language tasks (extraction, call agents): any OpenAI-compatible model via env.

## Ports (local)
talkie 3000 · halo 3001 · dashboard 3002 · seraph 8000 · rosetta 8001 · silex 8002 (also serves views) ·
replicas: dispatch 8101, report 8102, occupants 8103 · gabriel: worker, no port. Details: `contracts/README.md`.

## Glossary (fire service, French)
COS commandant des opérations de secours · CODIS/CTA centre d'alerte · ARI appareil respiratoire isolant ·
binôme two-person team under ARI · VSAV ambulance · FPT fire engine · EPA aerial ladder · colonne sèche dry riser ·
R+5 ground floor + 5 · PEI hydrant · ETARE pre-plan · ERP public building · IFC open BIM building model · « reçu » acknowledged.
