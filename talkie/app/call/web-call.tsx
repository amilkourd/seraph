"use client";

// `/call?occ=OCC-07` — web call for an occupant (direction "out"); without `occ`, an incoming 112 call ("in").
// Full duplex through CallTransport (lib/radio). This file renders and keeps the screen on.
import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { createCall, type CallPhase, type CallStatus, type CallTransport } from "@/lib/radio";
import { roger, unlockAudio } from "@/lib/audio/sounds";
import { unlockSpeech } from "@/lib/audio/speech";
import { useWakeLock } from "@/lib/use-wake-lock";

function mmss(ms: number): string {
  const s = Math.max(0, Math.floor(ms / 1000));
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}

export function WebCall() {
  const params = useSearchParams();
  const occ = params.get("occ")?.trim() || undefined;
  const dev = params.get("dev") === "1";
  const [call, setCall] = useState<CallTransport | null>(null);
  const [status, setStatus] = useState<CallStatus>({ phase: "idle", direction: occ ? "out" : "in" });
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const c = createCall();
    // eslint-disable-next-line react-hooks/set-state-in-effect -- the transport touches window, so it is made after mount
    setCall(c);
    const off = c.onCallState(setStatus);
    return () => {
      off();
      void c.hangUp();
    };
  }, []);

  const live = status.phase === "connecting" || status.phase === "in_call";
  useWakeLock(live);

  useEffect(() => {
    if (status.phase !== "in_call") return;
    const iv = setInterval(() => setNow(Date.now()), 250);
    return () => clearInterval(iv);
  }, [status.phase]);

  // hang-up tone when the line closes
  const prevPhase = useRef<CallPhase>("idle");
  useEffect(() => {
    if (prevPhase.current === "in_call" && status.phase === "ended") roger();
    prevPhase.current = status.phase;
  }, [status.phase]);

  const start = () => {
    if (!call) return;
    const ctx = unlockAudio(); // inside the tap (iOS)
    unlockSpeech();
    call.startCall(occ, { audioContext: ctx ?? undefined }).catch(() => {
      // the transport reports failures through onCallState
    });
  };

  const elapsed =
    status.phase === "in_call" && status.startedAt
      ? now - status.startedAt
      : status.startedAt && status.endedAt
        ? status.endedAt - status.startedAt
        : 0;

  return (
    <main className="radio-surface relative flex h-dvh flex-col overflow-hidden bg-black">
      <header className="safe-x safe-top relative z-10 flex justify-end">
        <span className="radio-label rounded-[5px] border border-white px-2.5 py-1 text-[14px] text-white">
          {call?.kind === "mock" ? "Exercice · mock" : "Exercice"}
        </span>
      </header>

      <section className="safe-x relative z-10 flex flex-1 flex-col items-center justify-center text-center">
        {status.phase === "idle" && (
          <>
            <div>
              <button
                type="button"
                onClick={start}
                disabled={!call}
                className="grid aspect-square w-[min(62vw,300px)] place-items-center rounded-full border-[3px] border-white bg-black px-8 text-white transition-transform active:scale-[0.97]"
              >
                <span className="flex flex-col items-center gap-4">
                  <PhoneGlyph />
                  <span className="lockup text-[22px] leading-[1.08]">
                    Appeler
                    <br />
                    les pompiers
                  </span>
                  <span className="lockup text-[16px]">(exercice)</span>
                </span>
              </button>
            </div>
          </>
        )}

        {status.phase === "connecting" && (
          <>
            <div>
              <p className="lockup text-[26px] text-white">Connexion…</p>
            </div>
          </>
        )}

        {status.phase === "in_call" && (
          <div className="flex w-full flex-1 flex-col items-center justify-between py-[3dvh]">
            <p className="max-w-[24ch] text-[21px] leading-[1.3] text-white">
              Vous parlez à Gabriel, assistant vocal (exercice)
            </p>
            <div>
              <p className="lockup text-[60px] tabular-nums text-white">{mmss(elapsed)}</p>
            </div>
            <div aria-hidden />
          </div>
        )}

        {status.phase === "ended" && (
          <>
            <div>
              <p className="lockup text-[52px] tabular-nums text-white">{mmss(elapsed)}</p>
            </div>
          </>
        )}

        {status.phase === "failed" && (
          <>
            <div>
              <p className="lockup text-[26px] text-white">Appel impossible</p>
            </div>
            <p className="mt-3 max-w-[30ch] text-[17px] text-white">{status.reason ?? "Réseau indisponible."}</p>
          </>
        )}
      </section>

      <footer className="safe-x safe-bottom relative z-10 flex flex-col items-center">
        {live ? (
          <button
            type="button"
            onClick={() => void call?.hangUp()}
            className="lockup flex h-[76px] w-full max-w-[420px] items-center justify-center gap-3 rounded-[14px] bg-white text-[19px] text-black active:opacity-80"
          >
            <HangUpGlyph />
            Raccrocher
          </button>
        ) : status.phase === "ended" || status.phase === "failed" ? (
          <button
            type="button"
            onClick={start}
            className={`lockup h-[76px] w-full max-w-[420px] rounded-[14px] text-[19px] active:opacity-80 ${
              status.phase === "ended" ? "border-[3px] border-white text-white" : "bg-white text-black"
            }`}
          >
            {status.phase === "ended" ? "Rappeler" : "Réessayer"}
          </button>
        ) : null}
      </footer>

      {dev && call?.dev && <CallDevBar call={call} />}
    </main>
  );
}

function CallDevBar({ call }: { call: CallTransport }) {
  const phases: CallPhase[] = ["idle", "connecting", "in_call", "ended", "failed"];
  return (
    <div className="safe-x fixed inset-x-0 top-[calc(max(14px,env(safe-area-inset-top))+40px)] z-50 flex flex-wrap gap-1">
      {phases.map((p) => (
        <button
          key={p}
          type="button"
          onClick={() => call.dev?.force(p)}
          className="radio-label h-[32px] rounded-[5px] border border-white bg-black px-2 text-[10px] text-white"
        >
          {p}
        </button>
      ))}
    </div>
  );
}

function PhoneGlyph() {
  return (
    <svg width="34" height="34" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden>
      <path
        d="M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function HangUpGlyph() {
  return (
    <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
      <path d="M3 14.5c5-4.7 13-4.7 18 0l-2.2 2.6-3.6-1.3v-2.5a9 9 0 0 0-6.4 0v2.5l-3.6 1.3z" strokeLinejoin="round" />
    </svg>
  );
}
