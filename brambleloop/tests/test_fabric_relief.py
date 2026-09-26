"""visual.fabric.texture_signature sees relief stitches, not only unworked loops.

Found by the Product-only Visual V1 graduation benchmark (2026-09-26): the rule called the
Heirloom Cable Throw -- 18 cable columns on back-post ribbing, every loop worked -- a flat
fabric, because it measured loop targets alone. Relief is light and shadow off the stitch
geometry whether it comes from an unworked loop or from a stitch that stands off the surface.
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
from brambleloop.cir import compiler, twin as TW
from brambleloop.cir.model import CIR, Component, Gauge, Material, Op, Row
from brambleloop.products import texture as T
from brambleloop.visual import fabric as F

PASSED = FAILED = 0
def check(name, ok, detail=""):
    global PASSED, FAILED
    PASSED += bool(ok); FAILED += (not ok)
    print(("OK   " if ok else "FAIL ") + name + ("" if ok else f"  -- {detail}"))

def twin_of(cir):
    res = compiler.compile_cir(cir); assert res.ok, res.errors
    return TW.build_twin(cir, res, cir.components[0].name)

sig = F.texture_signature(twin_of(T.build_cable_throw()))
check("the cable throw reads as textured", sig["textured"], str(sig))
check("its relief stitches are the post stitches and the crossing", set(sig.get("relief_stitches", [])) == {"bpdc", "cable2x2", "fpdc"}, str(sig.get("relief_stitches")))
check("its relief stacks into columns up the rows (cable columns and ribs)", sig.get("surface") == "ridges_up_the_rows", str(sig))
check("its along-row period is the eight-stitch repeat", sig.get("period_along_row_sts") == 8, str(sig.get("period_along_row_sts")))
sig = F.texture_signature(twin_of(T.build_bobble_pillow()))
check("the bobble pillow reads as textured and checkered (the bobbles stagger)", sig["textured"] and sig.get("surface") == "checkered", str(sig))
sig = F.texture_signature(twin_of(T.build_ribbed_scarf()))
check("the ribbed scarf reads as ridges up the rows", sig["textured"] and sig.get("surface") == "ridges_up_the_rows", str(sig))
plain = CIR(slug="plain", title="Plain", version="1.0.0", construction="flat_rows", risk_class="A", colors={"c": "#FFFFFF"},
            gauge=Gauge(stitches_per_10cm=16, rows_per_10cm=18, stitch_type="sc", hook_mm=5.0),
            materials=[Material(name="y", yarn_weight="worsted", color_id="c")],
            components=[Component(name="p", construction="flat_rows", foundation=20, rows=[Row(index=i, ops=[Op("sc", 20)], declared_count=20, color="c", turning_chain=1) for i in range(1, 6)])])
sig = F.texture_signature(twin_of(plain))
check("a plain single-crochet panel still reads as flat", not sig["textured"], str(sig))
blo = CIR(slug="blo", title="Blo", version="1.0.0", construction="flat_rows", risk_class="A", colors={"c": "#FFFFFF"},
          gauge=Gauge(stitches_per_10cm=16, rows_per_10cm=18, stitch_type="sc", hook_mm=5.0),
          materials=[Material(name="y", yarn_weight="worsted", color_id="c")],
          components=[Component(name="p", construction="flat_rows", foundation=20, rows=[Row(index=i, ops=[Op("sc", 20, loop="back" if i > 1 else "both")], declared_count=20, color="c", turning_chain=1) for i in range(1, 6)])])
sig = F.texture_signature(twin_of(blo))
check("back-loop ribbing keeps its loop-target reading (unchanged behaviour)", sig["textured"] and sig.get("loop_targeted_cells", 0) > 0, str(sig))
print(f"\n  {PASSED} passing, {FAILED} failing"); sys.exit(1 if FAILED else 0)
