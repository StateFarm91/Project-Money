"""Central budget control, and the three numbers it refuses to invent.

Requirement 188. Per-agent daily ceilings and the spend guard already exist and already
refuse. What did not exist is the view across them: cost per agent, task, product, department
and experiment; anomaly detection; marginal-value thresholds; and a rule for when adding
parallelism helps rather than duplicating.

Three of those four are measurements this company cannot take yet, and the module's value is
in refusing to fake them rather than in producing them.

**Attribution must sum to the bill.** Every dollar is attributed to a dimension or reported
as unattributed, and the two plus nothing else equal the total. An attribution table that
sums to less than the invoice is the commonest finance artefact in a company this size and
it is worse than no table, because it is acted on: the missing spend is always the spend
nobody has a story for, which is exactly the spend worth looking at.

**An anomaly needs a baseline, and a first observation is not a spike.** A detector with no
history fires on the first real day of work, teaching everybody to ignore it, and then never
fires again. Below the observation floor this module reports that it cannot say, which is
the truth: month-to-date model spend is about a dollar, and a dollar has no distribution.

**Marginal value is spend against outcome, and there are no outcomes.** A marginal-value
threshold computed with a zero numerator says every spend is worthless, which is arithmetic
rather than a finding. It is reported as unmeasurable, naming what it needs -- orders
attributable to the spend -- so the ceilings remain the only live control, and the module
says so instead of implying a sophistication it does not have.

**Parallelism cannot be judged from one setting of it.** The reason to add a worker is that
the queue holds independent work and throughput is worker-bound; the reason not to is that
two workers on a dependent chain take turns. Both are visible only by comparing at least two
worker counts, so `advise` refuses on a single observation rather than guessing from the
one number it has -- which would always recommend whatever was running when somebody asked.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from statistics import median

# The five the requirement names. Closed, because a dimension nobody named is spend nobody
# can trace, and untraceable spend is the whole failure this guards.
DIMENSIONS: dict[str, str] = {
    "agent": "which agent spent it",
    "task": "which job type spent it",
    "product": "which product it was spent on",
    "department": "which pod it was spent in",
    "experiment": "which experiment it belongs to",
}

UNATTRIBUTED = "unattributed"

# Days of history before a spike means anything. Two weeks is the smallest window in which a
# weekday effect and a weekend both appear.
MIN_DAYS_FOR_BASELINE = 14
# How far above the ordinary day counts as a spike, in median absolute deviations.
SPIKE_MADS = 4.0
# And a floor in dollars, because on a base of pennies every multiple is a spike.
SPIKE_FLOOR_CAD = 1.00

# At least this many distinct worker counts before parallelism can be judged at all.
MIN_PARALLELISM_OBSERVATIONS = 2
# An added worker has to move completions per worker-minute by more than this to have done
# anything but duplicate.
MATERIAL_THROUGHPUT_GAIN = 0.10


class GovernorRefused(ValueError):
    """A dimension nobody named, or a verdict the evidence cannot carry."""


def _rows(db, *, days: int, now: datetime | None = None):
    from sqlalchemy import select

    from ..core.models import CostEntry, Job

    now = now or datetime.now(timezone.utc)
    since = now - timedelta(days=days)
    entries = list(db.scalars(select(CostEntry).where(CostEntry.at >= since)))
    job_types = {}
    ids = [e.job_id for e in entries if e.job_id]
    if ids:
        job_types = {j.id: j.job_type for j in db.scalars(select(Job).where(Job.id.in_(ids)))}
    return entries, job_types


def spend_by(db, dimension: str, *, days: int = 30, now: datetime | None = None) -> dict:
    """Spend in one dimension, with the remainder named rather than dropped.

    The reconciliation is the point. Attributed plus unattributed equals the total, always,
    and a table that does not add up to the bill is refused rather than served -- the missing
    spend is always the spend nobody has a story for.
    """
    if dimension not in DIMENSIONS:
        raise GovernorRefused(f"{dimension!r} is not a dimension: {sorted(DIMENSIONS)}")

    entries, job_types = _rows(db, days=days, now=now)
    buckets: dict[str, float] = {}
    unattributed = 0.0
    for entry in entries:
        detail = entry.detail or {}
        if dimension == "agent":
            key = entry.agent or ""
        elif dimension == "task":
            key = job_types.get(entry.job_id or -1, "")
        else:
            key = str(detail.get(dimension) or "")
        amount = float(entry.amount_cad or 0.0)
        if key:
            buckets[key] = buckets.get(key, 0.0) + amount
        else:
            unattributed += amount

    total = round(sum(float(e.amount_cad or 0.0) for e in entries), 6)
    accounted = round(sum(buckets.values()) + unattributed, 6)
    if abs(total - accounted) > 1e-6:  # pragma: no cover - arithmetic guard
        raise GovernorRefused(
            f"attribution sums to CA${accounted} against a bill of CA${total}. A table that "
            f"does not add up to the invoice is worse than none, because it is acted on")

    return {
        "dimension": dimension,
        "days": days,
        "total_cad": round(total, 6),
        "rows": [{"key": k, "cad": round(v, 6),
                  "share": round(v / total, 4) if total else None}
                 for k, v in sorted(buckets.items(), key=lambda kv: -kv[1])],
        "unattributed_cad": round(unattributed, 6),
        "unattributed_share": round(unattributed / total, 4) if total else None,
        "reconciles": True,
        "note": ("the remainder is named rather than dropped: the spend nobody has a story "
                 "for is exactly the spend worth looking at"),
    }


def attribution(db, *, days: int = 30, now: datetime | None = None) -> dict:
    """All five dimensions at once, each reconciled against the same bill."""
    return {"days": days,
            "dimensions": {d: spend_by(db, d, days=days, now=now) for d in DIMENSIONS}}


def anomaly(db, *, days: int = 60, now: datetime | None = None) -> dict:
    """Whether today's spend is a spike, or whether there is not yet a normal to spike from.

    A detector with no history fires on the first real day of work, teaches everybody to
    ignore it, and then never fires again. So the refusal comes first.
    """
    entries, _ = _rows(db, days=days, now=now)
    now = now or datetime.now(timezone.utc)

    by_day: dict[str, float] = {}
    for entry in entries:
        when = entry.at
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        key = when.date().isoformat()
        by_day[key] = by_day.get(key, 0.0) + float(entry.amount_cad or 0.0)

    today = now.date().isoformat()
    history = [v for k, v in by_day.items() if k != today]
    today_spend = round(by_day.get(today, 0.0), 6)

    if len(history) < MIN_DAYS_FOR_BASELINE:
        return {
            "measurable": False, "days_of_history": len(history),
            "needs_days": MIN_DAYS_FOR_BASELINE, "today_cad": today_spend,
            "why": (f"{len(history)} day(s) of history against a floor of "
                    f"{MIN_DAYS_FOR_BASELINE}. A first observation is not a spike, and a "
                    f"detector with no baseline fires on the first real day of work, teaches "
                    f"everybody to ignore it, and then never fires again"),
        }

    mid = median(history)
    mad = median([abs(v - mid) for v in history]) or 0.0
    threshold = max(mid + SPIKE_MADS * mad, mid + SPIKE_FLOOR_CAD)
    return {
        "measurable": True, "days_of_history": len(history),
        "today_cad": today_spend, "ordinary_day_cad": round(mid, 6),
        "threshold_cad": round(threshold, 6),
        "spike": today_spend > threshold,
        "why": (f"CA${today_spend} against an ordinary day of CA${round(mid, 4)}"
                + (" -- above the threshold" if today_spend > threshold else "")),
        "floor_note": (f"a dollar floor sits under the statistical threshold, because on a "
                       f"base of pennies every multiple is a spike"),
    }


def marginal_value(db, *, days: int = 30, now: datetime | None = None) -> dict:
    """What the spend produced, which is the only thing that justifies more of it."""
    from sqlalchemy import func, select

    from ..core.models import CostEntry, LedgerEntry

    entries, _ = _rows(db, days=days, now=now)
    spend = round(sum(float(e.amount_cad or 0.0) for e in entries), 6)
    orders = db.scalar(select(func.count()).select_from(LedgerEntry)) or 0
    revenue = float(db.scalar(select(func.sum(LedgerEntry.gross_cad))) or 0.0)
    lifetime = float(db.scalar(select(func.sum(CostEntry.amount_cad))) or 0.0)

    if not orders:
        return {
            "measurable": False, "spend_cad": spend, "lifetime_spend_cad": round(lifetime, 6),
            "orders": 0,
            "why": ("no order has been attributed to any spend, so marginal value has a zero "
                    "numerator. Reporting that as 'every spend is worthless' is arithmetic "
                    "rather than a finding, and it would justify cutting the spend that has "
                    "not had time to work"),
            "needs": ["orders attributable to a spend"],
            "live_control": ("the daily and lifetime ceilings, which refuse before a spend "
                             "rather than reporting after it"),
        }
    return {
        "measurable": True, "spend_cad": spend, "orders": int(orders),
        "revenue_cad": round(revenue, 2),
        "return_per_dollar": round(revenue / spend, 3) if spend else None,
        "why": "revenue against spend over the window",
    }


def parallelism(observations: list[dict]) -> dict:
    """Whether to add a worker, remove one, or say that nobody can tell yet.

    Each observation is {workers, minutes, completed}. The comparison is completions per
    worker-minute: if adding a worker did not raise it materially, the workers were taking
    turns on dependent work and the second one duplicated.
    """
    rows = []
    for o in observations:
        workers = int(o["workers"])
        minutes = float(o["minutes"])
        if workers <= 0 or minutes <= 0:
            raise GovernorRefused("an observation needs workers and minutes above zero")
        rows.append({"workers": workers, "minutes": minutes,
                     "completed": int(o["completed"]),
                     "per_worker_minute": round(int(o["completed"]) / (workers * minutes), 6),
                     "per_minute": round(int(o["completed"]) / minutes, 6)})

    counts = {r["workers"] for r in rows}
    if len(counts) < MIN_PARALLELISM_OBSERVATIONS:
        return {
            "advice": None, "observations": rows,
            "why": (f"{len(counts)} distinct worker count(s). Parallelism cannot be judged "
                    f"from one setting of it: the question is whether adding a worker "
                    f"changed anything, and a single number answers it with whatever was "
                    f"running when somebody asked"),
        }

    ordered = sorted(rows, key=lambda r: r["workers"])
    low, high = ordered[0], ordered[-1]
    gain = ((high["per_minute"] - low["per_minute"]) / low["per_minute"]
            if low["per_minute"] else None)
    duplicated = gain is not None and gain < MATERIAL_THROUGHPUT_GAIN

    return {
        "advice": "scale_down" if duplicated else "scale_up",
        "compared": {"from_workers": low["workers"], "to_workers": high["workers"],
                     "throughput_gain": None if gain is None else round(gain, 3)},
        "observations": ordered,
        "why": (f"{high['workers']} workers completed "
                f"{'no more' if duplicated else 'materially more'} per minute than "
                f"{low['workers']}"
                + (". Two workers on a dependent chain take turns, and the second one is "
                   "cost without throughput" if duplicated else
                   ", so the queue holds independent work and throughput is worker-bound")),
        "threshold": MATERIAL_THROUGHPUT_GAIN,
    }


def report(db, *, days: int = 30, now: datetime | None = None) -> dict:
    """Everything the governor can honestly say today."""
    return {
        "attribution": attribution(db, days=days, now=now),
        "anomaly": anomaly(db, now=now),
        "marginal_value": marginal_value(db, days=days, now=now),
        "parallelism": parallelism([]),
        "note": ("three of this requirement's four controls are measurements this company "
                 "cannot take yet, and each says so rather than producing a number with the "
                 "right shape and no meaning. The ceilings are the live control, and they "
                 "refuse before a spend rather than reporting after it (#188)."),
    }


def state() -> dict:
    """The dimensions, the floors, and what this module will not invent."""
    return {
        "dimensions": dict(DIMENSIONS),
        "floors": {"days_for_baseline": MIN_DAYS_FOR_BASELINE,
                   "spike_mads": SPIKE_MADS, "spike_floor_cad": SPIKE_FLOOR_CAD,
                   "parallelism_observations": MIN_PARALLELISM_OBSERVATIONS,
                   "material_throughput_gain": MATERIAL_THROUGHPUT_GAIN},
        "will_not_invent": [
            "an anomaly without a baseline: a first observation is not a spike",
            "a marginal value with a zero numerator: that is arithmetic, not a finding",
            "a parallelism verdict from one worker count: it answers with whatever was "
            "running when somebody asked",
        ],
        "note": ("Attribution sums to the bill or it is refused. The spend nobody has a "
                 "story for is exactly the spend worth looking at, so the remainder is "
                 "named rather than dropped (#188)."),
    }
