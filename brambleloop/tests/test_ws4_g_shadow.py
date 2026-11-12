"""WS4 Stage D acceptance: the G-SHADOW reading (design §7.3; M6 item 10).

Each criterion is read from rows: the approved policy, 7 days and 10 real candidates of
shadow decisions, zero would-issue releases the owner refused or never granted (read from the
VERIFIED owner publication grant chain), and 7 days of stop-watch readings with no silence
over 30 minutes. The tests-and-mutants criterion is EXTERNAL and never claimed.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import os
import sys
from datetime import timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy import select  # noqa: E402

from brambleloop.core import owner_grant_keys as K  # noqa: E402
from brambleloop.core.models import AuditLog  # noqa: E402
from brambleloop.ops import publication_authority as pub  # noqa: E402
from brambleloop.ops import standing_boundary as SB  # noqa: E402
from brambleloop.ops import standing_policy as sp  # noqa: E402
from brambleloop.ops import standing_shadow_gate as G  # noqa: E402
from brambleloop.ops import standing_stop as ST  # noqa: E402
from test_ws4_policy_object import NOW, _approve, _db, _restore, content  # noqa: E402

_SAVED: dict = {}
LATER = NOW + timedelta(days=8)


def _owner_keys():
    for k, v in K.generate_keypair().items():
        _SAVED.setdefault(k, os.environ.get(k))
        os.environ[k] = v


def _restore_all():
    for k, v in _SAVED.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    _restore()


def _decisions(db, c, approval_id, n=10, *, issue=(), start=NOW):
    """n shadow decisions on n distinct releases; those indexed in `issue` would-issue."""
    with db.session() as s:
        for i in range(n):
            s.add(AuditLog(actor="standing_issuer", action=sp.SHADOW_DECISION,
                           artifact=c["policy_id"], detail={
                               "approval_id": approval_id, "shadow": True,
                               "slug": f"p{i}", "version": "1.0.0", "release": f"{i:064d}",
                               "decision": "ISSUE" if i in issue else "HOLD",
                               "decided_at": (start + timedelta(hours=i)).isoformat()}))


def _readings(db, c, *, start, end, every_minutes=5, skip=None):
    t = start
    with db.session() as s:
        while t <= end:
            if not (skip and skip[0] <= t < skip[1]):
                s.add(AuditLog(actor=ST.ACTOR, action=ST.READING, artifact=c["policy_id"],
                               detail={"policy_id": c["policy_id"], "read_at": t.isoformat()}))
            t += timedelta(minutes=every_minutes)


def _grant(db, i, *, revoke=False):
    with K.owner_request("owner-session"):
        gid = pub.LEDGER.append(db, action=pub.APPROVED, artifact=f"p{i}@1.0.0", detail={
            "principal": pub.PRINCIPAL, "action": pub.ACTION, "scope": f"p{i}@1.0.0",
            "release": f"{i:064d}", "content": {"x": i}, "digest": "d" * 64,
            "reason": "test", "approved_at": NOW.isoformat(),
            "expires_at": (NOW + timedelta(days=1)).isoformat()})
    if revoke:
        pub.LEDGER.revoke(db, gid)
    return gid


def _met_db(*, issue=(0, 1), grant=(0, 1)):
    db, c = _db(), content()
    _owner_keys()
    a = _approve(db, c)
    _decisions(db, c, a, issue=issue)
    _readings(db, c, start=LATER - timedelta(days=7, minutes=5), end=LATER)
    for i in grant:
        _grant(db, i)
    return db, c, a


def test_all_criteria_met_and_the_external_one_is_owed_not_claimed():
    try:
        db, c, a = _met_db()
        out = G.g_shadow(db, now=LATER)
        assert out["verdict"] == "MET" and out["owes"] == ["tests_and_mutants"], out
        assert out["criteria"]["tests_and_mutants"]["state"] == G.EXTERNAL
        assert out["criteria"]["owner_agreement"]["value"] == {
            "would_issue": 2, "owner_approved": 2, "owner_refused": 0, "undecided": 0}
        with db.session() as s:
            row = s.scalar(select(AuditLog).where(AuditLog.action == G.READING))
            assert row.detail["verdict"] == "MET" and row.artifact == c["policy_id"]
    finally:
        _restore_all()


def test_no_approved_policy_is_not_met():
    try:
        db = _db()
        out = G.g_shadow(db, now=LATER)
        assert out["verdict"] == "NOT_MET"
        assert out["criteria"]["policy_approved"]["state"] == SB.FAIL
    finally:
        _restore_all()


def test_fewer_than_seven_days_or_ten_candidates_is_not_met():
    try:
        db, c, a = _met_db()
        out = G.g_shadow(db, now=NOW + timedelta(days=6), record=False)
        assert out["criteria"]["shadow_period"]["state"] == SB.FAIL
        assert "less than 7 days" in out["criteria"]["shadow_period"]["why"]
        db2, c2 = _db(), content()
        a2 = _approve(db2, c2)
        _decisions(db2, c2, a2, n=9)
        out = G.g_shadow(db2, now=LATER, record=False)
        assert "9 distinct candidate" in out["criteria"]["shadow_period"]["why"], out
        # Decisions of another approval do not count.
        _decisions(db2, c2, a2 + 999, n=10)
        assert G.g_shadow(db2, now=LATER, record=False)["criteria"]["shadow_period"][
            "state"] == SB.FAIL
    finally:
        _restore_all()


def test_a_would_issue_release_the_owner_refused_fails():
    try:
        db, c, a = _met_db(grant=(0,))
        _grant(db, 1, revoke=True)
        out = G.g_shadow(db, now=LATER, record=False)
        f = out["criteria"]["owner_agreement"]
        assert out["verdict"] == "NOT_MET" and f["state"] == SB.FAIL, f
        assert "owner refused" in f["why"] and f["value"]["owner_refused"] == 1
    finally:
        _restore_all()


def test_a_would_issue_release_the_owner_never_granted_is_held_and_fails():
    try:
        db, c, a = _met_db(grant=(0,))
        f = G.g_shadow(db, now=LATER, record=False)["criteria"]["owner_agreement"]
        assert f["state"] == SB.FAIL and "not decided (held)" in f["why"], f
        # A grant for a different release of the same product is not this release's.
        with K.owner_request("owner-session"):
            pub.LEDGER.append(db, action=pub.APPROVED, artifact="p1@1.0.0", detail={
                "principal": pub.PRINCIPAL, "action": pub.ACTION, "scope": "p1@1.0.0",
                "release": "f" * 64, "content": {}, "digest": "d" * 64, "reason": "t",
                "approved_at": NOW.isoformat(),
                "expires_at": (NOW + timedelta(days=1)).isoformat()})
        assert G.g_shadow(db, now=LATER, record=False)["criteria"]["owner_agreement"][
            "state"] == SB.FAIL
    finally:
        _restore_all()


def test_a_grant_chain_that_does_not_verify_is_unknown():
    try:
        db, c, a = _met_db()
        with db.session() as s:
            row = s.scalar(select(AuditLog).where(AuditLog.action == pub.APPROVED))
            row.detail = {**row.detail, "release": "9" * 64}       # edited after sealing
        f = G.g_shadow(db, now=LATER, record=False)["criteria"]["owner_agreement"]
        assert f["state"] == SB.UNKNOWN and "does not verify" in f["why"], f
    finally:
        _restore_all()


def test_holding_everything_compares_nothing_and_passes_agreement():
    try:
        db, c, a = _met_db(issue=(), grant=())
        f = G.g_shadow(db, now=LATER, record=False)["criteria"]["owner_agreement"]
        assert f["state"] == SB.PASS and f["value"]["would_issue"] == 0, f
    finally:
        _restore_all()


def test_stop_watch_silence_or_a_short_history_is_not_met():
    try:
        db, c = _db(), content()
        a = _approve(db, c)
        _decisions(db, c, a)
        _readings(db, c, start=LATER - timedelta(days=7, minutes=5), end=LATER,
                  skip=(LATER - timedelta(days=3), LATER - timedelta(days=3, minutes=-31)))
        f = G.g_shadow(db, now=LATER, record=False)["criteria"]["stop_watch_continuity"]
        assert f["state"] == SB.FAIL and "silent" in f["why"], f
        # A 30-minute gap exactly is allowed.
        db2, c2 = _db(), content()
        a2 = _approve(db2, c2)
        _readings(db2, c2, start=LATER - timedelta(days=7, minutes=30), end=LATER,
                  every_minutes=30)
        assert G.g_shadow(db2, now=LATER, record=False)["criteria"][
            "stop_watch_continuity"]["state"] == SB.PASS
        # Readings that began less than 7 days ago.
        db3, c3 = _db(), content()
        _approve(db3, c3)
        _readings(db3, c3, start=LATER - timedelta(days=6), end=LATER)
        f = G.g_shadow(db3, now=LATER, record=False)["criteria"]["stop_watch_continuity"]
        assert f["state"] == SB.FAIL and "7 days" in f["why"], f
        # Silence since the last reading counts too.
        db4, c4 = _db(), content()
        _approve(db4, c4)
        _readings(db4, c4, start=LATER - timedelta(days=8), end=LATER - timedelta(hours=1))
        assert G.g_shadow(db4, now=LATER, record=False)["criteria"][
            "stop_watch_continuity"]["state"] == SB.FAIL
    finally:
        _restore_all()


def test_the_issuer_job_records_the_reading():
    import inspect

    from brambleloop.runtime import standing_policy_ops

    src = inspect.getsource(standing_policy_ops.handle_issuer_shadow)
    assert "standing_shadow_gate.g_shadow(ctx.db)" in src


if __name__ == "__main__":
    import _minipytest

    _minipytest.run_module(globals())
