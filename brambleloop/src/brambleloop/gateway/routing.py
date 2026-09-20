"""Which model answers which question, and the ceiling that cannot be argued with.

The owner approved one production model provider at a hard **CA$25 per month**, with four
conditions: route by capability and cost, start economically, cache and reuse analysis, and do
not treat the ceiling as a target. And one standing rule that outranks all of them — a model
may never generate canonical crochet pattern content.

**The ceiling is arithmetic, not judgement.** `Budget.check()` sums this calendar month's
`llm` cost entries and refuses a call whose estimate would cross CA$25. It runs *before* the
request, because a ceiling checked afterwards is a report. There is no override parameter: the
way past it is the owner raising it, which is an owner action with measured usage attached.

**Routing is by what the task actually needs.** Reading a title into a category is not the same
question as judging whether a photograph makes a garment look desirable, and paying the same
rate for both is how a CA$25 month becomes a CA$60 one. Three tiers, cheapest first, and the
tier is a property of the task rather than of the caller's mood.

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
FX_NOTE = ("model prices are published in USD; the CA$25 ceiling is converted at an assumed "
           "0.715 USD/CAD and is checked against the converted figure, so a weaker dollar "
           "spends the ceiling faster rather than silently exceeding it")

CHEAP = "cheap"
STANDARD = "standard"
DEEP = "deep"


@dataclass(frozen=True)
class Tier:
    key: str
    model: str
    usd_per_1m_input: float
    usd_per_1m_output: float
    vision: bool
    use_for: str

    def cost_cad(self, tokens_in: int, tokens_out: int) -> float:
        usd = (tokens_in / 1_000_000 * self.usd_per_1m_input
               + tokens_out / 1_000_000 * self.usd_per_1m_output)
        return round(usd / USD_PER_CAD, 6)


TIERS: dict[str, Tier] = {
    CHEAP: Tier(
        CHEAP, "claude-haiku-4-5", 1.00, 5.00, vision=True,
        use_for="classification, extraction and routing — high volume, low judgement"),
    STANDARD: Tier(
        STANDARD, "claude-sonnet-5", 2.00, 10.00, vision=True,
        use_for="image-level observation and listing copy — judgement at volume"),
    DEEP: Tier(
        DEEP, "claude-opus-5", 5.00, 25.00, vision=True,
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
    "seasonal_signal": Task(
        "seasonal_signal", CHEAP, 400, 1200, True,
        "classify a trend's half-life and seasonal fit (#290)"),
    "gallery_observation": Task(
        "gallery_observation", STANDARD, 1200, 3000, True,
        "shot type, composition, styling and thumbnail legibility from a public image URL "
        "(#209) — the part of the mandate the Etsy API cannot answer"),
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

MONTHLY_CEILING_CAD = 25.0
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
