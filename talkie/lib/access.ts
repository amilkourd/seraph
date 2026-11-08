// Crew access code. When the server has TALKIE_ACCESS_CODE, the crew link is `/?k=<code>`: the page passes k on to
// /api/token and into every crew link it makes. Remembered on the phone so a reload without ?k still joins.
// The occupant call (/call) never needs it.
const STORE_KEY = "talkie.k";

/** /api/token's 403 message. The radio screen shows a code field when the join fails with it. */
export const ACCESS_DENIED = "Code d'accès refusé.";

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

/** A code typed on the phone: kept on the phone and put in the page URL, so crew links and a home-screen icon carry it. */
export function setAccessCode(code: string): void {
  try {
    localStorage.setItem(STORE_KEY, code);
  } catch {
    // private mode: the URL still carries it
  }
  const url = new URL(window.location.href);
  url.searchParams.set("k", code);
  window.history.replaceState(window.history.state, "", url);
}
