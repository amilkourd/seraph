// POST /api/call-token { occ?, lang? } → { url, token, callId } for room `call-<callId>`, and a Gabriel call agent
// dispatched into it (agent `gabriel-call`). The agent itself tells Seraph (call_event, channel "web") once the
// caller is in the room, so a token that is never used never shows up as a call.
import { AccessToken, AgentDispatchClient } from "livekit-server-sdk";
import { serverEnv } from "@/lib/server/env";

const AGENT = "gabriel-call";

function newCallId(): string {
  const t = Date.now().toString(36).slice(-3).toUpperCase();
  const r = Math.random().toString(36).slice(2, 4).toUpperCase();
  return `CALL-W${t}${r}`;
}

export async function POST(req: Request) {
  const body = (await req.json().catch(() => ({}))) as { occ?: string; lang?: string };
  const lang = typeof body.lang === "string" && /^[a-z]{2}$/.test(body.lang) ? body.lang : "fr";
  const occ = typeof body.occ === "string" && /^OCC-[\w-]{1,20}$/.test(body.occ) ? body.occ : undefined;
  const url = serverEnv("LIVEKIT_URL");
  const key = serverEnv("LIVEKIT_API_KEY");
  const secret = serverEnv("LIVEKIT_API_SECRET");
  if (!url || !key || !secret) return Response.json({ error: "LiveKit non configuré." }, { status: 503 });

  const callId = newCallId();
  const room = `call-${callId}`;
  const identity = occ ? `occupant:${occ}` : `caller:${callId}`;
  const metadata = JSON.stringify({ call_id: callId, occupant_id: occ ?? null, direction: occ ? "out" : "in", channel: "web", lang });
  try {
    const dispatch = new AgentDispatchClient(url.replace(/^ws/, "http"), key, secret);
    await dispatch.createDispatch(room, AGENT, { metadata });
  } catch {
    return Response.json({ error: "Gabriel injoignable." }, { status: 502 });
  }
  const at = new AccessToken(key, secret, { identity, name: occ ?? "Appelant", ttl: "2h" });
  at.addGrant({ room, roomJoin: true, canPublish: true, canSubscribe: true, canPublishData: true });
  return Response.json({ url, token: await at.toJwt(), callId }, { headers: { "cache-control": "no-store" } });
}
