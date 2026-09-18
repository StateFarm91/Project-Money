"""Accessibility and localization (Master Plan section 31).

The section asks for two things the rest of the system had no test for: customer-facing
patterns that can gain another language without forking the canonical CIR, and
"colour-independent cues where practical".

The second was a real hole, and the most expensive kind: everything about the charts was
correct and internally consistent, and a maker with a colour vision deficiency still could
not read one. Twelve of the nineteen designs are two-colour mosaic or tapestry work, where
the colour *is* the motif rather than a decoration -- and the chart distinguished the yarns
by hue alone, with a legend whose only identifier for each yarn was a coloured square. A
sighted maker recovers from a bad chart by looking harder. This maker cannot: there is
nothing in the image that says which yarn a square meant.

So the tests below hold the chart to a property rather than to an appearance. Render it, then
ask whether two squares worked in *different yarns that look identical* are still
distinguishable. If they are, the cue is doing the work; if the test passes only because
cream is lighter than pine, it is testing the palette and would go green again the day
someone picks two similar colours.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.cir.compiler import compile_cir  # noqa: E402
from brambleloop.cir.model import CIR, Component, Gauge, Material, Op, Row  # noqa: E402
from brambleloop.cir.twin import build_twin  # noqa: E402
from brambleloop.cir.writer import write_pattern  # noqa: E402
from brambleloop.publish import charts as charts_mod  # noqa: E402
from brambleloop.publish import listing_assets as la  # noqa: E402
from brambleloop.publish.charts import (  # noqa: E402
    ChartSpec, color_letters, render_chart, render_legend,
)

GAUGE = Gauge(stitches_per_10cm=20, rows_per_10cm=24, stitch_type="sc", hook_mm=4.0)


def _two_colour(hex_a: str = "#244A3A", hex_b: str = "#FAF6EB") -> CIR:
    """A small two-colour chequerboard: the shape of every mosaic design we publish."""
    rows: list[Row] = []
    for index in range(1, 9):
        rows.append(Row(index=index, ops=[Op("sc", 8)], declared_count=8,
                        color="alpha" if index % 2 else "beta", turning_chain=1))
    return CIR(
        slug="cue-test", title="Cue Test Cloth", version="1.0.0",
        construction="flat_rows", risk_class="A",
        colors={"alpha": hex_a, "beta": hex_b}, gauge=GAUGE,
        materials=[Material(name="worsted cotton", yarn_weight="worsted",
                            colorway="alpha", color_id="alpha"),
                   Material(name="worsted cotton", yarn_weight="worsted",
                            colorway="beta", color_id="beta")],
        components=[Component(name="cloth", construction="flat_rows", rows=rows,
                              foundation=8)],
    )


def _one_colour() -> CIR:
    rows = [Row(index=i, ops=[Op("sc", 8)], declared_count=8, color="alpha",
                turning_chain=1) for i in range(1, 9)]
    return CIR(
        slug="plain-test", title="Plain Test Cloth", version="1.0.0",
        construction="flat_rows", risk_class="A",
        colors={"alpha": "#244A3A"}, gauge=GAUGE,
        materials=[Material(name="worsted cotton", yarn_weight="worsted",
                            colorway="alpha", color_id="alpha")],
        components=[Component(name="cloth", construction="flat_rows", rows=rows,
                              foundation=8)],
    )


def _twin(cir: CIR):
    result = compile_cir(cir)
    assert result.ok, [str(f) for f in result.errors]
    return result, build_twin(cir, result)


def _row_bands(img, cells: int, rows: int):
    """The rendered pixels of the middle of row 1 and the middle of row 2.

    Taken from the chart's own geometry rather than by searching for colours, so the
    comparison is between two known squares instead of whatever the sampler happened to hit.
    """
    from brambleloop.publish.charts import ChartSpec as _Spec

    spec = _Spec()
    cell = spec.cell_px
    grid_w = cells * cell
    left = (img.width - grid_w) // 2
    bottom_y = spec.margin_px + (rows - 1) * cell      # row 1 sits at the bottom
    second_y = spec.margin_px + (rows - 2) * cell
    box = (left + cell, cell)                          # the second square along
    return (img.crop((box[0], bottom_y, box[0] + cell, bottom_y + cell)),
            img.crop((box[0], second_y, box[0] + cell, second_y + cell)))


def test_two_yarns_that_look_identical_are_still_distinguishable_on_the_chart():
    """The property, tested where colour cannot help.

    Both yarns are given the *same* hex, which is the situation a colour-blind maker is in
    for any two colours they cannot separate. If the two squares still differ, something
    other than hue is carrying the information. Testing it with cream and pine instead would
    pass on the palette alone and go green again the day a designer picks two similar
    colours -- which is exactly when the maker needs it most.
    """
    cir = _two_colour(hex_a="#7A7A7A", hex_b="#7A7A7A")
    _, twin = _twin(cir)
    img = render_chart(cir, twin)
    one, two = _row_bands(img, cells=8, rows=8)
    assert one.tobytes() != two.tobytes(), (
        "two squares worked in different yarns render identically, so this chart can only "
        "be read by someone who can tell the colours apart")


def test_the_cue_is_the_colours_letter_and_the_legend_agrees():
    """A letter on the chart that the legend does not explain is a riddle, not a cue."""
    cir = _two_colour()
    _, twin = _twin(cir)
    cues = color_letters(cir)
    assert cues == {"alpha": "A", "beta": "B"}, cues

    # Rendering must not move them: the letter is an index into the CIR's colour order, so
    # it has to be the same in the chart, the legend and any future translation.
    assert color_letters(cir) == cues
    legend = render_legend(cir, twin)
    assert legend.width > 0 and legend.height > 0
    # The legend grows by one line for the sentence explaining the letters, which is the
    # cheapest available check that it rendered the multi-colour branch at all.
    plain_legend = render_legend(_one_colour(), _twin(_one_colour())[1])
    assert legend.height > plain_legend.height


def test_a_single_colour_chart_carries_no_letters():
    """Accessibility that adds noise is not accessibility.

    A one-colour chart marked "A" in every square says nothing and crowds the stitch glyph,
    which is the thing that square does have to say.
    """
    cir = _one_colour()
    assert color_letters(cir) == {"alpha": "A"}, "the mapping itself is unconditional"

    _, twin = _twin(cir)
    charts_mod.reset_render_flags()
    img = render_chart(cir, twin)
    one, two = _row_bands(img, cells=8, rows=8)
    assert one.tobytes() == two.tobytes(), (
        "two squares of the same yarn and the same stitch rendered differently, so "
        "something is being drawn that carries no information")
    assert charts_mod.COLOR_CUE_MISSING is False


def test_a_chart_too_small_for_a_cue_is_reported_rather_than_shipped():
    """The honest failure. A cue that does not fit is a fact, not a silence.

    This is the same discipline as the font fallback: the render succeeds, the image looks
    plausible, and the one customer who needs the cue cannot use the file. So the renderer
    records it and the frame plan blocks on it.
    """
    from brambleloop.publish.pdf import build_pattern_pdf

    cir = _two_colour()
    result, twin = _twin(cir)

    # A real frame list, built first so that `build_frames` clearing the flags cannot hide
    # the thing under test. These frames are otherwise fine: the only problem is the cue.
    doc = build_pattern_pdf(cir, twin=twin, terminology="US")
    frames = la.build_frames(cir, twin, pattern_text=write_pattern(cir, result),
                             difficulty="intermediate", pages=doc.pages, siblings=[])
    assert not la.check_frame_plan(frames), "these frames were supposed to be clean"

    charts_mod.reset_render_flags()
    render_chart(cir, twin, ChartSpec(cell_px=8))
    assert charts_mod.COLOR_CUE_MISSING is True, \
        "a chart drawn too small to carry its colour cue reported nothing"
    problems = la.check_frame_plan(frames)
    assert any(p.startswith("LISTING_CHART_COLOR_ONLY") for p in problems), problems

    charts_mod.reset_render_flags()
    render_chart(cir, twin, ChartSpec(cell_px=26))
    assert charts_mod.COLOR_CUE_MISSING is False
    assert not la.check_frame_plan(frames)

    # And nothing accumulated is thrown away by the empty-frames case, which used to return
    # LISTING_NO_IMAGES on its own and discard whatever the renderer had recorded.
    charts_mod.reset_render_flags()
    render_chart(cir, twin, ChartSpec(cell_px=8))
    empty = la.check_frame_plan([])
    assert any(p.startswith("LISTING_CHART_COLOR_ONLY") for p in empty), empty
    assert any(p.startswith("LISTING_NO_IMAGES") for p in empty), empty


def test_one_products_missing_cue_does_not_accuse_the_next_product():
    """A sticky flag turns a real check into noise that gets ignored.

    The worker renders every product in one process, so a flag set by one chart and never
    cleared would block every product rendered after it. `build_frames` clears them, which
    is the only place that knows a new product's imagery is starting.
    """
    from brambleloop.publish.pdf import build_pattern_pdf

    bad = _two_colour()
    _, bad_twin = _twin(bad)
    charts_mod.reset_render_flags()
    render_chart(bad, bad_twin, ChartSpec(cell_px=8))
    assert charts_mod.COLOR_CUE_MISSING is True

    good = _two_colour()
    result, twin = _twin(good)
    doc = build_pattern_pdf(good, twin=twin, terminology="US")
    frames = la.build_frames(good, twin, pattern_text=write_pattern(good, result),
                             difficulty="intermediate", pages=doc.pages, siblings=[])
    assert charts_mod.COLOR_CUE_MISSING is False, \
        "the previous product's problem is still being reported against this one"
    assert not any(p.startswith("LISTING_CHART_COLOR_ONLY")
                   for p in la.check_frame_plan(frames))


def test_every_multi_colour_product_in_the_catalogue_carries_the_cue():
    """The point of the whole exercise: not that the capability exists, that it is used.

    Twelve of the designs are two-colour work. A cue that the catalogue does not actually
    carry would be a capability with no customer.
    """
    from brambleloop.products import nordic_forest as nf
    from brambleloop.products.builder import CATALOGUE, build
    from brambleloop.publish.pdf import build_pattern_pdf

    designs = [("nordic-forest-mosaic-throw", nf.build())]
    designs += [(slug, build(CATALOGUE[slug])) for slug in sorted(CATALOGUE)]

    multi = 0
    for slug, cir in designs:
        result, twin = _twin(cir)
        if len(twin.colors_used) < 2:
            continue
        multi += 1
        doc = build_pattern_pdf(cir, twin=twin, terminology="US")
        frames = la.build_frames(cir, twin, pattern_text=write_pattern(cir, result),
                                 difficulty="intermediate", pages=doc.pages, siblings=[])
        problems = la.check_frame_plan(frames)
        assert not problems, (slug, problems)
        assert len(color_letters(cir)) >= 2, slug
    assert multi >= 10, f"only {multi} multi-colour designs found; the catalogue changed"


def test_a_round_chart_labels_its_rounds_and_refuses_to_label_a_mixed_one():
    """A wrong label is worse than a missing one.

    Every round-worked design in the catalogue is one colour per round, so the cue rides on
    the round number instead of being repeated around sixty wedges. The CIR permits a round
    worked in two colours, though, and one letter beside such a ring would say something
    untrue about half of it -- so that case reports no cue rather than an inaccurate one.
    """
    from brambleloop.products.vessels import build_hexagon_coaster
    from brambleloop.publish.charts import render_round_chart

    cir = build_hexagon_coaster()
    result, twin = _twin(cir)
    assert len(twin.colors_used) >= 2, "this design stopped being multi-colour"

    charts_mod.reset_render_flags()
    img = render_round_chart(cir, twin)
    assert img.width > 0
    assert charts_mod.COLOR_CUE_MISSING is False, \
        "a round chart with one colour per round should be able to label them"

    # The fabric view carries no labels at all by design, so it is not accused of missing a
    # cue: the chart page beside it is where a maker reads the colours.
    charts_mod.reset_render_flags()
    render_round_chart(cir, twin, plain=True)
    assert charts_mod.COLOR_CUE_MISSING is False

    # Now a round genuinely worked in two colours. Hand-built rather than found in the
    # catalogue, because no product does this today and the branch still has to be right.
    mixed = build_hexagon_coaster()

    charts_mod.reset_render_flags()
    _, mixed_twin = _twin(mixed)
    target = max(c.row for c in mixed_twin.cells)
    for cell in mixed_twin.cells:
        if cell.row == target and cell.position % 2:
            cell.color = next(c for c in mixed.colors if c != cell.color)
    assert len({c.color for c in mixed_twin.cells if c.row == target}) == 2
    render_round_chart(mixed, mixed_twin)
    assert charts_mod.COLOR_CUE_MISSING is True, \
        "a round worked in two colours was given a single letter, which is a wrong label"


def test_a_caption_wraps_rather_than_stretching_a_round_chart_into_a_rectangle():
    """A defect this session caused, so it gets a fixture (Gate B).

    Adding one sentence to the round chart's footer -- the sentence explaining the colour
    letters -- widened the canvas to fit it on one line and turned a disc chart into a 2:1
    rectangle that was mostly empty cream with a small circle in it. That is the exact shape
    the round renderer exists to stop producing, and `test_a_round_piece_gets_a_round_chart`
    caught it. The footer wraps now; height is cheap and aspect is not.

    Pinned against a deliberately absurd caption rather than against today's wording, so it
    keeps holding whatever anyone writes in the footer next.
    """
    from brambleloop.products.vessels import build_hexagon_coaster
    from brambleloop.publish.charts import ChartSpec, _wrap, render_round_chart
    from PIL import Image, ImageDraw

    cir = build_hexagon_coaster()
    _, twin = _twin(cir)
    chart = render_round_chart(cir, twin, ChartSpec(cell_px=20))
    assert 0.6 < chart.width / chart.height < 1.7, chart.size

    very_long = "word " * 120
    stretched = render_round_chart(cir, twin, ChartSpec(cell_px=20), caption=very_long.strip())
    assert stretched.width / stretched.height < 3.0, (
        "a long caption is still stretching the canvas instead of wrapping", stretched.size)

    # And the wrapper keeps every word: an over-long line is ugly, a missing one is a lie
    # about what the image says.
    draw = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    font = None
    from brambleloop.publish.charts import _font

    font = _font(15)
    text = "Round 1 is the centre and the letter after a round number is its yarn"
    lines = _wrap(draw, text, font, 120)
    assert len(lines) > 1, lines
    assert " ".join(lines).split() == text.split(), lines

    assert _wrap(draw, "", font, 100) == [""]
    assert _wrap(draw, "unbreakablesinglewordfarwiderthantheline", font, 10) == [
        "unbreakablesinglewordfarwiderthantheline"]


def test_the_written_pattern_names_the_yarn_so_a_translation_has_something_to_carry():
    """Section 31's other half: another language must not fork the canonical CIR.

    The CIR holds no prose. Terminology is rendered at write time (US canonical, UK
    downstream), and the colour is named on every row of a multi-colour pattern, so a
    translated document is another render of the same certified design rather than a second
    source of truth that can drift from it.
    """
    cir = _two_colour()
    result, _ = _twin(cir)
    us = write_pattern(cir, result, terminology="US")
    uk = write_pattern(cir, result, terminology="UK")
    assert us != uk, "terminology is not being rendered at all"
    assert "alpha" in us and "beta" in us, \
        "the written pattern does not name its yarns, so a translation has nothing to carry"

    # And the CIR itself is unchanged by either render: one design, many documents.
    assert cir.to_dict() == _two_colour().to_dict()


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
