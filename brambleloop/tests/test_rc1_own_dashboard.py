"""A3-09: the dashboard headline never shows unmeasured money as a measured zero."""
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


def _db():
    from brambleloop.core.db import Database

    tmp = tempfile.mkdtemp(prefix="rc1own-dash-")
    db = Database(f"sqlite:///{tmp}/d.db")
    db.create_all()
    return tmp, db


class _Source:
    def __init__(self, measured):
        self.measured = measured

    def __enter__(self):
        from brambleloop.commerce import orders_ingest

        self.orig = orders_ingest.source_state
        m = self.measured
        orders_ingest.source_state = lambda db: {
            "open": m, "measured": m, "missing": [], "last_read_at": None,
            "why": "" if m else "the order source is not connected", "owner_action": "x"}

    def __exit__(self, *a):
        from brambleloop.commerce import orders_ingest

        orders_ingest.source_state = self.orig


_STATUS = {"dead_letter_refusals": 0, "dead_letter_defects": 0, "dead_letters": 0}


def _kpi(head, key):
    return next(k for k in head["kpis"] if k["key"] == key)


def test_revenue_is_unmeasured_while_order_source_is_gated():
    from brambleloop.app import dashboard_truth as dt
    from brambleloop.core.models import LedgerEntry

    tmp, db = _db()
    try:
        with db.session() as s:  # a legacy row that names a reference but is not reconciled
            s.add(LedgerEntry(category="sale", gross_cad=20.0, evidence_ref="legacy:1"))
        with _Source(False):
            r = dt.revenue_reading(db)
            assert r["state"] == "UNMEASURED" and r["value_cad"] is None
            assert r["display"] == "UNMEASURED" and "0.00" not in r["display"]
            c = dt.commercial_evidence(db)
            assert c["evidenced_sales"] == 0 and c["state"] == "UNMEASURED"
            assert c["evidence"]["confidence"] == "unmeasured"
            assert c["recorded_unreconciled_sales"] == 1
            head = dt.headline(db, _STATUS, inbox={"cards": []})
            assert _kpi(head, "revenue")["value"] == "UNMEASURED"
            assert _kpi(head, "revenue")["alarm"] is True
            assert _kpi(head, "commercial_evidence")["value"] == "UNMEASURED"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_measured_revenue_sums_only_reconciled_measured_rows():
    from brambleloop.app import dashboard_truth as dt
    from brambleloop.core.models import LedgerEntry
    from brambleloop.finance.reconcile import RECONCILED

    tmp, db = _db()
    try:
        with db.session() as s:
            s.add(LedgerEntry(category="sale", gross_cad=10.0, refunds_cad=1.0,
                              evidence_ref="etsy:1", basis="measured",
                              reconciliation_state=RECONCILED))
            s.add(LedgerEntry(category="sale", gross_cad=50.0, evidence_ref="etsy:2",
                              basis="measured", reconciliation_state="unreconciled"))
            s.add(LedgerEntry(category="sale", gross_cad=70.0, evidence_ref="etsy:3",
                              basis="unknown", reconciliation_state=RECONCILED))
        with _Source(True):
            r = dt.revenue_reading(db)
            assert r["state"] == "MEASURED" and r["value_cad"] == 9.0, r
            assert r["unreconciled_rows"] == 2
            c = dt.commercial_evidence(db)
            assert c["evidenced_sales"] == 1 and c["evidenced_gross_cad"] == 10.0
            assert c["state"] == "OBSERVED"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_spend_counts_every_recorded_kind_and_is_labelled():
    from brambleloop.app import dashboard_truth as dt
    from brambleloop.core.models import CostEntry, LedgerEntry

    tmp, db = _db()
    try:
        with db.session() as s:
            s.add(CostEntry(agent="a", kind="llm", amount_cad=1.0))
            s.add(CostEntry(agent="a", kind="hosting", amount_cad=2.0))
            s.add(CostEntry(agent="a", kind="etsy_listing_fee", amount_cad=0.5))
            s.add(LedgerEntry(category="fee", fees_cad=0.25, expense_cad=0.75))
        sp = dt.spend_reading(db)
        assert sp["model_cad"] == 1.0
        assert sp["cost_entries_cad"] == 3.5
        assert sp["total_recorded_cad"] == 4.5
        assert "all kinds" in sp["label"] and "opex" not in sp["label"].lower()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_unknown_owner_inbox_raises_an_alarm():
    from brambleloop.app import dashboard_truth as dt

    tmp, db = _db()
    try:
        with _Source(False):
            for inbox in (None, {}, {"cards": None}):
                k = _kpi(dt.headline(db, _STATUS, inbox=inbox), "owner_inbox")
                assert k["value"] == "UNKNOWN" and k["alarm"] is True, (inbox, k)
            k = _kpi(dt.headline(db, _STATUS, inbox={"cards": []}), "owner_inbox")
            assert k["value"] == "0" and k["alarm"] is False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    test_revenue_is_unmeasured_while_order_source_is_gated()
    test_measured_revenue_sums_only_reconciled_measured_rows()
    test_spend_counts_every_recorded_kind_and_is_labelled()
    test_unknown_owner_inbox_raises_an_alarm()
    print("test_rc1_own_dashboard: OK")
