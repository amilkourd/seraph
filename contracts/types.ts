// Seraph contracts — the single source of truth for every message and for the incident state.
// TypeScript apps import this file. Python services mirror it with Pydantic models (same field names, snake_case).
// Owned by Amil. Do not edit from a session: ask in your status file.

// ───────────────────────── Common ─────────────────────────
export type Lang = "fr" | "en" | "es" | "ar" | "other";
export type ISODate = string;

/** Where a fact comes from. Shown next to every element on Halo and the dashboard. */
export interface Source {
  kind: "radio" | "call" | "plan" | "maps" | "earth" | "streetview" | "georisques" | "meteo" | "dispatch"
      | "occupants" | "ifc" /* building model */ | "seraph" /* computed by code */ | "learned" /* unverified learned source */;
  label: string;          // short French label shown in UI: « appel 3.12 », « plan », « Maps », « calcul »
  url?: string;           // page or screenshot URL when there is one
  confirmed: boolean;     // true = said on the radio/call or read from the source; false = inferred
  at: ISODate;
}

/** A point on an image, on H's 0–1000 grid (x right, y down), as returned by Holo pointing. */
export interface ImagePoint { image_id: string; x: number; y: number; }

export interface Screenshot {
  image_id: string;       // stable id, e.g. "maps-front-01"
  url: string;            // served by rosetta: http://localhost:8001/shots/<image_id>.jpg
  caption: string;        // « Façade côté boulevard (Street View) »
  side?: "front" | "left" | "right" | "rear" | "top" | "plan";
  width: number; height: number;
  taken_at: ISODate;
}

// ───────────────────────── Incident state (Seraph owns it) ─────────────────────────
export interface IncidentState {
  incident: {
    id: string;                       // "INC-0001"
    address: string;
    nature: string;                   // « Feu de local technique »
    origin: { floor: number; room?: string } | null;
    declared_at: ISODate | null;
    status: "idle" | "dispatched" | "en_route" | "on_scene" | "closing" | "closed";
    exercise: true;                   // always true: every screen says EXERCICE
  };
  building: Building;
  occupants: Occupant[];
  calls: Call[];
  crew: { teams: Team[] };
  environment: { wind: Wind | null; risks: Risk[] };
  routes: Route[];                    // computed by Seraph code only
  gates: Gate[];
  halo: HaloStatus;
  rosetta: RosettaStatus;
  timeline: TimelineEntry[];
  alerts: Alert[];
}

export interface Building {
  name: string;
  levels: { level: number; label: string; elevation_m?: number }[];          // 0 = RDC
  stairs: { id: string; label: string; status: "clear" | "smoke" | "blocked" | "unknown"; source?: Source }[];
  entrances: { id: string; label: string; side: "front" | "left" | "right" | "rear"; status: "usable" | "locked" | "blocked" | "unknown"; point?: ImagePoint; source?: Source }[];
  hydrants: { id: string; label: string; distance_m?: number; point?: ImagePoint; source?: Source }[];
  truck_spot: { label: string; point?: ImagePoint; source?: Source } | null;
  rooms: { id: string; level: number; label: string; area_m2?: number; use?: string; zone?: number[][]; /* polygon on plan image, 0–1000 */ source?: Source }[];
  plan: { image_id: string; url: string; level: number; points: { name: string; label: string; point: ImagePoint }[] } | null;
  hazards: Hazard[];
  approach: { best_entrance_id: string; reason: string; source: Source } | null;   // chosen by code
  screenshots: Screenshot[];          // all Rosetta screenshots kept as visual references
  // From the building's IFC (docs/10-ifc.md). Absent when there is no model. Never guessed: unknown = absent.
  doors?: { id: string; level: number; label: string; between: [string, string]; external?: boolean; fire_rating?: string; source?: Source }[];
  materials?: { element: "wall" | "slab" | "door" | "facade" | "roof"; level?: number; room?: string; material: string; fire_rating?: string; source: Source }[];
  graph?: { nodes: string[]; edges: ([string, string] | [string, string, number])[] };   // routing graph; 3rd item = length in m
  model?: {
    provenance: "architect" | "rebuilt_from_posted_plan" | "fictional";
    provenance_fr: string;            // on every screen: « Maquette IFC reconstruite depuis le plan affiché — exercice »
    ifc_url?: string; glb_url?: string;
    level_plans: { level: number; url: string; image_id: string }[];   // image_id "ifc-L<n>"; same 0–1000 frame as rooms[].zone
    stats: { levels: number; stairs: number; doors: number; rooms: number };
  } | null;
}

export interface Hazard {
  id: string;
  kind: "smoke" | "fire" | "heat" | "gas" | "structure" | "electric";
  where: { level?: number; room?: string; stair?: string; entrance?: string };
  severity: "low" | "medium" | "high";
  source: Source;
  reported_at: ISODate;
}

export interface Occupant {
  id: string;                         // "OCC-01"
  name?: string;
  phone_masked?: string;              // never show full numbers on screens
  level?: number; room?: string;
  people_count?: number;              // people with this caller
  status: "unknown" | "calling" | "in_call" | "no_answer" | "safe_outside" | "sheltering" | "trapped" | "moving" | "needs_help";
  mobility_issue?: boolean; injuries?: string; smoke_seen?: boolean; heading_to?: string; // e.g. "stair:B"
  language?: Lang;
  last_update: ISODate;
  source: Source;
  call_id?: string;
}

export interface Call {
  call_id: string;                    // "CALL-07"
  direction: "in" | "out";
  occupant_id?: string;
  number_masked: string;
  channel: "phone" | "web";
  status: "ringing" | "active" | "ended" | "no_answer" | "failed";
  language?: Lang;
  started_at: ISODate; ended_at?: ISODate;
  summary_fr?: string;                // one line for the crew
  transcript_excerpt?: string;
  voice?: VoiceSignal;                // last thing Gladia heard in the caller's voice; shown « selon la voix »
  urgency?: CallUrgency;              // computed by Seraph code (briefs/seraph.md); the calls board sorts on it
}

/** Computed by Seraph code, never by a model. Facts set the level; the voice can raise it by one, never lower it. */
export interface CallUrgency {
  level: 1 | 2 | 3;                   // 3 « urgent » · 2 « à suivre » · 1 « hors danger »
  reasons_fr: string[];               // « fauteuil roulant », « fumée sous la porte », « peur dans la voix »
  raised_by_voice: boolean;           // true = the facts alone gave one level less
  computed_at: ISODate;
}

export interface Team {
  id: string;                         // "B1"
  label: string;                      // « Binôme 1 »
  status: "standby" | "engaged" | "exiting" | "out";
  entered_at?: ISODate;
  pressure_bar_start?: number;
  exit_by?: ISODate;                  // computed by Seraph code (see briefs/seraph.md)
  location?: { level?: number; room?: string; stair?: string };
  last_update: ISODate;
}

export interface Wind { dir_deg: number; dir_label: string; speed_kmh: number; source: Source; }
export interface Risk { label: string; category: string; detail?: string; source: Source; }

export interface Route {
  id: string;
  purpose: "approach" | "to_victim" | "evacuation";
  from: string; to: string;           // node ids: "truck", "entrance:E2", "stair:A", "level:3", "room:3.12", "outside"
  via: string[];                      // ordered node ids
  avoids: string[];                   // hazard ids avoided
  computed_at: ISODate;
  source: Source;                     // kind "seraph", label « calcul »
}

export interface Gate {
  gate_id: string;
  kind: "relay_order" | "reroute_occupant" | "send_report" | "learn_source";
  summary_fr: string;                 // what will happen if confirmed
  confirmer: "COS";
  status: "pending" | "confirmed" | "cancelled" | "expired";
  created_at: ISODate; resolved_at?: ISODate; resolved_by?: "voice" | "dashboard";
}

export interface HaloStatus {
  current_view: { view_id: string; url: string; moment: Moment; built_by: "devin" | "fallback"; since: ISODate } | null;
  requests: ViewRequestStatus[];
}

export type Moment = "dispatch" | "approach" | "inside_route" | "occupants" | "team_engaged" | "commander_request" | "report";

export interface ViewRequestStatus {
  request_id: string; moment: Moment; purpose_fr: string;
  status: "requested" | "building" | "ready" | "failed" | "timed_out";
  view_id?: string; url?: string; devin_session_url?: string;
  requested_at: ISODate; ready_at?: ISODate;
}

export interface RosettaStatus {
  endpoints: { name: string; kind: "real" | "replica" | "learned"; verified: boolean; last_run_at?: ISODate; last_duration_ms?: number; last_live?: boolean; status: "idle" | "running" | "ok" | "failed" }[];
  counter: { sources_without_api: number; endpoints: number };
}

export interface TimelineEntry { t: ISODate; kind: "radio" | "call" | "rosetta" | "silex" | "seraph" | "gate" | "alert"; text_fr: string; source?: Source; }
export interface Alert { alert_id: string; level: "info" | "warning" | "danger"; text_fr: string; created_at: ISODate; spoken: boolean; }

// ───────────────────────── Gabriel ⇄ Seraph (WebSocket ws://localhost:8000/ws/gabriel) ─────────────────────────
export type GabrielToSeraph =
  | { kind: "radio_transcript"; utterance_id: string; room: "crew"; speaker: string; lang: Lang; text: string; text_fr?: string; start: ISODate; end: ISODate; audio_path?: string }
  | { kind: "call_event"; call_id: string; event: "ringing" | "answered" | "ended" | "no_answer" | "failed"; direction: "in" | "out"; channel: "phone" | "web"; occupant_id?: string; number_masked: string; lang?: Lang; at: ISODate }
  | { kind: "call_facts"; call_id: string; occupant_id?: string; lang: Lang; facts: CallFacts; transcript_excerpt: string; at: ISODate };

export interface CallFacts {
  level?: number; room?: string; people_count?: number;
  smoke_seen?: boolean; fire_seen?: boolean; heat?: boolean;
  mobility_issue?: boolean; injuries?: string;
  current_action?: "staying" | "moving" | "outside" | "unknown";
  heading_to?: string;                // "stair:B", "exit:E1"…
  free_text_fr?: string;              // anything else useful, translated to French
  confidence: number;                 // 0–1, from the extraction
  voice?: VoiceSignal;                // Gladia live sentiment + emotion on the caller's last sentence (docs/06-gabriel.md)
}

/** What Gladia hears in the caller's voice (live sentiment and emotion analysis). Inferred: never an instruction, never a position. */
export interface VoiceSignal {
  emotion: GladiaEmotion;
  sentiment: "positive" | "negative" | "neutral" | "mixed" | "unknown";
  text: string;                       // the sentence it was heard on, in the caller's language
  at: ISODate;
}
export type GladiaEmotion = "adoration" | "amusement" | "anger" | "awe" | "confusion" | "contempt" | "contentment" | "desire"
  | "disappointment" | "disgust" | "distress" | "ecstatic" | "elation" | "embarrassment" | "fear" | "interest" | "pain"
  | "realization" | "relief" | "sadness" | "negative_surprise" | "positive_surprise" | "sympathy" | "triumph" | "neutral";

export type SeraphToGabriel =
  | { kind: "say"; say_id: string; target: { room: "crew" } | { call_id: string } | { call_ids: string[] }; text: string; lang: Lang; priority: "normal" | "alert" }
  | { kind: "place_calls"; calls: { occupant_id: string; phone_e164: string; name?: string; language_hint?: Lang }[] }
  | { kind: "end_call"; call_id: string };

// ───────────────────────── Seraph → Rosetta (HTTP) ─────────────────────────
export interface RosettaRun { run_id: string; endpoint: string; params: Record<string, unknown>; priority: number; allow_cache: boolean; }
export interface RosettaResult {
  run_id: string; endpoint: string;
  status: "queued" | "running" | "ok" | "failed";
  live: boolean;                      // false = served from cache (always shown in UI)
  output?: Record<string, unknown>;   // shape per endpoint: contracts/rosetta-endpoints.md
  screenshots: Screenshot[];
  source: Source;
  error?: string; duration_ms?: number; started_at: ISODate; ended_at?: ISODate;
}

// ───────────────────────── Seraph → Silex (HTTP) ─────────────────────────
export interface ViewRequest {
  request_id: string;
  moment: Moment;
  purpose_fr: string;                 // « Montrer au chef d'agrès comment entrer : bloc, rue, camion, flèche vers E2 »
  data_keys: string[];                // which IncidentState paths the view reads, e.g. ["building.entrances", "building.approach", "routes"]
  references: Screenshot[];           // Rosetta screenshots the view should look like (simplified)
  interactions: string[];             // e.g. ["tap a level → Seraph shows who is there"]
  deadline_s: number;                 // after this, Seraph stays on the fallback view
  sample_state_url: string;           // GET returns the current IncidentState to build against
}
export interface ViewReady { request_id: string; status: "building" | "ready" | "failed"; view_id?: string; url?: string; devin_session_url?: string; note?: string; }

// ───────────────────────── Halo shell ⇄ view (window.postMessage) ─────────────────────────
export type ShellToView = { type: "seraph:state"; state: IncidentState } | { type: "seraph:alert"; alert: Alert };
export type ViewToShell = { type: "seraph:ready"; view_id: string } | { type: "seraph:tap"; target: { kind: "level" | "room" | "stair" | "entrance" | "team" | "occupant" | "hydrant"; id: string } };
