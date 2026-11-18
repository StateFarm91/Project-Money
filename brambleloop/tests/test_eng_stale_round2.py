"""eng/stale-rebuild-loop round 2: the four MEDIUMs of the independent review of 4b683993.

M-A  An EXISTING rebuild-incomplete row (production's were written with product_slug NULL)
     was invisible to every slug-keyed reader: exhausted, yet retry_hold_reason -> None and
     the daily retry looped. Restating now files the slug, the readers also match on the
     signature, and the sentinel files legacy rows against their product.
M-B  A rebuild that never reached verify (DEAD every day, or refused "no stored release")
     looped daily with no hold and no incident. DEAD/refused attempts at one change now count
     toward REBUILD_MAX_ATTEMPTS and then hold with the named reason on a durable
     rebuild-incomplete row (visible in production_evidence).
M-C  The sentinel closed rebuild-incomplete for any product with no STALE verdict -- a product
     with no provenance rows at all, or artefacts UNPROVEN. It now closes only when every
     artefact the row names reads FRESH or SUPERSEDED.
M-D  model.probe reused an ok probe whatever its model and with no key configured (usable()
     True while key_present False). Reuse is now tied to the probe model and a non-secret
     key fingerprint.
L1   retry_hold_reason and chain.rebuild read one withholding function.

Each test fails on 4b683993. Production-shaped tests also run on a disposable PostgreSQL
cluster when the toolchain exists.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # per-process temp sandbox, removed at exit  # noqa: E702
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import test_eng_stale_rebuild_loop as base  # noqa: E402  (helpers, runner, PG factory)
from sqlalchemy import select  # noqa: E402

from brambleloop.core.models import (Incident, Job, JobStatus, Phase,  # noqa: E402
                                     PatternVersion, Product, utcnow)
from brambleloop.ops import artefacts as A  # noqa: E402
from brambleloop.ops import incident_lifecycle as L  # noqa: E402
from brambleloop.ops import production_evidence as PE  # noqa: E402
from brambleloop.ops import rebuild_graph as G  # noqa: E402
from brambleloop.publish import release_gates  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import release  # noqa: E402
from brambleloop.runtime.worker import Worker  # noqa: E402

FP = {"chain:release": {"old": "0" * 16, "new": "1" * 16}}


def _legacy_row(s, slug, *, count, stale=None):
    """The production shape: written by the pre-branch code, product_slug NULL, no `held`."""
    s.add(Incident(severity="P2", signature=f"rebuild-incomplete:{slug}", product_slug=None,
                   halts_publication=True, report_count=count,
                   summary=f"artefacts of {slug} still carry a moved input",
                   detail={"stale": stale or [f"marketing_asset:{slug}:x"], "reason": "t",
                           "fingerprints": FP}))


def _exhausted_null_slug_row(s, slug, *, stale=None):
    """Round 3 (M-E): a pre-branch row is no longer exhausted by its count -- it gets a fresh
    budget first. M-A's property (slug-keyed readers also match the signature) is pinned on a
    row exhausted under the new budget (`attempts`, `held`) whose product_slug is NULL."""
    s.add(Incident(severity="P1", signature=f"rebuild-incomplete:{slug}", product_slug=None,
                   halts_publication=True, report_count=G.REBUILD_MAX_ATTEMPTS,
                   summary=f"artefacts of {slug} still carry a moved input",
                   detail={"stale": stale or [f"marketing_asset:{slug}:x"], "reason": "t",
                           "fingerprints": FP, "attempts": G.REBUILD_MAX_ATTEMPTS,
                           "held": f"{G.REBUILD_MAX_ATTEMPTS} rebuild attempts at this "
                                   "change left 1 artefact(s) stale"}))


# --- M-A ----------------------------------------------------------------------------------------

def test_ma_legacy_null_slug_exhausted_row_holds_the_retry():
    db = base._db()
    restore = base._no_policy()
    try:
        with db.session() as s:
            s.add(Product(slug="a", title="a"))
            _exhausted_null_slug_row(s, "a")
        why = release_gates.retry_hold_reason(db, slug="a")
        assert why and "could not complete" in why and "rebuild-incomplete:a" in why, why
        # the marketing-rebuild waiver and the systemic evidence see it too
        assert "rebuild-incomplete:a" in release_gates._halting_other_than_staleness(
            db, "a", set()), "an exhausted legacy row must refuse, not be waived"
        with db.session() as s:
            fams = {}
            for r in s.scalars(select(Incident)):
                fams.setdefault(L.kind_of(r.signature), set()).add(
                    release_gates.incident_slug(r))
            assert fams["rebuild-incomplete"] == {"a"}, fams
        ev = PE.stale_rebuilds(db, now=datetime.now(timezone.utc))
        assert ev["rebuild_incomplete_held"] == ["a"], ev
        # a legacy row holds nothing, whatever its count (round 3, M-E: a fresh budget first)
        db2 = base._db()
        with db2.session() as s:
            for slug, n in (("b", 1), ("c", G.REBUILD_MAX_ATTEMPTS), ("d", 6)):
                s.add(Product(slug=slug, title=slug))
                _legacy_row(s, slug, count=n)
        for slug in ("b", "c", "d"):
            assert release_gates.retry_hold_reason(db2, slug=slug) is None, slug
            assert not release_gates._halting_other_than_staleness(db2, slug, set()), slug
    finally:
        restore()


def test_ma_restating_a_legacy_row_files_its_product_slug():
    db = base._db()
    restore = base._no_policy()
    try:
        with db.session() as s:
            s.add(Product(slug="a", title="a"))
            _legacy_row(s, "a", count=1)
        # round 3 (M-E): the first restate starts a fresh budget, so exhausting it takes
        # REBUILD_MAX_ATTEMPTS restates under the new code (was MAX - 1 on top of the legacy 1)
        for _ in range(G.REBUILD_MAX_ATTEMPTS):
            release._rebuild_incomplete(base._Ctx(db), "a", "1.0.0",
                                        stale=["marketing_asset:a:x"], reason="t",
                                        fingerprints=FP, checks=3)
        with db.session() as s:
            row = s.scalar(select(Incident).where(Incident.signature == "rebuild-incomplete:a"))
            assert row.product_slug == "a", row.product_slug
            assert row.report_count == G.REBUILD_MAX_ATTEMPTS and row.detail.get("held")
            assert row.detail["budget_reset"]["legacy_report_count"] == 1, row.detail
        assert release_gates.retry_hold_reason(db, slug="a")
    finally:
        restore()


def test_ma_sentinel_holds_a_legacy_exhausted_product_instead_of_retrying():
    """The production loop end to end through the sentinel: the NULL-slug exhausted product is
    reported held with the named reason, the others are retried. (Round 3: exhausted under
    the new budget; a pre-branch count alone is retried -- see test_me_*.)"""
    db = base._db()
    slugs = base.SLUGS[:3]
    base._production_estate(db, slugs)
    restore = base._no_policy()
    try:
        with base._MovedChain():
            base._sentinel(db, "1")
            base._finish_all_rebuilds(db, at=utcnow() - timedelta(hours=13))
            with db.session() as s:
                _exhausted_null_slug_row(s, slugs[0], stale=[f"pdf:{slugs[0]}@1.0.0#pdf-us"])
            out = base._sentinel(db, "2")
        assert slugs[0] in out["rebuild_retry_held"], out
        assert "could not complete" in out["rebuild_retry_held"][slugs[0]], out
        assert slugs[0] not in out["rebuild_retried"], out
        assert sorted(out["rebuild_retried"]) == sorted(slugs[1:]), out
        with db.session() as s:
            row = s.scalar(select(Incident).where(
                Incident.signature == f"rebuild-incomplete:{slugs[0]}"))
            assert row.product_slug == slugs[0] and not row.resolved   # filed, still open
    finally:
        restore()


# --- M-B ----------------------------------------------------------------------------------------

def _days(db, slugs, *, settle, days=6):
    """Drive the sentinel's enqueue once a day for `days` days; `settle(now)` ends every
    attempt the way production's did. Returns {slug: [days retried]} and the last result."""
    changed = {"chain:release": "9" * 16}
    retried: dict[str, list[int]] = {s_: [] for s_ in slugs}
    t0 = datetime.now(timezone.utc)
    out = None
    for d in range(days):
        now = t0 + timedelta(days=d)
        with db.session() as s:
            out = G.enqueue(s, JobQueue(db), changed=changed, per="product", reason="t",
                            now=now,
                            hold=lambda slug: release_gates.retry_hold_reason(db, slug=slug))
        for slug in out["retried"]:
            retried[slug].append(d)
        settle(now)
    return retried, out


def _estate(db, slugs, *, release_for=()):
    with db.session() as s:
        for slug in slugs:
            p = Product(slug=slug, title=slug)
            s.add(p)
            s.flush()
            if slug in release_for:
                s.add(PatternVersion(product_id=p.id, version="1.0.0", cir_json={"x": 1},
                                     certified=True, release_hash="ab" * 16, certificate={}))
            A.record(s, artefact_class="pdf", artefact_key=f"{slug}@1.0.0#pdf-us",
                     product_slug=slug, inputs={"chain:release": "0" * 16})


def test_mb_dead_rebuilds_are_bounded_then_held_with_the_error_class():
    db = base._db()
    slugs = ["dead-a", "dead-b"]
    _estate(db, slugs, release_for=slugs)
    restore = base._no_policy()

    def die(now):
        with db.session() as s:
            for j in s.scalars(select(Job).where(Job.job_type == "chain.rebuild",
                                                 Job.status == JobStatus.PENDING)):
                j.status, j.finished_at = JobStatus.DEAD, now + timedelta(hours=1)
                j.last_error = "KeyError: 'pdf_sha256'"
    try:
        retried, last = _days(db, slugs, settle=die)
        # attempt 1 on day 0, retries on days 1 and 2, then held -- not retried days 1..5
        for slug in slugs:
            assert retried[slug] == [1, 2], retried
            assert "KeyError" in last["retry_held"][slug], last
            why = release_gates.retry_hold_reason(db, slug=slug)
            assert why and "KeyError" in why, why
        with db.session() as s:
            dead = s.scalars(select(Job).where(Job.status == JobStatus.DEAD)).all()
            assert len(dead) == 2 * G.REBUILD_MAX_ATTEMPTS, len(dead)
            rows = {r.signature: r for r in s.scalars(select(Incident).where(
                Incident.signature.like("rebuild-incomplete:%")))}
        for slug in slugs:
            r = rows[f"rebuild-incomplete:{slug}"]
            assert r.halts_publication and not r.resolved and r.product_slug == slug
            assert "KeyError" in r.detail["held"] and r.detail["stale"] == [
                f"pdf:{slug}@1.0.0#pdf-us"], r.detail
        ev = PE.stale_rebuilds(db, now=datetime.now(timezone.utc))
        assert ev["rebuild_incomplete_held"] == sorted(slugs), ev
        assert all("KeyError" in v for v in ev["rebuild_incomplete_held_reasons"].values()), ev
    finally:
        restore()


def test_mb_refused_no_stored_release_is_bounded_then_held_with_the_refusal():
    db = base._db()
    slugs = ["norel-a"]
    _estate(db, slugs)                      # no PatternVersion: the real rebuild refuses

    def run(now):
        w = Worker(db, "w-refuse", phase=Phase.SHADOW, job_types=["chain.rebuild"])
        for _ in range(10):
            if not w.run_once():
                break
    restore = base._no_policy()
    try:
        retried, last = _days(db, slugs, settle=run)
        assert retried["norel-a"] == [1, 2], retried
        assert "no stored release" in last["retry_held"]["norel-a"], last
        with db.session() as s:
            jobs = s.scalars(select(Job).where(Job.job_type == "chain.rebuild")).all()
            assert len(jobs) == G.REBUILD_MAX_ATTEMPTS, len(jobs)
            assert all((j.outputs or {}).get("refused") for j in jobs)
        why = release_gates.retry_hold_reason(db, slug="norel-a")
        assert why and "no stored release" in why, why
    finally:
        restore()


# --- M-C ----------------------------------------------------------------------------------------

def test_mc_sentinel_does_not_close_without_positive_evidence():
    db = base._db()
    with db.session() as s:
        for slug in ("ghost", "unproven", "fresh"):
            s.add(Product(slug=slug, title=slug))
        s.flush()
        # ghost: no provenance rows at all; unproven: the named artefact has no row
        _exhausted_null_slug_row(s, "ghost", stale=["marketing_asset:ghost:pin:1"])
        _legacy_row(s, "unproven", count=1, stale=["pdf:unproven@1.0.0#pdf-us"])
        A.record(s, artefact_class="chart", artefact_key="unproven@1.0.0#chart",
                 product_slug="unproven", inputs={"chain:release": A.chain_fingerprint()})
        # fresh: the named artefact reads fresh -> closes (the positive case)
        _legacy_row(s, "fresh", count=1, stale=["pdf:fresh@1.0.0#pdf-us"])
        A.record(s, artefact_class="pdf", artefact_key="fresh@1.0.0#pdf-us",
                 product_slug="fresh", inputs={"chain:release": A.chain_fingerprint()})
    out = base._sentinel(db, "mc")
    assert out["rebuild_incomplete_cleared"] == ["rebuild-incomplete:fresh"], out
    assert set(out["rebuild_incomplete_open"]) == {"rebuild-incomplete:ghost",
                                                   "rebuild-incomplete:unproven"}, out
    with db.session() as s:
        rows = {r.signature: r for r in s.scalars(select(Incident).where(
            Incident.signature.like("rebuild-incomplete:%")))}
        assert not rows["rebuild-incomplete:ghost"].resolved
        assert not rows["rebuild-incomplete:unproven"].resolved
        assert rows["rebuild-incomplete:fresh"].resolved
        read = rows["rebuild-incomplete:unproven"].detail["sentinel_read"]["verdicts"]
        assert read == {"pdf:unproven@1.0.0#pdf-us": "no provenance row"} or all(
            not v.startswith("fresh") for v in read.values()), read
        assert rows["rebuild-incomplete:ghost"].product_slug == "ghost"
    # the held ghost still holds
    restore = base._no_policy()
    try:
        assert release_gates.retry_hold_reason(db, slug="ghost")
    finally:
        restore()


# --- M-D ----------------------------------------------------------------------------------------

def _ok_probe_row(db, at, *, model=None, key_fp="__current__"):
    from brambleloop.core.models import AuditLog
    from brambleloop.gateway import anthropic as gw

    record = {"at": at.isoformat(), "model": model or gw.PROBE_MODEL, "ok": True,
              "reason": ""}
    if key_fp is not None:
        record["key_fp"] = gw.key_fingerprint() if key_fp == "__current__" else key_fp
    with db.session() as s:
        s.add(AuditLog(actor="orchestrator", action="model.probe", artifact="x",
                       detail=record))


def test_md_probe_reuse_requires_the_probe_model_and_the_same_key():
    from brambleloop.gateway import anthropic as gw

    t0 = datetime(2026, 11, 18, 0, 5, tzinfo=timezone.utc)
    saved = os.environ.pop("ANTHROPIC_API_KEY", None)
    try:
        # no key configured: a fresh ok probe on file is NOT reused; the real probe (which
        # sends nothing without a key) records NO_KEY_REASON and the gate closes
        db = base._db()
        _ok_probe_row(db, t0, key_fp=None)
        out = gw.probe_if_due(db, now=t0 + timedelta(hours=1))
        assert not out.get("reused") and out["ok"] is False, out
        assert out["reason"] == gw.NO_KEY_REASON, out
        assert gw.usable(db) is False and gw.state(db)["key_present"] is False

        calls: list = []
        restore = base._stub_probe(calls)           # sets a dummy key, stubs the call
        try:
            fp = gw.key_fingerprint()
            assert fp and len(fp) == 8 and os.environ["ANTHROPIC_API_KEY"] not in fp
            # another model's success is not this probe's
            db = base._db()
            _ok_probe_row(db, t0, model="claude-some-other-model")
            gw.probe_if_due(db, now=t0 + timedelta(hours=1))
            assert len(calls) == 1, calls
            # a success made with a different key (or none recorded) is re-asked
            db = base._db()
            _ok_probe_row(db, t0, key_fp="deadbeef")
            gw.probe_if_due(db, now=t0 + timedelta(hours=1))
            db2 = base._db()
            _ok_probe_row(db2, t0, key_fp=None)
            gw.probe_if_due(db2, now=t0 + timedelta(hours=1))
            assert len(calls) == 3, calls
            # same model, same key: reused, CA$0, and the key never appears in the record
            db = base._db()
            _ok_probe_row(db, t0)
            out = gw.probe_if_due(db, now=t0 + timedelta(hours=1))
            assert out["reused"] and len(calls) == 3, out
            assert os.environ["ANTHROPIC_API_KEY"] not in repr(gw.last_probe(db))
            # the key is rotated: the reuse stops
            os.environ["ANTHROPIC_API_KEY"] = "a-different-dummy-key"
            out = gw.probe_if_due(db, now=t0 + timedelta(hours=2))
            assert not out.get("reused") and len(calls) == 4, out
        finally:
            restore()
    finally:
        if saved is not None:
            os.environ["ANTHROPIC_API_KEY"] = saved


def test_md_the_real_probe_records_a_non_secret_key_fingerprint():
    """The record the reuse reads is written by `probe` itself (here with no key: None)."""
    from brambleloop.gateway import anthropic as gw

    saved = os.environ.pop("ANTHROPIC_API_KEY", None)
    try:
        db = base._db()
        rec = gw.probe(db)
        assert "key_fp" in rec and rec["key_fp"] is None and rec["model"] == gw.PROBE_MODEL
        assert gw.key_fingerprint("k") == __import__("hashlib").sha256(b"k").hexdigest()[:8]
    finally:
        if saved is not None:
            os.environ["ANTHROPIC_API_KEY"] = saved


# --- L1 -----------------------------------------------------------------------------------------

def test_l1_hold_and_rebuild_read_the_same_withholding():
    """retry_hold_reason read the stored record (`withholding.reasons`); chain.rebuild reads
    `withholding.current(stage="chain.rebuild")`, which re-reads the owner's ruling. With an
    owner veto ruled and not yet written to the record, the rebuild refused while the hold
    read a clean release and let the daily retry run. Both now read one function."""
    from brambleloop.core.models import OwnerVeto

    db = base._db()
    restore = base._no_policy()
    try:
        with db.session() as s:
            p = Product(slug="a", title="a")
            s.add(p)
            s.flush()
            s.add(PatternVersion(product_id=p.id, version="1.0.0", cir_json={"x": 1},
                                 certified=True, release_hash="ab" * 16, certificate={}))
            s.add(OwnerVeto(subject_ref="product:a", scope="flagship", reason="identity"))
        why = release_gates.retry_hold_reason(db, slug="a")
        assert why and "withheld" in why and "a@1.0.0" in why, why
        version, summary = release_gates.rebuild_withheld(db, "a")
        assert version == "1.0.0" and summary, summary
        # the real rebuild refuses on the same reading
        job = base._run_job(db, "listing", "chain.rebuild",
                            {"product_slug": "a", "artefacts": ["pdf:a@1.0.0#pdf-us"]}, "l1")
        assert job.outputs.get("withheld") is True, job.outputs
    finally:
        restore()


# --- round 3: M-E (review of 0d2e6cbc) ----------------------------------------------------------
#
# A pre-branch rebuild-incomplete row counted every failed daily attempt -- attempts that failed
# only because of the bugs this branch fixes -- so its report_count is not an attempt budget.
# Treating `report_count >= 3` on such a row as exhausted held every long-open product on the
# first sentinel run after the deploy, never retried, never rebuilt: a deadlock. A legacy row
# now gets a fresh, recorded budget on its first restate; after that budget the hold applies.

LEGACY_COUNTS = {"me-one": 1, "me-three": 3, "me-six": 6}


def test_me_legacy_counts_get_a_fresh_recorded_budget_then_hold():
    db = base._db()
    slugs = sorted(LEGACY_COUNTS)
    base._production_estate(db, slugs)
    restore = base._no_policy()
    try:
        with base._MovedChain():
            base._sentinel(db, "me-1")
            base._finish_all_rebuilds(db, at=utcnow() - timedelta(hours=13))
            with db.session() as s:
                for slug, n in LEGACY_COUNTS.items():
                    _legacy_row(s, slug, count=n, stale=[f"pdf:{slug}@1.0.0#pdf-us"])
            # before any restate: no legacy row is a hold, whatever its count
            for slug in slugs:
                assert release_gates.retry_hold_reason(db, slug=slug) is None, slug
            ev = PE.stale_rebuilds(db, now=datetime.now(timezone.utc))
            assert ev["rebuild_incomplete_held"] == [] and ev["rebuild_incomplete_held_count"] == 0
            assert ev["rebuild_incomplete_legacy_budget_pending"] == slugs, ev
            out = base._sentinel(db, "me-2")
            # the probe: legacy counts 1, 3, 6 -> all three retried once under the new code
            assert sorted(out["rebuild_retried"]) == slugs, out
            assert not out["rebuild_retry_held"], out
            # the retried attempts fail verify: each restate under the new code spends the
            # fresh budget; the first one records the legacy count and why it was reset
            for attempt in range(1, G.REBUILD_MAX_ATTEMPTS + 1):
                for slug in slugs:
                    release._rebuild_incomplete(base._Ctx(db), slug, "1.0.0",
                                                stale=[f"pdf:{slug}@1.0.0#pdf-us"],
                                                reason="t", fingerprints=FP, checks=3)
                with db.session() as s:
                    for slug, n in LEGACY_COUNTS.items():
                        row = s.scalar(select(Incident).where(
                            Incident.signature == f"rebuild-incomplete:{slug}"))
                        assert row.report_count == attempt, (slug, row.report_count)
                        reset = row.detail["budget_reset"]
                        assert reset["legacy_report_count"] == n, reset
                        assert "before eng/stale-rebuild-loop" in reset["why"], reset
                        # the history is kept, not erased
                        assert reset["legacy_detail"]["fingerprints"] == FP, reset
                        assert reset["legacy_detail"]["stale"] == [
                            f"pdf:{slug}@1.0.0#pdf-us"], reset
                held = [s_ for s_ in slugs if release_gates.retry_hold_reason(db, slug=s_)]
                if attempt < G.REBUILD_MAX_ATTEMPTS:
                    assert held == [], (attempt, held)   # budget left: retried, not held
                else:
                    assert held == slugs, held           # new budget spent: the named hold
            base._finish_all_rebuilds(db, at=utcnow() - timedelta(hours=13))
            out = base._sentinel(db, "me-3")
        assert sorted(out["rebuild_retry_held"]) == slugs, out
        assert all("could not complete" in v for v in out["rebuild_retry_held"].values()), out
        assert not out["rebuild_retried"], out
        # the remaining holds are visible to the owner: counted, with their reasons
        ev = PE.stale_rebuilds(db, now=datetime.now(timezone.utc))
        assert ev["rebuild_incomplete_held_count"] == 3 and ev["rebuild_incomplete_held"] == slugs
        assert set(ev["rebuild_incomplete_held_reasons"]) == set(slugs), ev
        assert all("rebuild attempts" in v for v in ev["rebuild_incomplete_held_reasons"].values())
        assert ev["rebuild_incomplete_legacy_budget_pending"] == []
        assert ev["rebuild_incomplete_budget_reset"] == {s_: n for s_, n in
                                                         LEGACY_COUNTS.items()}, ev
    finally:
        restore()


def test_me_legacy_dead_jobs_do_not_spend_the_new_budget():
    """The M-B bound has the same hazard: pre-branch DEAD attempts at a change (failed by the
    round-1 bugs) must not hold the product before the new code has tried it."""
    db = base._db()
    slugs = ["legacy-dead"]
    _estate(db, slugs, release_for=slugs)
    changed = {"chain:release": "9" * 16}
    stamp = "-".join(f"{ref}={fp[:8]}" for ref, fp in sorted(changed.items()))
    key = G.job_key("rebuild:product:legacy-dead", stamp)
    t_old = datetime.now(timezone.utc) - timedelta(days=4)
    with db.session() as s:      # the pre-branch payload: no per-product change id
        for i in range(4):
            s.add(Job(agent="listing", job_type="chain.rebuild", status=JobStatus.DEAD,
                      idempotency_key=key if i == 0 else f"{key}:retry:legacy-{i}",
                      inputs={"product_slug": "legacy-dead",
                              "artefacts": ["pdf:legacy-dead@1.0.0#pdf-us"], "reason": "t",
                              **({"retry_of_key": key} if i else {})},
                      last_error="KeyError: 'pdf_sha256'", finished_at=t_old))
    restore = base._no_policy()

    def die(now):
        with db.session() as s:
            for j in s.scalars(select(Job).where(Job.job_type == "chain.rebuild",
                                                 Job.status == JobStatus.PENDING)):
                j.status, j.finished_at = JobStatus.DEAD, now + timedelta(hours=1)
                j.last_error = "KeyError: 'pdf_sha256'"
    try:
        retried, last = _days(db, slugs, settle=die)
        assert retried["legacy-dead"] == [0, 1, 2], retried    # a fresh budget of three
        assert "KeyError" in last["retry_held"]["legacy-dead"], last
        with db.session() as s:
            row = s.scalar(select(Incident).where(
                Incident.signature == "rebuild-incomplete:legacy-dead"))
            assert row.detail["attempts"] == G.REBUILD_MAX_ATTEMPTS, row.detail
            assert row.detail["legacy_failed_attempts_not_counted"] == 4, row.detail
    finally:
        restore()


def test_low_mb_bound_is_per_product_not_per_estate_change():
    """Review LOW: the job key carries the estate-wide change set, so another product's ref
    moving restarted this product's bound. The bound is keyed on the product's own change."""
    db = base._db()
    slugs = ["perprod"]
    _estate(db, slugs, release_for=slugs)
    restore = base._no_policy()
    t0 = datetime.now(timezone.utc)
    try:
        for d in range(6):
            now = t0 + timedelta(days=d)
            # another product's ref moves every day: a new estate stamp, a new job key
            changed = {"chain:release": "9" * 16, "design:someone-else": f"{d:x}" * 16}
            with db.session() as s:
                out = G.enqueue(s, JobQueue(db), changed=changed, per="product", reason="t",
                                now=now, hold=lambda slug: release_gates.retry_hold_reason(
                                    db, slug=slug))
            with db.session() as s:
                for j in s.scalars(select(Job).where(Job.job_type == "chain.rebuild",
                                                     Job.status == JobStatus.PENDING)):
                    j.status, j.finished_at = JobStatus.DEAD, now + timedelta(hours=1)
                    j.last_error = "KeyError: 'pdf_sha256'"
        assert "perprod" in out["retry_held"], out
        with db.session() as s:
            n = len(s.scalars(select(Job).where(Job.job_type == "chain.rebuild")).all())
        assert n == G.REBUILD_MAX_ATTEMPTS, n          # on 0d2e6cbc: one per day (6)
    finally:
        restore()


def pg_e2e_convergence():
    """Review L3: the round-1 end-to-end convergence test (the real chain: compile, build,
    move the chain, sentinel, rebuild, verify, resolve) on this engine. Not prefixed `test_`:
    it runs on SQLite in test_eng_stale_rebuild_loop, so here it runs in the PG list only."""
    real = base._sqlite_db
    base._sqlite_db = base._db           # the factory the runner set (PG)
    try:
        base.test_end_to_end_a_moved_chain_converges_in_one_attempt()
    finally:
        base._sqlite_db = real


PG_TESTS = ("test_ma_legacy_null_slug_exhausted_row_holds_the_retry",
            "test_ma_restating_a_legacy_row_files_its_product_slug",
            "test_ma_sentinel_holds_a_legacy_exhausted_product_instead_of_retrying",
            "test_mb_dead_rebuilds_are_bounded_then_held_with_the_error_class",
            "test_mb_refused_no_stored_release_is_bounded_then_held_with_the_refusal",
            "test_mc_sentinel_does_not_close_without_positive_evidence",
            "test_md_probe_reuse_requires_the_probe_model_and_the_same_key",
            "test_l1_hold_and_rebuild_read_the_same_withholding",
            "test_me_legacy_counts_get_a_fresh_recorded_budget_then_hold",
            "test_me_legacy_dead_jobs_do_not_spend_the_new_budget",
            "test_low_mb_bound_is_per_product_not_per_estate_change",
            "pg_e2e_convergence")


def _run_here(names, label):
    fails = 0
    for name in names:
        try:
            globals()[name]()
            print(f"OK   {label}{name}")
        except Exception as e:  # noqa: BLE001
            import traceback

            traceback.print_exc()
            fails += 1
            print(f"FAIL {label}{name}", repr(e))
    return fails


if __name__ == "__main__":
    names = [n for n in list(globals()) if n.startswith("test_")]
    fails = _run_here(names, "")
    try:
        from test_codex_v0_postgres import _disposable_cluster
    except Exception:  # noqa: BLE001
        _disposable_cluster = None
    if _disposable_cluster is not None:
        with _disposable_cluster():
            raw = os.environ.get("CODEX_V0_TEST_DATABASE_URL")
            if raw and os.environ.get("CODEX_V0_DISPOSABLE_DATABASE") == "yes":
                base._MAKE_DB = base._pg_factory(raw)
                fails += _run_here(PG_TESTS, "[postgres] ")
                base._MAKE_DB = None
            else:
                print("SKIP [postgres] no local PostgreSQL toolchain: production-shaped "
                      "tests ran on SQLite only")
    print(f"{fails} failure(s)")
    sys.exit(1 if fails else 0)
