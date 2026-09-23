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


def test_a_spent_balance_stops_the_spending_it_cannot_check():
    """Rendering is prepaid elsewhere and would succeed. That is the trap.

    The revised pack rendered eight images at CA$0.08 and died at the first vision call,
    twice. Money spent to produce something that cannot be described, compared, gated or
    disclosed is money spent on nothing.
    """
    from brambleloop.cir.compiler import compile_cir
    from brambleloop.cir.twin import build_twin
    from brambleloop.products.builder import for_slug
    from brambleloop.publish import owned_photography
    from brambleloop.visual import reference_pack

    db = _db()
    funding.note(db, LIVE)
    assert funding.blocked(db)["blocked"] is True

    cir = for_slug("cloudline-baby-blanket")
    record = owned_photography.make(db, cir, build_twin(cir, compile_cir(cir)))
    assert record["made"] is False
    assert record["waiting_on"] == "model_provider_balance"

    pack = reference_pack.build(db)
    assert pack["built"] is False
    assert pack["stage"] == "funding"
    assert pack["spent_cad"] == 0.0


def test_the_action_is_closed_by_the_thing_working_rather_than_by_a_tick():
    """The other direction of the same staleness: an owner action that stays open after the
    owner has done the thing is how a queue stops being read."""
    db = _db()
    funding.note(db, LIVE)
    assert funding.blocked(db)["blocked"] is True

    assert funding.cleared(db)["cleared"] is True
    assert funding.blocked(db)["blocked"] is False
    # Idempotent: nothing to close is not an error.
    assert funding.cleared(db)["cleared"] is False


def test_the_probe_is_the_thing_that_closes_it():
    """Because the probe is the smallest real call there is, and a real call succeeding is
    exactly the evidence that the balance is no longer the blocker."""
    import ast

    from brambleloop.gateway import anthropic as gw

    tree = ast.parse((ROOT / "src/brambleloop/gateway/anthropic.py").read_text())
    probe = next(n for n in ast.walk(tree)
                 if isinstance(n, ast.FunctionDef) and n.name == "probe")
    called = {n.func.attr for n in ast.walk(probe)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    assert {"note", "cleared"} <= called, called
    assert gw.usable is not None


def test_the_worker_checks_both_outputs_and_exceptions():
    import ast

    tree = ast.parse((ROOT / "src/brambleloop/runtime/worker.py").read_text())
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Name) and n.func.id == "_note_funding"]
    assert len(calls) >= 2, "the funding check is on only one path"


def test_a_successful_vision_probe_clears_the_funding_block_too():
    """The evidence was on file and the gate could not read it.

    `funding.blocked` reads the open owner action, and `funding.cleared` was reached only
    from `model.probe`. Live, 2026-09-23: the vision probe came back working at 20:37Z
    while the action stayed open on an 18:00Z `model.probe` failure, so both
    owner-authorised experiments went on refusing for three and a half hours with the proof
    that they could run already recorded.

    A gate reading one specific probe rather than the thing the probe is evidence of. The
    clear belongs to any real call that got an answer, which is what `cleared`'s own
    docstring says it is for.
    """
    import inspect as _inspect

    from brambleloop.gateway import anthropic as gw

    source = _inspect.getsource(gw.vision_probe)
    assert "funding.cleared" in source, (
        "a vision call that got an answer still could not clear a funding block")


def test_the_clear_is_reached_from_both_probes_not_only_one():
    """Both halves of the same evidence, so neither can be the only way through."""
    import inspect as _inspect

    from brambleloop.gateway import anthropic as gw

    for probe in (gw.vision_probe, gw.probe):
        assert "funding.cleared" in _inspect.getsource(probe), probe.__name__


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
