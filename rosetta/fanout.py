"""The incident fan-out Seraph sends at dispatch, against a Rosetta instance (default the test one on :8011).

    uv run python fanout.py [base_url]
"""
import sys, time
import httpx

B = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8011"
A = "96 Boulevard Bessières, 75017 Paris"
RUNS = [("dispatch.read", {"incident_id": "INC-0001"}, 10),
        ("maps.building", {"address": A, "expected_entrances": [
            {"id": "E1", "label": "Porte d'entrée, hall de l'escalier", "side": "front"},
            {"id": "E2", "label": "Porte de garage, rampe (sous-sol)", "side": "left"}]}, 8),
        ("occupants.list", {"building": "Immeuble d'habitation (maquette TU Wien)"}, 7),
        ("plan.read", {"image_path": "ifc/out/levels/L-1.svg", "level": -1}, 6),
        ("georisques.risks", {"address": A}, 4),
        ("weather.wind", {"town": "Paris"}, 3)]
t0 = time.time()
ids = {n: httpx.post(f"{B}/run", json={"endpoint": n, "params": p, "priority": pr, "allow_cache": True}).json()["run_id"]
       for n, p, pr in RUNS}
done = {}
while len(done) < len(ids) and time.time() - t0 < 200:
    for n, i in ids.items():
        if n not in done:
            r = httpx.get(f"{B}/runs/{i}").json()
            if r["status"] in ("ok", "failed"):
                done[n] = 1
                print(f"{n:18} {r['status']:6} {'live ' if r['live'] else 'CACHE'} {r.get('duration_ms', 0) / 1000:5.1f}s "
                      f"(t+{time.time() - t0:4.1f}) {(r.get('error') or '')[:70]}", flush=True)
    time.sleep(1)
print(f"all done in {time.time() - t0:.1f} s")
