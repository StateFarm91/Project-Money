"""W4-C04: finance cluster (F-575, F-576, F-330, F-828; F-579 and F-607 have their own files).

Fixtures only: no network, no Etsy call, no spend. Each test names its row.
Run: cd brambleloop && python3 tests/test_w4_c04_finance.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # per-process temp sandbox, removed at exit
import os
import socket
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
_TMP = tempfile.mkdtemp(prefix="w4_c04_")
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")


def _no_network(*_a, **_k):
    raise OSError("network refused by the C04 harness")


socket.socket.connect = _no_network  # type: ignore[assignment]
socket.create_connection = _no_network  # type: ignore[assignment]

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import Incident  # noqa: E402

NOW = datetime(2026, 10, 27, 12, tzinfo=timezone.utc)
_n = [0]


def _db():
    _n[0] += 1
    db = Database(f"sqlite:///{_TMP}/c04_{_n[0]}.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _entry(eid, ledger_type, amount, balance, ts, ref="9001"):
    return {"entry_id": eid, "ledger_type": ledger_type, "amount": amount, "balance": balance,
            "currency": "CAD", "created_timestamp": int(ts.timestamp()),
            "reference_type": "receipt", "reference_id": ref}


# ---- F-575 Payment Account reconciliation ----------------------------------------------

def test_f575_payment_account_entries_reconcile_and_unexplained_movements_raise():
    from brambleloop.finance.accounting import exceptions, reconciliation

    db = _db()
    t = NOW - timedelta(days=2)
    entries = [
        _entry(1, "transaction", -65, 935, t),                     # balance 1000 -> 935
        _entry(2, "PROLIST", -300, 635, t + timedelta(hours=1)),   # Etsy Ads: not mapped
        _entry(3, "disbursement", -600, 35, t + timedelta(hours=2)),
        _entry(4, "transaction", -10, 0, t + timedelta(hours=3)),  # 35-10 = 25, not 0
    ]
    out = reconciliation.import_etsy_ledger(db, entries, now=NOW)
    assert out["imported"] == 3 and out["unclassified_skipped"] == 1, out
    assert out["balance_continuity"]["state"] == "BROKEN"
    assert [b["entry_id"] for b in out["balance_continuity"]["breaks"]] == ["4"]
    keys = {e["key"] for e in exceptions.listing(db)}
    assert "finance.unexplained:2" in keys and "finance.unexplained:4:balance" in keys, keys
    with db.session() as s:
        inc = s.scalar(select(Incident).where(
            Incident.signature == reconciliation.UNEXPLAINED_SIGNATURE))
        assert inc is not None
    # Idempotent: a re-read of the same window opens nothing new.
    again = reconciliation.import_etsy_ledger(db, entries, now=NOW)
    assert again["imported"] == 0 and again["unexplained"]["exceptions_opened"] == []


def test_f575_the_order_ingest_read_feeds_the_payment_account_statement():
    from brambleloop.commerce import orders_ingest
    from brambleloop.finance.accounting import reconciliation

    db = _db()
    t = NOW - timedelta(days=1)

    class Reader:
        def ledger_entries(self, *, min_created, max_created):
            return [_entry(10, "transaction", -65, 935, t),
                    _entry(11, "disbursement", -935, 0, t + timedelta(hours=1))]

    res = orders_ingest._reconcile_fees(db, Reader(), since=None, now=NOW)
    assert res["read"] is True and "payment_account" in res, res
    lines = reconciliation.statement_lines(db)
    assert {l["external_id"] for l in lines} == {"10", "11"}, lines
    assert res["payment_account"]["balance_continuity"]["state"] == "CONTINUOUS"



# ---- F-576 Monthly statement archive ----------------------------------------------------

def test_f576_the_original_is_kept_by_hash_versions_never_overwrite_and_totals_reconcile():
    import base64

    from brambleloop.app.command_center import approvals
    from brambleloop.finance.accounting import exceptions, reconciliation, statements

    db = _db()
    t = datetime(2026, 9, 10, tzinfo=timezone.utc)
    reconciliation.import_etsy_ledger(db, [_entry(20, "disbursement", -2500, 0, t)], now=NOW)
    pdf = b"%PDF-1.4 fixture statement September 2026"
    totals = {"revenue_cad": None, "fees_cad": None, "tax_cad": 1.3, "refunds_cad": None,
              "payouts_cad": 30.0}
    body = {"period": "2026-09", "content_base64": base64.b64encode(pdf).decode(),
            "content_type": "application/pdf", "totals": totals}
    first = approvals.execute(db, "finance.statement_archive", body, actor="owner-session")
    res = first["result"]
    assert res["archived"] and res["version"] == 1 and res["original_held"], res
    assert statements.original(db, res["sha256"]) == pdf
    rec = res["reconciliation"]["metrics"]
    assert rec["payouts_cad"]["state"] == "DIFFER" and rec["payouts_cad"]["ledger"] == 25.0
    assert rec["tax_cad"]["state"] == "UNKNOWN" and rec["revenue_cad"]["state"] == "UNKNOWN"
    assert "statement:2026-09:payouts_cad" in {e["key"] for e in exceptions.listing(db)}
    # Same bytes: nothing new. A corrected file: version 2, and version 1 is still held.
    again = approvals.execute(db, "finance.statement_archive", body, actor="owner-session")
    assert again["result"]["replayed"] is True
    body2 = dict(body, content_base64=base64.b64encode(pdf + b" corrected").decode())
    v2 = approvals.execute(db, "finance.statement_archive", body2, actor="owner-session")
    assert v2["result"]["version"] == 2
    assert statements.original(db, res["sha256"]) == pdf, "an earlier original was lost"
    # Refusals: a missing total, a future month, no file.
    for bad in ({**body, "totals": {"revenue_cad": 1.0}},
                {**body, "period": "2027-01"},
                {**body, "content_base64": ""}):
        try:
            approvals.execute(db, "finance.statement_archive", bad, actor="owner-session")
        except approvals.ActionRefused:
            continue
        raise AssertionError(f"accepted {bad}")
    assert approvals.ACTIONS["finance.statement_archive"][0] is False



# ---- F-330 Post-launch cost learning -----------------------------------------------------

def test_f330_unit_economics_are_reviewed_at_day_1_7_14_30_then_monthly_once_each():
    from brambleloop.core.models import AuditLog, OperatingReading
    from brambleloop.finance import launch_cost_review as L
    from brambleloop.improve import cost_learning

    db = _db()
    assert L.review(db, now=NOW)["state"] == "UNMEASURED"           # not live: no clock
    launched = NOW - timedelta(days=15)
    with db.session() as s:
        s.add(AuditLog(actor="publisher", action="store.published", artifact="fixture@1",
                       at=launched, detail={}))
    out = cost_learning.run(db, now=NOW)["launch_cost_review"]
    assert out["filed"] == ["day1", "day7", "day14"], out
    assert L.review(db, now=NOW)["filed"] == []                     # idempotent
    later = L.review(db, now=launched + timedelta(days=95))
    assert later["filed"] == ["day30", "day60", "day90"], later
    with db.session() as s:
        rows = {r.period_key: r.payload for r in s.query(OperatingReading).filter(
            OperatingReading.kind == L.REVIEW_KIND)}
    p = rows["day7"]
    assert p["window"]["until"] == (launched + timedelta(days=7)).isoformat()
    assert "unit_economics" in p and "profit_and_loss" in p
    assert "Product Truth" in p["never_cheapen"]["preserved"]
    assert all(r["status"] == "proposable" for r in p["waste"]["cut"])



# ---- F-828 Cross-department ownership of Learn gaps --------------------------------------

def test_f828_learn_gaps_are_owned_by_the_department_whose_part_is_missing():
    from brambleloop.core.models import PatternVersion, Product, SupportCase
    from brambleloop.learn import service
    from brambleloop.learn.models import LearnGap, LearnNode

    db = _db()
    with db.session() as s:
        p = Product(slug="fixture-hat", title="Fixture Hat")
        s.add(p)
        s.flush()
        s.add(PatternVersion(product_id=p.id, version="1", certified=True,
                             cir_json={"rows": [{"stitch": "sc"}], "yarn_weight": "worsted"}))
        s.add(SupportCase(product_slug="fixture-hat", specialist="tension",
                          customer_ref="c1", question="my rows keep tightening"))
    out = service.scan(db)
    with db.session() as s:
        gaps = {g.topic: g.owner for g in s.query(LearnGap)}
        node = s.get(LearnNode, "stitch:sc")
        routing = dict(node.detail["routing"])
    assert gaps["stitch:sc"] == "visual", gaps        # CIR teaches it; no diagram yet
    assert gaps["yarn:worsted"] == "learn", gaps      # truth in, no diagram needed
    assert gaps["support:tension"] == "pattern", gaps  # only support raised it
    assert routing["pattern"]["state"] == "supplied" and routing["visual"]["state"] == "needed"
    assert routing["finance"]["state"] == "UNMEASURED"
    assert routing["marketing_seo"]["state"] == "UNMEASURED"
    assert out["queued_by_owner"]["visual"] >= 1 and out["queued_by_owner"]["pattern"] == 1


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                traceback.print_exc()
                fails += 1
                print("FAIL", name, repr(e))
    sys.exit(1 if fails else 0)
