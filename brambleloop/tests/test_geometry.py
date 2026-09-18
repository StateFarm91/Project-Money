"""Construction beyond flat rows: what may be claimed about a piece worked in the round.

The flat model is a trap here, and a quiet one. Thirty stitches around is fifteen centimetres
of *circumference* at 20 sts/10cm, which is a piece under five centimetres across. Read as a
width it triples the size of the object in the listing, which is a refund and a return, and
nothing in the compiler would object because the arithmetic is all correct — it is the wrong
arithmetic.

So these tests pin three things.

The size of an open piece — a coaster, a tube, a basket — is computed from the surface the
stitches actually make, and checked against numbers a maker can verify with a tape measure.

The size of a *closed* piece is refused. Rounds 2 to 5 of every amigurumi grow at almost
exactly their own row height, which is geometrically the flat case, so the surface model
sincerely reports a hemisphere as a half-centimetre pancake. It is the stuffing and the
maker's tension that make the ball, and neither is in the gauge. A refusal plus a
circumference is the honest output; a confident height is fiction.

And fabric that has to gather is named as such, because a frill has no diameter.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from fixtures import good_sphere  # noqa: E402

from brambleloop.cir.compiler import compile_cir  # noqa: E402
from brambleloop.cir.reverse import ParseProblem  # noqa: E402
from brambleloop.cir.geometry import (  # noqa: E402
    CONE, DISC, GATHERED, SHAPED, TUBE, VESSEL, measure, measure_all,
)
from brambleloop.cir.model import CIR, Component, Gauge, Material, Op, Repeat, Row  # noqa: E402
from brambleloop.cir.twin import build_twin  # noqa: E402

GAUGE = Gauge(stitches_per_10cm=20, rows_per_10cm=22, stitch_type="sc", hook_mm=3.5)


def _round_cir(rows: list[Row], *, slug: str = "test-round",
               construction: str = "spiral_rounds") -> CIR:
    return CIR(
        slug=slug, title="Test Round Piece", version="1.0.0", construction=construction,
        risk_class="B", colors={"cream": "#FAF6EB"}, gauge=GAUGE,
        materials=[Material(name="worsted cotton", yarn_weight="worsted", color_id="cream")],
        components=[Component(name="body", construction=construction, rows=rows,
                              foundation=0, foundation_kind="magic_ring")],
    )


def _disc_rounds(n: int) -> list[Row]:
    """The standard flat circle: 6 sc in a ring, then +6 every round."""
    rows = [Row(index=1, ops=[Op("sc", 6)], declared_count=6, color="cream")]
    for i in range(2, n + 1):
        body: list = [Op("sc", i - 2), Op("inc")] if i > 2 else [Op("inc")]
        rows.append(Row(index=i, ops=[Repeat(body, times=6)], declared_count=6 * i,
                        color="cream"))
    return rows


def _measure(cir: CIR):
    result = compile_cir(cir)
    assert result.ok, [str(f) for f in result.errors]
    return measure(cir.components[0], result, cir)


# ---- open pieces: the model is exact --------------------------------------


def test_a_flat_circle_is_recognised_as_flat():
    """+6 per round is the flat case: the radius grows at exactly one row height."""
    rev = _measure(_round_cir(_disc_rounds(8)))
    assert rev.shape == DISC, rev.shape
    assert rev.smooth
    for ring in rev.rings[1:]:
        assert 0.95 <= ring.growth_ratio <= 1.15, ring


def test_a_coaster_is_measured_across_and_matches_a_tape_measure():
    """48 stitches around at 20 sts/10cm is 24 cm of circumference, so 7.6 cm across."""
    rev = _measure(_round_cir(_disc_rounds(8)))
    assert rev.rings[-1].count == 48
    circumference = 48 / 2.0  # 20 sts per 10 cm = 2 sts per cm
    assert abs(rev.max_circumference_cm - circumference) < 0.05
    across, tall = rev.footprint_cm()
    assert abs(across - circumference / math.pi) < 0.1, across
    # A coaster's two dimensions are the same number: it is a circle.
    assert across == tall


def test_a_tube_puts_its_whole_row_height_into_rising():
    rows = [Row(index=1, ops=[Op("sc", 48)], declared_count=48, color="cream")]
    rows += [Row(index=i, ops=[Op("sc", 48)], declared_count=48, color="cream")
             for i in range(2, 21)]
    rev = _measure(_round_cir(rows, construction="joined_rounds"))
    assert rev.shape == TUBE
    # 19 rounds of travel after the first, each 10/22 cm tall.
    assert abs(rev.axial_height_cm - 19 * (10.0 / 22.0)) < 0.01
    across, tall = rev.footprint_cm()
    assert abs(across - 24.0 / math.pi) < 0.1
    assert tall == round(rev.axial_height_cm, 1)


def test_a_basket_is_a_base_and_then_walls_and_both_are_measurable():
    """Growth that stops is an open vessel: the base sets the width, the walls the height."""
    rows = _disc_rounds(10)                       # 60 sts, ~9.5 cm across
    for i in range(11, 31):                       # 20 straight rounds of wall
        rows.append(Row(index=i, ops=[Op("sc", 60)], declared_count=60, color="cream"))
    rev = _measure(_round_cir(rows, construction="joined_rounds"))
    assert rev.shape == VESSEL, rev.shape
    assert rev.refusal() is None
    across, tall = rev.footprint_cm()
    assert abs(across - 30.0 / math.pi) < 0.2, across
    # Only the straight rounds rise; the base is flat and contributes almost nothing.
    assert abs(tall - 20 * (10.0 / 22.0)) < 0.4, tall


def test_a_cone_rises_less_than_its_row_height_but_still_rises():
    """+3 per round at this gauge grows at about half the row height, so it must rise."""
    rows = [Row(index=1, ops=[Op("sc", 6)], declared_count=6, color="cream")]
    count = 6
    for i in range(2, 16):
        prev = count
        count += 3
        rows.append(Row(index=i, ops=[Repeat([Op("sc", prev // 3 - 1), Op("inc")], times=3)],
                        declared_count=count, color="cream", allow_remainder=True))
    rev = _measure(_round_cir(rows))
    assert rev.shape in (CONE, VESSEL), rev.shape
    assert rev.refusal() is None
    across, tall = rev.footprint_cm()
    assert tall > 2.0, tall
    assert across > tall, (across, tall)


# ---- closed pieces: the model refuses -------------------------------------


def test_a_closed_shaped_piece_refuses_to_state_a_height():
    cir = good_sphere()
    rev = _measure(cir)
    assert rev.shape == SHAPED
    assert rev.footprint_cm() == (None, None)
    assert "stuffing and tension" in (rev.refusal() or "")
    # The circumference is still arithmetic, and still worth stating.
    assert abs(rev.max_circumference_cm - 15.0) < 0.05


def test_the_twin_of_a_round_piece_does_not_report_a_flat_width():
    """The whole point. 30 sts around is not 15 cm wide, and the twin no longer says it is."""
    cir = good_sphere()
    twin = build_twin(cir, compile_cir(cir))
    assert twin.width_cm is None and twin.height_cm is None
    assert twin.circumference_cm == 15.0
    assert twin.shape == SHAPED
    assert twin.size_refusal


def test_the_twin_still_measures_a_flat_panel_the_flat_way():
    from fixtures import good_mosaic_panel
    cir = good_mosaic_panel()
    twin = build_twin(cir, compile_cir(cir))
    assert twin.width_cm and twin.height_cm
    assert twin.shape is None and twin.size_refusal is None


def test_a_coaster_reaches_the_twin_as_a_diameter():
    cir = _round_cir(_disc_rounds(8), slug="test-coaster")
    twin = build_twin(cir, compile_cir(cir))
    assert twin.shape == DISC
    assert twin.width_cm == twin.height_cm
    assert 7.0 < twin.width_cm < 8.5, twin.width_cm


# ---- fabric that cannot lie flat ------------------------------------------


def test_shaping_faster_than_the_row_height_is_reported_as_gathering():
    """Doubling every round asks for more surface than the fabric has. That is a frill."""
    rows = [Row(index=1, ops=[Op("sc", 6)], declared_count=6, color="cream")]
    count = 6
    for i in range(2, 6):
        rows.append(Row(index=i, ops=[Repeat([Op("inc")], times=count)],
                        declared_count=count * 2, color="cream"))
        count *= 2
    rev = _measure(_round_cir(rows))
    assert rev.shape == GATHERED
    assert not rev.smooth
    codes = {f.code for f in rev.findings}
    assert "ROUND_FRILL" in codes, codes
    # A frill has no diameter, so nothing may be claimed about how big it is.
    assert rev.footprint_cm() == (None, None)


def test_gathering_is_a_warning_not_an_error():
    """A ruffled edge is a legitimate design. Claiming a size for it is what is refused."""
    rows = [Row(index=1, ops=[Op("sc", 6)], declared_count=6, color="cream")]
    count = 6
    for i in range(2, 6):
        rows.append(Row(index=i, ops=[Repeat([Op("inc")], times=count)],
                        declared_count=count * 2, color="cream"))
        count *= 2
    rev = _measure(_round_cir(rows))
    assert rev.findings
    assert all(f.severity == "WARNING" for f in rev.findings), \
        "a frill must not block a release; the refusal to state its size is the protection"


def test_a_frilled_round_names_the_round_it_is_on():
    rows = [Row(index=1, ops=[Op("sc", 6)], declared_count=6, color="cream")]
    count = 6
    for i in range(2, 4):
        rows.append(Row(index=i, ops=[Repeat([Op("inc")], times=count)],
                        declared_count=count * 2, color="cream"))
        count *= 2
    rev = _measure(_round_cir(rows))
    rounds = {f.row for f in rev.findings}
    assert rounds <= {2, 3} and rounds, rounds


# ---- refusals and housekeeping --------------------------------------------


def test_measuring_a_flat_component_as_a_revolution_is_refused():
    from fixtures import good_mosaic_panel
    cir = good_mosaic_panel()
    rev = measure(cir.components[0], compile_cir(cir), cir)
    assert [f.code for f in rev.findings] == ["ROUND_GEOMETRY_MISAPPLIED"]
    assert rev.footprint_cm() == (None, None)


def test_no_gauge_means_no_geometry_rather_than_a_guess():
    cir = _round_cir(_disc_rounds(6))
    cir.gauge = None
    rev = measure(cir.components[0], compile_cir(cir), cir)
    assert [f.code for f in rev.findings] == ["ROUND_NO_GAUGE"]
    assert rev.footprint_cm() == (None, None)


def test_a_last_round_small_enough_to_close_is_known_to_close():
    rows = _disc_rounds(4)
    rows.append(Row(index=5, ops=[Repeat([Op("dec")], times=12)], declared_count=12,
                    color="cream"))
    rows.append(Row(index=6, ops=[Repeat([Op("dec")], times=6)], declared_count=6,
                    color="cream"))
    rev = _measure(_round_cir(rows))
    assert rev.closes
    open_rev = _measure(_round_cir(_disc_rounds(6)))
    assert not open_rev.closes


def test_only_round_worked_components_are_measured():
    cir = good_sphere()
    assert set(measure_all(cir, compile_cir(cir))) == {"body"}
    from fixtures import good_mosaic_panel
    flat = good_mosaic_panel()
    assert measure_all(flat, compile_cir(flat)) == {}


# ---- the shapes the catalogue actually sells ------------------------------


def test_the_basket_is_measurable_in_all_three_sizes():
    """A basket is a base and then walls, and both numbers come out of the gauge."""
    from brambleloop.products.vessels import BASKET_SIZES, build_basket

    for spec in BASKET_SIZES:
        cir = build_basket(spec.key)
        rev = _measure(cir)
        assert rev.shape == VESSEL, (spec.key, rev.shape)
        across, tall = rev.footprint_cm()
        assert abs(across - spec.across_cm) < 1.5, (spec.key, across, spec.across_cm)
        assert abs(tall - spec.tall_cm) < 1.5, (spec.key, tall, spec.tall_cm)


def test_the_hexagon_coaster_really_has_six_corners():
    """Six stacked increase columns is a hexagon; the same counts staggered is a circle."""
    from brambleloop.cir.geometry import corners
    from brambleloop.products.vessels import build_hexagon_coaster

    cir = build_hexagon_coaster()
    result = compile_cir(cir)
    assert result.ok, [str(f) for f in result.errors]
    assert corners(result.rows) == 6


def test_the_round_worked_products_certify_and_read_back():
    from brambleloop.cir.reverse import compare
    from brambleloop.cir.writer import write_pattern
    from brambleloop.gates.certificate import certify
    from brambleloop.products.vessels import build_basket, build_hexagon_coaster

    for cir in (build_basket("medium"), build_hexagon_coaster()):
        result = compile_cir(cir)
        assert not compare(cir, write_pattern(cir, result)), cir.slug
        cert = certify(cir)
        assert cert.granted, (cir.slug, [str(f) for f in cert.errors])


def test_a_coaster_set_needs_yarn_for_the_whole_set():
    """`make 4` is four coasters. One coaster's yardage would be short by a factor of four."""
    from brambleloop.products.vessels import build_hexagon_coaster

    one = build_twin(build_hexagon_coaster(make=1),
                     compile_cir(build_hexagon_coaster(make=1)))
    four = build_twin(build_hexagon_coaster(make=4),
                      compile_cir(build_hexagon_coaster(make=4)))
    for color, metres in one.yarn_metres_by_color.items():
        assert abs(four.yarn_metres_by_color[color] - metres * 4) < 0.5


# ---- claims about shape ---------------------------------------------------


def test_a_flat_panel_named_for_a_basket_is_refused():
    """The defect this was built for: "Market Basket Trio" was one flat rectangle.

    Its own designer note said "the side panel, seamed into the basket", and the pattern
    contained no seaming instructions. A buyer would have paid for three baskets and
    received one panel.
    """
    from brambleloop.gates.asset_truth import check_shape_claims
    from fixtures import good_mosaic_panel

    cir = good_mosaic_panel()
    twin = build_twin(cir, compile_cir(cir))
    findings = check_shape_claims("Market Basket Trio", cir, twin)
    assert [f.code for f in findings] == ["CLAIM_CONSTRUCTION_UNSUPPORTED"]


def test_a_rectangle_named_for_a_hexagon_is_refused():
    from brambleloop.gates.asset_truth import check_shape_claims
    from fixtures import good_mosaic_panel

    cir = good_mosaic_panel()
    twin = build_twin(cir, compile_cir(cir))
    findings = check_shape_claims("Hexagon Coaster Set", cir, twin)
    assert [f.code for f in findings] == ["CLAIM_SHAPE_UNSUPPORTED"]


def test_a_motif_worked_on_a_rectangle_is_not_a_shape_claim():
    """Mosaic work legitimately depicts stars and hearts on rectangular fabric."""
    from brambleloop.gates.asset_truth import check_shape_claims
    from fixtures import good_mosaic_panel

    cir = good_mosaic_panel()
    twin = build_twin(cir, compile_cir(cir))
    for title in ("Nordic Star Throw", "Valentine Heart Blanket",
                  "Basket Weave Cushion Cover", "Bobble Floor Pillow"):
        assert not check_shape_claims(title, cir, twin), title


def test_the_real_basket_and_coaster_pass_the_same_check():
    from brambleloop.gates.asset_truth import check_shape_claims
    from brambleloop.products.vessels import build_basket, build_hexagon_coaster

    for cir in (build_basket("large"), build_hexagon_coaster()):
        twin = build_twin(cir, compile_cir(cir))
        assert not check_shape_claims(cir.title, cir, twin), cir.title


def test_a_size_claim_the_twin_cannot_check_is_refused_not_ignored():
    """The hole this closes: `actual is None` used to mean "nothing to check", so a claim
    about a piece the twin refuses to measure passed silently."""
    from brambleloop.gates.asset_truth import (
        Asset, AssetClass, Claims, Provenance, check_asset,
    )

    cir = good_sphere()
    twin = build_twin(cir, compile_cir(cir))
    asset = Asset(
        asset_id="hero", asset_class=AssetClass.DIGITAL_TWIN_RENDER,
        provenance=Provenance(source="twin", created_by="test"),
        claims=Claims(finished_width_cm=15.0, finished_height_cm=15.0), is_hero=True)
    codes = [f.code for f in check_asset(asset, cir, twin)]
    assert codes.count("CLAIM_SIZE_UNVERIFIABLE") == 2, codes


# ---- how the rounds are worked --------------------------------------------


def test_the_document_has_to_say_whether_to_join():
    from brambleloop.cir.reverse import compare
    from brambleloop.cir.writer import write_pattern

    cir = good_sphere()
    text = write_pattern(cir, compile_cir(cir))
    stripped = "\n".join(l for l in text.splitlines() if "spiral" not in l.lower())
    assert [f.code for f in compare(cir, stripped)] == ["REVERSE_CONSTRUCTION_MISSING"]


def test_a_document_that_says_the_opposite_is_caught():
    from brambleloop.cir.reverse import compare
    from brambleloop.cir.writer import JOINED_LINE, SPIRAL_LINE, write_pattern

    cir = good_sphere()
    text = write_pattern(cir, compile_cir(cir))
    swapped = text.replace(SPIRAL_LINE, JOINED_LINE)
    assert swapped != text
    assert [f.code for f in compare(cir, swapped)] == ["REVERSE_CONSTRUCTION_MISMATCH"]


def test_a_document_cannot_ask_for_both():
    from brambleloop.cir.reverse import parse_construction

    try:
        parse_construction("Work in a continuous spiral. Join each round with a sl st.")
    except ParseProblem:
        return
    raise AssertionError("a text that says both spiral and join must be refused")


def test_the_written_pattern_names_the_yarn_for_every_colour_change():
    """A two-colour pattern whose words never name the yarn is a chart with sentences."""
    from brambleloop.cir.reverse import compare
    from brambleloop.cir.writer import write_pattern
    from brambleloop.products.vessels import build_basket

    cir = build_basket("small")
    text = write_pattern(cir, compile_cir(cir))
    assert "(wine)" in text and "(cream)" in text
    # And the reader checks it: swapping a colour in the document is caught. The needle has
    # to be a round line -- the materials list also contains "(wine)", and tampering with
    # that proves nothing about the instructions.
    victim = next(l for l in text.splitlines()
                  if l.startswith("Rnd ") and "(wine)" in l)
    swapped = text.replace(victim, victim.replace("(wine)", "(cream)"), 1)
    assert swapped != text
    assert "REVERSE_COLOR" in [f.code for f in compare(cir, swapped)]


def test_a_single_colour_pattern_is_not_cluttered_with_colour_names():
    from brambleloop.cir.writer import write_pattern

    cir = _round_cir(_disc_rounds(6))
    cir.colors = {"cream": "#FAF6EB"}
    text = write_pattern(cir, compile_cir(cir))
    assert "(cream)" not in text


# ---- charts for round work -------------------------------------------------


def test_a_round_piece_gets_a_round_chart():
    from brambleloop.publish.charts import ChartSpec, is_round, render_any_chart
    from brambleloop.products.vessels import build_hexagon_coaster
    from fixtures import good_mosaic_panel

    cir = build_hexagon_coaster()
    twin = build_twin(cir, compile_cir(cir))
    assert is_round(cir, twin)
    chart = render_any_chart(cir, twin, ChartSpec(cell_px=20))
    # A round chart is about as tall as it is wide, because it is a disc. The flat renderer
    # produced a 4:1 ragged staircase for this same piece.
    assert 0.6 < chart.width / chart.height < 1.7, chart.size

    flat = good_mosaic_panel()
    flat_twin = build_twin(flat, compile_cir(flat))
    assert not is_round(flat, flat_twin)


# ---- the finishing ---------------------------------------------------------


def test_a_seam_that_names_a_piece_the_pattern_does_not_have_is_an_error():
    from brambleloop.cir.model import Seam
    from fixtures import good_mosaic_panel

    cir = good_mosaic_panel()
    cir.assembly = [Seam("sew", "handle", "body")]
    codes = [f.code for f in compile_cir(cir).findings]
    assert "ASSEMBLY_UNKNOWN_PIECE" in codes, codes


def test_stuffing_has_to_be_in_the_materials_list():
    """A pattern that says "stuff firmly" to a buyer who was never told to buy stuffing."""
    from brambleloop.cir.model import Seam

    cir = good_sphere()
    cir.assembly = [Seam("sew", "body", "body", stuff_before_closing=True)]
    findings = [f for f in compile_cir(cir).findings
                if f.code == "ASSEMBLY_NO_STUFFING_DECLARED"]
    assert findings and findings[0].severity == "WARNING"


def test_the_finishing_round_trips_and_a_dropped_step_is_caught():
    from brambleloop.cir.model import Seam
    from brambleloop.cir.reverse import compare
    from brambleloop.cir.writer import write_pattern
    from fixtures import good_mosaic_panel

    cir = good_mosaic_panel()
    cir.assembly = [Seam("mattress", "body", "body", note="seam the panel into a tube"),
                    Seam("whipstitch", "body", "body", note="close the base")]
    text = write_pattern(cir, compile_cir(cir))
    assert not compare(cir, text), [str(f) for f in compare(cir, text)]

    dropped = "\n".join(l for l in text.splitlines() if not l.startswith("Step 2"))
    assert "REVERSE_ASSEMBLY" in [f.code for f in compare(cir, dropped)]


def test_a_changed_seam_method_is_caught():
    from brambleloop.cir.model import Seam
    from brambleloop.cir.reverse import compare
    from brambleloop.cir.writer import write_pattern
    from fixtures import good_mosaic_panel

    cir = good_mosaic_panel()
    cir.assembly = [Seam("mattress", "body", "body")]
    text = write_pattern(cir, compile_cir(cir))
    swapped = text.replace("Mattress stitch", "Whipstitch")
    assert swapped != text
    assert "REVERSE_ASSEMBLY" in [f.code for f in compare(cir, swapped)]


def test_a_seamed_flat_panel_may_be_called_a_basket():
    """Which is what the original design meant to be, and never said."""
    from brambleloop.cir.model import Seam
    from brambleloop.gates.asset_truth import check_shape_claims
    from fixtures import good_mosaic_panel

    cir = good_mosaic_panel()
    twin = build_twin(cir, compile_cir(cir))
    assert check_shape_claims("Market Basket", cir, twin)
    cir.assembly = [Seam("mattress", "body", "body", note="seam the panel into a tube")]
    assert not check_shape_claims("Market Basket", cir, twin)


def test_the_round_worked_basket_needs_no_seam_at_all():
    from brambleloop.products.vessels import build_basket

    cir = build_basket("medium")
    assert cir.assembly == []
    assert not cir.makes_a_closed_form
    assert len(cir.components) == 1



# ---- placement: where the pieces go ---------------------------------------


def _two_piece():
    """A body and an ear: the smallest thing that has somewhere to put something."""
    import copy

    from brambleloop.cir.model import Seam

    cir = good_sphere()
    ear = copy.deepcopy(cir.components[0])
    ear.name = "ear"
    cir.components.append(ear)
    return cir, Seam


def test_a_join_that_does_not_say_where_is_a_bag_of_pieces():
    """Every piece correct, and no way to arrive at the object.

    This is the "beauty image, guess the instructions" failure arriving through the back
    door of an unspecified assembly step, so it is reported rather than allowed through.
    """
    cir, Seam = _two_piece()
    cir.assembly = [Seam("sew", "ear", "body")]
    codes = [f.code for f in compile_cir(cir).findings]
    assert "ASSEMBLY_UNPLACED" in codes, codes


def test_a_placement_off_the_end_of_the_piece_is_an_error():
    """"Attach at round 40" on a seven-round head survives every other check, because the
    pieces themselves are all correct."""
    cir, Seam = _two_piece()
    cir.assembly = [Seam("sew", "ear", "body", at_round=40, spans_rounds=2,
                         stitches_from_centre=4)]
    codes = [f.code for f in compile_cir(cir).findings]
    assert "ASSEMBLY_PLACEMENT_OFF_PIECE" in codes, codes


def test_two_placements_that_would_overlap_are_refused():
    cir, Seam = _two_piece()
    cir.assembly = [Seam("sew", "ear", "body", at_round=5, spans_rounds=1,
                         stitches_from_centre=40)]
    codes = [f.code for f in compile_cir(cir).findings]
    assert "ASSEMBLY_PLACEMENT_TOO_WIDE" in codes, codes


def test_a_placed_join_compiles_clean_and_reads_back():
    from brambleloop.cir.reverse import compare, parse_assembly
    from brambleloop.cir.writer import write_pattern

    cir, Seam = _two_piece()
    cir.assembly = [Seam("sew", "ear", "body", at_round=5, spans_rounds=2,
                         stitches_from_centre=5, mirrored=True,
                         note="stuff the body firmly first")]
    result = compile_cir(cir)
    assert not [f for f in result.findings if f.severity == "ERROR"], \
        [str(f) for f in result.findings]

    text = write_pattern(cir, result)
    step = next(l for l in text.splitlines() if l.startswith("Step 1:"))
    assert "across rounds 5-6" in step
    assert "5 sts either side of centre" in step
    assert "mirrored" in step
    assert parse_assembly(text) == [("sew", "ear", "body", 5, 2, 5, True)]
    assert not compare(cir, text)


def test_moving_the_placement_in_the_document_is_caught():
    """A tampered placement is a different object, and the pieces would still be perfect."""
    from brambleloop.cir.reverse import compare
    from brambleloop.cir.writer import write_pattern

    cir, Seam = _two_piece()
    cir.assembly = [Seam("sew", "ear", "body", at_round=5, spans_rounds=2,
                         stitches_from_centre=5)]
    text = write_pattern(cir, compile_cir(cir))
    for before, after in (("across rounds 5-6", "across rounds 3-4"),
                          ("5 sts either side", "9 sts either side")):
        moved = text.replace(before, after)
        assert moved != text, f"the tamper {before!r} did not apply"
        assert "REVERSE_ASSEMBLY" in [f.code for f in compare(cir, moved)], after


def test_a_single_round_placement_reads_as_one_round():
    from brambleloop.cir.reverse import parse_assembly
    from brambleloop.cir.writer import write_pattern

    cir, Seam = _two_piece()
    cir.assembly = [Seam("slst", "ear", "body", at_round=4)]
    text = write_pattern(cir, compile_cir(cir))
    assert "across round 4," in text or "across round 4." in text
    assert parse_assembly(text)[0][3:6] == (4, 1, None)


def test_a_self_seam_needs_no_placement():
    """Joining a panel's own two edges is fully specified by naming the panel."""
    from fixtures import good_mosaic_panel

    from brambleloop.cir.model import Seam

    cir = good_mosaic_panel()
    cir.assembly = [Seam("mattress", "body", "body", note="seam into a tube")]
    codes = [f.code for f in compile_cir(cir).findings]
    assert "ASSEMBLY_UNPLACED" not in codes

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
