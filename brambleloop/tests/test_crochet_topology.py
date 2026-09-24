"""Crochet topology: does the yarn geometry actually correspond to the certified stitches?

Every test here exists because the thing it checks was once wrong and the validator caught
it. They are regression tests in the literal sense.
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

import numpy as np
from brambleloop.cir import benchmarks as B
from brambleloop.cir.compiler import compile_cir
from brambleloop.cir.twin import build_twin
from brambleloop.visual import crochet_topology as CT

PASSED = FAILED = 0


def check(name, cond, detail=""):
    global PASSED, FAILED
    # "OK  " at the start of the line, not "PASS". run_tests.sh counts a suite's passes
    # with grep -c '^OK', and counts a suite that exits clean while reporting none as a
    # failure -- deliberately, because nine files once printed a different marker and their
    # results silently stopped reaching the headline total for a whole session. These three
    # files did exactly that again: 44 passes absent from a total of 3213, and two suites
    # reported failing that were green.
    if cond:
        PASSED += 1
        print("OK  ", name)
    else:
        FAILED += 1
        print("FAIL", name, detail)


def swatch(rows, cols, settled=True):
    c = B.cardigan("S")
    t = build_twin(c, compile_cir(c), component="body")
    f = CT.build(t, c.gauge, max_rows=rows, max_cols=cols)
    if settled:
        f = CT.settle(f)
    return f, t


print("crochet topology")

f, t = swatch(6, 8)
v = CT.validate(f, t, max_rows=6, max_cols=8)

check("stitch count matches the CIR", v["stitches_built"] == v["stitches_expected"],
      f"{v['stitches_built']} vs {v['stitches_expected']}")
check("loop targets match the CIR", v["loop_targets_match_cir"] is True)
check("no stitch passes beside the loop below", not v.get("unlinked"),
      str(v.get("unlinked")))

# Every stitch is measured. The both-loop case used to be unmeasurable and was reported as
# such; it is now measured by linking number and must actually link.
check("every stitch's linkage is measurable", v["stitches_unmeasurable"] == 0)
check("every stitch is linked",
      v["stitches_linked"] == v["stitches_needing_linkage"],
      f"{v['stitches_linked']} of {v['stitches_needing_linkage']}")

# A stitch is drawn through the loop below exactly once. Any other number is a different
# stitch: 0 is yarn that went in and came back out, 2 was a bowtie ring counting one
# crossing twice.
check("every linking number is exactly one, in one sense or the other",
      set(v["linking_numbers"]) <= {-1, 1}, str(v["linking_numbers"]))

# --- interpenetration ---------------------------------------------------------
# The dive that carries a stitch around the loop below clears it by a yarn diameter. Sized
# purely as a fraction of the row height it passed within 0.53mm of a 2mm strand.
check("no two strands interpenetrate",
      v["closest_non_adjacent_mm"] >= f.yarn_diameter * 0.45,
      f"{v['closest_non_adjacent_mm']}mm at {f.yarn_diameter}mm yarn")

raw, _ = swatch(6, 8, settled=False)
vr = CT.validate(raw, t, max_rows=6, max_cols=8)
check("clearance is built in, not relaxed in afterwards",
      vr["closest_non_adjacent_mm"] > 0.6,
      f"{vr['closest_non_adjacent_mm']}mm before settling")

# --- settling preserves linkage ----------------------------------------------
# It did not. Uniform rest lengths dragged strands out of their loops (15 linked -> 0), and
# once the grid search was fixed blind repulsion pushed them out again (15 -> 5). Both were
# caught here.
check("settling does not destroy linkage",
      v["stitches_linked"] >= vr["stitches_linked"],
      f"{vr['stitches_linked']} before, {v['stitches_linked']} after")
check("settling relieves contact", v["closest_non_adjacent_mm"] > vr["closest_non_adjacent_mm"])

# --- loop spans ---------------------------------------------------------------
# Both spans once ran a point long. The extra point on the front loop is the run-off to the
# next stitch, which doubles back in x and made the strand a hairpin, so every front-loop
# stitch read as unlinked.
cell, spans = CT._hdc_cell(6.9, 10.5, 3.8, 1, "both", 0.0, 2.0)
for nm in ("front_loop", "back_loop"):
    a, b = spans[nm]
    check(f"{nm} span is the loop alone", b - a == 1, f"span {spans[nm]}")
fl = cell[spans["front_loop"][0]:spans["front_loop"][1] + 1]
check("the front loop does not double back on itself",
      np.ptp(fl[:, 0]) > 0 and len(fl) == 2)

# --- scale --------------------------------------------------------------------
# A 4x5 swatch contains no front-loop stitches at all. The first "15 of 15 linked" was
# measured on a sample that could not contain the case that was broken.
small, _ = swatch(4, 5)
targets = {o.loop_target for o in small.ops if o.kind == "hdc"}
big, _ = swatch(14, 16)
big_targets = {o.loop_target for o in big.ops if o.kind == "hdc"}
check("the small swatch is not representative", "front" not in targets)
check("the large swatch exercises every loop target",
      big_targets == {"front", "back", "both"}, str(big_targets))

vb = CT.validate(big, t, max_rows=14, max_cols=16)
check("no unlinked stitches at scale", not vb.get("unlinked"), str(vb.get("unlinked")))
check("no interpenetration at scale",
      vb["closest_non_adjacent_mm"] >= big.yarn_diameter * 0.45)

# --- continuity ---------------------------------------------------------------
check("the yarn is one path", vb["total_points"] > 0)
check("turning chains join the rows", vb["turning_chains"] >= 1)

# --- semantic coverage --------------------------------------------------------
# The guard against the mistake that hid defect 4: a fixture that does not contain a case
# cannot have tested it.
cov_small = CT.coverage(small)
cov_big = CT.coverage(big)
check("coverage reports the small swatch incomplete", not cov_small["complete"])
check("coverage names what the small swatch is missing",
      "loop_target_front" in cov_small["missing"], str(cov_small["missing"]))
check("the large fixture covers every semantic state", cov_big["complete"],
      str(cov_big["missing"]))
check("every loop target is exercised in both working directions",
      cov_big["loop_target_x_direction"] == 6, str(cov_big["loop_target_x_direction"]))

# --- reconciliation with the certified pattern --------------------------------
c = B.cardigan("S")
i = B.SIZES.index("S")
total = sum(build_twin(c, compile_cir(c), component=comp.name).stitch_total
            * {"sleeve": 2, "pocket": 2}.get(comp.name, 1) for comp in c.components)
expected_mm = B.YARN_G[i] * 2.25 * 1000.0 / total
rec = CT.reconciles_with_gauge(big, t, c.gauge, expected_mm_per_stitch=expected_mm)
check("stitch pitch matches the certified gauge", rec["pitch_matches_gauge"],
      f"{rec['stitch_pitch_mm']} vs {rec['expected_pitch_mm']}")
check("row height matches the certified gauge", rec["row_height_matches_gauge"],
      f"{rec['row_height_mm']} vs {rec['expected_row_height_mm']}")
check("yarn per stitch is the right order of magnitude",
      rec["yarn_per_stitch_is_the_right_order"],
      f"ratio {rec.get('yarn_vs_pattern_ratio')}")

# --- shape --------------------------------------------------------------------
check("every stitch is shaped like a half double crochet",
      vb["stitches_shaped_like_hdc"] == vb["stitches_built"],
      str(vb.get("misshapen")))

print(f"\n  {PASSED} passing, {FAILED} failing")
sys.exit(1 if FAILED else 0)
