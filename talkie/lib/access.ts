// Crew access code. When the server has TALKIE_ACCESS_CODE, the crew link is `/?k=<code>`: the page passes k on to
// /api/token and into every crew link it makes. Remembered on the phone so a reload without ?k still joins.
// The occupant call (/call) never needs it.
const STORE_KEY = "talkie.k";

export function accessCode(): string {
  if (typeof window === "undefined") return "";
  const k = new URLSearchParams(window.location.search).get("k")?.trim() ?? "";
  try {
    if (k) localStorage.setItem(STORE_KEY, k);
    return k || localStorage.getItem(STORE_KEY) || "";
  } catch {
    return k;
  }
}

/** `path` with `k=<code>` added when this phone has a code. */
export function withAccess(path: string): string {
  const k = accessCode();
  return k ? `${path}${path.includes("?") ? "&" : "?"}k=${encodeURIComponent(k)}` : path;
}
