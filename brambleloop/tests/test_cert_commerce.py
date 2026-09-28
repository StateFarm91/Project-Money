"""Certification I: a certified catalogue product through the commerce chain, never published.

compile -> certify -> listing.draft -> assets.build -> pricing.position -> listing.seo ->
launch.plan -> marketing.schedule -> store.publish, run by the real worker on a temp file
database, with the network refused and no model or Etsy credential in the environment.

Past shadow, `store.publish` is exercised with the Etsy client replaced by a stub that
refuses nothing and raises the moment an upload would be attempted, so the test can observe
how far the handler got without anything leaving the process.

Run: cd brambleloop && $PY tests/test_cert_commerce.py
"""
from __future__ import annotations

import io
import os
import socket
import sys
import tempfile
import time
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

_TMP = tempfile.mkdtemp(prefix="cert_commerce_")
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")
os.environ.pop("BRAMBLELOOP_PUBLISH_AUTHORISED", None)
for _k in list(os.environ):
    if _k.startswith(("ANTHROPIC_API", "ETSY", "OPENAI", "REPLICATE", "FAL_", "GEMINI",
                      "GOOGLE_API", "STABILITY", "BRAMBLELOOP_IMAGE_KEY")):
        os.environ.pop(_k)


def _no_network(*_a, **_k):
    raise OSError("network refused by the certification harness")


socket.socket.connect = _no_network  # type: ignore[assignment]
socket.create_connection = _no_network  # type: ignore[assignment]
socket.getaddrinfo = _no_network  # type: ignore[assignment]

import pypdf  # noqa: E402
from sqlalchemy import desc, select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (AuditLog, Job, JobStatus, Listing, PatternVersion,  # noqa: E402
                                     Phase, Product)
from brambleloop.products import builder as flat  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: E402  (registers handlers)
from brambleloop.runtime.worker import Worker  # noqa: E402

SLUG = None  # set by the chain
_STATE: dict = {}


class Spy:
    def __init__(self, module, name: str, replacement=None):
        self.module, self.name = module, name
        self.original = getattr(module, name)
        self.calls: list = []

        def wrapper(*a, **k):
            self.calls.append((a, k))
            if replacement is not None:
                return replacement(*a, **k)
            return self.original(*a, **k)

        setattr(module, name, wrapper)

    def restore(self) -> None:
        setattr(self.module, self.name, self.original)


def _drain(w: Worker, limit: int = 400) -> None:
    for _ in range(limit):
        if not w.run_once():
            return
    raise AssertionError("queue did not drain")


def chain() -> dict:
    """Compile the gauge-qualified Cloudline fixture; publication gates stay unchanged."""
    if _STATE:
        return _STATE
    from brambleloop.gates import policy

    cwd = os.getcwd()
    os.chdir(_TMP)
    try:
        db = Database(f"sqlite:///{_TMP}/commerce.db")
        db.create_all()
        Registry(db).seed_defaults()
        cir = flat.for_slug("cloudline-baby-blanket")
        ai_spy = Spy(policy, "check_ai_disclosure")
        JobQueue(db).enqueue("validator", "cir.compile", {"cir": cir.to_dict()},
                             idempotency_key="cert-commerce-compile")
        w = Worker(db, "cert-commerce", phase=Phase.SHADOW, lease_seconds=900)
        _drain(w)
        ai_spy.restore()
        _STATE.update(db=db, cir=cir, slug=cir.slug, version=cir.version,
                      ai_disclosure_calls=list(ai_spy.calls))
    finally:
        os.chdir(cwd)
    return _STATE


def _jobs(db, job_type):
    with db.session() as s:
        rows = list(s.scalars(select(Job).where(Job.job_type == job_type).order_by(Job.id)))
        for r in rows:
            s.expunge(r)
        return rows


def _pv(db, slug, version):
    with db.session() as s:
        p = s.scalar(select(Product).where(Product.slug == slug))
        pv = s.scalar(select(PatternVersion).where(PatternVersion.product_id == p.id,
                                                   PatternVersion.version == version))
        s.expunge(pv)
        return pv


def _listing(db, slug, version):
    with db.session() as s:
        row = s.scalar(select(Listing).where(Listing.product_slug == slug,
                                             Listing.version == version))
        s.expunge(row)
        return row


# ---- the chain -----------------------------------------------------------

def test_the_chain_certifies_prices_drafts_and_refuses_to_publish():
    st = chain()
    db = st["db"]
    for jt in ("cir.compile", "gate.certify", "listing.draft", "assets.build",
               "pricing.position", "listing.seo"):
        rows = _jobs(db, jt)
        assert rows and all(r.status is JobStatus.DONE for r in rows), (
            jt, [(r.status.value, (r.last_error or "")[:120]) for r in rows])
    pv = _pv(db, st["slug"], st["version"])
    assert pv.certified and pv.certificate["granted"] and len(pv.release_hash) == 64
    assert _listing(db, st["slug"], st["version"]).state == "draft"
    pubs = _jobs(db, "store.publish")
    assert pubs and all(p.status is JobStatus.DEAD
                        and p.last_error.startswith("capability not enabled") for p in pubs)


def test_the_certificate_carries_the_platform_policy_stamp():
    """#39: the certificate records which reading of Etsy's rules it was issued under."""
    from brambleloop.gates.platform_policy import POLICY_SOURCES, freshness

    st = chain()
    cert = _pv(st["db"], st["slug"], st["version"]).certificate
    stamp = cert.get("platform_policy")
    assert isinstance(stamp, dict) and stamp.get("platform") == "etsy", cert.keys()
    f = freshness(st["db"])
    # Independent: on a fresh database no policy page has been read, and the stamp says so.
    assert sorted(stamp["unread_sources"]) == sorted(f["never_checked"])
    assert stamp["certified_against_current_policy"] is f["all_fresh"]
    assert len(f["never_checked"]) == len(POLICY_SOURCES)
    assert cert.get("policy_version"), "our own rule version is missing from the certificate"


def test_a_recorded_policy_reading_is_stamped_on_the_next_certificate():
    from brambleloop.gates import platform_policy as pp
    from brambleloop.gates.certificate import certify

    st = chain()
    db = st["db"]
    source = sorted(pp.POLICY_SOURCES)[0]
    pp.record_page_reading(db, source=source, text="cert harness page text " * 20,
                           read_by="cert-harness")
    stamp = pp.policy_stamp(db)
    assert source in stamp["sources"] and source not in stamp["unread_sources"], stamp
    cert = certify(st["cir"], platform_policy=stamp)
    assert cert.to_dict()["platform_policy"]["sources"][source] == stamp["sources"][source]


def test_pricing_fees_come_from_the_fee_schedule_and_the_literals_agree():
    from brambleloop.commerce import fee_schedule as FS
    from brambleloop.commerce import pricing as P
    from brambleloop.integrations import etsy as E
    from brambleloop.scale import target as T

    st = chain()
    job = _jobs(st["db"], "pricing.position")[0]
    out = job.outputs
    price = out["price_cad"]
    # Independent arithmetic from the fee schedule's claims alone.
    listing_cad = FS.LISTING.amount / P.ASSUMED_USD_PER_CAD
    expected_fees = (price * FS.TRANSACTION.rate + price * FS.PAYMENT_PROCESSING.rate
                     + FS.PAYMENT_PROCESSING.amount + listing_cad / 10.0)
    assert abs((price - expected_fees) - out["net_cad"]) < 0.01, (price, expected_fees, out)
    assert FS.TRANSACTION.quotable and FS.PAYMENT_PROCESSING.quotable
    assert FS.PAYMENT_PROCESSING.currency == "CAD"
    # The literals that still live outside the schedule must say the same thing.
    assert T.TRANSACTION_FEE_RATE == FS.TRANSACTION.rate
    assert T.PAYMENT_PROCESSING_RATE == FS.PAYMENT_PROCESSING.rate
    assert T.PAYMENT_PROCESSING_FLAT_CAD == FS.PAYMENT_PROCESSING.amount
    assert T.LISTING_FEE_USD == FS.LISTING.amount == E.LISTING_FEE_USD
    assert T.USD_PER_CAD == P.ASSUMED_USD_PER_CAD
    fees = T.fees_on(price, 1)
    take = FS.take_rate(price)
    assert abs((fees.transaction_cad + fees.processing_cad) - take["total_cad"]) <= 0.01, (fees, take)


def test_the_ai_disclosure_error_fires_only_when_owed_and_absent():
    from brambleloop.gates import platform_policy as pp
    from brambleloop.gates.policy import ERROR, ListingDraft, check_listing

    st = chain()
    lst = _listing(st["db"], st["slug"], st["version"])
    owed = pp.classify(product_class=pp.AI_ASSISTED_DESIGN, assets=[])
    not_owed = pp.classify(product_class=pp.SELLER_DESIGNED_DIGITAL, assets=[])

    def codes(description, cls):
        d = ListingDraft(title=lst.title, description=description, tags=list(lst.tags),
                         price_cad=lst.price_cad)
        return {f.code for f in check_listing(d, classification=cls) if f.severity == ERROR}

    sentence = pp.DISCLOSURES["ai_assisted_design"]
    assert "POLICY_AI_DISCLOSURE_MISSING" in codes(lst.description.replace(sentence, ""), owed)
    assert "POLICY_AI_DISCLOSURE_MISSING" not in codes(lst.description + "\n\n" + sentence, owed)
    assert "POLICY_AI_DISCLOSURE_MISSING" not in codes(lst.description, not_owed)


def test_the_chain_checks_its_listing_for_the_ai_disclosure_it_owes():
    """The chain's own copy says 'developed with AI assistance', so the ai_assisted_design
    disclosure is owed. listing.seo calls check_listing without a classification, so the
    ERROR can never fire on the chain, and the drafted listing does not carry the sentence."""
    from brambleloop.gates import platform_policy as pp
    from brambleloop.gates.policy import ListingDraft, check_listing

    st = chain()
    lst = _listing(st["db"], st["slug"], st["version"])
    assert "AI assistance" in lst.description, "copy no longer self-declares AI assistance"
    owed = pp.classify(product_class=pp.AI_ASSISTED_DESIGN, assets=[])
    errors = [f.code for f in check_listing(
        ListingDraft(title=lst.title, description=lst.description, tags=list(lst.tags),
                     price_cad=lst.price_cad), classification=owed) if f.is_error]
    assert st["ai_disclosure_calls"], (
        "gates.policy.check_ai_disclosure was never called on the chain; the drafted listing "
        f"would fail it with {errors}")
    assert not errors, errors


def test_store_publish_refuses_in_shadow_before_touching_etsy_storage_or_hashes():
    from brambleloop.core import artifacts
    from brambleloop.integrations import etsy

    st = chain()
    db = st["db"]
    spies = [Spy(etsy, "EtsyClient"), Spy(pipeline, "check_pdf_hashes"),
             Spy(artifacts.ArtifactStore, "put")]
    try:
        JobQueue(db).enqueue("store_operator", "store.publish",
                             {"slug": st["slug"], "version": st["version"]},
                             idempotency_key="cert-shadow-publish")
        w = Worker(db, "cert-shadow", phase=Phase.SHADOW, job_types=["store.publish"])
        assert w.run_once()
    finally:
        for s in spies:
            s.restore()
    job = [j for j in _jobs(db, "store.publish") if j.idempotency_key == "cert-shadow-publish"][0]
    assert job.status is JobStatus.DEAD and "SHADOW" in job.last_error, job.last_error
    assert not any(s.calls for s in spies), [(s.name, len(s.calls)) for s in spies]


# ---- past shadow, with the Etsy client stubbed ---------------------------

class _Reached(Exception):
    pass


class _StubClient:
    instances: list = []

    def __init__(self, *a, **k):
        _StubClient.instances.append(k)

    def refusal(self):
        return None

    def publish(self, **k):
        raise _Reached("upload reached")

    def attach_file(self, *a, **k):
        raise _Reached("attach reached")


_MISSING_NAMES = ("_load_cir", "build_twin")


def _publish_past_shadow(db, *, key: str, inputs: dict, render_patch=None, shim: bool = True):
    """Run one store.publish at LIMITED_PRODUCTION with a stub client and parity forced to
    pass; return (job, audits for this job, whether an upload was reached).

    `shim`: `pipeline.handle_store_publish` calls `_load_cir` and `build_twin`, neither of
    which exists in `runtime.pipeline` (see the test below that runs without the shim). To
    exercise the hash check behind that crash, the test injects the two names from the
    modules that define them for the duration of one job, and removes them afterwards."""
    from brambleloop.cir import twin as twin_mod
    from brambleloop.integrations import etsy
    from brambleloop.publish import pdf as pdf_mod
    from brambleloop.runtime import release as release_mod

    injected = []
    if shim:
        for name, value in (("_load_cir", release_mod._load_cir),
                            ("build_twin", twin_mod.build_twin)):
            if not hasattr(pipeline, name):
                setattr(pipeline, name, value)
                injected.append(name)
    reached = []
    orig_client, orig_creds = etsy.EtsyClient, etsy.Credentials.from_env
    etsy.EtsyClient = _StubClient
    etsy.Credentials.from_env = staticmethod(lambda *a, **k: None)
    parity = Spy(pipeline, "_listing_parity",
                 replacement=lambda ctx: {"verdict": "pass", "blocks_release": False,
                                          "why": "forced by cert harness", "dimensions": {}})
    # The gates added after parity (the #126 search grid and the release-chain gates) are
    # forced the same way parity is: each is proven to block in its own certification file
    # (test_cert_publish_gates), and what this file tests is the path behind them -- the
    # PDF hash check and the upload. Forcing only parity would make these tests measure
    # whether a grid tournament has been judged, which nothing here is about.
    from brambleloop.creative import preengineering
    grid = Spy(preengineering, "release_grid_verdict",
               replacement=lambda db, slug: {"cleared": True, "why": "forced by cert harness"})
    gates = Spy(pipeline, "_release_gates",
                replacement=lambda ctx: {"blocks_release": False, "reasons": [],
                                         "forced": "cert harness"})
    # FB-1 B (F-524): the certified listing images are read after the release gates and
    # before anything is stored or sent, and are proven to refuse on a missing or unreadable
    # frame in tests/test_etsy_readback_observe.py. Forced here like the gates above, so this
    # file keeps measuring the hash check and the upload behind them.
    from brambleloop.runtime import etsy_ops
    images = Spy(etsy_ops, "certified_images",
                 replacement=lambda *a, **k: {"images": [("f-1.png", b"\x89PNG-cert")],
                                              "order": [], "record_id": None,
                                              "problems": []})
    render = Spy(pdf_mod, "build_pattern_pdf", replacement=render_patch) if render_patch else None
    # Earlier publish attempts in this file failed into retry backoff; once their backoff
    # elapses the worker would claim one of them instead of this job. Park them.
    with db.session() as s:
        for other in s.scalars(select(Job).where(
                Job.job_type == "store.publish",
                Job.status.in_([JobStatus.PENDING, JobStatus.FAILED]))):
            other.status = JobStatus.CANCELLED
        s.commit()
    try:
        JobQueue(db).enqueue("store_operator", "store.publish", inputs, idempotency_key=key)
        w = Worker(db, f"cert-{key}", phase=Phase.LIMITED_PRODUCTION, job_types=["store.publish"])
        try:
            assert w.run_once()
        except _Reached:
            reached.append(True)
    finally:
        etsy.EtsyClient, etsy.Credentials.from_env = orig_client, orig_creds
        parity.restore()
        grid.restore()
        gates.restore()
        images.restore()
        if render:
            render.restore()
        for name in injected:
            delattr(pipeline, name)
    job = [j for j in _jobs(db, "store.publish") if j.idempotency_key == key][0]
    with db.session() as s:
        audits = [(a.action, dict(a.detail or {})) for a in s.scalars(
            select(AuditLog).where(AuditLog.job_id == job.id).order_by(AuditLog.id))]
    reached = reached or ["upload reached" in (job.last_error or "")]
    return job, audits, bool(reached[0])


def test_past_shadow_publish_runs_at_all_without_a_test_shim():
    """Past shadow, with a client that refuses nothing and parity passing, store.publish must
    reach its PDF hash check. It crashes first: `_load_cir` and `build_twin` are not defined
    in runtime/pipeline.py, so every non-shadow publish dies with NameError (and, being a
    generic exception, is retried as if transient)."""
    st = chain()
    job, audits, reached = _publish_past_shadow(
        st["db"], key="cert-pub-noshim",
        inputs={"slug": st["slug"], "version": st["version"]}, shim=False)
    actions = [a for a, _d in audits]
    assert "store.pdf_hash_verified" in actions, (actions, (job.last_error or "")[:200])


def test_past_shadow_an_identical_rerender_passes_the_hash_check_and_reaches_upload():
    st = chain()
    job, audits, reached = _publish_past_shadow(
        st["db"], key="cert-pub-ok", inputs={"slug": st["slug"], "version": st["version"]})
    actions = [a for a, _d in audits]
    assert "store.pdf_hash_verified" in actions, (actions, job.last_error)
    assert reached, (job.status, (job.last_error or "")[:300])


def test_past_shadow_a_drifted_rerender_is_refused_before_any_upload():
    st = chain()
    from brambleloop.publish import pdf as pdf_mod

    real = pdf_mod.build_pattern_pdf

    def drifted(*a, **k):
        doc = real(*a, **k)
        if k.get("terminology") == "UK":
            return types.SimpleNamespace(pdf_bytes=doc.pdf_bytes + b"\n%cert-drift\n",
                                         pages=doc.pages)
        return doc

    job, audits, reached = _publish_past_shadow(
        st["db"], key="cert-pub-drift", inputs={"slug": st["slug"], "version": st["version"]},
        render_patch=drifted)
    assert not reached
    refused = [d for a, d in audits if a == "store.publish_refused"]
    assert refused and refused[-1].get("code") == "PDF_HASH_DRIFT", audits
    assert "PDF_HASH_DRIFT" in (job.last_error or "")
    assert job.status is JobStatus.DEAD, (
        f"a PermanentError drift is {job.status.value} (attempts {job.attempts}/"
        f"{job.max_attempts}), so it will be re-rendered and refused again")


def test_past_shadow_a_release_with_no_certified_hash_is_refused():
    st = chain()
    job, audits, reached = _publish_past_shadow(
        st["db"], key="cert-pub-nohash",
        inputs={"slug": st["slug"], "version": st["version"], "release": "0" * 64})
    assert not reached
    refused = [d for a, d in audits if a == "store.publish_refused"]
    assert refused and "no assets.built hash" in refused[-1].get("reason", ""), audits


def test_a_physically_calibrated_release_can_still_be_published():
    """assets.build renders with the stored calibration; store.publish re-renders without
    it. Once a tester sample lands, the certified PDF and the upload render disagree on the
    yardage lines, and every publish of that product is refused as PDF_HASH_DRIFT."""
    from brambleloop.core.models import PhysicalTest

    st = chain()
    db = st["db"]
    cir = st["cir"]
    with db.session() as s:
        s.add(PhysicalTest(product_slug=cir.slug, version=cir.version, tester_ref="cert-t",
                           passed=True,
                           measured={"factor": 1.25, "yarn": cir.materials[0].name,
                                     "stitch": cir.gauge.stitch_type, "size_agrees": True}))
        s.commit()
    pv = _pv(db, cir.slug, cir.version)
    JobQueue(db).enqueue("publishing", "assets.build",
                         {"slug": cir.slug, "version": cir.version, "release": pv.release_hash,
                          "rebuild": "cert-calibrated"},
                         idempotency_key="cert-assets-calibrated")
    cwd = os.getcwd()
    os.chdir(_TMP)
    try:
        w = Worker(db, "cert-cal", phase=Phase.SHADOW, job_types=["assets.build"])
        assert w.run_once()
    finally:
        os.chdir(cwd)
    built = [j for j in _jobs(db, "assets.build") if j.idempotency_key == "cert-assets-calibrated"][0]
    assert built.status is JobStatus.DONE and built.outputs.get("calibrated"), built.outputs
    job, audits, reached = _publish_past_shadow(
        db, key="cert-pub-cal", inputs={"slug": cir.slug, "version": cir.version,
                                        "release": pv.release_hash})
    refused = [d.get("reason", "")[:200] for a, d in audits if a == "store.publish_refused"]
    assert reached, f"calibrated release refused at upload: {refused}"


def test_the_shipped_us_and_uk_documents_pass_the_deliverable_qa():
    """The stored files from assets.build, held to tests/test_deliverable_qa.py's checks."""
    import tests.test_deliverable_qa as qa
    from brambleloop.cir.compiler import compile_cir
    from brambleloop.cir.twin import build_twin
    from brambleloop.publish import abbreviations as ab
    from brambleloop.publish import pdf as pdf_mod

    st = chain()
    db, cir = st["db"], st["cir"]
    pv = _pv(db, cir.slug, cir.version)
    with db.session() as s:
        row = s.scalar(select(AuditLog).where(AuditLog.action == "assets.built",
                                              AuditLog.artifact == f"{cir.slug}@{cir.version}")
                       .order_by(AuditLog.id))
        stored = dict(row.detail["pdfs"])
    assert set(stored) == {"US", "UK"}, stored
    from brambleloop.core.artifacts import ArtifactStore

    store = ArtifactStore()
    result = compile_cir(cir)
    twin = build_twin(cir, result)
    for t in pdf_mod.TERMINOLOGIES:
        data = store.get(stored[t]["sha256"])
        import hashlib

        assert hashlib.sha256(data).hexdigest() == stored[t]["sha256"], t
        doc = pdf_mod.build_pattern_pdf(cir, twin=twin, terminology=t,
                                        released_on=pv.created_at.date())
        assert doc.pdf_bytes == data, f"{t}: the QA render is not the shipped file"
        text = " ".join("\n".join(p.extract_text() for p in
                                  pypdf.PdfReader(io.BytesIO(data)).pages).split())
        assert doc.pages > 1 and doc.terminology == t
        assert f"{t} terms" in text, t
        assert all(p.startswith("PDF_CABLE_DIRECTION_UNSPECIFIED") for p in doc.problems), doc.problems
        key = {e.token for e in ab.stitch_key(doc.prose, t)}
        assert not ab.undefined_tokens(doc.prose, t, defined=key), (t, key)
    assert stored["US"]["sha256"] != stored["UK"]["sha256"]
    # And the QA suite's own checks, where they take no arguments, over the same renderer.
    failures = []
    for name in ("test_both_terminologies_render_for_every_shippable_design",
                 "test_every_abbreviation_in_the_instructions_is_defined_in_the_document",
                 "test_the_colour_key_describes_the_chart_that_was_actually_printed",
                 "test_the_chart_shows_the_repeat_the_written_instructions_use",
                 "test_no_chart_cell_is_smaller_than_the_brand_allows_type_to_be"):
        fn = getattr(qa, name, None)
        if fn is None:
            failures.append(f"{name}: missing from test_deliverable_qa")
            continue
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            failures.append(f"{name}: {type(e).__name__}: {str(e)[:200]}")
    assert not failures, failures


if __name__ == "__main__":
    t0 = time.monotonic()
    fails = 0
    tests = [(n, f) for n, f in list(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        try:
            fn()
            print("OK  ", name, flush=True)
        except Exception as e:  # noqa: BLE001
            fails += 1
            print("FAIL", name, f"{type(e).__name__}: {str(e)[:900]}", flush=True)
    print(f"{len(tests) - fails}/{len(tests)} passed in {time.monotonic() - t0:.0f}s")
    sys.exit(1 if fails else 0)
