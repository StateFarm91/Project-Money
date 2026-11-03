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


def _approved_rule(db, *, scope=None) -> dict:
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
    rule = (DK.propose_from_analysis(db, source_id) if scope is None else DK.propose(
        db, key=f"scoped_{scope}", producer="analyst",
        statement={"rule": "include_finishing_checklist", "parameters": {}},
        scope={"writer_section": "finishing", "construction_family": scope},
        provenance=[{"kind": "analysis", "id": source_id}]))
    for ref in [*(b.ref for b in code_benchmarks()), "fixture-purchase"]:
        record_fingerprint(db, ref, text=("xylophone quasar nebula orbit lantern velvet meadow "
                                          "cobalt river telescope compass marigold dolphin "
                                          "rainforest juniper quartz"))
    evaluation = design_eval.evaluate(db, rule["id"])
    assert evaluation["state"] == "passed", evaluation
    return DK.review_rule(db, rule["id"], reviewer="owner", decision="approve",
                          reason="independent review", evaluation_id=evaluation["audit_id"])


def _draft(db, path, seed_slug=SEED) -> CIR:
    import dataclasses as dc

    seed = pipeline._seed_for(seed_slug)
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


def test_approved_knowledge_is_frozen_into_the_draft_and_every_boundary_reverifies_it():
    db, path = _store()
    baseline = _draft(db, path)
    assert not KG.has_pins(baseline)                       # no approved rule: untouched
    approved = _approved_rule(db)
    pin = approved["pin"]
    # Retain the first draft and its audited jobs; a pin changes the compile key.
    pinned = _draft(db, path)
    assert KG.has_pins(pinned), pinned.provenance.primitives_used
    assert [e["pin"] for e in K.markers(pinned)] == [pin]
    assert pinned.fingerprint != baseline.fingerprint
    from brambleloop.cir.compiler import compile_cir
    from brambleloop.cir.writer import write_pattern
    baseline_text = write_pattern(baseline, compile_cir(baseline))
    pinned_text = write_pattern(pinned, compile_cir(pinned))
    assert pinned_text != baseline_text
    assert "\n- " in pinned_text.partition("## Finishing")[2]
    assert "\n- " not in baseline_text.partition("## Finishing")[2]
    with db.session() as s:
        frozen = [a.detail for a in s.scalars(select(AuditLog).where(
            AuditLog.action == KG.FROZEN))]
    assert frozen and frozen[-1]["pins"] == [pin], frozen
    assert KG.refusal(db, pinned) is None
    # certify and the PDF accept it while the pin verifies
    status, out, err = _run(db, path, "gate.certify", {"cir": pinned.to_dict()}, "quality_director")
    assert status == JobStatus.DONE and out.get("granted") is True, (status, out, err)
    release = pinned
    with db.session() as s:
        persisted = s.scalar(select(PatternVersion).join(Product).where(
            Product.slug == release.slug, PatternVersion.version == release.version))
        assert persisted is not None and persisted.certified is True
        assert CIR.from_dict(persisted.cir_json).fingerprint == release.fingerprint
    status, out, err = _run(db, path, "assets.build", {"slug": release.slug,
                                                       "version": release.version}, "publishing")
    assert status == JobStatus.DONE and out.get("pdf_sha256"), (out, err)
    # the rule is retired: every boundary refuses the pinned design by name
    DK.review_rule(db, approved["rule_id"] if "rule_id" in approved else approved["id"],
                   reviewer="owner", decision="retire", reason="retire the rule")
    why = KG.refusal(db, pinned)
    assert why and "does not verify" in why
    status, out, _err = _run(db, path, "gate.certify", {"cir": pinned.to_dict()}, "quality_director")
    assert status == JobStatus.DONE and out.get("granted") is False and out.get("refused") == "design_knowledge", out
    status, out, _err = _run(db, path, "assets.build", {"slug": release.slug,
                                                        "version": release.version}, "publishing")
    assert status == JobStatus.DONE and out.get("refused") == "design_knowledge", out
    from brambleloop.runtime import quality_ops

    r = quality_ops.reverify(db, "cir.twin", release.slug, release.version)
    assert r["ok"] is False and "does not verify" in r["problems"][0], r
    from brambleloop.publish import release_gates

    assert any("does not verify" in x
               for x in release_gates._knowledge_reasons(db, release.slug, release.version))
    with db.session() as s:
        boundaries = {a.detail.get("boundary") for a in s.scalars(select(AuditLog).where(
            AuditLog.action == KG.REFUSED))}
    assert {"gate.certify", "assets.build"} <= boundaries, boundaries
    # A queued visual stage and direct gallery actions must also re-check the
    # current pin, before a generator, follow-on job, approval or asset write.
    from brambleloop.visual import image_production as IP, gallery_persist as GP
    from brambleloop.visual.image_records import ImageCandidate
    visual_inputs = {"slug": release.slug, "version": release.version,
                     "release": "fixture", "stage": "product_generation"}
    status, out, err = _run(db, path, "visual.image_production", visual_inputs, "publishing")
    assert status == JobStatus.DONE and out.get("refused") == "design_knowledge", (out, err)
    key = IP._ensure_run(db, release.slug, release.version, "fixture")
    with db.session() as s:
        run = IP._run(s, key)
        run.status = "ready_for_owner_review"
        candidate = ImageCandidate(sha256="d" * 64, run_key=key, method="autonomous",
            provenance_kind="synthetic", slug=release.slug, version=release.version)
        s.add(candidate)
        s.flush()
        candidate_id = candidate.id
    approval = IP.approve(db, key, decided_by="owner")
    assert approval.get("refused") == "design_knowledge", approval
    with db.session() as s:
        IP._run(s, key).status = "approved_for_publication"
    persisted = GP.persist_approved(db, key)
    assert persisted.get("refused") == "design_knowledge", persisted
    checked = IP.reverify(db, candidate_id, judges=object())
    assert checked.get("refused") == "design_knowledge", checked
    # a design with no pins is never refused by the knowledge gate
    assert KG.refusal(db, baseline) is None
    assert release_gates._knowledge_reasons(db, release.slug, "9.9.9") == []


def test_scoped_rule_changes_matching_draft_and_never_freezes_wrong_family():
    from brambleloop.cir.compiler import compile_cir
    from brambleloop.cir.writer import write_pattern
    db, path = _store()
    baseline = _draft(db, path)
    assert baseline.construction == "joined_rounds"
    approved = _approved_rule(db, scope="joined_rounds")
    pinned = _draft(db, path)
    assert [e["pin"] for e in K.markers(pinned)] == [approved["pin"]]
    assert write_pattern(baseline, compile_cir(baseline)) != write_pattern(
        pinned, compile_cir(pinned))
    # A different family must receive no pin even though the rule is active.
    wrong_family = dataclasses.replace(baseline, construction="flat_rows")
    unchanged, records = KG.freeze_applicable(db, wrong_family)
    assert records == [] and not KG.has_pins(unchanged)
    try:
        DK.freeze_pins(db, wrong_family, [approved["pin"]])
    except DK.DesignKnowledgeRefused:
        pass
    else:
        raise AssertionError("a joined-round pin was attached to a flat design")


def test_revision_freezes_current_rule_and_refuses_a_retired_pin():
    from brambleloop.cir.compiler import compile_cir
    from brambleloop.runtime import engineering_ops  # noqa: F401
    db, path = _store()
    approved = _approved_rule(db, scope="flat_rows")
    broken = pipeline.concept_to_cir(pipeline.Concept(
        slug="revision-fixture", title="Revision Fixture", category="runner",
        stitch_repeat=[("sc", 3), ("dc", 1)], width_stitches=10, rows=4,
        colors={"a": "#ffffff"}, source_provenance="fixture:original-design"))
    assert not compile_cir(broken).ok
    status, result, error = _run(db, path, "cir.revise", {"cir": broken.to_dict()},
                                 "crochet_engineer")
    assert status == JobStatus.DONE and result.get("revised"), (result, error)
    with db.session() as session:
        job = session.scalars(select(Job).where(Job.job_type == "cir.compile")
                              .order_by(Job.id.desc())).first()
        revised = CIR.from_dict(job.inputs["cir"])
    assert [entry["pin"] for entry in K.markers(revised)] == [approved["pin"]]
    assert compile_cir(revised).ok
    stale_broken = DK.freeze_pins(db, broken, [approved["pin"]])
    DK.review_rule(db, approved["rule_id"] if "rule_id" in approved else approved["id"],
                   reviewer="owner", decision="retire", reason="fixture retirement")
    status, result, error = _run(db, path, "cir.revise", {"cir": stale_broken.to_dict()},
                                 "crochet_engineer")
    assert status == JobStatus.DONE and result.get("refused") == "design_knowledge", (
        result, error)


def test_legacy_approved_construction_preference_cannot_bypass_design_evaluation():
    import test_w5_a6_learning_to_design as old
    from brambleloop.improve import consume
    from brambleloop.creative.prospecting import ENGINE_ROUTE
    db = old.D._db()
    concept = old._winner(db)
    wanted = old._other_construction(concept)
    lesson_id = old._lesson(db, concept)
    consume.approve_for_design(db, lesson_id, parameter="construction", value=wanted,
                               approved_by="owner", why="legacy tests favour this construction for the form")
    out, cir = old._draft(db)
    assert cir.construction == ENGINE_ROUTE[concept["construction"]], out
    assert out["learning"]["design_changes_held"] is True
    assert not old.D._rows(db, consume.DESIGN_APPLIED)


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
