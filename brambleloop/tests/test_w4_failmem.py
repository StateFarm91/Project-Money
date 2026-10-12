"""W4-FAILMEM: fingerprinted, scoped failure memory (F-378, F-427, F-428, F-706).

Run: cd brambleloop && PYTHONPATH=src:tests .venv/bin/python tests/test_w4_failmem.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
_TMP = tempfile.mkdtemp(prefix="w4_failmem_")

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import Improvement  # noqa: E402
from brambleloop.improve import cells, failure_memory as fm  # noqa: E402

_n = [0]
HYP = ("raising the minimum price floor by one dollar should lift contribution margin because "
       "the measured demand curve on 12 listings is flat between 9 and 10 dollars")


def _db() -> Database:
    _n[0] += 1
    db = Database(f"sqlite:///{_TMP}/d{_n[0]}.sqlite")
    db.create_all()
    return db


def _propose(db, **kw):
    return cells.propose(db, cell="pricing", hypothesis=kw.pop("hypothesis", HYP),
                         expected_effect="margin rises", rollback_ref="config:pricing:1",
                         touches=("pricing",), proposed_by="pricing_agent", **kw)


def _refused(fn) -> str:
    try:
        fn()
    except cells.ImprovementRefused as exc:
        return str(exc)
    raise AssertionError("expected a refusal")


def _measured_failure(db) -> int:
    cells.record_capability(db, "pricing", 10.0)
    iid = _propose(db, evidence_ids=("orders:1-40",))
    assert cells.test_result(db, iid, 5.0) == cells.REJECTED
    return iid


def test_the_same_failed_improvement_months_later_is_refused():
    """F-706's v0.20 scenario: a measured loss, then the identical proposal again."""
    db = _db()
    iid = _measured_failure(db)
    why = _refused(lambda: _propose(db, evidence_ids=("orders:1-40",)))
    assert f"improvements:{iid}" in why and "F-378" in why, why
    assert _refused(lambda: _propose(db))  # citing nothing is the same evidence
    from sqlalchemy import func, select

    from brambleloop.core.models import AuditLog

    with db.session() as s:  # each refusal is audited, so "failures avoided" is countable
        assert s.scalar(select(func.count()).select_from(AuditLog).where(
            AuditLog.action == fm.REFUSAL_ACTION)) == 2


def test_new_evidence_or_a_changed_premise_reopens_the_question():
    db = _db()
    _measured_failure(db)
    a = _propose(db, evidence_ids=("orders:1-40", "orders:41-90"))
    with db.session() as s:
        assert s.get(Improvement, a).evidence["evidence_ids"] == ["orders:1-40", "orders:41-90"]
    b = _propose(db, premise="after the holiday season demand shifted to gift buyers")
    assert a != b


def test_a_refusal_or_first_measurement_is_not_a_failure():
    """B-686: a rejection with no measurement must never retire the idea."""
    db = _db()
    iid = _propose(db)  # no capability recorded: no baseline
    assert cells.test_result(db, iid, 7.0) == cells.REJECTED
    again = _propose(db)  # allowed: nothing was measured to lose
    assert again != iid
    db2 = _db()
    cells.record_capability(db2, "pricing", 10.0)
    r = _propose(db2)
    cells.reject(db2, r, why="withdrawn before any trial")
    assert _propose(db2)  # an explicit reject without a result is not a measured failure


def test_a_reverted_promotion_is_remembered():
    db = _db()
    cells.record_capability(db, "pricing", 10.0)
    iid = _propose(db)
    with db.session() as s:  # the end state `revert` writes after a verified rollback
        row = s.get(Improvement, iid)
        row.state = cells.REVERTED
        row.evidence = {**row.evidence, "reverted_because": "margin fell after promotion"}
    assert "margin fell" in _refused(lambda: _propose(db))


def test_digits_are_kept_so_new_measurements_are_a_new_claim():
    db = _db()
    _measured_failure(db)
    assert _propose(db, hypothesis=HYP.replace("12 listings", "31 listings"))


def test_scope_blocks_only_inside_the_observed_conditions():
    db = _db()
    scope = {"method": "render the gallery on provider x", "class": "pricing",
             "conditions": {"provider": "x", "balance": "empty"}}
    fm.record(db, cell="pricing", method="render the gallery on provider x", scope=scope,
              evidence_ids=["audit:1"], source="test:scope", reason="402 credits depleted")
    inside = {**scope, "conditions": {"provider": "x", "balance": "empty", "extra": "y"}}
    outside = {**scope, "conditions": {"provider": "x", "balance": "funded"}}
    kw = dict(method="render the gallery on provider x")
    assert "402" in _refused(lambda: _propose(db, scope=inside, **kw))
    assert _propose(db, scope=outside, **kw)


def test_generalisation_beyond_scope_needs_new_evidence():
    narrow = {"method": "m", "class": "c", "conditions": {"provider": "x"}}
    wide = {"method": "m", "class": "c", "conditions": {}}
    try:
        fm.generalise(narrow, wide)
    except fm.FailureMemoryRefused as exc:
        assert "cannot be generalised" in str(exc)
    else:
        raise AssertionError("widened without evidence")
    assert fm.generalise(narrow, wide, new_evidence_ids=["audit:9"]) == wide
    deeper = {"method": "m", "class": "c", "conditions": {"provider": "x", "region": "ca"}}
    assert fm.generalise(narrow, deeper) == deeper  # narrowing needs nothing


def test_records_need_evidence_and_scope():
    db = _db()
    for kwargs in ({"evidence_ids": [], "scope": {"method": "m", "class": "c"}},
                   {"evidence_ids": ["x:1"], "scope": {"method": "m"}}):
        try:
            fm.record(db, cell="pricing", method="m", source="t", reason="r", **kwargs)
        except fm.FailureMemoryRefused:
            continue
        raise AssertionError(kwargs)


def test_decision_log_dead_ends_are_seeded_and_enforced():
    db = _db()
    rows = fm.listing(db)
    sources = {r["source"] for r in rows}
    assert {"DECISION_LOG:B-650", "DECISION_LOG:B-634", "DECISION_LOG:B-675",
            "DECISION_LOG:B-686", "DECISION_LOG:B-647"} <= sources, sources
    assert fm.ensure_seeded(db) == 0 or len(fm.listing(db)) == len(rows)  # idempotent
    seed = next(s for s in fm.SEEDS if s["evidence_ids"] == ["DECISION_LOG:B-650"])
    hyp = ("re-rendering every frame of the gallery whenever one floor fails should raise the "
           "usable-gallery rate because a fresh draw replaces the failed frame")
    why = _refused(lambda: cells.propose(
        db, cell="creative_assets", hypothesis=hyp, expected_effect="usable rate rises",
        rollback_ref="config:render:1", proposed_by="visual", method=seed["method"],
        scope=seed["scope"]))
    assert "DECISION_LOG:B-650" in why, why
    assert cells.propose(
        db, cell="creative_assets", hypothesis=hyp, expected_effect="usable rate rises",
        rollback_ref="config:render:1", proposed_by="visual", method=seed["method"],
        scope=seed["scope"], evidence_ids=("renders:batch-7",))


def test_failure_memory_is_a_non_rederivable_record():
    from brambleloop.core import continuity

    assert "failure_memory" in continuity.NON_REDERIVABLE


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
