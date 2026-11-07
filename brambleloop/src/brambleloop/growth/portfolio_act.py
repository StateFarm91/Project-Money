"""P0-PORTFOLIO-ACT: a portfolio review's classifications become bounded, keyed work.

`portfolio.review` classifies every SKU (section 12), but its verdicts used to be text in
`PortfolioReview.actions` that nothing read. This turns each actionable final label into one
piece of work:

| label           | work                                                                  |
|-----------------|-----------------------------------------------------------------------|
| QUALITY_PROBLEM | re-verification of that one release: `cir.twin`, `cir.reverse`,        |
|                 | `gate.asset_truth`, `gate.policy` (`quality-fix:<check>:<slug>:<wk>`).  |
|                 | Read-only checks: a failure can only withhold or open an incident     |
| SEO_PROBLEM     | an owner card (`portfolio.seo:<slug>`). Never an automatic rebuild     |
| REWORK          | an owner card (`portfolio.rework:<slug>`). The A5 correction loop is   |
|                 | not on this base                                                      |
| RETIRE          | an owner card (`portfolio.retire:<slug>`). Never automatic             |

**Why SEO is a card, not a `listing.seo` (review PORTFOLIO f3bea437 F1/F2/F3).**
SEO_PROBLEM needs at least 300 impressions, so the listing is already live on Etsy. A
`listing.seo` re-run:
- resets that live listing to a local `draft`;
- restores the last run's price and frames over the current ones;
- carries its rebuild token through `launch.plan` to `store.publish`. That is the path
  independent review FMBATCH1 F-1 made opt-in for taxonomy drift.

It would not even reach the buyer, because `store.publish` refuses a listing that already has
an Etsy id. So the rebuild is put to the owner, the way taxonomy drift does it.

**Owner cards** are keyed per SKU, not per week, which gives three rules:
- An open card is restated in place, never duplicated.
- A card the owner has decided is not asked again for `DECIDED_QUIET_DAYS`. After that, a
  verdict that still stands is asked once more.
- Every card states its exact step, CA$0, ten minutes and the consequence of waiting.

**Bounds.**
- **At most `WEEKLY_CAP` new pieces of work per label per ISO week.** A restated card costs
  nothing. The overflow is reported as `capped`, never dropped silently.
- **Fair rotation.** Within a label, SKUs never acted on come first, then the ones acted on
  longest ago. A SKU capped this week is first in line next week.
- **Only a certified current release is re-verified.** A SKU without one is `skipped` by name.

A label the offer guard withheld (#13; it becomes OFFER_UNTESTED) is never acted on, because
only the final label counts.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

SEO, QUALITY, REWORK_CARD, RETIRE_CARD = "seo", "quality", "rework", "retire"
CARD_KINDS = (SEO, REWORK_CARD, RETIRE_CARD)
WEEKLY_CAP = 5
DECIDED_QUIET_DAYS = 90
ACTION = "portfolio.acted"
QUALITY_CHECKS = (("validator", "cir.twin"), ("validator", "cir.reverse"),
                  ("asset_truth", "gate.asset_truth"), ("policy", "gate.policy"))


def week_of(day: date) -> str:
    y, w, _ = day.isocalendar()
    return f"{y}-W{w:02d}"


def _week_start(day: date) -> datetime:
    monday = day - timedelta(days=day.isoweekday() - 1)
    return datetime(monday.year, monday.month, monday.day, tzinfo=timezone.utc)


def _aware(dt):
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _kind(label: str) -> str | None:
    from .portfolio import QUALITY_PROBLEM, RETIRE, REWORK, SEO_PROBLEM

    return {SEO_PROBLEM: SEO, QUALITY_PROBLEM: QUALITY, REWORK: REWORK_CARD,
            RETIRE: RETIRE_CARD}.get(label)


def card_key(kind: str, slug: str) -> str:
    return f"portfolio.{kind}:{slug}"


def _quality_key(check: str, slug: str, week: str) -> str:
    return f"quality-fix:{check}:{slug}:{week}"


def _history(session, kind: str, slugs: list[str], week: str, today: date) -> dict:
    """Per slug: when it was last acted on for `kind`, whether this week, and card state."""
    from sqlalchemy import select

    from ..core.models import Job, OwnerAction

    out: dict[str, dict] = {s: {"last": None, "this_week": False, "open": None,
                                "decided_at": None} for s in slugs}
    start = _week_start(today)
    if kind == QUALITY:
        for key, at in session.execute(select(Job.idempotency_key, Job.created_at).where(
                Job.idempotency_key.like("quality-fix:cir.twin:%"))):
            slug = (key or "").split(":")[2] if key and key.count(":") >= 3 else None
            if slug in out:
                h = out[slug]
                at = _aware(at)
                h["last"] = max(filter(None, (h["last"], at)), default=None)
                h["this_week"] = h["this_week"] or key.endswith(f":{week}")
        return out
    for slug in slugs:
        rows = list(session.scalars(select(OwnerAction).where(
            OwnerAction.requirement_key == card_key(kind, slug)).order_by(OwnerAction.id)))
        h = out[slug]
        for r in rows:
            at = _aware(r.at)
            h["last"] = max(filter(None, (h["last"], at)), default=None)
            if at and at >= start:
                h["this_week"] = True
            if not r.done:
                h["open"] = r.id
            else:
                h["decided_at"] = max(filter(None, (h["decided_at"],
                                                    _aware(r.state_at) or at)), default=None)
    return out


def _card(kind: str, c, rel: dict | None, today: date) -> dict:
    version = f"{c.slug}@{rel['version']}" if rel else c.slug
    if kind == SEO:
        action = (f"Decide whether to rebuild the listing copy of {version}: it is shown and "
                  f"not chosen ({c.reason}). To apply it, re-run the listing copy from the "
                  f"Command Center on the current price and frames, then update the live "
                  f"Etsy listing in Shop Manager. Close this card as withdrawn to keep the "
                  f"copy as it is")
        blocks = f"the SEO rebuild of {c.slug}"
    elif kind == RETIRE_CARD:
        action = (f"Decide whether to retire {version}: {c.reason}. To retire it, "
                  f"deactivate its Etsy listing in Shop Manager and mark the product retired "
                  f"in the Command Center. Close this card as withdrawn to keep selling it")
        blocks = f"retirement of {c.slug}"
    else:
        action = (f"Decide whether to rework {version}: {c.reason}. The A5 correction loop "
                  f"is not on this base, so a rework is a new design version you request "
                  f"from the Command Center. Close this card as withdrawn to keep it")
        blocks = f"rework of {c.slug}"
    return {"action": action,
            "reason": (f"portfolio review {today.isoformat()} classified it {c.label}; a "
                       f"verdict that changes or removes a live listing is never carried "
                       f"out automatically (section 12; review PORTFOLIO F1/F2)"),
            "max_cost_cad": 0.0, "minutes": 10,
            "consequence_of_delay": (f"{c.slug} stays as it is; the verdict is re-examined "
                                     f"at the next review"),
            "blocks": blocks}


def act(ctx, classifications, *, today: date, review_id: int | None) -> dict:
    """Turn the review's final labels into bounded work. Returns what was done and why not."""
    from ..ops import owner_queue
    from ..runtime.quality_ops import certified_releases

    week = week_of(today)
    now = datetime(today.year, today.month, today.day, tzinfo=timezone.utc)
    current = {r["slug"]: r for r in certified_releases(ctx.db)}
    done, restated, skipped, capped = [], [], [], []
    by_kind: dict[str, list] = {}
    for c in classifications:
        kind = _kind(c.label)
        if kind:
            by_kind.setdefault(kind, []).append(c)
    for kind, items in by_kind.items():
        with ctx.db.session() as s:
            hist = _history(s, kind, [c.slug for c in items], week, today)
        if kind == QUALITY:
            new_this_week = _quality_this_week(ctx.db, week)
        else:
            with ctx.db.session() as s:
                new_this_week = _cards_opened_since(s, kind, _week_start(today))
        budget = WEEKLY_CAP - new_this_week
        epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
        for c in sorted(items, key=lambda c: (hist[c.slug]["last"] or epoch, c.slug)):
            h, rel = hist[c.slug], current.get(c.slug)
            if kind == QUALITY:
                if h["this_week"]:
                    skipped.append({"slug": c.slug, "kind": kind,
                                    "why": f"already re-verified in {week}"})
                    continue
                if rel is None:
                    skipped.append({"slug": c.slug, "kind": kind,
                                    "why": "no certified current release to re-verify"})
                    continue
                if budget <= 0:
                    capped.append({"slug": c.slug, "kind": kind,
                                   "why": f"weekly cap of {WEEKLY_CAP} {kind} actions reached"})
                    continue
                # Literal job types, so the autonomy map sees each wake edge (AST, literals
                # only) -- the same four checks `gate.quality` queues, for this one release.
                jobs = [getattr(j, "id", None) for j in (
                    ctx.enqueue("validator", "cir.twin", dict(rel),
                                idempotency_key=_quality_key("cir.twin", c.slug, week)),
                    ctx.enqueue("validator", "cir.reverse", dict(rel),
                                idempotency_key=_quality_key("cir.reverse", c.slug, week)),
                    ctx.enqueue("asset_truth", "gate.asset_truth", dict(rel),
                                idempotency_key=_quality_key("gate.asset_truth", c.slug,
                                                             week)),
                    ctx.enqueue("policy", "gate.policy", dict(rel),
                                idempotency_key=_quality_key("gate.policy", c.slug, week)))]
                budget -= 1
                done.append({"slug": c.slug, "kind": kind, "label": c.label, "jobs": jobs})
                continue
            key = card_key(kind, c.slug)
            fields = _card(kind, c, rel, today)
            if h["open"] is not None:
                with ctx.db.session() as s:
                    owner_queue.ensure(s, key, **fields)
                restated.append({"slug": c.slug, "kind": kind, "owner_action": h["open"]})
                continue
            if h["decided_at"] and now - h["decided_at"] < timedelta(days=DECIDED_QUIET_DAYS):
                skipped.append({"slug": c.slug, "kind": kind, "why": (
                    f"the owner decided this on {h['decided_at'].date().isoformat()}; asked "
                    f"again after {DECIDED_QUIET_DAYS} days if the verdict still stands")})
                continue
            if budget <= 0:
                capped.append({"slug": c.slug, "kind": kind,
                               "why": f"weekly cap of {WEEKLY_CAP} {kind} cards reached"})
                continue
            with ctx.db.session() as s:
                row = owner_queue.ensure(s, key, **fields)
                row_id = row.id
            budget -= 1
            done.append({"slug": c.slug, "kind": kind, "label": c.label,
                         "jobs": [f"owner_action:{row_id}"]})
    report = {"week": week, "review_id": review_id, "acted": done, "restated": restated,
              "skipped": skipped, "capped": capped, "cap": WEEKLY_CAP}
    ctx.audit(ACTION, detail=report)
    return report


def _cards_opened_since(session, kind: str, since: datetime) -> int:
    from sqlalchemy import select

    from ..core.models import OwnerAction

    n = 0
    for at in session.scalars(select(OwnerAction.at).where(
            OwnerAction.requirement_key.like(f"portfolio.{kind}:%"))):
        at = _aware(at)
        if at and at >= since:
            n += 1
    return n


def _quality_this_week(db, week: str) -> int:
    from sqlalchemy import func, select

    from ..core.models import Job

    with db.session() as s:
        return int(s.scalar(select(func.count()).select_from(Job).where(
            Job.idempotency_key.like(f"quality-fix:cir.twin:%:{week}"))) or 0)
