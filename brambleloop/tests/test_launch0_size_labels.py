"""A Launch-0 size label is what the certified twin measures, to the label's own precision."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path[:0] = [str(ROOT / 'src'), str(ROOT)]
from brambleloop.products import launch0 as L


def test_every_launch0_variant_label_is_backed_by_its_twin():
    checked = 0
    for c in L.CANDIDATES:
        from brambleloop.cir.compiler import compile_cir
        from brambleloop.cir.twin import build_twin
        for v in c.variants:
            cir = L.cir_for(v.build); r = compile_cir(cir); assert r.ok, (c.slug, v.key)
            t = build_twin(cir, r)
            got = L.size_label_backed(v.label, t.width_cm, t.height_cm, twin=t)
            assert got["backed"], (c.slug, v.key, got)
            checked += 1
    assert checked >= 6


def test_a_hand_typed_label_that_drifted_from_the_twin_is_caught():
    # The large basket measures 24.4 x 23.2 cm; "25 cm across" was its old hand-typed label.
    assert not L.size_label_backed("25 cm across, 23 cm tall", 24.44, 23.19)["backed"]
    assert L.size_label_backed("24 cm across, 23 cm tall", 24.44, 23.19)["backed"]
    assert not L.size_label_backed("4 pieces, 9.6 cm across", 9.22, 9.22)["backed"]
    assert L.size_label_backed("79.2 x 96.4 cm", 79.2, 96.4)["backed"]
    assert not L.size_label_backed("one size", 10.0, 10.0)["backed"]  # no figure is not backed


def _twin(build):
    from brambleloop.cir.compiler import compile_cir
    from brambleloop.cir.twin import build_twin
    cir = L.cir_for(build)
    return build_twin(cir, compile_cir(cir))


def test_a_hexagon_label_must_name_its_convention():
    """PT-10: a stacked-increase piece is a hexagon with two 'across' measurements."""
    t = _twin("hexagon_coasters")
    assert t.sides == 6 and t.across_points_cm == 9.7 and t.across_flats_cm == 8.4
    ok = L.size_label_backed("4 pieces, 9.7 cm across the points, 8.4 cm across the flats",
                             None, None, twin=t)
    assert ok["backed"], ok
    # The old label: the circle formula, with no convention -- the size of no measurement.
    assert not L.size_label_backed("4 pieces, 9.2 cm across", None, None, twin=t)["backed"]
    # The right number with no convention is still ambiguous on a hexagon.
    assert not L.size_label_backed("4 pieces, 9.7 cm across", None, None, twin=t)["backed"]
    # Conventions swapped is caught.
    assert not L.size_label_backed("9.7 cm across the flats", None, None, twin=t)["backed"]
    b = _twin("basket_small")
    assert (b.across_points_cm, b.across_flats_cm) == (16.0, 13.9)
    assert not L.size_label_backed("15 cm across, 9 cm tall", None, None, twin=b)["backed"]
    assert L.size_label_backed("16.0 cm across the points, 13.9 cm across the flats, 9 cm tall",
                               None, None, twin=b)["backed"]


def test_hexagon_spans_are_the_perimeter_geometry():
    """60 sc at 12.5 sts/10 cm is a 48 cm perimeter: a hexagon of side 8 cm."""
    import math
    from brambleloop.cir.geometry import polygon_spans_cm
    pts, flats = polygon_spans_cm(48.0, 6)
    assert abs(pts - 16.0) < 1e-9 and abs(flats - 8 * math.sqrt(3)) < 1e-9


if __name__ == '__main__':
    failed = 0
    for k, f in list(globals().items()):
        if k.startswith('test_'):
            try: f(); print('OK  ', k)
            except Exception as e: failed += 1; print('FAIL', k, repr(e)[:300])
    sys.exit(1 if failed else 0)
