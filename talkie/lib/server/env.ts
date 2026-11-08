// Server-only env for the API routes. process.env first (Vercel, `next start`, which loads the root .env through
// next.config.ts). In dev only, the root .env is re-read on each call, so keys added after the dev server started
// work without a restart. Production never reads outside talkie/.
import { createHash, timingSafeEqual } from "node:crypto";
import { readFileSync } from "node:fs";
import path from "node:path";

export function serverEnv(name: string): string {
  let v = process.env[name];
  if (!v && process.env.NODE_ENV === "development") {
    try {
      const line = readFileSync(path.resolve(process.cwd(), "../.env"), "utf8")
        .split("\n")
        .find((l) => l.startsWith(`${name}=`));
      v = line?.slice(name.length + 1);
    } catch {
      // no root .env
    }
  }
  return (v ?? "")
    .split(/\s+#/)[0]
    .trim()
    .replace(/^["']|["']$/g, "");
}

/** Crew gate: true when TALKIE_ACCESS_CODE is unset, or `given` matches it. Constant time; never logs either value. */
export function crewAccessOk(given: string | null): boolean {
  const code = serverEnv("TALKIE_ACCESS_CODE");
  if (!code) return true;
  const a = createHash("sha256")
    .update(given ?? "")
    .digest();
  const b = createHash("sha256").update(code).digest();
  return timingSafeEqual(a, b);
}
