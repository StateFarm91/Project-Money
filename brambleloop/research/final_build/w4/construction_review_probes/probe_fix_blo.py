"""What-if (in memory only, no source change): Rnd 11 worked in back loop only.

Run: cd brambleloop && PYTHONPATH=src nice -n 19 python3 research/final_build/w4/construction_review_probes/probe_fix_blo.py
"""
import dataclasses
from brambleloop.products import vessels
from brambleloop.cir.model import Op
from brambleloop.cir.compiler import compile_cir
from brambleloop.cir.twin import build_twin
from brambleloop.cir.writer import write_pattern
from brambleloop.cir.reverse import compare
from brambleloop.cir import geometry

cir = vessels.build_basket("small", version="1.3.0")
rows = cir.components[0].rows
r11 = next(r for r in rows if r.index == 11)
r11.ops = [Op("sc", 60, loop="back")]
res = compile_cir(cir)
print("ok", res.ok, [str(f) for f in res.findings])
tw = build_twin(cir, res)
print("points/flats/height", tw.across_points_cm, tw.across_flats_cm, tw.height_cm,
      "yarn", tw.yarn_metres_by_color, "sides", tw.sides)
print("loops by row 11:", {c.loop for c in tw.cells if c.row == 11})
text = write_pattern(cir, res, "US")
print([l for l in text.splitlines() if l.startswith("Rnd 1") and len(l) < 80][:3])
print("reverse:", [str(f) for f in compare(cir, text, "US")])
print("stitch total", tw.stitch_total)
