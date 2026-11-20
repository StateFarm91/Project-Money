"""F-330: post-launch cost learning -- unit economics reviewed at day 1, 7, 14, 30, then monthly.

The clock starts at the first live listing: the earliest `store.published` audit row (the
one action that puts a listing in front of buyers). Before it there is nothing to review and
the reading says so (UNMEASURED, never a zero dashboard).

At each milestone the review is filed once (`OperatingReading` kind `REVIEW_KIND`, keyed by
the milestone; idempotent) with:

* the unit economics over the window since launch (`finance.books`): cost per validated
  pattern, per listing, per customer -- each UNMEASURED where its denominator is;
* the profit and loss over the same window;
* **waste to cut**: the cost-learning routes that are `proposable` -- a cheaper route whose
  recorded evals already clear every floor the current one clears (`routing.equivalence`).
  A cheaper route without that evidence is listed as `blocked_by_quality_floor`, never as
  a saving: the product is not cheapened to make a cost figure green. Nothing here applies
  a change; `routing.override_route` stays the only door and refuses without evidence.

Spends nothing, calls no model.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

REVIEW_KIND = "finance.launch_cost_review"
MILESTONES = (1, 7, 14, 30)
THEREAFTER_DAYS = 30
FLOORS = ("Pattern Truth", "Product Truth", "photographic realism", "customer experience",
          "every certified quality floor")


def _aware(at: datetime) -> datetime:
    return at if at.tzinfo else at.replace(tzinfo=timezone.utc)


def first_live_at(db) -> datetime | None:
    from sqlalchemy import select

    from ..core.models import AuditLog

    with db.session() as s:
        at = s.scalar(select(AuditLog.at).where(AuditLog.action == "store.published")
                      .order_by(AuditLog.at).limit(1))
    return _aware(at) if at is not None else None


def due_milestones(launched: datetime, now: datetime) -> list[int]:
    days = (now - launched).total_seconds() / 86400
    out = [d for d in MILESTONES if days >= d]
    d = MILESTONES[-1] + THEREAFTER_DAYS
    while days >= d:
        out.append(d)
        d += THEREAFTER_DAYS
    return out


def _filed(db) -> set[str]:
    from sqlalchemy import select

    from ..core.models import OperatingReading

    with db.session() as s:
        return set(s.scalars(select(OperatingReading.period_key).where(
            OperatingReading.kind == REVIEW_KIND)))


def _waste(db, now) -> dict:
    from ..improve import cost_learning

    try:
        opp = cost_learning.opportunities(db, now=now)
    except Exception as exc:  # noqa: BLE001 - an unreadable opportunity list is UNKNOWN
        return {"state": "UNKNOWN", "why": f"{type(exc).__name__}: {str(exc)[:160]}"}
    cut = [r for r in opp["routes"] if r["status"] == "proposable"]
    held = [{"task": r["task"], "to_tier": r["to_tier"],
             "projected_saving_cad_month": r["projected_saving_cad_month"],
             "why": "no recorded evidence the cheaper route clears the same quality floors",
             "missing_evidence": r["missing_evidence"][:3]}
            for r in opp["routes"] if r["status"] != "proposable"
            and (r["projected_saving_cad_month"] or 0) > 0]
    return {"state": "MEASURED", "cut": cut, "blocked_by_quality_floor": held,
            "context": opp["context"]}


def review(db, *, now: datetime | None = None) -> dict:
    """File every milestone review that is due and not yet filed."""
    from sqlalchemy import func, select

    from ..core.models import Listing, OperatingReading, PatternVersion
    from .books import Books

    now = now or datetime.now(timezone.utc)
    launched = first_live_at(db)
    if launched is None:
        return {"state": "UNMEASURED", "why": "no listing has gone live yet (no "
                                               "store.published); the clock has not started",
                "filed": []}
    done = _filed(db)
    filed = []
    for d in due_milestones(launched, now):
        key = f"day{d}"
        if key in done:
            continue
        until = launched + timedelta(days=d)
        books = Books(db)
        pl = books.profit_and_loss(since=launched, until=until)
        with db.session() as s:
            validated = s.scalar(select(func.count()).select_from(PatternVersion).where(
                PatternVersion.certified == True)) or 0  # noqa: E712
            listings = s.scalar(select(func.count()).select_from(Listing)) or 0
        payload = {
            "milestone_day": d, "launched_at": launched.isoformat(),
            "window": {"since": launched.isoformat(), "until": until.isoformat()},
            "unit_economics": books.unit_economics(products_validated=validated,
                                                   listings_drafted=listings, since=launched),
            "profit_and_loss": pl.to_dict(),
            "waste": _waste(db, now),
            "never_cheapen": {"preserved": list(FLOORS),
                              "rule": "a saving is proposable only with evidence that the "
                                      "cheaper route clears every floor the current one "
                                      "clears; cost alone never lowers a floor"},
        }
        with db.session() as s:
            s.add(OperatingReading(kind=REVIEW_KIND, period_key=key, at=now, payload=payload))
        filed.append(key)
    return {"state": "MEASURED", "launched_at": launched.isoformat(), "filed": filed,
            "due": [f"day{d}" for d in due_milestones(launched, now)]}
