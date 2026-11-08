"""Drive the four Rosetta flows through a real browser, then read the DOM the way Rosetta's code will.

    uv run python tests/flows.py [shots_dir]

Resets the replicas before and after. Needs the replicas running (uv run python run.py).
"""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from legacy.common import env, fixture  # noqa: E402

DISPATCH, REPORT, OCCUPANTS = "http://localhost:8101", "http://localhost:8102", "http://localhost:8103"
SHOTS = Path(sys.argv[1] if len(sys.argv) > 1 else "tests/shots")


def reset(base: str, scope: str = "") -> None:
    req = urllib.request.Request(f"{base}/admin/reset{'?scope=' + scope if scope else ''}", method="POST")
    with urllib.request.urlopen(req, timeout=5) as r:
        assert json.load(r)["ok"]


def login(page: Page, base: str, start: str) -> None:
    page.goto(base + start)
    assert "/login" in page.url, page.url
    shot(page, "login-" + base[-4:])
    page.get_by_label("Identifiant").fill("operateur")
    page.get_by_label("Mot de passe").fill(env("REPLICA_PASSWORD"))
    page.get_by_role("button", name="Connexion").click()
    page.wait_for_load_state()
    assert "/login" not in page.url, "login refused"


def shot(page: Page, name: str) -> None:
    page.screenshot(path=str(SHOTS / f"{name}.png"))


def dispatch_read(page: Page) -> dict:
    login(page, DISPATCH, "/interventions")
    shot(page, "dispatch-list")
    row = page.locator("#interventions tr.inc.open").first
    row.get_by_role("link").click()
    page.wait_for_url("**/interventions/INC-*")
    shot(page, "dispatch-incident")
    out = {
        "incident_id": page.inner_text("#f-numero"),
        "address": page.inner_text("#f-adresse"),
        "nature": page.inner_text("#f-nature"),
        "level": int(page.inner_text("#f-niveau")),
        "declared_at": page.get_attribute("#f-declaree time", "datetime"),
        "caller_notes": page.locator("#notes-appelant li").all_inner_texts(),
    }
    want = fixture("endpoints/dispatch.read.json")["output"]
    assert out["incident_id"] == "INC-0001", out
    assert out["nature"] == want["nature"] and out["level"] == want["level"], out
    assert out["caller_notes"] == want["caller_notes"], out
    return out


def dispatch_write_112(page: Page) -> dict:
    entry = "01:12 Appel OCC-03 : 2 personnes salle 3.12, fumée sous la porte."
    page.goto(DISPATCH + "/interventions/INC-0001")
    page.get_by_label("Message").fill(entry)
    page.get_by_role("button", name="Ajouter").click()
    page.wait_for_selector("#flash")
    shot(page, "dispatch-main-courante")
    flash = page.inner_text("#flash")
    first = page.locator("#main-courante-liste tbody tr").first
    entry_id = first.get_attribute("data-id")
    assert entry_id in flash and first.locator(".c-texte").inner_text() == entry, (flash, entry_id)
    return {"ok": True, "entry_id": entry_id}


def occupants_list(page: Page) -> dict:
    login(page, OCCUPANTS, "/batiments")
    page.get_by_role("link", name="Bâtiment d'exercice").click()
    page.wait_for_url("**/batiments/1")
    shot(page, "occupants-building")
    rows = []
    for tr in page.locator("#occupants tbody tr[data-id]").all():
        rows.append({
            "id": tr.get_attribute("data-id"),
            "name": tr.locator(".c-nom").inner_text(),
            "phone_e164": tr.locator(".c-tel").inner_text(),
            "level": int(tr.locator(".c-niveau").inner_text()),
            "room": tr.locator(".c-local").inner_text(),
            "language": tr.locator(".c-langue").inner_text(),
        })
    seed = {o["id"]: o for o in fixture("occupants.json")["occupants"]}
    for r in rows:
        if r["id"] in seed:
            assert r == {k: seed[r["id"]][k] for k in r}, (r, seed[r["id"]])
    assert len([r for r in rows if r["id"] in seed]) == len(seed), rows
    return {"occupants": rows}


def report_fill(page: Page) -> dict:
    login(page, REPORT, "/comptes-rendus/nouveau?intervention=INC-0001")
    sections = {
        "Chronologie": "00:00 alerte. 00:08 arrivée FPT 1. 00:31 feu éteint.",
        "Moyens engagés": "FPT 1, EPA 1, VSAV 1. Binôme 1 sous ARI.",
        "Victimes": "Aucune victime. 2 personnes mises en sécurité salle 3.12.",
        "Observations": "Local technique 3e étage. Porte coupe-feu efficace.",
    }
    for label, text in sections.items():
        page.get_by_label(label + " :", exact=True).fill(text)
    shot(page, "report-form")
    page.locator("#btn-enregistrer").click()
    page.wait_for_url("**/comptes-rendus/CR-*")
    assert page.inner_text("#cr-etat") == "Brouillon"
    shot(page, "report-draft")
    page.get_by_role("button", name="Transmettre").click()
    page.wait_for_selector("#flash")
    shot(page, "report-sent")
    assert page.inner_text("#cr-etat") == "Transmis", page.inner_text("#cr-etat")
    assert page.inner_text("#cr-victimes") == sections["Victimes"]
    return {"ok": True, "report_id": page.inner_text("#cr-numero"), "url": page.url}


def inscription_phone(browser) -> dict:
    ctx = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True,
                              extra_http_headers={"X-Forwarded-For": "203.0.113.7"})
    page = ctx.new_page()
    page.goto(OCCUPANTS + "/inscription")
    shot(page, "inscription-phone")
    overflow = page.evaluate("document.documentElement.scrollWidth") > 390
    page.get_by_label("Nom et prénom").fill("Juge Démo")
    page.get_by_label("Téléphone portable").fill("06 00 00 00 42")
    page.get_by_label("Étage").select_option("3")
    page.get_by_label("Salle").fill("3.14")
    page.get_by_label("Langue de l'appel").select_option("en")
    page.get_by_role("button", name="Valider mon inscription").click()
    blocked = page.evaluate("document.querySelector('#consentement').validity.valueMissing")
    page.get_by_label("J'accepte").check()
    page.get_by_role("button", name="Valider mon inscription").click()
    page.wait_for_selector("#flash")
    shot(page, "inscription-ok")
    ref = page.inner_text("#flash")
    private = page.goto(OCCUPANTS + "/batiments").status
    ctx.close()
    assert not overflow and blocked and private == 404, (overflow, blocked, private)
    return {"ref": ref, "no_horizontal_scroll": not overflow, "consent_required": blocked, "private_pages": private}


def main() -> None:
    SHOTS.mkdir(parents=True, exist_ok=True)
    for base in (DISPATCH, REPORT):
        reset(base)
    reset(OCCUPANTS, "all")
    results = {}
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(channel="chrome")
        except Exception:
            browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        for name, flow in [("dispatch.read", dispatch_read), ("dispatch.write_112", dispatch_write_112),
                           ("occupants.list", occupants_list), ("report.fill", report_fill)]:
            try:
                results[name] = {"pass": True, "output": flow(page)}
            except Exception as exc:  # report every flow, not just the first failure
                shot(page, name + "-FAIL")
                results[name] = {"pass": False, "error": repr(exc)[:300], "url": page.url}
        try:
            results["inscription (phone)"] = {"pass": True, "output": inscription_phone(browser)}
        except Exception as exc:
            results["inscription (phone)"] = {"pass": False, "error": repr(exc)[:300]}
        browser.close()
    for base in (DISPATCH, REPORT):
        reset(base)
    reset(OCCUPANTS, "all")
    for name, r in results.items():
        out = r.get("output", {})
        if name == "occupants.list" and r["pass"]:  # never print full numbers
            out = {"occupants": [{**o, "phone_e164": o["phone_e164"][:5] + "…"} for o in out["occupants"]]}
        print(("PASS " if r["pass"] else "FAIL ") + name, json.dumps(out if r["pass"] else r, ensure_ascii=False))
    sys.exit(0 if all(r["pass"] for r in results.values()) else 1)


if __name__ == "__main__":
    main()
