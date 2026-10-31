"""Independent probe of market-basket-small@1.2.0 (read-only; changes no source).

Run: cd brambleloop && PYTHONPATH=src nice -n 19 python3 research/final_build/w4/construction_review_probes/probe_basket_small.py
"""
import hashlib, json, math
from brambleloop.products import vessels
from brambleloop.cir.compiler import compile_cir
from brambleloop.cir.twin import build_twin
from brambleloop.cir import geometry

cir = vessels.build_basket("small")
d = cir.to_dict()
for name in ("content_hash", "fingerprint"):
    v = getattr(cir, name, None)
    print(name, v() if callable(v) else v)
print("sha256(sorted to_dict json):",
      hashlib.sha256(json.dumps(d, sort_keys=True, separators=(",", ":")).encode()).hexdigest())
g = cir.gauge
print("gauge", vars(g))
res = compile_cir(cir)
print("compile ok", res.ok, "errors", [str(f) for f in res.errors])
print("warnings", [str(f) for f in res.findings if f not in res.errors])
tw = build_twin(cir, res)
print("shape", tw.shape, "sides", tw.sides, "points", tw.across_points_cm, "flats",
      tw.across_flats_cm, "height", tw.height_cm, "circ", tw.circumference_cm)
print("yarn", tw.yarn_metres_by_color, "total", round(sum(tw.yarn_metres_by_color.values()), 1))
print("loops used", {c.loop for c in tw.cells})
print("\nRnd count color  r_cm  dR_cm  h_cm  rise  growth  axial")
for row, ring in zip([r for r in res.rows], tw.geometry.rings):
    print(f"{ring.index:3d} {ring.count:4d} {row.color:5s} {ring.radius_cm:5.2f} "
          f"{ring.radius_delta_cm:6.3f} {ring.row_height_cm:5.3f} {ring.rise_cm:5.3f} "
          f"{ring.growth_ratio:5.2f} {ring.axial_cm:6.2f}")
# Independent recomputation
spc = g.stitches_per_10cm / 10; rh = 10 / g.rows_per_10cm
n = 60
per = n / spc
side = per / 6
print("\nindep: perimeter", round(per, 2), "side", round(side, 2),
      "points", round(side * 2, 2), "flats", round(side * math.sqrt(3), 2),
      "circle-d", round(per / math.pi, 2), "row h", round(rh, 3))
# Flat-hexagon criterion: hexagon apothem growth per round = (6 st/round / spc)/(6*2*tan30)
dap = (6 / spc) / 6 / (2 * math.tan(math.pi / 6))
print("hexagon apothem growth per round", round(dap, 3), "vs row height", round(rh, 3),
      "ratio", round(dap / rh, 2))
dr_circle = (6 / spc) / (2 * math.pi)
print("circle radius growth per round", round(dr_circle, 3), "ratio", round(dr_circle / rh, 2))
# Yarn by hand
sw = 10 / g.stitches_per_10cm
tot = {}
for r in res.rows:
    for op in r.ops:
        tot[r.color] = tot.get(r.color, 0) + {"sc": 6.2, "inc": 12.4}[op.stitch] * sw * op.count
print("indep yarn m", {k: round(v / 100, 1) for k, v in tot.items()})
print("finished_size_note:", cir.finished_size_note)

# Release hash, compiled text, reverse re-derivation
from brambleloop.cir.writer import write_pattern
from brambleloop.gates.certificate import _release_hash
from brambleloop.cir.reverse import compare
from brambleloop.products import launch0
c2 = launch0.cir_for("basket_small")
r2 = compile_cir(c2)
text = write_pattern(c2, r2, "US")
print("\nrelease hash (launch0.cir_for):", _release_hash(c2, text))
print("reverse findings:", [str(f) for f in compare(c2, text, "US")])
print("corners():", geometry.corners(r2.rows))
print("\n--- compiled US text ---\n" + text)
