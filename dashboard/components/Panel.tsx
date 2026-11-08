"use client";
import { useEffect, useState, type ReactNode } from "react";
import QRCode from "qrcode";
import type { Live, Turn } from "@/lib/live";
import type { Gate, IncidentState } from "@/lib/types";
import { TEAM_STATUS, dur, hm, hms, levelLabel, secs } from "@/lib/fr";
import { Sq } from "./ui";

/** The one paper panel of the reference: the incident as a title, the COS decision when there is one, then three
 *  cards. The controls live behind the screen button, top right. */
export function Panel({ live, now, booth = false }: { live: Live; now: number; booth?: boolean }) {
  const s = live.state;
  const gate = s?.gates.filter((g) => g.status === "pending").sort((a, b) => b.created_at.localeCompare(a.created_at))[0];

  if (booth)
    return (
      <aside className="panel left-6 top-6 flex h-[1032px] w-[520px] flex-col px-7 pb-7 pt-9">
        <Booth live={live} />
        {gate && <Decision gate={gate} live={live} now={now} className="mt-6" />}
        <Turns turns={live.turns} />
      </aside>
    );

  return (
    <aside className="panel left-6 top-6 flex h-[1032px] w-[520px] flex-col px-7 pb-7 pt-9">
      {s ? (
        <>
          <Title s={s} now={now} />
          {gate && <Decision gate={gate} live={live} now={now} />}
          <div className="mt-auto flex flex-col gap-4">
            <div className="grid grid-cols-2 gap-4">
              <Team s={s} />
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

function Title({ s, now }: { s: IncidentState; now: number }) {
  const [head] = (s.incident.nature || "En attente d'incident").split(",");
  const o = s.incident.origin;
  return (
    <div className="flex flex-col gap-5">
      <h1 className="t-display text-[78px] text-ink [text-wrap:balance]">{head}</h1>
      <div className="flex flex-col items-start gap-1.5">
        <div className="flex gap-1.5">
          <span className="chip danger">Exercice</span>
          {o && <span className="chip">{`${levelLabel(s, o.floor)}${o.room ? ` · ${o.room}` : ""}`}</span>}
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

// the team as a position only: no air tracking in the demo (Amil)
function Team({ s }: { s: IncidentState }) {
  const t = s.crew.teams.find((x) => x.status === "engaged" || x.status === "exiting");
  const at = t?.location;
  const where = !t ? "Aucun engagé" : at?.stair ? `Esc. ${at.stair}` : at?.room === "corridor" ? "Circulation" : (at?.room ?? TEAM_STATUS[t.status]);
  return (
    <Card title="Binôme">
      <div className="flex items-baseline gap-2">
        <span className="t-num text-[44px] text-ink">{t?.id ?? "—"}</span>
        {at?.level != null && <span className="label text-ink-3">{levelLabel(s, at.level)}</span>}
      </div>
      <span className="label text-[12px]">{where}</span>
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
  // « à joindre »: listed, no call yet; « sans nouvelles »: a call rang with no answer — only that one is an alert
  const toReach = inside.filter((o) => o.status === "unknown").length;
  const noNews = inside.filter((o) => o.status === "no_answer").length;
  const stat = (label: string, value: number, alert = false) => (
    <div className="flex min-w-0 flex-col gap-2">
      <span className="label text-[12px] whitespace-nowrap">{label}</span>
      <span className={`t-num text-[44px] ${alert && value > 0 ? "text-alerte" : "text-ink"}`}>{value}</span>
    </div>
  );
  return (
    <Card title="À l'intérieur">
      <div className="grid grid-cols-4 gap-3">
        {stat("Personnes", people)}
        {stat("Aide", help)}
        {stat("À joindre", toReach)}
        {stat("Sans nouvelles", noNews, true)}
      </div>
    </Card>
  );
}

/** The reference's little node diagram: Seraph asks → Devin builds → on Halo. */
function HaloBuild({ s, now }: { s: IncidentState; now: number }) {
  // no « Mon air » view: air tracking is out of the demo
  const reqs = s.halo.requests.filter((r) => r.moment !== "team_engaged").sort((a, b) => b.requested_at.localeCompare(a.requested_at)).slice(0, 2);
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

// ───────── booth (key E): judges drive Seraph themselves, every answer shows where it comes from ─────────

const PHRASES = [
  "Seraph, quelle entrée ?",
  "Seraph, il me faut sur Halo le plan du R+3 avec les personnes et la fumée",
  "Seraph de Tête, porte E1 bloquée",
  "Seraph, point de situation",
  "Seraph, levée de doute au 1er",
];

function Booth({ live }: { live: Live }) {
  const url = live.config?.inscription;
  const [qr, setQr] = useState<string | null>(null);
  useEffect(() => {
    if (!url) return;
    QRCode.toString(url, { type: "svg", margin: 1, errorCorrectionLevel: "M", color: { dark: "#000000", light: "#ffffff" } })
      .then(setQr)
      .catch(() => setQr(null));
  }, [url]);
  return (
    <div className="flex flex-col gap-5">
      <div className="grid grid-cols-[1fr_auto] items-start gap-5">
        <div className="flex flex-col gap-3">
          <h1 className="t-display text-[78px] text-ink">Essayez</h1>
          <p className="text-[19px] leading-[1.3] text-ink-2">Appuyez sur le talkie, parlez à Seraph.</p>
        </div>
        <div className="flex flex-col items-center gap-2">
          {url && qr ? (
            <div className="h-[132px] w-[132px] bg-white [&>svg]:h-full [&>svg]:w-full" dangerouslySetInnerHTML={{ __html: qr }} />
          ) : (
            // never a fake QR: OCCUPANTS_PUBLIC_URL is not set in the root .env
            <div className="label grid h-[132px] w-[132px] place-items-center border border-rule p-3 text-center text-[13px] text-ink-3">Lien absent</div>
          )}
          <span className="label text-[12px]">Inscription</span>
        </div>
      </div>
      <ol className="flex flex-col gap-2">
        {PHRASES.map((p) => (
          <li key={p} className="card px-4 py-3 text-[19px] leading-[1.3] text-ink">« {p} »</li>
        ))}
      </ol>
    </div>
  );
}

const PATH: Record<string, string> = { rules: "Règles", llm: "LLM", none: "Non reconnu" };

/** Each speaker's last line: what was heard, what it became (rules or LLM), how long Seraph took, its answer. */
function Turns({ turns }: { turns: Turn[] }) {
  const last = [...turns].reverse().filter((t, i, a) => a.findIndex((x) => x.speaker === t.speaker) === i).slice(0, 3);
  return (
    <div className="mt-auto flex flex-col gap-3">
      {last.map((t) => (
        <section key={t.id} className="card flex flex-col gap-2 p-4">
          <header className="flex h-6 items-center justify-between gap-2">
            <span className="label">{t.speaker}</span>
            <span className="chip h-6 text-[12px]">{t.path ? `${PATH[t.path] ?? t.path} · ${secs(t.eotMs ?? t.ms)}` : "…"}</span>
          </header>
          <p className="line-clamp-2 text-[17px] leading-[1.3] text-ink">« {t.text} »</p>
          {t.events?.length ? <p className="label text-[13px] text-ink-2">→ {t.events.join(", ")}</p> : null}
          {t.reply && <p className="line-clamp-2 text-[15px] leading-[1.3] text-ink-2">Seraph : {t.reply}</p>}
        </section>
      ))}
    </div>
  );
}
