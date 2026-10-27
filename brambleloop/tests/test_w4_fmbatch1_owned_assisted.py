"""B2 #20: owned share is measured from owned channels (not the unpaid Etsy arm), and
assisted conversions are counted once each."""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import Cohort, Customer, Order  # noqa: E402
from brambleloop.growth import owned as O  # noqa: E402

T0 = datetime(2026, 10, 1, tzinfo=timezone.utc)


def _db():
    db = Database("sqlite://")
    db.create_all()
    return db


def _orders(db, ref, rows):
    with db.session() as s:
        c = Customer(customer_ref=ref)
        s.add(c)
        s.flush()
        for i, (slug, source) in enumerate(rows):
            s.add(Order(customer_id=c.id, external_ref=f"{ref}-{i}", product_slug=slug,
                        acquisition_source=source, at=T0 + timedelta(days=i)))


def test_unmeasurable_without_orders():
    assert O.owned_share(_db())["measurable"] is False
    assert O.assisted_conversions(_db())["measurable"] is False


def test_organic_etsy_is_not_owned():
    db = _db()
    with db.session() as s:
        s.add(Cohort(key="c1", product_slug="hex", arm="organic", visits=500))
    _orders(db, "a", [("hex", "etsy_organic"), ("hex", "etsy_organic")])
    share = O.owned_share(db)
    assert share["owned_share"] == 0.0 and share["marketplace_share"] == 1.0


def test_direct_and_assisted_are_counted_once_each():
    db = _db()
    _orders(db, "a", [("hex", "email"), ("hex", "etsy_organic"), ("tote", "etsy_ads")])
    _orders(db, "b", [("hex", "etsy_organic"), ("hex", "owned_direct")])   # owned came after
    out = O.assisted_conversions(db)
    assert out["by_product"]["hex"] == {"orders": 4, "direct": 2, "assisted": 1}
    assert out["by_product"]["tote"] == {"orders": 1, "direct": 0, "assisted": 1}
    assert out["total"] == {"orders": 5, "direct": 2, "assisted": 2}
    share = O.owned_share(db)
    assert share["owned_orders"] == 2 and share["owned_share"] == 0.4


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("OK  ", n)  # run_tests.sh counts lines beginning OK
