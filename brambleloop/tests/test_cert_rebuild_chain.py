"""C-69: the rebuild honours what the dependency graph asked for, and proves it was done.

#171: twin, geometry proof, reverse result, support knowledge and release bundle are recorded
by the chain that makes them. #172: `chain.rebuild` reads the artefacts, fingerprints and
reason on its job, enqueues the earliest stage that remakes exactly those, records the
request per artefact, and comes back to write completion evidence per artefact. #163: a
withheld release is never re-driven. #40: the terms are checked on the produced PDF, listing
and FAQ. Everything runs through `Worker.run_once` on the real chain.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

_TMP = tempfile.mkdtemp(prefix="cert_rebuild_chain_")
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (  # noqa: E402
    ArtefactProvenance, AuditLog, Job, JobStatus, Listing, PatternVersion, Phase, Product,
    utcnow,
)
from brambleloop.products import nordic_forest as nf  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: E402,F401 - registers handlers
from brambleloop.runtime.worker import Worker  # noqa: E402

_STATE: dict = {}


def _drain(db, name="rebuild-chain", limit=500):
    w = Worker(db, name, phase=Phase.SHADOW, lease_seconds=900)
    for _ in range(limit):
        if not w.run_once():
            break


def chain() -> dict:
    if _STATE:
        return _STATE
    db = Database(f"sqlite:///{_TMP}/chain.db")
    db.create_all()
    Registry(db).seed_defaults()
    cir = nf.build()
    JobQueue(db).enqueue("validator", "cir.compile", {"cir": cir.to_dict()},
                         idempotency_key="rb-compile")
    _drain(db)
    _STATE.update(db=db, cir=cir, slug=cir.slug, version=cir.version)
    return _STATE


def _rows(db, slug, cls):
    with db.session() as s:
        return [(r.artefact_key, dict(r.inputs or {}), r.job_id, list(r.parents or []))
                for r in s.scalars(select(ArtefactProvenance).where(
                    ArtefactProvenance.product_slug == slug,
                    ArtefactProvenance.artefact_class == cls))]


def _audits(db, action, artifact_prefix=""):
    with db.session() as s:
        return [(r.artifact, dict(r.detail or {})) for r in s.scalars(
            select(AuditLog).where(AuditLog.action == action).order_by(AuditLog.id))
            if (r.artifact or "").startswith(artifact_prefix)]


def _run(db, agent, job_type, inputs, key):
    job = JobQueue(db).enqueue(agent, job_type, inputs, priority=0, idempotency_key=key)
    Worker(db, f"rb-{key}", phase=Phase.SHADOW, job_types=[job_type]).run_once()
    with db.session() as s:
        row = s.get(Job, job.id)
        s.expunge(row)
        return row


def test_the_chain_records_twin_reverse_support_knowledge_and_release_bundle():
    st = chain()
    db, slug = st["db"], st["slug"]
    key = f"{slug}@{st['version']}"
    assert _rows(db, slug, "twin"), "no twin provenance"
    assert _rows(db, slug, "reverse_result"), "no reverse_result provenance"
    cert = _rows(db, slug, "certificate")
    assert cert and any(p.startswith("twin:") for p in cert[0][3]), cert
    support = _rows(db, slug, "support_knowledge")
    assert support and support[0][0] == f"{key}#support"
    bundle = _rows(db, slug, "release_bundle")
    assert bundle and bundle[0][0] == f"{key}#bundle"
    assert any(p.startswith("support_knowledge:") for p in bundle[0][3]), bundle[0][3]
    assert any(p.startswith("pdf:") for p in bundle[0][3])


def test_a_shaped_design_records_its_geometry_proof():
    from tests.fixtures import good_sphere

    db = Database(f"sqlite:///{tempfile.mkdtemp()}/geo.db")
    db.create_all()
    Registry(db).seed_defaults()
    cir = good_sphere()
    job = _run(db, "quality_director", "gate.certify", {"cir": cir.to_dict()}, "geo-cert")
    assert job.status == JobStatus.DONE, job.last_error
    assert job.outputs["granted"], job.outputs
    rows = _rows(db, cir.slug, "geometry_proof")
    assert rows and rows[0][0] == f"{cir.slug}@{cir.version}#geometry_proof", rows
    assert f"cir:{cir.slug}" in rows[0][1]


def test_terms_are_checked_on_the_produced_pdf_listing_and_faq():
    st = chain()
    built = _audits(st["db"], "support.knowledge_built", st["slug"])
    assert built, "no support knowledge was built"
    detail = built[-1][1]
    assert detail["pdf"] == "measured", detail
    assert detail["consistent"] is True, detail["divergences"]


def test_launch_readiness_measures_the_launch_package_from_what_the_chain_produced():
    """#54 (C-69): digital disclosure, support knowledge, FAQ, pricing plan, launch calendar,
    analytics baseline and rollback plan, each read per listing -- none of them a constant."""
    from brambleloop.core.models import OperatingReading

    st = chain()
    db = st["db"]

    from brambleloop.launch.readiness import assess

    by = {r.key: r for r in assess(db, phase="shadow").requirements}
    for key in ("digital_disclosure", "support_knowledge", "faq", "pricing_promotion_plan",
                "launch_calendar"):
        assert by[key].ready is True, (key, by[key].evidence)
    # nothing recorded a baseline reading or proved a restore: honestly not ready
    assert by["analytics_baseline"].ready is False
    assert by["rollback_plan"].ready is False
    assert "continuity restore unproven" in str(by["rollback_plan"].evidence) or \
        by["rollback_plan"].evidence["last_restore_proof"] is None
    with db.session() as s:
        s.add(OperatingReading(kind="growth.weekly", period_key="2026-W39", payload={}))
        s.add(AuditLog(actor="orchestrator", action="continuity.verified", detail={}))
    by = {r.key: r for r in assess(db, phase="shadow").requirements}
    assert by["analytics_baseline"].ready is True, by["analytics_baseline"].evidence
    assert by["rollback_plan"].ready is True, by["rollback_plan"].evidence
    job = _run(db, "orchestrator", "launch.readiness", {}, "readiness-1")
    assert job.status == JobStatus.DONE, job.last_error


def test_the_moat_is_inventoried_from_evidence_and_recognisability_is_measured():
    """#44 (C-69): existence read from what the chain produced, not hand-set flags."""
    from brambleloop.brand import moat
    from brambleloop.launch.readiness import assess

    st = chain()
    inv = moat.inventory(st["db"])
    assert inv["measured_from_evidence"] is True
    for key in ("deterministic_validation", "version_aware_support", "editorial_layout",
                "chart_style", "naming_architecture"):
        assert key in inv["built"], (key, inv["built"])
    assert "canonical_model" in inv["planned"] and "measured_yardage" in inv["planned"]
    rec = inv["recognisable_without_model"]
    assert st["slug"] in rec["recognisable"], rec
    by = {r.key: r for r in assess(st["db"], phase="shadow").requirements}
    assert by["brand_moat"].ready is True, by["brand_moat"].evidence


def test_a_divergent_listing_is_refused_and_halts_publication():
    from brambleloop.core.models import Incident
    from brambleloop.runtime import release

    st = chain()
    db, slug, version = st["db"], st["slug"], st["version"]
    q = JobQueue(db)
    from brambleloop.runtime.worker import JobContext

    with db.session() as s:
        built = next(dict(j.outputs) for j in s.scalars(select(Job).where(
            Job.job_type == "assets.build", Job.status == JobStatus.DONE)
            .order_by(Job.id.desc())) if (j.outputs or {}).get("pdf_sha256"))
    ctx = JobContext(job=q.enqueue("listing", "listing.seo", {}), db=db, queue=q,
                     registry=Registry(db), phase=Phase.SHADOW)
    from brambleloop.cir.compiler import compile_cir
    from brambleloop.cir.twin import build_twin

    cir = st["cir"]
    twin = build_twin(cir, compile_cir(cir))
    out = release._support_knowledge(ctx, slug, version, built, cir=cir, twin=twin,
                                     listing_text="A pattern. Redistribution is fine.")
    assert out["divergent"] is True
    with db.session() as s:
        inc = s.scalar(select(Incident).where(
            Incident.signature == f"{release.TERMS_DIVERGENCE_SIGNATURE}:{slug}"))
        assert inc is not None and inc.halts_publication
        inc.resolved = True          # leave the shared chain clean for the other tests


def test_a_targeted_rebuild_remakes_exactly_the_stale_marketing_and_proves_it():
    st = chain()
    db, slug = st["db"], st["slug"]
    marketing = _rows(db, slug, "marketing_asset")
    assert marketing, "the chain drafted no content"
    target = marketing[0][0]
    with db.session() as s:
        row = s.scalar(select(ArtefactProvenance).where(
            ArtefactProvenance.artefact_class == "marketing_asset",
            ArtefactProvenance.artefact_key == target))
        inputs = dict(row.inputs)
        old = inputs[f"cir:{slug}"]
        inputs[f"cir:{slug}"] = "0" * 16
        row.inputs = inputs
    node = f"marketing_asset:{target}"
    job = _run(db, "listing", "chain.rebuild",
               {"product_slug": slug, "artefacts": [node], "reason": "test: design moved",
                "fingerprints": {f"cir:{slug}": {"old": "0" * 16, "new": old}}},
               "targeted-marketing")
    assert job.status == JobStatus.DONE, job.last_error
    out = job.outputs
    assert out["targeted"] and out["requested"] == [node], out
    assert out["stage"] == "pricing.position", "marketing is remade from pricing, not recertified"
    requested = _audits(db, "chain.rebuild_requested", node)
    assert requested and requested[-1][1]["reason"] == "test: design moved"
    assert requested[-1][1]["fingerprints"][f"cir:{slug}"]["old"] == "0" * 16
    with db.session() as s:
        stage = s.get(Job, out["stage_job"])
        assert stage.job_type == "pricing.position" and stage.inputs["rebuild"]
        verify = s.scalar(select(Job).where(
            Job.job_type == "chain.rebuild",
            Job.idempotency_key == f"rebuild-verify:{slug}:{job.id}:1"))
        assert verify is not None and verify.inputs["verify"] == 1
        verify_id = verify.id
    _drain(db, "rebuild-drain")                # the stage chain runs; the check waits
    with db.session() as s:
        s.get(Job, verify_id).run_after = utcnow()     # the delay, elapsed
    _drain(db, "rebuild-verify")
    completed = _audits(db, "chain.rebuild_completed", node)
    assert completed, "no completion evidence was written for the rebuilt artefact"
    evidence = completed[-1][1]["evidence"]
    assert evidence["inputs"][f"cir:{slug}"] == old and evidence["job_id"] != marketing[0][2]


def test_a_stale_pdf_restarts_at_assets_build_not_at_certification():
    st = chain()
    db, slug = st["db"], st["slug"]
    pdf = _rows(db, slug, "pdf")[0][0]
    with db.session() as s:
        row = s.scalar(select(ArtefactProvenance).where(
            ArtefactProvenance.artefact_class == "pdf", ArtefactProvenance.artefact_key == pdf))
        saved = dict(row.inputs)
        row.inputs = {**saved, f"cir:{slug}": "0" * 16}
    job = _run(db, "listing", "chain.rebuild",
               {"product_slug": slug, "artefacts": [f"pdf:{pdf}", f"seo:{slug}@x"],
                "reason": "test", "fingerprints": {}}, "targeted-pdf")
    assert job.outputs["stage"] == "assets.build", job.outputs
    assert f"pdf:{pdf}" in job.outputs["requested"]
    with db.session() as s:
        s.scalar(select(ArtefactProvenance).where(
            ArtefactProvenance.artefact_class == "pdf",
            ArtefactProvenance.artefact_key == pdf)).inputs = saved
        for j in s.scalars(select(Job).where(Job.status == JobStatus.PENDING)):
            j.status = JobStatus.CANCELLED


def test_a_withheld_release_is_never_redriven():
    st = chain()
    db, slug, version = st["db"], st["slug"], st["version"]
    with db.session() as s:
        product = s.scalar(select(Product).where(Product.slug == slug))
        pv = s.scalar(select(PatternVersion).where(PatternVersion.product_id == product.id))
        pv.certificate = {**dict(pv.certificate or {}), "withheld": "teardown QA (#163): test"}
        for listing in s.scalars(select(Listing).where(Listing.product_slug == slug)):
            listing.chain_version = "old"            # stale, so the hourly rebuild would act
    try:
        hourly = _run(db, "listing", "chain.rebuild", {}, "hourly-withheld")
        assert f"{slug}@{version}" in hourly.outputs["withheld"], hourly.outputs
        assert not any(s.startswith(slug) for s in hourly.outputs["restarted"])
        targeted = _run(db, "listing", "chain.rebuild",
                        {"product_slug": slug, "artefacts": [f"seo:{slug}@{version}"],
                         "reason": "t"}, "targeted-withheld")
        assert targeted.outputs.get("withheld") is True
        draft = _run(db, "listing", "listing.draft", {"slug": slug, "version": version},
                     "draft-withheld")
        assert draft.outputs["drafted"] is False and draft.outputs["withheld"]
        # C-67 / M10: a pre-record mark is read as the teardown QA's reason on the release's
        # one withholding record, never dropped as unknown.
        with db.session() as s:
            product = s.scalar(select(Product).where(Product.slug == slug))
            pv = s.scalar(select(PatternVersion).where(PatternVersion.product_id == product.id))
            record = dict((pv.certificate or {}).get("withholding") or {})
        assert set(record) == {"teardown_qa"}, record
        assert record["teardown_qa"]["reason"] == "teardown QA (#163): test"
    finally:
        with db.session() as s:
            product = s.scalar(select(Product).where(Product.slug == slug))
            pv = s.scalar(select(PatternVersion).where(PatternVersion.product_id == product.id))
            cert = dict(pv.certificate or {})
            cert.pop("withheld", None)
            cert.pop("withholding", None)          # the record the mark migrated into
            pv.certificate = cert


if __name__ == "__main__":
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback
                traceback.print_exc()
                fails += 1
                print("FAIL", name, repr(e))
    print(f"\n{'PASS' if not fails else 'FAIL'}: {fails} failing")
    sys.exit(1 if fails else 0)
