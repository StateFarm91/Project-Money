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

from contextlib import contextmanager

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

# Where each dimension is actually stored on a CostEntry.
#
# This table exists because the absence of it cost three of the five dimensions. `product`
# and `department` were read out of the `detail` JSON blob, and `spend_report.record` -- the
# single writer the same owner instruction created -- writes them to the `product_slug` and
# `department` *columns*. So this module read an empty blob key, found nothing, and filed
# every dollar under `unattributed`. Measured on production 2026-09-24: `/api/spend-report`
# attributed all CA$75.93 across three departments and `/api/governor` reported the same
# CA$75.93 as 100% unattributed, from the same rows, in the same minute.
#
# The reconciliation guard below did not catch it and could not: it asserts that attributed
# plus unattributed equals the bill, and a dimension that reads nothing puts the whole bill
# in `unattributed`, where it still sums. A total that reconciles is not a dimension that
# works, and "worse than no table, because it is acted on" is exactly what a table of one
# row reading `unattributed: 100%` is.
#
# The `detail` key stays as a fallback rather than being dropped, because rows written before
# the columns existed still carry it, and the old rows are the ones a history question asks
# about.
COLUMN_FOR: dict[str, str] = {"agent": "agent", "product": "product_slug",
                              "department": "department"}
DETAIL_KEY_FOR: dict[str, str] = {"product": "product", "department": "department",
                                  "experiment": "experiment"}

# A dimension no code writes cannot be distinguished from a dimension every row forgot, and
# the two want different answers: one is a gap in the schema and the other is a gap in the
# call sites. Nothing in this repository writes an experiment onto a cost row -- there is no
# column and no `detail["experiment"]` writer -- so the dimension reports that it has no
# writer rather than reporting 100% unattributed, which reads like sloppiness about money
# that was in fact never tagged because nothing can tag it.
#
# Certification C-68 (#188): the experiment dimension now has a reader of real data rather
# than a label saying it has none. A cost row's experiment is, in order: `detail["experiment"]`
# where a writer put one; else the spending job's own `inputs["experiment"]` (a job enqueued
# for a registered experiment carries it); else, for work in the swarm's `exploration` band --
# "learning with no committed value", which is what an experiment is -- the job type that ran
# it. Spend on committed work stays unattributed on this dimension, and says so.
NO_WRITER: frozenset[str] = frozenset()


# C-80 defect 13 (Codex P13): how an experiment attribution was read. `tagged` is a real
# experiment record (a detail or job input naming one); `band_proxy` is spend by an
# exploration-band job with no experiment named -- learning spend, reported in its own bucket
# and never as an experiment key.
BASIS_TAGGED = "tagged"
BASIS_BAND_PROXY = "band_proxy"


def _experiment_of(job) -> dict:
    """The experiment a spending job belongs to, with the basis it was read on."""
    if job is None:
        return {"experiment": "", "basis": ""}
    inputs = job.inputs if isinstance(job.inputs, dict) else {}
    tagged = str(inputs.get("experiment") or inputs.get("experiment_id") or "").strip()
    if tagged:
        return {"experiment": tagged, "basis": BASIS_TAGGED}
    from ..swarm.orchestrate import band_for

    if band_for(job.job_type)["kind"] == "exploration":
        return {"experiment": f"exploration:{job.job_type}", "basis": BASIS_BAND_PROXY}
    return {"experiment": "", "basis": ""}

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
        jobs = list(db.scalars(select(Job).where(Job.id.in_(ids))))
        job_types = {j.id: j.job_type for j in jobs}
        job_types.update({("experiment", j.id): _experiment_of(j) for j in jobs})
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
    basis_of: dict[str, str] = {}
    proxy: dict[str, float] = {}
    unattributed = 0.0
    for entry in entries:
        detail = entry.detail or {}
        basis = ""
        if dimension == "task":
            key = job_types.get(entry.job_id or -1, "")
        else:
            column = COLUMN_FOR.get(dimension)
            key = str(getattr(entry, column, "") or "").strip() if column else ""
            if not key:
                key = str(detail.get(DETAIL_KEY_FOR.get(dimension, dimension)) or "").strip()
                if key and dimension == "experiment":
                    basis = BASIS_TAGGED
            if not key and dimension == "experiment":
                read = job_types.get(("experiment", entry.job_id or -1)) or {}
                key, basis = read.get("experiment", ""), read.get("basis", "")
        amount = float(entry.amount_cad or 0.0)
        if key and basis == BASIS_BAND_PROXY:
            # C-80 defect 13: exploration-band spend with no experiment named is its own
            # bucket -- learning spend -- not a row pretending to be an experiment.
            proxy[key] = proxy.get(key, 0.0) + amount
        elif key:
            buckets[key] = buckets.get(key, 0.0) + amount
            if basis:
                basis_of[key] = basis
        else:
            unattributed += amount

    total = round(sum(float(e.amount_cad or 0.0) for e in entries), 6)
    accounted = round(sum(buckets.values()) + sum(proxy.values()) + unattributed, 6)
    if abs(total - accounted) > 1e-6:  # pragma: no cover - arithmetic guard
        raise GovernorRefused(
            f"attribution sums to CA${accounted} against a bill of CA${total}. A table that "
            f"does not add up to the invoice is worse than none, because it is acted on")

    read_from = ("the job that spent it" if dimension == "task"
                 else f"CostEntry.{COLUMN_FOR[dimension]}, falling back to detail"
                 if dimension in COLUMN_FOR
                 else ("detail['experiment'], else the spending job's inputs['experiment'], "
                       "else its exploration-band job type")
                 if dimension == "experiment"
                 else f"detail[{DETAIL_KEY_FOR.get(dimension, dimension)!r}]")
    out = {
        "dimension": dimension,
        "days": days,
        "total_cad": round(total, 6),
        "rows": [{"key": k, "cad": round(v, 6),
                  "share": round(v / total, 4) if total else None,
                  **({"basis": basis_of[k]} if k in basis_of else {})}
                 for k, v in sorted(buckets.items(), key=lambda kv: -kv[1])],
        # spend attributed by a proxy rather than a record: named as such, summed apart
        "proxy": {"basis": BASIS_BAND_PROXY if proxy else None,
                  "cad": round(sum(proxy.values()), 6),
                  "rows": [{"key": k, "cad": round(v, 6)}
                           for k, v in sorted(proxy.items(), key=lambda kv: -kv[1])],
                  "why": ("exploration-band jobs that named no experiment: learning spend, "
                          "reported as a proxy bucket and never as an experiment (C-80)")},
        "unattributed_cad": round(unattributed, 6),
        "unattributed_share": round(unattributed / total, 4) if total else None,
        "reconciles": True,
        # Where the number came from, so "100% unattributed" can be told apart from "this
        # dimension is being read out of the wrong place". That distinction is what took
        # three of the five dimensions out of service without any check going red.
        "read_from": read_from,
        "note": ("the remainder is named rather than dropped: the spend nobody has a story "
                 "for is exactly the spend worth looking at"),
    }
    if dimension in NO_WRITER:
        out["has_writer"] = False
        out["why_unattributed"] = (
            f"nothing in this system writes a {dimension} onto a cost row -- there is no "
            f"column for it and no writer for the detail key. These dollars are untagged "
            f"because they cannot be tagged, which is a different fault from a call site "
            f"that forgot, and it is fixed in a different place")
    elif dimension == "experiment":
        # C-86 (independent audit of 15c5d1b): the only writer of a tagged experiment row was
        # a test fixture. Experiments are decided from readings and enqueue no work today, so
        # a writer exists only when a tagged row actually exists in the window -- and its
        # absence is said plainly rather than read as zero cost per experiment.
        tagged = [r for r in out["rows"] if r.get("basis") == BASIS_TAGGED]
        out["has_writer"] = bool(tagged)
        if not tagged:
            out["why_unattributed"] = (
                "no experiment-driven job spent in this window: experiments are registered "
                "and decided from readings and enqueue no work of their own yet, so cost per "
                "experiment is UNMEASURED here, not zero. The day experiment work is "
                "enqueued it must carry inputs['experiment'] to be attributed")
    else:
        out["has_writer"] = True
    return out


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


# F-319: the product milestones a listing advances through, each an audit row whose artifact
# is the product slug. "Advanced" means a milestone reached in the window that the product had
# not reached before it -- re-running a step is not progress.
ADVANCEMENT_ACTIONS: tuple[str, ...] = ("gate.certified", "listing.seo_drafted",
                                        "listing.drafted", "listing.mobile_qa",
                                        "listing.parity")
LISTING_MILESTONE = "listing.drafted"


@contextmanager
def _reader(db):
    """A session from a `Database`, or the session itself (`/api/governor` passes one)."""
    if callable(getattr(db, "session", None)):
        with db.session() as s:
            yield s
    else:
        yield db


def spend_to_progress(db, *, days: int = 30, now: datetime | None = None) -> dict:
    """F-319: cost per milestone and per listing advanced, by product, from the ledger.

    Spend is joined to progress by product (`CostEntry.product_slug` against the milestone's
    audit artifact). Spend with no product is reported as shared, never spread across the
    products to flatter them. A product that spent and advanced nothing has no ratio -- its
    cost per advance is None and it is named, because dividing by zero progress is the thing
    this ratio exists to expose."""
    from sqlalchemy import select

    from ..core.models import AuditLog, CostEntry

    now = now or datetime.now(timezone.utc)
    since = now - timedelta(days=days)
    with _reader(db) as s:
        spend: dict[str, float] = {}
        shared = 0.0
        for slug, amount in s.execute(select(CostEntry.product_slug, CostEntry.amount_cad)
                                      .where(CostEntry.at >= since)).all():
            if slug:
                spend[slug] = spend.get(slug, 0.0) + float(amount or 0.0)
            else:
                shared += float(amount or 0.0)
        before: set[tuple[str, str]] = set()
        reached: dict[str, set[str]] = {}
        for action, artifact, at in s.execute(select(
                AuditLog.action, AuditLog.artifact, AuditLog.at)
                .where(AuditLog.action.in_(ADVANCEMENT_ACTIONS))).all():
            if not artifact:
                continue
            if _aware(at) < since:
                before.add((artifact, action))
            else:
                reached.setdefault(artifact, set()).add(action)
    products = {}
    for slug in sorted(set(spend) | set(reached)):
        new = sorted(a for a in reached.get(slug, set()) if (slug, a) not in before)
        cad = round(spend.get(slug, 0.0), 6)
        listing = LISTING_MILESTONE in new
        products[slug] = {
            "spent_cad": cad, "milestones_advanced": new,
            "cad_per_milestone": round(cad / len(new), 6) if new else None,
            "listing_advanced": listing,
            "spent_without_progress": bool(cad > 0 and not new)}
    advanced = sum(len(p["milestones_advanced"]) for p in products.values())
    listings = sum(1 for p in products.values() if p["listing_advanced"])
    attributed = round(sum(spend.values()), 6)
    return {
        "window_days": days, "attributed_cad": attributed, "shared_cad": round(shared, 6),
        "milestones_advanced": advanced, "listings_advanced": listings,
        "cad_per_milestone_advanced": round(attributed / advanced, 6) if advanced else None,
        "cad_per_listing_advanced": round(attributed / listings, 6) if listings else None,
        "spent_without_progress": sorted(k for k, v in products.items()
                                         if v["spent_without_progress"]),
        "products": products,
        "milestones": list(ADVANCEMENT_ACTIONS),
        "note": ("product spend over milestones that product newly reached; shared spend is "
                 "kept apart rather than spread, so a ratio is never flattered by money no "
                 "product owns")}


def report(db, *, days: int = 30, now: datetime | None = None) -> dict:
    """Everything the governor can honestly say today."""
    return {
        "attribution": attribution(db, days=days, now=now),
        "spend_to_progress": spend_to_progress(db, days=days, now=now),
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


# ---------------------------------------------------------------------------
# #188 on a cadence: detection that acts
#
# Everything above answered when asked and enforced nothing: an anomaly was a dictionary on
# `/api/governor`, and the spike it described kept spending. `enforce` is the cadence's half.
# It runs the same three readings over the same rows, and each one that is measurable is acted
# on through a mechanism that already exists:
#
# * **An agent whose own spend spikes is paused** by a hold in the reservation table for the
#   rest of its UTC day, sized at exactly what its daily permission still allows. The ceiling
#   check at dispatch counts other holders' live reservations against the agent's permission,
#   so the agent's next call is refused there -- with the refusal recorded like every other --
#   and no ceiling is raised, lowered or rewritten. The hold expires at the day boundary, when
#   the daily permission itself resets, and it is reported rather than hidden: it also counts
#   against the month, which only ever makes the month stricter. An incident names the spike.
# * **Marginal value below the threshold** opens an incident for the owner. It does not pause
#   anything: spend that has not yet returned money is a decision, not a runaway.
# * **The parallelism advice** is written onto the latest swarm allocation and read back by
#   `swarm.orchestrate.lane_concurrency`, which holds a lane to one running job when adding
#   workers only duplicated work.
#
# A reading that is not measurable acts on nothing and says why. That is the rule the rest of
# this module is built on, and a cadence is not a reason to relax it.

ANOMALY_SIGNATURE = "spend-anomaly"
MARGINAL_SIGNATURE = "marginal-value-below-threshold"
HOLD_HOLDER_PREFIX = "governor:anomaly:"
HOLD_PURPOSE = "governor.anomaly_pause"
# Revenue per dollar of spend below which the spend has not paid for itself. The break-even
# point, and deliberately not a target: a spend returning 1.1x is not being endorsed.
MIN_RETURN_PER_DOLLAR = 1.0
# How far back the parallelism comparison reads its own recorded observations.
PARALLELISM_WINDOW_DAYS = 7
ACTION = "finance.governor"


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _judge_series(by_day: dict[str, float], today: str) -> dict:
    """The spike rule `anomaly` applies, over one series of daily spend."""
    history = [v for k, v in by_day.items() if k != today]
    today_spend = round(by_day.get(today, 0.0), 6)
    if len(history) < MIN_DAYS_FOR_BASELINE:
        return {"measurable": False, "days_of_history": len(history),
                "needs_days": MIN_DAYS_FOR_BASELINE, "today_cad": today_spend,
                "why": (f"{len(history)} day(s) of history against a floor of "
                        f"{MIN_DAYS_FOR_BASELINE}; a first observation is not a spike")}
    mid = median(history)
    mad = median([abs(v - mid) for v in history]) or 0.0
    threshold = max(mid + SPIKE_MADS * mad, mid + SPIKE_FLOOR_CAD)
    return {"measurable": True, "days_of_history": len(history), "today_cad": today_spend,
            "ordinary_day_cad": round(mid, 6), "threshold_cad": round(threshold, 6),
            "spike": today_spend > threshold,
            "why": (f"CA${today_spend} against an ordinary day of CA${round(mid, 4)} and a "
                    f"threshold of CA${round(threshold, 4)}")}


def agent_anomalies(session, *, days: int = 60, now: datetime | None = None) -> dict:
    """The spike rule per agent, so a spike can be attributed to the agent that is spending.

    A company-wide spike says money is leaving faster than usual; only a per-agent one says
    whose spend to pause. Each agent is judged against its own history with the same floors,
    so an agent with a fortnight of pennies is not a spike on its first real day.
    """
    now = now or datetime.now(timezone.utc)
    entries, _ = _rows(session, days=days, now=now)
    series: dict[str, dict[str, float]] = {}
    for entry in entries:
        agent = str(entry.agent or "").strip() or UNATTRIBUTED
        day = _aware(entry.at).date().isoformat()
        by_day = series.setdefault(agent, {})
        by_day[day] = by_day.get(day, 0.0) + float(entry.amount_cad or 0.0)
    today = now.date().isoformat()
    verdicts = {agent: _judge_series(by_day, today) for agent, by_day in series.items()}
    return {"agents": verdicts,
            "spiking": sorted(a for a, v in verdicts.items() if v.get("spike")),
            "unmeasurable": sorted(a for a, v in verdicts.items() if not v["measurable"])}


def observe_parallelism(session, *, since: datetime | None,
                        now: datetime | None = None) -> dict | None:
    """One observation of worker count against completions, taken by this cadence run.

    Nothing records which worker completed a job -- completion clears the lease -- so the
    worker count is read as the distinct live lease holders at this instant, which includes
    the worker running this cadence and is therefore never zero in a real run. It is a lower
    bound on the workers present, and it is labelled as one. Completions are the jobs
    finished since the previous governor run. With no previous run there is no interval, and
    no observation is invented.
    """
    from sqlalchemy import func, select

    from ..core.models import Job, JobStatus

    now = now or datetime.now(timezone.utc)
    if since is None or since >= now:
        return None
    holders = {h for h, lease in session.execute(
        select(Job.leased_by, Job.lease_expires_at).where(
            Job.status == JobStatus.RUNNING, Job.leased_by.is_not(None))).all()
        if lease is None or _aware(lease) > now}
    if not holders:
        return None
    completed = int(session.scalar(select(func.count()).select_from(Job).where(
        Job.status == JobStatus.DONE, Job.finished_at > since,
        Job.finished_at <= now)) or 0)
    return {"workers": len(holders), "minutes": round((now - since).total_seconds() / 60, 3),
            "completed": completed, "at": now.isoformat(),
            "workers_read_as": "distinct live lease holders at the observation instant"}


def _governor_history(session, *, days: int, now: datetime) -> list[dict]:
    from sqlalchemy import select

    from ..core.models import AuditLog

    since = now - timedelta(days=days)
    return [dict(r.detail or {}) | {"_at": _aware(r.at)} for r in session.scalars(
        select(AuditLog).where(AuditLog.action == ACTION).order_by(AuditLog.id))
        if _aware(r.at) >= since]


def _pause_agent(db, agent: str, verdict: dict, *, now: datetime) -> dict:
    """Hold what this agent may still spend today, so its next call is refused at dispatch."""
    from ..finance import reservations
    from ..gateway.anthropic import agent_daily_ceiling

    permission = agent_daily_ceiling(db, agent, now=now)
    if permission is None:
        return {"paused": False, "agent": agent,
                "why": (f"{agent!r} has no daily permission in the registry, so there is no "
                        f"per-agent ceiling to hold. The month's ceiling still refuses; the "
                        f"incident is the owner's signal")}
    holder = f"{HOLD_HOLDER_PREFIX}{agent}"
    live = [r for r in reservations.outstanding(db, now=now)["reservations"]
            if r["holder"] == holder]
    if live:
        return {"paused": True, "agent": agent, "reservation": live[0]["id"],
                "already": True, "why": "already held for the rest of this UTC day"}
    remaining = max(0.0, permission["daily_ceiling_cad"] - permission["spent_today_cad"])
    midnight = datetime.combine(now.date() + timedelta(days=1), datetime.min.time(),
                                tzinfo=timezone.utc)
    rid = reservations.reserve(
        db, amount_cad=remaining, holder=holder, agent=agent, purpose=HOLD_PURPOSE,
        ttl_seconds=max(1, int((midnight - now).total_seconds())), now=now,
        detail={"why": verdict.get("why"), "spike": verdict})
    return {"paused": True, "agent": agent, "reservation": rid,
            "held_cad": round(remaining, 6), "until": midnight.isoformat(),
            "why": (f"a hold of CA${remaining:.4f} -- everything {agent}'s daily permission "
                    f"of CA${permission['daily_ceiling_cad']:.2f} still allows -- stands in "
                    f"the reservation table until the UTC day ends, so its next call is "
                    f"refused by the ceiling check at dispatch. No ceiling was changed")}


def _open_incident(session, *, signature: str, summary: str, detail: dict,
                   severity: str = "P2") -> str:
    from sqlalchemy import select

    from ..core.models import Incident

    existing = session.scalar(select(Incident).where(
        Incident.signature == signature, Incident.resolved.is_(False)))
    if existing is not None:
        existing.report_count += 1
        existing.detail = detail
        return "still_open"
    session.add(Incident(severity=severity, signature=signature, summary=summary,
                         halts_publication=False, detail=detail))
    return "opened"


# #31 (C-68): validated products per operating dollar, measured hourly and acted on. Below
# this much spend in the window the ratio is noise; above it, spend that produced no validated
# pattern is an incident, and the lanes that spent it are capped at the next allocation.
MIN_SPEND_FOR_THROUGHPUT_CAD = 5.0
MIN_AGENT_SPEND_CAD = 1.0
THROUGHPUT_SIGNATURE = "throughput-no-validated-output"


def _act_on_unit_cost(db, *, now: datetime) -> dict:
    from sqlalchemy import select

    from ..core.models import CostEntry
    from . import unit_cost

    try:
        uc = unit_cost.unit_costs(db, days=30, now=now)
    except Exception as exc:  # noqa: BLE001 - an unreadable ratio acts on nothing
        return {"measurable": False, "why": f"{type(exc).__name__}: {exc}"[:200]}
    spent = float(uc["operating_cost_cad"] or 0.0)
    validated = int(uc["artefacts"]["validated_pattern"]["produced"])
    out = {"measurable": spent >= MIN_SPEND_FOR_THROUGHPUT_CAD,
           "operating_cost_cad": spent, "validated_products": validated,
           "validated_products_per_operating_dollar":
               uc["validated_products_per_operating_dollar"],
           "contribution_per_operating_dollar": uc["contribution_per_operating_dollar"],
           "burning": uc["burning"], "action": "none", "unproductive_agents": []}
    if not out["measurable"]:
        out["why"] = (f"CA${spent:.2f} spent in 30 days, under the CA$"
                      f"{MIN_SPEND_FOR_THROUGHPUT_CAD:.2f} below which the ratio is noise")
        return out
    if validated == 0:
        since = now - timedelta(days=30)
        by_agent: dict[str, float] = {}
        with db.session() as s:
            for c in s.scalars(select(CostEntry).where(CostEntry.at >= since)):
                by_agent[c.agent] = by_agent.get(c.agent, 0.0) + float(c.amount_cad or 0.0)
            state = _open_incident(
                s, signature=f"{THROUGHPUT_SIGNATURE}:{now.strftime('%Y-%m')}",
                summary=(f"CA${spent:.2f} of operating spend in 30 days produced no validated "
                         f"pattern (#31: validated products per operating dollar is 0). The "
                         f"lanes that spent it are capped at one specialist until a pattern "
                         f"validates"),
                detail={"unit_cost": out, "by_agent": by_agent}, severity="P2")
        out["unproductive_agents"] = sorted(a for a, v in by_agent.items()
                                            if v >= MIN_AGENT_SPEND_CAD)
        out.update({"action": "incident_and_lane_cap", "incident": state})
    return out


def unproductive_lanes(db, *, now: datetime | None = None) -> list[str]:
    """The agents the latest governor reading capped for spending without validated output."""
    from sqlalchemy import desc, select

    from ..core.models import AuditLog

    now = now or datetime.now(timezone.utc)
    with db.session() as s:
        row = s.scalar(select(AuditLog).where(AuditLog.action == ACTION)
                       .order_by(desc(AuditLog.id)).limit(1))
    if row is None or now - _aware(row.at) > timedelta(hours=6):
        return []
    return list(((row.detail or {}).get("unit_cost") or {}).get("unproductive_agents") or [])


def enforce(db, *, days: int = 30, now: datetime | None = None) -> dict:
    """Run the governor's readings and act on the ones that are measurable (#188)."""
    from sqlalchemy import desc, select

    from ..core.models import AuditLog, SwarmAllocation

    now = now or datetime.now(timezone.utc)
    today = now.date().isoformat()
    with db.session() as s:
        company = anomaly(s, now=now)
        agents = agent_anomalies(s, now=now)
        value = marginal_value(s, days=days, now=now)
        history = _governor_history(s, days=PARALLELISM_WINDOW_DAYS, now=now)
        previous_at = history[-1]["_at"] if history else None
        observation = observe_parallelism(s, since=previous_at, now=now)

    paused, incidents = [], []
    for agent in agents["spiking"]:
        verdict = agents["agents"][agent]
        pause = (_pause_agent(db, agent, verdict, now=now) if agent != UNATTRIBUTED else
                 {"paused": False, "agent": agent,
                  "why": "spend with no agent on the row cannot be paused by agent"})
        paused.append(pause)
        with db.session() as s:
            state = _open_incident(
                s, signature=f"{ANOMALY_SIGNATURE}:{agent}:{today}",
                summary=(f"Spend anomaly: {agent} has spent CA${verdict['today_cad']} today "
                         f"against an ordinary day of CA${verdict['ordinary_day_cad']}. "
                         + ("Its spend is paused for the rest of the UTC day."
                            if pause.get("paused") else pause["why"])),
                detail={"agent": agent, "verdict": verdict, "pause": pause})
        incidents.append({"signature": f"{ANOMALY_SIGNATURE}:{agent}:{today}",
                          "state": state})
    if company.get("measurable") and company.get("spike") and not agents["spiking"]:
        with db.session() as s:
            state = _open_incident(
                s, signature=f"{ANOMALY_SIGNATURE}:company:{today}",
                summary=(f"Spend anomaly across the company with no single agent spiking: "
                         f"{company['why']}. Nothing is paused, because no agent's own "
                         f"history marks it as the cause"),
                detail={"company": company})
        incidents.append({"signature": f"{ANOMALY_SIGNATURE}:company:{today}",
                          "state": state})

    marginal = {"measurable": bool(value.get("measurable")), "action": "none"}
    if value.get("measurable") and value.get("return_per_dollar") is not None \
            and value["return_per_dollar"] < MIN_RETURN_PER_DOLLAR:
        with db.session() as s:
            state = _open_incident(
                s, signature=f"{MARGINAL_SIGNATURE}:{today[:7]}",
                summary=(f"Spend returned CA${value['return_per_dollar']} per dollar over "
                         f"{days} days, below the break-even threshold of "
                         f"{MIN_RETURN_PER_DOLLAR}. Nothing is paused: this is the owner's "
                         f"decision about spend that has not yet paid for itself"),
                detail={"marginal_value": value}, severity="P3")
        marginal = {"measurable": True, "action": "incident", "state": state,
                    "return_per_dollar": value["return_per_dollar"]}
    elif not value.get("measurable"):
        marginal["why"] = value.get("why")

    observations = [h["observation"] for h in history if h.get("observation")]
    if observation:
        observations.append(observation)
    advice = parallelism([{k: o[k] for k in ("workers", "minutes", "completed")}
                          for o in observations])
    fed = None
    with db.session() as s:
        alloc = s.scalar(select(SwarmAllocation).order_by(desc(SwarmAllocation.id)).limit(1))
        if alloc is not None:
            alloc.detail = {**dict(alloc.detail or {}),
                            "parallelism": {"advice": advice.get("advice"),
                                            "why": advice.get("why"),
                                            "compared": advice.get("compared"),
                                            "from": ACTION, "at": now.isoformat()}}
            fed = alloc.id

    throughput = _act_on_unit_cost(db, now=now)
    # F-305/F-308/F-315/F-326: the waste shapes a daily spike misses (retry storms, a spiking
    # hour, identical evidence bought by several jobs, untraceable spend, oversized inputs).
    try:
        from . import spend_hygiene

        hygiene = spend_hygiene.sweep(db, now=now)
    except Exception as exc:  # noqa: BLE001 - a detector fault must not stop the governor
        hygiene = {"error": f"{type(exc).__name__}: {exc}"[:300]}

    detail = {
        "at": now.isoformat(),
        "unit_cost": throughput,
        "hygiene": hygiene,
        "company_anomaly": company,
        "agent_anomalies": {"spiking": agents["spiking"],
                            "unmeasurable": agents["unmeasurable"],
                            "measured": sorted(a for a, v in agents["agents"].items()
                                               if v["measurable"])},
        "paused": paused,
        "incidents": incidents,
        "marginal_value": marginal,
        "observation": observation,
        "parallelism": {"advice": advice.get("advice"), "why": advice.get("why"),
                        "compared": advice.get("compared"),
                        "observations": len(observations)},
        "allocation_fed": fed,
        "ceilings_changed": 0,
    }
    with db.session() as s:
        s.add(AuditLog(actor="cfo", action=ACTION, detail=detail))
    return detail
