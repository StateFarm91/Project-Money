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
                  "Basket for nurseries", "Basket for kids"):
        changed = dataclasses.replace(adult, title=title)
        assert launch0.child_words_in(title), title
        assert launch0.childrens_decision_for(changed)[0] == launch0.UNDECIDED, title
        assert harness._refused(changed), title
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
            JobQueue(reopened).enqueue("listing", "listing.package", {},
                                       idempotency_key="codex:a1:listing")
            assert Worker(reopened, "listing-child", job_types=["listing.package"]).run_once()
            package = listing_package.latest(reopened, cir.slug, cir.version)
            assert package and package["state"] == listing_package.BLOCKED, package
            assert package["identity"]["childrens_decision"][0] == launch0.UNDECIDED, package
            assert any(b["source"] == "childrens_decision" for b in package["blockers"]), package
            assert package["publishes"] is False
        finally:
            if old_dir is None:
                os.environ.pop("BRAMBLELOOP_ARTIFACT_DIR", None)
            else:
                os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = old_dir


if __name__ == "__main__":
    test_plural_child_audience_words_are_held_in_pdf_worker()
    test_persistent_listing_package_and_publish_verdict_hold_child_copy()
    print("PASS child-audience listing and plural titles are held through real workers")
