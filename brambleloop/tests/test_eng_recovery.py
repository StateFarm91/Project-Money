"""ENG-RECOVERY (P0, production 8bc96eef read 2026-11-19T15:03Z): the factory makes nothing.

OFFLINE TEST -- NOT PRODUCTION EVIDENCE. No network, no spend, no Etsy write.

Each production state is reproduced as a fixture:

A. Thrash-breaker re-arm. 19 job types were parked by the breaker, most of them backoffs at
   the 32x cap (chain.rebuild, chain.successors) recorded under older releases. A backoff never
   lifted on a code change, so a fixed and redeployed loop stayed parked. Now a suspended
   NON-SPENDING loop gets exactly one probe run per new release (a new boot record for a new
   commit, or a changed handler digest); a spending loop keeps the breaker unless its gate
   changed; an unknown release grants nothing.
B. Policy hold #39 (listing_image_rules). An unreviewed publication-side change held every
   daily rebuild retry ("retry_held 16"). Internal rebuild now proceeds; publication stays
   held; a change governing product creation still holds the rebuild.
C. original_product resuming from `selection_all_drafted` with an undrafted pool is in
   tests/test_w5_a7_supply_stall.py (real radar.scan/radar.score handlers); a fixture of the
   production numbers is repeated here at the selection level.

Run: cd brambleloop && python3 tests/test_eng_recovery.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702 - per-process temp sandbox, removed at exit
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

for _k in ("ETSY_API_KEY", "ETSY_SHARED_SECRET", "ANTHROPIC_API_KEY", "RAILWAY_GIT_COMMIT_SHA",
           "BRAMBLELOOP_COMMIT", "GIT_COMMIT_SHA", "SOURCE_COMMIT"):
    os.environ.pop(_k, None)

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog, CostEntry, Incident, Job, JobStatus  # noqa: E402
from brambleloop.gates import platform_policy  # noqa: E402
from brambleloop.ops import rebuild_graph  # noqa: E402
from brambleloop.publish import release_gates  # noqa: E402
from brambleloop.runtime import pipeline, release  # noqa: E402,F401 - registers handlers
from brambleloop.runtime.worker import CADENCES, Scheduler  # noqa: E402
from brambleloop.swarm import orchestrate as orc  # noqa: E402

OLD = "f34c25ae" + "0" * 32
NEW = "8bc96eef" + "1" * 32
NOW = datetime(2026, 11, 19, 15, 3, tzinfo=timezone.utc)
PERIOD = {jt: p for _n, _a, jt, p in CADENCES}


def _db():
    db = Database(f"sqlite:///{tempfile.mkdtemp(prefix='engrec-')}/r.db")
    db.create_all()
    Registry(db).seed_defaults()
    return db


class _Release:
    """The running build's commit, as Railway sets it."""

    def __init__(self, sha):
        self.sha = sha

    def __enter__(self):
        if self.sha is None:
            os.environ.pop("RAILWAY_GIT_COMMIT_SHA", None)
        else:
            os.environ["RAILWAY_GIT_COMMIT_SHA"] = self.sha
        return self

    def __exit__(self, *a):
        os.environ.pop("RAILWAY_GIT_COMMIT_SHA", None)


def _boot(db, sha, at):
    with db.session() as s:
        s.add(AuditLog(actor="release_guard", action="release.boot_verdict", at=at,
                       detail={"ok": True, "running_commit": sha}))


def _backoff(db, jt, *, commit=OLD, since=None, until=None, digest=None, level=5,
             kind=orc.BACKOFF):
    since = since or (NOW - timedelta(days=3))
    until = until or (NOW + timedelta(hours=31))
    sus = {"kind": kind, "job_type": jt, "level": level, "factor": 32,
           "suspend_until": until.isoformat(), "code_commit": commit, "since": since.isoformat()}
    if digest is not None:
        sus["handler_digest"] = digest
    sig = (f"{orc.BACKOFF_SIGNATURE_PREFIX}{jt}" if kind == orc.BACKOFF
           else f"{orc.THRASH_SIGNATURE_PREFIX}{jt}:fixture")
    with db.session() as s:
        s.add(Incident(severity="P3", signature=sig, summary="fixture backoff",
                       halts_publication=False, at=since, detail={"suspension": sus}))


def _jobs(db, jt):
    with db.session() as s:
        return [(j.id, j.created_at) for j in s.scalars(
            select(Job).where(Job.job_type == jt).order_by(Job.id))]


# --- A. the thrash-breaker re-arm ----------------------------------------------------------

def test_a_suspended_free_loop_rearms_once_after_a_release_change():
    db = _db()
    _backoff(db, "chain.rebuild")
    _backoff(db, "chain.successors")
    with _Release(OLD):
        assert "chain.rebuild" in orc.suspended_job_types(db, now=NOW)      # same release
    with _Release(NEW):
        # a new commit with no boot record yet: nothing proves when it started -- no probe
        assert "chain.rebuild" in orc.suspended_job_types(db, now=NOW)
        _boot(db, NEW, NOW - timedelta(minutes=10))
        held = orc.suspended_job_types(db, now=NOW)
        assert "chain.rebuild" not in held and "chain.successors" not in held, held
        rearmed = {r["job_type"] for r in orc.rearmed_job_types(db)}
        assert {"chain.rebuild", "chain.successors"} <= rearmed, rearmed
        # the scheduler enqueues exactly one probe ...
        Scheduler(db).tick(now=NOW)
        assert len(_jobs(db, "chain.rebuild")) == 1
        # ... and no second one, in this window or any later window of the same release
        for h in (1, 2, 5):
            later = NOW + timedelta(hours=h)
            assert "chain.rebuild" in orc.suspended_job_types(db, now=later)
            Scheduler(db).tick(now=later)
        assert len(_jobs(db, "chain.rebuild")) == 1
        # a second boot of the same release (a restart) is not a new release
        _boot(db, NEW, NOW + timedelta(hours=6))
        assert "chain.rebuild" in orc.suspended_job_types(db, now=NOW + timedelta(hours=7))
    # the next release gets its own single probe
    third = "a35ad302" + "2" * 32
    with _Release(third):
        _boot(db, third, NOW + timedelta(hours=8))
        assert "chain.rebuild" not in orc.suspended_job_types(db, now=NOW + timedelta(hours=9))


def test_the_probe_is_judged_by_the_next_sweep_and_an_unchanged_result_reparks_it():
    db = _db()
    _backoff(db, "chain.successors")
    with _Release(NEW):
        _boot(db, NEW, NOW - timedelta(minutes=10))
        assert "chain.successors" not in orc.suspended_job_types(db, now=NOW)
        # the probe ran and observed the same state; the sweep records it under NEW
        with db.session() as s:
            row = s.scalar(select(Incident).where(
                Incident.signature == f"{orc.BACKOFF_SIGNATURE_PREFIX}chain.successors"))
            sus = dict(row.detail["suspension"])
            sus.update(code_commit=NEW, since=(NOW + timedelta(minutes=30)).isoformat(),
                       level=6, suspend_until=(NOW + timedelta(hours=32)).isoformat())
            row.detail = {"suspension": sus}
        assert "chain.successors" in orc.suspended_job_types(db, now=NOW + timedelta(hours=1))
        assert orc.rearmed_job_types(db) == []


def test_a_spending_loop_does_not_rearm_on_a_release_change():
    db = _db()
    for jt in ("creative.model_tournament", "assets.owned_photography", "marketing.ads_readiness",
               "intel.gallery_analysis", "visual.rnd.cycle"):
        _backoff(db, jt)
    # a job type that is not in any paid family but has spent: spending by evidence
    _backoff(db, "listing.package")
    with db.session() as s:
        j = Job(agent="listing", job_type="listing.package", inputs={}, status=JobStatus.DONE,
                cost_cad=0.0)
        s.add(j)
        s.flush()
        s.add(CostEntry(agent="listing", job_id=j.id, amount_cad=0.02))
    with _Release(NEW):
        _boot(db, NEW, NOW - timedelta(minutes=10))
        held = orc.suspended_job_types(db, now=NOW)
        for jt in ("creative.model_tournament", "assets.owned_photography",
                   "marketing.ads_readiness", "intel.gallery_analysis", "visual.rnd.cycle",
                   "listing.package"):
            assert jt in held, (jt, held)
        assert orc.rearmed_job_types(db) == []


def test_a_breaker_suspension_of_a_free_loop_rearms_once_and_a_paid_one_does_not():
    db = _db()
    # modern suspensions carry the handler digest (unchanged here): only the release moved
    _backoff(db, "ops.policy_watch", kind=orc.SUSPENDED,
             digest=orc.handler_digest("ops.policy_watch"))
    _backoff(db, "creative.candidates_file", kind=orc.SUSPENDED,
             digest=orc.handler_digest("creative.candidates_file"))
    assert orc.handler_digest("ops.policy_watch") and orc.handler_digest("creative.candidates_file")
    with _Release(NEW):
        assert "ops.policy_watch" in orc.suspended_job_types(db, now=NOW)   # no boot record
        _boot(db, NEW, NOW - timedelta(minutes=10))
        held = orc.suspended_job_types(db, now=NOW)
        assert "ops.policy_watch" not in held and "creative.candidates_file" in held, held


def test_an_unknown_release_never_rearms():
    db = _db()
    _backoff(db, "chain.rebuild")
    _boot(db, "unknown", NOW - timedelta(minutes=10))
    with _Release(None):
        assert "chain.rebuild" in orc.suspended_job_types(db, now=NOW)
    db2 = _db()
    _backoff(db2, "chain.rebuild", commit="unknown")
    with _Release(NEW):
        _boot(db2, NEW, NOW - timedelta(minutes=10))
        assert "chain.rebuild" in orc.suspended_job_types(db2, now=NOW)


def test_rearm_probe_itself_refuses_an_unknown_running_commit():
    """Defence in depth: even if a boot time were found, an unknown running build is no
    evidence of a release change (UNKNOWN is never PASS)."""
    db = _db()
    _backoff(db, "chain.rebuild")
    real = orc.release_booted_at
    orc.release_booted_at = lambda session, commit=None: NOW - timedelta(minutes=10)
    try:
        with _Release(None):
            assert "chain.rebuild" in orc.suspended_job_types(db, now=NOW)
    finally:
        orc.release_booted_at = real


def test_a_changed_handler_digest_is_a_recorded_hypothesis_change():
    db = _db()
    # recorded under this very release but with another handler source: the hypothesis moved
    with _Release(NEW):
        _boot(db, NEW, NOW - timedelta(hours=2))
        _backoff(db, "chain.successors", commit=NEW, since=NOW - timedelta(days=1),
                 digest="0" * 16)
        assert "chain.successors" not in orc.suspended_job_types(db, now=NOW)
        # the same digest as the running handler: nothing changed, it stays parked
        db2 = _db()
        _boot(db2, NEW, NOW - timedelta(hours=2))
        _backoff(db2, "chain.successors", commit=NEW, since=NOW - timedelta(days=1),
                 digest=orc.handler_digest("chain.successors"))
        assert "chain.successors" in orc.suspended_job_types(db2, now=NOW)


def test_a_suspension_recorded_after_this_release_booted_gets_no_probe():
    db = _db()
    with _Release(NEW):
        _boot(db, NEW, NOW - timedelta(hours=2))
        _backoff(db, "chain.successors", commit=OLD, since=NOW - timedelta(hours=1),
                 digest="0" * 16)
        assert "chain.successors" in orc.suspended_job_types(db, now=NOW)


def test_the_sweep_records_the_handler_digest_on_a_backoff_and_reports_rearmed():
    db = _db()
    _backoff(db, "chain.rebuild")
    with _Release(NEW):
        _boot(db, NEW, NOW - timedelta(minutes=10))
        out = orc.thrash_sweep(db, now=NOW)
        assert any(r["job_type"] == "chain.rebuild" for r in out["rearmed"]), out["rearmed"]
        assert "chain.rebuild" not in out["suspended"]


def test_spending_classifier_is_conservative():
    db = _db()
    with db.session() as s:
        assert orc.spending_job_type(s, "creative.model_tournament")
        assert orc.spending_job_type(s, "assets.model_photography")
        assert orc.spending_job_type(s, "culture.sweep")
        assert orc.spending_job_type(s, "")
        assert not orc.spending_job_type(s, "chain.rebuild")
        assert not orc.spending_job_type(s, "plan.cycle")
        s.add(Job(agent="x", job_type="improve.monitor", inputs={}, status=JobStatus.DONE,
                  cost_cad=0.01))
        s.flush()
        assert orc.spending_job_type(s, "improve.monitor")


# --- B. policy hold #39: internal rebuild proceeds, publication stays held -----------------

IMAGE_RULES = {"source": "listing_image_rules", "snapshot_id": 39, "checked_on": "2026-10-11",
               "version": "v2", "affects": ["creative_assets", "publishing"]}
CHILDREN = {"source": "children_and_baby", "snapshot_id": 40, "checked_on": "2026-10-11",
            "version": "v2", "affects": ["publishing", "product_creation"]}


class _Policy:
    def __init__(self, *changes):
        self.changes = list(changes)

    def __enter__(self):
        self.real = platform_policy.unreviewed_changes
        platform_policy.unreviewed_changes = lambda db: list(self.changes)
        return self

    def __exit__(self, *a):
        platform_policy.unreviewed_changes = self.real


def test_a_publication_side_policy_change_does_not_hold_the_internal_rebuild():
    db = _db()
    with _Policy(IMAGE_RULES):
        assert release_gates.retry_hold_reason(db, slug="hexie-coaster-set") is None
        gate = release_gates.staleness(db, slug="hexie-coaster-set")
        # publication still refuses on it, by name
        assert gate["blocks"] is True and gate["policy_changes_unreviewed"] == [
            "listing_image_rules"]
        assert any("listing_image_rules" in r for r in gate["reasons"]), gate["reasons"]
        assert gate["policy_publication_only"] == ["listing_image_rules"]


def test_a_product_creation_policy_change_still_holds_the_rebuild():
    db = _db()
    with _Policy(IMAGE_RULES, CHILDREN):
        why = release_gates.retry_hold_reason(db, slug="hexie-coaster-set")
        assert why and "children_and_baby" in why and "listing_image_rules" not in why, why
        gate = release_gates.staleness(db, slug="hexie-coaster-set")
        assert gate["policy_publication_only"] == ["listing_image_rules"]


def _plan(db, changed, expected=None):
    return {"rebuild": [{"key": "pdf:hexie-coaster-set@1#pdf", "product_slug": "hexie-coaster-set",
                         "artefact_class": "pdf", "artefact_key": "hexie-coaster-set@1#pdf",
                         "refs": ["cir:hexie-coaster-set"]}],
            "changed": sorted(changed)}


def test_the_daily_retry_runs_under_a_pending_image_rule_review():
    """The production state: 16 retries held on listing_image_rules. Under the pending review
    the retry is enqueued; publication for the same product still refuses."""
    from brambleloop.queue.durable import JobQueue

    db = _db()
    q = JobQueue(db)
    real = rebuild_graph.rebuild_set
    rebuild_graph.rebuild_set = _plan
    try:
        with _Policy(IMAGE_RULES):
            def go(now):
                with db.session() as s:
                    return rebuild_graph.enqueue(
                        s, q, changed={"cir:hexie-coaster-set": "f" * 16}, reason="t",
                        per="product", now=now,
                        hold=lambda slug: release_gates.retry_hold_reason(db, slug=slug))

            assert go(NOW)["enqueued"]
            with db.session() as s:
                j = s.scalar(select(Job).where(Job.job_type == "chain.rebuild"))
                j.status, j.finished_at = JobStatus.DONE, NOW
            out = go(NOW + timedelta(days=1, hours=1))
            assert out["retried"] == ["hexie-coaster-set"] and not out["retry_held"], out
            assert release_gates.staleness(db, slug="hexie-coaster-set")["blocks"] is True
    finally:
        rebuild_graph.rebuild_set = real


def test_the_policy_card_names_the_owner_action_and_the_scope():
    from brambleloop.app.command_center import approvals

    src = Path(approvals.__file__).read_text()
    assert "publication stays held until you review it" in src
    assert approvals.POLICY_REVIEW_CONFIRMATION == "reviewed and tested"


# --- D. the legacy rebuild-incomplete rows (slice 2) -----------------------------------------

def test_a_legacy_row_with_nothing_stale_gets_exactly_one_targeted_rebuild():
    """Production: 14 rows in `rebuild_incomplete_legacy_budget_pending`. A pre-branch row whose
    product reads nothing STALE is never reached by the propagation (it enqueues only for moved
    refs), so it could neither restate onto the bounded budget nor close. It now gets one
    targeted rebuild of its named keys, once per row; nothing is closed without evidence."""
    import test_eng_stale_rebuild_loop as base

    from brambleloop.core.models import Product
    from brambleloop.ops import artefacts as A

    fp = {"chain:release": {"old": "0" * 16, "new": "1" * 16}}
    db = base._db()
    with db.session() as s:
        for slug in ("hexie-coaster-set", "spooky-garland", "pet-snuggle-mat"):
            s.add(Product(slug=slug, title=slug))
        s.flush()
        # legacy, nothing stale: its named PDF has no provenance row; its chart reads fresh
        s.add(Incident(severity="P2", signature="rebuild-incomplete:hexie-coaster-set",
                       product_slug=None, halts_publication=True, report_count=6,
                       summary="legacy", detail={"stale": ["pdf:hexie-coaster-set@1.0.0#pdf-us"],
                                                 "reason": "t", "fingerprints": fp}))
        A.record(s, artefact_class="chart", artefact_key="hexie-coaster-set@1.0.0#chart",
                 product_slug="hexie-coaster-set",
                 inputs={"chain:release": A.chain_fingerprint()})
        # already under the new budget: the bounded retry owns it, no restart here
        s.add(Incident(severity="P2", signature="rebuild-incomplete:spooky-garland",
                       product_slug="spooky-garland", halts_publication=True, report_count=1,
                       summary="new", detail={"stale": ["pdf:spooky-garland@1.0.0#pdf-us"],
                                              "reason": "t", "fingerprints": fp, "attempts": 1}))
        # legacy but its product reads STALE: the propagation reaches it, no restart here
        s.add(Incident(severity="P2", signature="rebuild-incomplete:pet-snuggle-mat",
                       product_slug=None, halts_publication=True, report_count=3,
                       summary="legacy", detail={"stale": ["chart:pet-snuggle-mat@1.0.0#chart"],
                                                 "reason": "t", "fingerprints": fp}))
        A.record(s, artefact_class="chart", artefact_key="pet-snuggle-mat@1.0.0#chart",
                 product_slug="pet-snuggle-mat", inputs={"chain:release": "0" * 16})
    with _Policy():
        out = base._sentinel(db, "legacy-1")
        assert out["rebuild_incomplete_legacy_restarted"] == ["hexie-coaster-set"], out
        again = base._sentinel(db, "legacy-2")
        assert again["rebuild_incomplete_legacy_restarted"] == [], again
    with db.session() as s:
        jobs = [j for j in s.scalars(select(Job).where(Job.job_type == "chain.rebuild"))
                if (j.idempotency_key or "").startswith("rebuild:legacy-restart:")]
        assert len(jobs) == 1 and jobs[0].inputs["artefacts"] == [
            "pdf:hexie-coaster-set@1.0.0#pdf-us"], [(j.idempotency_key, j.inputs) for j in jobs]
        rows = {r.signature: r for r in s.scalars(select(Incident).where(
            Incident.signature.like("rebuild-incomplete:%")))}
        assert not any(r.resolved for r in rows.values())            # nothing closed
        assert all(r.halts_publication for r in rows.values())        # no halt lifted


# --- C. original_product: selection from the undrafted pool ------------------------------

def test_selection_from_the_production_supply_state_reaches_undrafted_concepts():
    """pool 34, drafted 16, the old selection all drafted: the scan's selection is now taken
    from the undrafted concepts (the handler-level proof is in test_w5_a7_supply_stall)."""
    from datetime import date

    from brambleloop.radar.intake import pool_with_intake
    from brambleloop.radar.opportunity import score_pool, select_portfolio

    db = _db()
    today = date(2026, 11, 19)
    scored = score_pool(pool_with_intake(db), today=today)
    old = select_portfolio(scored, target=10, today=today)
    drafted = {c.slug for c in old.selected}
    undrafted = [c for c in scored if c.slug not in drafted]
    assert undrafted
    new = select_portfolio(undrafted, target=10, today=today)
    assert new.selected and not {c.slug for c in new.selected} & drafted


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                fails += 1
                print("FAIL", name, repr(e))
                traceback.print_exc()
    print(f"{fails} failed")
    sys.exit(1 if fails else 0)
