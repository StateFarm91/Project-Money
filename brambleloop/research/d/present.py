"""Render the saved draped configurations under the presentation staging, hash-checked.

The geometry is loaded from `research/d/out/<kind>_draped.npz`, written by `milestone_d.assess`
with the sha256 of the points it measured; the render refuses to draw anything whose hash
does not match the assessment record. Nothing here moves a vertex.
"""
import hashlib, json, os, sys, time
import numpy as np
from dataclasses import replace
from brambleloop.visual import milestone_d as MD, pbr_scene as PS, drape as DR

kind = sys.argv[1]; out = sys.argv[2]; spp = int(sys.argv[3]) if len(sys.argv) > 3 else 384
tag = sys.argv[4] if len(sys.argv) > 4 else "presentation"
record = json.load(open(os.path.join(out, sys.argv[5] if len(sys.argv) > 5 else f"milestone_d_{kind}_12800_settle.json")))
hand = MD.HandTension() if os.environ.get("PRESENT_HAND") else None
cir, twin, flat, _, tex = MD.certified_swatch(kind, 5, 5, hand=hand)
z = np.load(os.path.join(out, f"{kind}_draped.npz"))
pts = z["points"]; sha = hashlib.sha256(np.ascontiguousarray(pts, dtype=np.float64).tobytes()).hexdigest()
assert sha == str(z["sha256"]) == record["geometry_sha256"]["draped"], "the saved geometry is not the assessed geometry"
draped = replace(flat, ops=DR._rewrite(flat, pts))
form = tuple(float(x) for x in z["form"])
res = {"kind": kind, "geometry_sha256": sha, "assessment": os.path.basename(record and f"milestone_d_{kind}_12800_settle.json"), "views": {}}
for view in ("camera", "oblique"):
    t = time.time()
    path = os.path.join(out, f"{kind}_draped_{tag}_{view}.png")
    r = PS.render(draped, path, view=view, spp=spp, plied_tex=tex, staging=PS.STAGING_PRESENTATION, form=form, frame=flat)
    res["views"][view] = {"path": path, "image_sha256": hashlib.sha256(open(path, "rb").read()).hexdigest(),
                          "plies": r["plied"]["plies"], "fibres": r["plied"]["fibres"], "spp": r["spp"],
                          "staging": r["staging"], "form_drawn": r["form_drawn"], "not_reproduced": r["not_reproduced"],
                          "seconds": round(time.time() - t, 1)}
    print(view, res["views"][view]["seconds"], "s", r["plied"]["fibres"], "fibres")
json.dump(res, open(os.path.join(out, f"{kind}_draped_{tag}.json"), "w"), indent=1)
