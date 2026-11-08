# dashboard — the projector (Next.js, :3002)

```bash
npm install
npm run dev        # live: Seraph state + SSE, Rosetta agent cam, Silex sessions (URLs from the root .env)
npm run dev:mock   # MOCK=1: contracts/fixtures only, with a short scripted radio replay
```

Fixed 1920×1080 stage scaled to the screen. Layout after the art-direction reference: paper panels with registration
crosses over a dot-matrix field; the building is drawn from state (floor plates, room zones, hazards, people, teams,
Seraph's routes). Brand colours from `brand/tokens.css`.

Keys: `Space` confirm / `Esc` cancel the latest gate · `1–5` force a Halo moment · `R` replay radio fixture ·
`V C F G` show which fallback is engaged.

Server routes: `/api/proxy/<service>/<path>` (same-origin proxy, SSE passthrough), `/api/health`, `/api/config`,
`/api/fixtures/<file>` (reads `../contracts/fixtures/`).
