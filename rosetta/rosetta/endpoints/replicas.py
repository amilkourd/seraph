"""The replicas (software we don't own, no API): dispatch, building manager, report.

Code logs in; Holo navigates; code verifies the page and reads the DOM. Exact texts (main courante entry, report
sections) are typed by code through `type_param` where Holo chose the field: the model never retypes data.
"""

from __future__ import annotations

import re
import unicodedata

from ..config import settings
from ..core import Run, RunFailed, endpoint
from .common import agent, replica_login, text

D, R, O = settings.dispatch_url, settings.report_url, settings.occupants_url


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "").replace("’", "'")
    return re.sub(r"\s+", " ", s).strip()


def fold(s: str) -> str:
    return unicodedata.normalize("NFKD", norm(s)).encode("ascii", "ignore").decode().lower()


# ───────── dispatch.read ─────────
@endpoint(name="dispatch.read", kind="replica", access="read", timeout_s=30, cache=None, site="dispatch",
          source_kind="dispatch", source_label="alerte", params={"incident_id": "string?"})
async def dispatch_read(run: Run) -> dict:
    page = run.page
    want = (run.params.get("incident_id") or "").strip()
    await replica_login(run, D, "/interventions")
    if not want:                                   # code reads the list: the newest « En cours »
        want = await text(page, "#interventions tr.inc.open a")
    task = (f"Open intervention {want} from the list of interventions. "
            "When its detail page is displayed, answer with its number, address, nature and level.")

    async def verify(_: str):
        m = re.search(r"/interventions/(INC-\d+)", page.url)
        if not m:
            return False, "not on an intervention detail page"
        if m.group(1) != want:
            return False, f"opened {m.group(1)}, expected {want}"
        return await page.locator("#f-numero").count() > 0, "detail page"

    await agent(run, task, verify, max_steps=8)
    img = await page.screenshot(type="jpeg", quality=85)
    run.add_shot("dispatch-01", img, f"Fiche intervention {want} (logiciel d'alerte)", "top")
    level_txt = await text(page, "#f-niveau")
    out = {
        "incident_id": await text(page, "#f-numero"),
        "address": await text(page, "#f-adresse"),
        "commune": await text(page, "#f-commune"),
        "nature": await text(page, "#f-nature"),
        "level": int(level_txt) if re.fullmatch(r"-?\d+", level_txt) else None,
        "declared_at": await page.get_attribute("#f-declaree time", "datetime"),
        "caller_notes": [norm(t) for t in await page.locator("#notes-appelant li").all_inner_texts()],
    }
    run.source["url"] = page.url
    run.extra["summary"] = f"{out['incident_id']} · {out['nature']}"
    return out


# ───────── occupants.list ─────────
@endpoint(name="occupants.list", kind="replica", access="read", timeout_s=30, cache=None, site="occupants",
          source_kind="occupants", source_label="gestionnaire", params={"building": "string"})
async def occupants_list(run: Run) -> dict:
    page = run.page
    await replica_login(run, O, "/batiments")
    links = page.locator("a[href^='/batiments/']")
    names = [norm(t) for t in await links.all_inner_texts()]
    hrefs = [await links.nth(i).get_attribute("href") for i in range(await links.count())]
    if not names:
        raise RunFailed("aucun bâtiment dans le logiciel du gestionnaire")
    asked = fold(run.params.get("building") or "")
    pick = next((i for i, n in enumerate(names) if fold(n) == asked), None)
    if pick is None:                               # the manager names buildings its own way: one match or « exercice »
        pick = 0 if len(names) == 1 else next((i for i, n in enumerate(names) if "exercice" in fold(n)), 0)
    name, href = names[pick], hrefs[pick]
    task = f"Open the building « {name} » and display its occupant table. Answer with the number of occupants listed."

    async def verify(_: str):
        if not page.url.rstrip("/").endswith(href):
            return False, f"not on the page of « {name} »"
        n = await page.locator("#occupants tbody tr[data-id]").count()
        return n > 0, f"{n} occupants"

    await agent(run, task, verify, max_steps=8)
    img = await page.screenshot(type="jpeg", quality=85)       # phones are CSS-blurred on screen (rule 5)
    run.add_shot("occupants-01", img, "Liste des occupants (logiciel du gestionnaire)", "top")
    rows = []
    for tr in await page.locator("#occupants tbody tr[data-id]").all():
        async def cell(c: str) -> str:
            loc = tr.locator(c)
            return norm(await loc.inner_text()) if await loc.count() else ""
        lvl = await cell(".c-niveau")
        rows.append({"id": await tr.get_attribute("data-id"), "name": await cell(".c-nom"),
                     "phone_e164": re.sub(r"[^\d+]", "", await cell(".c-tel")),
                     "level": int(lvl) if re.fullmatch(r"-?\d+", lvl) else None, "room": await cell(".c-local"),
                     "language": await cell(".c-langue") or "fr", "notes": await cell(".c-notes"),
                     "origin": await cell(".c-origine")})
    run.source["url"] = page.url
    run.extra["summary"] = f"{len(rows)} occupants · numéros lus dans le DOM, masqués à l'écran"
    return {"occupants": rows, "building": name}


# ───────── dispatch.write_112 ─────────
@endpoint(name="dispatch.write_112", kind="replica", access="write", timeout_s=30, cache=None, site="dispatch",
          source_kind="dispatch", source_label="alerte", params={"incident_id": "string", "entry_fr": "string"})
async def dispatch_write_112(run: Run) -> dict:
    page = run.page
    inc = (run.params.get("incident_id") or "").strip()
    entry = norm(run.params.get("entry_fr") or "")
    if not inc or not entry:
        raise RunFailed("incident_id et entry_fr requis")
    await replica_login(run, D, f"/interventions/{inc}")
    rows = page.locator("#main-courante-liste tbody tr")
    before = await rows.first.get_attribute("data-id") if await rows.count() else None
    task = (f"On this intervention page ({inc}), in the « Main courante » section, click the « Message » field, "
            "type the parameter entry_fr with type_param, then click « Ajouter ». Answer once the entry appears in the list.")

    async def verify(_: str):
        if not await rows.count():
            return False, "main courante is empty"
        first = rows.first
        rid = await first.get_attribute("data-id")
        got = norm(await first.locator(".c-texte").inner_text())
        if rid == before:
            return False, "no new entry in the main courante yet"
        return got == entry, f"{rid}: {got[:60]}"

    await agent(run, task, verify, params={"entry_fr": entry}, max_steps=10, forbid=frozenset({"write"}))
    img = await page.screenshot(type="jpeg", quality=85)
    rid = await rows.first.get_attribute("data-id")
    run.add_shot(f"dispatch-{(rid or 'mc').lower()}", img, f"Main courante : entrée {rid} ajoutée", "top")
    run.source["url"] = page.url
    run.extra["summary"] = f"{rid} ajoutée"
    return {"ok": True, "entry_id": rid}


# ───────── report.fill (gated) ─────────
SECTIONS = ["chronologie", "moyens", "victimes", "observations"]


@endpoint(name="report.fill", kind="replica", access="write, gated", timeout_s=120, cache=None, site="report",
          source_kind="dispatch", source_label="compte rendu",
          params={"incident_id": "string", "gate_id": "string", "sections": "{chronologie, moyens, victimes, observations}"})
async def report_fill(run: Run) -> dict:
    if not run.params.get("gate_id"):
        raise RunFailed("refusé : pas de gate_id (l'envoi du rapport passe par « confirmez »)")
    page = run.page
    inc = (run.params.get("incident_id") or "").strip().upper()
    if not re.fullmatch(r"INC-\d{4}", inc):
        raise RunFailed(f"incident_id invalide ({inc or 'vide'})")
    sec = run.params.get("sections") or {}
    values = {k: (sec.get(k) or "").strip() or "Néant." for k in SECTIONS}
    # the list's « Nouveau compte rendu » button names one fixed intervention: code opens the form for this one
    await replica_login(run, R, f"/comptes-rendus/nouveau?intervention={inc}")
    task = (f"This is a new compte rendu for intervention {inc}. The « Numéro de l'intervention » field must hold "
            f"{inc} (if it does not, type the parameter intervention there with type_param). Fill the four sections, "
            "each with type_param: « Chronologie » = chronologie, « Moyens engagés » = moyens, « Victimes » = victimes, "
            "« Observations » = observations. Click « Enregistrer », then on the next page click « Transmettre ». "
            "Answer when the état shows « Transmis ».")

    async def wrong() -> list[str]:
        """What the saved compte rendu on screen gets wrong: its intervention, then each section."""
        loc = page.locator("#cr-intervention")
        bad = [] if await loc.count() and norm(await loc.inner_text()).upper() == inc else ["intervention"]
        for k in SECTIONS:
            loc = page.locator(f"#cr-{k}")
            if not await loc.count() or norm(await loc.inner_text()) != norm(values[k]):
                bad.append(k)
        return bad

    async def verify(_: str):
        if await page.locator("#cr-etat").count() == 0:
            return False, "not on a saved compte rendu"
        etat = await text(page, "#cr-etat")
        diffs = await wrong()
        if diffs:
            return False, f"fields that differ from what was asked: {', '.join(diffs)}"
        return etat == "Transmis", f"état = {etat}"

    async def guard(call) -> str | None:
        """« Transmettre » is irreversible: code checks the saved intervention and sections before letting the click through."""
        if call.tool_name not in ("click", "double_click"):
            return None
        btn = page.locator("#btn-transmettre")
        if not await btn.count():
            return None
        box = await btn.first.bounding_box()
        x, y = call.x / 1000 * 1280, call.y / 1000 * 800
        if not box or not (box["x"] - 12 <= x <= box["x"] + box["width"] + 12 and box["y"] - 12 <= y <= box["y"] + box["height"] + 12):
            return None
        bad = await wrong()
        if bad:
            return (f"this draft does not hold the requested values ({', '.join(bad)}); do not transmit it. "
                    "Click « Modifier » and fix those fields with type_param, then save again.")
        return None

    await agent(run, task, verify, params={**values, "intervention": inc}, max_steps=30, guard=guard,
                forbid=frozenset({"write"}))
    img = await page.screenshot(type="jpeg", quality=85)
    rid = await text(page, "#cr-numero")
    run.add_shot("report-01", img, f"Compte rendu {rid} transmis", "top")
    run.source["url"] = page.url
    run.extra["summary"] = f"{rid} transmis"
    return {"ok": True, "report_id": rid, "url": page.url}
