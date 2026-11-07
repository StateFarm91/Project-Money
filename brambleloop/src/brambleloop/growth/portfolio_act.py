"""P0-PORTFOLIO-ACT: a portfolio review's classifications become bounded, keyed work.

`portfolio.review` classifies every SKU (section 12), but until now its verdicts were text in
`PortfolioReview.actions` that nothing read. This turns each actionable label into one piece
of work:

| label           | work                                                                 |
|-----------------|----------------------------------------------------------------------|
| SEO_PROBLEM     | `listing.seo` rebuild of the current release (`seo-fix:<slug>:<wk>`)  |
| QUALITY_PROBLEM | re-verification of that one release: `cir.twin`, `cir.reverse`,       |
|                 | `gate.asset_truth`, `gate.policy` (`quality-fix:<check>:<slug>:<wk>`) |
| REWORK          | an owner card (`portfolio.rework:<slug>`). The A5 correction loop is  |
|                 | not on this base, so nothing reworks a design automatically          |
| RETIRE          | an owner card (`portfolio.retire:<slug>`). Never automatic           |

Bounds:
* **Once per ISO week per SKU.** `<wk>` is the review date's ISO week (`2026-W45`), so a
  rerun in the same week enqueues nothing, and a later week can try again.
* **At most `WEEKLY_CAP` new pieces of work per label per week.** SKUs over the cap are
  reported as `capped`, never dropped silently.
* **Only a certified current release is acted on.** A SKU with no certified release is
  `skipped` with its reason. A listing rebuild that has no earlier `listing.seo` inputs to
  rebuild from is skipped too, never invented.

A label the offer guard withheld (#13; it becomes OFFER_UNTESTED) is never acted on as a
discard: only the final label counts.
"""
from __future__ import annotations

from datetime import date

SEO, QUALITY, REWORK_CARD, RETIRE_CARD = "seo", "quality", "rework", "retire"
WEEKLY_CAP = 5
ACTION = "portfolio.acted"
QUALITY_CHECKS = (("validator", "cir.twin"), ("validator", "cir.reverse"),
                  ("asset_truth", "gate.asset_truth"), ("policy", "gate.policy"))


def week_of(day: date) -> str:
    y, w, _ = day.isocalendar()
    return f"{y}-W{w:02d}"


def _kind(label: str) -> str | None:
    from .portfolio import QUALITY_PROBLEM, RETIRE, REWORK, SEO_PROBLEM

    return {SEO_PROBLEM: SEO, QUALITY_PROBLEM: QUALITY, REWORK: REWORK_CARD,
            RETIRE: RETIRE_CARD}.get(label)


def _used_this_week(session, kind: str, week: str) -> set[str]:
    """Slugs already acted on for `kind` this week (from the keys themselves)."""
    from sqlalchemy import select

    from ..core.models import Job, OwnerAction

    if kind in (SEO, QUALITY):
        prefix = "seo-fix:" if kind == SEO else "quality-fix:cir.twin:"
        keys = session.scalars(select(Job.idempotency_key).where(
            Job.idempotency_key.like(f"{prefix}%:{week}")))
        return {k[len(prefix):-(len(week) + 1)] for k in keys if k}
    prefix = f"portfolio.{kind}:"
    keys = session.scalars(select(OwnerAction.requirement_key).where(
        OwnerAction.requirement_key.like(f"{prefix}%:{week}")))
    return {k[len(prefix):-(len(week) + 1)] for k in keys if k}


def act(ctx, classifications, *, today: date, review_id: int | None) -> dict:
    """Turn the review's final labels into bounded work. Returns what was done and why not."""
    from ..integrations.taxonomy_drift import _last_seo_inputs
    from ..ops import owner_queue
    from ..runtime.quality_ops import certified_releases

    week = week_of(today)
    current = {r["slug"]: r for r in certified_releases(ctx.db)}
    done: list[dict] = []
    skipped: list[dict] = []
    capped: list[dict] = []
    by_kind: dict[str, list] = {}
    for c in classifications:
        kind = _kind(c.label)
        if kind:
            by_kind.setdefault(kind, []).append(c)
    for kind, items in by_kind.items():
        with ctx.db.session() as s:
            used = _used_this_week(s, kind, week)
        budget = WEEKLY_CAP - len(used)
        for c in sorted(items, key=lambda c: c.slug):
            if c.slug in used:
                skipped.append({"slug": c.slug, "kind": kind, "why": "already acted on in "
                                f"{week}"})
                continue
            rel = current.get(c.slug)
            if rel is None and kind in (SEO, QUALITY):
                skipped.append({"slug": c.slug, "kind": kind,
                                "why": "no certified current release to act on"})
                continue
            if budget <= 0:
                capped.append({"slug": c.slug, "kind": kind,
                               "why": f"weekly cap of {WEEKLY_CAP} {kind} actions reached"})
                continue
            if kind == SEO:
                with ctx.db.session() as s:
                    inputs = _last_seo_inputs(s, rel["slug"], rel["version"])
                if inputs is None:
                    skipped.append({"slug": c.slug, "kind": kind, "why": (
                        f"no earlier listing.seo for {rel['slug']}@{rel['version']} to "
                        f"rebuild from")})
                    continue
                job = ctx.enqueue("listing", "listing.seo",
                                  {**inputs, "rebuild": f"portfolio:{week}",
                                   "portfolio_review": review_id},
                                  idempotency_key=f"seo-fix:{c.slug}:{week}")
                jobs = [getattr(job, "id", None)]
            elif kind == QUALITY:
                # Literal job types, so the autonomy map sees each wake edge (AST, literals
                # only) -- the same four checks `gate.quality` queues, for this one release.
                k = f"{c.slug}:{week}"
                jobs = [getattr(j, "id", None) for j in (
                    ctx.enqueue("validator", "cir.twin", dict(rel),
                                idempotency_key=f"quality-fix:cir.twin:{k}"),
                    ctx.enqueue("validator", "cir.reverse", dict(rel),
                                idempotency_key=f"quality-fix:cir.reverse:{k}"),
                    ctx.enqueue("asset_truth", "gate.asset_truth", dict(rel),
                                idempotency_key=f"quality-fix:gate.asset_truth:{k}"),
                    ctx.enqueue("policy", "gate.policy", dict(rel),
                                idempotency_key=f"quality-fix:gate.policy:{k}"))]
            else:
                key = f"portfolio.{kind}:{c.slug}:{week}"
                verb = "retire" if kind == RETIRE_CARD else "rework"
                with ctx.db.session() as s:
                    row = owner_queue.ensure(
                        s, key,
                        action=(f"Decide whether to {verb} {c.slug}. Portfolio review "
                                f"{today.isoformat()} classified it {c.label}: {c.reason}"),
                        reason=("a portfolio verdict to discard or rework a design is never "
                                "carried out automatically (section 12)" +
                                ("; the A5 correction loop is not on this base, so a rework "
                                 "has no automatic entry yet" if kind == REWORK_CARD else "")),
                        max_cost_cad=0.0, minutes=10,
                        consequence_of_delay=(f"{c.slug} stays listed as it is; the verdict "
                                              f"is re-examined at the next review"),
                        blocks=f"{verb} of {c.slug}")
                    jobs = [f"owner_action:{row.id}"]
            budget -= 1
            done.append({"slug": c.slug, "kind": kind, "label": c.label, "jobs": jobs})
    report = {"week": week, "review_id": review_id, "acted": done, "skipped": skipped,
              "capped": capped, "cap": WEEKLY_CAP}
    ctx.audit(ACTION, detail=report)
    return report
