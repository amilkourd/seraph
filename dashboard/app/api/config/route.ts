import type { NextRequest } from "next/server";
import { connection } from "next/server";
import { isMock, serviceUrl } from "@/lib/services";

// What the browser needs at runtime: mock flag, Seraph's URL (for Halo's live preview), Rosetta's agent-cam
// WebSocket, and Halo's read-only mirror — only when the Halo shell actually serves /mirror.
// A browser on another machine (the projector) gets the services on the host it reached us by, not « localhost ».
export async function GET(req: NextRequest) {
  await connection();
  const host = (req.headers.get("x-forwarded-host") ?? req.headers.get("host") ?? "localhost").replace(/:\d+$/, "");
  const local = host === "localhost" || host === "127.0.0.1" || host === "[::1]";
  const forBrowser = (url: string) => (local ? url : url.replace(/\/\/(localhost|127\.0\.0\.1)(?=[:/]|$)/, `//${host}`));
  const mirror = `${serviceUrl("halo")}/mirror`;
  const mirrorUp = await fetch(mirror, { cache: "no-store", signal: AbortSignal.timeout(800) })
    .then((r) => r.ok)
    .catch(() => false);
  return Response.json({
    mock: isMock(),
    seraph: forBrowser(serviceUrl("seraph")!),
    halo: forBrowser(serviceUrl("halo")!),
    rosettaWs: forBrowser(`${serviceUrl("rosetta")!.replace(/^http/, "ws")}/ws/cam`),
    haloMirror: mirrorUp ? forBrowser(mirror) : null,
    inscription: inscription(),
  });
}

// the occupants replica's public opt-in page, for the booth's QR (same rule as talkie's /qr)
function inscription(): string | null {
  const base = process.env.OCCUPANTS_PUBLIC_URL?.trim().replace(/\/+$/, "");
  if (!base) return null;
  return base.endsWith("/inscription") ? base : `${base}/inscription`;
}
