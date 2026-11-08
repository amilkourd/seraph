import type { NextRequest } from "next/server";
import { serviceUrl } from "@/lib/services";

// Same-origin proxy to the FastAPI services, so the browser never depends on their CORS settings.
// SSE (`/stream`) is passed through unbuffered; everything else has an 8 s timeout.
async function forward(req: NextRequest, ctx: RouteContext<"/api/proxy/[service]/[...path]">) {
  const { service, path } = await ctx.params;
  const base = serviceUrl(service);
  if (!base) return Response.json({ ok: false, error: `service inconnu: ${service}` }, { status: 404 });

  const stream = path[path.length - 1] === "stream";
  const url = `${base}/${path.map(encodeURIComponent).join("/")}${req.nextUrl.search}`;
  const signal = stream ? req.signal : AbortSignal.any([req.signal, AbortSignal.timeout(8000)]);

  try {
    const upstream = await fetch(url, {
      method: req.method,
      headers: {
        "content-type": req.headers.get("content-type") ?? "application/json",
        accept: req.headers.get("accept") ?? "*/*",
      },
      body: req.method === "GET" ? undefined : await req.text(),
      cache: "no-store",
      signal,
    });
    const headers = new Headers({
      "content-type": upstream.headers.get("content-type") ?? "application/json",
      "cache-control": "no-cache, no-transform",
    });
    if (stream) headers.set("x-accel-buffering", "no");
    return new Response(upstream.body, { status: upstream.status, headers });
  } catch (e) {
    return Response.json({ ok: false, error: `${service} injoignable`, detail: String(e) }, { status: 502 });
  }
}

export { forward as GET, forward as POST };
