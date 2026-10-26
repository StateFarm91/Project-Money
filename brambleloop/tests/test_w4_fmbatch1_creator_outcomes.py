"""B2 #21: creator outcomes are measured from rows; unmeasured blocks scaling, never zero."""
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (Cohort, CostEntry, CreatorProfile, PhysicalPhoto,  # noqa: E402
                                     SupportCase)
from brambleloop.growth import creators as C  # noqa: E402


def _db():
    db = Database("sqlite://")
    db.create_all()
    return db


def _creator(db, ref, *, cohort=True):
    with db.session() as s:
        s.add(CreatorProfile(ref=ref, delivered=1, invited=1))
        if cohort:
            s.add(Cohort(key=f"creator:{ref}:hex", product_slug="hex", arm="creator",
                         visits=120, orders=4, at=datetime(2026, 10, 20, tzinfo=timezone.utc)))
        s.add(PhysicalPhoto(product_slug="hex", source="creator", sha256=ref.ljust(64, "0"),
                            taken_by=ref, rights_basis="listing:scope-ref-1"))
        s.add(SupportCase(customer_ref="b1", question="row 3?", detail={"creator_ref": ref}))
        s.add(CostEntry(agent="growth", kind="api", amount_cad=0.0, purpose=f"creator:{ref}"))


def test_nothing_recorded_is_unmeasured_not_zero():
    o = C.measure_outcome(_db(), "nobody")
    assert o.attributable_sessions is None and o.conversions is None
    assert o.support_cases is None and set(o.unmeasured()) >= {"attributable_sessions",
                                                                "conversions", "measured_on"}


def test_rows_become_a_measured_outcome():
    db = _db()
    _creator(db, "maker-a")
    o = C.measure_outcome(db, "maker-a")
    assert (o.attributable_sessions, o.conversions, o.support_cases, o.usable_assets) == \
        (120, 4, 1, 1)
    assert o.unmeasured() == []


def test_scaling_needs_the_floor_and_every_outcome_measured():
    db = _db()
    for ref in ("a", "b"):
        _creator(db, ref)
    _creator(db, "c", cohort=False)                     # delivered, never measured
    out = C.scaling_decision(db)
    assert out["may_scale"] is False and "c" in out["unmeasured"]
    db2 = _db()
    for ref in ("a", "b", "c"):
        _creator(db2, ref)
    assert C.scaling_decision(db2)["may_scale"] is True


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("ok", n)
