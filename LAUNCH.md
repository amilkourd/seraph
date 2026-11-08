# Launch (Amil) — from zero to 10 sessions in ~20 minutes

## 1. Repo (5 min)
```bash
unzip seraph-repo.zip && cd seraph
git init && git add -A && git commit -m "seraph: contracts, docs, briefs"
gh repo create seraph --private --source . --push      # Devin needs the repo
cp .env.example .env                                    # fill what you have now, the rest as you go
mkdir -p .claude && cp setup/claude-settings.example.json .claude/settings.json
```
Give Devin access to the GitHub repo (Devin app → GitHub integration).

## 2. Accounts and keys (in parallel with step 3)
LiveKit Cloud · Gladia · H (API key, Builder plan if needed) · Devin API · an OpenAI-compatible LLM · a TTS that speaks
fr/en/es · Twilio (paid account, one number) · `cloudflared` for tunnels (talkie, halo, silex, seraph, occupants
`/inscription`).

## 3. Sessions — one terminal each, from the repo root
Paste this as the first message (replace `<name>`):
> You are the `<name>` session of Seraph. Read SYSTEM.md, CLAUDE.md, docs/01-architecture.md, every file in contracts/, then
> briefs/<name>.md and status/. Create status/<name>.md from status/_TEMPLATE.md with a 10-line plan, then build.
> Start with MOCK mode so you never wait for another session. Message other sessions only when something is ready,
> blocked, or a contract is wrong.

| Wave | When | Command |
|---|---|---|
| 1 | now | `claude -n seraph` · `claude -n gabriel` · `claude -n talkie` · `claude -n halo` · `claude -n rosetta` · `claude -n replicas` · `claude -n ifc` |
| 2 | ~02:00 | `claude -n silex` · `claude -n dashboard` |
| 3 | ~05:00 | `claude -n eval` |

`/peers` lists sessions. Every ~2 hours: pull, run everything, test on the phones, fix contracts if needed (you own
`contracts/` and `docs/`; tell the sessions what changed).

## 4. Your own jobs tonight
- Twilio number + LiveKit SIP trunks with the `gabriel` session.
- **Now:** ask the venue team whether the building manager or architect has plans (IFC, Revit, DWG, PDF). Photograph
  the evacuation / intervention plan on every floor and the one at the entrance (ask first) → `ifc/venue/photos/`;
  set `PLAN_IMAGE_PATH` to the entrance one. Optional: download the TU Wien IFC on the laptop into `ifc/test/`
  (`docs/10-ifc.md`) to test the extractor on a real architect's file.
- Running armband for phone A (Halo). Phone B = talkie. Brightness max, auto-lock off on both.
- Gates and cut order: `docs/08-timeline.md`. Demo script: `docs/03-demo-script.md`.
