"""Gestion des occupants (:8103): the building manager's software, plus the public /inscription page for judges."""

from __future__ import annotations

import sqlite3

from fastapi import Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from .common import (Replica, Store, building_model, demo_address, demo_commune, fixture, iso, level_label, mask_phone,
                     normalize_phone, utcnow)

SCHEMA = """
DROP TABLE IF EXISTS meta;
DROP TABLE IF EXISTS buildings;
DROP TABLE IF EXISTS occupants;
DROP TABLE IF EXISTS access_log;
CREATE TABLE meta (k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE buildings (id INTEGER PRIMARY KEY, name TEXT, address TEXT, commune TEXT, levels TEXT, manager TEXT);
CREATE TABLE occupants (
  id TEXT PRIMARY KEY, seq INTEGER, building_id INTEGER, name TEXT, phone_e164 TEXT, level INTEGER, room TEXT,
  language TEXT, notes TEXT, source TEXT, consent_at TEXT, created_at TEXT, updated_at TEXT
);
CREATE TABLE access_log (id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT, user TEXT, action TEXT, detail TEXT, ip TEXT);
"""

MANAGER, PUBLIC = "Gestionnaire", "Inscription QR"
LANGUAGES = [("fr", "Français"), ("en", "English"), ("es", "Español")]
LIVING = ("chambre", "séjour-cuisine")
MAX_PUBLIC = 200
CONSENT = "J'accepte d'être appelé(e) par l'assistant vocal pendant la démonstration"


def floor_name(level: int) -> str:
    return {0: "RDC", 1: "1er étage"}.get(level, f"{level}e étage" if level > 0 else f"Sous-sol {level_label(level)}")


def levels() -> list[tuple[int, str]]:
    """Floors of the building Seraph loads (IFC), else R+0..R+5."""
    found = sorted(l["level"] for l in building_model().get("levels", []))
    return [(n, floor_name(n)) for n in (found or range(6))]


def living_rooms() -> list[tuple[int, str, list[tuple[str, str]]]]:
    """Bedrooms and living rooms per floor, with the IFC's room ids, so Seraph can place each judge."""
    by_level: dict[int, list[tuple[str, str]]] = {}
    for room in building_model().get("rooms", []):
        if room.get("use") in LIVING and room.get("level", -1) >= 0:
            by_level.setdefault(room["level"], []).append((room["id"], room.get("label") or room["id"]))
    return [(n, floor_name(n), sorted(by_level[n])) for n in sorted(by_level)]


def seed(conn: sqlite3.Connection, keep_public: bool) -> None:
    kept: list[tuple] = []
    if keep_public and conn.execute("SELECT 1 FROM sqlite_master WHERE name='occupants'").fetchone():
        kept = [tuple(r) for r in conn.execute("SELECT * FROM occupants WHERE source=?", (PUBLIC,))]
    conn.executescript(SCHEMA)
    data = fixture("occupants.json")
    floors = [n for n, _ in levels()]
    conn.execute("INSERT INTO buildings VALUES (1, ?, ?, ?, ?, 'Gestionnaire (fictif)')",
                 (data["building"], demo_address(), demo_commune(),
                  f"{level_label(floors[0])} à {level_label(floors[-1])}"))
    now = iso(utcnow())
    for o in data["occupants"]:
        conn.execute("INSERT INTO occupants VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (o["id"], int(o["id"].split("-")[1]), 1, o["name"], o["phone_e164"], o["level"], o["room"],
                      o["language"], o.get("notes", ""), MANAGER, None, now, now))
    conn.executemany("INSERT INTO occupants VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", kept)
    conn.execute("INSERT INTO meta VALUES ('seeded_at', ?)", (now,))
    conn.execute("INSERT INTO access_log (at, user, action, detail, ip) VALUES (?,?,?,?,?)",
                 (now, "admin", "Réinitialisation", f"{len(kept)} inscription(s) conservée(s)", "local"))


store = Store("occupants", SCHEMA, seed)
replica = Replica("occupants", "Gestion des occupants", "/batiments", store,
                  public_paths=("/inscription",), reset_scopes=True)
app = replica.app
login = Depends(replica.operator)


def log_access(conn: sqlite3.Connection, request: Request, user: str, action: str, detail: str = "") -> None:
    ip = request.client.host if request.client else ""
    conn.execute("INSERT INTO access_log (at, user, action, detail, ip) VALUES (?,?,?,?,?)",
                 (iso(utcnow()), user, action, detail, ip))


def next_occupant(conn: sqlite3.Connection) -> tuple[str, int]:
    seq = (conn.execute("SELECT max(seq) FROM occupants").fetchone()[0] or 0) + 1
    return f"OCC-{seq:02d}", seq


def phone_parts(e164: str) -> tuple[str, str, str]:
    """Split for display: the middle digits are blurred on screen, the DOM text keeps the full number."""
    if len(e164) < 8:
        return e164, "", ""
    return e164[:5], e164[5:-2], e164[-2:]


def check_occupant(name: str, phone: str, level: str, room: str, language: str) -> tuple[dict, str | None]:
    values = {"name": name.strip(), "phone_raw": phone.strip(), "level": level.strip(), "room": room.strip(),
              "language": language.strip()}
    e164 = normalize_phone(phone)
    if not values["name"] or len(values["name"]) > 80:
        return values, "Nom obligatoire (80 caractères maximum)."
    if not e164:
        return values, "Numéro de téléphone invalide."
    if values["level"] not in {str(n) for n, _ in levels()}:
        return values, "Niveau invalide."
    if not values["room"] or len(values["room"]) > 20:
        return values, "Local obligatoire (20 caractères maximum)."
    if values["language"] not in {code for code, _ in LANGUAGES}:
        return values, "Langue invalide."
    values["phone_e164"] = e164
    return values, None


def ctx() -> dict:
    with store.connect() as conn:
        row = conn.execute("SELECT name FROM buildings WHERE id=1").fetchone()
    return {"languages": LANGUAGES, "levels": levels(), "rooms": living_rooms(), "phone_parts": phone_parts,
            "building_name": row["name"] if row else ""}


@app.get("/batiments", response_class=HTMLResponse)
def buildings(request: Request, user: str = login):
    with store.connect() as conn:
        rows = [dict(r) for r in conn.execute(
            "SELECT b.*, (SELECT count(*) FROM occupants o WHERE o.building_id=b.id) AS n FROM buildings b ORDER BY id")]
    return replica.render(request, "occupants/buildings.html", rows=rows)


def building_page(request: Request, building_id: int, user: str, status_code: int = 200,
                  form: dict | None = None, error: str | None = None, log: bool = True) -> HTMLResponse:
    with store.connect() as conn:
        building = conn.execute("SELECT * FROM buildings WHERE id=?", (building_id,)).fetchone()
        if not building:
            return replica.render(request, "occupants/missing.html", status_code=404, what=f"Bâtiment {building_id}")
        rows = [dict(r) for r in conn.execute(
            "SELECT * FROM occupants WHERE building_id=? ORDER BY level, room, seq", (building_id,))]
        if log:
            log_access(conn, request, user, "Consultation liste des occupants", f"{building['name']} ({len(rows)})")
    return replica.render(request, "occupants/building.html", status_code=status_code, b=dict(building), rows=rows,
                          form=form or {"language": "fr", "level": "0"}, error=error, **ctx())


@app.get("/batiments/{building_id}", response_class=HTMLResponse)
def building(request: Request, building_id: int, user: str = login):
    return building_page(request, building_id, user)


@app.post("/batiments/{building_id}/occupants", response_class=HTMLResponse)
def add_occupant(request: Request, building_id: int, user: str = login, nom: str = Form(""),
                 telephone: str = Form(""), niveau: str = Form(""), local: str = Form(""),
                 langue: str = Form("fr"), notes: str = Form("")):
    values, error = check_occupant(nom, telephone, niveau, local, langue)
    values["notes"] = notes.strip()[:200]
    if error:
        return building_page(request, building_id, user, 400, values, error, log=False)
    now = iso(utcnow())
    with store.connect() as conn:
        occ_id, seq = next_occupant(conn)
        conn.execute("INSERT INTO occupants VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (occ_id, seq, building_id, values["name"], values["phone_e164"], int(values["level"]),
                      values["room"], values["language"], values["notes"], MANAGER, None, now, now))
        log_access(conn, request, user, "Ajout occupant", occ_id)
    replica.flash(request, f"Occupant {occ_id} ajouté.")
    return RedirectResponse(f"/batiments/{building_id}#occupants", status_code=303)


def get_occupant(occ_id: str) -> dict | None:
    with store.connect() as conn:
        row = conn.execute("SELECT * FROM occupants WHERE id=?", (occ_id.upper(),)).fetchone()
    return dict(row) if row else None


@app.get("/batiments/{building_id}/occupants/{occ_id}/modifier", response_class=HTMLResponse)
def edit_form(request: Request, building_id: int, occ_id: str, user: str = login):
    occ = get_occupant(occ_id)
    if not occ:
        return replica.render(request, "occupants/missing.html", status_code=404, what=f"Occupant {occ_id}")
    form = {**occ, "phone_raw": occ["phone_e164"], "level": str(occ["level"])}
    return replica.render(request, "occupants/edit.html", o=occ, form=form, error=None, building_id=building_id,
                          **ctx())


@app.post("/batiments/{building_id}/occupants/{occ_id}/modifier", response_class=HTMLResponse)
def edit_save(request: Request, building_id: int, occ_id: str, user: str = login, nom: str = Form(""),
              telephone: str = Form(""), niveau: str = Form(""), local: str = Form(""), langue: str = Form("fr"),
              notes: str = Form("")):
    occ = get_occupant(occ_id)
    if not occ:
        return replica.render(request, "occupants/missing.html", status_code=404, what=f"Occupant {occ_id}")
    values, error = check_occupant(nom, telephone, niveau, local, langue)
    values["notes"] = notes.strip()[:200]
    if error:
        return replica.render(request, "occupants/edit.html", status_code=400, o=occ, form=values, error=error,
                              building_id=building_id, **ctx())
    with store.connect() as conn:
        conn.execute("UPDATE occupants SET name=?, phone_e164=?, level=?, room=?, language=?, notes=?, updated_at=? "
                     "WHERE id=?", (values["name"], values["phone_e164"], int(values["level"]), values["room"],
                                    values["language"], values["notes"], iso(utcnow()), occ["id"]))
        log_access(conn, request, user, "Modification occupant", occ["id"])
    replica.flash(request, f"Occupant {occ['id']} modifié.")
    return RedirectResponse(f"/batiments/{building_id}#occupants", status_code=303)


@app.post("/batiments/{building_id}/occupants/{occ_id}/supprimer")
def delete(request: Request, building_id: int, occ_id: str, user: str = login):
    with store.connect() as conn:
        conn.execute("DELETE FROM occupants WHERE id=?", (occ_id.upper(),))
        log_access(conn, request, user, "Suppression occupant", occ_id.upper())
    replica.flash(request, f"Occupant {occ_id.upper()} supprimé.")
    return RedirectResponse(f"/batiments/{building_id}#occupants", status_code=303)


@app.get("/journal", response_class=HTMLResponse)
def journal(request: Request, user: str = login):
    with store.connect() as conn:
        rows = [dict(r) for r in conn.execute("SELECT * FROM access_log ORDER BY id DESC LIMIT 200")]
    return replica.render(request, "occupants/journal.html", rows=rows)


# ---------- public: judges opt in from the QR code ----------

@app.get("/inscription", response_class=HTMLResponse)
def signup_form(request: Request):
    return replica.render(request, "occupants/inscription.html", form={"language": "fr", "level": ""}, error=None,
                          consent=CONSENT, **ctx())


@app.post("/inscription", response_class=HTMLResponse)
def signup(request: Request, nom: str = Form(""), telephone: str = Form(""), niveau: str = Form(""),
           local: str = Form(""), langue: str = Form("fr"), consentement: str = Form("")):
    rooms = {rid: (n, label) for n, _, items in living_rooms() for rid, label in items}
    if rooms:
        niveau = str(rooms[local][0]) if local in rooms else ""
    values, error = check_occupant(nom, telephone, niveau, local, langue)
    if rooms and local not in rooms:
        error = "Choisissez une pièce dans la liste."
    if not error and consentement != "oui":
        error = "Cochez la case de consentement pour vous inscrire."
    if error:
        return replica.render(request, "occupants/inscription.html", status_code=400, form=values, error=error,
                              consent=CONSENT, **ctx())
    now = iso(utcnow())
    with store.connect() as conn:
        existing = conn.execute("SELECT id FROM occupants WHERE phone_e164=? AND source=?",
                                (values["phone_e164"], PUBLIC)).fetchone()
        if existing:
            occ_id = existing["id"]
            conn.execute("UPDATE occupants SET name=?, level=?, room=?, language=?, consent_at=?, updated_at=? "
                         "WHERE id=?", (values["name"], int(values["level"]), values["room"], values["language"],
                                        now, now, occ_id))
        else:
            if conn.execute("SELECT count(*) FROM occupants WHERE source=?", (PUBLIC,)).fetchone()[0] >= MAX_PUBLIC:
                return replica.render(request, "occupants/inscription.html", status_code=429, form=values,
                                      error="Inscriptions closes.", consent=CONSENT, **ctx())
            occ_id, seq = next_occupant(conn)
            conn.execute("INSERT INTO occupants VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                         (occ_id, seq, 1, values["name"], values["phone_e164"], int(values["level"]), values["room"],
                          values["language"], "", PUBLIC, now, now, now))
        log_access(conn, request, "public", "Inscription (consentement)", occ_id)
    return replica.render(request, "occupants/inscription_ok.html", occ_id=occ_id, name=values["name"],
                          phone=mask_phone(values["phone_e164"]), floor=floor_name(int(values["level"])),
                          room=rooms.get(values["room"], (0, values["room"]))[1], **ctx())
