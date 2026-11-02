"""OPUS2 P0-PHOTO-ASSET-REVIEW: an attested sample photo frame is reviewed by code and approved.

`physical_upgrade` puts an attested sample photograph first and leaves its frame unapproved,
"awaiting asset-truth review and listing-set re-certification"; no production path ever did
that review, so a photo-led listing set could never certify. `publish.photo_asset_review`
does it deterministically (no model): the attestation binds this release, the hashes match the
attested sample, the frame order is valid, and the frame claims nothing a photo does not
establish. Every check must pass; anything unknown is a refusal; a render is never approved
as a photo. These run the real intake, attestation, upgrade planner, the real job through the
worker, and the real listing-set certificate step (fixtures from test_physfix_photo_first).

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_opus2_photo_asset_review.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from sqlalchemy import select  # noqa: E402

import test_physfix_photo_first as T  # noqa: E402
from brambleloop.core.models import AuditLog, Job, ListingAsset  # noqa: E402
from brambleloop.publish import eligibility as el  # noqa: E402
from brambleloop.publish import photo_asset_review as par  # noqa: E402
from brambleloop.publish import release_gates, sample_photo  # noqa: E402


def _run(db, agent: str, job_type: str, inputs: dict) -> Job:
    from brambleloop.queue.durable import JobQueue
    from brambleloop.runtime.worker import Worker

    job = JobQueue(db).enqueue(agent, job_type, inputs, priority=0)
    Worker(db, f"w-{job_type}", job_types=[job_type]).run_once()
    with db.session() as s:
        row = s.get(Job, job.id)
        s.expunge(row)
        return row


def _setup(*, attest=True, unedited=True, full_make=True):
    db = T._db()
    cir, release = T._certified_basket(db)
    T._render_gallery(db, cir)
    test_id = T._passed_full_make(db, cir) if full_make else None
    plan = T._upgrade(db, cir, test_id, attest=attest, unedited=unedited)
    return db, cir, release, plan


def _photo_frame(db, cir):
    with db.session() as s:
        f = s.scalar(select(ListingAsset).where(
            ListingAsset.product_slug == cir.slug,
            ListingAsset.asset_class == par.PHOTO_CLASS))
        return f.id


def _certify_without_touching_approval(db, cir, release):
    """The certificate step on the frames exactly as stored (no hand approval)."""
    with db.session() as s:
        frames = sorted(s.scalars(select(ListingAsset).where(
            ListingAsset.product_slug == cir.slug, ListingAsset.version == cir.version)),
            key=lambda f: f.position)
        for f in frames:
            s.expunge(f)
    per_frame = [{"position": f.position, "sha256": f.sha256, "role": f.role,
                  "gates": {g: {"outcome": el.PASSED} for g in el.GATES}} for f in frames]
    return frames, release_gates.certificate_step(
        db, slug=cir.slug, version=cir.version, release_hash=release, frames=frames,
        per_frame=per_frame, geometry={"width_cm": 16.0, "height_cm": 8.7},
        claims={"title": cir.title}, issue=True)


def test_the_upgrade_job_queues_the_review_and_the_job_approves_the_attested_photo():
    db = T._db()
    cir, release = T._certified_basket(db)
    T._render_gallery(db, cir)
    test_id = T._passed_full_make(db, cir)
    from brambleloop.core.artifacts import ArtifactStore
    from brambleloop.publish import physical_upgrade as pu

    sha = ArtifactStore().put("sample.jpg", b"unedited camera file", "image/jpeg").sha256
    rec = pu.intake(db, slug=cir.slug, version=cir.version, source="tester", sha256=sha,
                    rights_basis="tester_agreement", taken_by="tester-1",
                    physical_test_id=test_id, unedited=True)
    pu.attest_unedited(db, rec["photo_id"], actor=T.OWNER, confirm=pu.UNEDITED_CONFIRMATION)
    up = _run(db, "publishing", "assets.physical_upgrade", {"photo_id": rec["photo_id"]})
    assert up.last_error is None, up.last_error
    with db.session() as s:
        queued = [j for j in s.scalars(select(Job).where(Job.job_type == "assets.photo_review"))]
    assert len(queued) == 1, queued
    fid = _photo_frame(db, cir)
    with db.session() as s:
        assert s.get(ListingAsset, fid).approved is False      # until the review runs
    job = _run(db, "asset_truth", "assets.photo_review", {})
    assert job.last_error is None, job.last_error
    with db.session() as s:
        frame = s.get(ListingAsset, fid)
        assert frame.approved is True and frame.blocked_reasons == [], frame.blocked_reasons
        audit = s.scalar(select(AuditLog).where(AuditLog.action == par.ACTION))
        assert audit is not None and audit.detail["approved"] is True
        assert all(audit.detail["checks"][c] is True for c in par.CHECKS), audit.detail
    # The certificate now issues on the frames as stored, and the gate accepts the photo.
    _frames, cert = _certify_without_touching_approval(db, cir, release)
    assert cert["valid"] and cert["issued"], cert
    req = sample_photo.requirement(db, cir.slug, cir.version)
    assert req["satisfied"] is True and req["first_frame"]["sha256"] == sha, req


def test_the_awaiting_reason_is_a_failing_gate_reading_until_the_review_clears_it():
    """Why a photo-led set never certified: the awaiting reason is read by the listing-set
    gates as a failure (release_gates._classify), and nothing cleared it."""
    db, cir, _release, _plan = _setup()
    fid = _photo_frame(db, cir)
    assert release_gates._classify(par.AWAITING) in el.GATES
    with db.session() as s:
        assert par.AWAITING in s.get(ListingAsset, fid).blocked_reasons
    assert fid in par.awaiting_frames(db)
    out = par.review_frame(db, fid, reissue=False)
    assert out["approved"] is True and out["frame_approved"] is True, out
    with db.session() as s:
        frame = s.get(ListingAsset, fid)
        assert frame.approved is True and frame.blocked_reasons == []
    assert par.awaiting_frames(db) == []


def test_every_check_fails_closed():
    cases = []
    # 1. Not owner-attested: it does not qualify (and is not first).
    db, cir, _r, _p = _setup(attest=False)
    cases.append(("not attested", db, _photo_frame(db, cir),
                  {"attestation_binds_release", "frame_order_valid"}))
    # 2. No passed full make behind it.
    db, cir, _r, _p = _setup(full_make=False)
    cases.append(("no full make", db, _photo_frame(db, cir), {"attestation_binds_release"}))
    # 3. The frame's bytes were swapped for a render's.
    db, cir, _r, _p = _setup()
    fid = _photo_frame(db, cir)
    with db.session() as s:
        render = s.scalar(select(ListingAsset).where(ListingAsset.product_slug == cir.slug,
                                                     ListingAsset.position == 2))
        s.get(ListingAsset, fid).sha256 = render.sha256
    cases.append(("swapped hash", db, fid, {"hash_matches_attested_sample"}))
    # 4. A size claim a photo does not establish.
    db, cir, _r, _p = _setup()
    fid = _photo_frame(db, cir)
    with db.session() as s:
        f = s.get(ListingAsset, fid)
        f.claims = {**f.claims, "width_cm": 16.0}
    cases.append(("size claim", db, fid, {"no_disclosure_free_claim"}))
    # 5. Moved off position 1.
    db, cir, _r, _p = _setup()
    fid = _photo_frame(db, cir)
    with db.session() as s:
        frames = sorted(s.scalars(select(ListingAsset).where(
            ListingAsset.product_slug == cir.slug)), key=lambda f: f.position)
        from brambleloop.publish.physical_upgrade import _renumber
        _renumber(s, frames[1:2] + frames[:1] + frames[2:])
    cases.append(("not first", db, fid, {"frame_order_valid"}))
    assert len(cases) == 5
    for name, db, fid, expected in cases:
        out = par.review_frame(db, fid)
        assert out["approved"] is False, (name, out)
        assert expected <= set(out["failed"]), (name, out["failed"])
        with db.session() as s:
            frame = s.get(ListingAsset, fid)
            assert frame.approved is False and par.AWAITING in frame.blocked_reasons, name
            assert s.scalar(select(AuditLog).where(AuditLog.action == par.ACTION)) is not None


def test_a_render_is_never_approved_as_a_photo_and_unknown_is_a_refusal():
    db, cir, _r, _p = _setup()
    with db.session() as s:
        render = s.scalar(select(ListingAsset).where(ListingAsset.product_slug == cir.slug,
                                                     ListingAsset.position == 2))
        rid = render.id
    out = par.review_frame(db, rid)
    assert out["approved"] is False and set(out["failed"]) == set(par.CHECKS), out
    # A render relabelled as a photo frame is still made, not taken.
    with db.session() as s:
        r = s.get(ListingAsset, rid)
        r.asset_class, r.claims = par.PHOTO_CLASS, {"provenance": "camera",
                                                    "physical_photo_id": _p["photo_id"]}
    out = par.review_frame(db, rid)
    # Its bytes are the render's, never the attested sample's, so it is refused.
    assert out["approved"] is False and "hash_matches_attested_sample" in out["failed"], out
    # An unreadable gate approves nothing.
    fid = _photo_frame(db, cir)
    saved = sample_photo.qualifying_photos
    sample_photo.qualifying_photos = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("db"))
    try:
        out = par.review_frame(db, fid)
    finally:
        sample_photo.qualifying_photos = saved
    assert out["approved"] is False and all(str(out["checks"][c]).startswith("UNKNOWN")
                                            for c in par.CHECKS), out


def test_another_recorded_reason_keeps_the_frame_blocked():
    db, cir, _r, _p = _setup()
    fid = _photo_frame(db, cir)
    with db.session() as s:
        f = s.get(ListingAsset, fid)
        f.blocked_reasons = [par.AWAITING, "owner veto (#228): not this photo"]
    out = par.review_frame(db, fid, reissue=False)
    assert out["approved"] is True and out["frame_approved"] is False, out
    with db.session() as s:
        f = s.get(ListingAsset, fid)
        assert f.approved is False and f.blocked_reasons == ["owner veto (#228): not this photo"]
    # And the sweep no longer finds it awaiting.
    assert fid not in par.awaiting_frames(db)


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"OK   {name}")
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print(f"FAIL {name} {exc!r}"[:400])
                import traceback
                traceback.print_exc()
    print(f"{failed} failed")
    sys.exit(1 if failed else 0)
