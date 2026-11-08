import { connection } from "next/server";
import { isMock, serviceUrl } from "@/lib/services";

// What the browser needs at runtime: mock flag, Rosetta's agent-cam WebSocket, Halo's read-only mirror.
export async function GET() {
  await connection();
  return Response.json({
    mock: isMock(),
    rosettaWs: `${serviceUrl("rosetta")!.replace(/^http/, "ws")}/ws/cam`,
    haloMirror: `${serviceUrl("halo")}/mirror`,
  });
}
