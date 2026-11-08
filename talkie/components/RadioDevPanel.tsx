"use client";

// `?dev=1` on `/`: jump to any state, play any fixture line, force disconnects. Mock transport only for the
// controls; with LiveKit it shows what the transport reports.
import { useEffect, useState } from "react";
import type { LinkState, RadioDevLog, RadioTransport } from "@/lib/radio";

export function RadioDevPanel({
  radio,
  link,
  view,
  remote,
}: {
  radio: RadioTransport;
  link: LinkState;
  view: string;
  remote: string | null;
}) {
  const [open, setOpen] = useState(false);
  const [ds, setDs] = useState<{ auto: boolean; voice: boolean; log: RadioDevLog[] }>({
    auto: false,
    voice: false,
    log: [],
  });
  const d = radio.dev;
  useEffect(() => d?.onDevState(setDs), [d]);

  const btn =
    "radio-label h-[40px] rounded-[6px] border border-white bg-black px-3 text-[11px] text-white active:bg-white active:text-black";
  const on = "radio-label h-[40px] rounded-[6px] border border-white bg-white px-3 text-[11px] text-black";

  return (
    <div className="radio-surface fixed inset-x-0 bottom-0 z-50" style={{ touchAction: "manipulation" }}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="radio-label absolute right-3 bottom-[calc(100%+6px)] rounded-[4px] border border-white bg-black px-2 py-1 text-[10px] text-white"
        style={open ? undefined : { bottom: "max(10px, env(safe-area-inset-bottom))" }}
      >
        {open ? "Fermer" : "Dev"}
      </button>
      {open && (
        <div className="safe-x safe-bottom max-h-[58dvh] overflow-y-auto border-t border-white bg-black pt-3 backdrop-blur">
          <p className="radio-label text-[10px] text-white">
            {radio.kind} · lien {link} · vue {view}
            {remote ? ` · ${remote}` : ""}
          </p>

          {!d ? (
            <p className="mt-2 text-[13px] text-white">Contrôles dev : transport mock seulement (?mock=1).</p>
          ) : (
            <>
              <p className="radio-label mt-3 text-[10px] text-white">États</p>
              <div className="mt-1 flex flex-wrap gap-2">
                <button type="button" className={btn} onClick={() => d.idle()}>
                  Repos
                </button>
                <button type="button" className={btn} onClick={() => d.holdFor(4000)}>
                  Émission 4 s
                </button>
                <button type="button" className={btn} onClick={() => d.seraphSays("Reçu, fumée 3e côté sud.")}>
                  Seraph parle
                </button>
                <button type="button" className={btn} onClick={() => d.remoteTalks("Tête", 4000)}>
                  Tête parle
                </button>
                <button type="button" className={btn} onClick={() => d.drop(5000)}>
                  Coupure 5 s
                </button>
                <button type="button" className={btn} onClick={() => d.drop()}>
                  Coupure
                </button>
                <button type="button" className={btn} onClick={() => d.reconnect()}>
                  Reconnecter
                </button>
              </div>

              <p className="radio-label mt-3 text-[10px] text-white">Rejeu radio.jsonl</p>
              <div className="mt-1 flex flex-wrap gap-2">
                <button type="button" className={ds.auto ? on : btn} onClick={() => d.setAuto(!ds.auto)}>
                  Auto {ds.auto ? "oui" : "non"}
                </button>
                <button type="button" className={ds.voice ? on : btn} onClick={() => d.setVoice(!ds.voice)}>
                  Voix {ds.voice ? "oui" : "non"}
                </button>
              </div>
              <div className="mt-2 grid grid-cols-1 gap-1">
                {d.lines.map((l) => (
                  <button
                    key={l.id}
                    type="button"
                    onClick={() => d.play(l.id)}
                    className="flex items-baseline gap-2 rounded-[6px] border border-white bg-black px-3 py-2 text-left active:bg-white active:text-black"
                  >
                    <span className="radio-label shrink-0 text-[10px] text-white">
                      {l.id} · {l.speaker}
                    </span>
                    <span className="truncate text-[12px] text-white">{l.text}</span>
                  </button>
                ))}
              </div>

              <p className="radio-label mt-3 text-[10px] text-white">Journal</p>
              <ol className="mt-1 mb-2 space-y-1">
                {ds.log.slice(0, 12).map((e, i) => (
                  <li key={`${e.t}-${i}`} className="font-mono text-[11px] leading-snug text-white">
                    <span className="text-white">
                      {new Date(e.t).toLocaleTimeString("fr-FR", { timeZone: "Europe/Paris" })}{" "}
                    </span>
                    {e.text}
                  </li>
                ))}
              </ol>
            </>
          )}
        </div>
      )}
    </div>
  );
}
