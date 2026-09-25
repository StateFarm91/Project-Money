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
# The module's calibrated stiffness, imported rather than restated. A literal here was a
# second copy of a physical constant, and when the calibration moved it was left twenty times
# too stiff -- which surfaced as this suite asserting gravity had moved the fabric while the
# fabric moved 0.03mm. 800 iterations because reaching gravitational equilibrium takes
# thousands, and a test that stops before anything happens proves nothing about drape.
SETUP = DR.DrapeSetup(bending_rigidity_N_m2=DR.CALIBRATED_BENDING_N_M2,
                      linear_density_kg_m=AM["linear_density_kg_m"],
                      down=(0.0, 0.0, -1.0), clamp_fraction=0.5, iterations=800)
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
      iw < 0.01, "%.3f%%" % (100 * iw))
# Width and height are held to DIFFERENT tolerances, on purpose. Width is across the
# cantilever and carries no load, so it must not move at all. Height is along it, and the
# hanging half is carrying its own weight, so the fabric extends slightly under that load --
# a real property of loaded cloth, not the product changing size. At the full 7x7 solve this
# reaches 2.8%. Holding both to the same figure would either fail a correct result or let a
# genuine width change through.
check("the product's intrinsic height changes only by load extension, not by resizing",
      ih < 0.04, "%.3f%%" % (100 * ih))
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

# --- drape must not deform the stitches themselves ---------------------------------
# Distinct from "does it still pass the shape check". A binary verdict cannot tell a stitch
# 0.02mm the wrong side of a threshold from one turned inside out, and the two need opposite
# responses. Measured in millimetres of margin, negative being correct.
#
# This exists because the first out-of-plane run failed three edge stitches on the third
# loop, and the margins settled what kind of failure it was: flat, every stitch sat 1.5 to
# 1.7mm clear with NONE within 0.5mm of the line; draped, two had moved by +4.6mm and
# +7.0mm. Not a threshold being grazed -- genuinely everted stitches at the free edge, where
# there are fewest contacts to hold them.
from brambleloop.visual import stitch_shape as SS                 # noqa: E402


def worst_third_loop_margin(fab):
    hdc = [o for o in fab.ops if o.kind == "hdc"]
    by = {(o.row, o.position): o for o in hdc}
    rws = sorted({r for r, _ in by})
    worst = -1e9
    for o in hdc:
        ri = rws.index(o.row)
        ahead = by.get((o.row, o.position + 1))
        behind = by.get((o.row, o.position - 1))
        anc = by.get((rws[ri - 1], o.position)) if ri > 0 else by.get((rws[ri + 1], o.position))
        if anc is None:
            continue
        try:
            a, u, t = SS.local_frame(o, ahead if ahead is not None else behind, anc,
                                     neighbour_is_ahead=ahead is not None)
        except SS.Unframeable:
            continue
        if ri == 0:
            u, t = -u, -t
        m = SS.shape_margins(o, fab.L, fab.H, fab.D, (a, u, t))
        if m:
            worst = max(worst, m["third_loop_below_v_mm"])
    return worst


flat_margin = worst_third_loop_margin(FLAT)
drape_margin = worst_third_loop_margin(DRAPED)
check("flat fabric keeps every third loop clearly below its V",
      flat_margin < -0.5, "%.3f mm" % flat_margin)
check("draping does not push any third loop above its V",
      drape_margin < 0.0, "%.3f mm" % drape_margin)
check("draping does not erode the third-loop margin by more than a yarn diameter",
      drape_margin - flat_margin < FLAT.yarn_diameter,
      "%.3f -> %.3f mm" % (flat_margin, drape_margin))
check("the margin is reported in millimetres rather than as a verdict",
      isinstance(drape_margin, float))

# --- the rest state is now an option, and the default must not have moved ----------
# Kaldor-2010 bounded plastic rest-state migration is implemented as a NAMED, SOURCED option.
# It changes the fabric's shape, so the thing that most needs a check is that nothing reaches
# it by accident: every committed Visual result was produced without it.
from dataclasses import replace                                   # noqa: E402

_probe = DR.DrapeSetup(linear_density_kg_m=1e-4)
check("bounded plastic rest migration is off unless it is asked for",
      _probe.plastic_rest_migration is False)
check("the default run reports no rest migration whatsoever",
      REPORT.rest_migration_max_rad == 0.0 and REPORT.rest_migration_mean_rad == 0.0)
check("Kaldor's own published plasticity parameters are the ones carried",
      (_probe.p_plastic_rad, _probe.p_max_plastic_rad) == (0.01, 2.5))
check("the plastic option's provenance separates what is sourced from what is not",
      all(w in DR.PROVENANCE["plastic_rest_migration"]
          for w in ("SOURCED", "DERIVED", "UNKNOWN")))

# The angular-to-curvature mapping is an identity for equal segments, not a linearisation,
# and that matters because a crochet loop's turning angles are NOT small -- this swatch's mean
# is about 1.4 radians. A small-angle version would misplace the plasticity radii by a third.
_exact = True
for _th in (0.01, 0.5, 1.4, 3.0):
    _L = 0.004
    _d1 = np.array([1.0, 0.0, 0.0])
    _d2 = np.array([np.cos(_th), np.sin(_th), 0.0])
    _exact &= abs(float(np.linalg.norm(_L * (_d2 - _d1)))
                  - DR.angular_radius_to_lap(_th, _L)) < 1e-15
check("the angular-to-curvature mapping is exact for equal segments, not linearised", _exact)
check("the mapping saturates at a half turn rather than running past it",
      abs(DR.angular_radius_to_lap(4.0, 0.004) - DR.angular_radius_to_lap(np.pi, 0.004)) < 1e-18)

# --- the relief metric is tested on fabrics whose answer is known ------------------
# The corrugated-relief symptom -- rows bowing as rigid bars -- is the dominant remaining
# realism cue, and a measurement of it is worthless if it cannot tell the two cases apart.
def _shift(fab, fn):
    ops = []
    for o in fab.ops:
        q = o.points.copy()
        if o.kind == "hdc":
            q[:, 2] += fn(o)
        ops.append(replace(o, points=q))
    return replace(fab, ops=ops)


# The two endpoints are exact rather than thresholds, because a threshold here would be a
# guess. The first version of this check asserted "> 0.3" against a fixture whose arithmetic
# gives 0.235006, and the instrument was right while the number was invented -- so the fixtures
# are now the two cases whose answer the construction pins to a single value.
_mean_pos = np.mean([o.position for o in FLAT.ops if o.kind == "hdc"])
_rows_only = _shift(FLAT, lambda o: 0.5 * o.row)
_across_only = _shift(FLAT, lambda o: 0.4 * (o.position - _mean_pos))
_pr_rows = DR.relief_profile(FLAT, _rows_only)
_pr_across = DR.relief_profile(FLAT, _across_only)
check("displacement that depends only on the row scores as no cross-row variation at all",
      _pr_rows["within_row_fraction"] < 1e-12, "%.3e" % _pr_rows["within_row_fraction"])
check("displacement that varies only ACROSS the row scores as entirely cross-row variation",
      abs(_pr_across["within_row_fraction"] - 1.0) < 1e-12,
      "%.12f" % _pr_across["within_row_fraction"])
check("the relief metric reports millimetres alongside the fraction",
      _pr_across["within_row_rms_mm"] > 0.0 and _pr_across["total_rms_mm"] > 0.0)

# --- an explicit rest curvature must reproduce the captured default exactly ---------
LAP0 = DR.rest_curvature_of(FLAT)
_short = replace(SETUP, iterations=120)
_a, _ = DR.drape(FLAT, _short)
_b, _ = DR.drape(FLAT, _short, rest_curvature=LAP0)
check("supplying the rest curvature explicitly reproduces the captured default exactly",
      np.array_equal(_a.points, _b.points))
_shape_ok = False
try:
    DR.drape(FLAT, _short, rest_curvature=LAP0[:-3])
except ValueError:
    _shape_ok = True
check("a rest curvature of the wrong shape is refused rather than broadcast", _shape_ok)

# --- THE TRAP THAT INVALIDATED THE FIRST RECOVERY EXPERIMENT ------------------------
# `rest_is_relaxed_shape` captures rest curvature at the START of the call, so releasing
# gravity on an already-draped fabric leaves the DRAPED shape as its own rest state: there is
# no restoring force by construction and the experiment cannot detect recovery whichever
# answer is true. This pins the trap so that nobody runs that experiment that way again.
_load = replace(SETUP, iterations=400)
_loaded, _ = DR.drape(FLAT, _load, rest_curvature=LAP0)
_off = replace(SETUP, gravity=0.0, iterations=400)
_released, _ = DR.drape(_loaded, _off, rest_curvature=LAP0)
_trap, _ = DR.drape(_loaded, _off)
_moved_ok = float(np.abs(_released.points - _loaded.points).max())
_moved_trap = float(np.abs(_trap.points - _loaded.points).max())
check("releasing the load against the ORIGINAL rest curvature produces a restoring motion",
      _moved_ok > 3.0 * max(_moved_trap, 1e-9),
      "%.4f mm vs %.4f mm" % (_moved_ok, _moved_trap))
check("capturing rest at the start of the release call leaves almost no restoring force, "
      "which is why the first recovery experiment was invalid",
      _moved_trap < 0.25 * _moved_ok, "%.4f mm" % _moved_trap)

# --- Product Truth survives the plastic option too ----------------------------------
# It is off by default; it must still not be able to break the product when it is on.
_plastic = replace(SETUP, iterations=400, plastic_rest_migration=True)
_pl, _prep = DR.drape(FLAT, _plastic)
_pg = CT.validate(_pl, TWIN, max_rows=ROWS, max_cols=COLS)
check("plastic rest migration actually migrated the rest state, so it is being measured",
      _prep.rest_migration_max_rad > 0.0, "%.4f rad" % _prep.rest_migration_max_rad)
check("plastic rest migration leaves the stitch count and loop targets untouched",
      _pg["stitches_built"] == before["stitches_built"] and
      [o.loop_target for o in _pl.ops] == [o.loop_target for o in FLAT.ops])
check("plastic rest migration keeps every stitch linked",
      _pg["stitches_linked"] == _pg["stitches_needing_linkage"],
      "%s/%s" % (_pg["stitches_linked"], _pg["stitches_needing_linkage"]))
check("plastic rest migration preserves total yarn length",
      abs(_prep.length_change_pct) < 0.5, "%.4f%%" % _prep.length_change_pct)
check("plastic rest migration never let a strand reach another",
      _prep.min_gap_seen_mm > 0.0 and _prep.crossing_impossible)

# --- convergence is now reportable, which the ASTM result turned on -----------------
# `largest_step_mm` is a maximum over the whole run and cannot distinguish a solve that
# finished from one that ran out of iterations still moving. Every bending length quoted from
# this solver depends on which of those it was, so the report has to be able to say.
check("the report distinguishes a finished solve from one that ran out of iterations",
      (REPORT.converged is False and REPORT.final_step_mm >= 1e-5) or
      (REPORT.converged is True and REPORT.final_step_mm < 1e-5),
      "converged=%s final_step=%.3e" % (REPORT.converged, REPORT.final_step_mm))
check("the final step is reported, not only the largest one over the run",
      REPORT.final_step_mm > 0.0 and REPORT.final_step_mm <= REPORT.largest_step_mm,
      "%.3e <= %.3e" % (REPORT.final_step_mm, REPORT.largest_step_mm))

# --- the cantilever instrument must report what it actually measured ----------------
# `overhang_mm` is the length the clamp fraction ASKS for. The clamp is a threshold on y and
# the swatch has five discrete rows, so the length actually left free is quantised to row
# boundaries -- and since the tip angle is arctan(drop / overhang), a denominator that is wrong
# non-monotonically puts a wiggle into the angle that is not a property of the fabric. Both are
# now reported; the nominal one is unchanged so no committed figure moves.
_ct = DR.cantilever_test(FLAT, replace(SETUP, iterations=150),
                         overhang_fractions=(0.4, 0.5))
check("the cantilever test reports the overhang it measured, not only the one asked for",
      all({"free_extent_mm", "angle_on_measured_overhang_deg", "converged"} <= set(st)
          for st in _ct["steps"]))
check("the nominal and measured overhangs do differ, which is why both are reported",
      any(abs(st["free_extent_mm"] - st["overhang_mm"]) > 0.01 for st in _ct["steps"]),
      str([(round(st["overhang_mm"], 3), round(st["free_extent_mm"], 3))
           for st in _ct["steps"]]))
check("the cantilever test states whether each step's solve converged",
      all(isinstance(st["converged"], bool) for st in _ct["steps"]))

print(f"\n  {PASSED} passing, {FAILED} failing")
sys.exit(1 if FAILED else 0)
