"""A6 x I-A6-FROZEN-KNOWLEDGE-CONTRACT: approved design knowledge (Codex's evaluated, independently
approved DesignRule) is frozen into a draft and re-verified at every boundary (opus2).

Real SQLite file, real handlers through the Worker: the rule is reached the only way it can be
-- licensed fixture analysis, independent review, a passed held-out evaluation, owner approval
(as in test_codex_knowledge_contract). Then: `cir.draft` freezes its pin into the CIR, the
compiled design certifies (`gate.certify`), its PDF renders (`assets.build`); once the rule
is retired the same design is refused by name at certification, re-verification, the PDF and
the release gate, and a design with no pins is untouched throughout.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_w5_a6_frozen_knowledge.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import dataclasses
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.cir import knowledge as K  # noqa: E402
from brambleloop.cir.model import CIR  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (AuditLog, BenchmarkAnalysis, BenchmarkProduct, Job,  # noqa: E402
                                     JobStatus, PatternVersion, Product)
from brambleloop.improve import design_knowledge as DK  # noqa: E402
from brambleloop.improve import knowledge_gate as KG  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: E402
from brambleloop.runtime.worker import Worker  # noqa: E402

SEED = "nordic-forest-basket"


def _store():
    path = f"{tempfile.mkdtemp(prefix='a6k_')}/a6k.sqlite"
    db = Database(f"sqlite:///{path}")
    db.create_all()
    Registry(db).seed_defaults()
    return db, path


def _approved_rule(db) -> dict:
    """The rule, the only way it can exist: reviewed analysis -> evaluated -> owner approval."""
    from brambleloop.gates.originality import code_benchmarks, record_fingerprint
    from brambleloop.quality import design_eval
    from brambleloop.teardown import licence, review

    sha = "b" * 64
    with db.session() as s:
        product = BenchmarkProduct(ref="fixture-purchase", seller="fixture",
                                   files=[{"name": "reference.pdf", "sha256": sha}])
        s.add(product)
        s.flush()
        source = BenchmarkAnalysis(benchmark_id=product.id, file_sha256=sha, observations={
            "fully_readable": True, "dimensions": {"finishing": "absent"}})
        s.add(source)
        s.flush()
        source_id = source.id
    licence.capture_purchase(db, "fixture-purchase")
    review.review_analysis(db, source_id, reviewer="independent-reviewer", decision="reviewed",
                           reason="reviewed observation")
    rule = DK.propose_from_analysis(db, source_id)
    for ref in [*(b.ref for b in code_benchmarks()), "fixture-purchase"]:
        record_fingerprint(db, ref, text=("xylophone quasar nebula orbit lantern velvet meadow "
                                          "cobalt river telescope compass marigold dolphin "
                                          "rainforest juniper quartz"))
    evaluation = design_eval.evaluate(db, rule["id"])
    assert evaluation["state"] == "passed", evaluation
    return DK.review_rule(db, rule["id"], reviewer="owner", decision="approve",
                          reason="independent review", evaluation_id=evaluation["audit_id"])


def _draft(db, path) -> CIR:
    import dataclasses as dc

    seed = pipeline._seed_for(SEED)
    with db.session() as s:
        p = s.scalar(select(Product).where(Product.slug == seed.slug))
        if p is None:
            p = Product(slug=seed.slug, title=seed.title)
            s.add(p)
            s.flush()
            s.add(PatternVersion(product_id=p.id, version="0.9.0", cir_json={},
                                 certified=True))
    inputs = {k: v for k, v in dc.asdict(seed).items() if not isinstance(v, tuple)}
    inputs.update(pipeline.concept_geometry(seed))
    JobQueue(db).enqueue("crochet_engineer", "cir.draft", inputs, priority=0)
    w = Worker(Database(f"sqlite:///{path}"), "a6k", job_types=["cir.draft"])
    while w.run_once():
        pass
    with db.session() as s:
        j = s.scalars(select(Job).where(Job.job_type == "cir.compile")
                      .order_by(Job.id.desc())).first()
        return CIR.from_dict(j.inputs["cir"])


def _run(db, path, job_type, inputs, agent):
    job = JobQueue(db).enqueue(agent, job_type, inputs, priority=0)
    w = Worker(Database(f"sqlite:///{path}"), "a6k", job_types=[job_type])
    while w.run_once():
        pass
    with db.session() as s:
        row = s.get(Job, job.id)
        return row.status, dict(row.outputs or {}), str(row.last_error or "")


def _certified(db, cir, version):
    pinned = dataclasses.replace(cir, version=version)
    with db.session() as s:
        p = s.scalar(select(Product).where(Product.slug == pinned.slug))
        s.add(PatternVersion(product_id=p.id, version=version, cir_json=pinned.to_dict(),
                             certified=True))
    return pinned


def test_approved_knowledge_is_frozen_into_the_draft_and_every_boundary_reverifies_it():
    db, path = _store()
    baseline = _draft(db, path)
    assert not KG.has_pins(baseline)                       # no approved rule: untouched
    approved = _approved_rule(db)
    pin = approved["pin"]
    # a fresh draft of the same concept now carries the frozen pin, recorded once
    with db.session() as s:
        for j in s.scalars(select(Job).where(Job.job_type.in_(("cir.draft", "cir.compile")))):
            s.delete(j)
    pinned = _draft(db, path)
    assert KG.has_pins(pinned), pinned.provenance.primitives_used
    assert [e["pin"] for e in K.markers(pinned)] == [pin]
    assert pinned.fingerprint != baseline.fingerprint
    with db.session() as s:
        frozen = [a.detail for a in s.scalars(select(AuditLog).where(
            AuditLog.action == KG.FROZEN))]
    assert frozen and frozen[-1]["pins"] == [pin], frozen
    assert KG.refusal(db, pinned) is None
    # certify and the PDF accept it while the pin verifies
    status, out, err = _run(db, path, "gate.certify", {"cir": pinned.to_dict()}, "validator")
    assert out.get("refused") != "design_knowledge", (status, out, err)
    release = _certified(db, pinned, "2.0.0")
    status, out, err = _run(db, path, "assets.build", {"slug": release.slug,
                                                       "version": "2.0.0"}, "publishing")
    assert status == JobStatus.DONE and out.get("refused") != "design_knowledge", (out, err)
    # the rule is retired: every boundary refuses the pinned design by name
    DK.review_rule(db, approved["rule_id"] if "rule_id" in approved else approved["id"],
                   reviewer="owner", decision="retire", reason="retire the rule")
    why = KG.refusal(db, pinned)
    assert why and "does not verify" in why
    status, out, _err = _run(db, path, "gate.certify", {"cir": pinned.to_dict()}, "validator")
    assert out.get("granted") is False and out.get("refused") == "design_knowledge", out
    status, out, _err = _run(db, path, "assets.build", {"slug": release.slug,
                                                        "version": "2.0.0"}, "publishing")
    assert status == JobStatus.DONE and out.get("refused") == "design_knowledge", out
    from brambleloop.runtime import quality_ops

    r = quality_ops.reverify(db, "cir.twin", release.slug, "2.0.0")
    assert r["ok"] is False and "does not verify" in r["problems"][0], r
    from brambleloop.publish import release_gates

    assert any("does not verify" in x
               for x in release_gates._knowledge_reasons(db, release.slug, "2.0.0"))
    with db.session() as s:
        boundaries = {a.detail.get("boundary") for a in s.scalars(select(AuditLog).where(
            AuditLog.action == KG.REFUSED))}
    assert {"gate.certify", "assets.build"} <= boundaries, boundaries
    # a design with no pins is never refused by the knowledge gate
    assert KG.refusal(db, baseline) is None
    assert release_gates._knowledge_reasons(db, release.slug, "9.9.9") == []


def test_a_forged_pin_is_refused_and_the_contract_is_v3():
    from brambleloop.core import contracts

    db, path = _store()
    baseline = _draft(db, path)
    forged = {"rule_id": 999, "rule_version": 1, "rule_digest": "a" * 64,
              "evaluation_digest": "c" * 64}
    prov = dataclasses.replace(baseline.provenance, primitives_used=(
        *baseline.provenance.primitives_used, K.marker("include_finishing_checklist", forged)))
    fake = dataclasses.replace(baseline, provenance=prov)
    assert KG.has_pins(fake) and KG.refusal(db, fake)
    assert contracts.CONTRACTS["cir"][0] == 3 and contracts.check() == []


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"OK   {name}")
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print(f"FAIL {name} {exc!r}"[:900])
                import traceback
                traceback.print_exc()
    print(f"{failed} failed")
    sys.exit(1 if failed else 0)
