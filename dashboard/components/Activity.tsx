"use client";
import type { Live } from "@/lib/live";
import type { IncidentState, TimelineEntry } from "@/lib/types";

// Top right of the main view, for the jury: what Seraph's parts are doing now (pulsing), then what they just did
// (Seraph's timeline, newest first). Radio lines are left out: the captions above Halo already show them.
const MODULE = {
  seraph: ["Seraph", "var(--seraph)"],
  gabriel: ["Gabriel", "var(--gabriel)"],
  rosetta: ["Rosetta", "var(--rosetta)"],
  silex: ["Silex", "var(--silex)"],
  cos: ["COS", "var(--ink)"],
  alert: ["Alerte", "var(--alerte)"],
} as const;
type Mod = keyof typeof MODULE;

const KIND: Record<Exclude<TimelineEntry["kind"], "radio">, Mod> = {
  seraph: "seraph",
  call: "gabriel",
  rosetta: "rosetta",
  silex: "silex",
  gate: "cos",
  alert: "alert",
};

// what a Rosetta agent is doing on its screen, said for the jury
const DOING: Record<string, string> = {
  "dispatch.read": "Lit l'alerte dans le logiciel du CODIS",
  "maps.building": "Regarde le bâtiment sur Google Maps",
  "georisques.risks": "Cherche les risques sur Géorisques",
  "plan.read": "Lit le plan affiché à l'entrée",
  "occupants.list": "Lit la liste des occupants chez le gestionnaire",
  "dispatch.write_112": "Écrit l'appel 112 dans la main courante",
  "report.fill": "Remplit le compte rendu",
  "weather.wind": "Lit le vent sur Météo-France",
};

type Row = { key: string; mod: Mod; text: string; now: boolean };

function running(s: IncidentState): Row[] {
  const rows: Row[] = [];
  for (const e of s.rosetta.endpoints)
    if (e.status === "running") rows.push({ key: `r-${e.name}`, mod: "rosetta", text: `${DOING[e.name] ?? `Lance ${e.name}`}…`, now: true });

  // Gabriel calls everyone listed at once: one line for all the calls, not one per call
  const who = (c: IncidentState["calls"][number]) => (c.direction === "in" ? "l'appel 112" : (s.occupants.find((o) => o.id === c.occupant_id)?.name ?? "un occupant"));
  const active = s.calls.filter((c) => c.status === "active");
  const ringing = s.calls.filter((c) => c.status === "ringing" && c.direction === "out");
  const calls = [
    s.calls.some((c) => c.status === "ringing" && c.direction === "in") && "décroche un appel 112",
    active.length && `en ligne avec ${active.length === 1 ? who(active[0]) : `${active.length} personnes`}`,
    ringing.length && `appelle ${ringing.length === 1 ? who(ringing[0]) : `${ringing.length} personnes`}`,
  ].filter(Boolean).join(", ");
  if (calls) rows.push({ key: "g", mod: "gabriel", now: true, text: `${calls[0].toUpperCase()}${calls.slice(1)}…` });

  for (const r of s.halo.requests)
    if (r.status === "requested" || r.status === "building")
      rows.push({ key: `s-${r.request_id}`, mod: "silex", now: true, text: `Devin construit la vue Halo : ${r.purpose_fr}…` });
  return rows;
}

function done(s: IncidentState): Row[] {
  return s.timeline
    .filter((e): e is TimelineEntry & { kind: keyof typeof KIND } => e.kind !== "radio")
    .slice(-8)
    .reverse()
    .map((e) => ({ key: `t-${e.t}-${e.text_fr.slice(0, 24)}`, mod: KIND[e.kind], text: e.text_fr, now: false }));
}

export function Activity({ live }: { live: Live }) {
  const s = live.state;
  if (!s) return null;
  const rows = [...running(s), ...done(s)].slice(0, 6);
  if (!rows.length) return null;
  const latest = rows.findIndex((r) => !r.now);
  return (
    <aside data-tour="activite" className="panel right-6 top-[112px] flex max-h-[460px] w-[304px] flex-col gap-5 overflow-hidden px-5 pb-5 pt-4">
      <span className="label">Ce que fait Seraph</span>
      {rows.map((r, i) => {
        const [label, color] = MODULE[r.mod];
        return (
          <div key={r.key} className="flex flex-col gap-1.5" style={{ opacity: r.now || i === latest ? 1 : 0.55 }}>
            <span className="mono flex items-center gap-2 text-[14px] font-medium" style={{ color }}>
              <i className={`sq ${r.now ? "pulse" : ""}`} style={{ background: color }} />
              {label}
            </span>
            <p className="line-clamp-3 text-[18px] leading-[1.3] text-ink">{r.text}</p>
          </div>
        );
      })}
    </aside>
  );
}
