"""Unmeasured child's garment waist drawstrings cannot silently pass."""
import dataclasses
from unittest.mock import patch

import test_a1r_child_safety_core as harness
from brambleloop.core.models import JobStatus
from brambleloop.intel import childrens as ch
from brambleloop.products import inventory, launch0
from brambleloop.publish import pdf


def test_explicit_waist_drawstring_held_by_real_assets_worker():
    original = inventory._engineered("cloudline-baby-blanket")
    cir = dataclasses.replace(original, designer_notes="Thread a drawcord through the waist channel.")
    assert ch.waist_drawstring_in_cir(cir)
    concept = ch.concept_from_cir(cir, subcategory="childrens_garment", audience=ch.THREE_TO_SIX)
    assert "WAIST_DRAWSTRING_UNASSESSED" in {f.code for f in ch.assess(concept)}
    # Synthetic category and digest exercise the actual Worker, not owner authority.
    with patch.dict(launch0._cir_audience_map(), {cir.slug: ("childrens_garment", ch.THREE_TO_SIX)}), \
         patch.dict(launch0._ASSIGNED_DECISION_CIR_SHA256,
                    {cir.slug: launch0._cir_decision_digest(cir)}):
        try:
            pdf._refuse_what_the_childrens_assessment_refuses(cir, ("childrens_garment", ch.THREE_TO_SIX))
        except pdf.ChildrensDecisionRequired as exc:
            assert exc.reason == "safety_refusal" and "WAIST_DRAWSTRING_UNASSESSED" in str(exc)
        else:
            raise AssertionError("unmeasured waist drawcord passed")
        result = harness._assets_build_full(cir)
    assert result["status"] == JobStatus.DONE and result["outputs"].get("held"), result
    assert result["outputs"]["reason"] == "safety_refusal", result
    assert "WAIST_DRAWSTRING_UNASSESSED" in result["outputs"]["why"], result
    assert not result["outputs"].get("pdf_sha256"), result


def test_unrelated_and_adult_copy_does_not_add_waist_drawstring_finding():
    original = inventory._engineered("cloudline-baby-blanket")
    for note in ("Measure the waist. Tie off yarn and weave in ends.", "Crochet the waist band."):
        cir = dataclasses.replace(original, designer_notes=note)
        assert not ch.waist_drawstring_in_cir(cir)
    cir = dataclasses.replace(original, designer_notes="Thread a drawcord through the waist channel.")
    concept = ch.concept_from_cir(cir, subcategory="baby_blanket", audience=ch.UNDER_3)
    assert "WAIST_DRAWSTRING_UNASSESSED" not in {f.code for f in ch.assess(concept)}
