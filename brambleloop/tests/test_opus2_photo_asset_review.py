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
            assert frame.approved is False, name
            # I-A3-NONQUALIFYING-PHOTO: a photo that does not qualify is held by a terminal
            # named reason (and out of the set); any other failure stays awaiting review.
            if set(out["failed"]) & {"attestation_binds_release", "hash_matches_attested_sample"}:
                assert par.AWAITING not in frame.blocked_reasons, name
                assert any(r.startswith(par.NOT_QUALIFYING) for r in frame.blocked_reasons), name
            else:
                assert par.AWAITING in frame.blocked_reasons, name
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



def _second_attested_photo(db, cir, test_id, body=b"a second unedited camera file"):
    from brambleloop.core.artifacts import ArtifactStore
    from brambleloop.publish import physical_upgrade as pu

    sha = ArtifactStore().put("sample2.jpg", body, "image/jpeg").sha256
    rec = pu.intake(db, slug=cir.slug, version=cir.version, source="tester", sha256=sha,
                    rights_basis="tester_agreement", taken_by="tester-1",
                    physical_test_id=test_id, unedited=True)
    pu.attest_unedited(db, rec["photo_id"], actor=T.OWNER, confirm=pu.UNEDITED_CONFIRMATION)
    plan = pu.plan_upgrade(db, rec["photo_id"])
    assert plan["upgraded"], plan
    return sha


def test_review_opus2s_s1_a_withdrawn_frame_is_never_approved():
    """OPUS2S-1: a frame with approved=False and no reason has been withdrawn; the review
    approves only a frame still awaiting it, read under the write lock."""
    db, cir, _r, _p = _setup()
    fid = _photo_frame(db, cir)
    with db.session() as s:
        f = s.get(ListingAsset, fid)
        f.approved, f.blocked_reasons = False, []
    out = par.review_frame(db, fid, reissue=False)
    assert out["approved"] is False and out["failed"] == ["not awaiting asset-truth review"], out
    with db.session() as s:
        assert s.get(ListingAsset, fid).approved is False


def test_review_opus2w_w1_a_writer_cannot_commit_between_the_checks_and_the_write():
    """OPUS2W-1: the checks run inside the review's write lock. A concurrent writer that moves
    the frame and re-marks it while the checks run waits for the review to commit, so its
    change lands after the approval and is not overwritten by it; with the old unlocked read,
    the writer committed inside the window and the review approved the moved frame and cleared
    the writer's reasons."""
    import threading

    db, cir, _r, _p = _setup()
    fid = _photo_frame(db, cir)
    real = par._checks
    done = {}

    def writer():
        with db.session() as s:
            f = s.get(ListingAsset, fid)
            f.position = 999
            f.blocked_reasons = [par.AWAITING, "re-marked by a concurrent upgrade"]
        done["at"] = True

    def racing(db_, frame_id):
        t = threading.Thread(target=writer)
        t.start()
        t.join(timeout=0.5)                 # the writer is held by the review's lock
        done["waited"] = t.is_alive()
        done["thread"] = t
        return real(db_, frame_id)

    par._checks = racing
    try:
        out = par.review_frame(db, fid, reissue=False)
    finally:
        par._checks = real
    done["thread"].join(timeout=30)
    assert done["waited"] is True, "the writer committed inside the review's window"
    assert out["approved"] is True and done.get("at"), out
    with db.session() as s:
        f = s.get(ListingAsset, fid)
        # the writer's change landed after the review and was not overwritten by it
        assert f.position == 999, f.position
        assert f.blocked_reasons == [par.AWAITING, "re-marked by a concurrent upgrade"], \
            f.blocked_reasons


def test_review_opus2w_w2_a_photo_that_does_not_qualify_never_holds_the_set_hostage():
    """OPUS2W-2 / I-A3-NONQUALIFYING-PHOTO: a frame whose photo is not attested gets a
    terminal named reason, the listing set excludes it, and a later attestation re-opens it."""
    from brambleloop.publish import physical_upgrade as pu

    db, cir, release, _p = _setup(attest=False)
    fid = _photo_frame(db, cir)
    out = par.review_frame(db, fid, reissue=False)
    assert out["approved"] is False and out["not_qualifying"], out
    with db.session() as s:
        f = s.get(ListingAsset, fid)
        assert f.approved is False and par.AWAITING not in f.blocked_reasons
        assert any(r.startswith(par.NOT_QUALIFYING) for r in f.blocked_reasons), f.blocked_reasons
        pid = (f.claims or {}).get("physical_photo_id")
    assert fid not in [f.id for f in release_gates._frames(db, cir.slug, cir.version)]
    assert par.awaiting_frames(db) == []                  # not re-reviewed while unqualified
    pu.attest_unedited(db, pid, actor=T.OWNER, confirm=pu.UNEDITED_CONFIRMATION)
    assert fid in par.awaiting_frames(db)                 # a later attestation re-opens it
    par.sweep(db)
    with db.session() as s:
        f = s.get(ListingAsset, fid)
        assert not any(str(r).startswith(par.NOT_QUALIFYING) for r in f.blocked_reasons or [])


def test_review_opus2w_w3_w4_w5_supplement_conditions_leader_class_and_a_gone_frame():
    """OPUS2W-3: each condition of the supplement rule; OPUS2W-4: the leader must be a photo;
    OPUS2W-5: a frame deleted before the write is never reported approved."""
    db = T._db()
    cir, _release = T._certified_basket(db)
    T._render_gallery(db, cir)
    test_id = T._passed_full_make(db, cir)
    T._upgrade(db, cir, test_id)
    first = _photo_frame(db, cir)
    assert par.review_frame(db, first, reissue=False)["approved"] is True
    _second_attested_photo(db, cir, test_id)
    with db.session() as s:
        rows = {f.id: f for f in s.scalars(select(ListingAsset).where(
            ListingAsset.product_slug == cir.slug))}
        leader = next(f for f in rows.values() if (f.claims or {}).get("leads_gallery"))
        lead_id = leader.id
        render_id = next(f.id for f in rows.values() if f.asset_class != par.PHOTO_CLASS)

    def supplement_ok(mutate):
        with db.session() as s:
            mutate(s)
            f = s.get(ListingAsset, first)
            f.approved, f.blocked_reasons = False, [par.AWAITING]
        return par.review_frame(db, first, reissue=False)["approved"]

    assert supplement_ok(lambda s: None) is True
    # two leaders (N6)
    def two(s):
        f = s.get(ListingAsset, render_id)
        f.claims = {**(f.claims or {}), "leads_gallery": True}
    assert supplement_ok(two) is False
    def undo_two(s):
        f = s.get(ListingAsset, render_id)
        f.claims = {k: v for k, v in (f.claims or {}).items() if k != "leads_gallery"}
    supplement_ok(undo_two)
    # the leader not at position 1 (N7): swap the leader with the last frame
    def demote(s):
        frames = sorted(rows_now(s), key=lambda f: f.position)
        lead, last = s.get(ListingAsset, lead_id), frames[-1]
        lp, xp = lead.position, last.position
        lead.position = 10_000
        s.flush()
        last.position = lp
        s.flush()
        lead.position = xp
    def rows_now(s):
        return list(s.scalars(select(ListingAsset).where(ListingAsset.product_slug == cir.slug)))
    assert supplement_ok(demote) is False
    db2 = T._db()                                    # a fresh set for the gap and class cases
    cir2, _ = T._certified_basket(db2)
    T._render_gallery(db2, cir2)
    t2 = T._passed_full_make(db2, cir2)
    T._upgrade(db2, cir2, t2)
    f1 = _photo_frame(db2, cir2)
    par.review_frame(db2, f1, reissue=False)
    _second_attested_photo(db2, cir2, t2)
    with db2.session() as s:                          # a gap in the positions (N9)
        last = max(s.scalars(select(ListingAsset).where(
            ListingAsset.product_slug == cir2.slug)), key=lambda f: f.position)
        last.position += 7
        f = s.get(ListingAsset, f1)
        f.approved, f.blocked_reasons = False, [par.AWAITING]
    assert par.review_frame(db2, f1, reissue=False)["approved"] is False
    with db2.session() as s:                          # a render claims to lead (W-4)
        last.position -= 7
        for f in s.scalars(select(ListingAsset).where(ListingAsset.product_slug == cir2.slug)):
            if f.id == last.id:
                f.position -= 7
            if (f.claims or {}).get("leads_gallery"):
                f.claims = {**(f.claims or {}), "leads_gallery": False}
        rend = next(f for f in s.scalars(select(ListingAsset).where(
            ListingAsset.product_slug == cir2.slug, ListingAsset.position == 1)))
        rend_pos1_is_photo = rend.asset_class == par.PHOTO_CLASS
        rend.claims = {**(rend.claims or {}), "leads_gallery": True}
        rend.asset_class = "DIGITAL_TWIN_RENDER"
        f = s.get(ListingAsset, f1)
        f.approved, f.blocked_reasons = False, [par.AWAITING]
    assert rend_pos1_is_photo is True
    assert par.review_frame(db2, f1, reissue=False)["approved"] is False
    # W-5: the frame is gone before the write
    real = par._checks

    def gone(db_, frame_id):
        checks, ctx = real(db_, frame_id)
        return {c: True for c in par.CHECKS}, ctx
    db3, cir3, _r3, _p3 = _setup()
    fid3 = _photo_frame(db3, cir3)
    with db3.session() as s:
        s.delete(s.get(ListingAsset, fid3))
    par._checks = gone
    try:
        out = par.review_frame(db3, fid3, reissue=False)
    finally:
        par._checks = real
    assert out["approved"] is False and out["failed"] == ["frame_gone"], out


def test_review_opus2s_s3_a_second_qualifying_photo_does_not_deadlock_the_set():
    """OPUS2S-3: a second qualifying photo of the same release goes first; the first, demoted,
    no longer claims to lead. Both are approved (one leads, one supplements) and the set
    certifies."""
    db = T._db()
    cir, release = T._certified_basket(db)
    T._render_gallery(db, cir)
    test_id = T._passed_full_make(db, cir)
    T._upgrade(db, cir, test_id)
    first = _photo_frame(db, cir)
    assert par.review_frame(db, first, reissue=False)["approved"] is True
    sha2 = _second_attested_photo(db, cir, test_id)
    with db.session() as s:
        photos = sorted((f.position, f.id, dict(f.claims or {}).get("leads_gallery"))
                        for f in s.scalars(select(ListingAsset).where(
                            ListingAsset.product_slug == cir.slug,
                            ListingAsset.asset_class == par.PHOTO_CLASS)))
    assert [lead for _p, _i, lead in photos] == [True, False], photos
    assert photos[1][1] == first, photos
    swept = par.sweep(db)
    assert swept["refused"] == [], swept
    with db.session() as s:
        assert all(f.approved for f in s.scalars(select(ListingAsset).where(
            ListingAsset.product_slug == cir.slug,
            ListingAsset.asset_class == par.PHOTO_CLASS)))
    # the supplement was approved earlier as the leader; re-reviewed as a supplement it passes
    with db.session() as s:
        f = s.get(ListingAsset, first)
        f.approved, f.blocked_reasons = False, [par.AWAITING]
    assert par.review_frame(db, first, reissue=False)["approved"] is True
    _frames, cert = _certify_without_touching_approval(db, cir, release)
    assert cert["valid"] and cert["issued"], cert
    assert sample_photo.requirement(db, cir.slug, cir.version)["first_frame"]["sha256"] == sha2


def test_review_opus2s_s4_each_order_and_claim_rule_is_load_bearing():
    """OPUS2S-4: the sole-leader rule, positions 1..n, provenance 'camera', the generated-frame
    clause and the photo-class guard each refuse on their own."""
    def fresh():
        db, cir, _r, _p = _setup()
        return db, cir, _photo_frame(db, cir)

    db, cir, fid = fresh()                            # a second frame also claims to lead
    with db.session() as s:
        other = s.scalar(select(ListingAsset).where(
            ListingAsset.product_slug == cir.slug, ListingAsset.id != fid))
        other.claims = {**(other.claims or {}), "leads_gallery": True}
    assert par.review_frame(db, fid, reissue=False)["failed"] == ["frame_order_valid"]
    db, cir, fid = fresh()                            # a gap in the positions
    with db.session() as s:
        last = max(s.scalars(select(ListingAsset).where(
            ListingAsset.product_slug == cir.slug)), key=lambda f: f.position)
        last.position += 5
    assert par.review_frame(db, fid, reissue=False)["failed"] == ["frame_order_valid"]
    db, cir, fid = fresh()                            # not a camera file
    with db.session() as s:
        f = s.get(ListingAsset, fid)
        f.claims = {**(f.claims or {}), "provenance": "render"}
    assert par.review_frame(db, fid, reissue=False)["failed"] == ["no_disclosure_free_claim"]
    db, cir, fid = fresh()                            # a frame the system generated
    from brambleloop.publish import release_gates as rg

    real = rg.is_generated_frame
    rg.is_generated_frame = lambda frame: True
    try:
        out = par.review_frame(db, fid, reissue=False)
    finally:
        rg.is_generated_frame = real
    assert out["failed"] == ["no_disclosure_free_claim"], out
    db, cir, fid = fresh()                            # the class guard on its own
    with db.session() as s:
        s.get(ListingAsset, fid).asset_class = "RENDER"
    checks, _ctx = par._checks(db, fid)
    assert all(isinstance(v, str) and "not a PHYSICAL_PRODUCT_PHOTO frame" in v
               for v in checks.values()), checks



def _qualify_by_a_later_full_make(db, cir, fid):
    """The photo was filed before any full make passed; a full make passes later and is
    linked to it. No attestation call runs, so `lead_with_if_qualifying` is never triggered."""
    from brambleloop.core.models import PhysicalPhoto

    test_id = T._passed_full_make(db, cir)
    with db.session() as s:
        pid = s.get(ListingAsset, fid).claims["physical_photo_id"]
        s.get(PhysicalPhoto, pid).physical_test_id = test_id
    q = sample_photo.qualifying_photos(db, cir.slug, cir.version)
    assert any(e.get("photo_id") == pid for e in q.get("qualifying") or []), q
    return pid


def test_review_a3d1_a_photo_that_qualifies_later_without_an_attestation_leads_and_approves():
    """A3D-1 (MED liveness) and A3D-4 (K9, K12): a held frame whose photo qualifies through a
    later full make -- not `attest_unedited` -- is re-opened, promoted to lead, approved, and
    its stale "not qualifying" reason is gone; the set includes it again."""
    db, cir, _release, _p = _setup(full_make=False)
    fid = _photo_frame(db, cir)
    assert par.review_frame(db, fid, reissue=False)["not_qualifying"]
    assert fid not in [f.id for f in release_gates._frames(db, cir.slug, cir.version)]
    _qualify_by_a_later_full_make(db, cir, fid)
    assert par.awaiting_frames(db) == [fid]
    swept = par.sweep(db)
    assert swept["approved"] == 1, swept
    with db.session() as s:
        f = s.get(ListingAsset, fid)
        assert f.approved is True and f.blocked_reasons == [], f.blocked_reasons
        assert f.position == 1 and f.claims.get("leads_gallery") is True
    assert fid in [f.id for f in release_gates._frames(db, cir.slug, cir.version)]
    assert par.awaiting_frames(db) == []                  # nothing left to churn
    assert par.sweep(db)["reviewed"] == 0


def test_review_a3d1_a_qualifying_photo_that_fails_another_check_is_never_left_stale():
    """A3D-1: when a held photo qualifies but still fails a non-qualifying check (here a claim
    it may not make), its "not qualifying" reason is replaced by the awaiting reason: it rejoins
    the set and blocks it by name, instead of staying excluded with a false reason."""
    db, cir, _release, _p = _setup(full_make=False)
    fid = _photo_frame(db, cir)
    assert par.review_frame(db, fid, reissue=False)["not_qualifying"]
    _qualify_by_a_later_full_make(db, cir, fid)
    # reviewed directly, as A3D-1 traced it: filed last, it fails only frame_order_valid
    out = par.review_frame(db, fid, reissue=False)
    assert out["approved"] is False and out["failed"] == ["frame_order_valid"], out
    assert out.get("reopened_awaiting") == ["frame_order_valid"], out
    with db.session() as s:
        f = s.get(ListingAsset, fid)
        assert f.approved is False and f.blocked_reasons == [par.AWAITING], f.blocked_reasons
    assert fid in [f.id for f in release_gates._frames(db, cir.slug, cir.version)]



def test_review_a3d4_k9_k12_a_held_supplement_that_qualifies_later_is_approved_clean():
    """A3D-4 (K9, K12): the set already leads with an approved photograph; a second photo
    filed before its full make passed is held as not qualifying. Once its full make is linked,
    the sweep re-opens it, nothing is promoted (a photograph leads), the review approves it as
    a supplement and no "not qualifying" reason survives the approval."""
    db, cir, _release, _p = _setup()
    lead = _photo_frame(db, cir)
    assert par.sweep(db)["approved"] == 1
    _second_attested_photo(db, cir, None)
    with db.session() as s:
        second = [f.id for f in s.scalars(select(ListingAsset).where(
            ListingAsset.product_slug == cir.slug,
            ListingAsset.asset_class == par.PHOTO_CLASS)) if f.id != lead][0]
    assert par.review_frame(db, second, reissue=False)["not_qualifying"]
    _qualify_by_a_later_full_make(db, cir, second)
    assert par.awaiting_frames(db) == [second]
    assert par.sweep(db)["approved"] == 1
    with db.session() as s:
        f, first = s.get(ListingAsset, second), s.get(ListingAsset, lead)
        assert f.approved is True and f.blocked_reasons == [], f.blocked_reasons
        assert f.claims.get("leads_gallery") is False and f.position > 1
        assert first.position == 1 and first.claims.get("leads_gallery") is True
    assert second in [f.id for f in release_gates._frames(db, cir.slug, cir.version)]


def test_review_a3d3_a_frame_holding_other_bytes_is_not_reopened_every_sweep():
    """A3D-3: the photo qualifies, but the frame holds other bytes. It is not re-opened, so
    no hourly re-review, audit row or re-certification repeats for it."""
    from sqlalchemy import func

    db, cir, _release, _p = _setup(full_make=False)
    fid = _photo_frame(db, cir)
    par.review_frame(db, fid, reissue=False)
    _qualify_by_a_later_full_make(db, cir, fid)
    with db.session() as s:
        s.get(ListingAsset, fid).sha256 = "0" * 64
    assert par.awaiting_frames(db) == []
    with db.session() as s:
        before = s.scalar(select(func.count()).select_from(AuditLog).where(
            AuditLog.action == par.ACTION))
    for _ in range(3):
        assert par.sweep(db)["reviewed"] == 0
    with db.session() as s:
        assert s.scalar(select(func.count()).select_from(AuditLog).where(
            AuditLog.action == par.ACTION)) == before


def test_review_a3d4_k7_an_unreadable_record_is_never_made_terminal():
    """A3D-4 (K7): when the qualifying record cannot be read, the frame stays awaiting review
    (and so in the set, blocking it); it is never marked terminal and dropped from the set."""
    db, cir, _release, _p = _setup()
    fid = _photo_frame(db, cir)
    real = sample_photo.qualifying_photos

    def unreadable(*_a, **_k):
        raise RuntimeError("store unreadable")
    sample_photo.qualifying_photos = unreadable
    try:
        out = par.review_frame(db, fid, reissue=False)
    finally:
        sample_photo.qualifying_photos = real
    assert out["approved"] is False and not out.get("not_qualifying"), out
    with db.session() as s:
        f = s.get(ListingAsset, fid)
        assert f.blocked_reasons == [par.AWAITING], f.blocked_reasons
    assert fid in [f.id for f in release_gates._frames(db, cir.slug, cir.version)]


def test_review_a3d2_the_leading_writer_waits_for_the_review_lock():
    """A3D-2: a review holds the lock and approves the frame; `lead_with_if_qualifying` runs
    meanwhile. It takes the same lock before it reads, so it reads the approval and writes
    approved=False with the awaiting reason -- never approved=True beside an awaiting reason
    (the stale-copy write SQLAlchemy would send without approved)."""
    import threading
    import time

    from sqlalchemy.orm.attributes import flag_modified

    from brambleloop.core.models import PhysicalPhoto
    from brambleloop.publish import physical_upgrade as pu

    db, cir, _release, _p = _setup(attest=False)
    fid = _photo_frame(db, cir)
    with db.session() as s:
        pid = s.get(ListingAsset, fid).claims["physical_photo_id"]
        p = s.get(PhysicalPhoto, pid)          # attested, but not yet moved to the front
        p.detail = {**(p.detail or {}), "owner_attestation": {
            "sha256": p.sha256, "by": T.OWNER, "confirmed": pu.UNEDITED_CONFIRMATION}}
        flag_modified(p, "detail")
    held = threading.Event()

    def a_review_holding_the_lock():
        with db.session() as s:
            par._lock(s, db)
            f = s.get(ListingAsset, fid)
            f.approved, f.blocked_reasons = True, []
            s.flush()
            held.set()
            time.sleep(1.0)

    t = threading.Thread(target=a_review_holding_the_lock)
    t.start()
    held.wait(5)
    assert pu.lead_with_if_qualifying(db, pid) is True
    t.join()
    with db.session() as s:
        f = s.get(ListingAsset, fid)
        assert f.blocked_reasons == [par.AWAITING] and f.approved is False, (
            f.approved, f.blocked_reasons)


def test_review_a3d5_a_lock_that_cannot_be_taken_refuses_one_frame_and_the_sweep_goes_on():
    """A3D-5: a write lock held past the busy timeout is a refusal for that frame, not an
    exception that stops the sweep; nothing is written."""
    from sqlalchemy.exc import OperationalError

    db, cir, _release, _p = _setup()
    fid = _photo_frame(db, cir)
    real = par._lock

    def locked(s, db_):
        raise OperationalError("BEGIN IMMEDIATE", {}, Exception("database is locked"))
    par._lock = locked
    try:
        out = par.sweep(db)
    finally:
        par._lock = real
    assert out["approved"] == 0 and out["reviewed"] == 1, out
    assert "UNKNOWN" in out["refused"][0]["failed"][0], out
    with db.session() as s:
        assert s.get(ListingAsset, fid).blocked_reasons == [par.AWAITING]

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
