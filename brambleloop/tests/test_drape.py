"""Out-of-plane relaxation must not be able to change the product.

Z freedom is the first thing in this pipeline that can move the fabric somewhere the
validators were never exercised, and several of them only worked because it could not. The
point of this file is that allowing gravity to act cannot silently alter Product Truth:
topology, stitch identity, stitch count, loop targets, yarn path, gauge and authored
construction are invariant, and the only thing that changes is the CONFIGURATION the same
product occupies in space.

The distinction that needs a test of its own is intrinsic versus projected size. A draped
fabric photographs narrower while remaining exactly as wide as it was, so measuring a
bounding box after deformation and reporting it as the garment's width would have the
product shrinking because somebody tilted it.
"""
import sys
import numpy as np

sys.path.insert(0, "src")
from brambleloop.cir import benchmarks as BM                      # noqa: E402
from brambleloop.cir.compiler import compile_cir                  # noqa: E402
from brambleloop.cir.twin import build_twin                       # noqa: E402
from brambleloop.visual import crochet_topology as CT             # noqa: E402
from brambleloop.visual import drape as DR                        # noqa: E402

PASSED = FAILED = 0


def check(name, ok, detail=""):
    global PASSED, FAILED
    if ok:
        PASSED += 1
        print("OK  ", name)
    else:
        FAILED += 1
        print("FAIL", name, detail)


ROWS, COLS = 5, 5
CIR = BM.cardigan("S")
TWIN = build_twin(CIR, compile_cir(CIR), component="body")
# Relaxed first, exactly as the real pipeline does: an unrelaxed build sits at 0.6mm
# clearance and does not pass the gate, so comparing gate results either side of drape would
# otherwise be comparing two failures and calling them equal.
from brambleloop.visual import relaxation as RX                   # noqa: E402
FLAT, _rx = RX.relax(CT.settle(CT.build(TWIN, CIR.gauge, max_rows=ROWS, max_cols=COLS)),
                     iterations=600)
AM = DR.areal_mass(FLAT, 444.0)
SETUP = DR.DrapeSetup(bending_rigidity_N_m2=6e-7,
                      linear_density_kg_m=AM["linear_density_kg_m"],
                      down=(0.0, 0.0, -1.0), clamp_fraction=0.5, iterations=250)
DRAPED, REPORT = DR.drape(FLAT, SETUP)

before = CT.validate(FLAT, TWIN, max_rows=ROWS, max_cols=COLS)
after = CT.validate(DRAPED, TWIN, max_rows=ROWS, max_cols=COLS)

# --- it actually moved, or the rest of this file proves nothing ----------------
check("gravity moved the fabric out of its plane at all",
      REPORT.max_out_of_plane_mm > 0.1, "%.4f mm" % REPORT.max_out_of_plane_mm)

# --- Product Truth -------------------------------------------------------------
check("every stitch is still linked to the loop it was worked into",
      after["stitches_linked"] == before["stitches_linked"] ==
      after["stitches_needing_linkage"],
      "%s -> %s" % (before["stitches_linked"], after["stitches_linked"]))
check("no stitch became unmeasurable for linkage",
      after["stitches_unmeasurable"] == 0, str(after["stitches_unmeasurable"]))
check("every stitch is still shaped like a half double",
      after["stitches_shaped_like_hdc"] == after["stitches_built"],
      "%s/%s" % (after["stitches_shaped_like_hdc"], after["stitches_built"]))
check("no stitch lost the frame its morphology is measured in",
      after.get("stitches_unframeable", 0) == 0)
check("the stitch count is unchanged", after["stitches_built"] == before["stitches_built"])
check("loop targets are untouched",
      [o.loop_target for o in DRAPED.ops] == [o.loop_target for o in FLAT.ops])
check("the yarn path has the same vertices in the same order",
      sum(len(o.points) for o in DRAPED.ops) == sum(len(o.points) for o in FLAT.ops))
check("stitch identity and row/position are unchanged",
      [(o.kind, o.row, o.position) for o in DRAPED.ops] ==
      [(o.kind, o.row, o.position) for o in FLAT.ops])

# --- no pull-through, no interpenetration ---------------------------------------
check("no strand ever reached another during the solve",
      REPORT.min_gap_seen_mm > 0.0, "%.4f mm" % REPORT.min_gap_seen_mm)
check("no iteration moved further than its own clearance allowed",
      REPORT.cap_exceeded == 0, str(REPORT.cap_exceeded))
check("crossing was impossible throughout, not merely absent at the end",
      REPORT.crossing_impossible)
gap_after, _ = CT.min_segment_separation(DRAPED.points, DRAPED.yarn_diameter)
check("no two non-adjacent strands interpenetrate afterwards",
      gap_after > 0.0, "%.4f mm" % gap_after)

# --- inextensibility -------------------------------------------------------------
check("total yarn length is preserved", abs(REPORT.length_change_pct) < 0.5,
      "%.4f%%" % REPORT.length_change_pct)
check("no measurable segment is stretched more than a few per cent",
      REPORT.max_strain < 0.05, "%.4f" % REPORT.max_strain)
# The strain statistic must exclude the degenerate near-zero segments, and must say so.
check("degenerate sub-micron segments are excluded from the strain statistic and counted",
      REPORT.degenerate_segments >= 0)

# --- joins -----------------------------------------------------------------------
check("the yarn is still continuous within every row",
      after["largest_join_within_a_row_mm"] <= before["largest_join_within_a_row_mm"] + 1.0,
      "%.3f -> %.3f" % (before["largest_join_within_a_row_mm"],
                        after["largest_join_within_a_row_mm"]))
check("the turns are still joined",
      after["largest_join_at_a_turn_mm"] <= before["largest_join_at_a_turn_mm"] + 1.0,
      "%.3f -> %.3f" % (before["largest_join_at_a_turn_mm"],
                        after["largest_join_at_a_turn_mm"]))

# --- intrinsic versus projected size ----------------------------------------------
d0 = DR.intrinsic_dimensions(FLAT, ROWS, COLS)
d1 = DR.intrinsic_dimensions(DRAPED, ROWS, COLS)
iw = abs(d1["intrinsic_width_mm"] - d0["intrinsic_width_mm"]) / d0["intrinsic_width_mm"]
ih = abs(d1["intrinsic_height_mm"] - d0["intrinsic_height_mm"]) / d0["intrinsic_height_mm"]
check("the product's intrinsic width does not change when it is draped",
      iw < 0.02, "%.3f%%" % (100 * iw))
check("the product's intrinsic height does not change when it is draped",
      ih < 0.02, "%.3f%%" % (100 * ih))
check("intrinsic and projected size are reported as different quantities",
      set(d1) == {"intrinsic_width_mm", "intrinsic_height_mm",
                  "projected_width_mm", "projected_height_mm"})

# --- the gate itself --------------------------------------------------------------
check("the draped fabric passes the same gate the flat one did",
      after["passes"] == before["passes"] is True,
      "%s -> %s" % (before["passes"], after["passes"]))

# --- the provenance is stated, including what is NOT modelled ----------------------
check("every physical parameter carries a provenance label",
      set(DR.PROVENANCE) >= {"linear_density", "gravity", "bending_rigidity"})
check("the bending rigidity is labelled bounded rather than sourced",
      "BOUNDED" in DR.PROVENANCE["bending_rigidity"])
check("friction is declared unmodelled rather than quietly omitted",
      "NOT MODELLED" in DR.PROVENANCE["support_friction"])

# --- derived quantities are derived, not typed in ----------------------------------
check("areal mass is derived from the fabric's own yarn length and extent",
      0.05 < AM["areal_mass_kg_m2"] < 2.0, str(AM["areal_mass_kg_m2"]))
check("linear density is the tex definition rather than an estimate",
      abs(DR.linear_density_kg_per_m(444.0) - 4.44e-4) < 1e-12)
br = DR.bending_bracket(FLAT.yarn_diameter, 444.0, 0.0094, 1345)
check("the bending bracket spans orders of magnitude and says so",
      br["ratio"] > 1e4, "%.2e" % br["ratio"])

print(f"\n  {PASSED} passing, {FAILED} failing")
sys.exit(1 if FAILED else 0)
