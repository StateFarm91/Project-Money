"""Raster rendering of certified fabric. Structure from the twin, appearance from drawing.

These test that the renderer draws what the CIR says and refuses what it cannot show. They
deliberately do NOT test that the result looks photographic, because it does not -- see
BUILD_STATE 2026-09-24 and B-704. A test asserting "looks real" would either be a vision call
in the suite or a lie.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from brambleloop.cir import benchmarks as B
from brambleloop.cir.compiler import compile_cir
from brambleloop.cir.twin import build_twin
from brambleloop.visual import render


def _twin(component="body"):
    c = B.cardigan("S")
    r = compile_cir(c)
    assert r.ok
    return c, build_twin(c, r, component=component)


def test_it_refuses_a_scale_too_small_to_show_a_stitch():
    """Below a certain size this is a chart pretending to be a fabric."""
    c, t = _twin()
    try:
        render.fabric_raster(t, c.gauge, px_per_stitch=8)
    except ValueError as exc:
        assert "chart, not a fabric" in str(exc)
    else:
        raise AssertionError("rendered a fabric too small to have stitches in it")


def test_the_raster_is_deterministic_for_a_given_seed():
    """The same CIR renders the same fabric, or the irregularity is noise rather than grain."""
    c, t = _twin()
    kw = dict(px_per_stitch=22, max_rows=5, max_cols=6)
    a = render.fabric_raster(t, c.gauge, seed=11, **kw)
    b = render.fabric_raster(t, c.gauge, seed=11, **kw)
    assert a.tobytes() == b.tobytes()
    assert render.fabric_raster(t, c.gauge, seed=12, **kw).tobytes() != a.tobytes()


def test_the_stitch_aspect_comes_from_the_gauge():
    """Certified geometry decides the stitch's shape, not the renderer's convenience."""
    c, t = _twin()
    img = render.fabric_raster(t, c.gauge, px_per_stitch=30, max_rows=4, max_cols=5)
    assert img.width == 5 * 30
    # Taller than wide per stitch, because this gauge's rows are taller than its stitches.
    assert img.height > 4 * 30 * 0.5


def test_loop_targeting_changes_the_drawing():
    """If back-loop and front-loop fabric render identically, the texture is decorative."""
    c, t = _twin()
    kw = dict(px_per_stitch=24, max_rows=6, max_cols=8, seed=5)
    textured = render.fabric_raster(t, c.gauge, **kw)
    for cell in t.cells:
        cell.loop = "both"
    plain = render.fabric_raster(t, c.gauge, **kw)
    assert textured.tobytes() != plain.tobytes()


def test_the_height_field_is_greyscale_and_matches_the_raster_geometry():
    c, t = _twin()
    kw = dict(px_per_stitch=26, max_rows=5, max_cols=7, seed=2)
    assert render.height_field(t, c.gauge, **kw).mode == "L"
    assert render.height_field(t, c.gauge, **kw).size == \
        render.fabric_raster(t, c.gauge, **kw).size


def test_the_broken_lighting_helpers_are_absent_rather_than_shipped_broken():
    """A function that is present and does not work is worse than an absent one.

    `light()` and `lit_fabric()` produced crushed, far-too-dark output. They were removed
    rather than left in the tree for somebody to call, see output from, and trust.
    """
    assert not hasattr(render, "light")
    assert not hasattr(render, "lit_fabric")


# ------------------------------------------------------------------------------------------
# WAVE 5 -- the physically based scene, committed so a comparison can be repeated.
#
# Mitsuba is NOT a dependency (requirements.txt says so and why), so nothing here renders.
# What is tested is everything above the renderer: what gets drawn, what deliberately does
# not, and that the staging is one fixed description rather than a sentence in a commit
# message. research/VISUAL_WAVE5.md.
# ------------------------------------------------------------------------------------------
import numpy as np                                                    # noqa: E402
from brambleloop.visual import crochet_topology as CT                 # noqa: E402
from brambleloop.visual import drape as DR                            # noqa: E402
from brambleloop.visual import pbr_scene as PS                        # noqa: E402
from brambleloop.visual import relaxation as RX                       # noqa: E402


def _fabric():
    c, t = _twin()
    return RX.relax(CT.settle(CT.build(t, c.gauge, max_rows=3, max_cols=3)),
                    iterations=120)[0]


def test_the_scene_does_not_draw_the_paths_artificial_hops_as_yarn():
    fab = _fabric()
    seg = np.linalg.norm(np.diff(np.asarray(fab.points, float), axis=0), axis=1)
    bad = int(((seg >= DR.JUMP_SEGMENT_MM) | (seg <= DR.DEGENERATE_SEGMENT_MM)).sum())
    strands = PS.fabric_strands(fab, per_segment=1)
    assert bad > 0, "this fixture is supposed to contain hops and joins"
    # One cut per artefact segment, so the strand count is bounded by it and is never one.
    assert 1 < len(strands) <= bad + 1, (len(strands), bad)
    for s in strands:
        d = np.linalg.norm(np.diff(s, axis=0), axis=1)
        assert d.max() < DR.JUMP_SEGMENT_MM and d.min() > DR.DEGENERATE_SEGMENT_MM


def test_smoothing_interpolates_and_never_moves_a_control_point():
    fab = _fabric()
    raw = PS.fabric_strands(fab, per_segment=1)
    smooth = PS.fabric_strands(fab, per_segment=6)
    assert len(raw) == len(smooth)
    for a, b in zip(raw, smooth):
        assert len(b) >= len(a)
        # every control point still appears in the smoothed strand
        for p in a:
            assert np.abs(b - p).sum(axis=1).min() < 1e-9


def test_the_curve_file_carries_the_fabrics_own_yarn_radius():
    import tempfile, os
    fab = _fabric()
    path = os.path.join(tempfile.mkdtemp(), "c.txt")
    strands, verts = PS.write_curve_file(fab, path)
    text = open(path).read().strip().splitlines()
    radii = {round(float(line.split()[3]), 5) for line in text if line.strip()}
    assert radii == {round(fab.yarn_diameter / 2.0, 5)}, radii
    assert verts == sum(len(s) for s in PS.fabric_strands(fab)) and strands > 1


def test_two_fabrics_compared_under_this_scene_get_the_same_camera_and_lights():
    # The point of committing the staging: everything but the curve file is identical for two
    # renders framed by the same fabric, and that is checkable rather than asserted in prose.
    flat = _fabric()
    draped = DR.drape(flat, DR.DrapeSetup(
        linear_density_kg_m=DR.areal_mass(flat, 444.0)["linear_density_kg_m"],
        clamp_fraction=0.5, iterations=60))[0]
    assert PS.framing_centre(draped) != PS.framing_centre(flat), "the drape moved nothing"
    centre = PS.framing_centre(flat)
    a = PS.scene_dict("flat.txt", centre)
    b = PS.scene_dict("draped.txt", centre)
    for key in ("sensor", "integrator", "backdrop", "key", "fill"):
        assert a[key] == b[key], key
    assert a["yarn"]["bsdf"] == b["yarn"]["bsdf"]
    assert a["yarn"]["filename"] != b["yarn"]["filename"]
    # and the camera is framed ON the reference, not on whatever it is pointed at
    assert a["sensor"]["to_world"][2] == tuple(centre)
    assert a["sensor"]["to_world"][1] != tuple(centre)


def test_the_scene_states_which_yarn_layers_it_does_not_reproduce():
    # The Layer 1-5 ladder -- plies, fibre, surface fuzz, hand -- is a separate committed
    # result at a far higher standard than this scene reaches. A comparison instrument that
    # did not say so would read as a claim about appearance.
    doc = PS.__doc__ + str(PS.STAGING)
    assert "never committed" in PS.__doc__
    assert "Layer 1-5" in doc
    assert "fibre halo" in PS.STAGING["not_reproduced"]
    assert "ply wobble" in PS.STAGING["not_reproduced"]
    assert "surface fuzz" in PS.STAGING["not_reproduced"]


# --- wave 6: the bridge between the certified geometry and the yarn as it is built --------
def test_the_plied_writer_draws_the_certified_strands_and_nothing_else():
    import tempfile, os
    fab = _fabric()
    path = os.path.join(tempfile.mkdtemp(), "plied.txt")
    info = PS.write_plied_curve_file(fab, path, tex=444.0, fibres_per_ply=3)
    strands = PS.fabric_strands(fab)
    assert info["strands"] == len(strands)
    assert info["plies"] == 4 * len(strands), info
    assert info["fibres"] == 3 * info["plies"], info
    blocks = [b for b in open(path).read().split("\n\n") if b.strip()]
    assert len(blocks) == info["plies"] + info["fibres"]
    # every ply vertex lies within the yarn radius of its own strand: geometry derived from
    # the validated centreline, never a second geometry
    r_yarn = fab.yarn_diameter / 2.0
    at = 0
    for k, s in enumerate(strands):
        for _ in range(4):
            v = np.array([[float(x) for x in line.split()[:3]] for line in blocks[at].splitlines()])
            d = np.linalg.norm(v[:, None, :] - s[None, :, :], axis=2).min(axis=1)
            assert d.max() <= 1.05 * r_yarn, (k, d.max(), r_yarn)
            at += 1
        at += 3 * 4          # the strand's fibres follow its plies
    radii = {round(float(line.split()[3]), 5) for line in open(path) if line.strip()}
    assert round(info["ply_radius_mm"], 5) in radii and round(info["fibre_radius_mm"], 5) in radii
    assert abs(info["fibre_radius_mm"] - 0.00943) < 1e-4, "the fibre radius is derived, 18.9um"


def test_the_plied_writer_moves_no_control_point():
    import tempfile, os, hashlib
    fab = _fabric()
    before = hashlib.sha256(np.ascontiguousarray(fab.points).tobytes()).hexdigest()
    PS.write_plied_curve_file(fab, os.path.join(tempfile.mkdtemp(), "p.txt"), tex=444.0)
    after = hashlib.sha256(np.ascontiguousarray(fab.points).tobytes()).hexdigest()
    assert before == after


def test_the_plied_staging_differs_from_the_committed_one_only_in_what_it_admits():
    keys = {k for k in set(PS.STAGING) | set(PS.STAGING_PLIED)
            if PS.STAGING.get(k) != PS.STAGING_PLIED.get(k)}
    assert keys == {"not_reproduced", "reproduced_as_geometry"}, keys
    assert "fibre surface normal map" in PS.STAGING_PLIED["not_reproduced"]
    assert "hand tension drift" in PS.STAGING_PLIED["not_reproduced"]
    assert "plies" in " ".join(PS.STAGING_PLIED["reproduced_as_geometry"])
    # the render says which staging it used, so a picture cannot be passed off as the other
    import inspect
    src = inspect.getsource(PS.render)
    assert "STAGING_PLIED" in src and '"not_reproduced": staging["not_reproduced"]' in src


if __name__ == "__main__":
    import traceback
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print("OK  ", name)
            except Exception as e:
                fails += 1; print("FAIL", name, repr(e)); traceback.print_exc()
    print(f"\n{'PASS' if not fails else 'FAIL'}: {fails} failing")
    sys.exit(1 if fails else 0)
