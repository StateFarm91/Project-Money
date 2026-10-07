"""Which model answers which question, and the ceiling that cannot be argued with.

The governing policy lives in `finance.spend_policy` and this module obeys it: **QUALITY
FIRST, COST SECOND, WASTE NEVER**, under an authorised ceiling that is read from there rather
than restated here. And one standing rule that outranks everything — a model may never
generate canonical crochet pattern content.

**The ceiling is arithmetic, not judgement.** `Budget.check()` sums this calendar month's
`llm` cost entries and refuses a call whose estimate would cross the authorised figure. It
runs *before* the request, because a ceiling checked afterwards is a report. There is no
override parameter: the way past it is the owner raising it, which is an owner action with
measured usage attached.

**Routing is by what the task needs, and "needs" is about the answer rather than the bill.**
Reading a title into a category is not the same question as judging whether a photograph makes
a garment look desirable; the first is extraction and the second is taste, and they are routed
apart because they *are* different questions. Tiering them to save money would be the same
table with a worse reason, and the difference shows up on the day the budget rises: a routing
built on the shape of the question does not change, and one built on the price does.

**Caching is the biggest lever and it is free.** Competitor evidence is overwhelmingly
unchanged between runs (#212, #225): a listing whose fingerprint has not moved must never be
paid for twice. The cache is keyed on content, so it cannot go stale — a changed listing has a
different fingerprint and simply misses.

**Pattern content is not a model task.** `PATTERN_TASKS_REFUSED` names the things a model may
not be asked, and `route()` raises on them. The compiler decides what a pattern says; a model
that disagrees is noise (§27).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

# Anthropic's published first-party rates, USD per million tokens, and the exchange rate used
# to express the ceiling in the owner's currency. The rate is an assumption and is labelled
# one: it moves, and a ceiling quoted in CAD against a bill charged in USD has to say so.
from ..core.fx import ASSUMED_USD_PER_CAD as USD_PER_CAD  # the single assumed rate
FX_NOTE = ("model prices are published in USD; the ceiling is quoted in CAD, converted at an "
           "assumed 0.715 USD/CAD and checked against the converted figure, so a weaker "
           "dollar spends the ceiling faster rather than silently exceeding it")

CHEAP = "cheap"
STANDARD = "standard"
DEEP = "deep"


class UnpricedTier(ValueError):
    """A tier whose model the billing table does not price."""


@dataclass(frozen=True)
class Tier:
    """A model tier. Its prices are read from the table that bills, never restated here.

    They used to be restated, and the two disagreed: this file said the deep tier cost
    USD 5/25 per million tokens while the provider billed 15/75. Every estimate in the system
    was therefore a third of the truth, and the first live expedition -- estimated at CA$0.15
    a field -- cost CA$1.02. An estimate that is wrong in the cheap direction is worse than no
    estimate: it is the number a budget decision gets made on.
    """

    key: str
    model: str
    vision: bool
    use_for: str

    @property
    def _prices(self) -> tuple[float, float]:
        from .anthropic import PRICES_USD_PER_MTOK

        prices = PRICES_USD_PER_MTOK.get(self.model)
        if prices is None:
            raise UnpricedTier(
                f"tier {self.key!r} routes to {self.model!r}, which the billing table does "
                f"not price. An estimate for a model nobody can bill is a guess, and the "
                f"call it authorises is unbounded")
        return prices

    @property
    def usd_per_1m_input(self) -> float:
        return self._prices[0]

    @property
    def usd_per_1m_output(self) -> float:
        return self._prices[1]

    def cost_cad(self, tokens_in: int, tokens_out: int) -> float:
        usd = (tokens_in / 1_000_000 * self.usd_per_1m_input
               + tokens_out / 1_000_000 * self.usd_per_1m_output)
        return round(usd / USD_PER_CAD, 6)


TIERS: dict[str, Tier] = {
    CHEAP: Tier(
        CHEAP, "claude-haiku-4-5", vision=True,
        use_for="classification, extraction and routing — high volume, low judgement"),
    STANDARD: Tier(
        STANDARD, "claude-sonnet-5", vision=True,
        use_for="image-level observation and listing copy — judgement at volume"),
    DEEP: Tier(
        DEEP, "claude-opus-5", vision=True,
        use_for="creative evaluation and the benchmark challenge — where being wrong is "
                "expensive and the call is made a handful of times"),
}


# Every Build-2 task a model is allowed to do, with the tier that answers it and a token
# estimate used for the pre-call budget check. "Start economically" is encoded here: the
# expensive tier is reserved for the judgements that decide what ships.
@dataclass(frozen=True)
class Task:
    key: str
    tier: str
    max_output_tokens: int
    typical_input_tokens: int
    cacheable: bool
    why: str
    # False: an optional nicety that parks (and its caller falls back to deterministic text)
    # rather than paying a stronger tier when its own model is down or unaffordable.
    stronger_fallback: bool = True


TASKS: dict[str, Task] = {
    "listing_classify": Task(
        "listing_classify", CHEAP, 256, 900, True,
        "route a benchmark listing to a pod when the keyword rules return unclassified"),
    "listing_mechanisms": Task(
        "listing_mechanisms", CHEAP, 800, 2000, True,
        "extract merchandising mechanisms from listing text — structured reading, not taste"),
    # Filing a discovered topic into the radar's ten domains. Cheap tier, and the reason is
    # the question: this is extraction against a closed vocabulary, not taste. The test that
    # it is the right tier is that the answer would not improve on a stronger model -- the
    # domains are disjoint and a topic either is a television series or is not.
    "topic_filing": Task(
        "topic_filing", CHEAP, 1500, 1200, True,
        "file discovered cultural topics into the ten mandated domains (#133)"),
    "seasonal_signal": Task(
        "seasonal_signal", CHEAP, 400, 1200, True,
        "classify a trend's half-life and seasonal fit (#290)"),
    # Standard tier, and the reason is the question rather than the price. Judging what a
    # photograph does commercially is taste, not extraction -- #209's vocabulary is shot
    # type, composition, scale communication and emotional merchandising, and a model that
    # reads a title well is not thereby a model that reads a gallery well.
    #
    # Reconciled 2026-09-20: `intel.vision` was calling the cheap tier directly and
    # bypassing this table entirely, so the declared tier said one thing and the code did
    # another for a day. MJs intelligence is the owner's second spending priority and
    # visual-analysis depth is named as something not to reduce for cost, which made the
    # bypass a policy breach as well as an inconsistency.
    "gallery_observation": Task(
        "gallery_observation", STANDARD, 1200, 3000, True,
        "shot type, composition, styling and thumbnail legibility from a public image URL "
        "(#209) — the part of the mandate the Etsy API cannot answer"),
    # The construction reading behind #278 and #116: neckline, sleeve treatment, colour
    # blocking, proportion. Deep tier, because this is the evidence a concept brief is
    # written from and a misread construction detail becomes a design constraint nobody
    # questions afterwards.
    "construction_reading": Task(
        "construction_reading", DEEP, 700, 2600, True,
        "how a competitor object is built and presented, never what it depicts (#278, #116)"),
    # Our own rendered assets, judged before release. Standard rather than cheap: #61 asks
    # whether an image communicates what its caption claims, which is a judgement, and #79's
    # ten realism checks are a maker's eye rather than a classifier's.
    "asset_inspection": Task(
        "asset_inspection", STANDARD, 900, 2600, False,
        "describe a rendered Brambleloop asset and judge its physical realism (#61, #79)"),
    # Choosing the image generator. Deep tier on purpose: this judgement is made a few dozen
    # times and decides which provider renders every listing image afterwards.
    "image_benchmark_judging": Task(
        "image_benchmark_judging", DEEP, 500, 2600, False,
        "score one rendered candidate image against the visual requirements, blind"),
    "listing_copy": Task(
        "listing_copy", STANDARD, 1500, 2500, False,
        "customer-facing listing copy in the brand voice. Never pattern instructions"),
    "creative_evaluation": Task(
        "creative_evaluation", DEEP, 2000, 4000, False,
        "is this concept commercially desirable and distinctive, or merely correct (#218)"),
    # The tournament's ideation stage (#3). Cheap tier on purpose, and the requirement says
    # why: "generate roughly 75-100 **inexpensive** concepts". A hundred concepts at the deep
    # tier costs about CA$5.70 and is the opposite of what that sentence asks for -- the
    # whole shape of the funnel is to spend little on a wide field and concentrate cost only
    # after the field has been cut. Batched twelve at a time, a hundred concepts costs about
    # CA$0.30.
    "concept_ideation": Task(
        "concept_ideation", CHEAP, 4000, 1600, False,
        "a wide, cheap field for the tournament's ideation stage (#3)"),
    # Discovery into a proven arena. Deep tier on purpose: this is the call that decides
    # what the company tries to sell, and the owner's standing instruction is not to quietly
    # trade creative quality for trivial savings. Batched -- one call proposes a whole field,
    # which is both cheaper per concept and produces internal variety, because a model asked
    # for five different things at once cannot answer with the same thing five times.
    "concept_generation": Task(
        "concept_generation", DEEP, 4000, 1600, False,
        "propose a field of concepts for one form in one proven arena (#104, #106-#115)"),
    # Optional owner-facing phrasing of a business statement Laura already decided in code
    # (lane F). Cheap tier because the question is rewording, not judgement: every fact, figure
    # and decision is supplied, and `gateway.laura_phrase` refuses any answer that adds a
    # number the facts did not contain. Small output budget, no stronger fallback, its own
    # allocation stop, and a deterministic sentence whenever it is not worth paying for.
    "laura.business_phrase": Task(
        "laura.business_phrase", CHEAP, 220, 700, True,
        "reword a decided business statement in Laura's voice; facts are supplied, so this "
        "is rephrasing against fixed content rather than judgement", stronger_fallback=False),
    "benchmark_challenge": Task(
        "benchmark_challenge", DEEP, 2500, 6000, False,
        "blinded comparison against category-matched benchmark evidence (#315) — "
        "release-blocking, so it gets the model that is right most often"),
}

# Questions a model may not be asked at all, whatever the budget. Deterministic code already
# answers them, and §27 says deterministic validation wins even if every model disagrees.
PATTERN_TASKS_REFUSED: tuple[str, ...] = (
    "pattern_instructions", "stitch_counts", "row_instructions", "cir_generation",
    "finished_dimensions", "yardage", "gauge", "chart_symbols", "pattern_correction",
)

# F-312 (Deterministic Before Generative): every question deterministic code already answers,
# with the code that answers it (`module:function`). `route()` refuses each of them by naming
# that alternative, so the refusal is a pointer to the free answer rather than a dead end, and
# `tests/test_w4_spend_routing.py` imports every target -- an alternative that does not exist
# is not one. The pattern questions are the compiler's (§27); the gallery-structure questions
# are answered by `visual.parity` from the frames themselves (GALLERY / BRAND dimensions) and
# sizing by `cir.grading`. A declared model task may never shadow one of these keys.
DETERMINISTIC_ALTERNATIVES: dict[str, str] = {
    "pattern_instructions": "brambleloop.cir.writer:write_pattern",
    "stitch_counts": "brambleloop.cir.compiler:compile_cir",
    "row_instructions": "brambleloop.cir.writer:write_row",
    "cir_generation": "brambleloop.cir.specification:refuse_an_underspecified_design",
    "finished_dimensions": "brambleloop.cir.twin:build_twin",
    "yardage": "brambleloop.cir.twin:build_twin",
    "gauge": "brambleloop.cir.grading:grade",
    "chart_symbols": "brambleloop.cir.stitches:term",
    "pattern_correction": "brambleloop.cir.compiler:compile_cir",
    "size_grading": "brambleloop.cir.grading:grade",
    "gallery_sequence_completeness": "brambleloop.visual.parity:assess",
    "gallery_brand_consistency": "brambleloop.visual.parity:assess",
}

# F-316 (Output Token Discipline): the same cap `prompts.register` enforces, read from there.
from .prompts import OUTPUT_TOKEN_CAP  # noqa: E402

# Read from the policy rather than restated. It was written twice -- here and in the provider
# gateway -- which is the defect this build keeps naming about prices: a number written twice
# is a number that will drift, and the one that bills is the one that is true. A test refuses
# a second literal.
def _ceiling() -> float:
    from ..finance.spend_policy import ceiling_cad

    return ceiling_cad()


MONTHLY_CEILING_CAD = _ceiling()
SCOPE = "model_provider"


class CeilingReached(PermissionError):
    """The month's approved model budget is spent. Not overridable in code."""


class TaskRefused(PermissionError):
    """A task a model may not be given, or one nobody has declared."""


def route(task_key: str) -> tuple[Task, Tier]:
    """Pick the tier for a declared task, refusing anything the compiler owns."""
    if task_key in PATTERN_TASKS_REFUSED or task_key in DETERMINISTIC_ALTERNATIVES:
        raise TaskRefused(
            f"{task_key!r} is decided by deterministic code, not by a model "
            f"({DETERMINISTIC_ALTERNATIVES.get(task_key, 'the compiler')} answers it, free). "
            f"Patterns are software releases: the compiler and the twin answer this, and a "
            f"model that disagrees is noise (§27)")
    task = TASKS.get(task_key)
    if task is None:
        raise TaskRefused(
            f"{task_key!r} is not a declared model task. Adding one is a deliberate change to "
            f"TASKS with a tier and a token estimate, so the monthly ceiling can be checked "
            f"before the call rather than discovered after it")
    return task, TIERS[task.tier]


def estimate_cad(task_key: str) -> float:
    task, tier = route(task_key)
    return tier.cost_cad(task.typical_input_tokens, task.max_output_tokens)


# ---------------------------------------------------------------------------
# The ceiling


def month_key(now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    return f"{now:%Y-%m}"


@dataclass(frozen=True)
class BudgetState:
    month: str
    spent_cad: float
    ceiling_cad: float

    @property
    def remaining_cad(self) -> float:
        return round(max(0.0, self.ceiling_cad - self.spent_cad), 4)

    @property
    def share_used(self) -> float:
        return round(self.spent_cad / self.ceiling_cad, 4) if self.ceiling_cad else 1.0

    def to_dict(self) -> dict:
        return {"month": self.month, "spent_cad": round(self.spent_cad, 4),
                "ceiling_cad": self.ceiling_cad, "remaining_cad": self.remaining_cad,
                "share_used": self.share_used,
                "note": ("The ceiling is a maximum, not a target. Spending less of it is a "
                         "better month, not an underused resource.")}


# The ledger row kind the monthly ceiling counts. It is a constant because it was a literal
# in four places and one of them disagreed: `ModelGateway` recorded its calls as "model"
# while every ceiling reads "llm", so a real gateway call would have been invisible to the
# budget and the ceiling would have read CA$0.00 forever while money left the account. It
# never bit only because nothing had ever constructed a ModelGateway.
COST_KIND = "llm"

# The kind an image render's ledger row carries (RC1 audit B2). `images.generate` writes one
# for every render the provider billed; before it did, render spend lived only in a released
# reservation and vanished from the month the moment the reservation was given back.
IMAGE_COST_KIND = "image"

# Spend kinds governed by a ceiling *other* than the model/vision/image month, and only those,
# are left out of it. Everything else counts -- including a kind nobody has invented yet -- so
# the monthly ceiling fails closed: a new way to spend money is inside the ceiling until
# somebody decides, in this tuple, which other ceiling governs it.
#   * etsy_listing_fee(_actual): serialised and capped by `finance.listing_costs.reserve`;
#   * hosting / software: the separate infrastructure ceiling (`spend_policy.INFRA_CEILING_CAD`).
SEPARATELY_GOVERNED_KINDS = ("etsy_listing_fee", "etsy_listing_fee_actual",
                             "hosting", "software")


def counts_against_monthly_ceiling(kind: str | None) -> bool:
    """Whether a ledger row of this kind is spend the CA$ monthly model ceiling governs."""
    return (kind or "") not in SEPARATELY_GOVERNED_KINDS


def ceiling_kind_filter():
    """SQL predicate for `counts_against_monthly_ceiling` (NULL kind counts: unknown is not
    exempt)."""
    from sqlalchemy import or_

    from ..core.models import CostEntry

    return or_(CostEntry.kind.is_(None),
               CostEntry.kind.notin_(SEPARATELY_GOVERNED_KINDS))


def spent_this_month(db, now: datetime | None = None) -> float:
    """What the month's ceiling-governed spend has cost, from the ledger that records it.

    Every kind the monthly ceiling governs (`counts_against_monthly_ceiling`), not only
    `llm`: image renders are recorded as `image` and are inside the same CA$ month.
    """
    from sqlalchemy import func, select

    from ..core.models import CostEntry

    now = now or datetime.now(timezone.utc)
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    with db.session() as s:
        total = s.scalar(
            select(func.coalesce(func.sum(CostEntry.amount_cad), 0.0))
            .where(ceiling_kind_filter(), CostEntry.at >= start))
    return float(total or 0.0)


def budget(db, now: datetime | None = None,
           ceiling_cad: float = MONTHLY_CEILING_CAD) -> BudgetState:
    return BudgetState(month_key(now), spent_this_month(db, now), ceiling_cad)


def check(db, task_key: str, *, now: datetime | None = None,
          ceiling_cad: float = MONTHLY_CEILING_CAD) -> BudgetState:
    """Refuse before the call if this task would cross the month's ceiling.

    Before, not after. A ceiling checked after the request is a report about an overspend, and
    the owner approved a maximum rather than a target.
    """
    state = budget(db, now, ceiling_cad)
    cost = estimate_cad(task_key)
    if state.spent_cad + cost > state.ceiling_cad:
        raise CeilingReached(
            f"{task_key!r} would cost about CA${cost:.4f} and CA${state.spent_cad:.2f} of the "
            f"CA${state.ceiling_cad:.2f} month is already spent. Work that does not need a "
            f"model continues; raising the ceiling is an owner decision and needs measured "
            f"usage, the capability gap and the expected value attached")
    return state


def record(db, task_key: str, *, agent: str, tokens_in: int, tokens_out: int,
           cached: bool = False, job_id: int | None = None) -> float:
    """Ledger what a call actually cost, which is what the ceiling is checked against."""
    from ..core.models import CostEntry

    task, tier = route(task_key)
    cost = 0.0 if cached else tier.cost_cad(tokens_in, tokens_out)
    with db.session() as s:
        s.add(CostEntry(agent=agent, job_id=job_id, kind=COST_KIND, amount_cad=cost,
                        tokens_in=0 if cached else tokens_in,
                        tokens_out=0 if cached else tokens_out,
                        detail={"task": task_key, "tier": tier.key, "model": tier.model,
                                "cached": cached}))
    return cost


# ---------------------------------------------------------------------------
# Reuse (#225)


def fingerprint(payload: dict) -> str:
    """Content identity. A changed listing has a different key and simply misses."""
    from .evidence_key import content

    return content(payload)


def cache_key(task_key: str, payload: dict) -> str:
    task, tier = route(task_key)
    # The model is part of the key: the same question answered by a cheaper model is a
    # different answer, and silently serving it would make a routing change invisible.
    return f"{task_key}:{tier.model}:{fingerprint(payload)}"


def cached_analysis(db, task_key: str, payload: dict) -> dict | None:
    """Return a previous answer for identical content, or None.

    Competitor evidence barely changes between runs, so this is the difference between
    re-reading a catalogue every night and reading only what moved.
    """
    from sqlalchemy import desc, select

    from ..core.models import AuditLog

    key = cache_key(task_key, payload)
    with db.session() as s:
        rows = list(s.scalars(
            select(AuditLog).where(AuditLog.action == "model.analysis",
                                   AuditLog.artifact == key)
            .order_by(desc(AuditLog.id)).limit(1)))
    return (rows[0].detail or {}).get("result") if rows else None


def remember_analysis(db, task_key: str, payload: dict, result: dict,
                      *, agent: str = "orchestrator") -> str:
    from ..agents.registry import Registry

    key = cache_key(task_key, payload)
    Registry(db).audit(agent, "model.analysis", artifact=key,
                       detail={"task": task_key, "result": result})
    return key


def plan(db, now: datetime | None = None) -> dict:
    """What the routing costs and what is left, for the owner rather than for a log."""
    state = budget(db, now)
    return {
        "budget": state.to_dict(),
        "fx": FX_NOTE,
        "tiers": {k: {"model": t.model, "usd_per_1m_input": t.usd_per_1m_input,
                      "usd_per_1m_output": t.usd_per_1m_output, "use_for": t.use_for}
                  for k, t in TIERS.items()},
        "tasks": {k: {"tier": t.tier, "model": TIERS[t.tier].model,
                      "estimated_cad_per_call": estimate_cad(k),
                      "cacheable": t.cacheable, "why": t.why}
                  for k, t in TASKS.items()},
        "refused": list(PATTERN_TASKS_REFUSED),
        "note": ("Canonical pattern content is never a model task. The compiler and the twin "
                 "decide what a pattern says, and a model that disagrees is noise (§27)."),
    }


# ---------------------------------------------------------------------------
# Quality-proven routing (F-313) and deep-tier escalation (F-314)
#
# The table above is the declared route. It may move a task to a *cheaper* tier only on
# recorded evidence that the cheaper model clears the same quality floors on the same eval set
# -- never on an argument about money (`spend_policy.may_downgrade_for_cost` refuses that by
# name), and never for longer than the evidence holds: a later recorded regression of the
# cheaper model on that task ends the override with no further action. A route *up* is a
# quality decision and needs no equivalence proof, so `effective_route` only ever reads
# downgrades from here. Everything is an audit row, so a routing change is evidence-backed,
# reversible and inspectable rather than an edit nobody can explain.

ROUTE_EVIDENCE_ACTION = "routing.evidence"
ROUTE_OVERRIDE_ACTION = "routing.override"
# The smallest eval set that can authorise a downgrade. Below it a pass rate is an anecdote.
MIN_EVIDENCE_ITEMS = 20
TIER_ORDER = (CHEAP, STANDARD, DEEP)


class RouteRefused(PermissionError):
    """A routing override without the evidence that would make it a quality decision."""


def _tier_rank(tier_key: str) -> int:
    return TIER_ORDER.index(tier_key)


def record_route_evidence(db, task_key: str, model: str, *, floors: dict[str, bool],
                          items: int, eval_ref: str, agent: str = "orchestrator") -> dict:
    """One eval result for (task, model): which quality floors it cleared, over how many items.

    Written by whatever ran the eval (`gateway.evals`, an improve/ experiment, a gateway eval
    row). A regression is simply a later row with a floor that failed.
    """
    from ..agents.registry import Registry

    route(task_key)                                   # refuses undeclared/compiler tasks
    if not floors:
        raise RouteRefused("route evidence names no quality floors; it proves nothing")
    if not eval_ref:
        raise RouteRefused("route evidence must cite the eval it came from")
    detail = {"task": task_key, "model": model, "floors": {k: bool(v) for k, v in
                                                           floors.items()},
              "items": int(items), "eval_ref": eval_ref}
    Registry(db).audit(agent, ROUTE_EVIDENCE_ACTION, artifact=f"{task_key}:{model}"[:200],
                       detail=detail)
    return detail


def _latest_evidence(db, task_key: str, model: str) -> dict | None:
    from sqlalchemy import desc, select

    from ..core.models import AuditLog

    with db.session() as s:
        row = s.scalars(select(AuditLog).where(
            AuditLog.action == ROUTE_EVIDENCE_ACTION,
            AuditLog.artifact == f"{task_key}:{model}"[:200])
            .order_by(desc(AuditLog.id)).limit(1)).first()
        return dict(row.detail or {}, audit_id=row.id) if row else None


def equivalence(db, task_key: str, to_tier: str) -> dict:
    """Whether recorded evidence shows `to_tier`'s model clears every floor the declared model
    clears on this task, on the same eval set, with enough items. Writes nothing."""
    task, declared = route(task_key)
    cheaper = TIERS[to_tier]
    base = _latest_evidence(db, task_key, declared.model)
    cand = _latest_evidence(db, task_key, cheaper.model)
    reasons = []
    if base is None:
        reasons.append(f"no recorded evidence for the declared model {declared.model}")
    if cand is None:
        reasons.append(f"no recorded evidence for {cheaper.model} on {task_key}")
    if base and cand:
        if base.get("eval_ref") != cand.get("eval_ref"):
            reasons.append("the two models were not measured on the same eval set")
        if min(int(base.get("items") or 0), int(cand.get("items") or 0)) < MIN_EVIDENCE_ITEMS:
            reasons.append(f"fewer than {MIN_EVIDENCE_ITEMS} eval items")
        floors = base.get("floors") or {}
        missing = [f for f in floors if f not in (cand.get("floors") or {})]
        failed = [f for f, ok in (cand.get("floors") or {}).items() if not ok]
        if missing:
            reasons.append(f"floors not measured on {cheaper.model}: {sorted(missing)}")
        if failed:
            reasons.append(f"{cheaper.model} failed floors {sorted(failed)}")
    return {"task": task_key, "from": declared.model, "to": cheaper.model,
            "equivalent": not reasons, "reasons": reasons,
            "evidence": {"declared": base, "candidate": cand}}


def override_route(db, task_key: str, to_tier: str, *, reason: str,
                   agent: str = "orchestrator") -> dict:
    """Move a task to a cheaper tier -- only on recorded equivalence, never on cost."""
    from ..agents.registry import Registry
    from ..finance import spend_policy

    task, declared = route(task_key)
    if to_tier not in TIERS:
        raise RouteRefused(f"unknown tier {to_tier!r}")
    if _tier_rank(to_tier) >= _tier_rank(task.tier):
        raise RouteRefused(
            f"{task_key} is already on {task.tier}; an override only records a downgrade, "
            f"and moving a task up is a TASKS edit, not an evidence question")
    eq = equivalence(db, task_key, to_tier)
    if not eq["equivalent"]:
        # The argument offered is money if no evidence carries it -- refused by name.
        try:
            spend_policy.may_downgrade_for_cost(priority_key="high_value_judgement",
                                                reason=reason)
        except spend_policy.PolicyRefused as exc:
            raise RouteRefused(f"{exc}. Missing evidence: {'; '.join(eq['reasons'])}") from exc
    detail = {"task": task_key, "from_tier": task.tier, "to_tier": to_tier,
              "reason": reason, "evidence": {
                  "declared": (eq["evidence"]["declared"] or {}).get("audit_id"),
                  "candidate": (eq["evidence"]["candidate"] or {}).get("audit_id")}}
    Registry(db).audit(agent, ROUTE_OVERRIDE_ACTION, artifact=task_key[:200], detail=detail)
    return detail


def effective_route(db, task_key: str) -> tuple[Task, Tier, dict]:
    """The route in force: the declared one, or an evidenced override that still holds.

    Re-checked on every read, so a regression recorded after the override reverses it.
    """
    from sqlalchemy import desc, select

    from ..core.models import AuditLog

    task, declared = route(task_key)
    with db.session() as s:
        row = s.scalars(select(AuditLog).where(
            AuditLog.action == ROUTE_OVERRIDE_ACTION, AuditLog.artifact == task_key[:200])
            .order_by(desc(AuditLog.id)).limit(1)).first()
        override = dict(row.detail or {}) if row else None
    if not override:
        return task, declared, {"basis": "declared"}
    to_tier = override.get("to_tier")
    if to_tier not in TIERS or _tier_rank(to_tier) >= _tier_rank(task.tier):
        return task, declared, {"basis": "declared", "ignored_override": override}
    eq = equivalence(db, task_key, to_tier)
    if not eq["equivalent"]:
        return task, declared, {"basis": "declared", "override_reversed": eq["reasons"]}
    return task, TIERS[to_tier], {"basis": "evidenced_override", "override": override}


# F-314: escalation. A cheap or standard answer that says it is unsure, or that cannot be
# verified, is asked once more on the next stronger tier rather than shipped. Deep has nowhere
# to go, so a deep answer that is unsure is returned as unsure for the caller to treat as
# unjudged. An answer that reports nothing about its own confidence is not escalated: absence
# of a confidence field is not low confidence.
ESCALATE_BELOW_CONFIDENCE = 0.6
UNSURE_MARKERS = ("unsure", "uncertain", "cannot_tell", "unverifiable", "insufficient")


def needs_escalation(answer: dict | None) -> str:
    """Why this answer should go one tier up, or '' when it should not."""
    if not isinstance(answer, dict):
        return ""
    conf = answer.get("confidence")
    if isinstance(conf, (int, float)) and not isinstance(conf, bool) \
            and float(conf) < ESCALATE_BELOW_CONFIDENCE:
        return f"confidence {float(conf):.2f} < {ESCALATE_BELOW_CONFIDENCE}"
    if answer.get("verifiable") is False:
        return "the answer says it cannot be verified"
    verdict = str(answer.get("verdict") or answer.get("status") or "").lower()
    if verdict in UNSURE_MARKERS:
        return f"verdict {verdict!r}"
    return ""


def escalation_tier(task_key: str) -> Tier | None:
    """The next stronger tier for a declared task, or None on the deep tier."""
    task, tier = route(task_key)
    if not task.stronger_fallback:
        return None          # an optional nicety (laura phrasing) never pays a stronger tier
    rank = _tier_rank(task.tier)
    return TIERS[TIER_ORDER[rank + 1]] if rank + 1 < len(TIER_ORDER) else None
