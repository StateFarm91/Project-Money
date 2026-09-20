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

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone

# Anthropic's published first-party rates, USD per million tokens, and the exchange rate used
# to express the ceiling in the owner's currency. The rate is an assumption and is labelled
# one: it moves, and a ceiling quoted in CAD against a bill charged in USD has to say so.
USD_PER_CAD = 0.715
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
    if task_key in PATTERN_TASKS_REFUSED:
        raise TaskRefused(
            f"{task_key!r} is decided by deterministic code, not by a model. Patterns are "
            f"software releases: the compiler and the twin answer this, and a model that "
            f"disagrees is noise (§27)")
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


def spent_this_month(db, now: datetime | None = None) -> float:
    """What the month's model calls have actually cost, from the ledger that records them."""
    from sqlalchemy import func, select

    from ..core.models import CostEntry

    now = now or datetime.now(timezone.utc)
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    with db.session() as s:
        total = s.scalar(
            select(func.coalesce(func.sum(CostEntry.amount_cad), 0.0))
            .where(CostEntry.kind == COST_KIND, CostEntry.at >= start))
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
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


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
