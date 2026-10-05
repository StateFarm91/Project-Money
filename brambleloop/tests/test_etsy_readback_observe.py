"""FB-1 cluster B: publish with images, read back, activate only when proven, observe the shop.

Everything Etsy-shaped here runs against `tests/fake_etsy.py`, the local model of Etsy's
documented contract. What these tests establish is this system's behaviour against that
model -- that the certified images are the ones sent and in certificate order, that a write
the server ignored or transformed is caught by read-back rather than by a status code, that
activation refuses on every missing proof and on authority read at execution time, and that
the shop snapshot and listing census turn readings into incidents and owner-action closures
without ever reading an unread shop as clean. It does not establish that Etsy behaves this
way; no request here leaves the machine.

Run: cd brambleloop && $PY tests/test_etsy_readback_observe.py
"""
from __future__ import annotations

import hashlib
import os
import sys
import tempfile
import time
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

_TMP = tempfile.mkdtemp(prefix="fb1b_")
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")
for _k in list(os.environ):
    if _k.startswith(("ETSY", "BRAMBLELOOP_PUBLISH_AUTHORISED", "BRAMBLELOOP_SECRET_KEY")):
        os.environ.pop(_k)

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.artifacts import ArtifactStore  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (AuditLog, CostEntry, Incident, Job, JobStatus,  # noqa: E402
                                     Listing, ListingSetCertificateRecord, OperatingReading,
                                     OwnerAction, PatternVersion, Phase, Product)
from brambleloop.integrations import etsy_oauth, etsy_verify  # noqa: E402
from brambleloop.integrations.etsy import Credentials, EtsyClient  # noqa: E402
from brambleloop.integrations.http import UrllibTransport  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import etsy_ops, pipeline  # noqa: E402
from brambleloop.runtime.worker import CADENCES, JobContext, Worker  # noqa: E402
from tests.fake_etsy import FakeEtsy  # noqa: E402

PNG = b"\x89PNG\r\n\x1a\n" + b"frame-bytes-"
TITLE = "Nordic Forest Throw Digital Crochet Pattern"
DESCRIPTION = ("Digital crochet pattern, not a finished item: an instant digital download. "
               "Skill level: intermediate. You will need worsted yarn and a 5 mm hook. "
               "Written in US crochet terms and UK crochet terms. Questions? Message us.")


# ---- fixtures ----------------------------------------------------------------------------

_N = [0]


def _db() -> Database:
    _N[0] += 1
    db = Database(f"sqlite:///{_TMP}/b{_N[0]}.db")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _product(db, *, frames: int = 3) -> dict:
    """A certified release with a drafted listing and a valid listing-set certificate whose
    frames are real bytes in the artifact store."""
    from brambleloop.products import nordic_forest as nf

    cir = nf.build()
    store = ArtifactStore(os.environ["BRAMBLELOOP_ARTIFACT_DIR"])
    shas = [store.put(f"{cir.slug}/frame{p}.png", PNG + bytes([p]) * (p + 5),
                      "image/png").sha256 for p in range(1, frames + 1)]
    with db.session() as s:
        from brambleloop.core.models import ListingSearchProfile
        s.add(ListingSearchProfile(product_slug=cir.slug, version=cir.version,
                                  category_status="CHOSEN", taxonomy_id=2114,
                                  properties=[{"property_id": 200, "value_ids": [1], "values": ["Beige"], "scale_id": None}],
                                  verdict="PASS"))
        product = Product(slug=cir.slug, title="Nordic Forest", status="certified")
        s.add(product)
        s.flush()
        s.add(PatternVersion(product_id=product.id, version=cir.version,
                             cir_json=cir.to_dict(), release_hash="r" * 64, certified=True))
        s.add(Listing(product_slug=cir.slug, version=cir.version, title=TITLE,
                      description=DESCRIPTION, tags=["crochet pattern", "throw blanket"],
                      price_cad=12.5, release_hash="r" * 64))
        # Stored out of order on purpose: the upload must follow `position`, not row order.
        s.add(ListingSetCertificateRecord(
            product_slug=cir.slug, version=cir.version, release_hash="r" * 64, state="valid",
            certificate={"frames": [
                {"position": p, "asset_id": f"{cir.slug}-frame-{p}", "sha256": shas[p - 1],
                 "job": "hero", "purpose": "conversion", "medium": "render"}
                for p in reversed(range(1, frames + 1))]}))
    return {"slug": cir.slug, "version": cir.version, "shas": shas}


def _client(fake: FakeEtsy, *, owner: bool = False, phase: str = "limited_production",
            provider=None, token: str = "111.live-token") -> EtsyClient:
    creds = Credentials(api_key=fake.keystring, shared_secret=fake.shared_secret,
                        access_token=token, shop_id=fake.shop_id, token_provider=provider)
    return EtsyClient(UrllibTransport(), credentials=creds, phase=phase,
                      owner_authorised=owner, base=fake.base)


def _ctx(db, job_type: str, inputs: dict, *, agent: str = "store_operator",
         phase: Phase = Phase.LIMITED_PRODUCTION) -> JobContext:
    job = JobQueue(db).enqueue(agent, job_type, inputs,
                               idempotency_key=f"t:{job_type}:{time.time_ns()}")
    with db.session() as s:
        row = s.get(Job, job.id)
        s.expunge(row)
    return JobContext(job=row, db=db, queue=JobQueue(db), registry=Registry(db), phase=phase)


class _Doc:
    def __init__(self, data: bytes):
        self.pdf_bytes = data


def _docs():
    return {"US": _Doc(b"%PDF-1.7 US pattern " * 40), "UK": _Doc(b"%PDF-1.7 UK pattern " * 41)}


def _record_assets_built(db, p, docs, *, release: str = "r" * 64) -> dict:
    """Record the `assets.built` evidence the pre-create check reads, in the producer's shape.

    `runtime.release.handle_assets_build` stores each terminology's PDF in the artifact store
    and audits `assets.built` from its `assets.build` job, with `pdfs` keyed by terminology
    and carrying each stored file's sha256; `pipeline._certified_pdf_hashes` reads that row
    back and binds it to the release through the job's inputs. This writes the same row from
    the same kind of job for the exact bytes about to be uploaded, so the real
    `check_pdf_hashes` inside `_revalidate_publish_effect` runs and passes on the merits.
    """
    store = ArtifactStore(os.environ["BRAMBLELOOP_ARTIFACT_DIR"])
    pdfs = {t: store.put(f"{p['slug']}/{p['version']}/pattern-{t.lower()}.pdf", d.pdf_bytes,
                         "application/pdf")
            for t, d in sorted(docs.items())}
    ctx = _ctx(db, "assets.build", {"slug": p["slug"], "version": p["version"],
                                    "release": release}, agent="publishing")
    ctx.audit("assets.built", artifact=f"{p['slug']}@{p['version']}", detail={
        "pdf": pdfs["US"].to_dict(),
        "pdfs": {t: stored.to_dict() for t, stored in sorted(pdfs.items())}})
    hashes = pipeline._certified_pdf_hashes(db, p["slug"], p["version"], release)
    assert hashes == {t: hashlib.sha256(d.pdf_bytes).hexdigest() for t, d in docs.items()}, \
        hashes
    return hashes


def _publish(db, fake, p, *, docs=None, certified=None, client=None):
    """Publish as the pipeline does once the owner has granted publication authority.

    Owner publication authority is a durable, sealed, content-bound grant
    (`ops.publication_authority`) recorded here through the real `approve` path against the
    real preview digest, under the ops credential already in the environment (or a fixture
    one for the duration of the publish). The environment flag is only the global
    kill-switch, held open for the duration of the publish and restored afterwards:
    activation tests then decide authority for themselves at activation time.
    The creative-parity and release gates are held passing here, exactly as `_gates_pass`
    does for activation, because this fixture is a synthetic release with no parity or
    release evidence; the authority, PDF-hash, payload, image and release-binding checks of
    the pre-create revalidation all run for real.
    """
    docs = docs or _docs()
    certified = certified or {t: hashlib.sha256(d.pdf_bytes).hexdigest()
                              for t, d in docs.items()}
    _record_assets_built(db, p, docs)
    ctx = _ctx(db, "store.publish", {"slug": p["slug"], "version": p["version"]})
    images = etsy_ops.certified_images(db, p["slug"], p["version"], release="r" * 64)
    assert not images["problems"], images["problems"]
    payload = etsy_ops.certified_payload(db, p["slug"], p["version"])
    stored = types.SimpleNamespace(sha256=certified["US"])
    before = len(_audits(db, "store.execution_revalidated"))
    prior = os.environ.get("BRAMBLELOOP_PUBLISH_AUTHORISED")
    prior_token = os.environ.get("BRAMBLELOOP_OPS_TOKEN")
    os.environ["BRAMBLELOOP_PUBLISH_AUTHORISED"] = "1"
    from brambleloop.core import opsauth
    if not opsauth.configured():
        os.environ["BRAMBLELOOP_OPS_TOKEN"] = PUBLISH_FIXTURE_TOKEN
    orig = _gates_pass()
    try:
        grant = _grant_publication(db, p["slug"], p["version"], "r" * 64)
        used = client or _client(fake, owner=True)
        out = pipeline._publish_guarded(
            ctx, used, slug=p["slug"], version=p["version"],
            release="r" * 64, payload=payload, docs=docs, hash_check={"certified": certified},
            stored=stored, stored_by_terminology={t: types.SimpleNamespace(sha256=h)
                                                  for t, h in certified.items()},
            listing_images=images)
    finally:
        _restore(orig)
        if prior is None:
            os.environ.pop("BRAMBLELOOP_PUBLISH_AUTHORISED", None)
        else:
            os.environ["BRAMBLELOOP_PUBLISH_AUTHORISED"] = prior
        if prior_token is None:
            os.environ.pop("BRAMBLELOOP_OPS_TOKEN", None)
        else:
            os.environ["BRAMBLELOOP_OPS_TOKEN"] = prior_token
    # The full pre-create revalidation really ran and passed on the merits, at both
    # boundaries, under the owner's durable grant: once before the durable intent was claimed
    # (`pre_claim`) and once inside the stock client immediately before the create request
    # (`before_create`). A client of unknown publish order runs only the in-hook check.
    runs = _audits(db, "store.execution_revalidated")[before:]
    from brambleloop.runtime.pipeline import _STOCK_PUBLISH
    expected = (["pre_claim", "before_create"]
                if getattr(type(used), "publish", None) is _STOCK_PUBLISH
                else ["before_create"])
    assert [r.get("stage") for r in runs] == expected, runs
    assert all(r.get("owner_publication_grant") == grant for r in runs), (runs, grant)
    assert all(r.get("current_evidence") is True for r in runs), runs
    return out, ctx


PUBLISH_FIXTURE_TOKEN = "fixture-owner-publication-credential-32+"


def _grant_publication(db, slug: str, version: str, release: str) -> int:
    """The owner's publication grant, recorded through the real approve path (FB3-P)."""
    from brambleloop.ops import publication_authority as pa

    token = os.environ["BRAMBLELOOP_OPS_TOKEN"]
    content = pa.snapshot(db, slug, version, release)
    return pa.approve(db, authorization=token, slug=slug, version=version, release=release,
                      expected_digest=pa.digest(content),
                      reason="fixture: owner reviewed this release")["approval_id"]


def _audits(db, action: str) -> list[dict]:
    with db.session() as s:
        return [dict(a.detail or {}) for a in s.scalars(
            select(AuditLog).where(AuditLog.action == action).order_by(AuditLog.id))]


def _open_incidents(db, prefix: str = "") -> list[Incident]:
    with db.session() as s:
        rows = [i for i in s.scalars(select(Incident).where(Incident.resolved == False))  # noqa: E712
                if i.signature.startswith(prefix)]
        for r in rows:
            s.expunge(r)
        return rows


def _owner(db, key: str) -> list[OwnerAction]:
    with db.session() as s:
        rows = list(s.scalars(select(OwnerAction).where(OwnerAction.requirement_key == key)))
        for r in rows:
            s.expunge(r)
        return rows


class _Patched:
    """Point `etsy_ops.build_client` at the fake for one block, honouring owner_authorised."""

    def __init__(self, fake, **kw):
        self.fake, self.kw = fake, kw

    def __enter__(self):
        self.original = etsy_ops.build_client
        fake, kw = self.fake, self.kw

        def build(db, phase, *, owner_authorised=False, transport=None):
            if kw.get("no_credentials"):
                return EtsyClient(UrllibTransport(), credentials=None, phase=phase)
            return _client(fake, owner=owner_authorised, phase=phase,
                           provider=kw.get("provider"))

        etsy_ops.build_client = build
        return self

    def __exit__(self, *exc):
        etsy_ops.build_client = self.original


def _run(db, job_type: str, inputs: dict | None = None, *, agent: str = "orchestrator",
         phase: Phase = Phase.SHADOW) -> Job:
    # A verified publish queues its own store.activate (with no launch authorisation); park
    # anything already pending of this type so the worker runs the job this test names.
    with db.session() as s:
        for other in s.scalars(select(Job).where(Job.job_type == job_type,
                                                 Job.status == JobStatus.PENDING)):
            other.status = JobStatus.CANCELLED
    job = JobQueue(db).enqueue(agent, job_type, inputs or {},
                               idempotency_key=f"run:{job_type}:{time.time_ns()}")
    assert Worker(db, f"w-{job_type}", phase=phase, job_types=[job_type]).run_once()
    with db.session() as s:
        row = s.get(Job, job.id)
        s.expunge(row)
        return row


# ---- F-559: files, read back -------------------------------------------------------------


def test_file_read_back_matches_name_and_exact_size_and_says_etsy_exposes_no_hash():
    expected = [{"name": "a.pdf", "size": 10, "sha256": "x" * 64, "certified_sha256": "x" * 64}]
    ok = etsy_verify.verify_files(expected, [{"filename": "a.pdf", "size_bytes": 10}])
    assert ok.verified, ok.summary()
    assert ok.summary()["hash_on_etsy"] == etsy_verify.HASH_NOT_EXPOSED


def test_a_stale_file_beside_the_certified_one_fails_file_read_back():
    expected = [{"name": "a.pdf", "size": 10, "sha256": "x" * 64, "certified_sha256": "x" * 64}]
    out = etsy_verify.verify_files(expected, [{"filename": "a.pdf", "size_bytes": 10},
                                              {"filename": "old-v0.pdf", "size_bytes": 9}])
    assert not out.verified and any("old-v0.pdf" in p for p in out.problems), out.problems


def test_a_same_named_file_of_another_size_or_uncertified_bytes_fails():
    expected = [{"name": "a.pdf", "size": 10, "sha256": "x" * 64, "certified_sha256": "x" * 64}]
    assert not etsy_verify.verify_files(expected, [{"filename": "a.pdf",
                                                    "size_bytes": 11}]).verified
    drifted = [{**expected[0], "sha256": "y" * 64}]
    assert not etsy_verify.verify_files(drifted, [{"filename": "a.pdf",
                                                   "size_bytes": 10}]).verified
    # a human-readable filesize is never parsed into a byte count
    assert not etsy_verify.verify_files(expected, [{"filename": "a.pdf",
                                                    "filesize": "10 B"}]).verified


def test_an_unread_file_list_is_unverified_rather_than_clean():
    out = etsy_verify.verify_files([{"name": "a.pdf", "size": 1, "sha256": "x",
                                     "certified_sha256": "x"}], None)
    assert not out.verified and out.problems


def test_the_client_reads_a_listings_files_through_get_all_listing_files():
    with FakeEtsy() as fake:
        client = _client(fake, owner=True)
        from brambleloop.integrations.etsy import build_payload

        lid = client.create_draft(build_payload(title=TITLE, description=DESCRIPTION,
                                                price_cad=9.0, tags=["crochet"],
                                                materials=["yarn"]))
        client.attach_file(lid, filename="p.pdf", data=b"%PDF" * 10)
        files = client.get_listing_files(lid)
        assert [(f["filename"], f["size_bytes"]) for f in files] == [("p.pdf", 40)], files
        assert any(r["operation"] == "getAllListingFiles" for r in fake.requests)


# ---- F-524 / F-542: publish sends the certified images and reads the draft back ---------


def test_publish_sends_the_certified_image_bytes_in_certificate_order_and_reads_back():
    db = _db()
    p = _product(db)
    with FakeEtsy() as fake:
        out, _ctx_ = _publish(db, fake, p)
        lid = out["etsy_listing_id"]
        assert out["published"] and out["read_back_verified"], out
        ranks = [(i["rank"]) for i in fake.images[lid]]
        assert ranks == [1, 2, 3], ranks
        uploads = [r for r in fake.requests if r["operation"] == "uploadListingImage"]
        assert len(uploads) == 3
        reads = [r["operation"] for r in fake.requests]
        assert reads.index("getListing") > reads.index("uploadListingFile")
        assert "getAllListingFiles" in reads
    published = _audits(db, "store.published")[-1]
    assert [o["position"] for o in published["image_order"]] == [1, 2, 3]
    assert [o["sha256"] for o in published["image_order"]] == p["shas"]
    assert published["read_back"]["verified"] is True
    assert {f["name"] for f in published["files_sent"]} == {
        f"{p['slug']}-{n}" for n in ("pattern-us.pdf", "pattern-uk.pdf")} or \
        len(published["files_sent"]) == 2, published["files_sent"]
    with db.session() as s:
        queued = list(s.scalars(select(Job).where(Job.job_type == "store.activate")))
        assert len(queued) == 1 and queued[0].agent == "store_operator"


def test_a_missing_frame_refuses_before_anything_is_created_on_etsy():
    db = _db()
    p = _product(db)
    os.remove(ArtifactStore(os.environ["BRAMBLELOOP_ARTIFACT_DIR"]).root
              / p["shas"][1][:2] / p["shas"][1])
    images = etsy_ops.certified_images(db, p["slug"], p["version"], release="r" * 64)
    assert images["images"] == [] and any("frame 2" in x for x in images["problems"]), images


def test_a_write_etsy_silently_changed_is_caught_by_read_back_and_halts_the_product():
    """The fake remaps the taxonomy with a 201, exactly as Etsy does for a deprecated node.
    Nothing in any response is an error; only the read-back sees it."""
    db = _db()
    p = _product(db)
    with FakeEtsy(remap_taxonomy_to=67) as fake:
        out, _c = _publish(db, fake, p)
    assert out["published"] is False and not out["read_back_verified"], out
    assert any("taxonomy_id" in r for r in out["problems"]), out["problems"]
    assert _audits(db, "store.publish_incomplete"), "the mismatch was not recorded"
    halting = _open_incidents(db, etsy_ops.PUBLISH_INCOMPLETE)
    assert halting and halting[0].halts_publication and halting[0].severity == "P1"
    with db.session() as s:
        row = s.scalar(select(Listing).where(Listing.product_slug == p["slug"]))
        assert row.state == "incomplete_on_etsy"
        assert not list(s.scalars(select(Job).where(Job.job_type == "store.activate")))


def test_uploaded_bytes_that_are_not_the_certified_release_fail_file_read_back():
    db = _db()
    p = _product(db)
    docs = _docs()
    certified = {t: hashlib.sha256(d.pdf_bytes).hexdigest() for t, d in docs.items()}
    certified["UK"] = "0" * 64
    with FakeEtsy() as fake:
        out, _c = _publish(db, fake, p, docs=docs, certified=certified)
    assert out["published"] is False
    assert any("certified release file" in r for r in out["problems"]), out["problems"]


# ---- F-541: a credential only the owner can repair ---------------------------------------


def _provider(fake, *, refresh_token: str = "111.refresh-one", scopes=None,
              access: str = "111.dead-token", expires: float = 0.0):
    app = etsy_oauth.OAuthApp(keystring=fake.keystring, redirect_uri="https://x/cb",
                              shared_secret=fake.shared_secret, token_url=fake.token_url)
    return etsy_oauth.TokenProvider(
        app=app, transport=UrllibTransport(),
        tokens=etsy_oauth.TokenSet(access_token=access, refresh_token=refresh_token,
                                   expires_at=expires,
                                   scopes=tuple(scopes or fake.scopes)))


def _publish_expecting_owner(db, fake, provider) -> None:
    p = _product(db)
    try:
        _publish(db, fake, p, client=_client(fake, owner=True, provider=provider))
    except etsy_oauth.EtsyAuthNeedsOwner:
        return
    raise AssertionError("an auth failure did not reach the owner path")


def test_invalid_grant_on_publish_becomes_one_owner_action_and_one_incident():
    db = _db()
    with FakeEtsy() as fake:
        _publish_expecting_owner(db, fake, _provider(fake, refresh_token="111.spent"))
        assert not fake.listings, "a draft was created with a dead credential"
    actions = _owner(db, etsy_ops.AUTH_KEY)
    assert len(actions) == 1 and not actions[0].done
    incident = _open_incidents(db, etsy_ops.AUTH_INCIDENT)
    assert len(incident) == 1 and incident[0].detail["class"] == "invalid_grant", incident
    # a second failure restates rather than duplicates
    etsy_ops.record_auth_needs_owner(db, "invalid_grant again", where="store.publish")
    assert len(_owner(db, etsy_ops.AUTH_KEY)) == 1
    assert len(_open_incidents(db, etsy_ops.AUTH_INCIDENT)) == 1


def test_revoked_access_on_publish_is_an_owner_action_too():
    db = _db()
    with FakeEtsy() as fake:
        fake.token_failure = (401, {"error": "invalid_token", "error_description": "revoked"})
        _publish_expecting_owner(db, fake, _provider(fake))
    assert _owner(db, etsy_ops.AUTH_KEY)
    assert _open_incidents(db, etsy_ops.AUTH_INCIDENT)[0].detail["class"] in (
        "revoked_access", "refused_by_etsy", "invalid_grant")


def test_a_scope_the_grant_lacks_is_refused_before_the_request_and_queued_for_the_owner():
    db = _db()
    with FakeEtsy() as fake:
        provider = _provider(fake, access="111.live-token", expires=time.time() + 3600,
                             scopes=("listings_r", "shops_r"))
        _publish_expecting_owner(db, fake, provider)
        assert not any(r["operation"] == "createDraftListing" for r in fake.requests)
    assert _open_incidents(db, etsy_ops.AUTH_INCIDENT)[0].detail["class"] == "scope_drift"


def test_the_classifier_names_every_failure_class_f541_lists():
    c = etsy_ops.classify_auth_failure
    assert c("Etsy refused the refresh grant with 400: invalid_grant") == "invalid_grant"
    assert c("this token cannot perform x: it is missing ['listings_w']") == "scope_drift"
    assert c("stored credential is not openable under the current sealing key") == \
        "changed_encryption_key"
    assert c("no refresh token. ETSY_REFRESH_TOKEN is absent") == "no_token"


# ---- F-543: store.activate ---------------------------------------------------------------


def _published(db, fake):
    p = _product(db)
    out, _c = _publish(db, fake, p)
    assert out["published"], out
    return p, out["etsy_listing_id"]


def _gates_pass():
    orig = (pipeline._listing_parity, pipeline._release_gates)
    pipeline._listing_parity = lambda ctx: {"verdict": "pass", "blocks_release": False,
                                            "why": "forced", "dimensions": {}}
    pipeline._release_gates = lambda ctx: {"blocks_release": False, "reasons": []}
    return orig


def _restore(orig):
    pipeline._listing_parity, pipeline._release_gates = orig


def test_activation_in_shadow_is_refused_before_any_etsy_read():
    db = _db()
    with FakeEtsy() as fake:
        p, lid = _published(db, fake)
        before = len(fake.requests)
        orig = _gates_pass()
        try:
            with _Patched(fake):
                job = _run(db, "store.activate", {"slug": p["slug"], "version": p["version"],
                                                  "launch_authorisation": "L0"},
                           agent="store_operator", phase=Phase.SHADOW)
        finally:
            _restore(orig)
        assert job.status is JobStatus.DEAD and "SHADOW" in job.last_error, job.last_error
        assert len(fake.requests) == before and fake.listings[lid]["state"] == "draft"


def test_activation_verifies_the_draft_and_without_a_launch_authorisation_does_not_activate():
    db = _db()
    os.environ["BRAMBLELOOP_PUBLISH_AUTHORISED"] = "1"
    orig = _gates_pass()
    try:
        with FakeEtsy() as fake:
            p, lid = _published(db, fake)
            with _Patched(fake):
                job = _run(db, "store.activate", {"slug": p["slug"], "version": p["version"]},
                           agent="store_operator", phase=Phase.LIMITED_PRODUCTION)
            assert fake.listings[lid]["state"] == "draft"
    finally:
        _restore(orig)
        os.environ.pop("BRAMBLELOOP_PUBLISH_AUTHORISED", None)
    assert job.status is JobStatus.DONE and job.outputs["verified"] is True, job.outputs
    assert job.outputs["activated"] is False
    assert "Launch-0" in job.outputs["reasons"][0]
    assert _audits(db, "store.activation_verified")[-1]["ready"] is True


def test_the_owner_grant_is_read_when_activation_runs_not_when_it_was_planned():
    db = _db()
    orig = _gates_pass()
    try:
        with FakeEtsy() as fake:
            p, lid = _published(db, fake)
            with _Patched(fake):
                job = _run(db, "store.activate", {"slug": p["slug"], "version": p["version"],
                                                  "launch_authorisation": "L0-2026-10-01"},
                           agent="store_operator", phase=Phase.LIMITED_PRODUCTION)
            assert fake.listings[lid]["state"] == "draft"
    finally:
        _restore(orig)
    assert job.outputs["activated"] is False
    assert "RED action" in job.outputs["reasons"][0], job.outputs


def test_a_draft_edited_on_etsy_is_not_activated_and_says_which_field():
    db = _db()
    os.environ["BRAMBLELOOP_PUBLISH_AUTHORISED"] = "1"
    orig = _gates_pass()
    try:
        with FakeEtsy() as fake:
            p, lid = _published(db, fake)
            fake.listings[lid]["price"] = {"amount": 100, "divisor": 100, "currency_code": "CAD"}
            fake.files[lid].append({"filename": "old.pdf", "size_bytes": 3})
            with _Patched(fake):
                job = _run(db, "store.activate", {"slug": p["slug"], "version": p["version"],
                                                  "launch_authorisation": "L0"},
                           agent="store_operator", phase=Phase.LIMITED_PRODUCTION)
            assert fake.listings[lid]["state"] == "draft"
    finally:
        _restore(orig)
        os.environ.pop("BRAMBLELOOP_PUBLISH_AUTHORISED", None)
    reasons = " ".join(job.outputs["reasons"])
    assert job.outputs["activated"] is False and "price" in reasons and "old.pdf" in reasons


def test_a_failing_release_gate_at_execution_blocks_activation():
    db = _db()
    os.environ["BRAMBLELOOP_PUBLISH_AUTHORISED"] = "1"
    orig = _gates_pass()
    pipeline._release_gates = lambda ctx: {"blocks_release": True,
                                           "reasons": ["halting incident open"]}
    try:
        with FakeEtsy() as fake:
            p, lid = _published(db, fake)
            with _Patched(fake):
                job = _run(db, "store.activate", {"slug": p["slug"], "version": p["version"],
                                                  "launch_authorisation": "L0"},
                           agent="store_operator", phase=Phase.LIMITED_PRODUCTION)
            assert fake.listings[lid]["state"] == "draft"
    finally:
        _restore(orig)
        os.environ.pop("BRAMBLELOOP_PUBLISH_AUTHORISED", None)
    assert any("halting incident" in r for r in job.outputs["reasons"]), job.outputs


def test_with_every_proof_and_authority_present_the_listing_goes_live_and_is_read_back():
    db = _db()
    os.environ["BRAMBLELOOP_PUBLISH_AUTHORISED"] = "1"
    orig = _gates_pass()
    try:
        with FakeEtsy() as fake:
            p, lid = _published(db, fake)
            from brambleloop.ops import activation_authority as authority
            from unittest.mock import patch
            with patch.dict(os.environ, {"BRAMBLELOOP_OPS_TOKEN": "test-owner-credential-32-characters"}):
                content = authority.snapshot(db, p["slug"], p["version"])
                approval = authority.approve(db, authorization="test-owner-credential-32-characters",
                    slug=p["slug"], version=p["version"], expected_digest=authority.digest(content),
                    reason="owner reviewed this exact test draft")
                with _Patched(fake):
                    job = _run(db, "store.activate", {"slug": p["slug"], "version": p["version"],
                                                  "owner_activation_approval_id": approval["approval_id"]},
                           agent="store_operator", phase=Phase.LIMITED_PRODUCTION)
            assert fake.listings[lid]["state"] == "active"
    finally:
        _restore(orig)
        os.environ.pop("BRAMBLELOOP_PUBLISH_AUTHORISED", None)
    assert job.outputs["activated"] is True, job.outputs
    with db.session() as s:
        assert s.scalar(select(Listing).where(Listing.product_slug == p["slug"])).state == \
            "active"
        fee = list(s.scalars(select(CostEntry).where(CostEntry.kind == "etsy_listing_fee")))
        assert len(fee) == 1 and fee[0].agent == "store_operator"
    assert _audits(db, "store.activated")


# ---- F-553 / F-544 / F-568: the listing census -------------------------------------------


def test_the_census_is_a_daily_cadence_on_a_permitted_agent():
    names = {c[2]: c for c in CADENCES}
    for job_type in ("etsy.listing_census", "etsy.shop_snapshot", "etsy.credential_health"):
        assert names[job_type][3] == 24 * 60 * 60
        Registry(_db()).authorize(names[job_type][1], job_type)


def test_the_census_stores_the_estate_and_a_vanished_listing_is_a_suspected_takedown():
    db = _db()
    with FakeEtsy() as fake:
        p, lid = _published(db, fake)
        with _Patched(fake):
            job = _run(db, "etsy.listing_census")
            assert job.status is JobStatus.DONE and job.outputs["evidence"] == "FRESH", \
                job.outputs
            assert not job.outputs["suspected_policy"] and not job.outputs["field_drift"]
            reading = etsy_ops.latest_reading(db, etsy_ops.CENSUS_READING)
            assert reading["estate"][0]["listing_id"] == lid and reading["estate"][0]["ours"]
            fake.listings[lid]["state"] = "inactive"
            job = _run(db, "etsy.listing_census")
    assert job.outputs["suspected_policy"] == [lid], job.outputs
    incident = _open_incidents(db, etsy_ops.POLICY_SUSPECTED)[0]
    assert incident.halts_publication and incident.detail["deadline"]
    assert "closure_evidence" in incident.detail and incident.detail["remediation_owner"]


def test_a_listing_edited_on_etsy_is_field_drift_and_is_never_overwritten():
    db = _db()
    with FakeEtsy() as fake:
        p, lid = _published(db, fake)
        fake.listings[lid]["title"] = "Somebody edited this by hand"
        with _Patched(fake):
            job = _run(db, "etsy.listing_census")
        writes = [r for r in fake.requests if r["method"] in ("PATCH", "DELETE")]
        assert fake.listings[lid]["title"] == "Somebody edited this by hand" and not writes
    assert job.outputs["field_drift"] == [lid]
    drift = _open_incidents(db, etsy_ops.LISTING_DRIFT)[0]
    assert "title" in drift.summary and drift.halts_publication


def test_a_listing_nobody_here_created_is_reported():
    db = _db()
    with FakeEtsy() as fake:
        from brambleloop.integrations.etsy import build_payload

        stranger = _client(fake, owner=True).create_draft(build_payload(
            title=TITLE, description=DESCRIPTION, price_cad=3.0, tags=["x"], materials=["y"]))
        with _Patched(fake):
            job = _run(db, "etsy.listing_census")
    assert job.outputs["unexpected"] == [stranger]
    assert _open_incidents(db, etsy_ops.UNEXPECTED_LISTING)


def test_a_census_that_could_not_read_resolves_nothing_and_a_restored_listing_resolves():
    db = _db()
    with FakeEtsy() as fake:
        p, lid = _published(db, fake)
        fake.listings[lid]["state"] = "inactive"
        with _Patched(fake):
            _run(db, "etsy.listing_census")
        assert _open_incidents(db, etsy_ops.POLICY_SUSPECTED)
        with _Patched(fake, no_credentials=True):
            job = _run(db, "etsy.listing_census")
        assert job.outputs["evidence"] == "NO_EVIDENCE"
        assert _open_incidents(db, etsy_ops.POLICY_SUSPECTED), "an unread census closed it"
        fake.listings[lid]["state"] = "draft"
        with _Patched(fake):
            _run(db, "etsy.listing_census")
    assert not _open_incidents(db, etsy_ops.POLICY_SUSPECTED)
    with db.session() as s:
        closed = s.scalar(select(Incident).where(
            Incident.signature == f"{etsy_ops.POLICY_SUSPECTED}{lid}"))
        assert "census" in closed.detail["resolution"]


# ---- F-515 / F-577 / F-585: the shop snapshot --------------------------------------------

GOOD_SHOP = {"shop_name": "Brambleloop", "title": "Crochet patterns",
             "announcement": "Open", "digital_sale_message": "Thank you",
             "icon_url_fullxfull": "https://i/icon", "image_url_760x100": "https://i/banner",
             "policy_payment": "p", "policy_shipping": "s", "policy_refunds": "r",
             "policy_privacy": "v", "policy_additional": "a",
             "is_etsy_payments_onboarded": True, "is_vacation": False,
             "currency_code": "CAD", "digital_listing_count": 3}


def test_a_complete_shop_is_stored_and_closes_the_owner_actions_it_evidences():
    db = _db()
    etsy_ops.seed_owner_queue(db)
    with FakeEtsy(shop_body=dict(GOOD_SHOP)) as fake:
        with _Patched(fake):
            job = _run(db, "etsy.shop_snapshot")
    assert job.outputs["green"] is True, job.outputs
    stored = etsy_ops.latest_reading(db, etsy_ops.SHOP_READING)
    assert stored["shop"]["currency_code"] == "CAD" and stored["observed_at"]
    assert etsy_ops.CLOSES_ON_SHOP_CHECKS, "no owner action closes on the shop checks"
    for key in etsy_ops.CLOSES_ON_SHOP_CHECKS:
        assert _owner(db, f"{etsy_ops.SURFACE_PREFIX}{key}")[0].done, key
    assert not _owner(db, f"{etsy_ops.SURFACE_PREFIX}legal_and_tax_setup")[0].done


def test_vacation_mode_and_a_foreign_currency_open_halting_incidents():
    db = _db()
    with FakeEtsy(shop_body={**GOOD_SHOP, "is_vacation": True,
                             "currency_code": "USD"}) as fake:
        with _Patched(fake):
            _run(db, "etsy.shop_snapshot")
    sigs = {i.signature: i for i in _open_incidents(db, etsy_ops.SHOP_INCIDENTS)}
    assert sigs[f"{etsy_ops.SHOP_INCIDENTS}vacation"].halts_publication
    assert sigs[f"{etsy_ops.SHOP_INCIDENTS}currency_drift"].halts_publication


def test_payments_going_from_onboarded_to_not_is_an_incident_and_reopens_the_action():
    db = _db()
    etsy_ops.seed_owner_queue(db)
    with FakeEtsy(shop_body=dict(GOOD_SHOP)) as fake:
        with _Patched(fake):
            _run(db, "etsy.shop_snapshot")
            fake.shop_body = {**GOOD_SHOP, "is_etsy_payments_onboarded": False}
            # the reading is keyed by day; the flip is judged against the stored one
            _run(db, "etsy.shop_snapshot")
    assert _open_incidents(db, f"{etsy_ops.SHOP_INCIDENTS}payments_drift")
    assert not _owner(db, f"{etsy_ops.SURFACE_PREFIX}payment_settings_setup")[-1].done


def test_missing_trust_surfaces_cannot_pass_silently():
    db = _db()
    with FakeEtsy(shop_body={**GOOD_SHOP, "policy_refunds": None,
                             "icon_url_fullxfull": ""}) as fake:
        with _Patched(fake):
            job = _run(db, "etsy.shop_snapshot")
    assert job.outputs["green"] is False
    incident = _open_incidents(db, f"{etsy_ops.SHOP_INCIDENTS}incomplete")[0]
    assert incident.severity == "P1" and "icon_set" in incident.summary


def test_no_credentials_means_no_reading_not_an_empty_shop():
    db = _db()
    with FakeEtsy() as fake:
        with _Patched(fake, no_credentials=True):
            job = _run(db, "etsy.shop_snapshot")
    assert job.outputs["evidence"] == "NO_EVIDENCE"
    assert etsy_ops.latest_reading(db, etsy_ops.SHOP_READING) is None
    assert not _open_incidents(db)


# ---- F-540: credential health ------------------------------------------------------------


def test_credential_health_refreshes_rotates_and_persists_and_closes_a_reauth_action():
    from brambleloop.core import oauth_store
    from brambleloop.integrations.etsy import _persisting_on_refresh

    db = _db()
    os.environ["BRAMBLELOOP_SECRET_KEY"] = "k" * 48
    try:
        oauth_store.save_refresh_token(db, "111.refresh-one",
                                       scopes=" ".join(etsy_ops.REQUIRED_SCOPES),
                                       source="test", new_grant=True)
        etsy_ops.record_auth_needs_owner(db, "Etsy refused the refresh grant with 400: "
                                             "invalid_grant", where="store.publish")
        with FakeEtsy() as fake:
            provider = _provider(fake)
            provider.on_refresh = _persisting_on_refresh(db, dict(os.environ),
                                                         current_token="111.refresh-one")
            with _Patched(fake, provider=provider):
                job = _run(db, "etsy.credential_health")
            assert fake.refreshes == 1
        after = oauth_store.credential_health(db)
    finally:
        os.environ.pop("BRAMBLELOOP_SECRET_KEY", None)
    assert job.outputs["status"] == "HEALTHY", job.outputs
    assert after["rotations"] >= 1
    assert _owner(db, etsy_ops.AUTH_KEY)[0].done
    assert not _open_incidents(db, etsy_ops.AUTH_INCIDENT)
    assert etsy_ops.latest_reading(db, etsy_ops.CREDENTIAL_READING)["status"] == "HEALTHY"


def test_a_credential_sealed_under_another_key_is_unhealthy_and_queued_for_the_owner():
    from brambleloop.core import oauth_store

    db = _db()
    os.environ["BRAMBLELOOP_SECRET_KEY"] = "k" * 48
    oauth_store.save_refresh_token(db, "111.refresh-one",
                                   scopes=" ".join(etsy_ops.REQUIRED_SCOPES), source="test",
                                   new_grant=True)
    os.environ["BRAMBLELOOP_SECRET_KEY"] = "z" * 48
    try:
        with FakeEtsy() as fake:
            with _Patched(fake):
                job = _run(db, "etsy.credential_health")
            assert fake.refreshes == 0
    finally:
        os.environ.pop("BRAMBLELOOP_SECRET_KEY", None)
    assert job.outputs["status"] == "UNHEALTHY"
    assert _open_incidents(db, etsy_ops.AUTH_INCIDENT)[0].detail["class"] == \
        "changed_encryption_key"
    assert _open_incidents(db, f"{etsy_ops.CREDENTIAL_READING}:unhealthy")


def test_scope_drift_on_the_stored_credential_is_an_incident():
    from brambleloop.core import oauth_store

    db = _db()
    os.environ["BRAMBLELOOP_SECRET_KEY"] = "k" * 48
    try:
        oauth_store.save_refresh_token(db, "111.refresh-one", scopes="listings_r shops_r",
                                       source="test", new_grant=True)
        with FakeEtsy() as fake:
            with _Patched(fake, provider=_provider(fake)):
                job = _run(db, "etsy.credential_health")
    finally:
        os.environ.pop("BRAMBLELOOP_SECRET_KEY", None)
    assert job.outputs["status"] == "UNHEALTHY"
    assert "listings_w" in " ".join(job.outputs["findings"])
    assert _open_incidents(db, etsy_ops.AUTH_INCIDENT)[0].detail["class"] == "scope_drift"


# ---- F-593 / F-547: the Etsy owner-only queue in the one owner queue ---------------------


def test_the_etsy_owner_queue_is_seeded_once_by_key_with_its_closing_evidence():
    from brambleloop.intel import etsy_surfaces

    db = _db()
    first = etsy_ops.seed_owner_queue(db)
    second = etsy_ops.seed_owner_queue(db)
    assert len(first["queued"]) == len(etsy_surfaces.owner_queue()) and not second["queued"]
    with db.session() as s:
        rows = list(s.scalars(select(OwnerAction).where(
            OwnerAction.requirement_key.like(f"{etsy_ops.SURFACE_PREFIX}%"))))
    assert len(rows) == len(etsy_surfaces.owner_queue())
    assert all("Closes on:" in r.reason and r.minutes > 0 for r in rows)


def test_a_seeded_action_closed_on_evidence_is_not_asked_again():
    db = _db()
    etsy_ops.seed_owner_queue(db)
    key = f"{etsy_ops.SURFACE_PREFIX}payment_settings_setup"
    with db.session() as s:
        etsy_ops._set_owner_action(s, key, done=True)
    assert not etsy_ops.seed_owner_queue(db)["queued"]
    assert len(_owner(db, key)) == 1 and _owner(db, key)[0].done


def test_launch_readiness_seeds_the_etsy_queue_and_does_not_close_it():
    db = _db()
    job = _run(db, "launch.readiness")
    assert job.status is JobStatus.DONE, job.last_error
    with db.session() as s:
        rows = list(s.scalars(select(OwnerAction).where(
            OwnerAction.requirement_key.like(f"{etsy_ops.SURFACE_PREFIX}%"))))
    assert rows and not any(r.done for r in rows)
    etsy_ops.record_auth_needs_owner(db, "invalid_grant", where="test")
    _run(db, "launch.readiness")
    assert not _owner(db, etsy_ops.AUTH_KEY)[0].done, "readiness closed the reauth action"
    assert not any(r.done for r in _owner(db, f"{etsy_ops.SURFACE_PREFIX}etsy_ads_off"))


# ---- F-594: readiness reads the exercise breadcrumbs -------------------------------------


def _crumb(db, action: str, detail: dict) -> None:
    with db.session() as s:
        s.add(AuditLog(actor="orchestrator", action=action, detail=detail))


def test_etsy_integration_turns_ready_only_on_a_live_full_round_trip_with_nothing_left():
    from brambleloop.launch.readiness import _etsy_exercise_evidence

    db = _db()
    assert _etsy_exercise_evidence(db)["round_trip_proven"] is False
    _crumb(db, "etsy.exercise_draft_created", {"listing_id": "1"})
    _crumb(db, "etsy.exercise_finished", {"mode": "full", "ok": True,
                                          "status": "RAN AGAINST A LOCAL MODEL OF ETSY"})
    local = _etsy_exercise_evidence(db)
    assert local["round_trip_proven"] is False and local["ever_called_against_etsy"] is False
    _crumb(db, "etsy.exercise_finished", {"mode": "full", "ok": True,
                                          "status": "EXERCISED against openapi.etsy.com."})
    assert _etsy_exercise_evidence(db)["round_trip_proven"] is False, \
        "a draft never confirmed removed must hold it"
    _crumb(db, "etsy.exercise_draft_removed", {"listing_id": "1"})
    live = _etsy_exercise_evidence(db)
    assert live["round_trip_proven"] is True and live["ever_called_against_etsy"] is True


def test_the_readiness_item_needs_credentials_as_well_as_the_proof():
    from brambleloop.launch.readiness import BLOCKED_INTEGRATION, assess

    db = _db()
    _crumb(db, "etsy.exercise_draft_created", {"listing_id": "1"})
    _crumb(db, "etsy.exercise_draft_removed", {"listing_id": "1"})
    _crumb(db, "etsy.exercise_finished", {"mode": "full", "ok": True,
                                          "status": "EXERCISED against openapi.etsy.com."})
    item = next(r for r in assess(db, phase="shadow").requirements
                if r.key == "etsy_integration")
    assert item.evidence["round_trip_proven"] is True and item.evidence["ever_called"] is True
    assert item.ready is False and item.blocked_by == BLOCKED_INTEGRATION, \
        "no credential in this environment, so it is not credentialled"


if __name__ == "__main__":
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                fails += 1
                print("FAIL", name, repr(e)[:600])
                traceback.print_exc(limit=4)
    print(f"\n{sum(1 for n in globals() if n.startswith('test_')) - fails} passed, "
          f"{fails} failed")
    sys.exit(1 if fails else 0)
