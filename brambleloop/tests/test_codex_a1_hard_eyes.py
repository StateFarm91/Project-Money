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
    assert result["status"] == JobStatus.DONE and result["outputs"].get("held"), result
    assert result["outputs"]["reason"] == "safety_refusal", result
    assert "SMALL_PART_UNDER_3" in result["outputs"]["why"], result
    assert result["attempts"] == 1
    assert not result["outputs"].get("pdf_sha256"), result


def test_real_assets_worker_refuses_detachable_rattle_insert_under_three():
    from brambleloop.core.models import OwnerAction

    original = inventory._engineered("cloudline-baby-blanket")
    changed = dataclasses.replace(original, designer_notes="Add a rattle insert.")
    db, path = harness._store()
    with db.session() as session:
        session.add(OwnerAction(requirement_key=f"childrens-decision:{changed.slug}",
                                action="Existing audience decision request", reason="pending",
                                state="parked"))
    # Synthetic exact assignment only for this test; no physical evidence added.
    with patch.dict(launch0._ASSIGNED_DECISION_CIR_SHA256,
                    {changed.slug: launch0._cir_decision_digest(changed)}):
        result = harness._assets_build_full(changed, db=db, path=path)
    assert result["status"] == JobStatus.DONE and result["outputs"].get("held"), result
    assert result["outputs"]["reason"] == "safety_refusal", result
    assert "SMALL_PART_UNDER_3" in result["outputs"]["why"], result
    assert result["attempts"] == 1
    assert not result["outputs"].get("pdf_sha256"), result

    # A later attempt still holds and does not open duplicate owner decisions.
    from sqlalchemy import select
    from brambleloop.core.models import OwnerAction
    from brambleloop.queue.durable import JobQueue
    from brambleloop.runtime.worker import Worker
    db = result["db"]
    JobQueue(db).enqueue("publishing", "assets.build",
                         {"slug": changed.slug, "version": changed.version},
                         idempotency_key="test:repeated-safety-refusal")
    with patch.dict(launch0._ASSIGNED_DECISION_CIR_SHA256,
                    {changed.slug: launch0._cir_decision_digest(changed)}):
        assert Worker(db, "repeat-safety", job_types=["assets.build"]).run_once()
    with db.session() as session:
        audience = session.scalar(select(OwnerAction).where(
            OwnerAction.requirement_key == f"childrens-decision:{changed.slug}"))
        actions = list(session.scalars(select(OwnerAction).where(
            OwnerAction.requirement_key.like(f"childrens-safety:{changed.slug}@{changed.version}:%"),
            OwnerAction.done == False)))  # noqa: E712
    assert len(actions) == 1
    assert launch0._cir_decision_digest(changed) in actions[0].requirement_key
    assert "audience exemption does not clear" in actions[0].action
    assert "SMALL_PART_UNDER_3" in actions[0].reason
    assert audience.state == "parked" and audience.action == "Existing audience decision request"


def test_new_design_safety_finding_does_not_reopen_or_hide_parked_action():
    from sqlalchemy import select
    from brambleloop.core.models import OwnerAction

    original = inventory._engineered("cloudline-baby-blanket")
    first = dataclasses.replace(original, designer_notes="Use snap-in eyes.")
    with patch.dict(launch0._ASSIGNED_DECISION_CIR_SHA256,
                    {first.slug: launch0._cir_decision_digest(first)}):
        result = harness._assets_build_full(first)
    db, path = result["db"], result["path"]
    with db.session() as session:
        previous = session.scalar(select(OwnerAction).where(
            OwnerAction.requirement_key.like(f"childrens-safety:{first.slug}@%")))
        assert previous is not None
        previous.state = "parked"
        old_id = previous.id
    second = dataclasses.replace(first, version="9.9.9", designer_notes="Add a rattle insert.")
    with patch.dict(launch0._ASSIGNED_DECISION_CIR_SHA256,
                    {second.slug: launch0._cir_decision_digest(second)}):
        updated = harness._assets_build_full(second, db=db, path=path)
    assert updated["status"] == JobStatus.DONE and updated["outputs"].get("held")
    with db.session() as session:
        actions = list(session.scalars(select(OwnerAction).where(
            OwnerAction.requirement_key.like(f"childrens-safety:{first.slug}@%"))))
    assert len(actions) == 2
    assert next(row for row in actions if row.id == old_id).state == "parked"
    assert next(row for row in actions if row.id != old_id).state == "open"

def test_real_assets_worker_refuses_unassessed_toy_eyes_under_three():
    original = inventory._engineered("cloudline-baby-blanket")
    changed = dataclasses.replace(original, designer_notes="Attach toy eyes.")
    # Synthetic exact assignment only for this test; no physical evidence added.
    with patch.dict(launch0._ASSIGNED_DECISION_CIR_SHA256,
                    {changed.slug: launch0._cir_decision_digest(changed)}):
        result = harness._assets_build_full(changed)
    assert result["status"] == JobStatus.DONE and result["outputs"].get("held"), result
    assert result["outputs"]["reason"] == "safety_refusal", result
    assert "UNRECOGNISED_PART" in result["outputs"]["why"], result
    assert not result["outputs"].get("pdf_sha256"), result


def test_real_assets_worker_refuses_child_neck_drawcord():
    original = inventory._engineered("cloudline-baby-blanket")
    changed = dataclasses.replace(original, designer_notes="Thread the drawcord through the hood.")
    # Synthetic exact assignment only for this test; no physical evidence added.
    with patch.dict(launch0._ASSIGNED_DECISION_CIR_SHA256,
                    {changed.slug: launch0._cir_decision_digest(changed)}):
        result = harness._assets_build_full(changed)
    assert result["status"] == JobStatus.DONE and result["outputs"].get("held"), result
    assert result["outputs"]["reason"] == "safety_refusal", result
    assert "NECK_OR_HOOD_DRAWSTRING" in result["outputs"]["why"], result
    assert not result["outputs"].get("pdf_sha256"), result


def test_real_assets_worker_refuses_unassessed_sewn_felt():
    original = inventory._engineered("cloudline-baby-blanket")
    changed = dataclasses.replace(original, designer_notes="Attach felt shapes sewn.")
    # Synthetic exact assignment only for this test; no physical evidence added.
    with patch.dict(launch0._ASSIGNED_DECISION_CIR_SHA256,
                    {changed.slug: launch0._cir_decision_digest(changed)}):
        result = harness._assets_build_full(changed)
    assert result["status"] == JobStatus.DONE and result["outputs"].get("held"), result
    assert result["outputs"]["reason"] == "safety_refusal", result
    assert "UNRECOGNISED_PART" in result["outputs"]["why"], result
    assert not result["outputs"].get("pdf_sha256"), result


def test_real_assets_worker_refuses_separately_attached_crocheted_eyes():
    original = inventory._engineered("cloudline-baby-blanket")
    changed = dataclasses.replace(original, designer_notes="Sew the crocheted eyes onto the head.")
    # Synthetic exact assignment only for this test; no physical evidence added.
    with patch.dict(launch0._ASSIGNED_DECISION_CIR_SHA256,
                    {changed.slug: launch0._cir_decision_digest(changed)}):
        result = harness._assets_build_full(changed)
    assert result["status"] == JobStatus.DONE and result["outputs"].get("held"), result
    assert result["outputs"]["reason"] == "safety_refusal", result
    assert "UNRECOGNISED_PART" in result["outputs"]["why"], result
    assert not result["outputs"].get("pdf_sha256"), result
