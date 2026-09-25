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
from brambleloop.visual import linkage as LK                      # noqa: E402

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

# =====================================================================================
# WAVE 3 -- frame invariance, and the instruments that replace the cantilever inversion.
#
# The thread running through all of it: a bending length is supposed to be a property of the
# CLOTH. Three things were found not to be, and each has a check here that fails if the
# finding stops being true.
# =====================================================================================

# --- the co-rotational rotation is a rotation, and it is the right one ----------------
_ang = 0.7
_ax = np.array([0.3, 0.5, 0.81])
_ax = _ax / np.linalg.norm(_ax)
_K = np.array([[0.0, -_ax[2], _ax[1]], [_ax[2], 0.0, -_ax[0]], [-_ax[1], _ax[0], 0.0]])
_Q = np.eye(3) + np.sin(_ang) * _K + (1.0 - np.cos(_ang)) * (_K @ _K)
_P = FLAT.points.astype(float)
_R = DR.corotational_rotations(_P @ _Q.T, _P)
check("the co-rotational rotation recovers a known rigid rotation at every interior vertex",
      float(np.abs(_R[1:-1] - _Q).max()) < 1e-8,
      "%.3e" % float(np.abs(_R[1:-1] - _Q).max()))
check("every co-rotational rotation is orthogonal with determinant +1",
      float(np.abs(np.einsum("nij,nkj->nik", _R, _R) - np.eye(3)).max()) < 1e-8 and
      float(np.abs(np.linalg.det(_R) - 1.0).max()) < 1e-8)

# --- THE DEFECT: the documented bending energy is not invariant under rotation ---------
# Turning a finished piece of cloth round deforms nothing. A material energy must read zero.
# This one does not, and the size of what it reads is the size of a stiffness against turning
# that no yarn has. The check states the measured number so that a change to it is visible.
_resp = DR.rigid_motion_response(FLAT)
_by_angle = {r["angle_deg"]: r for r in _resp["rotations"]}
check("the bending energy is invariant under pure translation",
      _resp["translation_energy_J"] < 1e-24, "%.3e J" % _resp["translation_energy_J"])
check("the world-space rest state charges real energy for a rigid ROTATION, which is the "
      "defect", _by_angle[5.0]["world_rest_energy_J"] > 1e-8,
      "%.4e J at 5 deg" % _by_angle[5.0]["world_rest_energy_J"])
# "Big enough to matter" needs a scale that is not invented. The one that is already in this
# file is the droop the standard solve produces: if turning a stitch a few degrees costs the
# same order of gravitational work as the entire drape, then the spurious stiffness is not a
# correction to the mechanics, it IS the mechanics. Same order is a factor of ten either way,
# which is the definition rather than a threshold; the measured ratio is printed so the
# number is visible instead of the verdict.
_ratio = _by_angle[5.0]["equivalent_lift_per_vertex_mm"] / max(REPORT.max_out_of_plane_mm, 1e-9)
check("the spurious energy is of the same order as the whole gravitational drive: turning "
      "one stitch 5 degrees costs what lifting it a good fraction of the drape costs",
      0.1 < _ratio < 10.0,
      "%.4f mm of lift per stitch against %.4f mm of droop, ratio %.3f"
      % (_by_angle[5.0]["equivalent_lift_per_vertex_mm"], REPORT.max_out_of_plane_mm, _ratio))
check("it grows quadratically with the angle, so it is a spring and not an offset",
      abs(_by_angle[1.0]["world_rest_energy_J"] /
          _by_angle[0.5]["world_rest_energy_J"] - 4.0) < 0.02,
      "%.4f" % (_by_angle[1.0]["world_rest_energy_J"] /
                _by_angle[0.5]["world_rest_energy_J"]))
check("carrying the rest state into the vertex frame removes it to machine precision",
      all(r["frame_invariant_energy_J"] < 1e-20 for r in _resp["rotations"]),
      "%.3e J worst" % max(r["frame_invariant_energy_J"] for r in _resp["rotations"]))

# --- the imposed-curvature instrument, and what it needs to be believed ---------------
# The wrap has to be a bend and not a stretch, or the energy is measuring the wrong thing.
_grid = np.zeros((40, 3))
_grid[:, 1] = np.linspace(0.0, 60.0, 40)
_bent_grid = DR.cylindrical_bend(_grid, 2.0, "wale")
_l0 = np.linalg.norm(np.diff(_grid, axis=0), axis=1)
_l1 = np.linalg.norm(np.diff(_bent_grid, axis=0), axis=1)
check("the cylindrical wrap is an isometry of the midsurface to 1e-6",
      float(np.abs(_l1 / _l0 - 1.0).max()) < 1e-6,
      "%.3e" % float(np.abs(_l1 / _l0 - 1.0).max()))
check("the wrap really does curve the midsurface rather than translate it",
      float(np.ptp(_bent_grid[:, 2])) > 0.5,
      "%.4f mm of rise" % float(np.ptp(_bent_grid[:, 2])))

_g = DR.flexural_rigidity(FLAT, 444.0, along="wale", frame_invariant=True, yarn_only=False)
check("the imposed-curvature rigidity is independent of the curvature imposed, so a single "
      "rigidity describes the model", _g["curvature_independent_to"] < 1.01,
      "%.5f over a 4x sweep" % _g["curvature_independent_to"])
check("the wrap's residual strain on the yarn's own thickness is reported and small",
      0.0 < _g["max_segment_strain"] < 0.01, "%.3e" % _g["max_segment_strain"])
check("the bending length follows ASTM's own relation G = W g c^3, with W measured off this "
      "fabric rather than looked up",
      abs(_g["flexural_rigidity_N_m"] /
          (_g["areal_mass_kg_m2"] * DR.STANDARD_GRAVITY *
           (_g["bending_length_mm"] * 1e-3) ** 3) - 1.0) < 1e-9)

# --- THE CONSEQUENCE: with the world rest state, "bending length" depends on how much
# --- cloth you measured. With frame invariance it does not. -----------------------------
# A settled but unrelaxed fabric is used for the second size, because this is a property of
# the energy rather than of the relaxation, and a 600-iteration relax on 1500 vertices costs
# 45 seconds to prove something that does not depend on it.
_BIG = CT.settle(CT.build(TWIN, CIR.gauge, max_rows=9, max_cols=9))
_SMALL = CT.settle(CT.build(TWIN, CIR.gauge, max_rows=5, max_cols=5))
check("the two swatches really are different sizes",
      len(_BIG.points) > 2.5 * len(_SMALL.points),
      "%d vs %d vertices" % (len(_BIG.points), len(_SMALL.points)))
_w_small = DR.flexural_rigidity(_SMALL, frame_invariant=False, yarn_only=False)["bending_length_mm"]
_w_big = DR.flexural_rigidity(_BIG, frame_invariant=False, yarn_only=False)["bending_length_mm"]
_f_small = DR.flexural_rigidity(_SMALL, frame_invariant=True, yarn_only=False)["bending_length_mm"]
_f_big = DR.flexural_rigidity(_BIG, frame_invariant=True, yarn_only=False)["bending_length_mm"]
check("with the world-space rest state the bending length grows with the size of the "
      "swatch, so it is not a property of the fabric",
      _w_big > 1.25 * _w_small, "%.3f mm -> %.3f mm" % (_w_small, _w_big))
check("with frame invariance the same measurement is size independent to under 1 per cent",
      abs(_f_big / _f_small - 1.0) < 0.01, "%.3f mm vs %.3f mm" % (_f_small, _f_big))

# --- re-deriving B in code, and the conditions the derivation holds under ---------------
_d = DR.derive_bending_rigidity(FLAT, 444.0, target_bending_length_mm=DR.TARGET_BENDING_LENGTH_MM,
                                along="wale", frame_invariant=True, yarn_only=False)
check("the derivation is declared usable only when the rigidity it inverts is a material "
      "property", _d["derivable"] is True, str(_d["derivable"]))
_check = DR.flexural_rigidity(FLAT, 444.0, along="wale", frame_invariant=True,
                              yarn_only=False,
                              bending_rigidity_N_m2=_d["derived_bending_rigidity_N_m2"])
check("re-running the instrument at the derived B lands on the calibration target",
      abs(_check["bending_length_mm"] / DR.TARGET_BENDING_LENGTH_MM - 1.0) < 1e-6,
      "%.6f mm against a target of %.1f mm"
      % (_check["bending_length_mm"], DR.TARGET_BENDING_LENGTH_MM))
check("the derived B disagrees with the committed constant, and the factor is reported "
      "rather than applied", _d["factor_on_committed_value"] > 2.0,
      "%.2fx -> %.4e N m^2" % (_d["factor_on_committed_value"],
                               _d["derived_bending_rigidity_N_m2"]))
check("the derived B stays inside the published bracket it has to live in",
      br["lower_free_fibres_N_m2"] < _d["derived_bending_rigidity_N_m2"]
      < br["upper_solid_rod_N_m2"],
      "%.3e in [%.3e, %.3e]" % (_d["derived_bending_rigidity_N_m2"],
                                br["lower_free_fibres_N_m2"], br["upper_solid_rod_N_m2"]))
check("the derivation refuses to certify itself when frame invariance is off",
      DR.derive_bending_rigidity(FLAT, frame_invariant=False)["derivable"] is False)
check("the derivation carries every condition it holds under, not just an answer",
      {"along", "curvature_per_m", "frame_invariant", "yarn_only", "vertices_used",
       "max_segment_strain", "curvature_independent_to", "areal_mass_kg_m2",
       "target_bending_length_mm", "reference_bending_rigidity_N_m2"} <= set(_d))
# The fabric is not isotropic and the instrument must be able to say so.
_dc = DR.derive_bending_rigidity(FLAT, along="course", frame_invariant=True, yarn_only=False)
check("bending along the wale and along the course give different rigidities, which is "
      "reported rather than averaged away",
      abs(_dc["reference_bending_length_mm"] / _d["reference_bending_length_mm"] - 1.0) > 0.05,
      "wale %.3f mm, course %.3f mm"
      % (_d["reference_bending_length_mm"], _dc["reference_bending_length_mm"]))
# Whether the artificial hops between ops count is worth a factor of ten in B, so it is a
# stated condition and not a default nobody looks at.
_dy = DR.derive_bending_rigidity(FLAT, along="wale", frame_invariant=True, yarn_only=True)
check("whether the artificial hops between ops count changes the derived B by more than "
      "an order of magnitude, so the answer is a bracket and the condition is stated",
      _dy["derived_bending_rigidity_N_m2"] / _d["derived_bending_rigidity_N_m2"] > 2.0,
      "%.3e (yarn only) vs %.3e (whole path)"
      % (_dy["derived_bending_rigidity_N_m2"], _d["derived_bending_rigidity_N_m2"]))
check("the path carries segments that are not yarn, and they are identified rather than "
      "assumed away",
      0 < int(DR.genuine_yarn_vertices(FLAT.points).sum()) < len(FLAT.points),
      "%d of %d vertices have two genuine yarn segments"
      % (int(DR.genuine_yarn_vertices(FLAT.points).sum()), len(FLAT.points)))
# CORRECTION, pinned. `drape()` divides by the median over ALL path segments, artificial hops
# included: 4.086mm on this fixture. The wave 2 record quotes the solver's `l` as 3.1427mm,
# which is the median over segments shorter than 5mm -- a different statistic, and not the one
# the code uses. They differ by 1.30x, so `B/l^3` differs by 2.20x, and every prestress ratio
# computed from the recorded value is out by that factor. (Excluding the 20 sub-micron joins
# as well gives 3.973mm, a third statistic; which of the three is meant has to be stated.)
_allseg = np.clip(np.linalg.norm(np.diff(FLAT.points, axis=0), axis=1), 1e-9, None)
_solver_l = float(np.median(_allseg))
_recorded_l = float(np.median(_allseg[_allseg < DR.JUMP_SEGMENT_MM]))
check("the length scale the solver uses is the median over the WHOLE path, and it is not the "
      "figure the wave 2 record quotes for it",
      abs(_solver_l / _recorded_l - 1.0) > 0.2,
      "solver uses %.4f mm, the record says %.4f mm, so B/l^3 differs by %.2fx"
      % (_solver_l, _recorded_l, (_solver_l / _recorded_l) ** 3))

# --- why the cantilever inversion cannot be converged, in closed form -------------------
_bound = DR.cantilever_equilibrium_bound(FLAT, SETUP, overhang_fraction=0.7)
check("the cantilever bound is computed from the fabric rather than stated",
      _bound["free_vertices"] > 0 and _bound["effective_tension_N"] > 0.0)
check("the standard cantilever's free region outweighs the tension the force law can "
      "supply, so there is no shallow equilibrium to converge to",
      _bound["supports_its_own_weight"] is False and _bound["weight_over_tension"] > 1.0,
      "%.4e N of cloth against %.4e N of tension, %.2fx"
      % (_bound["free_region_weight_N"], _bound["effective_tension_N"],
         _bound["weight_over_tension"]))
# CHARACTERISATION. The solver applies bend_coeff*(lap - lap_rest), which is NOT the gradient
# of the energy the module documents -- that gradient is the second difference applied twice.
# Pinned here so that changing the force law has to change this check deliberately, and so
# the gradient used by every instrument above is itself verified against the energy.
_rng = np.random.default_rng(7)
_pp = FLAT.points.astype(float) + _rng.normal(0.0, 0.05, FLAT.points.shape)
_ell = float(np.median(np.clip(np.linalg.norm(np.diff(FLAT.points, axis=0), axis=1),
                               1e-9, None))) * 1e-3
_zero = np.zeros_like(_pp)


def _energy(q):
    return DR.bending_energy_J(q, _zero, DR.CALIBRATED_BENDING_N_M2, _ell)


_k = DR.CALIBRATED_BENDING_N_M2 / _ell ** 3
_r = DR._laplacian(_pp)
_grad = np.zeros_like(_r)
_grad[:-2] += _r[1:-1]
_grad[1:-1] += -2.0 * _r[1:-1]
_grad[2:] += _r[1:-1]
_grad = -_k * _grad
_impl = _k * _r
_h = 1e-6
_fd_ok = True
_worst = 0.0
for _i in (5, 61, 137, 240, 333, 410):
    for _a in range(3):
        _q = _pp.copy(); _q[_i, _a] += _h
        _e1 = _energy(_q)
        _q = _pp.copy(); _q[_i, _a] -= _h
        _e2 = _energy(_q)
        _fd = -(_e1 - _e2) / (2.0 * _h * 1e-3)
        _worst = max(_worst, abs(_fd - _grad[_i, _a]) / max(abs(_fd), 1e-12))
check("the bending energy's analytic gradient matches finite differences on the certified "
      "geometry, so the instruments above are differentiating the documented energy",
      _worst < 1e-5, "worst relative error %.3e" % _worst)
_cos = float((_impl * _grad).sum() /
             (np.linalg.norm(_impl) * np.linalg.norm(_grad)))
check("the force the solver applies is NOT that gradient -- it is the second difference once "
      "rather than twice, which is a string and not a beam",
      _cos < 0.99, "cosine %.4f, |difference| %.4e N of |gradient| %.4e N"
      % (_cos, float(np.linalg.norm(_impl - _grad)), float(np.linalg.norm(_grad))))

# --- what the frame-invariant option does to Product Truth, MEASURED, on real geometry ---
#
# It is off by default and this records why, rather than asserting it is safe. Most of the
# product survives it. Stitch SHAPE does not, in the middle of the descent, and the checks
# below pin that as a recorded negative result: the option is not adoptable while it is true,
# and if it stops being true these checks fail and somebody has to look.
_fi = replace(SETUP, frame_invariant_rest=True, iterations=400)
_fifab, _firep = DR.drape(FLAT, _fi)
_fig = CT.validate(_fifab, TWIN, max_rows=ROWS, max_cols=COLS)
check("frame-invariant rest actually changes the solve, so it is being exercised",
      float(np.abs(_fifab.points - DR.drape(FLAT, replace(SETUP, iterations=400))[0].points
                   ).max()) > 1e-4)
check("frame-invariant rest keeps every stitch linked to the loop it was worked into",
      _fig["stitches_linked"] == _fig["stitches_needing_linkage"] ==
      before["stitches_linked"],
      "%s/%s" % (_fig["stitches_linked"], _fig["stitches_needing_linkage"]))
check("frame-invariant rest leaves stitch identity and loop targets untouched",
      [(o.kind, o.row, o.position) for o in _fifab.ops] ==
      [(o.kind, o.row, o.position) for o in FLAT.ops] and
      [o.loop_target for o in _fifab.ops] == [o.loop_target for o in FLAT.ops])
check("frame-invariant rest preserves total yarn length",
      abs(_firep.length_change_pct) < 0.5, "%.4f%%" % _firep.length_change_pct)
check("frame-invariant rest never let a strand reach another",
      _firep.min_gap_seen_mm > 0.0 and _firep.crossing_impossible and
      _firep.cap_exceeded == 0, "%.4f mm" % _firep.min_gap_seen_mm)
_fid = DR.intrinsic_dimensions(_fifab, ROWS, COLS)
check("frame-invariant rest does not resize the product across the cantilever",
      abs(_fid["intrinsic_width_mm"] / d0["intrinsic_width_mm"] - 1.0) < 0.01,
      "%.4f%%" % (100 * (_fid["intrinsic_width_mm"] / d0["intrinsic_width_mm"] - 1.0)))
# THE RECORDED NEGATIVE. The spurious rotational stiffness was, among other things, what was
# holding a stitch's shape. Remove it and free-edge stitches evert partway down the descent.
check("RECORDED NEGATIVE: frame-invariant rest everts free-edge stitches partway through "
      "the descent, so it is not adoptable and is off by default",
      worst_third_loop_margin(_fifab) > 0.0 and
      _fig["stitches_shaped_like_hdc"] < _fig["stitches_built"],
      "worst third-loop margin %.3f mm (flat %.3f), %d of %d stitches still shaped"
      % (worst_third_loop_margin(_fifab), flat_margin,
         _fig["stitches_shaped_like_hdc"], _fig["stitches_built"]))
check("it is geometry and not the instrument: the same instrument reads correct on the "
      "default solve at the same iteration count",
      worst_third_loop_margin(DR.drape(FLAT, replace(SETUP, iterations=400))[0]) < -0.5)
# And the product's validity is NOT MONOTONE in the iteration count, which is the part that
# matters for every lock in this file: a solve can pass through a configuration in which the
# product is not the product and come out the other side valid, and an end-of-solve check
# cannot see that it happened. Measured across the descent: valid at 100, broken at 200, 400
# and 800, valid again at 1600, then broken and worsening -- 20/25 at 3200 and 17/25 at 6400,
# see research/VISUAL_WAVE3.md. Those two are not run here: they cost minutes to add further
# points to a sequence that is already non-monotone by 1600.
_fi2, _firep2 = DR.drape(FLAT, replace(SETUP, frame_invariant_rest=True, iterations=1600))
_fig2 = CT.validate(_fi2, TWIN, max_rows=ROWS, max_cols=COLS)
check("the product's validity is not monotone in the iteration count: broken at 400, valid "
      "again at 1600, so an end-of-solve check cannot see that it was ever broken",
      _fig2["stitches_shaped_like_hdc"] == _fig2["stitches_built"] and
      worst_third_loop_margin(_fi2) < 0.0 and _fig2["passes"] is True,
      "%d/%d shaped and margin %.3f mm at 1600, against %d/%d and %.3f mm at 400"
      % (_fig2["stitches_shaped_like_hdc"], _fig2["stitches_built"],
         worst_third_loop_margin(_fi2), _fig["stitches_shaped_like_hdc"],
         _fig["stitches_built"], worst_third_loop_margin(_fifab)))
# The reason to keep the option at all: it is the only thing tried so far that moves the
# standing conformability symptom in the right direction.
_relief_default = DR.relief_profile(FLAT, DR.drape(FLAT, replace(SETUP, iterations=1600))[0])
_relief_frame = DR.relief_profile(FLAT, _fi2)
check("frame-invariant rest RAISES the share of relief a per-row mean cannot explain, which "
      "is the direction the standing symptom needs and the opposite of what the Kaldor "
      "option did to it",
      _relief_frame["within_row_fraction"] > _relief_default["within_row_fraction"],
      "%.4f against %.4f at 1600 iterations, a factor of %.1f"
      % (_relief_frame["within_row_fraction"], _relief_default["within_row_fraction"],
         _relief_frame["within_row_fraction"] /
         max(_relief_default["within_row_fraction"], 1e-12)))

# --- the two rest-state options are not defined together, and say so --------------------
try:
    DR.drape(FLAT, replace(SETUP, frame_invariant_rest=True, plastic_rest_migration=True,
                           iterations=5))
    _refused = False
except ValueError:
    _refused = True
check("running Kaldor's world-space plasticity and the frame-invariant rest together is "
      "refused rather than quietly given a meaning", _refused)

# --- Product Truth on a configuration no validator has ever seen ------------------------
# The locks were written against a fabric that was flat, then against one that drooped. A
# cylinder is curved everywhere and planar nowhere, and no validator may be passing because
# the fabric happened to lie in a plane.
_wrapped = replace(FLAT, ops=[replace(_o, points=_q) for _o, _q in zip(
    FLAT.ops, np.split(DR.cylindrical_bend(FLAT.points.astype(float), 8.0, "wale"),
                       np.cumsum([len(_o.points) for _o in FLAT.ops])[:-1]))])
_wg = CT.validate(_wrapped, TWIN, max_rows=ROWS, max_cols=COLS)
check("wrapping the fabric round a 125mm cylinder leaves every stitch linked",
      _wg["stitches_linked"] == _wg["stitches_needing_linkage"] == before["stitches_linked"],
      "%s/%s" % (_wg["stitches_linked"], _wg["stitches_needing_linkage"]))
check("wrapping the fabric round a cylinder leaves every stitch shaped like a half double, "
      "so the morphology check is not passing because the fabric was flat",
      _wg["stitches_shaped_like_hdc"] == _wg["stitches_built"] == before["stitches_built"],
      "%s/%s" % (_wg["stitches_shaped_like_hdc"], _wg["stitches_built"]))
check("no stitch becomes unframeable when the fabric is curved everywhere",
      _wg.get("stitches_unframeable", 0) == 0 and _wg["stitches_unmeasurable"] == 0)
check("the wrapped fabric passes the same topology gate",
      _wg["passes"] is before["passes"] is True)
_wd = DR.intrinsic_dimensions(_wrapped, ROWS, COLS)
check("the product's intrinsic width survives being wrapped round a cylinder",
      abs(_wd["intrinsic_width_mm"] / d0["intrinsic_width_mm"] - 1.0) < 0.01,
      "%.4f%%" % (100 * (_wd["intrinsic_width_mm"] / d0["intrinsic_width_mm"] - 1.0)))
_wmoved = float(np.abs(_wrapped.points - FLAT.points).max())
check("the wrap really moved the geometry, or the checks above prove nothing",
      _wmoved > 1.0, "%.3f mm at the furthest vertex" % _wmoved)
check("the product's intrinsic height survives a bend that moves every stitch, which is the "
      "whole reason intrinsic and projected size are separate quantities",
      abs(_wd["intrinsic_height_mm"] / d0["intrinsic_height_mm"] - 1.0) < 0.02,
      "intrinsic %.3f -> %.3f mm while the projected box went %.3f x %.3f -> %.3f x %.3f mm"
      % (d0["intrinsic_height_mm"], _wd["intrinsic_height_mm"],
         d0["projected_width_mm"], d0["projected_height_mm"],
         _wd["projected_width_mm"], _wd["projected_height_mm"]))

# ==========================================================================================
# WAVE 4 -- the tensile stitch linkage, and the experiment it was built for.
#
# Everything below defends one of two things: that the new force acts on the relation the
# topology module CERTIFIES rather than on convenient neighbours, or that the experiment's
# result -- which is a NEGATIVE -- stays recorded and fails loudly if it stops being true.
# ==========================================================================================

_holds = DR.linkage_holds(FLAT)
check("the tensile linkage acts on exactly the pairs the validator demands a linking number "
      "for, so the fabric is not being held together by a relationship nothing certified",
      len(_holds["pairs"]) == before["stitches_needing_linkage"],
      "%d pairs against %d demanded" % (len(_holds["pairs"]),
                                        before["stitches_needing_linkage"]))
check("each certified pair contributes a hold per anchor arc that holds it -- two under both "
      "top loops, one under a single loop",
      _holds["n_holds"] == sum(len(p.holding) for p in _holds["pairs"]) and
      _holds["n_holds"] >= len(_holds["pairs"]),
      "%d holds for %d pairs" % (_holds["n_holds"], len(_holds["pairs"])))
_ext_flat = DR.linkage_extension(FLAT)
check("the constraint's rest separation is MEASURED off the certified geometry, so the "
      "certified fabric reads exactly zero extension against itself",
      _ext_flat["max_extension_mm"] == 0.0 and _ext_flat["rest_separation_min_mm"] > 0.5,
      "%.3e mm, rest separations from %.4f mm"
      % (_ext_flat["max_extension_mm"], _ext_flat["rest_separation_min_mm"]))


def _rigidly_moved(fab, deg, axis=(0.3, 0.5, 0.81), shift=(11.0, -5.0, 3.0)):
    a = np.asarray(axis, float)
    a = a / np.linalg.norm(a)
    kx = np.array([[0, -a[2], a[1]], [a[2], 0, -a[0]], [-a[1], a[0], 0]], float)
    th = np.radians(deg)
    rot = np.eye(3) + np.sin(th) * kx + (1 - np.cos(th)) * (kx @ kx)
    pts = fab.points.astype(float) @ rot.T + np.asarray(shift, float)
    cuts = np.cumsum([len(o.points) for o in fab.ops])[:-1]
    return replace(fab, ops=[replace(o, points=q)
                             for o, q in zip(fab.ops, np.split(pts, cuts))]), rot


# THE PROPERTY THE MECHANISM WAS REQUIRED TO HAVE. research/VISUAL_WAVE3.md named it: a force
# that resists a stitch being pulled OUT of its loop without resisting that stitch TURNING,
# because a fabric conforms by letting each stitch turn relative to its neighbours. A
# constraint on a DISTANCE has that property exactly, and this is the check that says so.
_moved_drape, _rot = _rigidly_moved(DRAPED, 37.0)
_moved_flat, _ = _rigidly_moved(FLAT, 37.0)
_e_here = DR.linkage_extension(DRAPED, rest_points=FLAT.points.astype(float))
_e_moved = DR.linkage_extension(_moved_drape, rest_points=_moved_flat.points.astype(float))
check("the linkage constraint is blind to a rigid motion of the whole fabric, so it cannot "
      "be resisting a stitch turning",
      abs(_e_here["max_extension_mm"] - _e_moved["max_extension_mm"]) < 1e-9 and
      abs(_e_here["mean_extension_mm"] - _e_moved["mean_extension_mm"]) < 1e-9,
      "%.12f vs %.12f mm" % (_e_here["max_extension_mm"], _e_moved["max_extension_mm"]))
# And it does not resist conforming to a curved surface either, which is the same statement
# made on geometry rather than on a rotation: wrapping the swatch round a 125mm cylinder
# moves every stitch and opens no certified link.
_wrap_ext = DR.linkage_extension(
    replace(FLAT, ops=[replace(_o, points=_q) for _o, _q in zip(
        FLAT.ops, np.split(DR.cylindrical_bend(FLAT.points.astype(float), 8.0, "wale"),
                           np.cumsum([len(_o.points) for _o in FLAT.ops])[:-1]))]),
    rest_points=FLAT.points.astype(float))
check("wrapping the fabric round a 125mm cylinder opens no certified linkage, so the "
      "constraint does not fight the cloth conforming to a curved surface",
      _wrap_ext["max_extension_mm"] < 0.01,
      "%.5f mm" % _wrap_ext["max_extension_mm"])

# TENSION ONLY. Pushing apart is contact's job; doing it twice would be two disagreeing
# copies of the same floor.
_closed = FLAT.points.astype(float).copy()
_inflated = DR.linkage_rest_separations(FLAT.points.astype(float), _holds) + 1.0
_worst = DR.apply_stitch_linkage(_closed, _holds, _inflated)
check("the linkage force is tension only: a pair that has closed is not pushed apart",
      float(np.abs(_closed - FLAT.points.astype(float)).max()) == 0.0 and _worst < 0.0,
      "moved %.3e mm, worst extension %.4f mm"
      % (float(np.abs(_closed - FLAT.points.astype(float)).max()), _worst))

# --- the force does what it was derived to do -------------------------------------------
_lf = replace(SETUP, stitch_linkage=True, frame_invariant_rest=True, iterations=400)
_lffab, _lfrep = DR.drape(FLAT, _lf)
_lfg = CT.validate(_lffab, TWIN, max_rows=ROWS, max_cols=COLS)
check("the tensile linkage holds the certified links shut: with it the worst extension "
      "anywhere in the run is a small fraction of what co-rotation alone allows",
      _lfrep.linkage_max_extension_mm < 0.1 * _firep.linkage_max_extension_mm,
      "%.4f mm with the force against %.4f mm without, at the same 400 iterations"
      % (_lfrep.linkage_max_extension_mm, _firep.linkage_max_extension_mm))
check("the linkage watch reports a maximum over the WHOLE run, not the value at the end, so "
      "a solve that passed through an open link cannot report clean",
      _lfrep.linkage_max_extension_mm > 2.0 * _lfrep.linkage_final_extension_mm and
      _lfrep.linkage_worst_iteration < _lfrep.iterations,
      "max %.4f at iteration %d, final %.4f"
      % (_lfrep.linkage_max_extension_mm, _lfrep.linkage_worst_iteration,
         _lfrep.linkage_final_extension_mm))
check("the linkage force does not stretch the yarn to do its work",
      abs(_lfrep.length_change_pct) < 0.5, "%.6f%%" % _lfrep.length_change_pct)
check("the linkage force never let a strand reach another",
      _lfrep.min_gap_seen_mm > 0.0 and _lfrep.crossing_impossible and
      _lfrep.cap_exceeded == 0, "%.4f mm" % _lfrep.min_gap_seen_mm)

# THE RESULT OF THE EXPERIMENT, RECORDED AS A NEGATIVE. Tensile linkage paired with the
# co-rotational rest state does NOT stop free-edge stitches everting, and it makes the worst
# third-loop margin worse rather than better. research/VISUAL_WAVE4.md. If this stops being
# true somebody has to look, because it is the finding Milestone D rests on.
check("RECORDED NEGATIVE: tensile linkage plus co-rotation does not stop free-edge stitches "
      "everting, so the missing mechanism was not the missing tensile link",
      worst_third_loop_margin(_lffab) > 0.0 and
      _lfg["stitches_shaped_like_hdc"] < _lfg["stitches_built"],
      "worst margin %+.3f mm (flat %+.3f, committed default %+.3f), %d of %d shaped"
      % (worst_third_loop_margin(_lffab), flat_margin, worst_third_loop_margin(DRAPED),
         _lfg["stitches_shaped_like_hdc"], _lfg["stitches_built"]))

# --- the control: the new force must not move the committed model -------------------------
_lofab, _lorep = DR.drape(FLAT, replace(SETUP, stitch_linkage=True))
check("on the committed model the tensile linkage is nearly inert -- the links barely open, "
      "so no committed Visual result moves when the option is available",
      abs(worst_third_loop_margin(_lofab) - worst_third_loop_margin(DRAPED)) < 0.01 and
      abs(_lorep.max_out_of_plane_mm / REPORT.max_out_of_plane_mm - 1.0) < 0.02,
      "margin %+.3f vs %+.3f, droop %.4f vs %.4f mm"
      % (worst_third_loop_margin(_lofab), worst_third_loop_margin(DRAPED),
         _lorep.max_out_of_plane_mm, REPORT.max_out_of_plane_mm))

# --- WHY the experiment could not be decided in this solver as it stood -------------------
# The bending term is a lumped Laplacian, not the gradient of the documented energy. With a
# fixed world-space rest state that is survivable; with the rest state carried into the
# vertex frame the target moves with the configuration and the run CLIMBS.
_lam_rest = DR.rest_curvature_of(FLAT)
_segs = np.clip(np.linalg.norm(np.diff(FLAT.points.astype(float), axis=0), axis=1), 1e-9, None)
_ellm = float(np.median(_segs)) * 1e-3
_lump = np.zeros(len(FLAT.points))
_lump[:-1] += _segs * 1e-3 / 2.0
_lump[1:] += _segs * 1e-3 / 2.0
_massv = _lump * AM["linear_density_kg_m"]


def _potential(pts):
    return float((_massv * DR.STANDARD_GRAVITY *
                  (pts[:, 2] - FLAT.points[:, 2]) * 1e-3).sum())


_c400 = DR.drape(FLAT, replace(SETUP, iterations=400))[0]
_e_c = DR.bending_energy_J(_c400.points.astype(float), _lam_rest,
                           DR.CALIBRATED_BENDING_N_M2, _ellm)
_g_c = _potential(_c400.points.astype(float))
check("the committed solve DESCENDS: it releases more gravitational potential than it puts "
      "into bending", _e_c + _g_c < 0.0,
      "bending %+.3e J against %+.3e J of potential" % (_e_c, _g_c))
_e_f = DR.bending_energy_J(_fifab.points.astype(float), _lam_rest,
                           DR.CALIBRATED_BENDING_N_M2, _ellm,
                           rest_pts=FLAT.points.astype(float), frame_invariant=True)
_g_f = _potential(_fifab.points.astype(float))
check("RECORDED NEGATIVE: with the rest state carried into the vertex frame the same solve "
      "CLIMBS -- it gains far more bending energy than gravity releases -- so the lumped "
      "Laplacian is not a descent direction for the energy it is standing in for",
      _e_f > 5.0 * abs(_g_f),
      "bending %+.3e J against %+.3e J of potential, a factor of %.1f"
      % (_e_f, _g_f, _e_f / max(abs(_g_f), 1e-30)))

# --- AND THE MEASUREMENT THAT SETTLES WHAT THE MOTION IS ----------------------------------
# Switch gravity off and run the identical solve. Whatever still happens is not drape.
_c0 = DR.drape(FLAT, replace(SETUP, iterations=400, gravity=0.0))[0]
_f0 = DR.drape(FLAT, replace(SETUP, iterations=400, gravity=0.0,
                             frame_invariant_rest=True))[0]


def _rms_from_flat(fab):
    return float(np.sqrt(np.mean(np.sum(
        (fab.points.astype(float) - FLAT.points.astype(float)) ** 2, axis=1))))


check("the committed solver has no drift: with gravity off it does not move",
      _rms_from_flat(_c0) < 0.01, "%.5f mm rms" % _rms_from_flat(_c0))
check("RECORDED NEGATIVE: the frame-invariant rest state moves the fabric just as far WITH "
      "GRAVITY SWITCHED OFF, so what it produces is a load-independent instability and not "
      "drape",
      _rms_from_flat(_f0) > 0.8 * _rms_from_flat(_fifab) and
      worst_third_loop_margin(_f0) > 0.0,
      "%.4f mm rms at zero gravity against %.4f mm under gravity, margin %+.3f"
      % (_rms_from_flat(_f0), _rms_from_flat(_fifab), worst_third_loop_margin(_f0)))

# --- the bending term as the actual gradient ----------------------------------------------
_gr = DR.drape(FLAT, replace(SETUP, iterations=400, energy_gradient_bending=True))[0]
_e_gr = DR.bending_energy_J(_gr.points.astype(float), _lam_rest,
                            DR.CALIBRATED_BENDING_N_M2, _ellm)
check("the gradient form of the bending term is wired in and changes the solve",
      float(np.abs(_gr.points - _c400.points).max()) > 1e-4,
      "%.4f mm at the furthest vertex" % float(np.abs(_gr.points - _c400.points).max()))
check("the gradient form descends too, so replacing the lumped Laplacian did not break the "
      "committed configuration", _e_gr + _potential(_gr.points.astype(float)) < 0.0,
      "bending %+.3e J against %+.3e J of potential"
      % (_e_gr, _potential(_gr.points.astype(float))))

# --- the supplementary conformability measure, and its floor ------------------------------
_art_flat = DR.articulation_profile(FLAT)
_art_moved = DR.articulation_profile(_rigidly_moved(FLAT, 41.0)[0])
check("local articulation is a property of the cloth, not of its orientation: a rigid "
      "rotation leaves it unchanged",
      abs(_art_flat["articulation_rms_deg"] - _art_moved["articulation_rms_deg"]) < 1e-9,
      "%.9f vs %.9f deg" % (_art_flat["articulation_rms_deg"],
                            _art_moved["articulation_rms_deg"]))
check("local articulation reports its floor honestly: the certified FLAT fabric does not "
      "read zero, so a reading has to be judged against it",
      0.0 < _art_flat["articulation_rms_deg"] < 1.0,
      "%.4f deg on flat cloth" % _art_flat["articulation_rms_deg"])
check("the frame-invariant configuration reads higher local articulation than the committed "
      "default, which is the direction the standing symptom needs even though the zero-"
      "gravity control above shows it is not drape",
      DR.articulation_profile(_fifab)["articulation_rms_deg"] >
      DR.articulation_profile(DRAPED)["articulation_rms_deg"],
      "%.4f vs %.4f deg" % (DR.articulation_profile(_fifab)["articulation_rms_deg"],
                            DR.articulation_profile(DRAPED)["articulation_rms_deg"]))

# --- how much margin the single-loop linkage instrument actually has ----------------------
# `_encirclement` closes a single top loop through a fictitious point and tries ten
# directions, taking one clear detection as proof. That is a MARGIN, and the margin is
# measurable: on correct geometry about two in five directions detect the crossing. On the
# strongly deformed 3200-iteration frame-invariant run it falls to about one in seven and the
# structured ten find none at all -- which is why that run reads 17 of 20 linked while the
# solver's own continuous guarantee says no strand ever reached another. See
# research/VISUAL_WAVE4.md. Pinned here on the cheap configurations so the margin cannot
# quietly thin further.
_rng2 = np.random.default_rng(11)
_dirs = _rng2.normal(size=(60, 3))
_dirs /= np.linalg.norm(_dirs, axis=1, keepdims=True)
_reach = CT._away_reach(FLAT)
_need = FLAT.yarn_diameter * 0.35
_shares = []
for _p in CT.certified_linkage_pairs(FLAT):
    if _p.loop_target not in ("front", "back"):
        continue
    _a = FLAT.ops[_p.anchor_index]
    _o = FLAT.ops[_p.op_index]
    _arc = (_a.points[_a.front_loop[0]:_a.front_loop[1] + 1] if _p.loop_target == "front"
            else _a.points[_a.back_loop[0]:_a.back_loop[1] + 1])
    _centre = _arc.mean(axis=0)
    _room = _hit = 0
    for _dd in _dirs:
        _tip = _centre + _dd * _reach
        if CT._clearance_to_path(_centre, _tip, _o.points,
                                 skip_mm=2.0 * FLAT.yarn_diameter) < _need:
            continue
        _room += 1
        try:
            if LK.link_with_open_path(LK.close_arc(np.vstack([_arc, _tip])), _o.points) != 0:
                _hit += 1
        except (LK.CurvesIntersect, ValueError):
            pass
    _shares.append(_hit / max(_room, 1))
check("the single-loop linkage instrument has real margin on correct geometry: a large share "
      "of closure directions detect the crossing, not just the structured few",
      len(_shares) > 4 and min(_shares) > 0.25,
      "worst stitch %.3f, mean %.3f over %d single-loop stitches"
      % (min(_shares), sum(_shares) / len(_shares), len(_shares)))

print(f"\n  {PASSED} passing, {FAILED} failing")
sys.exit(1 if FAILED else 0)
