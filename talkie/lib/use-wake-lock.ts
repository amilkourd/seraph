"use client";

import { useEffect, useState } from "react";

/** Keep the screen on while `on`. Re-acquired when the page comes back (the browser drops it when hidden). */
export function useWakeLock(on: boolean): boolean {
  const [held, setHeld] = useState(false);
  useEffect(() => {
    if (!on || typeof navigator === "undefined" || !("wakeLock" in navigator)) return;
    let lock: WakeLockSentinel | null = null;
    let dead = false;
    const acquire = async () => {
      if (dead || document.visibilityState !== "visible" || (lock && !lock.released)) return;
      try {
        lock = await navigator.wakeLock.request("screen");
        setHeld(true);
        lock.addEventListener("release", () => setHeld(false));
      } catch {
        setHeld(false); // low battery mode, or not allowed: the crew sets auto-lock off
      }
    };
    void acquire();
    const onVis = () => void acquire();
    document.addEventListener("visibilitychange", onVis);
    // iOS only grants it after a gesture; retry on the next tap if the first try failed
    document.addEventListener("pointerdown", onVis, { passive: true });
    return () => {
      dead = true;
      document.removeEventListener("visibilitychange", onVis);
      document.removeEventListener("pointerdown", onVis);
      void lock?.release().catch(() => {});
    };
  }, [on]);
  return held;
}
