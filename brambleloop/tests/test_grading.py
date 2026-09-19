"""Size grading: the primitive a fitted garment cannot exist without.

Every garment concept in the v1.4.3 spec — the cropped cardigan it uses as its worked example,
most of the garments pod — has to exist in a run of sizes. A size run is where hand-written
patterns most often fail: the medium gets checked and the extra-large is arithmetic nobody
re-did.

The failures here all compile. That is what makes them worth a test rather than a comment.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.cir import grading as g  # noqa: E402


def _run() -> list[g.SizeSpec]:
    return [g.SizeSpec("XS", 81, 10, 52), g.SizeSpec("S", 86, 10, 54),
            g.SizeSpec("M", 96, 11, 56), g.SizeSpec("L", 107, 11, 58),
            g.SizeSpec("XL", 117, 12, 60), g.SizeSpec("2XL", 127, 12, 62)]


def test_every_size_is_a_whole_number_of_motif_repeats():
    """A rounded stitch count produces half a motif at one edge.

    It compiles, it passes every count check in the system, and it is a visible defect on the
    finished object — which is the worst combination available.
    """
    graded = g.grade(_run(), stitches_per_10cm=16, rows_per_10cm=18, motif_width=8)

    assert len(graded) == 6
    for size in graded:
        assert size.stitches % 8 == 0, f"{size.spec.name} is not a whole motif count"
        assert size.motif_repeats * 8 == size.stitches
        assert size.rows > 0

    # And the counts rise with the sizes.
    counts = [s.stitches for s in graded]
    assert counts == sorted(counts)


def test_a_size_run_the_motif_cannot_tile_is_refused_rather_than_rounded():
    """The real case, found the first time this was run against plausible numbers.

    A twelve-stitch motif at 16 sts/10cm cannot express a 2XL within 2cm of its target. The
    honest fixes are a narrower motif, a different gauge or fewer sizes — and the refusal
    names all three rather than leaving somebody to guess why it said no.
    """
    try:
        g.grade(_run(), stitches_per_10cm=16, rows_per_10cm=18, motif_width=12)
    except g.GradingRefused as e:
        message = str(e)
        assert "2XL" in message
        assert "not the size it claims" in message
        assert "narrower motif" in message and "different gauge" in message
    else:
        raise AssertionError("a size run that drifts 3.5cm from target was accepted")

    # Narrower motifs do close, which is what makes the refusal actionable rather than fatal.
    for width in (4, 6, 8):
        assert len(g.grade(_run(), stitches_per_10cm=16, rows_per_10cm=18,
                           motif_width=width)) == 6


def test_a_design_with_no_motif_may_use_any_stitch_count():
    """Plain fabric has no repeat to break, so refusing it would be pedantry.

    But the permission is explicit and off by default: a design *with* a motif that silently
    allowed a partial one is the defect this module exists to prevent.
    """
    plain = g.grade(_run(), stitches_per_10cm=16, rows_per_10cm=18, motif_width=1)
    assert len(plain) == 6

    forced = g.grade(_run(), stitches_per_10cm=16, rows_per_10cm=18, motif_width=12,
                     allow_partial_motif=True)
    assert len(forced) == 6
    assert any(s.stitches % 12 for s in forced), \
        "allow_partial_motif did nothing, so the flag is not what stops the refusal"


def test_a_size_run_that_goes_backwards_is_refused():
    """The failure that compiles perfectly and is found by a customer.

    One transposed number in a size table gives a 2XL narrower shoulders than an XL. Every
    stitch count is internally consistent; the garment is simply wrong.
    """
    backwards = [g.SizeSpec("S", 86, 10, 54), g.SizeSpec("M", 80, 10, 56)]
    try:
        g.grade(backwards, stitches_per_10cm=16, rows_per_10cm=18)
    except g.GradingRefused as e:
        assert "does not increase" in str(e)
        assert "found by a customer" in str(e)
    else:
        raise AssertionError("a size run that shrank was accepted")

    shorter = [g.SizeSpec("S", 86, 10, 56), g.SizeSpec("M", 96, 10, 54)]
    try:
        g.grade(shorter, stitches_per_10cm=16, rows_per_10cm=18)
    except g.GradingRefused as e:
        assert "length_cm" in str(e)
    else:
        raise AssertionError("a size run that got shorter was accepted")


def test_ease_is_declared_per_size_rather_than_scaled():
    """Five centimetres is generous on a small and negligible on a 3XL.

    Scaling ease with the body is the intuitive implementation and it produces a size run
    where the fit changes as the sizes grow.
    """
    sizes = _run()
    eases = [s.ease_cm for s in sizes]
    assert eases == sorted(eases), "ease should be declared, and here it rises deliberately"

    for spec in sizes:
        assert spec.finished_bust_cm == round(spec.bust_cm + spec.ease_cm, 1)

    negative = [g.SizeSpec("S", 86, -4, 54), g.SizeSpec("M", 96, 10, 56)]
    try:
        g.grade(negative, stitches_per_10cm=16, rows_per_10cm=18)
    except g.GradingRefused as e:
        assert "smaller than the body" in str(e)
    else:
        raise AssertionError("negative ease was accepted")


def test_grading_a_component_moves_the_counts_and_not_the_construction():
    """A design whose construction changes between sizes is several designs sharing a name."""
    from brambleloop.cir.model import Component, Op, Row

    component = Component(
        name="body", construction="flat_rows", foundation=100,
        rows=[Row(index=1, ops=[Op("dc", 100)], declared_count=100),
              Row(index=2, ops=[Op("dc", 100)], declared_count=100)])

    graded = g.grade(_run(), stitches_per_10cm=16, rows_per_10cm=18, motif_width=8)
    large = [s for s in graded if s.spec.name == "L"][0]
    resized = g.grade_component(component, large, motif_width=8)

    assert resized.foundation == large.stitches
    assert resized.construction == component.construction
    assert len(resized.rows) == len(component.rows)
    assert all(r.declared_count == large.stitches for r in resized.rows)


def test_the_size_table_says_the_two_things_a_maker_needs_to_know():
    """Gauge governs the outcome, and no size was rounded to fit."""
    graded = g.grade(_run(), stitches_per_10cm=16, rows_per_10cm=18, motif_width=8)
    table = g.size_table(graded)

    assert len(table["sizes"]) == 6
    assert "gauge swatch is not optional" in table["gauge_note"]
    assert "No size was rounded" in table["motif_note"]
    assert all("finished_bust_cm" in row for row in table["sizes"])


def test_degenerate_inputs_are_refused_rather_than_producing_a_pattern():
    for kwargs in ({"stitches_per_10cm": 0, "rows_per_10cm": 18},
                   {"stitches_per_10cm": 16, "rows_per_10cm": 0}):
        try:
            g.grade(_run(), **kwargs)
        except g.GradingRefused as e:
            assert "gauge must be positive" in str(e)
        else:
            raise AssertionError(f"accepted {kwargs}")

    try:
        g.grade([], stitches_per_10cm=16, rows_per_10cm=18)
    except g.GradingRefused as e:
        assert "not a size run" in str(e)
    else:
        raise AssertionError("an empty size run was graded")


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, repr(e))
    sys.exit(1 if fails else 0)
