"""The cross-department lesson bus.

Requirements 97 and 101. A lesson discovered in one department has to reach the others it
affects, and the spec's own example is the shape of it: customers prefer low-sew construction,
so Market Radar scores low-sew opportunities higher, Creativity explores low-sew concepts, and
Pattern Engineering prefers low-sew constructions.

Two failures this is built against.

**A lesson nobody routed is a lesson nobody has.** Writing it down in the department that found
it feels like learning and changes nothing anywhere else. So a lesson declares its subject, and
the subject decides who hears it — routing is derived, not remembered.

**A company that starts from generic intelligence every time is not compounding (#101).** The
test of accumulated knowledge is not that lessons exist; it is that a later decision can be
shown to have used one. So `acted_on` is recorded against the lesson, and a lesson nobody has
acted on after being routed is visible as exactly that.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .cells import BY_KEY, CELLS

# Which cells care about which subject. Derived routing rather than a distribution list,
# because a list is maintained by whoever remembers to.
SUBJECT_ROUTING: dict[str, tuple[str, ...]] = {
    "construction_preference": ("product_creativity", "pattern_engineering", "market_radar"),
    "sizing": ("pattern_engineering", "quality", "customer_experience"),
    "instruction_clarity": ("pattern_engineering", "quality", "customer_experience"),
    "chart_quality": ("creative_assets", "quality", "customer_experience"),
    "thumbnail": ("creative_assets", "seo_search", "product_creativity"),
    "palette": ("product_creativity", "creative_assets"),
    "seasonal_timing": ("market_radar", "growth", "portfolio", "product_creativity"),
    "pricing_response": ("pricing", "portfolio", "finance"),
    "search_language": ("seo_search", "product_creativity", "growth"),
    "delivery_experience": ("customer_experience", "creative_assets", "quality"),
    "defect": ("quality", "pattern_engineering", "runtime"),
    "cost": ("finance", "runtime", "growth"),
}

CONFIDENCE = ("observed", "measured", "confirmed")


class LessonRefused(ValueError):
    """A lesson that cannot be routed, or that is not a lesson."""


def route_for(subject: str) -> tuple[str, ...]:
    if subject not in SUBJECT_ROUTING:
        raise LessonRefused(
            f"{subject!r} has no routing. A lesson whose audience is undefined stays in the "
            f"department that found it, which feels like learning and changes nothing")
    return SUBJECT_ROUTING[subject]


def publish(db, *, origin_cell: str, subject: str, statement: str,
            evidence_ref: str = "", confidence: str = "observed") -> int:
    """Record a lesson and route it to every cell the subject concerns."""
    from ..core.models import Lesson

    if origin_cell not in BY_KEY:
        raise LessonRefused(f"unknown cell {origin_cell!r}")
    if confidence not in CONFIDENCE:
        raise LessonRefused(f"confidence must be one of {CONFIDENCE}")
    if len(statement.split()) < 6:
        raise LessonRefused(
            "a lesson states what was learned and what follows from it; this is a label")

    audience = [c for c in route_for(subject) if c != origin_cell]
    with db.session() as s:
        row = Lesson(origin_cell=origin_cell, subject=subject, statement=statement,
                     evidence_ref=evidence_ref, confidence=confidence,
                     routed_to=audience, acted_on_by=[])
        s.add(row)
        s.flush()
        return row.id


def acted_on(db, lesson_id: int, cell: str, *, how: str = "") -> list[str]:
    """Record that a cell actually changed something because of a lesson (#101)."""
    from ..core.models import Lesson

    if cell not in BY_KEY:
        raise LessonRefused(f"unknown cell {cell!r}")
    with db.session() as s:
        row = s.get(Lesson, lesson_id)
        if row is None:
            raise LessonRefused(f"no lesson {lesson_id}")
        if cell not in (row.routed_to or []) and cell != row.origin_cell:
            raise LessonRefused(
                f"{cell!r} was not routed lesson {lesson_id}; acting on a lesson nobody sent "
                f"it is how an audit trail stops meaning anything")
        entries = list(row.acted_on_by or [])
        if not any(e.get("cell") == cell for e in entries):
            entries.append({"cell": cell, "how": how,
                            "at": datetime.now(timezone.utc).isoformat()})
            row.acted_on_by = entries
        return [e["cell"] for e in entries]


def inbox(db, cell: str, *, unacted_only: bool = True) -> list[dict]:
    """What this cell has been told and has not yet done anything about."""
    from sqlalchemy import select

    from ..core.models import Lesson

    with db.session() as s:
        rows = list(s.scalars(select(Lesson).where(Lesson.superseded_by.is_(None))))
    out = []
    for row in rows:
        if cell not in (row.routed_to or []):
            continue
        acted = [e.get("cell") for e in (row.acted_on_by or [])]
        if unacted_only and cell in acted:
            continue
        out.append({"id": row.id, "subject": row.subject, "statement": row.statement,
                    "from": row.origin_cell, "confidence": row.confidence,
                    "evidence_ref": row.evidence_ref})
    return out


def compounding(db, *, stale_after_days: int = 30) -> dict:
    """Whether knowledge is actually accumulating, or merely being filed (#101).

    The measure is not how many lessons exist. It is how many reached somebody who then did
    something, and how many have been sitting routed and untouched long enough that nobody is
    going to.
    """
    from sqlalchemy import select

    from ..core.models import Lesson

    with db.session() as s:
        rows = list(s.scalars(select(Lesson)))

    def _aware(value):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

    cutoff = datetime.now(timezone.utc) - timedelta(days=stale_after_days)
    routed = [r for r in rows if r.routed_to]
    acted = [r for r in routed if r.acted_on_by]
    stale = [r for r in routed if not r.acted_on_by and _aware(r.at) < cutoff]

    by_subject: dict[str, int] = {}
    for row in rows:
        by_subject[row.subject] = by_subject.get(row.subject, 0) + 1

    return {
        "lessons": len(rows),
        "routed": len(routed),
        "acted_on": len(acted),
        "action_rate": round(len(acted) / len(routed), 3) if routed else 0.0,
        "stale_unacted": [{"id": r.id, "subject": r.subject, "from": r.origin_cell}
                          for r in stale],
        "by_subject": dict(sorted(by_subject.items(), key=lambda kv: -kv[1])),
        "cells": len(CELLS),
        "note": ("Lessons exist but nothing has acted on one, so this is filing rather than "
                 "compounding (#101)."
                 if routed and not acted else
                 "No lesson has been recorded yet." if not rows else
                 f"{len(acted)} of {len(routed)} routed lessons changed something in the "
                 f"cell that received them."),
    }
