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
from .listing_costs import cost_basis, basis_summary

from contextlib import contextmanager
from contextvars import ContextVar
from datetime import date, datetime, timedelta, timezone

UNATTRIBUTED = "unattributed"

# ---------------------------------------------------------------------------
# Product attribution (F-321/F-324/F-325/F-329)
#
# Every billable writer used to pass `product_slug=""` because none of them knew which product
# they were working for: the slug lives in the *job*, and the spend happens five calls deep
# in a gateway or a vision judge that was never handed it. The result was a ledger where only
# test fixtures carried a product, so `sustainability.forecast` was INSUFFICIENT_DATA by
# construction and the launch requirement `sustainable_economics` could never pass.
#
# The slug is therefore carried as job context rather than threaded through forty
# signatures: the worker opens `attributed_to(job_product(db, job))` around the handler, and
# `record`, the reservation and the gateway's own cost row read it when the caller named no
# product. Spend outside any product job -- cadences, probes, research -- stays untagged and
# is labelled `shared` in its detail, which is platform spend, not a product's creation cost.

ATTRIBUTION_PRODUCT = "product"
ATTRIBUTION_SHARED = "shared"

_CURRENT_PRODUCT: ContextVar[str] = ContextVar("brambleloop_spend_product", default="")


def current_product() -> str:
    """The product the running job works for, or "" when the spend is shared."""
    return _CURRENT_PRODUCT.get()


class JobSlug(str):
    """The product slug a job's spend belongs to, carrying the job it was read from.

    `job_product` returns one so that the worker's existing
    `attributed_to(job_product(db, job))` also opens the paid-call job scope (F-307,
    `gateway.paid_calls`) without a second argument at the call site. It is an ordinary
    string everywhere else ("" when the spend is shared)."""

    db = None
    job = None

    def __new__(cls, value: str, *, db=None, job=None):
        obj = super().__new__(cls, value)
        obj.db, obj.job = db, job
        return obj


@contextmanager
def attributed_to(product_slug: str | None, *, job=None, db=None):
    """Attribute every spend write inside this block to `product_slug` ("" = shared).

    With a job (passed explicitly, or carried by a `JobSlug`), every paid call inside the
    block is also guarded against re-execution of that job (`gateway.paid_calls`): a reclaimed
    or retried attempt replays what the earlier one paid for rather than paying again."""
    job = job if job is not None else getattr(product_slug, "job", None)
    db = db if db is not None else getattr(product_slug, "db", None)
    token = _CURRENT_PRODUCT.set(str(product_slug or "")[:80])
    try:
        if job is not None and db is not None:
            from ..gateway import paid_calls

            with paid_calls.job_scope(db, job):
                yield
        else:
            yield
    finally:
        _CURRENT_PRODUCT.reset(token)


def job_product(db, job) -> str:
    """The product a job's spend is attributable to, or "" when it is genuinely shared.

    Reads the slug wherever job inputs carry it (`slug`, `product_slug`, `cir.slug`). A slug
    is only a *product* when the catalogue knows the product (a `Product` or `Listing` row);
    a slug naming anything else -- a lesson, a season, a benchmark -- is not a product and its
    spend stays shared rather than being mis-charged to a product's break-even.

    RC1 audit F1: a `cir` dict in the job inputs used to be trusted on its own say-so (any
    job could charge any slug's break-even by carrying `{"cir": {"slug": ...}}`). Job inputs
    are data, not evidence, so the CIR's slug is now checked against the catalogue like
    every other slug. Unattributable spend is not lost: it stays in platform spend, where
    the ceiling and the forecast still count it.
    """
    return JobSlug(_job_slug(db, job), db=db, job=job)


def _job_slug(db, job) -> str:
    inputs = getattr(job, "inputs", None)
    inputs = inputs if isinstance(inputs, dict) else {}
    cir = inputs.get("cir") if isinstance(inputs.get("cir"), dict) else {}
    slug = str(inputs.get("slug") or inputs.get("product_slug") or cir.get("slug") or "")
    if not slug:
        return ""
    try:
        from sqlalchemy import select

        from ..core.models import Listing, Product

        with db.session() as s:
            known = (s.scalar(select(Product.id).where(Product.slug == slug).limit(1))
                     or s.scalar(select(Listing.id).where(Listing.product_slug == slug)
                                 .limit(1)))
    except Exception:  # noqa: BLE001 - attribution must never fail the job it describes
        return ""
    return slug if known else ""


def attribution(product_slug: str, detail: dict | None) -> tuple[str, dict]:
    """(slug, detail) with the context applied and the attribution labelled.

    An explicit `{"attribution": "shared"}` inside a product job is honoured -- some spend
    in a product job genuinely is platform spend -- but it is no longer silent (RC1 audit
    F1): the row carries `shared_override_of` naming the product it was *not* charged to,
    so an override that hides a product's creation cost is visible in the ledger itself.
    """
    out = dict(detail or {})
    running = current_product()
    if not product_slug and out.get("attribution") != ATTRIBUTION_SHARED:
        product_slug = running
    elif not product_slug and running:
        out["shared_override_of"] = running
    out["attribution"] = ATTRIBUTION_PRODUCT if product_slug else ATTRIBUTION_SHARED
    return product_slug, out


SHARED_OVERRIDE_ACTION = "spend.attribution_shared_override"

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


def _week_bounds(now: datetime | None = None) -> tuple[datetime, datetime]:
    """The ISO week: Monday 00:00 UTC to the next Monday, not "the last seven days".

    A rolling window and a calendar week answer different questions and the report has to
    say which one it is answering. The ceilings reset on calendar boundaries, so the period
    the owner compares against them is the calendar one.
    """
    now = now or datetime.now(timezone.utc)
    monday = datetime(now.year, now.month, now.day, tzinfo=timezone.utc) - timedelta(
        days=now.isoweekday() - 1)
    return monday, monday + timedelta(days=7)


def period_bounds(period: str, now: datetime | None = None) -> tuple[datetime, datetime]:
    if period == "month":
        return _month_bounds(now)
    if period == "week":
        return _week_bounds(now)
    raise ValueError(f"period must be 'month' or 'week', not {period!r}")


def rows(db, *, now: datetime | None = None, kind: str | None = None,
         period: str = "month") -> list:
    """The period's ledger rows. `kind=None` (the default) is every kind the monthly ceiling
    governs (`routing.counts_against_monthly_ceiling`) -- model, vision *and* image renders --
    so the report and the provider ceilings read what the ceiling reads. It defaulted to
    `"llm"`, and image renders (kind `image`, RC1 audit B2) would have been spend the ceiling
    counted and the report did not show."""
    from sqlalchemy import select

    from ..core.models import CostEntry
    from ..gateway import routing

    start, end = period_bounds(period, now)
    where = routing.ceiling_kind_filter() if kind is None else CostEntry.kind == kind
    with db.session() as s:
        return [r for r in s.scalars(select(CostEntry).where(where))
                if start <= (_aware(r.at) or start) < end]


# The audit action a ceiling refusal writes. A refusal that leaves no row is a guard whose
# work cannot be counted, and "how often did the ceiling actually say no this month" is the
# first question anybody asks about a ceiling. Read by name in `refusals` below over the
# calendar month only, so pruning older audit rows does not change what the count claims.
REFUSED_ACTION = "spend.refused"


def record_refusal(db, *, agent: str, ceiling_cad: float, estimate_cad: float,
                   committed_cad: float, which: str, why: str,
                   purpose: str = "", now: datetime | None = None,
                   detail: dict | None = None) -> None:
    """One audit row per refusal, with the four numbers the refusal was decided on.

    Never raises: a refusal is already an exception in flight, and a failure to write the
    record of it must not turn the refusal into a different error.
    """
    from ..core.models import AuditLog

    try:
        with db.session() as s:
            s.add(AuditLog(
                at=now or datetime.now(timezone.utc),
                actor=(agent or "gateway")[:64], action=REFUSED_ACTION,
                artifact=(purpose or which)[:200],
                detail={"ceiling": round(float(ceiling_cad), 6),
                        "estimate": round(float(estimate_cad), 6),
                        "committed": round(float(committed_cad), 6),
                        "agent": agent or "", "which": which, "purpose": purpose,
                        "why": why[:600], **dict(detail or {})}))
    except Exception:  # noqa: BLE001 - the refusal itself is what must reach the caller
        return


def refusals(db, *, now: datetime | None = None) -> dict:
    """This month's ceiling refusals, counted and split by which ceiling said no."""
    from sqlalchemy import select

    from ..core.models import AuditLog

    start, end = _month_bounds(now)
    action = REFUSED_ACTION
    by_which: dict[str, int] = {}
    by_agent: dict[str, int] = {}
    total = 0
    with db.session() as s:
        for row in s.scalars(select(AuditLog).where(AuditLog.action == action)):
            at = _aware(row.at)
            if at is None or not (start <= at < end):
                continue
            total += 1
            which = (row.detail or {}).get("which") or "unknown"
            by_which[which] = by_which.get(which, 0) + 1
            agent = (row.detail or {}).get("agent") or row.actor or UNATTRIBUTED
            by_agent[agent] = by_agent.get(agent, 0) + 1
    return {"month": start.date().isoformat(), "count": total,
            "by_ceiling": dict(sorted(by_which.items())),
            "by_agent": dict(sorted(by_agent.items(), key=lambda kv: -kv[1])),
            "why": ("every `check_budget` refusal writes one audit row with the ceiling, the "
                    "estimate and what was committed, so a ceiling that says no is a "
                    "ceiling whose work can be counted")}


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
        bucket = out.setdefault(key, {"estimated_cad": 0.0, "recorded_cad": 0.0, "calls": 0, "_basis": []})
        bucket["estimated_cad"] = round(bucket["estimated_cad"] + estimate, 6)
        bucket["recorded_cad"] = round(bucket["recorded_cad"] + float(row.amount_cad or 0.0), 6)
        bucket["_basis"].append((float(row.amount_cad or 0.0),cost_basis(row)))
        bucket["calls"] += 1

    for key, bucket in out.items():
        basis = basis_summary(bucket.pop("_basis"))
        bucket["cost_basis"] = basis
        bucket["actual_cad"] = basis["actual_cad"]
        bucket["comparison_basis"] = "recorded_exposure_vs_reservation"
        estimated = bucket["estimated_cad"]
        bucket["ratio"] = round(bucket["recorded_cad"] / estimated, 4) if estimated else None
        bucket["within_tolerance"] = (
            bucket["ratio"] is not None
            and abs(bucket["ratio"] - 1.0) <= VARIANCE_TOLERANCE)
        # Under-estimating is the direction that matters: it is the ceiling being checked
        # against a number smaller than the bill.
        bucket["under_estimated"] = bucket["ratio"] is not None and bucket["ratio"] > 1.0

    return {
        "by_purpose": dict(sorted(out.items(), key=lambda kv: -kv[1]["recorded_cad"])),
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
        "cost_basis": basis_summary((r.amount_cad or 0.0,cost_basis(r)) for r in month),
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
        # F-303: the closed economic class of every row, one-time creation apart from
        # recurring operation; unknown purposes counted as `unclassified`, never dropped.
        "by_economic_class": _economic(month),
        "reconciliation": variance(month),
        "unattributed_note": (
            f"rows with no recorded dimension are counted under {UNATTRIBUTED!r} with their "
            f"dollars intact. Dropping them would show a tidier number that does not match "
            f"the bill, and the gap would be exactly the spending nobody could account for"),
    }


def _economic(month) -> dict:
    from . import economics

    return economics.by_class(month)


def per_agent_today(db, *, now: datetime | None = None) -> dict:
    """What each agent has spent on the current UTC day, against its declared daily ceiling.

    This existed nowhere, and the gap is the point. `Agent.daily_cost_ceiling_cad` is
    checked in exactly one place -- `registry.record_cost`, which the model gateway uses --
    and `record` below is the single writer the owner's spend-accounting instruction
    created for everything else: vision, image generation, inspection, tournaments,
    reference packs, the probes. None of those paths consults an agent's ceiling, so a
    ceiling could be exceeded every day without any surface in this system saying so, and
    `/api/verify` asserted only that a number was configured.

    A reader, not a guard. It cannot refuse a spend that has already happened; it makes the
    overrun visible, which was the thing missing on 2026-09-24.

    **Enforcement now exists and is somewhere else.** On the owner's ruling of 2026-09-25,
    `gateway.anthropic.check_budget` checks the agent's ceiling *before* the call and raises
    `AgentCeilingExceeded`, as a permission rather than as a share of the budget -- the global
    monthly ceiling stays authoritative. So an agent appearing in `over` below now means one of
    two things, and they are different faults: rows written before the enforcement existed, or
    a spend path that does not pass its `agent` to `check_budget` (the `visual/**` writers
    still do not). This reader is what tells them apart, which is why it stayed a reader.

    All kinds, not just `llm`. An agent's daily ceiling is a limit on what that agent may
    spend, and a ceiling that ignores whichever kinds were added later is a ceiling that
    quietly stops covering the newest way to spend money.
    """
    from sqlalchemy import select

    from ..core.models import Agent, CostEntry

    now = now or datetime.now(timezone.utc)
    today = now.date()
    spent: dict[str, float] = {}
    with db.session() as s:
        for row in s.scalars(select(CostEntry)):
            at = _aware(row.at)
            if at is not None and at.date() == today:
                name = row.agent or UNATTRIBUTED
                spent[name] = round(spent.get(name, 0.0) + float(row.amount_cad or 0.0), 8)
        agents = [(a.name, float(a.daily_cost_ceiling_cad or 0.0))
                  for a in s.scalars(select(Agent))]

    rows = []
    over = []
    for name, ceiling in sorted(agents):
        today_cad = round(spent.pop(name, 0.0), 6)
        entry = {"agent": name, "spent_today_cad": today_cad, "daily_ceiling_cad": ceiling,
                 "share": round(today_cad / ceiling, 4) if ceiling else None}
        rows.append(entry)
        if ceiling > 0 and today_cad > ceiling:
            over.append(entry)
    # Spend attributed to a name that is not a registered agent has no ceiling at all, and
    # it is reported rather than dropped for the same reason `unattributed` is: the dollars
    # nobody has a story for are the dollars worth looking at.
    unregistered = [{"agent": name, "spent_today_cad": round(cad, 6),
                     "daily_ceiling_cad": None}
                    for name, cad in sorted(spent.items()) if cad]
    return {
        "day": today.isoformat(),
        "agents": rows,
        "over": over,
        "spenders_with_no_agent_row": unregistered,
        "why": ("an agent's daily ceiling is consulted by `registry.record_cost` and by "
                "nothing else. This is recorded exposure beside what was allowed"),
    }


def record(db, *, agent: str, amount_cad: float, purpose: str, provider: str = "",
           model: str = "", department: str = "", product_slug: str = "",
           estimated_cad: float = 0.0, tokens_in: int = 0, tokens_out: int = 0,
           job_id: int | None = None, kind: str = "llm", detail: dict | None = None) -> int:
    """One billable call, with every dimension the owner asked to see it by.

    A single writer so the dimensions cannot be optional by accident. They were optional
    before -- written into a JSON blob where somebody remembered -- and the result was a
    ledger that could total and could not explain.

    `product_slug` left empty takes the running job's product (`attributed_to`); a caller
    whose spend is genuinely shared passes `detail={"attribution": "shared"}` to keep it
    untagged even inside a product job.
    """
    import math

    from ..core.models import CostEntry

    # R2-FIN (audit L2): a cost row is money spent. A negative row would lower the month's
    # counted spend and re-grant budget under the ceiling; a NaN/inf row cannot be summed.
    # Both are refused here, before anything is written (a credit is not a cost row).
    try:
        amt = float(amount_cad)
    except (TypeError, ValueError):
        raise ValueError(f"amount_cad {amount_cad!r} is not a number") from None
    if not math.isfinite(amt) or amt < 0:
        raise ValueError(f"amount_cad {amount_cad!r} must be a finite, non-negative CAD "
                         "amount; a credit or refund is not recorded as a negative cost")
    product_slug, detail = attribution(product_slug, detail)
    # F-307: tie the row to the write-ahead paid-call intent it bills, and label a replayed
    # answer (nothing sent, so a zero amount) as exactly that rather than as a free call.
    from ..gateway import paid_calls

    note = (paid_calls.ledger_note()
            if "paid_call_key" not in detail and kind in ("llm", "image") else {})
    if note.get("replayed") and amt > 0:
        note = {"paid_call_key": note["paid_call_key"]}       # a real bill is never relabelled
    note.pop("replayed", None)
    detail.update(note)
    if detail.get("shared_override_of"):
        # F1: the override is audited as well as labelled, so "how much product-job spend
        # was declared shared" is a count rather than a scan of JSON details.
        from ..core.models import AuditLog

        with db.session() as s:
            s.add(AuditLog(actor=(agent or "gateway")[:64], action=SHARED_OVERRIDE_ACTION,
                           artifact=str(detail["shared_override_of"])[:200],
                           detail={"purpose": purpose, "amount_cad": round(float(amount_cad), 8),
                                   "kind": kind, "provider": provider, "job_id": job_id}))
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


# ---------------------------------------------------------------------------
# Drift: is the reservation still the bill?

# A purpose is judged on its estimates only once it has this many calls behind them. One call
# can be anything; twenty consistently outside the band is a price that is wrong.
DRIFT_MIN_CALLS = 20
# The share of the month's calls that may carry no reservation before the mechanism itself is
# the finding: past this, "the ceiling is checked before every call" is not what the ledger
# shows.
UNRESERVED_SHARE_TOLERANCE = 0.10


def _image_provider_keys() -> set[str]:
    try:
        from ..gateway.images import BY_KEY
    except Exception:  # noqa: BLE001 - a report must not fail on an import
        return set()
    return set(BY_KEY)


def estimate_drift(db, *, now: datetime | None = None) -> dict:
    """Whether the pre-call estimates still describe the bills, this month.

    `degraded` when a purpose with at least `DRIFT_MIN_CALLS` estimated calls averages
    outside `VARIANCE_TOLERANCE`, or when more than `UNRESERVED_SHARE_TOLERANCE` of the
    month's calls carry no reservation at all. Both are the same fault seen from two sides:
    a ceiling being checked against a number that is not the bill.

    Image rows are set aside and labelled `reconciles_by_construction`. An image is priced per
    image (`gateway.images.ImageProvider.cad_per_image`) and the reservation *is* that price,
    so estimate and bill agree by definition -- counting them would flatter every purpose that
    renders and hide the token-priced calls, which are the ones that can drift.
    """
    month = rows(db, now=now)
    image_keys = _image_provider_keys()
    image_rows = [r for r in month
                  if (r.provider or "") in image_keys or (r.model or "") in image_keys]
    # F-307: a replayed answer (nothing sent, CA$0) and an in-flight orphan (counted at its
    # estimate) say nothing about whether estimates describe bills, so neither is judged.
    def _billing(r) -> str:
        return str((r.detail or {}).get("billing") or "") if isinstance(r.detail, dict) else ""

    replayed = [r for r in month if _billing(r) == "replayed_not_billed"]
    orphaned = [r for r in month
                if _billing(r) == "in_flight_when_worker_lost_counted_at_estimate"]
    token_rows = [r for r in month
                  if r not in image_rows and r not in replayed and r not in orphaned]

    v = variance(token_rows)
    outside = {k: b for k, b in v["by_purpose"].items()
               if b["calls"] >= DRIFT_MIN_CALLS and not b["within_tolerance"]}
    unreserved = v["calls_with_no_reservation"]
    unreserved_share = round(unreserved / len(token_rows), 4) if token_rows else 0.0
    too_many_unreserved = token_rows and unreserved_share > UNRESERVED_SHARE_TOLERANCE

    reasons = []
    for key, bucket in outside.items():
        reasons.append(
            f"{key}: {bucket['calls']} calls estimated CA${bucket['estimated_cad']:.4f} and "
            f"recorded CA${bucket['recorded_cad']:.4f} ({bucket['cost_basis']['reading']}; ratio {bucket['ratio']}), outside "
            f"±{int(VARIANCE_TOLERANCE * 100)}%"
            + (" -- under-estimated, which is the direction that breaks the ceiling"
               if bucket["under_estimated"] else ""))
    if too_many_unreserved:
        reasons.append(
            f"{unreserved} of {len(token_rows)} token-priced calls ({unreserved_share * 100:.0f}%) "
            f"carry no reservation, over the {int(UNRESERVED_SHARE_TOLERANCE * 100)}% the "
            f"mechanism tolerates: those calls were checked against nothing")

    return {
        "state": "degraded" if reasons else "healthy",
        "degraded": bool(reasons),
        "why": "; ".join(reasons),
        "purposes_outside_tolerance": outside,
        "purposes_measured": {k: b for k, b in v["by_purpose"].items()
                              if b["calls"] >= DRIFT_MIN_CALLS and b["actual_cad"] is not None},
        "purposes_recorded": {k: b for k, b in v["by_purpose"].items() if b["calls"] >= DRIFT_MIN_CALLS},
        "purposes_too_few_calls_to_judge": sorted(
            k for k, b in v["by_purpose"].items() if b["calls"] < DRIFT_MIN_CALLS),
        "min_calls_to_judge": DRIFT_MIN_CALLS,
        "tolerance": VARIANCE_TOLERANCE,
        "calls_with_no_reservation": unreserved,
        "calls_with_no_reservation_share": unreserved_share,
        "unreserved_share_tolerance": UNRESERVED_SHARE_TOLERANCE,
        "token_priced_calls": len(token_rows),
        "replayed_not_billed_rows": len(replayed),
        "in_flight_orphans_counted_at_estimate": {
            "calls": len(orphaned),
            "cad": round(sum(float(r.amount_cad or 0.0) for r in orphaned), 6)},
        "image_rows": {"calls": len(image_rows),
                       "cad": round(sum(float(r.amount_cad or 0.0) for r in image_rows), 6),
                       "reconciles_by_construction": True,
                       "why": ("an image is priced per image and reserved at that price, so "
                               "its estimate and its recorded exposure agree by construction, not observed billing. Set aside so "
                               "it cannot flatter the token-priced calls that can drift")},
    }


def governance(db, *, now: datetime | None = None) -> dict:
    """The live spend controls in one reading, for the dashboard and the console.

    This is what `SpendLimit` was mistaken for. That table holds *scoped* caps -- paid media,
    which no agent has authority over -- and it is empty, so a dashboard reading it alone
    said "No spend limits configured." over a company whose every model call is refused
    against a monthly ceiling, an agent permission, a purpose allocation and a live
    reservation table. Every one of those is here, each from the function that enforces it,
    and each part is guarded so a fault in one leaves the others readable.
    """
    from ..core.models import SpendLimit
    from . import reservations, spend_policy

    now = now or datetime.now(timezone.utc)
    out: dict = {"as_of": now.isoformat()}

    def _part(key, build):
        try:
            out[key] = build()
        except Exception as exc:  # noqa: BLE001 - one unreadable control must not hide the rest
            out[key] = {"unavailable": f"{type(exc).__name__}: {exc}"[:200]}

    produced = what_it_bought(db, now=now)
    out["month"] = {"cost_basis": produced["cost_basis"], "spent_cad": produced["spent_cad"], "calls": produced["calls"],
                    "burn_rate_cad_per_day": produced["burn_rate_cad_per_day"],
                    "projected_month_end_cad": produced["projected_month_end_cad"],
                    "by_provider": produced["by_provider"]}
    out["headroom"] = spend_policy.headroom(produced["spent_cad"])
    _part("reservations", lambda: reservations.outstanding(db, now=now))
    _part("allocations", lambda: {
        purpose: spend_policy.may_spend(db, purpose, now=now)
        for purpose in sorted(spend_policy.ALLOCATION)})
    out["department_allocations"] = dict(spend_policy.DEPARTMENT_ALLOCATION)
    out["provider_ceilings_cad"] = dict(spend_policy.PROVIDER_CEILINGS_CAD)
    _part("agents", lambda: per_agent_today(db, now=now))
    _part("refusals", lambda: refusals(db, now=now))
    _part("drift", lambda: estimate_drift(db, now=now))
    _part("escalation", lambda: spend_policy.escalation(db, now=now))
    _part("binding", lambda: spend_policy.binding_ceiling(db, now=now))
    _part("vocabulary", lambda: spend_policy.vocabulary(db))

    def _scoped():
        with db.session() as s:
            from sqlalchemy import select
            limits = list(s.scalars(select(SpendLimit)))
        return {"count": len(limits),
                "limits": [{"scope": l.scope, "daily_cap_cad": l.daily_cap_cad,
                            "lifetime_cap_cad": l.lifetime_cap_cad,
                            "spent_today_cad": l.spent_today_cad,
                            "spent_lifetime_cad": l.spent_lifetime_cad,
                            "paused": l.paused} for l in limits],
                "why_none": ("" if limits else
                             "no scoped cap is configured: advertising authority has not "
                             "been granted, so there is no paid-media scope to cap. This is "
                             "not the model ceiling, which is live above")}
    _part("scoped_caps", _scoped)
    return out
