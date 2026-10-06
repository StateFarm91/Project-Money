"""F-004 end to end: the search certificate reaches PASS on the merits, and publish succeeds.

`runtime.etsy_ops.certified_payload` refuses unless the stored search verdict is PASS, and
`listing.seo` -- the only writer -- issued the certificate with the hero unjudged, so the
stored verdict was at best PENDING and no release could ever be published. Every test that
reached a draft forced the stored verdict to PASS. Here nothing is forced: the real
`gate.certify` -> `assets.build` (the disclosed render set) -> `listing.seo` handlers run on
a temporary sqlite database, the hero is judged on the listing-set certificate and the
completed certificate written back with its evidence, the owner's publication grant is
recorded through the real approve path, and the real `store.publish` handler creates
exactly one draft on `tests/fake_etsy` (loopback only). The negatives: a hero that was
never judged, a hero that fails, and a certified set that was superseded all refuse with
zero Etsy requests.

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


def _chain():
    """certify -> assets.build -> listing.seo, through the real handlers. Returns a db path."""
    key = "full"
    if key not in _BUILT:
        path = os.path.join(_TMP, f"{key}.sqlite")
        db = Database(f"sqlite:///{path}")
        db.create_all()
        Registry(db).seed_defaults()
        snap = FX.snapshot()
        with db.session() as s:
            s.add(EtsyTaxonomySnapshot(sha256="fixture", node_count=len(snap["nodes"]),
                                       nodes=snap["nodes"], properties=snap["properties"]))
        cir = pipeline._engineered_cir(SLUG)
        job = _run(db, "quality_director", "gate.certify", {"cir": cir.to_dict()})
        assert job.status is JobStatus.DONE and job.outputs.get("granted"), job.outputs
        with db.session() as s:
            rh = s.scalar(select(PatternVersion)).release_hash
        job = _run(db, "publishing", "assets.build",
                   {"slug": SLUG, "version": cir.version, "release": rh,
                    "rebuild": "disclosed"})
        assert job.status is JobStatus.DONE, job.last_error
        job = _run(db, "listing", "listing.seo",
                   {"slug": SLUG, "version": cir.version, "release": rh, "price_cad": 9.5,
                    "category": "baby_blanket"})
        assert job.status is JobStatus.DONE and job.outputs["ok"], job.outputs
        db.engine.dispose()
        _BUILT[key] = (path, cir.version, rh)
    path, version, rh = _BUILT[key]
    copy = os.path.join(_TMP, f"{key}-{time.time_ns()}.sqlite")
    shutil.copy(path, copy)
    return copy, version, rh


def _profile(db) -> ListingSearchProfile:
    with db.session() as s:
        row = s.scalar(select(ListingSearchProfile).where(
            ListingSearchProfile.product_slug == SLUG))
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


def _grant(db, version, rh) -> int:
    from unittest.mock import patch

    from brambleloop.ops import publication_authority as pa

    with patch.dict(os.environ, {"BRAMBLELOOP_OPS_TOKEN": OWNER_TOKEN,
                                 "BRAMBLELOOP_PUBLISH_AUTHORISED": "1"}):
        return _approve(db, pa, version, rh)


def _approve(db, pa, version, rh) -> int:
    content = pa.snapshot(db, SLUG, version, rh)
    return pa.approve(db, authorization=OWNER_TOKEN, slug=SLUG, version=version, release=rh,
                      expected_digest=pa.digest(content),
                      reason="fixture: owner reviewed this release")["approval_id"]


def _creates(fake) -> list:
    return [r for r in fake.requests if r["operation"] == "createDraftListing"]


# ---------------------------------------------------------------------------- the merits

def test_certify_assets_seo_grant_publish_creates_exactly_one_draft_with_no_forced_verdict():
    path, version, rh = _chain()
    db = Database(f"sqlite:///{path}")
    row = _profile(db)
    # listing.seo judged the hero on the certified disclosed set and wrote PASS back, with
    # the evidence it used, bound to this release.
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
    assert cert["bound_fingerprint"] == row.fingerprint
    payload = etsy_ops.certified_payload(db, SLUG, version)
    assert payload.taxonomy_id == row.taxonomy_id

    with FakeEtsy() as fake, _owner_and_fake(fake):
        grant = _grant(db, version, rh)
        job = _run(db, "store_operator", "store.publish",
                   {"slug": SLUG, "version": version, "release": rh},
                   phase=Phase.LIMITED_PRODUCTION)
        assert job.status is JobStatus.DONE, job.last_error
        assert job.outputs.get("published") is True, job.outputs
        assert len(_creates(fake)) == 1, [r["operation"] for r in fake.requests]
        lid = job.outputs["etsy_listing_id"]
        assert fake.listings[lid]["state"] == "draft"
        assert int(fake.listings[lid]["taxonomy_id"]) == row.taxonomy_id
        assert len(fake.images[lid]) == 3
    with db.session() as s:
        listing = s.scalar(select(Listing).where(Listing.product_slug == SLUG))
        assert str(listing.etsy_listing_id) == str(lid)
    assert grant
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
