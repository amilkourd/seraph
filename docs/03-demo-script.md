# Demo — 3 minutes

## Roles and devices
| Who | Device | Role |
|---|---|---|
| Amil | Phone B (talkie) | COS, and voices Tête / Binôme lines |
| Amil's forearm | Phone A (Halo) | the firefighter's wrist |
| 2–3 participants | their own phones | occupants (opted in through the QR code) or a 112 caller |
| Projector | laptop | dashboard |

## Setup checklist (T-20 min)
- [ ] `.env` filled, all services up, `GET /health` green on the dashboard.
- [ ] `POST /admin/reset`, then clear Rosetta's cache only if you want the live run (keep the golden path as backup).
- [ ] QR on screen → participants opt in on `/inscription` (name, number, floor, room, language, consent).
- [ ] **T-15: start the incident** (dashboard « Déclencher »). Rosetta runs, Silex/Devin builds the approach view,
      Gabriel calls the occupants (participants' phones ring early — tell them to pick up and play along, or keep the
      participants' calls for the live moment with « Appeler maintenant » on the dashboard). Confirm the standing
      instruction (stay put, « si fumée dans l'escalier ou devant la porte, rester chez soi ») right away, before
      the calls: « confirme » always takes the latest pending gate.
- [ ] Phone A strapped, Halo on the approach view, brightness max, auto-lock off.
- [ ] Laptop speaker as backup for Gabriel's voice; web-call link ready in case SIP fails.

## Script
| Time | What you say / do | What they see and hear |
|---|---|---|
| 0:00–0:20 | « Grenfell, Londres, 2017 : 72 morts. Un seul escalier. Les appels arrivaient au centre d'alerte, pas aux pompiers. Et « restez chez vous » n'a été levé qu'à 2 h 47, près de deux heures après le premier appel. » | Dashboard: EXERCICE, the TU Wien building (real IFC, placed at the venue's address), fire in the garage, the single stair in smoke |
| 0:20–0:50 | On the talkie, as Tête: « Seraph de Tête, quelle entrée ? » | Gabriel answers on the talkie: « … entrée par E1, hall de l'escalier A. Évitez E2, la rampe mène au garage en feu selon l'alerte. Seul escalier, enfumé selon l'alerte… ». Halo (raise your arm): the arrow to E1, E2 crossed out. Dashboard: the Devin session that built this view during the "drive", Rosetta's Earth screenshots |
| 0:50–1:55 | « Seraph appelle chaque occupant. » A participant's phone rings, they answer; let the call run (where, how many, smoke) | Live call; their words become a line on the radio, sorted by urgency (« selon la voix » when fear raises it); their dot appears on their floor. Then Tom (fixture or participant), 2nd floor, starts down the smoky stair → Gabriel: « Je lui dis de rester dans son logement, porte fermée, et d'aller sur le balcon ? » → you: « Seraph, confirme » → Tom is told, in English → balcony 2.17 lights up on Halo as a ladder point |
| 1:55–2:15 | As Tête: « Seraph de Tête, escalier A désenfumé. » Then as COS: « Seraph, levée du confinement : dis à tous les occupants de sortir par l'escalier A. » → « Confirme. » | Gabriel reads it back, « sauf Inès Rahmani, en fauteuil » · on « confirme » every open call hears it at once, each in its language. « Grenfell : deux heures. Ici : une phrase. » |
| 2:15–2:35 | « Seraph, fais le rapport. » → « Confirme. » | Agent cam: Rosetta fills the report in the legacy software, live: chronology, the calls, the stay-put decisions flat by flat |
| 2:35–3:00 | « Huit sources sans API. Huit endpoints. Seraph transforme n'importe quel écran en API — et le commandant décide. » | Counter, the eval line (voice → crew in X s) |

## If something breaks (keys on the dashboard)
- `V` voice fails → Gabriel speaks through the laptop speaker.
- `C` SIP fails → participants use the web call link.
- `F` Devin late → Halo stays on the fallback view (labelled), keep talking, it swaps when ready.
- `G` Rosetta live fails → golden-path cache (labelled « cache »).
- `R` replay a fixture line (radio or call) if a live line is missed.
Never apologise on stage for a fallback: say what it is (« vue de secours ») and move on.
