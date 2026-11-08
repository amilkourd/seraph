"""Radio line → events, with plain text rules. Fire radio is formulaic: rules first, the LLM only for leftovers.
« confirme » and « annule » never depend on a model."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Optional

NUM_WORDS = {"un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5, "six": 6, "sept": 7, "huit": 8,
             "neuf": 9, "dix": 10}
ORDINALS = {"premier": 1, "1er": 1, "deuxieme": 2, "second": 2, "troisieme": 3, "quatrieme": 4, "cinquieme": 5,
            "sixieme": 6, "septieme": 7, "rdc": 0, "rez de chaussee": 0, "sous sol": -1}
CALL_SIGNS = r"(seraph|cos|tete|codis|cta|chef(?: d agres)?|fpt|epa|vsav|binome (?:\d|un|deux|trois|quatre)|b\d)"


@dataclass
class Event:
    type: str
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class Parsed:
    text: str                       # original
    norm: str                       # normalised full line
    body: str                       # normalised, without the « X de Y » formula
    body_raw: str                   # original, without the formula
    dest: Optional[str]             # addressee call sign (normalised) or None
    to_seraph: bool
    question: bool
    events: list[Event]
    path: str = "rules"             # rules | llm | none


def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def normalize(s: str) -> str:
    s = strip_accents(s.lower()).replace("’", "'").replace("œ", "oe")
    s = re.sub(r"(\d)\.(\w)", r"\1§\2", s)          # protect room ids like 3.12 / 3.t
    s = re.sub(r"[^\w§\s]", " ", s)
    s = s.replace("§", ".")
    return re.sub(r"\s+", " ", s).strip()


def num(tok: str) -> Optional[int]:
    if tok.isdigit():
        return int(tok)
    return NUM_WORDS.get(tok)


def team_id(tok: str) -> Optional[str]:
    n = num(tok)
    return f"B{n}" if n else None


def find_level(s: str) -> Optional[int]:
    m = re.search(r"\b(?:au|du|le|en|niveau|etage|r ?\+ ?)\s*(\d)\s*(?:e|eme|er)?\b(?:\s*etage)?", s)
    if m:
        return int(m.group(1))
    m = re.search(r"\b(\d)\s*(?:e|eme|er)\b(?:\s*etage)?", s)
    if m:
        return int(m.group(1))
    for w, n in ORDINALS.items():
        if re.search(rf"\b{w}\b", s):
            return n
    return None


ROOM_RE = re.compile(r"\b(\d{1,2}\.(?:\d{1,3}|t))\b")


def find_room(s: str) -> Optional[str]:
    m = ROOM_RE.search(s)
    if m:
        r = m.group(1)
        return r[:-1] + "T" if r.endswith(".t") else r
    if re.search(r"\b(circulation|couloir|corridor|palier)\b", s):
        return "corridor"
    return None


def find_stair(s: str) -> Optional[str]:
    m = re.search(r"\bescaliers? ([ab]|nord|sud)\b", s)
    if not m:
        return None
    return {"nord": "A", "sud": "B"}.get(m.group(1), m.group(1).upper())


def find_entrance(s: str) -> Optional[str]:
    m = re.search(r"\b(?:entree|porte|acces) ?(e\d)\b", s) or re.search(r"\b(e\d)\b", s)
    return m.group(1).upper() if m else None


def split_formula(norm: str, raw: str) -> tuple[Optional[str], str, str]:
    """« Seraph de Tête, … » → ("seraph", body_norm, body_raw)."""
    m = re.match(rf"^{CALL_SIGNS}(?: de {CALL_SIGNS})?\b\s*", norm)
    if not m:
        return None, norm, raw
    dest = m.group(1)
    body = norm[m.end():].strip()
    # cut the raw text after the first comma when the formula is there (keeps accents for purposes / names)
    raw_body = raw.split(",", 1)[1].strip() if "," in raw[:40] else raw
    return dest, body, raw_body


CONFIRM_WORDS = r"(je confirme|c est confirme|ok confirme|confirme|confirmez|confirmer|affirmatif|valide|je valide)"
CANCEL_WORDS = r"(on annule|j annule|annule|annulez|annuler|negatif|laisse tomber|abandonne|stop)"
FILLER = r"(?:oui |ok |bien |c est bon )*"

SMOKE = r"(fumee|fumees|enfume|enfumee|enfumes|enfumees)"
FIRE = r"(feu|flammes?|embrase|embrasement)"
HIGH = r"(enfume|enfumee|enfumes|enfumees|epaisse|dense|noire|importante|impraticable|beaucoup|totalement)"
LOW = r"(legere|leger|peu de)"


def _is_question(norm: str, raw: str) -> bool:
    return "?" in raw or bool(re.match(r"^(est ce qu|il y a|y a t il|combien|ou |quel|quelle|comment|pourquoi|qu est ce)", norm))


def parse(text: str, speaker: str = "") -> Parsed:
    norm = normalize(text)
    dest, body, body_raw = split_formula(norm, text)
    to_seraph = dest == "seraph" or (dest is None and "seraph" in norm) or dest is None
    if dest is not None and dest != "seraph" and "seraph" in body.split()[:2]:
        to_seraph = True
    body = re.sub(r"^seraph\b\s*", "", body)
    p = Parsed(text=text, norm=norm, body=body, body_raw=body_raw, dest=dest, to_seraph=to_seraph,
               question=_is_question(body, text), events=[])
    sp = normalize(speaker)
    crew_talk = dest is not None and dest != "seraph" and "seraph" not in norm
    if crew_talk:
        # crew to crew: Seraph listens silently for facts, never replies
        p.events = [e for e in [_team(body, sp)] + _hazards(body, body_raw) if e]
        for e in p.events:
            e.data["silent"] = True
        if not p.events:
            p.events = [Event("chatter")]
        return p
    p.events = _classify(p, sp)
    if not p.events:
        p.path = "none"
    return p


def _classify(p: Parsed, sp: str) -> list[Event]:
    b = p.body
    words = b.split()
    # 1. confirm / cancel: short and explicit only
    if re.match(rf"^{FILLER}{CONFIRM_WORDS}\b", b) and len(words) <= 5:
        return [Event("confirm")]
    if re.match(rf"^{FILLER}{CANCEL_WORDS}\b", b) and len(words) <= 5:
        return [Event("cancel")]
    # 2. report, sitrep
    if re.search(r"\b(fais|faire|prepare|redige|lance|envoie|demarre)( moi)? (le |un |la )?(rapport|compte rendu|cr)\b", b) \
            or re.fullmatch(r"(le )?(rapport|compte rendu)( stp)?", b):
        return [Event("report_request")]
    if re.search(r"\b(point de situation|point situation|fais le point|fais moi le point|bilan|ou on en est|ou en est on|etat des lieux)\b", b) \
            or re.fullmatch(r"situation", b):
        return [Event("sitrep_request")]
    # 3. Halo
    if re.search(r"\bhalo\b", b):
        return [_view_request(p)]
    # 4. order to occupants (read back + gated)
    m = re.match(r"^(?:ok |bon )?(dis|demande|ordonne|indique|annonce|previens|transmets?)\b(.*)$", b) \
        or re.search(r"^(?:levee du confinement|fin du confinement|deconfinement|evacuation generale)\s+(dis|demande|ordonne|indique|annonce|previens|transmets?)\b(.*)$", b)
    if m:
        rest = m.group(2)
        mo = re.search(r"\b(?:de|d) (ne (?:pas|plus) \w+|\w+(?:er|ir|re))\b", rest)
        if mo:
            target = rest[:mo.start()].strip()
            order = rest[mo.start():].split(" ", 1)[1]
            lift = bool(re.match(r"^(levee du confinement|fin du confinement|deconfinement|evacuation generale)", b))
            return [Event("order_to_occupants", {"target_text": target, "order_norm": order, "raw": p.body_raw, "lift": lift})]
    # 4b. a hazard cleared (« escalier A désenfumé »): never adds smoke
    if re.search(r"\b(desenfumee?s?|fumee dissipee|plus de fumee|pas de fumee|aucune fumee|feu eteint|feu maitrise|pas de feu|levee de doute)\b", b):
        kind = "fire" if re.search(r"\bfeu\b", b) and not re.search(r"fumee", b) else "smoke"
        where: dict[str, Any] = {}
        if find_stair(b):
            where["stair"] = find_stair(b)
        elif find_room(b):
            where["room"] = find_room(b)
        if find_level(b) is not None and "stair" not in where:
            where["level"] = find_level(b)
        return [Event("hazard_cleared", {"kind": kind, "where": where})]
    # 5. specific questions
    q = _question_topic(b, p)
    if q:
        return [q]
    # 6. people found / evacuated
    occ = _occupants_update(b, sp)
    if occ:
        out = [occ]
        for hz in _hazards(b, p.body_raw):
            hz.data["secondary"] = True
            out.append(hz)
        return out
    # 7. team update (+ hazard in the same line)
    team = _team(b, sp)
    hzs = _hazards(b, p.body_raw)
    if team:
        for hz in hzs:
            hz.data["secondary"] = True
        return [team] + hzs
    if hzs:
        return hzs
    if p.question:
        return [Event("question", {"topic": "unknown_source", "question_fr": p.body_raw.strip()})]
    if re.fullmatch(r"(recu|bien recu|ok|compris|5 sur 5|cinq sur cinq)( seraph)?", b):
        return [Event("chatter", {"ack": True})]
    return []


def _view_request(p: Parsed) -> Event:
    b = p.body
    moment = None
    for key, mom in ((r"approche|entree|acces", "approach"), (r"\bair\b|pression|sortie|\bari\b", "team_engaged"),
                     (r"qui est ou|occupants|personnes|victimes", "occupants"),
                     (r"plan|montee|chemin|itineraire|route", "inside_route")):
        if re.search(key, b):
            moment = mom
            break
    switch = bool(re.match(r"^(montre|affiche|remets|reviens|repasse|mets)", b))
    raw = p.body_raw
    purpose = re.sub(r"(?i)^\s*(seraph\s*,?\s*)?", "", raw)
    purpose = re.sub(r"(?i)\b(il me faut|j'ai besoin d[e']|je veux|mets(-moi)?|montre(-moi)?|affiche(-moi)?|remets|donne(-moi)?)\b", "", purpose)
    purpose = re.sub(r"(?i)\bsur halo\b", "", purpose)
    purpose = re.sub(r"^\s*(la|le|les|l'|une|un|des)\s*", "", purpose.strip(), flags=re.I)
    purpose = re.sub(r"\s+", " ", purpose).strip(" .,!?")
    purpose = purpose[:1].upper() + purpose[1:] if purpose else "Demande du COS"
    return Event("view_request", {"moment": moment, "switch": switch, "purpose_fr": purpose})


def _question_topic(b: str, p: Parsed) -> Optional[Event]:
    def q(topic: str, **kw: Any) -> Event:
        return Event("question", {"topic": topic, "question_fr": p.body_raw.strip(), **kw})

    if re.search(r"\b(quelle entree|quel acces|par ou (on |je |nous )?(rentre|entre|attaque|penetre|passe)|on (rentre|entre) par ou|entree \?|ou est ce qu on (rentre|entre))", b) \
            or re.search(r"\bquelle? (entree|porte)\b", b):
        return q("approach")
    if re.search(r"\b(hydrant|poteau|pei|bouche d incendie|point d eau)\b", b):
        return q("hydrant")
    if re.search(r"\bcolonne( seche)?\b", b):
        return q("riser")
    if re.search(r"\bcoupure|vanne\b", b):
        return q("cutoff", what="gas" if "gaz" in b else "electric" if "elec" in b else None)
    if re.search(r"\bvent\b", b):
        return q("wind")
    if re.search(r"\b(risques?|seveso|georisques|industriel)\b", b):
        return q("risks")
    if re.search(r"\b(coupe feu|materiaux?|facade|cloison|plancher|dalle|structure du batiment)\b", b) \
            or (p.question and re.search(r"\bla porte (du|de la|des)\b", b)):
        return q("building", room=find_room(b), level=find_level(b), stair=find_stair(b))
    if p.question and re.search(r"\b(pression|air|sortie|reste combien|temps)\b", b) and re.search(r"\bbinome|b\d\b", b):
        m = re.search(r"\bbinome (\d|un|deux|trois|quatre)\b|\bb(\d)\b", b)
        tid = team_id(m.group(1) or m.group(2)) if m else None
        return q("air", team=tid)
    if p.question and find_stair(b) and not re.search(r"\bbinome\b", b):
        return q("stair", stair=find_stair(b))
    if p.question and re.search(r"\b(combien|qui|ou est|ou sont|personnes|occupants|victimes|gens)\b", b):
        return q("occupants", level=find_level(b), room=find_room(b), name=b)
    return None


def _team(b: str, sp: str) -> Optional[Event]:
    tid = None
    m = re.search(r"\bbinome (\d|un|deux|trois|quatre)\b|\bb(\d)\b", b)
    if m:
        tid = team_id(m.group(1) or m.group(2))
    elif sp.startswith("binome"):
        tid = team_id(sp.split()[-1])
    if not tid:
        return None
    status = None
    if re.search(r"\b(engage|engages|engagee|on engage|on rentre|entre dans|on entre)\b", b):
        status = "engaged"
    elif re.search(r"\b(sorti|sortis|dehors|a l exterieur|on est sorti|retour au camion)\b", b):
        status = "out"
    elif re.search(r"\b(on ressort|en sortie|on sort|on se replie|repli)\b", b):
        status = "exiting"
    loc_level = find_level(b)
    stair = find_stair(b)
    room = None
    m2 = re.search(r"\b(?:on est|nous sommes|je suis|arrive|arrives) (?:en|dans la|dans le|a la|au) ?(\d{1,2}\.(?:\d{1,3}|t))\b", b)
    if m2:
        room = m2.group(1)
    target = None
    m3 = re.search(r"\b(?:vers|direction|on va|on monte|on progresse vers)(?: la| le| en)? (\d{1,2}\.(?:\d{1,3}|t))\b", b)
    if m3:
        target = m3.group(1)
        if loc_level is None:
            loc_level = int(target.split(".")[0])
    pressure = None
    m4 = re.search(r"\b(\d{2,3}) ?bars?\b", b)
    if m4:
        pressure = int(m4.group(1))
    position_words = re.search(r"\b(on est|nous sommes|on progresse|on monte|on descend|on arrive|arrive|on redescend)\b", b)
    if not (status or pressure or (position_words and (loc_level is not None or stair or room))):
        return None
    loc: dict[str, Any] = {}
    if loc_level is not None and (position_words or status == "engaged" and not stair):
        loc["level"] = loc_level
    if stair:
        loc["stair"] = stair
    if room:
        loc["room"] = room
    team: dict[str, Any] = {"id": tid}
    if status:
        team["status"] = status
    if pressure:
        team["pressure_bar_start"] = pressure
    if loc:
        team["location"] = loc
    return Event("team_update", {"team": team, "target_room": target})


def _occupants_update(b: str, sp: str) -> Optional[Event]:
    m = re.search(r"\b(?:(\d+|un|une|deux|trois|quatre|cinq|six) )?(victimes?|personnes?|occupants?|blesses?)\b.*?\b(trouvees?|retrouvees?|localisees?|prises? en charge|avec nous|evacuees?|dehors|sorties?)\b", b)
    if not m:
        return None
    count = num(m.group(1)) if m.group(1) else None
    room = find_room(b)
    level = find_level(b)
    if room and room != "corridor" and level is None:
        level = int(room.split(".")[0]) if room[0].isdigit() else None
    status = "moving"
    if re.search(r"\b(evacuees?|dehors|sorties?|a l exterieur)\b", b):
        status = "safe_outside"
    heading = None
    st = find_stair(b)
    if status == "moving" and st:
        heading = f"stair:{st}"
    team = None
    mt = re.search(r"\bbinome (\d|un|deux|trois|quatre)\b", b)
    if mt:
        team = team_id(mt.group(1))
    elif sp.startswith("binome"):
        team = team_id(sp.split()[-1])
    conscious = None
    if re.search(r"\binconscientes?\b", b):
        conscious = False
    elif re.search(r"\bconscientes?\b", b):
        conscious = True
    return Event("occupants_update", {"count": count, "room": room, "level": level, "status": status,
                                      "heading_to": heading, "team": team, "conscious": conscious})


def _clause(raw: str, pattern: str) -> Optional[str]:
    for c in re.split(r"[,;!?]|\.(?![\dtT])", raw):
        n = normalize(c)
        if re.search(pattern, n):
            return n
    return None


HAZARD_WORDS = rf"\b({FIRE}|{SMOKE}|odeur de gaz|fuite de gaz|effondre|effondrement|ecroule|chaleur|tres chaud)\b"


def _hazards(b: str, raw: str) -> list[Event]:
    """Every hazard of the line, one per clause (« feu de véhicule au parking, fumée dans la cage d'escalier »)."""
    out: list[Event] = []
    level = find_level(b)
    for clause in re.split(r"[,;!?]|\.(?![\dtT])|\bet\b", raw or ""):
        cn = normalize(clause)
        if not cn or not re.search(HAZARD_WORDS, cn):
            continue
        ev = _hazard(cn, clause)
        if not ev:
            continue
        w = ev.data["hazard"]["where"]
        if "level" not in w and level is not None and not (w.get("stair") or w.get("entrance")):
            w["level"] = level
        ev.data["clause"] = cn                 # the place is resolved on its own clause, not the whole line
        out.append(ev)
    if not out:
        ev = _hazard(b, raw)
        return [ev] if ev else []
    return out


def _hazard(b: str, raw: str = "") -> Optional[Event]:
    if re.search(rf"\b(pas de|aucune?|sans|plus de) {SMOKE}|\b(pas de|aucun|sans|plus de) {FIRE}\b", b):
        return None
    kind = None
    if re.search(rf"\b{FIRE}\b", b) and not re.search(r"\b(feu de local|coupe feu|pompiers?)\b", b):
        kind = "fire"
    elif re.search(rf"\b{SMOKE}\b", b):
        kind = "smoke"
    elif re.search(r"\b(odeur de gaz|fuite de gaz)\b", b):
        kind = "gas"
    elif re.search(r"\b(effondre|effondrement|ecroule|plafond tombe|menace de ruine)\b", b):
        kind = "structure"
    elif re.search(r"\b(chaleur|tres chaud)\b", b):
        kind = "heat"
    blocked_entrance = re.search(r"\b(?:porte|entree|acces) ?(e\d)\b.*\b(bloquee|condamnee|verrouillee|fermee|impraticable)\b", b)
    if not kind and not blocked_entrance:
        return None
    where: dict[str, Any] = {}
    word = {"fire": FIRE, "smoke": SMOKE}.get(kind or "", r"gaz|effondr|ecroul|plafond|chaleur|chaud")
    c = _clause(raw, rf"\b{word}") if raw else None
    c = c or b
    lvl = find_level(c)
    if lvl is None:
        lvl = find_level(b)
    room = find_room(c)
    stair = find_stair(c)
    if kind and stair and re.search(rf"\bescaliers? \w+ (est |reste )?{SMOKE}|{SMOKE} dans l escalier|escaliers? \w+ (bloque|impraticable)", c):
        where["stair"] = stair
    elif room:
        if lvl is not None:
            where["level"] = lvl
        where["room"] = room
        if room != "corridor" and "level" not in where and room[0].isdigit():
            where["level"] = int(room.split(".")[0])
    elif lvl is not None:
        where["level"] = lvl
    if blocked_entrance and not kind:
        e = blocked_entrance.group(1).upper()
        return Event("hazard", {"hazard": {"kind": "structure", "where": {"entrance": e}, "severity": "high"},
                                "entrance_status": "locked" if "verrouill" in b else "blocked"})
    side = re.search(r"\bcote (nord|sud|est|ouest|rue|boulevard|cour)\b", c)
    sev = "medium"
    if kind == "fire" or re.search(rf"\b{HIGH}\b", c):
        sev = "high"
    elif re.search(rf"\b{LOW}\b", c):
        sev = "low"
    return Event("hazard", {"hazard": {"kind": kind, "where": where, "severity": sev},
                            "side": side.group(1) if side else None})
