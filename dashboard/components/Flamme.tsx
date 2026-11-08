"use client";
import { useEffect, useId, useRef, useState } from "react";
import { NOTIF_BLUE } from "@/lib/bloub/decor";
import { BotEngine, type BotFrame } from "@/lib/bloub/engine";
import { EXPRESSION_BY_ID, type BotExpression } from "@/lib/bloub/expressions";
import { FLAME_RADII } from "@/lib/bloub/flamme";
import { clamp } from "@/lib/bloub/math";
import { DEMI_VIEWBOX as VB, RAYON as R } from "@/lib/bloub/repere";
import { mixHex } from "@/lib/bloub/skins";
import { STATE_BY_ID, type EyeCfg, type StateId } from "@/lib/bloub/states";

// How far the eyes turn when the cursor reaches the edge of the window, in degrees (Bloub's 16 and 13, a little more
// so it reads on a projector). Bloub also turns the head toward its own side panel: not here, the flame looks ahead.
const YAW_MAX = 22;
const PITCH_MAX = 17;

/** The flame's eyes are always wide open (Amil): a face keeps its gaze, its eye spacing and half its tilt, never a
 *  squint. The engine's blinks are off too. */
function wideOpen(id: string): BotExpression | null {
  const e = EXPRESSION_BY_ID.get(id);
  if (!e) return null;
  const big = (c: EyeCfg): EyeCfg => ({ ...c, w: Math.max(c.w, 0.34), h: Math.max(c.h, 0.62), tilt: (c.tilt ?? 0) / 2, open: 1 });
  return { ...e, eyes: [big(e.eyes[0]), big(e.eyes[1])] };
}

/** Seraph's flame: Bloub's engine sampled every frame, drawn like BloubBot.vue (eyes are holes in the body). Its eyes
 *  follow the cursor on the resting face; a gesture (wink, swirl…) takes the gaze back while it plays. */
export function Flamme({ state, expression, color, paper, size }: { state: StateId; expression: string; color: string; paper: string; size: number }) {
  const [engine] = useState(() => {
    const e = new BotEngine(R, state, FLAME_RADII, wideOpen(expression));
    e.blinks = false;
    return e;
  });
  const [f, setFrame] = useState<BotFrame>(() => engine.sample(0));
  const clock = useRef(0);
  const playing = useRef<StateId>(state); // what the engine plays now: a gesture goes back to idle by itself
  const svg = useRef<SVGSVGElement>(null);
  const uid = useId().replace(/[^a-zA-Z0-9]/g, "");

  useEffect(() => {
    engine.setState(state, clock.current);
    playing.current = state;
    if (state === "idle") return;
    // a gesture (wink, wide, swirl, notify) holds its last pose: play it once, then back to rest
    const back = setTimeout(() => {
      engine.setState("idle", clock.current);
      playing.current = "idle";
    }, (STATE_BY_ID.get(state)?.duration ?? 1.6) * 1000);
    return () => clearTimeout(back);
  }, [engine, state]);
  useEffect(() => {
    engine.setExpression(wideOpen(expression), clock.current);
  }, [engine, expression]);

  useEffect(() => {
    let raf = 0;
    let last = 0;
    let pointer: { x: number; y: number } | null = null;
    let aiming = false;
    // a finger leaves no cursor behind: on touch the gaze keeps drifting on its own
    const onMove = (e: PointerEvent) => {
      if (e.pointerType !== "touch") pointer = { x: e.clientX, y: e.clientY };
    };
    const onLeave = () => {
      pointer = null;
    };
    const aim = () => {
      if (!STATE_BY_ID.get(playing.current)?.baseFace) {
        if (aiming) engine.setLook(null, clock.current, 1.1);
        aiming = false;
        return;
      }
      // read each frame: the bubble glides from step to step. A hidden pane measures 0 × 0, and a NaN look would stay.
      const box = svg.current?.getBoundingClientRect();
      if (!box || box.width === 0 || box.height === 0) return;
      const nx = pointer ? clamp((pointer.x - (box.left + box.width / 2)) / Math.max(1, window.innerWidth / 2), -1, 1) : 0;
      const ny = pointer ? clamp((pointer.y - (box.top + box.height / 2)) / Math.max(1, window.innerHeight / 2), -1, 1) : 0;
      engine.setLook({ yaw: nx * YAW_MAX, pitch: -ny * PITCH_MAX, mix: 1, spin: 0, wander: pointer ? 0 : 1 }, clock.current);
      aiming = true;
    };
    const tick = (ms: number) => {
      raf = requestAnimationFrame(tick);
      // bounded delta: a hidden tab resumes where it stopped instead of jumping ahead
      const dt = last ? Math.min((ms - last) / 1000, 0.064) : 0;
      last = ms;
      clock.current += dt;
      aim();
      setFrame(engine.sample(clock.current));
    };
    window.addEventListener("pointermove", onMove);
    document.addEventListener("pointerleave", onLeave);
    raf = requestAnimationFrame(tick);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("pointermove", onMove);
      document.removeEventListener("pointerleave", onLeave);
    };
  }, [engine]);

  const maskId = `flamme-${uid}`;
  const dot = (d: BotFrame["dots"][number], key: string) => {
    const fill = d.color ?? (d.depth === undefined ? color : mixHex(paper, color, d.depth));
    return d.d ? (
      <path key={key} d={d.d} fill={fill} opacity={d.opacity} transform={`translate(${d.x} ${d.y}) rotate(${d.rot ?? 0}) scale(${R})`} />
    ) : (
      <circle key={key} cx={d.x} cy={d.y} r={d.r} fill={fill} opacity={d.opacity} />
    );
  };

  return (
    <svg ref={svg} width={size} height={size} viewBox={`${-VB} ${-VB} ${VB * 2} ${VB * 2}`} aria-hidden="true" className="flex-none overflow-visible">
      <defs>
        <mask id={maskId} maskUnits="userSpaceOnUse" x={-VB} y={-VB} width={VB * 2} height={VB * 2}>
          <path d={f.bodyPath} fill="#fff" />
          {f.eyes.map((eye, i) => (
            <path key={i} d={eye.d} transform={eye.matrix} opacity={eye.alpha} fill="#000" />
          ))}
          {f.notch && <circle cx={f.notch.x} cy={f.notch.y} r={f.notch.r} fill="#000" />}
        </mask>
        {f.arcs.map((arc) => (
          <linearGradient key={arc.id} id={`${uid}-${arc.id}`} gradientUnits="userSpaceOnUse" x1={arc.grad.x1} y1={arc.grad.y1} x2={arc.grad.x2} y2={arc.grad.y2}>
            {arc.grad.stops.map((c, i) => (
              <stop key={i} offset={i / (arc.grad.stops.length - 1)} stopColor={c} />
            ))}
          </linearGradient>
        ))}
      </defs>
      {/* back half of the orbits, drawn before the body so it hides them */}
      <g fill="none" strokeLinecap="round">
        {f.arcs.map((arc) => (
          <path key={`b${arc.id}`} d={arc.back} stroke={`url(#${uid}-${arc.id})`} strokeWidth={arc.width} opacity={arc.opacity} />
        ))}
      </g>
      {f.dotsBehind && <g>{f.dots.map((d, i) => dot(d, `pb${i}`))}</g>}
      <g opacity={f.bodyAlpha}>
        <path d={f.bodyPath} fill={paper} />
        <g mask={`url(#${maskId})`}>
          <rect x={-VB} y={-VB} width={VB * 2} height={VB * 2} fill={color} style={{ transition: "fill 450ms ease" }} />
        </g>
      </g>
      {!f.dotsBehind && <g>{f.dots.map((d, i) => dot(d, `pf${i}`))}</g>}
      {f.notif && <circle cx={f.notif.x} cy={f.notif.y} r={f.notif.r} fill={NOTIF_BLUE} />}
      <g fill="none" strokeLinecap="round">
        {f.arcs.map((arc) => (
          <path key={`f${arc.id}`} d={arc.front} stroke={`url(#${uid}-${arc.id})`} strokeWidth={arc.width} opacity={arc.opacity} />
        ))}
      </g>
    </svg>
  );
}
