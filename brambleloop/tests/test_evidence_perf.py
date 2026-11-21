"""eng/evidence-perf: GET /api/readback/evidence on a production-sized database.

Production took 45-91 s and `ops/readback.py` (60 s) timed out, so the readback read the
evidence as UNKNOWN. The cost was the same rows read again and again -- every product's
release history with its CIR and certificate JSON, once per `lifecycle.derive` (16 for the
certification board, then one per parked release for the sale admission), once per
`newest_release`, once in `current_from_db` -- plus unbounded job scans.

Proved here, on a seeded database of production's shape (600 provenance rows, 200
incidents, 16 products with release histories, 6000 jobs, 6000 audit rows, 40 parked runs):

1. the whole evidence body is built within a generous wall-clock bound;
2. ONE `current_from_db` and ONE `artefacts.check` per request, each product derived once,
   the halted releases read once, each listing package read once;
3. the request memo changes nothing: the body is identical with the memo switched off;
4. the memo is request-scoped: the next request sees new rows; a failed read is never
   cached (it stays UNKNOWN, never 0), and readers never share a mutable result;
5. no private text: seeded inputs, outputs, error text and incident text never appear;
6. the bounded dead-letter and factory-job queries count exactly what the old scans did;
7. the new indexes exist after `create_all`, and `ops/readback.py` waits 120 s.

Run: cd brambleloop && PYTHONPATH=src:tests .venv/bin/python tests/test_evidence_perf.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import contextlib
import json
import os
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT.parent / "ops"))

from brambleloop.core import request_memo  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.ops import production_evidence as pe  # noqa: E402

import _evidence_seed  # noqa: E402

NOW = datetime(2026, 11, 21, 3, 0, tzinfo=timezone.utc)
# Generous: the target is under 10 s in production; this machine builds it in about 1 s.
# A regression to the old repeated reads at production scale blows well past it.
BOUND_S = 30.0

_DB: Database | None = None


def _seeded() -> Database:
    global _DB
    if _DB is None:
        os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = tempfile.mkdtemp()
        _DB = Database(f"sqlite:///{tempfile.mkdtemp()}/prod.db")
        _DB.create_all()
        _evidence_seed.seed(_DB, now=NOW)
    return _DB


def _comparable(ev: dict) -> dict:
    """The body without its wall-clock fields (the only values that may differ)."""
    out = json.loads(json.dumps(ev, default=str))
    out.pop("timing_ms", None)
    (out.get("factory_visibility") or {}).pop("parked_admission_ms", None)
    return out


@contextlib.contextmanager
def _counting(module, name, calls: list):
    real = getattr(module, name)

    def wrapped(*a, **k):
        calls.append(a[1:] if len(a) > 1 else ())
        return real(*a, **k)

    setattr(module, name, wrapped)
    try:
        yield
    finally:
        setattr(module, name, real)


def test_production_sized_evidence_is_built_within_the_bound():
    db = _seeded()
    pe.evidence(db, now=NOW)            # warm imports once; the bound is on the request
    t0 = time.perf_counter()
    ev = pe.evidence(db, now=NOW)
    took = time.perf_counter() - t0
    print(f"     evidence on the production-sized DB: {took:.2f} s "
          f"(slowest: {list(ev['timing_ms'].items())[:3]})")
    assert took < BOUND_S, (took, ev["timing_ms"])
    fv = ev["factory_visibility"]
    # the seeded shape is really exercised, not a vacuous pass
    assert fv["parked_runs"] == 40 and len(fv["parked_admission"]) == 12, fv
    assert fv["stale_incidents"]["open"] > 50, fv["stale_incidents"]
    assert ev["certification_pipeline"]["products"] == 16, ev["certification_pipeline"]


def test_one_provenance_check_and_one_read_of_each_shared_row_per_request():
    from brambleloop.ops import artefacts
    from brambleloop.products import lifecycle
    from brambleloop.publish import listing_package
    from brambleloop.runtime import release_recovery

    db = _seeded()
    checks, currents, derives, halted, packages = [], [], [], [], []
    with _counting(artefacts, "check", checks), \
            _counting(artefacts, "current_from_db", currents), \
            _counting(lifecycle, "_derive", derives), \
            _counting(release_recovery, "_halted_releases", halted), \
            _counting(listing_package, "_latest", packages):
        pe.evidence(db, now=NOW)
    assert len(checks) == 1 and len(currents) == 1, (len(checks), len(currents))
    slugs = [a[0] for a in derives]
    assert len(slugs) == len(set(slugs)) == 16, sorted(slugs)
    assert len(halted) == 1, halted
    assert len(packages) == len(set(packages)), packages


def test_the_memo_changes_nothing_in_the_body():
    db = _seeded()
    with_memo = _comparable(pe.evidence(db, now=NOW))
    real_scope = request_memo.scope
    request_memo.scope = contextlib.nullcontext   # every read live, as before the memo
    try:
        assert not request_memo.active()
        without = _comparable(pe.evidence(db, now=NOW))
    finally:
        request_memo.scope = real_scope
    assert with_memo == without
    # and /api/verify's evidence_checks likewise
    assert pe.checks(db, now=NOW) == pe._checks(db, now=NOW)


def test_the_memo_is_request_scoped_and_never_caches_a_failure():
    from brambleloop.core.models import Incident
    from brambleloop.ops import artefacts

    db = _seeded()
    before = pe.evidence(db, now=NOW)["factory_visibility"]["stale_incidents"]["open"]
    with db.session() as s:
        s.add(Incident(product_slug="seed-product-00", resolved=False,
                       signature=f"{artefacts.SENTINEL_SIGNATURE}:pdf:seed-product-00@1.1.0:x"))
    try:
        after = pe.evidence(db, now=NOW)["factory_visibility"]["stale_incidents"]["open"]
        assert after == before + 1, (before, after)   # the next request reads live rows
    finally:
        with db.session() as s:
            s.query(Incident).filter(Incident.signature.like("%:seed-product-00@1.1.0:x")
                                     ).delete(synchronize_session=False)

    # outside a scope: a plain call every time
    n = []
    assert request_memo.memo("k", lambda: n.append(1) or len(n)) == 1
    assert request_memo.memo("k", lambda: n.append(1) or len(n)) == 2
    # inside: once per key, each reader its own copy, a failure never cached
    with request_memo.scope():
        a = request_memo.memo("d", lambda: {"x": [1]})
        a["x"].append(2)
        assert request_memo.memo("d", lambda: {"x": [9]}) == {"x": [1]}
        boom = []

        def fail():
            boom.append(1)
            raise RuntimeError("unreadable")

        for _ in range(2):
            with contextlib.suppress(RuntimeError):
                request_memo.memo("f", fail)
        assert boom == [1, 1]
    assert not request_memo.active()

    # UNKNOWN stays UNKNOWN: an unreadable provenance read is an unreadable section, never
    # "0 open incidents", and the next reader in the same request reads (and fails) again.
    calls = []
    real = artefacts.current_from_db

    def broken(*a, **k):
        calls.append(1)
        raise RuntimeError("database gone")

    artefacts.current_from_db = broken
    try:
        with request_memo.scope():
            ev = pe.factory_visibility(db, now=NOW)
            again = pe.factory_visibility(db, now=NOW)
    finally:
        artefacts.current_from_db = real
    for v in (ev, again):
        assert v["stale_incidents"] == {"readable": False, "error_class": "RuntimeError"}, v
    assert calls == [1, 1], calls


def test_the_evidence_carries_no_private_seeded_text():
    db = _seeded()
    text = json.dumps(pe.evidence(db, now=NOW), default=str)
    assert _evidence_seed.PRIVATE_MARK not in text
    assert "PricingNotPass" in text      # the leading code of a blocker is the vocabulary


def test_the_bounded_job_queries_count_what_the_full_scans_counted():
    from brambleloop.core.models import Job, JobStatus

    db = Database(f"sqlite:///{tempfile.mkdtemp()}/b.db")
    db.create_all()
    old, new = NOW - timedelta(hours=30), NOW - timedelta(hours=2)
    with db.session() as s:   # jobs.created_at is NOT NULL, so every row has a time
        for fin, created, jt in ((new, old, "a.finished_in_window"),
                                 (None, new, "b.created_in_window"),
                                 (old, new, "c.finished_before_window"),
                                 (None, old, "d.created_before_window"),
                                 (NOW + timedelta(hours=1), old, "f.future")):
            s.add(Job(agent="t", job_type=jt, status=JobStatus.DEAD, last_error="x",
                      finished_at=fin, created_at=created))
        for created in (new, old, NOW + timedelta(hours=1)):
            s.add(Job(agent="t", job_type="listing.package", status=JobStatus.DONE,
                      created_at=created))
    dl = pe.dead_letters(db, now=NOW)
    assert sorted(g["job_type"] for g in dl["by_type"]) == [
        "a.finished_in_window", "b.created_in_window", "f.future"], dl
    fv = pe.factory_visibility(db, now=NOW)
    # in-window and future rows are counted (as the full scan did); the old one is not
    assert fv["jobs_24h"] == {"listing.package:done": 2}, fv["jobs_24h"]


def test_indexes_exist_and_the_readback_client_waits_120_seconds():
    from sqlalchemy import inspect

    db = _seeded()
    insp = inspect(db.engine)
    assert "ix_jobs_type_status_finished" in {i["name"] for i in insp.get_indexes("jobs")}
    audit = {i["name"] for i in insp.get_indexes("audit_log")}
    assert {"ix_audit_log_action_id", "ix_audit_log_action_at"} <= audit, audit
    import readback

    assert readback.HTTP_TIMEOUT_S == 120
    src = (ROOT.parent / "ops" / "readback.py").read_text()
    assert "timeout=HTTP_TIMEOUT_S" in src and "timeout=60" not in src


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
