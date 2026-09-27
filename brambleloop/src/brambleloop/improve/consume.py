"""Reading a department's lesson inbox where its decisions are made (#97, #101, #147).

`improve.bus` routed every lesson to the cells its subject concerns, and `bus.acted_on` -- the
record that a receiving department changed something because of one -- had no runtime caller:
only the creativity brief ever read an inbox. So Market Radar, Pattern Engineering, Listings
and Support were told things and never listened, and `compounding()` read zero forever.

This is the listening half, deliberately small. A consumer hands over the text its decision is
about (a concept, a listing's candidate queries, a customer's question); the lessons in its
inbox whose statements share content words with that text are the ones that apply; the
consumer changes its decision with them and records exactly that through `bus.acted_on`, with
the words it acted on. A lesson that applies to nothing the department is deciding stays
unacted, which is the honest reading.
"""
from __future__ import annotations

import re

from . import bus

_WORD = re.compile(r"[a-z][a-z\-]{2,}")
# Words that appear in lessons about everything and so tie a lesson to nothing.
_STOP: frozenset[str] = frozenset({
    "the", "and", "for", "with", "that", "this", "from", "have", "has", "was", "were", "are",
    "not", "but", "its", "our", "their", "they", "them", "than", "then", "into", "onto",
    "which", "when", "what", "who", "whom", "will", "would", "should", "could", "been",
    "being", "more", "most", "less", "each", "every", "any", "all", "one", "two", "three",
    "pattern", "patterns", "product", "products", "crochet", "brambleloop", "customer",
    "customers", "listing", "listings", "lesson", "lessons", "department", "requirement",
    "teardown", "benchmark", "binds", "prevent", "exceed", "clarify", "higher", "lower",
    "score", "scores", "scored", "because", "about", "there", "here", "also", "only",
    "must", "make", "made", "does", "doing", "done", "rather", "other", "same", "again",
})

# Subjects whose lessons raise what they match, and subjects whose lessons lower it: a
# construction customers prefer is a reason to pursue, a creative death is a reason not to.
FAVOURS: frozenset[str] = frozenset({"construction_preference", "cultural_territory",
                                     "cultural_timing", "seasonal_timing", "search_language",
                                     "pricing_response"})
DISFAVOURS: frozenset[str] = frozenset({"creative_rejection", "defect"})


def words(text: str) -> set[str]:
    return {w for w in _WORD.findall((text or "").lower()) if w not in _STOP}


def matching(db, cell: str, text: str, *, min_shared: int = 2,
             subjects: frozenset[str] | None = None) -> list[dict]:
    """Lessons routed to (or published by) this cell that apply to `text`."""
    want = words(text)
    out = []
    for lesson in bus.inbox(db, cell, unacted_only=False, include_own=False):
        if subjects is not None and lesson["subject"] not in subjects:
            continue
        shared = sorted(words(lesson["statement"]) & want)
        if len(shared) >= min_shared:
            out.append({**lesson, "shared": shared,
                        "direction": (1 if lesson["subject"] in FAVOURS else
                                      -1 if lesson["subject"] in DISFAVOURS else 0)})
    return out


def act(db, cell: str, lessons: list[dict], *, how: str) -> list[int]:
    """Record that this cell changed a decision because of these lessons."""
    acted = []
    for lesson in lessons:
        try:
            bus.acted_on(db, int(lesson["id"]), cell,
                         how=f"{how} (shared: {', '.join(lesson.get('shared', [])[:6])})"[:300])
            acted.append(int(lesson["id"]))
        except bus.LessonRefused:
            continue
    return acted


def score_adjustment(lessons: list[dict], *, step: float = 0.02, cap: float = 0.06) -> float:
    """A bounded nudge from the lessons that apply: favoured up, disfavoured down."""
    total = sum(step * lesson["direction"] for lesson in lessons)
    return round(max(-cap, min(cap, total)), 4)
