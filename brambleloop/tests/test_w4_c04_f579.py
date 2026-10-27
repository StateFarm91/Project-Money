"""W4-C04 F-579 (an owner-decision row, kept in its own commit and file).

Fixtures only: no network, no Etsy call, no spend. Each test names its row.
Run: cd brambleloop && python3 tests/test_w4_c04_f579.py
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


# ---- F-579 Accounting integration decision -----------------------------------------------

def test_f579_qbo_and_xero_are_evaluated_and_not_connected_while_the_books_win():
    from brambleloop.finance import tool_decisions
    from brambleloop.finance.accounting import integration_decision as D

    d = D.decide()
    assert set(D.CANDIDATES) >= {"quickbooks_online", "xero", "in_house_books"}
    for c in D.CANDIDATES.values():
        assert set(c["scores"]) == set(D.CRITERIA) and all(r for _s, r in c["scores"].values())
    assert d["recommend"] == "in_house_books" and d["connect_external"] is False, d
    assert d["revisit_when"] and d["sources"]["xero"].startswith("https://")
    db = _db()
    ref = tool_decisions.record_evaluation(
        db, tool="xero", monthly_cost_cad=60.0, evaluated_by="test",
        evaluation={"capability_gap": "x", "overlap": [{"existing": "finance.accounting",
                                                        "why_not_enough": "y"}],
                    "expected_roi": {"value_cad_month": 100.0, "basis": "z"},
                    "data_quality": "q", "permissions": "p", "vendor_risk": "r",
                    "build_vs_buy": "b"})
    try:
        tool_decisions.check_scope(db, "software:xero", ref)
    except tool_decisions.ToolSpendRefused as exc:
        assert "F-579" in str(exc)
    else:
        raise AssertionError("an accounting integration got a spend scope against F-579")
    assert D.connection_allowed("figma")[0] is True        # not an accounting tool


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
