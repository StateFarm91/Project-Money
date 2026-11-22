"""Audit F-14: whole-table ORM entity scans behind GET /api/readback/evidence.

The production route passes `deploy_handlers`, so `/api/swarm/runtime` (and with it
`agent_quality`, `work_items`, `parallel_window`) runs in-process on every evidence read.
Those, and `build2.maturity._signals`, `products.inventory.chain_evidence` and
`gateway.paid_calls.summary`, loaded whole `jobs` / `audit_log` / `paid_call_records` rows
-- JSON inputs, outputs, detail and payload included -- to read a handful of scalar columns.

Proved here, on a seeded database with bulky JSON:

1. none of the fixed functions sends a SELECT that reads `jobs.inputs`, `jobs.outputs`
   (except `chain_evidence`'s slug filter, which reads `inputs` only), `audit_log.detail`
   or `paid_call_records.payload`;
2. ZERO behaviour change: each function returns exactly what the OLD implementation
   returns. The oracle is the old implementation itself: the function's current source
   with the old (entity-load) lines substituted back, executed in the module's namespace;
3. `production_evidence.evidence(db, deploy_handlers=<the real app.main handlers>)` sends no
   unbounded entity SELECT on `jobs` (one with `jobs.inputs` and no WHERE clause).

Run: cd brambleloop && PYTHONPATH=src:tests python tests/test_audit_table_scans.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import contextlib
import inspect
import json
import os
import re
import sys
import tempfile
import textwrap
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

_TMP = tempfile.mkdtemp()
os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{os.path.join(_TMP, 'main.db')}"
os.environ.pop("DATABASE_URL", None)
os.environ.setdefault("BRAMBLELOOP_ARTIFACT_DIR", os.path.join(_TMP, "artifacts"))

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from sqlalchemy import event  # noqa: E402

from brambleloop.core.db import Database  # noqa: E402

NOW = datetime.now(timezone.utc).replace(microsecond=0)
BULK = "x" * 1500
_JOBS_N, _AUDIT_N, _PAID_N = 4000, 4000, 600
# job types `function_quality` reads outputs of (orchestrate.function_quality)
_METRIC_TYPES = ("radar.score", "cir.compile", "gate.certify", "cir.draft",
                 "marketing.schedule")

# A column of a bulky JSON field, qualified by its table, as SQLAlchemy renders it.
_JOB_INPUTS = re.compile(r"\bjobs\.inputs\b", re.I)
_JOB_OUTPUTS = re.compile(r"\bjobs\.outputs\b", re.I)
_AUDIT_DETAIL = re.compile(r"\baudit_log\.detail\b", re.I)
_PAID_PAYLOAD = re.compile(r"\bpaid_call_records\.payload\b", re.I)


@contextlib.contextmanager
def _probe(db: Database):
    """Every SELECT sent to the database, whitespace-normalised."""
    seen: list[str] = []

    def before(conn, cursor, statement, params, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            seen.append(" ".join(statement.split()))

    event.listen(db.engine, "before_cursor_execute", before)
    try:
        yield seen
    finally:
        event.remove(db.engine, "before_cursor_execute", before)


# `function_quality` needs `outputs` (its metrics are read from them), so the one statement
# allowed to read `jobs.outputs` is its per-agent read of exactly (job_type, outputs).
_OUTPUTS_NEEDED = re.compile(r"^SELECT jobs\.job_type, jobs\.outputs FROM jobs WHERE jobs\.agent = ",
                             re.I)


# Out of this fix's scope, and listed in the audit report: an action-filtered audit read
# whose `detail` its caller uses (`improve.roles.activity_from_db`, reached from
# `function_quality` for the role metric). Only `WHERE audit_log.action = ?` reads pass.
_DETAIL_BY_ACTION = re.compile(r"\bFROM audit_log WHERE audit_log\.action = \?", re.I)


def _bulky(seen: list[str], *, allow_inputs: bool = False) -> list[str]:
    pats = [_PAID_PAYLOAD] + ([] if allow_inputs else [_JOB_INPUTS])
    return [q for q in seen if any(p.search(q) for p in pats)
            or (_JOB_OUTPUTS.search(q) and not _OUTPUTS_NEEDED.search(q))
            or (_AUDIT_DETAIL.search(q) and not _DETAIL_BY_ACTION.search(q))]


def _seed(db: Database) -> dict:
    """Jobs for the real agents, with bulky JSON, every status, naive and aware times,
    permission-denied errors; audit rows (some with job ids, some repeated, some None);
    paid-call records in every outcome."""
    from brambleloop.agents.registry import Registry
    from brambleloop.core.models import AuditLog, Job, JobStatus
    from brambleloop.gateway import paid_calls

    reg = Registry(db)
    reg.seed_defaults()
    agents = [a.name for a in reg.all()]
    statuses = list(JobStatus)
    errors = (None, "", "permission denied: job type not held",
              "RuntimeError: " + BULK, "permission denied" + "y" * 80)
    slugs = ("alpha-shawl", "beta-hat", "gamma-cowl")
    with db.session() as s:
        for k in range(_JOBS_N):
            st = statuses[k % len(statuses)]
            fin = NOW - timedelta(hours=k % 2000)
            if k % 7 == 0:
                fin = None
            elif k % 3 == 0:
                fin = fin.replace(tzinfo=None)
            jt = ("store.publish" if k % 13 == 0 else
                  _METRIC_TYPES[k % len(_METRIC_TYPES)] if k % 2 else
                  f"type.{k % 9}" if k % 4 else "listing.package")
            s.add(Job(agent=agents[k % len(agents)] if k % 17 else "ghost-agent",
                      job_type=jt, status=st, attempts=k % 4,
                      inputs={"slug": slugs[k % 3] if k % 5 == 0 else None, "bulk": BULK},
                      outputs={"bulk": BULK, "n": k, **({"promoted": k % 3 == 0,
                               "compiled": k % 4 != 1, "granted": k % 5 != 2,
                               "problems": [] if k % 6 else ["p"]} if k % 11 else {})},
                      last_error=errors[k % len(errors)],
                      started_at=(fin - timedelta(minutes=5 + k % 30)) if fin else None,
                      finished_at=fin, created_at=NOW - timedelta(hours=k % 2000)))
        s.flush()
        for k in range(_AUDIT_N):
            s.add(AuditLog(at=NOW - timedelta(minutes=k), actor="seed",
                           action=("store.publish_refused" if k % 50 == 0 else "seed.act"),
                           artifact=f"{slugs[k % 3]}@1.0.0",
                           job_id=None if k % 3 == 0 else 1 + (k * 7) % _JOBS_N,
                           detail={"bulk": BULK, "k": k}))
    paid_calls.ensure_table(db)
    outcomes = (paid_calls.PENDING, paid_calls.UNCERTAIN, paid_calls.OK, "failed")
    with db.session() as s:
        for k in range(_PAID_N):
            s.add(paid_calls.PaidCallRecord(
                key=f"{k:064x}", effect=f"effect.{k % 5}", job_id=None if k % 4 else k,
                fingerprint="f" * 64, outcome=outcomes[k % len(outcomes)],
                replays=k % 3, orphan_billed=bool(k % 2), payload={"bulk": BULK},
                at=NOW - timedelta(minutes=k)))
    return {"slugs": slugs}


_DB: Database | None = None


def _db() -> Database:
    global _DB
    if _DB is None:
        _DB = Database(f"sqlite:///{tempfile.mkdtemp()}/scan.db")
        _DB.create_all()
        _seed(_DB)
    return _DB


# --- the oracle: the OLD implementation, exactly -------------------------------------
# Each entry: (module, function, the NEW lines now in the source, the OLD lines they
# replaced at base f9011cf). The oracle is the current function with the old lines put back.
_OLD = {
    "agent_quality": ("brambleloop.swarm.orchestrate", "agent_quality", """\
        # F-14: the five columns read, never the entity (inputs/outputs JSON stay unread).
        jobs = [(j.agent, j.job_type, _status(j), _aware(j.finished_at),
                 (j.last_error or "")[:40]) for j in s.execute(
                     select(Job.agent, Job.job_type, Job.status, Job.finished_at,
                            Job.last_error))]""", """\
        jobs = [(j.agent, j.job_type, _status(j), _aware(j.finished_at),
                 (j.last_error or "")[:40]) for j in s.scalars(select(Job))]"""),
    "function_quality": ("brambleloop.swarm.orchestrate", "function_quality", """\
            # F-14: the two columns read, never the entity (inputs JSON stays unread), and
            # the job-type filter also in SQL (exact string equality, as in Python) so only
            # the matching rows' outputs are read; every caller only counts these rows.
            q = select(Job.job_type, Job.outputs).where(
                Job.agent == name, Job.status == _TERMINAL_OK_STATUS())
            if job_types is not None:
                q = q.where(Job.job_type.in_(job_types))
            return [dict(j.outputs or {}) for j in s.execute(q)
                    if job_types is None or j.job_type in job_types]""", """\
            q = select(Job).where(Job.agent == name, Job.status == _TERMINAL_OK_STATUS())
            return [dict(j.outputs or {}) for j in s.scalars(q)
                    if job_types is None or j.job_type in job_types]"""),
    "work_items": ("brambleloop.swarm.orchestrate", "work_items", """\
        # F-14: the columns read, never the entity (inputs/outputs JSON stay unread).
        for job in s.execute(select(Job.id, Job.agent, Job.job_type, Job.status).where(
                Job.status.in_((JobStatus.PENDING, JobStatus.RUNNING, JobStatus.FAILED)))):""",
                   """\
        for job in s.scalars(select(Job).where(
                Job.status.in_((JobStatus.PENDING, JobStatus.RUNNING, JobStatus.FAILED)))):"""),
    "parallel_window": ("brambleloop.swarm.metrics", "parallel_window", """\
        # F-14: the columns read, never the entity (inputs/outputs JSON stay unread).
        for j in s.execute(select(Job.started_at, Job.finished_at, Job.attempts,
                                  Job.last_error, Job.status).where(
                Job.finished_at.is_not(None), Job.finished_at >= since)):""", """\
        for j in s.scalars(select(Job).where(Job.finished_at.is_not(None),
                                             Job.finished_at >= since)):"""),
    "_signals": ("brambleloop.build2.maturity", "_signals", """\
        # F-14: four columns, and the distinct audited job ids, never whole entities.
        rows = [(j.id, j.job_type, j.status, j.finished_at) for j in s.execute(
            select(Job.id, Job.job_type, Job.status, Job.finished_at))]
        audited_job_ids = set(s.scalars(select(AuditLog.job_id).where(
            AuditLog.job_id.is_not(None)).distinct()))""", """\
        rows = [(j.id, j.job_type, j.status, j.finished_at)
                for j in s.scalars(select(Job))]
        audited_job_ids = {a.job_id for a in s.scalars(select(AuditLog))
                           if a.job_id is not None}"""),
    "chain_evidence": ("brambleloop.products.inventory", "chain_evidence", """\
            # F-14: the three columns read; the slug filter stays in Python (JSON dialects).
            jobs = [j for j in s.execute(select(Job.job_type, Job.status, Job.inputs))
                    if (j.inputs or {}).get("slug") == slug]""", """\
            jobs = [j for j in s.scalars(select(Job)) if (j.inputs or {}).get("slug") == slug]"""),
    "summary": ("brambleloop.gateway.paid_calls", "summary", """\
            # F-14: the columns read, never the entity (the payload JSON stays unread).
            all_rows = list(s.execute(select(
                PaidCallRecord.key, PaidCallRecord.effect, PaidCallRecord.job_id,
                PaidCallRecord.outcome, PaidCallRecord.orphan_billed,
                PaidCallRecord.replays)))""", """\
            all_rows = list(s.scalars(select(PaidCallRecord)))"""),
}


def _old(name: str):
    import importlib

    modname, fn, new, old = _OLD[name]
    mod = importlib.import_module(modname)
    src = textwrap.dedent(inspect.getsource(getattr(mod, fn)))
    assert src.count(new) == 1, f"{name}: the fixed lines are not in the source (unfixed?)"
    ns: dict = {}
    exec(compile(src.replace(new, old), f"<old {name}>", "exec"), mod.__dict__, ns)
    return ns[fn]


def _new(name: str):
    import importlib

    modname, fn, _, _ = _OLD[name]
    return getattr(importlib.import_module(modname), fn)


def _canon(value):
    """Comparable form: WorkItem dataclasses and datetimes rendered, order preserved."""
    return json.loads(json.dumps(value, default=repr, sort_keys=True))


_CALLS = {
    "agent_quality": lambda f, db: f(db, now=NOW),
    "function_quality": lambda f, db: {a: f(db, a, now=NOW) for a in _agents(db)},
    "work_items": lambda f, db: f(db),
    "parallel_window": lambda f, db: f(db, hours=24 * 30, now=NOW),
    "_signals": lambda f, db: f(db),
    "chain_evidence": lambda f, db: f(db, "alpha-shawl"),  # no Product row: the job scan
    "summary": lambda f, db: f(db),
}


def _agents(db) -> list[str]:
    from brambleloop.agents.registry import Registry

    return [a.name for a in Registry(db).all()]


_TIMINGS: dict[str, tuple[float, float]] = {}


def _strip_clock(name: str, out):
    if name == "summary" and isinstance(out, dict):
        out = dict(out)
        out.pop("as_of", None)  # utcnow() at call time, the only value that may differ
    return out


def test_fixed_functions_select_no_bulky_json_column():
    db = _db()
    # guard against a vacuous pass: the probe does see an entity load
    from sqlalchemy import select

    from brambleloop.core.models import AuditLog, Job

    with _probe(db) as seen, db.session() as s:
        s.scalars(select(Job).limit(1)).first()
        s.scalars(select(AuditLog).limit(1)).first()
    assert len(_bulky(seen)) == 2, seen
    assert _OUTPUTS_NEEDED.search("SELECT jobs.job_type, jobs.outputs FROM jobs WHERE jobs.agent = ?")
    problems = {}
    for name, call in _CALLS.items():
        with _probe(db) as seen:
            call(_new(name), db)
        bad = _bulky(seen, allow_inputs=(name == "chain_evidence"))
        if bad:
            problems[name] = bad
    assert not problems, json.dumps(problems, indent=1)


def test_each_function_returns_exactly_what_the_old_implementation_returned():
    db = _db()
    for name, call in _CALLS.items():
        old_f, new_f = _old(name), _new(name)
        t0 = time.perf_counter()
        before = call(old_f, db)
        t1 = time.perf_counter()
        after = call(new_f, db)
        t2 = time.perf_counter()
        _TIMINGS[name] = (t1 - t0, t2 - t1)
        if name == "_signals":  # sets of strings: compared as sets (their repr order is not)
            assert after == before, name
        else:
            assert _canon(_strip_clock(name, after)) == _canon(_strip_clock(name, before)), name
    # the oracle comparison is not vacuous: the seed exercises each function's data
    q = _CALLS["agent_quality"](_new("agent_quality"), db)
    assert sum(a["sample"] for a in q["agents"].values()) > 100, q
    assert any(a["permission_denied"] for a in q["agents"].values()), q
    assert len([w for w in _new("work_items")(db) if w["source"] == "job"]) > 1000
    assert _CALLS["parallel_window"](_new("parallel_window"), db)["attempts"] > 100
    sig = _new("_signals")(db)
    assert sig["jobs_audited"] and sig["jobs_recent"], sig
    fq = _CALLS["function_quality"](_new("function_quality"), db)
    assert sum(1 for v in fq.values() if v["sample"]) >= 3, fq
    assert len(_new("chain_evidence")(db, "alpha-shawl")["jobs"]) > 3
    assert _new("summary")(db)["unresolved"] > 100
    for name, (a, b) in _TIMINGS.items():
        print(f"     {name}: old {a * 1000:.0f} ms -> new {b * 1000:.0f} ms")


def test_evidence_with_deploy_handlers_sends_no_unbounded_entity_select_on_jobs():
    from brambleloop.app import main
    from brambleloop.ops import production_evidence as pe

    import _evidence_seed

    db = main.db
    db.create_all()
    _evidence_seed.seed(db, now=NOW)
    _seed(db)
    handlers = {"/api/departments": main.api_departments,
                "/api/swarm/runtime": main.api_swarm_runtime,
                "/api/funding/packets": main.api_funding_packets,
                "/api/offsite": main.api_offsite,
                "/api/continuity": main.api_continuity, "/api/etsy": main.api_etsy}
    with _probe(db) as seen:
        t0 = time.perf_counter()
        ev = pe.evidence(db, now=NOW, deploy_handlers=handlers)
        took = time.perf_counter() - t0
    unbounded = [q[:220] for q in seen if _JOB_INPUTS.search(q) and " WHERE " not in q.upper()]
    assert unbounded == [], unbounded
    assert ev["deploy_readback"]["/api/swarm/runtime"]["status"] == 200, ev["deploy_readback"]
    with _probe(db) as seen:
        main.api_swarm_runtime()
    assert _bulky(seen) == [], _bulky(seen)
    print(f"     evidence with deploy handlers: {took * 1000:.0f} ms")


TESTS = [v for k, v in dict(globals()).items() if k.startswith("test_") and callable(v)]

if __name__ == "__main__":
    failed = 0
    for t in TESTS:
        try:
            t()
            print(f"OK   {t.__name__}")
        except Exception:  # noqa: BLE001
            import traceback

            failed += 1
            print(f"FAIL {t.__name__}")
            traceback.print_exc()
    print(f"{len(TESTS) - failed}/{len(TESTS)} passed")
    sys.exit(1 if failed else 0)
