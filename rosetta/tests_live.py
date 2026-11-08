"""Live check: submit runs to Rosetta, wait, print results (phones masked by /runs).

    uv run python tests_live.py dispatch.read occupants.list ...   (params from PARAMS below)
"""
import json, sys, time
import httpx

BASE = "http://localhost:8001"
PARAMS = {
    "dispatch.read": {"incident_id": "INC-0001"},
    "occupants.list": {"building": "Immeuble d'habitation (maquette TU Wien)"},
    "dispatch.write_112": {"incident_id": "INC-0001", "entry_fr": "05:12 Appel OCC-03 : 2 personnes salle 3.12, fumée sous la porte."},
    "report.fill": {"incident_id": "INC-0001", "gate_id": "gate_test", "sections": {
        "chronologie": "00:00 alerte.\n00:08 arrivée FPT 1.\n00:31 feu éteint.", "moyens": "FPT 1, EPA 1, VSAV 1. Binôme 1 sous ARI.",
        "victimes": "Aucune victime. 2 personnes mises en sécurité salle 3.12.", "observations": "Porte coupe-feu efficace."}},
    "plan.read": {"image_path": "ifc/out/levels/L-1.svg", "level": -1},
}


def main():
    names = sys.argv[1:]
    extra = {}
    if names and names[-1].startswith("{"):
        extra = json.loads(names.pop())
    ids = {}
    for n in names:
        r = httpx.post(f"{BASE}/run", json={"endpoint": n, "params": {**PARAMS.get(n, {}), **extra}, "priority": 5})
        print(n, r.status_code, r.text)
        if r.status_code == 200:
            ids[n] = r.json()["run_id"]
    t0 = time.time()
    done = {}
    while len(done) < len(ids) and time.time() - t0 < 200:
        for n, i in ids.items():
            if n in done:
                continue
            r = httpx.get(f"{BASE}/runs/{i}").json()
            if r["status"] in ("ok", "failed"):
                done[n] = r
                print(f"== {n} {r['status']} live={r['live']} {r.get('duration_ms')} ms err={r.get('error')}")
                print(json.dumps(r.get("output"), ensure_ascii=False)[:1500])
                print([s["image_id"] for s in r["screenshots"]])
        time.sleep(1)


if __name__ == "__main__":
    main()
