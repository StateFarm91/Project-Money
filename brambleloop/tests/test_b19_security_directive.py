"""B19 security review (review-results/b19-security): mutation tests for D-OWNER-APPROVE-ALL.

Each test kills a mutant the original suite let live:

* S1 (HIGH, renewal): `apply` had no sunset. Any store without a directive row -- a fresh
  environment, a database restored from a pre-2026-11-20 backup, a recreated table -- was
  given a fresh 30-day activation on every boot, for ever. The directive ("approve what is
  pending now") must stop minting authority 30 days after it was given.
* S2 (MEDIUM, authority): the gate trusted any row carrying the directive's actor and marker,
  whatever its ceilings or lifetime. A row with the directive's name but a CA$90 monthly
  ceiling, 500 calls per run or a 2099 expiry authorised spend. Directive authority now
  covers only rows inside the directive's own table and window.
* S3 (LOW, race): two processes (boot + hourly job) could both see "no prior" and write two
  rows; `apply` now checks-and-writes under the spend lock.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sqlalchemy import select  # noqa: E402

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.gateway import paid_provider_gate as G  # noqa: E402
from brambleloop.ops import owner_directives as D  # noqa: E402

_TMP = tempfile.mkdtemp()
_N = [0]
NOW = datetime(2026, 11, 20, 22, 0, tzinfo=timezone.utc)
GIVEN = datetime(2026, 11, 20, 13, 20, tzinfo=timezone.utc)


def _db():
    _N[0] += 1
    db = Database(f"sqlite:///{_TMP}/s{_N[0]}.db")
    db.create_all()
    G.ensure_tables(db)
    return db


def _forge(db, **over):
    base = dict(provider="flux-3-image", scope="generation", activated_by=D.ACTOR,
                activated_at=NOW, step_up={"owner_directive": D.DIRECTIVE_ID,
                                           "session_public_id": None},
                daily_ceiling_cad=5.0, monthly_ceiling_cad=40.0, per_gallery_cad=2.5,
                max_attempts_per_request=G.DEFAULT_MAX_ATTEMPTS,
                max_calls_per_run=G.DEFAULT_MAX_CALLS_PER_RUN,
                expires_at=NOW + timedelta(days=1))
    base.update(over)
    with db.session() as s:
        row = G.PaidProviderActivation(**base)
        s.add(row)
        s.flush()
        return row.id


def _active(db, now=NOW):
    return G.activation_state(db, "flux-3-image", "generation", now=now)["active"]


# ---- S1: no renewal after the directive's window ---------------------------------------------

def test_s1_a_fresh_store_after_the_window_is_never_given_an_activation():
    db = _db()
    later = GIVEN + D.EXPIRY + timedelta(minutes=1)
    out = D.apply(db, now=later)
    assert out["activated"] == [], out
    assert not _active(db, now=later)


def test_s1_a_store_reset_two_months_later_is_never_reactivated():
    db = _db()
    D.apply(db, now=NOW)
    with db.session() as s:                        # e.g. restored from an older backup
        for r in s.scalars(select(G.PaidProviderActivation)):
            s.delete(r)
    later = NOW + timedelta(days=60)
    assert D.apply(db, now=later)["activated"] == []
    assert not _active(db, now=later)


def test_s1_an_activation_written_late_in_the_window_ends_with_the_window():
    db = _db()
    late = GIVEN + D.EXPIRY - timedelta(days=1)
    D.apply(db, now=late)
    with db.session() as s:
        row = s.scalar(select(G.PaidProviderActivation).limit(1))
        assert G._aware(row.expires_at) <= GIVEN + D.EXPIRY, row.expires_at


def test_s1_a_revoked_directive_is_never_renewed():
    db = _db()
    D.apply(db, now=NOW)
    with db.session() as s:
        for r in s.scalars(select(G.PaidProviderActivation)):
            r.revoked_at, r.revoked_by = NOW, "owner"
    assert D.apply(db, now=NOW + timedelta(hours=2))["activated"] == []
    assert not _active(db, now=NOW + timedelta(hours=2))


def test_s1_a_directive_dated_before_it_was_given_is_refused():
    db = _db()
    assert D.apply(db, now=GIVEN - timedelta(days=1))["activated"] == []


# ---- S2: directive authority is bounded by the directive's own table and window -------------

def test_s2_the_genuine_row_authorises():
    db = _db()
    D.apply(db, now=NOW)
    assert _active(db)


def test_s2_a_row_with_a_wider_monthly_ceiling_has_no_directive_authority():
    db = _db()
    _forge(db, monthly_ceiling_cad=90.0)
    assert not _active(db)


def test_s2_a_row_with_a_wider_daily_or_gallery_ceiling_has_no_directive_authority():
    db = _db()
    _forge(db, daily_ceiling_cad=5.01)
    assert not _active(db)
    db = _db()
    _forge(db, per_gallery_cad=50.0)
    assert not _active(db)


def test_s2_a_row_with_wider_call_ceilings_has_no_directive_authority():
    db = _db()
    _forge(db, max_calls_per_run=500)
    assert not _active(db)
    db = _db()
    _forge(db, max_attempts_per_request=5)
    assert G.DEFAULT_MAX_ATTEMPTS >= 5 or not _active(db)


def test_s2_a_row_living_longer_than_the_directive_has_no_authority():
    db = _db()
    _forge(db, expires_at=datetime(2099, 1, 1, tzinfo=timezone.utc))
    assert not _active(db)


def test_s2_a_row_written_after_the_window_has_no_authority():
    db = _db()
    at = GIVEN + D.EXPIRY + timedelta(days=1)
    _forge(db, activated_at=at, expires_at=at + timedelta(days=1))
    assert not _active(db, now=at + timedelta(hours=1))


def test_s2_is_active_id_applies_the_same_bounds():
    db = _db()
    rid = _forge(db, monthly_ceiling_cad=90.0)
    assert not G.is_active_id(db, rid, now=NOW)
    db = _db()
    D.apply(db, now=NOW)
    with db.session() as s:
        good = s.scalar(select(G.PaidProviderActivation.id).limit(1))
    assert G.is_active_id(db, good, now=NOW)


def test_s2_an_actor_lookalike_or_missing_marker_has_no_authority():
    db = _db()
    _forge(db, activated_by=D.ACTOR + " ")
    assert not _active(db)
    db = _db()
    _forge(db, step_up={"owner_directive": D.DIRECTIVE_ID.lower(), "session_public_id": None})
    assert not _active(db)
    db = _db()
    _forge(db, step_up={"session_public_id": ""})
    assert not _active(db)


# ---- S3: one row per triple, even under concurrent appliers ----------------------------------

def test_s3_apply_checks_and_writes_under_the_spend_lock():
    import inspect
    src = inspect.getsource(D.apply)
    assert "budget_lock" in src, "apply must hold the spend lock across check-and-write"


def test_s3_concurrent_apply_writes_each_triple_once():
    import threading
    db = _db()
    outs = []
    ts = [threading.Thread(target=lambda: outs.append(D.apply(db, now=NOW))) for _ in range(4)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    with db.session() as s:
        rows = list(s.scalars(select(G.PaidProviderActivation)))
    assert len(rows) == 2, [(r.provider, r.scope) for r in rows]


# ---- secret exposure: the job summary carries no raw exception text -------------------------

def test_refusal_reasons_carry_no_raw_exception_text():
    class Boom:
        engine = None

        def session(self):
            raise RuntimeError("postgresql://user:hunter2@db/x")
    out = D.apply(Boom(), now=NOW)
    assert "hunter2" not in repr(out), out


if __name__ == "__main__":
    import traceback
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as exc:  # noqa: BLE001
                fails += 1
                print("FAIL", name, repr(exc))
                traceback.print_exc(limit=1)
    print(f"{fails} failed")
    sys.exit(1 if fails else 0)
