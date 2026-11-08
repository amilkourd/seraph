// The talkie's only boundary with the network. The UI imports these types and `createRadio` / `createCall`
// from "@/lib/radio" and nothing else. Implementations: mock.ts (default, fixtures) and livekit.ts (Gabriel).
// Rooms, identities and data topics: contracts/README.md ("LiveKit rooms").

export type Unsubscribe = () => void;

/** Connection to room `crew`. The UI shows « Reconnexion… » for anything but "connected". */
export type LinkState = "offline" | "connecting" | "connected" | "reconnecting";

export interface JoinOptions {
  /**
   * The AudioContext the UI unlocked inside the « Rejoindre le canal » tap (iOS needs a user gesture).
   * Use it for received audio so the radio filter and the UI sounds share one unlocked context
   * (LiveKit: `new Room({ webAudioMix: { audioContext } })`).
   */
  audioContext?: AudioContext;
}

/** Crew push-to-talk on room `crew`. */
export interface RadioTransport {
  readonly kind: "mock" | "livekit";

  /** Connect to `crew` with identity = callSign. Link goes connecting → connected. Rejects if it cannot connect. */
  join(callSign: string, options?: JoinOptions): Promise<void>;
  /** Disconnect. Link goes to "offline". Safe to call twice. */
  leave(): Promise<void>;

  /**
   * Take the floor: unmute the mic and set attribute `talking=true`.
   * Resolves false (and changes nothing) if not connected or someone else holds the floor: first press wins.
   * Must be fast: unmute first, do not await the attribute echo before resolving.
   */
  startTalking(): Promise<boolean>;
  /**
   * Release: mute, `talking=false`, then publish `{"kind":"eot","speaker":<callSign>}` (JSON, UTF-8, reliable)
   * on topic `ptt`. Gabriel cuts the utterance on that message. No-op when not talking.
   */
  stopTalking(): Promise<void>;

  /** Link state. Replays the current value on subscribe. */
  onState(cb: (state: LinkState) => void): Unsubscribe;
  /**
   * Whether this phone is on air. true after a successful startTalking, false after stopTalking or when the
   * transport ends it by itself (disconnect, lost a press collision). Replays the current value on subscribe.
   */
  onLocalTalking(cb: (talking: boolean) => void): Unsubscribe;
  /**
   * Who else holds the floor: the identity of the remote participant whose attribute `talking` is "true"
   * ("Seraph" for Gabriel's radio agent, or a call sign like "Tête"), or null when nobody does.
   * Replays the current value on subscribe.
   */
  onRemoteTalking(cb: (speaker: string | null) => void): Unsubscribe;

  /** Mock only: controls for the `?dev=1` panel. */
  readonly dev?: RadioDev;
}

/** Web call for an occupant (`/call?occ=OCC-07`, direction "out") or an incoming 112 call (no occ, "in"). */
export type CallPhase = "idle" | "connecting" | "in_call" | "ended" | "failed";

export interface CallStatus {
  phase: CallPhase;
  /** Room is `call-<callId>`, e.g. "CALL-07". Set from "connecting" on. */
  callId?: string;
  direction: "in" | "out";
  /** Date.now() when the agent picked up. The UI runs the timer from it. */
  startedAt?: number;
  /** Date.now() when the call ended. */
  endedAt?: number;
  /** French, shown under « Appel impossible ». */
  reason?: string;
}

export interface CallTransport {
  readonly kind: "mock" | "livekit";
  /**
   * Start the web call. Full duplex, no push-to-talk. With occId: the occupant's call (direction "out");
   * without: an incoming 112 call (direction "in"). Phase goes connecting → in_call once a Gabriel call
   * agent is in the room, or failed.
   */
  startCall(occId?: string, options?: JoinOptions): Promise<void>;
  /** Leave the room. Phase goes to "ended". Safe to call twice. */
  hangUp(): Promise<void>;
  /** Replays the current status on subscribe. */
  onCallState(cb: (status: CallStatus) => void): Unsubscribe;
  /** Mock only. */
  readonly dev?: CallDev;
}

/** One line of contracts/fixtures/radio.jsonl (the fields the talkie uses). */
export interface RadioLine {
  id: string;
  speaker: string;
  lang: string;
  text: string;
  expected: { event: string; say_crew?: string | null };
}

export interface RadioDevLog {
  t: number;
  text: string;
}

export interface RadioDev {
  lines: RadioLine[];
  /** Play one exchange: the speaker talks (skipped if it is you), then Seraph answers with say_crew. */
  play(id: string): void;
  /** Seraph says this now (waits for the floor, like Gabriel). */
  seraphSays(text: string): void;
  /** Someone else holds the floor for ms. */
  remoteTalks(speaker: string, ms?: number): void;
  /** Go on air for ms as if the button were held (no button needed). */
  holdFor(ms?: number): void;
  /** Back to a quiet channel: stop whoever talks, reconnect if needed. */
  idle(): void;
  /** Lose the link. With ms, it comes back by itself; without, until reconnect(). */
  drop(ms?: number): void;
  reconnect(): void;
  /** Replay the fixture by itself between your transmissions. */
  setAuto(on: boolean): void;
  /** Speak the mock lines with the browser's voice (speechSynthesis). */
  setVoice(on: boolean): void;
  onDevState(cb: (s: { auto: boolean; voice: boolean; log: RadioDevLog[] }) => void): Unsubscribe;
}

export interface CallDev {
  /** Jump straight to a phase (failed takes a reason). */
  force(phase: CallPhase, reason?: string): void;
}
