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


def test_research_descriptor_vocabulary_is_accepted_by_the_name_object_contract():
    from brambleloop.creative import fallback_constructions
    from brambleloop.radar.ideation import HOUSE_DESCRIPTORS, POD_OBJECTS

    for objects in POD_OBJECTS.values():
        for obj in objects:
            for descriptor, _, _, _ in HOUSE_DESCRIPTORS:
                title = f"{descriptor} {obj.noun}"
                result = fallback_constructions.plan(category=obj.category, title=title)
                assert result["family"] != fallback_constructions.REFUSED, (title, result)
