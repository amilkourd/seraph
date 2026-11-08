// GET /api/token?identity=<callSign> → { url, token } for LiveKit room `crew` (contracts/README.md).
// canUpdateOwnMetadata is what lets the talkie set its `talking` attribute. Keys stay on the server.
// TALKIE_ACCESS_CODE set (public deploy) → 403 unless ?k=<code> matches. Unset → open, as on the LAN.
import { AccessToken } from "livekit-server-sdk";
import { crewAccessOk, serverEnv } from "@/lib/server/env";
import type { NextRequest } from "next/server";

const ROOM = "crew";

export async function GET(req: NextRequest) {
  if (!crewAccessOk(req.nextUrl.searchParams.get("k"))) {
    return Response.json({ error: "Code d'accès refusé." }, { status: 403 });
  }
  const identity = (req.nextUrl.searchParams.get("identity") ?? "").trim().slice(0, 40);
  const url = serverEnv("LIVEKIT_URL");
  const key = serverEnv("LIVEKIT_API_KEY");
  const secret = serverEnv("LIVEKIT_API_SECRET");
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
