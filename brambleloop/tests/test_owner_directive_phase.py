"""D-OWNER-AUDIT-APPROVALS (F-01): the owner's directed SHADOW -> STAGING move.

The owner approved the phase transition in words ("I approve my stuff... Get p0 done"), with no
step-up. `ops.owner_directives.apply_phase` records it through `core.phase` with every gate kept:
one step up, cited readiness and rollback evidence resolving to real rows, and the launch
readiness verdict evaluated now and `ready`. The row's principal names the directive and carries
`owner_directed_without_attestation`. A refusal writes no transition and is recorded.

Every row here is a TEST FIXTURE; the readiness verdicts are synthetic.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_owner_directive_phase.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from sqlalchemy import select  # noqa: E402

from brambleloop.core import phase as P  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog  # noqa: E402
from brambleloop.ops import owner_directives as OD  # noqa: E402
from phase_fixture import synthetic_evidence, synthetic_readiness  # noqa: E402

ENV = {"BRAMBLELOOP_OPS_TOKEN": "directive-phase-synthetic-credential-not-a-secret"}


def _db() -> Database:
    db = Database(f"sqlite:///{tempfile.mkdtemp()}/dp.sqlite")
    db.create_all()
    return db


def _transitions(db) -> list:
    with db.session() as s:
        return [(r.actor, dict(r.detail)) for r in s.scalars(
            select(AuditLog).where(AuditLog.action == P.TRANSITION).order_by(AuditLog.id))]


def _outcomes(db) -> list:
    with db.session() as s:
        return [dict(r.detail).get("outcome") for r in s.scalars(
            select(AuditLog).where(AuditLog.action == OD.PHASE_ACTION).order_by(AuditLog.id))]


def test_a_ready_verdict_records_staging_under_the_directive():
    with patch.dict(os.environ, ENV):
        db = _db()
        synthetic_evidence(db)
        out = OD.apply_phase(db, readiness_verdict=synthetic_readiness)
        assert out["recorded"] is True, out
        rows = _transitions(db)
        assert len(rows) == 1, rows
        actor, d = rows[0]
        assert actor == "owner-directive:D-OWNER-AUDIT-APPROVALS", actor
        assert d["from"] == "shadow" and d["to"] == "staging", d
        assert d["attestation"] == "owner_directed_without_attestation", d
        assert P.chain(db)["valid"], "the directed row verifies in the sealed chain"
        assert P.resolve(db, env={P.ENV_VAR: "staging"})["phase"] == "staging"
        assert OD.apply_phase(db, readiness_verdict=synthetic_readiness).get("already") == \
            "staging", "idempotent"
        assert len(_transitions(db)) == 1


def test_not_ready_records_no_transition_and_says_why():
    with patch.dict(os.environ, ENV):
        db = _db()
        synthetic_evidence(db)
        out = OD.apply_phase(db, readiness_verdict=lambda _db, _to: {
            "ready": False, "failing": ["findable:catalogue_depth"]})
        assert out["recorded"] is False and "not ready" in out["refused"], out
        assert _transitions(db) == []
        assert _outcomes(db) == ["refused"]


def test_without_evidence_rows_it_is_refused():
    with patch.dict(os.environ, ENV):
        db = _db()
        out = OD.apply_phase(db, readiness_verdict=synthetic_readiness)
        assert out["recorded"] is False and "evidence" in out["refused"], out
        assert _transitions(db) == []


def test_the_directive_covers_only_shadow_to_staging():
    with patch.dict(os.environ, ENV):
        db = _db()
        synthetic_evidence(db)
        try:
            P.record_directive_transition(db, directive=OD.AUDIT_APPROVALS_ID,
                                          to="limited_production", reason="x",
                                          evidence_refs=synthetic_evidence(db),
                                          readiness_verdict=synthetic_readiness)
        except ValueError as exc:
            assert "does not cover" in str(exc), exc
        else:
            raise AssertionError("a move the table does not list was accepted")
        try:
            P.record_directive_transition(db, directive="D-NOT-A-DIRECTIVE", to="staging",
                                          reason="x", evidence_refs=synthetic_evidence(db),
                                          readiness_verdict=synthetic_readiness)
        except ValueError:
            pass
        else:
            raise AssertionError("an unknown directive was accepted")
        assert _transitions(db) == []


def test_the_owner_path_still_requires_the_credential():
    with patch.dict(os.environ, ENV):
        db = _db()
        try:
            P.record_transition(db, authorization="wrong", to="staging", reason="x",
                                evidence_refs=synthetic_evidence(db),
                                readiness_verdict=synthetic_readiness)
        except Exception:  # noqa: BLE001 - refused, any credential error
            pass
        else:
            raise AssertionError("a wrong credential recorded a transition")
        assert _transitions(db) == []


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"OK   {name}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"{len(tests) - failed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
