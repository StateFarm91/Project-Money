"""OPUS2 (P1-CULTURE-SWEEP-TIMEOUT): a classifier timeout no longer dead-letters the sweep.

Production (2026-10-27 job 34246, 2026-11-01 job 41979): attempt 1's classifier call timed
out. `culture.classify` caught only PermanentError/TransientError, so the TimeoutError escaped,
failed the attempt and left its budget reservation to expire; the paid-call intent was left
UNCERTAIN, so every retry correctly refused to re-send (F-307/F-339) and the job dead-lettered.

Now the timeout is caught in `classify`: nothing is filed, the unknown spend is counted once at
the reservation estimate (never zero), and nothing is re-sent. A later attempt that meets the
UNCERTAIN intent gets `PaidCallUnresolved`, a PermanentError, which `classify` already turns
into "nothing filed" -- so the sweep completes on its fixed topics either way.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_opus2_culture_sweep_timeout.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sqlalchemy import select  # noqa: E402

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import CostEntry  # noqa: E402
from brambleloop.culture import classify as C  # noqa: E402


class _Provider:
    model = "claude-haiku-4-5"
    cost_per_1k_input_cad = 0.001
    cost_per_1k_output_cad = 0.005
    calls = 0

    @staticmethod
    def key():
        return "k"

    def complete(self, system, user, *, max_tokens):
        type(self).calls += 1
        raise TimeoutError("The read operation timed out")


def _db():
    db = Database(f"sqlite:///{tempfile.mkdtemp()}/c.sqlite")
    db.create_all()
    return db


def _reservations(db):
    from brambleloop.core.models import SpendReservation

    with db.session() as s:
        return [(r.amount_cad, r.released_at is not None)
                for r in s.scalars(select(SpendReservation))]


def test_a_timeout_files_nothing_and_raises_nothing():
    out = C.classify(["Wednesday_(TV_series)"], provider=_Provider())
    assert out["filed"] == {} and out["unresolved"] is True
    assert "timed out" in out["reason"] and "not an empty culture" in out["note"]


def test_the_unknown_spend_is_counted_once_at_the_estimate_and_the_reservation_released():
    db = _db()
    _Provider.calls = 0
    out = C.classify(["A_topic", "B_topic"], provider=_Provider(), db=db)
    assert out["unresolved"] is True and _Provider.calls == 1        # sent once, not retried
    with db.session() as s:
        rows = [r for r in s.scalars(select(CostEntry)) if (r.detail or {}).get("billing")
                == "unknown_counted_at_estimate"]
        assert len(rows) == 1, rows
        assert rows[0].amount_cad > 0 and rows[0].amount_cad == rows[0].estimated_cad
        assert rows[0].agent == "market_radar"
    held = _reservations(db)
    assert held and all(released for _amount, released in held)      # never left to expire


def test_a_retry_that_meets_the_unresolved_intent_files_nothing_without_resending():
    from brambleloop.gateway.paid_calls import PaidCallUnresolved

    class _Unresolved(_Provider):
        def complete(self, system, user, *, max_tokens):
            type(self).calls += 1
            raise PaidCallUnresolved("anthropic.messages: earlier attempt has no known outcome")

    out = C.classify(["A_topic"], provider=_Unresolved(), db=_db())
    assert out["filed"] == {} and "no known outcome" in out["reason"]


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                fails += 1
                print("FAIL", name, repr(e))
                traceback.print_exc()
    print(f"{fails} failed")
    sys.exit(1 if fails else 0)
