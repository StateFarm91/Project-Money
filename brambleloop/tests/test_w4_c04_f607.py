"""W4-C04 F-607 (an owner-decision row, kept in its own commit and file).

Fixtures only: no network, no Etsy call, no spend. Each test names its row.
Run: cd brambleloop && python3 tests/test_w4_c04_f607.py
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


# ---- F-607 Finance & Accounting department led by an Accountant/Controller ---------------

def test_f607_the_accountant_keeps_the_books_independently_of_the_cfo_challenger():
    from brambleloop.agents.registry import (DEFAULT_AGENTS, FORBIDDEN_COMBINATIONS,
                                             PermissionDenied)
    from brambleloop.autonomy import charters
    from brambleloop.queue.durable import JobQueue
    from brambleloop.runtime import pipeline  # noqa: F401 - registers handlers
    from brambleloop.runtime.worker import CADENCES, Worker
    from brambleloop.core.models import Job, JobStatus, Phase

    agents = {a["name"]: a for a in DEFAULT_AGENTS}
    books = {"finance.reconcile", "finance.accounting.cycle", "finance.accounting.period_pack"}
    assert books <= set(agents["accountant"]["allowed_job_types"])
    assert not books & set(agents["cfo"]["allowed_job_types"])
    assert agents["accountant"]["daily_cost_ceiling_cad"] == 0.0
    assert {"finance.challenge", "finance.governor"} <= FORBIDDEN_COMBINATIONS["accountant"]
    assert books <= FORBIDDEN_COMBINATIONS["cfo"]
    cad = {jt: agent for _k, agent, jt, _s in CADENCES}
    assert all(cad[j] == "accountant" for j in books), {j: cad[j] for j in books}
    fin = next(c for c in charters.CHARTERS if c.key == "finance")
    assert "accountant" in fin.agents and "cfo" in fin.agents
    db = _db()
    reg = Registry(db)
    try:
        reg.authorize("cfo", "finance.accounting.cycle")
    except PermissionDenied:
        pass
    else:
        raise AssertionError("the CFO challenger may run the books")
    reg.authorize("accountant", "finance.accounting.cycle")
    job = JobQueue(db).enqueue("accountant", "finance.accounting.cycle", {},
                               idempotency_key="c04-acct")
    Worker(db, "c04", phase=Phase.SHADOW, job_types=["finance.accounting.cycle"]).run_once()
    with db.session() as s:
        row = s.get(Job, job.id)
        assert row.status == JobStatus.DONE, row.last_error


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
