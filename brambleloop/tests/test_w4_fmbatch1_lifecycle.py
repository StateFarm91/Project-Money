"""F-672: lifecycle stages derived from rows, illegal moves refused, REJECTED/ROLLED_BACK
recorded, and a board grouping every product."""
import _tmp; _tmp.install()  # per-process temp sandbox, removed at exit
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (Customer, Listing, ListingAsset,  # noqa: E402
                                     ListingSetCertificateRecord, Order, PatternVersion,
                                     Product)
from brambleloop.products import lifecycle as L  # noqa: E402
from brambleloop.visual.shot_plans import CAMPAIGN_MIN_FRAMES  # noqa: E402


def _db():
    db = Database(f"sqlite:///{tempfile.mkdtemp(prefix='fmb1lc-')}/t.sqlite")
    db.create_all()
    return db


def test_stages_follow_the_rows():
    db = _db()
    assert L.derive(db, "x")["stage"] == "DISCOVERED"
    with db.session() as s:
        p = Product(slug="x", title="x", status="concept")
        s.add(p)
        s.flush()
        pid = p.id
    assert L.derive(db, "x")["stage"] == "SELECTED"
    with db.session() as s:
        s.add(PatternVersion(product_id=pid, version="1", cir_json={}, certified=False))
    assert L.derive(db, "x")["stage"] == "PATTERN"
    with db.session() as s:
        s.query(PatternVersion).update({"certified": True})
    assert L.derive(db, "x")["stage"] == "QA"
    with db.session() as s:
        s.add(Listing(product_slug="x", version="1", title="t", description="d", state="drafted"))
    assert L.derive(db, "x")["stage"] == "VISUAL"
    with db.session() as s:
        s.add(ListingAsset(product_slug="x", version="1", position=1, asset_class="hero",
                           role="hero"))
    # D-OWNER-GALLERY-COMPLETE: a draft with a partial certified gallery is not ready ...
    assert L.derive(db, "x")["stage"] == "VISUAL"
    with db.session() as s:
        s.add(ListingSetCertificateRecord(
            product_slug="x", version="1", state="valid",
            certificate={"frames": [{"position": i} for i in range(1, CAMPAIGN_MIN_FRAMES)]}))
    assert L.derive(db, "x")["stage"] == "VISUAL"
    # ... and the complete gallery alone is still not LISTING_READY. D-OWNER-SALE-PIPELINE
    # (2026-11-20, owner HARD RULE): ready for sale = certified pattern + complete certified
    # gallery + both premium PDFs certified + every listing gate PASS, read by
    # `publish.sale_pipeline.ready_for_sale`. These rows carry no PDFs or package, so the
    # stage stays VISUAL and says why.
    with db.session() as s:
        s.add(ListingSetCertificateRecord(
            product_slug="x", version="1", state="valid",
            certificate={"frames": [{"position": i}
                                    for i in range(1, CAMPAIGN_MIN_FRAMES + 1)]}))
    d = L.derive(db, "x")
    assert d["stage"] == "VISUAL" and "not yet ready for sale" in d["why"], d
    # The real ready_for_sale on a real chain reaching LISTING_READY is
    # tests/test_sale_pipeline.py; here its reading is supplied at its seam so the stage
    # mapping is what is tested: READY -> LISTING_READY, asked for the certified listed
    # version, and a not-ready reading keeps VISUAL.
    from brambleloop.publish import sale_pipeline
    saved = sale_pipeline.ready_for_sale
    asked = []
    try:
        sale_pipeline.ready_for_sale = lambda _db, slug, version: (
            asked.append((slug, version)) or {"ready": False, "reasons": ["PDFs pending"]})
        d = L.derive(db, "x")
        assert d["stage"] == "VISUAL" and "PDFs pending" in d["why"], d
        sale_pipeline.ready_for_sale = lambda _db, slug, version: (
            asked.append((slug, version)) or {"ready": True, "reasons": []})
        assert L.derive(db, "x")["stage"] == "LISTING_READY"
    finally:
        sale_pipeline.ready_for_sale = saved
    assert asked == [("x", "1"), ("x", "1")], asked
    with db.session() as s:
        s.query(Listing).update({"state": "published"})
    assert L.derive(db, "x")["stage"] == "LIVE"
    with db.session() as s:
        c = Customer(customer_ref="b")
        s.add(c)
        s.flush()
        s.add(Order(customer_id=c.id, external_ref="r1", product_slug="x"))
    assert L.derive(db, "x")["stage"] == "GROWING"
    assert "x" in L.board(db)["columns"]["GROWING"]


def test_illegal_moves_are_refused_and_rejection_or_rollback_is_recorded():
    db = _db()
    with db.session() as s:
        s.add(Product(slug="y", title="y", status="concept"))
    try:
        L.transition(db, "y", "LIVE", why="skip ahead")
        raise AssertionError("SELECTED -> LIVE was allowed")
    except L.LifecycleRefused:
        pass
    try:
        L.transition(db, "y", "REJECTED", why=" ")
        raise AssertionError("a transition without a reason was recorded")
    except L.LifecycleRefused:
        pass
    assert L.transition(db, "y", "REJECTED", why="failed the creative gate")["to"] == "REJECTED"
    assert L.derive(db, "y")["stage"] == "REJECTED"
    try:
        L.transition(db, "y", "PATTERN", why="revive")
        raise AssertionError("REJECTED is terminal")
    except L.LifecycleRefused:
        pass
    assert L.may_move("LIVE", "ROLLED_BACK") and L.may_move("ROLLED_BACK", "LISTING_READY")
    assert not L.may_move("RETIRED", "LIVE")


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("OK  ", n)  # run_tests.sh counts lines beginning OK
