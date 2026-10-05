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
from brambleloop.products import builder  # noqa: E402
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
    # Current Launch-0 construction; this suite tests lifecycle/provenance, not mosaic math.
    # The independent shaped fixture and synthetic recognisability judge remain unchanged.
    cir = builder.for_slug("cloudline-baby-blanket")
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
    # C-80 defect 10 (Codex P12): the search baseline is the coverage the listing stage
    # recorded at drafting (the chain wrote it), and traffic is honestly UNMEASURED -- no
    # weekly operating reading or seo_score stands in for either
    ab = by["analytics_baseline"]
    assert ab.ready is True and ab.evidence["releases_without_search_baseline"] == [], ab.evidence
    assert ab.evidence["traffic_baseline"].startswith("UNMEASURED"), ab.evidence
    # the rollback plan is a rehearsed withdrawal round trip, not a database restore proof
    assert by["rollback_plan"].ready is False
    assert by["rollback_plan"].evidence["unrehearsed"], by["rollback_plan"].evidence
    with db.session() as s:
        s.add(OperatingReading(kind="growth.weekly", period_key="2026-W39", payload={}))
        s.add(AuditLog(actor="orchestrator", action="continuity.verified", detail={}))
    by = {r.key: r for r in assess(db, phase="shadow").requirements}
    assert by["rollback_plan"].ready is False, "a restore proof is not a rehearsed withdrawal"

    # the daily assessment rehearses first: while the rehearsal fails, the package is not
    # ready and the requests that open live Etsy are withheld from the owner queue (#54)
    from brambleloop.core.models import OwnerAction
    from brambleloop.launch import rollback

    real = rollback.rehearse

    def failing(db_, *, slug, version, store=None, job_id=None):
        out = real(db_, slug=slug, version=version, store=store, job_id=job_id)
        with db.session() as s:
            row = [r for r in s.scalars(select(AuditLog).where(
                AuditLog.action == rollback.ACTION).order_by(AuditLog.id))][-1]
            row.detail = {**dict(row.detail), "ok": False,
                          "steps": [{**st, "ok": False} if st["step"] == "deliverables_restorable"
                                    else st for st in row.detail["steps"]]}
        return {**out, "ok": False}

    rollback.rehearse = failing
    try:
        job = _run(db, "orchestrator", "launch.readiness", {}, "readiness-1")
    finally:
        rollback.rehearse = real
    assert job.status == JobStatus.DONE, job.last_error
    assessed = _audits(db, "launch.assessed")[-1][1]
    assert "rollback_plan" in assessed["launch_package_blocked"], assessed
    assert set(assessed["owner_requests_withheld_until_package_ready"]) >= {"etsy_shop", "phase"}
    with db.session() as s:
        queued = {a.requirement_key for a in s.scalars(select(OwnerAction))}
    assert not ({"etsy_shop", "payout", "listing_fees", "phase"} & queued), queued
    by = {r.key: r for r in assess(db, phase="shadow").requirements}
    assert by["rollback_plan"].ready is False and by["rollback_plan"].evidence["rehearsal_failed"]

    # the real rehearsal passes on this chain (certificate retained, listing on record, every
    # PDF and frame on disk, state round trip). The chain holds one listing, so the package's
    # catalogue-depth item still withholds the asks; with the depth met, the asks go out.
    job = _run(db, "orchestrator", "launch.readiness", {}, "readiness-1b")
    assert job.status == JobStatus.DONE, job.last_error
    assessed = _audits(db, "launch.assessed")[-1][1]
    assert assessed["launch_package_blocked"] == ["catalogue_depth"], assessed
    assert "etsy_shop" in assessed["owner_requests_withheld_until_package_ready"]
    from brambleloop.launch import readiness as readiness_mod

    depth = readiness_mod.MIN_LISTINGS_TO_OPEN
    readiness_mod.MIN_LISTINGS_TO_OPEN = 1
    try:
        job = _run(db, "orchestrator", "launch.readiness", {}, "readiness-2")
    finally:
        readiness_mod.MIN_LISTINGS_TO_OPEN = depth
    assert job.status == JobStatus.DONE, job.last_error
    rehearsed = _audits(db, rollback.ACTION, f"{st['slug']}@")[-1][1]
    assert rehearsed["ok"] is True and rehearsed["dry_run"] is True, rehearsed
    assert [x["step"] for x in rehearsed["steps"]] == [
        "certificate_retained", "listing_on_record", "deliverables_restorable",
        "state_round_trip"]
    assert rehearsed["steps"][3]["transitions"][1] == "withdrawn"
    by = {r.key: r for r in assess(db, phase="shadow").requirements}
    assert by["rollback_plan"].ready is True, by["rollback_plan"].evidence
    assessed = _audits(db, "launch.assessed")[-1][1]
    assert assessed["launch_package_blocked"] == [], assessed
    assert assessed["owner_requests_withheld_until_package_ready"] == []
    with db.session() as s:
        queued = {a.requirement_key for a in s.scalars(select(OwnerAction))}
        listing = s.scalar(select(Listing).where(Listing.product_slug == st["slug"]))
        assert listing.state != "withdrawn", "the rehearsal was a dry run"
    assert "etsy_shop" in queued and "phase" in queued, queued


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
    # C-80 defect 15 (Codex P16): the count is labelled a proxy, and the real measurement --
    # blind identification of the hero frame -- is recorded UNMEASURED behind image_vision
    per = rec["per_listing"][st["slug"]]
    assert per["basis"].startswith("recognisability_proxy") and per["recognisable_by_proxy"]
    assert per["measured"]["status"] == "UNMEASURED"
    assert per["measured"]["gated_on"] == "image_vision"
    assert st["slug"] in rec["by_proxy_only"] and rec["measured"] == []
    by = {r.key: r for r in assess(st["db"], phase="shadow").requirements}
    assert by["brand_moat"].ready is True, by["brand_moat"].evidence
    assert by["brand_moat"].evidence["recognisability_measurement_gated_on"] == "image_vision"
    assert st["slug"] in by["brand_moat"].evidence["recognisability_by_proxy_only"]

    # with the gate open the measurement runs on the stored hero frame and decides
    from brambleloop.build2 import executor
    from brambleloop.visual import inspect as inspection

    gate = executor.GATE_BY_KEY["image_vision"]
    originals = (gate.check, inspection.inspect_image)

    def judge(colours):
        def fake(ref, *, db=None, provider=None, claim=None):
            description = {"object_shown": "a blanket", "chart_or_diagram": False,
                           "finished_or_in_progress": "finished", "object_count": "1",
                           "clarity": "clear", "text_present": False, "human_present": False,
                           "dominant_colours": colours, "third_party_marks": "none"}
            return {"described": True, "description": description, "realism": {},
                    "realism_unjudged": [], "semantic": inspection.compare(description, claim or {})}
        return fake

    gate.check = lambda db, env: True
    try:
        inspection.inspect_image = judge("deep pine green, cream and a little gold")
        measured = moat.measure_recognisability(st["db"], st["slug"])
        assert measured["status"] == "MEASURED" and measured["recognisable"] is True, measured
        assert set(measured["brand_colours_named"]) >= {"pine", "cream"}
        rec = moat.inventory(st["db"])["recognisable_without_model"]
        assert st["slug"] in rec["measured"] and rec["by_proxy_only"] == []
        assert rec["per_listing"][st["slug"]]["basis"].startswith("measured")

        inspection.inspect_image = judge("neon pink and electric blue")
        rec = moat.inventory(st["db"])["recognisable_without_model"]
        assert st["slug"] in rec["not_recognisable"], rec
        assert rec["per_listing"][st["slug"]]["recognisable_by_proxy"] is True, \
            "the proxy would have passed it; the measurement decides"
        by = {r.key: r for r in assess(st["db"], phase="shadow").requirements}
        assert by["brand_moat"].ready is False
    finally:
        gate.check, inspection.inspect_image = originals


def test_a_divergent_listing_is_refused_and_halts_publication():
    """C-80 defect 19: proved through `listing.seo` on the worker, not by calling the helper.
    The listing copy is made to omit the redistribution term the PDF and FAQ state; the job
    completes with ok=False, opens the halting incident and enqueues nothing downstream."""
    from brambleloop.commerce import terms
    from brambleloop.core.models import Incident
    from brambleloop.runtime import release

    st = chain()
    db, slug, version = st["db"], st["slug"], st["version"]
    with db.session() as s:
        seo_inputs = next(dict(j.inputs) for j in s.scalars(select(Job).where(
            Job.job_type == "listing.seo", Job.status == JobStatus.DONE)
            .order_by(Job.id.desc())))
        launch_before = len(list(s.scalars(select(Job).where(Job.job_type == "launch.plan"))))
    sentence = terms.BRAMBLELOOP_TERMS.sentence(terms.REDISTRIBUTION)
    real = release.seo_mod.build_description

    def divergent(*a, **k):
        text = real(*a, **k)
        assert sentence in text, "the fixture must diverge from a listing that carried the term"
        return text.replace(sentence, "Redistribution is fine.")

    release.seo_mod.build_description = divergent
    try:
        job = _run(db, "listing", "listing.seo", seo_inputs, "seo-divergent")
    finally:
        release.seo_mod.build_description = real
    assert job.status == JobStatus.DONE, job.last_error
    assert job.outputs["ok"] is False and "terms diverge" in job.outputs["blocking"][0]
    assert any(d["surface"] == "listing" and d["axis"] == terms.REDISTRIBUTION
               for d in job.outputs["terms"]["divergences"]), job.outputs["terms"]
    with db.session() as s:
        inc = s.scalar(select(Incident).where(
            Incident.signature == f"{release.TERMS_DIVERGENCE_SIGNATURE}:{slug}",
            Incident.resolved.is_(False)))
        assert inc is not None and inc.halts_publication
        launch_after = len(list(s.scalars(select(Job).where(Job.job_type == "launch.plan"))))
        assert launch_after == launch_before, "the divergent listing still queued its launch"
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
    # C-80 defect 11: the marketing gate exposes the exception as a structured flag
    from brambleloop.publish.release_gates import for_marketing

    gate = for_marketing(db, slug=slug, version=st["version"])
    assert gate["blocks"] and gate["staleness"]["outstanding_only_marketing"] is True, gate
    assert gate["only_own_marketing_stale"] is True
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
    # C-80 defect 12: completion is bound to this attempt -- the row was written by the
    # stage job (or later) and carries exactly fingerprints.new for the requested ref
    bound = completed[-1][1]["bound"]
    assert bound["bound"] is True and bound["fingerprints_match"] is True
    assert bound["stage_job"] == out["stage_job"] and bound["row_job"] >= out["stage_job"]
    # and the gate's flag clears once the marketing is remade
    assert for_marketing(db, slug=slug, version=st["version"])["staleness"][
        "outstanding_only_marketing"] is False


def test_completion_is_not_claimed_for_a_row_this_attempt_did_not_produce():
    """C-80 defect 12 (Codex P10): a row that reads FRESH is not completion evidence for an
    attempt whose stage job did not write it, nor when its inputs are not fingerprints.new."""
    st = chain()
    db, slug = st["db"], st["slug"]
    target, inputs, row_job, _parents = _rows(db, slug, "marketing_asset")[0]
    node = f"marketing_asset:{target}"
    current = inputs[f"cir:{slug}"]
    with db.session() as s:
        far_future_job = max(j.id for j in s.scalars(select(Job))) + 1000
    # a verify pass for an attempt whose stage job is later than the row's job: unbound
    job = _run(db, "listing", "chain.rebuild",
               {"product_slug": slug, "artefacts": [node], "reason": "test: not mine",
                "fingerprints": {f"cir:{slug}": {"old": "0" * 16, "new": current}},
                "verify": 1, "stage_job": far_future_job, "requested_by": far_future_job},
               "verify-unbound")
    assert job.status == JobStatus.DONE, job.last_error
    assert job.outputs["completed"] == [] and job.outputs["unbound"] == [node], job.outputs
    assert job.outputs["outstanding"] == [node]
    unbound = _audits(db, "chain.rebuild_unbound", node)
    assert unbound and unbound[-1][1]["bound"]["job_bound"] is False
    assert unbound[-1][1]["bound"]["row_job"] == row_job
    # a request whose fingerprints.new is not what the row carries is not already-fresh either
    job = _run(db, "listing", "chain.rebuild",
               {"product_slug": slug, "artefacts": [node], "reason": "test: wrong new",
                "fingerprints": {f"cir:{slug}": {"old": current, "new": "f" * 16}}},
               "request-wrong-new")
    assert job.outputs["already_fresh"] == [] and job.outputs["fresh_but_unbound"] == [node]
    with db.session() as s:
        for j in s.scalars(select(Job).where(Job.status == JobStatus.PENDING,
                                             Job.job_type == "chain.rebuild")):
            j.status = JobStatus.CANCELLED


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
