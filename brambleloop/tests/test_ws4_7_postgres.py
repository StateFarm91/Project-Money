"""WS4-7 review fixes on a real PostgreSQL under the owner runbook's database roles.

* M-3: with the runbook's column grant, the worker role cannot reset `consumed_at` and consume
  a grant twice (the write-once trigger refuses it); it cannot insert a grant or a slot.
* M-3: role separation is read from PostgreSQL's own catalogue. A worker on a superuser role
  under a name different from the issuer's reads Mode S, not "separated".
* M-5: the issuer role (no CREATE) answers an out-of-policy request -- its HOLD card is written
  -- and the next request in the same pass; it never creates the grant store itself.

A throwaway cluster is made for the run (loopback only, `initdb -A trust`), as in
`test_codex_v0_postgres.py`, and destroyed afterwards. With no PostgreSQL toolchain the suite
prints SKIP and exits 0 (the runner counts that as no passes).

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_ws4_7_postgres.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import contextlib
import glob
import os
import shutil
import socket
import subprocess
import sys
import tempfile
from datetime import timedelta
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy import create_engine, select, text  # noqa: E402
from sqlalchemy.exc import DBAPIError  # noqa: E402

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog  # noqa: E402
from brambleloop.ops import standing_grants as SG  # noqa: E402
from brambleloop.ops import standing_issuer as SI  # noqa: E402
from brambleloop.ops import standing_policy as sp  # noqa: E402
from test_ws4_7_issuer import (AT_CEILINGS, REL, _InPolicy, _as_issuer,  # noqa: E402
                               _bind_shop, _issuer_env, _issuer_keys, _job,
                               _reset)
from test_ws4_issuer_shadow import SLUG, VERSION, _release  # noqa: E402
from test_ws4_policy_object import NOW, _activate_raw, _approve, _keys, content  # noqa: E402


class _Skip(Exception):
    pass


# The runbook as WS4-7 (fa3a09e9) shipped it: used only when this suite is run against that
# code, to show the old store let the worker role reset a consumed grant.
_OLD_RUNBOOK = [
    "CREATE ROLE bl_issuer LOGIN PASSWORD 'x'", "CREATE ROLE bl_worker LOGIN PASSWORD 'y'",
    "GRANT SELECT ON ALL TABLES IN SCHEMA public TO bl_issuer, bl_worker",
    "GRANT INSERT ON standing_grants, standing_grant_slots, audit_log, ops_runtime_samples "
    "TO bl_issuer",
    "GRANT INSERT, UPDATE ON ops_leases TO bl_issuer",
    "GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO bl_issuer",
    "REVOKE INSERT, UPDATE, DELETE ON standing_grants, standing_grant_slots FROM bl_worker",
    "GRANT UPDATE (consumed_at, consumed_job_id, consumed_stage) ON standing_grants "
    "TO bl_worker",
    "GRANT INSERT ON audit_log, ops_runtime_samples TO bl_worker",
    "GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO bl_worker"]


@contextlib.contextmanager
def _cluster():
    """Yield a superuser URL template on a brand-new loopback cluster, destroyed after."""
    bins = sorted(glob.glob("/usr/lib/postgresql/*/bin/initdb"))
    if not bins:
        raise _Skip("no PostgreSQL toolchain")
    bindir = os.path.dirname(bins[-1])
    as_pg = []
    if os.geteuid() == 0:
        import pwd

        try:
            pwd.getpwnam("postgres")
        except KeyError:
            raise _Skip("running as root with no postgres user") from None
        as_pg = ["runuser", "-u", "postgres", "--"]
    base = tempfile.mkdtemp(prefix="ws4-7-pg-", dir="/tmp")
    os.chmod(base, 0o755)
    if as_pg:
        shutil.chown(base, user="postgres")
    data = os.path.join(base, "data")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    started = False
    try:
        run = lambda *a: subprocess.run(as_pg + list(a), check=True, capture_output=True,  # noqa: E731
                                        timeout=120)
        run(f"{bindir}/initdb", "-D", data, "-A", "trust", "-U", "postgres")
        started = True
        run(f"{bindir}/pg_ctl", "-D", data, "-w", "-l", os.path.join(base, "log"), "-o",
            f"-c listen_addresses=127.0.0.1 -c port={port} -c unix_socket_directories={base}",
            "start")
        yield f"postgresql+psycopg2://{{user}}@127.0.0.1:{port}/{{db}}", bindir
    finally:
        if started:
            subprocess.run(as_pg + [f"{bindir}/pg_ctl", "-D", data, "-m", "immediate", "-w",
                                    "stop"], capture_output=True, timeout=120)
        shutil.rmtree(base, ignore_errors=True)


_N = {"db": 0}


def _fresh(url):
    """A new database: created and migrated by the owner (superuser `postgres`, the role web
    uses), then the runbook applied. Returns (owner, issuer, worker) Database handles."""
    _N["db"] += 1
    name = f"ws47_{_N['db']}"
    admin = create_engine(url.format(user="postgres", db="postgres"),
                          isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f"CREATE DATABASE {name}"))
    admin.dispose()
    _keys()
    _issuer_keys()
    owner = Database(url.format(user="postgres", db=name))
    owner.create_all()
    stmts = (SG.runbook_sql("postgres", "x", "y") if hasattr(SG, "runbook_sql")
             else _OLD_RUNBOOK)
    with owner.engine.begin() as c:
        for stmt in stmts:
            if stmt.startswith("CREATE ROLE") and c.execute(text(
                    "SELECT 1 FROM pg_roles WHERE rolname = :r"),
                    {"r": stmt.split()[2]}).scalar():
                continue               # roles are cluster-wide; made by the first database
            c.execute(text(stmt))
    return (owner, Database(url.format(user="bl_issuer", db=name)),
            Database(url.format(user="bl_worker", db=name)))


def _pg_reports(owner, issuer, worker, *, now=NOW, worker_db=None):
    """Each process's report from ITS OWN connection: the worker's from `worker_db` (default:
    the bl_worker role), web's from the owner, the issuer's (signed) from bl_issuer."""
    w = {sp.ISSUER_VERIFY_KEY_VAR: os.environ[sp.ISSUER_VERIFY_KEY_VAR],
         sp.VERIFY_KEY_VAR: os.environ[sp.VERIFY_KEY_VAR], sp.EMBEDDED_VAR: "0"}
    SG.process_report(worker_db or worker, SG.WORKER_COMPONENT, now=now, env=w)
    web = {sp.SIGNING_KEY_VAR: os.environ[sp.SIGNING_KEY_VAR],
           sp.VERIFY_KEY_VAR: os.environ[sp.VERIFY_KEY_VAR],
           sp.ISSUER_VERIFY_KEY_VAR: os.environ[sp.ISSUER_VERIFY_KEY_VAR], sp.EMBEDDED_VAR: "0"}
    SG.process_report(owner, SG.WEB_COMPONENT, now=now, env=web)
    _as_issuer()
    SG.issuer_heartbeat(issuer, now=now + timedelta(seconds=1), env=_issuer_env())


def _policy(owner, slugs, frequency=AT_CEILINGS):
    c = content(frequency=dict(frequency))
    a = _approve(owner, c)
    _activate_raw(owner, a, c)
    for slug in slugs:
        _release(owner, slug=slug, release=REL)
    _bind_shop(owner)
    return c, a


def _issue(issuer, owner, slug, job, at):
    _job(owner, job, slug)
    return SG.issue(issuer, slug=slug, version=VERSION, release=REL, job_id=job, now=at)


def test_role_separation_is_read_from_the_catalogue(url):
    owner, issuer, worker = _fresh(url)
    try:
        _pg_reports(owner, issuer, worker)
        got = SG.mode_report(issuer, now=NOW + timedelta(seconds=2))
        assert got == {"mode": "T", "reasons": [], "db_roles_separated": True}, got
        # Review M-3 probe: the worker on the superuser role ("postgres" != "bl_issuer").
        _pg_reports(owner, issuer, worker, now=NOW + timedelta(seconds=10), worker_db=owner)
        got = SG.mode_report(issuer, now=NOW + timedelta(seconds=12))
        assert got["mode"] == "S" and got["db_roles_separated"] is False, got
        assert any("superuser" in r for r in got["reasons"]), got
        _at, hb = SG._latest(issuer, SG.ISSUER_COMPONENT)
        assert hb["worker_role"] == "postgres" and "superuser" in hb["worker_role_powers"], hb
        assert hb["db_powers"] == ["INSERT standing_grants", "INSERT standing_grant_slots",
                                   "INSERT standing_activation_slots"], hb
    finally:
        _reset()


def test_the_worker_role_cannot_reset_a_consumed_grant_or_mint_one(url):
    owner, issuer, worker = _fresh(url)
    try:
        _policy(owner, [SLUG])
        _pg_reports(owner, issuer, worker)
        t = NOW + timedelta(minutes=1)
        with _InPolicy():
            g = _issue(issuer, owner, SLUG, 41, t)
        SG.consume(worker, g["grant_id"], job_id=41, now=t + timedelta(minutes=1))
        # Review M-3 probe: as the worker role, consumed_at back to NULL, then consume again.
        try:
            with worker.session() as s:
                s.execute(text("UPDATE standing_grants SET consumed_at = NULL WHERE id = :i"),
                          {"i": g["grant_id"]})
            raise AssertionError("the worker role reset a consumed grant")
        except DBAPIError as exc:
            assert "write-once" in str(exc.orig), exc
        try:
            SG.consume(worker, g["grant_id"], job_id=41, now=t + timedelta(minutes=2))
            raise AssertionError("a grant was consumed twice")
        except SG.GrantRefused:
            pass
        with owner.session() as s:
            assert s.scalar(select(SG.StandingGrant.consumed_at).where(
                SG.StandingGrant.id == g["grant_id"])) is not None
            assert len(list(s.scalars(select(AuditLog).where(
                AuditLog.action == SG.CONSUMED)))) == 1
        for stmt in ("INSERT INTO standing_grant_slots (policy_row_id, day, slot_no, at) "
                     "VALUES (1, '2026-11-20', 2, now())",
                     "UPDATE standing_grants SET expires_at = expires_at + interval '2 days'",
                     "DELETE FROM standing_grants"):
            try:
                with worker.session() as s:
                    s.execute(text(stmt))
                raise AssertionError(f"the worker role may: {stmt}")
            except DBAPIError as exc:
                assert "permission denied" in str(exc.orig), (stmt, exc)
    finally:
        _reset()


def test_no_process_role_can_reset_a_stage_a_cap(url):
    """Verdict 6999967600 L-A: Stage A's slot tables are in the role model. The migration
    owner creates them (register_models); the worker never writes an activation slot and may
    only INSERT a withdrawal slot; neither the worker nor the issuer may UPDATE or DELETE
    either table, so no process can reset a pace or fee cap."""
    owner, issuer, worker = _fresh(url)
    try:
        with owner.session() as s:
            for t in ("standing_activation_slots", "standing_withdrawal_slots"):
                assert s.execute(text("SELECT tableowner FROM pg_tables WHERE tablename = :t"),
                                 {"t": t}).scalar() == "postgres", t
            s.execute(text("INSERT INTO standing_activation_slots (policy_row_id, day, slot_no, "
                           "at) VALUES (1, '2026-11-20', 1, now())"))
            s.execute(text("INSERT INTO standing_withdrawal_slots (hour, slot_no, listing_id, "
                           "at) VALUES ('2026-11-20T12', 1, 'a', now())"))
        refused = {
            worker: ("INSERT INTO standing_activation_slots (policy_row_id, day, slot_no, at) "
                     "VALUES (1, '2026-11-21', 1, now())",
                     "UPDATE standing_activation_slots SET slot_no = 2",
                     "DELETE FROM standing_activation_slots",
                     "UPDATE standing_withdrawal_slots SET hour = '2026-11-19T00'",
                     "DELETE FROM standing_withdrawal_slots"),
            issuer: ("UPDATE standing_activation_slots SET slot_no = 2",
                     "DELETE FROM standing_activation_slots",
                     "DELETE FROM standing_withdrawal_slots"),
        }
        assert len(refused) == 2 and all(refused.values()), refused
        for role, stmts in refused.items():
            assert stmts, role
            for stmt in stmts:
                try:
                    with role.session() as s:
                        s.execute(text(stmt))
                    raise AssertionError(f"a process role may: {stmt}")
                except DBAPIError as exc:
                    assert "permission denied" in str(exc.orig), (stmt, exc)
        with worker.session() as s:             # what a withdrawal job does
            s.execute(text("INSERT INTO standing_withdrawal_slots (hour, slot_no, listing_id, at)"
                           " VALUES ('2026-11-20T12', 2, 'b', now())"))
        with issuer.session() as s:             # what Stage A's issue does
            s.execute(text("INSERT INTO standing_activation_slots (policy_row_id, day, slot_no, "
                           "at) VALUES (2, '2026-11-21', 1, now())"))
        with owner.session() as s:
            assert s.execute(text("SELECT count(*) FROM standing_activation_slots")).scalar() == 2
            assert s.execute(text("SELECT count(*) FROM standing_withdrawal_slots")).scalar() == 2
        # The catalogue read Mode T relies on names the slot tables too.
        with owner.session() as s:
            worker_powers = SG._role_powers(s, "bl_worker")
            issuer_powers = SG._role_powers(s, "bl_issuer")
        assert not [p for p in worker_powers if "activation_slots" in p or
                    "withdrawal_slots" in p], worker_powers
        assert "INSERT standing_activation_slots" in issuer_powers, issuer_powers
        assert not [p for p in issuer_powers if p.startswith(("UPDATE", "DELETE"))], issuer_powers
    finally:
        _reset()


def test_the_issuer_role_answers_an_out_of_policy_request_and_the_next(url):
    from brambleloop.app import issuer_entry
    from brambleloop.core.models import OwnerAction

    slugs = [f"{SLUG}-pg{i}" for i in range(2)]
    owner, issuer, worker = _fresh(url)
    try:
        _policy(owner, slugs)
        _pg_reports(owner, issuer, worker)
        for i, slug in enumerate(slugs):
            _job(owner, 100 + i, slug)
            SG.request_grant(worker, slug=slug, version=VERSION, release=REL, job_id=100 + i)
        from test_ws4_boundary import facts

        def read_facts(db_, slug, version, release, content_, **_kw):
            f = facts(slug=slug)
            if slug == slugs[0]:          # out of policy: priced outside the class band
                f["price_cad"] = {"state": "PASS", "value": 99.0, "why": None}
            return f

        os.environ.pop(sp.SIGNING_KEY_VAR, None)
        with _InPolicy(), patch.object(SI, "read_facts", read_facts):
            out = issuer_entry.tick(issuer, holder="issuer-pg",
                                    now=NOW + timedelta(minutes=1))
        got = {x["request_id"]: x for x in out["answered"]}
        assert [x["issued"] for x in out["answered"]] == [False, True], out
        assert SG.pending_requests(issuer) == []
        with owner.session() as s:
            cards = [r.requirement_key for r in s.scalars(select(OwnerAction))
                     if r.requirement_key == SI.hold_key(slugs[0], VERSION, REL)]
        assert cards, "the HOLD became an owner card, written by the issuer role"
        assert "out of policy" in got[min(got)]["why"], got
    finally:
        _reset()


_WORKER_BOOT_PG = """
import _tmp; _tmp.install()
import json, sys
from unittest.mock import patch
from brambleloop.core.db import Database
db = Database(sys.argv[1])
from brambleloop.app import worker_entry

class _NoRun:
    def __init__(self, *a, **k): pass
    def run(self, **k): return {}

with patch.object(worker_entry, "Database", lambda *a, **k: db), \\
        patch.object(worker_entry, "Worker", _NoRun):
    rc = worker_entry.main()
print(json.dumps({"rc": rc}))
"""


def _boot_worker_as(url_):
    import json

    here = os.path.dirname(__file__)
    env = {k: v for k, v in os.environ.items() if k != sp.ISSUER_KEY_VAR}
    env.update(PYTHONPATH=os.pathsep.join([os.path.join(here, "..", "src"), here,
                                           os.environ.get("PYTHONPATH", "")]))
    out = subprocess.run([sys.executable, "-c", _WORKER_BOOT_PG, url_], capture_output=True,
                         text=True, env=env, timeout=600)
    assert out.returncode == 0, out.stderr[-1500:]
    return json.loads(out.stdout.strip().splitlines()[-1]), out.stderr


def _owned_by(owner, role):
    with owner.engine.connect() as c:
        return sorted(c.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = "
                                     "'public' AND tableowner = :r"), {"r": role}).scalars())


def test_the_worker_role_never_creates_a_table_it_should_not_own(url):
    """Round-2 L4: under the runbook the worker keeps CREATE on the schema. A worker that
    booted before web on a release adding the grant store ran create_all and OWNED it (and
    an owner can drop the write-once trigger). It now refuses to start and creates nothing."""
    owner, issuer, worker = _fresh(url)
    name = owner.engine.url.database
    wurl = url.format(user="bl_worker", db=name)
    try:
        got, _err = _boot_worker_as(wurl)                 # every table exists: it starts
        assert got["rc"] == 0, (got, _err[-1500:])
        assert _owned_by(owner, "bl_worker") == [], _owned_by(owner, "bl_worker")
        with owner.engine.begin() as c:   # a release that adds the grant store, web not up
            c.execute(text("DROP TABLE standing_grant_slots, standing_grants CASCADE"))
            c.execute(text(f"DROP FUNCTION {SG.WRITE_ONCE_TRIGGER}()"))
        got, err = _boot_worker_as(wurl)
        assert got["rc"] == 3, (got, err[-800:])
        assert "Deploy web (the migration owner) first" in err, err[-800:]
        assert _owned_by(owner, "bl_worker") == [], _owned_by(owner, "bl_worker")
        with owner.engine.connect() as c:
            assert c.execute(text("SELECT to_regclass('public.standing_grants')")).scalar() \
                is None
        # Nor does the worker create the grant store lazily from a job process.
        SG._PROCESS.update(job=True)
        try:
            try:
                SG.ensure_tables(Database(wurl))          # a new engine: no cached check
                raise AssertionError("a job process created the grant store")
            except SG.GrantRefused as exc:
                assert "never creates it" in str(exc), exc
        finally:
            SG._PROCESS.update(job=False)
        assert _owned_by(owner, "bl_worker") == []
        # Web (the migration owner) boots: it creates them, guard included; the worker starts.
        out = owner.boot_schema("web")
        assert out["created"] is True and out["refusal"] is None, out
        got, _err = _boot_worker_as(wurl)
        assert got["rc"] == 0, got
        assert _owned_by(owner, "bl_worker") == []
        # Round-3 LOW: a release that only ADDS a column (every table exists) is the same
        # case. The worker refuses rather than starting against a table it cannot read.
        with owner.engine.begin() as c:
            c.execute(text("ALTER TABLE jobs DROP COLUMN last_error"))
        out = Database(wurl).boot_schema("worker")
        assert out["missing"] == [] and out["missing_columns"] == ["jobs.last_error"], out
        got, err = _boot_worker_as(wurl)
        assert got["rc"] == 3, (got, err[-800:])
        assert "column(s) do not exist yet" in err and "jobs.last_error" in err, err[-800:]
        assert "Deploy web (the migration owner) first" in err, err[-800:]
        out = owner.boot_schema("web")                    # web migrates: the column is back
        assert out["refusal"] is None and any("jobs.last_error" in x for x in out["changes"]), out
        got, _err = _boot_worker_as(wurl)
        assert got["rc"] == 0, got
        assert _owned_by(owner, "bl_worker") == []
    finally:
        _reset()


if __name__ == "__main__":
    tests = [(n, f) for n, f in list(globals().items()) if n.startswith("test_")]
    try:
        with _cluster() as (url, _bindir):
            failed = 0
            for name, fn in tests:
                try:
                    fn(url)
                    print(f"OK   {name}")
                except Exception as exc:  # noqa: BLE001
                    failed += 1
                    print(f"FAIL {name} {exc!r}"[:700])
                    import traceback

                    traceback.print_exc()
    except _Skip as e:
        print(f"SKIP test_ws4_7_postgres: {e}")
        sys.exit(0)
    print(f"{failed} failed")
    sys.exit(1 if failed else 0)
