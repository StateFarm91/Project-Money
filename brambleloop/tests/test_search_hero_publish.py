"""F-004 end to end: the search certificate reaches PASS on the merits, and publish is no
longer stopped by it.

`runtime.etsy_ops.certified_payload` refuses unless the stored search verdict is PASS, and
`listing.seo` -- the only writer -- issued the certificate with the hero unjudged, so the
stored verdict was at best PENDING and no release could ever be published. Every test that
reached a draft forced the stored verdict to PASS. Here nothing is forced: the real
`gate.certify` -> `assets.build` (the disclosed render set) -> `listing.seo` handlers run on
a temporary sqlite database, the hero is judged on the listing-set certificate and the
completed certificate written back with its evidence, the owner's publication grant is
recorded through the real approve path, and the real `store.publish` handler passes the
search, listing-set and certified-image gates on a complete (>= 7 frame) certified gallery
and is stopped only by D-OWNER-SALE-PIPELINE (the release is truthfully not READY for sale
here; see the merits test). The negatives: a six-frame certified set
(D-OWNER-GALLERY-COMPLETE), a hero that was never judged, a hero that fails, and a certified
set that was superseded all refuse with zero Etsy requests (`tests/fake_etsy`, loopback).

Held outside this test's subject, each with its own tests: the creative parity gate (#75;
the disclosed set's HERO and COMPETITIVE dimensions need a vision description and a blind
review that cannot exist offline), the #126 search-grid tournament, and the Launch-0
first-customer scope gate (it names real owner/physical blockers -- durable storage, an
uncalibrated twin -- that are true of this environment). The listing-set, search,
staleness, window, originality and standards gates run for real.

Run: cd brambleloop && PYTHONPATH=src $PY tests/test_search_hero_publish.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import os
import shutil
import socket
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

_TMP = tempfile.mkdtemp(prefix="search_hero_publish_")
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")
for _k in list(os.environ):
    if _k.startswith(("ETSY", "BRAMBLELOOP_PUBLISH_AUTHORISED", "BRAMBLELOOP_SECRET_KEY",
                      "BRAMBLELOOP_OPS_TOKEN")):
        os.environ.pop(_k)

_real_connect = socket.socket.connect


def _loopback_only(sock, address, *a, **k):
    host = address[0] if isinstance(address, tuple) else address
    if host not in ("127.0.0.1", "localhost", "::1"):
        raise OSError(f"network refused: this test makes no outbound connection ({host})")
    return _real_connect(sock, address, *a, **k)


socket.socket.connect = _loopback_only

from sqlalchemy import select  # noqa: E402

import fixtures_etsy_taxonomy as FX  # noqa: E402
from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (  # noqa: E402
    EtsyTaxonomySnapshot, Job, JobStatus, Listing, ListingSearchProfile,
    ListingSetCertificateRecord, PatternVersion, Phase,
)
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import etsy_ops, pipeline, release  # noqa: E402,F401
from brambleloop.runtime.worker import Worker  # noqa: E402
from tests.fake_etsy import FakeEtsy  # noqa: E402
import _owner_grant; _owner_grant.scoped_owner_approvals()  # noqa: E402,E702  (WS4-0a)

SLUG = "cloudline-baby-blanket"
OWNER_TOKEN = "fixture-owner-publication-credential-32+"
_BUILT: dict = {}


def _run(db, agent: str, job_type: str, inputs: dict, *, phase=Phase.SHADOW) -> Job:
    with db.session() as s:   # a chain step queues its successors; run only the one named
        for other in s.scalars(select(Job).where(Job.job_type == job_type,
                                                 Job.status == JobStatus.PENDING)):
            other.status = JobStatus.CANCELLED
    if phase is not Phase.SHADOW:
        # F-299: past shadow, the runtime needs the owner's recorded transition path, not
        # the env alone; record it through the same sealed owner-only path the route uses.
        from unittest.mock import patch as _patch

        from phase_fixture import record_phase_path
        with _patch.dict(os.environ, {"BRAMBLELOOP_OPS_TOKEN": OWNER_TOKEN}):
            record_phase_path(db, OWNER_TOKEN, phase.value)
    job = JobQueue(db).enqueue(agent, job_type, inputs, priority=0,
                               idempotency_key=f"{job_type}:{time.time_ns()}")
    # The effective phase is the env AND the recorded transition (F-299): both must agree.
    from unittest.mock import patch as _patch2
    with _patch2.dict(os.environ, {"BRAMBLELOOP_PHASE": phase.value}):
        Worker(db, f"w-{job_type}", phase=phase, job_types=[job_type],
               lease_seconds=900).run_once()
    with db.session() as s:
        row = s.get(Job, job.id)
        s.expunge(row)
        return row


def _chain(slug: str = SLUG, category: str = "baby_blanket"):
    """certify -> assets.build -> listing.seo, through the real handlers. Returns a db path.

    `slug`/`category` default to the blanket every test here is about; test_visual_factory_e2e
    also drives a product whose disclosed set certifies the complete gallery
    (D-OWNER-GALLERY-COMPLETE)."""
    key = "full" if slug == SLUG else f"full-{slug}"
    if key not in _BUILT:
        path = os.path.join(_TMP, f"{key}.sqlite")
        db = Database(f"sqlite:///{path}")
        db.create_all()
        Registry(db).seed_defaults()
        snap = FX.snapshot()
        with db.session() as s:
            s.add(EtsyTaxonomySnapshot(sha256="fixture", node_count=len(snap["nodes"]),
                                       nodes=snap["nodes"], properties=snap["properties"]))
        cir = pipeline._engineered_cir(slug)
        job = _run(db, "quality_director", "gate.certify", {"cir": cir.to_dict()})
        assert job.status is JobStatus.DONE and job.outputs.get("granted"), job.outputs
        with db.session() as s:
            rh = s.scalar(select(PatternVersion)).release_hash
        job = _run(db, "publishing", "assets.build",
                   {"slug": slug, "version": cir.version, "release": rh,
                    "rebuild": "disclosed"})
        assert job.status is JobStatus.DONE, job.last_error
        # The price is the one the release path gives this Launch-0 product: pricing.position
        # prices Launch-0 from its own SOURCED plan (PT-04), CA$7.50 for the blanket. The
        # fixture used to hand listing.seo CA$9.50, a price no release path produces for it,
        # which publication now refuses as LISTING_PRICE_NOT_PLAN (W4-CAP1).
        from brambleloop.products import launch0 as _l0

        plan = _l0.launch_price(slug)
        assert plan is not None and plan["within_plan_band"], plan
        job = _run(db, "listing", "listing.seo",
                   {"slug": slug, "version": cir.version, "release": rh,
                    "price_cad": plan["price_cad"], "category": category})
        assert job.status is JobStatus.DONE and job.outputs["ok"], job.outputs
        db.engine.dispose()
        _BUILT[key] = (path, cir.version, rh)
    path, version, rh = _BUILT[key]
    copy = os.path.join(_TMP, f"{key}-{time.time_ns()}.sqlite")
    shutil.copy(path, copy)
    return copy, version, rh


def _profile(db, slug: str = SLUG) -> ListingSearchProfile:
    with db.session() as s:
        row = s.scalar(select(ListingSearchProfile).where(
            ListingSearchProfile.product_slug == slug))
        s.expunge(row)
        return row


@contextmanager
def _owner_and_fake(fake):
    """The owner's kill-switch open and ops credential set; the stock client on the fake.

    `store.publish` builds `EtsyClient(UrllibTransport(), credentials=from_env(...))`. The
    client class and its code run unchanged; only its base URL and credentials point at the
    loopback fake. Parity, the search grid and the Launch-0 scope gate are held (see the
    module docstring); every other gate runs.
    """
    from brambleloop.creative import preengineering
    from brambleloop.integrations import etsy
    from brambleloop.publish import eligibility

    creds = etsy.Credentials(api_key=fake.keystring, shared_secret=fake.shared_secret,
                             access_token="111.live-token", shop_id=fake.shop_id)

    class _Loopback(etsy.EtsyClient):
        def __init__(self, transport, *, credentials=None, phase="shadow",
                     owner_authorised=False, **kw):
            super().__init__(transport, credentials=creds, phase=phase,
                             owner_authorised=owner_authorised, base=fake.base)

    saved = (etsy.EtsyClient, etsy.Credentials.from_env, pipeline._listing_parity,
             preengineering.release_grid_verdict, eligibility.product_publication)
    env = {k: os.environ.get(k) for k in ("BRAMBLELOOP_PUBLISH_AUTHORISED",
                                          "BRAMBLELOOP_OPS_TOKEN")}
    etsy.EtsyClient = _Loopback
    etsy.Credentials.from_env = staticmethod(lambda *a, **k: creds)
    pipeline._listing_parity = lambda ctx: {"verdict": "pass", "blocks_release": False,
                                            "why": "held: #75 has its own tests",
                                            "dimensions": {}}
    preengineering.release_grid_verdict = lambda db, slug: {"cleared": True,
                                                            "why": "held: #126"}
    eligibility.product_publication = lambda *a, **k: {"reasons": [],
                                                       "held": "Launch-0 scope gate"}
    os.environ["BRAMBLELOOP_PUBLISH_AUTHORISED"] = "1"
    os.environ["BRAMBLELOOP_OPS_TOKEN"] = OWNER_TOKEN
    try:
        yield
    finally:
        (etsy.EtsyClient, etsy.Credentials.from_env, pipeline._listing_parity,
         preengineering.release_grid_verdict, eligibility.product_publication) = saved
        for k, v in env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _grant(db, version, rh, slug: str = SLUG) -> int:
    from unittest.mock import patch

    from brambleloop.ops import publication_authority as pa

    with patch.dict(os.environ, {"BRAMBLELOOP_OPS_TOKEN": OWNER_TOKEN,
                                 "BRAMBLELOOP_PUBLISH_AUTHORISED": "1"}):
        return _approve(db, pa, version, rh, slug=slug)


def _approve(db, pa, version, rh, slug: str = SLUG) -> int:
    content = pa.snapshot(db, slug, version, rh)
    return pa.approve(db, authorization=OWNER_TOKEN, slug=slug, version=version, release=rh,
                      expected_digest=pa.digest(content),
                      reason="fixture: owner reviewed this release")["approval_id"]


def _creates(fake) -> list:
    return [r for r in fake.requests if r["operation"] == "createDraftListing"]


# ---------------------------------------------------------------------------- the merits

# D-OWNER-GALLERY-COMPLETE: a listing is uploaded only with its whole certified gallery
# (`shot_plans.CAMPAIGN_MIN_FRAMES`, seven). The blanket's disclosed set plus its verified
# supplements certifies six frames on the production path (a flat piece has no ANGLE or
# CONSTRUCTION frame); the key basket's certifies eight. So the merits run is on the basket,
# through the same real handlers, and the six-frame blanket is asserted blocked on its own.
FULL_SLUG = "housewarming-key-basket"
FULL_CATEGORY = "basket"


def _hero_passed_on_the_merits(db, slug, version, rh) -> dict:
    """listing.seo judged the hero on the certified disclosed set and wrote PASS back, with
    the evidence it used, bound to this release. Returns the valid listing-set record."""
    row = _profile(db, slug)
    assert row.verdict == "PASS", (row.verdict, row.certificate.get("reasons"))
    cert = row.certificate
    assert cert["checks"]["hero"]["ok"] is True and not cert["pending"], cert["checks"]["hero"]
    ev = cert["hero_evidence"]
    with db.session() as s:
        rec = s.get(ListingSetCertificateRecord, ev["listing_set_record_id"])
        assert rec.state == "valid" and rec.release_hash == rh == ev["release_hash"]
        frame1 = next(f for f in rec.certificate["frames"] if f["position"] == 1)
        assert frame1["sha256"] == ev["frame_1_sha256"]
        assert frame1["kind"] == "disclosed_render"
        valid = list(s.scalars(select(ListingSetCertificateRecord).where(
            ListingSetCertificateRecord.state == "valid")))
        assert [r.id for r in valid] == [ev["listing_set_record_id"]], \
            [(r.id, r.state) for r in valid]
        frames = sorted((int(f["position"]), f["sha256"]) for f in rec.certificate["frames"])
    assert cert["bound_fingerprint"] == row.fingerprint
    payload = etsy_ops.certified_payload(db, slug, version)
    assert payload.taxonomy_id == row.taxonomy_id
    return {"record_id": ev["listing_set_record_id"], "frames": frames}


def test_certify_assets_seo_grant_publish_passes_every_gate_up_to_the_sale_rule_with_no_forced_verdict():
    """The merits, nothing forced, on a release whose certified set is the whole gallery.

    Before ENG-SALE-PIPELINE this run ended in exactly one Etsy draft. D-OWNER-SALE-PIPELINE
    (HARD RULE) now refuses publication unless the release is READY for sale -- both premium
    PDFs certified and the listing package READY -- and in this environment that is truthfully
    not so (no physical sample is bound; the Etsy remote claims are unverified). Faking READY
    is refused here as in test_visual_factory_e2e::test_b1. So the run asserts what this
    module owns -- the search certificate PASSES on the merits, the certified set is complete
    and every frame is served byte for byte in certificate order -- and that store.publish
    passes the search, listing-set and F-524 image gates and is stopped by the sale rule alone,
    with zero Etsy requests. The draft-and-read-back of a READY release is the integration
    item named in w6/review_requests/FIX-SALE-PIPELINE.md."""
    from brambleloop.visual.shot_plans import CAMPAIGN_MIN_FRAMES

    path, version, rh = _chain(FULL_SLUG, FULL_CATEGORY)
    db = Database(f"sqlite:///{path}")
    rec = _hero_passed_on_the_merits(db, FULL_SLUG, version, rh)
    # The whole certified gallery: the disclosed renders plus the W4-VISUAL supplements the
    # certificate was issued with, at least the campaign standard's seven.
    assert len(rec["frames"]) >= CAMPAIGN_MIN_FRAMES == 7, rec["frames"]
    served = etsy_ops.certified_images(db, FULL_SLUG, version, release=rh)
    assert served["problems"] == [], served["problems"]
    assert served["record_id"] == rec["record_id"]
    import hashlib

    assert [hashlib.sha256(d).hexdigest() for _n, d in served["images"]] == \
        [sha for _pos, sha in rec["frames"]], "served set differs from the certified set"

    with FakeEtsy() as fake, _owner_and_fake(fake):
        grant = _grant(db, version, rh, slug=FULL_SLUG)
        job = _run(db, "store_operator", "store.publish",
                   {"slug": FULL_SLUG, "version": version, "release": rh},
                   phase=Phase.LIMITED_PRODUCTION)
        assert job.status is JobStatus.DONE, job.last_error
        out = job.outputs
        assert out.get("published") is False and out.get("blocked") is True, out
        # stopped by the sale rule alone: no search, listing-set or image-gate reason
        assert out["reasons"] and all("D-OWNER-SALE-PIPELINE" in r for r in out["reasons"]), out
        assert not any("gallery incomplete" in r or "search" in r.split(":")[0]
                       for r in out["reasons"]), out
        assert fake.requests == [], [r["operation"] for r in fake.requests]
    with db.session() as s:
        listing = s.scalar(select(Listing).where(Listing.product_slug == FULL_SLUG))
        assert listing.etsy_listing_id in (None, ""), listing.etsy_listing_id
    assert grant
    db.engine.dispose()


def test_a_six_frame_certified_set_passes_search_but_is_blocked_before_etsy():
    """D-OWNER-GALLERY-COMPLETE: the blanket's hero passes on the merits, but its certified
    set is six frames, one short of the whole gallery, so publish refuses at the image gate
    with zero Etsy requests -- no partial gallery is ever uploaded."""
    from brambleloop.visual.shot_plans import CAMPAIGN_MIN_FRAMES

    path, version, rh = _chain()
    db = Database(f"sqlite:///{path}")
    rec = _hero_passed_on_the_merits(db, SLUG, version, rh)
    assert len(rec["frames"]) == 6 < CAMPAIGN_MIN_FRAMES, rec["frames"]
    served = etsy_ops.certified_images(db, SLUG, version, release=rh)
    assert served["images"] == [], served
    assert served["problems"] == [
        f"gallery incomplete: listing-set certificate {served['record_id']} names 6 of the "
        f"{CAMPAIGN_MIN_FRAMES} required listing photos (D-OWNER-GALLERY-COMPLETE)"], served
    with FakeEtsy() as fake, _owner_and_fake(fake):
        _grant(db, version, rh)
        job = _run(db, "store_operator", "store.publish",
                   {"slug": SLUG, "version": version, "release": rh},
                   phase=Phase.LIMITED_PRODUCTION)
        assert job.status is JobStatus.DONE, job.last_error
        out = job.outputs
        assert out.get("published") is False and out.get("blocked") is True, out
        assert any("gallery incomplete" in r for r in out.get("reasons") or []), out
        assert fake.requests == [], [r["operation"] for r in fake.requests]
    db.engine.dispose()


# ---------------------------------------------------------------------------- refusals

def _refused_with_no_request(db, version, rh, *, why: str):
    with FakeEtsy() as fake, _owner_and_fake(fake):
        try:
            _grant(db, version, rh)
        except ValueError as exc:
            assert "not certified PASS" in str(exc), str(exc)
        else:
            raise AssertionError("an owner grant was recorded for an uncertified listing")
        job = _run(db, "store_operator", "store.publish",
                   {"slug": SLUG, "version": version, "release": rh},
                   phase=Phase.LIMITED_PRODUCTION)
        assert job.status is not JobStatus.DONE or not job.outputs.get("published"), \
            job.outputs
        assert why in (job.last_error or "") or why in str(job.outputs), \
            (job.last_error, job.outputs)
        assert fake.requests == [], [r["operation"] for r in fake.requests]


def test_no_certified_listing_set_means_no_hero_pass_and_publish_makes_no_request():
    """No valid listing-set certificate, and none may be issued: the hero stays unjudged."""
    from brambleloop.commerce import search
    from brambleloop.core.models import Incident
    from brambleloop.publish import release_gates as RG

    path, version, rh = _chain()
    db = Database(f"sqlite:///{path}")
    with db.session() as s:
        for rec in s.scalars(select(ListingSetCertificateRecord)):
            rec.state = "superseded"
        # A halting incident: no listing-set certificate is issued while it is open.
        s.add(Incident(signature="provenance.stale:fixture", product_slug=SLUG,
                       severity="P1", halts_publication=True, summary="fixture"))
    got = search.judge_hero(db, slug=SLUG, version=version,
                            set_verdict=RG.listing_set(db, slug=SLUG, version=version,
                                                       issue=False))
    # Without a certified set the hero is not judged export-ready: never PASS.
    assert got["verdict"] in ("PENDING", "REFUSED") and got["hero"]["ok"] is not True, got
    assert got["evidence"] is None
    row = _profile(db)
    assert row.verdict != "PASS" and row.certificate["hero_evidence"] is None, row.certificate
    _refused_with_no_request(db, version, rh, why="not certified PASS")
    assert _profile(db).verdict != "PASS"   # store.publish re-judged; still not PASS
    db.engine.dispose()


def test_a_failing_hero_refuses_and_publish_makes_no_request():
    from brambleloop.commerce import search
    from brambleloop.publish import release_gates as RG

    path, version, rh = _chain()
    db = Database(f"sqlite:///{path}")
    # The judgement itself: frame 1 failing a gate makes the stored certificate REFUSED.
    sv = RG.listing_set(db, slug=SLUG, version=version, issue=False)
    failing = {**sv, "frames": [dict(f, may_export=False, why="fixture: hero fails a gate")
                                if f["position"] == 1 else f for f in sv["frames"]]}
    got = search.judge_hero(db, slug=SLUG, version=version, set_verdict=failing)
    assert got["verdict"] == "REFUSED" and got["hero"]["ok"] is False, got
    assert _profile(db).verdict == "REFUSED"
    try:
        _grant(db, version, rh)
    except ValueError as exc:
        assert "not certified PASS" in str(exc), str(exc)
    else:
        raise AssertionError("an owner grant was recorded on a REFUSED search certificate")
    # On the merits again, the same function writes PASS back: the gate is not a dead end.
    again = search.judge_hero(db, slug=SLUG, version=version, set_verdict=sv)
    assert again["verdict"] == "PASS", again

    # At publish: the owner granted the PASS release, then the copy lost the disclosure the
    # disclosed set is certified against. store.publish re-judges frame 1 on the set as it
    # now stands; it fails, the stored verdict is written back REFUSED, and nothing reaches
    # Etsy.
    from brambleloop.publish import disclosed_listing

    with FakeEtsy() as fake, _owner_and_fake(fake):
        _grant(db, version, rh)
        with db.session() as s:
            listing = s.scalar(select(Listing).where(Listing.product_slug == SLUG))
            listing.description = listing.description.replace(
                disclosed_listing.COPY_DISCLOSURE, "")
            assert disclosed_listing.COPY_DISCLOSURE not in listing.description
        job = _run(db, "store_operator", "store.publish",
                   {"slug": SLUG, "version": version, "release": rh},
                   phase=Phase.LIMITED_PRODUCTION)
        assert not (job.outputs or {}).get("published"), job.outputs
        assert "not certified PASS (REFUSED" in (job.last_error or ""), job.last_error
        assert fake.requests == [], [r["operation"] for r in fake.requests]
    row = _profile(db)
    assert row.verdict == "REFUSED", row.verdict
    assert row.certificate["checks"]["hero"]["ok"] is False, row.certificate["checks"]
    db.engine.dispose()


def test_a_superseded_set_or_an_edited_listing_makes_the_stored_pass_stale():
    from brambleloop.commerce import category

    path, version, rh = _chain()
    db = Database(f"sqlite:///{path}")
    assert category.publish_inputs(db, slug=SLUG, version=version)["certified"] == "PASS"
    # 1. The listing copy edited after certification (F-294).
    with db.session() as s:
        listing = s.scalar(select(Listing).where(Listing.product_slug == SLUG))
        saved = list(listing.tags)
        listing.tags = saved[:-1] + ["edited by hand"]
    got = category.publish_inputs(db, slug=SLUG, version=version)
    assert got["certified"] == "STALE" and any("changed" in p for p in
                                               got["certified_problems"]), got
    with db.session() as s:
        s.scalar(select(Listing).where(Listing.product_slug == SLUG)).tags = saved
    assert category.publish_inputs(db, slug=SLUG, version=version)["certified"] == "PASS"
    # 2. The certified set the hero was judged on is superseded.
    with db.session() as s:
        for rec in s.scalars(select(ListingSetCertificateRecord)):
            rec.state = "superseded"
    got = category.publish_inputs(db, slug=SLUG, version=version)
    assert got["certified"] == "STALE", got
    try:
        _grant(db, version, rh)
    except ValueError as exc:
        assert "not certified PASS" in str(exc) and "no longer valid" in str(exc), str(exc)
    else:
        raise AssertionError("an owner grant was recorded on a stale search PASS")
    db.engine.dispose()


if __name__ == "__main__":
    fails = 0
    tests = [(n, f) for n, f in list(globals().items()) if n.startswith("test_")]
    for name, fn in tests:
        started = time.time()
        try:
            fn()
            print("OK  ", name, f"{time.time() - started:.1f}s")
        except Exception as exc:  # noqa: BLE001
            fails += 1
            import traceback

            traceback.print_exc()
            print("FAIL", name, type(exc).__name__, str(exc)[:500])
    print(f"{len(tests) - fails}/{len(tests)} passing")
    sys.exit(1 if fails else 0)
