import type { NextConfig } from "next";
import path from "node:path";

// Env comes from the repo root .env (CLAUDE.md rule 7). Already-set vars win.
try {
  process.loadEnvFile(path.resolve(process.cwd(), "../.env"));
} catch {
  // no root .env: mock transport, placeholder QR
}

// Which radio/call transport the phones use. "mock" until the Gabriel session fills lib/radio/livekit.ts and
// sets TALKIE_TRANSPORT=livekit. MOCK=1 always wins. `?mock=1` on any page forces mock at runtime.
const transport = process.env.MOCK === "1" ? "mock" : process.env.TALKIE_TRANSPORT === "livekit" ? "livekit" : "mock";

const nextConfig: NextConfig = {
  cacheComponents: true,
  partialPrefetching: true,
  // Phones reach the dev server through a tunnel or the LAN.
  allowedDevOrigins: ["*.trycloudflare.com", "*.ngrok-free.app", "*.local", "192.168.*.*", "10.*.*.*"],
  env: {
    NEXT_PUBLIC_TALKIE_TRANSPORT: transport,
  },
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
