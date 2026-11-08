// Server-side only: where every service lives (contracts/README.md). Read lazily so the root .env is loaded first.

export const SERVICE_NAMES = ["seraph", "rosetta", "silex", "halo", "talkie", "dispatch", "report", "occupants"] as const;
export type ServiceName = (typeof SERVICE_NAMES)[number];

const DEFAULTS: Record<ServiceName, [string, string]> = {
  seraph: ["SERAPH_URL", "http://localhost:8000"],
  rosetta: ["ROSETTA_URL", "http://localhost:8001"],
  silex: ["SILEX_URL", "http://localhost:8002"],
  halo: ["HALO_URL", "http://localhost:3001"],
  talkie: ["TALKIE_URL", "http://localhost:3000"],
  dispatch: ["DISPATCH_URL", "http://localhost:8101"],
  report: ["REPORT_URL", "http://localhost:8102"],
  occupants: ["OCCUPANTS_URL", "http://localhost:8103"],
};

export function serviceUrl(name: string): string | null {
  if (!(SERVICE_NAMES as readonly string[]).includes(name)) return null;
  const [env, fallback] = DEFAULTS[name as ServiceName];
  return (process.env[env] || fallback).replace(/\/$/, "");
}

export const isMock = () => process.env.MOCK === "1";
