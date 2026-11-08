import { connection } from "next/server";
import { SERVICE_NAMES, serviceUrl } from "@/lib/services";

// One GET /health per service (contracts/api.md), 1.5 s timeout each, all in parallel.
export async function GET() {
  await connection();
  const entries = await Promise.all(
    SERVICE_NAMES.map(async (name) => {
      const t0 = Date.now();
      try {
        const r = await fetch(`${serviceUrl(name)}/health`, { cache: "no-store", signal: AbortSignal.timeout(1500) });
        const body = r.ok ? await r.json().catch(() => ({})) : {};
        return [name, { ok: r.ok && body.ok !== false, mock: Boolean(body.mock), ms: Date.now() - t0 }] as const;
      } catch {
        return [name, { ok: false, mock: false, ms: null }] as const;
      }
    }),
  );
  return Response.json(Object.fromEntries(entries));
}
