"use client";
// Live data for the projector: Seraph state + SSE, Rosetta agent cam (WS), Silex sessions (poll 2 s), health (poll 5 s).
// MOCK=1 → contracts/fixtures only. Seraph unreachable → the same fixtures, labelled, retried every 4 s.
import { useCallback, useEffect, useRef, useState } from "react";
import type {
  Alert,
  Call,
  Gate,
  GabrielToSeraph,
  IncidentState,
  Lang,
  Moment,
  RosettaResult,
  SeraphToGabriel,
  TimelineEntry,
  ViewRequestStatus,
} from "./types";

export type RadioLine = { id: string; t: string; speaker: string; text: string; seraph: boolean; source?: string };
export type CamFrame = {
  run_id: string;
  endpoint: string;
  step?: number;
  action?: string;
  thought?: string;
  shot_url?: string;
  page_url?: string;
  at: string;
  first_at: string;
};
// `replay` (Seraph only): "idle" | "running:<fixture>" | "done" | "cancelled" — anything but idle is a replay until reset
export type ServiceHealth = { ok: boolean; mock: boolean; ms: number | null; replay?: string };
/** One line said to Seraph on the radio and what it became: rules or LLM, measured time, Seraph's answer. */
export type Turn = {
  id: string;
  t: string;
  speaker: string;
  text: string;
  path?: string; // rules | llm | none (Seraph's voice_to_say metric)
  ms?: number; // Seraph's processing time
  eotMs?: number; // end of speech → Seraph's answer, when Gabriel gives the end time
  events?: string[]; // Seraph's event types, e.g. ["hazard", "hazard"]; ["chatter"] for crew-to-crew talk
  said?: boolean; // false: Seraph listened and did not answer
  reply?: string;
};
export type SilexSession = {
  id?: string;
  session_id?: string;
  url?: string;
  kind?: string;
  status?: string;
  started_at?: string;
  purpose?: string;
};
export type Mode = "connecting" | "live" | "mock" | "fixtures";
export type Config = { mock: boolean; seraph?: string; halo?: string; rosettaWs: string; haloMirror: string | null; inscription?: string | null; fixtures?: string };
export type Toast = { id: number; text: string; tone: "ok" | "err" | "wait" };

export interface Live {
  mode: Mode;
  streamOk: boolean;
  state: IncidentState | null;
  radio: RadioLine[];
  turns: Turn[];
  cams: Record<string, CamFrame>;
  results: Record<string, RosettaResult>;
  sessions: SilexSession[];
  health: Record<string, ServiceHealth>;
  metrics: Record<string, number>;
  config: Config | null;
  toast: Toast | null;
  act: (label: string, service: string, path: string, body?: unknown) => Promise<void>;
  confirmGate: (id: string) => void;
  cancelGate: (id: string) => void;
}

// ───────── helpers ─────────

async function getJSON<T>(url: string, ms = 3000): Promise<T> {
  const r = await fetch(url, { cache: "no-store", signal: AbortSignal.timeout(ms) });
  if (!r.ok) throw new Error(`${url} → ${r.status}`);
  return r.json() as Promise<T>;
}

async function getLines<T>(url: string): Promise<T[]> {
  const r = await fetch(url, { cache: "no-store", signal: AbortSignal.timeout(3000) });
  if (!r.ok) throw new Error(`${url} → ${r.status}`);
  return (await r.text())
    .split("\n")
    .filter((l) => l.trim())
    .map((l) => JSON.parse(l) as T);
}

function upsert<T, K extends keyof T>(list: T[], item: T, key: K): T[] {
  const i = list.findIndex((x) => x[key] === item[key]);
  if (i < 0) return [...list, item];
  const next = list.slice();
  next[i] = item;
  return next;
}

const ISO = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d+)?)?Z$/;
/** Shift every ISO timestamp so a fixture snapshot reads as "now". */
function rebase<T>(v: T, shift: number): T {
  if (typeof v === "string" && ISO.test(v)) return new Date(Date.parse(v) + shift).toISOString() as T;
  if (Array.isArray(v)) return v.map((x) => rebase(x, shift)) as T;
  if (v && typeof v === "object")
    return Object.fromEntries(Object.entries(v).map(([k, x]) => [k, rebase(x, shift)])) as T;
  return v;
}

// ───────── fixtures (mock mode) ─────────

type RadioFixture = { id: string; speaker: string; lang: Lang; text: string; expected?: { say_crew?: string } };
type CallFixture = { call_id: string; occupant_id?: string; lang: Lang; expected_crew?: string };
type Fixtures = {
  state: IncidentState;
  radio: RadioFixture[];
  calls: CallFixture[];
  results: Record<string, RosettaResult>;
};

const FIXTURE_NOW = Date.parse("2026-11-08T00:41:00Z"); // the moment state-sample.json describes
const ENDPOINT_FIXTURES = [
  "dispatch.read",
  "maps.building",
  "georisques.risks",
  "plan.read",
  "occupants.list",
  "dispatch.write_112",
  "report.fill",
  "weather.wind",
];

// `base`: /api/fixtures (contracts/fixtures, dev) or /fixtures (the copy made at build: a deployed replay has no repo
// around it), as /api/config says. Rosetta's shots come from public/shots, never from Rosetta.
async function loadFixtures(base = "/api/fixtures"): Promise<Fixtures> {
  const [state, radio, calls, ...results] = await Promise.all([
    getJSON<IncidentState>(`${base}/state-sample.json`),
    getLines<RadioFixture>(`${base}/radio.jsonl`),
    getLines<CallFixture>(`${base}/calls.jsonl`),
    ...ENDPOINT_FIXTURES.map((e) => getJSON<RosettaResult>(`${base}/endpoints/${e}.json`).catch(() => null)),
  ]);
  const local = (r: RosettaResult): RosettaResult => ({
    ...r,
    screenshots: r.screenshots.map((s) => ({ ...s, url: s.url.replace(/^https?:\/\/[^/]+\/shots\//, "/shots/") })),
  });
  return {
    state,
    radio,
    calls,
    results: Object.fromEntries(results.filter((r): r is RosettaResult => !!r).map((r) => [r.endpoint, local(r)])),
  };
}

const at = (hhmmss: string) => `2026-11-08T${hhmmss}Z`;

/** The state-sample snapshot, plus call summaries and the crew lines that led to it (fixture times). */
function mockSeed(fx: Fixtures) {
  const summary = (occ: string) => fx.calls.find((c) => c.occupant_id === occ)?.expected_crew;
  const state: IncidentState = structuredClone(fx.state);
  state.calls = state.calls.map((c) => ({ ...c, summary_fr: c.summary_fr ?? (c.occupant_id && summary(c.occupant_id)) ?? undefined }));

  const r = (id: string) => fx.radio.find((x) => x.id === id);
  const lines: RadioLine[] = [];
  const crew = (id: string, t: string) => {
    const x = r(id);
    if (x) lines.push({ id, t: at(t), speaker: x.speaker, text: x.text, seraph: false });
  };
  const say = (id: string, t: string, text?: string, source?: string) => {
    if (text) lines.push({ id: `say-${id}`, t: at(t), speaker: "Seraph", text, seraph: true, source });
  };
  crew("R01", "00:28:10");
  say("R01", "00:28:30", r("R01")?.expected?.say_crew, "calcul");
  crew("R02", "00:33:00");
  say("R02", "00:33:05", r("R02")?.expected?.say_crew);
  say("CALL-01", "00:33:40", summary("OCC-01"), "appel");
  say("CALL-04", "00:35:00", summary("OCC-05"), "appel");
  crew("R03", "00:36:00");
  say("CALL-06", "00:37:00", summary("OCC-02"), "appel");
  crew("R04", "00:38:00");
  say("R04", "00:38:10", r("R04")?.expected?.say_crew, "appel");
  say("CALL-02", "00:39:10", summary("OCC-04"), "appel");
  const gate = state.gates.find((g) => g.status === "pending");
  if (gate) say(gate.gate_id, "00:39:30", gate.summary_fr, "appel");
  return { state, lines };
}

// ───────── the hook ─────────

export function useLive(): Live {
  const [mode, setMode] = useState<Mode>("connecting");
  const [streamOk, setStreamOk] = useState(false);
  const [state, setState] = useState<IncidentState | null>(null);
  const [radio, setRadio] = useState<RadioLine[]>([]);
  const [cams, setCams] = useState<Record<string, CamFrame>>({});
  const [results, setResults] = useState<Record<string, RosettaResult>>({});
  const [sessions, setSessions] = useState<SilexSession[]>([]);
  const [health, setHealth] = useState<Record<string, ServiceHealth>>({});
  const [metrics, setMetrics] = useState<Record<string, number>>({});
  const [turns, setTurns] = useState<Turn[]>([]);
  const [config, setConfig] = useState<Config | null>(null);
  const [toast, setToast] = useState<Toast | null>(null);

  const modeRef = useRef<Mode>("connecting");
  const mockRef = useRef<{ handle: (path: string, body?: unknown) => string } | null>(null);
  const setModeBoth = (m: Mode) => {
    modeRef.current = m;
    setMode(m);
  };

  const pushRadio = useCallback((line: RadioLine) => {
    setRadio((r) => (r.some((x) => x.id === line.id) ? r : [...r, line].slice(-80)));
  }, []);

  const say = useCallback((text: string, tone: Toast["tone"]) => setToast({ id: Date.now() + Math.random(), text, tone }), []);

  useEffect(() => {
    let stopped = false;
    let es: EventSource | null = null;
    let ws: WebSocket | null = null;
    const timers = new Set<ReturnType<typeof setTimeout>>();
    const later = (fn: () => void, ms: number) => {
      const t = setTimeout(() => {
        timers.delete(t);
        if (!stopped) fn();
      }, ms);
      timers.add(t);
    };
    let fixtures: Fixtures | null = null;
    const scriptTimers = new Set<ReturnType<typeof setTimeout>>();
    const scriptLater = (fn: () => void, ms: number) => {
      const t = setTimeout(() => {
        scriptTimers.delete(t);
        if (!stopped) fn();
      }, ms);
      scriptTimers.add(t);
    };

    // — mock engine: fixture snapshot rebased to now, then a short scripted replay of radio.jsonl —
    function startFixtures(script: boolean) {
      if (!fixtures) return;
      const fx = fixtures;
      scriptTimers.forEach(clearTimeout);
      scriptTimers.clear();
      const shift = Date.now() - FIXTURE_NOW;
      const seed = rebase(mockSeed(fx), shift);
      setState(seed.state);
      setRadio(seed.lines);
      setResults(rebase(fx.results, shift));
      if (!script) return;

      const line = (id: string, withAnswer = true) => {
        const x = fx.radio.find((r) => r.id === id);
        if (!x) return;
        const t = new Date().toISOString();
        pushRadio({ id: `${id}-${t}`, t, speaker: x.speaker, text: x.text, seraph: false });
        const answer = x.expected?.say_crew;
        if (withAnswer && answer && !answer.includes("…"))
          scriptLater(() => pushRadio({ id: `say-${id}-${t}`, t: new Date().toISOString(), speaker: "Seraph", text: answer, seraph: true }), 2200);
      };
      const resolve = (status: Gate["status"], by: Gate["resolved_by"]) =>
        setState((s) => {
          if (!s) return s;
          const g = [...s.gates].reverse().find((x) => x.status === "pending");
          if (!g) return s;
          return { ...s, gates: upsert(s.gates, { ...g, status, resolved_by: by, resolved_at: new Date().toISOString() }, "gate_id") };
        });
      const steps: [number, () => void][] = [
        [9000, () => line("R05", false)],
        [9000, () => line("R06")],
        [11000, () => { line("R07", false); resolve("confirmed", "voice"); }],
        [11000, () => line("R09")],
        [11000, () => {
          line("R10");
          setState((s) => s && {
            ...s,
            gates: [...s.gates, {
              gate_id: `gate_report_${Date.now()}`,
              kind: "send_report",
              summary_fr: "Compte rendu prêt dans le logiciel. Je le transmets au CODIS ?",
              confirmer: "COS",
              status: "pending",
              created_at: new Date().toISOString(),
            }],
          });
        }],
        [14000, () => line("R12")],
        [24000, () => startFixtures(true)],
      ];
      let i = 0;
      const next = () => {
        if (i >= steps.length) return;
        const [ms, fn] = steps[i++];
        scriptLater(() => { fn(); next(); }, ms);
      };
      next();

      mockRef.current = {
        handle(path, body) {
          if (path === "admin/moment") {
            // what Seraph does on a moment change: Halo shows the view built for it (in mock, the kit's example)
            const moment = (body as { moment: Moment }).moment;
            setState((s) => s && {
              ...s,
              halo: { ...s.halo, current_view: { view_id: `view_${moment}_example`, url: "", moment, built_by: "devin", since: new Date().toISOString() } },
            });
            return `Mock · Halo → ${moment}`;
          }
          if (path === "incident/start" || path === "admin/reset") {
            startFixtures(true);
            return "Mock · fixtures rechargées";
          }
          const m = path.match(/^gates\/(.+)\/(confirm|cancel)$/);
          if (m) {
            setState((s) => {
              const g = s?.gates.find((x) => x.gate_id === m[1]);
              if (!s || !g) return s;
              const status = m[2] === "confirm" ? "confirmed" : "cancelled";
              return { ...s, gates: upsert(s.gates, { ...g, status, resolved_by: "dashboard", resolved_at: new Date().toISOString() }, "gate_id") };
            });
            return m[2] === "confirm" ? "Mock · confirmé" : "Mock · annulé";
          }
          if (path === "admin/replay") {
            // the whole scripted replay again from the snapshot (Shift+R, and the guided tour's last button)
            startFixtures(true);
            return "Rejeu relancé";
          }
          return `Mock · ${path} non simulé`;
        },
      };
    }

    // — live: Seraph state + SSE —
    function openStream() {
      es = new EventSource("/api/proxy/seraph/stream?client=dashboard");
      es.onopen = () => setStreamOk(true);
      es.onerror = () => setStreamOk(false);
      const on = <T,>(name: string, fn: (data: T) => void) =>
        es!.addEventListener(name, (e) => {
          try {
            fn(JSON.parse((e as MessageEvent).data) as T);
          } catch {
            /* malformed event: ignore, next state snapshot fixes it */
          }
        });
      on<IncidentState>("state", setState);
      on<GabrielToSeraph>("radio", (m) => {
        if (m.kind !== "radio_transcript") return;
        pushRadio({ id: m.utterance_id, t: m.start, speaker: m.speaker, text: m.text_fr ?? m.text, seraph: false });
        setTurns((ts) => (ts.some((x) => x.id === m.utterance_id) ? ts : [...ts, { id: m.utterance_id, t: new Date().toISOString(), speaker: m.speaker, text: m.text_fr ?? m.text }].slice(-40)));
      });
      on<SeraphToGabriel>("say", (m) => {
        if (m.kind !== "say" || !("room" in m.target) || m.target.room !== "crew") return;
        pushRadio({ id: m.say_id, t: new Date().toISOString(), speaker: "Seraph", text: m.text, seraph: true });
        // Seraph answers a line before its metric arrives: the answer goes to the latest line still without one
        setTurns((ts) => {
          const i = ts.findLastIndex((x) => !x.reply && Date.now() - Date.parse(x.t) < 20_000);
          return i < 0 ? ts : ts.map((x, j) => (j === i ? { ...x, reply: m.text } : x));
        });
      });
      on<Call>("call", (c) => setState((s) => s && { ...s, calls: upsert(s.calls, c, "call_id") }));
      on<Gate>("gate", (g) => setState((s) => s && { ...s, gates: upsert(s.gates, g, "gate_id") }));
      on<Alert>("alert", (a) => setState((s) => s && { ...s, alerts: upsert(s.alerts, a, "alert_id") }));
      on<TimelineEntry>("timeline", (e) => setState((s) => s && { ...s, timeline: [...s.timeline, e].slice(-300) }));
      on<RosettaResult>("rosetta", (r) => setResults((m) => ({ ...m, [r.endpoint]: r })));
      on<ViewRequestStatus | { name: string }>("silex", (v) => {
        if (!("request_id" in v)) return;
        setState((s) => s && { ...s, halo: { ...s.halo, requests: upsert(s.halo.requests, v, "request_id") } });
      });
      on<{ name: string; value_ms: number; path?: string; since_eot_ms?: number | null; utterance_id?: string; events?: unknown; said?: boolean }>("metric", (m) => {
        setMetrics((x) => ({ ...x, [m.name]: m.value_ms }));
        if (m.name !== "voice_to_say" || !m.utterance_id) return;
        const events = Array.isArray(m.events) ? m.events.map((e) => (typeof e === "string" ? e : String((e as { type?: string }).type ?? ""))).filter(Boolean) : undefined;
        setTurns((ts) => ts.map((x) => (x.id === m.utterance_id ? { ...x, path: m.path, ms: m.value_ms, eotMs: m.since_eot_ms ?? undefined, events, said: m.said } : x)));
      });
    }

    async function connectSeraph() {
      try {
        const s = await getJSON<IncidentState>("/api/proxy/seraph/state", 3000);
        if (stopped) return;
        setState(s);
        setRadio(
          s.timeline
            .filter((e) => e.kind === "radio")
            .map((e, i) => {
              // timeline radio lines read « Speaker : text »
              const m = e.text_fr.match(/^([^:]{1,24}?) : (.+)$/);
              const speaker = m ? m[1] : "Radio";
              return { id: `tl-${i}-${e.t}`, t: e.t, speaker, text: m ? m[2] : e.text_fr, seraph: speaker.startsWith("Seraph") };
            }),
        );
        setResults({});
        setModeBoth("live");
        openStream();
      } catch {
        if (stopped) return;
        if (modeRef.current !== "fixtures") {
          fixtures ??= await loadFixtures().catch(() => null);
          startFixtures(false);
          setModeBoth("fixtures");
        }
        later(connectSeraph, 4000);
      }
    }

    function openCam(url: string) {
      try {
        ws = new WebSocket(url);
      } catch {
        later(() => openCam(url), 3000);
        return;
      }
      ws.onmessage = (e) => {
        try {
          const f = JSON.parse(e.data) as Omit<CamFrame, "first_at">;
          setCams((c) => ({ ...c, [f.run_id]: { ...f, first_at: c[f.run_id]?.first_at ?? f.at } }));
        } catch {
          /* not a frame */
        }
      };
      ws.onerror = () => ws?.close();
      ws.onclose = () => later(() => openCam(url), 3000);
    }

    async function pollSilex() {
      try {
        const r = await getJSON<SilexSession[] | { sessions: SilexSession[] }>("/api/proxy/silex/sessions", 1800);
        setSessions(Array.isArray(r) ? r : r.sessions ?? []);
      } catch {
        /* silex down: health shows it */
      }
      later(pollSilex, 2000);
    }

    async function pollHealth() {
      try {
        setHealth(await getJSON<Record<string, ServiceHealth>>("/api/health", 4000));
      } catch {
        /* dashboard server itself is down: nothing to show */
      }
      later(pollHealth, 5000);
    }

    (async () => {
      pollHealth();
      const cfg = await getJSON<Config>("/api/config").catch((): Config => ({ mock: false, rosettaWs: "", haloMirror: null }));
      if (stopped) return;
      setConfig(cfg);
      if (cfg.mock) {
        fixtures = await loadFixtures(cfg.fixtures).catch(() => null);
        setModeBoth("mock");
        startFixtures(true);
        return;
      }
      connectSeraph();
      if (cfg.rosettaWs) openCam(cfg.rosettaWs);
      pollSilex();
    })();

    return () => {
      stopped = true;
      timers.forEach(clearTimeout);
      scriptTimers.forEach(clearTimeout);
      es?.close();
      if (ws) {
        ws.onclose = null;
        ws.close();
      }
    };
  }, [pushRadio]);

  useEffect(() => {
    if (!toast || toast.tone === "wait") return;
    const t = setTimeout(() => setToast((x) => (x?.id === toast.id ? null : x)), 3500);
    return () => clearTimeout(t);
  }, [toast]);

  const act = useCallback(
    async (label: string, service: string, path: string, body?: unknown) => {
      if (modeRef.current !== "live") {
        const text = mockRef.current?.handle(path, body) ?? `${label} · Seraph injoignable`;
        say(text, mockRef.current ? "ok" : "err");
        return;
      }
      say(`${label}…`, "wait");
      try {
        const r = await fetch(`/api/proxy/${service}/${path}`, {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify(body ?? {}),
          signal: AbortSignal.timeout(6000),
        });
        if (!r.ok) throw new Error(String(r.status));
        say(`${label} · ok`, "ok");
      } catch {
        say(`${label} · échec, ${service} injoignable`, "err");
      }
    },
    [say],
  );

  const confirmGate = useCallback((id: string) => act("Confirmer", "seraph", `gates/${id}/confirm`), [act]);
  const cancelGate = useCallback((id: string) => act("Annuler", "seraph", `gates/${id}/cancel`), [act]);

  return { mode, streamOk, state, radio, turns, cams, results, sessions, health, metrics, config, toast, act, confirmGate, cancelGate };
}
