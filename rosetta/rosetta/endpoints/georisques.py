"""georisques.risks — georisques.gouv.fr « Connaître les risques près de chez moi ». Holo fills the address and picks
the suggestion; code checks the report page and reads the risks from the DOM."""

from __future__ import annotations

import re


from ..core import Run, RunFailed, endpoint
from .common import agent
from .maps import ban

NATUREL = re.compile(r"inondation|séisme|seisme|argile|cavit|mouvement|feu de forêt|feux de forêt|avalanche|radon|"
                     r"submersion|recul du trait|volcan|cyclone|tempête|érosion", re.I)
TECHNO = re.compile(r"industriel|nucléaire|nucleaire|canalisation|transport de matières|rupture de barrage|minier|"
                    r"pollution|installation|icpe|seveso|sols pollués|engins de guerre", re.I)


@endpoint(name="georisques.risks", kind="real", access="read", timeout_s=45, cache="golden", site="georisques",
          source_kind="georisques", source_label="Géorisques", params={"address": "string"},
          cache_key=lambda p: str(p.get("address") or ""))
async def georisques_risks(run: Run) -> dict:
    page = run.page
    address = str(run.params.get("address") or "").strip()
    b = await ban(address)
    if not b or b["score"] < 0.75:
        run.extra["cacheable"] = False
        raise RunFailed(f"adresse introuvable dans la Base Adresse Nationale ({address}"
                        + (f" ; plus proche : {b['label']}" if b else "") + ")")
    await page.goto("https://www.georisques.gouv.fr/", wait_until="domcontentloaded", timeout=15000)
    await page.wait_for_timeout(800)
    task = (f"Find the natural and technological risks for the address « {address} ». If a cookie banner is shown, "
            "click « Refuser » first. Click the « Adresse exacte » field, type the address, click the matching "
            "suggestion in the list that appears, then click « Accéder à mes risques ». Answer when the page listing "
            "the risks for this address is displayed.")

    async def verify(_: str):
        await page.wait_for_timeout(800)
        url = page.url
        if "georisques.gouv.fr" not in url or not re.search(r"rapport|mes-risques/connaitre", url):
            return False, "the risks report page is not open"
        lat = re.search(r"[?&]lat=(-?\d+\.\d+)", url)
        lon = re.search(r"[?&]lon=(-?\d+\.\d+)", url)
        if lat and lon and (abs(float(lat.group(1)) - b["lat"]) > 0.01 or abs(float(lon.group(1)) - b["lng"]) > 0.01):
            return False, "the report is for another place than the address"
        body = await page.inner_text("body")
        return bool(NATUREL.search(body) or TECHNO.search(body)), "risks page"

    await agent(run, task, verify, max_steps=14)
    await page.wait_for_timeout(1500)
    img = await page.screenshot(type="jpeg", quality=85)
    run.add_shot("georisques-01", img, f"Géorisques : risques à {b['label']}", "top")
    risks = await extract(page)
    run.source["url"] = page.url
    run.extra["summary"] = ", ".join(r["label"] for r in risks[:4]) or "aucun risque lu"
    return {"risks": risks, "url": page.url, "address_ban": b["label"]}


async def extract(page) -> list[dict]:
    """Code reads the report: risk cards' titles, kept only when they name a known risk family."""
    titles = await page.evaluate("""() => {
      const out = [];
      document.querySelectorAll('h2, h3, h4, .fr-card__title, .fr-tile__title, [class*="risque"] [class*="titre"], [class*="risk"] [class*="title"]').forEach(e => {
        const t = (e.innerText || '').trim();
        if (t && t.length < 120) out.push(t);
      });
      return out;
    }""")
    seen, risks = set(), []
    for t in titles:
        t1 = re.sub(r"\s+", " ", t).strip()
        k = t1.lower()
        if k in seen or re.search(r"^(risques? (naturels?|technologiques?)|mes risques|connaître|que faire)", k):
            continue
        cat = "naturel" if NATUREL.search(t1) else "technologique" if TECHNO.search(t1) else None
        if cat:
            seen.add(k)
            risks.append({"label": t1, "category": cat})
    return risks
