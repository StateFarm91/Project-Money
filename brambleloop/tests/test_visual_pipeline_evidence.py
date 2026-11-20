"""ENG-VISUAL: the `visual_pipeline` section of /api/readback/evidence.

Proves, on seeded rows only:

1. every count comes from persisted rows (certified PDFs by terminology, image runs by state,
   blocked reasons grouped into a fixed vocabulary, image candidates by technical status,
   Laura identity checks run/passed/failed/not run, listing packages, Etsy drafts read back);
2. UNKNOWN is never 0: a missing table or an unreadable part reads "UNKNOWN";
3. a fixture-only identity reading is never counted as an identity check that ran;
4. no free text (blocked reasons, prompts) leaves the section;
5. the ops/readback.py row is advisory: WARN until a draft is read back in full, then PASS.

Run: cd brambleloop && PYTHONPATH=src:tests $PY tests/test_visual_pipeline_evidence.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # per-process temp sandbox, removed at exit
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT.parent / "ops"))
os.environ.pop("DATABASE_URL", None)
os.environ.pop("BRAMBLELOOP_REQUIRE_POSTGRES", None)

from sqlalchemy import text  # noqa: E402

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (  # noqa: E402
    AuditLog, Job, JobStatus, OperatingReading, PatternVersion, Product)
from brambleloop.ops import production_evidence as pe  # noqa: E402
from brambleloop.visual.image_records import ImageCandidate, ImageProductionRun  # noqa: E402

NOW = datetime(2026, 11, 19, 12, 0, tzinfo=timezone.utc)
SECRET_REASON = "VISUAL-PRIVATE-REASON-identity drift on the nose bridge"
SECRET_PROMPT = "VISUAL-PRIVATE-PROMPT-laura in a meadow"


def _db() -> Database:
    d = Database(f"sqlite:///{tempfile.mkdtemp(prefix='vp_')}/v.db")
    d.create_all()
    return d


def _release(d, slug, version, release, terminologies=("US", "UK")):
    with d.session() as s:
        p = Product(slug=slug, title=slug, status="certified")
        s.add(p)
        s.flush()
        s.add(PatternVersion(product_id=p.id, version=version, cir_json={},
                             release_hash=release, certified=True))
        if terminologies:
            j = Job(agent="assets", job_type="assets.build", status=JobStatus.DONE,
                    inputs={"slug": slug, "version": version, "release": release},
                    outputs={"release": release, "pdf_sha256_by_terminology":
                             {t: t.lower() * 32 for t in terminologies}})
            s.add(j)
            s.flush()
            s.add(AuditLog(actor="assets", action="assets.built", artifact=f"{slug}@{version}",
                           job_id=j.id, detail={}))


def _run(d, slug, status, stage="", reason="", exhausted=False):
    with d.session() as s:
        s.add(ImageProductionRun(run_key=f"{slug}@v1@r", slug=slug, version="v1",
                                 status=status, stage=stage, blocked_reason=reason,
                                 attempts_exhausted=exhausted))


def _cand(d, sha, status, *, laura=False, identity=None, outcome="unverified"):
    checks = {} if identity is None else {"identity": identity}
    with d.session() as s:
        s.add(ImageCandidate(sha256=sha, method="autonomous", provenance_kind="generated",
                             slug="alpha-wrap", technical_status=status, outcome=outcome,
                             laura_present=laura, checks=checks, prompt=SECRET_PROMPT))


def test_an_empty_database_counts_zero_rows_and_says_identity_is_not_qualified():
    d = _db()
    vp = pe.visual_pipeline(d, now=NOW)
    assert vp["readable"] is True
    assert vp["certified_pdfs"]["certified_releases"] == 0
    assert vp["galleries"]["valid"] == 0 and vp["galleries"]["blocked"] == 0
    assert vp["images"]["candidates"] == 0
    assert vp["laura_identity_checks"]["run"] == 0
    assert vp["listing_packages"]["listing_ready"] == 0
    assert vp["etsy_drafts"]["drafts"] == 0
    # No producer for recovered images on this build: UNKNOWN, never 0.
    assert vp["recovered_images"]["count"] == "UNKNOWN", vp["recovered_images"]
    m = vp["laura_identity_method"]
    assert m["production_qualified"] is False
    assert m["canonical_references_expected"] == 3, m
    assert m["identity_id"] == "laura-r2-a42aeac7", m
    assert vp["gallery_standard_frames"] == 7


def test_missing_image_tables_are_unknown_never_zero():
    d = _db()
    with d.engine.begin() as c:
        c.execute(text("DROP TABLE image_candidates"))
        c.execute(text("DROP TABLE image_production_runs"))
    vp = pe.visual_pipeline(d, now=NOW)
    for k in ("galleries", "images", "laura_identity_checks"):
        assert vp[k]["readable"] is False and vp[k]["count"] == "UNKNOWN", (k, vp[k])
    import readback

    verdict, why = readback._judge_section("visual_pipeline", vp, None)
    assert verdict == readback.WARN
    assert "galleries valid UNKNOWN" in why and "identity run UNKNOWN" in why, why
    assert "valid 0" not in why


def test_an_unreadable_part_is_unknown_and_the_rest_still_reads():
    d = _db()
    saved = pe._vp_packages
    pe._vp_packages = lambda _db: (_ for _ in ()).throw(RuntimeError("boom"))
    try:
        vp = pe.visual_pipeline(d, now=NOW)
    finally:
        pe._vp_packages = saved
    assert vp["listing_packages"] == {"readable": False, "count": "UNKNOWN",
                                      "error_class": "RuntimeError"}
    assert vp["certified_pdfs"]["certified_releases"] == 0


def test_counts_come_from_rows_and_carry_no_free_text():
    d = _db()
    _release(d, "alpha-wrap", "v1", "a" * 64)
    _release(d, "beta-shawl", "v1", "b" * 64, terminologies=("US",))
    _release(d, "gamma-cowl", "v1", "c" * 64, terminologies=())
    _run(d, "alpha-wrap", "ready_for_owner_review", stage="owner_card")
    _run(d, "beta-shawl", "blocked", stage="verification", reason=SECRET_REASON,
         exhausted=True)
    _run(d, "gamma-cowl", "blocked", stage="product_generation",
         reason="budget exceeded for image_generation")
    _cand(d, "1" * 64, "PASS", laura=True, outcome="accepted",
          identity={"status": "PASS", "biometric": {"status": "PASS"}})
    _cand(d, "2" * 64, "FAIL", laura=True, outcome="rejected", identity={"status": "FAIL"})
    _cand(d, "3" * 64, "UNKNOWN", laura=True, identity={"status": "UNKNOWN"})
    _cand(d, "4" * 64, "UNKNOWN", laura=True,
          identity={"status": "PASS", "fixture_only": True})
    _cand(d, "5" * 64, "UNKNOWN", laura=True)
    _cand(d, "6" * 64, "PASS", outcome="accepted")
    with d.session() as s:
        s.add(OperatingReading(kind="listing.package", period_key="alpha-wrap@v1",
                               payload={"state": "ready_for_owner_review"}))
        s.add(OperatingReading(kind="listing.package", period_key="beta-shawl@v1",
                               payload={"state": "blocked", "blockers": [
                                   {"source": "listing_images", "reason": SECRET_REASON}]}))
        full = {"etsy_listing_id": "111", "images_uploaded": 7,
                "files_attached_by_terminology": {"US": True, "UK": True},
                "read_back": {"verified": True, "files": {"verified": True},
                              "images": {"verified": True}}}
        part = {"etsy_listing_id": "222", "images_uploaded": 7,
                "files_attached_by_terminology": {"US": True, "UK": False},
                "read_back": {"verified": False, "files": {"verified": False},
                              "images": {"verified": True}}}
        s.add(AuditLog(actor="store", action="store.publish_incomplete",
                       artifact="beta-shawl@v1", detail=part))
        s.add(AuditLog(actor="store", action="store.publish_incomplete",
                       artifact="alpha-wrap@v1", detail=part))
        # newer and complete: the newest row per release wins
        s.add(AuditLog(actor="store", action="store.published",
                       artifact="alpha-wrap@v1", detail=full))
    vp = pe.visual_pipeline(d, now=NOW)
    pdf = vp["certified_pdfs"]
    assert (pdf["certified_releases"], pdf["with_us_and_uk_pdf_hashes"], pdf["us_only"],
            pdf["no_certified_pdf"]) == (3, 1, 1, 1), pdf
    assert sorted(pdf["releases_missing_a_pdf"]) == ["beta-shawl@v1", "gamma-cowl@v1"]
    g = vp["galleries"]
    assert (g["valid"], g["blocked"]) == (1, 2), g
    assert g["blocked_reasons_grouped"] == {"product_generation:budget": 1,
                                            "verification:identity:exhausted": 1}, g
    im = vp["images"]
    assert (im["candidates"], im["verified"], im["failed"], im["unmeasurable"]) == (6, 2, 1, 3)
    idn = vp["laura_identity_checks"]
    assert idn == {"laura_frames": 5, "run": 3, "passed": 1, "failed": 1, "not_run": 2,
                   "unknown": 1, "fixture_only": 1, "biometric_measured": 1}, idn
    pk = vp["listing_packages"]
    assert (pk["listing_ready"], pk["blocked"]) == (1, 1)
    assert pk["blocker_sources"] == {"listing_images": 1}
    dr = vp["etsy_drafts"]
    assert dr["drafts"] == 2 and dr["fully_read_back"] == 1, dr
    by = {r["release"]: r for r in dr["releases"]}
    assert by["alpha-wrap@v1"]["pdfs_attached"] == ["UK", "US"]
    assert by["beta-shawl@v1"]["files_read_back_verified"] is False
    dumped = json.dumps(vp)
    assert "VISUAL-PRIVATE" not in dumped and "111" not in dumped, dumped
    import readback

    verdict, why = readback._judge_section("visual_pipeline", {**vp}, None)
    assert verdict == readback.PASS, why
    assert "fully read back 1" in why and "certified PDFs US+UK 1/3" in why, why


def test_the_section_is_served_on_the_evidence_body():
    d = _db()
    body = pe.evidence(d, now=NOW)
    assert "visual_pipeline" in body and body["visual_pipeline"]["readable"] is True


def test_block_family_vocabulary_is_fixed():
    assert pe.block_family("") == "unrecorded"
    assert pe.block_family("something nobody anticipated") == "other"
    assert pe.block_family("Motif fidelity FAIL") == "product_truth"
    fams = {f for f, _n in pe.BLOCK_FAMILIES} | {"other", "unrecorded"}
    assert all(f.isidentifier() for f in fams)


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, repr(e)[:3000])
    sys.exit(1 if fails else 0)
