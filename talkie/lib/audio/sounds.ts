// Radio sounds, synthesized with Web Audio (no files): chirp on press, roger beep on release, squelch clicks
// around received audio, a faint noise bed while receiving, and the band-pass filter for received voices.
// One AudioContext for the whole app, unlocked by unlockAudio() inside a tap (iOS).

type WebkitWindow = Window & { webkitAudioContext?: typeof AudioContext };
type AudioSessionNavigator = Navigator & { audioSession?: { type: string } };

let ctx: AudioContext | null = null;
let master: GainNode | null = null;
let noiseBuf: AudioBuffer | null = null;
let bed: { src: AudioBufferSourceNode; gain: GainNode } | null = null;

export function audioContext(): AudioContext | null {
  return ctx;
}

/**
 * Create and resume the AudioContext. Call it synchronously inside a click/tap handler, before any await:
 * iOS only lets audio start from a user gesture.
 */
export function unlockAudio(): AudioContext | null {
  if (typeof window === "undefined") return null;
  try {
    // iOS: without this, Web Audio follows the ring/silent switch. "playback" ignores it (Safari 17+).
    const nav = navigator as AudioSessionNavigator;
    if (nav.audioSession && nav.audioSession.type === "auto") nav.audioSession.type = "playback";
  } catch {
    // older Safari: the silent switch mutes us; the status file tells the crew to flip it
  }
  if (!ctx) {
    const Ctor = window.AudioContext ?? (window as WebkitWindow).webkitAudioContext;
    if (!Ctor) return null;
    ctx = new Ctor({ latencyHint: "interactive" });
    const comp = ctx.createDynamicsCompressor();
    comp.threshold.value = -14;
    comp.ratio.value = 4;
    master = ctx.createGain();
    master.gain.value = 0.9;
    master.connect(comp).connect(ctx.destination);
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "visible") void ctx?.resume();
    });
  }
  void ctx.resume();
  // A one-sample silent buffer started inside the gesture is what actually unlocks iOS.
  const b = ctx.createBuffer(1, 1, ctx.sampleRate);
  const s = ctx.createBufferSource();
  s.buffer = b;
  s.connect(ctx.destination);
  s.start(0);
  return ctx;
}

function out(): { c: AudioContext; m: GainNode } | null {
  if (!ctx || !master) return null;
  if (ctx.state !== "running") void ctx.resume();
  return { c: ctx, m: master };
}

function noise(c: AudioContext): AudioBuffer {
  if (noiseBuf && noiseBuf.sampleRate === c.sampleRate) return noiseBuf;
  const len = c.sampleRate * 2;
  noiseBuf = c.createBuffer(1, len, c.sampleRate);
  const d = noiseBuf.getChannelData(0);
  for (let i = 0; i < len; i++) d[i] = Math.random() * 2 - 1;
  return noiseBuf;
}

function tone(freq: number, at: number, dur: number, gain = 0.22, type: OscillatorType = "square") {
  const o = out();
  if (!o) return;
  const { c, m } = o;
  const osc = c.createOscillator();
  osc.type = type;
  osc.frequency.setValueAtTime(freq, at);
  const lp = c.createBiquadFilter();
  lp.type = "lowpass";
  lp.frequency.value = 3200;
  const g = c.createGain();
  g.gain.setValueAtTime(0, at);
  g.gain.linearRampToValueAtTime(gain, at + 0.004);
  g.gain.setValueAtTime(gain, at + dur - 0.012);
  g.gain.linearRampToValueAtTime(0, at + dur);
  osc.connect(lp).connect(g).connect(m);
  osc.start(at);
  osc.stop(at + dur + 0.02);
}

function burst(at: number, dur: number, gain: number, fromHz: number, toHz: number) {
  const o = out();
  if (!o) return;
  const { c, m } = o;
  const src = c.createBufferSource();
  src.buffer = noise(c);
  const bp = c.createBiquadFilter();
  bp.type = "bandpass";
  bp.Q.value = 0.9;
  bp.frequency.setValueAtTime(fromHz, at);
  bp.frequency.exponentialRampToValueAtTime(toHz, at + dur);
  const g = c.createGain();
  g.gain.setValueAtTime(gain, at);
  g.gain.exponentialRampToValueAtTime(0.001, at + dur);
  src.connect(bp).connect(g).connect(m);
  src.start(at, Math.random());
  src.stop(at + dur + 0.02);
}

function click(at: number, gain = 0.35) {
  const o = out();
  if (!o) return;
  const { c, m } = o;
  const b = c.createBuffer(1, Math.floor(c.sampleRate * 0.004), c.sampleRate);
  const d = b.getChannelData(0);
  for (let i = 0; i < d.length; i++) d[i] = (Math.random() * 2 - 1) * (1 - i / d.length);
  const s = c.createBufferSource();
  s.buffer = b;
  const g = c.createGain();
  g.gain.value = gain;
  s.connect(g).connect(m);
  s.start(at);
}

const now = () => (ctx ? ctx.currentTime + 0.005 : 0);

/** Press: you have the floor. */
export function chirp() {
  const t = now();
  click(t, 0.25);
  tone(1050, t + 0.01, 0.045);
  tone(1560, t + 0.07, 0.07);
}

/** Release: the classic two-tone roger beep, then a squelch tail. */
export function roger() {
  const t = now();
  tone(1250, t, 0.07, 0.2);
  tone(880, t + 0.08, 0.11, 0.2);
  burst(t + 0.2, 0.14, 0.12, 2600, 1200);
}

/** Someone else starts transmitting. */
export function squelchOpen() {
  const t = now();
  click(t, 0.3);
  burst(t, 0.06, 0.16, 2400, 1800);
}

/** Someone else stops: the « kssht » tail. */
export function squelchClose() {
  const t = now();
  burst(t, 0.18, 0.22, 3200, 1100);
  click(t + 0.18, 0.18);
}

/** Pressed while the floor is taken. */
export function busy() {
  const t = now();
  tone(420, t, 0.09, 0.18);
  tone(420, t + 0.15, 0.09, 0.18);
}

/** Faint band-limited hiss under received audio. */
export function noiseBed(on: boolean) {
  const o = out();
  if (!o) return;
  const { c, m } = o;
  const t = c.currentTime;
  if (on && !bed) {
    const src = c.createBufferSource();
    src.buffer = noise(c);
    src.loop = true;
    const hp = c.createBiquadFilter();
    hp.type = "highpass";
    hp.frequency.value = 300;
    const lp = c.createBiquadFilter();
    lp.type = "lowpass";
    lp.frequency.value = 3000;
    const gain = c.createGain();
    gain.gain.setValueAtTime(0, t);
    gain.gain.linearRampToValueAtTime(0.028, t + 0.05);
    src.connect(hp).connect(lp).connect(gain).connect(m);
    src.start();
    bed = { src, gain };
  } else if (!on && bed) {
    const b = bed;
    bed = null;
    b.gain.gain.cancelScheduledValues(t);
    b.gain.gain.setValueAtTime(b.gain.gain.value, t);
    b.gain.gain.linearRampToValueAtTime(0, t + 0.08);
    b.src.stop(t + 0.1);
  }
}

/**
 * The radio voice: band-pass 300–3000 Hz, a presence bump and a soft clip. Returns UNCONNECTED nodes in order,
 * the shape LiveKit's `RemoteAudioTrack.setWebAudioPlugins(nodes)` chains itself. For a manual graph, use
 * `chain(nodes)` and connect source → first, last → destination. The UI adds the hiss (noiseBed) itself.
 */
export function radioFilter(c: AudioContext): AudioNode[] {
  const hp = c.createBiquadFilter();
  hp.type = "highpass";
  hp.frequency.value = 300;
  hp.Q.value = 0.7;
  const lp = c.createBiquadFilter();
  lp.type = "lowpass";
  lp.frequency.value = 3000;
  lp.Q.value = 0.7;
  const presence = c.createBiquadFilter();
  presence.type = "peaking";
  presence.frequency.value = 1800;
  presence.gain.value = 4;
  const clip = c.createWaveShaper();
  const curve = new Float32Array(1024);
  for (let i = 0; i < curve.length; i++) {
    const x = (i / (curve.length - 1)) * 2 - 1;
    curve[i] = Math.tanh(1.6 * x) / Math.tanh(1.6);
  }
  clip.curve = curve;
  const makeup = c.createGain();
  makeup.gain.value = 1.15;
  return [hp, lp, presence, clip, makeup];
}

export function chain(nodes: AudioNode[]): { input: AudioNode; output: AudioNode } {
  for (let i = 0; i < nodes.length - 1; i++) nodes[i].connect(nodes[i + 1]);
  return { input: nodes[0], output: nodes[nodes.length - 1] };
}

/**
 * Mock only: a filtered "voice-like" murmur for ms, for crew lines when speech synthesis is off.
 * Calls onLevel ~15 Hz with 0..1. Returns a stop function.
 */
export function babble(ms: number, onLevel?: (l: number) => void): () => void {
  const o = out();
  if (!o) return () => {};
  const { c, m } = o;
  const t = c.currentTime;
  const src = c.createBufferSource();
  src.buffer = noise(c);
  src.loop = true;
  const formant = c.createBiquadFilter();
  formant.type = "bandpass";
  formant.Q.value = 3;
  formant.frequency.value = 700;
  const env = c.createGain();
  env.gain.value = 0;
  const nodes = radioFilter(c);
  const { input, output } = chain(nodes);
  src.connect(formant).connect(env).connect(input);
  output.connect(m);
  src.start(t);
  let alive = true;
  const started = performance.now();
  const iv = window.setInterval(() => {
    const el = (performance.now() - started) / 1000;
    const syl = Math.max(0, Math.sin(el * 2 * Math.PI * 4.3) * Math.sin(el * 2 * Math.PI * 1.1 + 0.7));
    const level = Math.min(1, 0.15 + syl * 0.9);
    const ct = c.currentTime;
    env.gain.setTargetAtTime(level * 0.9, ct, 0.02);
    formant.frequency.setTargetAtTime(500 + Math.random() * 1400, ct, 0.04);
    onLevel?.(level);
  }, 66);
  const stop = () => {
    if (!alive) return;
    alive = false;
    window.clearInterval(iv);
    const ct = c.currentTime;
    env.gain.setTargetAtTime(0, ct, 0.02);
    src.stop(ct + 0.1);
    onLevel?.(0);
  };
  window.setTimeout(stop, ms);
  return stop;
}
