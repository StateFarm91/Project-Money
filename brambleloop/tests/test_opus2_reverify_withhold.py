"""OPUS2-P0: P0-REVERIFY-WITHHOLD -- a failed re-verification durably withholds publication.

Found by W-INVENTORY: a failing `quality.reverified` audit row was kept only for a retention
window and `for_publish` did not read it, so after pruning, a product that failed
re-verification could advance. The verdict now lives on the stored release
(`publish.withholding` kind `quality_reverify`), per check, until that check passes again.
Check outcomes are simulated exactly as test_w4_departments does; everything else is real.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_opus2_reverify_withhold.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from sqlalchemy import delete, select  # noqa: E402

import test_w4_departments as D  # noqa: E402 - the department suite's release fixture
from brambleloop.core.models import AuditLog, PatternVersion  # noqa: E402
from brambleloop.publish import withholding as W  # noqa: E402
from brambleloop.runtime import quality_ops as QO  # noqa: E402


def _ref(cir):
    return {"slug": cir.slug, "version": cir.version}


def _sim(outcomes):
    """Each call of quality_ops.reverify returns the next outcome for its check."""
    it = iter(outcomes)
    real = QO.reverify
    QO.reverify = lambda db_, check, slug, version: {"check": check, **next(it)}
    return real


def _held(db, cir):
    return W.reasons(db, cir.slug, cir.version)


def test_a_failed_check_withholds_publication_on_the_stored_release():
    cir = D._cir()
    db = D._db(cir)
    real = _sim([{"ok": False, "problems": ["SIMULATED: writer drift"]}])
    try:
        out = D._run(db, "validator", "cir.reverse", _ref(cir))
    finally:
        QO.reverify = real
    assert out["withheld_checks"] == ["cir.reverse"]
    held = _held(db, cir)
    assert W.QUALITY_REVERIFY in held["reasons"] and held["blocks_publish"] is True
    assert "cir.reverse: SIMULATED: writer drift" in held["reasons"][W.QUALITY_REVERIFY]["reason"]
    # Publication only: the build stages still draft and rebuild (that is how a fix ships).
    assert held["blocks_build"] is False and held["summary"] is None
    with db.session() as s:
        pv = s.scalar(select(PatternVersion))
        assert pv.certified is True and pv.certificate.get("granted") is True


def test_pruning_the_audit_row_does_not_reopen_publication():
    from brambleloop.ops import publication_authority as pa
    from brambleloop.publish import release_gates

    cir = D._cir()
    db = D._db(cir)
    real = _sim([{"ok": False, "problems": ["SIMULATED: twin drift"]}])
    try:
        D._run(db, "validator", "cir.twin", _ref(cir))
    finally:
        QO.reverify = real
    with db.session() as s:
        s.execute(delete(AuditLog).where(AuditLog.action == QO.READING))
        assert not list(s.scalars(select(AuditLog).where(AuditLog.action == QO.READING)))
    g = release_gates.for_publish(db, slug=cir.slug, version=cir.version, read_only=True)
    assert g["blocks_release"] is True
    assert any(r.startswith("release withheld (re-verification)") for r in g["reasons"]), \
        g["reasons"][:6]
    with db.session() as s:
        rh = s.scalar(select(PatternVersion)).release_hash
    cert = pa.evidence(db, cir.slug, cir.version, rh)["certification"]
    assert cert["state"] != pa.PASS and cert["withheld"] is True


def test_each_check_clears_only_itself_and_the_kind_clears_when_none_fail():
    cir = D._cir()
    db = D._db(cir)
    ref = _ref(cir)
    real = _sim([{"ok": False, "problems": ["twin drift"]},
                 {"ok": False, "problems": ["reverse drift"]},
                 {"ok": True, "problems": []},
                 {"ok": True, "problems": []}])
    try:
        D._run(db, "validator", "cir.twin", ref)
        D._run(db, "validator", "cir.reverse", ref)
        assert _held(db, cir)["reasons"][W.QUALITY_REVERIFY]
        D._run(db, "validator", "cir.reverse", ref)              # reverse passes again
        held = _held(db, cir)
        assert "twin drift" in held["reasons"][W.QUALITY_REVERIFY]["reason"]
        assert "reverse drift" not in held["reasons"][W.QUALITY_REVERIFY]["reason"]
        D._run(db, "validator", "cir.twin", ref)                 # twin passes again
    finally:
        QO.reverify = real
    held = _held(db, cir)
    assert W.QUALITY_REVERIFY not in held["reasons"] and held["withheld"] is False
    with db.session() as s:
        cert = s.scalar(select(PatternVersion)).certificate
    assert W.REVERIFY_FAILED not in cert and cert.get("withholding_cleared", {}).get(
        W.QUALITY_REVERIFY)


def test_an_unknown_reading_changes_nothing_and_reconcile_keeps_the_kind():
    cir = D._cir()
    db = D._db(cir)
    ref = _ref(cir)
    real = _sim([{"ok": False, "problems": ["policy drift"]},
                 {"ok": None, "problems": [], "why": "no drafted listing"}])
    try:
        D._run(db, "policy", "gate.policy", ref)
        out = D._run(db, "policy", "gate.policy", ref)
    finally:
        QO.reverify = real
    assert out["ran"] is False
    assert W.QUALITY_REVERIFY in _held(db, cir)["reasons"]       # unknown is never a pass
    # The publish standards reconcile only their own kinds; this one is not theirs.
    W.reconcile(db, cir.slug, cir.version, standards={})
    assert W.QUALITY_REVERIFY in _held(db, cir)["reasons"]


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
