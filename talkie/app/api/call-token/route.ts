// POST /api/call-token { occ?, lang? } → { url, token, callId } for room `call-<callId>`, and a Gabriel call agent
// dispatched into it (agent `gabriel-call`). The agent itself tells Seraph (call_event, channel "web") once the
// caller is in the room, so a token that is never used never shows up as a call.
import { readFileSync } from "node:fs";
import path from "node:path";
import { AccessToken, AgentDispatchClient } from "livekit-server-sdk";

const AGENT = "gabriel-call";

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

function newCallId(): string {
  const t = Date.now().toString(36).slice(-3).toUpperCase();
  const r = Math.random().toString(36).slice(2, 4).toUpperCase();
  return `CALL-W${t}${r}`;
}

export async function POST(req: Request) {
  const body = (await req.json().catch(() => ({}))) as { occ?: string; lang?: string };
  const lang = typeof body.lang === "string" && /^[a-z]{2}$/.test(body.lang) ? body.lang : "fr";
  const occ = typeof body.occ === "string" && /^OCC-[\w-]{1,20}$/.test(body.occ) ? body.occ : undefined;
  const url = env("LIVEKIT_URL");
  const key = env("LIVEKIT_API_KEY");
  const secret = env("LIVEKIT_API_SECRET");
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
