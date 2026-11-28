"""D-OWNER-PHOTO-VISION: the owner's 2026-11-28T16:50Z approval of anthropic-vision as the second,
independent vision vendor ("Im on my phone. You do it. I approve").

Pinned here:
1. Inside its own window the directive writes exactly anthropic-vision:vision, once, at the
   owner's ceilings (CA$2/day, CA$10/month, CA$1 per gallery), saying plainly no step-up happened.
2. It is never back-dated: before its given-at time nothing is written for that triple.
3. After its own 30-day window it is never renewed.
4. Its authority is its own: a row claiming D-OWNER-APPROVE-ALL for anthropic-vision, or this
   directive for another triple, or wider ceilings, or a login, authorises nothing.
5. The original directive's triples are unchanged.
"""
from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from brambleloop.gateway import paid_provider_gate as G  # noqa: E402
from brambleloop.ops import owner_directives as D  # noqa: E402

GIVEN = datetime(2026, 11, 28, 16, 50, tzinfo=timezone.utc)
NOW = GIVEN + timedelta(minutes=30)


def _db():
    from brambleloop.core.db import Database

    d = tempfile.mkdtemp(prefix="bl-pvd-")
    db = Database(f"sqlite:///{d}/t.db")
    db.create_all()
    G.ensure_tables(db)
    return db


def _rows(db):
    from sqlalchemy import select

    with db.session() as s:
        return [(r.provider, r.scope, r.activated_by, dict(r.step_up or {}),
                 float(r.daily_ceiling_cad), float(r.monthly_ceiling_cad),
                 float(r.per_gallery_cad), r.expires_at)
                for r in s.scalars(select(G.PaidProviderActivation))]


def test_1_written_once_inside_its_window_at_the_owners_ceilings():
    db = _db()
    out = D.apply(db, now=NOW)
    assert "anthropic-vision:vision" in out["activated"], out
    again = D.apply(db, now=NOW + timedelta(hours=1))
    assert "anthropic-vision:vision" in again["already"] and not again["activated"], again
    rows = [r for r in _rows(db) if r[0] == "anthropic-vision"]
    assert len(rows) == 1, rows
    prov, scope, actor, su, day, month, gallery, _exp = rows[0]
    assert (prov, scope) == ("anthropic-vision", "vision")
    assert actor == "owner-directive:D-OWNER-PHOTO-VISION"
    assert su["owner_directive"] == "D-OWNER-PHOTO-VISION"
    assert su["session_public_id"] is None and su["step_up_performed"] is False
    assert (day, month, gallery) == (2.0, 10.0, 1.0)
    assert G.activation_state(db, "anthropic-vision", "vision", now=NOW)["active"]


def test_2_never_back_dated_before_the_owner_said_it():
    db = _db()
    out = D.apply(db, now=GIVEN - timedelta(hours=1))
    assert "anthropic-vision:vision" not in out["activated"], out
    assert not [r for r in _rows(db) if r[0] == "anthropic-vision"]


def test_3_never_renewed_after_its_own_window():
    db = _db()
    D.apply(db, now=NOW)
    later = GIVEN + D.EXPIRY + timedelta(days=1)
    assert not G.activation_state(db, "anthropic-vision", "vision", now=later)["active"]
    fresh = _db()
    out = D.apply(fresh, now=later)
    assert "anthropic-vision:vision" not in out["activated"], out


def test_4_its_authority_is_its_own():
    db = _db()
    base = dict(activated_at=NOW, daily_ceiling_cad=2.0, monthly_ceiling_cad=10.0,
                per_gallery_cad=1.0, max_attempts_per_request=G.DEFAULT_MAX_ATTEMPTS,
                max_calls_per_run=G.DEFAULT_MAX_CALLS_PER_RUN,
                expires_at=NOW + timedelta(days=1))
    with db.session() as s:
        # the old directive's actor/id claiming the new triple
        s.add(G.PaidProviderActivation(
            provider="anthropic-vision", scope="vision", activated_by=D.ACTOR,
            step_up={"owner_directive": D.DIRECTIVE_ID, "session_public_id": None}, **base))
        # the new directive claiming a triple it does not cover
        s.add(G.PaidProviderActivation(
            provider="anthropic-vision", scope="generation",
            activated_by="owner-directive:D-OWNER-PHOTO-VISION",
            step_up={"owner_directive": "D-OWNER-PHOTO-VISION", "session_public_id": None},
            **base))
    assert not G.activation_state(db, "anthropic-vision", "vision", now=NOW)["active"]
    assert not G.activation_state(db, "anthropic-vision", "generation", now=NOW)["active"]
    wide = _db()
    with wide.session() as s:
        s.add(G.PaidProviderActivation(
            provider="anthropic-vision", scope="vision",
            activated_by="owner-directive:D-OWNER-PHOTO-VISION",
            step_up={"owner_directive": "D-OWNER-PHOTO-VISION", "session_public_id": None},
            **{**base, "daily_ceiling_cad": 5.0}))
    assert not G.activation_state(wide, "anthropic-vision", "vision", now=NOW)["active"]


def test_5_the_original_directive_is_unchanged():
    assert D.directive_for("flux-3-image", "generation")[0] == D.DIRECTIVE_ID
    assert D.directive_for("openai-vision", "vision")[0] == D.DIRECTIVE_ID
    assert D.DIRECTIVES[D.DIRECTIVE_ID]["sunset"] == D.SUNSET
    assert D.ACTIVATIONS[("openai-vision", "vision")] == {
        "daily_ceiling_cad": 2.0, "monthly_ceiling_cad": 10.0, "per_gallery_cad": 1.0}


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"OK   {t.__name__}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL {t.__name__} {exc!r}")
    print(f"{len(tests) - failed}/{len(tests)} passing")
    sys.exit(1 if failed else 0)
