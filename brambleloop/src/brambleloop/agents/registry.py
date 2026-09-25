"""Agent registry, permissions, budget ceilings and the audit log (sections 14, 26).

The governance rules exist because a single over-permissive agent is how an autonomous
company quietly does something irreversible. Listing cannot spend ad money. Marketing cannot
alter CIR. Designer cannot publish. Support cannot silently patch canonical patterns.

These are enforced here in code, not asserted in a prompt.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Iterable

from sqlalchemy import select

from ..core.db import Database, is_postgres
from ..core.models import (
    Agent, Authority, AuditLog, CostEntry, Job, Phase, SpendLimit, utcnow,
)


def _utc_date(value: datetime):
    """The UTC calendar date of a timestamp, whether or not it carries a timezone.

    SQLite hands back naive datetimes and Postgres hands back aware ones, and the naive ones
    are UTC by construction (`utcnow` writes them). Comparing the two without saying so is
    how a day boundary becomes a coin toss.
    """
    return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).astimezone(
        timezone.utc).date()


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
                            "ops.capacity", "ops.sentinel", "ops.health", "model.probe",
                            "improve.nightly", "improve.weekly",
                            # The three gates that stopped reading environment variables
                            # need something to keep asking whether the capability still
                            # works. Three reads and a fraction of a cent (B-479).
                            "ops.capability_probes",
                            # The off-provider half of #51. Separate from `ops.continuity`
                            # because a local restore proving out is not an archive existing
                            # anywhere this provider's failure would not reach (B-524).
                            "ops.offsite_archive",
                            # Retention (2026-09-25). Nothing pruned anything: 4,700 audit
                            # rows a day, 900 jobs, 21 dead letters, on the database that is
                            # the main cost under the CA$20/month infrastructure ceiling.
                            # `ops.retention` holds the policy and refuses to run when the
                            # code reads an audit action it has no decision about.
                            "ops.retention"],
         authority=Authority.GREEN,
         daily_cost_ceiling_cad=3.0),
    dict(name="market_radar", description="Discovery, category, trend and seasonality scanning",
         allowed_job_types=["radar.scan", "radar.score", "radar.competitor_snapshot",
                            "mjs.scan", "mjs.reviews", "etsy.probe",
                            # A free keyless sanctioned read, and the gallery backlog that
                            # was waiting on a call nobody had written rather than on a
                            # capability anybody had to buy (B-478, B-483).
                            "culture.sweep", "intel.gallery_analysis"],
         authority=Authority.GREEN, daily_cost_ceiling_cad=4.0),
    # The creative side of #94: it judges this catalogue against an observed human one and
    # records the result. It writes no product, publishes nothing and contacts nobody; the
    # only thing it spends is model budget, which the gateway's ceiling bounds before each
    # call. Its own daily ceiling is set low on purpose -- a capability measurement that can
    # consume a day's whole model allowance is a measurement nobody can afford to repeat.
    dict(name="creative_director",
         description="Blinded creative benchmarking and product discovery (#94, #104, #3)",
         allowed_job_types=["creative.blinded", "creative.expedition",
                            "creative.tournament",
                            # The image-provider benchmark (owner decision 2026-09-20).
                            # It is the one job here that can spend double figures in a
                            # sitting, which is why it carries its own daily ceiling below.
                            "creative.image_benchmark",
                            # The canonical-model tournament (#199). It renders a field and
                            # stress-tests finalists; it cannot select one.
                            "creative.model_tournament",
                            # The reference pack built from the owner's own candidate
                            # (2026-09-21). It renders two reference frames and the
                            # controlled scenes and measures them; it cannot freeze an
                            # identity either.
                            "creative.model_reference_pack",
                            # Freezing the pack the owner approved, and proving the gate
                            # on it afterwards. Writes one row and spends nothing
                            # (#200, #201; owner approval 2026-09-22).
                            "creative.model_freeze",
                            # Asking the photographic-realism judge whether it can pass a
                            # photograph nobody generated. One vision call about a public
                            # benchmark image; renders nothing and copies nothing
                            # (2026-09-22, after two renders were blocked on checks a real
                            # photograph might not have cleared either).
                            "creative.photoreal_calibration"],
         # Three cadences landing on one day: the expedition at about CA$1.02, the blinded
         # run at CA$0.15 and the tournament at about CA$0.27. The ceiling is set above that
         # sum rather than at it, because a ceiling a normal week touches is a ceiling that
         # stops work rather than one that catches a runaway.
         # Raised from 2.5 for the image benchmark, which is a one-off measurement of up to
         # CA$25 that the owner approved as a separate budget. A ceiling that stops the very
         # job it was raised for is the shape of guard this build keeps having to fix.
         authority=Authority.GREEN, daily_cost_ceiling_cad=28.0),
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
         allowed_job_types=["assets.build", "assets.render",
                            # A styled image of the finished object, generated from the
                            # certified CIR and disclosed as an illustration (#292, #300).
                            "assets.owned_photography",
                            # #300's cycle run as a job, so its assets link can be closed
                            # for the product the cycle itself engineered rather than for
                            # whichever product was photographed last (B-611).
                            "seasonal.cycle_proof",
                            # A listing frame with the canonical model in it, conditioned
                            # on the frozen pack and verified afterwards (#72, #130, #202).
                            "assets.model_photography",
                            # Whether the tiling blocker is specific to the incumbent image
                            # provider. Owner-authorised 2026-09-23 up to CA$4.00 -- but
                            # this agent's daily ceiling is CA$2.00 and is NOT raised for
                            # it, so the binding limit is the lower of the two. A standing
                            # spend control does not get widened to fit an experiment; the
                            # experiment is sized to fit the control.
                            "visual.provider_trial",
                            # A bounded repair attempt on the approved canonical portrait,
                            # owner-authorised 2026-09-23 inside a CA$1.00 ceiling. It
                            # adopts nothing: the reference is replaced only on the owner's
                            # visual approval of the side-by-side evidence.
                            "visual.portrait_repair"],
         authority=Authority.GREEN,
         daily_cost_ceiling_cad=2.0),
    dict(name="growth", description="Launch timing and marketing cadence. Cannot author patterns.",
         allowed_job_types=["launch.plan", "marketing.schedule", "content.draft"],
         authority=Authority.GREEN,
         daily_cost_ceiling_cad=2.0),
    dict(name="listing", description="Drafts listings and SEO. Cannot spend ad money.",
         allowed_job_types=["seasonal.remerchandising",
                            "listing.draft", "listing.seo", "collection.assemble",
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
# The eight meta-agents of #179, generated from the roster rather than retyped, because two
# lists of the same eight roles drift and the drift is silent: an agent here with no role in
# `improve.roles` would have authority over nothing, and a role there with no agent would be
# a job description nobody holds.
#
# All GREEN and all cheap. Each reads the rows it answers for and reports what it found; none
# of them proposes or promotes, because proposing runs through #190's pipeline and promotion
# through #178's tiers. The daily ceiling is nominal rather than absent: these are database
# reads, and a meta-agent that can spend real money to decide whether somebody else should
# have spent money is the wrong shape.
def _meta_agents() -> list[dict]:
    from ..improve.roles import ROLE_JOB_TYPE, ROLES

    return [dict(name=role.key,
                 description=f"Meta-agent (#179): {role.job}",
                 allowed_job_types=[ROLE_JOB_TYPE],
                 authority=Authority.GREEN,
                 daily_cost_ceiling_cad=0.25)
            for role in ROLES]


DEFAULT_AGENTS.extend(_meta_agents())


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
    def spend_today(self, agent_name: str, *, now: datetime | None = None) -> float:
        """This agent's spend on the current UTC day.

        UTC, because every other timestamp in this system is and the rows being summed are
        written with `utcnow`. `date.today()` is the host's local day, so on any host not
        set to UTC the window being summed and the window the rows were stamped in are
        different windows -- a ceiling that resets at the wrong hour, silently, and only on
        some machines.

        `now` was added when this became a pre-call guard rather than only a post-call one.
        A ceiling check that takes a timestamp for one of its two numbers and the wall clock
        for the other is asking two clocks about the same day: it agrees with itself while
        the frozen date happens to be today and disagrees after the next UTC midnight, which
        is a defect this repository has already had twice.
        """
        today = (now or utcnow()).astimezone(timezone.utc).date()
        with self.db.session() as s:
            entries = s.scalars(select(CostEntry).where(CostEntry.agent == agent_name))
            return round(
                sum(e.amount_cad for e in entries if _utc_date(e.at) == today), 4
            )

    def record_cost(
        self, agent_name: str, amount_cad: float, *, kind: str = "llm",
        job_id: int | None = None, tokens_in: int = 0, tokens_out: int = 0,
        detail: dict | None = None,
    ) -> None:
        """Write the cost row, then refuse if this agent is over its daily ceiling.

        The order is the fix. This checked first and wrote second, so the one call that
        crossed the ceiling wrote no row at all -- the spend that breached the guard was the
        single spend the ledger did not contain. That is not a conservative failure: the
        money had already left (this is called *after* the provider answered), and the
        monthly ceiling in `gateway.anthropic.spent_this_month_cad` is computed from exactly
        these rows, so a breach of the daily ceiling quietly lowered the number the monthly
        ceiling is checked against. A guard that erases its own evidence makes the guard
        above it wrong.

        The refusal is unchanged and still raises: the caller still fails, the job still
        dead-letters, and nothing new is permitted. What changed is that the bill is now
        complete whether or not the ceiling held.
        """
        agent = self.get(agent_name)
        with self.db.session() as s:
            s.add(CostEntry(
                agent=agent_name, amount_cad=amount_cad, kind=kind, job_id=job_id,
                tokens_in=tokens_in, tokens_out=tokens_out, detail=detail or {},
            ))
        if self.spend_today(agent_name) > agent.daily_cost_ceiling_cad:
            raise BudgetExceeded(
                f"agent {agent_name!r} would exceed its daily ceiling of "
                f"CA${agent.daily_cost_ceiling_cad:.2f}"
            )

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
            lim.day = utcnow().date().isoformat()

    def _roll_day(self, lim: SpendLimit) -> None:
        # UTC, matching every timestamp this system writes. A daily cap that rolls on the
        # host's local midnight and is spent against rows stamped in UTC is a cap whose
        # window depends on a container setting nobody records.
        today = utcnow().date().isoformat()
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
            # Locked for the read-modify-write. Two authorisations arriving together both
            # read the same `spent_today_cad`, both find room, and both write their own
            # total back -- the classic lost update, and on a cap it means the second spend
            # is authorised against a balance that does not include the first. Several
            # agents now run in parallel against one database, so this is a live shape
            # rather than a theoretical one. `FOR UPDATE` is a no-op on SQLite, which
            # serialises writers anyway; it is Postgres that needs it.
            q = select(SpendLimit).where(SpendLimit.scope == scope)
            if is_postgres(self.db.engine):
                q = q.with_for_update()
            lim = s.scalar(q)
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
