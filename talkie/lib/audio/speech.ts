// Mock only: the browser's own French voice (speechSynthesis) reading fixture lines, so a phone alone feels
// like the channel. Real speech comes from Gabriel over LiveKit.

let unlocked = false;

/** Call inside the join tap: iOS only lets speechSynthesis start from a gesture. */
export function unlockSpeech() {
  if (unlocked || typeof window === "undefined" || !("speechSynthesis" in window)) return;
  unlocked = true;
  try {
    const u = new SpeechSynthesisUtterance(" ");
    u.volume = 0;
    window.speechSynthesis.speak(u);
  } catch {
    // no voice: the mock falls back to a timer
  }
}

function frenchVoice(): SpeechSynthesisVoice | null {
  const voices = window.speechSynthesis.getVoices();
  return (
    voices.find((v) => v.lang === "fr-FR" && /thomas|daniel|google/i.test(v.name)) ??
    voices.find((v) => v.lang === "fr-FR") ??
    voices.find((v) => v.lang.startsWith("fr")) ??
    null
  );
}

export interface Spoken {
  done: Promise<void>;
  cancel: () => void;
}

/** Speak text; `done` resolves when it ends (or after a length-based timeout if the engine never says so). */
export function speak(text: string, who: "seraph" | "crew" | "caller", enabled = true): Spoken {
  // ~13 characters a second of radio French, plus a breath.
  const estimate = Math.min(22000, 900 + text.length * 78);
  let cancelTimer = () => {};
  let finish = () => {};
  const done = new Promise<void>((resolve) => {
    finish = resolve;
    const t = window.setTimeout(resolve, enabled ? estimate * 1.35 : estimate);
    cancelTimer = () => window.clearTimeout(t);
  });
  const hasSpeech = typeof window !== "undefined" && "speechSynthesis" in window;
  if (enabled && hasSpeech) {
    const u = new SpeechSynthesisUtterance(text);
    u.lang = "fr-FR";
    const v = frenchVoice();
    if (v) u.voice = v;
    u.rate = who === "crew" ? 1.12 : 1.05;
    u.pitch = who === "crew" ? 1.2 : 0.85;
    u.onend = () => finish();
    u.onerror = () => finish();
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(u);
  }
  void done.then(cancelTimer);
  return {
    done,
    cancel: () => {
      if (hasSpeech) window.speechSynthesis.cancel();
      finish();
    },
  };
}

/** Whether the mock should treat speech as real (any French or default voice available). */
export function speechAvailable(): boolean {
  return typeof window !== "undefined" && "speechSynthesis" in window;
}
