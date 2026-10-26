"""W4-PRODFIX (production 051dbee2, 2026-10-26).

1. The certification/publication deadlock: the company-wide halt raised *because* stale
   marketing was widespread refused every marketing rebuild, and a rebuild that ended without
   delivering held its idempotency key for good, so nothing asked again.
2. Repeated paid requests: a paid but unusable gallery observation was re-bought by three
   later jobs, and the 6-hourly capability sweep re-rendered the identical image probe.
"""
import _tmp; _tmp.install()  # per-process temp sandbox, removed at exit
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sqlalchemy import select  # noqa: E402

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (AuditLog, BenchmarkListing, Incident, Job,  # noqa: E402
                                     JobStatus, Product)
from brambleloop.gateway import images  # noqa: E402
from brambleloop.intel import vision  # noqa: E402
from brambleloop.ops import rebuild_graph  # noqa: E402
from brambleloop.publish import release_gates  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402

NOW = datetime(2026, 10, 26, 17, 0, tzinfo=timezone.utc)


def _db():
    db = Database(f"sqlite:///{tempfile.mkdtemp(prefix='prodfix-')}/t.sqlite")
    db.create_all()
    return db


# --- 1a: a staleness-only company-wide halt does not refuse the marketing rebuild ----------

def _stale_marketing_estate(db, *, integrity: bool = False):
    slugs = ["a", "b", "c"]
    with db.session() as s:
        for sl in slugs:
            s.add(Product(slug=sl, title=sl))
            s.add(Incident(severity="P1", product_slug=sl, halts_publication=True,
                           signature=f"stale-artefact:marketing_asset:{sl}:pin:1",
                           summary="stale"))
        s.add(Incident(severity="P0", product_slug=None, halts_publication=True,
                       signature="systemic-halt:publication", summary="systemic"))
        if integrity:
            s.add(Incident(severity="P0", product_slug=None, halts_publication=True,
                           signature="authority_chain_tamper:x", summary="tamper"))


def _gate(db, slug="a"):
    real_gate = rebuild_graph.publication_gate
    from brambleloop.gates import platform_policy

    real_policy = platform_policy.unreviewed_changes
    rebuild_graph.publication_gate = lambda s, slug: {
        "may_publish": False, "why": "stale", "outstanding": [f"marketing_asset:{slug}:pin:1"]}
    platform_policy.unreviewed_changes = lambda db: []
    try:
        return release_gates.staleness(db, slug=slug)
    finally:
        rebuild_graph.publication_gate = real_gate
        platform_policy.unreviewed_changes = real_policy


def test_a_staleness_only_systemic_halt_lets_the_marketing_rebuild_through():
    db = _db()
    _stale_marketing_estate(db)
    out = _gate(db)
    assert out["outstanding_only_marketing"] is True
    # publication still reads the halt
    assert out["halted"] is True and out["blocks"] is True
    assert any("systemic" in i["summary"] for i in out["incidents"])


def test_a_systemic_halt_with_an_integrity_failure_still_refuses_the_rebuild():
    db = _db()
    _stale_marketing_estate(db, integrity=True)
    assert _gate(db)["outstanding_only_marketing"] is False


# --- 1b: a terminal rebuild attempt is asked for again, once a day, never while in flight ---

def _plan(*_a, **_k):
    return {"rebuild": [{"key": "marketing_asset:a:pin:1", "product_slug": "a",
                         "artefact_class": "marketing_asset", "artefact_key": "a:pin:1"}],
            "changed": {"cir:a": "f" * 16}}


def test_a_rebuild_that_ended_without_delivering_is_asked_for_again_once_a_day():
    db = _db()
    q = JobQueue(db)
    real = rebuild_graph.rebuild_set
    rebuild_graph.rebuild_set = _plan
    try:
        def go(now):
            with db.session() as s:
                return rebuild_graph.enqueue(s, q, changed={"cir:a": "f" * 16}, reason="t",
                                             per="product", now=now)
        first = go(NOW)
        assert first["enqueued"] and not first["retried"]
        assert go(NOW)["already_queued"]                        # pending: no second job
        with db.session() as s:
            j = s.scalar(select(Job).where(Job.job_type == "chain.rebuild"))
            j.status, j.finished_at = JobStatus.DONE, NOW
        assert not go(NOW + timedelta(hours=2))["retried"]      # too soon after it ended
        later = NOW + timedelta(hours=13)
        again = go(later)
        assert again["retried"] == ["a"] and again["enqueued"]
        with db.session() as s:
            for j in s.scalars(select(Job).where(Job.job_type == "chain.rebuild")):
                j.status, j.finished_at = JobStatus.DONE, later
        assert not go(later + timedelta(hours=1))["retried"]   # ended an hour ago
        with db.session() as s:
            n = len(list(s.scalars(select(Job).where(Job.job_type == "chain.rebuild"))))
        assert n == 2
    finally:
        rebuild_graph.rebuild_set = real


# --- 2a: a paid, unusable gallery observation is not bought again ---------------------------

def test_a_paid_unusable_observation_gives_the_image_up_at_once():
    db = _db()
    with db.session() as s:
        s.add(BenchmarkListing(benchmark_key="k", listing_ref="L1", audit_state="audited",
                               detail={"image_urls": ["https://x/1.jpg", "https://x/2.jpg"]}))
    item = vision.pending(db, "k")[0]
    vision._mark_failed(db, item, give_up=True)
    assert [p.rank for p in vision.pending(db, "k")] == [2]
    vision._mark_failed(db, vision.pending(db, "k")[0])    # an unanswered attempt retries
    assert [p.rank for p in vision.pending(db, "k")] == [2]
    assert vision.pending_count(db, "k")["given_up_on"] == 1


# --- 2b: a fresh successful image probe is reused, a failed or old one re-probes -------------

def _probe_row(db, *, ok, at):
    with db.session() as s:
        s.add(AuditLog(actor="t", action=images.PROBE_ACTION,
                       detail={"ok": ok, "at": at.isoformat(), "provider": "p"}))


def test_a_fresh_successful_image_probe_is_reused_and_nothing_is_rendered():
    db = _db()
    calls = []
    real = images.probe
    images.probe = lambda db, **kw: calls.append(kw) or {"ok": True}
    try:
        _probe_row(db, ok=True, at=NOW - timedelta(hours=5))
        out = images.probe_if_due(db, now=NOW)
        assert out["reused"] is True and calls == []
        images.probe_if_due(db, now=NOW + timedelta(hours=20))
        assert len(calls) == 1                                  # older than a day: re-probe
        _probe_row(db, ok=False, at=NOW + timedelta(hours=20))
        images.probe_if_due(db, now=NOW + timedelta(hours=21))
        assert len(calls) == 2                                  # failed: always re-probe
    finally:
        images.probe = real


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("ok", n)
