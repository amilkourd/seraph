import type { NextConfig } from "next";
import path from "node:path";

// Service URLs and MOCK come from the repo root .env (CLAUDE.md rule 7). Already-set vars win.
try {
  process.loadEnvFile(path.resolve(process.cwd(), "../.env"));
} catch {
  // no root .env: defaults in lib/services.ts (localhost ports from contracts/README.md)
}

const nextConfig: NextConfig = {
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
