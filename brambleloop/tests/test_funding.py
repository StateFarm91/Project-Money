"""A spent account balance reaches the one person who can fix it.

Found live: the reference-pack build rendered its images, spent CA$0.08 and died at the
first vision call because the Anthropic balance was empty. Every component behaved
correctly -- classified permanent, recorded honestly, job completed green with `built:
false` -- and nobody was told.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import OwnerAction  # noqa: E402
from brambleloop.ops import funding  # noqa: E402

LIVE = ('anthropic 400: {"type":"error","error":{"type":"invalid_request_error",'
        '"message":"Your credit balance is too low to access the Anthropic API."}}')


def _db() -> Database:
    db = Database("sqlite://")
    db.create_all()
    return db


def _actions(db) -> list[OwnerAction]:
    with db.session() as s:
        return list(s.scalars(select(OwnerAction).where(
            OwnerAction.requirement_key == funding.REQUIREMENT_KEY)))


def test_the_live_message_is_recognised_and_an_outage_is_not():
    assert funding.detect(LIVE) is True
    assert funding.detect("anthropic 529: overloaded") is False
    assert funding.detect("anthropic unreachable: timed out") is False
    assert funding.detect("") is False


def test_it_names_the_account_to_top_up_rather_than_a_provider():
    """'A model provider is down' sends somebody to the wrong screen, twice: it is not down
    and it is not all of them."""
    db = _db()
    assert funding.note(db, LIVE)["raised"] is True
    action = _actions(db)[0]
    assert "Anthropic" in action.action and "console.anthropic.com" in action.action
    assert action.minutes == 5 and action.max_cost_cad == 25.0
    assert "only\nyou can add" in action.reason or "only you can add" in action.reason
    # Out of money is not over budget, and the reason says so: the ceiling is a policy this
    # system enforces on itself and was nowhere near breached at the time.
    assert "not the monthly ceiling" in action.reason
    # And what keeps working is stated, because renders succeeding while their checks fail
    # is the confusing part.
    assert "prepaid elsewhere" in action.consequence_of_delay


def test_one_spent_balance_raises_one_action():
    """It fails every call that follows it, and a queue with forty copies is unread."""
    db = _db()
    for _ in range(5):
        funding.note(db, LIVE)
    assert len(_actions(db)) == 1


def test_a_handler_that_completed_honestly_still_reaches_the_queue():
    """The pack build caught it, recorded it and completed green. That is correct behaviour
    from the handler and silence from the system, so the worker reads outputs too."""
    import json

    db = _db()
    outputs = {"ran": True, "built": False, "stage": "observe:neutral_portrait",
               "why": LIVE, "spent_cad": 0.0822}
    from brambleloop.runtime.worker import _note_funding

    _note_funding(db, json.dumps(outputs))
    assert len(_actions(db)) == 1


def test_the_worker_checks_both_outputs_and_exceptions():
    import ast

    tree = ast.parse((ROOT / "src/brambleloop/runtime/worker.py").read_text())
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Name) and n.func.id == "_note_funding"]
    assert len(calls) >= 2, "the funding check is on only one path"


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, repr(e))
    sys.exit(1 if fails else 0)
