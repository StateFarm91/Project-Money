"""Elastic specialist capacity, and the rules that stop it becoming a crowd.

Requirements 34, 174, 175, 176, 186, 187, 192, 302. The spec is explicit that agent count is
not to be artificially small — dozens or hundreds of logical specialists are allowed when
parallel specialisation improves quality or latency. What it is equally explicit about is the
other direction: redundant or consistently weak agents are merged or retired, because a swarm
that only grows is a cost centre wearing an org chart.

Four rules hold the middle.

**Work decides headcount, not ambition (#175).** Fan-out is computed from queue depth,
deadline pressure and the value of what is waiting. A fixed pool is wrong in both directions —
idle during a catalogue baseline, and expensively awake during a quiet Tuesday.

**No work is unowned (#176).** Every material task has an accountable cell and an explicit
state. Orphan detection is not a report somebody runs; it is a query with a name, because work
that nobody owns is not noticed by anybody — that is what being unowned means.

**Idle is a backlog, not a slogan (#186).** An agent with nothing urgent does not spin to
satisfy a 24/7 claim, and it does not stop either. It takes the highest-value thing from a
standing backlog, and the backlog is ordered by what the business actually needs next.

**Three identical observations is a stop, not a fourth (#34).** A loop that keeps making the
same call and getting the same answer has stopped working and started spending. Detection is
mechanical: identical call plus identical result, three times, opens the circuit and forces a
re-plan.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

# Priority bands (#187). Lower number wins. The ordering is a commercial argument, not a
# preference: a truth defect in a live product costs trust that cannot be re-earned, and a
# seasonal window that closes cannot be reopened at any price.
BANDS: tuple[tuple[int, str, str], ...] = (
    (10, "customer_incident", "a customer is affected right now"),
    (15, "truth_defect", "a published claim is not true"),
    (25, "seasonal_deadline", "a window closes and cannot be reopened"),
    (40, "proven_winner", "known demand, known economics"),
    (55, "benchmark_change", "the named benchmark moved"),
    (70, "new_opportunity", "unproven, possibly valuable"),
    (85, "exploration", "learning with no committed value"),
    (95, "housekeeping", "keeps the system honest, urgent to nobody"),
)

BAND_BY_KIND: dict[str, int] = {kind: p for p, kind, _ in BANDS}

# How many specialists one unit of waiting work justifies. Fan-out is bounded by spend rather
# than by a headcount constant: the ceiling that matters is money, and a number in the code is
# the "artificial scarcity" #174 objects to.
WORK_PER_SPECIALIST = 8
MIN_SPECIALISTS = 1

# Three identical observations (#34).
THRASH_LIMIT = 3


class SwarmRefused(ValueError):
    """Work that cannot be scheduled, or a fan-out that cannot be afforded."""


@dataclass(frozen=True)
class WorkItem:
    key: str
    kind: str
    owner: str = ""
    state: str = "open"
    value_cad: float = 0.0
    deadline_days: int | None = None

    def __post_init__(self) -> None:
        if self.kind not in BAND_BY_KIND:
            raise SwarmRefused(
                f"{self.key}: {self.kind!r} has no priority band. Unbanded work is scheduled "
                f"by whoever wrote the enqueue call, which is how housekeeping outranks a "
                f"customer incident")

    @property
    def band(self) -> int:
        return BAND_BY_KIND[self.kind]

    def priority(self) -> float:
        """Band first, then deadline pressure, then value. Band is never traded away.

        A high-value opportunity does not outrank a customer incident however large it is,
        because the ordering between bands is a commercial argument the scheduler does not
        get to re-open.
        """
        urgency = 0.0
        if self.deadline_days is not None:
            urgency = max(0.0, 1.0 - min(self.deadline_days, 90) / 90.0)
        # Value contributes within a band only, scaled to stay below one band step.
        value = min(1.0, self.value_cad / 5000.0)
        return self.band - (urgency * 4.0) - (value * 3.0)

    def to_dict(self) -> dict:
        return {"key": self.key, "kind": self.kind, "owner": self.owner,
                "state": self.state, "band": self.band,
                "priority": round(self.priority(), 3),
                "value_cad": self.value_cad, "deadline_days": self.deadline_days}


def schedule(items: list[WorkItem]) -> list[WorkItem]:
    """Order the backlog. Stable within equal priority, so it does not shuffle each tick."""
    return sorted(items, key=lambda w: (w.priority(), w.key))


def orphans(items: list[WorkItem]) -> list[dict]:
    """Work with no accountable cell (#176).

    A query with a name rather than a report somebody remembers to run, because unowned work
    is precisely the work nobody is watching — that is what unowned means.
    """
    return [w.to_dict() for w in items
            if not w.owner and w.state not in ("done", "abandoned")]


def fan_out(*, open_work: int, budget_remaining_cad: float,
            cost_per_specialist_cad: float = 0.05,
            deadline_pressure: bool = False) -> dict:
    """How many specialists the waiting work justifies, bounded by money rather than a number.

    #174 objects to artificial scarcity and #188 requires central budget control, and those
    are the same requirement seen twice: the ceiling should be the real constraint, not a
    constant somebody picked.
    """
    if cost_per_specialist_cad <= 0:
        raise SwarmRefused("a specialist with no cost makes the budget ceiling meaningless")

    wanted = max(MIN_SPECIALISTS, -(-open_work // WORK_PER_SPECIALIST))
    if deadline_pressure:
        wanted = int(wanted * 1.5) or 1
    affordable = int(budget_remaining_cad / cost_per_specialist_cad)
    granted = max(0, min(wanted, affordable))

    return {
        "open_work": open_work,
        "wanted": wanted,
        "affordable": affordable,
        "granted": granted,
        "bounded_by": ("budget" if affordable < wanted else "work"),
        "note": ("Fan-out is bounded by spend rather than by a headcount constant: the "
                 "ceiling that matters is money, and a number in the code is the artificial "
                 "scarcity #174 objects to."),
    }


# ---------------------------------------------------------------------------
# Work-conserving autonomy (#186)

# The standing backlog an agent falls back to. Ordered by what the business needs next rather
# than by what is pleasant, and every entry is genuinely useful work rather than a way to look
# busy.
STANDING_BACKLOG: tuple[tuple[str, str], ...] = (
    ("benchmark_change", "check the named benchmark for changes"),
    ("new_opportunity", "score an uncovered arena in the coverage gap queue"),
    ("exploration", "run a concept tournament for the thinnest seasonal department"),
    ("housekeeping", "re-verify the continuity restore proof"),
    ("housekeeping", "recompute seasonal launch dates against today"),
    ("exploration", "mine recent failures for an improvement hypothesis"),
    ("housekeeping", "refresh the Build-2 coverage map from the registry"),
)


def next_work(urgent: list[WorkItem]) -> dict:
    """What to do now. Never nothing, and never spinning.

    An idle agent that polls to satisfy a 24/7 claim spends money to produce a heartbeat. An
    idle agent that stops is a 24/7 claim that is false. The third option is a backlog.
    """
    if urgent:
        chosen = schedule(urgent)[0]
        return {"source": "queue", "work": chosen.to_dict(),
                "why": f"highest priority open work, band {chosen.band}"}
    kind, description = STANDING_BACKLOG[0]
    return {
        "source": "standing_backlog",
        "work": {"kind": kind, "description": description,
                 "band": BAND_BY_KIND[kind]},
        "why": ("no urgent work; taking the highest-value standing item rather than polling "
                "to look alive or idling to look thrifty (#186)"),
        "backlog": [{"kind": k, "description": d} for k, d in STANDING_BACKLOG],
    }


# ---------------------------------------------------------------------------
# Thrash detection (#34)


@dataclass
class ThrashDetector:
    """Three identical observations is a stop, not a fourth.

    An agent repeating a call and getting the same answer has stopped working and started
    spending. The check is on call *and* result: a poll whose answer keeps changing is
    progress, and a poll whose answer never does is a loop.
    """

    limit: int = THRASH_LIMIT
    seen: dict[str, int] = field(default_factory=dict)
    tripped: set = field(default_factory=set)

    @staticmethod
    def signature(call: str, result) -> str:
        blob = json.dumps({"call": call, "result": result}, sort_keys=True, default=str)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:32]

    def observe(self, call: str, result) -> dict:
        key = self.signature(call, result)
        self.seen[key] = self.seen.get(key, 0) + 1
        count = self.seen[key]
        if count >= self.limit:
            self.tripped.add(key)
            return {
                "continue": False, "observations": count, "signature": key,
                "action": "replan",
                "why": (f"{count} identical observations of {call!r} with an identical "
                        f"result. The loop has stopped working and started spending; "
                        f"re-plan rather than poll again (#34)"),
            }
        return {"continue": True, "observations": count, "signature": key}

    def reset(self, call: str, result) -> None:
        self.seen.pop(self.signature(call, result), None)


# ---------------------------------------------------------------------------
# Retirement and merge (#192)

# A cell producing nothing over this many days with no successes is a candidate.
IDLE_DAYS_BEFORE_REVIEW = 21


def retirement_review(cells: list[dict], *, now: datetime | None = None) -> dict:
    """Which specialists should be merged or retired, and what must be kept first.

    The knowledge is the point. Retiring a cell that learned something and discarding what it
    learned costs more than the cell did, so every recommendation carries what to preserve.
    """
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=IDLE_DAYS_BEFORE_REVIEW)

    retire, merge, keep = [], [], []
    by_scope: dict[str, list[dict]] = {}
    for cell in cells:
        by_scope.setdefault(cell.get("scope", ""), []).append(cell)

    for cell in cells:
        last = cell.get("last_success_at")
        last_dt = (datetime.fromisoformat(last) if isinstance(last, str) else last)
        if last_dt is not None and last_dt.tzinfo is None:
            last_dt = last_dt.replace(tzinfo=timezone.utc)
        idle = last_dt is None or last_dt < cutoff
        duplicates = [c for c in by_scope.get(cell.get("scope", ""), [])
                      if c["key"] != cell["key"]]

        if duplicates and cell.get("tasks", 0) < max(
                (d.get("tasks", 0) for d in duplicates), default=0):
            merge.append({"cell": cell["key"], "into": duplicates[0]["key"],
                          "reason": f"redundant scope {cell.get('scope')!r}, fewer completions",
                          "preserve": cell.get("lessons", [])})
        elif idle and cell.get("tasks", 0) == 0:
            retire.append({"cell": cell["key"],
                           "reason": f"no completed work in {IDLE_DAYS_BEFORE_REVIEW} days",
                           "preserve": cell.get("lessons", [])})
        else:
            keep.append(cell["key"])

    return {
        "keep": keep, "merge": merge, "retire": retire,
        "note": ("More agents are allowed; redundant and consistently idle ones are not. "
                 "Every recommendation carries what to preserve first — retiring a cell and "
                 "discarding what it learned costs more than the cell did (#192)."),
    }
