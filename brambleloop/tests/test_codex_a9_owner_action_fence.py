"""Committed ORM source edits withdraw old review authority atomically."""
from sqlalchemy import select

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
