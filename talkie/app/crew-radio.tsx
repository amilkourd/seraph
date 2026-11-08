"use client";

// `/` — the crew radio on phone B. Call-sign picker, then one screen: hold to talk.
// Everything network goes through RadioTransport (lib/radio); this file only renders and makes the sounds.
import { useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { RadioDevPanel } from "@/components/RadioDevPanel";
import { ACCESS_DENIED, setAccessCode, withAccess } from "@/lib/access";
import { createRadio, speakerLabel, type LinkState, type RadioTransport } from "@/lib/radio";
import { busy, chirp, noiseBed, roger, squelchClose, squelchOpen, unlockAudio } from "@/lib/audio/sounds";
import { unlockSpeech } from "@/lib/audio/speech";
import { useWakeLock } from "@/lib/use-wake-lock";

const CALL_SIGNS = ["COS", "Tête", "Binôme 1", "Binôme 2"];
const MAX_TALK_MS = 60_000;
const STORE_KEY = "talkie.callSign";

type View = "idle" | "tx" | "rx" | "off";

function readStored(): string {
  try {
    return localStorage.getItem(STORE_KEY) ?? "";
  } catch {
    return "";
  }
}

function mmss(ms: number): string {
  const s = Math.floor(ms / 1000);
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}

export function CrewRadio() {
  const params = useSearchParams();
  const dev = params.get("dev") === "1";
  const [radio, setRadio] = useState<RadioTransport | null>(null);
  const [callSign, setCallSign] = useState<string | null>(null);

  useEffect(() => {
    const r = createRadio();
    // eslint-disable-next-line react-hooks/set-state-in-effect -- the transport touches window, so it is made after mount
    setRadio(r);
    return () => void r.leave();
  }, []);

  const [joinError, setJoinError] = useState<string | null>(null);

  const join = useCallback(
    (cs: string) => {
      if (!radio) return;
      // Inside the tap, before any await: iOS unlocks audio only here.
      const ctx = unlockAudio();
      unlockSpeech();
      try {
        localStorage.setItem(STORE_KEY, cs);
      } catch {
        // private mode: the picker just won't remember
      }
      setCallSign(cs);
      setJoinError(null);
      radio.join(cs, { audioContext: ctx ?? undefined }).catch((e: unknown) => {
        setJoinError(e instanceof Error ? e.message : "Canal crew injoignable.");
      });
    },
    [radio],
  );

  const leave = useCallback(() => {
    void radio?.leave();
    setCallSign(null);
    setJoinError(null);
  }, [radio]);

  return (
    <>
      {dev && radio && <DevAutoJoin radio={radio} join={join} joined={!!callSign} />}
      {!radio ? <main className="h-dvh bg-black" /> : null}
      {radio && !callSign && <CallSignPicker onJoin={join} />}
      {radio && callSign && (
        <RadioScreen
          radio={radio}
          callSign={callSign}
          joinError={joinError}
          onLeave={leave}
          onRetry={() => join(callSign)}
          dev={dev}
        />
      )}
    </>
  );
}

/**
 * `?dev=1&join=Tête&state=tx|rx|seraph|off` — join and hold a state without touching the screen, for simulator
 * screenshots and rehearsals. No audio on iOS this way (nothing unlocked it).
 */
function DevAutoJoin({ radio, join, joined }: { radio: RadioTransport; join: (cs: string) => void; joined: boolean }) {
  const params = useSearchParams();
  const as = params.get("join");
  const state = params.get("state");
  const done = useRef(false);
  useEffect(() => {
    if (!as || joined || done.current) return;
    done.current = true;
    join(as);
    const d = radio.dev;
    if (!d || !state) return;
    d.setAuto(false);
    // not cleared when `joined` flips: that re-run is exactly when this must still fire
    setTimeout(() => {
      if (state === "tx") d.holdFor(600_000);
      if (state === "rx") d.remoteTalks("Binôme 1", 600_000);
      if (state === "seraph") d.play("R12");
      if (state === "off") d.drop();
    }, 900);
  }, [as, state, joined, join, radio]);
  return null;
}

// ── picker ──

function CallSignPicker({ onJoin }: { onJoin: (cs: string) => void }) {
  const [picked, setPicked] = useState<string>(() => (typeof window === "undefined" ? "" : readStored()));
  const preset = CALL_SIGNS.includes(picked);
  const [free, setFree] = useState(() => (preset ? "" : picked));
  const value = (free.trim() || picked).trim();

  return (
    <main className="radio-surface safe-x safe-top safe-bottom flex h-dvh flex-col bg-black">
      {/* same header as the radio: one channel, the buttons below pick who you are on it */}
      <header className="flex items-start justify-between gap-3">
        <div>
          <span className="lockup block text-[15px] text-white">Canal crew</span>
          <span className="lockup mt-1.5 block text-[30px] text-white">Votre indicatif</span>
        </div>
        <ExerciceTag />
      </header>

      <div className="mt-[6dvh] flex flex-1 flex-col">
        <div className="grid grid-cols-2 gap-3">
          {CALL_SIGNS.map((cs) => {
            const on = !free.trim() && picked === cs;
            return (
              <button
                key={cs}
                type="button"
                onClick={() => {
                  setPicked(cs);
                  setFree("");
                }}
                aria-pressed={on}
                className={`radio-label h-[76px] rounded-[10px] border text-[19px] transition-colors ${
                  on
                    ? "border-white bg-white text-black"
                    : "border-white bg-black text-white active:bg-white active:text-black"
                }`}
              >
                {cs}
              </button>
            );
          })}
        </div>
        <label className="mt-3 block">
          <span className="sr-only">Autre indicatif</span>
          <input
            value={free}
            onChange={(e) => setFree(e.target.value.slice(0, 24))}
            placeholder="Autre indicatif"
            autoCapitalize="words"
            autoCorrect="off"
            spellCheck={false}
            enterKeyHint="go"
            onKeyDown={(e) => {
              if (e.key === "Enter" && value) onJoin(value);
            }}
            className={`radio-label h-[64px] w-full rounded-[10px] border bg-black px-4 text-[18px] text-white placeholder:text-white/50 focus:outline-none ${
              free.trim() ? "border-[3px] border-white" : "border-white"
            }`}
          />
        </label>

        <div className="flex-1" />

        <button
          type="button"
          disabled={!value}
          onClick={() => onJoin(value)}
          className="lockup h-[72px] w-full rounded-[12px] bg-white text-[17px] text-black transition-opacity disabled:opacity-30 active:opacity-80"
        >
          Rejoindre le canal
        </button>
      </div>
    </main>
  );
}

/** The public deploy refused the code (none in the link, or a wrong one): type it once, the phone keeps it. */
function AccessCodeCard({ onCode }: { onCode: (code: string) => void }) {
  const [code, setCode] = useState("");
  const ok = code.trim().length > 0;
  return (
    <form
      className="mb-3 rounded-[10px] border border-white bg-black p-4"
      onSubmit={(e) => {
        e.preventDefault();
        if (ok) onCode(code.trim());
      }}
    >
      <label className="lockup block text-[17px] text-white" htmlFor="access-code">
        Code d&apos;accès
      </label>
      <input
        id="access-code"
        value={code}
        onChange={(e) => setCode(e.target.value.slice(0, 64))}
        autoCapitalize="off"
        autoCorrect="off"
        autoComplete="off"
        spellCheck={false}
        enterKeyHint="go"
        className="mt-3 h-[56px] w-full rounded-[8px] border border-white bg-black px-4 font-mono text-[18px] text-white focus:outline-none"
      />
      <button
        type="submit"
        disabled={!ok}
        className="lockup mt-3 h-[52px] w-full rounded-[8px] bg-white text-[15px] text-black transition-opacity disabled:opacity-30"
      >
        Rejoindre
      </button>
    </form>
  );
}

function ExerciceTag({ mock = false }: { mock?: boolean }) {
  return (
    <span className="radio-label rounded-[5px] border border-white px-2.5 py-1 text-[14px] text-white">
      {mock ? "Exercice · mock" : "Exercice"}
    </span>
  );
}

// ── the radio ──

function RadioScreen({
  radio,
  callSign,
  joinError,
  onLeave,
  onRetry,
  dev,
}: {
  radio: RadioTransport;
  callSign: string;
  joinError: string | null;
  onLeave: () => void;
  onRetry: () => void;
  dev: boolean;
}) {
  const [link, setLink] = useState<LinkState>("connecting");
  const [local, setLocal] = useState(false);
  const [remote, setRemote] = useState<string | null>(null);
  const [talkStart, setTalkStart] = useState(0);
  const [now, setNow] = useState(() => Date.now());
  const buttonRef = useRef<HTMLButtonElement>(null);
  const holding = useRef(false);

  useWakeLock(true);

  // transport → state
  useEffect(() => {
    const offs = [radio.onState(setLink), radio.onLocalTalking(setLocal), radio.onRemoteTalking(setRemote)];
    return () => offs.forEach((off) => off());
  }, [radio]);

  // sounds on transitions
  const prevLocal = useRef(false);
  useEffect(() => {
    if (local && !prevLocal.current) {
      chirp();
      navigator.vibrate?.(18);
      setTalkStart(Date.now());
    }
    if (!local && prevLocal.current) roger();
    prevLocal.current = local;
  }, [local]);

  const prevRemote = useRef<string | null>(null);
  useEffect(() => {
    const was = prevRemote.current;
    if (remote && !was) {
      squelchOpen();
      noiseBed(true);
    } else if (!remote && was) {
      squelchClose();
      noiseBed(false);
    } else if (remote && was && remote !== was) {
      squelchClose();
      squelchOpen();
    }
    prevRemote.current = remote;
  }, [remote]);
  useEffect(() => () => noiseBed(false), []);

  // talk timer
  useEffect(() => {
    if (!local) return;
    const iv = setInterval(() => setNow(Date.now()), 200);
    return () => clearInterval(iv);
  }, [local]);

  const view: View = link !== "connected" ? "off" : local ? "tx" : remote ? "rx" : "idle";

  // ── press / release ──
  const release = useCallback(() => {
    if (!holding.current) return;
    holding.current = false;
    void radio.stopTalking();
  }, [radio]);

  const press = useCallback(() => {
    if (holding.current) return;
    if (view === "rx" || view === "off") {
      busy();
      navigator.vibrate?.([30, 40, 30]);
      return;
    }
    holding.current = true;
    void radio.startTalking().then((ok) => {
      if (!ok) {
        holding.current = false;
        busy();
        return;
      }
      // released before the transport answered: close the transmission right away
      if (!holding.current) void radio.stopTalking();
    });
  }, [radio, view]);

  // safety: 60 s max on air, release when the page hides
  useEffect(() => {
    if (!local) return;
    const t = setTimeout(() => {
      holding.current = true;
      release();
    }, MAX_TALK_MS);
    return () => clearTimeout(t);
  }, [local, release]);
  useEffect(() => {
    const onHide = () => {
      if (document.visibilityState === "hidden") release();
    };
    document.addEventListener("visibilitychange", onHide);
    window.addEventListener("pagehide", release);
    window.addEventListener("blur", release);
    return () => {
      document.removeEventListener("visibilitychange", onHide);
      window.removeEventListener("pagehide", release);
      window.removeEventListener("blur", release);
    };
  }, [release]);

  // keyboard: hold Space (laptop tests)
  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if (e.code !== "Space" || e.repeat || (e.target as HTMLElement)?.tagName === "INPUT") return;
      e.preventDefault();
      press();
    };
    const up = (e: KeyboardEvent) => {
      if (e.code !== "Space") return;
      e.preventDefault();
      release();
    };
    window.addEventListener("keydown", down);
    window.addEventListener("keyup", up);
    return () => {
      window.removeEventListener("keydown", down);
      window.removeEventListener("keyup", up);
    };
  }, [press, release]);

  // iOS: kill the long-press magnifier / callout on the button (React's touch listeners are passive)
  useEffect(() => {
    const b = buttonRef.current;
    if (!b) return;
    const stop = (e: Event) => e.preventDefault();
    b.addEventListener("touchstart", stop, { passive: false });
    b.addEventListener("contextmenu", stop);
    return () => {
      b.removeEventListener("touchstart", stop);
      b.removeEventListener("contextmenu", stop);
    };
  }, []);

  const remoteLabel = remote ? speakerLabel(remote) : null;

  const offLabel = link === "connecting" ? "Connexion…" : link === "reconnecting" ? "Reconnexion…" : "Hors canal";

  return (
    <main className="radio-surface relative flex h-dvh flex-col overflow-hidden bg-black">
      {/* top: channel, call sign, exercise */}
      <header className="safe-x safe-top relative z-10 flex items-start justify-between gap-3">
        <button
          type="button"
          onClick={onLeave}
          className="min-w-0 text-left"
          aria-label={`Canal crew, indicatif ${callSign}, changer`}
        >
          <span className="lockup block text-[15px] text-white">Canal crew</span>
          <span className="lockup mt-1.5 block max-w-full truncate text-[30px] text-white">{callSign}</span>
        </button>
        <ExerciceTag mock={radio.kind === "mock"} />
      </header>

      {/* centre: the button */}
      <section className="relative z-10 flex flex-1 items-center justify-center">
        <button
          ref={buttonRef}
          type="button"
          data-state={view}
          aria-label={
            view === "tx" ? "En émission, relâcher pour terminer" : view === "idle" ? "Maintenir pour parler" : offLabel
          }
          aria-disabled={view === "rx" || view === "off"}
          className="ptt"
          onPointerDown={(e) => {
            if (e.button !== 0) return;
            e.currentTarget.setPointerCapture(e.pointerId);
            press();
          }}
          onPointerUp={release}
          onPointerCancel={release}
          onLostPointerCapture={release}
        >
          <ButtonFace view={view} remote={remoteLabel} offLabel={offLabel} talkMs={now - talkStart} />
        </button>
      </section>

      {/* bottom: only when the channel cannot be joined */}
      <footer className="safe-x safe-bottom relative z-10">
        {view === "off" && joinError === ACCESS_DENIED && link === "offline" ? (
          <AccessCodeCard
            onCode={(code) => {
              setAccessCode(code);
              onRetry();
            }}
          />
        ) : view === "off" && joinError && link === "offline" ? (
          <div className="mb-3 rounded-[10px] border border-white bg-black p-4">
            <p className="lockup text-[17px] text-white">Canal indisponible</p>
            <p className="mt-2 text-[16px] text-white">{joinError}</p>
            <div className="mt-3 flex gap-2">
              <button
                type="button"
                onClick={onRetry}
                className="lockup h-[52px] flex-1 rounded-[8px] bg-white text-[15px] text-black"
              >
                Réessayer
              </button>
              {radio.kind !== "mock" && (
                <a
                  href={withAccess(`/?mock=1${dev ? "&dev=1" : ""}`)}
                  className="lockup grid h-[52px] flex-1 place-items-center rounded-[8px] border border-white text-[15px] text-white"
                >
                  Mode local
                </a>
              )}
            </div>
          </div>
        ) : null}
      </footer>

      {dev && <RadioDevPanel radio={radio} link={link} view={view} remote={remote} />}
    </main>
  );
}

function ButtonFace({
  view,
  remote,
  offLabel,
  talkMs,
}: {
  view: View;
  remote: string | null;
  offLabel: string;
  talkMs: number;
}) {
  if (view === "tx")
    return (
      <span className="flex flex-col items-center gap-2">
        <span className="lockup text-[18px]">En émission</span>
        <span className="lockup text-[52px] tabular-nums">{mmss(Math.max(0, talkMs))}</span>
      </span>
    );
  if (view === "rx")
    return (
      <span className="flex flex-col items-center gap-3 px-6">
        <LockGlyph />
        <span className="lockup text-[21px] leading-[1.05]">{remote ?? "Quelqu'un"} parle…</span>
      </span>
    );
  if (view === "off")
    return (
      <span className="flex flex-col items-center gap-3 px-6">
        <span className="lockup text-[16px] leading-[1.05]">{offLabel}</span>
      </span>
    );
  return (
    <span className="flex flex-col items-center gap-3 px-6">
      <MicGlyph />
      <span className="lockup text-[19px] leading-[1.1]">
        Maintenir
        <br />
        pour parler
      </span>
    </span>
  );
}

function MicGlyph() {
  return (
    <svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden>
      <rect x="9" y="3" width="6" height="11" rx="3" />
      <path d="M5 11a7 7 0 0 0 14 0M12 18v3" strokeLinecap="round" />
    </svg>
  );
}

function LockGlyph() {
  return (
    <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden>
      <rect x="5" y="11" width="14" height="10" rx="2" />
      <path d="M8 11V8a4 4 0 0 1 8 0v3" strokeLinecap="round" />
    </svg>
  );
}
