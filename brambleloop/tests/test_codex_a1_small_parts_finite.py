"""Unknown or impossible geometry must never clear the small-parts gate."""
import dataclasses
import math

import test_a1r_child_safety_core as harness
from brambleloop.gates import small_parts
from brambleloop.products import inventory
from brambleloop.publish import pdf


def test_invalid_measurements_and_gauges_are_unknown():
    for value in (float("nan"), float("inf"), float("-inf"), 0, -1, None, True):
        assert small_parts.verdict(value, 10) == small_parts.UNKNOWN, value
        assert small_parts.verdict(10, value) == small_parts.UNKNOWN, value
    assert small_parts.verdict(10, 10, tolerance=float("nan")) == small_parts.UNKNOWN
    basket = inventory._engineered("market-basket-small")
    disc = harness._one_piece_ball().components[0]
    tab = dataclasses.replace(disc, name="tab", rows=disc.rows[:2])
    seam = dataclasses.replace(inventory._engineered("heart-row-ring-pillow").assembly[0],
        piece_a="tab", piece_b="basket", stuff_before_closing=False,
        note=None, at_round=None, stitches_from_centre=None)
    product = dataclasses.replace(basket, components=list(basket.components) + [tab],
                                  assembly=[seam])
    # Gauge's existing constructor does not reject NaN, so inspect the real gate.
    for field in ("stitches_per_10cm", "rows_per_10cm"):
        gauge = dataclasses.replace(product.gauge, **{field: float("nan")})
        bad = dataclasses.replace(product, gauge=gauge)
        blocks = small_parts.blocking(bad)
        assert blocks and small_parts.UNKNOWN in str(blocks), blocks
        try:
            pdf._refuse_an_undecided_childrens_title(bad, ("toys", "under_3"))
        except pdf.ChildrensDecisionRequired as exc:
            assert exc.reason == "small_parts"
        else:
            raise AssertionError(f"non-finite {field} cleared the PDF safety gate")
    # The actual assets worker records a durable child-safety hold, not a PDF.
    assigned = dataclasses.replace(bad, slug="market-basket-medium")
    small_parts.SMALL_PARTS_EVIDENCE[assigned.slug] = "unscoped alleged sample"
    try:
        result = harness._assets_build_full(assigned)
    finally:
        small_parts.SMALL_PARTS_EVIDENCE.pop(assigned.slug)
    assert harness._held(result), result
    assert result["outputs"]["reason"] == "small_parts", result
    assert "unknown" in result["outputs"]["why"], result
    from sqlalchemy import select
    from brambleloop.core.models import OwnerAction
    with result["db"].session() as session:
        action = session.scalar(select(OwnerAction).where(
            OwnerAction.requirement_key == "childrens-decision:market-basket-medium"))
        assert "content-bound" in action.action, action.action
        assert "SMALL_PARTS_EVIDENCE" not in action.action, action.action
    assert small_parts.verdict(36, 62) == small_parts.CLEAR
    assert small_parts.verdict(31, 50) == small_parts.FITS


def test_either_seam_endpoint_can_be_a_small_part():
    basket = inventory._engineered("market-basket-medium")
    disc = harness._one_piece_ball().components[0]
    tab = dataclasses.replace(disc, name="tab", rows=disc.rows[:2])
    original = inventory._engineered("heart-row-ring-pillow").assembly[0]
    for a, b in (("tab", "basket"), ("basket", "tab")):
        seam = dataclasses.replace(original, piece_a=a, piece_b=b,
            stuff_before_closing=False, note=None, at_round=None, stitches_from_centre=None)
        product = dataclasses.replace(basket, components=list(basket.components) + [tab],
                                      assembly=[seam])
        blocks = small_parts.blocking(product)
        assert any("tab" in item for item in blocks), (a, b, blocks)
        result = harness._assets_build_full(product)
        assert harness._held(result), (a, b, result)
        assert result["outputs"]["reason"] == "small_parts", result


if __name__ == "__main__":
    test_invalid_measurements_and_gauges_are_unknown()
    test_either_seam_endpoint_can_be_a_small_part()
    print("PASS invalid child small-parts geometry is UNKNOWN and held")
