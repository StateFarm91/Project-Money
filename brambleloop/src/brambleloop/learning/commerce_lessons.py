"""Real sales into the same lesson store (ENG-LEARN slice 4).

When real Etsy data exists, this joins each listing's measured outcomes to what made it. The
outcomes are views, favourites, orders and refunds. What made it is the image template arm its
accepted frames came from, and the pattern construction family it was engineered in. It then
asks whether one arm or family converts differently from the rest.

**Only real rows count.** `commerce.evidence_provenance.learnable` excludes anything not
marked `real`: a fixture, a rehearsal, a hand-inserted row or an unflagged legacy row. With no
real rows the answer is UNMEASURED, with the n needed, and nothing is published. There are no
fake sales: this module never writes an outcome, only lessons computed from outcomes that
exist.

Lessons go to the existing commerce subjects (`commercial_demand` /
`commercial_underperformance`), so Market Radar and Creativity read them through the same
`consume.matching` path as every other buyer lesson. Those buyer lessons are capped separately
from internal ones (WS5 E5).
"""
from __future__ import annotations

from datetime import datetime, timezone

from . import stats
from .store import DerivedLesson, ensure_tables

MIN_VISITS = 200          # per side
MIN_ORDERS = 5            # in the group, before a conversion lesson is stated
ALPHA = 0.01
UNMEASURED = "UNMEASURED"


def readings(db) -> dict[str, dict]:
    """Per product slug: real visits, favourites, orders and refunds."""
    from sqlalchemy import select

    from ..commerce.evidence_provenance import learnable
    from ..core.models import ListingOutcome, Order

    out: dict[str, dict] = {}
    with db.session() as s:
        for r in s.scalars(select(ListingOutcome)):
            if not learnable(r.detail):
                continue
            d = out.setdefault(r.product_slug, {"visits": 0, "favourites": 0, "orders": 0,
                                                "refunds": 0})
            d["visits"] += int(r.visits or 0)
            d["favourites"] += int(r.favourites or 0)
        for o in s.scalars(select(Order)):
            if not learnable(o.detail):
                continue
            d = out.setdefault(o.product_slug, {"visits": 0, "favourites": 0, "orders": 0,
                                                "refunds": 0})
            d["orders"] += 1
            d["refunds"] += 1 if o.refunded else 0
    return out


def _arm_of_listing(db) -> dict[str, str]:
    """slug -> the image arm (prompt_version) most of its accepted frames came from."""
    from sqlalchemy import select

    from .store import ImageObservation

    counts: dict[str, dict[str, int]] = {}
    with db.session() as s:
        for slug, pv in s.execute(select(ImageObservation.slug, ImageObservation.prompt_version)
                                  .where(ImageObservation.outcome == "accepted")):
            if pv:
                c = counts.setdefault(slug, {})
                c[pv] = c.get(pv, 0) + 1
    return {slug: max(c.items(), key=lambda x: (x[1], x[0]))[0] for slug, c in counts.items()}


def _family_of_listing(db) -> dict[str, str]:
    from . import pattern_lessons

    return {d["slug"]: d["family"] for d in pattern_lessons.designs(db)}


def cycle(db, *, now: datetime | None = None) -> dict:
    from sqlalchemy import select

    ensure_tables(db)
    now = now or datetime.now(timezone.utc)
    reads = readings(db)
    total = {k: sum(r[k] for r in reads.values()) for k in ("visits", "favourites", "orders",
                                                            "refunds")}
    if total["visits"] < 2 * MIN_VISITS:
        return {"status": UNMEASURED, "real_listings": len(reads), **total,
                "why": (f"{total['visits']} real visits; a commerce lesson needs "
                        f"{MIN_VISITS} per side"), "lessons": 0, "work_done": 0}
    found: dict[str, dict] = {}
    for dim, by in (("image_arm", _arm_of_listing(db)), ("pattern_family",
                                                         _family_of_listing(db))):
        groups: dict[str, list[str]] = {}
        for slug in reads:
            if slug in by:
                groups.setdefault(by[slug], []).append(slug)
        for value, slugs in groups.items():
            rest = [s for s in reads if s in by and by[s] != value]
            a = {k: sum(reads[s][k] for s in slugs) for k in total}
            b = {k: sum(reads[s][k] for s in rest) for k in total}
            if a["visits"] < MIN_VISITS or b["visits"] < MIN_VISITS or a["orders"] < MIN_ORDERS:
                continue
            up = stats.two_proportion(b["orders"], b["visits"], a["orders"], a["visits"])
            down = stats.two_proportion(a["orders"], a["visits"], b["orders"], b["visits"])
            for direction, t in ((1, up), (-1, down)):
                if t["p"] >= ALPHA:
                    continue
                word = "converts better" if direction > 0 else "converts worse"
                statement = (f"Real Etsy sales: listings whose {dim.replace('_', ' ')} is "
                             f"{value} {word} than the rest ({a['orders']} orders in "
                             f"{a['visits']} visits vs {b['orders']} in {b['visits']}, "
                             f"p={t['p']:.2g}); listings {', '.join(slugs[:4])}.")
                key = f"commerce:{dim}:{value}:{'+' if direction > 0 else '-'}"
                found[key] = {"scope": f"{dim}:{value}", "direction": direction,
                              "statement": statement,
                              "evidence": {"dim": dim, "value": value, "group": a, "rest": b,
                                           "p": t["p"], "listings": slugs[:20]}}
    made = 0
    with db.session() as s:
        existing = {r.key: r for r in s.scalars(select(DerivedLesson).where(
            DerivedLesson.loop == "commerce"))}
        for key, f in found.items():
            row = existing.get(key)
            if row is None:
                s.add(DerivedLesson(loop="commerce", key=key, at=now, scope=f["scope"],
                                    direction=f["direction"], statement=f["statement"],
                                    evidence=f["evidence"], active=True))
                made += 1
            else:
                row.active, row.statement, row.evidence = True, f["statement"], f["evidence"]
        for key, row in existing.items():
            if key not in found and row.active:
                row.active = False
    published = _publish(db)
    return {"status": "MEASURED", "real_listings": len(reads), **total, "lessons": len(found),
            "new": made, "published": published, "work_done": made}


def _publish(db) -> int:
    from sqlalchemy import select

    from ..improve import bus

    n = 0
    with db.session() as s:
        pending = [(r.id, r.statement, r.key, r.direction) for r in s.scalars(
            select(DerivedLesson).where(DerivedLesson.loop == "commerce",
                                        DerivedLesson.active == True,  # noqa: E712
                                        DerivedLesson.bus_lesson_id.is_(None)))]
    for rid, statement, key, direction in pending:
        subject = "commercial_demand" if direction > 0 else "commercial_underperformance"
        try:
            lid = bus.publish(db, origin_cell="growth", subject=subject, statement=statement,
                              evidence_ref=key[:200], confidence="measured")
        except bus.LessonRefused:
            continue
        with db.session() as s:
            s.get(DerivedLesson, rid).bus_lesson_id = lid
        n += 1
    return n
