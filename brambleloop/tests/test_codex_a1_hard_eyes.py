"""Real worker must not produce a children's PDF naming detachable hard eyes."""
import dataclasses
from unittest.mock import patch

import test_a1r_child_safety_core as harness
from brambleloop.core.models import JobStatus
from brambleloop.products import inventory, launch0


def test_real_assets_worker_refuses_hard_eyes_under_three():
    original = inventory._engineered("cloudline-baby-blanket")
    changed = dataclasses.replace(original, designer_notes="Use snap-in eyes.")
    # A synthetic test-only exact binding reaches the child's PDF assessment;
    # it grants no real owner authority or physical evidence.
    with patch.dict(launch0._ASSIGNED_DECISION_CIR_SHA256,
                    {changed.slug: launch0._cir_decision_digest(changed)}):
        result = harness._assets_build_full(changed)
    assert result["status"] in {JobStatus.FAILED, JobStatus.DEAD}, result
    assert "SMALL_PART_UNDER_3" in result["error"], result
    assert not result["outputs"].get("pdf_sha256"), result


def test_real_assets_worker_refuses_detachable_rattle_insert_under_three():
    original = inventory._engineered("cloudline-baby-blanket")
    changed = dataclasses.replace(original, designer_notes="Add a rattle insert.")
    # Synthetic exact assignment only for this test; no physical evidence added.
    with patch.dict(launch0._ASSIGNED_DECISION_CIR_SHA256,
                    {changed.slug: launch0._cir_decision_digest(changed)}):
        result = harness._assets_build_full(changed)
    assert result["status"] in {JobStatus.FAILED, JobStatus.DEAD}, result
    assert "SMALL_PART_UNDER_3" in result["error"], result
    assert not result["outputs"].get("pdf_sha256"), result


def test_real_assets_worker_refuses_unassessed_toy_eyes_under_three():
    original = inventory._engineered("cloudline-baby-blanket")
    changed = dataclasses.replace(original, designer_notes="Attach toy eyes.")
    # Synthetic exact assignment only for this test; no physical evidence added.
    with patch.dict(launch0._ASSIGNED_DECISION_CIR_SHA256,
                    {changed.slug: launch0._cir_decision_digest(changed)}):
        result = harness._assets_build_full(changed)
    assert result["status"] in {JobStatus.FAILED, JobStatus.DEAD}, result
    assert "UNRECOGNISED_PART" in result["error"], result
    assert not result["outputs"].get("pdf_sha256"), result
