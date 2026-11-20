"""The coverage gap queue: benchmark arenas with no Brambleloop answer yet.

Requirement 314, and the part of it that is easy to skip. A queue of opportunities is simple;
what the requirement actually asks for is a queue that distinguishes *uncovered, concepting,
engineering, certified, launched, validated winner* and *not pursuing with a reason* -- which
is a lifecycle, and the last state is the one that makes the queue honest. A queue whose items
can leave without saying why is a queue that shrinks by forgetting, and then reports good
coverage.

The scoring is deliberately explicit rather than learned. Every component is stored beside the
score, so a ranking can be argued with -- and when the data to compute a component does not
exist yet, the component is absent rather than assumed, and the score says how much of itself
is evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

UNCOVERED = "uncovered"
CONCEPTING = "concepting"
ENGINEERING = "engineering"
CERTIFIED = "certified"
LAUNCHED = "launched"
VALIDATED_WINNER = "validated_winner"
NOT_PURSUING = "not_pursuing"

STATES: tuple[str, ...] = (UNCOVERED, CONCEPTING, ENGINEERING, CERTIFIED, LAUNCHED,
                           VALIDATED_WINNER, NOT_PURSUING)

# The forward path, plus the two honest exits: anything may be abandoned with a reason, and a
# launched product that stops selling drops back rather than sitting as a permanent success.
_ALLOWED: dict[str, tuple[str, ...]] = {
    UNCOVERED: (CONCEPTING, NOT_PURSUING),
    CONCEPTING: (ENGINEERING, NOT_PURSUING, UNCOVERED),
    ENGINEERING: (CERTIFIED, CONCEPTING, NOT_PURSUING),
    CERTIFIED: (LAUNCHED, ENGINEERING, NOT_PURSUING),
    LAUNCHED: (VALIDATED_WINNER, CERTIFIED, NOT_PURSUING),
    VALIDATED_WINNER: (LAUNCHED, NOT_PURSUING),
    NOT_PURSUING: (UNCOVERED,),
}

# Weights sum to 1. Demand and contribution lead because this queue decides where the
# company's only scarce resource -- finished, certified products -- gets spent.
WEIGHTS: dict[str, float] = {
    "apparent_demand": 0.24,
    "expected_contribution": 0.20,
    "seasonal_timing": 0.16,
    "search_opportunity": 0.14,
    "creative_potential": 0.12,
    "portfolio_fit": 0.08,
    "make_time": 0.06,
}

COMPONENTS: tuple[str, ...] = tuple(WEIGHTS)


class GapRefused(Exception):
    """A transition the lifecycle does not allow, or an exit with no reason."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class Score:
    value: float
    components: dict[str, float]
    evidence_weight: float
    missing: tuple[str, ...]

    def to_dict(self) -> dict:
        return {"value": self.value, "components": dict(self.components),
                "evidence_weight": self.evidence_weight, "missing": list(self.missing)}


def score(components: dict[str, float]) -> Score:
    """Rank an arena from whatever evidence exists, and say how much that was.

    Unknown components are left out rather than filled with a midpoint. A midpoint is an
    opinion wearing a number's clothes, and it is indistinguishable from a measurement once it
    is in the table. `evidence_weight` is the share of the weighting that was actually
    answered, so a confident-looking 0.8 computed from one component cannot pass for a
    considered one.
    """
    unknown = [k for k in components if k not in WEIGHTS]
    if unknown:
        raise GapRefused(f"unknown scoring components: {sorted(unknown)}")
    for key, value in components.items():
        if not 0.0 <= float(value) <= 1.0:
            raise GapRefused(f"{key}={value!r}: components are normalised to 0..1")

    used = {k: float(v) for k, v in components.items()}
    weight = sum(WEIGHTS[k] for k in used)
    if weight == 0:
        return Score(0.0, {}, 0.0, COMPONENTS)
    value = sum(WEIGHTS[k] * v for k, v in used.items()) / weight
    missing = tuple(k for k in COMPONENTS if k not in used)
    return Score(round(value, 4), used, round(weight, 4), missing)


def check_transition(current: str, to: str, reason: str = "") -> None:
    """Refuse an illegal move, and refuse an exit that does not say why."""
    if current not in STATES:
        raise GapRefused(f"unknown state {current!r}")
    if to not in STATES:
        raise GapRefused(f"unknown state {to!r}")
    if to == current:
        return
    if to not in _ALLOWED[current]:
        raise GapRefused(
            f"{current!r} -> {to!r} is not a move this lifecycle allows. The queue's states "
            f"are the record of what was actually done; skipping one makes it fiction")
    if to == NOT_PURSUING and len(reason.strip()) < 10:
        raise GapRefused(
            "leaving the queue requires a reason (#314). A gap that can be closed silently "
            "is how a coverage report improves without the coverage improving")


def upsert(db, *, benchmark_key: str, arena: str, pod: str,
           components: dict[str, float] | None = None,
           evidence: dict | None = None) -> int:
    """Record or refresh an arena in the queue. Returns the row id.

    Re-scoring an existing gap never resets its lifecycle state: evidence changing is not the
    same event as work happening, and conflating them would drop a half-engineered product
    back to uncovered every time the benchmark posted something.
    """
    from sqlalchemy import select

    from ..core.models import CoverageGap

    s_ = score(components or {})
    with db.session() as s:
        row = s.scalar(select(CoverageGap).where(
            CoverageGap.benchmark_key == benchmark_key, CoverageGap.arena == arena))
        if row is None:
            row = CoverageGap(benchmark_key=benchmark_key, arena=arena, pod=pod,
                              state=UNCOVERED)
            s.add(row)
        row.pod = pod
        row.score = s_.value
        row.components = s_.to_dict()
        if evidence is not None:
            row.evidence = evidence
        row.updated_at = _utcnow()
        s.flush()
        return row.id


def advance(db, gap_id: int, to: str, *, reason: str = "", product_slug: str = "") -> str:
    """Move a gap along its lifecycle, or refuse."""
    from ..core.models import CoverageGap

    with db.session() as s:
        row = s.get(CoverageGap, gap_id)
        if row is None:
            raise GapRefused(f"no coverage gap {gap_id}")
        check_transition(row.state, to, reason)
        row.state = to
        if reason:
            row.reason = reason
        if product_slug:
            row.product_slug = product_slug
        row.updated_at = _utcnow()
        return row.state


def queue(db, benchmark_key: str | None = None, *, states: tuple[str, ...] = (),
          limit: int = 50) -> list[dict]:
    """The queue as the owner and the pods read it: highest-scoring open work first."""
    from sqlalchemy import select

    from ..core.models import CoverageGap

    stmt = select(CoverageGap)
    if benchmark_key:
        stmt = stmt.where(CoverageGap.benchmark_key == benchmark_key)
    if states:
        stmt = stmt.where(CoverageGap.state.in_(states))
    with db.session() as s:
        rows = list(s.scalars(stmt))
        out = [{
            "id": r.id, "benchmark": r.benchmark_key, "arena": r.arena, "pod": r.pod,
            "state": r.state, "score": r.score, "components": r.components,
            "reason": r.reason, "product_slug": r.product_slug,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        } for r in rows]
    return sorted(out, key=lambda d: -d["score"])[:limit]


def summary(db, benchmark_key: str | None = None) -> dict:
    """Counts by state, which is what the mission dashboard shows (#318)."""
    rows = queue(db, benchmark_key, limit=100000)
    counts = {state: 0 for state in STATES}
    for r in rows:
        counts[r["state"]] = counts.get(r["state"], 0) + 1
    answered = sum(counts[s] for s in (CERTIFIED, LAUNCHED, VALIDATED_WINNER))
    return {
        "total": len(rows),
        "by_state": counts,
        # Deliberately not "coverage": an arena in `concepting` is not covered, and a
        # percentage that counted intentions would climb without a product existing.
        "answered_with_a_certified_product": answered,
        "top_uncovered": [r for r in rows if r["state"] == UNCOVERED][:10],
    }
