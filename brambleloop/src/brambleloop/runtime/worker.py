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
    ):
        self.db = db
        self.name = name
        self.phase = phase
        self.job_types = list(job_types) if job_types else None
        self.queue = JobQueue(db, lease_seconds=lease_seconds)
        self.agents = Registry(db)
        self.handlers = registry or handlers
        self.stats = WorkerStats()
        self._stopping = False

    def stop(self, *_a) -> None:
        self._stopping = True

    def run_once(self) -> bool:
        """Claim and run at most one job. Returns False when there was nothing to do."""
        job = self.queue.claim(self.name, self.job_types)
        if job is None:
            return False
        self.stats.claimed += 1

        # Authorize before anything else, including handler lookup. An agent reaching for work
        # it may not do is denied whether or not a handler happens to exist for it.
        try:
            self.agents.authorize(job.agent, job.job_type)
        except PermissionDenied as e:
            # Never retry a permission failure: it will never spontaneously become allowed.
            self.queue.fail(job.id, f"permission denied: {e}", retry=False)
            self.agents.audit(job.agent, "job.denied", artifact=job.job_type,
                              job_id=job.id, phase=self.phase, detail={"error": str(e)})
            self.stats.denied += 1
            return True

        handler = self.handlers.get(job.job_type)
        if handler is None:
            self.queue.fail(job.id, f"no handler registered for {job.job_type!r}", retry=False)
            self.stats.skipped += 1
            return True

        ctx = JobContext(job=job, db=self.db, queue=self.queue,
                         registry=self.agents, phase=self.phase)
        try:
            outputs = handler(ctx) or {}
            self.queue.complete(job.id, outputs)
            self.agents.audit(job.agent, f"job.completed:{job.job_type}",
                              artifact=str(outputs.get("artifact") or job.job_type),
                              job_id=job.id, phase=self.phase)
            self.stats.completed += 1
        except CapabilityNotEnabled as e:
            self.queue.fail(job.id, f"capability not enabled: {e}", retry=False)
            self.agents.audit(job.agent, "job.capability_not_enabled", artifact=job.job_type,
                              job_id=job.id, phase=self.phase, detail={"error": str(e)})
            self.stats.failed += 1
        except BudgetExceeded as e:
            self.queue.fail(job.id, f"budget exceeded: {e}", retry=False)
            self.agents.audit(job.agent, "job.budget_exceeded", job_id=job.id,
                              phase=self.phase, detail={"error": str(e)})
            self.stats.failed += 1
        except Exception as e:  # noqa: BLE001 - a worker must survive any handler
            self.queue.fail(job.id, f"{type(e).__name__}: {e}\n{traceback.format_exc()[:2000]}")
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
    # (name, agent, job_type, period_seconds)
    ("infra_heartbeat", "orchestrator", "ops.heartbeat", 15 * 60),
    ("queue_check", "orchestrator", "ops.queue_check", 60 * 60),
    ("signal_review", "market_radar", "radar.scan", 6 * 60 * 60),
    ("daily_review", "orchestrator", "plan.cycle", 24 * 60 * 60),
    ("portfolio_review", "orchestrator", "portfolio.review", 7 * 24 * 60 * 60),
    ("finance_reconcile", "cfo", "finance.reconcile", 24 * 60 * 60),
    ("strategy_review", "orchestrator", "plan.strategy", 30 * 24 * 60 * 60),
    # Hourly on purpose: it is the thing that notices a certified product with no listing,
    # which is what a pipeline upgrade leaves behind.
    ("chain_rebuild", "listing", "chain.rebuild", 60 * 60),
    # Daily, because what blocks a launch changes as the company builds: a requirement that
    # was ours yesterday can be the owner's today, and the owner queue should say so without
    # anyone asking.
    ("launch_readiness", "orchestrator", "launch.readiness", 24 * 60 * 60),
    # Six-hourly. The model gate reads a recorded successful call rather than a configured
    # key, because the key this company has authenticates against an account with no credit.
    # This is what makes the gate open by itself the moment that changes, and it is cheap:
    # eight tokens on the smallest model, refused entirely if the month's ceiling is close.
    ("model_probe", "orchestrator", "model.probe", 6 * 60 * 60),
    # Requirement 51. Daily, and it proves the restore rather than only writing the export --
    # a backup nobody has restored is a hope, not a continuity plan.
    ("continuity_proof", "orchestrator", "ops.continuity", 24 * 60 * 60),
    # Daily, because a launch date that was comfortable in September is missed in October
    # without anything changing except the date. The first run of this engine found that the
    # whole catalogue had already missed Canadian Thanksgiving; rediscovering that by hand
    # once a quarter is how a company misses Christmas too.
    ("seasonal_sentinel", "orchestrator", "seasonal.sentinel", 24 * 60 * 60),
    # Six-hourly, matching the radar scan. #313 wants frequent lightweight checks once a
    # baseline exists, and the fingerprint makes an unchanged catalogue nearly free -- but
    # cadence that adapts to the shop's own posting behaviour is still to build, so this is
    # a fixed interval chosen to be cheap rather than an adaptive one claimed to be smart.
    ("mjs_scan", "market_radar", "mjs.scan", 6 * 60 * 60),
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
]


class Scheduler:
    def __init__(self, db: Database):
        self.db = db
        self.queue = JobQueue(db)

    def tick(self, now=None) -> list[str]:
        """Enqueue any cadence whose window has opened. Safe to call as often as you like."""
        now = now or utcnow()
        enqueued: list[str] = []
        for name, agent, job_type, period in CADENCES:
            window = int(now.timestamp() // period)
            key = f"cadence:{name}:{window}"
            try:
                self.queue.enqueue(agent, job_type, {"cadence": name}, idempotency_key=key,
                                   priority=50 if period <= 3600 else 100)
                enqueued.append(name)
            except DuplicateJob:
                continue
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
