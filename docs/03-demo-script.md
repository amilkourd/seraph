# Demo — 3 minutes

## Roles and devices
| Who | Device | Role |
|---|---|---|
| Amil | Phone B (talkie) | COS, and voices Tête / Binôme lines |
| Amil's forearm | Phone A (Halo) | the firefighter's wrist |
| 2–3 judges | their own phones | occupants (opted in through the QR code) or a 112 caller |
| Projector | laptop | dashboard |

## Setup checklist (T-20 min)
- [ ] `.env` filled, all services up, `GET /health` green on the dashboard.
- [ ] `POST /admin/reset`, then clear Rosetta's cache only if you want the live run (keep the golden path as backup).
- [ ] QR on screen → judges opt in on `/inscription` (name, number, floor, room, language, consent).
- [ ] **T-15: start the incident** (dashboard « Déclencher »). Rosetta runs, Silex/Devin builds the approach view,
      Gabriel calls the occupants (judges' phones ring early — tell them to pick up and play along, or keep the
      judges' calls for the live moment with « Appeler maintenant » on the dashboard).
- [ ] Phone A strapped, Halo on the approach view, brightness max, auto-lock off.
- [ ] Laptop speaker as backup for Gabriel's voice; web-call link ready in case SIP fails.

## Script
| Time | What you say / do | What they see and hear |
|---|---|---|
| 0:00–0:20 | « Grenfell, Londres, 2017 : 72 morts. Les appels arrivaient au centre d'alerte. Ils n'arrivaient pas aux pompiers. » | Dashboard: EXERCICE, the building, the timeline |
| 0:20–0:50 | On the talkie, as Tête: « Seraph de Tête, quelle entrée ? » | Gabriel answers on the talkie: « … porte latérale E2, escalier A dégagé… ». Halo (raise your arm): the arrow to E2. Dashboard: the Devin session that built this view during the "drive", Rosetta's Earth screenshots |
| 0:50–1:40 | « Seraph appelle chaque occupant. » A judge's phone rings, they answer | Live call; their words become a line on the radio; their dot appears on the floor stack. Then Tom (fixture or judge) heads to stair B → Gabriel: « Je lui dis de prendre A ? » → you: « Seraph, confirme » → he's told, in English |
| 1:40–2:15 | « Binôme 1 engagé par l'escalier A, 300 bars. » | Halo switches: Devin built « mon air » with a countdown; Gabriel gives the exit time; later the T-5 alarm vibrates |
| 2:15–2:35 | « Seraph, fais le rapport. » → « Confirme. » | Agent cam: Rosetta fills the report in the legacy software, live |
| 2:35–3:00 | « Huit sources sans API. Huit endpoints. Seraph transforme n'importe quel écran en API — et le commandant décide. » | Counter, the eval line (voice → crew in X s) |

## If something breaks (keys on the dashboard)
- `V` voice fails → Gabriel speaks through the laptop speaker.
- `C` SIP fails → judges use the web call link.
- `F` Devin late → Halo stays on the fallback view (labelled), keep talking, it swaps when ready.
- `G` Rosetta live fails → golden-path cache (labelled « cache »).
- `R` replay a fixture line (radio or call) if a live line is missed.
Never apologise on stage for a fallback: say what it is (« vue de secours ») and move on.
