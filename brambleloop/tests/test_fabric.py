"""Deterministic fabric: the product's structure comes from the instructions.

Written after the provider trial returned product truth 0 of 12 (B-689). The fixtures here
are generic textured swatches, never a purchased pattern: what is under test is Brambleloop's
architecture, not anybody's product.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from brambleloop.cir.compiler import compile_cir
from brambleloop.cir.model import CIR, Component, Gauge, Op, Repeat, Row
from brambleloop.cir.twin import build_twin
from brambleloop.visual import fabric

GAUGE = Gauge(stitches_per_10cm=14.5, rows_per_10cm=9.5, stitch_type="hdc", hook_mm=6.0)
# The field between the rib band and the final stitch must hold whole BLO/FLO pairs, so
# `width - rib - 1` has to be even -- the same constraint the real stitch pattern satisfies
# by asking for a foundation chain of an even number of stitches.
WIDTH, RIB = 20, 5


def _waffle_row(i, a_row, width=WIDTH, rib=RIB):
    """A rib band at one edge, then a BLO/FLO field whose phase flips each row."""
    field = width - rib - 1
    assert field % 2 == 0, f"field of {field} cannot hold whole BLO/FLO pairs"
    first, second = ("front", "back") if a_row else ("back", "front")
    pair = Repeat([Op("hdc", loop=first), Op("hdc", loop=second)], times=field // 2)
    ops = ([Op("hdc", rib, loop="back"), pair, Op("hdc", 1)] if a_row
           else [pair, Op("hdc", rib, loop="back"), Op("hdc", 1)])
    return Row(index=i, ops=ops, declared_count=width, turning_chain=1)


def _cir(rows_n=10, width=WIDTH, textured=True):
    rows = [Row(index=1, ops=[Op("hdc", width)], declared_count=width, turning_chain=1)]
    for i in range(2, rows_n + 1):
        rows.append(_waffle_row(i, a_row=(i % 2 == 1), width=width) if textured
                    else Row(index=i, ops=[Op("hdc", width)], declared_count=width,
                             turning_chain=1))
    return CIR(slug="swatch", title="Swatch", version="1.0.0", construction="flat_rows",
               components=[Component("panel", "flat_rows", rows, foundation=width)],
               gauge=GAUGE)


def _twin(**kw):
    c = _cir(**kw)
    r = compile_cir(c)
    assert r.ok, [str(f) for f in r.errors]
    return c, build_twin(c, r)


def test_loop_targeting_does_not_change_any_stitch_count():
    """The whole point of the primitive: texture is count-neutral.

    If declaring a loop target moved a single number, every existing certified pattern would
    have to be re-verified before it could carry texture -- and the compiler's arithmetic,
    which is the one thing this system guarantees, would depend on a decorative field.
    """
    plain_c, plain = _twin(textured=False)
    tex_c, tex = _twin(textured=True)
    assert plain.stitch_total == tex.stitch_total
    assert plain.row_widths == tex.row_widths
    assert (plain.width_cm, plain.height_cm) == (tex.width_cm, tex.height_cm)


def test_the_fabric_grid_is_in_fabric_order_not_working_order():
    """Flat rows turn, so alternate rows are mirrored -- B-690.

    The integral rib is worked at one edge of every row. In working order it lands at
    opposite ends on alternate rows, which describes a rib zig-zagging across the fabric
    instead of the continuous band the garment actually has.
    """
    _, t = _twin(rows_n=8)
    bands = []
    for row in range(2, 7):
        cells = sorted((c for c in t.cells if c.row == row), key=lambda c: c.fabric_position)
        backs = [c.fabric_position for c in cells if c.loop == "back"]
        runs, cur = [], [backs[0]]
        for p in backs[1:]:
            (cur.append(p) if p == cur[-1] + 1 else (runs.append(cur), cur.clear(), cur.append(p)))
        runs.append(list(cur))
        bands.append(min(max(runs, key=len)))
    assert max(bands) - min(bands) <= 1, (
        f"the rib band moved across the fabric between rows: {bands}. Working-order "
        f"positions were being read as fabric positions")


def test_a_plain_fabric_is_reported_as_untextured_rather_than_guessed():
    """Absence of texture is drawn and reported as absence."""
    _, t = _twin(textured=False)
    sig = fabric.texture_signature(t)
    assert sig["textured"] is False
    assert "flat" in sig["why"]


def test_the_surface_is_classified_from_both_axes_not_one_threshold():
    """A checkerboard and a ridge differ only in the between-row offset.

    Thresholding on alternation alone would call both of them ridges, which asserts a
    direction the measurement cannot support.
    """
    _, t = _twin(rows_n=12)
    sig = fabric.texture_signature(t)
    assert sig["textured"] is True
    assert sig["alternation_along_row"] >= 0.5
    assert sig["offset_between_rows"] >= 0.5, (
        "alternating phase between rows is what makes a waffle rather than stripes")
    assert sig["surface"] == "checkered"


def test_it_never_claims_an_orientation_on_the_worn_garment():
    """Which fabric axis is vertical depends on grain, which the CIR does not carry.

    Naming a direction anyway would be a claim about the finished object derived from
    information nobody recorded -- the defect this codebase keeps finding.
    """
    _, t = _twin()
    sig = fabric.texture_signature(t)
    assert "grain" in sig["orientation_is_in_fabric_axes"]
    assert "vertical" not in sig["surface"]


def test_the_swatch_draws_one_rect_per_counted_stitch_and_invents_none():
    """Product truth by construction: nothing in the drawing that is not in the fabric."""
    c, t = _twin(rows_n=6, width=10)
    svg = fabric.swatch_svg(t, GAUGE, scale=4.0)
    drawn = svg.count("<rect") - 1                      # less the background
    bars = sum(1 for cell in t.cells if cell.loop in ("front", "back"))
    assert drawn == t.stitch_total + bars, (
        f"drew {drawn} rects for {t.stitch_total} stitches and {bars} unworked loops")


def test_the_swatch_geometry_comes_from_the_gauge():
    """A cell's size is the gauge's own arithmetic, so the swatch and the size claim agree."""
    w_mm, h_mm = fabric.cell_size_mm(GAUGE)
    assert round(w_mm, 3) == round(100.0 / 14.5, 3)
    assert round(h_mm, 3) == round(100.0 / 9.5, 3)
    _, t = _twin(rows_n=4, width=10)
    svg = fabric.swatch_svg(t, GAUGE, scale=1.0)
    assert f'width="{10 * w_mm:.0f}"' in svg


def test_a_textured_pattern_is_distinguishable_from_a_plain_one_by_measurement():
    """The regression that matters: texture must be *measurable*, not merely present.

    A representation that cannot tell its own textured fabric from plain fabric is exactly
    the count-perfect, texture-blind CIR this work existed to fix.
    """
    _, plain = _twin(textured=False)
    _, tex = _twin(textured=True)
    assert fabric.texture_signature(plain)["textured"] is False
    assert fabric.texture_signature(tex)["textured"] is True
    assert fabric.swatch_svg(plain, GAUGE) != fabric.swatch_svg(tex, GAUGE)


if __name__ == "__main__":
    import traceback
    fails = 0
    for name, fn in sorted(list(globals().items())):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print("OK  ", name)
            except Exception as e:
                fails += 1
                print("FAIL", name, repr(e)); traceback.print_exc()
    print(f"\n{'PASS' if not fails else 'FAIL'}: {fails} failing")
    sys.exit(1 if fails else 0)
