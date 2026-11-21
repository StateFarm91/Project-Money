"""HALT-380 H2: does a rebuild produce an artefact whose fingerprint never equals what the
sentinel expects?

Production 7b250d61 (2026-11-21): systemic publishing halt #380 open since 2026-10-11; 12
products both stale-artefact and rebuild-incomplete; 112 open stale-artefact incidents; 12
chain.rebuild jobs constantly re-queued; no verified rebuild since 2026-11-20T13:12Z.

H2 says the rebuild's output fingerprint can never equal the sentinel's expectation, because
(i) the expected fingerprint carries code / version / layout identity the rebuild does not
reproduce, (ii) something non-deterministic differs, or (iii) verify compares against a
different binding than the sentinel. This file runs the real chain on one product (SQLite),
moves `chain:release` (what a deploy does), runs the sentinel -> chain.rebuild -> stage ->
verify passes, and then compares, for every artefact the rebuild was asked to remake:

* the row's recorded inputs against `current_from_db` (the sentinel's expectation);
* the row's recorded inputs against the fingerprints the rebuild request carried (the
  binding the verify pass checks);
* the same row's inputs after a second, independent rebuild at the same change (determinism).

Each comparison is printed, so the verdict in w6/review_requests/HALT-380-H2.md is read off
this output, not asserted from memory.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # per-process temp sandbox, removed at exit  # noqa: E702
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

_TMP = tempfile.mkdtemp(prefix="halt380_h2_")
os.environ.setdefault("BRAMBLELOOP_ARTIFACT_DIR", os.path.join(_TMP, "artifacts"))

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (ArtefactProvenance, AuditLog, Incident, Job,  # noqa: E402
                                     JobStatus, Phase, utcnow)
from brambleloop.ops import artefacts as A  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: E402,F401 - registers handlers
from brambleloop.runtime import release  # noqa: E402
from brambleloop.runtime.worker import Worker  # noqa: E402

SLUG = "cloudline-baby-blanket"


def _db():
    db = Database(f"sqlite:///{tempfile.mkdtemp(prefix='h2-', dir=_TMP)}/t.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _drain(db, name, limit=800):
    w = Worker(db, name, phase=Phase.SHADOW, lease_seconds=900)
    for _ in range(limit):
        if not w.run_once():
            break


def _elapse(db):
    with db.session() as s:
        for j in s.scalars(select(Job).where(Job.status == JobStatus.PENDING)):
            j.run_after = utcnow()


def _sentinel(db, tag):
    job = JobQueue(db).enqueue("orchestrator", "ops.sentinel", {}, priority=0,
                               idempotency_key=f"sentinel-{tag}")
    Worker(db, f"w-{tag}", phase=Phase.SHADOW, job_types=["ops.sentinel"]).run_once()
    with db.session() as s:
        row = s.get(Job, job.id)
        assert row.status == JobStatus.DONE, row.last_error
        return dict(row.outputs or {})


def _rows(s):
    return {f"{r.artefact_class}:{r.artefact_key}": dict(r.inputs or {})
            for r in s.scalars(select(ArtefactProvenance).where(
                ArtefactProvenance.product_slug == SLUG))}


class _MovedChain:
    def __init__(self, suffix):
        self.suffix = suffix

    def __enter__(self):
        self.saved = release.CHAIN_VERSION
        release.CHAIN_VERSION = self.saved + self.suffix
        return self

    def __exit__(self, *exc):
        release.CHAIN_VERSION = self.saved


def _build():
    from brambleloop.products import builder

    db = _db()
    cir = builder.for_slug(SLUG)
    JobQueue(db).enqueue("validator", "cir.compile", {"cir": cir.to_dict()},
                         idempotency_key="h2-compile")
    _drain(db, "h2-build")
    return db


def _rebuild_and_verify(db, tag):
    """sentinel -> chain.rebuild -> stage chain -> verify checks, at the moved change."""
    first = _sentinel(db, tag)
    for _ in range(6):
        _drain(db, f"h2-drain-{tag}")
        _elapse(db)
    return first


def _compare(db):
    """Every artefact a rebuild was requested for: recorded vs expected vs requested."""
    with db.session() as s:
        current = A.current_from_db(s)
        rows = _rows(s)
        verdicts = {f"{v.artefact_class}:{v.artefact_key}": v
                    for v in A.check(s, current=current)
                    if v.product_slug == SLUG}
        requested = {}
        for a in s.scalars(select(AuditLog).where(
                AuditLog.action == "chain.rebuild_requested")):
            requested[a.artifact] = (a.detail or {}).get("fingerprints") or {}
        unbound = [a.artifact for a in s.scalars(select(AuditLog).where(
            AuditLog.action == "chain.rebuild_unbound"))]
        completed = {a.artifact for a in s.scalars(select(AuditLog).where(
            AuditLog.action == "chain.rebuild_completed"))
            if not (a.detail or {}).get("already_fresh")}
        open_ = sorted(i.signature for i in s.scalars(select(Incident).where(
            Incident.resolved == False)))  # noqa: E712
    report = {}
    for k in sorted(requested):
        inputs = rows.get(k, {})
        vs_current = {ref: (fp, current.get(ref)) for ref, fp in inputs.items()
                      if current.get(ref) != fp}
        vs_request = {ref: (inputs.get(ref), want.get("new"))
                      for ref, want in requested[k].items()
                      if isinstance(want, dict) and want.get("new") and ref in inputs
                      and inputs.get(ref) != want.get("new")}
        report[k] = {"state": getattr(verdicts.get(k), "state", "no row"),
                     "differs_from_sentinel": vs_current,
                     "differs_from_request": vs_request,
                     "completed": k in completed, "unbound": k in unbound}
    return report, rows, open_


def test_h2_rebuild_reproduces_the_fingerprint_the_sentinel_expects():
    db = _build()
    with db.session() as s:
        built = _rows(s)
    assert built, "the chain recorded no provenance for the product"
    classes = sorted({k.split(":", 1)[0] for k in built})
    print("  built classes:", classes, "rows:", len(built))

    with _MovedChain("-h2a"):
        first = _rebuild_and_verify(db, "a")
        assert first.get("stale"), f"moving chain:release made nothing stale: {first}"
        report, rows_a, open_ = _compare(db)
    assert report, "the sentinel requested no rebuild"
    for k, r in report.items():
        print("  ", json.dumps({k: r}, default=str)[:400])

    never_equal = {k: r for k, r in report.items()
                   if r["differs_from_sentinel"] or r["differs_from_request"]}
    still_stale = {k: r["state"] for k, r in report.items() if r["state"] == A.STALE}
    not_done = [k for k, r in report.items() if not r["completed"]]
    print("  rows whose fingerprint != sentinel/request after rebuild:", sorted(never_equal))
    print("  still stale:", still_stale)
    print("  requested but not completed:", not_done)
    print("  open incidents:", open_)
    # H2's claim, refuted or proved here: a rebuilt row's every recorded ref equals both the
    # sentinel's current fingerprint and the fingerprint the rebuild request named.
    assert not never_equal, f"H2 PROVED: rebuild output never matches: {never_equal}"
    assert not still_stale, f"artefacts still stale after the rebuild: {still_stale}"
    assert not not_done, f"rebuilt rows never bound as completed: {not_done}"
    assert not [x for x in open_ if x.startswith(("stale-artefact:", "rebuild-incomplete:"))
                ], open_

    # Determinism: a second, independent change rebuilds the same rows; the fingerprints
    # each row records are exactly the published current ones again (no time / random /
    # ordering component survives into a recorded input).
    with _MovedChain("-h2b"):
        _rebuild_and_verify(db, "b")
        report_b, rows_b, open_b = _compare(db)
        with db.session() as s:
            current_b = A.current_from_db(s)
    moved = [k for k in rows_a if k in rows_b and rows_a[k] != rows_b[k]]
    assert moved, "the second chain move rebuilt nothing, so determinism was not exercised"
    for k in moved:
        diff = {ref for ref in set(rows_a[k]) | set(rows_b[k])
                if rows_a[k].get(ref) != rows_b[k].get(ref)}
        assert diff <= {"chain:release"}, (k, diff, rows_a[k], rows_b[k])
        assert rows_b[k]["chain:release"] == current_b["chain:release"], k
    assert set(rows_a) == set(rows_b), sorted(set(rows_a) ^ set(rows_b))
    assert not [x for x in open_b if x.startswith(("stale-artefact:",
                                                   "rebuild-incomplete:"))], open_b
    print("  determinism: second rebuild moved only chain:release on", len(moved), "rows")


def test_h2_a_rebuild_request_from_a_sentinel_restart_binds_with_no_fingerprints():
    """The restart paths (legacy / hold-released) enqueue `fingerprints: {}`: the verify
    binding must then reduce to the job binding, not compare against an absent expectation."""
    db = _build()
    with db.session() as s:
        rows = _rows(s)
    node = next(k for k in rows if k.startswith("marketing_asset:"))
    job = JobQueue(db).enqueue("listing", "chain.rebuild",
                               {"product_slug": SLUG, "artefacts": [node], "fingerprints": {},
                                "reason": "h2 restart shape"}, priority=0,
                               idempotency_key="h2-restart")
    Worker(db, "h2-restart", phase=Phase.SHADOW, job_types=["chain.rebuild"]).run_once()
    with db.session() as s:
        out = dict(s.get(Job, job.id).outputs or {})
    assert out.get("already_fresh") == [node], out
    assert out.get("fresh_but_unbound") == [], out


if __name__ == "__main__":
    fails = 0
    for name in [n for n in list(globals()) if n.startswith("test_")]:
        try:
            globals()[name]()
            print(f"OK   {name}")
        except Exception as e:  # noqa: BLE001
            import traceback

            traceback.print_exc()
            fails += 1
            print(f"FAIL {name}", repr(e)[:2000])
    print(f"{fails} failure(s)")
    sys.exit(1 if fails else 0)
