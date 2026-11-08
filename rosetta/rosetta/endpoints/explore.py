"""/explore — learning a source live. Holo answers a question no endpoint covers, from an official public site,
on screen. The answer is the model's reading: it goes back tagged « source non vérifiée » (`verified:false`), and the
full trace (`GET /runs/{id}/trace`) is what Silex turns into a learned skill."""

from __future__ import annotations

import html
import re
from urllib.parse import urlparse

from ..config import SKILLS, settings
from ..core import Run, RunFailed, endpoint, slug
from .common import agent

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


@endpoint(name="explore", kind="learned", access="read", timeout_s=120, cache=None, site="explore",
          source_kind="learned", source_label="source non vérifiée", params={"question_fr": "string", "hints": "string?"},
          verified=False)
async def explore(run: Run) -> dict:
    page = run.page
    q = str(run.params.get("question_fr") or "").strip()
    if not q:
        raise RunFailed("question_fr requis")
    where = settings.demo_address
    links = "".join(f'<li style="margin:18px 0"><a style="font-size:26px" href="{html.escape(u)}">{html.escape(t)}</a></li>'
                    for t, u in starts())
    await page.set_content(f'<html><body style="font-family:Arial;padding:40px"><h1>Sources officielles</h1>'
                           f'<p style="font-size:20px">Question : {html.escape(q)}<br>Adresse : {html.escape(where)}</p>'
                           f'<ul>{links}</ul></body></html>')
    await run.frame("choisit une source officielle", q)
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
            "steps": res.steps}
