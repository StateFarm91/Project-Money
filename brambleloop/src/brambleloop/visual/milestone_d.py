"""Milestone D, measured on the certified geometry: authoritative object -> presentation
without structural drift.

THE CLAIM D MAKES, recovered from the owner's instruction of 2026-09-24 and the realism
standard in `final_standard` (B-700): the object the customer will be shown is the certified
fabric -- the same stitches, the same yarn path, the same linkage -- placed under a physically
plausible load, keeping every Product Truth lock while it does so, and drawn from THAT
configuration. Not a picture that resembles it. Each half is measurable, and this module
measures it; the half that is a judgement about a photograph is reported as UNKNOWN, never
inferred from the measured half.

WHAT WAS FOUND ON THE WAY HERE, because it is the reason the module looks like this.

  1. THE RIGID-BAR SYMPTOM WAS DRIFT. Wave 5 recorded that "every row still reads as a rigid
     bar bowing as a unit". The drape solver's force step is scaled to the yarn's bending
     force, so gravity moved a vertex about 0.7 micrometres per iteration; the reported
     0.566mm at 800 iterations became 1.130mm at 1600 and 4.44mm at 6400 -- linear, a fabric
     in free drift, nowhere near equilibrium. A uniformly drifting fabric moves every row as
     a unit by construction. `DrapeSetup.momentum` and `step_multiplier` exist so the solve
     can actually arrive; with them the same fabric on a sphere carries MORE within-row
     relief than wrapping the sphere geometrically requires.

  2. THE FRICTIONLESS FORCE LAW TAKES THE STITCHES APART. Once the fabric actually drapes,
     14 of 25 half doubles on the 5x5 had their third loop above the V after 25,600 plain
     iterations at the committed 3.0e-8 N m^2 -- the same defect with momentum, with the
     guard, after an 800-iteration settle-back, and at the bending rigidity
     `drape.derive_bending_rigidity` derives from this fabric (1.27e-6 N m^2, 42x: 16 of 25
     everted after 6,400 iterations). The sc swatch loses 13 of 20 linkages the same way. A
     fabric whose strands slide freely over one another IS netting. The force missing was
     yarn-on-yarn friction, which at this scale outweighs gravity on a stitch by orders of
     magnitude; `DrapeSetup.rigid_stitches` is its infinite-friction limit, and every result
     that uses it says that the stitch's internal shape is then an input, not an outcome.
     The bending rigidity used is the derived one; the committed constant is documented in
     `drape` as unconverged, and the value used is on every result.

Nothing here lowers a threshold. `validate` is called unchanged on the draped fabric; the
sphere is a form the cloth must not enter; the only chosen numbers are named in CRITERIA with
their reason, and each one is a bar the evidence has to clear, not a definition fitted to
what the solver produced.

Judged items -- whether the picture reads as a photograph -- need a judge, and the owner froze
paid judges on 2026-09-26. They are UNKNOWN here, and an UNKNOWN never contributes to a PASS.
"""
from __future__ import annotations

import hashlib
import os
import time
from dataclasses import replace

import numpy as np

from . import crochet_topology as CT
from . import drape as DR
from . import relaxation as RX
from . import pbr_scene as PS

PASS, FAIL, UNKNOWN = "PASS", "FAIL", "UNKNOWN"
PARTIAL = "PARTIAL"

# Every number chosen here, with why. A criterion that is not in this table is not a criterion.
CRITERIA = {
    "fixed_point_mm": (1e-9, "the certified fabric must be an exact fixed point of the loaded "
                             "solver with the load removed: wave 5 measured 1.58e-17mm, so "
                             "a nanometre is a thousand-million times that, not a tolerance "
                             "on the mechanics"),
    "stationarity_fraction": (0.02, "CHOSEN: the fabric has stopped when the rms displacement "
                                    "over the last tenth of the solve changes by under 2 per "
                                    "cent of the whole motion. Reported with the trace so a "
                                    "reader can disagree"),
    "contact_mm": (0.05, "DERIVED from the solver: a vertex the sphere projection has touched "
                         "sits within one accepted step of the keep-out surface; 0.05mm is "
                         "under half the smallest cap the solver uses"),
    "contact_patch": ((2, 2), "DERIVED from geometry: a rigid row tangent to a sphere touches "
                              "it at one point, so a stack of rigid rows meets the form along "
                              "one column at most. A cloth curving both ways meets it over a "
                              "patch: some row touches at two or more columns AND some column "
                              "at two or more rows. The within-row share of relief is reported "
                              "beside it against what wrapping the form would demand, as a "
                              "measurement rather than a bar"),
    "irregularity_cv": (0.034, "SOURCED via hand_tension.PROVENANCE: half a stitch over a "
                               "gauge swatch, the craft threshold for a swatch reading as "
                               "hand-made rather than machine-uniform"),
    "ply_within_yarn_radius": (1.05, "DERIVED: every ply vertex lies within the yarn radius "
                                     "of its centreline by construction; 5 per cent covers "
                                     "the Catmull-Rom resample of the centreline"),
}

JUDGED = ("fabric_folds_naturally", "lighting_is_realistic", "shadows_are_coherent",
          "has_ordinary_photographic_imperfection")
JUDGED_REJECTS = ("melted_yarn", "synthetic_stitch_texture", "catalogue_perfect_sterility")

# The loaded configuration, the reconciled one wave 5 arrived at plus the three rate devices
# this increment added. None of the three is on by default in `drape`, and every committed
# Visual result is untouched by them; here they are what lets the solve arrive.
SOLVER = dict(energy_gradient_bending=True, frame_invariant_rest=True,
              contact_rest_is_relaxed_shape=True, bend_on_yarn_only=True,
              momentum=0.98, step_multiplier=8.0, polish_passes=4, rigid_stitches=True,
              support_friction=True)


def certified_swatch(kind: str = "hdc", rows: int = 5, cols: int = 5, *, hand=None):
    """The certified fabric exactly as the pipeline makes it: build, settle, relax."""
    if kind == "hdc":
        from ..cir import benchmarks as BM
        from ..cir.compiler import compile_cir
        from ..cir.twin import build_twin
        cir = BM.cardigan("S")
        twin = build_twin(cir, compile_cir(cir), component="body")
        tex = 444.0
    elif kind == "sc":
        from .sc_swatch import sc_twin
        cir, twin = sc_twin(rows + 2, cols + 2)
        tex = 300.0
    else:
        raise CT.UnmodelledStitch(f"no certified swatch is modelled for {kind!r}")
    built = CT.build(twin, cir.gauge, max_rows=rows, max_cols=cols, hand=hand)
    flat, relax_report = RX.relax(CT.settle(built), iterations=600)
    return cir, twin, flat, relax_report, tex


def sphere_form(flat: CT.Fabric, radius_mm: float | None = None) -> tuple:
    """A rigid sphere under the fabric's centre, its keep-out surface touching the fabric's
    lowest point, so the cloth falls onto the form rather than being born inside it."""
    pts = flat.points
    lo, hi = pts.min(axis=0), pts.max(axis=0)
    R = radius_mm if radius_mm is not None else 0.45 * float(min(hi[0] - lo[0], hi[1] - lo[1]))
    cx, cy = float((lo[0] + hi[0]) / 2), float((lo[1] + hi[1]) / 2)
    cz = float(lo[2] - R - 0.5 * flat.yarn_diameter)
    return (cx, cy, cz, R)


def _stitch_centres(fab):
    keys, cs = [], []
    for o in fab.ops:
        if CT.is_stitch(o):
            keys.append((o.row, o.position))
            cs.append(o.points.mean(axis=0))
    return keys, np.asarray(cs)


def _relief_split(keys, disp, down):
    d = disp @ np.asarray(down, float)
    rows: dict = {}
    for k, v in zip(keys, d):
        rows.setdefault(k[0], []).append(v)
    total = float(np.sum(d ** 2))
    within = sum(float(np.sum((np.array(v) - np.mean(v)) ** 2)) for v in rows.values())
    return {"total_rms_mm": float(np.sqrt(total / max(len(d), 1))),
            "within_row_rms_mm": float(np.sqrt(within / max(len(d), 1))),
            "within_row_fraction": within / total if total > 0 else 0.0}


def conformability(flat: CT.Fabric, draped: CT.Fabric, form: tuple, down=(0.0, 0.0, -1.0)) -> dict:
    """The fabric's within-row relief against what wrapping the form geometrically demands,
    and against the rigid-row null (zero)."""
    cx, cy, cz, R = form
    keys, c0 = _stitch_centres(flat)
    _, c1 = _stitch_centres(draped)
    top = cz + R + 0.5 * flat.yarn_diameter        # where a centreline rests on the form
    ref = []
    for c in c0:
        rr = float(np.hypot(c[0] - cx, c[1] - cy))
        z = top - R + (np.sqrt(max(R * R - rr * rr, 0.0)) if rr < R else 0.0)
        ref.append((c[0], c[1], z))
    fabric = _relief_split(keys, c1 - c0, down)
    target = _relief_split(keys, np.asarray(ref) - c0, down)
    ratio = (fabric["within_row_fraction"] / target["within_row_fraction"]
             if target["within_row_fraction"] > 0 else float("inf"))
    return {"fabric": fabric, "wrapped_target": target, "rigid_row_null": 0.0,
            "ratio_to_target": float(ratio)}


def contact_patch(fab: CT.Fabric, form: tuple, tol_mm: float) -> dict:
    """Which stitches touch the form: those with a vertex within `tol_mm` of the keep-out."""
    cx, cy, cz, R = form
    keep = R + 0.5 * fab.yarn_diameter
    rows_by_col: dict = {}
    cols_by_row: dict = {}
    touching = []
    for o in fab.ops:
        if not CT.is_stitch(o):
            continue
        d = np.linalg.norm(o.points - np.array([cx, cy, cz]), axis=1) - keep
        if float(d.min()) <= tol_mm:
            touching.append((o.row, o.position))
            cols_by_row.setdefault(o.row, set()).add(o.position)
            rows_by_col.setdefault(o.position, set()).add(o.row)
    widest_row = max((len(v) for v in cols_by_row.values()), default=0)
    tallest_col = max((len(v) for v in rows_by_col.values()), default=0)
    return {"touching": sorted(touching), "stitches_touching": len(touching),
            "most_columns_in_one_row": widest_row, "most_rows_in_one_column": tallest_col}


def distance_to_form(fab: CT.Fabric, form: tuple) -> float:
    cx, cy, cz, R = form
    d = np.linalg.norm(fab.points - np.array([cx, cy, cz]), axis=1)
    return float((d - (R + 0.5 * fab.yarn_diameter)).min())


def _sha(points: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(points, dtype=np.float64).tobytes()).hexdigest()


def _item(name, status, measured, requirement, standard=None):
    return {"item": name, "status": status, "measured": measured,
            "requirement": requirement, "standard": standard}


def assess(kind: str = "hdc", rows: int = 5, cols: int = 5, *, iterations: int = 3200,
           bending: float | str = "derived", render_dir: str | None = None,
           hand=None, spp: int = 48, save_dir: str | None = None,
           settle_iterations: int = 0) -> dict:
    """Run the chain and report every item with its measurement. Nothing is stored unless
    `save_dir` is given, and then only the configurations themselves (flat and draped points
    with their hashes) so that a later render or judge can be shown to have used exactly the
    geometry this assessment measured.

    `settle_iterations`, when set, finishes the loaded solve with momentum off -- the way a
    FIRE minimisation is finished -- and the stationarity item is measured over the whole
    motion, both phases, by the same criterion."""
    t0 = time.time()
    items: list[dict] = []
    cir, twin, flat, rx_rep, tex = certified_swatch(kind, rows, cols, hand=hand)

    # --- identity: what was built is what the CIR ordered, and nothing else ---------------
    cells = {(getattr(c, "fabric_row", c.row), getattr(c, "fabric_position", c.position)):
             c.stitch for c in twin.cells}
    wrong = [(o.row, o.position, o.kind, cells.get((o.row, o.position)))
             for o in flat.ops if CT.is_stitch(o) and cells.get((o.row, o.position)) not in (None, o.kind)]
    kinds = sorted({o.kind for o in flat.ops if CT.is_stitch(o)})
    items.append(_item("stitch_identity", PASS if not wrong and kinds == [kind] else FAIL,
                       {"kinds_built": kinds, "mismatches": wrong[:5]},
                       "every built stitch carries the kind the CIR ordered; unmodelled kinds "
                       "are refused by name before any geometry exists"))

    before = CT.validate(flat, twin, max_rows=rows, max_cols=cols)
    items.append(_item("certified_flat", PASS if before["passes"] else FAIL,
                       {k: before[k] for k in ("stitches_built", "stitches_linked",
                                               "stitches_shaped_as_ordered",
                                               "closest_non_adjacent_mm", "contact_floor_mm",
                                               "findings")},
                       "the relaxed fabric passes every Product Truth lock before any load"))

    # --- bending rigidity: derived on THIS fabric, never assumed ------------------------
    derived = DR.derive_bending_rigidity(flat, tex, along="wale")
    if bending == "derived":
        B = float(derived["derived_bending_rigidity_N_m2"])
    elif bending == "committed":
        B = DR.CALIBRATED_BENDING_N_M2
    else:
        B = float(bending)
    items.append(_item("bending_rigidity_provenance",
                       PASS if derived["derivable"] and derived["curvature_independent_to"] < 1.01 else UNKNOWN,
                       {"used_N_m2": B, "derived_wale_N_m2": derived["derived_bending_rigidity_N_m2"],
                        "factor_on_committed": derived["factor_on_committed_value"],
                        "curvature_independent_to": derived["curvature_independent_to"],
                        "committed_N_m2": DR.CALIBRATED_BENDING_N_M2,
                        "committed_is_documented_unconverged": True},
                       "the rigidity the drape uses is derived from this fabric by the committed "
                       "procedure and is curvature-independent to 1 per cent"))

    am = DR.areal_mass(flat, tex)
    form = sphere_form(flat)
    setup = DR.DrapeSetup(bending_rigidity_N_m2=B, linear_density_kg_m=am["linear_density_kg_m"],
                          down=(0.0, 0.0, -1.0), clamp_fraction=0.0, iterations=iterations,
                          support_sphere=form, **SOLVER)

    # --- the fixed point: load off, the same solver must not move the certified fabric ----
    still, still_rep = DR.drape(flat, replace(setup, gravity=0.0, iterations=200))
    moved = float(np.sqrt(np.mean(np.sum((still.points - flat.points) ** 2, axis=1))))
    items.append(_item("equilibrium_fixed_point", PASS if moved < CRITERIA["fixed_point_mm"][0] else FAIL,
                       {"rms_displacement_mm": moved, "iterations": still_rep.iterations},
                       f"with gravity off the solver, momentum and step multiplier included, moves "
                       f"the certified fabric less than {CRITERIA['fixed_point_mm'][0]:g}mm",
                       "gravity_is_plausible"))

    # --- the loaded solve --------------------------------------------------------------
    draped, rep = DR.drape(flat, setup)
    if settle_iterations:
        settled, rep2 = DR.drape(draped, replace(setup, momentum=0.0, iterations=settle_iterations),
                                 rest_curvature=DR.rest_curvature_of(flat), rest_points=flat.points,
                                 trace_from=flat.points)
        # One motion, two phases: the trace continues from where the first phase ended, its
        # rms measured from the same origin, and every scalar the items read is the finished
        # solve's.
        base_it = rep.iterations
        rep.trace = list(rep.trace) + [(base_it + it, r, s) for it, r, s in rep2.trace]
        rep.iterations = base_it + rep2.iterations
        rep.energy_final_J = rep2.energy_final_J
        rep.final_step_mm = rep2.final_step_mm
        rep.support_violations += rep2.support_violations
        rep.min_gap_seen_mm = min(rep.min_gap_seen_mm, rep2.min_gap_seen_mm)
        rep.max_strain = rep2.max_strain
        rep.linkage_max_extension_mm = max(rep.linkage_max_extension_mm, rep2.linkage_max_extension_mm)
        rep.shape_residual_max_mm = max(rep.shape_residual_max_mm, rep2.shape_residual_max_mm)
        rep.max_out_of_plane_mm = float(np.abs((settled.points - flat.points) @ np.asarray(setup.down)).max())
        rep.stalled = rep2.stalled
        rep.energy_rejections += rep2.energy_rejections
        draped = settled
    items.append(_item("energy_descends", PASS if rep.energy_final_J < rep.energy_start_J else FAIL,
                       {"start_J": rep.energy_start_J, "final_J": rep.energy_final_J,
                        "energy_rejections": rep.energy_rejections, "stalled": rep.stalled},
                       "the loaded configuration has lower total energy than the certified one",
                       "gravity_is_plausible"))
    tr = rep.trace
    if len(tr) >= 10:
        tail = tr[-max(1, len(tr) // 10):]
        motion = tr[-1][1]
        change = abs(tail[-1][1] - tail[0][1])
        frac = change / motion if motion > 0 else 0.0
        stationary = frac < CRITERIA["stationarity_fraction"][0]
        st = PASS if stationary else UNKNOWN
    else:
        frac, motion, st = float("nan"), float("nan"), UNKNOWN
    items.append(_item("stationary", st,
                       {"rms_motion_mm": motion, "last_tenth_change_fraction": frac,
                        "final_step_mm": rep.final_step_mm, "iterations": rep.iterations,
                        "trace": tr[::4]},
                       f"the rms displacement changes by under {CRITERIA['stationarity_fraction'][0]:g} "
                       "of the whole motion over the last tenth of the solve; otherwise the "
                       "configuration is still moving and is reported as UNKNOWN, not as drape",
                       "gravity_is_plausible"))

    gap = distance_to_form(draped, form)
    items.append(_item("contacts_the_form", PASS if gap <= CRITERIA["contact_mm"][0] and rep.support_violations > 0 else FAIL,
                       {"closest_mm_to_keep_out": gap, "support_corrections": rep.support_violations,
                        "form": form},
                       "the fabric rests on the form rather than floating above it",
                       "garment_contacts_the_body_coherently / floating_garment"))

    # --- NO STRUCTURAL DRIFT: the lock, unchanged, on the draped configuration ------------
    after = CT.validate(draped, twin, max_rows=rows, max_cols=cols, reference=flat)
    same_product = (after["stitches_built"] == before["stitches_built"]
                    and [o.loop_target for o in draped.ops] == [o.loop_target for o in flat.ops]
                    and [o.kind for o in draped.ops] == [o.kind for o in flat.ops])
    items.append(_item("no_structural_drift", PASS if after["passes"] and same_product else FAIL,
                       {k: after[k] for k in ("stitches_built", "stitches_linked",
                                              "stitches_needing_linkage", "stitches_shaped_as_ordered",
                                              "closest_non_adjacent_mm", "contact_floor_mm", "findings",
                                              "frame")}
                       | {"same_stitches_kinds_and_targets": same_product,
                          "morphology_held_by": ("friction lock (rigid_stitches): the stitch's internal "
                                                 "shape is an input here, not an outcome; linkage, "
                                                 "floor and clearance are outcomes"),
                          "shape_residual_max_mm": rep.shape_residual_max_mm,
                          "shape_residual_final_mm": rep.shape_residual_final_mm,
                          "max_strain": rep.max_strain, "linkage_max_extension_mm": rep.linkage_max_extension_mm,
                          "max_out_of_plane_mm": rep.max_out_of_plane_mm},
                       "`validate` passes on the draped fabric exactly as it did on the flat one: "
                       "every stitch linked, shaped as ordered, no strand under the compression floor"))

    conf = conformability(flat, draped, form, setup.down)
    art0 = DR.articulation_profile(flat)["articulation_rms_deg"]
    art1 = DR.articulation_profile(draped)["articulation_rms_deg"]
    patch = contact_patch(draped, form, CRITERIA["contact_mm"][0])
    need_cols, need_rows = CRITERIA["contact_patch"][0]
    curved_both_ways = (patch["most_columns_in_one_row"] >= need_cols
                        and patch["most_rows_in_one_column"] >= need_rows)
    items.append(_item("double_curvature", PASS if curved_both_ways and art1 > art0 else FAIL,
                       {**conf, **patch, "articulation_flat_rms_deg": art0,
                        "articulation_draped_rms_deg": art1},
                       "the fabric meets the form over a patch spanning at least two columns "
                       "in one row and two rows in one column, and stitches articulate more "
                       "than they did flat: rows are not rigid bars",
                       "fabric_folds_naturally / crochet_drape_is_physically_plausible"))

    # --- irregularity: measured, never a gate ---------------------------------------------
    # The first version gated on "realised stitch-width variation >= 3.4%", the craft threshold
    # for a swatch reading uneven. That threshold is a statement about GAUGE deviation over a
    # swatch, and the hand-tension anchor -- the owner's hard constraint, pinned in
    # tests/test_hand_tension.py -- renormalises every row to the certified width, so gauge
    # deviation is zero by construction and the gate could never be met by any fabric that
    # kept the lock. A criterion an owner constraint makes unsatisfiable is not a criterion.
    # What the standard (B-700) actually asks is whether the PHOTOGRAPH has ordinary
    # imperfection and whether the stitch texture reads as synthetic; those are judged items
    # below, and the realised geometric variation is reported beside them as measurement.
    from .hand_tension import HandTension, realised_variation
    rv = realised_variation(rows, cols, flat.L, flat.H, hand or HandTension(), seeds=16)
    hand_measured = {"applied_to_this_build": hand is not None,
                     "realised_at_the_sourced_5pct_input": rv,
                     "craft_threshold_pct": 3.4,
                     "why_not_a_gate": ("the owner's per-row anchor makes swatch gauge deviation "
                                        "zero by construction; imperfection is judged on the "
                                        "image, as B-700 states it")}

    # --- the render consumes the validated configuration, and nothing else ----------------
    import tempfile
    h_before = _sha(draped.points)
    with tempfile.TemporaryDirectory(prefix="brambleloop-d-") as tmp:
        cf = os.path.join(tmp, "plied.txt")
        drawn = PS.write_plied_curve_file(draped, cf, tex=tex, fibres_per_ply=0)
        strands = PS.fabric_strands(draped)
        worst = 0.0
        with open(cf) as f:
            blocks = [b for b in f.read().split("\n\n") if b.strip()]
        for k, block in enumerate(blocks[:40]):
            centre = strands[k // drawn["spec"]["plies"]]
            v = np.array([[float(x) for x in line.split()[:3]] for line in block.splitlines()])
            d = np.linalg.norm(v[:, None, :] - centre[None, :, :], axis=2).min(axis=1)
            worst = max(worst, float(d.max()))
    h_after = _sha(draped.points)
    r_yarn = draped.yarn_diameter / 2.0
    items.append(_item("render_consumes_validated_geometry",
                       PASS if h_before == h_after and worst <= CRITERIA["ply_within_yarn_radius"][0] * r_yarn else FAIL,
                       {"geometry_sha256": h_before, "unchanged_by_render": h_before == h_after,
                        "worst_ply_offset_mm": worst, "yarn_radius_mm": r_yarn,
                        "strands": drawn["strands"], "plies": drawn["plies"], "spec": drawn["spec"]},
                       "the curve file is derived from the draped fabric's own strands; every ply "
                       "vertex lies within the yarn radius of its centreline; the fabric is not "
                       "touched by drawing it"))

    if save_dir:
        os.makedirs(save_dir, exist_ok=True)
        np.savez(os.path.join(save_dir, f"{kind}_flat.npz"), points=flat.points, sha256=_sha(flat.points))
        np.savez(os.path.join(save_dir, f"{kind}_draped.npz"), points=draped.points,
                 sha256=_sha(draped.points), form=np.array(form))

    images = None
    if render_dir:
        try:
            os.makedirs(render_dir, exist_ok=True)
            images = {}
            for tag, fab in (("flat", flat), ("draped", draped)):
                for view in ("camera", "oblique"):
                    out = os.path.join(render_dir, f"{kind}_{tag}_plied_{view}.png")
                    r = PS.render(fab, out, view=view, spp=spp, plied_tex=tex, frame=flat)
                    images[f"{tag}_{view}"] = {"path": out, "geometry_sha256": _sha(fab.points),
                                               "plies": r["plied"]["plies"], "fibres": r["plied"]["fibres"],
                                               "not_reproduced": r["not_reproduced"]}
            items.append(_item("images_rendered", PASS, images,
                               "flat and draped rendered from their own geometry under one committed "
                               "scene, framed by the same reference"))
        except RuntimeError as exc:
            items.append(_item("images_rendered", UNKNOWN, {"reason": str(exc)[:200]},
                               "Mitsuba is not installed here; nothing was drawn"))
    else:
        items.append(_item("images_rendered", UNKNOWN, {"render_dir": None},
                           "no render directory was given; nothing was drawn"))

    for j in JUDGED + JUDGED_REJECTS:
        m = {"judge": None}
        if j in ("has_ordinary_photographic_imperfection", "synthetic_stitch_texture"):
            m["geometric_irregularity"] = hand_measured
        items.append(_item(j, UNKNOWN, m,
                           "a judgement about the photograph: an independent judge's reading of "
                           "the authoritative renders (`d_judge`), applied with `apply_judgement`; "
                           "UNKNOWN until one has been recorded",
                           j))

    result = {
        "milestone": "D", "kind": kind, "rows": rows, "cols": cols, "status": None,
        "geometry_sha256": {"flat": _sha(flat.points), "draped": _sha(draped.points)},
        "form": list(form), "settle_iterations": settle_iterations,
        "items": items, "solver": {**SOLVER, "iterations": iterations, "bending_N_m2": B},
        "criteria": {k: {"value": v[0], "why": v[1]} for k, v in CRITERIA.items()},
        "seconds": round(time.time() - t0, 1),
        "rule": RULE,
    }
    return verdict(result)


RULE = ("PASS only when every item passes; an UNKNOWN never counts toward a PASS; a FAIL "
        "anywhere is FAIL")


def verdict(result: dict) -> dict:
    """The milestone's status from its items and nothing else. Called by `assess` and again
    by `apply_judgement`, so there is one place the verdict is computed."""
    items = result["items"]
    statuses = [i["status"] for i in items]
    result["status"] = FAIL if FAIL in statuses else (PASS if all(s == PASS for s in statuses) else PARTIAL)
    measured = [i for i in items if i["status"] != UNKNOWN]
    result["measured_pass"] = all(i["status"] == PASS for i in measured) and bool(measured)
    result["unknown"] = [i["item"] for i in items if i["status"] == UNKNOWN]
    result["failed"] = [i["item"] for i in items if i["status"] == FAIL]
    return result


def apply_judgement(result: dict, judgement: dict) -> dict:
    """Fill the judged items from an independent judge's record (`d_judge.judge_views`) and
    recompute the verdict. The record carries the model, the prompt, every view's raw answer
    and the per-view readings; the item's measured dict keeps them, so the verdict can be
    traced to the exact call that produced it."""
    by_item = {i["item"]: i for i in result["items"]}
    for item, j in judgement["items"].items():
        if item not in by_item:
            continue
        by_item[item]["status"] = {"PASS": PASS, "FAIL": FAIL}.get(j["status"], UNKNOWN)
        by_item[item]["measured"] = {**by_item[item]["measured"],
                                     "judge": judgement["model"], "per_view": j["per_view"],
                                     "notes": [v["reading"].get("notes", "") for v in judgement["views"]],
                                     "response_ids": [v.get("response_id") for v in judgement["views"]],
                                     "cost_usd": judgement.get("total_cost_usd")}
    result["judgement"] = {"model": judgement["model"], "views": [os.path.basename(v["image"]) for v in judgement["views"]],
                           "image_sha256": [v.get("image_sha256") for v in judgement["views"]],
                           "total_cost_usd": judgement.get("total_cost_usd")}
    return verdict(result)


def summary(result: dict) -> str:
    """One line per item, for the ladder's evidence field and for people."""
    lines = [f"D {result['status']} on {result['kind']} {result['rows']}x{result['cols']} "
             f"(B={result['solver']['bending_N_m2']:.3g} N m^2, {result['solver']['iterations']} it, "
             f"{result['seconds']}s)"]
    for i in result["items"]:
        m = i["measured"]
        short = {k: (float("%.4g" % v) if isinstance(v, float) else v) for k, v in m.items()
                 if k in ("rms_displacement_mm", "ratio_to_target", "closest_mm_to_keep_out",
                          "stitches_linked", "stitches_shaped_as_ordered", "findings",
                          "last_tenth_change_fraction", "used_N_m2", "observed_stitch_width_cv",
                          "worst_ply_offset_mm", "most_columns_in_one_row",
                          "most_rows_in_one_column", "stitches_touching")} if isinstance(m, dict) else m
        lines.append(f"  {i['status']:7s} {i['item']}: {short}")
    return "\n".join(lines)


if __name__ == "__main__":                              # pragma: no cover
    import json
    import sys
    kind = sys.argv[1] if len(sys.argv) > 1 else "hdc"
    out_dir = sys.argv[2] if len(sys.argv) > 2 else None
    its = int(sys.argv[3]) if len(sys.argv) > 3 else 3200
    settle = int(sys.argv[4]) if len(sys.argv) > 4 else 0
    res = assess(kind, iterations=its, render_dir=out_dir, save_dir=out_dir, settle_iterations=settle)
    print(summary(res))
    if out_dir:
        with open(os.path.join(out_dir, f"milestone_d_{kind}.json"), "w") as f:
            json.dump(res, f, indent=1, default=str)
