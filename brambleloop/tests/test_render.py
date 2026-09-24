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
