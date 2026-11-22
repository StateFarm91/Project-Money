"""ENG-ETSY-PUBLISH, end to end on FakeEtsy with a release READY for sale
(tests/ready_release_fixture.py; READY-FIXTURE.md says what is faked and what is real).

package -> draft -> images (gallery order, alt text) and BOTH PDFs uploaded -> read back
(every byte that left hashes to the certified release, Etsy's sizes and dimensions match) ->
rollback (draft withdrawn, verified gone, local listing restored) -> a draft already on Etsy
with no local intent is ADOPTED and completed in place, never duplicated -> publication is
refused without the owner's grant -> the fee budget refuses beyond one fee per listing and
beyond CA$6.

The fixture and the held gates are exactly those of test_first_listing_doors (readiness, #75
parity, #126 grid and the Launch-0 scope are held there and here; each has its own tests).

Run: cd brambleloop && .venv/bin/python tests/test_etsy_publish_e2e.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702  W3-HYG
import hashlib
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

import test_first_listing_doors as FL  # noqa: E402  (fixture, env and loopback guard)
import ready_release_fixture as RF  # noqa: E402  (a READY release, real sale pipeline)

from sqlalchemy import select  # noqa: E402

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog, Job, JobStatus, Listing  # noqa: E402

SH, RP, reh = FL.SH, FL.RP, FL.reh


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _creates(fake) -> int:
    return sum(1 for r in fake.requests if r.get("operation") == "createDraftListing")


def _listing(db, slug, version):
    with db.session() as s:
        row = s.scalar(select(Listing).where(Listing.product_slug == slug,
                                             Listing.version == version))
        return {"state": row.state, "etsy_listing_id": str(row.etsy_listing_id or ""),
                "title": row.title, "price_cad": row.price_cad}


def _certified_pdfs(db, slug, version, rh):
    """The PDF editions certified for sale for this release (D-OWNER-SALE-PIPELINE): the
    premium US/UK editions whose `pdf_certificates` PASS, each bound to the `assets.build`
    edition of the same terminology. Since 19f these, not the base editions, are what a READY
    release uploads (test_vis_gallery_e2e test_3 asserts the same)."""
    from brambleloop.publish import sale_pipeline as SPL
    from brambleloop.publish.sale_pipeline import PdfCertificate
    from brambleloop.runtime.pipeline import _certified_pdf_hashes

    base = _certified_pdf_hashes(db, slug, version, rh)
    certs = SPL.pdf_certificates(db, slug, version, rh)
    assert certs["both_pass"] is True, certs
    with db.session() as s:
        bound = {t: s.get(PdfCertificate, e["certificate_id"]).base_pdf_sha256
                 for t, e in certs["editions"].items()}
    assert bound == base, (bound, base)
    premium = {t: e["pdf_sha256"] for t, e in certs["editions"].items()}
    stored = SPL.certified_premium_pdfs(db, slug, version, rh) or {}
    assert {t: _sha(b) for t, b in stored.items()} == premium, premium
    return premium


def _grant(db, slug, version, rh, note):
    from brambleloop.core import owner_grant_keys as ogk
    from brambleloop.ops import publication_authority as pa

    content = pa.snapshot(db, slug, version, rh)
    with ogk.owner_request("etsy-publish-test-owner"):
        return pa.approve(db, authorization=reh.REHEARSAL_OPS_TOKEN, slug=slug,
                          version=version, release=rh, expected_digest=pa.digest(content),
                          reason=f"ENG-ETSY-PUBLISH test: {note}")["approval_id"]


def _publish_via_door(db, slug, version, rh, gid):
    out = FL._exec(db, "publication.execute", slug=slug, version=version, release=rh,
                   approval_id=gid)["result"]
    assert out["queued"] is True, out
    FL._run_all(db, ["store.publish"])
    return FL._job(db, out["job_id"])


def _assert_complete_draft(db, fake, slug, version, rh, listing_id, job):
    """Both PDFs and every certified image, byte-for-byte as certified, read back clean."""
    from brambleloop.runtime import etsy_ops

    assert job["status"] == "done" and job["outputs"].get("published") is True, job
    assert job["outputs"].get("read_back_verified") is True, job
    assert job["outputs"]["files_attached_by_terminology"] == {"US": True, "UK": True}, job
    certified = _certified_pdfs(db, slug, version, rh)
    assert set(certified) == {"US", "UK"}, certified
    got_files = fake.received_files.get(str(listing_id)) or []
    # What arrived on the server is exactly the certified bytes (the fake records the hash of
    # the bytes it received; real Etsy returns no hash, see etsy_ops.image_hash_checks).
    assert sorted(f["sha256"] for f in got_files) == sorted(certified.values()), got_files
    from brambleloop.publish.pdf import pattern_filename

    assert sorted(f["filename"] for f in got_files) == \
        sorted(f"{slug}-{pattern_filename(t)}" for t in ("US", "UK")), got_files
    imgs = etsy_ops.certified_images(db, slug, version, release=rh)
    want = [(rank, _sha(e[1])) for rank, e in enumerate(imgs["images"], start=1)]
    got = sorted((i["rank"], i["sha256"]) for i in fake.received_images.get(str(listing_id)) or [])
    # Gallery order: rank n received the certificate's n-th frame. (An overwrite replaces a
    # rank, so only the last upload per rank is what Etsy holds.)
    last = {}
    for rank, sha in got:
        last[rank] = sha
    assert sorted(last.items()) == want, (last, want)
    held_alt = [i["alt_text"] for i in sorted(fake.images[str(listing_id)],
                                             key=lambda i: i["rank"])]
    assert held_alt == [getattr(e, "alt_text", "") for e in imgs["images"]], held_alt
    row = FL._audits(db, "store.published")[-1]
    by_rank = (row["read_back"].get("images") or {}).get("by_rank") or []
    assert by_rank and all(r["hash_matches_certificate"] for r in by_rank), by_rank
    assert row["read_back"]["files"]["verified"], row["read_back"]["files"]


def _open_cards(db):
    from brambleloop.core.models import OwnerAction
    from brambleloop.publish import first_listing_card as FC

    with db.session() as s:
        return [{"id": r.id, "action": r.action, "reason": r.reason,
                 "max_cost_cad": r.max_cost_cad} for r in s.scalars(
            select(OwnerAction).where(OwnerAction.requirement_key == FC.CARD_KEY,
                                      OwnerAction.done == False))]  # noqa: E712


def _assert_card(db, slug, version, listing_id):
    """ONE card, naming the exact listing, never with empty evidence."""
    from brambleloop.publish import first_listing_card as FC

    cards = _open_cards(db)
    assert len(cards) == 1, cards
    card = cards[0]
    assert card["action"] == "Approve first public listing (step-up)", card
    assert f"{slug}@{version}" in card["reason"] and str(listing_id) in card["reason"], card
    assert 0.27 <= card["max_cost_cad"] <= 0.30, card
    ev = FL._audits(db, FC.EVIDENCE_ACTION)[-1]
    assert ev["listing"]["etsy_listing_id"] == str(listing_id), ev["listing"]
    assert ev["readback"]["verified"] is True and ev["readback"]["files_on_etsy"], ev
    assert set(ev["hashes"]["pdfs"]) == {"US", "UK"} and ev["hashes"]["images"], ev
    assert all(i["matches_certificate"] for i in ev["hashes"]["images"]), ev
    from brambleloop.ops import publication_authority as pa

    assert set(ev["gates"]) == set(pa.GATED_SECTIONS), ev["gates"]
    for t, sha in ev["hashes"]["pdfs"].items():
        assert sha[:12] in card["reason"], (t, card["reason"])


def test_package_to_draft_rollback_adoption_and_refusals():
    from tests.fake_etsy import FakeEtsy

    from brambleloop.core import owner_grant_keys as ogk
    from brambleloop.integrations import etsy as etsy_mod
    from brambleloop.integrations.http import UrllibTransport
    from brambleloop.launch import rollback
    from brambleloop.publish import draft_adoption

    # A release READY for sale (D-OWNER-SALE-PIPELINE), built through the real sale chain on
    # fake image / vision providers only (tests/ready_release_fixture.py, READY-FIXTURE.md).
    path, version, rh = RF.ready_chain("etsypub")
    copy = path + ".etsypub.sqlite"
    shutil.copyfile(path, copy)
    db = Database(f"sqlite:///{copy}")
    slug = SH.SLUG
    with db.session() as s:
        s.add(AuditLog(actor="orchestrator", action="launch.rollback_rehearsed",
                       artifact=f"{slug}@{version}", detail={"ok": True}))
    env_keys = {"BRAMBLELOOP_OPS_TOKEN": reh.REHEARSAL_OPS_TOKEN,
                "BRAMBLELOOP_PUBLISH_AUTHORISED": "1", **ogk.generate_keypair()}
    saved_env = {k: os.environ.get(k) for k in
                 list(env_keys) + ["BRAMBLELOOP_PHASE", "ETSY_API_KEY", "ETSY_ACCESS_TOKEN",
                                   "ETSY_SHOP_ID", "ETSY_SHARED_SECRET", "ETSY_KEYSTRING",
                                   "ETSY_REFRESH_TOKEN"]}
    saved_base = etsy_mod.EtsyClient.BASE
    restore_gates = RP._held_gates()
    sim_tree, sim_craft = reh.simulated_taxonomy()
    log: list = []
    try:
        with FakeEtsy(taxonomy_nodes=sim_tree, required_property=sim_craft,
                      create_refuses_required_property=False) as fake:
            restore_net = reh._guard_narrowed(fake.port, log)
            try:
                os.environ.update(env_keys)
                os.environ["BRAMBLELOOP_PHASE"] = "shadow"
                for k in ("ETSY_KEYSTRING", "ETSY_REFRESH_TOKEN"):
                    os.environ.pop(k, None)
                os.environ.update({"ETSY_API_KEY": fake.keystring,
                                   "ETSY_ACCESS_TOKEN": "111.live-token",
                                   "ETSY_SHOP_ID": fake.shop_id,
                                   "ETSY_SHARED_SECRET": fake.shared_secret})
                etsy_mod.EtsyClient.BASE = fake.base
                rec = reh.Recorder()
                # The simulated seller taxonomy and the release's listing.seo were recorded by
                # the READY fixture in production order, before the gallery
                # (ready_release_fixture._simulated_taxonomy, the same
                # reh.record_simulated_taxonomy step); read back here. Re-running listing.seo
                # after a certified generated gallery is refused (READY-FIXTURE.md, F1).
                RF.assert_taxonomy_recorded(db, slug, version)
                os.environ["BRAMBLELOOP_PHASE"] = "limited_production"

                def run_job(db_, agent, job_type, inputs, phase):
                    if job_type == "launch.readiness":
                        with db_.session() as s:
                            s.add(AuditLog(actor="orchestrator", action="launch.assessed",
                                           artifact="launch", detail={"ready": True}))
                        return {"id": None, "status": "not run (test)", "last_error": ""}
                    return real_run_job(db_, agent, job_type, inputs, phase)
                real_run_job = reh._run_job
                reh._run_job = run_job
                try:
                    reh.record_owner_phase(rec, db, readiness_verdict=RP._ready)
                finally:
                    reh._run_job = real_run_job

                # 1. Refused without the owner's grant: a store.publish with no grant id
                #    creates nothing (publication only under the existing authority path).
                with db.session() as s:
                    s.add(Job(agent="store_operator", job_type="store.publish",
                              inputs={"slug": slug, "version": version, "release": rh},
                              idempotency_key="etsy-publish-test:no-grant"))
                FL._run_all(db, ["store.publish"])
                assert fake.listings == {} and _creates(fake) == 0, fake.listings
                assert _listing(db, slug, version)["etsy_listing_id"] == ""
                #    The scheduler finds no owner grant and queues nothing (it never grants).
                from brambleloop.publish import publication_scheduler

                tick = publication_scheduler.tick(db)
                assert tick["queued"] == [] and tick["waiting_for_owner_grant"] >= 1, tick

                # 2. With the grant: one draft, both PDFs, every image, read back clean.
                #    The first file upload is refused, so the create leaves a draft with no
                #    file and no image; the bounded completion round sends what Etsy lacks
                #    and the second read-back is clean. Still exactly one create.
                fake.file_failures.append((400, "simulated upload refusal"))
                gid = _grant(db, slug, version, rh, "first draft")
                job = _publish_via_door(db, slug, version, rh, gid)
                first_id = str(job["outputs"]["etsy_listing_id"])
                assert _creates(fake) == 1 and len(fake.listings) == 1, fake.listings
                assert job["outputs"].get("completion_rounds") == 1, job
                _assert_complete_draft(db, fake, slug, version, rh, first_id, job)
                assert _listing(db, slug, version)["state"] == "published"
                _assert_card(db, slug, version, first_id)

                # 3. Rollback: the draft is withdrawn, verified gone, the local listing
                #    restored. The publication grant may delete only its own draft.
                client = etsy_mod.EtsyClient(
                    UrllibTransport(), credentials=etsy_mod.Credentials.from_env(),
                    phase="limited_production", owner_authorised=True)
                client.db = db
                grant = etsy_mod.OwnerGrant(db, action=etsy_mod.OwnerGrant.PUBLISH,
                                            approval_id=gid, slug=slug, version=version,
                                            release=rh)
                out = rollback.withdraw_draft(db, client, slug=slug, version=version,
                                              reason="test rollback", grant=grant)
                assert out["verified_absent"] and first_id not in fake.listings, out
                local = _listing(db, slug, version)
                assert local["state"] == "draft" and local["etsy_listing_id"] == "", local
                # The card follows the evidence: with no verified draft it is withdrawn.
                from brambleloop.publish import first_listing_card as FC

                assert FC.refresh(db)["state"] == "withdrawn"
                assert _open_cards(db) == []

                # 4. Duplicate recovery: a draft for this release is on Etsy with no local
                #    intent (a restore from before the create, or a hand-made draft). The
                #    next publication adopts and completes it; no second listing is created.
                seeded = fake._new_listing({
                    "title": local["title"], "description": "hand-made draft",
                    "price": f"{local['price_cad']:.2f}", "quantity": "999",
                    "who_made": "i_did", "when_made": "made_to_order", "taxonomy_id": "66",
                    "type": "download"})
                seeded_id = str(seeded["listing_id"])
                # The hand-made draft carries the certified copy fields (what adoption
                # completes is files, images and properties; a field mismatch stays a
                # read-back finding, which a test below pins).
                from brambleloop.runtime import etsy_ops

                sent = etsy_ops.sent_fields(etsy_ops.certified_payload(db, slug, version))
                for k in ("description", "tags", "materials", "taxonomy_id", "who_made",
                          "when_made", "is_supply", "should_auto_renew", "quantity"):
                    if k in sent:
                        seeded[k] = sent[k]
                seeded["listing_type"] = sent.get("type", "download")
                # Review b17-d A1: the hand-made draft already holds an image at every rank
                # with the certified alt text and pixel size, but other bytes. Matching alt
                # text is no proof; adoption must overwrite every rank with our bytes.
                imgs = etsy_ops.certified_images(db, slug, version, release=rh)
                fake.images[seeded_id] = []
                for rank, e in enumerate(imgs["images"], start=1):
                    w, h = etsy_ops._dimensions(e[1])
                    fake.images[seeded_id].append({
                        "listing_image_id": 990000 + rank, "listing_id": int(seeded_id),
                        "rank": rank, "alt_text": getattr(e, "alt_text", ""),
                        "full_width": w, "full_height": h})
                assert not fake.received_images.get(seeded_id)
                creates_before = _creates(fake)
                # D-OWNER-SALE-PIPELINE: the rollback rewrote the local listing, so the
                # package fence invalidated the reviewed listing package ("listing or
                # certified release changed after package review") and the release is not
                # READY until it is re-assembled. The real packager re-assembles it.
                pk = SH._run(db, "listing", "listing.package", {"slug": slug,
                                                                "version": version})
                assert pk.status is JobStatus.DONE, pk.last_error
                from brambleloop.publish import sale_pipeline as SPL

                assert SPL.ready_for_sale(db, slug, version, rh)["ready"] is True, \
                    SPL.ready_for_sale(db, slug, version, rh)
                gid2 = _grant(db, slug, version, rh, "after rollback")
                #    No button: the hourly scheduler sees the owner's grant and queues the
                #    one store.publish for it; a second tick queues nothing more.
                tick = publication_scheduler.tick(db)
                assert [q["release"] for q in tick["queued"]] == [f"{slug}@{version}"], tick
                assert publication_scheduler.tick(db)["queued"] == []
                FL._run_all(db, ["store.publish"])
                job = FL._job(db, tick["queued"][0]["job_id"])
                assert _creates(fake) == creates_before, "a second listing was created"
                assert "etsy_listing_id" in job["outputs"], job
                assert str(job["outputs"]["etsy_listing_id"]) == seeded_id, job
                assert job["outputs"].get("adopted_existing_draft") is True, job
                assert FL._audits(db, draft_adoption.ADOPTED), "adoption is audited"
                _assert_complete_draft(db, fake, slug, version, rh, seeded_id, job)
                got_ranks = sorted({i["rank"] for i in fake.received_images[seeded_id]})
                assert got_ranks == list(range(1, len(imgs["images"]) + 1)), got_ranks
                by_rank = FL._audits(db, "store.published")[-1]["read_back"]["images"][
                    "by_rank"]
                last = {i["rank"]: i["sha256"] for i in fake.received_images[seeded_id]}
                assert all(r["uploaded_in_this_job"] and r["sent_sha256"] == last[r["rank"]]
                           for r in by_rank), by_rank
                assert len(fake.listings) == 1
                _assert_card(db, slug, version, seeded_id)

                # 5. The publication door is closed once a draft is bound.
                try:
                    FL._exec(db, "publication.execute", slug=slug, version=version,
                             release=rh, approval_id=gid2)
                    raise AssertionError("a second draft door opened")
                except FL.approvals.ActionRefused:
                    pass
                assert FL._fees(db) == [], "a draft reserves no listing fee"
                assert not log, log[:5]
            finally:
                restore_net()
    finally:
        restore_gates()
        etsy_mod.EtsyClient.BASE = saved_base
        for k, v in saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        db.engine.dispose()


def test_two_matching_drafts_or_a_live_one_escalate_and_nothing_is_created():
    from brambleloop.publish import draft_adoption as DA

    path, version, _rh = SH._chain()
    copy = path + ".etsypub-esc.sqlite"
    shutil.copyfile(path, copy)
    db = Database(f"sqlite:///{copy}")
    slug = SH.SLUG
    local = _listing(db, slug, version)
    draft = {"title": local["title"], "state": "draft",
             "price": {"amount": int(round(local["price_cad"] * 100)), "divisor": 100}}
    one = DA.judge(db, slug=slug, version=version, listings=[{**draft, "listing_id": 1}])
    assert one["verdict"] == DA.ADOPT and one["listing_id"] == "1", one
    two = DA.judge(db, slug=slug, version=version,
                   listings=[{**draft, "listing_id": 1}, {**draft, "listing_id": 2}])
    assert two["verdict"] == DA.ESCALATE, two
    live = DA.judge(db, slug=slug, version=version,
                    listings=[{**draft, "listing_id": 3, "state": "active"}])
    assert live["verdict"] == DA.ESCALATE and "'active'" in live["why"], live
    price = DA.judge(db, slug=slug, version=version,
                     listings=[{**draft, "listing_id": 4,
                                "price": {"amount": 1, "divisor": 100}}])
    assert price["verdict"] == DA.ESCALATE and "price" in price["why"], price
    other = DA.judge(db, slug=slug, version=version,
                     listings=[{**draft, "listing_id": 5, "title": "Another pattern"}])
    assert other["verdict"] == DA.NONE, other

    class Unreadable:
        def get_shop_listings(self, **_kw):
            raise RuntimeError("503")

    assert DA.check(db, Unreadable(), slug=slug, version=version)["verdict"] == DA.UNREAD

    class Stateless:
        def get_shop_listings(self, **_kw):
            return [{"listing_id": 9, "title": "x"}]

    assert DA.check(db, Stateless(), slug=slug, version=version)["verdict"] == DA.UNREAD

    class Two:
        def get_shop_listings(self, state, **_kw):
            return [{**draft, "listing_id": 1}, {**draft, "listing_id": 2}] \
                if state == "draft" else []

    assert DA.check(db, Two(), slug=slug, version=version)["verdict"] == DA.ESCALATE
    from brambleloop.core.models import Incident

    with db.session() as s:
        inc = s.scalar(select(Incident).where(Incident.signature == f"{DA.INCIDENT}{slug}@{version}"))
        assert inc is not None and inc.halts_publication and not inc.resolved
    db.engine.dispose()


def test_the_fee_budget_refuses_above_one_fee_per_listing_and_beyond_six_dollars():
    import tempfile

    from brambleloop.agents.registry import BudgetExceeded
    from brambleloop.core.fx import ASSUMED_CAD_PER_USD
    from brambleloop.finance import listing_costs as LC

    db = Database(f"sqlite:///{tempfile.mkdtemp()}/fee.sqlite")
    db.create_all()
    fee = round(0.20 * ASSUMED_CAD_PER_USD, 2)
    assert fee <= LC.per_listing_cap_cad() < fee + 0.02, (fee, LC.per_listing_cap_cad())
    try:
        LC.reserve(db, listing_id="big", amount=0.50, agent="store_operator", ceiling=100)
        raise AssertionError("a CA$0.50 single fee was reserved")
    except BudgetExceeded as exc:
        assert "per-listing cap" in str(exc), exc
    n = 0
    while True:
        try:
            LC.reserve(db, listing_id=f"l{n}", amount=fee, agent=f"a{n}", ceiling=100)
            n += 1
        except BudgetExceeded as exc:
            assert "CA$6.00" in str(exc), exc
            break
        assert n < 100
    assert n == int(6.00 // fee), (n, fee)
    assert LC.opening_budget(db)["used_cad"] <= 6.00
    # once reserved, a listing costs nothing more (idempotent per listing)
    assert LC.reserve(db, listing_id="l0", amount=fee, agent="a0", ceiling=100)


FL.__name__  # keep the import (the fixture module's tests do not run here)

if __name__ == "__main__":
    import traceback

    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn) and fn.__module__ == __name__:
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                traceback.print_exc()
                print("FAIL", name, repr(e))
    sys.exit(1 if fails else 0)
