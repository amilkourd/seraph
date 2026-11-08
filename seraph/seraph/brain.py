"""Seraph's brain: input → event → state → rules → actions → stream. One instance, one asyncio loop, no locks.
Outbound IO is injected (app.py wires HTTP/WS; tests wire fixtures), so the logic runs the same everywhere."""
from __future__ import annotations

import json
from pathlib import Path
import os
import random
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

from . import building as B
from . import llm, rules, speech
from .config import REPO, settings
from .models import (
    Alert, Approach, Call, CallUrgency, CurrentView, EndpointStatus, Entrance, Gate, Hazard, Hydrant, ImagePoint, IncidentState,
    Occupant, Origin, Plan, PlanPoint, Risk, Room, Route, Screenshot, Source, Team, TeamLocation, TimelineEntry,
    TruckSpot, ViewRequestStatus, VoiceSignal, Wind, dump, now_iso,
)
from .registry import BuildingRegistry, default_registry, empty_kit
from .rules import Event, normalize, strip_accents
from .speech import addressed, cap, hhmm, level_fr, n_fr

ENDPOINTS = [  # name, kind — contracts/rosetta-endpoints.md
    ("dispatch.read", "replica"), ("maps.building", "real"), ("georisques.risks", "real"), ("weather.wind", "real"),
    ("plan.read", "real"), ("occupants.list", "replica"), ("dispatch.write_112", "replica"), ("report.fill", "replica"),
]
PRIORITY = {"dispatch": 0, "report": 0, "approach": 1, "inside_route": 2, "occupants": 3, "team_engaged": 4,
            "commander_request": 5}
JOINED = {"in_call", "sheltering", "moving", "needs_help", "safe_outside", "trapped"}
GATE_TTL_S = 120
NO_NEWS_S = 180
VOICE_RAISE = {"distress": "détresse", "fear": "peur", "pain": "douleur"}
KIND_FR = {"smoke": "fumée", "fire": "feu", "heat": "chaleur", "gas": "gaz", "structure": "risque structure",
           "electric": "risque électrique"}
STATUS_OCC_FR = {"unknown": "pas encore joint", "calling": "appel en cours", "in_call": "en ligne",
                 "no_answer": "sans réponse", "safe_outside": "dehors", "sheltering": "à l'abri",
                 "trapped": "bloqué", "moving": "en mouvement", "needs_help": "aide nécessaire"}
_B32 = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def ulid() -> str:
    t = int(time.time() * 1000)
    s = ""
    for _ in range(10):
        s = _B32[t % 32] + s
        t //= 32
    return s + "".join(random.choice(_B32) for _ in range(16))


def parse_iso(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def mask(phone: str) -> str:
    return phone[:5] + "•••••" + phone[-2:] if len(phone) > 7 else "•••"


def noop(*_a: Any, **_k: Any) -> None:
    return None


class Brain:
    def __init__(self, registry: Optional[BuildingRegistry] = None):
        self.registry: BuildingRegistry = registry or default_registry()
        # outbound, wired by app.py (or tests)
        self.publish: Callable[[str, dict], None] = noop          # SSE event
        self.send_gabriel: Callable[[dict], None] = noop          # SeraphToGabriel
        self.run_rosetta: Callable[[str, str, dict, int], None] = noop   # (run_id, endpoint, params, priority)
        self.explore: Callable[[str, str], None] = noop           # (run_id, question_fr)
        self.request_view_out: Callable[[dict], None] = noop      # ViewRequest
        self.learn_out: Callable[[dict], None] = noop             # silex /endpoints/learn body
        self.version = 0
        self.incident_t0 = 0.0
        self.say_log: list[dict] = []
        self.reset()

    # ───────── lifecycle ─────────
    def reset(self, address: str = "") -> None:
        try:
            kit = self.registry.lookup(address or settings.demo_address)
        except Exception as e:   # the registry never stops Seraph: no model = « pas de maquette »
            print("building registry lookup failed", repr(e))
            kit = None
        self.kit = kit or empty_kit()
        self.state = IncidentState(building=self.kit.building.model_copy(deep=True))
        self.state.rosetta.endpoints = [EndpointStatus(name=n, kind=k) for n, k in ENDPOINTS]
        self._count_endpoints()
        self.phones: dict[str, str] = {}
        self.gate_actions: dict[str, dict] = {}
        self.runs: dict[str, dict] = {}
        self.incident_t0 = time.time()
        self.call_facts: dict[str, dict] = {}
        self.call_flags: dict[str, dict] = {}
        self.no_answer_count: dict[str, int] = {}
        self.called_at: dict[str, float] = {}
        self.with_team: dict[str, str] = {}
        self.caught: set[str] = set()
        self.air_alarm: set[str] = set()
        self.standing_confirmed = False
        self.approach_say: Optional[str] = None
        self.approach_key: Optional[str] = None
        self.sitrep_say = ""
        self.last_call_id: Optional[str] = None
        self.occupants_loaded = False
        self.replay_mode = False
        self.mock_speed = 1.0
        self.hz_n = 0
        self.rt_n = 0
        self.req_n = 0
        self.al_n = 0
        self.recompute()
        self.touch()

    def touch(self) -> None:
        self.version += 1

    def snapshot(self) -> dict:
        return {"state": dump(self.state), "building_path": str(self.kit.path), "internal": {
            "phones": self.phones, "gate_actions": self.gate_actions, "call_facts": self.call_facts,
            "call_flags": self.call_flags, "no_answer_count": self.no_answer_count, "with_team": self.with_team,
            "caught": sorted(self.caught), "air_alarm": sorted(self.air_alarm),
            "standing_confirmed": self.standing_confirmed,
            "occupants_loaded": self.occupants_loaded, "counters": [self.hz_n, self.rt_n, self.req_n, self.al_n]}}

    def restore(self, snap: dict) -> bool:
        if snap.get("building_path") != str(self.kit.path):
            return False
        self.state = IncidentState.model_validate(snap["state"])
        i = snap.get("internal", {})
        self.phones = i.get("phones", {})
        self.gate_actions = i.get("gate_actions", {})
        self.call_facts = i.get("call_facts", {})
        self.call_flags = i.get("call_flags", {})
        self.no_answer_count = i.get("no_answer_count", {})
        self.with_team = i.get("with_team", {})
        self.caught = set(i.get("caught", []))
        self.air_alarm = set(i.get("air_alarm", []))
        self.standing_confirmed = i.get("standing_confirmed", False)
        self.occupants_loaded = i.get("occupants_loaded", False)
        self.hz_n, self.rt_n, self.req_n, self.al_n = i.get("counters", [0, 0, 0, 0])
        self.recompute()
        self.touch()
        return True

    # ───────── small helpers ─────────
    @property
    def b(self):
        return self.state.building

    def log(self, kind: str, text: str, source: Optional[Source] = None) -> None:
        e = TimelineEntry(kind=kind, text_fr=text, source=source)
        self.state.timeline.append(e)
        if len(self.state.timeline) > 400:
            self.state.timeline = self.state.timeline[-400:]
        self.publish("timeline", dump(e))
        self.touch()

    def alert(self, level: str, text: str, spoken: bool = True) -> Optional[Alert]:
        if any(a.text_fr == text for a in self.state.alerts):
            return None
        self.al_n += 1
        a = Alert(alert_id=f"al_{self.al_n:02d}", level=level, text_fr=text, spoken=spoken)
        self.state.alerts.append(a)
        self.publish("alert", dump(a))
        self.log("alert", text)
        return a

    def say(self, text: str, target: Optional[dict] = None, lang: str = "fr", priority: str = "normal",
            extra: Optional[dict] = None) -> dict:
        msg = {"kind": "say", "say_id": f"say_{ulid()}", "target": target or {"room": "crew"}, "text": text,
               "lang": lang, "priority": priority}
        if extra:
            msg.update(extra)
        self.send_gabriel(msg)
        self.publish("say", msg)
        self.say_log.append(msg)
        if "room" in msg["target"]:
            self.log("radio", f"Seraph : {text}", Source(kind="seraph", label="Seraph"))
        else:
            who = msg["target"].get("call_id") or ", ".join(msg["target"].get("call_ids", []))
            self.log("call", f"Seraph → {who} : {text}", Source(kind="seraph", label="Seraph"))
        return msg

    def metric(self, name: str, value_ms: float, **extra: Any) -> None:
        self.publish("metric", {"name": name, "value_ms": round(value_ms, 1), "at": now_iso(), **extra})

    def occ(self, occ_id: Optional[str]) -> Optional[Occupant]:
        return next((o for o in self.state.occupants if o.id == occ_id), None) if occ_id else None

    def call(self, call_id: str) -> Optional[Call]:
        return next((c for c in self.state.calls if c.call_id == call_id), None)

    def team(self, tid: str, create: bool = True) -> Optional[Team]:
        t = next((t for t in self.state.crew.teams if t.id == tid), None)
        if not t and create:
            t = Team(id=tid, label=f"Binôme {tid[1:]}" if tid.startswith("B") else tid)
            self.state.crew.teams.append(t)
        return t

    def stair_label(self, sid: str) -> str:
        return f"l'escalier {sid}"

    def _count_endpoints(self) -> None:
        eps = self.state.rosetta.endpoints
        self.state.rosetta.counter.endpoints = len(eps)
        self.state.rosetta.counter.sources_without_api = len(eps)

    # ───────── recompute (code, never a model) ─────────
    def recompute(self) -> None:
        hz = self.b.hazards
        for s in self.b.stairs:
            st = B.stair_status(self.kit, s.id, hz)
            s.status = st
            s.source = next((h.source for h in hz if h.where.get("stair") == s.id), s.source)
        res = B.choose_approach(self.kit, hz, self.b, self._approach_target()) if self.b.entrances else None
        if res:
            appr, detail = res
            self.b.approach = appr
            self.approach_say = self._approach_text(detail)
        self._routes()
        self._focus()
        self.sitrep_say = self._sitrep_text()

    def _focus(self) -> None:
        """Which levels matter now (the others are greyed on every plan). Code only, recomputed on every change."""
        why: dict[int, list[str]] = {}

        def add(level: Optional[int], reason: str) -> None:
            if level is None:
                return
            lst = why.setdefault(level, [])
            if reason not in lst:
                lst.append(reason)

        for h in self.b.hazards:
            if h.kind not in ("fire", "smoke"):
                continue
            lvl = h.where.get("level")
            if lvl is None and h.where.get("entrance"):
                e = next((x for x in self.b.entrances if x.id == h.where["entrance"]), None)
                lvl = (e.model_extra or {}).get("level", 0) if e else None
            if lvl is None and h.where.get("room"):
                lvl = B.room_level(self.kit, B.room_node(str(h.where["room"]), None))
            add(lvl, "feu" if h.kind == "fire" else "fumée")
        for o in self.state.occupants:
            attention = o.status in ("trapped", "needs_help", "no_answer") or (
                o.heading_to and o.id not in self.with_team and (self._node_hazard(o.heading_to) or o.heading_to.startswith("ladder:")))
            if attention:
                add(o.level, "personnes")
            if o.status != "safe_outside":
                add(o.level, "occupants")
        for t in self.state.crew.teams:
            if t.status == "engaged" and t.location and t.location.level is not None:
                add(t.location.level, t.id)
        for r in self.state.routes:
            add(B.room_level(self.kit, r.to) if r.to != "outside" else B.room_level(self.kit, r.from_), "cible")
        if self.state.incident.status in ("dispatched", "en_route") and self.b.approach:
            e = next((x for x in self.b.entrances if x.id == self.b.approach.best_entrance_id), None)
            if e:
                add((e.model_extra or {}).get("level", 0), "accès")
        for lv in self.b.levels:
            lv.focus_reasons = why.get(lv.level, [])
            lv.focus = bool(lv.focus_reasons)

    def _approach_target(self) -> Optional[str]:
        o = self.state.incident.origin
        return f"level:{o.floor}" if o else None

    def _approach_text(self, d: dict) -> str:
        best: Entrance = d["best"]
        lab = best.label[:1].lower() + best.label[1:]
        if len(self.b.stairs) == 1 and lab.endswith("escalier"):
            lab += f" {self.b.stairs[0].id}"
        parts = [f"entrée par {best.id}, {lab}"]
        lt = d.get("best_leads_to") or best.leads_to or ""
        single = len(self.b.stairs) == 1
        if lt.startswith("stair:") and not single:
            verb = "donne sur" if (best.leads_to or "").startswith("stair:") else "mène à"
            parts.append(f"elle {verb} l'escalier {lt[6:]}, {B.STATUS_FR.get(d['best_stair_status'] or 'unknown')}")
        hyd = None
        if self.b.hydrants:
            h = self.b.hydrants[0]
            hyd = f"hydrant à {int(h.distance_m)} mètres" if h.distance_m else f"hydrant : {h.label[:1].lower() + h.label[1:]}"
            if h.point and best.point and h.point.image_id == best.point.image_id:
                near = min((e for e in self.b.entrances if e.point and e.point.image_id == h.point.image_id),
                           key=lambda e: (e.point.x - h.point.x) ** 2 + (e.point.y - h.point.y) ** 2)
                if near.id == best.id:
                    hyd += f" devant {best.id}"
        for e, st in d["others"]:
            elt = d.get("others_leads_to", {}).get(e.id) or e.leads_to or ""
            if e.id in d.get("why_out", {}):
                parts.append(f"évitez {e.id}, {d['why_out'][e.id]}")
            elif elt.startswith("stair:") and st in ("smoke", "blocked") and len(self.b.stairs) > 1:
                parts.append(f"évitez {e.id}, escalier {elt[6:]} {B.STATUS_FR[st]}")
            elif e.status in ("blocked", "locked"):
                parts.append(f"évitez {e.id}, {'verrouillée' if e.status == 'locked' else 'bloquée'}")
        if single:
            st = self.b.stairs[0]
            o = self.state.incident.origin
            parts.append(f"seul escalier, {self._stair_fr(st)}" if st.status != "unknown" else f"seul escalier, {st.id}")
        if hyd:
            parts.append(hyd)
        return ". ".join(cap(p) if i else p for i, p in enumerate(parts)) + "."

    def _routes(self) -> None:
        if not self.kit.adj or self.state.incident.status == "idle":
            return
        wanted: list[tuple[str, str, str]] = []
        origin = self.state.incident.origin
        target_level = origin.floor if origin else None
        start = "truck" if "truck" in self.kit.adj else "outside"
        if target_level is not None and start in self.kit.adj and f"level:{target_level}" in self.kit.adj:
            wanted.append(("approach", start, f"level:{target_level}"))
        for r in self.state.routes:
            if r.purpose in ("to_victim", "evacuation"):
                wanted.append((r.purpose, r.from_, r.to))
        new: list[Route] = []
        seen = set()
        for purpose, src, dst in wanted:
            if (purpose, src, dst) in seen:
                continue
            seen.add((purpose, src, dst))
            res = B.shortest_path(self.kit, src, dst, self.b.hazards)
            if not res:
                continue
            path, avoided = res
            old = next((r for r in self.state.routes if (r.purpose, r.from_, r.to) == (purpose, src, dst)), None)
            if old and old.via == path and old.avoids == avoided:
                new.append(old)
                continue
            self.rt_n += 1 if not old else 0
            rid = old.id if old else f"RT-{self.rt_n}"
            r = Route(id=rid, purpose=purpose, **{"from": src}, to=dst, via=path, avoids=avoided,
                      source=Source(kind="seraph", label="calcul"))
            self._set_path(r)
            new.append(r)
        self.state.routes = new

    def add_route(self, purpose: str, src: str, dst: str) -> Optional[Route]:
        if not self.kit.adj:
            return None
        if not any((r.purpose, r.from_, r.to) == (purpose, src, dst) for r in self.state.routes):
            self.rt_n += 1
            self.state.routes.append(Route(id=f"RT-{self.rt_n}", purpose=purpose, **{"from": src}, to=dst,
                                           source=Source(kind="seraph", label="calcul")))
            # placeholder path recomputed right away
            self.state.routes[-1].via = []
        self._routes_force(purpose, src, dst)
        return next((r for r in self.state.routes if (r.purpose, r.from_, r.to) == (purpose, src, dst)), None)

    def _routes_force(self, purpose: str, src: str, dst: str) -> None:
        res = B.shortest_path(self.kit, src, dst, self.b.hazards)
        for r in self.state.routes:
            if (r.purpose, r.from_, r.to) == (purpose, src, dst):
                if not res:
                    self.state.routes.remove(r)
                    return
                r.via, r.avoids = res
                r.computed_at = now_iso()
                self._set_path(r)
                return

    def _set_path(self, r: Route) -> None:
        pp = B.plan_path(self.kit, r.via)
        if pp and len(pp[0]) >= 2:
            r.path, r.path_image_id, r.path_level = pp
        else:
            r.path = r.path_image_id = r.path_level = None

    def _sitrep_text(self) -> str:
        occs = self.state.occupants
        parts: list[str] = []
        if occs:
            joined = [o for o in occs if o.status in JOINED]
            no_ans = [o for o in occs if o.status == "no_answer"]
            waiting = len(occs) - len(joined) - len(no_ans)
            parts.append(f"{n_fr(len(occs))} occupants listés")
            p = f"{cap(n_fr(len(joined)))} joint{'s' if len(joined) > 1 else ''}"
            if no_ans:
                p += f", {n_fr(len(no_ans))} sans réponse, " + ", ".join(f"{o.name} {o.room or ''}".strip() for o in no_ans)
            if waiting:
                p += f", {n_fr(waiting)} en attente"
            parts.append(p)
        else:
            parts.append("aucun occupant listé")
        # urgent first: with a team, trapped, needs help, into smoke, sheltering in smoke
        groups: dict[tuple[str, str], int] = {}
        for o in occs:
            if o.id in self.with_team:
                k = (o.room or level_fr(o.level), self.with_team[o.id])
                groups[k] = groups.get(k, 0) + (o.people_count or 1)
        for (room, tid), n in groups.items():
            t = self.team(tid, create=False)
            parts.append(f"{n_fr(n, fem=True)} personne{'s' if n > 1 else ''} en {room} avec {(t.label if t else tid).lower()}")
        def rank(o: Occupant) -> tuple[int, int]:
            cat = 0 if o.status == "trapped" or o.mobility_issue or o.injuries else (1 if (o.heading_to or "").startswith("ladder:") else 2)
            return cat, -self._urgency_level(o)
        for o in sorted(occs, key=rank):
            if o.id in self.with_team:
                continue
            if o.status == "trapped":
                parts.append(f"{o.name} bloqué{'e' if False else ''} en {o.room or level_fr(o.level)}")
            elif o.mobility_issue or o.injuries:
                why = "en fauteuil" if self._wheelchair(o) else ("blessé" if o.injuries else "mobilité réduite")
                parts.append(f"{o.name} au {level_fr(o.level)} {why}, aide nécessaire")
            elif o.heading_to and o.heading_to.startswith("ladder:"):
                out = o.heading_to.split(":", 1)[1]
                parts.append(f"{o.name} au {level_fr(o.level)}, {B.room_word(self.kit, out)} {out}, échelle")
            elif o.heading_to and self._node_hazard(o.heading_to):
                parts.append(f"{o.name} vers {self._node_fr(o.heading_to)}, {self._node_hazard_fr(o.heading_to)}")
            elif o.smoke_seen and o.status == "sheltering":
                parts.append(f"{n_fr(o.people_count or 1, fem=True)} personne{'s' if (o.people_count or 1) > 1 else ''} en {o.room}, fumée sous la porte")
        for s in self.b.stairs:
            if s.status in ("smoke", "blocked"):
                parts.append(f"escalier {s.id} {self._stair_fr(s)}")
        for e in self.b.entrances:
            if e.status in ("blocked", "locked"):
                parts.append(f"entrée {e.id} {'verrouillée' if e.status == 'locked' else 'bloquée'}")
        return addressed("COS", ". ".join(cap(p) if i else p for i, p in enumerate(parts)) + ".")

    def _urgency_level(self, o: Occupant) -> int:
        c = self.call(o.call_id) if o.call_id else None
        return c.urgency.level if c and c.urgency else 0

    def _wheelchair(self, o: Occupant) -> bool:
        c = self.call(o.call_id) if o.call_id else None
        ex = normalize((c.transcript_excerpt or "") if c else "")
        return bool(re.search(r"fauteuil|wheelchair|silla de ruedas", ex))

    def _node_hazard(self, node: str) -> list[Hazard]:
        return [h for h in self.b.hazards if node in B.hazard_nodes(h)]

    def _node_fr(self, node: str) -> str:
        kind, _, nid = node.partition(":")
        return {"stair": f"l'escalier {nid}", "entrance": f"l'entrée {nid}", "exit": f"la sortie {nid}",
                "room": f"la salle {nid}"}.get(kind, node)

    def _node_hazard_fr(self, node: str) -> str:
        hz = self._node_hazard(node)
        if not hz:
            return ""
        h = next((x for x in hz if x.source.confirmed), hz[0])
        return f"{self._node_hazard_word(node)} {self._selon(h.source)}"

    def _node_hazard_word(self, node: str) -> str:
        hz = self._node_hazard(node)
        if not hz:
            return ""
        return {"smoke": "enfumé", "fire": "en feu"}.get(hz[0].kind, KIND_FR.get(hz[0].kind, hz[0].kind))

    def _stair_fr(self, s) -> str:
        if s.status in ("smoke", "blocked") and s.source is not None:
            return f"{B.STATUS_FR[s.status]} {self._selon(s.source)}"
        return B.STATUS_FR.get(s.status, s.status)

    # ───────── incident start ─────────
    def start_incident(self, incident_id: Optional[str] = None) -> None:
        inc = self.state.incident
        if inc.status not in ("idle", "closed"):
            return
        inc.id = incident_id or inc.id or "INC-0001"
        # look the building up again with the incident id (access log); swap it while still idle if it changed
        try:
            kit = self.registry.lookup(settings.demo_address or inc.address, incident_id=inc.id)
        except Exception as e:
            kit = None
            self.log("seraph", f"Registre des bâtiments indisponible ({type(e).__name__}).")
        if kit and str(kit.path) != str(self.kit.path):
            keep = self.state.incident
            self.kit = kit
            self.state = IncidentState(building=kit.building.model_copy(deep=True), incident=keep,
                                       rosetta=self.state.rosetta, timeline=self.state.timeline)
            inc = self.state.incident
        if not self.kit.adj:
            self.log("seraph", "Pas de maquette pour cette adresse : Rosetta et le plan affiché seulement.")
        inc.status = "dispatched"
        inc.declared_at = now_iso()
        self.incident_t0 = time.time()           # Rosetta results of runs started before this are stale
        inc.address = settings.demo_address or inc.address
        self.log("seraph", f"Incident {inc.id} déclenché (exercice).")
        self.show_moment("dispatch", explicit=True)
        self.rosetta("dispatch.read", {"incident_id": inc.id}, priority=10)
        self.open_gate("relay_order",
                       "Consigne par défaut aux occupants : si fumée dans l'escalier ou devant la porte, rester chez soi, porte fermée.",
                       {"standing": True},
                       addressed("COS", "consigne par défaut aux occupants : si fumée dans l'escalier ou devant la porte, rester chez soi, porte fermée. Confirmez ?"))
        self.touch()

    def _posted_plan(self, level: int) -> tuple[Path, int]:
        """The plan posted at the door. PLAN_IMAGE_PATH when it is set to a real photo; when it still points at the v1
        dev plan (or nothing) and the model has a level plan, the model's plan of the fire level (scenario v2: L-1)."""
        p = settings.plan_image_path
        if p.exists() and p.name != "plan-level3.svg":
            return p, level
        for base in (self.kit.files_dir, REPO / "ifc" / "out"):
            for lv in (level, 0):
                f = Path(base) / "levels" / f"L{lv}.svg"
                if str(base) not in ("", ".") and f.exists():
                    return f, lv
        return p, level

    # ───────── Rosetta ─────────
    def rosetta(self, endpoint: str, params: dict, priority: int = 5) -> str:
        run_id = f"run_{ulid()}"
        self.runs[run_id] = {"endpoint": endpoint, "params": params, "started": time.time(), "done": False,
                             "incident_id": self.state.incident.id, "incident_t0": self.incident_t0}
        self._endpoint_status(endpoint, status="running")
        self.run_rosetta(run_id, endpoint, params, priority)
        return run_id

    def _endpoint_status(self, name: str, **kw: Any) -> None:
        ep = next((e for e in self.state.rosetta.endpoints if e.name == name), None)
        if ep is None:
            return
        for k, v in kw.items():
            setattr(ep, k, v)
        self.touch()

    def on_rosetta_result(self, res: dict) -> None:
        ep_name = res.get("endpoint", "")
        run = self.runs.get(res.get("run_id", ""), {})
        stale = not run or run.get("incident_t0") != self.incident_t0 or run.get("incident_id") != self.state.incident.id
        out_id = (res.get("output") or {}).get("incident_id") if ep_name == "dispatch.read" else None
        if not stale and out_id and run.get("params", {}).get("incident_id") and out_id != run["params"]["incident_id"]:
            stale = True
        if stale:
            self.log("rosetta", f"Résultat périmé ignoré : {ep_name or 'Rosetta'} ({res.get('run_id', '?')}).")
            return
        self.publish("rosetta", res)
        status = res.get("status")
        if status in ("queued", "running"):
            self._endpoint_status(ep_name, status="running")
            return
        self._endpoint_status(ep_name, status="ok" if status == "ok" else "failed", last_run_at=res.get("ended_at") or now_iso(),
                              last_duration_ms=res.get("duration_ms"), last_live=res.get("live"))
        if run:
            if run.get("done") and status != "ok":
                return
            run["done"] = True
        live = "live" if res.get("live") else "cache"
        if ep_name and ep_name not in [e.name for e in self.state.rosetta.endpoints] and ep_name != "explore":
            self.state.rosetta.endpoints.append(EndpointStatus(name=ep_name, kind="learned", verified=False, status="ok"))
            self._count_endpoints()
        if res.get("duration_ms") is not None:
            self.metric(f"rosetta.{ep_name}", res["duration_ms"], live=bool(res.get("live")))
        if status != "ok":
            self.log("rosetta", f"Rosetta {ep_name} : échec ({res.get('error') or 'erreur'}).")
            if ep_name == "explore" or run.get("endpoint") == "explore":
                self.say(addressed("COS", "pas trouvé, exploration indisponible."))
            return
        out = res.get("output") or {}
        shots = [Screenshot.model_validate(s) for s in res.get("screenshots") or []]
        for s in shots:
            if not any(x.image_id == s.image_id for x in self.b.screenshots):
                self.b.screenshots.append(s)
        src = Source.model_validate(res["source"]) if res.get("source") else Source(kind="seraph", label="Rosetta")
        handler = getattr(self, "_r_" + (run.get("endpoint") or ep_name).replace(".", "_"), None)
        if handler:
            handler(out, src, shots, live, run)
        self.recompute()
        self.touch()

    def _r_dispatch_read(self, out: dict, src: Source, shots, live: str, run: dict) -> None:
        inc = self.state.incident
        src = Source(kind="dispatch", label="alerte", url=src.url, confirmed=False)   # what 112 callers said
        inc.source = dump(src)
        addr = out.get("address") or ""
        if addr in ("", "DEMO_ADDRESS"):
            addr = settings.demo_address or addr
        inc.address = addr
        inc.nature = out.get("nature") or inc.nature
        if out.get("level") is not None:
            inc.origin = Origin(floor=int(out["level"]), room=inc.origin.room if inc.origin else None)
        if out.get("incident_id"):
            inc.id = out["incident_id"]
        if inc.status == "idle":
            inc.status = "dispatched"
        for text in [inc.nature] + list(out.get("caller_notes") or []):   # the 112 callers' words → unconfirmed
            self._hazards_from_text(text, inc.origin.floor if inc.origin else None,
                                    Source(kind="dispatch", label="alerte", confirmed=False))
        fire = next((h for h in self.b.hazards if h.kind == "fire" and h.where.get("room")), None)
        if fire and inc.origin and fire.where.get("level") == inc.origin.floor:
            inc.origin.room = str(fire.where["room"])
        notes = "; ".join(out.get("caller_notes") or [])
        self.log("rosetta", f"Alerte lue ({live}) : {inc.nature}, {level_fr(inc.origin.floor if inc.origin else None)}. {notes}".strip(), src)
        params_addr = inc.address or settings.demo_address
        expected = [{"id": e.id, "label": e.label, "side": e.side} for e in self.b.entrances]
        self.rosetta("maps.building", {"address": params_addr, "expected_entrances": expected}, priority=8)
        img, lvl = self._posted_plan(inc.origin.floor if inc.origin else 0)
        self.rosetta("plan.read", {"image_path": str(img), "level": lvl}, priority=6)
        self.rosetta("georisques.risks", {"address": params_addr}, priority=4)
        self.rosetta("weather.wind", {"town": settings.demo_town}, priority=3)
        self.rosetta("occupants.list", {"building": self.b.name}, priority=7)

    def _r_maps_building(self, out: dict, src: Source, shots, live: str, run: dict) -> None:
        for e in out.get("entrances") or []:
            cur = next((x for x in self.b.entrances if x.id == e.get("id")), None)
            point = ImagePoint.model_validate(e["point"]) if e.get("point") else None
            if cur:
                cur.point = point or cur.point
                cur.side = e.get("side") or cur.side
                if cur.status == "unknown":
                    cur.status = "usable"
                cur.source = src
            else:
                ent = Entrance(id=e["id"], label=e.get("label", e["id"]), side=e.get("side", "front"), status="usable",
                               point=point, source=src)
                ent.leads_to = B._guess_leads_to(self.kit, ent)
                self.b.entrances.append(ent)
        for h in out.get("hydrants") or []:
            cur = next((x for x in self.b.hydrants if x.id == h.get("id")), None)
            point = ImagePoint.model_validate(h["point"]) if h.get("point") else None
            hsrc = src.model_copy(update={"kind": "streetview", "label": "Street View"})
            if cur:
                cur.point = point or cur.point
                cur.source = hsrc
                cur.distance_m = h.get("distance_m") or cur.distance_m
            else:
                self.b.hydrants.append(Hydrant(id=h["id"], label=h.get("label", h["id"]), distance_m=h.get("distance_m"),
                                               point=point, source=hsrc))
        fp = out.get("footprint")   # building outline on the top view, pointed by Holo (Rosetta); never drawn by Seraph
        if isinstance(fp, dict) and fp.get("polygon") and fp.get("image_id"):
            self.b.footprint = {"image_id": fp["image_id"], "polygon": fp["polygon"],
                                "source": dump(Source(kind="earth", label="Earth", url=src.url, confirmed=True))}
        ts = out.get("truck_spot")
        if ts:
            self.b.truck_spot = TruckSpot(label=ts.get("label", ""), point=ImagePoint.model_validate(ts["point"]) if ts.get("point") else None, source=src)
        obstacles = ", ".join(out.get("obstacles") or [])
        self.log("rosetta", f"Maps / Earth lu ({live}) : {len(out.get('entrances') or [])} entrées, {len(shots)} vues." + (f" Obstacles : {obstacles}." if obstacles else ""), src)
        self.recompute()
        if self.b.approach:
            key = self.b.approach.best_entrance_id
            if key != self.approach_key:
                self.approach_key = key
                self.log("seraph", f"Approche calculée : {self.b.approach.reason}", self.b.approach.source)
                if self.state.incident.status in ("dispatched", "en_route"):
                    self.state.incident.status = "en_route"
                self.say(addressed("Tête", self.approach_say or ""))
            det = (B.choose_approach(self.kit, self.b.hazards, self.b, self._approach_target()) or ({}, {"others": [], "why_out": {}}))[1]
            barred = [f", {e.id} barrée ({det['why_out'][e.id]})" for e, _ in det["others"] if e.id in det.get("why_out", {})]
            barred += [f", {e.id} barrée ({B.STATUS_FR.get(st or '', 'danger')})" for e, st in det["others"]
                       if st in ("smoke", "blocked") and e.id not in det.get("why_out", {}) and len(self.b.stairs) > 1]
            # a live result with screenshots the last request didn't carry → ask Devin again (Silex fetches the shots)
            sent = set()
            for r in self.state.halo.requests:
                if r.moment == "approach":
                    sent |= set(self.runs.get(r.request_id, {}).get("refs", []))
            new_shots = {s.image_id for s in shots if self._ref_for("approach", s)} - sent
            refresh = live == "live" and bool(new_shots) and any(r.moment == "approach" for r in self.state.halo.requests)
            self.request_moment("approach", f"Par où j'entre : bloc vu du dessus, rue, camion, flèche vers {key}, hydrant" + "".join(barred),
                                ["building.entrances", "building.approach", "building.hydrants", "building.truck_spot", "routes"],
                                deadline_s=300, refresh=refresh)

    def _r_plan_read(self, out: dict, src: Source, shots, live: str, run: dict) -> None:
        lvl = int(out.get("level", 0))
        img = out.get("image_id") or (shots[0].image_id if shots else "plan")
        url = next((s.url for s in shots if s.image_id == img), self.b.plan.url if self.b.plan else "")
        if self.b.model and self.kit.adj:
            # cross-check only: never merge the photo into the IFC; keep it only if it describes this building
            names = [n for n in (B.plan_name_to_node(p.get("name", ""), lvl) for p in out.get("points") or []) if n]
            missing = [n for n in names if n not in self.kit.adj]
            if missing:
                self.log("rosetta", f"Plan affiché ({live}) : {', '.join(m.split(':', 1)[1] for m in missing[:6])} pas dans la maquette.", src)
            if names and len(missing) * 2 > len(names):
                self.log("rosetta", "Plan affiché écarté : il ne correspond pas à la maquette IFC.", src)
                return
        self.b.plan = Plan(image_id=img, url=url, level=lvl,
                           points=[PlanPoint.model_validate(p) for p in out.get("points") or []])
        for z in out.get("zones") or []:
            node = B.plan_name_to_node(z["name"], lvl)
            if not node:
                continue
            if self.b.model:          # the IFC frame wins; the photo only cross-checks it (kept in building.plan)
                continue
            self.kit.zones[node] = B.Zone(node, lvl, z["polygon"], img)
            if node.startswith("room:") or node.startswith("corridor:"):
                rid = "corridor" if node.startswith("corridor:") else node[5:]
                room = next((r for r in self.b.rooms if r.id == rid and r.level == lvl), None)
                label = next((p.label for p in self.b.plan.points if p.name == z["name"]), rid)
                if room and not (self.b.model and room.zone):
                    room.zone = z["polygon"]
                    room.source = src
                elif not room:
                    self.b.rooms.append(Room(id=rid, level=lvl, label=label, zone=z["polygon"], source=src))
        for p in self.b.plan.points:
            node = B.plan_name_to_node(p.name, lvl)
            if node and not self.b.model:
                self.kit.points[node] = (p.point.x, p.point.y, p.point.image_id)
        names = ", ".join(p.label for p in self.b.plan.points[:6])
        self.log("rosetta", f"Plan niveau {lvl} lu ({live}) : {names}.", src)
        self._maybe_inside_route()

    def _r_georisques_risks(self, out: dict, src: Source, shots, live: str, run: dict) -> None:
        self.state.environment.risks = [Risk(label=r.get("label", ""), category=r.get("category", ""), detail=r.get("detail"), source=src)
                                        for r in out.get("risks") or []]
        self.log("rosetta", f"Géorisques lu ({live}) : " + (", ".join(r.label for r in self.state.environment.risks) or "aucun risque") + ".", src)

    def _r_weather_wind(self, out: dict, src: Source, shots, live: str, run: dict) -> None:
        if out.get("dir_label") is None:
            return
        self.state.environment.wind = Wind(dir_deg=out.get("dir_deg", 0), dir_label=out["dir_label"],
                                           speed_kmh=out.get("speed_kmh", 0), source=src)
        self.log("rosetta", f"Vent lu ({live}) : {out['dir_label']}, {out.get('speed_kmh')} km/h.", src)

    def _r_occupants_list(self, out: dict, src: Source, shots, live: str, run: dict) -> None:
        new_calls = []
        for o in out.get("occupants") or []:
            oid = o.get("id")
            if not oid:
                continue
            if o.get("phone_e164"):
                self.phones[oid] = o["phone_e164"]
            cur = self.occ(oid)
            if not cur:
                cur = Occupant(id=oid, name=o.get("name"), level=o.get("level"), room=o.get("room"),
                               language=o.get("language") or "fr", phone_masked=mask(o["phone_e164"]) if o.get("phone_e164") else None,
                               status="unknown", source=src)
                self.state.occupants.append(cur)
                if o.get("phone_e164"):
                    new_calls.append({"occupant_id": oid, "phone_e164": o["phone_e164"], "name": o.get("name"),
                                      "language_hint": o.get("language") or "fr"})
        self.occupants_loaded = True
        self.log("rosetta", f"Occupants lus ({live}) : {len(out.get('occupants') or [])} personnes. Accès journalisé, usage limité à l'incident.", src)
        if new_calls:
            self.place_calls(new_calls)

    def _r_dispatch_write_112(self, out: dict, src: Source, shots, live: str, run: dict) -> None:
        self.log("rosetta", f"Main courante : entrée {out.get('entry_id', '')} ajoutée ({live}).", src)

    def _r_report_fill(self, out: dict, src: Source, shots, live: str, run: dict) -> None:
        rid = out.get("report_id", "")
        self.log("rosetta", f"Compte rendu {rid} transmis ({live}).", src)
        self.state.incident.status = "closing"
        self.say(addressed("COS", f"rapport transmis, {rid}."))

    def _r_explore(self, out: dict, src: Source, shots, live: str, run: dict) -> None:
        ans = out.get("answer_fr") or out.get("answer") or ""
        q = run.get("params", {}).get("question_fr", "")
        if not ans:
            self.say(addressed("COS", "pas trouvé."))
            return
        self.say(addressed("COS", f"{ans.rstrip('.')}. Source non vérifiée."))
        self.open_gate("learn_source", f"Ajouter cette source à Seraph : « {q} » ?",
                       {"run_id": run.get("run_id") or res_run_id(run), "question_fr": q,
                        "name_hint": out.get("name_hint") or "learned.source"},
                       addressed("COS", "ajouter cette source à Seraph ? Confirmez ?"))

    # ───────── Gabriel: calls ─────────
    def place_calls(self, calls: list[dict]) -> None:
        # status and the 3-min « sans nouvelles » timer start on Gabriel's call_event (ringing), not here: a call
        # nobody dialed yet (web calls only, SIP off) is « en attente », never « sans nouvelles »
        self.send_gabriel({"kind": "place_calls", "calls": calls})
        self.publish("calls_placed", {"count": len(calls), "occupant_ids": [c["occupant_id"] for c in calls]})
        self.log("call", f"Gabriel appelle {len(calls)} occupant{'s' if len(calls) > 1 else ''}.")

    def on_call_event(self, msg: dict) -> None:
        cid = msg["call_id"]
        c = self.call(cid)
        if not c:
            c = Call(call_id=cid, direction=msg.get("direction", "out"), occupant_id=msg.get("occupant_id"),
                     number_masked=msg.get("number_masked", ""), channel=msg.get("channel", "phone"),
                     language=msg.get("lang"), started_at=msg.get("at") or now_iso())
            self.state.calls.append(c)
        ev = msg.get("event")
        c.status = {"ringing": "ringing", "answered": "active", "ended": "ended", "no_answer": "no_answer",
                    "failed": "failed"}.get(ev, c.status)
        if ev in ("ended", "no_answer", "failed"):
            c.ended_at = msg.get("at") or now_iso()
        if ev in ("ringing", "answered"):
            c.ended_at = None
        o = self.occ(c.occupant_id)
        if o and ev == "ringing":
            self.called_at.setdefault(o.id, time.time())
        if o:
            o.call_id = cid
            o.last_update = now_iso()
            if ev == "ringing" and o.status in ("unknown", "no_answer"):
                o.status = "calling"
            elif ev == "answered" and o.status in ("unknown", "calling", "no_answer"):
                o.status = "in_call"
            elif ev in ("no_answer", "failed") and o.status in ("unknown", "calling"):
                o.status = "no_answer"
        if ev in ("no_answer", "failed") and o:
            n = self.no_answer_count.get(o.id, 0) + 1
            self.no_answer_count[o.id] = n
            if n == 1 and o.id in self.phones:
                self.place_calls([{"occupant_id": o.id, "phone_e164": self.phones[o.id], "name": o.name,
                                   "language_hint": o.language or "fr"}])
            elif n >= 2:
                self._no_news(o)
        if ev == "answered":
            self.log("call", f"Appel {c.call_id} décroché" + (f" : {o.name}" if o else " (112)") + ".")
        self._urgency(c)
        self.publish("call", dump(c))
        self.recompute()
        self.touch()

    def _no_news(self, o: Occupant) -> None:
        if f"nonews:{o.id}" in self.caught:
            return
        self.caught.add(f"nonews:{o.id}")
        where = o.room or level_fr(o.level)
        self.alert("warning", f"Sans nouvelles : {o.name}, {where}")
        self.say(f"{o.name}, {where} : pas de réponse.")

    def on_call_facts(self, msg: dict) -> None:
        t0 = time.perf_counter()
        cid = msg["call_id"]
        c = self.call(cid)
        if not c:
            c = Call(call_id=cid, direction="in" if not msg.get("occupant_id") else "out", occupant_id=msg.get("occupant_id"),
                     status="active", language=msg.get("lang"))
            self.state.calls.append(c)
        if c.status in ("ringing", "no_answer"):
            c.status = "active"
        c.language = msg.get("lang") or c.language
        f_new = {k: v for k, v in (msg.get("facts") or {}).items() if v is not None}
        if "room" in f_new:
            # a room as heard is checked against the model: « 2.1 » → 2.01; anything else never overwrites a known room
            o0 = self.occ(msg.get("occupant_id") or c.occupant_id)
            lvl = f_new.get("level", o0.level if o0 else None)
            heard = f_new.pop("room")
            rid = B.resolve_room(self.kit, heard, lvl)
            if rid:
                f_new["room"] = rid
                self.call_flags.setdefault(cid, {}).pop("room_unconfirmed", None)
            else:
                self.call_flags.setdefault(cid, {})["room_unconfirmed"] = str(heard)
                self.log("call", f"Appel {cid} : pièce « {heard} » pas dans la maquette, à confirmer.")
        facts = self.call_facts.setdefault(cid, {})
        facts.update({k: v for k, v in f_new.items() if k != "voice"})
        if f_new.get("voice"):
            v = VoiceSignal.model_validate(f_new["voice"])
            c.voice = v
            if v.emotion in VOICE_RAISE and v.sentiment in ("negative", "mixed"):
                self.call_flags.setdefault(cid, {})["voice"] = v.emotion
        if msg.get("transcript_excerpt"):
            c.transcript_excerpt = msg["transcript_excerpt"]
        o = self.occ(msg.get("occupant_id") or c.occupant_id)
        if o:
            c.occupant_id = o.id
            o.call_id = cid
            self._facts_to_occupant(o, facts, c)
        self.last_call_id = cid
        self._call_hazards(c, o, f_new, facts)
        self._urgency(c)
        self.recompute()
        line, gate = self._call_catches(c, o, facts)
        summary = self._call_summary(c, o, facts)
        changed = summary != c.summary_fr
        c.summary_fr = summary
        if changed and not gate and summary:
            self.say(line or summary)
            self.metric("call_fact_to_crew", (time.perf_counter() - t0) * 1000, call_id=cid)
            self.rosetta("dispatch.write_112", {"incident_id": self.state.incident.id,
                                                "entry_fr": f"{hhmm(now_iso())} {summary}"}, priority=2)
        elif gate:
            self.metric("call_fact_to_crew", (time.perf_counter() - t0) * 1000, call_id=cid)
            self.rosetta("dispatch.write_112", {"incident_id": self.state.incident.id,
                                                "entry_fr": f"{hhmm(now_iso())} {summary}"}, priority=2)
        self._standing_for(c, facts)
        if sum(1 for k in self.call_facts if self.call_facts[k]) >= 2:
            self.request_moment("occupants", "Qui est où : étages, personnes, aide nécessaire, sans nouvelles",
                                ["occupants", "calls", "building.levels", "building.hazards", "building.rooms",
                                 "building.model.ladder_points", "routes"], deadline_s=300)
        self.publish("call", dump(c))
        self.touch()

    def _call_hazards(self, c: Call, o: Optional[Occupant], f_new: dict, f: dict) -> None:
        """What a caller says they see becomes a hazard « selon l'appel », unconfirmed, at the place they say."""
        if not (f_new.get("smoke_seen") or f_new.get("fire_seen")):
            return
        kind = "fire" if f_new.get("fire_seen") else "smoke"
        src = Source(kind="call", label=f"appel {o.name}" if o and o.name else ("appel 112" if c.direction == "in" else f"appel {c.call_id}"),
                     confirmed=False)
        heading = f.get("heading_to") or ""
        if f.get("current_action") == "moving" and heading.startswith("stair:"):
            self._add_hazard(kind, {"stair": heading.split(":", 1)[1]}, "medium", src)   # sees it on the way down
            return
        if f.get("free_text_fr") and self._hazards_from_text(f["free_text_fr"], f.get("level"), src):
            return
        lvl = f.get("level", o.level if o else None)
        if lvl is not None and f.get("current_action") != "outside":
            self._add_hazard(kind, {"level": lvl}, "medium" if kind == "smoke" else "high", src)

    def _facts_to_occupant(self, o: Occupant, f: dict, c: Call) -> None:
        for k in ("level", "room", "people_count", "smoke_seen", "mobility_issue", "injuries", "heading_to"):
            if f.get(k) is not None:
                setattr(o, k, f[k])
        act = f.get("current_action")
        if f.get("mobility_issue") or f.get("injuries"):
            o.status = "needs_help"
        elif act == "outside":
            o.status = "safe_outside"
        elif act == "moving":
            o.status = "moving"
        elif act == "staying":
            o.status = "sheltering"
        elif o.status in ("unknown", "calling", "no_answer"):
            o.status = "in_call"
        o.language = c.language or o.language
        o.last_update = now_iso()
        o.source = Source(kind="call", label=f"appel {o.name or c.call_id}", confirmed=False)   # signalé until the crew says it

    def _urgency(self, c: Call) -> None:
        f = self.call_facts.get(c.call_id, {})
        o = self.occ(c.occupant_id)
        reasons: list[str] = []
        lvl = 2
        outside = f.get("current_action") == "outside" or (o and o.status == "safe_outside")
        heading = f.get("heading_to") or (o.heading_to if o else None)
        fire_floor = self.state.incident.origin.floor if self.state.incident.origin else None
        excerpt = normalize(c.transcript_excerpt or "")
        level = f.get("level", o.level if o else None)
        if c.status == "no_answer" and not f:
            if o and o.level is not None and o.level == fire_floor:
                lvl, reasons = 3, ["sans nouvelles, étage du feu"]
            else:
                lvl, reasons = 2, ["sans nouvelles"]
        elif outside:
            lvl, reasons = 1, ["dehors"]
        else:
            if f.get("mobility_issue"):
                lvl = 3
                reasons.append("fauteuil roulant" + (", ne peut pas descendre seule" if "seule" in excerpt else "")
                               if re.search(r"fauteuil|wheelchair|silla", excerpt) else "mobilité réduite")
            if f.get("injuries"):
                lvl = 3
                reasons.append(f"blessure : {f['injuries']}")
            if o and o.status == "trapped":
                lvl = 3
                reasons.append("bloqué")
            if heading and self._node_hazard(heading):
                lvl = 3
                reasons.append(f"descend vers {self._node_fr(heading)}, {self._node_hazard_word(heading)}")
            if f.get("smoke_seen") or f.get("fire_seen"):
                lvl = 3
                reasons.append("fumée sous la porte" if re.search(r"porte|door|puerta", excerpt) else
                               ("feu signalé" if f.get("fire_seen") else "fumée signalée"))
            if lvl == 2:
                reasons.append(f"{level_fr(level)}, pas de fumée" if f.get("smoke_seen") is False else
                               ("dans le bâtiment" if level is None else f"{level_fr(level)}, à suivre"))
        raised = False
        emo = self.call_flags.get(c.call_id, {}).get("voice")
        if emo:
            reasons.append(f"{VOICE_RAISE[emo]} dans la voix")
            if lvl < 3:
                lvl += 1
                raised = True
        c.urgency = CallUrgency(level=lvl, reasons_fr=reasons, raised_by_voice=raised)

    def _call_summary(self, c: Call, o: Optional[Occupant], f: dict) -> str:
        if not any(k not in ("confidence", "voice") for k in f):
            return c.summary_fr or ""
        who = f"Appel {o.name}" if o and o.name else ("Appel 112" if c.direction == "in" else f"Appel {c.call_id}")
        if c.language and c.language != "fr":
            who += f", {speech.LANG_FR.get(c.language, c.language)}"
        ex = normalize(c.transcript_excerpt or "")
        bits: list[str] = []
        act = f.get("current_action")
        if act == "outside" and not o:
            if f.get("free_text_fr"):
                return f"{who} : {f['free_text_fr'].rstrip('.')}."
            who += ", témoin dehors"
        pc = f.get("people_count")
        room = f.get("room") or (o.room if o and f.get("level") is not None and f.get("level") == o.level and act != "moving" else None)
        level = f.get("level")
        unconfirmed = self.call_flags.get(c.call_id, {}).get("room_unconfirmed") and not f.get("room")
        if unconfirmed and not room:
            room = None
        if pc and pc > 1:
            bits.append(f"{n_fr(pc, fem=True)} personnes" + (f" {B.room_word(self.kit, room)} {room}" if room else (" pièce à confirmer" if unconfirmed else "")))
            if level is not None and not room:
                bits[-1] += f" au {level_fr(level)}"
        else:
            if level is not None:
                bits.append(level_fr(level))
            if room:
                bits.append(f"{B.room_word(self.kit, room)} {room}")
            elif unconfirmed:
                bits.append("pièce à confirmer")
        if f.get("mobility_issue"):
            bits.append("en fauteuil, ne peut pas descendre seule" if re.search(r"fauteuil|wheelchair|silla", ex) and "seule" in ex
                        else ("en fauteuil" if re.search(r"fauteuil|wheelchair|silla", ex) else "mobilité réduite"))
        if f.get("injuries"):
            bits.append(f"blessé : {f['injuries']}")
        if f.get("smoke_seen"):
            bits.append("fumée sous la porte" if re.search(r"porte|door|puerta", ex) else "fumée signalée")
        elif f.get("smoke_seen") is False and not f.get("mobility_issue"):
            bits.append("pas de fumée")
        if f.get("fire_seen"):
            bits.append("feu visible")
        if act == "moving" and f.get("heading_to"):
            bits.append(f"descend par {self._node_fr(f['heading_to'])}")
        asks = re.search(r"que faire|qu est ce que je fais|what should i do|what do i do|que tengo que hacer|que hago", ex)
        if act == "staying" and not f.get("mobility_issue") and not asks:
            bits.append("reste sur place" if not pc or pc == 1 else "restent sur place")
        elif act == "outside":
            bits.append("dehors")
        if f.get("free_text_fr") and o:
            bits.append(f["free_text_fr"].rstrip("."))
        s = f"{who} : {', '.join(bits)}" if bits else who
        if f.get("mobility_issue") or f.get("injuries"):
            s += ". Aide nécessaire"
        if asks:
            s += ", demande quoi faire. Consigne ?"
            return s
        return s + "."

    def _call_catches(self, c: Call, o: Optional[Occupant], f: dict) -> tuple[Optional[str], bool]:
        if not o:
            return None, False
        if o.id in self.with_team:      # with a team: the team decides on the spot, no « heading into smoke »
            return None, False
        gate = False
        heading = f.get("heading_to")
        if heading and self._node_hazard(heading) and f"reroute:{o.id}:{heading}" not in self.caught:
            alt = self._alt_stair(heading)
            if not alt and heading.startswith("stair:"):
                # single stair (TU Wien): no other stair to give → stay home, door closed, and the flat's
                # balcony / terrace (ladder point, chosen by code). The COS decides.
                self.caught.add(f"reroute:{o.id}:{heading}")
                frm = heading.split(":", 1)[1]
                lvl = level_fr(o.level if f.get('level') is None else f['level'])
                lad = B.ladder_for(self.kit, o.room, self.b.hazards)
                head = f"{o.name}, {lvl}, descend par l'escalier {frm}, {self._node_hazard_fr(heading)}" + \
                       (", seul escalier" if len(self.b.stairs) == 1 else ", pas d'autre escalier")
                if lad:
                    word = B.room_word(self.kit, lad[1])
                    kind = "terrasse" if "terrasse" in normalize(word) else "balcon"
                    art = "la" if kind == "terrasse" else "le"
                    summary = f"{head}. Je lui dis de rester dans son logement, porte fermée, et d'aller sur {art} {kind} ?"
                else:
                    kind = None
                    summary = f"{head}. Je lui dis de rester dans son logement, porte fermée ?"
                self.open_gate("reroute_occupant", summary,
                               {"occupant_id": o.id, "call_id": c.call_id, "shelter": True, "from": frm,
                                "ladder": lad[0] if lad else None, "outdoor": lad[1] if lad else None,
                                "outdoor_kind": kind, "lang": c.language or o.language or "fr"},
                               addressed("COS", summary))
                gate = True
            if alt:
                self.caught.add(f"reroute:{o.id}:{heading}")
                frm = heading.split(":", 1)[1]
                summary = f"{o.name}, {level_fr(o.level if f.get('level') is None else f['level'])}, descend par l'escalier {frm}. {frm} est {self._node_hazard_fr(heading)}. Je lui dis de prendre l'escalier {alt} ?"
                self.open_gate("reroute_occupant", summary,
                               {"occupant_id": o.id, "call_id": c.call_id, "to": alt, "from": frm, "lang": c.language or o.language or "fr"},
                               addressed("COS", summary))
                gate = True
        if (f.get("mobility_issue") or f.get("injuries")) and f"help:{o.id}" not in self.caught:
            self.caught.add(f"help:{o.id}")
            what = "Personne à mobilité réduite" if f.get("mobility_issue") else "Blessé"
            self.alert("warning", f"{what} au {level_fr(o.level)} ({o.room or '?'})")
        return None, gate

    def _alt_stair(self, node: str) -> Optional[str]:
        if not node.startswith("stair:"):
            return None
        bad = node.split(":", 1)[1]
        for s in self.b.stairs:
            if s.id != bad and s.status == "clear":
                return s.id
        for s in self.b.stairs:
            if s.id != bad and s.status == "unknown":
                return s.id
        return None

    def _standing_for(self, c: Call, f: dict) -> None:
        if not self.standing_confirmed or not f.get("smoke_seen") or f.get("current_action") not in ("staying", None):
            return
        if f.get("current_action") is None and not f.get("room"):
            return
        flags = self.call_flags.setdefault(c.call_id, {})
        if flags.get("standing_said"):
            return
        flags["standing_said"] = True
        lang = c.language or "fr"
        self.say(speech.standing_text(lang), target={"call_id": c.call_id}, lang=lang)

    # ───────── gates ─────────
    def open_gate(self, kind: str, summary: str, action: dict, say_text: str) -> Gate:
        g = Gate(gate_id=f"gate_{ulid()}", kind=kind, summary_fr=summary)
        self.state.gates.append(g)
        self.gate_actions[g.gate_id] = action
        self.publish("gate", dump(g))
        self.log("gate", f"Proposition : {summary}")
        self.say(say_text, priority="alert")
        return g

    def pending_gate(self) -> Optional[Gate]:
        pend = [g for g in self.state.gates if g.status == "pending"]
        return pend[-1] if pend else None

    def resolve_gate(self, gate_id: Optional[str], confirm: bool, by: str) -> Optional[Gate]:
        g = next((x for x in self.state.gates if x.gate_id == gate_id), None) if gate_id else self.pending_gate()
        if not g or g.status != "pending":
            return None
        g.status = "confirmed" if confirm else "cancelled"
        g.resolved_at = now_iso()
        g.resolved_by = by
        self.publish("gate", dump(g))
        self.log("gate", f"{'Confirmé' if confirm else 'Annulé'} par le COS ({'voix' if by == 'voice' else 'tableau'}) : {g.summary_fr}")
        action = self.gate_actions.get(g.gate_id, {})
        if confirm:
            getattr(self, f"_do_{g.kind}")(g, action)
        else:
            self.say("Reçu, annulé.")
        self.recompute()
        self.touch()
        return g

    def _do_relay_order(self, g: Gate, a: dict) -> None:
        if a.get("standing"):
            self.standing_confirmed = True
            self.say("Reçu, consigne par défaut active.")
            for c in self.state.calls:
                if c.status == "active":
                    self._standing_for(c, self.call_facts.get(c.call_id, {}))
            return
        if a.get("lift"):
            self.standing_confirmed = False      # stay put lifted: new callers no longer hear it
            self.log("seraph", "Levée du confinement confirmée par le COS.")
        for t in a.get("targets", []):
            self.say(t["text"], target={"call_id": t["call_id"]}, lang=t["lang"],
                     extra={"text_fr": t["text_fr"], "translate": t["lang"] != "fr" and not t.get("translated")} if t["lang"] != "fr" else None)
        self.say(f"Reçu, transmis à {a.get('who_fr', 'eux')}.")

    def _do_reroute_occupant(self, g: Gate, a: dict) -> None:
        lang = a.get("lang", "fr")
        if a.get("shelter"):
            o = self.occ(a["occupant_id"])
            if a.get("ladder"):
                self.say(speech.stay_outdoor_text(lang, a.get("outdoor_kind") or "balcon"), target={"call_id": a["call_id"]}, lang=lang)
            else:
                self.say(speech.standing_text(lang), target={"call_id": a["call_id"]}, lang=lang)
            if o:
                o.heading_to = a.get("ladder")
                o.status = "sheltering"
                o.last_update = now_iso()
                f = self.call_facts.get(a["call_id"])
                if f is not None:
                    f["heading_to"] = a.get("ladder")
                    f["current_action"] = "staying"
                c = self.call(a["call_id"])
                if c:
                    self._urgency(c)
                    self.publish("call", dump(c))
            if a.get("ladder") and o:
                if o.room:
                    self.add_route("evacuation", B.room_node(o.room, o.level), a["ladder"])
                out = a.get("outdoor")
                word = B.room_word(self.kit, out)
                self.alert("warning", f"Échelle : {word} {out}, {level_fr(o.level)}, {o.name}")
                self.say(f"Reçu. {o.name} reste dans son logement, {word} {out} : point échelle.")
            else:
                self.say("Reçu, je lui dis de rester dans son logement, porte fermée.")
            return
        self.say(speech.reroute_text(lang, a["to"], a["from"]), target={"call_id": a["call_id"]}, lang=lang)
        o = self.occ(a["occupant_id"])
        if o:
            o.heading_to = f"stair:{a['to']}"
            o.last_update = now_iso()
            f = self.call_facts.get(a["call_id"])
            if f is not None:
                f["heading_to"] = o.heading_to
            c = self.call(a["call_id"])
            if c:
                self._urgency(c)
                self.publish("call", dump(c))
        self.say(f"Reçu, je lui dis de prendre l'escalier {a['to']}.")

    def _do_send_report(self, g: Gate, a: dict) -> None:
        self.rosetta("report.fill", {"incident_id": self.state.incident.id, "gate_id": g.gate_id,
                                     "sections": a.get("sections") or self.report_sections()}, priority=9)
        self.say("Reçu, envoi du rapport en cours.")

    def _do_learn_source(self, g: Gate, a: dict) -> None:
        self.learn_out({"run_id": a.get("run_id"), "name_hint": a.get("name_hint"), "question_fr": a.get("question_fr")})
        self.say("Reçu, Devin compile la source.")

    # ───────── radio ─────────
    async def on_radio(self, msg: dict) -> dict:
        t0 = time.perf_counter()
        text = msg.get("text_fr") or msg.get("text") or ""
        speaker = msg.get("speaker") or ""
        self.publish("radio", msg)
        self.log("radio", f"{speaker} : {text}", Source(kind="radio", label=speaker or "radio"))
        p = rules.parse(text, speaker)
        path = p.path
        t1 = time.perf_counter()
        if p.path == "none" and p.to_seraph and settings.llm_enabled:
            ev = await llm.extract(text, speaker, [e.text_fr for e in self.state.timeline[-10:]])
            if ev and ev.get("type") not in ("confirm", "cancel"):
                p.events = [self._llm_event(ev, p)]
                path = "llm"
        t2 = time.perf_counter()
        self._status_from_radio(p.body)
        n_says = len(self.say_log)
        reply = None
        for i, e in enumerate(p.events):
            r = self.handle(e, p, speaker)
            if i == 0 and r:
                reply = r
        if p.events and p.events[0].type == "hazard":
            parts = [e.data["_part"] for e in p.events if e.type == "hazard" and e.data.get("_part")
                     and not e.data.get("secondary") and not e.data.get("silent") and not e.data.get("entrance_status")]
            if parts:
                reply = f"Reçu, {' et '.join(parts)}, selon {speech.dest_fr(speaker)}."
        if reply is None and p.path == "none" and p.to_seraph and len(self.say_log) == n_says:
            reply = "Reçu."
        if reply:
            self.say(reply)
        t3 = time.perf_counter()
        said = self.say_log[n_says:]
        if said:
            from_eot = None
            if msg.get("end"):
                try:
                    from_eot = (datetime.now(timezone.utc) - parse_iso(msg["end"])).total_seconds() * 1000
                except ValueError:
                    pass
            self.metric("voice_to_say", (t3 - t0) * 1000, path=path,
                        stages={"rules_ms" if path != "llm" else "llm_ms": round(((t1 - t0) if path != "llm" else (t2 - t1)) * 1000, 2),
                                "compute_ms": round((t3 - t2) * 1000, 2), "queue_ms": 0.0},
                        since_eot_ms=round(from_eot, 1) if from_eot is not None and 0 <= from_eot < 600000 else None,
                        utterance_id=msg.get("utterance_id"))
        self.recompute()
        self.touch()
        return {"events": [{"type": e.type, **e.data} for e in p.events], "path": path,
                "says": said, "ms": round((t3 - t0) * 1000, 2)}

    def _status_from_radio(self, body: str) -> None:
        inc = self.state.incident
        if inc.status in ("dispatched", "en_route") and re.search(r"\b(sur place|on arrive|arrives?|sur les lieux)\b", body):
            inc.status = "on_scene"
        elif inc.status == "dispatched" and re.search(r"\b(en route|a \w+ minutes?|on part)\b", body):
            inc.status = "en_route"

    def _llm_event(self, ev: dict, p: rules.Parsed) -> Event:
        t = ev.pop("type")
        if t == "hazard":
            return Event("hazard", {"hazard": {"kind": ev.get("kind", "smoke"), "where": ev.get("where") or {},
                                               "severity": ev.get("severity", "medium")}, "side": None, "llm": True})
        if t == "team_update":
            team = ev.get("team") or {}
            if not team.get("id") or not (team.get("status") or team.get("pressure_bar_start") or team.get("location")):
                return Event("chatter")
            return Event("team_update", {"team": team, "target_room": None, "llm": True})
        if t == "view_request":
            return Event("view_request", {"moment": None, "switch": False, "purpose_fr": ev.get("purpose_fr") or "Demande du COS"})
        if t == "order_to_occupants":
            return Event("order_to_occupants", {"target_text": normalize(ev.get("target_text", "")),
                                                "order_norm": normalize(ev.get("order_fr", "")), "raw": ev.get("order_fr", "")})
        if t == "question":
            return Event("question", {"topic": ev.get("topic") or "unknown_source", "question_fr": p.body_raw})
        return Event(t, {k: v for k, v in ev.items()})

    def handle(self, e: Event, p: rules.Parsed, speaker: str) -> Optional[str]:
        dest = speech.dest_fr(speaker)
        silent = e.data.get("silent") or e.data.get("secondary")
        fn = getattr(self, f"_e_{e.type}", None)
        if not fn:
            return None
        r = fn(e.data, p, dest)
        return None if silent else r

    def _e_chatter(self, d: dict, p, dest: str) -> Optional[str]:
        return None

    def _e_confirm(self, d: dict, p, dest: str) -> Optional[str]:
        g = self.resolve_gate(None, True, "voice")
        return None if g else "Rien à confirmer."

    def _e_cancel(self, d: dict, p, dest: str) -> Optional[str]:
        g = self.resolve_gate(None, False, "voice")
        return None if g else "Rien à annuler."

    def _e_sitrep_request(self, d: dict, p, dest: str) -> Optional[str]:
        self.sitrep_say = self._sitrep_text()
        return self.sitrep_say.replace("COS de Seraph", f"{dest} de Seraph", 1)

    def _e_report_request(self, d: dict, p, dest: str) -> Optional[str]:
        sections = self.report_sections()
        self.open_gate("send_report", "Rapport prêt (chronologie, moyens, victimes, observations). Envoi dans le logiciel de compte rendu.",
                       {"sections": sections}, addressed("COS", "rapport prêt, confirmez l'envoi."))
        return None

    def _e_hazard(self, d: dict, p, dest: str) -> Optional[str]:
        h = d["hazard"]
        where = {k: v for k, v in (h.get("where") or {}).items() if v is not None}
        if not any(k in where for k in ("room", "stair", "entrance")):
            where = self._resolve_where(d.get("clause") or normalize(p.body), where, where.get("level"))
        if self.kit.adj:   # an id the building doesn't have is a mishearing: keep the level, say it is not in the model
            for key, node in (("room", B.room_node(str(where.get("room", "")), where.get("level")) if where.get("room") else None),
                              ("stair", f"stair:{where['stair']}" if where.get("stair") else None),
                              ("entrance", f"entrance:{where['entrance']}" if where.get("entrance") else None)):
                if node and node not in self.kit.adj and not node.startswith("corridor"):
                    self.log("seraph", f"{node.split(':', 1)[1]} pas dans la maquette : danger gardé au niveau seulement.")
                    where.pop(key)
            if not where:
                return addressed(dest, "pas dans la maquette, répétez.")
        if d.get("entrance_status") and where.get("entrance"):
            e = next((x for x in self.b.entrances if x.id == where["entrance"]), None)
            if e:
                e.status = d["entrance_status"]
                e.source = Source(kind="radio", label=dest)
        src = Source(kind="radio", label=dest or "radio", confirmed=True)   # the crew saw it
        old_best = self.b.approach.best_entrance_id if self.b.approach else None
        sev = h.get("severity", "medium")
        if where.get("stair") and h["kind"] == "smoke" and sev == "medium":
            sev = "high"                       # smoke in a stair cuts the way: the crew reporting it is enough
        if h["kind"] == "fire" and where.get("room"):
            lv = B.room_level(self.kit, B.room_node(str(where["room"]), None))
            if lv is not None:
                where = {"level": lv, "room": where["room"]}
        self._add_hazard(h["kind"], where, sev, src)
        d["_part"] = f"{KIND_FR.get(h['kind'], h['kind'])} {B.place_fr(self.kit, where)}" + (f" côté {d['side']}" if d.get("side") else "")
        self.recompute()
        self._after_hazard(old_best)
        side = f" côté {d['side']}" if d.get("side") else ""
        if d.get("entrance_status"):
            return f"Reçu, entrée {where['entrance']} {'verrouillée' if d['entrance_status'] == 'locked' else 'bloquée'}."
        return f"Reçu, {KIND_FR.get(h['kind'], h['kind'])} {self._where_fr(where)}{side}."

    def _add_hazard(self, kind: str, where: dict, severity: str, src: Source) -> tuple[Hazard, bool]:
        """The only way a hazard enters the state: from an event, with its source. Same kind + place = same hazard:
        severity goes up, a crew confirmation upgrades an alert or call report (never the other way round)."""
        cur = next((x for x in self.b.hazards if x.kind == kind and x.where == where), None)
        rank = {"low": 0, "medium": 1, "high": 2}
        if cur:
            if rank.get(severity, 1) > rank.get(cur.severity, 1):
                cur.severity = severity
            if src.confirmed and not cur.source.confirmed:
                self.log("seraph", f"Confirmé par {src.label} : {KIND_FR.get(kind, kind)} {self._where_fr(where)}.", src)
                cur.source = src
            elif src.confirmed:
                cur.source = src
            return cur, False
        self.hz_n += 1
        h = Hazard(id=f"HZ-{self.hz_n}", kind=kind, where=where, severity=severity, source=src)
        self.b.hazards.append(h)
        self.log("seraph", f"Danger : {KIND_FR.get(kind, kind)} {self._where_fr(where)} ({severity}), {self._selon(src)}.", src)
        return h, True

    def _selon(self, src: Optional[Source]) -> str:
        return B.selon(src) or "source inconnue"

    def _resolve_where(self, nb: str, where: dict, level: Optional[int]) -> dict:
        """A place said in words → ids of this building: the stair (« la cage d'escalier » = the only one), an entrance
        by its label (« rampe », « parking »), a room by its label on that level (« garage »). Never guessed beyond."""
        w = dict(where)
        if any(k in w for k in ("stair", "entrance")) or (w.get("room") and w["room"] != "corridor"):
            return w
        if re.search(r"\bescaliers?\b", nb) and len(self.b.stairs) == 1:
            return {"stair": self.b.stairs[0].id}
        e = self._entrance_named(nb)
        if e and re.search(r"\b(sort|sortant|rampe|porte|entree|devant)\b", nb):
            return {"entrance": e.id}
        rid = self._room_named(nb, level)
        if rid:
            return {"level": level, "room": rid} if level is not None else {"room": rid}
        if e:
            return {"entrance": e.id}
        return w

    def _room_named(self, nb: str, level: Optional[int]) -> Optional[str]:
        rooms = [r for r in self.b.rooms if level is None or r.level == level]
        words = [w for w in nb.split() if len(w) > 4]
        for pass_words in (words, [self.SYNONYMS[w] for w in words if w in self.SYNONYMS]):
            for w in pass_words:
                hits = [r for r in rooms if w in normalize(B.room_word(self.kit, r.id)).split()]
                if len(hits) == 1:
                    return hits[0].id
        return None

    def _hazards_from_text(self, text: str, level: Optional[int], src: Source) -> list[Hazard]:
        out = []
        for clause in re.split(r"[,;]|\.(?![\dtT])", text or ""):
            nb = normalize(clause)
            if not nb:
                continue
            ev = rules._hazard(nb, clause)
            if not ev or "hazard" not in ev.data:
                continue
            h = ev.data["hazard"]
            where = {k: v for k, v in (h.get("where") or {}).items() if v is not None}
            if level is not None and not where:
                where = {"level": level}
            where = self._resolve_where(nb, where, where.get("level", level))
            if not where:
                continue
            hz, new = self._add_hazard(h["kind"], where, "high" if h["kind"] == "fire" else h.get("severity", "medium"), src)
            if new:
                out.append(hz)
        if out:
            self.recompute()
        return out

    ENTRANCE_GENERIC = {"porte", "entree", "acces", "principale", "laterale", "hall", "escalier", "sous", "batiment"}
    SYNONYMS = {"parking": "garage", "garage": "parking", "rampe": "garage"}

    def _entrance_named(self, nb: str) -> Optional[Entrance]:
        words = set(nb.split())
        words |= {self.SYNONYMS[w] for w in words if w in self.SYNONYMS}
        for e in self.b.entrances:
            lab = {w for w in normalize(e.label).split() if len(w) > 4 and w not in self.ENTRANCE_GENERIC}
            if lab & words:
                return e
        return None

    def _e_hazard_cleared(self, d: dict, p, dest: str) -> Optional[str]:
        w = {k: v for k, v in (d.get("where") or {}).items() if v is not None}
        kind = d.get("kind", "smoke")
        before = len(self.b.hazards)
        self.b.hazards = [h for h in self.b.hazards if not (h.kind == kind and all(h.where.get(k) == v for k, v in w.items()))]
        src = Source(kind="radio", label=dest)
        if w.get("stair"):
            self.kit.base_stair_status[w["stair"]] = "clear"
            s = next((x for x in self.b.stairs if x.id == w["stair"]), None)
            if s:
                s.status = "clear"
                s.source = src
        self.log("seraph", f"Levé : {KIND_FR.get(kind, kind)} {self._where_fr(w)}, selon {dest}." if len(self.b.hazards) < before else
                 f"{dest} : {self._where_fr(w)} sans {KIND_FR.get(kind, kind)}.", src)
        self.recompute()
        word = "désenfumé" if kind == "smoke" else "feu éteint"
        return f"Reçu, {self._where_fr(w)} {word}." if w else "Reçu."

    def _where_fr(self, w: dict) -> str:
        if w.get("stair"):
            return f"escalier {w['stair']}"
        if w.get("entrance"):
            return f"entrée {w['entrance']}"
        if w.get("room"):
            r = w["room"]
            return f"circulation {level_fr(w.get('level'))}" if r == "corridor" else f"{r}"
        if w.get("level") is not None:
            return level_fr(w["level"])
        return ""

    def _after_hazard(self, old_best: Optional[str]) -> None:
        # approach blocked → say the change
        new_best = self.b.approach.best_entrance_id if self.b.approach else None
        if old_best and new_best and new_best != old_best:
            self.approach_key = new_best
            self.alert("warning", f"Approche changée : {new_best} au lieu de {old_best}")
            self.say(addressed("Tête", f"changement d'approche. {self.approach_say}"), priority="alert")
        # occupants now heading into a hazard
        for o in self.state.occupants:
            if o.heading_to and o.call_id and o.id not in self.with_team and self._node_hazard(o.heading_to):
                c = self.call(o.call_id)
                if c:
                    self._urgency(c)
                    self._call_catches(c, o, self.call_facts.get(c.call_id, {"heading_to": o.heading_to}))
        # teams standing in a hazard
        for t in self.state.crew.teams:
            if t.status == "engaged" and t.location and t.location.stair:
                self._team_hazard(t, f"stair:{t.location.stair}")

    def _team_hazard(self, t: Team, node: str) -> None:
        hz = [h for h in self._node_hazard(node) if h.severity == "high"]
        key = f"teamhz:{t.id}:{node}"
        if not hz or key in self.caught:
            return
        alt = self._alt_stair(node)
        if node.startswith("stair:") and not alt:
            return                       # single stair: going up it under ARI is the plan, not a mistake
        self.caught.add(key)
        what = f"{self._node_fr(node)[2:] if node.startswith('stair:') else node} {self._node_hazard_fr(node)}"
        text = f"{t.label}, {what}" + (f", passez par {alt}." if alt else ".")
        self.alert("danger", text)
        self.say(text, priority="alert")

    def _e_team_update(self, d: dict, p, dest: str) -> Optional[str]:
        td = d["team"]
        t = self.team(td["id"])
        assert t
        was = t.status
        if td.get("status"):
            t.status = td["status"]
        if td.get("pressure_bar_start") and settings.ari_enabled:
            t.pressure_bar_start = int(td["pressure_bar_start"])
        loc = td.get("location") or {}
        if loc:
            cur = t.location.model_dump() if t.location else {}
            if "level" in loc and "stair" not in loc:
                cur.pop("stair", None)
            cur.update({k: v for k, v in loc.items() if v is not None})
            t.location = TeamLocation.model_validate(cur)
        t.last_update = now_iso()
        if t.status == "engaged" and was != "engaged":
            t.entered_at = now_iso()
            if self.state.incident.status in ("dispatched", "en_route"):
                self.state.incident.status = "on_scene"
        if settings.ari_enabled and t.status == "engaged" and t.pressure_bar_start and t.entered_at:
            mins = (t.pressure_bar_start - 60) / 8 * 0.5 / settings.ari_time_factor
            t.exit_by = iso(parse_iso(t.entered_at) + timedelta(minutes=mins))
            self.air_alarm.discard(f"{t.id}:5")
            self.air_alarm.discard(f"{t.id}:0")
        self.log("seraph", f"{t.label} : {t.status}" + (f", {t.pressure_bar_start} bars, sortie {hhmm(t.exit_by)} (calcul simplifié)" if t.exit_by and t.status == "engaged" else "") + ".")
        # catches: team announces a route through a hazard
        if loc.get("stair"):
            self._team_hazard(t, f"stair:{loc['stair']}")
        target = d.get("target_room")
        if target and self.kit.building.rooms:
            target = B.resolve_room(self.kit, target, loc.get("level") or (t.location.level if t.location else None))
        if target:
            lvl = loc.get("level") or (t.location.level if t.location else None)
            if lvl is not None:
                self.add_route("to_victim", f"level:{lvl}", f"room:{target}")
            self._maybe_inside_route()
        # moment: first team engaged
        if t.status == "engaged" and was != "engaged":
            if not settings.ari_enabled:      # teams as positions only: no air, no « Mon air » view
                where = f" par l'escalier {t.location.stair}" if t.location and t.location.stair else (
                    f" au {level_fr(t.location.level)}" if t.location and t.location.level is not None else "")
                return f"Reçu, {t.label.lower()} engagé{where}."
            self.request_moment("team_engaged", "Mon air : binômes, compte à rebours de sortie", ["crew.teams"], deadline_s=120)
            if t.exit_by:
                return f"Reçu, {t.label.lower()} engagé, {t.pressure_bar_start} bars, sortie prévue à {hhmm(t.exit_by)}. Calcul simplifié."
            return f"Reçu, {t.label.lower()} engagé. Pression ?"
        if td.get("status") == "out":
            return f"Reçu, {t.label.lower()} sorti."
        if td.get("status") == "exiting":
            return f"Reçu, {t.label.lower()} en sortie."
        if target:
            info = self._room_info(target)
            return addressed(t.label, f"reçu. En {target}, {info}." if info else "reçu.")
        if settings.ari_enabled and td.get("pressure_bar_start") and t.exit_by:
            return f"Reçu, {t.label.lower()}, sortie prévue à {hhmm(t.exit_by)}. Calcul simplifié."
        return addressed(t.label, "reçu.")

    def _room_info(self, room: str) -> str:
        occs = [o for o in self.state.occupants if o.room == room and o.status not in ("safe_outside",)]
        if not occs:
            return ""
        n = sum(o.people_count or 1 for o in occs)
        bits = [f"{n_fr(n, fem=True)} personne{'s' if n > 1 else ''} signalée{'s' if n > 1 else ''} par appel"]
        if any(o.smoke_seen for o in occs):
            c = self.call(occs[0].call_id) if occs[0].call_id else None
            ex = normalize(c.transcript_excerpt or "") if c else ""
            bits.append("fumée sous la porte" if re.search(r"porte|door|puerta", ex) else "fumée signalée")
        if any(o.mobility_issue for o in occs):
            bits.append("mobilité réduite")
        s = ", ".join(bits)
        node = B.room_node(room, None)
        for n in self.kit.adj.get(node, {}):
            if n.startswith("room:") and f"ladder:{n[5:]}" in self.kit.adj:
                out = n[5:]
                s += f". {cap(B.room_word(self.kit, out))} {out} depuis la {B.room_word(self.kit, room)}"
                break
        return s

    def _e_occupants_update(self, d: dict, p, dest: str) -> Optional[str]:
        room = d.get("room")
        if room and room != "corridor" and self.kit.building.rooms:
            room = B.resolve_room(self.kit, room, d.get("level"))
        occs = [o for o in self.state.occupants if room and o.room == room]
        src = Source(kind="radio", label=dest)
        team = self.team(d["team"], create=False) if d.get("team") else None
        for o in occs:
            o.status = d["status"]
            o.heading_to = d.get("heading_to")
            o.source = src
            o.last_update = now_iso()
            if team:
                self.with_team[o.id] = team.id
            if o.call_id and (c := self.call(o.call_id)):
                f = self.call_facts.setdefault(c.call_id, {})
                f["current_action"] = "outside" if d["status"] == "safe_outside" else "moving"
                if d.get("heading_to"):
                    f["heading_to"] = d["heading_to"]
                self._urgency(c)
                self.publish("call", dump(c))
        if team and d.get("heading_to", "") and d["heading_to"].startswith("stair:"):
            team.location = TeamLocation(level=d.get("level"), stair=d["heading_to"].split(":")[1])
            team.last_update = now_iso()
        if room and d["status"] == "moving":
            node = B.room_node(room, d.get("level"))
            self.state.routes = [r for r in self.state.routes if not (r.purpose == "to_victim" and r.to == node)]
            self.add_route("evacuation", node, "outside")
        n = d.get("count") or sum(o.people_count or 1 for o in occs) or 1
        who = f"{n_fr(n, fem=True)} victime{'s' if n > 1 else ''} {room or ''}".strip()
        if d["status"] == "safe_outside":
            return f"Reçu, {who} évacuée{'s' if n > 1 else ''}."
        tail = f" avec {team.label.lower()}" if team else ""
        via = f", descente par {d['heading_to'].split(':')[1]}" if d.get("heading_to") else ""
        return f"Reçu, {who}{tail}{via}."

    def _e_view_request(self, d: dict, p, dest: str) -> Optional[str]:
        m = d.get("moment")
        if m and d.get("switch"):
            if self.show_moment(m, explicit=True, ready_only=True):
                return f"Reçu, {({'approach': 'approche', 'team_engaged': 'air', 'occupants': 'occupants', 'inside_route': 'montée'}).get(m, m)} sur Halo."
        purpose = d.get("purpose_fr") or "Demande du COS"
        keys = self._data_keys_for(normalize(purpose))
        self.request_moment("commander_request", purpose, keys, deadline_s=300, force=True)
        return "Reçu, vue en préparation sur Halo."

    def _data_keys_for(self, s: str) -> list[str]:
        keys = []
        if re.search(r"binome|equipe|ari|air|pression", s):
            keys += ["crew.teams"]
        if re.search(r"etage|niveau", s):
            keys += ["building.levels"]
        if re.search(r"occupant|personne|victime|appel", s):
            keys += ["occupants", "calls"]
        if re.search(r"plan|salle|piece|chemin|route|montee", s):
            keys += ["building.plan", "building.rooms", "routes"]
        if re.search(r"fumee|feu|danger", s):
            keys += ["building.hazards"]
        return keys or ["crew.teams", "building.levels", "occupants", "building.hazards"]

    def _e_order_to_occupants(self, d: dict, p, dest: str) -> Optional[str]:
        targets, who = self._resolve_targets(d.get("target_text", ""))
        left_out: list[Occupant] = []
        if re.search(r"\b(tous|tout le monde|chacun)\b", normalize(d.get("target_text", ""))):
            keep = []
            for c in targets:
                o = self.occ(c.occupant_id)
                if o and (o.mobility_issue or o.id in self.with_team):
                    if o.mobility_issue:
                        left_out.append(o)
                    continue
                keep.append(c)
            targets = keep
        if not targets:
            return addressed(dest, "à qui ? Répétez.")
        raw = d.get("raw") or ""
        m = re.search(r"\b(?:de|d['’]) ?((?:ne (?:pas|plus) )?\S+(?:er|ir|re)\b.*)$", raw, re.I)
        order_fr = speech.imperative(m.group(1) if m else d.get("order_norm", ""))
        out = []
        for c in targets:
            lang = c.language or "fr"
            tr = speech.translate_order(order_fr, lang)
            out.append({"call_id": c.call_id, "lang": lang, "text": tr or order_fr, "text_fr": order_fr, "translated": bool(tr) or lang == "fr"})
        summary = f"Je dis à {who} : « {order_fr} »"
        tail = ""
        if left_out:
            tail = " Sauf " + ", ".join(f"{o.name}, {'en fauteuil' if self._wheelchair(o) else 'mobilité réduite'}, {level_fr(o.level)}" for o in left_out) + "."
            summary += tail
        st = rules.find_stair(normalize(order_fr))
        warn = ""
        if st:
            s = next((x for x in self.b.stairs if x.id == st), None)
            if s and s.status in ("smoke", "blocked"):
                warn = f" Attention, escalier {st} signalé {B.STATUS_FR[s.status]}."
        spoken_tail = tail.replace(", en fauteuil, ", ", en fauteuil au ") if tail else ""
        self.open_gate("relay_order", summary + warn, {"targets": out, "who_fr": who, "lift": bool(d.get("lift"))},
                       addressed("COS", f"je dis à {who} : {order_fr[:1].lower() + order_fr[1:]}{spoken_tail}{warn} Confirmez ?"))
        return None

    def _resolve_targets(self, t: str) -> tuple[list[Call], str]:
        t = normalize(t)
        active = [c for c in self.state.calls if c.status in ("active", "ringing")]
        if re.search(r"\b(lui|leur)\b", t) and self.last_call_id:
            c = self.call(self.last_call_id)
            o = self.occ(c.occupant_id) if c else None
            return ([c] if c else []), (o.name if o and o.name else (c.call_id if c else ""))
        hits = []
        for o in self.state.occupants:
            parts = [normalize(x) for x in (o.name or "").split()]
            if any(len(x) > 2 and re.search(rf"\b{re.escape(x)}\b", t) for x in parts):
                hits.append(o)
        if hits:
            calls = [self.call(o.call_id) for o in hits if o.call_id]
            return [c for c in calls if c and c.status in ("active", "ringing")], ", ".join(o.name or o.id for o in hits)
        lvl = rules.find_level(t)
        if lvl is not None:
            occs = [o for o in self.state.occupants if o.level == lvl and o.call_id]
            calls = [c for o in occs if (c := self.call(o.call_id)) and c in active]
            return calls, f"occupants du {level_fr(lvl)}"
        if re.search(r"\b(tous|tout le monde|occupants|chacun)\b", t):
            return [c for c in active if c.occupant_id], "tous les occupants en ligne"
        return [], ""

    def _e_question(self, d: dict, p, dest: str) -> Optional[str]:
        topic = d.get("topic")
        b = self.b
        if topic == "approach":
            self.show_moment("approach", explicit=True)
            return addressed(dest, self.approach_say) if self.approach_say else addressed(dest, "approche pas encore calculée, Rosetta lit Maps.")
        if topic == "hydrant":
            if not b.hydrants:
                return addressed(dest, "pas d'hydrant connu.")
            h = b.hydrants[0]
            dist = f", à {int(h.distance_m)} mètres" if h.distance_m else ""
            return addressed(dest, f"hydrant {h.id}, {h.label[:1].lower() + h.label[1:]}{dist}, selon {h.source.label if h.source else 'la maquette'}.")
        if topic in ("riser", "cutoff"):
            name = "riser" if topic == "riser" else ("gas_cutoff" if d.get("what") != "electric" else "electric_cutoff")
            label = {"riser": "Colonne sèche", "gas_cutoff": "Coupure gaz", "electric_cutoff": "Coupure électrique"}[name]
            pt = next((x for x in (b.plan.points if b.plan else []) if x.name == name), None)
            if not pt:
                return addressed(dest, f"{label.lower()} : pas sur le plan.")
            where = self._zone_of(pt.point.x, pt.point.y, b.plan.level if b.plan else None)
            return addressed(dest, f"{label.lower()} {where}, niveau {b.plan.level if b.plan else '?'}, selon le plan.")
        if topic == "wind":
            w = self.state.environment.wind
            return addressed(dest, f"vent {w.dir_label}, {int(w.speed_kmh)} km/h, selon {w.source.label}." if w else "vent pas encore lu.")
        if topic == "risks":
            rs = self.state.environment.risks
            return addressed(dest, ("selon Géorisques : " + ", ".join(r.label.lower() for r in rs) + ".") if rs else "Géorisques pas encore lu.")
        if topic == "building":
            return addressed(dest, self._building_answer(p.body))
        if topic == "air" and not settings.ari_enabled:
            return addressed(dest, "pas de suivi de l'air.")
        if topic == "air":
            ts = [self.team(d["team"], create=False)] if d.get("team") else [t for t in self.state.crew.teams if t.status == "engaged"]
            ts = [t for t in ts if t]
            if not ts:
                return addressed(dest, "aucun binôme engagé.")
            return addressed(dest, " ".join(f"{t.label} : sortie prévue à {hhmm(t.exit_by)}." if t.exit_by else f"{t.label} : pression inconnue." for t in ts) + " Calcul simplifié.")
        if topic == "stair":
            s = next((x for x in b.stairs if x.id == d.get("stair")), None)
            if not s:
                return addressed(dest, f"escalier {d.get('stair')} pas dans la maquette.")
            src = (", selon la maquette" if s.source.kind == "ifc" else f", selon {s.source.label}") if s.source else ""
            if s.status in ("smoke", "blocked"):
                return addressed(dest, f"escalier {s.id} {self._stair_fr(s)}.")
            return addressed(dest, f"escalier {s.id} {B.STATUS_FR.get(s.status, s.status)}{src}.")
        if topic == "occupants":
            return addressed(dest, self._occupants_answer(p.body, d))
        if topic == "unknown_source":
            q = d.get("question_fr") or p.body_raw
            run_id = f"run_{ulid()}"
            self.runs[run_id] = {"endpoint": "explore", "params": {"question_fr": q}, "started": time.time(), "done": False,
                                 "run_id": run_id, "incident_id": self.state.incident.id, "incident_t0": self.incident_t0}
            self.explore(run_id, q)
            return "Je cherche, source non vérifiée."
        return None

    def _zone_of(self, x: float, y: float, level: Optional[int]) -> str:
        for node, z in self.kit.zones.items():
            if level is not None and z.level != level:
                continue
            x0, y0, x1, y1 = z.box
            if x0 <= x <= x1 and y0 <= y <= y1:
                return {"stair": f"dans l'escalier {node[6:]}", "room": f"en {node[5:]}",
                        "corridor": "dans la circulation"}.get(node.split(":")[0], node)
        return "sur le plan"

    def _building_answer(self, body: str) -> str:
        b = self.b
        if not b.model and not b.doors and not b.materials:
            return "pas de maquette."
        nb = normalize(body)
        room = None
        for r in b.rooms:
            lab = normalize(r.label)
            if r.id.lower() in nb or (len(lab) > 4 and any(w in nb for w in lab.split() if len(w) > 4)):
                room = r
                break
        if "porte" in nb:
            doors = [dr for dr in (b.doors or []) if room and any(x in (room.id, f"room:{room.id}") for x in dr.between)]
            if not doors:
                return "porte pas dans la maquette."
            dr = doors[0]
            fr = f"coupe-feu {dr.fire_rating}" if dr.fire_rating else "résistance au feu pas dans la maquette"
            lab = dr.label if dr.label.lower().startswith("porte") else f"porte {dr.label}"
            return f"{lab[:1].lower() + lab[1:]} : {fr}, source maquette."
        mats = b.materials or []
        el = next((e for e in ("facade", "wall", "slab", "roof") if {"facade": "facade", "wall": "cloison", "slab": "plancher", "roof": "toit"}[e] in nb), None)
        hits = [m for m in mats if (not el or m.element == el) and (not room or m.room == room.id)]
        if not hits:
            return "pas dans la maquette."
        m = hits[0]
        what = {"facade": "façade", "wall": "cloison", "slab": "plancher", "roof": "toiture", "door": "porte"}.get(m.element, m.element)
        return f"{what} : {m.material[:1].lower() + m.material[1:]}" + (f", {m.fire_rating}" if m.fire_rating else "") + ", source maquette."

    def _occupants_answer(self, body: str, d: dict) -> str:
        nb = normalize(body)
        for o in self.state.occupants:
            parts = [normalize(x) for x in (o.name or "").split()]
            if any(len(x) > 2 and re.search(rf"\b{re.escape(x)}\b", nb) for x in parts):
                st = STATUS_OCC_FR.get(o.status, o.status)
                head = f", vers {self._node_fr(o.heading_to)}" if o.heading_to else ""
                return f"{o.name} : {level_fr(o.level)}{', ' + o.room if o.room else ''}, {st}{head}, selon {o.source.label}."
        lvl = d.get("level")
        occs = [o for o in self.state.occupants if lvl is None or o.level == lvl]
        if lvl is not None:
            if not occs:
                return f"personne de listé au {level_fr(lvl)}."
            return f"au {level_fr(lvl)} : " + ", ".join(f"{o.name} {STATUS_OCC_FR.get(o.status, o.status)}" for o in occs) + "."
        return self._sitrep_text().split(" : ", 1)[1]

    # ───────── Halo moments ─────────
    def request_moment(self, moment: str, purpose: str, data_keys: list[str], deadline_s: int, force: bool = False,
                       refresh: bool = False) -> None:
        active = [r for r in self.state.halo.requests if r.moment == moment and r.status in ("requested", "building", "ready")]
        enabled = moment in settings.view_moments or force
        if moment != "commander_request" and active and not refresh:
            self.show_moment(moment)
            return
        if not enabled:
            return
        if True:
            self.req_n += 1
            req = ViewRequestStatus(request_id=f"req_{ulid()}", moment=moment, purpose_fr=purpose)
            self.state.halo.requests.append(req)
            refs = [dump(s) for s in self.b.screenshots if self._ref_for(moment, s)]
            if self.b.model:
                for lp in self.b.model.level_plans:
                    refs.append({"image_id": lp.image_id, "url": lp.url, "caption": f"Plan IFC niveau {lp.level}",
                                 "side": "plan", "width": 1000, "height": 1000, "taken_at": now_iso()})
            vr = {"request_id": req.request_id, "moment": moment, "purpose_fr": purpose, "data_keys": data_keys,
                  "references": refs, "interactions": ["tap a level → Seraph shows who is there"] if moment in ("occupants", "team_engaged") else [],
                  "deadline_s": deadline_s, "sample_state_url": f"{settings.seraph_public_url or settings.seraph_url}/state"}
            self.runs[req.request_id] = {"view": True, "deadline": time.time() + deadline_s, "t0": time.time(),
                                         "refs": [r["image_id"] for r in refs]}
            self.publish("silex", dump(req))
            self.log("silex", f"Vue demandée à Devin : {purpose}")
            self.request_view_out(vr)
        if moment != "commander_request":
            self.show_moment(moment)

    def _ref_for(self, moment: str, s: Screenshot) -> bool:
        if moment == "approach":
            return s.side in ("front", "left", "right", "rear", "top") and not s.image_id.startswith(("dispatch", "georisques", "meteo", "occupants", "report"))
        if moment in ("inside_route", "occupants"):
            return s.side == "plan"
        return False

    def show_moment(self, moment: str, explicit: bool = False, ready_only: bool = False) -> bool:
        ready = [r for r in self.state.halo.requests if r.moment == moment and r.status == "ready" and r.url]
        cur = self.state.halo.current_view
        if ready:
            r = ready[-1]
            view = CurrentView(view_id=r.view_id or r.request_id, url=r.url or "", moment=moment, built_by="devin")
        elif ready_only:
            return False
        else:
            view = CurrentView(view_id=f"fallback_{moment}", url=f"fallback://{moment}", moment=moment, built_by="fallback")
        if cur and cur.view_id == view.view_id:
            return True
        if not explicit and cur and cur.moment != moment and PRIORITY.get(cur.moment, 0) > PRIORITY.get(moment, 0):
            return False
        self.state.halo.current_view = view
        self.publish("halo_view", {"view_id": view.view_id, "url": view.url, "moment": moment, "built_by": view.built_by})
        self.log("silex", f"Halo : {'vue Devin' if view.built_by == 'devin' else 'vue de secours'} « {moment} ».")
        self.touch()
        return True

    def on_view_ready(self, vr: dict) -> None:
        req = next((r for r in self.state.halo.requests if r.request_id == vr.get("request_id")), None)
        if not req:
            return
        st = vr.get("status", "building")
        req.status = st
        req.view_id = vr.get("view_id") or req.view_id
        req.url = vr.get("url") or req.url
        req.devin_session_url = vr.get("devin_session_url") or req.devin_session_url
        if st == "ready":
            req.ready_at = now_iso()
            meta = self.runs.get(req.request_id, {})
            if meta.get("t0"):
                self.metric("request_to_view", (time.time() - meta["t0"]) * 1000, moment=req.moment)
            self.log("silex", f"Vue construite par Devin à {hhmm(req.ready_at)} : {req.purpose_fr}")
            cur = self.state.halo.current_view
            explicit = req.moment == "commander_request" or (cur is not None and cur.moment == req.moment)
            self.show_moment(req.moment, explicit=explicit)
        elif st == "failed":
            self.log("silex", f"Vue {req.moment} : échec Devin ({vr.get('note') or 'erreur'}), vue de secours.")
        self.publish("silex", dump(req))
        self.touch()

    def _maybe_inside_route(self) -> None:
        if not self.b.plan:
            return
        engaged = [t for t in self.state.crew.teams if t.status == "engaged" and t.location and t.location.level is not None]
        victim = [r for r in self.state.routes if r.purpose == "to_victim"]
        if engaged and victim:
            to = victim[-1].to.split(":", 1)[-1]
            self.request_moment("inside_route", f"Par où je monte : plan niveau {self.b.plan.level}, zones, fumée, flèche vers {to}",
                                ["building.plan", "building.rooms", "building.hazards", "routes"], deadline_s=300)

    # ───────── report ─────────
    def report_sections(self) -> dict:
        tl = [e for e in self.state.timeline if e.kind in ("radio", "call", "gate", "alert", "seraph", "rosetta")]
        chron = "\n".join(f"{hhmm(e.t)} {e.text_fr}" for e in tl[-60:])
        teams = ", ".join(f"{t.label} ({t.status}{', ' + str(t.pressure_bar_start) + ' bars' if t.pressure_bar_start else ''})" for t in self.state.crew.teams) or "aucun binôme"
        moyens = f"Binômes : {teams}. Assistant Seraph (exercice), Rosetta : {self.state.rosetta.counter.endpoints} sources sans API."
        vict = []
        for o in self.state.occupants:
            extra = f", avec {self.with_team[o.id]}" if o.id in self.with_team else ""
            vict.append(f"{o.name} ({level_fr(o.level)}{', ' + o.room if o.room else ''}) : {STATUS_OCC_FR.get(o.status, o.status)}{extra}")
        hz = "; ".join(f"{KIND_FR.get(h.kind, h.kind)} {self._where_fr(h.where)} ({h.severity}, {h.source.label})" for h in self.b.hazards)
        obs = f"EXERCICE. {self.state.incident.nature}. Dangers : {hz or 'aucun'}. " \
              f"Approche : {self.b.approach.reason if self.b.approach else 'non calculée'}"
        return {"chronologie": chron, "moyens": moyens, "victimes": "\n".join(vict) or "aucune", "observations": obs}

    # ───────── timers ─────────
    def tick(self) -> None:
        now = time.time()
        nowdt = datetime.now(timezone.utc)
        for g in self.state.gates:
            if g.status == "pending" and (nowdt - parse_iso(g.created_at)).total_seconds() > GATE_TTL_S:
                g.status = "expired"
                g.resolved_at = now_iso()
                self.publish("gate", dump(g))
                self.log("gate", f"Expiré sans confirmation : {g.summary_fr}")
                self.say(addressed("COS", f"sans confirmation, abandonné : {g.summary_fr.rstrip(' ?')}."))
                self.touch()
        f = settings.ari_time_factor
        for t in self.state.crew.teams:
            if not settings.ari_enabled or t.status != "engaged" or not t.exit_by:
                continue
            left = (parse_iso(t.exit_by) - nowdt).total_seconds()
            if left <= 5 * 60 / f and f"{t.id}:5" not in self.air_alarm:
                self.air_alarm.add(f"{t.id}:5")
                self.alert("danger", f"{t.label} : sortie dans 5 minutes (calcul simplifié)")
                self.say(f"{t.label} de Seraph, sortie dans 5 minutes.", priority="alert")
            if left <= 0 and f"{t.id}:0" not in self.air_alarm:
                self.air_alarm.add(f"{t.id}:0")
                self.alert("danger", f"{t.label} : heure de sortie atteinte (calcul simplifié)")
                self.say(f"{t.label} de Seraph, heure de sortie atteinte.", priority="alert")
        for r in self.state.halo.requests:
            meta = self.runs.get(r.request_id, {})
            if r.status in ("requested", "building") and meta.get("deadline") and now > meta["deadline"]:
                r.status = "timed_out"
                self.publish("silex", dump(r))
                self.log("silex", f"Vue {r.moment} en retard : Halo reste sur la vue de secours.")
                self.touch()
        for oid, t0 in list(self.called_at.items()):
            o = self.occ(oid)
            if o and o.status == "calling" and now - t0 > NO_NEWS_S / max(self.mock_speed, 1.0):
                self._no_news(o)
                self.touch()


def res_run_id(run: dict) -> Optional[str]:
    return run.get("run_id")
