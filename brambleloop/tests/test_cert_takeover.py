"""#131 executed (C-69): scheduled storefront takeovers applied and reverted on their dates.

`seasonal.engine` plans each takeover from the collection calendar; the executor now applies
each surface to the drafted storefront on its transition date and reverts it on its revert
date, and the storefront the launch gate checks is rendered with what is live.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402

from brambleloop.brand import storefront, takeover  # noqa: E402
from brambleloop.core.models import OperatingReading  # noqa: E402
from tests.test_cert_growth_seasonal import _db, _run, _seasonal_fixture  # noqa: E402

TODAY = date(2026, 9, 27)


def _states(db):
    with db.session() as s:
        return {(r.payload["event"], r.payload["surface"]): r.payload["state"]
                for r in s.scalars(select(OperatingReading).where(
                    OperatingReading.kind == takeover.STATE_KIND))}


def test_the_engine_applies_due_surfaces_and_reverts_them_after_the_occasion():
    db = _db()
    _seasonal_fixture(db)
    out = _run(db, "seasonal.engine", {"as_of": TODAY.isoformat()})
    assert out is not None
    states = _states(db)
    # Halloween's banner (60 days ahead of 31 October) is due; Christmas's is not yet.
    assert states.get(("Halloween", "banner")) == takeover.APPLIED, states
    assert ("Christmas", "banner") not in states
    assert states.get(("Christmas", "featured_collection")) == takeover.APPLIED
    live = takeover.active(db, today=TODAY)
    assert "Halloween" in live["banner"]["change"]
    # idempotent: a second run applies nothing new
    _run(db, "seasonal.engine", {"as_of": TODAY.isoformat()})
    assert _states(db) == states

    # a week after Halloween the banner comes down, whatever is planned that day
    _run(db, "seasonal.engine", {"as_of": "2026-11-08"})
    states = _states(db)
    assert states[("Halloween", "banner")] == takeover.REVERTED
    assert "Halloween" not in (takeover.active(db, today=date(2026, 11, 8)).get("banner")
                               or {}).get("change", "")


def test_the_storefront_is_rendered_with_the_live_takeover_and_still_checked():
    db = _db()
    _seasonal_fixture(db)
    _run(db, "seasonal.engine", {"as_of": TODAY.isoformat()})
    store = storefront.build_storefront(db=db)
    live = takeover.active(db)
    if live.get("banner"):
        assert store.announcement == live["banner"]["change"]
    assert storefront.check_storefront(store) == store.problems


def test_every_applied_surface_is_rendered_on_the_storefront_the_launch_check_reads():
    """C-80 defect 18: shop_content and featured_collection APPLIED rows reach the rendered
    storefront (About seasonal copy, pinned collection), through seasonal.engine."""
    from datetime import timedelta

    db = _db()
    _seasonal_fixture(db)
    _run(db, "seasonal.engine", {"as_of": TODAY.isoformat()})
    live = takeover.active(db, today=TODAY)
    assert live.get("featured_collection"), live
    store = storefront.build_storefront(db=db, today=TODAY)
    assert store.featured_collection == live["featured_collection"]["change"]
    assert store.to_dict()["featured_collection"] == store.featured_collection
    assert storefront.check_storefront(store) == store.problems == []
    # shop_content turns over closer to the event: a plan due today renders onto About
    plan = takeover.plan("Test", TODAY + timedelta(days=3),
                         {"shop_content": "A Test section holding the autumn table pieces."},
                         today=TODAY)
    out = takeover.execute(db, [plan], today=TODAY)
    assert out["applied"] and not out["refused"], out
    store = storefront.build_storefront(db=db, today=TODAY)
    assert store.about.endswith("A Test section holding the autumn table pieces.")
    assert store.seasonal_copy and store.problems == []


def test_a_featured_collection_that_names_nothing_real_is_refused():
    db = _db()
    _seasonal_fixture(db)
    plan = takeover.plan("Test", TODAY + timedelta_days(3),
                         {"featured_collection": "The Imaginary Collection"}, today=TODAY)
    out = takeover.execute(db, [plan], today=TODAY)
    assert out["applied"] == [] and out["refused"], out
    assert any("FEATURED_COLLECTION_NAMES_NOTHING" in p for p in out["refused"][0]["problems"])
    assert storefront.build_storefront(db=db, today=TODAY).featured_collection is None


def timedelta_days(n):
    from datetime import timedelta

    return timedelta(days=n)


def test_a_takeover_that_breaks_the_storefront_rules_is_refused_not_applied():
    db = _db()
    plan = takeover.plan("Test", date(2026, 10, 1), {"banner": "x" * 5000}, today=TODAY)
    out = takeover.execute(db, [plan], today=TODAY)
    assert out["applied"] == [] and out["refused"]
    assert any("ANNOUNCEMENT_TOO_LONG" in p for p in out["refused"][0]["problems"])


if __name__ == "__main__":
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback
                traceback.print_exc()
                fails += 1
                print("FAIL", name, repr(e))
    print(f"\n{'PASS' if not fails else 'FAIL'}: {fails} failing")
    sys.exit(1 if fails else 0)
