"""#81 in the runtime: a failed parity gate walks the escalation ladder as a recorded plan.

The proof audit (2026-09-26) found `visual.gallery.escalate()` with no caller: a parity
failure went straight to `blocks_release` and stopped. These run `store.publish` in Shadow
Mode, which computes parity on every attempt, and read the plan it recorded. Nothing here
renders, spends, or asks for a physical object -- the gated rungs say which gate holds them.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog, CostEntry, Phase  # noqa: E402
from brambleloop.publish import owned_photography  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: E402,F401
from brambleloop.runtime.worker import Worker  # noqa: E402
from brambleloop.visual import gallery, parity  # noqa: E402

SLUG = "fir-throw"


def _frames(*, with_chart: bool) -> list[dict]:
    frames = [{"role": "hero", "motif": {"verdict": "mismatch"}, "readable_at_grid": True}]
    if with_chart:
        frames.append({"role": "chart", "deterministic": True, "readable_at_grid": True})
    return frames


def _publish_attempt(frames: list[dict], *, setup=None, keep_db: list | None = None) -> dict:
    db = Database(f"sqlite:///{tempfile.mkdtemp()}/esc.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    if keep_db is not None:
        keep_db.append(db)
    if setup is not None:
        setup(db)
    with db.session() as s:
        s.add(AuditLog(actor="publishing", action=owned_photography.ACTION,
                       detail={"made": True, "slug": SLUG, "frames": frames,
                               "method_version": owned_photography.METHOD_VERSION}))
    JobQueue(db).enqueue("store_operator", "store.publish", {"slug": SLUG, "version": "1.0.0"})
    Worker(db, "w", phase=Phase.SHADOW).run_once()
    with db.session() as s:
        verdicts = [dict(r.detail) for r in s.scalars(select(AuditLog))
                    if r.action == "listing.parity"]
        assert s.scalar(select(CostEntry)) is None, "the escalation plan spent money"
    assert verdicts, "store.publish did not compute parity"
    return verdicts[-1]


def test_a_parity_failure_is_routed_through_the_ladder_and_takes_the_free_rung():
    verdict = _publish_attempt(_frames(with_chart=True))
    assert verdict["verdict"] == parity.FAIL and verdict["blocks_release"] is True
    plan = verdict["escalation"]
    assert parity.PRODUCT_TRUTH in plan["failed_dimensions"]
    by_action = {r["action"]: r for r in plan["rungs"]}
    for rung in ("regenerate_constrained", "change_composition", "change_tool"):
        assert by_action[rung]["status"] == "gated"
        assert by_action[rung]["gated_on"] == "image_generation"
        assert by_action[rung]["executed"] is False
    assert by_action["deterministic_representation"]["status"] == "taken"
    assert by_action["acquire_physical_proof"]["gated_on"] == "physical_proof"
    assert by_action["hold_listing"]["status"] == "not_needed"
    assert plan["taken"] == "deterministic_representation"
    # The plan does not lower the bar: release still waits for parity to pass.
    assert plan["still_blocks_release"] is True


def test_without_a_deterministic_render_the_ladder_ends_in_holding_the_listing():
    verdict = _publish_attempt(_frames(with_chart=False))
    plan = verdict["escalation"]
    by_action = {r["action"]: r for r in plan["rungs"]}
    assert by_action["deterministic_representation"]["status"] == "unavailable"
    assert plan["taken"] is None and plan["outcome"] == "hold the listing"
    assert by_action["hold_listing"]["status"] == "outcome"


def test_a_completed_physical_test_opens_the_proof_rung_read_live_from_the_database():
    """C-69: the ladder reads the live gate; a gate that opened is attempted, not skipped."""
    from datetime import datetime, timezone

    from brambleloop.core.models import PhysicalTest

    def tested(db):
        with db.session() as s:
            s.add(PhysicalTest(product_slug=SLUG, version="1.0.0", tester_ref="t-1",
                               completed_at=datetime.now(timezone.utc), passed=True))

    verdict = _publish_attempt(_frames(with_chart=False), setup=tested)
    plan = verdict["escalation"]
    by_action = {r["action"]: r for r in plan["rungs"]}
    assert plan["gates_read_live"] is True
    assert by_action["regenerate_constrained"]["status"] == "gated"
    assert by_action["regenerate_constrained"]["gate_open"] is False
    assert by_action["acquire_physical_proof"]["gate_open"] is True
    assert by_action["acquire_physical_proof"]["status"] == "taken"
    assert plan["taken"] == "acquire_physical_proof" and plan["still_blocks_release"]


def test_an_open_image_gate_attempts_the_first_rung_through_the_photography_job():
    from brambleloop.build2 import executor
    from brambleloop.core.models import Job

    gate = executor.GATE_BY_KEY["image_generation"]
    original = gate.check
    gate.check = lambda db, env: True          # the provider has produced an image
    dbs: list = []
    try:
        verdict = _publish_attempt(_frames(with_chart=True), keep_db=dbs)
    finally:
        gate.check = original
    plan = verdict["escalation"]
    assert plan["taken"] == "regenerate_constrained", plan
    by_action = {r["action"]: r for r in plan["rungs"]}
    assert by_action["change_composition"]["status"] == "eligible"
    assert by_action["deterministic_representation"]["status"] == "not_needed"
    with dbs[0].session() as s:
        jobs = [j for j in s.scalars(select(Job)) if j.job_type.startswith("assets.")
                and "photography" in j.job_type]
        assert jobs and jobs[0].inputs["reason"] == "parity_escalation:regenerate_constrained"


def test_unjudged_is_not_escalated_because_nobody_looked():
    verdict = parity.assess([])
    assert verdict["blocks_release"] is True and verdict["escalation"] is None


def test_the_plan_walks_every_rung_escalate_knows_in_order():
    plan = gallery.escalation_plan(["hero"], deterministic_available=True)
    assert [r["action"] for r in plan["rungs"]] == [a for a, _ in gallery.ESCALATION]
    assert set(gallery.RUNG_GATES) == {a for a, _ in gallery.ESCALATION}


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
