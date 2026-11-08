// GET /api/token?identity=<callSign>[&room=<room>] → { url, token, room } (contracts/README.md "LiveKit rooms").
// A LiveKit token opens one room only. Default `crew`: the radio, full rights; canUpdateOwnMetadata is what lets
// the talkie set its `talking` attribute. room=call-<id>: one phone call, listen only and hidden, so Gabriel's call
// agent and the caller never see the listener. Keys stay on the server.
// TALKIE_ACCESS_CODE set (public deploy) → 403 unless ?k=<code> matches. Unset → open, as on the LAN.
import { AccessToken } from "livekit-server-sdk";
import { crewAccessOk, serverEnv } from "@/lib/server/env";
import type { NextRequest } from "next/server";

const CREW = "crew";
// web calls call-CALL-W…, outbound calls call-CALL-P…, inbound 112 calls call-<callee>_<random>
const CALL_ROOM = /^call-[\w+-]{1,64}$/;

export async function GET(req: NextRequest) {
  if (!crewAccessOk(req.nextUrl.searchParams.get("k"))) {
    return Response.json({ error: "Code d'accès refusé." }, { status: 403 });
  }
  const identity = (req.nextUrl.searchParams.get("identity") ?? "").trim().slice(0, 40);
  const room = (req.nextUrl.searchParams.get("room") ?? CREW).trim() || CREW;
  const url = serverEnv("LIVEKIT_URL");
  const key = serverEnv("LIVEKIT_API_KEY");
  const secret = serverEnv("LIVEKIT_API_SECRET");
  if (!identity) return Response.json({ error: "Indicatif manquant." }, { status: 400 });
  if (identity === "Seraph") return Response.json({ error: "Indicatif réservé." }, { status: 400 });
  if (room !== CREW && !CALL_ROOM.test(room)) return Response.json({ error: "Room inconnue." }, { status: 400 });
  if (!url || !key || !secret) return Response.json({ error: "LiveKit non configuré." }, { status: 503 });
  const crew = room === CREW;
  const at = new AccessToken(key, secret, {
    identity,
    name: identity,
    ttl: crew ? "12h" : "2h",
    attributes: crew ? { talking: "false" } : undefined,
  });
  at.addGrant(
    crew
      ? { room, roomJoin: true, canPublish: true, canSubscribe: true, canPublishData: true, canUpdateOwnMetadata: true }
      : { room, roomJoin: true, canPublish: false, canSubscribe: true, canPublishData: false, hidden: true },
  );
  return Response.json({ url, token: await at.toJwt(), room }, { headers: { "cache-control": "no-store" } });
}
