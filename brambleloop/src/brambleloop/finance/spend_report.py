"""What the money bought, by every dimension the owner asked to see it by.

The spend-accounting instruction is specific: track every billable call by provider, model,
agent, department, product and purpose; keep the pre-call reservation and the post-call
reconciliation; and never let unknown spend read as zero.

**"What did the money produce" has to be a query, not an archaeology exercise.** Those
dimensions lived in a JSON blob before, written where somebody remembered to write them. A
dimension that has to be grepped out of a JSON field is a dimension nobody reports on, which
is how a spend review becomes a total and an anecdote.

**Unknown is not zero, and it is not hidden either.** A row whose purpose or model was never
recorded is counted under `unattributed` with its dollars intact. A report that silently
dropped those would show a smaller, tidier number that does not match the bill -- and the gap
would be exactly the spending nobody could account for, which is the spending worth finding.

**The reservation and the bill are kept side by side.** An estimate nobody compares against
the invoice can drift by a factor of three, and did: this gateway priced its deep tier at a
third of its real rate for a session, so every ceiling check in that session was computed
against the wrong number and none of them failed. Variance is reported per purpose, because a
purpose whose estimates are consistently low is a ceiling with a hole in it.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

UNATTRIBUTED = "unattributed"

# An estimate this far from the bill, consistently, is a pricing fault rather than noise.
# One call can be anything; a purpose whose estimates average outside this band is a ceiling
# check that has stopped meaning what it says.
VARIANCE_TOLERANCE = 0.25


def _month_bounds(now: datetime | None = None) -> tuple[datetime, datetime]:
    """The calendar month, not "the month so far".

    The upper bound was `now`, which quietly dropped any row timestamped a few seconds
    ahead of the reader's clock -- two processes, two clocks, and spend that exists and does
    not appear. A report that hides money because of skew is the same fault as one that
    drops unattributed rows, in a costume that looks like correctness. Elapsed time for the
    burn rate is still measured to `now`; what changed is which rows count.
    """
    now = now or datetime.now(timezone.utc)
    start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
    end = datetime(now.year + (now.month // 12), (now.month % 12) + 1, 1,
                   tzinfo=timezone.utc)
    return start, end


def _aware(value):
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def rows(db, *, now: datetime | None = None, kind: str = "llm") -> list:
    from sqlalchemy import select

    from ..core.models import CostEntry

    start, end = _month_bounds(now)
    with db.session() as s:
        return [r for r in s.scalars(select(CostEntry).where(CostEntry.kind == kind))
                if start <= (_aware(r.at) or start) < end]


def _bucket(rows_, attribute: str) -> dict:
    out: dict[str, dict] = {}
    for row in rows_:
        key = (getattr(row, attribute, "") or "").strip() or UNATTRIBUTED
        bucket = out.setdefault(key, {"cad": 0.0, "calls": 0,
                                      "tokens_in": 0, "tokens_out": 0})
        bucket["cad"] = round(bucket["cad"] + float(row.amount_cad or 0.0), 6)
        bucket["calls"] += 1
        bucket["tokens_in"] += int(row.tokens_in or 0)
        bucket["tokens_out"] += int(row.tokens_out or 0)
    return dict(sorted(out.items(), key=lambda kv: -kv[1]["cad"]))


def variance(rows_) -> dict:
    """Reservation against bill, per purpose.

    Only over rows that carry an estimate. A row with none is not a variance of zero -- it is
    a call whose reservation nobody recorded, and it is counted separately so the two cannot
    be confused.
    """
    out: dict[str, dict] = {}
    unestimated = 0
    for row in rows_:
        estimate = float(row.estimated_cad or 0.0)
        if estimate <= 0:
            unestimated += 1
            continue
        key = (row.purpose or "").strip() or UNATTRIBUTED
        bucket = out.setdefault(key, {"estimated_cad": 0.0, "actual_cad": 0.0, "calls": 0})
        bucket["estimated_cad"] = round(bucket["estimated_cad"] + estimate, 6)
        bucket["actual_cad"] = round(bucket["actual_cad"] + float(row.amount_cad or 0.0), 6)
        bucket["calls"] += 1

    for key, bucket in out.items():
        estimated = bucket["estimated_cad"]
        bucket["ratio"] = round(bucket["actual_cad"] / estimated, 4) if estimated else None
        bucket["within_tolerance"] = (
            bucket["ratio"] is not None
            and abs(bucket["ratio"] - 1.0) <= VARIANCE_TOLERANCE)
        # Under-estimating is the direction that matters: it is the ceiling being checked
        # against a number smaller than the bill.
        bucket["under_estimated"] = bucket["ratio"] is not None and bucket["ratio"] > 1.0

    return {
        "by_purpose": dict(sorted(out.items(), key=lambda kv: -kv[1]["actual_cad"])),
        "calls_with_no_reservation": unestimated,
        "tolerance": VARIANCE_TOLERANCE,
        "why_it_matters": (
            "an estimate nobody compares against the bill can drift by a factor of three, "
            "and did. Every ceiling check in that session was computed against the wrong "
            "number and none of them failed"),
    }


def what_it_bought(db, *, now: datetime | None = None) -> dict:
    """This month's spend, by every dimension, with burn rate and projection.

    The projection is linear and says so. A month with one expensive weekly cadence in it is
    not linear, and a projection presented without that caveat is a forecast rather than an
    arithmetic convenience.
    """
    now = now or datetime.now(timezone.utc)
    start, _ = _month_bounds(now)
    month = rows(db, now=now)
    spent = round(sum(float(r.amount_cad or 0.0) for r in month), 6)

    elapsed_days = max((now - start).total_seconds() / 86400.0, 1.0 / 24)
    days_in_month = (date(now.year + (now.month // 12), (now.month % 12) + 1, 1)
                     - date(now.year, now.month, 1)).days
    burn = round(spent / elapsed_days, 6)

    return {
        "month": start.date().isoformat(),
        "spent_cad": spent,
        "calls": len(month),
        "burn_rate_cad_per_day": burn,
        "projected_month_end_cad": round(burn * days_in_month, 4),
        "projection_is_linear": (
            "a month holding one expensive weekly cadence is not linear, so this is "
            "arithmetic rather than a forecast"),
        "by_purpose": _bucket(month, "purpose"),
        "by_model": _bucket(month, "model"),
        "by_provider": _bucket(month, "provider"),
        "by_agent": _bucket(month, "agent"),
        "by_department": _bucket(month, "department"),
        "by_product": _bucket(month, "product_slug"),
        "reconciliation": variance(month),
        "unattributed_note": (
            f"rows with no recorded dimension are counted under {UNATTRIBUTED!r} with their "
            f"dollars intact. Dropping them would show a tidier number that does not match "
            f"the bill, and the gap would be exactly the spending nobody could account for"),
    }


def record(db, *, agent: str, amount_cad: float, purpose: str, provider: str = "",
           model: str = "", department: str = "", product_slug: str = "",
           estimated_cad: float = 0.0, tokens_in: int = 0, tokens_out: int = 0,
           job_id: int | None = None, kind: str = "llm", detail: dict | None = None) -> int:
    """One billable call, with every dimension the owner asked to see it by.

    A single writer so the dimensions cannot be optional by accident. They were optional
    before -- written into a JSON blob where somebody remembered -- and the result was a
    ledger that could total and could not explain.
    """
    from ..core.models import CostEntry

    with db.session() as s:
        row = CostEntry(
            agent=agent, job_id=job_id, kind=kind,
            amount_cad=round(float(amount_cad), 8),
            estimated_cad=round(float(estimated_cad), 8),
            tokens_in=int(tokens_in), tokens_out=int(tokens_out),
            provider=provider, model=model, department=department,
            product_slug=product_slug, purpose=purpose,
            detail=dict(detail or {}))
        s.add(row)
        s.flush()
        return row.id
