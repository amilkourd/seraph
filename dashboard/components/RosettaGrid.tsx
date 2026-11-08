"use client";
// The six Rosetta screens: one card per computer-use agent, with what it sees (agent cam frame, else the last
// screenshot), what it is doing, and whether the result is live or from the cache. Never simulated: in mock, the
// cards show the fixture results, labelled CACHE or LIVE as the fixture says.
import { useState } from "react";
import type { Live } from "@/lib/live";
import { ENDPOINT_KIND, ENDPOINT_SITE, dur, hm, secs } from "@/lib/fr";
import { Sq } from "./ui";

type Tile = {
  name: string;
  kind?: "real" | "replica" | "learned";
  status: "idle" | "running" | "ok" | "failed";
  live: boolean | null;
  shot?: string;
  caption?: string;
  step?: number;
  action?: string;
  thought?: string;
  ms?: number;
  at?: string;
};

export function RosettaGrid({ live, now }: { live: Live; now: number }) {
  const endpoints = live.state?.rosetta.endpoints ?? [];
  const tiles: Tile[] = endpoints
    .map((e) => {
      const frame = Object.values(live.cams)
        .filter((f) => f.endpoint === e.name)
        .sort((a, b) => b.at.localeCompare(a.at))[0];
      const running = e.status === "running" || (frame && now - Date.parse(frame.at) < 30_000);
      const result = live.results[e.name];
      return {
        name: e.name,
        kind: e.kind,
        status: running ? "running" : e.status,
        live: running ? true : (e.last_live ?? result?.live ?? null), // Seraph's state first: it is the truth
        shot: frame?.shot_url ?? result?.screenshots[0]?.url,
        caption: result?.screenshots[0]?.caption,
        step: frame?.step,
        action: frame?.action,
        thought: frame?.thought,
        ms: running && frame ? now - Date.parse(frame.first_at) : (e.last_duration_ms ?? result?.duration_ms),
        at: e.last_run_at ?? result?.ended_at,
      } satisfies Tile;
    })
    .sort((a, b) => Number(b.status === "running") - Number(a.status === "running"))
    .slice(0, 6);

  return (
    <div className="dark absolute bottom-6 left-6 right-6 top-[564px] grid grid-cols-3 grid-rows-2 gap-4">
      {tiles.map((t) => (
        <Card key={t.name} t={t} />
      ))}
      {Array.from({ length: Math.max(0, 6 - tiles.length) }, (_, i) => (
        <div key={i} className="card flex items-center justify-center p-4">
          <span className="label text-ink-3">En attente d&apos;un agent Rosetta</span>
        </div>
      ))}
    </div>
  );
}

// Rosetta's own colour (brand: ironbow magenta) marks an agent at work
const STATUS: Record<Tile["status"], [string, "rosetta" | "sur" | "gris" | "alerte"]> = {
  running: ["En cours", "rosetta"],
  ok: ["Terminé", "sur"],
  idle: ["En attente", "gris"],
  failed: ["Échec", "alerte"],
};

function Card({ t }: { t: Tile }) {
  const [broken, setBroken] = useState<string | null>(null);
  const running = t.status === "running";
  const point = t.action?.match(/\((\d{1,4})\s*,\s*(\d{1,4})\)/);
  const [label, tone] = STATUS[t.status];

  return (
    <section className="card flex min-h-0 flex-col gap-3 p-4">
      <header className="flex h-6 flex-none items-center justify-between gap-3">
        <span className="label flex min-w-0 items-center gap-2">
          <Sq tone="rosetta" />
          <span className="truncate">{ENDPOINT_SITE[t.name] ?? t.name}</span>
        </span>
        <span className="chip h-6 flex-none">
          <Sq tone={tone} pulse={running} /> {running ? `Live · étape ${t.step ?? "…"}` : t.live === false ? "Cache" : label}
        </span>
      </header>
      <div className="grid min-h-0 flex-1 grid-cols-[288px_1fr] gap-4">
        <div className="relative overflow-hidden bg-suie">
          {t.shot && broken !== t.shot ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={t.shot} alt={t.caption ?? t.name} className="h-full w-full object-cover object-top" onError={() => setBroken(t.shot!)} />
          ) : (
            <div className="flex h-full items-center justify-center p-4 text-center">
              <span className="label text-[12px] text-gris">{t.caption ?? "Pas d'image"}</span>
            </div>
          )}
          {point && Number(point[1]) <= 1000 && Number(point[2]) <= 1000 && (
            <div className="pointer-events-none absolute" style={{ left: `${Number(point[1]) / 10}%`, top: `${Number(point[2]) / 10}%` }}>
              <div className="absolute -left-4 top-0 h-px w-8 bg-rosetta" />
              <div className="absolute -top-4 left-0 h-8 w-px bg-rosetta" />
              <div className="absolute -left-2 -top-2 h-4 w-4 rounded-full border-2 border-rosetta" />
            </div>
          )}
        </div>
        <div className="flex min-w-0 flex-col gap-2">
          <span className="label text-[12px]">{running ? "Depuis" : "Durée"}</span>
          <span className="t-num text-[40px] text-ink">{running ? dur(t.ms ?? 0) : secs(t.ms)}</span>
          <p className="line-clamp-3 text-[15px] leading-[1.35] text-ink-2">
            {running ? (t.thought ?? t.action ?? "…") : t.at ? `Lu à ${hm(t.at)}` : "Pas encore lancé"}
          </p>
          <span className="label mt-auto truncate text-[11px] text-ink-3">
            {t.name} · {t.kind ? ENDPOINT_KIND[t.kind] : ""}
          </span>
        </div>
      </div>
    </section>
  );
}
