"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { FLAME_COLOR, type FlameModule } from "@/lib/bloub/flamme";
import type { StateId } from "@/lib/bloub/states";
import type { Live } from "@/lib/live";
import { Flamme } from "./Flamme";

// The judges' tour: they open the public replay alone, Seraph's flame walks them around the stage one part at a
// time, in the colour of the module that acts. The first visit in a browser opens on « Bienvenue sur Seraph » (public
// replay only; ?tour anywhere); key T and « Visite guidée » go straight to step 1. Rects are stage pixels (1920×1080).
type Rect = { x: number; y: number; w: number; h: number };
type Step = {
  at: string; // data-tour of the element (a Card is tagged with its title), or "batiment" / "tout" (fixed frames)
  state: StateId;
  expression: string;
  module: FlameModule;
  text: string;
  act?: string; // what the judge can do there
  alt?: { at: string; text: string }; // when the element is not on screen
};

// Only idle, wink, wide, notify and swirl keep the flame body (Bloub's `baseBody`): the others turn it into dots, a
// « ! » or a ball. So the flame stays a flame and its face changes, with rings and a notification for punctuation
// (no wink: the eyes stay wide open).
const STEPS: Step[] = [
  { at: "titre", state: "idle", expression: "surpris", module: "seraph", text: "Exercice. Une voiture brûle au parking. L'immeuble n'a qu'un escalier." },
  { at: "ecrans", state: "idle", expression: "mefiant", module: "rosetta", text: "Seraph a lu l'alerte, Maps, Street View, Géorisques. Aucun de ces écrans n'a d'API." },
  { at: "batiment", state: "idle", expression: "curieux", module: "seraph", text: "Une vraie maquette d'architecte. Feu, fumée, personnes : chaque point dit d'où il vient.", act: "Tournez-la à la souris." },
  { at: "halo", state: "swirl", expression: "fier", module: "silex", text: "Le poignet du pompier. Devin a écrit cette vue pendant le trajet." },
  { at: "radio", state: "notify", expression: "excite", module: "gabriel", text: "La radio des pompiers. Seraph écoute et répond en une seconde." },
  { at: "À l'intérieur", state: "idle", expression: "heureux", module: "gabriel", text: "Seraph a appelé chaque habitant, dans sa langue." },
  { at: "Alertes", state: "idle", expression: "effraye", module: "seraph", text: "Tom descendait l'escalier enfumé. Seraph a proposé : reste chez toi, va sur ton balcon.", alt: { at: "batiment", text: "Tom descendait l'escalier enfumé. Seraph a proposé : reste chez toi, va sur ton balcon." } },
  {
    at: "Décision COS",
    state: "idle",
    expression: "attentif",
    module: "seraph",
    text: "Rien ne part sans le commandant.",
    act: "À vous : Confirmer.",
    alt: { at: "activite", text: "Rien ne part sans le commandant. Chaque ordre attend son « confirme »." },
  },
  { at: "tout", state: "idle", expression: "hilare", module: "seraph", text: "Seraph transforme n'importe quel écran en API." },
];

const STAGE: Rect = { x: 0, y: 0, w: 1920, h: 1080 };
const BUILDING: Rect = { x: 600, y: 90, w: 720, h: 900 }; // the 3D model has no element of its own
const BUBBLE_W = 600;
const SEEN = "seraph-tour";
const GLIDE = "left 550ms var(--ease), top 550ms var(--ease), width 550ms var(--ease), height 550ms var(--ease)";
const corner = (left: number | undefined, top: number | undefined, right: number | undefined, bottom: number | undefined, width: string, dx: number, dy: number) =>
  ({ left, top, right, bottom, borderColor: "#ffffff", borderStyle: "solid", borderWidth: width, "--dx": `${dx}px`, "--dy": `${dy}px` }) as React.CSSProperties;
const CORNERS = [
  { id: "tl", style: corner(-12, -12, undefined, undefined, "3px 0 0 3px", -20, -20) },
  { id: "tr", style: corner(undefined, -12, -12, undefined, "3px 3px 0 0", 20, -20) },
  { id: "bl", style: corner(-12, undefined, undefined, -12, "0 0 3px 3px", -20, 20) },
  { id: "br", style: corner(undefined, undefined, -12, -12, "0 3px 3px 0", 20, 20) },
];
const LOCK = `
@keyframes tour-lock { from { transform: translate(var(--dx), var(--dy)); opacity: 0; } to { transform: none; opacity: 1; } }
@keyframes tour-breathe { from { transform: none; } to { transform: translate(calc(var(--dx) * 0.4), calc(var(--dy) * 0.4)); } }
.tour-corner { animation: tour-lock 420ms var(--ease) both, tour-breathe 850ms ease-in-out 420ms infinite alternate; }
@media (prefers-reduced-motion: reduce) { .tour-corner { animation: none; } }
`;

function wanted(mock: boolean): boolean {
  if (typeof window === "undefined") return false;
  if (new URLSearchParams(window.location.search).has("tour")) return true;
  if (!mock) return false;
  try {
    return localStorage.getItem(SEEN) !== "vu";
  } catch {
    return true;
  }
}

// The welcome flame never stands still: a gesture, a face, the next gesture, in a loop.
const HELLO: { state: StateId; expression: string; ms: number }[] = [
  { state: "idle", expression: "surpris", ms: 1800 },
  { state: "swirl", expression: "excite", ms: 1500 },
  { state: "idle", expression: "excite", ms: 1800 },
  { state: "wide", expression: "curieux", ms: 1600 },
  { state: "idle", expression: "curieux", ms: 1800 },
  { state: "notify", expression: "heureux", ms: 1800 },
  { state: "idle", expression: "heureux", ms: 2000 },
];

/** The first visit in a browser: Seraph says hello and offers the tour. « Plus tard » counts as seen. */
function Welcome({ start, later }: { start: () => void; later: () => void }) {
  const [k, setK] = useState(0);
  useEffect(() => {
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return;
    const t = setTimeout(() => setK((n) => (n + 1) % HELLO.length), HELLO[k].ms);
    return () => clearTimeout(t);
  }, [k]);
  const hello = HELLO[k];
  return (
    <>
      <div className="absolute inset-0 bg-[rgba(11,10,10,0.72)]" />
      <div
        role="dialog"
        aria-label="Bienvenue sur Seraph"
        className="pointer-events-auto absolute left-1/2 top-1/2 flex w-[760px] -translate-x-1/2 -translate-y-1/2 flex-col items-center gap-8 rounded-[28px] border border-fumee bg-suie px-14 pb-12 pt-10 text-center text-blanc"
      >
        <Flamme state={hello.state} expression={hello.expression} color={FLAME_COLOR.seraph} paper="#0b0a0a" size={220} />
        <h2 className="t-display text-[72px] leading-none text-blanc">Bienvenue sur Seraph</h2>
        <p className="text-[26px] leading-[1.35] text-blanc [text-wrap:balance]">Le copilote des pompiers. La visite vous montre l&apos;écran en neuf étapes, deux minutes.</p>
        <div className="flex items-center gap-4">
          <button type="button" onClick={start} className="h-14 rounded-full px-8 text-[20px] font-semibold text-suie" style={{ background: FLAME_COLOR.seraph }}>
            Commencer la visite
          </button>
          <button type="button" onClick={later} className="h-14 rounded-full border border-brume px-8 text-[20px] text-blanc">
            Plus tard
          </button>
        </div>
      </div>
    </>
  );
}

export function Tour({ live }: { live: Live }) {
  const root = useRef<HTMLDivElement>(null);
  const [chosen, setOpen] = useState<boolean | null>(null); // null until the judge opens or closes it
  const [i, setI] = useState(-1); // -1: the welcome, before the first step
  const [rect, setRect] = useState<Rect | null>(null);
  const [missing, setMissing] = useState(false);
  const mock = live.mode === "mock";
  // by itself once the mode is known: on the public replay, or when asked with ?tour
  const open = chosen ?? (live.mode !== "connecting" && wanted(mock));

  const close = useCallback(() => {
    setOpen(false);
    setI(-1);
    try {
      localStorage.setItem(SEEN, "vu");
    } catch {}
  }, []);
  const go = useCallback((n: number) => {
    if (n >= STEPS.length) return close();
    setI(Math.max(0, n));
  }, [close]);

  // the element of the step, in stage pixels; measured again while the replay moves things around
  useEffect(() => {
    if (!open || i < 0) return;
    const step = STEPS[i];
    const measure = () => {
      const stage = root.current?.getBoundingClientRect();
      if (!stage) return;
      const k = stage.width / 1920;
      const find = (at: string): Rect | null => {
        if (at === "tout") return STAGE;
        if (at === "batiment") return BUILDING;
        const el = root.current?.parentElement?.querySelector(`[data-tour="${at}"]`);
        if (!el) return null;
        const r = el.getBoundingClientRect();
        return { x: (r.left - stage.left) / k, y: (r.top - stage.top) / k, w: r.width / k, h: r.height / k };
      };
      const own = find(step.at);
      if (own) {
        setMissing(false);
        setRect(own);
      } else {
        setMissing(true);
        setRect(step.alt ? find(step.alt.at) ?? STAGE : STAGE);
      }
    };
    measure();
    const t = setInterval(measure, 400);
    return () => clearInterval(t);
  }, [open, i]);

  // arrows and Enter move the tour, Escape closes it; caught before the dashboard's keys (Escape cancels a decision)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if (!open) {
        if (e.key === "t" || e.key === "T") {
          setI(0);
          setOpen(true);
        }
        return;
      }
      const keys: Record<string, () => void> = {
        ArrowRight: () => go(i + 1),
        Enter: () => go(i + 1),
        ArrowLeft: () => go(i - 1),
        Escape: close,
      };
      const act = keys[e.key];
      if (!act) return;
      e.preventDefault();
      e.stopImmediatePropagation();
      act();
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [open, i, go, close]);

  const step = STEPS[Math.max(i, 0)];
  const color = FLAME_COLOR[step.module];
  const text = missing && step.alt ? step.alt.text : step.text;
  const act = missing ? undefined : step.act;
  const whole = !rect || rect === STAGE || step.at === "tout";
  const pad = 14;
  const spot = rect && !whole ? { x: rect.x - pad, y: rect.y - pad, w: rect.w + pad * 2, h: rect.h + pad * 2 } : null;

  // the bubble sits beside the spotlight, on the side with room, and never leaves the stage
  let bx = (1920 - BUBBLE_W) / 2;
  let by = 330;
  if (spot) {
    const right = spot.x + spot.w + 32;
    const left = spot.x - 32 - BUBBLE_W;
    if (right + BUBBLE_W <= 1920 - 24) bx = right;
    else if (left >= 24) bx = left;
    else bx = Math.min(Math.max(spot.x, 24), 1920 - 24 - BUBBLE_W);
    by = Math.min(Math.max(spot.y + spot.h / 2 - 170, 24), 1080 - 24 - 380);
    if (bx === spot.x || (bx < spot.x + spot.w && bx + BUBBLE_W > spot.x)) by = spot.y + spot.h + 24 > 1080 - 380 ? Math.max(spot.y - 24 - 380, 24) : spot.y + spot.h + 24;
  }

  return (
    <div ref={root} className="pointer-events-none absolute inset-0 z-50">
      {open && i < 0 && <Welcome start={() => go(0)} later={close} />}
      {open && i >= 0 && (
        <>
          <style>{LOCK}</style>
          {spot ? (
            <>
              <div className="absolute" style={{ left: spot.x, top: spot.y, width: spot.w, height: spot.h, boxShadow: "0 0 0 4000px rgba(11, 10, 10, 0.55)", transition: GLIDE }} />
              {/* a white target, as on Halo: four corners close in on the part, no frame (remounted each step) */}
              <div key={i} className="absolute" style={{ left: spot.x, top: spot.y, width: spot.w, height: spot.h }}>
                {CORNERS.map((c) => (
                  <i key={c.id} className="tour-corner absolute block h-7 w-7" style={c.style} />
                ))}
              </div>
            </>
          ) : (
            <div className="absolute inset-0 bg-[rgba(11,10,10,0.5)]" />
          )}
          <div
            className="pointer-events-auto absolute flex flex-col gap-6 rounded-[24px] border border-fumee bg-suie p-8 text-blanc"
            style={{ left: bx, top: by, width: BUBBLE_W, transition: "left 550ms var(--ease), top 550ms var(--ease)" }}
            role="dialog"
            aria-label="Visite guidée"
          >
            <div className="flex items-center gap-5">
              <Flamme state={step.state} expression={step.expression} color={color} paper="#0b0a0a" size={128} />
              <span className="mono text-[17px] text-brume">
                {i + 1} / {STEPS.length}
              </span>
            </div>
            <p className="t-display text-[36px] leading-[1.12] text-blanc [text-wrap:balance]">{text}</p>
            {act && (
              <p className="text-[24px] font-semibold" style={{ color }}>
                {act}
              </p>
            )}
            <div className="flex items-center gap-3">
              <button type="button" onClick={() => go(i + 1)} className="h-12 rounded-full px-6 text-[18px] font-semibold text-suie" style={{ background: color }}>
                {i === STEPS.length - 1 ? "Terminer" : "Suivant"}
              </button>
              {i > 0 && (
                <button type="button" onClick={() => go(i - 1)} className="h-12 rounded-full border border-brume px-6 text-[18px] text-blanc">
                  Précédent
                </button>
              )}
              {i < STEPS.length - 1 && (
                <button type="button" onClick={close} className="ml-auto h-12 px-2 text-[18px] text-brume">
                  Passer
                </button>
              )}
            </div>
          </div>
        </>
      )}
      {!open && (mock || live.mode === "fixtures") && (
        <button
          type="button"
          onClick={() => {
            setI(0);
            setOpen(true);
          }}
          className="pointer-events-auto absolute left-[960px] top-[28px] h-12 -translate-x-1/2 rounded-full border border-fumee bg-suie px-6 text-[18px] font-semibold text-blanc"
        >
          Visite guidée
        </button>
      )}
    </div>
  );
}
