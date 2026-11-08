import type { NextConfig } from "next";
import os from "node:os";
import path from "node:path";

// Service URLs and MOCK come from the repo root .env (CLAUDE.md rule 7). Already-set vars win.
try {
  process.loadEnvFile(path.resolve(process.cwd(), "../.env"));
} catch {
  // no root .env: defaults in lib/services.ts (localhost ports from contracts/README.md)
}

// The projector or a phone opens the dashboard by this machine's network address. Next blocks its dev resources
// (HMR, fonts) for any origin but localhost, and the page then never starts: allow this machine's own addresses.
const lan = Object.values(os.networkInterfaces())
  .flat()
  .filter((i) => i && i.family === "IPv4" && !i.internal)
  .map((i) => i!.address);

const nextConfig: NextConfig = {
  allowedDevOrigins: [...lan, os.hostname(), "*.local"],
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
