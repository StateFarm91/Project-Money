"""W4-INTEG3 (2026-10-12): the production dead letters and the hotfix security-review follow-ups.

Production `/api/verify` (GET, 2026-10-12 18:0xZ, build 7bbbe72) failed only on
`no_unexpected_dead_letters_in_24h`:

* `radar.score` x2 -- `KeyError: 'slug'`. The Intelligence charter consumes CoverageGap rows
  with `radar.score` (`autonomy.charters`), and the orchestrator's handoff mission enqueues it
  with `{"handoff": {...}}` and no concept; Laura's follow-on does the same. The handler read
  `inputs["slug"]` unconditionally.
* `ops.policy_watch` -- `StringDataRightTruncation ... character varying(40)`.
  `policy_knowledge.seed_snapshots` records version `"<read_on>:search_engine_excerpt_of_official_page"`
  (49 characters) into `policy_snapshots.version VARCHAR(40)`. SQLite never enforces it.
* `ops.offsite_archive` -- `EphemeralStorageRefused: BRAMBLELOOP_REQUIRE_POSTGRES=1 ...`. The
  upload and read-back succeeded; the restore proof opened its throwaway SQLite file without
  `scratch=True`, and the hosted guard refuses every SQLite URL under REQUIRE_POSTGRES=1.

Security review of aa1e76d (INDEPENDENT_SECREVIEW_aa1e76d.md): L1 incident grouping by
job type + error class merged different incidents under one headline; L2 the shop resolver
retried on every client build while unbound; I2 a stale `@3` purpose label.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core import migrate, offsite  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (AuditLog, CoverageGap, Incident, Job,  # noqa: E402
                                     JobStatus, PolicySnapshot, Product)
from brambleloop.gates import platform_policy, policy_knowledge  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import pipeline, release  # noqa: E402,F401 - registers handlers
from brambleloop.runtime.worker import Worker  # noqa: E402

_N = [0]


def _db(seed: bool = True) -> Database:
    _N[0] += 1
    db = Database(f"sqlite:///{tempfile.mkdtemp(prefix='integ3-')}/t{_N[0]}.sqlite")
    db.create_all()
    if seed:
        Registry(db).seed_defaults()
    return db


def _run(db, job_type: str) -> Job:
    assert Worker(db, "integ3-w", job_types=[job_type]).run_once()
    with db.session() as s:
        return s.scalars(select(Job).where(Job.job_type == job_type)
                         .order_by(Job.id)).first()


# --- (a) radar.score without a concept --------------------------------------------------


def _gap(db, pod: str, arena: str, state: str = "uncovered") -> int:
    with db.session() as s:
        g = CoverageGap(benchmark_key="b1", arena=arena, pod=pod, state=state, score=0.5)
        s.add(g)
        s.flush()
        return g.id


def test_a_coverage_handoff_radar_score_completes_and_fans_out_per_concept():
    db = _db()
    gid = _gap(db, "stockings", "Christmas stockings")
    _gap(db, "kitchen_bath", "Kitchen & bath")          # no pool concept answers it
    # The exact inputs `orchestrator._enqueue_mission` builds for the handoff candidate.
    JobQueue(db).enqueue("market_radar", "radar.score", {
        "handoff": {"table": "coverage_gaps", "max_id": gid + 1, "rows": 2},
        "source": "autonomy", "department": "intelligence", "mission": "m:1",
        "reason": "2 CoverageGap row(s)", "evidence": []}, idempotency_key="m:1")
    job = _run(db, "radar.score")
    assert job.status == JobStatus.DONE, job.last_error
    assert "KeyError" not in (job.last_error or "")
    out = job.outputs or {}
    assert out["mode"] == "coverage_handoff" and out["promoted"] is False
    assert out["queued"] == ["nordic-forest-stocking"], out
    assert [u["pod"] for u in out["unanswered"]] == ["kitchen_bath"]
    assert out["without_a_pool_concept"] == 1 and out["score"] is None
    with db.session() as s:
        child = s.scalars(select(Job).where(Job.job_type == "radar.score",
                                            Job.id != job.id)).one()
        assert child.inputs["slug"] == "nordic-forest-stocking"
        assert child.inputs["coverage_gaps"] == [gid]
        assert child.idempotency_key.startswith("score:nordic-forest-stocking:")
        assert s.scalars(select(AuditLog).where(
            AuditLog.action == "radar.gap_queue_scored")).first() is not None


def test_a_closed_gap_is_not_scored_and_a_named_product_wins_over_pod_routing():
    """The handoff scores the whole open queue (gaps above its max_id included: the queue,
    not the delta, is what the charter names); a launched gap is closed and skipped; a gap
    that names its product is answered by that concept, not by everything its pod routes."""
    db = _db()
    _gap(db, "hats", "Hats", state="launched")
    gid = _gap(db, "garments", "Garments")
    _gap(db, "bags", "Bags")
    with db.session() as s:
        s.get(CoverageGap, gid).product_slug = "cropped-cardigan"
    JobQueue(db).enqueue("market_radar", "radar.score",
                         {"handoff": {"table": "coverage_gaps", "max_id": gid, "rows": 1}},
                         idempotency_key="m:2")
    job = _run(db, "radar.score")
    assert job.status == JobStatus.DONE, job.last_error
    assert job.outputs["open_gaps"] == 2
    queued = set(job.outputs["queued"])
    assert "cropped-cardigan" in queued and "lattice-triangle-shawl" not in queued
    assert {"nordic-forest-basket", "market-basket-trio"} <= queued
    assert not queued & {"cloudline-baby-hat", "alpine-slouch-beanie"}


def test_a_concept_already_queued_today_is_not_queued_twice():
    db = _db()
    _gap(db, "stockings", "Stockings")
    q = JobQueue(db)
    q.enqueue("market_radar", "radar.score", {"handoff": {}}, idempotency_key="m:3")
    q.enqueue("market_radar", "radar.score", {"handoff": {}}, idempotency_key="m:4")
    first = _run(db, "radar.score")
    assert first.outputs["queued"] == ["nordic-forest-stocking"]
    assert Worker(db, "integ3-w", job_types=["radar.score"]).run_once()
    with db.session() as s:
        second = s.get(Job, first.id + 1)
        assert second.status == JobStatus.DONE, second.last_error
        assert second.outputs["already_queued"] == ["nordic-forest-stocking"]


def test_a_concept_radar_score_is_unchanged():
    """The per-concept path still reads its slug: an unknown concept is still refused."""
    db = _db()
    JobQueue(db).enqueue("market_radar", "radar.score", {"slug": "no-such-concept"},
                         idempotency_key="m:5")
    job = _run(db, "radar.score")
    assert job.status == JobStatus.DONE
    assert job.outputs == {"slug": "no-such-concept", "promoted": False,
                           "reason": "not in the pool"}


# --- (b) ops.policy_watch: policy_snapshots.version -------------------------------------


def test_the_seeded_policy_versions_fit_the_column_and_the_guard_matches_the_model():
    width = PolicySnapshot.__table__.c.version.type.length
    assert width == platform_policy.VERSION_MAX == 120
    longest = max(len(f"{r.read_on}:{r.basis}") for r in policy_knowledge.READINGS.values())
    assert longest > 40, "the production overflow: the seed version exceeded VARCHAR(40)"
    assert longest <= width
    db = _db(seed=False)
    got = policy_knowledge.seed_snapshots(db)
    assert got["seeded"]
    with db.session() as s:
        versions = list(s.scalars(select(PolicySnapshot.version)))
    assert versions and max(map(len, versions)) == longest


def test_an_overlong_policy_version_is_refused_not_truncated():
    db = _db(seed=False)
    source = sorted(platform_policy.POLICY_SOURCES)[0]
    try:
        platform_policy.record_snapshot(db, source, text="policy text " * 20,
                                        version="v" * 121)
    except platform_policy.PolicyRefused as exc:
        assert "121 characters" in str(exc)
    else:
        raise AssertionError("an overlong version was stored (Postgres would dead-letter)")
    with db.session() as s:
        assert s.scalar(select(PolicySnapshot.id)) is None


def test_the_widening_migration_never_narrows_and_skips_sqlite():
    db = _db(seed=False)
    assert migrate.widen_plan(db.engine) == []    # SQLite: VARCHAR length is not enforced


def test_policy_watch_runs_to_done():
    db = _db()
    JobQueue(db).enqueue("orchestrator", "ops.policy_watch", {}, idempotency_key="pw")
    job = _run(db, "ops.policy_watch")
    assert job.status == JobStatus.DONE, job.last_error


# --- (c) ops.offsite_archive under BRAMBLELOOP_REQUIRE_POSTGRES=1 -----------------------


class _Bucket:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put(self, key, payload, *, env=None):
        self.objects[key] = payload
        return {"key": key, "bytes": len(payload), "bucket": "test", "host": "test"}

    def get(self, key, *, env=None):
        return self.objects[key]


CONFIGURED = {
    offsite.ENDPOINT_VAR: "https://s3.example.invalid",
    offsite.BUCKET_VAR: "archive",
    offsite.KEY_ID_VAR: "id",
    offsite.SECRET_VAR: "not-a-secret",
    offsite.ENCRYPTION_KEY_VAR: "a passphrase long enough to be stretched into a key",
    offsite.REGION_VAR: "us-west-004",
}


def test_the_restore_proof_runs_where_postgres_is_required():
    db = _db(seed=False)
    with db.session() as s:
        s.add(Product(slug="test-throw", title="Test throw"))
    bucket = _Bucket()
    old = os.environ.get("BRAMBLELOOP_REQUIRE_POSTGRES")
    os.environ["BRAMBLELOOP_REQUIRE_POSTGRES"] = "1"
    try:
        # The guard is real: an ordinary SQLite database is still refused here.
        try:
            Database(f"sqlite:///{tempfile.mkdtemp()}/x.sqlite")
        except Exception as exc:  # noqa: BLE001
            assert type(exc).__name__ == "EphemeralStorageRefused"
        else:
            raise AssertionError("the hosted guard accepted SQLite under REQUIRE_POSTGRES=1")
        record = offsite.archive(db, env=CONFIGURED, transport=(bucket.put, bucket.get))
    finally:
        if old is None:
            os.environ.pop("BRAMBLELOOP_REQUIRE_POSTGRES", None)
        else:
            os.environ["BRAMBLELOOP_REQUIRE_POSTGRES"] = old
    assert record["ok"] is True, record.get("reason")
    assert record["stage"] == "complete" and record["rows_restored"] > 0


def test_a_configured_archive_failure_opens_one_incident_instead_of_dead_lettering():
    db = _db()
    real_archive, real_configured = offsite.archive, offsite.configured
    offsite.archive = lambda _db, **kw: {"ok": False, "stage": "upload",
                                         "reason": "archive store 403"}
    offsite.configured = lambda *a, **k: True
    try:
        q = JobQueue(db)
        for i in range(2):
            q.enqueue("orchestrator", "ops.offsite_archive", {}, idempotency_key=f"oa{i}")
        for _ in range(2):
            assert Worker(db, "integ3-w", job_types=["ops.offsite_archive"]).run_once()
    finally:
        offsite.archive, offsite.configured = real_archive, real_configured
    with db.session() as s:
        jobs = list(s.scalars(select(Job).where(Job.job_type == "ops.offsite_archive")))
        assert [j.status for j in jobs] == [JobStatus.DONE] * 2, [j.last_error for j in jobs]
        incs = list(s.scalars(select(Incident).where(
            Incident.signature == "offsite_archive_failed")))
        assert len(incs) == 1 and incs[0].report_count == 2 and incs[0].severity == "P1"


# --- (d) security review follow-ups ------------------------------------------------------


def test_l1_different_incidents_sharing_job_type_and_error_class_keep_their_headlines():
    from brambleloop.laura.agency import briefing

    db = _db(seed=False)
    with db.session() as s:
        for sig, summary in (("render_timeout", "render timed out"),
                             ("etsy_read_timeout", "etsy read timed out"),
                             ("etsy_read_timeout", "etsy read timed out again")):
            s.add(Incident(severity="P1", signature=sig, summary=summary,
                           detail={"job_type": "intel.serp_capture",
                                   "error": "TimeoutError: timed out"}))
    got = briefing.incident_groups(db)
    assert got["raw"] == 3
    assert sorted(g["count"] for g in got["groups"]) == [1, 2]
    heads = {str(g["latest"].summary) for g in got["groups"]}
    assert "render timed out" in heads


def test_l2_an_unresolved_shop_binding_backs_off_and_a_success_resets_it():
    import test_w4_etsy_shop_binding as SB
    from brambleloop.integrations import etsy_shop_binding as B

    db = SB._db()
    SB._granted(db)
    calls = []
    real = B.resolve
    B.resolve = lambda *a, **k: calls.append(1) or {"status": "unreadable", "reason": "x"}
    try:
        assert B.ensure_credentials(db, transport=SB.StubEtsy(), env=SB.ENV) is None
        assert B.ensure_credentials(db, transport=SB.StubEtsy(), env=SB.ENV) is None
        assert len(calls) == 1, "the second build retried inside the backoff"
        now = datetime.now(timezone.utc)
        assert 0 < B.backoff_remaining(db, now=now) <= B.BACKOFF_BASE_S
        # After the window the next attempt runs; two failures double the wait, capped.
        assert B.backoff_remaining(db, now=now + timedelta(seconds=B.BACKOFF_BASE_S + 1)) == 0
        with db.session() as s:
            s.add(AuditLog(actor="etsy_shop_binding", action=B.FAILED_ACTION, detail={}))
        assert B.backoff_remaining(db, now=now) > B.BACKOFF_BASE_S
        with db.session() as s:
            for _ in range(14):
                s.add(AuditLog(actor="etsy_shop_binding", action=B.FAILED_ACTION, detail={}))
        assert B.backoff_remaining(db, now=now) <= B.BACKOFF_MAX_S
    finally:
        B.resolve = real
    with db.session() as s:
        s.add(AuditLog(actor="etsy_shop_binding", action=B.RESOLVED_ACTION, detail={}))
    assert B.backoff_remaining(db) == 0


def test_i2_the_registry_names_the_live_briefing_prompt():
    from brambleloop.gateway import laura_briefing

    src = (ROOT / "src/brambleloop/agents/registry.py").read_text()
    assert "laura.ceo_briefing@3" not in src
    assert laura_briefing.PROMPT.ref in src or f"@{laura_briefing.PROMPT.version}" in src


def _run_all() -> int:
    failures = 0
    for name, fn in sorted(globals().items()):
        if not (name.startswith("test_") and callable(fn)):
            continue
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            failures += 1
            import traceback

            traceback.print_exc()
            print(f"FAIL {name}: {type(exc).__name__}: {exc}")
        else:
            print(f"OK   {name}")
    print(f"{failures} failed")
    return failures


if __name__ == "__main__":
    raise SystemExit(1 if _run_all() else 0)
