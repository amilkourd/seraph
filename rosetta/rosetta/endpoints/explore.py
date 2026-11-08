"""/explore — learning a source live. Linkup finds the official pages for a question no endpoint covers, Holo
opens one and answers on screen. The answer is the model's reading: it goes back tagged « source non vérifiée »
(`verified:false`), and the full trace (`GET /runs/{id}/trace`) is what Silex turns into a learned skill."""

from __future__ import annotations

import html
import re
import time
from urllib.parse import urlparse

import httpx

from ..config import SKILLS, env, settings
from ..core import Run, RunFailed, endpoint, slug
from .common import agent

LINKUP_URL = "https://api.linkup.so/v1/search"
LINKUP_DOMAINS = ["gouv.fr", "service-public.fr", "paris.fr", "monenfant.fr", "caf.fr", "ameli.fr", "insee.fr"]

DEFAULT_START = [
    ("Annuaire de l'éducation (écoles, collèges, lycées)", "https://www.education.gouv.fr/annuaire"),
    ("Service-Public.fr (démarches, établissements publics)", "https://www.service-public.fr/"),
    ("data.gouv.fr (données publiques)", "https://www.data.gouv.fr/"),
    ("Paris.fr (équipements de la ville)", "https://www.paris.fr/"),
]
OFFICIAL = re.compile(r"(^|\.)(gouv\.fr|service-public\.fr|paris\.fr|education\.fr|ameli\.fr|insee\.fr|"
                      r"monenfant\.fr|caf\.fr|ville-[a-z-]+\.fr|mairie-[a-z-]+\.fr)$")


def starts() -> list[tuple[str, str]]:
    f = SKILLS / "_explore_start.md"
    if f.exists():
        got = re.findall(r"^-\s*(.+?)\s*:\s*(https?://\S+)", f.read_text(), re.M)
        if got:
            return got
    return DEFAULT_START


async def linkup(q: str, where: str) -> tuple[list[tuple[str, str]], str]:
    """Official pages for the question, from Linkup (web search for agents), official hosts only, at most 4.
    No key, an error or a timeout → [] and the fixed list is used; the note says which."""
    key = env("LINKUP_API_KEY")
    if not key:
        return [], "Linkup : pas de clé"
    t0 = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=12) as c:
            r = await c.post(LINKUP_URL, headers={"Authorization": f"Bearer {key}"},
                             json={"q": f"{q} — {where}", "depth": "fast", "outputType": "searchResults",
                                   "includeDomains": LINKUP_DOMAINS, "maxResults": 8})
        r.raise_for_status()
        got: list[tuple[str, str]] = []
        for it in r.json().get("results") or []:
            url = str(it.get("url") or "")
            if url.startswith("https://") and OFFICIAL.search(urlparse(url).hostname or "") and url not in {u for _, u in got}:
                got.append((re.sub(r"\s+", " ", str(it.get("name") or url))[:90], url))
    except Exception as e:                       # never the key: only the error's type
        return [], f"Linkup indisponible ({type(e).__name__})"
    got = got[:4]
    return got, f"Linkup : {len(got)} pages officielles en {int((time.monotonic() - t0) * 1000)} ms"


@endpoint(name="explore", kind="learned", access="read", timeout_s=120, cache=None, site="explore",
          source_kind="learned", source_label="source non vérifiée", params={"question_fr": "string", "hints": "string?"},
          verified=False)
async def explore(run: Run) -> dict:
    page = run.page
    q = str(run.params.get("question_fr") or "").strip()
    if not q:
        raise RunFailed("question_fr requis")
    where = settings.demo_address
    found, note = await linkup(q, where)
    items = found + [(t, u) for t, u in starts() if u not in {v for _, v in found}]
    links = "".join(f'<li style="margin:18px 0"><a style="font-size:26px" href="{html.escape(u)}">{html.escape(t)}</a></li>'
                    for t, u in items)
    title = "Sources officielles trouvées par Linkup" if found else "Sources officielles"
    await page.set_content(f'<html><body style="font-family:Arial;padding:40px"><h1>{title}</h1>'
                           f'<p style="font-size:20px">Question : {html.escape(q)}<br>Adresse : {html.escape(where)}</p>'
                           f'<ul>{links}</ul></body></html>')
    await run.frame(note if found else "choisit une source officielle", q)
    task = (f"Answer this question for the address « {where} »: « {q} ». Use only official French public websites: "
            "click the most relevant one in the list, then search and navigate it. Do not use a search engine. When a "
            "page shows the answer, call answer with one short sentence in French that states it, with the name of the "
            "place if there is one.")
    if run.params.get("hints"):
        task += f" Hints: {run.params['hints']}"

    async def verify(_: str):
        host = urlparse(page.url).hostname or ""
        if not OFFICIAL.search(host):
            return False, f"{host or 'this page'} is not an official public website from the list"
        return True, host

    res = await agent(run, task, verify, max_steps=24, hints="")
    img = await page.screenshot(type="jpeg", quality=85)
    run.add_shot("explore-01", img, f"Source trouvée : {urlparse(page.url).hostname}", "top")
    run.source["url"] = page.url
    answer = re.sub(r"\s+", " ", res.answer or "").strip()
    run.extra["summary"] = answer[:80]
    return {"answer_fr": answer, "url": page.url, "verified": False, "name_hint": "learned." + slug(q)[:40],
            "steps": res.steps, "found_by": "linkup" if found else "liste", "linkup_note": note,
            "linkup": [{"title": t, "url": u} for t, u in found]}
