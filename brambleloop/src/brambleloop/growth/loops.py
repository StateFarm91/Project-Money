"""The growth loop registry: what actually brings people here, and how strongly we know it.

Requirements 263, 264, 271. A growth loop is a mechanism that brings qualified visitors
repeatably. The registry exists because the alternative is a list of channels somebody believes
in, and a channel somebody believes in behaves exactly like a working one right up until the
month it needs to carry the target.

So each loop carries evidence strength, and the strengths are ordered by what they permit:

- `untested` — nobody has tried it. It may be listed and may not be counted.
- `attempted` — tried, no attributable traffic yet.
- `measured` — attributable traffic, over a sample.
- `repeatable` — measured more than once, with the cost per visit stable.

Only `measured` and `repeatable` count toward the confidence ladder's acquisition rung, which
is why that rung reads zero today: every loop here is untested, and a registry that counted
intentions would have quietly raised the CA$5K probability by listing ambitions.

#264's weekly constraint solver lives here too, and it answers one question: of all the things
that are wrong, which one is worth an agent's week? The answer is the term whose improvement
moves the target most for the least, which is arithmetic rather than judgement.
"""
from __future__ import annotations

from dataclasses import dataclass

UNTESTED = "untested"
ATTEMPTED = "attempted"
MEASURED = "measured"
REPEATABLE = "repeatable"

STRENGTHS: tuple[str, ...] = (UNTESTED, ATTEMPTED, MEASURED, REPEATABLE)
COUNTS_AS_EVIDENCE: frozenset[str] = frozenset({MEASURED, REPEATABLE})

# A loop needs this many attributable visits before `measured` means anything.
MEASURED_SAMPLE = 200


class LoopRefused(ValueError):
    """A claim a loop's evidence cannot carry."""


@dataclass
class Loop:
    """One acquisition mechanism, and how well it is actually understood."""

    key: str
    name: str
    strength: str = UNTESTED
    visits: int = 0
    orders: int = 0
    cost_cad: float = 0.0
    latency_days: int = 0
    scalable: bool = True
    note: str = ""

    def __post_init__(self) -> None:
        if self.strength not in STRENGTHS:
            raise LoopRefused(f"{self.strength!r} is not an evidence strength")
        if self.strength in COUNTS_AS_EVIDENCE and self.visits < MEASURED_SAMPLE:
            raise LoopRefused(
                f"{self.key}: {self.strength!r} claimed on {self.visits} visits, below the "
                f"{MEASURED_SAMPLE} a rate needs to mean anything. A loop measured over "
                f"twelve visits is a loop somebody is hopeful about")

    @property
    def counts_as_evidence(self) -> bool:
        return self.strength in COUNTS_AS_EVIDENCE

    @property
    def cost_per_visit_cad(self) -> float | None:
        return round(self.cost_cad / self.visits, 4) if self.visits else None

    @property
    def conversion(self) -> float | None:
        return round(self.orders / self.visits, 4) if self.visits else None

    def to_dict(self) -> dict:
        return {"key": self.key, "name": self.name, "strength": self.strength,
                "visits": self.visits, "orders": self.orders,
                "cost_per_visit_cad": self.cost_per_visit_cad,
                "conversion": self.conversion, "latency_days": self.latency_days,
                "scalable": self.scalable, "counts_as_evidence": self.counts_as_evidence,
                "note": self.note}


# The loops this business could plausibly run. Listed so the gaps are visible; every one is
# `untested`, which is the honest state and the reason the acquisition rung reads zero.
REGISTRY: tuple[Loop, ...] = (
    Loop("etsy_organic", "Etsy organic search",
         note="the default loop for a digital-pattern shop, and the one with the longest "
              "indexing latency"),
    Loop("pinterest", "Pinterest search",
         latency_days=45,
         note="long latency, long half-life: a pin keeps working for months, which is why it "
              "must start months early"),
    Loop("google_seo", "Owned search clusters", latency_days=90),
    Loop("creators", "Creator partnerships", latency_days=21, scalable=False,
         note="does not scale linearly: each partnership is a relationship, not a slot"),
    Loop("email", "Email and repeat", latency_days=30,
         note="needs consented subscribers, so CASL applies and nothing starts before the "
              "shop exists"),
    Loop("paid_ads", "Paid acquisition", latency_days=7,
         note="the only loop that buys traffic rather than earning it, and the only one "
              "gated on owner-approved spend"),
    Loop("bundles", "Bundles and cross-sell", latency_days=0,
         note="not acquisition: it raises the value of traffic the other loops brought"),
)

BY_KEY: dict[str, Loop] = {loop.key: loop for loop in REGISTRY}


def seed(db) -> list[str]:
    """Write the declared loops into the registry table, reconciling what code owns.

    Same split as the agent registry: identity, name and shape belong to the code; observed
    traffic belongs to the running system and a deploy never overwrites it.
    """
    from sqlalchemy import select

    from ..core.models import GrowthLoop

    changes: list[str] = []
    with db.session() as s:
        for loop in REGISTRY:
            row = s.scalar(select(GrowthLoop).where(GrowthLoop.key == loop.key))
            if row is None:
                s.add(GrowthLoop(key=loop.key, name=loop.name, strength=loop.strength,
                                 latency_days=loop.latency_days, scalable=loop.scalable,
                                 note=loop.note))
                changes.append(f"created {loop.key}")
                continue
            for field_name in ("name", "latency_days", "scalable", "note"):
                if getattr(row, field_name) != getattr(loop, field_name):
                    setattr(row, field_name, getattr(loop, field_name))
                    changes.append(f"{loop.key}.{field_name}")
    return changes


def observe(db, key: str, *, visits: int, orders: int = 0, cost_cad: float = 0.0) -> str:
    """Record traffic a loop actually produced, and let that decide its strength.

    The strength is derived rather than set. A field somebody assigns is a field somebody
    assigns optimistically, and this one feeds the CA$5K model's acquisition rung.
    """
    from sqlalchemy import select

    from ..core.models import GrowthLoop

    with db.session() as s:
        row = s.scalar(select(GrowthLoop).where(GrowthLoop.key == key))
        if row is None:
            raise LoopRefused(f"unknown loop {key!r}: add it to REGISTRY deliberately")
        row.visits += int(visits)
        row.orders += int(orders)
        row.cost_cad += float(cost_cad)
        if row.visits >= MEASURED_SAMPLE:
            # `repeatable` needs more than one observation, so it is reached by being seen
            # again rather than by one large week.
            row.strength = REPEATABLE if row.strength == MEASURED else MEASURED
        elif row.visits > 0:
            row.strength = ATTEMPTED
        return row.strength


def from_db(db) -> tuple[Loop, ...]:
    from sqlalchemy import select

    from ..core.models import GrowthLoop

    with db.session() as s:
        rows = list(s.scalars(select(GrowthLoop).order_by(GrowthLoop.key)))
    if not rows:
        return REGISTRY
    return tuple(Loop(key=r.key, name=r.name, strength=r.strength, visits=r.visits,
                      orders=r.orders, cost_cad=r.cost_cad, latency_days=r.latency_days,
                      scalable=r.scalable, note=r.note) for r in rows)


def evidence_summary(loops: tuple[Loop, ...] = REGISTRY) -> dict:
    """How many loops are actually known to work, which is what #275 counts."""
    counted = [loop for loop in loops if loop.counts_as_evidence]
    return {
        "loops": len(loops),
        "with_evidence": len(counted),
        "by_strength": {s: sum(1 for x in loops if x.strength == s) for s in STRENGTHS},
        "loops_detail": [loop.to_dict() for loop in loops],
        "note": ("No loop has attributable traffic, so the acquisition rung of the CA$5K "
                 "ladder reads zero. A registry that counted listed channels would have "
                 "raised the modelled probability by writing down ambitions."
                 if not counted else
                 f"{len(counted)} loops carry measured traffic."),
    }


# ---------------------------------------------------------------------------
# The weekly constraint solver (#264)

# The terms of the target, and what each one costs to move. Effort is a rough week-count
# because the useful comparison is "which of these is worth an agent's week", not a
# false-precision estimate.
TERMS: dict[str, dict] = {
    "qualified_visits": {"effort_weeks": 3.0, "ceiling": 12000.0,
                         "why": "the funnel's top, and the slowest to move"},
    "conversion_rate": {"effort_weeks": 1.0, "ceiling": 0.04,
                        "why": "listing copy, imagery and price; fastest to test"},
    "aov_cad": {"effort_weeks": 1.5, "ceiling": 45.0,
                "why": "bundles and cross-sell against existing traffic"},
    "repeat_rate": {"effort_weeks": 2.0, "ceiling": 0.35,
                    "why": "needs customers to exist first"},
}


def constraint(observed: dict[str, float], *, target_cad: float = 5000.0) -> dict:
    """Which single thing is worth this week (#264).

    Ranked by expected marginal contribution per week of effort rather than by how far each
    term is from its ceiling: the biggest gap is often the slowest to close, and a week spent
    on it buys less than a week spent somewhere cheaper.
    """
    visits = float(observed.get("qualified_visits") or 0.0)
    conversion = float(observed.get("conversion_rate") or 0.0)
    aov = float(observed.get("aov_cad") or 0.0)
    repeat = float(observed.get("repeat_rate") or 0.0)
    current = visits * conversion * aov * (1 + repeat)

    ranked = []
    for term, meta in TERMS.items():
        lifted = dict(qualified_visits=visits, conversion_rate=conversion,
                      aov_cad=aov, repeat_rate=repeat)
        # What happens if this one term moves halfway to its ceiling and nothing else does.
        lifted[term] = lifted[term] + (meta["ceiling"] - lifted[term]) * 0.5
        after = (lifted["qualified_visits"] * lifted["conversion_rate"]
                 * lifted["aov_cad"] * (1 + lifted["repeat_rate"]))
        gain = after - current
        ranked.append({
            "term": term, "observed": lifted[term] if False else observed.get(term, 0.0),
            "half_way_to": round(lifted[term], 4),
            "monthly_gain_cad": round(gain, 2),
            "effort_weeks": meta["effort_weeks"],
            "gain_per_week_cad": round(gain / meta["effort_weeks"], 2),
            "why": meta["why"],
        })
    ranked.sort(key=lambda r: -r["gain_per_week_cad"])

    zeroed = [r["term"] for r in ranked if not observed.get(r["term"])]
    return {
        "current_monthly_cad": round(current, 2),
        "target_cad": target_cad,
        "primary_constraint": ranked[0]["term"] if ranked else None,
        "ranked": ranked,
        "note": (
            "Every term is zero, so the product of them is zero and no single term can move "
            "it: with no traffic, doubling conversion doubles nothing. The binding constraint "
            "is the first term in the chain, and it is not an optimisation problem yet — it "
            "is a shop that does not exist."
            if len(zeroed) == len(TERMS) else
            f"Ranked by contribution per week of effort. Terms still at zero: {zeroed}."
            if zeroed else
            "Ranked by expected monthly contribution per week of effort."),
    }
