// French UI text (radio French: short) and Europe/Paris time formatting.
import type { Call, Gate, Hazard, IncidentState, Lang, Moment, Occupant, Source, Team, ViewRequestStatus } from "./types";

const TZ = "Europe/Paris";
const fmtHM = new Intl.DateTimeFormat("fr-FR", { timeZone: TZ, hour: "2-digit", minute: "2-digit" });
const fmtHMS = new Intl.DateTimeFormat("fr-FR", { timeZone: TZ, hour: "2-digit", minute: "2-digit", second: "2-digit" });

export const hm = (iso?: string | null) => (iso ? fmtHM.format(new Date(iso)) : "--:--");
export const hms = (t: number | string) => fmtHMS.format(new Date(t));

/** 4:05, 1:02:03 */
export function dur(ms: number) {
  if (!Number.isFinite(ms)) return "—";
  let s = Math.floor(Math.abs(ms) / 1000);
  const h = Math.floor(s / 3600);
  s -= h * 3600;
  const m = Math.floor(s / 60);
  s -= m * 60;
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${ms < 0 ? "-" : ""}${h ? `${h}:${pad(m)}` : m}:${pad(s)}`;
}

/** 1,8 s · 24 s · 5,2 min */
export function secs(ms?: number | null) {
  if (ms == null) return "—";
  if (ms < 10_000) return `${(ms / 1000).toFixed(1).replace(".", ",")} s`;
  if (ms < 120_000) return `${Math.round(ms / 1000)} s`;
  return `${(ms / 60_000).toFixed(1).replace(".", ",")} min`;
}

export function levelLabel(state: IncidentState, level?: number) {
  if (level == null) return "?";
  return state.building.levels.find((l) => l.level === level)?.label ?? (level === 0 ? "RDC" : `R+${level}`);
}

export const INCIDENT_STATUS: Record<IncidentState["incident"]["status"], string> = {
  idle: "En attente",
  dispatched: "Déclenché",
  en_route: "En route",
  on_scene: "Sur place",
  closing: "Clôture",
  closed: "Clos",
};

export const OCC_STATUS: Record<Occupant["status"], string> = {
  unknown: "inconnu",
  calling: "appel…",
  in_call: "en ligne",
  no_answer: "sans réponse",
  safe_outside: "dehors",
  sheltering: "à l'abri",
  trapped: "bloqué",
  moving: "se déplace",
  needs_help: "aide requise",
};

/** Brand signal colour per occupant status (brand/tokens.css). Always paired with a label. */
export const OCC_TONE: Record<Occupant["status"], Tone> = {
  unknown: "gris",
  calling: "blanc",
  in_call: "blanc",
  no_answer: "gris",
  safe_outside: "sur",
  sheltering: "blanc",
  trapped: "danger",
  moving: "alerte",
  needs_help: "danger",
};

export const CALL_STATUS: Record<Call["status"], string> = {
  ringing: "sonne",
  active: "en ligne",
  ended: "terminé",
  no_answer: "sans réponse",
  failed: "échec",
};

export const CALL_TONE: Record<Call["status"], Tone> = {
  ringing: "alerte",
  active: "sur",
  ended: "gris",
  no_answer: "danger",
  failed: "danger",
};

export const TEAM_STATUS: Record<Team["status"], string> = {
  standby: "attente",
  engaged: "engagé",
  exiting: "sortie",
  out: "dehors",
};

export const GATE_KIND: Record<Gate["kind"], string> = {
  relay_order: "Ordre à relayer",
  reroute_occupant: "Réorienter un occupant",
  send_report: "Envoyer le rapport",
  learn_source: "Nouvelle source",
};

export const GATE_STATUS: Record<Gate["status"], string> = {
  pending: "en attente",
  confirmed: "confirmé",
  cancelled: "annulé",
  expired: "expiré",
};

export const VIEW_STATUS: Record<ViewRequestStatus["status"], string> = {
  requested: "demandée",
  building: "Devin construit",
  ready: "prête",
  failed: "échec",
  timed_out: "délai dépassé",
};

export const HAZARD: Record<Hazard["kind"], string> = {
  smoke: "fumée",
  fire: "feu",
  heat: "chaleur",
  gas: "gaz",
  structure: "structure",
  electric: "électrique",
};

export const LANG: Record<Lang, string> = { fr: "FR", en: "EN", es: "ES", ar: "AR", other: "??" };

/** Keys 1–5 force these Halo moments (docs/03-demo-script.md). */
export const MOMENTS: Moment[] = ["dispatch", "approach", "inside_route", "occupants", "team_engaged"];

export const ENDPOINT_SITE: Record<string, string> = {
  "dispatch.read": "Dispatch · réplique",
  "maps.building": "Google Maps · Earth",
  "georisques.risks": "georisques.gouv.fr",
  "plan.read": "Plan affiché · photo",
  "occupants.list": "Gestionnaire · réplique",
  "dispatch.write_112": "Main courante · réplique",
  "report.fill": "Compte rendu · réplique",
  "weather.wind": "Météo-France",
};

export const ENDPOINT_KIND = { real: "réel", replica: "répl.", learned: "appris" } as const;

/** Short source tag shown next to every fact (docs/07-safety-rules.md rule 3). */
export const SOURCE_KIND: Record<Source["kind"], string> = {
  radio: "radio",
  call: "appel",
  plan: "plan",
  maps: "Maps",
  earth: "Earth",
  streetview: "Street View",
  georisques: "Géorisques",
  meteo: "Météo",
  dispatch: "dispatch",
  occupants: "gestionnaire",
  ifc: "maquette",
  seraph: "calcul",
  learned: "non vérifié",
};

export type Tone = "blanc" | "gris" | "sur" | "propose" | "alerte" | "danger" | "rosetta";
