"""Unknown or impossible geometry must never clear the small-parts gate."""
import dataclasses
import math

import test_a1r_child_safety_core as harness
from brambleloop.gates import small_parts
from brambleloop.products import inventory, launch0
from unittest.mock import patch
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
    # NaN is not serializable for a valid content binding: the authority hold is
    # encountered even before the direct small-parts UNKNOWN check above.
    assert result["outputs"]["reason"] == "undecided", result
    assert "exact design" in result["outputs"]["why"], result
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
        # Synthetic test-only assignment, so the actual Worker reaches the
        # small-parts gate instead of stopping at the assignment authority gate.
        with patch.dict(launch0._ASSIGNED_DECISION_CIR_SHA256,
                        {product.slug: launch0._cir_decision_digest(product)}), \
             patch.dict(small_parts.SMALL_PARTS_EVIDENCE,
                        {product.slug: "unscoped alleged sample"}):
            result = harness._assets_build_full(product)
        assert harness._held(result), (a, b, result)
        assert result["outputs"]["reason"] == "small_parts", result
        from sqlalchemy import select
        from brambleloop.core.models import OwnerAction
        with result["db"].session() as session:
            action = session.scalar(select(OwnerAction).where(
                OwnerAction.requirement_key.like(
                    f"childrens-small-parts:{product.slug}@{product.version}:%")))
            assert "content-bound" in action.action, action.action
            assert "SMALL_PARTS_EVIDENCE" not in action.action, action.action


def test_small_parts_hold_is_design_scoped_and_preserves_parked_audience_action():
    from sqlalchemy import select
    from brambleloop.core.models import JobStatus, OwnerAction

    basket = inventory._engineered("market-basket-medium")
    tab = dataclasses.replace(harness._one_piece_ball().components[0], name="tab",
                              rows=harness._one_piece_ball().components[0].rows[:2])
    seam = dataclasses.replace(inventory._engineered("heart-row-ring-pillow").assembly[0],
        piece_a="tab", piece_b="basket", stuff_before_closing=False,
        note=None, at_round=None, stitches_from_centre=None)
    cir = dataclasses.replace(basket, components=list(basket.components) + [tab], assembly=[seam])
    db, path = harness._store()
    with db.session() as session:
        session.add(OwnerAction(requirement_key=f"childrens-decision:{cir.slug}",
                                action="Earlier audience request", reason="pending", state="parked"))
    with patch.dict(launch0._ASSIGNED_DECISION_CIR_SHA256,
                    {cir.slug: launch0._cir_decision_digest(cir)}):
        result = harness._assets_build_full(cir, db=db, path=path)
    assert result["status"] == JobStatus.DONE and result["outputs"]["reason"] == "small_parts"
    with result["db"].session() as session:
        audience = session.scalar(select(OwnerAction).where(
            OwnerAction.requirement_key == f"childrens-decision:{cir.slug}"))
        actions = list(session.scalars(select(OwnerAction).where(
            OwnerAction.requirement_key.like(f"childrens-small-parts:{cir.slug}@{cir.version}:%"))))
    assert audience.state == "parked" and audience.action == "Earlier audience request"
    assert len(actions) == 1 and actions[0].state == "open"
    assert launch0._cir_decision_digest(cir) in actions[0].requirement_key


def test_small_parts_worker_refuses_changed_source_before_hold():
    from sqlalchemy import select
    from brambleloop.core.models import AuditLog, Job, JobStatus, OwnerAction, PatternVersion, Product
    from brambleloop.queue.durable import JobQueue
    from brambleloop.runtime import release
    from brambleloop.runtime.worker import Worker

    basket = inventory._engineered("market-basket-medium")
    disc = harness._one_piece_ball().components[0]
    tab = dataclasses.replace(disc, name="tab", rows=disc.rows[:2])
    seam = dataclasses.replace(inventory._engineered("heart-row-ring-pillow").assembly[0],
        piece_a="tab", piece_b="basket", stuff_before_closing=False,
        note=None, at_round=None, stitches_from_centre=None)
    cir = dataclasses.replace(basket, components=list(basket.components) + [tab], assembly=[seam])
    db, _ = harness._store()
    with db.session() as session:
        product = Product(slug=cir.slug, title=cir.title)
        session.add(product)
        session.flush()
        session.add(PatternVersion(product_id=product.id, version=cir.version,
                                   cir_json=cir.to_dict(), certified=True))
    queued = JobQueue(db).enqueue("publishing", "assets.build",
        {"slug": cir.slug, "version": cir.version}, idempotency_key="test:small-source-race")
    original = pdf._refuse_an_undecided_childrens_title

    def changed_after_assessment(*args, **kwargs):
        try:
            return original(*args, **kwargs)
        except pdf.ChildrensDecisionRequired as exc:
            if exc.reason == "small_parts":
                with db.session() as session:
                    product = session.scalar(select(Product).where(Product.slug == cir.slug))
                    pv = session.scalar(select(PatternVersion).where(
                        PatternVersion.product_id == product.id, PatternVersion.version == cir.version))
                    pv.cir_json = {**pv.cir_json, "designer_notes": "A changed design."}
            raise

    with patch.dict(launch0._ASSIGNED_DECISION_CIR_SHA256,
                    {cir.slug: launch0._cir_decision_digest(cir)}), \
         patch.object(pdf, "_refuse_an_undecided_childrens_title",
                      side_effect=changed_after_assessment):
        assert Worker(db, "small-source-race", job_types=["assets.build"]).run_once()
    with db.session() as session:
        job = session.get(Job, queued.id)
        assert job.status == JobStatus.FAILED and "source changed" in job.last_error
        assert not list(session.scalars(select(OwnerAction).where(
            OwnerAction.requirement_key.like("childrens-small-parts:%"))))
        assert not list(session.scalars(select(AuditLog).where(
            AuditLog.action == release.CHILDRENS_HOLD)))
def test_large_flexible_sewn_pieces_need_physical_fit_evidence():
    from brambleloop.core.models import JobStatus

    basket = inventory._engineered("market-basket-medium")
    panel = dataclasses.replace(basket.components[0], name="panel")
    seam = dataclasses.replace(inventory._engineered("heart-row-ring-pillow").assembly[0],
        piece_a="panel", piece_b="basket", stuff_before_closing=False,
        note=None, at_round=None, stitches_from_centre=None)
    cir = dataclasses.replace(basket, components=list(basket.components) + [panel], assembly=[seam])
    pieces = small_parts.separable_pieces(cir)
    assert pieces and all(small_parts.verdict(n, length) == small_parts.CLEAR
                          for _name, n, length in pieces)
    blocks = small_parts.blocking(cir)
    assert len(blocks) == len(pieces) and all("fit under force is unknown" in b for b in blocks)
    # The digest binding and sample assertion are synthetic test fixtures;
    # neither creates real owner authorization or physical test evidence.
    with patch.dict(launch0._ASSIGNED_DECISION_CIR_SHA256,
                    {cir.slug: launch0._cir_decision_digest(cir)}), \
         patch.dict(small_parts.SMALL_PARTS_EVIDENCE, {cir.slug: "unscoped alleged sample"}):
        try:
            pdf._refuse_an_undecided_childrens_title(cir, ("toys", "under_3"))
        except pdf.ChildrensDecisionRequired as exc:
            assert exc.reason == "small_parts" and "fit under force is unknown" in str(exc)
        else:
            raise AssertionError("flat size was incorrectly treated as physical clearance")
        result = harness._assets_build_full(cir)
    assert result["status"] == JobStatus.DONE and result["outputs"].get("held"), result
    assert result["outputs"]["reason"] == "small_parts", result
    assert not result["outputs"].get("pdf_sha256"), result


if __name__ == "__main__":
    test_invalid_measurements_and_gauges_are_unknown()
    test_either_seam_endpoint_can_be_a_small_part()
    print("PASS invalid child small-parts geometry is UNKNOWN and held")
