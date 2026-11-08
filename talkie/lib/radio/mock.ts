// Mock transports (the default). The crew channel replays contracts/fixtures/radio.jsonl: other speakers talk,
// Seraph answers with each line's `expected.say_crew`, and you can force disconnects from the `?dev=1` panel.
// When you transmit, Seraph answers with the next fixture line that has a say_crew (yours first).
import fixture from "./fixtures/radio.json";
import { babble } from "../audio/sounds";
import { speak, speechAvailable, type Spoken } from "../audio/speech";
import { encodeEot, SERAPH_IDENTITY, TOPIC_PTT } from "./payload";
import { Signal } from "./signal";
import type {
  CallDev,
  CallPhase,
  CallStatus,
  CallTransport,
  JoinOptions,
  LinkState,
  RadioDev,
  RadioDevLog,
  RadioLine,
  RadioTransport,
  Unsubscribe,
} from "./types";

const LINES = fixture as RadioLine[];

const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

class Aborted extends Error {}

export class MockRadio implements RadioTransport {
  readonly kind = "mock" as const;
  readonly dev: RadioDev;

  private link = new Signal<LinkState>("offline");
  private local = new Signal(false);
  private remote = new Signal<string | null>(null);
  private devState = new Signal<{ auto: boolean; voice: boolean; log: RadioDevLog[] }>({
    auto: true,
    voice: speechAvailable(),
    log: [],
  });

  private callSign = "";
  private cursor = 0;
  private epoch = 0;
  private talkStartedAt = 0;
  private speaking: Spoken | null = null;
  private stopBabble: (() => void) | null = null;
  private autoTimer: ReturnType<typeof setTimeout> | null = null;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private lastActivity = 0;
  private running = 0; // exchanges in flight

  constructor() {
    this.dev = {
      lines: LINES,
      play: (id) => {
        const line = LINES.find((l) => l.id === id);
        if (line) void this.run(line);
      },
      seraphSays: (text) => void this.seraphSays(text),
      remoteTalks: (speaker, ms = 3500) => void this.remoteFor(speaker, ms),
      holdFor: (ms = 4000) => {
        void this.startTalking().then((ok) => {
          if (ok) setTimeout(() => void this.stopTalking(), ms);
        });
      },
      idle: () => {
        if (this.link.get() === "offline") return;
        this.abortAll();
        this.reconnect();
      },
      drop: (ms) => this.drop(ms),
      reconnect: () => this.reconnect(),
      setAuto: (on) => {
        this.devState.set({ ...this.devState.get(), auto: on });
        this.scheduleAuto();
      },
      setVoice: (on) => this.devState.set({ ...this.devState.get(), voice: on }),
      onDevState: (cb) => this.devState.subscribe(cb),
    };
  }

  // ── RadioTransport ──

  async join(callSign: string, _options?: JoinOptions): Promise<void> {
    void _options; // the mock plays through the UI's unlocked context (lib/audio)
    this.callSign = callSign;
    const ep = ++this.epoch;
    this.link.set("connecting");
    await sleep(650);
    if (ep !== this.epoch) return;
    this.link.set("connected");
    this.log(`connecté à crew comme « ${callSign} »`);
    this.lastActivity = Date.now() - 12_000; // first auto line ~8 s after joining
    this.scheduleAuto();
  }

  async leave(): Promise<void> {
    this.abortAll();
    this.clearTimers();
    this.link.set("offline");
  }

  async startTalking(): Promise<boolean> {
    if (this.link.get() !== "connected" || this.remote.get() !== null || this.local.get()) return false;
    this.talkStartedAt = Date.now();
    this.local.set(true);
    this.log(`attribut talking=true (${this.callSign})`);
    return true;
  }

  async stopTalking(): Promise<void> {
    if (!this.local.get()) return;
    this.endLocal();
    const bytes = encodeEot(this.callSign);
    this.log(`${TOPIC_PTT} ← ${new TextDecoder().decode(bytes)}`);
    const held = Date.now() - this.talkStartedAt;
    if (held < 600) return; // a tap, not a message
    const line = this.nextAnswer();
    if (!line?.expected.say_crew) return;
    const say = line.expected.say_crew;
    const ep = this.epoch;
    this.running++;
    try {
      await sleep(1100); // Gabriel: STT final + Seraph + TTS
      if (ep !== this.epoch) return;
      await this.speakAs(SERAPH_IDENTITY, say, ep);
    } catch (e) {
      if (!(e instanceof Aborted)) throw e;
    } finally {
      this.running--;
    }
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

  // ── fixture playback ──

  private async run(line: RadioLine) {
    const ep = this.epoch;
    this.running++;
    try {
      if (line.speaker !== this.callSign) {
        await this.speakAs(line.speaker, line.text, ep);
        await sleep(800);
      }
      const say = line.expected.say_crew;
      if (say) await this.speakAs(SERAPH_IDENTITY, say, ep);
    } catch (e) {
      if (!(e instanceof Aborted)) throw e;
    } finally {
      this.running--;
      this.lastActivity = Date.now();
      this.scheduleAuto();
    }
  }

  private async seraphSays(text: string) {
    const ep = this.epoch;
    this.running++;
    try {
      await this.speakAs(SERAPH_IDENTITY, text, ep);
    } catch (e) {
      if (!(e instanceof Aborted)) throw e;
    } finally {
      this.running--;
    }
  }

  private async remoteFor(speaker: string, ms: number) {
    const ep = this.epoch;
    this.running++;
    try {
      await this.waitFloor(ep);
      this.remote.set(speaker);
      await sleep(ms);
      if (ep === this.epoch) this.remote.set(null);
    } catch (e) {
      if (!(e instanceof Aborted)) throw e;
    } finally {
      this.running--;
    }
  }

  /** Like Gabriel: wait until nobody is on air, take the floor, speak, release. */
  private async speakAs(identity: string, text: string, ep: number) {
    await this.waitFloor(ep);
    this.remote.set(identity);
    const isSeraph = identity === SERAPH_IDENTITY;
    this.log(`${identity} : ${text}`);
    const { voice } = this.devState.get();
    if (voice) {
      this.speaking = speak(text, isSeraph ? "seraph" : "crew", true);
      await this.speaking.done;
    } else {
      const ms = Math.min(9000, 900 + text.length * 60);
      this.stopBabble = babble(ms);
      await sleep(ms);
    }
    this.speaking = null;
    this.stopBabble = null;
    if (ep !== this.epoch) throw new Aborted();
    this.remote.set(null);
    this.lastActivity = Date.now();
  }

  private async waitFloor(ep: number) {
    for (;;) {
      if (ep !== this.epoch) throw new Aborted();
      if (this.link.get() === "connected" && !this.local.get() && this.remote.get() === null) return;
      await sleep(150);
    }
  }

  /** The next line Seraph answers when you transmit: yours first, else the next one with a say_crew. */
  private nextAnswer(): RadioLine | null {
    const n = LINES.length;
    for (const mineOnly of [true, false]) {
      for (let k = 0; k < n; k++) {
        const i = (this.cursor + k) % n;
        const l = LINES[i];
        if (!l.expected.say_crew) continue;
        if (mineOnly && l.speaker !== this.callSign) continue;
        this.cursor = i + 1;
        return l;
      }
    }
    return null;
  }

  /** The next line someone else says (auto replay). */
  private nextOther(): RadioLine | null {
    const n = LINES.length;
    for (let k = 0; k < n; k++) {
      const i = (this.cursor + k) % n;
      if (LINES[i].speaker !== this.callSign) {
        this.cursor = i + 1;
        return LINES[i];
      }
    }
    return null;
  }

  private scheduleAuto() {
    if (this.autoTimer) clearTimeout(this.autoTimer);
    this.autoTimer = null;
    if (!this.devState.get().auto || this.link.get() === "offline") return;
    this.autoTimer = setTimeout(() => {
      const quietFor = Date.now() - this.lastActivity;
      const free = this.link.get() === "connected" && !this.local.get() && this.remote.get() === null;
      if (free && this.running === 0 && quietFor > 20_000) {
        const line = this.nextOther();
        if (line) void this.run(line);
      }
      this.scheduleAuto();
    }, 2000);
  }

  // ── link faults ──

  private drop(ms?: number) {
    this.abortAll();
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    this.link.set("reconnecting");
    this.log(ms ? `coupure réseau (${Math.round(ms / 1000)} s)` : "coupure réseau");
    if (ms) this.reconnectTimer = setTimeout(() => this.reconnect(), ms);
  }

  private reconnect() {
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    this.reconnectTimer = null;
    if (this.link.get() === "offline") return;
    this.link.set("connected");
    this.lastActivity = Date.now();
    this.log("reconnecté");
    this.scheduleAuto();
  }

  private endLocal() {
    this.local.set(false);
  }

  private abortAll() {
    this.epoch++;
    this.speaking?.cancel();
    this.stopBabble?.();
    this.speaking = null;
    this.stopBabble = null;
    if (this.local.get()) this.endLocal();
    this.remote.set(null);
  }

  private clearTimers() {
    if (this.autoTimer) clearTimeout(this.autoTimer);
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    this.autoTimer = null;
    this.reconnectTimer = null;
  }

  private log(text: string) {
    const s = this.devState.get();
    this.devState.set({ ...s, log: [{ t: Date.now(), text }, ...s.log].slice(0, 40) });
    console.info(`[talkie mock] ${text}`);
  }
}

// ── web call ──

const CALL_SCRIPT = [
  "Où êtes-vous dans le bâtiment ? Quel étage, quelle salle ?",
  "Combien de personnes sont avec vous ?",
  "Voyez-vous de la fumée, ou sentez-vous de la chaleur près de vous ?",
  "Quelqu'un est-il blessé, ou ne peut pas marcher ?",
  "Que faites-vous en ce moment ?",
  "Je transmets aux pompiers. Restez en ligne.",
];

let callSeq = 90;

export class MockCall implements CallTransport {
  readonly kind = "mock" as const;
  readonly dev: CallDev;
  private status = new Signal<CallStatus>({ phase: "idle", direction: "in" });
  private epoch = 0;
  private speaking: Spoken | null = null;

  constructor() {
    this.dev = { force: (phase, reason) => this.force(phase, reason) };
  }

  async startCall(occId?: string, _options?: JoinOptions): Promise<void> {
    void _options;
    const ep = ++this.epoch;
    const direction = occId ? "out" : "in";
    const callId = `CALL-${callSeq++}`;
    this.status.set({ phase: "connecting", callId, direction });
    await sleep(1400); // room created, agent dispatched, agent joins
    if (ep !== this.epoch) return;
    this.status.set({ phase: "in_call", callId, direction, startedAt: Date.now() });
    const intro =
      direction === "in"
        ? "Exercice. Bonjour, ici Gabriel, l'assistant vocal des pompiers. Vous êtes sur la ligne 112 de l'exercice."
        : "Exercice. Bonjour, ici Gabriel, l'assistant vocal des pompiers.";
    for (const line of [intro, ...CALL_SCRIPT]) {
      if (ep !== this.epoch) return;
      await this.say(line, ep);
      await sleep(5500); // the caller answers (the mock does not listen)
    }
  }

  async hangUp(): Promise<void> {
    this.epoch++;
    this.speaking?.cancel();
    this.speaking = null;
    const s = this.status.get();
    if (s.phase === "idle" || s.phase === "ended") return;
    this.status.set({ ...s, phase: "ended", endedAt: Date.now() });
  }

  onCallState(cb: (status: CallStatus) => void): Unsubscribe {
    return this.status.subscribe(cb);
  }

  private async say(text: string, ep: number) {
    this.speaking = speak(text, "seraph", speechAvailable());
    await this.speaking.done;
    if (ep === this.epoch) this.speaking = null;
  }

  private force(phase: CallPhase, reason?: string) {
    const s = this.status.get();
    if (phase !== "in_call" && phase !== "connecting") {
      this.epoch++;
      this.speaking?.cancel();
    }
    const callId = s.callId ?? `CALL-${callSeq++}`;
    if (phase === "idle") this.status.set({ phase, direction: s.direction });
    else if (phase === "connecting") this.status.set({ phase, callId, direction: s.direction });
    else if (phase === "in_call")
      this.status.set({ phase, callId, direction: s.direction, startedAt: Date.now() - 42_000 });
    else if (phase === "ended")
      this.status.set({ ...s, phase, callId, startedAt: s.startedAt ?? Date.now() - 72_000, endedAt: Date.now() });
    else this.status.set({ phase, callId, direction: s.direction, reason: reason ?? "Gabriel ne répond pas." });
  }
}
