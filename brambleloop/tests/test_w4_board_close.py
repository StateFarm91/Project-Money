"""W4-BOARD closures: evidence for rows the 2026-10-19 spot audit found under-proven.

* Build 2 #184 names "clock drift" among the queue behaviours to test; nothing tested it. Leases
  are judged by each process's own clock (queue/durable.py `utcnow`), so two containers whose
  clocks disagree are the realistic failure: a fast clock reclaims a lease its holder still
  believes it owns, a slow clock sees an expired lease as live. The lease-token fence must keep
  the effect exactly-once either way.
* F-182 says the dashboard verification must FAIL while an already-satisfied owner action is
  still presented. Only the green path was tested; this forces the presented-but-satisfied case.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_w4_board_close.py
"""
from __future__ import annotations
import _opread  # W4-SECPATCH: owner-only GETs need the operator credential

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import os
import socket
import sys
import tempfile
import time
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

_TMP = tempfile.mkdtemp(prefix="w4_board_close_")
DB_FILE = os.path.join(_TMP, "board.db")
os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{DB_FILE}"
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")
os.environ.pop("BRAMBLELOOP_REQUIRE_POSTGRES", None)
os.environ.pop("BRAMBLELOOP_EMBEDDED_WORKER", None)
for _k in list(os.environ):
    if _k.startswith(("ANTHROPIC_API", "ETSY", "OPENAI", "REPLICATE", "FAL_", "GEMINI")):
        os.environ.pop(_k)


def _no_network(*_a, **_k):
    raise OSError("network refused by the board-closure harness")


socket.socket.connect = _no_network  # type: ignore[assignment]
socket.create_connection = _no_network  # type: ignore[assignment]

from sqlalchemy import select  # noqa: E402

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog, Job, JobStatus, utcnow  # noqa: E402
from brambleloop.queue import durable  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402

_n = [0]


def _db() -> Database:
    _n[0] += 1
    db = Database(f"sqlite:///{_TMP}/q{_n[0]}.sqlite")
    db.create_all()
    return db


class _Clock:
    """Stands in for one container's wall clock: the queue reads `durable.utcnow`."""

    def __init__(self, offset: timedelta):
        self.offset = offset

    def __enter__(self):
        self._orig = durable.utcnow
        durable.utcnow = lambda: self._orig() + self.offset
        return self

    def __exit__(self, *exc):
        durable.utcnow = self._orig
        return False


def _job(db, job_id):
    with db.session() as s:
        return s.get(Job, job_id)


def test_b184_a_fast_clock_reclaims_but_the_stale_holder_cannot_complete_over_it():
    db = _db()
    q = JobQueue(db, lease_seconds=60)
    j = q.enqueue("orchestrator", "ops.heartbeat", {"case": "fast-clock"})
    a = q.claim("worker-a")
    assert a is not None and a.id == j.id and a.lease_token
    # Container B's clock runs five minutes ahead: A's live lease looks expired to it.
    with _Clock(timedelta(minutes=5)):
        b = q.claim("worker-b")
    assert b is not None and b.id == j.id, "the drifted clock reclaimed the job"
    assert b.lease_token and b.lease_token != a.lease_token
    # A finishes and reports with the claim it holds: fenced off, nothing written.
    assert q.complete(j.id, {"by": "a"}, worker="worker-a", lease_token=a.lease_token) is False
    row = _job(db, j.id)
    assert row.status == JobStatus.RUNNING and row.leased_by == "worker-b"
    # B's report is the one that lands -- exactly once.
    assert q.complete(j.id, {"by": "b"}, worker="worker-b", lease_token=b.lease_token) is True
    row = _job(db, j.id)
    assert row.status == JobStatus.DONE and row.outputs == {"by": "b"}
    assert q.complete(j.id, {"by": "a-again"}, worker="worker-a",
                      lease_token=a.lease_token) is False
    assert _job(db, j.id).outputs == {"by": "b"}
    with db.session() as s:
        refused = s.scalars(select(AuditLog).where(
            AuditLog.action == "queue.stale_lease_refused", AuditLog.job_id == j.id)).all()
    assert len(refused) >= 1, "the refused stale write is recorded, not silently dropped"


def test_b184_a_slow_clock_never_takes_a_live_lease_and_takes_an_expired_one_late():
    db = _db()
    q = JobQueue(db, lease_seconds=60)
    j = q.enqueue("orchestrator", "ops.heartbeat", {"case": "slow-clock"})
    a = q.claim("worker-a")
    assert a is not None and a.id == j.id
    with _Clock(timedelta(minutes=-10)):
        assert q.claim("worker-b") is None, "a slow clock must not steal a live lease"
    # Real expiry: move the stored lease into the past, as if A died two minutes ago.
    with db.session() as s:
        s.get(Job, j.id).lease_expires_at = utcnow() - timedelta(minutes=2)
    with _Clock(timedelta(minutes=-10)):
        # Ten minutes slow, B still believes the dead lease is live: late, never early.
        assert q.claim("worker-b") is None
    b = q.claim("worker-b")                         # B's clock corrected
    assert b is not None and b.id == j.id and b.lease_token != a.lease_token
    assert q.complete(j.id, {"by": "b"}, worker="worker-b", lease_token=b.lease_token)
    assert _job(db, j.id).status == JobStatus.DONE


def test_b184_a_drifted_enqueue_of_the_same_cadence_slot_is_deduplicated():
    """Overlapping schedules under drift: two schedulers that compute the same idempotency key
    enqueue one job, whatever their clocks say."""
    db = _db()
    q = JobQueue(db, lease_seconds=60)
    first = q.enqueue("orchestrator", "ops.heartbeat", {}, idempotency_key="cadence:hb:slot-1")
    with _Clock(timedelta(minutes=3)):
        try:
            q.enqueue("orchestrator", "ops.heartbeat", {}, idempotency_key="cadence:hb:slot-1")
            raise AssertionError("a drifted scheduler enqueued a duplicate cadence job")
        except durable.DuplicateJob as dup:
            assert dup.existing_id == first.id
    with db.session() as s:
        n = len(s.scalars(select(Job).where(Job.idempotency_key == "cadence:hb:slot-1")).all())
    assert n == 1


def test_f697_durable_artifacts_ride_in_the_continuity_export():
    """F-697's remaining part named the canonical model's approved body frames, which live only
    in `durable_artifacts`. The offsite archive is the continuity export, so that table -- and
    every table but the credential/session/archive ones -- must be in it, with its bytes."""
    from brambleloop.core import continuity
    from brambleloop.core.models import DurableArtifact

    names = {t.name for t in continuity._ordered_tables()}
    assert "durable_artifacts" in names and "jobs" in names and "audit_log" in names
    assert set(continuity.EXCLUDED_TABLES) == {
        "continuity_archives", "oauth_credentials", "oauth_handshakes", "cc_owner_sessions",
        "cc_nonces"}, continuity.EXCLUDED_TABLES
    src = _db()
    payload = b"\x89PNG approved body frame"
    with src.session() as s:
        s.add(DurableArtifact(sha256="a" * 64, content_type="image/png",
                              bytes_len=len(payload), payload=payload, why_kept="F-697"))
    result = continuity.export(src, f"{_TMP}/f697.jsonl")
    dst = Database(f"sqlite:///{_TMP}/f697_restored.sqlite")
    counts = continuity.restore(result.path, dst)
    assert counts["durable_artifacts"] == 1, counts
    with dst.session() as s:
        got = s.get(DurableArtifact, "a" * 64)
        assert got is not None and got.payload == payload


def test_b195_a_department_whose_brief_is_refused_does_not_kill_the_reference_job():
    """Production 1b21e81 dead-lettered creative.reference_reading at 12:47:30Z: one
    department's evidence named a subject ('pumpkin'), its brief was refused by raising, and the
    exception killed the whole daily job (#195's off-device proof counts it). The refusal must
    stand -- nothing stored for that department, the reason returned -- and the rest continue."""
    from brambleloop.core.models import BenchmarkListing, OperatingReading
    from brambleloop.creative import reference
    from brambleloop.intel import benchmarks

    db = _db()
    with db.session() as s:
        for pod in ("decor", "garments"):
            s.add(BenchmarkListing(benchmark_key=benchmarks.MJS_KEY, listing_ref=f"{pod}-1",
                                   pod=pod, detail={}))
    real_brief = reference.brief

    def brief(_db, pod, *, benchmark_key=""):
        if pod == "decor":
            reference.check_free_of_depiction(["autumn pumpkin patch setting"])
        return {"usable": True, "primitives": {"silhouette": "boxy"}, "absent": [],
                "listings_with_evidence": 2}

    reference.brief = brief
    try:
        got = reference.run(db, provider=object(), today=None)
    finally:
        reference.brief = real_brief
    assert got["ran"] is True
    assert got["decompositions_stored"] == ["garments"], got
    assert [r["pod"] for r in got["decompositions_refused"]] == ["decor"], got
    assert "depicts" in got["decompositions_refused"][0]["why"]
    with db.session() as s:
        pods = {r.period_key for r in s.scalars(select(OperatingReading).where(
            OperatingReading.kind == reference.DECOMPOSITION_KIND))}
    assert pods == {"garments"}, "the refused department stored nothing"


def test_f182_a_satisfied_action_still_presented_fails_the_verification():
    from fastapi.testclient import TestClient

    from brambleloop.agents.registry import Registry
    from brambleloop.app import main
    from brambleloop.build2 import executor
    from brambleloop.core.models import OwnerAction

    assert str(main.db.engine.url).endswith(DB_FILE), main.db.engine.url
    main.db.create_all()
    Registry(main.db).seed_defaults()
    client = TestClient(main.app)
    old = os.environ.get("ETSY_SHOP_NAME")
    os.environ["ETSY_SHOP_NAME"] = "BoardShop"
    real_inbox = executor.approval_inbox
    try:
        with main.db.session() as s:
            s.add(AuditLog(actor="orchestrator", action="etsy.probe", detail={"ok": True}))
            s.add(OwnerAction(requirement_key="etsy_shop",
                              action="Open the Etsy shop BOARD-SENTINEL"))
        assert executor.GATE_BY_KEY["etsy_shop"].open(main.db, dict(os.environ))

        def chk():
            v = _opread.get(client, "/api/verify").json()
            return {c["check"]: c for c in v["checks"]}["no_satisfied_owner_action_presented"]

        green = chk()
        assert green["ok"] is True, green

        # A regression in the inbox's own filter: the satisfied card is presented anyway.
        def leaky_inbox(db, env=None):
            box = real_inbox(db, env=env)
            card = {"gate": "etsy_shop", "owner_action_id": 999,
                    "action": "Open the Etsy shop BOARD-SENTINEL"}
            return {**box, "cards": list(box["cards"]) + [card]}

        executor.approval_inbox = leaky_inbox
        red = chk()
        assert red["ok"] is False, red
        presented = red["evidence"]["presented_but_satisfied"]
        assert [p["gate"] for p in presented] == ["etsy_shop"], presented
    finally:
        executor.approval_inbox = real_inbox
        if old is None:
            os.environ.pop("ETSY_SHOP_NAME", None)
        else:
            os.environ["ETSY_SHOP_NAME"] = old


if __name__ == "__main__":
    t0 = time.monotonic()
    fails = 0
    tests = [(n, f) for n, f in list(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        try:
            fn()
            print("OK  ", name, flush=True)
        except Exception as e:  # noqa: BLE001
            fails += 1
            print("FAIL", name, f"{type(e).__name__}: {str(e)[:900]}", flush=True)
    print(f"{len(tests) - fails}/{len(tests)} passed in {time.monotonic() - t0:.0f}s")
    sys.exit(1 if fails else 0)
