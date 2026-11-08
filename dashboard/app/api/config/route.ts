import { connection } from "next/server";
import { isMock, serviceUrl } from "@/lib/services";

// What the browser needs at runtime: mock flag, Seraph's URL (for Halo's live preview), Rosetta's agent-cam
// WebSocket, and Halo's read-only mirror — only when the Halo shell actually serves /mirror.
export async function GET() {
  await connection();
  const mirror = `${serviceUrl("halo")}/mirror`;
  const mirrorUp = await fetch(mirror, { cache: "no-store", signal: AbortSignal.timeout(800) })
    .then((r) => r.ok)
    .catch(() => false);
  return Response.json({
    mock: isMock(),
    seraph: serviceUrl("seraph"),
    halo: serviceUrl("halo"),
    rosettaWs: `${serviceUrl("rosetta")!.replace(/^http/, "ws")}/ws/cam`,
    haloMirror: mirrorUp ? mirror : null,
  });
}
