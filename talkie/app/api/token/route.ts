// GET /api/token?identity=<callSign> → { url, token } for LiveKit room `crew` (contracts/README.md).
// canUpdateOwnMetadata is what lets the talkie set its `talking` attribute. Keys stay on the server.
import { readFileSync } from "node:fs";
import path from "node:path";
import { AccessToken } from "livekit-server-sdk";
import type { NextRequest } from "next/server";

const ROOM = "crew";

/** process.env first (Vercel), else the root .env read now (a dev server started before the keys were added). */
function env(name: string): string {
  let v = process.env[name];
  if (!v) {
    try {
      const line = readFileSync(path.resolve(process.cwd(), "../.env"), "utf8")
        .split("\n")
        .find((l) => l.startsWith(`${name}=`));
      v = line?.slice(name.length + 1);
    } catch {
      // no root .env
    }
  }
  return (v ?? "").split(/\s+#/)[0].trim().replace(/^["']|["']$/g, "");
}

export async function GET(req: NextRequest) {
  const identity = (req.nextUrl.searchParams.get("identity") ?? "").trim().slice(0, 40);
  const url = env("LIVEKIT_URL");
  const key = env("LIVEKIT_API_KEY");
  const secret = env("LIVEKIT_API_SECRET");
  if (!identity) return Response.json({ error: "Indicatif manquant." }, { status: 400 });
  if (identity === "Seraph") return Response.json({ error: "Indicatif réservé." }, { status: 400 });
  if (!url || !key || !secret) return Response.json({ error: "LiveKit non configuré." }, { status: 503 });
  const at = new AccessToken(key, secret, { identity, name: identity, ttl: "12h", attributes: { talking: "false" } });
  at.addGrant({
    room: ROOM,
    roomJoin: true,
    canPublish: true,
    canSubscribe: true,
    canPublishData: true,
    canUpdateOwnMetadata: true,
  });
  return Response.json({ url, token: await at.toJwt() }, { headers: { "cache-control": "no-store" } });
}
