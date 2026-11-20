"""B2 #8: the proof stack's customer rungs are read from rows (consented customer photo;
repeat buyer), contiguous, and marketing claims stay refused until they are."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import Customer, Order, PhysicalPhoto  # noqa: E402
from brambleloop.quality import proof as P  # noqa: E402


def _db():
    db = Database("sqlite://")
    db.create_all()
    return db


def _buyer(db, ref, slugs):
    with db.session() as s:
        c = Customer(customer_ref=ref)
        s.add(c)
        s.flush()
        for i, slug in enumerate(slugs):
            s.add(Order(customer_id=c.id, external_ref=f"{ref}-{i}", product_slug=slug))


def test_empty_rows_establish_nothing():
    st = P.states_from_db(_db(), "hex")
    assert st["customer_project"] is False and st["repeat_purchase"] is False


def test_unconsented_customer_photo_does_not_count_and_consented_does():
    db = _db()
    with db.session() as s:
        s.add(PhysicalPhoto(product_slug="hex", source="customer", sha256="a" * 64))
    assert P.states_from_db(db, "hex")["customer_project"] is False
    with db.session() as s:
        s.add(PhysicalPhoto(product_slug="hex", source="customer", sha256="b" * 64,
                            rights_basis="customer_consent:msg-17"))
        s.add(PhysicalPhoto(product_slug="hex", source="tester", sha256="c" * 64,
                            rights_basis="tester_agreement"))
    assert P.states_from_db(db, "hex")["customer_project"] is True
    assert P.states_from_db(db, "other")["customer_project"] is False


def test_repeat_purchase_needs_a_buyer_of_this_pattern_with_two_orders():
    db = _db()
    _buyer(db, "c1", ["hex"])
    _buyer(db, "c2", ["tote", "cowl"])                # repeat, but never bought hex
    assert P.states_from_db(db, "hex")["repeat_purchase"] is False
    _buyer(db, "c3", ["hex", "tote"])
    assert P.states_from_db(db, "hex")["repeat_purchase"] is True


def test_customer_rungs_do_not_leapfrog_or_license_claims_early():
    db = _db()
    _buyer(db, "c3", ["hex", "tote"])
    with db.session() as s:
        s.add(PhysicalPhoto(product_slug="hex", source="customer", sha256="d" * 64,
                            rights_basis="consent"))
    st = P.states_from_db(db, "hex")
    r = P.reached(st)
    assert r["claim_level"] == 0 and set(r["ahead_of_the_ladder"]) == {
        "customer_project", "repeat_purchase"}
    assert P.check_claim("repeat buyers love it", st)       # still refused
    rep = P.report(db, "hex")
    assert rep["not_reachable_yet"] == {}


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("OK  ", n)  # run_tests.sh counts lines beginning OK
