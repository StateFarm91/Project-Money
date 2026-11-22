"""ENG-PAID-REFUSALS: the readback says why paid calls are refused, and each activation's state.

Production (19h18, 2026-11-22T00:58Z): paid_call_dedupe read 47 DECLINED intents out of 50 in
24 h, and nothing said why. `paid_call_dedupe` now carries refusals by provider and fixed code,
declined intents by provider and fixed class, per-activation state (active, expiry, the
directive's sunset, ceiling, spent or reserved today, reservations left open over an hour),
and the concept judge's route. Counts, codes and provider names only.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_paid_refusals.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
os.environ.setdefault("BRAMBLELOOP_PHASE", "shadow")


def _db():
    import tempfile

    from brambleloop.core.db import Database

    db = Database(f"sqlite:///{tempfile.mkdtemp(prefix='paidref-')}/t.sqlite")
    db.create_all()
    return db


def test_refusals_are_counted_by_provider_and_code():
    from brambleloop.gateway import paid_provider_gate as G
    from brambleloop.ops import production_evidence as PE

    db = _db()
    G.ensure_tables(db)
    try:   # not activated: refused before any network I/O, and recorded with its code
        G.enforce(db, provider=G.OPENAI_VISION, scope=G.VISION, estimate_cad=0.01,
                  fingerprint="f" * 16, reservation_id=None, call=lambda: None,
                  classify=lambda e: G.RELEASED, purpose="test")
        raise AssertionError("an unactivated provider was not refused")
    except G.PaidCallRefused as exc:
        assert exc.code == G.NOT_ACTIVATED, exc.code
    now = datetime.now(timezone.utc)
    out = PE.paid_calls(db, now=now)
    assert out["refusals_by_provider_code"] == {
        "openai-vision": {"not_activated_by_owner": 1}}, out["refusals_by_provider_code"]
    acts = out["activations"]
    assert set(acts) == {"flux-3-image:generation", "openai-vision:vision"}, acts
    assert acts["openai-vision:vision"]["active"] is False
    assert acts["openai-vision:vision"]["state_code"] == "not_activated_by_owner"
    assert acts["openai-vision:vision"]["directive_sunset_at"]
    assert out["concept_judge"]["route_now"] == "none", out["concept_judge"]


def test_an_active_activation_shows_its_state_and_ceiling():
    import _paid_activation as paid

    from brambleloop.gateway import paid_provider_gate as G
    from brambleloop.ops import production_evidence as PE

    db = _db()
    paid.activate(db, G.OPENAI_VISION, G.VISION, daily=2.0, monthly=10.0, per_gallery=1.0)
    out = PE.paid_calls(db, now=datetime.now(timezone.utc))
    a = out["activations"]["openai-vision:vision"]
    assert a["active"] is True and a["status"] == "active", a
    assert a["daily_ceiling_cad"] == 2.0 and a["spent_or_reserved_today_cad"] == 0.0, a
    assert a["reserved_older_than_1h"] == 0, a


def test_privacy_no_free_text():
    from brambleloop.gateway import paid_provider_gate as G
    from brambleloop.ops import production_evidence as PE

    db = _db()
    G.ensure_tables(db)
    try:
        G.enforce(db, provider=G.OPENAI_VISION, scope=G.VISION, estimate_cad=0.01,
                  fingerprint="g" * 16, reservation_id=None, call=lambda: None,
                  classify=lambda e: G.RELEASED, purpose="secret purpose words")
    except G.PaidCallRefused:
        pass
    blob = json.dumps(PE.paid_calls(db, now=datetime.now(timezone.utc)))
    assert "secret purpose words" not in blob and "owner's" not in blob, blob[:400]


if __name__ == "__main__":
    fails = 0
    for name, t in sorted(globals().items()):
        if name.startswith("test_") and callable(t):
            try:
                t()
                print(f"OK   {name}")
            except Exception as exc:  # noqa: BLE001
                fails += 1
                print(f"FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"{3 - fails} passed, {fails} failed")
    sys.exit(1 if fails else 0)
