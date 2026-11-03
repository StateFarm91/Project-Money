"""Regression for interacting child, object, fabric and heat safety gates."""

from brambleloop.publish.eligibility import name_truth
from brambleloop.runtime.pipeline import Concept, concept_to_cir


def test_independent_listing_safety_findings_are_all_preserved():
    cir = concept_to_cir(Concept(
        slug="review-combined", title="Everyday Blanket", category="blanket",
        stitch_repeat=[("sc", 4)], width_stitches=40, rows=10,
        colors={"a": "#fff"},
    ))
    reasons = name_truth(cir, {
        "title": "Striped Pot Holder for Baby", "description": "Heart",
        "tags": ["infant"],
    })
    for fragment in ("child audience", "motif", "stripe", "Heat-protection"):
        assert any(fragment in reason for reason in reasons), (fragment, reasons)
