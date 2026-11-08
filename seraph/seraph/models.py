"""Pydantic mirror of contracts/types.ts (same field names). Enums are kept as plain strings on purpose:
the building JSON comes from another session (IFC extractor) and must never make Seraph crash on load."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class M(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)


# ───────── Common ─────────
class Source(M):
    kind: str
    label: str
    url: Optional[str] = None
    confirmed: bool = True
    at: str = Field(default_factory=now_iso)


class ImagePoint(M):
    image_id: str
    x: float
    y: float


class Screenshot(M):
    image_id: str
    url: str
    caption: str = ""
    side: Optional[str] = None
    width: int = 0
    height: int = 0
    taken_at: str = Field(default_factory=now_iso)


# ───────── Building ─────────
class Level(M):
    level: int
    label: str
    elevation_m: Optional[float] = None


class Stair(M):
    id: str
    label: str
    status: str = "unknown"            # clear | smoke | blocked | unknown
    source: Optional[Source] = None


class Entrance(M):
    id: str
    label: str
    side: str = "front"
    status: str = "unknown"            # usable | locked | blocked | unknown
    point: Optional[ImagePoint] = None
    source: Optional[Source] = None
    leads_to: Optional[str] = None     # graph node behind the door (fixture/IFC extra)


class Hydrant(M):
    id: str
    label: str
    distance_m: Optional[float] = None
    point: Optional[ImagePoint] = None
    source: Optional[Source] = None


class TruckSpot(M):
    label: str
    point: Optional[ImagePoint] = None
    source: Optional[Source] = None


class Room(M):
    id: str
    level: int
    label: str
    area_m2: Optional[float] = None
    use: Optional[str] = None
    zone: Optional[list[list[float]]] = None
    source: Optional[Source] = None


class PlanPoint(M):
    name: str
    label: str
    point: ImagePoint


class Plan(M):
    image_id: str
    url: str
    level: int
    points: list[PlanPoint] = []


class Hazard(M):
    id: str
    kind: str                          # smoke | fire | heat | gas | structure | electric
    where: dict[str, Any] = {}         # {level?, room?, stair?, entrance?}
    severity: str = "medium"           # low | medium | high
    source: Source
    reported_at: str = Field(default_factory=now_iso)


class Approach(M):
    best_entrance_id: str
    reason: str
    source: Source


class Door(M):
    id: str
    level: int
    label: str
    between: list[str]
    external: Optional[bool] = None
    fire_rating: Optional[str] = None
    source: Optional[Source] = None


class Material(M):
    element: str
    level: Optional[int] = None
    room: Optional[str] = None
    material: str
    fire_rating: Optional[str] = None
    source: Source


class Graph(M):
    nodes: list[str] = []
    edges: list[list[Any]] = []


class LevelPlan(M):
    level: int
    url: str
    image_id: str


class BuildingModel(M):
    provenance: str
    provenance_fr: str
    ifc_url: Optional[str] = None
    glb_url: Optional[str] = None
    level_plans: list[LevelPlan] = []
    stats: dict[str, int] = {}


class Building(M):
    name: str
    levels: list[Level] = []
    stairs: list[Stair] = []
    entrances: list[Entrance] = []
    hydrants: list[Hydrant] = []
    truck_spot: Optional[TruckSpot] = None
    rooms: list[Room] = []
    plan: Optional[Plan] = None
    hazards: list[Hazard] = []
    approach: Optional[Approach] = None
    screenshots: list[Screenshot] = []
    doors: Optional[list[Door]] = None
    materials: Optional[list[Material]] = None
    graph: Optional[Graph] = None
    model: Optional[BuildingModel] = None


# ───────── People, calls, crew ─────────
class Occupant(M):
    id: str
    name: Optional[str] = None
    phone_masked: Optional[str] = None
    level: Optional[int] = None
    room: Optional[str] = None
    people_count: Optional[int] = None
    status: str = "unknown"
    mobility_issue: Optional[bool] = None
    injuries: Optional[str] = None
    smoke_seen: Optional[bool] = None
    heading_to: Optional[str] = None
    language: Optional[str] = None
    last_update: str = Field(default_factory=now_iso)
    source: Source
    call_id: Optional[str] = None


class VoiceSignal(M):
    emotion: str = "neutral"
    sentiment: str = "unknown"
    text: str = ""
    at: str = Field(default_factory=now_iso)


class CallUrgency(M):
    level: int
    reasons_fr: list[str] = []
    raised_by_voice: bool = False
    computed_at: str = Field(default_factory=now_iso)


class Call(M):
    call_id: str
    direction: str = "out"
    occupant_id: Optional[str] = None
    number_masked: str = ""
    channel: str = "phone"
    status: str = "ringing"
    language: Optional[str] = None
    started_at: str = Field(default_factory=now_iso)
    ended_at: Optional[str] = None
    summary_fr: Optional[str] = None
    transcript_excerpt: Optional[str] = None
    voice: Optional[VoiceSignal] = None
    urgency: Optional[CallUrgency] = None


class TeamLocation(M):
    level: Optional[int] = None
    room: Optional[str] = None
    stair: Optional[str] = None


class Team(M):
    id: str
    label: str
    status: str = "standby"            # standby | engaged | exiting | out
    entered_at: Optional[str] = None
    pressure_bar_start: Optional[int] = None
    exit_by: Optional[str] = None
    location: Optional[TeamLocation] = None
    last_update: str = Field(default_factory=now_iso)


class Crew(M):
    teams: list[Team] = []


class Wind(M):
    dir_deg: float
    dir_label: str
    speed_kmh: float
    source: Source


class Risk(M):
    label: str
    category: str = ""
    detail: Optional[str] = None
    source: Source


class Environment(M):
    wind: Optional[Wind] = None
    risks: list[Risk] = []


class Route(M):
    id: str
    purpose: str                       # approach | to_victim | evacuation
    from_: str = Field(alias="from")
    to: str
    via: list[str] = []
    avoids: list[str] = []
    computed_at: str = Field(default_factory=now_iso)
    source: Source
    # Extra (requested by halo + dashboard, not yet in types.ts): the route on the plan's 0–1000 frame.
    path: Optional[list[list[float]]] = None
    path_image_id: Optional[str] = None
    path_level: Optional[int] = None


class Gate(M):
    gate_id: str
    kind: str                          # relay_order | reroute_occupant | send_report | learn_source
    summary_fr: str
    confirmer: str = "COS"
    status: str = "pending"
    created_at: str = Field(default_factory=now_iso)
    resolved_at: Optional[str] = None
    resolved_by: Optional[str] = None


class CurrentView(M):
    view_id: str
    url: str
    moment: str
    built_by: str                      # devin | fallback
    since: str = Field(default_factory=now_iso)


class ViewRequestStatus(M):
    request_id: str
    moment: str
    purpose_fr: str
    status: str = "requested"
    view_id: Optional[str] = None
    url: Optional[str] = None
    devin_session_url: Optional[str] = None
    requested_at: str = Field(default_factory=now_iso)
    ready_at: Optional[str] = None


class HaloStatus(M):
    current_view: Optional[CurrentView] = None
    requests: list[ViewRequestStatus] = []


class EndpointStatus(M):
    name: str
    kind: str
    verified: bool = True
    last_run_at: Optional[str] = None
    last_duration_ms: Optional[int] = None
    last_live: Optional[bool] = None
    status: str = "idle"


class RosettaCounter(M):
    sources_without_api: int = 0
    endpoints: int = 0


class RosettaStatus(M):
    endpoints: list[EndpointStatus] = []
    counter: RosettaCounter = RosettaCounter()


class TimelineEntry(M):
    t: str = Field(default_factory=now_iso)
    kind: str
    text_fr: str
    source: Optional[Source] = None


class Alert(M):
    alert_id: str
    level: str                         # info | warning | danger
    text_fr: str
    created_at: str = Field(default_factory=now_iso)
    spoken: bool = False


class Origin(M):
    floor: int
    room: Optional[str] = None


class Incident(M):
    id: str = "INC-0001"
    address: str = ""
    nature: str = ""
    origin: Optional[Origin] = None
    declared_at: Optional[str] = None
    status: str = "idle"
    exercise: bool = True


class IncidentState(M):
    incident: Incident = Incident()
    building: Building
    occupants: list[Occupant] = []
    calls: list[Call] = []
    crew: Crew = Crew()
    environment: Environment = Environment()
    routes: list[Route] = []
    gates: list[Gate] = []
    halo: HaloStatus = HaloStatus()
    rosetta: RosettaStatus = RosettaStatus()
    timeline: list[TimelineEntry] = []
    alerts: list[Alert] = []


def dump(model: BaseModel) -> dict[str, Any]:
    return model.model_dump(mode="json", by_alias=True)
