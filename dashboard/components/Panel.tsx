"use client";
import type { ReactNode } from "react";
import type { Live } from "@/lib/live";
import type { Gate, IncidentState } from "@/lib/types";
import { dur, hm, hms, levelLabel } from "@/lib/fr";
import { Sq } from "./ui";

/** The one paper panel of the reference: the incident as a title, the COS decision when there is one, then three
 *  cards. The controls live behind the screen button, top right. */
export function Panel({ live, now }: { live: Live; now: number }) {
  const s = live.state;
  const gate = s?.gates.filter((g) => g.status === "pending").sort((a, b) => b.created_at.localeCompare(a.created_at))[0];

  return (
    <aside className="panel left-6 top-6 flex h-[1032px] w-[520px] flex-col px-7 pb-7 pt-9">
      {s ? (
        <>
          <Title s={s} live={live} now={now} />
          {gate && <Decision gate={gate} live={live} now={now} />}
          <div className="mt-auto flex flex-col gap-4">
            <div className="grid grid-cols-2 gap-4">
              <Team s={s} now={now} />
              <Alerts s={s} />
            </div>
            <Inside s={s} />
            <HaloBuild s={s} now={now} />
          </div>
        </>
      ) : (
        <p className="label mt-auto text-ink-3">Connexion à Seraph…</p>
      )}
    </aside>
  );
}

function Title({ s, live, now }: { s: IncidentState; live: Live; now: number }) {
  const [head] = (s.incident.nature || "En attente d'incident").split(",");
  const o = s.incident.origin;
  return (
    <div className="flex flex-col gap-5">
      <h1 className="t-display text-[78px] text-ink [text-wrap:balance]">{head}</h1>
      <div className="flex flex-col items-start gap-1.5">
        <div className="flex gap-1.5">
          <span className="chip danger">Exercice</span>
          {o && <span className="chip">{`${levelLabel(s, o.floor)}${o.room ? ` · ${o.room}` : ""}`}</span>}
          {live.mode !== "live" && <span className="chip solid">{live.mode === "mock" ? "Mock" : live.mode === "fixtures" ? "Seraph hors ligne" : "…"}</span>}
        </div>
        <span className="chip">
          {s.incident.declared_at ? `T+${dur(now - Date.parse(s.incident.declared_at))}` : "—"} · {hms(now)}
        </span>
      </div>
    </div>
  );
}

function Card({ title, right, children, className = "" }: { title: string; right?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`card flex flex-col gap-3 p-4 ${className}`}>
      <header className="flex h-6 items-center justify-between gap-2">
        <span className="label">{title}</span>
        {right}
      </header>
      {children}
    </section>
  );
}

export function Decision({ gate, live, now, className = "mt-8" }: { gate: Gate; live: Live; now: number; className?: string }) {
  return (
    <Card
      className={className}
      title="Décision COS"
      right={
        <span className="chip h-6 text-[12px]">
          <Sq tone="propose" pulse /> {dur(now - Date.parse(gate.created_at))}
        </span>
      }
    >
      <p className="text-[21px] leading-[1.35] text-ink">{gate.summary_fr}</p>
      <div className="grid grid-cols-[1fr_auto] gap-2">
        <button
          type="button"
          onClick={() => live.confirmGate(gate.gate_id)}
          className="label flex h-12 items-center justify-between rounded-full bg-propose px-5 text-[15px] text-suie transition-colors hover:bg-blanc"
        >
          Confirmer <span className="text-[11px] opacity-60">espace</span>
        </button>
        <button
          type="button"
          onClick={() => live.cancelGate(gate.gate_id)}
          className="label flex h-12 items-center border border-rule px-5 text-[15px] text-ink-2 transition-colors hover:border-ink"
        >
          Annuler
        </button>
      </div>
    </Card>
  );
}

function Team({ s, now }: { s: IncidentState; now: number }) {
  const t = s.crew.teams.find((x) => x.status === "engaged" || x.status === "exiting");
  const left = t?.exit_by ? Date.parse(t.exit_by) - now : null;
  return (
    <Card
      title="Binôme"
      right={left != null && <span className={`chip h-6 text-[12px] ${left <= 0 ? "danger" : ""}`}>{hm(t!.exit_by)}</span>}
    >
      <div className="flex items-baseline gap-2">
        <span className="t-num text-[44px] text-ink">{t?.id ?? "—"}</span>
        {t?.location?.level != null && <span className="label text-ink-3">{levelLabel(s, t.location.level)}</span>}
      </div>
      <span className="label text-[12px]">
        {left != null ? `Sortie dans ${dur(Math.max(0, left))}` : "Aucun engagé"}
      </span>
    </Card>
  );
}

function Alerts({ s }: { s: IncidentState }) {
  const all = [...s.alerts].sort((a, b) => b.created_at.localeCompare(a.created_at));
  const top = all[0];
  return (
    <Card title="Alertes" right={<span className="chip h-6 text-[12px]">{all.length}</span>}>
      {top ? (
        <p className="flex gap-2 text-[16px] leading-[1.3] text-ink">
          <span className="mt-[5px]">
            <Sq tone={top.level === "danger" ? "danger" : top.level === "warning" ? "alerte" : "blanc"} />
          </span>
          <span className="line-clamp-3">{top.text_fr}</span>
        </p>
      ) : (
        <p className="label text-ink-3">Aucune</p>
      )}
    </Card>
  );
}

function Inside({ s }: { s: IncidentState }) {
  const inside = s.occupants.filter((o) => o.status !== "safe_outside");
  const people = inside.reduce((n, o) => n + (o.people_count ?? 1), 0);
  const help = inside.filter((o) => o.status === "needs_help" || o.status === "trapped").length;
  const noNews = inside.filter((o) => o.status === "no_answer" || o.status === "unknown").length;
  const stat = (label: string, value: number) => (
    <div className="flex flex-col gap-2">
      <span className="label text-[12px]">{label}</span>
      <span className="t-num text-[44px] text-ink">{value}</span>
    </div>
  );
  return (
    <Card title="À l'intérieur">
      <div className="grid grid-cols-3 gap-4">
        {stat("Personnes", people)}
        {stat("Aide", help)}
        {stat("Sans nouvelles", noNews)}
      </div>
    </Card>
  );
}

/** The reference's little node diagram: Seraph asks → Devin builds → on Halo. */
function HaloBuild({ s, now }: { s: IncidentState; now: number }) {
  const reqs = [...s.halo.requests].sort((a, b) => b.requested_at.localeCompare(a.requested_at)).slice(0, 2);
  return (
    <Card title="Vues Halo">
      {reqs.length === 0 && <p className="label text-ink-3">Aucune demande</p>}
      {reqs.map((r) => {
        const done = r.status === "ready";
        const failed = r.status === "failed" || r.status === "timed_out";
        return (
          <div key={r.request_id} className="grid grid-cols-[1fr_auto] items-center gap-3">
            <div className="flex min-w-0 items-center">
              <Node on />
              <Link on />
              <Node on={done} label="Devin" />
              <Link on={done} building={!done && !failed} />
              <Node on={done} danger={failed} />
              <span className="ml-3 truncate text-[17px] text-ink">{r.purpose_fr}</span>
            </div>
            <span className="label text-[12px]">{done ? hm(r.ready_at) : failed ? "échec" : dur(now - Date.parse(r.requested_at))}</span>
          </div>
        );
      })}
    </Card>
  );
}

function Node({ on, label, danger }: { on: boolean; label?: string; danger?: boolean }) {
  return (
    <span
      title={label}
      className={`block h-3.5 w-3.5 flex-none border-2 ${danger ? "border-danger bg-danger" : on ? "border-ink bg-ink" : "border-ink bg-paper"}`}
    />
  );
}

function Link({ on, building }: { on: boolean; building?: boolean }) {
  return <span className={`block h-0 w-7 flex-none border-t-2 ${on ? "border-ink" : building ? "border-dashed border-propose" : "border-dashed border-ink-3"}`} />;
}
