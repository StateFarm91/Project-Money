"""Worker loop and scheduler (Master Plan section 13).

This is the part that keeps running when Claude and the owner's computer are off. It claims
leased jobs, dispatches them through the permission layer, records cost and audit, and either
completes them or fails them into backoff / dead-letter.

Two rules shape the design:

  - A worker never trusts itself. Every dispatch goes through `Registry.authorize`, so an
    agent cannot run work it has no permission for even if something enqueued it by mistake.
  - A worker never runs forever on one job. Leases expire, so a hung handler is reclaimable
    by another worker rather than silently stalling the company.
"""
from __future__ import annotations

import signal
import threading
import time
import traceback
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Callable, Sequence

from sqlalchemy import select

from ..agents.registry import BudgetExceeded, PermissionDenied, Registry
from ..core.db import Database
from ..core.models import Job, JobStatus, Phase, utcnow
from ..queue.durable import DuplicateJob, JobQueue

Handler = Callable[["JobContext"], dict]


class CapabilityNotEnabled(RuntimeError):
    """A production capability was attempted before its gate opened.

    Terminal, not transient: shadow mode will not spontaneously become production between
    retries, so retrying is pure churn and buries the real reason under "retries exhausted".
    """


@dataclass
class JobContext:
    job: Job
    db: Database
    queue: JobQueue
    registry: Registry
    phase: Phase

    def enqueue(self, agent: str, job_type: str, inputs: dict | None = None, **kw) -> Job | None:
        """Queue follow-on work. Duplicate keys are a success, not an error."""
        try:
            return self.queue.enqueue(agent, job_type, inputs, **kw)
        except DuplicateJob:
            return None

    def audit(self, action: str, **kw) -> None:
        self.registry.audit(self.job.agent, action, job_id=self.job.id, phase=self.phase, **kw)

    def heartbeat(self) -> None:
        """Extend this job's lease. A handler that legitimately runs longer than the lease
        -- a render, a paged scan, a restore -- calls this between steps, so it is not
        reclaimed and run twice while it is still working. Since completions are fenced on
        the lease holder, a long handler that never heartbeats would also have its own
        result refused once another worker reclaimed the job.

        Fenced to this job's lease holder (C-13): the name is the one `claim` stamped on the
        job this context was built from, so a stale context cannot extend a lease another
        worker now holds."""
        return self.queue.heartbeat(self.job.id, worker=self.job.leased_by or None,
                                    lease_token=getattr(self.job, "lease_token", None))

    def assert_lease(self) -> None:
        """Raise `LeaseLost` unless this context's claim still holds the job (audit ddf9c6e
        L-1). Called at the effect boundary (`queue.effects.guard`) so a stale-but-alive
        worker stops BEFORE an external effect, not only at its (fenced) completion. A
        context built without a lease token (direct handler calls in tests/tools) has no
        claim to lose and passes."""
        token = getattr(self.job, "lease_token", None)
        if not token or getattr(self.job, "id", None) is None:
            return
        from ..queue.effects import LeaseLost

        with self.db.session() as s:
            row = s.execute(select(Job.status, Job.lease_token, Job.lease_expires_at)
                            .where(Job.id == self.job.id)).first()
        if row is None or row.status != JobStatus.RUNNING or row.lease_token != token:
            raise LeaseLost(f"job {self.job.id}: lease no longer held by this attempt; "
                            f"external effect not performed")
        exp = row.lease_expires_at
        if exp is not None:
            exp = exp if exp.tzinfo else exp.replace(tzinfo=utcnow().tzinfo)
            if exp <= utcnow():
                raise LeaseLost(f"job {self.job.id}: lease expired at {exp.isoformat()}; "
                                f"external effect not performed")

    def effect(self, effect: str, idem: str):
        """`with ctx.effect("etsy.activate", key) as intent:` -- see queue.effects.guard."""
        from ..queue import effects

        return effects.guard(self, effect, idem)


def protected_phase(ctx: "JobContext") -> Phase:
    """rc1-AUTH A1: the phase a protected external effect may run in, resolved *now*.

    The more restrictive of the phase this job was started with and the effective phase
    (`core.phase.effective`: the environment AND the owner's latest recorded, chained
    transition). An owner rollback recorded after the worker booted -- or after the job was
    claimed -- therefore stops publication, activation and spend at the next effect boundary.
    Fails closed to shadow.
    """
    from ..core import phase as phase_mod

    try:
        live = phase_mod.effective(ctx.db)
    except Exception:  # noqa: BLE001 - an unreadable phase is shadow
        live = phase_mod.DEFAULT
    started = getattr(ctx.phase, "value", None) or phase_mod.DEFAULT
    return Phase(phase_mod.more_restrictive(started, live))


class HandlerRegistry:
    def __init__(self) -> None:
        self._handlers: dict[str, Handler] = {}

    def register(self, job_type: str) -> Callable[[Handler], Handler]:
        def deco(fn: Handler) -> Handler:
            self._handlers[job_type] = fn
            return fn

        return deco

    def get(self, job_type: str) -> Handler | None:
        return self._handlers.get(job_type)

    def known(self) -> list[str]:
        return sorted(self._handlers)


handlers = HandlerRegistry()


def _note_funding(db, text: str) -> None:
    """Raise the owner action for a spent provider balance. Never fails a job."""
    try:
        from ..ops import funding

        funding.note(db, text)
    except Exception:  # noqa: BLE001 - telling somebody must never break the telling
        pass


@dataclass
class WorkerStats:
    claimed: int = 0
    completed: int = 0
    failed: int = 0
    skipped: int = 0
    denied: int = 0


class Worker:
    def __init__(
        self,
        db: Database,
        name: str = "worker-1",
        *,
        phase: Phase = Phase.SHADOW,
        job_types: Sequence[str] | None = None,
        registry: HandlerRegistry | None = None,
        lease_seconds: int = 300,
        live_phase: bool = False,
    ):
        self.db = db
        self.name = name
        self.phase = phase
        # rc1-AUTH A1: a deployed worker re-resolves the effective phase for every job rather
        # than keeping the one it booted with, so an owner rollback recorded while it runs
        # applies to the next job (and `protected_phase` re-checks at each effect boundary).
        self.live_phase = live_phase
        self.job_types = list(job_types) if job_types else None
        self.queue = JobQueue(db, lease_seconds=lease_seconds)
        self.agents = Registry(db)
        self.handlers = registry or handlers
        self.stats = WorkerStats()
        self._stopping = False

    def _resolve_phase(self) -> Phase:
        from ..core.phase import effective_phase

        try:
            return effective_phase(self.db)
        except Exception:  # noqa: BLE001 - fail closed
            return Phase.SHADOW

    def stop(self, *_a) -> None:
        self._stopping = True

    def _funding_text(self, value) -> str:
        import json as _json

        try:
            return _json.dumps(value, default=str)
        except Exception:  # noqa: BLE001 # pragma: no cover
            return str(value)

    def run_once(self) -> bool:
        """Claim and run at most one job. Returns False when there was nothing to do."""
        job = self.queue.claim(self.name, self.job_types)
        if job is None:
            return False
        self.stats.claimed += 1
        if self.live_phase:
            self.phase = self._resolve_phase()

        # #175: the lane allocation limits how many jobs an agent's lane runs at once. A job
        # over its lane's concurrency goes back to PENDING un-counted (audited swarm.lane_held).
        if lane_hold(self.db, job, worker=self.name):
            return True

        # Authorize before anything else, including handler lookup. An agent reaching for work
        # it may not do is denied whether or not a handler happens to exist for it.
        try:
            self.agents.authorize(job.agent, job.job_type)
        except PermissionDenied as e:
            # Never retry a permission failure: it will never spontaneously become allowed.
            self.queue.fail(job.id, f"permission denied: {e}", retry=False,
                            worker=self.name, lease_token=job.lease_token)
            self.agents.audit(job.agent, "job.denied", artifact=job.job_type,
                              job_id=job.id, phase=self.phase, detail={"error": str(e)})
            self.stats.denied += 1
            return True

        handler = self.handlers.get(job.job_type)
        if handler is None:
            self.queue.fail(job.id, f"no handler registered for {job.job_type!r}", retry=False,
                            worker=self.name, lease_token=job.lease_token)
            self.stats.skipped += 1
            return True

        ctx = JobContext(job=job, db=self.db, queue=self.queue,
                         registry=self.agents, phase=self.phase)
        from ..ops import artefacts as provenance

        # Lease renewal for the handler's lifetime. Completion is fenced to the lease holder
        # (a reclaimed job's original worker cannot complete it), so a legitimate handler
        # longer than the lease -- a render, a benchmark, a continuity restore -- would lose
        # its result. Renewing from here covers every handler without each one remembering
        # to. It stops at MAX_HANDLER_SECONDS: a genuinely hung handler must still become
        # reclaimable, which is what the lease exists for.
        renewal = _LeaseRenewal(self.queue, job.id, worker=self.name,
                                lease_token=job.lease_token)
        renewal.start()
        from ..finance import spend_report as _spend

        try:
            # Spend inside the handler is attributed to the product the job works for
            # (F-321/F-324): the slug lives in the job, the bill is written five calls deeper.
            with _spend.attributed_to(_spend.job_product(self.db, job)):
                outputs = handler(ctx) or {}
            renewal.stop()
            # Provenance backstop (#171). The write path records lineage as it writes; this
            # is the check that it did, after the handler and before the job is marked done.
            # Any listing, frame, certificate or content piece this job created without a
            # provenance row is audited as `provenance.refused`, and once the estate's
            # backlog is closed (`may_enforce_unproven`, read without this job's own rows so
            # the row that should fail the job cannot also excuse it) the job fails rather
            # than completing with an artefact nobody can prove fresh. Before then it is
            # audited and logged only -- failing a whole catalogue of jobs over
            # instrumentation nobody had fitted is a different problem from a stale artefact.
            try:
                with self.db.session() as s:
                    # This attempt's window, not the job's first attempt (C-52): a retried
                    # job was otherwise blamed for every artefact other jobs wrote between
                    # its first attempt and this one.
                    gap = provenance.assert_instrumented(
                        s, since=getattr(job, "attempt_started_at", None) or job.started_at,
                        job_id=job.id)
                    enforce = bool(gap["missing"]) and provenance.may_enforce_unproven(
                        s, ignoring=gap["missing"])["may_enforce_unproven"]
            except Exception as exc:  # noqa: BLE001 - the check must not break what it checks
                gap, enforce = {"missing": [], "error": f"{type(exc).__name__}: {exc}"}, False
            if gap["missing"]:
                self.agents.audit(job.agent, "provenance.refused", artifact=job.job_type,
                                  job_id=job.id, phase=self.phase,
                                  detail={"count": len(gap["missing"]),
                                          "missing": [list(m) for m in gap["missing"]][:50],
                                          # rows that exist but lack this job's lineage
                                          # (certification C-27): a bare `record()` row
                                          # does not instrument an artefact
                                          "incomplete": list(gap.get("incomplete") or [])[:50],
                                          "enforcing": enforce})
                if enforce:
                    raise provenance.ProvenanceRefused(
                        f"{job.job_type} wrote {len(gap['missing'])} derived artefact(s) "
                        f"with no lineage-complete provenance row from this job: "
                        f"{gap['missing'][:3]}. The backlog is "
                        f"closed, so an absent row is a defect rather than an unfitted "
                        f"instrument, and a job that leaves one does not complete")
            # A handler that caught a spent balance and recorded it honestly still completes,
            # so the funding check reads the outputs as well as the exceptions. The pack
            # build did exactly that: `built: false`, the provider's own sentence in `why`,
            # a green job, and nobody told.
            _note_funding(self.db, self._funding_text(outputs))
            if not self.queue.complete(job.id, outputs, worker=self.name,
                                       lease_token=job.lease_token):
                # The lease was reclaimed while this handler ran. The queue recorded the
                # refusal; the job's outcome belongs to the worker that holds it now.
                self.stats.skipped += 1
                return True
            self.agents.audit(job.agent, f"job.completed:{job.job_type}",
                              artifact=str(outputs.get("artifact") or job.job_type),
                              job_id=job.id, phase=self.phase)
            self.stats.completed += 1
        except CapabilityNotEnabled as e:
            renewal.stop()
            self.queue.fail(job.id, f"capability not enabled: {e}", retry=False,
                            worker=self.name, lease_token=job.lease_token)
            self.agents.audit(job.agent, "job.capability_not_enabled", artifact=job.job_type,
                              job_id=job.id, phase=self.phase, detail={"error": str(e)})
            self.stats.failed += 1
        except BudgetExceeded as e:
            renewal.stop()
            self.queue.fail(job.id, f"budget exceeded: {e}", retry=False,
                            worker=self.name, lease_token=job.lease_token)
            self.agents.audit(job.agent, "job.budget_exceeded", job_id=job.id,
                              phase=self.phase, detail={"error": str(e)})
            self.stats.failed += 1
        except provenance.ProvenanceRefused as e:
            renewal.stop()
            # Terminal, like a capability gate: a handler that cannot say what made its
            # artefact will not be able to say so on the next attempt either.
            self.queue.fail(job.id, f"provenance refused: {e}", retry=False,
                            worker=self.name, lease_token=job.lease_token)
            self.agents.audit(job.agent, "job.provenance_refused", artifact=job.job_type,
                              job_id=job.id, phase=self.phase, detail={"error": str(e)[:500]})
            self.stats.failed += 1
        except Exception as e:  # noqa: BLE001 - a worker must survive any handler
            renewal.stop()
            _note_funding(self.db, str(e))
            # A PermanentError is terminal (C-51): hash drift, a corrupt artefact, a refusal in
            # the provider's own words will be the same on the next attempt, so retrying it
            # only spends the attempts and delays the dead letter somebody has to read.
            from ..core.resilience import PermanentError

            self.queue.fail(job.id, f"{type(e).__name__}: {e}\n{traceback.format_exc()[:2000]}",
                            retry=not isinstance(e, PermanentError), worker=self.name,
                            lease_token=job.lease_token)
            self.agents.audit(job.agent, "job.failed", job_id=job.id, phase=self.phase,
                              detail={"error": str(e)})
            self.stats.failed += 1
        return True

    def run(self, *, max_jobs: int | None = None, idle_sleep: float = 2.0,
            max_seconds: float | None = None) -> WorkerStats:
        """Drain the queue, sleeping when idle. Agents sleep when no valuable work exists."""
        signal.signal(signal.SIGTERM, self.stop)
        started = time.monotonic()
        done = 0
        while not self._stopping:
            if max_jobs is not None and done >= max_jobs:
                break
            if max_seconds is not None and time.monotonic() - started > max_seconds:
                break
            if self.run_once():
                done += 1
            else:
                if max_jobs is not None or max_seconds is not None:
                    break  # bounded run: an empty queue means finished
                time.sleep(idle_sleep)
        return self.stats


# ---- scheduler -----------------------------------------------------------

# Master Plan section 13 cadences. The scheduler is idempotent per window: enqueuing the same
# cadence twice in the same window is refused by the job's idempotency key, so a restart loop
# cannot flood the queue.
CADENCES: list[tuple[str, str, str, int]] = [
    ("learn_gap_scan", "learn", "learn.scan", 3600),
    # (name, agent, job_type, period_seconds)
    ("infra_heartbeat", "orchestrator", "ops.heartbeat", 15 * 60),
    ("queue_check", "orchestrator", "ops.queue_check", 60 * 60),
    ("signal_review", "market_radar", "radar.scan", 6 * 60 * 60),
    ("daily_review", "orchestrator", "plan.cycle", 24 * 60 * 60),
    ("portfolio_review", "orchestrator", "portfolio.review", 7 * 24 * 60 * 60),
    ("finance_reconcile", "cfo", "finance.reconcile", 24 * 60 * 60),
    ("strategy_review", "orchestrator", "plan.strategy", 30 * 24 * 60 * 60),
    # Requirement 193. Daily, and deliberately the *minimum* comprehensive sweep rather than
    # the only way learning happens: it reads, compares and records, and queues nothing that
    # promotes itself. Its verdict is computed from what each stage read, so a night where
    # six stages had nothing to read reports `incomplete` instead of success -- which is the
    # honest reading of a shadow-mode company and the one a "finished without raising" job
    # would hide.
    ("nightly_improvement", "orchestrator", "improve.nightly", 24 * 60 * 60),
    # Requirement 194. Weekly, across the eight domains the requirement names. A domain with
    # nothing read is `not_audited` rather than clean, because a weekly report of a healthy
    # business nobody looked at is the same output as one somebody did.
    ("weekly_evolution", "orchestrator", "improve.weekly", 7 * 24 * 60 * 60),
    # Requirements 90, 94. Daily: one deterministic query per capability cell. An identical
    # reading is not re-recorded, so running it beside the nightly sweep cannot manufacture
    # a flat history for the plateau detector to read as a defect.
    ("capability_measure", "orchestrator", "improve.measure", 24 * 60 * 60),
    # Requirement 97. Six-hourly: failures mined into routed lessons, idempotent on evidence,
    # so a defect open for a month is one lesson a month old. Nightly is the minimum sweep.
    ("failure_mine", "orchestrator", "improve.mine", 6 * 60 * 60),
    # Requirement 93. Daily: every promoted change judged once per new production reading,
    # and a regression becomes a revert plus a rollback incident rather than a quiet row.
    ("promotion_monitor", "orchestrator", "improve.monitor", 24 * 60 * 60),
    # Certification 2026-09-27 (#82, #89, #298): the learners run daily and report UNMEASURED
    # with the minimum n until listings produce outcomes; the harvest refuses a season that
    # has not passed or has fewer than 20 orders.
    ("style_learning", "creative_director", "creative.style_learning", 24 * 60 * 60),
    ("outcome_learning", "creative_director", "creative.outcome_learning", 24 * 60 * 60),
    ("season_harvest", "orchestrator", "seasonal.harvest", 24 * 60 * 60),
    # #5 / #43: every certified release is routed to its lane, its owed gates checked, and
    # tester demand planned against the roster.
    ("production_lanes", "quality_director", "gate.lanes", 24 * 60 * 60),
    # #118 / #121: weekly white-space discovery and the four-season programme feed every
    # tournament and expedition brief.
    ("white_space_discovery", "creative_director", "creative.white_space", 7 * 24 * 60 * 60),
    ("four_season_programme", "creative_director", "creative.four_season", 7 * 24 * 60 * 60),
    # #92 / #95 / #180: sandbox trials and the challenger league, daily; #188 the governor,
    # hourly; C-42 / #41 support triage, hourly (drafts only, nothing is sent in shadow).
    ("improve_sandbox", "orchestrator", "improve.sandbox", 24 * 60 * 60),
    ("improve_league", "orchestrator", "improve.league", 24 * 60 * 60),
    ("finance_governor", "cfo", "finance.governor", 60 * 60),
    ("support_triage", "support", "support.triage", 60 * 60),
    # C-59 (#23 #236 #253 #254 #256 #257): the machinery of the gated commerce rows runs daily
    # on what the database holds, so the day the data arrives is the day it is read.
    ("commerce_readings", "cfo", "commerce.readings", 24 * 60 * 60),
    # C-64: the order source (six-hourly, behind the transactions_r gate; no network call
    # while it is closed), everything that reads orders (daily, and after any ingest that
    # wrote one), the nightly trajectory (#26) and the creative north star by cohort (#132).
    ("orders_ingest", "cfo", "commerce.orders_ingest", 6 * 60 * 60),
    # F-005: Etsy's seller taxonomy and the crochet-pattern subtree's property schemas, into
    # a snapshot the category chooser reads. Daily, read-only, CA$0, and a no-op with no
    # network call while the etsy_api gate is closed.
    ("etsy_taxonomy", "listing", "listing.taxonomy_refresh", 24 * 60 * 60),
    # F-280: launch-week Search Visibility watch -- a daily owner card for the seven days
    # after the phase first leaves shadow; a no-op in shadow (runtime.storefront_watch).
    ("search_visibility_watch", "listing", "listing.search_visibility_watch", 24 * 60 * 60),
    ("order_readings", "cfo", "commerce.order_readings", 24 * 60 * 60),
    ("trajectory_nightly", "orchestrator", "scale.trajectory", 24 * 60 * 60),
    ("creative_north_star", "creative_director", "creative.north_star", 24 * 60 * 60),
    # C-60 (#17 #19 #238 #239 #242-#251 #255 #258-#261 #264 #267 #276 #291 #294 #295): paid
    # media planned behind the owner's ad gate, distribution and the buyer journey read from
    # the database daily, and the week's reallocation applied to the queue hourly.
    ("ads_review", "ads", "ads.adjust", 24 * 60 * 60),
    ("growth_distribution", "growth", "growth.distribution", 24 * 60 * 60),
    ("growth_journey", "growth", "growth.journey", 24 * 60 * 60),
    ("growth_steer", "swarm_steward", "growth.steer", 60 * 60),
    # #265 / #266 experiments concluded daily; #34 the thrash sweep hourly; the seasonal
    # engine daily (#33 #38 #131 #267 #286 #287 #289 #290 #291).
    ("growth_conclude", "experiment_steward", "growth.conclude", 24 * 60 * 60),
    ("thrash_sweep", "orchestrator", "ops.thrash", 60 * 60),
    ("seasonal_engine", "orchestrator", "seasonal.engine", 24 * 60 * 60),
    # Build 2 closeout (2026-09-27): the runtime halves of libraries that had none.
    # #174-#176, #186, #192: the swarm reviews agent quality, sizes lanes, resolves orphaned
    # work and feeds an idle queue from the standing backlog -- GREEN only, never spending.
    ("swarm_review", "swarm_steward", "swarm.review", 24 * 60 * 60),
    ("swarm_allocate", "swarm_steward", "swarm.allocate", 60 * 60),
    ("swarm_orphans", "swarm_steward", "swarm.orphans", 60 * 60),
    ("swarm_backlog", "swarm_steward", "swarm.backlog", 60 * 60),
    # #4: concept posts prepared and checked daily for the concepts held before engineering;
    # posting refused while owned_surfaces is closed, interest UNMEASURED until a platform
    # reports it, and a measured result steers the next field's brief.
    ("preproduction_validation", "growth", "growth.preproduction", 24 * 60 * 60),
    # #241/#265: experiments persisted with owner, expected value and a kill rule.
    ("growth_experiments", "experiment_steward", "growth.experiments", 24 * 60 * 60),
    # #75 COMPETITIVE and #222/#320: the blind review and the acceptance runner read stored
    # evidence only; neither fetches or spends.
    ("blind_review", "creative_director", "creative.blind_review", 24 * 60 * 60),
    # #126: weekly, judged by a vision panel inside the ceiling; refused pods are recorded.
    ("grid_tournament", "creative_director", "creative.grid_tournament", 7 * 24 * 60 * 60),
    ("intel_acceptance", "market_radar", "intel.acceptance", 24 * 60 * 60),
    # #171: lineage backfilled only where a job, audit or hash proves it; idempotent.
    ("provenance_backfill", "orchestrator", "ops.provenance_backfill", 24 * 60 * 60),
    # Cost governance: the 80% escalation becomes an owner action without anybody looking.
    ("spend_escalation", "cfo", "finance.escalation_check", 6 * 60 * 60),
    # Hourly on purpose: it is the thing that notices a certified product with no listing,
    # which is what a pipeline upgrade leaves behind.
    ("chain_rebuild", "listing", "chain.rebuild", 60 * 60),
    # Daily, because what blocks a launch changes as the company builds: a requirement that
    # was ours yesterday can be the owner's today, and the owner queue should say so without
    # anyone asking.
    ("launch_readiness", "orchestrator", "launch.readiness", 24 * 60 * 60),
    # F-125: a completion claim the measurement contradicts (COMPLETE but never ran,
    # INTEGRATED but not reached) is an incident, checked daily rather than by hand.
    ("maturity_disagreements", "orchestrator", "ops.maturity_disagreements", 24 * 60 * 60),
    # Six-hourly. The model gate reads a recorded successful call rather than a configured
    # key, because the key this company has authenticates against an account with no credit.
    # This is what makes the gate open by itself the moment that changes, and it is cheap:
    # eight tokens on the smallest model, refused entirely if the month's ceiling is close.
    ("model_probe", "orchestrator", "model.probe", 6 * 60 * 60),
    # Requirement 51. Daily, and it proves the restore rather than only writing the export --
    # a backup nobody has restored is a hope, not a continuity plan.
    ("continuity_proof", "orchestrator", "ops.continuity", 24 * 60 * 60),
    # Requirement 51's other half, and a separate job on purpose: `ops.continuity` proves the
    # export restores, this proves a copy of it is somewhere that losing this hosting
    # provider does not take with it. One job reporting one verdict would let a healthy local
    # restore stand in for an archive that was never written.
    ("offsite_archive", "orchestrator", "ops.offsite_archive", 24 * 60 * 60),
    # Weekly, and cheap after the first run: a candidate already measured under this exact
    # rubric is reused rather than re-rendered, so the recurring cost is whatever changed --
    # a provider whose credential has just arrived, or every candidate again if the rubric
    # itself moved. It is on a cadence because the alternative was an endpoint needing a
    # credential nobody in a session holds, and a benchmark that only runs when somebody
    # remembers to press something is a benchmark that runs once.
    # Six-hourly rather than weekly, and that is not a cost decision: a candidate already
    # measured under the current method is reused rather than re-rendered, so a settled
    # benchmark costs nothing to re-check and an unsettled one is picked up within hours of
    # a credential arriving or a method changing. Weekly was chosen before reuse existed,
    # and it left a half-measured benchmark sitting for seven days.
    ("image_benchmark", "creative_director", "creative.image_benchmark", 60 * 60),
    # The canonical-model tournament. Hourly like the benchmark and free after the first
    # run: it is keyed on the brief, so it renders once and a changed brief renders again.
    ("model_tournament", "creative_director", "creative.model_tournament", 60 * 60),
    # The owner's candidate, same shape: keyed on the candidate, so it builds once and a
    # new concept builds again. Free after the first run.
    ("model_reference_pack", "creative_director", "creative.model_reference_pack", 60 * 60),
    # Daily, because a launch date that was comfortable in September is missed in October
    # without anything changing except the date. The first run of this engine found that the
    # whole catalogue had already missed Canadian Thanksgiving; rediscovering that by hand
    # once a quarter is how a company misses Christmas too.
    # Daily and free after the first run: an asset already made for a release is not
    # remade, so this costs one image the day a release first gets one and nothing after.
    ("owned_photography", "publishing", "assets.owned_photography", 24 * 60 * 60),
    # Daily, and its counterpart: the forms a buyer cannot judge without a body. Idempotent
    # by product and version inside the handler, so this costs one render per release and
    # nothing afterwards -- and it refuses to spend at all when no frozen identity exists
    # to verify the result against (#72, #130, #202).
    ("model_photography", "publishing", "assets.model_photography", 24 * 60 * 60),
    ("seasonal_sentinel", "orchestrator", "seasonal.sentinel", 24 * 60 * 60),
    # Six-hourly, matching the radar scan. #313 wants frequent lightweight checks once a
    # baseline exists, and the fingerprint makes an unchanged catalogue nearly free -- but
    # cadence that adapts to the shop's own posting behaviour is still to build, so this is
    # a fixed interval chosen to be cheap rather than an adaptive one claimed to be smart.
    # Six-hourly, ahead of the scan that depends on it. The benchmark gate reads this
    # probe's result rather than the presence of two variables, so this is what opens it --
    # and what closes it again if the credential is ever revoked, without anybody noticing
    # by finding an empty catalogue.
    ("etsy_probe", "market_radar", "etsy.probe", 6 * 60 * 60),
    # Two-hourly *opportunity*, not two-hourly scans: `scan_or_explain` is adaptive by
    # default (#313) and defers any scan the benchmark's own posting history says is not due,
    # before a single request is made. Two hours is the adaptive floor; with thin history it
    # falls back to six hours and says so.
    ("mjs_scan", "market_radar", "mjs.scan", 2 * 60 * 60),
    # Certification C-40 (#2, #15, #98): daily capture of the API search index for the pod
    # vocabulary, labelled api_index_score_sort -- directional, never the rendered page.
    ("serp_capture", "market_radar", "intel.serp_capture", 24 * 60 * 60),
    # #206 / #226 / #311: MJs benchmark URL health, pod capability readings, and the seasonal
    # deadline sentinel for MJs-derived opportunities.
    ("mjs_benchmark_health", "market_radar", "intel.benchmark_health", 24 * 60 * 60),
    ("mjs_pod_learning", "market_radar", "intel.pod_learning", 24 * 60 * 60),
    ("mjs_seasonal_sentinel", "market_radar", "mjs.seasonal_sentinel", 24 * 60 * 60),
    # C-60 (#219, #268): other category leaders join the elite panel from the API index.
    ("panel_discovery", "market_radar", "intel.panel_discovery", 7 * 24 * 60 * 60),
    # C-60 (#165): benchmark refresh recommendations, weekly and free.
    ("benchmark_refresh", "market_radar", "intel.benchmark_refresh", 7 * 24 * 60 * 60),
    # C-60 (#64): physical-proof upgrades measured daily; UNMEASURED until listings are live.
    ("physical_upgrade_impact", "quality_director", "physical.upgrade_impact", 24 * 60 * 60),
    # C-60 (#201): the canonical identity checked as a series across batches, daily.
    ("identity_drift", "quality_director", "visual.identity_drift", 24 * 60 * 60),
    # C-60 (#86): the creativity benchmark memory, daily and free; UNMEASURED until a judged
    # image carries a commercial attribute (the judging runs behind image_vision).
    ("benchmark_memory", "creative_director", "creative.benchmark_memory", 24 * 60 * 60),
    # C-60 (#116): construction readings and stored decompositions, gated on image_vision.
    ("reference_reading", "creative_director", "creative.reference_reading", 24 * 60 * 60),
    # Weekly. Reviews move slowly, and this is the one observation that reaches the
    # customer_pain domain without this company having customers. It keeps counts per theme
    # and no review text, reviewer or quotation.
    ("mjs_reviews", "market_radar", "mjs.reviews", 7 * 24 * 60 * 60),
    # Weekly, because a retrospective run daily becomes noise and one run quarterly is
    # archaeology. #100 asks for a cadence; this is the one a human would keep reading.
    ("improvement_retrospective", "orchestrator", "improve.retrospective", 7 * 24 * 60 * 60),
    # Daily. A platform policy is not a constant, and the cost of noticing a change late is
    # a suspension notice about listings that were compliant when they were created (#39).
    ("policy_watch", "orchestrator", "ops.policy_watch", 24 * 60 * 60),
    # Hourly. The build loop's own heartbeat: it reconciles the requirement graph against the
    # owner gates, un-parks anything whose gate opened, and notices a stall. Hourly rather
    # than daily because the interesting event -- a credential arriving -- should not wait
    # until tomorrow to unblock fourteen requirements.
    ("build_tick", "orchestrator", "build.tick", 60 * 60),
    # Fortnightly. Reconciled 2026-09-20 under the quality-first policy: this was monthly,
    # and the stated reason was that weekly would be 27% of a CA$25 ceiling. That argument
    # is gone -- twelve judged pairs at the deep tier is about CA$1.55, which is 1.5% of the
    # authorised figure now.
    #
    # It did not become weekly, and the reason is the measurement rather than the money.
    # #94 asks for creative capability tracked *over time*, and the thing being tracked does
    # not move in seven days: sampling faster than the signal changes buys noise and a
    # larger bill. Fortnightly doubles the resolution where the old interval was genuinely
    # coarse -- a monthly series takes a quarter to show a trend -- and stops where more
    # frequency would stop adding information rather than where it would start costing
    # money.
    ("blinded_benchmark", "creative_director", "creative.blinded", 14 * 24 * 60 * 60),
    # Weekly. Discovery into a proven arena the catalogue does not answer, rotating through
    # the gaps so breadth accumulates rather than one department deepening. **Measured at
    # CA$1.02** on the first live run -- three slots of six concepts at the deep tier -- not
    # the CA$0.32 estimated before the prompt's output budget was raised to hold a full
    # field. That is about CA$4.40 a month, and the interval stays weekly on the merits:
    # a catalogue widens by repeatedly trying somewhere it does not sell rather than by one
    # campaign, and the constraint on how often that is worth doing is how fast the gap
    # queue refills, not what it costs.
    ("arena_expedition", "creative_director", "creative.expedition", 7 * 24 * 60 * 60),
    # #3's tournament at the scale the requirement specifies: roughly eighty concepts at the
    # cheap tier, about CA$0.27 a run, against the one arena this cycle's wheel picked. The
    # expedition asks what we could make for an occasion; this asks whether there is a
    # Brambleloop answer to a proven arena we have no answer to, with a field wide enough
    # that the answer is not an artefact of the sample. Weekly and offset from the
    # expedition by running on the same wheel position, so the two land on the same arena and
    # the deep handful can be read against the wide field.
    ("product_tournament", "creative_director", "creative.tournament", 7 * 24 * 60 * 60),
    # Weekly, and free. #292 asks for evergreen products to be *periodically* inspected for
    # seasonal re-merchandising, and a review that never runs is the same as one that does
    # not exist. It reads certified products and an already-observed catalogue, changes no
    # listing and cannot increment the catalogue by construction.
    ("remerchandising_review", "listing", "seasonal.remerchandising", 7 * 24 * 60 * 60),
    # Weekly. #300 is a launch-blocking acceptance test whose eighth link -- create
    # Brambleloop-owned assets -- it could not satisfy for its own product: the cycle
    # certifies its concept in memory, and the daily photography job looks products up by
    # slug and can never reach it. This runs the cycle as a job so the asset is made for
    # the CIR in hand. Weekly rather than daily because it costs one render and its
    # checks, and because the thing it proves -- that the chain closes end to end -- does
    # not change between Tuesdays. `/api/seasonal/cycle` reads what this produced.
    ("seasonal_cycle_proof", "publishing", "seasonal.cycle_proof", 7 * 24 * 60 * 60),
    # Weekly, and free. #30's argument is that the capacity mix has to arrive as a number,
    # because the default for a system with no audience is more engineering -- it is the
    # work that is here, it always finishes, and it never needs anybody outside this
    # company. A module nobody calls is exactly "whatever was easiest to pick up", so the
    # allocation is a cadence for the same reason the re-merchandising review is one.
    ("capacity_review", "orchestrator", "ops.capacity", 7 * 24 * 60 * 60),
    # Hourly, and free. #173 asks for a *permanent* sentinel: a stale artefact under a stable
    # slug looks current to everything that reads it, so the only thing that finds it is
    # something that keeps looking. Hourly rather than daily because the window between a
    # design changing and its PDF being served is the whole exposure.
    ("stale_artefact_sentinel", "orchestrator", "ops.sentinel", 60 * 60),
    # Every fifteen minutes, and free. #185's definition is the reason it exists at all:
    # online means useful work is progressing, not that HTTP returned 200, and the only way
    # to know the difference is to keep asking whether anything was completed.
    ("health_sweep", "orchestrator", "ops.health", 15 * 60),
    # Six-hourly, free, and the reason it is a cadence rather than a one-off: a capability
    # that was proven once is not a capability that works. The three probes here answer
    # whether a rendered page can be fetched, whether a real image can be looked at, and
    # whether the culture source still returns a series -- and each writes a row the build
    # executor's gates read. A gate that opened on a configured variable needed nobody to
    # keep checking, which is exactly what was wrong with it.
    ("capability_probes", "orchestrator", "ops.capability_probes", 6 * 60 * 60),
    # Daily. Reference-reading interest for the topics this catalogue is merchandised
    # against, from Wikimedia's free sanctioned endpoint. Daily rather than hourly because
    # the pipeline behind it runs two days late and a cultural trend that moves within an
    # hour is not one; courtesy to a free source is also part of the justification for
    # using it.
    ("culture_sweep", "market_radar", "culture.sweep", 24 * 60 * 60),
    # Two-hourly. Drains the gallery-observation backlog once a vision probe has actually
    # succeeded, and refuses to run before that.
    #
    # **The period is here and the batch size is not, and that is the fix.** This said
    # twenty-five images every two hours, with a comment stating the cost -- CA$8.70 a day --
    # against `market_radar`'s authorised CA$4.00. Two owner-derived numbers, written in two
    # files, neither aware of the other, and nothing enforcing the smaller one on this path.
    # The owner ruled on 2026-09-25: keep the CA$4.00 and adapt the cadence. So the handler
    # now asks `finance.spend_policy.work_that_fits` how many images fit inside the ceiling
    # this run, using *this* period. The rate follows the ceiling automatically and the two
    # cannot disagree, because the batch is no longer written down anywhere.
    #
    # The period stays a freshness decision rather than a cost one: two hours is how stale
    # the benchmark's visual evidence is allowed to get, and pacing the day's permission
    # across twelve runs is what keeps the agent's other cadences -- the culture sweep, the
    # radar scans, the probes -- from finding the budget spent at 00:05.
    #
    # It is also self-limiting: once the backlog is empty the handler judges only new and
    # changed listings, so the standing cost falls to whatever the benchmark shop publishes.
    ("gallery_analysis", "market_radar", "intel.gallery_analysis", 2 * 60 * 60),
    # Daily. Retention: the audit log grows about 4,700 rows a day, the job table 900 and the
    # dead-letter queue 21, and until 2026-09-25 nothing pruned any of them -- `purge_dead`
    # existed and was called from nowhere. Daily rather than weekly because a daily run
    # deletes a day's worth and a weekly one deletes a week's worth in one transaction, and
    # the second is the shape that times out on a table that has grown. It removes nothing a
    # gate reads and refuses to run at all when it finds an audit action nobody has decided
    # about; `ops.retention` carries the reasoning.
    ("retention_sweep", "orchestrator", "ops.retention", 24 * 60 * 60),
    # C-69 (#50, #29): the dependency map probed daily and every failed probe, unproved
    # recovery, unmapped paid provider or existential concentration raised as an incident.
    ("dependency_sweep", "orchestrator", "ops.dependencies", 24 * 60 * 60),
    # #95 / #180 / #187: the league's producer of runs -- historical jobs replayed under the
    # job-priority policy and its challengers, newest days held out. Deterministic, no model.
    ("improve_replay", "orchestrator", "improve.replay", 24 * 60 * 60),
    # #153-#161: teardown findings checked as enforced requirements and routed to consumers.
    ("teardown_enforce", "orchestrator", "teardown.enforce", 24 * 60 * 60),
    # FB-1 cluster B. Daily reads of our own shop, through scopes already granted; none of
    # them writes to Etsy. F-540: the stored OAuth credential is openable, fully scoped and
    # still refreshing (one getMe, which rotates and persists the refresh token). F-515 /
    # F-577 / F-585: getShop stored and judged by `etsy_surfaces.assess_shop` (vacation,
    # currency, payments and trust-surface drift become incidents; passing checks close the
    # owner actions they evidence). F-553 / F-544 / F-568: getListingsByShop in every state,
    # compared with what we created, field drift and suspected takedowns as incidents.
    ("etsy_credential_health", "orchestrator", "etsy.credential_health", 24 * 60 * 60),
    ("etsy_shop_snapshot", "orchestrator", "etsy.shop_snapshot", 24 * 60 * 60),
    ("etsy_listing_census", "orchestrator", "etsy.listing_census", 24 * 60 * 60),
    # v1.1 lane A (PRIORITY ZERO, F-893/F-894): the Executive Orchestrator. Every fifteen
    # minutes it reads every department, reconciles the missions it created, and gives each
    # idle department its next highest-value safe work from durable evidence -- protected
    # actions become owner approval items, never jobs. `Scheduler.tick` also wakes it at once
    # when the whole queue is empty, so an empty queue never means an idle company.
    ("executive_orchestrator", "coo", "autonomy.orchestrate", 15 * 60),
    # Wave 3 lane D (D-FB-13): Laura's executive tick -- Laura -> COO -> departments ->
    # results -> Laura. Deterministic, GREEN, CA$0; she is also woken by the COO when a
    # mission she delegated closes (laura.executive.results_wake).
    ("laura_executive", "laura", "laura.executive_tick", 5 * 60),
    # v1.1 wiring (integrator). Each handler is registered in runtime.v11_wiring.
    # Lane I (F-924): SLOs evaluated and slo.* incidents raised/closed. Stored notifications
    # only; a watchdog, so it is never thrash-suspended (swarm LIVENESS_JOB_TYPES).
    ("slo_check", "orchestrator", "ops.slo", 15 * 60),
    # Lane G (directive §11): continuous SEO; idempotent, proposals only, no Etsy write.
    ("seo_cycle", "listing", "seo.cycle", 6 * 60 * 60),
    # Lane E (F-901): the Accountant cycle -- post, reconcile, anomalies, close check. Rows
    # only; moves no money, files nothing.
    ("accounting_cycle", "cfo", "finance.accounting.cycle", 6 * 60 * 60),
    # Lane H (F-686): Etsy Ads eligibility evidence re-evaluated hourly. Spends nothing and
    # activates nothing; a due refresh becomes an owner action.
    ("ads_readiness", "growth", "marketing.ads_readiness", 60 * 60),
]


def cadence_seconds(name: str) -> int:
    """The declared period of one cadence, read from the table that schedules it.

    A handler that needs to know its own rate -- to pace a budget across the day, say -- has
    to read it from here rather than restate it, because a period written twice is the defect
    that put a CA$8.70/day batch under a CA$4.00/day ceiling.
    """
    for cadence, _agent, _job_type, period in CADENCES:
        if cadence == name:
            return int(period)
    raise KeyError(
        f"no cadence named {name!r}. The schedule is the list above; a handler asking about "
        f"a cadence that is not scheduled is asking about a rate nothing sets")

# Requirement 179's eight meta-agents, one daily cadence each, generated from the roster so
# that the roles, the agents and the cadences cannot drift apart. Daily and read-only: each
# reads the rows it answers for and reports what it found. None proposes or promotes --
# proposing runs through #190's pipeline and promotion through #178's tiers, and a meta-agent
# that could promote would be the company rewriting itself faster than it can observe the
# results, which is the failure #178 exists to prevent.
#
# The period is offset per role rather than all landing at once: eight simultaneous scans of
# the same tables is a thundering herd on a container sized for one worker, and spreading
# them costs nothing because none of them is urgent.
def _role_cadences() -> list[tuple[str, str, str, int]]:
    from ..improve.roles import ROLE_JOB_TYPE, ROLES

    day = 24 * 60 * 60
    return [(f"role_{role.key}", role.key, ROLE_JOB_TYPE, day) for role in ROLES]


CADENCES.extend(_role_cadences())



# A handler may renew its lease for at most this long. Past it the lease lapses, another
# worker may reclaim the job, and the original's completion is refused by the fence.
MAX_HANDLER_SECONDS = 60 * 60


class _LeaseRenewal:
    """Renews a running job's lease every third of a lease, until stopped or capped.

    Names the worker it renews for (C-13), so the queue refuses to extend a lease somebody
    else now holds; once refused, this worker has lost the job and the thread stops rather
    than asking again every interval. `worker=None` keeps the unnamed legacy renewal."""

    def __init__(self, queue, job_id: int, *, worker: str | None = None,
                 cap_seconds: int = MAX_HANDLER_SECONDS, lease_token: str | None = None):
        self.queue, self.job_id, self.cap = queue, job_id, cap_seconds
        self.worker = worker
        self.lease_token = lease_token
        self.interval = max(1.0, float(getattr(queue, "lease_seconds", 300)) / 3.0)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True,
                                        name=f"lease-renewal-{job_id}")
        self.renewals = 0
        self.lost = False

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        started = time.monotonic()
        while not self._stop.wait(self.interval):
            if time.monotonic() - started >= self.cap:
                return
            try:
                extended = (self.queue.heartbeat(self.job_id, worker=self.worker,
                                                 lease_token=self.lease_token)
                            if self.lease_token else
                            self.queue.heartbeat(self.job_id, worker=self.worker))
            except Exception:  # noqa: BLE001 - a failed renewal must not kill the handler
                continue
            if extended is False:
                self.lost = True
                return
            self.renewals += 1

from ..swarm.orchestrate import lane_hold, priority_for  # noqa: E402


class Scheduler:
    def __init__(self, db: Database):
        self.db = db
        self.queue = JobQueue(db)

    def _blocked_departments(self, now) -> dict[str, str]:
        """Departments whose cadences this tick must not enqueue (audit ddf9c6e L-2).

        A department block (owner action / command-center block) now binds the department's
        scheduled cadences as well as orchestrator generation. Never-pause departments
        (F-889: executive, product truth, finance, platform) are exempt -- the same single rule
        the emergency pause and the orchestrator use. Blocks expire (memory.BLOCK_DEFAULT_TTL)
        unless renewed, so a forgotten block cannot silence a department forever."""
        out: dict[str, str] = {}
        try:
            from ..app.command_center.emergency import never_paused_refusal
            from ..autonomy import memory
            from ..autonomy.charters import CHARTERS

            for ch in CHARTERS:
                if never_paused_refusal(ch.key) is not None:
                    continue
                block = memory.active_block(self.db, ch.key, now=now)
                if block:
                    out[ch.key] = str(block["body"].get("reason") or "blocked")
        except Exception:  # noqa: BLE001 - an unreadable block table never stops scheduling
            self.block_read_error = traceback.format_exc(limit=2)[-300:]
        return out

    def _record_cadence_failure(self, name: str, job_type: str, exc: BaseException) -> None:
        """One poisoned cadence -> one deduplicated incident + audit row (audit ddf9c6e M-2)."""
        from ..core.models import AuditLog, Incident

        sig = f"scheduler.cadence_failed:{name}"[:200]
        err = f"{type(exc).__name__}: {str(exc)[:300]}"
        try:
            with self.db.session() as s:
                inc = s.scalar(select(Incident).where(Incident.signature == sig,
                                                      Incident.resolved.is_(False)))
                if inc is None:
                    s.add(Incident(severity="P2", signature=sig,
                                   summary=(f"cadence {name} ({job_type}) could not be "
                                            f"enqueued; the other cadences continue"),
                                   detail={"cadence": name, "job_type": job_type,
                                           "error": err}))
                else:
                    inc.report_count = (inc.report_count or 1) + 1
                    inc.detail = {**(inc.detail or {}), "error": err}
                s.add(AuditLog(actor="scheduler", action="scheduler.cadence_failed",
                               artifact=name[:200],
                               detail={"job_type": job_type, "error": err}))
        except Exception:  # noqa: BLE001 - recording a failure must not become one
            pass

    def tick(self, now=None) -> list[str]:
        """Enqueue any cadence whose window has opened. Safe to call as often as you like.

        Per-cadence isolation (audit ddf9c6e M-2): one cadence whose enqueue raises is
        recorded (incident + audit) and skipped; the remaining cadences are still enqueued
        and the tick completes, so the runner's heartbeat stays fresh and the stale-scheduler
        self-exit is not driven by a single poisoned cadence. Only when EVERY cadence that
        was attempted failed (database down) does the tick raise -- that is a scheduler that
        has genuinely stopped, which the self-exit exists for."""
        now = now or utcnow()
        enqueued: list[str] = []
        self.failures: dict[str, str] = {}
        self.blocked_skipped: dict[str, str] = {}
        # #34: a loop the thrash breaker suspended, or a poll it backed off, is not re-enqueued
        # by the next cadence window.
        try:
            from ..swarm.orchestrate import suspended_job_types

            suspended = suspended_job_types(self.db, now=now)
        except Exception:  # noqa: BLE001 - a failed read must never stop the scheduler
            suspended = {}
        self.suspended = suspended
        blocked = self._blocked_departments(now)
        self.blocked = blocked
        try:
            from ..autonomy.charters import department_of
        except Exception:  # noqa: BLE001
            def department_of(_jt):  # type: ignore[misc]
                return None
        attempted = ok = 0
        for name, agent, job_type, period in CADENCES:
            if job_type in suspended:
                continue
            dept = department_of(job_type) if blocked else None
            if dept in blocked:
                self.blocked_skipped[name] = dept
                continue
            attempted += 1
            try:
                window = int(now.timestamp() // period)
                key = f"cadence:{name}:{window}"
                # The job type's band (#187), not how often it happens to be scheduled.
                self.queue.enqueue(agent, job_type, {"cadence": name}, idempotency_key=key,
                                   priority=priority_for(job_type))
                enqueued.append(name)
                ok += 1
            except DuplicateJob:
                ok += 1
                continue
            except Exception as exc:  # noqa: BLE001 - one cadence never starves the others
                self.failures[name] = f"{type(exc).__name__}: {str(exc)[:200]}"
                self._record_cadence_failure(name, job_type, exc)
                continue
        if attempted and not ok:
            raise RuntimeError(f"every cadence failed to enqueue ({len(self.failures)}); "
                               f"first: {next(iter(self.failures.values()), '')}")
        # PRIORITY ZERO: an empty queue is a reason to ask the orchestrator now, not to wait
        # for its next window. Keyed per five minutes inside `idle_wake`, so it cannot flood.
        try:
            from ..autonomy.orchestrator import idle_wake

            if idle_wake(self.db, self.queue, now=now):
                enqueued.append("executive_orchestrator:idle_wake")
        except Exception:  # noqa: BLE001 - a failed wake never stops the scheduler
            pass
        return enqueued

    def due_soon(self, within_seconds: int = 3600) -> list[Job]:
        cutoff = utcnow() + timedelta(seconds=within_seconds)
        with self.db.session() as s:
            rows = list(s.scalars(
                select(Job).where(Job.status == JobStatus.PENDING, Job.run_after <= cutoff)
            ))
            for r in rows:
                s.expunge(r)
            return rows
