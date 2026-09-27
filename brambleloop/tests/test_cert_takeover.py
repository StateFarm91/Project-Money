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
