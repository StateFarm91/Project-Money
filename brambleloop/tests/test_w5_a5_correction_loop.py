"""W5-A5 P0-CORRECTION-LOOP: certify / quality / assets refusals are corrected or held, bounded.

Every flow here runs the REAL registered handlers (`cir.compile`, `gate.certify`, `cir.revise`,
the re-verification checks) through `JobQueue` + `Worker.run_once()` on a real SQLite FILE.
Nothing under test is mocked. The CIRs are the Launch-0 catalogue designs with one defect
injected (a gauge outside the declared yarn's band, or no design provenance): TEST FIXTURES,
not products anybody released.

Run: cd brambleloop && python tests/test_w5_a5_correction_loop.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702  W3-HYG: per-process temp sandbox
import dataclasses
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sqlalchemy import select, update  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (AuditLog, Incident, Job, JobStatus, Listing,  # noqa: E402
                                     PatternVersion, Phase, Product)
from brambleloop.ops import incident_lifecycle  # noqa: E402
from brambleloop.products import launch0  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import engineering_ops as EO  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: E402,F401 - registers handlers
from brambleloop.runtime import quality_ops  # noqa: E402,F401 - registers handlers
from brambleloop.runtime import release  # noqa: E402,F401 - registers handlers
from brambleloop.runtime.worker import JobContext, Worker, handlers  # noqa: E402

LOOP = ["cir.compile", "gate.certify", "cir.revise"]
_N = [0]


def _db() -> Database:
    _N[0] += 1
    db = Database(f"sqlite:///{tempfile.mkdtemp()}/a5_{_N[0]}.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _off_band(key: str, sts: float = 30.0):
    """A Launch-0 design whose gauge its own declared yarn cannot hold."""
    cir = launch0.cir_for(key)
    return dataclasses.replace(cir, gauge=dataclasses.replace(cir.gauge,
                                                              stitches_per_10cm=sts))


def _no_provenance(cir):
    return dataclasses.replace(cir, provenance=None)


def _enqueue_compile(db, cir, key: str | None = None, **extra):
    return JobQueue(db).enqueue("validator", "cir.compile", {"cir": cir.to_dict(), **extra},
                                idempotency_key=key or f"t:compile:{cir.slug}:{cir.fingerprint}")


def _drain(db, types=LOOP, name="a5", limit=200) -> int:
    """Run the worker until nothing of `types` is runnable (quiescence). Bounded."""
    w = Worker(db, name, job_types=types)
    n = 0
    while w.run_once():
        n += 1
        assert n < limit, "the correction loop did not reach quiescence"
    return n


def _slug_of(job) -> str | None:
    i = job.inputs or {}
    return (i.get("cir") or {}).get("slug") or i.get("slug")


def _jobs(db, slug=None, job_type=None) -> list[Job]:
    with db.session() as s:
        rows = list(s.scalars(select(Job).order_by(Job.id)))
    return [j for j in rows if (slug is None or _slug_of(j) == slug)
            and (job_type is None or j.job_type == job_type)]


def _audits(db, action, artifact=None) -> list[AuditLog]:
    with db.session() as s:
        q = select(AuditLog).where(AuditLog.action == action).order_by(AuditLog.id)
        if artifact:
            q = q.where(AuditLog.artifact == artifact)
        return list(s.scalars(q))


def _holds(db, slug, version, open_only=True) -> list[Incident]:
    with db.session() as s:
        q = select(Incident).where(Incident.signature == EO.hold_signature(slug, version))
        if open_only:
            q = q.where(Incident.resolved == False)  # noqa: E712
        return list(s.scalars(q))


def _certified(db, slug, version) -> PatternVersion | None:
    with db.session() as s:
        return s.scalar(select(PatternVersion).join(Product, Product.id ==
                                                    PatternVersion.product_id)
                        .where(Product.slug == slug, PatternVersion.version == version,
                               PatternVersion.certified == True))  # noqa: E712


def _done(jobs) -> list[Job]:
    return [j for j in jobs if j.status == JobStatus.DONE]


# ---- 1. a fixable certify block is revised, recompiled and recertified, untouched by hand ----

def test_a_fixable_certify_block_is_revised_recompiled_and_recertified():
    db = _db()
    healthy = launch0.cir_for("placemat_pair")
    fixable = _off_band("harvest_runner")
    _enqueue_compile(db, fixable)
    _enqueue_compile(db, healthy)
    _drain(db)

    certs = _done(_jobs(db, fixable.slug, "gate.certify"))
    assert len(certs) == 2, [(j.id, j.outputs) for j in certs]
    first, second = certs
    assert first.outputs["granted"] is False
    assert any("GAUGE_OUTSIDE_DECLARED_YARN_BAND" in r for r in first.outputs["reasons"])
    assert first.outputs["correction"]["rules"] == ["GAUGE_FROM_YARN_BAND"]
    revs = _jobs(db, fixable.slug, "cir.revise")
    assert len(revs) == 1 and revs[0].status == JobStatus.DONE
    assert revs[0].agent == "crochet_engineer"
    assert revs[0].inputs["stage"] == "certify"
    assert revs[0].idempotency_key == (f"revise:{fixable.slug}:{fixable.version}:"
                                       f"{fixable.fingerprint}")
    out = revs[0].outputs
    assert out["revised"] is True and out["rule"] == "GAUGE_FROM_YARN_BAND", out
    assert out["detail"]["gauge_from"] == 30.0 and out["detail"]["gauge_to"] < 14.0
    compiles = _jobs(db, fixable.slug, "cir.compile")
    assert len(compiles) == 2 and compiles[1].inputs["revision"] == 1
    assert compiles[1].inputs["revision_of"] == fixable.fingerprint
    # the lineage counter rides from the recompile to the recertification
    assert second.inputs.get("revision") == 1
    assert second.outputs["granted"] is True, second.outputs
    pv = _certified(db, fixable.slug, fixable.version)
    assert pv is not None and pv.cir_json["gauge"]["stitches_per_10cm"] == \
        out["detail"]["gauge_to"]
    assert not _holds(db, fixable.slug, fixable.version)
    assert len(_audits(db, "cir.revised", f"{fixable.slug}@{fixable.version}")) == 1
    # the release chain continues for both products
    for slug in (fixable.slug, healthy.slug):
        assert [j.status for j in _jobs(db, slug, "listing.draft")] == [JobStatus.PENDING], slug


# ---- 2. bounded: exactly MAX_REVISIONS, then a named hold, then nothing more ----

def test_the_cap_is_one_revision_then_a_named_hold_and_quiescence():
    assert EO.MAX_REVISIONS == 1
    db = _db()
    healthy = launch0.cir_for("placemat_pair")
    # A gauge defect the rule repairs AND a provenance defect no rule can: one revision runs,
    # the recertification still refuses, and the loop stops on a named hold.
    stuck = _no_provenance(_off_band("hexagon_coasters"))
    _enqueue_compile(db, stuck)
    _enqueue_compile(db, healthy)
    _drain(db)

    revs = _jobs(db, stuck.slug, "cir.revise")
    assert len(revs) == EO.MAX_REVISIONS == 1, [r.outputs for r in revs]
    assert revs[0].outputs["revised"] is True
    certs = _done(_jobs(db, stuck.slug, "gate.certify"))
    assert [c.outputs["granted"] for c in certs] == [False, False]
    last = certs[-1].outputs["correction"]
    assert last["held"] is True and "PROVENANCE_MISSING" in last["reason"], last
    holds = _holds(db, stuck.slug, stuck.version)
    assert len(holds) == 1
    h = holds[0]
    assert h.severity == "P2" and h.halts_publication is False
    assert h.product_slug == stuck.slug
    assert h.detail["kind"] == "correction_hold" and h.detail["stage"] == "certify"
    assert h.detail["cap"] == 1 and h.detail["attempts"] == 1
    # visible with a named owner and path (the CC incident list reads `actionability`)
    act = incident_lifecycle.actionability(h)
    assert act["needs_owner_path"] is False and "crochet_engineer" in act["remediation_owner"]
    held_rows = _audits(db, EO.HOLD_AUDIT, f"{stuck.slug}@{stuck.version}")
    assert held_rows and held_rows[-1].detail["signature"] == h.signature

    # Quiescence: nothing of the held product is runnable, and more ticks enqueue nothing.
    before = len(_jobs(db, stuck.slug))
    assert all(j.status != JobStatus.PENDING for j in _jobs(db, stuck.slug)), \
        [(j.job_type, j.status) for j in _jobs(db, stuck.slug)]
    assert _drain(db) == 0
    assert len(_jobs(db, stuck.slug)) == before
    # A later event for the held version (a re-certification request under a new key) is
    # refused again and still enqueues no revision.
    revised_cir = CIR_from(certs[-1])
    JobQueue(db).enqueue("quality_director", "gate.certify", {"cir": revised_cir},
                         idempotency_key="t:late-recertify")
    assert _drain(db) == 1
    late = _jobs(db, stuck.slug, "gate.certify")[-1]
    assert late.outputs["correction"].get("already_held") is True
    assert len(_jobs(db, stuck.slug, "cir.revise")) == 1
    assert len(_jobs(db, stuck.slug)) == before + 1
    assert len(_holds(db, stuck.slug, stuck.version)) == 1
    # ... and the healthy product progressed in the same run.
    assert _done(_jobs(db, healthy.slug, "gate.certify"))[0].outputs["granted"] is True
    assert _jobs(db, healthy.slug, "listing.draft")


def CIR_from(job) -> dict:
    return dict(job.inputs["cir"])


def test_cap_off_by_one_is_caught_at_the_boundary():
    """Revision counter 0 -> exactly one revise; counter == cap -> hold, no revise."""
    db = _db()
    under = _off_band("harvest_runner")
    JobQueue(db).enqueue("quality_director", "gate.certify",
                         {"cir": under.to_dict(), "revision": EO.MAX_REVISIONS - 1},
                         idempotency_key="t:under")
    _drain(db, ["gate.certify"])
    assert len(_jobs(db, under.slug, "cir.revise")) == 1
    assert not _holds(db, under.slug, under.version)

    db2 = _db()
    at = _off_band("harvest_runner")
    JobQueue(db2).enqueue("quality_director", "gate.certify",
                          {"cir": at.to_dict(), "revision": EO.MAX_REVISIONS},
                          idempotency_key="t:at")
    _drain(db2, ["gate.certify"])
    assert _jobs(db2, at.slug, "cir.revise") == []
    out = _jobs(db2, at.slug, "gate.certify")[0].outputs["correction"]
    assert out["held"] is True and "revision cap 1" in out["reason"], out
    assert len(_holds(db2, at.slug, at.version)) == 1


def test_the_durable_count_bounds_a_lineage_whose_counter_was_reset():
    """A second design of the same slug@version arriving with revision 0 (a re-draft, a
    replayed event) is still bounded by the revisions already recorded for that version."""
    db = _db()
    first = _off_band("harvest_runner", 30.0)
    _enqueue_compile(db, first)
    _drain(db)
    assert len(_jobs(db, first.slug, "cir.revise")) == 1
    assert EO.revision_attempts(db, first.slug, first.version) == 1
    other = _off_band("harvest_runner", 29.0)          # same slug@version, new fingerprint
    assert other.fingerprint != first.fingerprint
    JobQueue(db).enqueue("quality_director", "gate.certify", {"cir": other.to_dict()},
                         idempotency_key="t:other")
    _drain(db)
    assert len(_jobs(db, first.slug, "cir.revise")) == 1
    out = _jobs(db, first.slug, "gate.certify")[-1].outputs["correction"]
    assert out["held"] is True and "revision cap" in out["reason"], out


def test_an_unanswerable_block_goes_straight_to_the_named_hold():
    db = _db()
    healthy = launch0.cir_for("placemat_pair")
    bare = _no_provenance(launch0.cir_for("nordic_forest_baby"))
    _enqueue_compile(db, bare)
    _enqueue_compile(db, healthy)
    _drain(db)
    assert _jobs(db, bare.slug, "cir.revise") == []
    cert = _jobs(db, bare.slug, "gate.certify")[0].outputs
    assert cert["granted"] is False and cert["correction"]["held"] is True
    assert "no deterministic revision" in cert["correction"]["reason"]
    h = _holds(db, bare.slug, bare.version)
    assert len(h) == 1 and h[0].detail["attempts"] == 0
    assert "PROVENANCE_MISSING" in h[0].detail["codes"]
    assert _done(_jobs(db, healthy.slug, "gate.certify"))[0].outputs["granted"] is True


def test_evidence_refusal_ignores_unrelated_uppercase_prose():
    codes = EO.codes_of(["ERROR PHYSICAL_TEST_REQUIRED: missing sample; NOTE: wait",
                         "ERROR: plain failure", "US REPEAT: broken repeat"])
    assert codes == ["PHYSICAL_TEST_REQUIRED", "REPEAT"], codes
    db = _db()
    cir = _off_band("harvest_runner")
    job = JobQueue(db).enqueue("quality_director", "gate.certify", {"cir": cir.to_dict()},
                               idempotency_key="t:evidence-message")
    ctx = JobContext(job=job, db=db, queue=JobQueue(db), registry=Registry(db),
                     phase=Phase.SHADOW)
    out = EO.route_failure(ctx, cir, stage="certify",
                           problems=["ERROR PHYSICAL_TEST_REQUIRED: no sample; NOTE: wait"])
    assert out.get("waiting_on_evidence") == ["PHYSICAL_TEST_REQUIRED"], out
    assert _jobs(db, cir.slug, "cir.revise") == []
    assert not _holds(db, cir.slug, cir.version)


def test_missing_physical_evidence_waits_and_is_not_held():
    db = _db()
    cir = launch0.cir_for("harvest_runner")
    job = JobQueue(db).enqueue("quality_director", "gate.certify", {"cir": cir.to_dict()},
                               idempotency_key="t:evidence")
    ctx = JobContext(job=job, db=db, queue=JobQueue(db), registry=Registry(db),
                     phase=Phase.SHADOW)
    out = EO.route_failure(ctx, cir, stage="certify", codes={"PHYSICAL_TEST_REQUIRED"})
    assert out == {"held": False, "waiting_on_evidence": ["PHYSICAL_TEST_REQUIRED"]}
    assert not _holds(db, cir.slug, cir.version)
    assert _jobs(db, job_type="cir.revise") == []


# ---- 3. idempotency: duplicate events and a lost lease never duplicate a revision ----

def test_duplicate_certify_events_produce_one_revision():
    db = _db()
    fixable = _off_band("harvest_runner")
    for key in ("t:event-a", "t:event-b"):
        JobQueue(db).enqueue("quality_director", "gate.certify", {"cir": fixable.to_dict()},
                             idempotency_key=key)
    _drain(db, ["gate.certify"])
    certs = _jobs(db, fixable.slug, "gate.certify")
    assert len(certs) == 2
    assert [c.outputs["correction"]["duplicate"] for c in certs] == [False, True]
    assert len(_jobs(db, fixable.slug, "cir.revise")) == 1


def test_a_lost_lease_rerun_never_duplicates_the_revision():
    db = _db()
    fixable = _off_band("harvest_runner")
    JobQueue(db).enqueue("quality_director", "gate.certify", {"cir": fixable.to_dict()},
                         idempotency_key="t:lease")
    _drain(db, ["gate.certify"])
    q = JobQueue(db)
    # A worker claims the revision, does its work, and dies before completing it.
    dead = q.claim("dead-worker", ["cir.revise"])
    assert dead is not None and dead.job_type == "cir.revise"
    handlers.get("cir.revise")(JobContext(job=dead, db=db, queue=q, registry=Registry(db),
                                          phase=Phase.SHADOW))
    assert len(_audits(db, "cir.revised")) == 1
    with db.session() as s:
        s.execute(update(Job).where(Job.id == dead.id).values(
            lease_expires_at=datetime(2000, 1, 1, tzinfo=timezone.utc)))
    # A restarted worker reclaims the expired lease and runs the body again.
    _drain(db, ["cir.revise"], name="restarted")
    assert _audits(db, "queue.lease_reclaimed")
    with db.session() as s:
        assert s.get(Job, dead.id).status == JobStatus.DONE
    assert len(_jobs(db, fixable.slug, "cir.revise")) == 1
    assert len(_audits(db, "cir.revised")) == 1, "a re-run wrote a second revision record"
    assert EO.revision_attempts(db, fixable.slug, fixable.version) == 1
    recompiles = [j for j in _jobs(db, fixable.slug, "cir.compile")
                  if j.inputs.get("revision") == 1]
    assert len(recompiles) == 1, "a re-run enqueued a second recompile"
    _drain(db)
    assert _certified(db, fixable.slug, fixable.version) is not None


def test_a_lost_lease_on_a_held_certify_keeps_one_hold():
    db = _db()
    bare = _no_provenance(launch0.cir_for("nordic_forest_baby"))
    JobQueue(db).enqueue("quality_director", "gate.certify", {"cir": bare.to_dict()},
                         idempotency_key="t:hold-lease")
    q = JobQueue(db)
    dead = q.claim("dead-worker", ["gate.certify"])
    handlers.get("gate.certify")(JobContext(job=dead, db=db, queue=q, registry=Registry(db),
                                            phase=Phase.SHADOW))
    with db.session() as s:
        s.execute(update(Job).where(Job.id == dead.id).values(
            lease_expires_at=datetime(2000, 1, 1, tzinfo=timezone.utc)))
    _drain(db, ["gate.certify"], name="restarted")
    holds = _holds(db, bare.slug, bare.version)
    assert len(holds) == 1 and holds[0].report_count == 2
    assert _jobs(db, job_type="cir.revise") == []


# ---- 4. quality re-verification and assets: corrected when a rule answers, else held ----

def _legacy_release(db, cir, listing_title: str):
    with db.session() as s:
        p = Product(slug=cir.slug, title=cir.title, status="certified")
        s.add(p)
        s.flush()
        s.add(PatternVersion(product_id=p.id, version=cir.version, cir_json=cir.to_dict(),
                             certified=True, release_hash="r" * 64,
                             certificate={"granted": True}))
        s.add(Listing(product_slug=cir.slug, version=cir.version, title=listing_title,
                      description="Worked flat.", tags=["crochet pattern"], price_cad=9.0))


def test_unrelated_reverification_does_not_rewrite_gauge():
    db = _db()
    legacy = _off_band("harvest_runner")
    _legacy_release(db, legacy, "Harvest Market Basket Crochet Pattern")
    healthy = launch0.cir_for("placemat_pair")
    _enqueue_compile(db, healthy)
    JobQueue(db).enqueue("asset_truth", "gate.asset_truth",
                         {"slug": legacy.slug, "version": legacy.version,
                          "release_hash": "r" * 64}, idempotency_key="t:reverify")
    _drain(db, ["gate.asset_truth"] + LOOP)
    check = _jobs(db, legacy.slug, "gate.asset_truth")[0].outputs
    assert check["ok"] is False and check["correction"]["held"] is True, check
    assert _jobs(db, legacy.slug, "cir.revise") == []
    pv = _certified(db, legacy.slug, legacy.version)
    assert pv.cir_json["gauge"]["stitches_per_10cm"] == 30.0
    assert pv.certificate.get("withholding", {}).get("quality_reverify")
    assert _done(_jobs(db, healthy.slug, "gate.certify"))[0].outputs["granted"] is True


def test_gauge_repair_preserves_hook_row_and_chain_measurements():
    cir = _off_band("harvest_runner")
    gauge = dataclasses.replace(cir.gauge, hook_mm=3.5, rows_per_10cm=24,
                                chains_per_10cm=21, chain_gauge_uncertainty=0.05)
    cir = dataclasses.replace(cir, gauge=gauge)
    repaired, audit = EO.repair_gauge_band(cir)
    assert repaired is not None, audit
    assert repaired.gauge.stitches_per_10cm != gauge.stitches_per_10cm
    for field in ("hook_mm", "rows_per_10cm", "chains_per_10cm", "chain_gauge_uncertainty",
                  "stitch_type", "yarn_weight"):
        assert getattr(repaired.gauge, field) == getattr(gauge, field), field
    assert audit["gauge_from"] == gauge.stitches_per_10cm
    assert audit["gauge_to"] == repaired.gauge.stitches_per_10cm


def test_certified_version_is_revised_as_a_new_immutable_release():
    db = _db()
    legacy = _off_band("harvest_runner")
    _legacy_release(db, legacy, "Harvest Table Runner Crochet Pattern")
    JobQueue(db).enqueue("quality_director", "gate.certify", {"cir": legacy.to_dict()},
                         idempotency_key="t:recertify-legacy")
    _drain(db)
    revise = _jobs(db, legacy.slug, "cir.revise")
    assert len(revise) == 1 and revise[0].status == JobStatus.DONE, revise
    assert revise[0].inputs["bump_version"] is True
    assert revise[0].outputs["to_version"] == "1.3.0", revise[0].outputs
    assert _certified(db, legacy.slug, "1.3.0") is not None
    old = _certified(db, legacy.slug, legacy.version)
    assert old.cir_json["gauge"]["stitches_per_10cm"] == 30.0
    certs = _jobs(db, legacy.slug, "gate.certify")
    assert len(certs) == 2 and certs[-1].outputs["granted"] is True
    assert certs[-1].inputs["correction"]["of_release_hashes"] == ["r" * 64]
    with db.session() as session:
        assert not session.scalar(select(Incident).where(
            Incident.signature == f"release.version_immutable:{legacy.slug}@{legacy.version}"))


def test_occupied_correction_version_is_held_before_any_revision():
    db = _db()
    legacy = _off_band("harvest_runner")
    _legacy_release(db, legacy, "Harvest Table Runner Crochet Pattern")
    with db.session() as session:
        product = session.scalar(select(Product).where(Product.slug == legacy.slug))
        session.add(PatternVersion(product_id=product.id, version="1.3.0",
                                   cir_json=dataclasses.replace(legacy, version="1.3.0").to_dict(),
                                   certified=True, release_hash="s" * 64,
                                   certificate={"granted": True}))
    JobQueue(db).enqueue("quality_director", "gate.certify", {"cir": legacy.to_dict()},
                         idempotency_key="t:recertify-occupied")
    _drain(db)
    jobs = _jobs(db, legacy.slug, "cir.revise")
    assert len(jobs) == 1 and jobs[0].status == JobStatus.DONE
    assert jobs[0].outputs["held"] and not jobs[0].outputs["revised"], jobs[0].outputs
    assert _holds(db, legacy.slug, legacy.version)
    assert not _audits(db, EO.REVISED_AUDIT, f"{legacy.slug}@{legacy.version}")
    assert not _jobs(db, legacy.slug, "cir.compile")
    assert _certified(db, legacy.slug, "1.3.0").release_hash == "s" * 64


def test_late_version_collision_gets_a_named_source_hold():
    db = _db()
    original = launch0.cir_for("harvest_runner")
    candidate = dataclasses.replace(original, version="1.3.0")
    existing = dataclasses.replace(candidate, title="Other Table Runner")
    _legacy_release(db, existing, "Other Table Runner Crochet Pattern")
    JobQueue(db).enqueue("quality_director", "gate.certify",
                         {"cir": candidate.to_dict(),
                          "correction": {"of_versions": [original.version]}},
                         idempotency_key="t:late-version-collision")
    _drain(db, ["gate.certify"])
    result = _jobs(db, original.slug, "gate.certify")[0].outputs
    assert result["refused"] == "version_immutable", result
    assert _holds(db, original.slug, original.version)
    assert _certified(db, original.slug, "1.3.0").cir_json["title"] == existing.title


def test_physically_evidenced_gauge_is_not_changed_for_unrelated_refusal():
    from brambleloop.gates.certificate import gauge_findings
    db = _db()
    cir = _off_band("harvest_runner")
    assert not any(f.is_error for f in gauge_findings(cir, physically_evidenced=True))
    job = JobQueue(db).enqueue("quality_director", "gate.certify", {"cir": cir.to_dict()},
                               idempotency_key="t:physical-evidence-refusal")
    ctx = JobContext(job=job, db=db, queue=JobQueue(db), registry=Registry(db),
                     phase=Phase.SHADOW)
    out = EO.route_failure(ctx, cir, stage="certify", codes={"PROVENANCE_MISSING"})
    assert out["held"] is True, out
    assert _jobs(db, cir.slug, "cir.revise") == []


def test_a_reverification_with_no_rule_stands_on_its_existing_hold():
    db = _db()
    cir = launch0.cir_for("harvest_runner")              # in-band gauge: no rule answers
    _legacy_release(db, cir, "Harvest Market Basket Crochet Pattern")
    JobQueue(db).enqueue("asset_truth", "gate.asset_truth",
                         {"slug": cir.slug, "version": cir.version, "release_hash": "r" * 64},
                         idempotency_key="t:reverify-nofix")
    _drain(db, ["gate.asset_truth"] + LOOP)
    out = _jobs(db, cir.slug, "gate.asset_truth")[0].outputs
    assert out["ok"] is False and out["correction"]["held"] is True
    assert out["correction"]["hold"] == quality_ops.signature("gate.asset_truth", cir.slug,
                                                              cir.version)
    assert _jobs(db, cir.slug, "cir.revise") == []
    with db.session() as s:
        incs = list(s.scalars(select(Incident)))
    # no second incident: the re-verification's own P2 incident is the named hold
    assert [i.signature for i in incs] == [out["correction"]["hold"]]
    assert _audits(db, EO.HOLD_AUDIT, f"{cir.slug}@{cir.version}")


def test_assets_truth_failure_routes_through_the_same_loop():
    """`assets.build`'s successor wrapper hands Asset Truth errors to the router. No current
    rule answers an asset-truth code, so it stands on the assets dead-end incident."""
    from brambleloop.runtime import chain_successors
    from brambleloop.runtime.release import _correct_assets

    db = _db()
    cir = launch0.cir_for("harvest_runner")
    _legacy_release(db, cir, "Harvest Table Runner Crochet Pattern")
    job = JobQueue(db).enqueue("publishing", "assets.build",
                               {"slug": cir.slug, "version": cir.version, "release": "r" * 64},
                               idempotency_key="t:assets")
    ctx = JobContext(job=job, db=db, queue=JobQueue(db), registry=Registry(db),
                     phase=Phase.SHADOW)
    out = _correct_assets(ctx, ["ERROR COLOR_NOT_IN_PATTERN: frame 2 shows teal"])
    assert out["held"] is True and out["hold"] == chain_successors.signature(
        chain_successors.ASSETS, cir.slug, cir.version)
    assert _jobs(db, job_type="cir.revise") == []
    # An unrelated asset defect never authorizes changing the gauge.
    db2 = _db()
    bad = _off_band("harvest_runner")
    _legacy_release(db2, bad, "Harvest Table Runner Crochet Pattern")
    job2 = JobQueue(db2).enqueue("publishing", "assets.build",
                                 {"slug": bad.slug, "version": bad.version,
                                  "release": "r" * 64}, idempotency_key="t:assets2")
    ctx2 = JobContext(job=job2, db=db2, queue=JobQueue(db2), registry=Registry(db2),
                      phase=Phase.SHADOW)
    out2 = _correct_assets(ctx2, ["ERROR COLOR_NOT_IN_PATTERN: frame 2 shows teal"])
    assert out2["held"] is True, out2
    assert _jobs(db2, bad.slug, "cir.revise") == []


def test_concurrent_distinct_revisions_claim_only_one_source_version():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    db = _db()
    one = _off_band("harvest_runner", 30.0)
    two = _off_band("harvest_runner", 31.0)
    assert one.fingerprint != two.fingerprint and one.version == two.version
    queue = JobQueue(db)
    for i, cir in enumerate((one, two)):
        queue.enqueue("crochet_engineer", "cir.revise",
                      {"cir": cir.to_dict(), "stage": "certify",
                       "codes": ["GAUGE_OUTSIDE_DECLARED_YARN_BAND"]},
                      idempotency_key=f"t:concurrent-revision:{i}")
    barrier = Barrier(2, timeout=20)
    original = EO.RULES
    rule = EO.repair_gauge_band

    def overlap(cir):
        result = rule(cir)
        barrier.wait()
        return result

    EO.RULES = tuple((name, codes, overlap if name == "GAUGE_FROM_YARN_BAND" else fn)
                     for name, codes, fn in original)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(Worker(db, f"parallel-{i}", job_types=["cir.revise"]).run_once)
                       for i in range(2)]
            assert all(f.result(timeout=45) for f in futures)
    finally:
        EO.RULES = original
    revisions = _jobs(db, one.slug, "cir.revise")
    assert all(job.status == JobStatus.DONE for job in revisions), [(j.status, j.last_error) for j in revisions]
    assert sum(bool(job.outputs.get("revised")) for job in revisions) == 1, [j.outputs for j in revisions]
    assert sum(bool(job.outputs.get("held")) for job in revisions) == 1, [j.outputs for j in revisions]
    assert len(_audits(db, EO.REVISED_AUDIT, f"{one.slug}@{one.version}")) == 1
    assert len(_jobs(db, one.slug, "cir.compile")) == 1


def test_a_compile_failure_without_a_rule_is_held_not_revised():
    from brambleloop.runtime.pipeline import Concept, concept_to_cir
    from brambleloop.cir.model import Op

    bad = concept_to_cir(Concept(slug="a5-ragged", title="A5 Ragged Panel", category="coaster",
                                 stitch_repeat=[("sc", 2), ("dc", 2)], width_stitches=50,
                                 rows=8, colors={"A": "cream", "B": "sage"}))
    bad.components[0].rows[2].ops.append(Op("dc", 3))   # not a uniform panel any more
    db = _db()
    _enqueue_compile(db, bad)
    _drain(db)
    revs = _jobs(db, bad.slug, "cir.revise")
    # REPEAT is answerable in principle, so one revision is tried; it cannot apply here
    assert len(revs) == 1 and revs[0].outputs["unrepairable"] is True
    assert len(_holds(db, bad.slug, bad.version)) == 1
    assert _jobs(db, bad.slug, "gate.certify") == []
    assert _drain(db) == 0


if __name__ == "__main__":
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                traceback.print_exc()
                fails += 1
                print("FAIL", name, repr(e))
    print(f"{fails} failure(s)")
    sys.exit(1 if fails else 0)
