"""A child audience added by listing copy must reach the safety gate and package."""
import dataclasses
import os
import tempfile

import test_a1r_child_safety_core as harness
from brambleloop.agents.registry import Registry
from brambleloop.core.db import Database
from brambleloop.core.models import Listing, PatternVersion, Product
from brambleloop.gates.certificate import GAUGE_STANDARD
from brambleloop.products import inventory, launch0
from brambleloop.publish import eligibility, listing_package
from brambleloop.queue.durable import JobQueue
from brambleloop.runtime import listing_package_ops  # noqa: F401
from brambleloop.runtime.worker import Worker


def test_plural_child_audience_words_are_held_in_pdf_worker():
    adult = inventory._engineered("market-basket-small")
    for title in ("Basket for toddlers", "Basket for infants", "Basket for newborns",
                  "Basket for nurseries", "Basket for kids", "Basket for tots",
                  "Basket for preschoolers", "Basket for preemies"):
        changed = dataclasses.replace(adult, title=title)
        assert launch0.child_words_in(title), title
        assert launch0.childrens_decision_for(changed)[0] == launch0.UNDECIDED, title
        assert harness._refused(changed), title
    for title in ("For ages 2–4", "Suitable from 0 to 36 months", "For preschool",
                  "Perfect for 3 year olds", "For young ones", "For youth",
                  "For ages two to four", "For girls", "For boys", "For teens"):
        assert launch0.child_words_in(title), title
        assert harness._refused(dataclasses.replace(adult, title=title)), title
    for title in ("For adults age 25", "A basket for ages 18–30", "Everyday Storage Basket"):
        assert not launch0.child_words_in(title), (title, launch0.child_words_in(title))
    result = harness._assets_build_full(dataclasses.replace(adult, title="Basket for toddlers"))
    assert harness._held(result), result
    assert result["outputs"]["reason"] == "undecided", result


def test_persistent_listing_package_and_publish_verdict_hold_child_copy():
    with tempfile.TemporaryDirectory() as directory:
        old_dir = os.environ.get("BRAMBLELOOP_ARTIFACT_DIR")
        os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = directory + "/artifacts"
        try:
            url = f"sqlite:///{directory}/listing.sqlite"
            db = Database(url, scratch=True)
            db.create_all()
            Registry(db).seed_defaults()
            cir = inventory._engineered("market-basket-small")
            with db.session() as s:
                product = Product(slug=cir.slug, title=cir.title, status="certified")
                s.add(product)
                s.flush()
                s.add(PatternVersion(product_id=product.id, version=cir.version, certified=True,
                    cir_json=cir.to_dict(), release_hash="a" * 64,
                    certificate={"granted": True, "gauge_standard": GAUGE_STANDARD}))
                s.add(Listing(product_slug=cir.slug, version=cir.version, state="draft",
                    title="Baby Basket", description="A plain basket", tags=["storage"],
                    price_cad=5, release_hash="a" * 64))
            reopened = Database(url, scratch=True)
            for listing in ({"title": "Baby Basket", "tags": []},
                            {"title": "Basket", "description": "For toddlers", "tags": []},
                            {"title": "Basket", "tags": ["newborns"]},
                            {"title": "Basket", "tags": ["Βabies"]}):
                verdict = eligibility.product_publication(reopened, cir.slug, cir.version,
                    listing=listing, first_customer=lambda *_a, **_k: [])
                assert not verdict["publishable"], verdict
                assert any(r["code"] == eligibility.NAME_OUTRUNS_PATTERN and
                           "child audience" in r["why"] for r in verdict["reasons"]), verdict
            for value in (False, 0, "", {}):
                bad = {"title": "Storage Basket", "description": "plain", "tags": value}
                reasons = eligibility.name_truth(cir, bad)
                assert any("child audience: listing copy cannot be checked" in r
                           for r in reasons), (value, reasons)
            for title in ("For ages 2–4", "Suitable from 0 to 36 months", "For preschool",
                          "Perfect for 3 year olds", "For young ones", "For youth",
                  "For ages two to four", "For girls", "For boys", "For teens"):
                reasons = eligibility.name_truth(cir, {"title": title, "tags": []})
                assert any("child audience" in r for r in reasons), (title, reasons)
            JobQueue(reopened).enqueue("listing", "listing.package", {},
                                       idempotency_key="codex:a1:listing")
            assert Worker(reopened, "listing-child", job_types=["listing.package"]).run_once()
            package = listing_package.latest(reopened, cir.slug, cir.version)
            assert package and package["state"] == listing_package.BLOCKED, package
            assert package["identity"]["childrens_decision"][0] == launch0.UNDECIDED, package
            assert any(b["source"] == "childrens_decision" for b in package["blockers"]), package
            assert package["publishes"] is False
            # The activation gate must see malformed DB tags as malformed, not
            # split "baby" into a harmless-looking list of characters.
            from sqlalchemy import select
            from brambleloop.publish import release_gates
            with reopened.session() as session:
                stored = session.scalar(select(Listing).where(Listing.product_slug == cir.slug))
                stored.title = "Storage Basket"
                stored.tags = "baby"
            gated = release_gates.for_publish(reopened, slug=cir.slug, version=cir.version,
                read_only=True, stage=release_gates.STAGE_ACTIVATION)
            assert any("child audience: listing copy cannot be checked" in str(reason)
                       for reason in gated["reasons"]), gated["reasons"]
        finally:
            if old_dir is None:
                os.environ.pop("BRAMBLELOOP_ARTIFACT_DIR", None)
            else:
                os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = old_dir


def test_listing_copy_race_is_blocked_and_classifies_emitted_copy():
    from unittest.mock import patch
    from sqlalchemy import select
    from brambleloop.commerce import category
    from brambleloop.runtime import etsy_ops

    with tempfile.TemporaryDirectory() as directory:
        db = Database(f"sqlite:///{directory}/race.sqlite", scratch=True)
        db.create_all()
        Registry(db).seed_defaults()
        cir = inventory._engineered("market-basket-small")
        with db.session() as s:
            product = Product(slug=cir.slug, title=cir.title, status="certified")
            s.add(product)
            s.flush()
            s.add(PatternVersion(product_id=product.id, version=cir.version, certified=True,
                cir_json=cir.to_dict(), release_hash="a" * 64,
                certificate={"granted": True, "gauge_standard": GAUGE_STANDARD}))
            s.add(Listing(product_slug=cir.slug, version=cir.version, state="draft",
                title="Storage Basket", description="Plain basket", tags=["storage"],
                price_cad=5, release_hash="a" * 64))
        original = etsy_ops.certified_payload
        def concurrent_edit(db_, slug, version):
            with db_.session() as session:
                row = session.scalar(select(Listing).where(Listing.product_slug == slug))
                row.title = "Baby Basket"
            return original(db_, slug, version)
        selection = {"status": category.CHOSEN, "taxonomy_id": 1,
                     "certified": "PASS", "properties": []}
        with patch.object(etsy_ops, "certified_payload", side_effect=concurrent_edit), \
             patch.object(category, "publish_inputs", return_value=selection):
            package = listing_package.assemble(db, cir.slug, cir.version)
        assert package["copy"]["title"] == "Baby Basket", package
        assert package["state"] == listing_package.BLOCKED, package
        assert package["identity"]["childrens_decision"][0] == launch0.UNDECIDED, package
        assert {"listing_snapshot", "childrens_decision"} <= {
            b["source"] for b in package["blockers"]}, package["blockers"]
        assert package["listing_snapshot_sha256"] != listing_package.listing_copy_digest(package["copy"])


if __name__ == "__main__":
    # Review U6 H2: run under the suite harness (one `OK name` line per test), without pytest.
    import _minipytest

    _minipytest.run_module(globals())
