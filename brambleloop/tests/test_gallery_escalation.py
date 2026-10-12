"""#81 in the runtime: a failed parity gate walks the escalation ladder as a recorded plan.

The proof audit (2026-09-26) found `visual.gallery.escalate()` with no caller: a parity
failure went straight to `blocks_release` and stopped. These run `store.publish` in Shadow
Mode, which computes parity on every attempt, and read the plan it recorded. Nothing here
renders, spends, or asks for a physical object -- the gated rungs say which gate holds them.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
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


def _publish_attempt(frames: list[dict], *, setup=None, keep_db: list | None = None,
                     slug: str = SLUG, version: str = "1.0.0") -> dict:
    db = Database(f"sqlite:///{tempfile.mkdtemp()}/esc.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    if keep_db is not None:
        keep_db.append(db)
    if setup is not None:
        setup(db)
    with db.session() as s:
        s.add(AuditLog(actor="publishing", action=owned_photography.ACTION,
                       detail={"made": True, "slug": slug, "frames": frames,
                               "method_version": owned_photography.METHOD_VERSION}))
    JobQueue(db).enqueue("store_operator", "store.publish", {"slug": slug, "version": version})
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


def _publish_again(db, *, job_types=("store.publish",), slug: str = SLUG,
                   version: str = "1.0.0") -> dict:
    JobQueue(db).enqueue("store_operator", "store.publish", {"slug": slug, "version": version})
    Worker(db, "w2", phase=Phase.SHADOW, job_types=list(job_types)).run_once()
    with db.session() as s:
        verdicts = [dict(r.detail) for r in s.scalars(select(AuditLog))
                    if r.action == "listing.parity"]
    return verdicts[-1]


def test_the_ladder_advances_through_distinct_rungs_from_persisted_results():
    """C-80 defect 8 (Codex P11): each generation rung is its own strategy -- constrained
    brief, changed composition, other tool -- with its own budget; the photography job
    persists the rung's result and the next parity verdict resumes the ladder from it, so
    change_composition and change_tool are reached and then the deterministic rung."""
    from brambleloop.build2 import executor
    from brambleloop.core.models import Job, JobStatus
    from brambleloop.gateway import images
    from brambleloop.visual import tournament

    # a catalogue product `products.builder.for_slug` can build, product-first, compiling
    slug = "cloudline-baby-blanket"
    # CB2-P11: the release under test is the CIR the catalogue builds today (the fixture used
    # to hard-code 1.0.0, which went stale when cloudline was redesigned to 1.1.0).
    from brambleloop.products.builder import for_slug

    version = for_slug(slug).version
    calls: list[dict] = []

    def fake_make(db, cir, twin, **kw):
        calls.append(dict(kw))
        return {"made": True, "slug": slug, "version": version,
                "method_version": owned_photography.METHOD_VERSION,
                "frames": _frames(with_chart=True), "rung": kw.get("rung") or None,
                "rung_constraints": list(kw.get("constraints") or ()),
                "provider": kw.get("provider_key") or "gpt-image-2",
                "usable_as_listing_asset": False, "verdict": "blocked",
                "why": "fixture: the render failed asset truth", "spent_cad": 0.0}

    gate = executor.GATE_BY_KEY["image_generation"]
    originals = (gate.check, images.usable, owned_photography.make,
                 tournament.alternate_provider)
    gate.check = lambda db, env: True
    images.usable = lambda db: True
    owned_photography.make = fake_make
    tournament.alternate_provider = lambda db=None, env=None, *, exclude=(): "flux-2-pro"
    dbs: list = []
    try:
        verdict = _publish_attempt(_frames(with_chart=True), keep_db=dbs, slug=slug,
                                   version=version)
        db = dbs[0]
        assert verdict["escalation"]["taken"] == "regenerate_constrained"

        def run_rung(expected_rung):
            with db.session() as s:
                job = next(j for j in s.scalars(select(Job).where(
                    Job.job_type == "assets.owned_photography", Job.status == JobStatus.PENDING)))
                assert job.inputs["rung"] == expected_rung, job.inputs
                assert job.inputs["version"] == version
                job_id = job.id
            Worker(db, "rung", phase=Phase.SHADOW,
                   job_types=["assets.owned_photography"]).run_once()
            with db.session() as s:
                row = s.get(Job, job_id)
                assert row.status == JobStatus.DONE, row.last_error
                return dict(row.outputs)

        out = run_rung("regenerate_constrained")
        assert out["ran"] and out["attempted"] and out["usable"] is False
        assert any("failed these checks" in c and parity.PRODUCT_TRUTH in c
                   for c in calls[-1]["constraints"]), calls[-1]
        progress = gallery.escalation_progress(db, slug=slug, version=version)
        assert progress["start_attempt"] == 1 and progress["attempted"] == [
            "regenerate_constrained"]

        verdict = _publish_again(db, slug=slug, version=version)
        plan = verdict["escalation"]
        assert plan["taken"] == "change_composition", plan
        assert plan["start_attempt"] == 1 and "regenerate_constrained" in plan["rung_results"]
        out = run_rung("change_composition")
        assert out["composition"] == "alternate"
        assert any("composition" in c.lower() for c in calls[-1]["constraints"])

        verdict = _publish_again(db, slug=slug, version=version)
        assert verdict["escalation"]["taken"] == "change_tool"
        out = run_rung("change_tool")
        assert calls[-1]["provider_key"] == "flux-2-pro" and out["provider"] == "flux-2-pro"

        # every generation rung has been tried once, on its own budget: the ordinary daily
        # budget is untouched and the ladder now takes the free deterministic rung
        assert owned_photography.ordinary_attempts(db, slug=slug, version=version) == []
        for rung in gallery.GENERATION_RUNGS:
            assert len(owned_photography.rung_attempts(db, slug=slug, version=version,
                                                       rung=rung)) == 1
        verdict = _publish_again(db, slug=slug, version=version)
        plan = verdict["escalation"]
        assert plan["start_attempt"] == 3
        assert plan["taken"] == "deterministic_representation", plan
        by_action = {r["action"]: r for r in plan["rungs"]}
        assert set(by_action) == {"deterministic_representation", "acquire_physical_proof",
                                  "hold_listing"}
        assert plan["still_blocks_release"] is True
        # a rung is never repeated: the same job asked again records it and renders nothing
        JobQueue(db).enqueue("publishing", "assets.owned_photography",
                             {"slug": slug, "version": version, "rung": "change_tool",
                              "reason": "parity_escalation:change_tool", "failed": ["x"]},
                             idempotency_key="repeat-rung")
        before = len(calls)
        Worker(db, "rung", phase=Phase.SHADOW,
               job_types=["assets.owned_photography"]).run_once()
        assert len(calls) == before
        with db.session() as s:
            last = [dict(r.detail) for r in s.scalars(select(AuditLog).where(
                AuditLog.action == gallery.ESCALATION_RESULT_ACTION))][-1]
        assert last["attempted"] is False and last["reason"] == "rung_already_attempted"
    finally:
        (gate.check, images.usable, owned_photography.make,
         tournament.alternate_provider) = originals


def test_a_rung_for_a_superseded_version_is_refused_and_recorded_not_rendered():
    """CB2-P11: the rung job names the release whose parity failed. When the CIR on file has
    since been rebuilt under another version, the handler refuses explicitly -- recorded under
    the requested release with reason stale_version -- and renders nothing, rather than
    filing a render of the new release as the old one's rung result."""
    from brambleloop.build2 import executor
    from brambleloop.core.models import Job, JobStatus
    from brambleloop.gateway import images
    from brambleloop.products.builder import for_slug

    slug = "cloudline-baby-blanket"
    current = for_slug(slug).version
    stale = "0.0.1" if current != "0.0.1" else "0.0.2"
    calls: list = []
    gate = executor.GATE_BY_KEY["image_generation"]
    originals = (gate.check, images.usable, owned_photography.make)
    gate.check = lambda db, env: True
    images.usable = lambda db: True
    owned_photography.make = lambda *a, **k: calls.append(k) or {"made": True}
    try:
        db = Database(f"sqlite:///{tempfile.mkdtemp()}/stale.sqlite")
        db.create_all()
        Registry(db).seed_defaults()
        job = JobQueue(db).enqueue(
            "publishing", "assets.owned_photography",
            {"slug": slug, "version": stale, "rung": "regenerate_constrained",
             "reason": "parity_escalation:regenerate_constrained", "failed": ["x"]})
        Worker(db, "rung", phase=Phase.SHADOW,
               job_types=["assets.owned_photography"]).run_once()
        with db.session() as s:
            row = s.get(Job, job.id)
            assert row.status == JobStatus.DONE, row.last_error
            out = dict(row.outputs)
            rec = [dict(r.detail) for r in s.scalars(select(AuditLog).where(
                AuditLog.action == gallery.ESCALATION_RESULT_ACTION,
                AuditLog.artifact == f"{slug}@{stale}"))]
        assert calls == [], "a superseded release's rung rendered the new release"
        assert out["attempted"] is False and out["reason"] == "stale_version", out
        assert out["version"] == stale and out["current_version"] == current
        assert rec and rec[-1]["reason"] == "stale_version"
        # Not counted as an attempt: the ladder for the stale release did not advance falsely,
        # and the current release's ladder is untouched.
        assert gallery.escalation_progress(db, slug=slug, version=stale)["attempted"] == []
        assert gallery.escalation_progress(db, slug=slug, version=current)["attempted"] == []
    finally:
        gate.check, images.usable, owned_photography.make = originals


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
