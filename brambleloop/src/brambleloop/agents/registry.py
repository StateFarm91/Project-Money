"""Agent registry, permissions, budget ceilings and the audit log (sections 14, 26).

The governance rules exist because a single over-permissive agent is how an autonomous
company quietly does something irreversible. Listing cannot spend ad money. Marketing cannot
alter CIR. Designer cannot publish. Support cannot silently patch canonical patterns.

These are enforced here in code, not asserted in a prompt.
"""
from __future__ import annotations

from datetime import date
from typing import Iterable

from sqlalchemy import select

from ..core.db import Database
from ..core.models import (
    Agent, Authority, AuditLog, CostEntry, Job, Phase, SpendLimit, utcnow,
)


class PermissionDenied(Exception):
    pass


class BudgetExceeded(Exception):
    pass


# The starting organisation. Job types are explicit: an agent can only ever run what is
# listed here, so widening authority is a visible, reviewable change.
DEFAULT_AGENTS: list[dict] = [
    dict(name="orchestrator", description="CEO/Orchestrator: sets priorities, schedules work",
         allowed_job_types=["plan.cycle", "portfolio.review", "ops.heartbeat",
                            "ops.queue_check", "plan.strategy", "launch.readiness",
                            "ops.continuity", "seasonal.sentinel",
                            "improve.retrospective", "ops.policy_watch", "build.tick",
                            "model.probe"],
         authority=Authority.GREEN,
         daily_cost_ceiling_cad=3.0),
    dict(name="market_radar", description="Discovery, category, trend and seasonality scanning",
         allowed_job_types=["radar.scan", "radar.score", "radar.competitor_snapshot",
                            "mjs.scan", "etsy.probe"],
         authority=Authority.GREEN, daily_cost_ceiling_cad=4.0),
    dict(name="crochet_engineer", description="Authors CIR from a creative brief",
         allowed_job_types=["cir.draft", "cir.revise"], authority=Authority.GREEN,
         daily_cost_ceiling_cad=4.0),
    dict(name="validator", description="Deterministic compile, twin, reverse compile",
         allowed_job_types=["cir.compile", "cir.twin", "cir.reverse"], authority=Authority.GREEN,
         daily_cost_ceiling_cad=1.0),
    dict(name="quality_director", description="Owns release certificates; can veto",
         allowed_job_types=["gate.quality", "gate.certify", "physical.record"],
         authority=Authority.GREEN,
         daily_cost_ceiling_cad=1.0),
    dict(name="asset_truth", description="Blocks imagery that misrepresents the pattern",
         allowed_job_types=["gate.asset_truth"], authority=Authority.GREEN,
         daily_cost_ceiling_cad=1.0),
    dict(name="policy", description="Platform policy and compliance checks; can veto",
         allowed_job_types=["gate.policy"], authority=Authority.GREEN,
         daily_cost_ceiling_cad=1.0),
    dict(name="publishing", description="Renders the PDF, charts and listing assets",
         allowed_job_types=["assets.build", "assets.render"], authority=Authority.GREEN,
         daily_cost_ceiling_cad=2.0),
    dict(name="growth", description="Launch timing and marketing cadence. Cannot author patterns.",
         allowed_job_types=["launch.plan", "marketing.schedule", "content.draft"],
         authority=Authority.GREEN,
         daily_cost_ceiling_cad=2.0),
    dict(name="listing", description="Drafts listings and SEO. Cannot spend ad money.",
         allowed_job_types=["listing.draft", "listing.seo", "collection.assemble",
                            "chain.rebuild"],
         authority=Authority.GREEN,
         daily_cost_ceiling_cad=2.0),
    dict(name="pricing", description="Price positioning and experiments; cannot bypass policy",
         allowed_job_types=["pricing.position", "pricing.experiment"], authority=Authority.GREEN,
         daily_cost_ceiling_cad=1.0),
    dict(name="store_operator", description="Publishes to the live store",
         allowed_job_types=["store.publish", "store.update"], authority=Authority.YELLOW,
         daily_cost_ceiling_cad=1.0),
    dict(name="ads", description="Paid media inside hard caps",
         allowed_job_types=["ads.campaign", "ads.adjust"], authority=Authority.YELLOW,
         daily_cost_ceiling_cad=1.0),
    dict(name="support", description="Customer replies. Cannot patch canonical patterns.",
         allowed_job_types=["support.reply", "support.triage"], authority=Authority.YELLOW,
         daily_cost_ceiling_cad=2.0),
    dict(name="cfo", description="Challenges spend; reconciles the ledger",
         allowed_job_types=["finance.reconcile", "finance.challenge"], authority=Authority.GREEN,
         daily_cost_ceiling_cad=1.0),
]

# Capabilities no agent may hold, regardless of registry contents. Belt and braces against a
# future session widening `allowed_job_types` without thinking.
FORBIDDEN_COMBINATIONS: dict[str, set[str]] = {
    "listing": {"ads.campaign", "ads.adjust"},
    "marketing": {"cir.draft", "cir.revise"},
    "support": {"cir.draft", "cir.revise", "store.publish"},
    "pricing": {"gate.policy"},
    # Publishing renders what was certified; it never decides what ships or authors a pattern.
    "publishing": {"store.publish", "store.update", "cir.draft", "cir.revise", "gate.certify"},
    # Growth schedules attention. Pattern content and live publication are not its business.
    "growth": {"cir.draft", "cir.revise", "store.publish", "gate.certify"},
}


class Registry:
    def __init__(self, db: Database):
        self.db = db

    # Fields DEFAULT_AGENTS owns outright. Everything else on an Agent row -- `enabled`, and
    # any future runtime state -- belongs to the running system and is never overwritten.
    DECLARED_FIELDS = ("description", "allowed_job_types", "authority", "phase",
                       "daily_cost_ceiling_cad")

    def seed_defaults(self) -> list[str]:
        """Create missing agents and reconcile the declared fields of existing ones.

        Insert-if-absent was not enough, and production proved it. The operational heartbeat
        was scheduled against an agent with no permission for it; the fix added the permission
        to DEFAULT_AGENTS, the fix deployed, and the heartbeat kept failing -- because the
        agent row already existed and was never revisited. A permission that lives in code and
        cannot reach the database is not a permission, it is a comment.

        So permissions and ceilings are declarative: the code is the source of truth, a deploy
        applies it, and changing an agent's authority means changing it where it can be
        reviewed. Returns a description of what moved, which the caller logs.
        """
        changes: list[str] = []
        with self.db.session() as s:
            for spec in DEFAULT_AGENTS:
                agent = s.scalar(select(Agent).where(Agent.name == spec["name"]))
                if agent is None:
                    s.add(Agent(**spec))
                    changes.append(f"created {spec['name']}")
                    continue
                for field in self.DECLARED_FIELDS:
                    if field not in spec:
                        continue
                    current, declared = getattr(agent, field), spec[field]
                    if current != declared:
                        setattr(agent, field, declared)
                        changes.append(f"{spec['name']}.{field}: {current!r} -> {declared!r}")
        return changes

    def get(self, name: str) -> Agent:
        with self.db.session() as s:
            a = s.scalar(select(Agent).where(Agent.name == name))
            if a is None:
                raise PermissionDenied(f"unknown agent {name!r}")
            s.expunge(a)
            return a

    def all(self) -> list[Agent]:
        with self.db.session() as s:
            agents = list(s.scalars(select(Agent).order_by(Agent.name)))
            for a in agents:
                s.expunge(a)
            return agents

    def authorize(self, agent_name: str, job_type: str) -> Agent:
        """Raise unless this agent is allowed to run this job type right now."""
        agent = self.get(agent_name)
        forbidden = FORBIDDEN_COMBINATIONS.get(agent_name, set())
        if job_type in forbidden:
            raise PermissionDenied(
                f"agent {agent_name!r} is structurally forbidden from {job_type!r}"
            )
        if not agent.may_run(job_type):
            raise PermissionDenied(
                f"agent {agent_name!r} may not run {job_type!r} "
                f"(allowed: {agent.allowed_job_types})"
            )
        return agent

    # ---- cost ceilings -------------------------------------------------
    def spend_today(self, agent_name: str) -> float:
        today = date.today().isoformat()
        with self.db.session() as s:
            entries = s.scalars(select(CostEntry).where(CostEntry.agent == agent_name))
            return round(
                sum(e.amount_cad for e in entries if e.at.date().isoformat() == today), 4
            )

    def record_cost(
        self, agent_name: str, amount_cad: float, *, kind: str = "llm",
        job_id: int | None = None, tokens_in: int = 0, tokens_out: int = 0,
        detail: dict | None = None,
    ) -> None:
        agent = self.get(agent_name)
        if self.spend_today(agent_name) + amount_cad > agent.daily_cost_ceiling_cad:
            raise BudgetExceeded(
                f"agent {agent_name!r} would exceed its daily ceiling of "
                f"CA${agent.daily_cost_ceiling_cad:.2f}"
            )
        with self.db.session() as s:
            s.add(CostEntry(
                agent=agent_name, amount_cad=amount_cad, kind=kind, job_id=job_id,
                tokens_in=tokens_in, tokens_out=tokens_out, detail=detail or {},
            ))

    # ---- audit ---------------------------------------------------------
    def audit(
        self, actor: str, action: str, *, artifact: str | None = None,
        job_id: int | None = None, phase: Phase | None = None,
        model_version: str | None = None, policy_version: str | None = None,
        detail: dict | None = None,
    ) -> None:
        with self.db.session() as s:
            s.add(AuditLog(
                actor=actor, action=action, artifact=artifact, job_id=job_id, phase=phase,
                model_version=model_version, policy_version=policy_version,
                detail=detail or {},
            ))

    def audit_trail(self, artifact: str | None = None, limit: int = 100) -> list[AuditLog]:
        with self.db.session() as s:
            q = select(AuditLog).order_by(AuditLog.id.desc()).limit(limit)
            if artifact:
                q = q.where(AuditLog.artifact == artifact)
            rows = list(s.scalars(q))
            for r in rows:
                s.expunge(r)
            return rows


class SpendGuard:
    """Hard money caps enforced before any spend, with automatic pause (section 11).

    Returns/raises rather than trusting a caller to check: `authorize_spend` is the only way
    to legitimately spend, and it refuses rather than warns.
    """

    def __init__(self, db: Database):
        self.db = db

    def set_limit(self, scope: str, daily_cap_cad: float, lifetime_cap_cad: float) -> None:
        with self.db.session() as s:
            lim = s.scalar(select(SpendLimit).where(SpendLimit.scope == scope))
            if lim is None:
                lim = SpendLimit(scope=scope)
                s.add(lim)
            lim.daily_cap_cad = daily_cap_cad
            lim.lifetime_cap_cad = lifetime_cap_cad
            lim.day = date.today().isoformat()

    def _roll_day(self, lim: SpendLimit) -> None:
        today = date.today().isoformat()
        if lim.day != today:
            lim.day = today
            lim.spent_today_cad = 0.0

    def authorize_spend(self, scope: str, amount_cad: float) -> None:
        """Refuse and pause the scope if this spend would breach a cap.

        The breach is recorded and committed *before* raising. Raising inside the session
        would roll the `paused` flag back with the transaction, so a breach would refuse one
        spend and then quietly allow the next -- precisely the failure this guard exists to
        prevent.
        """
        breach: str | None = None
        with self.db.session() as s:
            lim = s.scalar(select(SpendLimit).where(SpendLimit.scope == scope))
            if lim is None:
                breach = f"no spend limit configured for {scope!r}; refusing to spend"
            else:
                self._roll_day(lim)
                if lim.paused:
                    breach = f"spend scope {scope!r} is paused"
                elif lim.spent_today_cad + amount_cad > lim.daily_cap_cad:
                    lim.paused = True
                    breach = (
                        f"daily cap breached for {scope!r}: CA${lim.spent_today_cad:.2f} + "
                        f"CA${amount_cad:.2f} > CA${lim.daily_cap_cad:.2f} -- scope paused"
                    )
                elif lim.spent_lifetime_cad + amount_cad > lim.lifetime_cap_cad:
                    lim.paused = True
                    breach = (
                        f"lifetime cap breached for {scope!r}: "
                        f"CA${lim.spent_lifetime_cad:.2f} + CA${amount_cad:.2f} > "
                        f"CA${lim.lifetime_cap_cad:.2f} -- scope paused"
                    )
                else:
                    lim.spent_today_cad += amount_cad
                    lim.spent_lifetime_cad += amount_cad
        if breach:
            raise BudgetExceeded(breach)

    def status(self, scope: str) -> SpendLimit | None:
        with self.db.session() as s:
            lim = s.scalar(select(SpendLimit).where(SpendLimit.scope == scope))
            if lim:
                s.expunge(lim)
            return lim

    def pause(self, scope: str) -> None:
        with self.db.session() as s:
            lim = s.scalar(select(SpendLimit).where(SpendLimit.scope == scope))
            if lim:
                lim.paused = True
