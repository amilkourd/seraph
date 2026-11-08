# Timeline to 14:00 (Sunday)

| Time | Milestone | If it isn't there |
|---|---|---|
| 01:15 | Repo pushed to GitHub (Devin needs it), `.env` filled, wave 1 sessions launched: seraph, gabriel, talkie, halo, rosetta, replicas | — |
| 01:30 | Twilio number bought, LiveKit SIP trunks started (Amil, in parallel) | web calls only |
| 02:00 | Amil: ask the venue for plans; photograph the posted plans on every floor → `ifc/venue/photos/`; launch `claude -n ifc` (dev IFC first) | fictional building |
| 02:00 | Wave 2: silex, dashboard. Every service runs in MOCK mode, `POST /admin/replay` animates dashboard + Halo | — |
| 03:00 | **Gate 1**: talkie → Gabriel → Seraph → Gabriel speaks back on `crew` | laptop speaker + clip upload |
| 04:30 | **Gate 2**: Rosetta live on 3 endpoints (dispatch.read, maps.building, plan.read) with agent cam on the dashboard · venue IFC → `ifc/out/` passes its checks, Seraph routes on it, glb on the dashboard | golden path from the first good run · fictional building |
| 05:30 | **Gate 3**: a Halo view built by Devin from a `ViewRequest`, served by Silex, shown on phone A, fed live | fallback view |
| 07:00 | **Gate 4**: calls out and in (SIP or web), facts → crew line, the stair-B catch with the gate | web calls; fixtures replay |
| 08:00 | `plan.read` on the real entrance photo (taken at 02:00), cross-checked with the IFC | fixture plan |
| 09:00 | **Gate 5**: team_engaged view + countdown; report.fill gated; eval running | cut the learning demo first |
| 10:00 | **Feature freeze.** Only fixes after this | — |
| 10:00–12:00 | Eval numbers, slides (problem, demo, architecture, numbers, vision), backup video by 12:00, 5 rehearsals with 2 strangers | — |
| 12:00–13:30 | Buffer, README, clips for X/LinkedIn | — |
| **13:30** | **Submit** | — |

Cut order if late: learning demo → occupants view → OpenEMR-like extras (none planned) → weather → dashboard 3D (keep
level plans) → Earth (keep Street View). Never cut: the gate, the agent cam, one Devin-built view, one live call.
