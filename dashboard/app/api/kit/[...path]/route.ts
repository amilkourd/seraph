import { readFile } from "node:fs/promises";
import path from "node:path";

// Serves the Halo kit read-only from halo/kit/ (owned by the halo session), so the dashboard's scheme speaks the
// same visual language as the wrist. Example views get {{HALO_KIT_URL}} filled in, like Silex does.
const ROOT = path.resolve(process.cwd(), "../halo/kit");
const TYPES: Record<string, string> = { ".js": "text/javascript", ".css": "text/css", ".html": "text/html" };

export async function GET(_req: Request, ctx: RouteContext<"/api/kit/[...path]">) {
  const { path: parts } = await ctx.params;
  const file = path.resolve(ROOT, ...parts);
  const type = TYPES[path.extname(file)];
  if (!file.startsWith(ROOT + path.sep) || !type) return Response.json({ ok: false, error: "fichier refusé" }, { status: 400 });
  try {
    let body = await readFile(file, "utf8");
    if (type === "text/html") body = body.replaceAll("{{HALO_KIT_URL}}", "/api/kit");
    return new Response(body, { headers: { "content-type": `${type}; charset=utf-8`, "cache-control": "no-store" } });
  } catch {
    return Response.json({ ok: false, error: "kit absent" }, { status: 404 });
  }
}
