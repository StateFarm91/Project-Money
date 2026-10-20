"""W4-CLOSE5 batch 2: the clauses of the W4-FMCLOSE Etsy rows that its own tests left implicit.

  F-558  Order Operations Ledger -- "For every order, reconcile payment, item/version, digital
         delivery state, buyer issue, refund/cancellation/case state and downstream accounting
         evidence."  tests/test_w4_fmclose_etsy.py asserts the six parts exist and the refund
         path; this asserts the ITEM/VERSION content and the CANCELLATION path.

Uses the W4-FMCLOSE fixtures (stub Etsy feed, no network). Code under test is in the deployed
tree (b931d17).
Run: cd brambleloop && PYTHONPATH=src:tests $PY tests/test_w4_close5_rows2.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import test_w4_fmclose_etsy as F  # noqa: E402  (stub feed, listing and gate fixtures)


def test_f558_item_version_is_named_with_its_basis_and_a_cancellation_reaches_the_row():
    from brambleloop.commerce import order_ledger, orders_ingest

    db = F._db()
    F._listing(db)
    F._open_gate(db)
    F._verify_mapping(db)
    paid = F._receipt(1, 501, "222", 900)
    paid["transactions"][0]["is_digital"] = True
    orders_ingest.ingest(db, reader=F.Feed([paid]))
    row = order_ledger.ledger(db)["rows"][0]
    item = row["item"]
    assert item["listing_id"] == "222" and item["product_slug"] == "cloudline-baby-blanket"
    assert item["version"] == "1.0.0" and item["version_basis"], item
    assert row["refund_case"]["cancelled"] is False and row["payment"]["state"] == "paid"
    assert row["delivery"]["state"] == "available_on_payment"

    # Etsy later reports the same receipt cancelled: the row is kept (not deleted), says so in
    # payment, delivery and the refund/case state, and carries no revenue.
    orders_ingest.ingest(db, reader=F.Feed([dict(paid, status="canceled")]))
    got = order_ledger.ledger(db)
    assert got["orders"] == 1, got
    row = got["rows"][0]
    assert row["payment"]["state"] == "cancelled" and row["payment"]["revenue_cad"] == 0.0
    assert row["delivery"]["state"] == "cancelled"
    assert row["refund_case"]["cancelled"] is True and row["refund_case"]["state"] == "cancelled"
    assert row["item"]["version"] == "1.0.0", "the cancellation keeps what was sold"
    assert row["accounting"] is not None and row["accounting"]["ledger_row"], row


def test_f558_an_unknown_version_is_a_problem_never_a_pass():
    from brambleloop.commerce import order_ledger, orders_ingest
    from brambleloop.core.models import Order
    from sqlalchemy import select

    db = F._db()
    F._listing(db)
    F._open_gate(db)
    paid = F._receipt(1, 501, "222", 900)
    paid["transactions"][0]["is_digital"] = True
    orders_ingest.ingest(db, reader=F.Feed([paid]))
    with db.session() as s:
        s.scalar(select(Order)).version = ""   # NOT NULL column: empty is "not known"
    row = order_ledger.ledger(db)["rows"][0]
    assert row["item"]["version"] == order_ledger.UNKNOWN
    assert "item/version: version not known" in row["problems"] and row["reconciled"] is False


if __name__ == "__main__":
    fails = 0
    ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            ran += 1
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                traceback.print_exc()
                fails += 1
                print("FAIL", name, repr(e))
    assert ran >= 2, "no tests collected"
    print(f"\n{'PASS' if not fails else 'FAIL'}: {fails} failing of {ran}")
    sys.exit(1 if fails else 0)
