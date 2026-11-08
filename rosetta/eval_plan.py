"""Compare plan.read's computed zones with the IFC's zones (same 0–1000 frame). uv run python eval_plan.py <run_id>"""
import json, sys
import cv2, httpx, numpy as np

r = json.load(open(sys.argv[1])) if sys.argv[1].endswith(".json") else httpx.get(f"http://localhost:8001/runs/{sys.argv[1]}").json()
b = json.load(open("../ifc/out/building.json"))
ifc = {("elevator" if x.get("kind") == "elevator" else f"room:{x['id'].split(':')[-1]}"): x["zone"] for x in b["rooms"] if x.get("level") == -1 and x.get("zone")}
for s in b["stairs"]:
    for z in s.get("zones", []):
        if z["level"] == -1:
            ifc[s["id"] if s["id"].startswith("stair:") else "stair:" + s["id"]] = z["zone"]


def mask(poly):
    m = np.zeros((1000, 1000), np.uint8)
    cv2.fillPoly(m, [np.array(poly, np.int32)], 1)
    return m


out = r["output"]
print("points:", [(p["name"], p["point"]["x"], p["point"]["y"]) for p in out["points"] if not p["name"].startswith("room:")])
for z in out["zones"]:
    want = ifc.get(z["name"])
    if not want:
        print(f"{z['name']:12} no IFC zone   also={z.get('also')}")
        continue
    a, bb = mask(z["polygon"]), mask(want)
    iou = (a & bb).sum() / max(1, (a | bb).sum())
    print(f"{z['name']:12} IoU {iou:.2f}  area {z['area_pct']}%  also={z.get('also')}")
print("ifc names:", sorted(ifc))
