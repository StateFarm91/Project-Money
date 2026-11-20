"""W4-C12: the new-listing learning window, the bulk operations guard and renewal economics.

Rows (Final Master, quoted):
- F-034 "Schedule evidence capture during Etsy's temporary new-listing boost."
- F-554 "Support safe bulk edits/renewals only with preview, affected-count proof, invariant
  checks and rollback plan. Never bulk-edit Product Truth, safety or legal fields from a
  heuristic."
- F-555 "Measure manual/automatic renewal economics and performance. Renew because evidence
  supports the listing, not merely because expiry is approaching."
Fixture listings and outcomes; no Etsy call, no listing written.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sqlalchemy import select  # noqa: E402

from brambleloop.commerce import listing_lifecycle as L  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog, ListingOutcome  # noqa: E402

NOW = datetime.now(timezone.utc)


def _db() -> Database:
    db = Database("sqlite://", scratch=True)
    db.create_all()
    return db


# ---- F-034 ----------------------------------------------------------------------------------

def test_f034_a_verified_activation_schedules_the_window_and_captures_are_dated():
    db = _db()
    assert L.learning_window(db, "111")["state"] == "NOT_LIVE"
    L.record(db, action="activate", listing_id="111", actor="store",
             evidence="store.activated read-back", result="verified")
    with db.session() as s:                               # activated four days ago
        row = s.scalar(select(AuditLog).where(AuditLog.action == L.ACTION))
        row.at = NOW - timedelta(days=4)
    w = L.learning_window(db, "111", now=NOW)
    assert [x["day"] for x in w["schedule"]] == list(L.WINDOW_DAYS) and w["basis"]
    states = {x["day"]: x["state"] for x in w["schedule"]}
    assert states == {0: "due", 1: "due", 3: "due", 7: "scheduled", 14: "scheduled"}
    assert w["missed"] == [0, 1]
    try:
        L.record_capture(db, "111", day=7, source="stats_export", evidence="stats.csv",
                         observed_at=NOW)
        raise AssertionError("a capture before its due day was accepted")
    except L.LifecycleRefused:
        pass
    L.record_capture(db, "111", day=3, source="stats_export", evidence="stats-d3.csv",
                     observed_at=NOW - timedelta(hours=2), values={"visits": 41})
    w = L.learning_window(db, "111", now=NOW)
    d3 = next(x for x in w["schedule"] if x["day"] == 3)
    assert d3["state"] == "captured" and d3["capture"]["values"] == {"visits": 41}
    assert [d["day"] for d in L.due_captures(db, ["111"], now=NOW)] == [0, 1]
    try:
        L.record_capture(db, "222", day=0, source="census", evidence="x", observed_at=NOW)
        raise AssertionError("a capture for a listing that is not live was accepted")
    except L.LifecycleRefused:
        pass


# ---- F-554 ----------------------------------------------------------------------------------

CURRENT = {"1": {"title": "Moss basket", "tags": ["a"], "price": 8.0, "state": "active"},
           "2": {"title": "Fern cowl", "tags": ["b"], "price": 9.0, "state": "active"},
           "3": {"title": "Old hat", "tags": [], "price": 7.0, "state": "expired"}}


def test_f554_protected_fields_are_never_bulk_edited():
    db = _db()
    for field in ("description", "materials", "who_made", "is_digital", "safety"):
        try:
            L.bulk_plan(db, operation="edit", changes={"1": {field: "x"}}, current=CURRENT,
                        expected_count=1, reason="heuristic tidy-up", actor="seo")
            raise AssertionError(field)
        except L.LifecycleRefused as e:
            assert "Product Truth" in str(e)


def test_f554_a_plan_previews_counts_checks_and_carries_its_rollback():
    db = _db()
    plan = L.bulk_plan(db, operation="edit",
                       changes={"1": {"tags": ["a", "moss"]}, "2": {"tags": ["b"]}},
                       current=CURRENT, expected_count=2, reason="add the moss tag",
                       actor="seo")
    assert plan["affected"] == 1 and not plan["safe"]          # "2" would not change
    assert "expected 2" in plan["invariants"][0]
    plan = L.bulk_plan(db, operation="edit", changes={"1": {"tags": ["a", "moss"]}},
                       current=CURRENT, expected_count=1, reason="add the moss tag",
                       actor="seo")
    assert plan["safe"] and plan["preview"][0]["diff"]["tags"]["from"] == ["a"]
    assert plan["rollback"] == {"1": {"tags": ["a"]}}
    assert L.verify_plan(plan, CURRENT)["may_run"] is True
    moved = {**CURRENT, "1": {**CURRENT["1"], "tags": ["a", "x"]}}
    assert L.verify_plan(plan, moved)["may_run"] is False
    # A bulk renewal passes the recency rule per listing: an active listing is refused.
    renew = L.bulk_plan(db, operation="renew",
                        changes={"1": {"state": "active"}, "3": {"state": "active"}},
                        current=CURRENT, expected_count=1, reason="renew",
                        actor="store", renewal_reasons={"1": "expiring_soon",
                                                        "3": "expired"})
    assert not renew["safe"] and any(i.startswith("1:") for i in renew["invariants"])
    with db.session() as s:
        assert len(list(s.scalars(select(AuditLog).where(
            AuditLog.action == L.BULK_ACTION)))) == 3


# ---- F-555 ----------------------------------------------------------------------------------

def _outcome(db, slug, start, end, visits, orders):
    with db.session() as s:
        s.add(ListingOutcome(product_slug=slug, period_start=start, period_end=end,
                             visits=visits, orders=orders, source="fixture stats export"))


def test_f555_expiry_alone_never_renews_and_evidence_decides():
    db = _db()
    near = L.renewal_economics(db, slug="moss", net_per_sale_cad=5.0, usd_per_cad=0.72,
                               days_to_expiry=2, mode="auto")
    assert near["decision"] == "UNMEASURED" and near["auto_renew"] is False
    _outcome(db, "moss", "2026-09-01", "2026-09-30", 200, 6)
    good = L.renewal_economics(db, slug="moss", net_per_sale_cad=5.0, usd_per_cad=0.72,
                               days_to_expiry=40)
    assert good["decision"] == "RENEW" and good["auto_renew"] is True
    assert good["expected_contribution_cad"] > good["renewal_fee_cad"] > 0
    _outcome(db, "fern", "2026-09-01", "2026-09-30", 300, 0)
    poor = L.renewal_economics(db, slug="fern", net_per_sale_cad=5.0, usd_per_cad=0.72,
                               days_to_expiry=1)
    assert poor["decision"] == "LET_EXPIRE" and poor["auto_renew"] is False
    # The same evidence gives the same answer however close expiry is.
    far = L.renewal_economics(db, slug="fern", net_per_sale_cad=5.0, usd_per_cad=0.72,
                              days_to_expiry=90)
    assert far["decision"] == poor["decision"]


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print("OK  ", t.__name__)
        except Exception as exc:  # noqa: BLE001
            failed += 1
            import traceback
            traceback.print_exc()
            print("FAIL", t.__name__, exc)
    print(f"{len(tests) - failed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
