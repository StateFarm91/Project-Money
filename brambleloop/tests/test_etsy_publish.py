"""ENG-ETSY-PUBLISH: the automatic Etsy path, end to end on FakeEtsy.

Slice 1 (rollback):

* The rollback rehearsal reads the PDFs certified for THIS release from every `assets.built`
  row. It used to read only the newest 200 assets.build jobs across the catalogue, so an older
  release on a busy factory read "no built PDF" and FAILed.
* It reads the valid listing-set certificate's frames (the frames an upload sends). It used
  to read every stored ListingAsset, so a stale frame no certificate names failed the drill.
* `launch.rollback.withdraw_draft` executes the rollback of a draft this system created: read
  back, delete only while Etsy says `draft`, verify gone by a second read, then restore the
  local listing to its pre-draft state and retire the creation intent. A live listing, a
  refused delete or a listing Etsy still holds afterwards changes nothing.

Run: cd brambleloop && .venv/bin/python tests/test_etsy_publish.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702  W3-HYG: per-process temp sandbox, removed at exit
import hashlib
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from _r2_harness import run  # noqa: E402
from fake_etsy import FakeEtsy  # noqa: E402

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.integrations import etsy as E  # noqa: E402
from brambleloop.integrations.http import UrllibTransport  # noqa: E402

SLUG = "hexagonal-bread-basket"
VERSION = "1.0.0"
RELEASE = "a" * 64


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _db():
    from brambleloop.publish import draft_intent  # noqa: F401  registers its table

    db = Database(f"sqlite:///{tempfile.mkdtemp(prefix='etsypub_')}/d.sqlite")
    db.create_all()
    return db


def _client(fake: FakeEtsy, db, *, shadow_lane: bool = True) -> E.EtsyClient:
    creds = E.Credentials(api_key=fake.api_key_header(), access_token="111.live-token",
                          shop_id=fake.shop_id)
    client = E.EtsyClient(UrllibTransport(), credentials=creds, phase="shadow",
                          shadow_writes_authorised=shadow_lane, base=fake.base)
    client.db = db
    return client


def _remote_draft(fake: FakeEtsy, *, state: str = "draft") -> str:
    rec = fake._new_listing({"title": "Hexagonal Bread Basket Crochet Pattern",
                             "description": "d", "price": "6.50", "quantity": "999",
                             "who_made": "i_did", "when_made": "made_to_order",
                             "taxonomy_id": "66", "type": "download"})
    rec["state"] = state
    return str(rec["listing_id"])


def _local(db, listing_id: str | None, *, state: str = "published", intent: bool = True):
    from brambleloop.core.models import Incident, Listing
    from brambleloop.publish import draft_intent

    with db.session() as s:
        s.add(Listing(product_slug=SLUG, version=VERSION, title="t", description="d",
                      tags=[], price_cad=6.5, state=state, release_hash=RELEASE,
                      etsy_listing_id=listing_id or ""))
        if intent:
            s.add(draft_intent.DraftIntent(
                key=draft_intent.key_for(SLUG, VERSION), slug=SLUG, version=VERSION,
                release=RELEASE, content_digest="c" * 64, token="t" * 32, state="CREATED",
                remote_id=listing_id, detail={}))
        s.add(Incident(product_slug=SLUG, severity="P1", halts_publication=True,
                       signature=f"store.publish_incomplete:{SLUG}@{VERSION}",
                       summary="draft read back short", detail={}))


def _row(db):
    from sqlalchemy import select

    from brambleloop.core.models import Listing
    from brambleloop.publish import draft_intent

    with db.session() as s:
        row = s.scalar(select(Listing).where(Listing.product_slug == SLUG))
        intent = s.get(draft_intent.DraftIntent, draft_intent.key_for(SLUG, VERSION))
        return ({"state": row.state, "etsy_listing_id": row.etsy_listing_id,
                 "release_hash": row.release_hash, "price_cad": row.price_cad},
                None if intent is None else intent.state)


def _audits(db, action):
    from sqlalchemy import select

    from brambleloop.core.models import AuditLog

    with db.session() as s:
        return [dict(r.detail or {}) for r in s.scalars(
            select(AuditLog).where(AuditLog.action == action))]


def _deletes(fake):
    return [r for r in fake.requests if r.get("operation") == "deleteListing"
            or r.get("method") == "DELETE"]


# ---- slice 1: the executed draft rollback ---------------------------------------------------

def test_a_draft_is_withdrawn_verified_gone_and_the_local_listing_restored():
    from brambleloop.core.models import Incident
    from brambleloop.launch import rollback

    db = _db()
    with FakeEtsy() as fake:
        lid = _remote_draft(fake)
        _local(db, lid)
        out = rollback.withdraw_draft(db, _client(fake, db), slug=SLUG, version=VERSION,
                                      reason="rehearsed rollback")
        assert lid not in fake.listings, "the draft must be gone from Etsy"
    assert out["verified_absent"] and out["deleted_by_this_call"], out
    assert out["before"] == {"state": "published", "etsy_listing_id": lid,
                             "release_hash": RELEASE}, out["before"]
    row, intent = _row(db)
    assert row == {"state": "draft", "etsy_listing_id": "", "release_hash": RELEASE,
                   "price_cad": 6.5}, row
    assert intent is None, "the verified-gone draft's creation intent is retired"
    assert out["retired_intent"]["remote_id"] == lid, out["retired_intent"]
    assert _audits(db, rollback.DRAFT_WITHDRAWN), "the withdrawal is audited"
    with db.session() as s:
        from sqlalchemy import select

        inc = s.scalar(select(Incident).where(Incident.signature.like("store.publish_incomplete:%")))
        assert inc.resolved, "the publish-incomplete incident resolves with the evidence"


def test_a_live_listing_is_never_deleted_and_nothing_changes():
    from brambleloop.launch import rollback

    db = _db()
    with FakeEtsy() as fake:
        lid = _remote_draft(fake, state="active")
        _local(db, lid)
        before = _row(db)
        try:
            rollback.withdraw_draft(db, _client(fake, db), slug=SLUG, version=VERSION,
                                    reason="r")
            raise AssertionError("a live listing was withdrawn by the draft path")
        except rollback.RollbackRefused as exc:
            assert "deactivated, never deleted" in str(exc), exc
        assert lid in fake.listings and fake.listings[lid]["state"] == "active"
        assert not _deletes(fake), "no delete request may be sent"
    assert _row(db) == before
    assert _audits(db, rollback.DRAFT_WITHDRAW_REFUSED)


def test_a_delete_without_authority_changes_nothing():
    from brambleloop.launch import rollback

    db = _db()
    with FakeEtsy() as fake:
        lid = _remote_draft(fake)
        _local(db, lid)
        before = _row(db)
        try:
            rollback.withdraw_draft(db, _client(fake, db, shadow_lane=False), slug=SLUG,
                                    version=VERSION, reason="r")
            raise AssertionError("withdrew with no grant and no shadow lane")
        except rollback.RollbackRefused as exc:
            assert "delete refused" in str(exc), exc
        assert lid in fake.listings
    assert _row(db) == before


def test_a_listing_etsy_still_holds_after_the_delete_is_not_restored_locally():
    from brambleloop.launch import rollback

    db = _db()
    with FakeEtsy(delete_failure=(500, "server error")) as fake:
        lid = _remote_draft(fake)
        _local(db, lid)
        before = _row(db)
        try:
            rollback.withdraw_draft(db, _client(fake, db), slug=SLUG, version=VERSION,
                                    reason="r")
            raise AssertionError("restored locally while Etsy still holds the draft")
        except rollback.RollbackRefused:
            pass
        assert lid in fake.listings
    assert _row(db) == before


def test_a_204_that_left_the_draft_on_etsy_restores_nothing_locally():
    from brambleloop.launch import rollback

    db = _db()
    with FakeEtsy() as fake:
        fake.delete_is_noop = True
        lid = _remote_draft(fake)
        _local(db, lid)
        before = _row(db)
        try:
            rollback.withdraw_draft(db, _client(fake, db), slug=SLUG, version=VERSION,
                                    reason="r")
            raise AssertionError("a 204 was taken as proof the draft is gone")
        except rollback.RollbackRefused as exc:
            assert "still holds" in str(exc), exc
        assert fake.listings[lid]["state"] == "draft" and _deletes(fake)
    assert _row(db) == before


def test_a_soft_delete_counts_as_gone_and_an_absent_draft_reconciles_without_a_delete():
    from brambleloop.launch import rollback

    db = _db()
    with FakeEtsy(delete_is_soft=True) as fake:
        lid = _remote_draft(fake)
        _local(db, lid)
        out = rollback.withdraw_draft(db, _client(fake, db), slug=SLUG, version=VERSION,
                                      reason="r")
        assert fake.listings[lid]["state"] == "removed"
    assert out["remote_state_after"] == "removed", out
    db2 = _db()
    with FakeEtsy() as fake:
        _local(db2, "700999999")          # Etsy holds no such listing
        out = rollback.withdraw_draft(db2, _client(fake, db2), slug=SLUG, version=VERSION,
                                      reason="r")
        assert not _deletes(fake), "nothing to delete: no request is sent"
    assert out["remote_state_before"] == "absent" and not out["deleted_by_this_call"]
    assert _row(db2)[0]["etsy_listing_id"] == ""


def test_withdrawal_refuses_a_listing_that_is_not_a_draft_locally_or_has_no_reason():
    from brambleloop.launch import rollback

    for state, reason, needle in (("draft", "r", "records no Etsy draft"),
                                  ("withdrawn", "r", "is not a draft this path"),
                                  ("published", " ", "needs a reason")):
        db = _db()
        with FakeEtsy() as fake:
            lid = _remote_draft(fake)
            _local(db, None if state == "draft" else lid, state=state)
            try:
                rollback.withdraw_draft(db, _client(fake, db), slug=SLUG, version=VERSION,
                                        reason=reason)
                raise AssertionError(state)
            except rollback.RollbackRefused as exc:
                assert needle in str(exc), (state, exc)
            assert lid in fake.listings


# ---- slice 1: the rehearsal reads what a restore would re-serve -----------------------------

def _rehearsal_release(db, store, *, padding_jobs: int, stale_frame: bool):
    from brambleloop.core.models import (AuditLog, Job, JobStatus, Listing, ListingAsset,
                                         ListingSetCertificateRecord, PatternVersion, Product)

    pdfs = {"US": b"%PDF-1.4 us certified", "UK": b"%PDF-1.4 uk certified"}
    frame = b"\x89PNG\r\n\x1a\n" + b"certified-frame"
    for t, b in pdfs.items():
        store.put(f"{SLUG}/{t}.pdf", b, "application/pdf")
    store.put(f"{SLUG}/frame-1.png", frame, "image/png")
    hashes = {t: _sha(b) for t, b in pdfs.items()}
    with db.session() as s:
        p = Product(slug=SLUG, title="Basket", status="certified")
        s.add(p)
        s.flush()
        s.add(PatternVersion(product_id=p.id, version=VERSION, cir_json={}, certified=True,
                             certificate={"granted": True}, release_hash=RELEASE))
        job = Job(agent="assets", job_type="assets.build", status=JobStatus.DONE,
                  inputs={"slug": SLUG, "release": RELEASE},
                  outputs={"slug": SLUG, "version": VERSION, "release": RELEASE,
                           "pdf_sha256": hashes["US"], "pdf_sha256_by_terminology": hashes})
        s.add(job)
        s.flush()
        s.add(AuditLog(actor="assets", action="assets.built", artifact=f"{SLUG}@{VERSION}",
                       job_id=job.id, detail={"pdf_sha256_by_terminology": hashes}))
        for i in range(padding_jobs):  # a busy factory: other products built since
            s.add(Job(agent="assets", job_type="assets.build", status=JobStatus.DONE,
                      inputs={"slug": f"other-{i}"},
                      outputs={"slug": f"other-{i}", "version": "1.0.0",
                               "pdf_sha256": "f" * 64}))
        s.add(ListingSetCertificateRecord(
            product_slug=SLUG, version=VERSION, release_hash=RELEASE, state="valid",
            certificate={"frames": [{"position": 1, "sha256": _sha(frame)}]}))
        if stale_frame:  # a frame of an older gallery, named by no certificate, not on disk
            s.add(ListingAsset(product_slug=SLUG, version=VERSION, position=9,
                               asset_class="photo", role="detail", sha256="e" * 64))
        s.add(Listing(product_slug=SLUG, version=VERSION, title="t", description="d",
                      tags=[], price_cad=6.5, state="draft", release_hash=RELEASE))


def test_the_rehearsal_reads_this_releases_pdfs_and_the_certified_frames():
    from brambleloop.core.artifacts import ArtifactStore
    from brambleloop.launch import rollback

    db = _db()
    store = ArtifactStore(Path(tempfile.mkdtemp()) / "art")
    _rehearsal_release(db, store, padding_jobs=210, stale_frame=True)
    drill = rollback.rehearse(db, slug=SLUG, version=VERSION, store=store)
    step = next(s for s in drill["steps"] if s["step"] == "deliverables_restorable")
    assert step["ok"], step
    assert step["pdf_hashes"] == 2 and step["pdf_terminologies"] == ["UK", "US"], step
    assert step["frame_source"] == "listing_set_certificate" and step["frame_hashes"] == 1
    assert drill["ok"], drill
    rt = next(s for s in drill["steps"] if s["step"] == "state_round_trip")
    assert "withdraw_draft" in rt["executable_path"], rt


def test_the_rehearsal_still_fails_when_a_certified_frame_is_missing():
    from brambleloop.core.artifacts import ArtifactStore
    from brambleloop.core.models import ListingSetCertificateRecord
    from brambleloop.launch import rollback

    db = _db()
    store = ArtifactStore(Path(tempfile.mkdtemp()) / "art")
    _rehearsal_release(db, store, padding_jobs=0, stale_frame=False)
    with db.session() as s:
        rec = s.query(ListingSetCertificateRecord).one()
        rec.certificate = {"frames": [{"position": 1, "sha256": "d" * 64}]}
    step = next(s for s in rollback.rehearse(db, slug=SLUG, version=VERSION, store=store)
                ["steps"] if s["step"] == "deliverables_restorable")
    assert not step["ok"] and step["missing_on_disk"], step


# ---- slice 2: read-back hashes and dimensions ------------------------------------------------

def _png(w: int, h: int) -> bytes:
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (w, h), (200, 180, 160)).save(buf, format="PNG")
    return buf.getvalue()


def test_image_readback_compares_sent_hashes_with_the_certificate_and_etsy_dimensions():
    from brambleloop.runtime import etsy_ops

    a, b = _png(40, 30), _png(20, 20)
    sent = {"images": [etsy_ops.CertifiedImage("f-1.png", a, "alt one"),
                       etsy_ops.CertifiedImage("f-2.png", b, "alt two")],
            "order": [{"position": 1, "sha256": _sha(a)}, {"position": 2, "sha256": _sha(b)}]}
    remote = [{"rank": 1, "alt_text": "alt one", "full_width": 40, "full_height": 30},
              {"rank": 2, "alt_text": "alt two", "full_width": 20, "full_height": 20}]
    uploaded = {1: _sha(a), 2: _sha(b)}
    rows, problems = etsy_ops.image_hash_checks(sent, remote, uploaded)
    assert not problems and all(r["hash_matches_certificate"] for r in rows), (rows, problems)
    # bytes that are not the certified frame
    wrong = {**sent, "order": [{"position": 1, "sha256": "0" * 64}, sent["order"][1]]}
    rows, problems = etsy_ops.image_hash_checks(wrong, remote, uploaded)
    assert not rows[0]["hash_matches_certificate"] and "rank 1" in problems[0], problems
    # Etsy holds an image of other dimensions at rank 2
    rows, problems = etsy_ops.image_hash_checks(
        sent, [remote[0], {**remote[1], "full_width": 640}], uploaded)
    assert problems == ["image rank 2: sent 20x20, Etsy holds 640x20"], problems
    # Review b17-d A1: a rank not uploaded in this job proves nothing, whatever we meant to send
    rows, problems = etsy_ops.image_hash_checks(sent, remote, {1: _sha(a)})
    assert rows[1]["uploaded_in_this_job"] is False and not rows[1]["hash_matches_certificate"]
    assert problems == [problems[0]] and "rank 2: no bytes were uploaded" in problems[0], problems
    rows, problems = etsy_ops.image_hash_checks(sent, remote)
    assert len(problems) == 2, problems
    # ... and the hash is of the bytes uploaded, not of the bytes the job intended
    rows, problems = etsy_ops.image_hash_checks(sent, remote, {1: "f" * 64, 2: _sha(b)})
    assert "rank 1: sent bytes hash to ffffffffffff" in problems[0], problems
    # a missing Etsy dimension is a problem, never a skipped check
    rows, problems = etsy_ops.image_hash_checks(
        sent, [remote[0], {"rank": 2, "alt_text": "alt two"}], uploaded)
    assert problems == ["image rank 2: Etsy reported no full-size dimensions, so the image "
                        "it holds is unchecked"], problems

    class Client:
        def get_listing_images(self, _lid):
            return remote

    out = etsy_ops.images_read_back(Client(), "1", ["alt one", "alt two"], sent_images=wrong,
                                    uploaded=uploaded)
    assert out["verified"] is False and out["by_rank"], out


def test_only_missing_files_and_images_make_a_read_back_completable():
    from brambleloop.runtime import etsy_ops

    assert etsy_ops.completable({"verified": False, "files": {"problems": ["x missing"]},
                                 "images": {"verified": True}})
    assert etsy_ops.completable({"verified": False, "files": {"problems": []},
                                 "images": {"verified": False}})
    assert not etsy_ops.completable({"verified": False, "files": {"problems": []},
                                     "images": {"verified": True}})   # a field mismatch
    assert not etsy_ops.completable({"verified": False, "read_error": "503",
                                     "files": {"problems": ["x"]}})
    assert not etsy_ops.completable({"verified": True})


# ---- the grant guard: no recorded owner grant, no create ------------------------------------

def test_publication_without_a_recorded_owner_grant_sends_nothing():
    import os
    from unittest.mock import patch

    from phase_fixture import record_phase_path

    from brambleloop.ops import publication_authority as pa

    db = _db()
    _local(db, None, state="draft", intent=False)
    token = "etsy-publish-ops-token-for-tests-only"
    with patch.dict(os.environ, {"BRAMBLELOOP_OPS_TOKEN": token,
                                 "BRAMBLELOOP_PHASE": "limited_production",
                                 pa.KILL_SWITCH_VAR: "1"}):
        record_phase_path(db, token, "limited_production")
        grant = E.OwnerGrant(db, action=E.OwnerGrant.PUBLISH, approval_id=None, slug=SLUG,
                             version=VERSION, release=RELEASE)
        why = grant.refusal(action=E.OwnerGrant.PUBLISH)
        assert why and "grant" in why, why
        with FakeEtsy() as fake:
            client = _client(fake, db, shadow_lane=False)
            client.phase, client.owner_authorised = "limited_production", True
            payload = E.build_payload(title="t", description="d", price_cad=6.5,
                                      tags=["crochet"], materials=["yarn"])
            try:
                client.publish(payload=payload, filename="p.pdf", data=b"%PDF-1.4 x",
                               images=[("f.png", _png(40, 30))], grant=grant)
                raise AssertionError("published without a recorded grant")
            except E.EtsyNotPermitted as exc:
                assert "refused at the client" in str(exc), exc
            assert not [r for r in fake.requests if r["operation"] == "createDraftListing"]


# ---- slice 2: the one owner card is never raised on empty evidence ------------------------------

def test_the_first_listing_card_is_not_raised_without_its_evidence():
    from sqlalchemy import select

    from brambleloop.core.models import AuditLog, OwnerAction
    from brambleloop.publish import first_listing_card as FC

    db = _db()
    _local(db, "700000001", state="published", intent=False)   # a verified draft, locally
    out = FC.refresh(db)
    assert out["state"] == "none" and out["not_ready"], out
    missing = out["not_ready"][0]["missing"]
    assert any("store.published" in m for m in missing), missing
    assert any("PDF hashes" in m for m in missing), missing
    with db.session() as s:
        assert not list(s.scalars(select(OwnerAction).where(
            OwnerAction.requirement_key == FC.CARD_KEY)))
        assert not list(s.scalars(select(AuditLog).where(
            AuditLog.action == FC.EVIDENCE_ACTION)))
    # a published row whose read-back failed is still not evidence
    with db.session() as s:
        s.add(AuditLog(actor="t", action="store.published", artifact=f"{SLUG}@{VERSION}",
                       detail={"etsy_listing_id": "700000001",
                               "read_back": {"verified": False}}))
    out = FC.refresh(db)
    assert out["state"] == "none", out
    assert any("not verified" in m for m in out["not_ready"][0]["missing"]), out
    # once a listing is live there is no first-listing card to raise
    from brambleloop.core.models import Listing

    with db.session() as s:
        s.scalar(select(Listing)).state = "active"
    assert FC.refresh(db)["why"] == "a listing is live"


# ---- slice 2: the readback names why parity / listing_set / rollback do not pass --------------

def test_section_diagnostics_are_measurable_and_carry_no_free_text():
    import json

    from brambleloop.ops import production_evidence as pe

    secret = "private listing copy THAT MUST NOT LEAK"
    ev = {"parity": {"state": "UNKNOWN", "unjudged": ["competitive_blind_review", secret],
                     "failed": [], "frames_judged": 7, "why": secret,
                     "frame_review": {"reviewed": True, "why": secret},
                     "exported_frame_review": {"applies": True, "reviewed": False}},
          "listing_set": {"state": "FAIL", "blocks_release": True,
                          "certificate": {"valid": False, "why": secret},
                          "frames": [{"position": 1, "may_export": True},
                                     {"position": 2, "may_export": False}],
                          "reasons": [secret, secret]},
          "rollback": {"state": "FAIL", "rehearsal": {"ok": False, "steps": [
              {"step": "deliverables_restorable", "ok": False},
              {"step": "listing_on_record", "ok": True}, {"step": secret, "ok": False}]}},
          "search": {"state": "FAIL", "category_status": "UNKNOWN",
                     "checks": {"category": False, "hero": True, secret: False}},
          "certification": {"state": "FAIL", "certificate_granted": True,
                            "release_matches": True, "withheld": True, "why": secret}}
    d = pe._section_diagnostics(ev)
    assert secret not in json.dumps(d), d
    assert d["parity"]["unjudged"] == ["competitive_blind_review"], d["parity"]
    assert d["parity"]["exported_frame_review_done"] is False
    assert d["listing_set"] == {"certificate_valid": False, "blocks_release": True,
                                "frames": 2, "frames_may_export": 1, "reason_count": 2}
    assert d["rollback"] == {"rehearsal_recent": True,
                             "failing_steps": ["deliverables_restorable"]}
    assert d["search"] == {"category_status": "UNKNOWN", "failing_checks": ["category"]}
    assert d["certification"]["withheld"] is True
    assert pe._section_diagnostics({}) == {}


# ---- the scheduler and the card never write a grant --------------------------------------------

def test_the_scheduler_and_the_card_import_no_grant_writer():
    import ast
    import inspect

    from brambleloop.publish import first_listing_card, publication_scheduler

    for mod in (publication_scheduler, first_listing_card):
        tree = ast.parse(inspect.getsource(mod))
        called = {n.func.attr if isinstance(n.func, ast.Attribute) else getattr(n.func, "id", "")
                  for n in ast.walk(tree) if isinstance(n, ast.Call)}
        imported = {a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)
                    for a in n.names}
        for writer in ("approve", "rebase", "_seal", "owner_request", "issue", "sign",
                       "record_transition", "activate", "queue_activation"):
            assert writer not in called, (mod.__name__, writer)
        assert "owner_grant_keys" not in imported and "standing_issuer" not in imported, \
            (mod.__name__, imported)


def test_the_scheduler_queues_nothing_without_an_owner_grant():
    from sqlalchemy import select

    from brambleloop.core.models import Job, PatternVersion, Product
    from brambleloop.publish import publication_scheduler

    db = _db()
    _local(db, None, state="draft", intent=False)
    with db.session() as s:
        p = Product(slug=SLUG, title="Basket", status="certified")
        s.add(p)
        s.flush()
        s.add(PatternVersion(product_id=p.id, version=VERSION, cir_json={}, certified=True,
                             certificate={"granted": True}, release_hash=RELEASE))
    out = publication_scheduler.tick(db)
    assert out["queued"] == [] and out["waiting_for_owner_grant"] == 1, out
    with db.session() as s:
        assert not list(s.scalars(select(Job).where(Job.job_type == "store.publish")))


class _Ctx:
    """A JobContext stand-in: the db and an audit sink (what the helpers below use)."""

    def __init__(self, db):
        self.db, self.audits = db, []

    def audit(self, action, **kw):
        from brambleloop.core.models import AuditLog

        self.audits.append((action, kw))
        with self.db.session() as s:
            s.add(AuditLog(actor="store_operator", action=action,
                           artifact=kw.get("artifact"), detail=kw.get("detail") or {}))


def test_an_adopted_draft_has_every_image_rank_resent_and_reports_the_uploaded_hashes():
    """Review b17-d A1: matching alt text on an adopted draft is no reason to skip a rank."""
    from brambleloop.runtime import etsy_ops, pipeline

    a, b = _png(40, 30), _png(20, 20)
    images = {"images": [etsy_ops.CertifiedImage("f-1.png", a, "alt one"),
                         etsy_ops.CertifiedImage("f-2.png", b, "alt two")]}

    class Client:
        def __init__(self):
            self.uploads = []

        def get_listing_files(self, _lid):
            return []

        def attach_file(self, *_a, **_k):
            return True

        def get_listing_images(self, _lid):
            return [{"rank": 1, "alt_text": "alt one"}, {"rank": 2, "alt_text": "alt two"}]

        def upload_image(self, _lid, **kw):
            self.uploads.append((kw["rank"], kw["overwrite"], _sha(kw["data"])))

    docs = {t: type("D", (), {"pdf_bytes": b"%PDF"})() for t in ("US", "UK")}
    lazy = Client()
    out = pipeline._complete_draft(lazy, "1", slug="s", docs=docs, listing_images=images,
                                   payload=None, grant_fn=lambda: None)
    assert lazy.uploads == [] and out["sent_ranks"] == {}, out
    forced = Client()
    out = pipeline._complete_draft(forced, "1", slug="s", docs=docs, listing_images=images,
                                   payload=None, grant_fn=lambda: None, force_images=True)
    assert forced.uploads == [(1, True, _sha(a)), (2, True, _sha(b))], forced.uploads
    assert out["sent_ranks"] == {1: _sha(a), 2: _sha(b)}, out


def test_an_adopted_draft_holding_a_file_of_our_name_is_escalated():
    """Review b17-d A2: name and size cannot prove a held PDF is this release's."""
    from brambleloop.core.resilience import PermanentError
    from brambleloop.publish import draft_adoption
    from brambleloop.publish.pdf import pattern_filename
    from brambleloop.runtime import pipeline

    db = _db()
    ctx = _Ctx(db)

    class Client:
        def __init__(self, names):
            self.names = names

        def get_listing_files(self, _lid):
            return [{"filename": n} for n in self.names]

    pipeline._refuse_held_pattern_files(ctx, Client(["other.pdf"]), "9", slug=SLUG,
                                        version=VERSION, release=RELEASE)
    assert ctx.audits == []
    try:
        pipeline._refuse_held_pattern_files(
            ctx, Client([f"{SLUG}-{pattern_filename('UK')}"]), "9", slug=SLUG,
            version=VERSION, release=RELEASE)
        raise AssertionError("a held file of our name was accepted")
    except PermanentError as e:
        assert "DRAFT_ADOPTION_ESCALATED" in str(e), e
    assert ctx.audits[-1][0] == draft_adoption.ESCALATED, ctx.audits


def test_an_unreadable_shop_dead_letters_after_the_bound_with_one_incident():
    """Review b17-d A3: UNREAD retries are bounded; still nothing is created."""
    from sqlalchemy import select

    from brambleloop.core.models import Incident
    from brambleloop.core.resilience import PermanentError
    from brambleloop.runtime import pipeline

    db = _db()
    ctx = _Ctx(db)

    def refuse():
        ctx.audit("store.execution_refused", artifact=f"{SLUG}@{VERSION}",
                  detail={"release": RELEASE, "stage": "duplicate_check", "reason": "x"})

    for _ in range(pipeline.MAX_CONSECUTIVE_UNREAD - 1):
        pipeline._dead_letter_if_unread_too_often(ctx, slug=SLUG, version=VERSION,
                                                  release=RELEASE, why="503")
        refuse()
    for _ in range(2):
        try:
            pipeline._dead_letter_if_unread_too_often(ctx, slug=SLUG, version=VERSION,
                                                      release=RELEASE, why="503")
            raise AssertionError("an unreadable shop retried past the bound")
        except PermanentError as e:
            assert "DEAD_LETTER" in str(e), e
    with db.session() as s:
        rows = list(s.scalars(select(Incident).where(
            Incident.signature == f"store.draft_adoption:unread:{SLUG}@{VERSION}")))
        assert len(rows) == 1 and rows[0].severity == "P2", rows
    # Another outcome (an adoption) ends the streak.
    ctx.audit("store.draft_adopted", artifact=f"{SLUG}@{VERSION}", detail={})
    pipeline._dead_letter_if_unread_too_often(ctx, slug=SLUG, version=VERSION,
                                              release=RELEASE, why="503")


run(globals())
