"""Committed ORM source edits withdraw old review authority atomically."""
from sqlalchemy import select
from sqlalchemy.orm import load_only

from brambleloop.core.models import Listing, OwnerAction, PatternVersion, Product
from brambleloop.publish import listing_package as lp
from test_codex_a9_source_binding import active, fixture, package


def test_listing_edit_withdraws_request_without_a_sweep():
    db = fixture()
    old = package(db)
    assert lp.record(db, old)["review_requested"]
    with db.session() as s:
        s.scalar(select(Listing).where(Listing.product_slug == old["slug"])).title = "Baby Basket"
    assert not active(db)
    assert lp.latest(db, old["slug"], old["version"])["state"] == lp.BLOCKED


def test_version_edit_withdraws_request_and_rollback_restores_it():
    db = fixture()
    old = package(db)
    assert lp.record(db, old)["review_requested"]
    s = db.new_session()
    pv = s.scalar(select(PatternVersion).join(Product).where(Product.slug == old["slug"]))
    pv.certificate = {"granted": False}
    s.flush()
    assert s.scalar(select(OwnerAction).where(OwnerAction.done.is_(False))) is None
    s.rollback()
    s.close()
    assert active(db)
    with db.session() as s:
        s.scalar(select(PatternVersion).join(Product).where(
            Product.slug == old["slug"])).certificate = {"granted": False}
    assert not active(db)


def test_deferred_old_listing_identity_is_withdrawn():
    db = fixture()
    old = package(db)
    assert lp.record(db, old)["review_requested"]
    with db.session() as s:
        listing = s.scalar(select(Listing).options(load_only(Listing.id)).where(
            Listing.product_slug == old["slug"]))
        listing.product_slug = "moved-product"
    assert not active(db)
    assert lp.latest(db, old["slug"], old["version"])["state"] == lp.BLOCKED


def test_deferred_old_version_identity_is_withdrawn():
    db = fixture()
    old = package(db)
    assert lp.record(db, old)["review_requested"]
    with db.session() as s:
        pv = s.scalar(select(PatternVersion).join(Product).options(
            load_only(PatternVersion.id)).where(Product.slug == old["slug"]))
        pv.version = "2.0.0"
    assert not active(db)
    assert lp.latest(db, old["slug"], old["version"])["state"] == lp.BLOCKED


def test_product_rename_withdraws_original_review():
    db = fixture()
    old = package(db)
    assert lp.record(db, old)["review_requested"]
    with db.session() as s:
        product = s.scalar(select(Product).options(load_only(Product.id)).where(
            Product.slug == old["slug"]))
        product.slug = "renamed-product"
    assert not active(db)
    assert lp.latest(db, old["slug"], old["version"])["state"] == lp.BLOCKED


def test_relationship_reassignment_withdraws_original_review():
    db = fixture()
    old = package(db)
    assert lp.record(db, old)["review_requested"]
    with db.session() as s:
        other = Product(slug="other-product", title="Other")
        s.add(other)
        pv = s.scalar(select(PatternVersion).join(Product).where(Product.slug == old["slug"]))
        pv.product = other
    assert not active(db)
    assert lp.latest(db, old["slug"], old["version"])["state"] == lp.BLOCKED
