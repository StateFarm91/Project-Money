"""Milestone D, conformability on a curved form.

Wave 5 left the standing symptom in one sentence: "every row still reads as a rigid bar bowing
as a unit". Its Section 6c asked for conformability under a prescribed form, because gravity
on a clamped strip gives a uniform row no reason to bend within itself -- the cantilever cannot
distinguish cloth from a stack of bars. A sphere can. A cloth laid over a sphere must curve in
both directions at once; a stack of rigid rows cannot, whatever it does row to row.

So the reference here is not a floor someone chose. It is computed: the fraction of relief that
a surface WRAPPING THIS SPHERE must carry within its rows, projected exactly as
`relief_profile` projects the fabric. The fabric is measured against that, and the same
numbers are reported for the rigid-row null model (per-row mean of the wrapped surface), so a
reader can see where the fabric sits between "bars" and "cloth" without anyone declaring it.

Usage: python research/d/sphere_form.py [hdc|sc] [rows] [cols] [radius_mm] [iterations] [momentum] [polish_passes]
"""
from __future__ import annotations
import os, sys, time, json
from dataclasses import replace
import numpy as np

from brambleloop.visual import crochet_topology as CT, drape as DR, relaxation as RX
from brambleloop.cir import benchmarks as BM
from brambleloop.cir.compiler import compile_cir
from brambleloop.cir.twin import build_twin

RECONCILED = dict(energy_gradient_bending=True, frame_invariant_rest=True,
                  contact_rest_is_relaxed_shape=True, bend_on_yarn_only=True)


def certified(kind: str, rows: int, cols: int):
    if kind == "hdc":
        cir = BM.cardigan("S")
        twin = build_twin(cir, compile_cir(cir), component="body")
    else:
        sys.path.insert(0, "research/d")
        from sc_swatch import sc_cir, sc_twin
        cir, twin = sc_twin(rows + 2, cols + 2)
    flat, rep = RX.relax(CT.settle(CT.build(twin, cir.gauge, max_rows=rows, max_cols=cols)),
                         iterations=600)
    return cir, twin, flat


def stitch_centres(fab):
    keys, cs = [], []
    for o in fab.ops:
        if CT.is_stitch(o):
            keys.append((o.row, o.position)); cs.append(o.points.mean(axis=0))
    return keys, np.array(cs)


def wrapped_reference(fab, centre, R):
    """Where each stitch centre would sit if the fabric wrapped the sphere: the flat centre's
    (x, y) projected radially onto the sphere top (z above the centre). Points outside the
    sphere's shadow hang at the tangent height, which is how a real cloth does it, roughly.
    This is the geometric target, not a claim about what the mechanics should achieve."""
    keys, cs = stitch_centres(fab)
    cx, cy, cz = centre
    out = []
    for c in cs:
        dx, dy = c[0] - cx, c[1] - cy
        rr = np.hypot(dx, dy)
        z = cz + (np.sqrt(max(R * R - rr * rr, 0.0)) if rr < R else 0.0)
        out.append((c[0], c[1], z))
    return keys, np.array(out)


def relief_split(keys, disp, down):
    """Same decomposition as drape.relief_profile: displacement along `down`, per-row mean
    removed, residual fraction of total energy."""
    d = disp @ np.asarray(down, float)
    rows = {}
    for k, v in zip(keys, d):
        rows.setdefault(k[0], []).append(v)
    total = float(np.sum(d ** 2))
    within = 0.0
    for r, vals in rows.items():
        vals = np.array(vals); within += float(np.sum((vals - vals.mean()) ** 2))
    return {"total_rms_mm": float(np.sqrt(total / max(len(d), 1))),
            "within_row_rms_mm": float(np.sqrt(within / max(len(d), 1))),
            "within_row_fraction": within / total if total > 0 else 0.0}


def main(kind="hdc", rows=5, cols=5, R=None, iterations=800, momentum=0.0, polish=0,
         guard=False, bending=None, settle_iterations=0):
    t0 = time.time()
    cir, twin, flat = certified(kind, rows, cols)
    pts = flat.points
    lo, hi = pts.min(axis=0), pts.max(axis=0)
    extent = hi - lo
    if R is None:
        R = 0.45 * min(extent[0], extent[1])
    # Sphere directly beneath the fabric's centre, its keep-out surface touching the fabric's
    # LOWEST point. The first attempt put it at the mid-plane: half the slab began inside the
    # form, the projection moved 640 vertices by millimetres in one iteration, the crossing
    # budget (0.45 x measured clearance) refused a move that size at every retry, and the
    # solve stalled at iteration 0. The fabric must fall onto the form, not be born inside it.
    cx, cy = (lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2
    cz = lo[2] - R - 0.5 * flat.yarn_diameter
    am = DR.areal_mass(flat, 444.0 if kind == "hdc" else 300.0)
    setup = DR.DrapeSetup(bending_rigidity_N_m2=DR.CALIBRATED_BENDING_N_M2,
                          linear_density_kg_m=am["linear_density_kg_m"],
                          down=(0.0, 0.0, -1.0), clamp_fraction=0.0, iterations=iterations,
                          support_sphere=(cx, cy, cz, R), momentum=momentum,
                          polish_passes=polish, **RECONCILED)
    if guard:
        setup = replace(setup, guard_morphology=True)
    if bending is not None:
        setup = replace(setup, bending_rigidity_N_m2=bending)
    setup = replace(setup, step_multiplier=float(os.environ.get('SPHERE_STEP', '1')),
                    gravity=float(os.environ.get('SPHERE_G', str(DR.STANDARD_GRAVITY))),
                    rigid_stitches=bool(int(os.environ.get("SPHERE_RIGID", "0"))),
                    support_friction=bool(int(os.environ.get("SPHERE_FRICTION", "0"))))
    draped, rep = DR.drape(flat, setup)
    if settle_iterations:
        # Momentum off, same rest state, same form: does the configuration momentum reached
        # hold as an equilibrium, or was it a transient the plain descent walks back from?
        draped, rep2 = DR.drape(draped, replace(setup, momentum=0.0, iterations=settle_iterations),
                                rest_curvature=DR.rest_curvature_of(flat), rest_points=flat.points)
        rep.iterations += rep2.iterations; rep.support_violations += rep2.support_violations
        rep.min_gap_seen_mm = min(rep.min_gap_seen_mm, rep2.min_gap_seen_mm)
        rep.energy_final_J = rep2.energy_final_J; rep.final_step_mm = rep2.final_step_mm
        rep.morphology_rejections += rep2.morphology_rejections; rep.stalled = rep2.stalled
        rep.polish_max_strain = rep2.polish_max_strain
    keys, c0 = stitch_centres(flat)
    _, c1 = stitch_centres(draped)
    _, cref = wrapped_reference(flat, (cx, cy, cz + 0.5 * flat.yarn_diameter), R)
    fabric = relief_split(keys, c1 - c0, setup.down)
    target = relief_split(keys, cref - c0, setup.down)
    # Rigid-row null: the wrapped reference with each row's within-row variation removed.
    null = {"within_row_fraction": 0.0}
    art_flat = DR.articulation_profile(flat)
    art_drp = DR.articulation_profile(draped)
    val = CT.validate(draped, twin, max_rows=rows, max_cols=cols)
    out = {
        "kind": kind, "rows": rows, "cols": cols, "radius_mm": R, "guard": guard,
        "bending_N_m2": setup.bending_rigidity_N_m2, "step_multiplier": setup.step_multiplier, "gravity": setup.gravity,
        "trace": rep.trace[::4], "rigid_stitches": setup.rigid_stitches, "shape_residual_max_mm": rep.shape_residual_max_mm, "shape_residual_final_mm": rep.shape_residual_final_mm, "polish_reverted_for_morphology": rep.polish_reverted_for_morphology, "settle_iterations": settle_iterations,
        "extent_mm": extent.round(2).tolist(),
        "momentum": momentum, "polish_passes": polish, "momentum_resets": rep.momentum_resets,
        "polish_floor_pairs": rep.polish_floor_pairs, "polish_max_strain": rep.polish_max_strain,
        "retries": rep.retries, "largest_step_mm": rep.largest_step_mm, "final_step_mm": rep.final_step_mm,
        "iterations": rep.iterations, "converged": rep.converged, "stalled": rep.stalled,
        "support_violations": rep.support_violations,
        "min_gap_seen_mm": rep.min_gap_seen_mm, "max_strain": rep.max_strain,
        "energy_start_J": rep.energy_start_J, "energy_final_J": rep.energy_final_J,
        "energy_rejections": rep.energy_rejections, "morphology_rejections": rep.morphology_rejections,
        "max_out_of_plane_mm": rep.max_out_of_plane_mm,
        "fabric_relief": fabric, "wrapped_target_relief": target, "rigid_row_null": null,
        "articulation_flat_rms_deg": art_flat["articulation_rms_deg"],
        "articulation_draped_rms_deg": art_drp["articulation_rms_deg"],
        "validate_after": {k: v for k, v in val.items() if k != "checks"},
        "seconds": round(time.time() - t0, 1),
    }
    print(json.dumps(out, indent=1, default=str))
    return draped, out


if __name__ == "__main__":
    a = sys.argv[1:]
    main(a[0] if a else "hdc", int(a[1]) if len(a) > 1 else 5, int(a[2]) if len(a) > 2 else 5,
         float(a[3]) if len(a) > 3 else None, int(a[4]) if len(a) > 4 else 800,
         float(a[5]) if len(a) > 5 else 0.0, int(a[6]) if len(a) > 6 else 0,
         guard=bool(int(os.environ.get("SPHERE_GUARD", "0"))),
         bending=(float(os.environ["SPHERE_B"]) if os.environ.get("SPHERE_B") else None),
         settle_iterations=int(os.environ.get("SPHERE_SETTLE", "0")))
