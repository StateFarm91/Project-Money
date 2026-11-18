"""WS4-7 (Main S3, 6953884261): the trusted issuer service boundary and the grant store.

* Only the policy-issuer process signs: unmarked, job, embedded-worker or Etsy-holding
  processes are refused, and the worker scrubs the issuer key at boot.
* Mode T is read from the three processes' own latest reports (the issuer's is signed under
  its key); any disagreement, stale or forged report reads Mode S.
* A grant is issued only for an EFFECTIVE policy, an in-policy release and an agreeing Mode T;
  it is signed, bound to its job, single use, expiring, at most 2 outstanding and 3 a day --
  the database itself refuses a 4th slot of a day and a second open grant for a release.
* The issuer entry answers request rows under a lease and refuses to start misconfigured.
* Its resident memory is measured (the S3 cost note prices it).

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_ws4_7_issuer.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import os
import subprocess
import sys
from datetime import timedelta
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy import select  # noqa: E402

from brambleloop.core.models import AuditLog  # noqa: E402
from brambleloop.ops import publication_authority as PA  # noqa: E402
from brambleloop.ops import standing_grants as SG  # noqa: E402
from brambleloop.ops import standing_issuer as SI  # noqa: E402
from brambleloop.ops import standing_policy as sp  # noqa: E402
from test_ws4_issuer_shadow import SLUG, VERSION, _release  # noqa: E402
from test_ws4_policy_object import (NOW, _activate_raw, _approve, _db, _restore,  # noqa: E402
                                    content)

_ENV_SAVED: dict = {}


def _issuer_keys():
    pairs = sp.generate_keypairs()
    for var in (sp.ISSUER_KEY_VAR, sp.ISSUER_VERIFY_KEY_VAR):
        _ENV_SAVED.setdefault(var, os.environ.get(var))
        os.environ[var] = pairs[var]
    return pairs


def _reset():
    SG._PROCESS.update(issuer=False, job=False)
    for k, v in _ENV_SAVED.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    _restore()


def _as_issuer():
    SG._PROCESS.update(issuer=True, job=False)


def _issuer_env():
    """The issuer service's environment: its own key, no policy signing key (that is web's)."""
    return {k: v for k, v in os.environ.items() if k != sp.SIGNING_KEY_VAR}


def _reports(db, *, now=NOW, worker_env=None, web_env=None):
    """The three processes' reports as a correct Mode T deployment writes them."""
    _as_issuer()
    SG.issuer_heartbeat(db, now=now, env=_issuer_env())
    w = {sp.ISSUER_VERIFY_KEY_VAR: os.environ[sp.ISSUER_VERIFY_KEY_VAR],
         sp.VERIFY_KEY_VAR: os.environ[sp.VERIFY_KEY_VAR], sp.EMBEDDED_VAR: "0"}
    SG.process_report(db, SG.WORKER_COMPONENT, now=now, env={**w, **(worker_env or {})})
    web = {sp.SIGNING_KEY_VAR: os.environ[sp.SIGNING_KEY_VAR],
           sp.VERIFY_KEY_VAR: os.environ[sp.VERIFY_KEY_VAR],
           sp.ISSUER_VERIFY_KEY_VAR: os.environ[sp.ISSUER_VERIFY_KEY_VAR], sp.EMBEDDED_VAR: "0"}
    SG.process_report(db, SG.WEB_COMPONENT, now=now, env={**web, **(web_env or {})})


REL = "a" * 64


# The code ceilings as a policy: 3 a day, 10 a week, 2 outstanding, no spacing.
AT_CEILINGS = {"max_per_day": sp.MAX_PER_DAY, "max_per_7d": sp.MAX_PER_7D,
               "min_spacing_minutes": 0, "max_outstanding_unconsumed_grants": sp.MAX_OUTSTANDING}


def _effective_db(*, slugs=(SLUG,), frequency=None):
    """An EFFECTIVE policy and one certified release (REL) per slug."""
    db = _db()
    c = content(frequency=dict(frequency)) if frequency else content()
    _issuer_keys()
    a = _approve(db, c)
    _activate_raw(db, a, c)
    for slug in slugs:
        _release(db, slug=slug, release=REL)
    return db, c, a


def _all_pass(db_, slug, version, release, content_, *, shadow=True, **_kw):
    from test_ws4_boundary import facts

    return facts(slug=slug)


def _snapshot(db, slug, version, release):
    return {"action": "store.publish", "slug": slug, "version": version, "release": release,
            "cir_digest": "c" * 64, "payload": {"title": "Shadow Coaster"}, "evidence": {}}


class _InPolicy:
    def __enter__(self):
        self.p = [patch.object(SI, "read_facts", _all_pass),
                  patch.object(PA, "snapshot", _snapshot)]
        for p in self.p:
            p.start()

    def __exit__(self, *a):
        for p in self.p:
            p.stop()


def _refused(fn, contains):
    try:
        fn()
    except SG.GrantRefused as exc:
        assert contains in str(exc), (contains, str(exc))
        return str(exc)
    raise AssertionError(f"expected a refusal containing {contains!r}")


# ---- who may sign --------------------------------------------------------------------------

def test_only_the_marked_issuer_process_may_sign():
    try:
        _db()
        _issuer_keys()
        assert "only the policy-issuer" in SG.issuer_signing_refusal()
        _as_issuer()
        assert SG.issuer_signing_refusal() is None
        assert "embedded" in SG.issuer_signing_refusal({sp.EMBEDDED_VAR: "1"}).lower()
        assert "Etsy" in SG.issuer_signing_refusal({sp.EMBEDDED_VAR: "0",
                                                    "ETSY_ACCESS_TOKEN": "x"})
        assert SG.mark_job_process() is True                    # the worker's boot scrub
        assert sp.ISSUER_KEY_VAR not in os.environ
        assert "runs jobs" in SG.issuer_signing_refusal()      # job wins over the issuer mark
        _refused(lambda: SG._sign(SG.DOMAIN, {"x": 1}), "runs jobs")
    finally:
        _reset()


def test_the_worker_scrubs_and_reports_and_web_reports_at_startup():
    import inspect

    from brambleloop.app import main as web, worker_entry

    w = inspect.getsource(worker_entry.main)
    assert "_sg.mark_job_process()" in w and "_sg.process_report(db, _sg.WORKER_COMPONENT)" in w
    assert "_sg.process_report(db, _sg.WEB_COMPONENT)" in inspect.getsource(web._startup)


# ---- Mode T from the processes' own reports ----------------------------------------------------

def test_mode_t_only_when_every_report_agrees():
    try:
        db, c, a = _effective_db()
        assert sp.deployment_mode(None) == "S" and sp.deployment_mode(db, now=NOW) == "S"
        assert "no policy_issuer report" in SG.mode_report(db, now=NOW)["reasons"]
        _reports(db)
        assert SG.mode_report(db, now=NOW) == {"mode": "T", "reasons": [],
                                               "db_roles_separated": False}
        assert sp.deployment_mode(db, now=NOW) == "T"
        assert sp.effective(db, now=NOW + timedelta(minutes=1))["state"] == sp.EFFECTIVE
        # Stale evidence is not Mode T.
        assert sp.deployment_mode(db, now=NOW + timedelta(minutes=6)) == "S"
    finally:
        _reset()


def test_each_disagreement_reads_mode_s():
    bad_cases = {
        "the worker holds the issuer signing key":
            dict(worker_env={sp.ISSUER_KEY_VAR: "AAAA"}),
        "the worker's issuer verify key is not the issuer's key":
            dict(worker_env={sp.ISSUER_VERIFY_KEY_VAR: sp.generate_keypairs()[
                sp.ISSUER_VERIFY_KEY_VAR]}),
        "the worker has no issuer verify key": dict(worker_env={sp.ISSUER_VERIFY_KEY_VAR: ""}),
        "web reports": dict(web_env={sp.EMBEDDED_VAR: "1"}),
        "web holds the issuer signing key": dict(web_env={sp.ISSUER_KEY_VAR: "AAAA"}),
    }
    for why, kw in bad_cases.items():
        try:
            db, c, a = _effective_db()
            _reports(db, **kw)
            got = SG.mode_report(db, now=NOW)
            assert got["mode"] == "S" and any(why in r for r in got["reasons"]), (why, got)
        finally:
            _reset()


def test_a_forged_issuer_heartbeat_reads_mode_s():
    try:
        db, c, a = _effective_db()
        _reports(db)
        real = os.environ[sp.ISSUER_KEY_VAR]
        os.environ[sp.ISSUER_KEY_VAR] = sp.generate_keypairs()[sp.ISSUER_KEY_VAR]
        SG.issuer_heartbeat(db, now=NOW + timedelta(seconds=1),
                            env=_issuer_env())                    # signed by another key
        os.environ[sp.ISSUER_KEY_VAR] = real
        got = SG.mode_report(db, now=NOW)
        assert got["mode"] == "S" and any("does not verify" in r for r in got["reasons"]), got
    finally:
        _reset()


def test_the_same_database_role_for_worker_and_issuer_reads_mode_s():
    try:
        db, c, a = _effective_db()
        with patch.object(SG, "_db_user", lambda _db: "brambleloop"):
            _reports(db)
        got = SG.mode_report(db, now=NOW)
        assert got["mode"] == "S" and any("same database role" in r for r in got["reasons"])
        with patch.object(SG, "_db_user", lambda _db: "bl_issuer"):
            _as_issuer()
            SG.issuer_heartbeat(db, now=NOW + timedelta(seconds=1), env=_issuer_env())
        got = SG.mode_report(db, now=NOW + timedelta(seconds=2))
        assert got["mode"] == "T" and got["db_roles_separated"] is True, got
    finally:
        _reset()


# ---- issuing, using, limits ---------------------------------------------------------------------

def test_an_in_policy_request_is_answered_with_a_signed_single_use_job_bound_grant():
    from brambleloop.app import issuer_entry

    try:
        db, c, a = _effective_db()
        _reports(db)
        rid = SG.request_grant(db, slug=SLUG, version=VERSION, release="a" * 64, job_id=41)
        os.environ.pop(sp.SIGNING_KEY_VAR, None)    # the issuer service never holds it
        with _InPolicy():
            out = issuer_entry.tick(db, holder="issuer-test", now=NOW + timedelta(minutes=1))
        assert out["leader"] is True and out["answered"][0]["issued"] is True, out
        gid = out["answered"][0]["grant_id"]
        assert SG.pending_requests(db) == []                       # answered once
        with db.session() as s:
            row = s.get(SG.StandingGrant, gid)
            body = dict(row.detail_json)
            assert row.expires_at - row.issued_at == timedelta(minutes=sp.SEG_TTL_MINUTES)
        assert body["job_id"] == 41 and body["policy"]["row_id"] == a
        assert body["budget"]["slot_no"] == 1 and body["issuer_host"] == SG.ISSUER_HOST
        assert SG.verify(SG.DOMAIN, body, row.seal)
        # Used once, by its own job, before it expires.
        _refused(lambda: SG.consume(db, gid, job_id=99, now=NOW + timedelta(minutes=2)),
                 "issued for job 41")
        assert SG.consume(db, gid, job_id=41, now=NOW + timedelta(minutes=2))["scope"] == \
            f"{SLUG}@{VERSION}"
        _refused(lambda: SG.consume(db, gid, job_id=41, now=NOW + timedelta(minutes=3)),
                 "used, expired or gone")
        assert rid
    finally:
        _reset()


def test_a_new_request_is_seen_past_any_number_of_answered_ones():
    try:
        db, c, a = _effective_db()
        with patch.object(SG, "_REQUEST_SCAN", 2):
            for job in (1, 2, 3):
                rid = SG.request_grant(db, slug=SLUG, version=VERSION, release="a" * 64,
                                       job_id=job)
                with db.session() as s:
                    s.add(AuditLog(actor=SG.ACTOR, action=SG.HELD, artifact=SLUG,
                                   detail={"request_id": rid}))
            new = SG.request_grant(db, slug=SLUG, version=VERSION, release="a" * 64,
                                   job_id=4)
            assert [r["request_id"] for r in SG.pending_requests(db)] == [new]
    finally:
        _reset()


def test_an_expired_or_tampered_grant_is_refused_at_use():
    try:
        db, c, a = _effective_db(slugs=(SLUG, SLUG + "-2"), frequency=AT_CEILINGS)
        _reports(db)
        _as_issuer()
        with _InPolicy():
            g1 = SG.issue(db, slug=SLUG, version=VERSION, release=REL, job_id=1,
                          now=NOW + timedelta(minutes=1))
            g2 = SG.issue(db, slug=SLUG + "-2", version=VERSION, release=REL, job_id=2,
                          now=NOW + timedelta(minutes=1))
        _refused(lambda: SG.consume(db, g1["grant_id"], job_id=1,
                                    now=NOW + timedelta(minutes=17)), "used, expired or gone")
        with db.session() as s:
            row = s.get(SG.StandingGrant, g2["grant_id"])
            row.detail_json = {**row.detail_json, "release": "c" * 64}
        _refused(lambda: SG.consume(db, g2["grant_id"], job_id=2,
                                    now=NOW + timedelta(minutes=2)), "does not verify")
    finally:
        _reset()


def test_outstanding_and_daily_limits_hold_in_code_and_in_the_database():
    from sqlalchemy.exc import IntegrityError

    slugs = [f"{SLUG}-{i}" for i in range(5)]
    try:
        db, c, a = _effective_db(slugs=slugs, frequency=AT_CEILINGS)
        _reports(db)
        _as_issuer()
        t = NOW + timedelta(minutes=1)
        with _InPolicy():
            g1 = SG.issue(db, slug=slugs[0], version=VERSION, release=REL, job_id=1, now=t)
            SG.issue(db, slug=slugs[1], version=VERSION, release=REL, job_id=2, now=t)
            _refused(lambda: SG.issue(db, slug=slugs[2], version=VERSION, release=REL,
                                      job_id=3, now=t), "outstanding")
            SG.consume(db, g1["grant_id"], job_id=1, now=t)
            SG.issue(db, slug=slugs[2], version=VERSION, release=REL, job_id=3, now=t)
            with db.session() as s:
                for g in s.scalars(select(SG.StandingGrant)):
                    if g.consumed_at is None:
                        g.consumed_at, g.consumed_job_id = t, g.id + 1000
            _refused(lambda: SG.issue(db, slug=slugs[3], version=VERSION, release=REL,
                                      job_id=4, now=t), "grants_today: 3 issued")
        # The database refuses a 4th slot and a second open grant even if code did not.
        for build in (lambda: SG.StandingGrantSlot(policy_row_id=a, day=t.date().isoformat(),
                                                   slot_no=4),
                      lambda: SG.StandingGrantSlot(policy_row_id=a, day=t.date().isoformat(),
                                                   slot_no=1)):
            try:
                with db.session() as s:
                    s.add(build())
                    s.flush()
                raise AssertionError("the slot table must refuse this")
            except IntegrityError:
                pass
        with db.session() as s:
            proto = s.scalars(select(SG.StandingGrant)).first()
            twin = dict(policy_row_id=a, policy_version=1, scope=proto.scope, release="z" * 64,
                        digest="d", detail_json={}, seal="s", issued_at=t,
                        expires_at=t + timedelta(minutes=15))
        try:
            with db.session() as s:
                s.add(SG.StandingGrant(**twin))
                s.add(SG.StandingGrant(**twin))
                s.flush()
            raise AssertionError("two open grants for one release must be refused")
        except IntegrityError:
            pass
    finally:
        _reset()


def test_no_grant_without_mode_t_an_effective_policy_or_an_in_policy_release():
    try:
        db, c, a = _effective_db()
        _as_issuer()
        with _InPolicy():
            why = _refused(lambda: SG.issue(db, slug=SLUG, version=VERSION, release="a" * 64,
                                            job_id=1, now=NOW), "not Mode T")
        # The issuer's own Mode T check, not only the policy's (defence in depth).
        assert why.startswith("deployment is not Mode T: no policy_issuer report"), why
        _reports(db)
        _refused(lambda: SG.issue(db, slug=SLUG, version=VERSION, release="a" * 64,
                                  job_id=1, now=NOW + timedelta(minutes=1)), "out of policy")
        # The answer is recorded, so the request is not retried every tick.
        rid = SG.request_grant(db, slug=SLUG, version=VERSION, release="a" * 64, job_id=5)
        got = SG.answer(db, SG.pending_requests(db)[0], now=NOW + timedelta(minutes=1))
        assert got["issued"] is False and got["request_id"] == rid
        assert SG.pending_requests(db) == []
        with db.session() as s:
            assert s.scalar(select(AuditLog).where(AuditLog.action == SG.HELD)) is not None
    finally:
        _reset()
    try:
        db2, c2 = _db(), content()
        _issuer_keys()
        _release(db2, release="a" * 64)
        _reports(db2)
        _refused(lambda: SG.issue(db2, slug=SLUG, version=VERSION, release="a" * 64,
                                  job_id=1, now=NOW), "no effective standing policy")
    finally:
        _reset()


def test_the_issuer_refuses_to_start_misconfigured_and_a_second_replica_idles():
    from brambleloop.app import issuer_entry

    try:
        db, c, a = _effective_db()
        saved = os.environ.get(sp.EMBEDDED_VAR)
        os.environ[sp.EMBEDDED_VAR] = "1"
        os.environ["BRAMBLELOOP_ISSUER_ONCE"] = "1"     # a broken refusal returns, not loops
        try:
            assert issuer_entry.main() == 2
        finally:
            os.environ[sp.EMBEDDED_VAR] = saved if saved is not None else "0"
            os.environ.pop("BRAMBLELOOP_ISSUER_ONCE", None)
        _reports(db)
        assert issuer_entry.tick(db, holder="issuer-a", now=NOW)["leader"] is True
        assert issuer_entry.tick(db, holder="issuer-b", now=NOW)["leader"] is False
    finally:
        _reset()


def test_the_issuer_has_no_http_listener():
    import inspect

    from brambleloop.app import issuer_entry

    src = inspect.getsource(issuer_entry)
    for forbidden in ("uvicorn", "FastAPI", "socket.bind", "http.server", "listen("):
        assert forbidden not in src, forbidden


def test_the_issuer_pass_is_small():
    """Resident memory of a fresh process that imports the issuer and runs one pass (the
    figure the S3 cost note prices). Measured, not assumed; bounded so growth is noticed."""
    code = (
        "import _tmp; _tmp.install()\n"
        "import resource, tempfile, os\n"
        "from brambleloop.core.db import Database\n"
        "from brambleloop.app import issuer_entry\n"
        "db = Database(f'sqlite:///{tempfile.mkdtemp()}/i.sqlite', scratch=True); db.create_all()\n"
        "from brambleloop.ops import standing_grants as SG, standing_policy as sp\n"
        "k = sp.generate_keypairs(); os.environ.update({sp.ISSUER_KEY_VAR: k[sp.ISSUER_KEY_VAR],"
        " sp.ISSUER_VERIFY_KEY_VAR: k[sp.ISSUER_VERIFY_KEY_VAR], sp.EMBEDDED_VAR: '0'})\n"
        "SG.mark_issuer_process(); issuer_entry.tick(db, holder='m')\n"
        "print(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)\n")
    here = os.path.dirname(__file__)
    env = dict(os.environ, PYTHONPATH=os.pathsep.join(
        [os.path.join(here, "..", "src"), here, os.environ.get("PYTHONPATH", "")]))
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env,
                         timeout=300)
    assert out.returncode == 0, out.stderr[-800:]
    kib = int(out.stdout.strip().splitlines()[-1])
    print(f"   issuer pass peak RSS: {kib / 1024:.1f} MiB")
    assert kib < 200 * 1024, kib


# ---- HIGH-1: the owner's signed pace limits, read from the grant store ------------------------

def _issue(db, slug, job, at):
    return SG.issue(db, slug=slug, version=VERSION, release=REL, job_id=job, now=at)


def test_the_owner_pace_limits_are_enforced_not_only_the_code_ceilings():
    """Review HIGH-1 probe: policy signed 2/day, 1 outstanding, 180 min spacing. The old code
    issued 3 grants in one minute (it enforced only 3/day and 2 outstanding)."""
    slugs = [f"{SLUG}-p{i}" for i in range(4)]
    try:
        db, c, a = _effective_db(slugs=slugs)
        assert c["frequency"] == {"max_per_day": 2, "max_per_7d": 6, "min_spacing_minutes": 180,
                                  "max_outstanding_unconsumed_grants": 1}
        _reports(db)
        _as_issuer()
        t = NOW + timedelta(minutes=1)
        with _InPolicy():
            g1 = _issue(db, slugs[0], 1, t)
            # One minute later: the second grant is refused (1 outstanding, 180 min spacing).
            why = _refused(lambda: _issue(db, slugs[1], 2, t + timedelta(minutes=1)),
                           "grants outstanding")
            assert "minutes since the last grant" in why, why
            SG.consume(db, g1["grant_id"], job_id=1, now=t + timedelta(minutes=1))
            _refused(lambda: _issue(db, slugs[1], 2, t + timedelta(minutes=2)),
                     "minutes since the last grant; the policy needs 180")
            # After the spacing: the second of the day is issued...
            t2 = t + timedelta(minutes=181)
            _reports(db, now=t2)
            g2 = _issue(db, slugs[1], 2, t2)
            SG.consume(db, g2["grant_id"], job_id=2, now=t2)
            # ...and the third is refused by the owner's 2/day, though code allows 3.
            _reports(db, now=t2 + timedelta(minutes=200))
            _refused(lambda: _issue(db, slugs[2], 3, t2 + timedelta(minutes=200)),
                     "grants_today: 2 issued; the limit is 2")
        with db.session() as s:
            assert len(list(s.scalars(select(SG.StandingGrant)))) == 2
    finally:
        _reset()


def test_the_seven_day_limit_counts_every_grant_in_the_window():
    slugs = [f"{SLUG}-w{i}" for i in range(4)]
    freq = {"max_per_day": 2, "max_per_7d": 3, "min_spacing_minutes": 0,
            "max_outstanding_unconsumed_grants": 2}
    try:
        db, c, a = _effective_db(slugs=slugs, frequency=freq)
        _reports(db)
        _as_issuer()
        t = NOW + timedelta(minutes=1)
        with _InPolicy():
            _issue(db, slugs[0], 1, t)
            _issue(db, slugs[1], 2, t)                # never used: it expires, still counted
            day2 = t + timedelta(days=1)
            _reports(db, now=day2)
            g3 = _issue(db, slugs[2], 3, day2)
            SG.consume(db, g3["grant_id"], job_id=3, now=day2)
            day3 = t + timedelta(days=2)
            _reports(db, now=day3)
            _refused(lambda: _issue(db, slugs[3], 4, day3), "grants_7d: 3 issued")
            later = t + timedelta(days=7, minutes=1)   # the first two leave the window
            _reports(db, now=later)
            _issue(db, slugs[3], 4, later)
    finally:
        _reset()


def test_read_facts_reports_the_grant_store_not_zero():
    """The boundary's pace facts come from the store: with one outstanding grant under a
    1-outstanding / 180-minute policy, the issue-time classification HOLDs."""
    slugs = [f"{SLUG}-f{i}" for i in range(2)]
    try:
        db, c, a = _effective_db(slugs=slugs)
        _reports(db)
        _as_issuer()
        t = NOW + timedelta(minutes=1)
        with _InPolicy():
            _issue(db, slugs[0], 1, t)
        facts = SI.read_facts(db, slugs[1], VERSION, REL, c, shadow=False,
                              now=t + timedelta(minutes=5))
        assert facts["outstanding"]["value"] == 1, facts["outstanding"]
        assert facts["grants_today"]["value"] == {"consumed": 0, "outstanding": 1}
        assert abs(facts["minutes_since_last"]["value"] - 5.0) < 1e-6
        from brambleloop.ops import standing_boundary as SB
        from test_ws4_boundary import facts as all_pass

        merged = {**all_pass(slug=slugs[1]), **{k: facts[k] for k in (
            "grants_today", "grants_7d", "outstanding", "minutes_since_last")}}
        reasons = SB.classify(c, merged)["reasons"]
        assert any("outstanding" in r for r in reasons), reasons
        assert any("minutes since the last grant" in r for r in reasons), reasons
    finally:
        _reset()


def test_concurrent_issuers_cannot_both_take_the_last_grant():
    """The pace re-read and the slot insert are one serialized transaction: two issuers
    racing on a 1-outstanding policy produce exactly one grant."""
    import threading

    slugs = [f"{SLUG}-r{i}" for i in range(2)]
    freq = {"max_per_day": 3, "max_per_7d": 10, "min_spacing_minutes": 0,
            "max_outstanding_unconsumed_grants": 1}
    try:
        db, c, a = _effective_db(slugs=slugs, frequency=freq)
        _reports(db)
        _as_issuer()
        t = NOW + timedelta(minutes=1)
        barrier = threading.Barrier(2)
        real_pace = SG.pace
        calls = {"n": 0}

        def slow_pace(session, now):
            got = real_pace(session, now)
            calls["n"] += 1
            if calls["n"] <= 2:          # both early (unlocked) reads see nothing issued
                barrier.wait(timeout=10)
            return got

        out = []
        with _InPolicy(), patch.object(SG, "pace", slow_pace):
            def go(slug, job):
                try:
                    out.append(_issue(db, slug, job, t)["grant_id"])
                except SG.GrantRefused as exc:
                    out.append(str(exc))
            ts = [threading.Thread(target=go, args=(slugs[i], i + 1)) for i in range(2)]
            for th in ts:
                th.start()
            for th in ts:
                th.join(30)
        assert sum(isinstance(x, int) for x in out) == 1, out
        assert any(isinstance(x, str) and "outstanding" in x for x in out), out
    finally:
        _reset()


if __name__ == "__main__":
    failed = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"OK   {name}")
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print(f"FAIL {name} {exc!r}"[:600])
                import traceback

                traceback.print_exc()
    print(f"{failed} failed")
    sys.exit(1 if failed else 0)
