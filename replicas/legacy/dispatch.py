"""Alerte / Interventions (:8101): the fire service's dispatch software, as Rosetta sees it."""

from __future__ import annotations

import json
import re
import sqlite3

from fastapi import Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from .common import (Replica, Store, ago, building_model, commune_of, demo_address, demo_commune, fixture, iso,
                     level_label, utcnow)

SCHEMA = """
DROP TABLE IF EXISTS meta;
DROP TABLE IF EXISTS incidents;
DROP TABLE IF EXISTS main_courante;
CREATE TABLE meta (k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE incidents (
  id TEXT PRIMARY KEY, declared_at TEXT, address TEXT, commune TEXT, nature TEXT, level INTEGER,
  status TEXT, caller TEXT, caller_phone TEXT, caller_notes TEXT, means TEXT, centre TEXT, closed_at TEXT
);
CREATE TABLE main_courante (id TEXT PRIMARY KEY, incident_id TEXT, at TEXT, author TEXT, text TEXT);
"""

OPEN, CLOSED = "En cours", "Clôturée"

# Past incidents, so the list looks like a working day. Fictional streets.
HISTORY = [
    ("INC-0999", 6 * 60 + 12, "41 rue des Essais", "Feu de poubelle sur voie publique", 0, "FPT 1"),
    ("INC-0998", 11 * 60 + 48, "3 place du Modèle", "Malaise sur voie publique", 0, "VSAV 1"),
    ("INC-0997", 19 * 60 + 41, "12 rue de l'Exemple", "Fuite d'eau, inondation de local", 1, "FPT 1"),
    ("INC-0996", 28 * 60 + 23, "7 impasse Fictive", "Personne bloquée dans ascenseur", 4, "FPT 1"),
    ("INC-0995", 40 * 60 + 5, "25 boulevard de la Simulation", "Odeur de gaz dans immeuble", 2, "FPT 1 · VSAV 1"),
]



def seed_log(notes: list[str]) -> list[tuple[float, str, str]]:
    """Six entries before the demo starts (the next one is MC-0007), built from the fixture's caller notes."""
    levels = sorted(l["level"] for l in building_model().get("levels", [])) or [0]
    building = f"Immeuble {level_label(levels[-1])}" + (f", sous-sol {level_label(levels[0])}" if levels[0] < 0 else "")
    first = notes[0] if notes else "feu signalé"
    rest = "; ".join(notes[1:]) or "pas de précision"
    return [
        (4.0, "CTA", f"Appel 18 reçu. Témoin : {first}."),
        (3.5, "CTA", f"Appelant : {rest}."),
        (3.0, "CTA", "Départ FPT 1, EPA 1, VSAV 1."),
        (2.5, "CTA", f"{building}. Gestionnaire prévenu, liste des occupants demandée."),
        (1.5, "FPT 1", "FPT 1 parti."),
        (1.0, "EPA 1", "EPA 1 parti."),
    ]


def seed(conn: sqlite3.Connection, keep_public: bool) -> None:
    conn.executescript(SCHEMA)
    demo = fixture("endpoints/dispatch.read.json")["output"]
    town = demo_commune()
    conn.execute(
        "INSERT INTO incidents VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ("INC-0001", ago(4.5), demo_address(), town, demo["nature"], demo["level"], OPEN,
         "Témoin (voie publique)", "+33100000099", json.dumps(demo["caller_notes"], ensure_ascii=False),
         "FPT 1 · EPA 1 · VSAV 1", "CIS Centre (fictif)", None),
    )
    for inc_id, minutes, address, nature, level, means in HISTORY:
        conn.execute(
            "INSERT INTO incidents VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (inc_id, ago(minutes), address, town, nature, level, CLOSED, "Requérant", "+33100000098",
             "[]", means, "CIS Centre (fictif)", ago(minutes - 55)),
        )
    log = seed_log(demo["caller_notes"])
    for n, (minutes, author, text) in enumerate(log, start=1):
        conn.execute("INSERT INTO main_courante VALUES (?,?,?,?,?)",
                     (f"MC-{n:04d}", "INC-0001", ago(minutes), author, text))
    conn.executemany("INSERT INTO meta VALUES (?,?)",
                     [("incident", "2"), ("main_courante", str(len(log) + 1))])


def demo_nature() -> str:
    return fixture("endpoints/dispatch.read.json")["output"]["nature"]


store = Store("dispatch", SCHEMA, seed)
replica = Replica("dispatch", "Alerte / Interventions", "/interventions", store)
app = replica.app
login = Depends(replica.operator)


def incident_row(row: sqlite3.Row) -> dict:
    data = dict(row)
    data["caller_notes"] = json.loads(data["caller_notes"] or "[]")
    data["level_label"] = level_label(data["level"])
    return data


@app.get("/interventions", response_class=HTMLResponse)
def interventions(request: Request, statut: str = "", user: str = login):
    with store.connect() as conn:
        rows = [incident_row(r) for r in conn.execute("SELECT * FROM incidents ORDER BY declared_at DESC")]
    shown = [r for r in rows if not statut or r["status"] == statut]
    counts = {OPEN: sum(r["status"] == OPEN for r in rows), CLOSED: sum(r["status"] == CLOSED for r in rows)}
    return replica.render(request, "dispatch/list.html", rows=shown, statut=statut, counts=counts,
                          statuses=[OPEN, CLOSED])


@app.get("/interventions/nouvelle", response_class=HTMLResponse)
def new_form(request: Request, user: str = login):
    return replica.render(request, "dispatch/new.html", error=None, form={}, demo_nature=demo_nature())


@app.post("/interventions/nouvelle", response_class=HTMLResponse)
def new_create(request: Request, user: str = login, adresse: str = Form(""), commune: str = Form(""),
               nature: str = Form(""), niveau: str = Form("0"), appelant: str = Form(""),
               renseignements: str = Form(""), moyens: str = Form("")):
    form = {"adresse": adresse, "commune": commune, "nature": nature, "niveau": niveau, "appelant": appelant,
            "renseignements": renseignements, "moyens": moyens}
    if not adresse.strip() or not nature.strip() or not re.fullmatch(r"-?\d{1,2}", niveau.strip()):
        return replica.render(request, "dispatch/new.html", status_code=400, form=form, demo_nature=demo_nature(),
                              error="Adresse, nature et niveau (nombre) obligatoires.")
    notes = [line.strip() for line in renseignements.splitlines() if line.strip()]
    with store.connect() as conn:
        inc_id = f"INC-{store.next_id(conn, 'incident'):04d}"
        conn.execute(
            "INSERT INTO incidents VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (inc_id, iso(utcnow()), adresse.strip(), commune.strip() or commune_of(adresse), nature.strip(),
             int(niveau), OPEN,
             appelant.strip() or "Non renseigné", "", json.dumps(notes, ensure_ascii=False), moyens.strip(),
             "CIS Centre (fictif)", None),
        )
        mc_id = f"MC-{store.next_id(conn, 'main_courante'):04d}"
        conn.execute("INSERT INTO main_courante VALUES (?,?,?,?,?)",
                     (mc_id, inc_id, iso(utcnow()), user, f"Création de l'intervention : {nature.strip()}."))
    replica.flash(request, f"Intervention {inc_id} créée.")
    return RedirectResponse(f"/interventions/{inc_id}", status_code=303)


def load_incident(inc_id: str) -> tuple[dict | None, list[dict]]:
    with store.connect() as conn:
        row = conn.execute("SELECT * FROM incidents WHERE id=?", (inc_id,)).fetchone()
        log = [dict(r) for r in conn.execute(
            "SELECT * FROM main_courante WHERE incident_id=? ORDER BY at DESC, id DESC", (inc_id,))]
    return (incident_row(row) if row else None), log


@app.get("/interventions/{inc_id}", response_class=HTMLResponse)
def incident(request: Request, inc_id: str, ajout: str = "", user: str = login):
    inc, log = load_incident(inc_id.upper())
    if not inc:
        return replica.render(request, "dispatch/missing.html", status_code=404, inc_id=inc_id)
    return replica.render(request, "dispatch/incident.html", inc=inc, log=log, added=ajout, error=None, texte="")


@app.post("/interventions/{inc_id}/main-courante", response_class=HTMLResponse)
def add_entry(request: Request, inc_id: str, texte: str = Form(""), user: str = login):
    inc, log = load_incident(inc_id.upper())
    if not inc:
        return replica.render(request, "dispatch/missing.html", status_code=404, inc_id=inc_id)
    text = texte.strip()
    if not text or len(text) > 2000:
        return replica.render(request, "dispatch/incident.html", status_code=400, inc=inc, log=log, added="",
                              texte=texte, error="Message vide ou trop long (2000 caractères maximum).")
    with store.connect() as conn:
        mc_id = f"MC-{store.next_id(conn, 'main_courante'):04d}"
        conn.execute("INSERT INTO main_courante VALUES (?,?,?,?,?)", (mc_id, inc["id"], iso(utcnow()), user, text))
    replica.flash(request, f"Entrée {mc_id} ajoutée à la main courante.")
    return RedirectResponse(f"/interventions/{inc['id']}?ajout={mc_id}#main-courante", status_code=303)
