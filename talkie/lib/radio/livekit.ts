// LiveKit transports (written by the Gabriel session). Same interface as mock.ts; picked by `TALKIE_TRANSPORT=livekit`.
//
// Contract: contracts/README.md ("LiveKit rooms") · docs/06-gabriel.md · status/talkie.md ("Radio interface").
// Interface: ./types.ts. Wire formats: ./payload.ts. Radio filter: ../audio/sounds.ts (the UI plays chirp / roger /
// squelch / hiss itself). Tokens: app/api/token (crew) and app/api/call-token (call room + Gabriel dispatch).
import {
  ConnectionState,
  type LocalAudioTrack,
  type Participant,
  RemoteAudioTrack,
  type RemoteParticipant,
  type RemoteTrack,
  Room,
  RoomEvent,
  Track,
} from "livekit-client";
import { radioFilter } from "../audio/sounds";
import { ATTR_TALKING, encodeEot, TOPIC_PTT } from "./payload";
import { Signal } from "./signal";
import type { CallStatus, CallTransport, JoinOptions, LinkState, RadioTransport, Unsubscribe } from "./types";

const AGENT_TIMEOUT_MS = 15_000;

function roomOptions(options?: JoinOptions) {
  return {
    webAudioMix: options?.audioContext ? { audioContext: options.audioContext } : true,
    audioCaptureDefaults: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    adaptiveStream: false,
    dynacast: false,
  };
}

/** Play a remote audio track through the shared context; optionally with the radio voice filter. */
function playAudio(track: RemoteTrack, ctx: AudioContext | undefined, filter: boolean): void {
  if (track.kind !== Track.Kind.Audio) return;
  const el = track.attach();
  el.style.display = "none";
  document.body.appendChild(el);
  if (filter && ctx && track instanceof RemoteAudioTrack) {
    try {
      track.setWebAudioPlugins(radioFilter(ctx));
    } catch {
      // @internal in the SDK: if it misbehaves, keep the audio without the filter
    }
  }
}

function since(p: Participant): number {
  const v = Number(p.attributes?.talking_since ?? "");
  return Number.isFinite(v) && v > 0 ? v : Number.MAX_SAFE_INTEGER;
}

async function fetchJson<T>(input: string, init?: RequestInit): Promise<T> {
  const ctl = new AbortController();
  const t = setTimeout(() => ctl.abort(), 8000);
  try {
    const r = await fetch(input, { ...init, signal: ctl.signal, cache: "no-store" });
    const body = (await r.json().catch(() => ({}))) as T & { error?: string };
    if (!r.ok) throw new Error(body.error || `Serveur ${r.status}`);
    return body;
  } finally {
    clearTimeout(t);
  }
}

export class LiveKitRadio implements RadioTransport {
  readonly kind = "livekit" as const;
  private link = new Signal<LinkState>("offline");
  private local = new Signal(false);
  private remote = new Signal<string | null>(null);
  private room: Room | null = null;
  private callSign = "";
  private options: JoinOptions | undefined;
  private leaving = false;
  private retry: ReturnType<typeof setTimeout> | null = null;

  async join(callSign: string, options?: JoinOptions): Promise<void> {
    this.callSign = callSign;
    this.options = options;
    this.leaving = false;
    if (this.retry) clearTimeout(this.retry);
    await this.connect("connecting");
  }

  private async connect(state: LinkState): Promise<void> {
    await this.dropRoom();
    this.link.set(state);
    const room = new Room(roomOptions(this.options));
    this.room = room;
    const ctx = this.options?.audioContext;
    room
      .on(RoomEvent.Reconnecting, () => this.link.set("reconnecting"))
      .on(RoomEvent.SignalReconnecting, () => this.link.set("reconnecting"))
      .on(RoomEvent.Reconnected, () => {
        this.link.set("connected");
        this.floor();
      })
      .on(RoomEvent.Disconnected, () => {
        if (this.room !== room) return;
        this.endLocal(false);
        this.remote.set(null);
        if (this.leaving) {
          this.link.set("offline");
          return;
        }
        // Lost for good: rejoin by ourselves (« Reconnexion… » meanwhile).
        this.link.set("reconnecting");
        this.retry = setTimeout(() => void this.connect("reconnecting").catch(() => this.scheduleRetry()), 1000);
      })
      .on(RoomEvent.ParticipantAttributesChanged, () => this.floor())
      .on(RoomEvent.ParticipantConnected, () => this.floor())
      .on(RoomEvent.ParticipantDisconnected, () => this.floor())
      .on(RoomEvent.TrackSubscribed, (track) => playAudio(track, ctx, true))
      .on(RoomEvent.TrackUnsubscribed, (track) => track.detach().forEach((el) => el.remove()));

    try {
      const { url, token } = await fetchJson<{ url: string; token: string }>(
        `/api/token?identity=${encodeURIComponent(this.callSign)}`,
      );
      await room.connect(url, token, { autoSubscribe: true });
      void room.startAudio().catch(() => {});
      // Publish the mic now, muted: the iOS prompt happens at join and a press only unmutes.
      await room.localParticipant.setMicrophoneEnabled(true);
      await this.mic()?.mute();
      void room.localParticipant.setAttributes({ [ATTR_TALKING]: "false" }).catch(() => {});
      this.link.set("connected");
      this.floor();
    } catch (e) {
      if (this.room === room) this.room = null;
      await room.disconnect().catch(() => {});
      this.link.set("offline");
      throw e instanceof Error ? e : new Error("Canal crew injoignable.");
    }
  }

  private scheduleRetry(): void {
    if (this.leaving) return;
    this.link.set("reconnecting");
    this.retry = setTimeout(() => void this.connect("reconnecting").catch(() => this.scheduleRetry()), 3000);
  }

  private async dropRoom(): Promise<void> {
    const r = this.room;
    this.room = null;
    if (r) await r.disconnect().catch(() => {});
  }

  private mic(): LocalAudioTrack | undefined {
    return this.room?.localParticipant.getTrackPublication(Track.Source.Microphone)?.audioTrack as
      | LocalAudioTrack
      | undefined;
  }

  /** Who holds the floor. While we are on air, a remote press that came first (earlier talking_since) wins. */
  private floor(): void {
    const room = this.room;
    if (!room) return;
    const talkers = [...room.remoteParticipants.values()]
      .filter((p: RemoteParticipant) => p.attributes?.[ATTR_TALKING] === "true")
      .sort((a, b) => since(a) - since(b) || a.identity.localeCompare(b.identity));
    if (this.local.get()) {
      const mine = since(room.localParticipant);
      const winner = talkers.find(
        (p) => since(p) < mine || (since(p) === mine && p.identity.localeCompare(this.callSign) < 0),
      );
      if (winner) {
        this.endLocal(true);
        this.remote.set(winner.identity);
      }
      return;
    }
    this.remote.set(talkers[0]?.identity ?? null);
  }

  /** Off air: mute, talking=false, and (when it was a transmission) the eot Gabriel cuts on. */
  private endLocal(sendEot: boolean): void {
    if (!this.local.get()) return;
    this.local.set(false);
    const room = this.room;
    void this.mic()?.mute();
    if (!room || room.state !== ConnectionState.Connected) return;
    void room.localParticipant.setAttributes({ [ATTR_TALKING]: "false" }).catch(() => {});
    if (sendEot)
      void room.localParticipant
        .publishData(encodeEot(this.callSign), { reliable: true, topic: TOPIC_PTT })
        .catch(() => {});
  }

  async leave(): Promise<void> {
    this.leaving = true;
    if (this.retry) clearTimeout(this.retry);
    this.endLocal(true);
    await this.dropRoom();
    this.local.set(false);
    this.remote.set(null);
    this.link.set("offline");
  }

  async startTalking(): Promise<boolean> {
    const room = this.room;
    if (!room || this.link.get() !== "connected" || this.remote.get() !== null || this.local.get()) return false;
    const track = this.mic();
    if (!track) return false;
    await track.unmute();
    this.local.set(true);
    // Not awaited: setAttributes waits up to 5 s for the server echo.
    void room.localParticipant
      .setAttributes({ [ATTR_TALKING]: "true", talking_since: String(Date.now()) })
      .catch(() => {});
    return true;
  }

  async stopTalking(): Promise<void> {
    this.endLocal(true);
  }

  onState(cb: (state: LinkState) => void): Unsubscribe {
    return this.link.subscribe(cb);
  }
  onLocalTalking(cb: (talking: boolean) => void): Unsubscribe {
    return this.local.subscribe(cb);
  }
  onRemoteTalking(cb: (speaker: string | null) => void): Unsubscribe {
    return this.remote.subscribe(cb);
  }
}

export class LiveKitCall implements CallTransport {
  readonly kind = "livekit" as const;
  private status = new Signal<CallStatus>({ phase: "idle", direction: "in" });
  private room: Room | null = null;
  private timer: ReturnType<typeof setTimeout> | null = null;

  async startCall(occId?: string, options?: JoinOptions): Promise<void> {
    const direction = occId ? "out" : "in";
    await this.close();
    this.status.set({ phase: "connecting", direction });
    let callId: string | undefined;
    try {
      const res = await fetchJson<{ url: string; token: string; callId: string }>("/api/call-token", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(occId ? { occ: occId } : {}),
      });
      callId = res.callId;
      this.status.set({ phase: "connecting", direction, callId });
      const room = new Room(roomOptions(options));
      this.room = room;
      const ctx = options?.audioContext;
      const pickUp = () => {
        const s = this.status.get();
        if (s.phase !== "connecting") return;
        if (this.timer) clearTimeout(this.timer);
        this.status.set({ phase: "in_call", direction, callId, startedAt: Date.now() });
      };
      room
        .on(RoomEvent.ParticipantConnected, (p) => p.isAgent && pickUp())
        .on(RoomEvent.TrackSubscribed, (track, _pub, p) => {
          playAudio(track, ctx, false);
          if (p.isAgent) pickUp();
        })
        .on(RoomEvent.ParticipantDisconnected, (p) => {
          if (p.isAgent && this.room === room) void this.finish("ended");
        })
        .on(RoomEvent.Disconnected, () => {
          if (this.room !== room) return;
          const s = this.status.get();
          void this.finish(s.phase === "in_call" ? "ended" : "failed", "Ligne coupée.");
        });
      await room.connect(res.url, res.token, { autoSubscribe: true });
      void room.startAudio().catch(() => {});
      await room.localParticipant.setMicrophoneEnabled(true);
      if ([...room.remoteParticipants.values()].some((p) => p.isAgent)) pickUp();
      else
        this.timer = setTimeout(() => {
          if (this.status.get().phase === "connecting") void this.finish("failed", "Gabriel ne répond pas.");
        }, AGENT_TIMEOUT_MS);
    } catch (e) {
      await this.close();
      this.status.set({
        phase: "failed",
        direction,
        callId,
        reason: e instanceof Error && e.message ? e.message : "Appel impossible.",
      });
    }
  }

  private async finish(phase: "ended" | "failed", reason?: string): Promise<void> {
    const s = this.status.get();
    await this.close();
    if (s.phase === "ended" || s.phase === "failed" || s.phase === "idle") return;
    this.status.set(
      phase === "ended" ? { ...s, phase, endedAt: Date.now() } : { ...s, phase, reason: reason ?? "Appel impossible." },
    );
  }

  private async close(): Promise<void> {
    if (this.timer) clearTimeout(this.timer);
    this.timer = null;
    const r = this.room;
    this.room = null;
    if (r) await r.disconnect().catch(() => {});
  }

  async hangUp(): Promise<void> {
    const s = this.status.get();
    await this.close();
    if (s.phase !== "idle" && s.phase !== "ended" && s.phase !== "failed")
      this.status.set({ ...s, phase: "ended", endedAt: Date.now() });
  }

  onCallState(cb: (status: CallStatus) => void): Unsubscribe {
    return this.status.subscribe(cb);
  }
}
