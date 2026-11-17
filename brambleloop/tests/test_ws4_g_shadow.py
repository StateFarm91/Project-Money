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


def _certify(db, i, *, certified=True, release=None):
    """A certified PatternVersion of p<i> 1.0.0 at release <i>: what a real candidate is."""
    from brambleloop.core.models import PatternVersion, Product

    with db.session() as s:
        p = s.scalar(select(Product).where(Product.slug == f"p{i}"))
        if p is None:
            p = Product(slug=f"p{i}", title=f"fixture {i}")
            s.add(p)
            s.flush()
            s.add(PatternVersion(product_id=p.id, version="1.0.0", cir_json={},
                                 release_hash=release or f"{i:064d}", certified=certified))


def _decisions(db, c, approval_id, n=10, *, issue=(), start=NOW, actor="standing_issuer",
               certify=True):
    """n shadow decisions on n distinct certified releases; those in `issue` would-issue.
    Each row is stored at its own decision time, as the issuer writes it."""
    for i in range(n):
        if certify:
            _certify(db, i)
        with db.session() as s:
            when = start + timedelta(hours=i)
            s.add(AuditLog(actor=actor, action=sp.SHADOW_DECISION, at=when,
                           artifact=c["policy_id"], detail={
                               "approval_id": approval_id, "shadow": True,
                               "slug": f"p{i}", "version": "1.0.0", "release": f"{i:064d}",
                               "decision": "ISSUE" if i in issue else "HOLD",
                               "decided_at": when.isoformat()}))


def _readings(db, c, *, start, end, every_minutes=5, skip=None):
    t = start
    with db.session() as s:
        while t <= end:
            if not (skip and skip[0] <= t < skip[1]):
                s.add(AuditLog(actor=ST.ACTOR, action=ST.READING, artifact=c["policy_id"],
                               at=t, detail={"policy_id": c["policy_id"],
                                             "read_at": t.isoformat()}))
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


def test_holding_everything_compares_nothing_and_does_not_pass_agreement():
    """Review 6955504377 (LOW): zero would-issue decisions show no agreement at all."""
    try:
        db, c, a = _met_db(issue=(), grant=())
        f = G.g_shadow(db, now=LATER, record=False)["criteria"]["owner_agreement"]
        assert f["state"] == SB.FAIL and f["value"]["would_issue"] == 0, f
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



# ---- review 6955504377 M-1: G-SHADOW evidence rules ---------------------------------------

def test_main_probe_backdated_foreign_rows_on_nonexistent_releases_never_meet():
    """10 backdated `some_agent` rows on a nonexistent slug, an hour after approval: NOT MET."""
    try:
        db, c = _db(), content()
        _owner_keys()
        a = _approve(db, c)
        _decisions(db, c, a, actor="some_agent", certify=False, issue=(0, 1),
                   start=NOW - timedelta(days=9))
        _readings(db, c, start=LATER - timedelta(days=7, minutes=5), end=LATER)
        out = G.g_shadow(db, now=NOW + timedelta(hours=1), record=False)
        assert out["verdict"] == "NOT_MET", out
        assert out["criteria"]["shadow_period"]["value"]["distinct_releases"] == 0
    finally:
        _restore_all()


def test_only_the_issuers_rows_count():
    """The same rows the MET case uses, written by any other actor, are not evidence (the MET
    case itself is test_all_criteria_met_and_the_external_one_is_owed_not_claimed)."""
    try:
        db2, c2 = _db(), content()
        _owner_keys()
        a2 = _approve(db2, c2)
        _decisions(db2, c2, a2, issue=(0, 1), actor="some_agent")
        _readings(db2, c2, start=LATER - timedelta(days=7, minutes=5), end=LATER)
        for i in (0, 1):
            _grant(db2, i)
        out = G.g_shadow(db2, now=LATER, record=False)
        assert out["verdict"] == "NOT_MET", out
        assert out["criteria"]["shadow_period"]["value"]["distinct_releases"] == 0, out
    finally:
        _restore_all()


def test_rows_timed_before_the_signed_approval_do_not_count():
    try:
        db, c = _db(), content()
        _owner_keys()
        a = _approve(db, c)
        _decisions(db, c, a, issue=(0, 1), start=NOW - timedelta(days=2))  # 0..9 h, 2 d early
        _readings(db, c, start=LATER - timedelta(days=7, minutes=5), end=LATER)
        for i in (0, 1):
            _grant(db, i)
        out = G.g_shadow(db, now=LATER, record=False)
        assert out["criteria"]["shadow_period"]["value"]["distinct_releases"] == 0, out
    finally:
        _restore_all()


def test_a_backdated_insert_breaks_the_row_order_and_is_dropped():
    try:
        db, c, a = _met_db()
        before = G.g_shadow(db, now=LATER, record=False)["criteria"]["shadow_period"]["value"]
        _certify(db, 50)
        with db.session() as s:          # written last, claiming a time before earlier rows
            when = NOW + timedelta(minutes=30)
            s.add(AuditLog(actor="standing_issuer", action=sp.SHADOW_DECISION, at=when,
                           artifact=c["policy_id"], detail={
                               "approval_id": a, "shadow": True, "slug": "p50",
                               "version": "1.0.0", "release": f"{50:064d}",
                               "decision": "HOLD", "decided_at": when.isoformat()}))
        after = G.g_shadow(db, now=LATER, record=False)["criteria"]["shadow_period"]["value"]
        assert after["distinct_releases"] == before["distinct_releases"], (before, after)
    finally:
        _restore_all()


def test_a_row_whose_claimed_time_disagrees_with_its_stored_time_is_dropped():
    try:
        db, c, a = _met_db()
        _certify(db, 60)
        with db.session() as s:
            s.add(AuditLog(actor="standing_issuer", action=sp.SHADOW_DECISION, at=LATER,
                           artifact=c["policy_id"], detail={
                               "approval_id": a, "shadow": True, "slug": "p60",
                               "version": "1.0.0", "release": f"{60:064d}",
                               "decision": "HOLD",
                               "decided_at": (LATER - timedelta(days=1)).isoformat()}))
        v = G.g_shadow(db, now=LATER, record=False)["criteria"]["shadow_period"]["value"]
        assert v["distinct_releases"] == 10, v
    finally:
        _restore_all()


def test_candidates_must_be_certified_releases_of_real_products():
    try:
        db, c = _db(), content()
        _owner_keys()
        a = _approve(db, c)
        _decisions(db, c, a, issue=(0, 1))
        with db.session() as s:          # one uncertified, one at another release
            from brambleloop.core.models import PatternVersion, Product

            for i, change in ((2, "uncertified"), (3, "release")):
                pv = s.scalar(select(PatternVersion).join(Product).where(
                    Product.slug == f"p{i}"))
                if change == "uncertified":
                    pv.certified = False
                else:
                    pv.release_hash = "e" * 64
        v = G.g_shadow(db, now=LATER, record=False)["criteria"]["shadow_period"]["value"]
        assert v["distinct_releases"] == 8, v
    finally:
        _restore_all()


def test_a_row_dated_after_the_reading_does_not_count():
    try:
        db, c, a = _met_db()
        _certify(db, 70)
        when = LATER + timedelta(hours=1)            # stored and claimed in the future
        with db.session() as s:
            s.add(AuditLog(actor="standing_issuer", action=sp.SHADOW_DECISION, at=when,
                           artifact=c["policy_id"], detail={
                               "approval_id": a, "shadow": True, "slug": "p70",
                               "version": "1.0.0", "release": f"{70:064d}",
                               "decision": "HOLD", "decided_at": when.isoformat()}))
        v = G.g_shadow(db, now=LATER, record=False)["criteria"]["shadow_period"]["value"]
        assert v["distinct_releases"] == 10, v
    finally:
        _restore_all()


def test_an_approval_without_a_signed_approved_at_is_not_met():
    from brambleloop.ops import standing_issuer as SI

    real = SI.shadow_policy
    try:
        db, c, a = _met_db()
        SI.shadow_policy = lambda *a_, **k: {**real(*a_, **k), "approved_at": None}
        out = G.g_shadow(db, now=LATER, record=False)
        assert out["verdict"] != "MET", out
        assert out["criteria"]["policy_approved"]["state"] == SB.FAIL, out
    finally:
        SI.shadow_policy = real
        _restore_all()


def test_activation_needs_a_fresh_g_shadow_met_for_this_approval():
    try:
        db, c = _db(), content()
        _owner_keys()
        a = _approve(db, c)
        why = sp.activation_refusals(db, a, now=LATER)
        assert any("G-SHADOW is not MET" in w for w in why), why
    finally:
        _restore_all()


if __name__ == "__main__":
    import _minipytest

    _minipytest.run_module(globals())
