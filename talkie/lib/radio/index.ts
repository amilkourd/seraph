// The UI's single entry point to the network. Pick the transport here, nowhere else.
import { LiveKitCall, LiveKitRadio } from "./livekit";
import { MockCall, MockRadio } from "./mock";
import type { CallTransport, RadioTransport } from "./types";

export type * from "./types";
export { speakerLabel } from "./payload";

/** "mock" unless TALKIE_TRANSPORT=livekit (root .env). `?mock=1` forces mock, `?transport=livekit` forces LiveKit. */
export function transportKind(): "mock" | "livekit" {
  if (typeof window !== "undefined") {
    const q = new URLSearchParams(window.location.search);
    if (q.get("mock") === "1") return "mock";
    if (q.get("transport") === "livekit") return "livekit";
  }
  return process.env.NEXT_PUBLIC_TALKIE_TRANSPORT === "livekit" ? "livekit" : "mock";
}

export function createRadio(): RadioTransport {
  return transportKind() === "livekit" ? new LiveKitRadio() : new MockRadio();
}

export function createCall(): CallTransport {
  return transportKind() === "livekit" ? new LiveKitCall() : new MockCall();
}
