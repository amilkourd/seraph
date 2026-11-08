"""Comptes rendus (:8102): the intervention report software. Brouillon → Transmis."""

from __future__ import annotations

import re
import sqlite3

from fastapi import Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from .common import DATA, Replica, Store, ago, fmt_local, iso, utcnow
from .dispatch import HISTORY

SCHEMA = """
DROP TABLE IF EXISTS meta;
DROP TABLE IF EXISTS reports;
CREATE TABLE meta (k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE reports (
  id TEXT PRIMARY KEY, incident_id TEXT, address TEXT, nature TEXT, incident_at TEXT, author TEXT, fonction TEXT,
  status TEXT, created_at TEXT, updated_at TEXT, transmitted_at TEXT,
  chronologie TEXT, moyens TEXT, victimes TEXT, observations TEXT
);
"""

DRAFT, SENT = "Brouillon", "Transmis"
SECTIONS = [
    ("chronologie", "Chronologie"),
    ("moyens", "Moyens engagés"),
    ("victimes", "Victimes"),
    ("observations", "Observations"),
]
FONCTIONS = ["COS", "Chef de groupe", "Chef d'agrès", "Chef de colonne"]
INCIDENT_RE = re.compile(r"INC-\d{4}")


def seed(conn: sqlite3.Connection, keep_public: bool) -> None:
    conn.executescript(SCHEMA)
    for inc_id, minutes, address, nature, level, means in HISTORY:
        sent = ago(minutes - 120)
        conn.execute(
            "INSERT INTO reports VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (inc_id.replace("INC", "CR"), inc_id, address, nature, ago(minutes), "operateur", "Chef d'agrès", SENT,
             ago(minutes - 90), sent, sent,
             "Départ, arrivée sur les lieux, reconnaissance, fin d'intervention.", means,
             "Aucune victime.", "RAS."),
        )
    conn.execute("INSERT INTO meta VALUES ('report', '1')")


store = Store("report", SCHEMA, seed)
replica = Replica("report", "Comptes rendus d'intervention", "/comptes-rendus", store)
app = replica.app
login = Depends(replica.operator)


def dispatch_row(sql: str, args: tuple = ()) -> sqlite3.Row | None:
    """One row of the dispatch software's database, read-only. None if it isn't there."""
    path = DATA / "dispatch.db"
    if not path.exists():
        return None
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=2)
        conn.row_factory = sqlite3.Row
        row = conn.execute(sql, args).fetchone()
        conn.close()
    except sqlite3.Error:
        return None
    return row


def newest_open_incident() -> str:
    """The incident « Nouveau compte rendu » opens: the newest « En cours » in dispatch, else none."""
    row = dispatch_row("SELECT id FROM incidents WHERE status='En cours' ORDER BY declared_at DESC LIMIT 1")
    return row["id"] if row else ""


def dispatch_incident(inc_id: str) -> dict:
    """Identification fields come from the dispatch software, read-only (« champs grisés »). {} if unknown."""
    row = dispatch_row("SELECT address, commune, nature, declared_at FROM incidents WHERE id=?", (inc_id,))
    if not row:
        return {}
    address, commune = row["address"], row["commune"] or ""
    if commune and commune.lower() not in address.lower():
        address = f"{address}, {commune}"
    return {"address": address,
            "nature": row["nature"], "incident_at": row["declared_at"]}


def get_report(cr_id: str) -> dict | None:
    with store.connect() as conn:
        row = conn.execute("SELECT * FROM reports WHERE id=?", (cr_id.upper(),)).fetchone()
    return dict(row) if row else None


@app.get("/comptes-rendus", response_class=HTMLResponse)
def reports(request: Request, etat: str = "", numero: str = "", user: str = login):
    sql, args = "SELECT * FROM reports WHERE 1=1", []
    if etat:
        sql += " AND status=?"
        args.append(etat)
    if numero.strip():
        sql += " AND (id LIKE ? OR incident_id LIKE ?)"
        args += [f"%{numero.strip()}%"] * 2
    with store.connect() as conn:
        rows = [dict(r) for r in conn.execute(sql + " ORDER BY created_at DESC LIMIT 100", args)]
    return replica.render(request, "report/list.html", rows=rows, etat=etat, numero=numero, states=[DRAFT, SENT],
                          newest=newest_open_incident())


def form_context(values: dict, error: str | None = None) -> dict:
    return {"r": values, "sections": SECTIONS, "fonctions": FONCTIONS, "error": error}


@app.get("/comptes-rendus/nouveau", response_class=HTMLResponse)
def new_form(request: Request, intervention: str = "", user: str = login):
    inc_id = intervention.strip().upper()
    ident = dispatch_incident(inc_id) if inc_id else {}
    values = {"id": None, "incident_id": inc_id, "author": user, "fonction": "COS", **ident}
    error = unknown(inc_id) if inc_id and not ident else None
    return replica.render(request, "report/form.html", status_code=404 if error else 200,
                          **form_context(values, error))


def unknown(inc_id: str) -> str:
    return f"Intervention {inc_id} inconnue dans le logiciel d'alerte."


def read_form(incident_id: str, fonction: str, sections: dict[str, str]) -> tuple[dict, str | None]:
    inc_id = incident_id.strip().upper()
    values = {"incident_id": inc_id, "fonction": fonction if fonction in FONCTIONS else "COS",
              **{k: v.strip() for k, v in sections.items()}}
    if not INCIDENT_RE.fullmatch(inc_id):
        return values, "N° d'intervention invalide (format INC-0000)."
    if not dispatch_incident(inc_id):
        return values, unknown(inc_id)
    return values, None


@app.post("/comptes-rendus/nouveau", response_class=HTMLResponse)
def new_save(request: Request, user: str = login, intervention: str = Form(""), fonction: str = Form("COS"),
             chronologie: str = Form(""), moyens: str = Form(""), victimes: str = Form(""),
             observations: str = Form("")):
    values, error = read_form(intervention, fonction, {"chronologie": chronologie, "moyens": moyens,
                                                       "victimes": victimes, "observations": observations})
    ident = dispatch_incident(values["incident_id"])
    if error:
        return replica.render(request, "report/form.html", status_code=400,
                              **form_context({"id": None, "author": user, **ident, **values}, error))
    now = iso(utcnow())
    with store.connect() as conn:
        cr_id = f"CR-{store.next_id(conn, 'report'):04d}"
        conn.execute(
            "INSERT INTO reports VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (cr_id, values["incident_id"], ident.get("address", ""), ident.get("nature", ""),
             ident.get("incident_at"), user, values["fonction"], DRAFT, now, now, None,
             values["chronologie"], values["moyens"], values["victimes"], values["observations"]),
        )
    replica.flash(request, f"Compte rendu {cr_id} enregistré. État : {DRAFT}.")
    return RedirectResponse(f"/comptes-rendus/{cr_id}", status_code=303)


@app.get("/comptes-rendus/{cr_id}", response_class=HTMLResponse)
def view(request: Request, cr_id: str, user: str = login):
    report = get_report(cr_id)
    if not report:
        return replica.render(request, "report/missing.html", status_code=404, cr_id=cr_id)
    return replica.render(request, "report/view.html", r=report, sections=SECTIONS, error=None)


@app.get("/comptes-rendus/{cr_id}/modifier", response_class=HTMLResponse)
def edit_form(request: Request, cr_id: str, user: str = login):
    report = get_report(cr_id)
    if not report:
        return replica.render(request, "report/missing.html", status_code=404, cr_id=cr_id)
    if report["status"] != DRAFT:
        return replica.render(request, "report/view.html", status_code=409, r=report, sections=SECTIONS,
                              error="Compte rendu transmis : modification impossible.")
    return replica.render(request, "report/form.html", **form_context(report))


@app.post("/comptes-rendus/{cr_id}/modifier", response_class=HTMLResponse)
def edit_save(request: Request, cr_id: str, user: str = login, intervention: str = Form(""),
              fonction: str = Form("COS"), chronologie: str = Form(""), moyens: str = Form(""),
              victimes: str = Form(""), observations: str = Form("")):
    report = get_report(cr_id)
    if not report:
        return replica.render(request, "report/missing.html", status_code=404, cr_id=cr_id)
    if report["status"] != DRAFT:
        return replica.render(request, "report/view.html", status_code=409, r=report, sections=SECTIONS,
                              error="Compte rendu transmis : modification impossible.")
    values, error = read_form(intervention or report["incident_id"], fonction,
                              {"chronologie": chronologie, "moyens": moyens, "victimes": victimes,
                               "observations": observations})
    if error:
        return replica.render(request, "report/form.html", status_code=400, **form_context({**report, **values}, error))
    with store.connect() as conn:
        conn.execute(
            "UPDATE reports SET incident_id=?, fonction=?, chronologie=?, moyens=?, victimes=?, observations=?, "
            "updated_at=? WHERE id=?",
            (values["incident_id"], values["fonction"], values["chronologie"], values["moyens"], values["victimes"],
             values["observations"], iso(utcnow()), report["id"]),
        )
    replica.flash(request, f"Compte rendu {report['id']} enregistré. État : {DRAFT}.")
    return RedirectResponse(f"/comptes-rendus/{report['id']}", status_code=303)


@app.post("/comptes-rendus/{cr_id}/transmettre", response_class=HTMLResponse)
def transmit(request: Request, cr_id: str, user: str = login):
    report = get_report(cr_id)
    if not report:
        return replica.render(request, "report/missing.html", status_code=404, cr_id=cr_id)
    if report["status"] == SENT:
        return RedirectResponse(f"/comptes-rendus/{report['id']}", status_code=303)
    missing = [label for key, label in SECTIONS if not (report[key] or "").strip()]
    if missing:
        return replica.render(request, "report/view.html", status_code=400, r=report, sections=SECTIONS,
                              error="Transmission impossible, sections obligatoires vides : " + ", ".join(missing) + ".")
    now = iso(utcnow())
    with store.connect() as conn:
        conn.execute("UPDATE reports SET status=?, transmitted_at=?, updated_at=? WHERE id=?",
                     (SENT, now, now, report["id"]))
    replica.flash(request, f"Compte rendu {report['id']} transmis le {fmt_local(now)}.")
    return RedirectResponse(f"/comptes-rendus/{report['id']}", status_code=303)
