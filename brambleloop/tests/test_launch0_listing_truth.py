"""Launch-0 listings name their own product, at their own price, and the first-customer gate
can clear on evidence (audit findings PT-01, PT-02, PT-04, PT-06, PT-11, PT-12, PT-13).

The real `gate.certify` -> `pricing.position` -> `listing.seo` handlers on a temporary sqlite
database for every one of the five Launch-0 CIR slugs, with the recorded Etsy taxonomy shape
stored as the snapshot. Every outbound socket is refused; no model, image provider or spend.

What was wrong, each line a test below:

* PT-01: a basket and the coaster set were titled and tagged "Mosaic Blanket" and filed under
  Blankets & Afghans, because a slug the radar pool did not name defaulted to `mosaic_blanket`.
* PT-04: the coaster set and the baskets went out at CA$14 (plan CA$4.00 / CA$6.50), the
  blanket at CA$8.91 (plan CA$7.50): `launch0.price_plan` was never read.
* PT-02: the first-customer gate could never clear: no calibration reached its twin, and its
  imagery check never read the disclosed set that is the Launch-0 imagery.
"""
from __future__ import annotations

import os
import socket
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
_TMP = tempfile.mkdtemp(prefix="launch0_listing_truth_")
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")


def _refuse(*_a, **_k):
    raise OSError("network refused: this test makes no outbound connection")


socket.socket.connect = _refuse
socket.create_connection = _refuse

from sqlalchemy import select  # noqa: E402

import fixtures_etsy_taxonomy as FX  # noqa: E402
from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (  # noqa: E402
    AuditLog, EtsyTaxonomySnapshot, Job, JobStatus, Listing, ListingSearchProfile,
    PatternVersion, Phase, PhysicalTest, Product,
)
from brambleloop.gates import first_customer as FC  # noqa: E402
from brambleloop.products import launch0 as L  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import pipeline, release  # noqa: E402,F401
from brambleloop.runtime.worker import Worker  # noqa: E402

BUILDS = ("basket_small", "basket_medium", "basket_large", "hexagon_coasters",
          "cloudline_blanket")
PLAN_PRICE = {"basket": 6.50, "coaster": 4.00, "blanket": 7.50}
_STATE: dict = {}


def _db(name: str) -> Database:
    db = Database(f"sqlite:///{tempfile.mkdtemp(dir=_TMP)}/{name}.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    snap = FX.snapshot()
    with db.session() as s:
        s.add(EtsyTaxonomySnapshot(sha256="fixture", node_count=len(snap["nodes"]),
                                   nodes=snap["nodes"], properties=snap["properties"]))
    return db


def _run(db, agent: str, job_type: str, inputs: dict, key: str):
    job = JobQueue(db).enqueue(agent, job_type, inputs, idempotency_key=key, priority=0)
    Worker(db, f"w-{key}", phase=Phase.SHADOW, job_types=[job_type],
           lease_seconds=900).run_once()
    with db.session() as s:
        row = s.get(Job, job.id)
        s.expunge(row)
        return row


CHAIN = ("gate.certify", "listing.draft", "assets.build", "pricing.position", "listing.seo")


def _chain() -> Database:
    """certify -> assets.build -> pricing.position -> listing.seo for all five, once.

    The real handlers enqueue each other; the worker is limited to the stages up to the
    listing draft, so nothing downstream (launch plan, publication) runs.
    """
    if "chain" not in _STATE:
        db = _db("chain")
        for build in BUILDS:
            cir = L.cir_for(build)
            JobQueue(db).enqueue("quality_director", "gate.certify", {"cir": cir.to_dict()},
                                 idempotency_key=f"cert-{build}", priority=0)
        worker = Worker(db, "chain", phase=Phase.SHADOW, job_types=list(CHAIN),
                        lease_seconds=900)
        for _ in range(200):
            if not worker.run_once():
                break
        with db.session() as s:
            stuck = [(j.job_type, j.status.value, (j.last_error or "")[-300:])
                     for j in s.scalars(select(Job).where(Job.job_type.in_(CHAIN)))
                     if j.status is not JobStatus.DONE]
        assert not stuck, stuck
        _STATE["chain"] = db
    return _STATE["chain"]


def _listing(db, slug: str) -> Listing:
    with db.session() as s:
        row = s.scalar(select(Listing).where(Listing.product_slug == slug))
        assert row is not None, f"no listing drafted for {slug}"
        s.expunge(row)
        return row


# ---- PT-01: every Launch-0 listing names its own product -------------------------------

def test_every_launch0_slug_drafts_a_title_tags_and_category_naming_its_own_product():
    db = _chain()
    snap = FX.snapshot()
    from brambleloop.commerce import category as C

    for build in BUILDS:
        cir = L.cir_for(build)
        identity = L.listing_identity(cir.slug)
        assert identity is not None, cir.slug
        row = _listing(db, cir.slug)
        title, tags = row.title, list(row.tags or [])
        # Its own noun is in the title, and no other product type is anywhere in the copy.
        assert identity.kind in title.lower(), (cir.slug, title)
        assert FC.product_type_findings(cir, title=title, tags=tags) == [], (title, tags)
        assert "mosaic" not in title.lower(), title
        assert not [t for t in tags if "mosaic" in t or "blanket" in t] or identity.kind == \
            "blanket", tags
        # The category node is the one its own record intends, and the node names it.
        with db.session() as s:
            profile = s.scalar(select(ListingSearchProfile).where(
                ListingSearchProfile.product_slug == cir.slug))
            taxonomy_id = profile.taxonomy_id
        expected = C.choose(snap, identity.etsy_category)
        assert expected.status == C.CHOSEN and taxonomy_id == expected.taxonomy_id, \
            (cir.slug, taxonomy_id, expected.to_dict())
        blanket_node = C.choose(snap, "mosaic_blanket").taxonomy_id
        if identity.kind != "blanket":
            assert taxonomy_id != blanket_node, (cir.slug, taxonomy_id)
        path = " ".join(expected.path_names).lower()
        assert identity.kind in path or identity.etsy_category in path, (cir.slug, path)


def test_the_listing_audit_records_the_product_record_it_was_drafted_from():
    db = _chain()
    with db.session() as s:
        rows = [r.detail for r in s.scalars(select(AuditLog).where(
            AuditLog.action == "listing.seo_drafted"))]
    sources = {d["product_record"]["source"] for d in rows}
    assert sources == {"products.launch0:nursery-nesting-baskets",
                       "products.launch0:hexagon-coaster-set",
                       "products.launch0:cloudline-baby-blanket"}, sources
    assert all(d["product_record"]["launch0"] for d in rows)


def test_an_undescribed_product_is_refused_rather_than_given_a_default_type():
    """No default product type ever: pricing and listing.seo both refuse an unknown kind."""
    assert release._product_record("zz-undescribed-object") is None
    db = _db("unknown")
    job = _run(db, "pricing", "pricing.position",
               {"slug": "zz-undescribed-object", "version": "1.0.0", "release": ""}, "p")
    assert job.status is JobStatus.DONE and job.outputs["code"] == release.UNKNOWN_PRODUCT
    with db.session() as s:
        assert not list(s.scalars(select(Job).where(Job.job_type == "listing.seo")))
    # A certified CIR under a slug nobody described: the listing is refused, not defaulted.
    cir = L.cir_for("hexagon_coasters")
    from brambleloop.cir.model import CIR

    stray = CIR.from_dict({**cir.to_dict(), "slug": "zz-undescribed-object"})
    job = _run(db, "quality_director", "gate.certify", {"cir": stray.to_dict()}, "c")
    assert job.outputs.get("granted"), job.outputs
    job = _run(db, "listing", "listing.seo",
               {"slug": stray.slug, "version": stray.version, "release": "",
                "price_cad": 4.0}, "s")
    assert job.outputs["ok"] is False
    assert any(release.UNKNOWN_PRODUCT in b for b in job.outputs["blocking"]), job.outputs
    with db.session() as s:
        assert s.scalar(select(Listing).where(Listing.product_slug == stray.slug)) is None


def test_claim_checks_refuse_a_product_type_or_fabric_the_cir_does_not_make():
    from brambleloop.cir.compiler import compile_cir
    from brambleloop.cir.twin import build_twin

    basket = L.cir_for("basket_small")
    twin = build_twin(basket, compile_cir(basket))
    desc = "A crochet basket pattern, worked in the round, as two PDFs."
    wrong = {"title": "Bread Basket | Crochet Pattern PDF | Market Mosaic Blanket",
             "description": desc, "tags": ["mosaic blanket", "basket crochet"],
             "price_cad": 6.5}
    check = FC.check_listing_claims(basket, twin, wrong)
    assert check.state == FC.FAIL and "LISTING_PRODUCT_TYPE_UNSUPPORTED" in check.detail, check
    # A tag alone naming another product fails too.
    tag_only = dict(wrong, title="Bread Basket | Crochet Pattern PDF", tags=["crochet throw"])
    assert FC.check_listing_claims(basket, twin, tag_only).state == FC.FAIL
    # A colourwork technique the one-colour-per-row fabric cannot make fails.
    mosaic = dict(wrong, title="Bread Basket | Crochet Pattern PDF", tags=["basket mosaic"])
    check = FC.check_listing_claims(basket, twin, mosaic)
    assert check.state == FC.FAIL and "LISTING_COLOURWORK_UNSUPPORTED" in check.detail, check
    right = dict(wrong, title="Bread Basket | Crochet Pattern PDF | Nursery",
                 tags=["basket crochet", "nursery basket"])
    assert FC.check_listing_claims(basket, twin, right).state == FC.PASS


def test_certify_examines_the_real_stored_listing_copy():
    db = _db("certify_copy")
    cir = L.cir_for("hexagon_coasters")
    with db.session() as s:
        s.add(Listing(product_slug=cir.slug, version=cir.version,
                      title="Hexagon Coaster Set | Crochet Pattern PDF | US and UK Terms",
                      description="A hexagon coaster pattern.", price_cad=4.0,
                      tags=["coaster crochet", "hexagon crochet"], state="draft"))
    _run(db, "quality_director", "gate.certify", {"cir": cir.to_dict()}, "c1")
    with db.session() as s:
        detail = s.scalar(select(AuditLog).where(AuditLog.action.in_(
            ["gate.certified", "gate.blocked"]))).detail
    assert detail["listing_examined"]["source"] == "stored Listing row", detail
    assert detail["listing_examined"]["title"].startswith("Hexagon Coaster Set")

    # A stored copy naming another product is refused and recorded, never attested.
    db = _db("certify_wrong_copy")
    with db.session() as s:
        s.add(Listing(product_slug=cir.slug, version=cir.version,
                      title="Hexagon Coaster Set | Crochet Pattern PDF | Mosaic Blanket",
                      description="x", price_cad=14.0, tags=["mosaic blanket"],
                      state="draft"))
    _run(db, "quality_director", "gate.certify", {"cir": cir.to_dict()}, "c2")
    with db.session() as s:
        refused = s.scalar(select(AuditLog).where(
            AuditLog.action == "gate.listing_copy_refused"))
        examined = s.scalar(select(AuditLog).where(AuditLog.action.in_(
            ["gate.certified", "gate.blocked"]))).detail["listing_examined"]
    assert refused is not None and refused.detail["findings"], "the refusal is recorded"
    assert examined["source"] == "products.launch0 listing identity", examined
    assert "blanket" not in examined["title"].lower()


# ---- PT-04: Launch-0 is priced from its own plan -----------------------------------------

def test_every_launch0_slug_is_priced_from_its_own_plan_with_the_basis_recorded():
    db = _chain()
    for build in BUILDS:
        cir = L.cir_for(build)
        kind = L.listing_identity(cir.slug).kind
        row = _listing(db, cir.slug)
        assert row.price_cad == PLAN_PRICE[kind], (cir.slug, row.price_cad)
        plan = L.launch_price(cir.slug)
        assert plan["price_cad"] == row.price_cad and plan["within_plan_band"]
        with db.session() as s:
            audit = s.scalar(select(AuditLog).where(
                AuditLog.action == "pricing.positioned", AuditLog.artifact == cir.slug))
        assert audit.detail["basis"].startswith("products.launch0.price_plan("), audit.detail
        assert audit.detail["band_cad"] == list(plan["band_cad"])


# ---- PT-11: one production entry path, under the Launch-0 slugs ---------------------------

def test_the_planner_routes_retired_concept_slugs_to_the_launch0_slugs():
    from brambleloop.publish import eligibility as E

    for legacy, record in L.LEGACY_DUPLICATES.items():
        assert legacy not in pipeline.ENGINEERED, legacy
        for target in record["superseded_by"]:
            cir = pipeline._engineered_cir(target)
            assert cir is not None and cir.slug == target, target
            assert target in L.launch_scope_slugs()
    db = _db("planner")
    job = _run(db, "crochet_engineer", "cir.draft", {"slug": "hexie-coaster-set"}, "d")
    assert job.outputs.get("retired_alias") and job.outputs["routed_to"] == [
        f"hexagon-coaster-set@{L.cir_for('hexagon_coasters').version}"], job.outputs
    with db.session() as s:
        compiles = [j.inputs["cir"]["slug"] for j in s.scalars(select(Job).where(
            Job.job_type == "cir.compile"))]
        routed = s.scalar(select(AuditLog).where(AuditLog.action == "cir.draft_routed"))
    assert compiles == ["hexagon-coaster-set"] and routed is not None
    # The retired slug is refused publication by name, whatever its certificate says.
    verdict = E.product_publication(db, "market-basket-trio", "1.1.0",
                                    first_customer=lambda *a, **k: [])
    assert E.RETIRED_DUPLICATE in [r["code"] for r in verdict["reasons"]], verdict


# ---- PT-06: one product's rebuilds do not hide another's disclosed set --------------------

def test_disclosed_last_asset_is_read_per_product_not_from_a_global_window():
    from brambleloop.publish import disclosed_listing as DL
    from brambleloop.visual.disclosed_render import RENDERER_VERSION

    db = _db("last_asset")
    for slug in ("market-basket-small", "cloudline-baby-blanket"):
        DL.record(db, {"slug": slug, "version": "1.1.0", "made": True,
                       "method_version": RENDERER_VERSION, "frames": []})
    for _ in range(60):
        DL.record(db, {"slug": "hexagon-coaster-set", "version": "1.1.0", "made": True,
                       "method_version": RENDERER_VERSION, "frames": []})
    for slug in ("market-basket-small", "cloudline-baby-blanket", "hexagon-coaster-set"):
        rec = DL.last_asset(db, slug=slug)
        assert rec is not None and rec["slug"] == slug, slug
    # A slug that is a prefix of another is not confused with it.
    assert DL.last_asset(db, slug="market-basket") is None


# ---- PT-02: the first-customer gate clears on evidence -------------------------------------

def _disclosed_release():
    """The blanket certified, its disclosed set filed by assets.build, copy and certificate."""
    if "disclosed" not in _STATE:
        from brambleloop.publish import disclosed_listing, release_gates

        db = _db("disclosed")
        cir = L.cir_for("cloudline_blanket")
        job = _run(db, "quality_director", "gate.certify", {"cir": cir.to_dict()}, "c")
        assert job.outputs.get("granted"), job.outputs
        with db.session() as s:
            rh = s.scalar(select(PatternVersion)).release_hash
        job = _run(db, "publishing", "assets.build",
                   {"slug": cir.slug, "version": cir.version, "release": rh,
                    "rebuild": "disclosed"}, "a")
        assert job.status is JobStatus.DONE, job.last_error
        with db.session() as s:
            s.add(Listing(product_slug=cir.slug, version=cir.version,
                          title="Cloudline Textured Baby Blanket | Crochet Pattern PDF",
                          description=("A worsted-weight baby blanket pattern.\n\n"
                                       + disclosed_listing.COPY_DISCLOSURE),
                          tags=["baby blanket crochet"], price_cad=7.5, state="draft"))
        verdict = release_gates.listing_set(db, slug=cir.slug, version=cir.version)
        assert verdict["certificate"]["valid"] is True, verdict["reasons"]
        _STATE["disclosed"] = (db, cir, rh)
    return _STATE["disclosed"]


def test_no_sample_blocks_on_physical_proof_and_a_bound_sample_clears_it():
    db, cir, _rh = _disclosed_release()
    gate = FC.gate_product(cir, db=db, version=cir.version)
    by_area = {c.area: c for c in gate.checks}
    assert by_area["gauge_and_size_claims"].state == FC.UNRESOLVED
    assert "no passed physical sample" in by_area["gauge_and_size_claims"].detail

    binding = FC.physical_binding(db, cir)
    now = datetime.now(timezone.utc)
    with db.session() as s:
        # A sample of another text binds nothing: still unresolved.
        s.add(PhysicalTest(product_slug=cir.slug, version=cir.version, tester_ref="t-old",
                           completed_at=now, passed=True,
                           measured={"content_hash": "0" * 64, "factor": 1.05,
                                     "yarn": "x", "stitch": "sc"}))
    gate = FC.gate_product(cir, db=db, version=cir.version)
    assert {c.area: c for c in gate.checks}["gauge_and_size_claims"].state == FC.UNRESOLVED
    with db.session() as s:
        s.add(PhysicalTest(product_slug=cir.slug, version=cir.version, tester_ref="t-1",
                           completed_at=now, passed=True,
                           measured={"content_hash": binding["content_hash"],
                                     "factor": 1.05, "yarn": "x", "stitch": "sc"}))
    try:
        gate = FC.gate_product(cir, db=db, version=cir.version)
        check = {c.area: c for c in gate.checks}["gauge_and_size_claims"]
        assert check.state == FC.PASS, check
        assert "gauge_and_size_claims" not in [c.area for c in gate.blocking]
    finally:
        with db.session() as s:
            for row in s.scalars(select(PhysicalTest)):
                s.delete(row)


def test_the_disclosed_set_and_its_certificate_make_imagery_pass():
    db, cir, _rh = _disclosed_release()
    imagery = {c.area: c for c in FC.gate_product(cir, db=db, version=cir.version).checks}
    assert imagery["imagery"].state == FC.PASS, imagery["imagery"]
    # Without the database (no evidence read) the gate stays where it was: unbuilt imagery.
    offline = {c.area: c for c in FC.gate_product(cir).checks}
    assert offline["imagery"].state == FC.UNVERIFIABLE
    # The publication path hands the gate the database.
    from brambleloop.publish import eligibility as E

    seen = {}

    def spy(c, **kw):
        seen.update(kw)
        return []

    E.product_publication(db, cir.slug, cir.version, first_customer=spy)
    assert seen.get("db") is db and seen.get("version") == cir.version


def test_a_certificate_bound_to_no_release_is_neither_filed_nor_served():
    """PT-13: an empty release hash no longer skips the binding."""
    from brambleloop.core.models import ListingSetCertificateRecord
    from brambleloop.publish import release_gates
    from brambleloop.runtime import etsy_ops

    db, cir, rh = _disclosed_release()
    assert etsy_ops.certified_frames(db, cir.slug, cir.version)["problems"] == []
    with db.session() as s:
        row = s.scalar(select(ListingSetCertificateRecord).where(
            ListingSetCertificateRecord.state == "valid"))
        row.release_hash = ""
    try:
        got = etsy_ops.certified_frames(db, cir.slug, cir.version, release=rh)
        assert any("bound to no release hash" in p for p in got["problems"]), got
        got = etsy_ops.certified_frames(db, cir.slug, cir.version)
        assert got["problems"], got
        imagery = FC.disclosed_imagery(db, cir.slug, cir.version)
        assert imagery["state"] == FC.FAIL and "no release hash" in imagery["detail"]
    finally:
        with db.session() as s:
            s.scalar(select(ListingSetCertificateRecord).where(
                ListingSetCertificateRecord.state == "valid")).release_hash = rh

    class _Cert:
        slug, version, frames = cir.slug, cir.version, ()

    out = release_gates._record_certificate(db, _Cert(), release_hash="", issue=True,
                                            rechecked=[])
    assert out["valid"] is False and "no release hash" in out["why"]


def test_a_listing_variant_other_than_the_sets_is_refused():
    """PT-13 / F-757: the listing's declared configuration is checked at listing-set certify."""
    from brambleloop.publish import disclosed_listing, listing_set as LS

    db, cir, _rh = _disclosed_release()
    rec = disclosed_listing.last_asset(db, slug=cir.slug)
    try:
        LS.certify_disclosed(slug=cir.slug, version=cir.version, rec=rec, images=[],
                             geometry={}, claims={}, policy_version="p", dimensions_ok=True,
                             listing_variant="colour=wine")
    except LS.ListingSetRefused as e:
        assert "F-757" in str(e)
    else:
        raise AssertionError("a listing declaring another configuration was certified")


# ---- PT-12: the alt text Etsy holds is read back -----------------------------------------

def test_read_back_compares_the_alt_text_etsy_holds():
    from brambleloop.runtime import etsy_ops

    class _Client:
        def __init__(self, held):
            self.held = held

        def get_listing_images(self, listing_id):
            return [{"rank": i + 1, "alt_text": a} for i, a in enumerate(self.held)]

    sent = ["Digital render. Frame one.", "Digital render. Frame two."]
    ok = etsy_ops.images_read_back(_Client(sent), "1", sent)
    assert ok["verified"] and ok["problems"] == []
    dropped = etsy_ops.images_read_back(_Client([sent[0], ""]), "1", sent)
    assert not dropped["verified"] and "rank 2 alt_text" in dropped["problems"][0]
    truncated = etsy_ops.images_read_back(_Client([sent[0][:10], sent[1]]), "1", sent)
    assert not truncated["verified"]

    class _Broken:
        def get_listing_images(self, listing_id):
            raise RuntimeError("timeout")

    broken = etsy_ops.images_read_back(_Broken(), "1", sent)
    assert not broken["verified"] and "read failed" in broken["problems"][0]


# ---- PT-14: the nursery statement no longer contradicts the product -------------------------

def test_the_fibre_statement_does_not_say_a_nursery_basket_will_be_mouthed():
    from brambleloop.intel import childrens as ch

    text = ch.STATEMENT_SET["fibre_and_care"].text
    assert "will be mouthed" not in text
    assert "washability is hygiene rather than convenience" in text


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                fails += 1
                print("FAIL", name, repr(e)[:600])
                traceback.print_exc()
    import shutil

    shutil.rmtree(_TMP, ignore_errors=True)
    sys.exit(1 if fails else 0)
