"""B2 #292: proven evergreen candidates; sales matched to the exact product, never a prefix."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (Customer, LedgerEntry, Order, PatternVersion,  # noqa: E402
                                     Product)
from brambleloop.seasonal import leadtime, remerchandising as R  # noqa: E402


def _db():
    db = Database("sqlite://")
    db.create_all()
    return db


def _product(db, slug):
    with db.session() as s:
        p = Product(slug=slug, title=slug, status="released")
        s.add(p)
        s.flush()
        s.add(PatternVersion(product_id=p.id, version="1.0.0", cir_json={"slug": slug},
                             certified=True))


def test_a_sale_of_a_longer_slug_does_not_prove_its_prefix():
    db = _db()
    _product(db, "hat")
    _product(db, "hat-xl")
    with db.session() as s:
        s.add(LedgerEntry(category="sale", gross_cad=9.0, evidence_ref="order:hat-xl:1"))
    rows = {r["slug"]: r for r in R.candidates(db)["eligible"]}
    assert rows["hat-xl"]["proven"] is True and rows["hat"]["proven"] is False


def test_orders_prove_and_the_same_sale_is_not_counted_twice():
    db = _db()
    _product(db, "tote")
    with db.session() as s:
        c = Customer(customer_ref="b")
        s.add(c)
        s.flush()
        s.add(Order(customer_id=c.id, external_ref="r1", product_slug="tote"))
        s.add(LedgerEntry(category="sale", gross_cad=9.0, evidence_ref="order:tote:r1"))
    row = R.candidates(db)["eligible"][0]
    assert row["orders"] == 1 and row["proven"] is True


def test_proven_evergreen_is_the_subject():
    db = _db()
    _product(db, "tote")
    real = leadtime.occasion_for
    leadtime.occasion_for = lambda slug: leadtime.EVERGREEN if slug == "tote" else "Christmas"
    try:
        _product(db, "garland")
        with db.session() as s:
            c = Customer(customer_ref="b")
            s.add(c)
            s.flush()
            for i, slug in enumerate(("tote", "garland")):
                s.add(Order(customer_id=c.id, external_ref=f"r{i}", product_slug=slug))
        out = R.candidates(db)
    finally:
        leadtime.occasion_for = real
    assert out["proven_evergreen"] == ["tote"]
    assert {r["slug"]: r["evergreen"] for r in out["eligible"]} == {"tote": True,
                                                                     "garland": False}


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("ok", n)
