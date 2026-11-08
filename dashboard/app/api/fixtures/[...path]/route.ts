import { readFile } from "node:fs/promises";
import path from "node:path";

// Serves contracts/fixtures/ read-only, so mock mode always uses the single source of truth.
const ROOT = path.resolve(process.cwd(), "../contracts/fixtures");

export async function GET(_req: Request, ctx: RouteContext<"/api/fixtures/[...path]">) {
  const { path: parts } = await ctx.params;
  const file = path.resolve(ROOT, ...parts);
  if (!file.startsWith(ROOT + path.sep) || !/\.(json|jsonl|svg)$/.test(file)) {
    return Response.json({ ok: false, error: "fixture refusée" }, { status: 400 });
  }
  try {
    const body = await readFile(file, "utf8");
    const type = file.endsWith(".svg") ? "image/svg+xml" : file.endsWith(".jsonl") ? "text/plain" : "application/json";
    return new Response(body, { headers: { "content-type": `${type}; charset=utf-8`, "cache-control": "no-store" } });
  } catch {
    return Response.json({ ok: false, error: "fixture absente" }, { status: 404 });
  }
}
