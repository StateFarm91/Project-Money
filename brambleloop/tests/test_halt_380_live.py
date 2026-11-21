"""eng/halt-380-live: why no rebuild attempt ran on 01ab8df3, and the fix.

Production 01ab8df3, 15:01Z: 12 rebuild-incomplete, rebuilds_verified_24h 0, unfinished 0,
last propagation enqueued 0 and retry_waiting 18, while the sentinel ran at 14:57Z on the new
code. The 2026-11-21 sequence, replayed here on the real chain (production's 12-product
marketing shape from test_halt_380_marketing):

1. the chain moves (19b): the sentinel enqueues every product's first attempt, which ends
   unverified on that code;
2. 19h4 deploys: RETRY_AFTER is counted from the deploy, so its sentinel retries every
   product, under the DAILY retry key; that retry runs on pre-marketing code and ends
   unverified (rebuild-incomplete, 2 attempts);
3. 01ab8df3 (eng/halt-380-marketing) deploys the same UTC day: its sentinel finds the
   window reopened, computes the same daily retry key, hits DuplicateJob, and reports the
   product `retry_waiting`. Nothing is enqueued, nothing is unfinished, and no attempt ever
   reaches the fixed marketing.schedule.

On base, step 3 enqueues nothing for any of the twelve. With the fix (`rebuild_graph.
retry_stamp`: the retry key carries the commit when that deploy reopened the window) each
product gets its one retry on the new code; the real chain then verifies every product except
the one whose published piece correctly keeps it held, and the systemic halt resolves.

Run: cd brambleloop && python3 tests/test_halt_380_live.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import test_eng_stale_rebuild_loop as base  # noqa: E402
import test_halt_380_marketing as M  # noqa: E402
from sqlalchemy import select  # noqa: E402

from brambleloop.core import build  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog, Incident, Job, JobStatus, utcnow  # noqa: E402
from brambleloop.ops import incident_lifecycle as L  # noqa: E402
from brambleloop.ops import production_evidence as pe  # noqa: E402
from brambleloop.ops import rebuild_graph as G  # noqa: E402


def _boot(db, commit, at):
    with db.session() as s:
        s.add(AuditLog(at=at, actor="orchestrator", action="runtime.started",
                       detail={"commit": commit}))


def _end_targeted_rebuilds(db, at):
    """Every targeted chain.rebuild in flight ran on the older code and ended (unverified)."""
    with db.session() as s:
        for j in s.scalars(select(Job).where(Job.job_type == "chain.rebuild",
                                             Job.status == JobStatus.PENDING)):
            j.status, j.finished_at = JobStatus.DONE, at


class _Running:
    def __init__(self, commit):
        self.commit = commit

    def __enter__(self):
        self.real = build.identity
        build.identity = lambda: {"commit": self.commit}

    def __exit__(self, *exc):
        build.identity = self.real


def test_retry_stamp_is_per_deploy_only_when_the_deploy_reopened_the_window():
    db = Database(f"sqlite:///{tempfile.mkdtemp()}/k.db")
    db.create_all()
    now = datetime(2026, 11, 21, 14, 57, tzinfo=timezone.utc)
    with db.session() as s:
        with _Running("dev"):
            assert G.retry_stamp(s, now) == "2026-11-21"           # no deploy identity
        with _Running("17f17c200593d0f044f2"):
            assert G.retry_stamp(s, now) == "2026-11-21"           # never booted
    _boot(db, "aaaaaaaaaaaa0000", now - timedelta(hours=13))         # older than RETRY_AFTER
    _boot(db, "17f17c200593d0f044f2", now - timedelta(hours=2, minutes=36))
    _boot(db, "01ab8df3ffff0000", now - timedelta(minutes=12))
    _boot(db, "17f17c200593d0f044f2", now - timedelta(minutes=5))    # a restart: first boot counts
    with db.session() as s:
        with _Running("aaaaaaaaaaaa0000"):
            assert G.retry_stamp(s, now) == "2026-11-21"
        with _Running("17f17c200593d0f044f2"):
            a = G.retry_stamp(s, now)
        with _Running("01ab8df3ffff0000"):
            b = G.retry_stamp(s, now)
            assert G.retry_stamp(s, now + timedelta(minutes=50)) == b   # idempotent per deploy
            # the key of each deploy's retry is its own; the date still leads
            k1 = G._retry_key(s, "x", "rebuild:product:x:k", now=now, recent=set(), stamp=a)
            k2 = G._retry_key(s, "x", "rebuild:product:x:k", now=now, recent=set())
            assert G._retry_key(s, "x", "k", now=now, recent={"x"}) is None
    assert a == "2026-11-21:17f17c200593" and b == "2026-11-21:01ab8df3ffff", (a, b)
    assert k1 != k2 and k2.endswith(":retry:2026-11-21:01ab8df3ffff"), (k1, k2)
    assert len(k1) <= G.IDEMPOTENCY_KEY_MAX


def test_production_sequence_a_second_deploy_the_same_day_retries_and_converges():
    restore = base._no_policy()
    try:
        _run()
    finally:
        restore()


def _run():
    db, slugs = M._build_catalogue()
    now = utcnow()
    with base._MovedChain():
        plan = M._production_shape(db, slugs)
        owner = slugs[0]

        # 1. the chain moves: first attempts, ended unverified on that code
        _boot(db, "c9e8549f3592cf9c", now - timedelta(hours=13))
        with _Running("c9e8549f3592cf9c"):
            first = base._sentinel(db, "live-1")
        assert first["rebuild_enqueued"], first
        _end_targeted_rebuilds(db, now - timedelta(hours=12, minutes=30))

        # 2. 19h4 deploys; its sentinel retries every product under that day's retry key; the
        #    retry runs on pre-marketing code and ends unverified: rebuild-incomplete, 2 tries
        _boot(db, "17f17c200593d0f0", now - timedelta(hours=2, minutes=36))
        with _Running("17f17c200593d0f0"):
            second = base._sentinel(db, "live-2")
        assert set(slugs) <= set(second["rebuild_retried"]), second
        with db.session() as s:
            retries = {(j.inputs or {}).get("product_slug"): dict(j.inputs or {})
                       for j in s.scalars(select(Job).where(
                           Job.job_type == "chain.rebuild", Job.status == JobStatus.PENDING))
                       if (j.inputs or {}).get("retry")}
            for slug in slugs:
                s.add(Incident(severity="P2", signature=f"rebuild-incomplete:{slug}",
                               product_slug=slug, halts_publication=True, report_count=2,
                               summary=f"artefacts of {slug} still stale after 3 checks",
                               detail={"stale": retries[slug]["artefacts"][:50],
                                       "fingerprints": retries[slug]["fingerprints"],
                                       "attempts": 2, "max_attempts": G.REBUILD_MAX_ATTEMPTS,
                                       "reason": "chain moved", "refused_by": []}))
        _end_targeted_rebuilds(db, now - timedelta(hours=1))
        with db.session() as s:
            assert L.escalate_systemic(s)["systemic"]

        # 3. 01ab8df3 deploys the same UTC day; its sentinel (14:57Z) must retry on new code
        _boot(db, "01ab8df3e5d1c0a9", now - timedelta(minutes=12))
        with _Running("01ab8df3e5d1c0a9"):
            third = base._sentinel(db, "live-3")
            # base: enqueued [] / retried [] / retry_waiting == all twelve, as production read
            assert set(slugs) <= set(third["rebuild_retried"]), (
                third.get("rebuild_retried"), third.get("rebuild_retry_waiting"),
                third.get("rebuild_retry_spent"))
            assert not third["rebuild_retry_spent"], third["rebuild_retry_spent"]
            # inside one deploy the retry stays one: a second sentinel enqueues nothing
            again = base._sentinel(db, "live-3b")
            assert again["rebuild_retried"] == [] and again["rebuild_enqueued"] == [], again
            M._drain_attempt(db)
            out = pe.rebuild_outcomes(db, now=utcnow())

        with db.session() as s:
            open_rows = {i.signature: i for i in s.scalars(select(Incident).where(
                Incident.resolved == False))}  # noqa: E712
            ev = L.escalate_systemic(s)
        # every product but the published-copy owner verified on the new code
        for slug in slugs:
            rec = out["by_product"][slug]
            assert rec["attempt"]["kind"] == "retry", (slug, rec["attempt"])
            assert rec["stage"]["enqueued"] == "pricing.position" and \
                rec["stage"]["status"] == "done", (slug, rec["stage"])
            assert "marketing.schedule:done" in rec["chain"], (slug, rec["chain"])
            assert "marketing.blocked" not in rec["refusals"], (slug, rec["refusals"])
            assert rec["verified_pass_seen"], slug
            want = {"marketing_asset": 1} if slug == owner else {}
            assert rec["by_class"]["outstanding"] == want, (slug, rec["by_class"],
                                                            rec["outstanding_states"])
        incomplete = sorted(k for k in open_rows if k.startswith("rebuild-incomplete:"))
        assert incomplete == [f"rebuild-incomplete:{owner}"], incomplete
        # its third failed attempt at this change holds it, named, on its own public copy
        held = (open_rows[f"rebuild-incomplete:{owner}"].detail or {})
        assert held.get("attempts") == 3 and held.get("held"), held
        assert plan[owner]["published"], plan[owner]
        # one product held by its own published copy is not systemic: the halt resolves
        assert not ev["systemic"] and ev["resolved"], ev


if __name__ == "__main__":
    test_retry_stamp_is_per_deploy_only_when_the_deploy_reopened_the_window()
    print("OK   test_retry_stamp_is_per_deploy_only_when_the_deploy_reopened_the_window")
    test_production_sequence_a_second_deploy_the_same_day_retries_and_converges()
    print("OK   test_production_sequence_a_second_deploy_the_same_day_retries_and_converges")
