"""FABLE-P0 §6: the product stage register (products.stage_register).

Every stage is derived from rows the pipeline writes; nothing is typed. The register reads,
never writes product rows, and reports stalls and loops from measurements.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_p0_stage_register.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
os.environ.setdefault("BRAMBLELOOP_PHASE", "shadow")

from sqlalchemy import func, select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (  # noqa: E402
    AuditLog, CostEntry, Incident, Job, JobStatus, Listing, ListingAsset, OperatingReading,
    OwnerAction, PatternVersion, PhysicalTest, Product,
)
from brambleloop.products import stage_register as SR  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: E402,F401 - registers handlers
from brambleloop.runtime.worker import JobContext, handlers  # noqa: E402

NOW = datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc)
SLUG = "p0-register-test-cowl"


def _db() -> Database:
    db = Database(f"sqlite:///{tempfile.mkdtemp(prefix='p0_register_')}/r.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _product(db, *, risk="A", certified=False, at=NOW - timedelta(days=1)):
    with db.session() as s:
        p = Product(slug=SLUG, title="Register test cowl", status="concept", risk_class=risk,
                    created_at=at)
        s.add(p)
        s.flush()
        s.add(PatternVersion(product_id=p.id, version="1.0.0", cir_json={"slug": SLUG},
                             release_hash="r" * 64 if certified else None,
                             certified=certified,
                             certificate={"granted": certified, "findings": []},
                             created_at=at))


def _job(db, job_type, *, status=JobStatus.DONE, outputs=None, inputs=None,
         finished=NOW - timedelta(hours=1), agent="orchestrator", error=None):
    with db.session() as s:
        j = Job(agent=agent, job_type=job_type, inputs=inputs or {"slug": SLUG, "version": "1.0.0"},
                outputs=outputs, status=status, created_at=finished - timedelta(minutes=1),
                finished_at=finished if status in (JobStatus.DONE, JobStatus.DEAD) else None,
                last_error=error)
        s.add(j)
        s.flush()
        return j.id


def _audit(db, action, artifact=SLUG, detail=None, at=NOW - timedelta(hours=2),
           actor="creative_director"):
    with db.session() as s:
        s.add(AuditLog(actor=actor, action=action, artifact=artifact, detail=detail or {}, at=at))


def _row(db):
    return SR.derive(db, SLUG, now=NOW)


def test_the_fifteen_stages_are_the_owners_and_each_has_a_department_and_a_next_action():
    assert len(SR.STAGES) == 15 and len(set(SR.STAGES)) == 15
    assert SR.STAGES[0] == "RESEARCH_CANDIDATE" and SR.STAGES[12] == "PUBLISHED"
    assert set(SR.DEPARTMENT) == set(SR.STAGES) == set(SR.NEXT_ACTION)
    assert all(SR.NEXT_ACTION[s] for s in SR.STAGES)


def test_research_candidate_approved_and_rejected_come_from_gate_rows():
    db = _db()
    _audit(db, "concept.gate_waiting", detail={"waiting_on": ["image_vision"]})
    r = _row(db)
    assert r["stage"] == "RESEARCH_CANDIDATE" and r["department"] == "intelligence"
    assert r["evidence"]["RESEARCH_CANDIDATE"]["waiting_on"] == ["image_vision"]
    _audit(db, "concept.gate_passed", at=NOW - timedelta(hours=1))
    assert _row(db)["stage"] == "RESEARCH_APPROVED"
    db2 = _db()
    _audit(db2, "concept.gate_refused", detail={"decision": "refused"})
    r = _row(db2)
    assert r["stage"] == "REJECTED" and "refused" in r["why"]
    db3 = _db()
    _audit(db3, "creative.winner_intake", detail={"decision": "engineering"})
    assert _row(db3)["stage"] == "RESEARCH_APPROVED"


def test_each_forward_stage_is_reached_only_on_its_own_row():
    db = _db()
    _product(db, risk="B")
    assert _row(db)["stage"] == "PATTERN_IN_DEVELOPMENT"
    db = _db()
    _product(db, risk="B", certified=True)
    r = _row(db)
    assert r["stage"] == "TECHNICALLY_VALIDATED" and r["version"] == "1.0.0"
    assert r["source_digests"]["release_hash"] == "r" * 64
    assert r["source_digests"]["cir_sha256"] == SR.cir_digest({"slug": SLUG})
    # Independent re-verification: the sweep's checks completed on this version.
    _job(db, "cir.twin", outputs={"checked": 1}, agent="validator")
    _job(db, "gate.policy", outputs={"checked": 1}, agent="policy")
    r = _row(db)
    assert r["stage"] == "INDEPENDENT_REVIEW_PASSED"
    assert r["evidence"]["INDEPENDENT_REVIEW_PASSED"]["checks"] == ["cir.twin", "gate.policy"]
    # A customer PDF is the assets.build job's sha256 output, not a listing asset.
    _job(db, "assets.build", outputs={"pdf_sha256": "a" * 64, "pages": 9,
                                      "pdf_sha256_by_terminology": {"US": "a" * 64,
                                                                    "UK": "b" * 64}},
         agent="publishing")
    r = _row(db)
    assert r["stage"] == "PREMIUM_PDF_COMPLETED"
    assert r["source_digests"]["pdf_sha256_by_terminology"]["UK"] == "b" * 64
    with db.session() as s:
        s.add(ListingAsset(product_slug=SLUG, version="1.0.0", position=1, asset_class="render",
                           role="hero", approved=False, blocked_reasons=["untrue"]))
    assert _row(db)["stage"] == "PREMIUM_PDF_COMPLETED", "a blocked asset is not a package"
    with db.session() as s:
        s.add(ListingAsset(product_slug=SLUG, version="1.0.0", position=2, asset_class="render",
                           role="hero", approved=True))
    r = _row(db)
    assert r["stage"] == "VISUAL_PACKAGE_COMPLETED"
    ev = r["evidence"]["VISUAL_PACKAGE_COMPLETED"]
    assert (ev["assets"], ev["approved"], ev["blocked"]) == (2, 1, 1)
    with db.session() as s:
        s.add(Listing(product_slug=SLUG, version="1.0.0", title="t", description="d",
                      state="draft", seo_score=0.8, release_hash="r" * 64))
    r = _row(db)
    # Class B: the listing package is complete, and the physical test is now the owner's.
    assert r["stage"] == "PHYSICAL_TESTING_PENDING" and r["department"] == "owner"
    assert "LISTING_PACKAGE_COMPLETED" in r["evidence"]
    assert any(h.get("requirement") == "physical test" for h in r["owner_held"])
    with db.session() as s:
        s.add(PhysicalTest(product_slug=SLUG, version="1.0.0", tester_ref="tester-1",
                           passed=True, completed_at=NOW - timedelta(hours=1)))
    r = _row(db)
    assert r["stage"] == "PHYSICAL_TESTING_PASSED"
    assert r["quality_evidence"]["physical_tests"] == {"requested": 1, "passed": 1, "failed": 0}
    # An owner grant is READY; a published listing is PUBLISHED.
    _audit(db, "owner.publication.approved", artifact=f"{SLUG}@1.0.0", actor="owner:ops-token",
           at=NOW - timedelta(minutes=30))
    assert _row(db)["stage"] == "READY_FOR_PUBLICATION"
    with db.session() as s:
        l = s.scalar(select(Listing).where(Listing.product_slug == SLUG))
        l.state, l.etsy_listing_id = "published", "123"
    r = _row(db)
    assert r["stage"] == "PUBLISHED" and r["evidence"]["PUBLISHED"]["etsy_listing_id"] == "123"


def test_class_a_skips_the_physical_stage_and_waits_on_the_approval_packet():
    db = _db()
    _product(db, risk="A", certified=True)
    with db.session() as s:
        s.add(ListingAsset(product_slug=SLUG, version="1.0.0", position=1, asset_class="render",
                           role="hero", approved=True))
        s.add(Listing(product_slug=SLUG, version="1.0.0", title="t", description="d",
                      state="draft", release_hash="r" * 64))
    r = _row(db)
    # The approval packet cannot pass on this fixture (no certificate sections), so the
    # product stays at the listing package: OWNER_APPROVAL_PENDING is never reached by
    # assumption.
    assert r["stage"] == "LISTING_PACKAGE_COMPLETED"
    assert "OWNER_APPROVAL_PENDING" not in r["evidence"]
    assert "PHYSICAL_TESTING_PENDING" not in r["evidence"]


def test_revision_required_from_a_halting_incident_or_the_newest_refusal():
    db = _db()
    _product(db, certified=True)
    with db.session() as s:
        s.add(Incident(severity="P1", product_slug=SLUG, signature="stale-artefact:x",
                       summary="x", halts_publication=True, resolved=False))
    r = _row(db)
    assert r["stage"] == "REVISION_REQUIRED" and "incident" in r["why"]
    assert r["quality_evidence"]["open_incidents"][0]["signature"] == "stale-artefact:x"
    db = _db()
    _product(db)
    _audit(db, "cir.drafted", artifact=f"{SLUG}@1.0.0", at=NOW - timedelta(hours=3))
    _audit(db, "cir.revise_unrepairable", artifact=SLUG, at=NOW - timedelta(hours=2))
    r = _row(db)
    assert r["stage"] == "REVISION_REQUIRED"
    assert r["failure_history"]["counts"]["refusals"] == 1
    # Progress after the refusal clears it.
    _audit(db, "cir.compiled", artifact=f"{SLUG}@1.0.0", at=NOW - timedelta(hours=1))
    assert _row(db)["stage"] == "PATTERN_IN_DEVELOPMENT"


def test_a_stall_is_a_stage_older_than_its_allowance_unless_the_owner_holds_it():
    db = _db()
    _product(db, certified=True, at=NOW - timedelta(days=10))
    r = _row(db)
    assert r["stage"] == "TECHNICALLY_VALIDATED" and r["stalled"] is True
    assert r["stall"]["allowance_days"] == SR.STALL_DAYS["TECHNICALLY_VALIDATED"]
    with db.session() as s:
        s.add(OwnerAction(requirement_key=f"physical_calibration:{SLUG}",
                          action=f"tester works a sample of {SLUG}", blocks="publication"))
    r = _row(db)
    assert r["stalled"] is False and r["owner_held"][0]["owner_action"]
    db = _db()
    _product(db, certified=True, at=NOW - timedelta(days=1))
    assert _row(db)["stalled"] is False


def test_loops_are_repeated_no_op_completions_and_revise_cycles():
    db = _db()
    _product(db, certified=True)
    for i in range(SR.LOOP_MIN):
        _job(db, "assets.owned_photography", outputs={"ran": False},
             finished=NOW - timedelta(days=i + 1), agent="publishing")
    r = _row(db)
    assert r["loops"] and r["loops"][0]["kind"] == "repeated_no_op"
    assert r["loops"][0]["job_type"] == "assets.owned_photography"
    assert r["loops"][0]["count"] == SR.LOOP_MIN
    # Work done is not a loop.
    db = _db()
    _product(db, certified=True)
    for i in range(SR.LOOP_MIN):
        _job(db, "assets.owned_photography", outputs={"work_done": 1},
             finished=NOW - timedelta(days=i + 1), agent="publishing")
    assert _row(db)["loops"] == []
    # Outside the window is not a loop either.
    db = _db()
    _product(db, certified=True)
    for i in range(SR.LOOP_MIN):
        _job(db, "assets.owned_photography", outputs={"ran": False},
             finished=NOW - timedelta(days=SR.LOOP_WINDOW_DAYS + i + 1), agent="publishing")
    assert _row(db)["loops"] == []
    db = _db()
    _product(db)
    _job(db, "cir.revise", outputs={"revised": 1}, agent="crochet_engineer",
         finished=NOW - timedelta(days=2))
    _job(db, "cir.revise", outputs={"revised": 1}, agent="crochet_engineer",
         finished=NOW - timedelta(days=1))
    assert [l["kind"] for l in _row(db)["loops"]] == ["compile_revise_cycle"]


def test_cost_last_job_and_failures_are_read_from_rows():
    db = _db()
    _product(db, certified=True)
    ok = _job(db, "gate.certify", outputs={"certified": 1}, agent="quality_director",
              finished=NOW - timedelta(hours=5))
    _job(db, "listing.seo", status=JobStatus.DEAD, error="KeyError: 'slug'",
         finished=NOW - timedelta(hours=4), agent="listing")
    with db.session() as s:
        s.add(CostEntry(agent="publishing", kind="api", amount_cad=0.37, product_slug=SLUG))
        s.add(CostEntry(agent="publishing", kind="api", amount_cad=0.13, product_slug=SLUG))
        s.add(CostEntry(agent="publishing", kind="api", amount_cad=9.0, product_slug="other"))
    r = _row(db)
    assert r["cost_cad"] == 0.5 and r["cost_basis"].startswith("cost_entries")
    assert r["last_successful_job"]["id"] == ok
    assert r["last_successful_job"]["job_type"] == "gate.certify"
    fh = r["failure_history"]
    assert fh["counts"]["dead_or_failed_jobs"] == 1
    assert fh["dead_or_failed_jobs"][0]["error"] == "KeyError: 'slug'"


def test_the_register_counts_every_known_slug_and_reports_production_output():
    db = _db()
    _product(db, certified=True)
    _job(db, "assets.build", outputs={"pdf_sha256": "a" * 64}, agent="publishing")
    _audit(db, "concept.gate_waiting", artifact="another-concept")
    reg = SR.register(db, now=NOW)
    assert reg["products"] == 2
    assert reg["counts"]["PREMIUM_PDF_COMPLETED"] == 1
    assert reg["counts"]["RESEARCH_CANDIDATE"] == 1
    assert reg["produced"] == {"certified_versions": 1, "customer_pdfs": 1,
                               "visual_packages": 0, "listing_packages": 0, "published": 0}
    s = SR.summary(reg)
    assert s["rows"][0]["stage"] and "evidence" not in s["rows"][0]


def test_the_job_writes_one_reading_per_day_reports_work_and_writes_no_product_row():
    db = _db()
    _product(db, certified=True)
    q = JobQueue(db)

    def run():
        job = q.enqueue("orchestrator", "products.stage_register",
                        {"as_of": NOW.isoformat()},
                        idempotency_key=f"t:{os.urandom(4).hex()}")
        ctx = JobContext(job=job, db=db, queue=q, registry=Registry(db), phase=None)
        return handlers.get("products.stage_register")(ctx)

    with db.session() as s:
        before = (s.scalar(select(func.count()).select_from(Product)),
                  s.scalar(select(func.count()).select_from(PatternVersion)),
                  s.scalar(select(func.count()).select_from(Listing)),
                  s.scalar(select(func.count()).select_from(Incident)))
    out = run()
    assert out["ran"] is True and out["work_done"] == 1 and out["reading"]["created"] is True
    assert not pipeline.did_no_work(out, "products.stage_register")
    out2 = run()
    assert out2["reading"]["created"] is False
    with db.session() as s:
        n = s.scalar(select(func.count()).select_from(OperatingReading).where(
            OperatingReading.kind == SR.READING_KIND))
        after = (s.scalar(select(func.count()).select_from(Product)),
                 s.scalar(select(func.count()).select_from(PatternVersion)),
                 s.scalar(select(func.count()).select_from(Listing)),
                 s.scalar(select(func.count()).select_from(Incident)))
        audits = s.scalar(select(func.count()).select_from(AuditLog).where(
            AuditLog.action == SR.AUDIT_ACTION))
    assert n == 1 and audits == 2 and before == after
    assert SR.latest(db)["counts"]["TECHNICALLY_VALIDATED"] == 1


def test_an_empty_company_is_no_work():
    db = _db()
    q = JobQueue(db)
    job = q.enqueue("orchestrator", "products.stage_register", {"as_of": NOW.isoformat()},
                    idempotency_key="t:empty")
    ctx = JobContext(job=job, db=db, queue=q, registry=Registry(db), phase=None)
    out = handlers.get("products.stage_register")(ctx)
    assert out["products"] == 0 and pipeline.did_no_work(out, "products.stage_register")


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                fails += 1
                print("FAIL", name, repr(e))
                traceback.print_exc()
    print(f"{fails} failed")
    sys.exit(1 if fails else 0)
