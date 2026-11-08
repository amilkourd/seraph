"use client";
import { Fragment, useEffect, useRef, useState } from "react";
import { useLive, type Live } from "@/lib/live";
import type { IncidentState } from "@/lib/types";
import { MOMENTS, dur, hm, hms, levelLabel, type Tone } from "@/lib/fr";
import { Building3D } from "./Building3D";
import { Decision, Panel } from "./Panel";
import { RosettaGrid } from "./RosettaGrid";
import { Sq } from "./ui";

// Stage layout (1920×1080). Main view: panel | the building, full height | radio over Halo.
// Split view (screen button): the building framed on the level that matters, above the six Rosetta screens.
const SCHEME = { x: 560, y: 0, w: 800, h: 1080 };
const TOP = { x: 0, y: 0, w: 1920, h: 548 };
const PHONE = { w: 874, h: 402, scale: 0.6 }; // iPhone 17 Pro in landscape, as Halo runs on the forearm
const KIT_VIEWS = ["approach", "inside_route", "occupants"]; // halo/kit/examples

/** The projector screen: a fixed 1920×1080 stage, scaled to whatever display it lands on. */
export function Dashboard() {
  const live = useLive();
  const [scale, setScale] = useState(1);
  const [now, setNow] = useState(0); // set on mount: the clock must not be read during prerender
  const [view, setView] = useState<"main" | "split">("main");
  const [booth, setBooth] = useState(false); // « Essayez »: the judges' booth in the left panel (key E)

  useEffect(() => {
    const fit = () => setScale(Math.min(window.innerWidth / 1920, window.innerHeight / 1080));
    fit();
    setNow(Date.now());
    if (window.location.hash === "#rosetta") setView("split"); // open straight on the split view
    window.addEventListener("resize", fit);
    const tick = setInterval(() => setNow(Date.now()), 1000);
    return () => {
      window.removeEventListener("resize", fit);
      clearInterval(tick);
    };
  }, []);

  // Keys from docs/03-demo-script.md: Space confirm / Esc cancel the latest gate, 1–4 force a Halo moment,
  // R replay the next radio line (R00…R15, for a line missed live). Controls: D start the incident, A call everyone
  // now, Shift+R replay the whole incident, X twice reset, E the judges' booth.
  const liveRef = useRef(live);
  useEffect(() => {
    liveRef.current = live;
  });
  useEffect(() => {
    let armed = 0;
    let line = 0;
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const l = liveRef.current;
      const gate = l.state?.gates.filter((g) => g.status === "pending").sort((a, b) => b.created_at.localeCompare(a.created_at))[0];
      if (e.code === "Space") {
        e.preventDefault();
        if (gate) l.confirmGate(gate.gate_id);
      } else if (e.key === "Escape") {
        if (gate) l.cancelGate(gate.gate_id);
      } else if (/^[1-4]$/.test(e.key)) {
        const moment = MOMENTS[Number(e.key) - 1];
        l.act(`Moment Halo ${moment}`, "seraph", "admin/moment", { moment });
      } else if (e.key === "R") {
        l.act("Rejouer les fixtures", "seraph", "admin/replay", { fixture: "all", speed: 4 });
      } else if (e.key === "r") {
        const id = `R${String(line % 16).padStart(2, "0")}`;
        line++;
        l.act(`Ligne ${id}`, "seraph", "admin/replay_line", { id });
      } else if (e.key.toLowerCase() === "a") {
        l.act("Appeler maintenant", "seraph", "admin/call_now", {});
      } else if (e.key.toLowerCase() === "d") {
        l.act("Lancer l'incident", "seraph", "incident/start", {});
      } else if (e.key.toLowerCase() === "e") {
        setBooth((b) => !b);
      } else if (e.key.toLowerCase() === "x") {
        if (Date.now() - armed < 3000) {
          armed = 0;
          l.act("Réinitialiser", "seraph", "admin/reset", {});
        } else {
          armed = Date.now();
        }
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const s = live.state;
  return (
    <div className="viewport">
      <div className="stage" style={{ transform: `translate(-50%, -50%) scale(${scale})` }}>
        {view === "main" ? (
          <>
            <Building3D key="main" state={s} box={SCHEME} scale={scale} />
            <Panel live={live} now={now} booth={booth} />
            <Radio live={live} />
            <HaloPhone live={live} />
          </>
        ) : (
          <>
            <Building3D key="split" state={s} box={TOP} scale={scale} zoom="focus" />
            <SplitHeader live={live} now={now} />
            <RosettaGrid live={live} now={now} />
          </>
        )}
        <SourceBadge live={live} />
        <ScreenButton live={live} active={view === "split"} onClick={() => setView((v) => (v === "main" ? "split" : "main"))} />
        {live.toast && (
          <div
            className={`mono absolute left-[1246px] top-[40px] -translate-x-1/2 px-4 py-2.5 text-[15px] ${
              live.toast.tone === "err" ? "bg-danger text-suie" : "border border-[rgba(220,218,214,0.14)] bg-suie text-brume"
            }`}
          >
            {live.toast.text}
          </div>
        )}
      </div>
    </div>
  );
}

/** An iframe fed like a Halo view: `seraph:state` on load and on every state change. */
function StateFrame({ src, state, title, className, style }: { src: string; state: IncidentState | null; title: string; className?: string; style?: React.CSSProperties }) {
  const ref = useRef<HTMLIFrameElement>(null);
  const post = () => {
    if (state) ref.current?.contentWindow?.postMessage({ type: "seraph:state", state }, "*");
  };
  // only when the state changes: the clock re-renders every second, and each post makes the view redraw
  useEffect(post, [state]); // eslint-disable-line react-hooks/exhaustive-deps
  return <iframe ref={ref} src={src} title={title} onLoad={post} className={`border-0 ${className ?? ""}`} style={style} />;
}

/** Always on screen, left of the screen button: live, a fixture replay, or the mock. A replay never looks live:
 *  Seraph's /health says `replay` is anything but "idle" from the moment it starts until the next reset. */
function SourceBadge({ live }: { live: Live }) {
  const replay = live.health.seraph?.replay;
  const replaying = live.mode === "live" && replay != null && replay !== "idle";
  const [text, tone]: [string, Tone] =
    live.mode === "mock" ? ["Mock", "gris"]
    : live.mode === "connecting" ? ["Connexion", "gris"]
    : live.mode === "fixtures" ? ["Hors ligne", "danger"]
    : replaying ? ["Rejeu", "alerte"]
    : ["Live", "sur"];
  return (
    <div
      className={`dark label absolute right-[104px] top-6 flex h-16 items-center gap-3 rounded-full border bg-paper px-6 text-[20px] ${
        replaying ? "border-alerte text-alerte" : "border-rule text-ink"
      }`}
    >
      <Sq tone={tone} pulse={text === "Live"} />
      {text}
    </div>
  );
}

/** Top right: one screen button. It switches to the split view (building above, Rosetta's screens below) and back.
 *  Its square says how Seraph is reached. */
function ScreenButton({ live, active, onClick }: { live: Live; active: boolean; onClick: () => void }) {
  const core = ["seraph", "halo", "silex", "talkie"];
  const down = core.filter((k) => live.health[k] && !live.health[k].ok);
  const link = live.mode === "live" ? (live.streamOk ? "en direct" : "flux coupé") : live.mode === "mock" ? "mock" : "Seraph hors ligne";
  // grey in mock (services are expected down), red if a service is down, amber if the stream dropped, green otherwise
  const tone = live.mode === "mock" ? "gris" : down.length || live.mode === "fixtures" ? "danger" : live.streamOk ? "sur" : "alerte";
  return (
    <button
      type="button"
      onClick={onClick}
      title={`${active ? "Revenir à la vue principale" : "Écrans Rosetta"} · Seraph ${link}${down.length ? ` · hors ligne : ${down.join(", ")}` : ""}`}
      className={`dark absolute right-6 top-6 grid h-16 w-16 place-items-center rounded-full border border-rule transition-colors ${active ? "bg-ink text-paper" : "bg-paper text-ink"}`}
    >
      <svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden>
        <rect x="3" y="4" width="18" height="12" />
        <path d="M9 20h6M12 16v4" />
      </svg>
      <i className={`sq ${tone} absolute right-3 top-3 h-2 w-2 rounded-full`} />
    </button>
  );
}

/** Split view, over the building: the incident in a line, and the COS decision when there is one. */
function SplitHeader({ live, now }: { live: Live; now: number }) {
  const s = live.state;
  if (!s) return null;
  const [head] = (s.incident.nature || "En attente d'incident").split(",");
  const o = s.incident.origin;
  const gate = s.gates.filter((g) => g.status === "pending").sort((a, b) => b.created_at.localeCompare(a.created_at))[0];
  return (
    <div className="dark absolute left-10 top-9 flex w-[460px] flex-col gap-4">
      <h1 className="t-display text-[52px] text-blanc">{head}</h1>
      <div className="flex flex-wrap gap-1.5">
        <span className="chip danger">Exercice</span>
        {o && <span className="chip">{`${levelLabel(s, o.floor)}${o.room ? ` · ${o.room}` : ""}`}</span>}
        <span className="chip">{s.incident.declared_at ? `T+${dur(now - Date.parse(s.incident.declared_at))}` : "—"} · {hms(now)}</span>
      </div>
      {gate && <Decision gate={gate} live={live} now={now} className="mt-2" />}
    </div>
  );
}

const SOURCE_PHRASE = /(selon (?:l'appel|le plan|la maquette|Géorisques|Maps|Earth|le dispatch)|calcul simplifié)/gi;

/** The radio as captions on the map: the last exchange only, in the kit's black tags. */
function Radio({ live }: { live: Live }) {
  const lines = live.radio.slice(-2);
  return (
    <div className="absolute bottom-[330px] left-[1376px] flex w-[520px] flex-col items-start gap-2">
      {lines.map((l, i) => (
        <div key={l.id} className="flex max-w-full items-baseline gap-3 bg-[rgba(11,11,11,0.94)] px-3 py-2" style={{ opacity: i === lines.length - 1 ? 1 : 0.55 }}>
          <span className={`mono flex-none text-[13px] font-medium ${l.seraph ? "text-gabriel" : "text-gris"}`}>
            {hm(l.t)} {l.speaker}
          </span>
          <span className="line-clamp-2 text-[22px] leading-[1.25] text-blanc">
            {l.text.split(SOURCE_PHRASE).map((p, k) => (k % 2 ? <mark className="src" key={k}>{p}</mark> : <Fragment key={k}>{p}</Fragment>))}
          </span>
        </div>
      ))}
    </div>
  );
}

/** Halo on the forearm: a landscape phone showing exactly what phone A shows (halo/ protocol): the current view's
 *  URL in a frame, fed `seraph:state` on every change; « fallback://<moment> » is Halo's stand-in at
 *  HALO_URL/views/<moment>/. Before any view, the kit's live preview. Mock → the kit's example, fixture state. */
function HaloPhone({ live }: { live: Live }) {
  const view = live.state?.halo.current_view;
  const isLive = live.mode === "live";
  const stand = view?.url.startsWith("fallback://");
  // the view phone A shows: Devin's (Silex URL) or Halo's stand-in for a fallback moment
  const current = isLive && view ? (stand ? (KIT_VIEWS.includes(view.moment) && live.config?.halo ? `${live.config.halo}/views/${view.moment}/` : null) : view.url) : null;
  const preview = isLive && !view && live.config?.seraph ? `/api/kit/examples/index.html?v=approach&live=${encodeURIComponent(live.config.seraph)}` : null;
  const example = live.mode === "mock" && view ? `/api/kit/examples/${view.moment}.html` : null;
  const src = current ?? preview ?? example;
  const sw = PHONE.w * PHONE.scale;
  const sh = PHONE.h * PHONE.scale;

  return (
    <div className="absolute bottom-7 right-6 flex flex-col items-end gap-2.5">
      <span className="mono text-[13px] text-gris">Halo</span>
      <div className="rounded-[34px] border-2 border-brume bg-black p-[10px]" style={{ width: sw + 24, height: sh + 24 }}>
        <div className="relative h-full w-full overflow-hidden rounded-[24px] bg-black">
          {src ? (
            <StateFrame
              key={src}
              src={src}
              state={preview ? null : live.state}
              title="Halo"
              className="absolute left-0 top-0 origin-top-left"
              style={{ width: PHONE.w, height: PHONE.h, transform: `scale(${PHONE.scale})` }}
            />
          ) : (
            <div className="mono flex h-full items-center justify-center text-[13px] text-gris">
              {view ? `Vue de secours · ${view.moment}` : "Halo hors ligne"}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
