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
                                     "pricing_response",
                                     # OPUS2-P0: measured own-listing demand (improve.
                                     # commercial_lessons) raises the concepts it names.
                                     "commercial_demand"})
DISFAVOURS: frozenset[str] = frozenset({"creative_rejection", "defect",
                                        # OPUS2-P0: measured own-listing underperformance.
                                        "commercial_underperformance"})


def words(text: str) -> set[str]:
    return {w for w in _WORD.findall((text or "").lower()) if w not in _STOP}


def policy(db, cell: str, call_site_min_shared: int) -> dict:
    """The match threshold this cell uses now (v1.1 lane B, directive §4).

    For a cell with a measured policy loop (`policy_loops.LOOP_FOR_CELL`) the registry
    incumbent decides once one is recorded -- the call-site value is the code default the
    loop's first version was registered from. A cell with no loop keeps its call-site value.
    """
    from . import policy_loops

    key = policy_loops.LOOP_FOR_CELL.get(cell)
    if key is None:
        return {"loop": None, "value": call_site_min_shared, "config_id": None,
                "source": "call_site"}
    current = policy_loops.active(db, key)
    if current["source"] != "registry":
        return {**current, "value": call_site_min_shared, "source": "call_site"}
    return current


def matching(db, cell: str, text: str, *, min_shared: int = 2,
             subjects: frozenset[str] | None = None,
             subject: str | None = None) -> list[dict]:
    """Lessons routed to (or published by) this cell that apply to `text`.

    `subject` names what the decision is about (a product slug, `support_case:<id>`). When
    given, and the cell has a policy loop, the decision is logged with the feature it was
    taken on, so its outcome can later be attributed and the threshold evaluated (§4).
    """
    current = policy(db, cell, min_shared)
    threshold = int(current["value"])
    want = words(text)
    out = []
    best = 0
    candidates = 0
    for lesson in bus.inbox(db, cell, unacted_only=False, include_own=False):
        if subjects is not None and lesson["subject"] not in subjects:
            continue
        shared = sorted(words(lesson["statement"]) & want)
        candidates += 1
        best = max(best, len(shared))
        if len(shared) >= threshold:
            out.append({**lesson, "shared": shared,
                        "direction": (1 if lesson["subject"] in FAVOURS else
                                      -1 if lesson["subject"] in DISFAVOURS else 0)})
    if subject and current.get("loop"):
        from . import policy_loops

        policy_loops.record_decision(
            db, current["loop"], subject,
            features={"max_shared": best, "candidates": candidates},
            action={"applied": bool(out), "lessons": [int(x["id"]) for x in out]},
            config_id=current.get("config_id"), params={"min_shared": threshold})
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


# WS5 E5: two kinds of lesson, each with its own cap. A buyer lesson rests on what buyers did
# (real-provenance outcome rows, `commerce.evidence_provenance`); an internal lesson rests on
# the company's own judgement (the jury, defects, research). One shared cap let a run of
# internal opinions use up the room a buyer signal needs, and the reverse.
BUYER_SUBJECTS: frozenset[str] = frozenset({"commercial_demand",
                                            "commercial_underperformance"})
INTERNAL_CAP = 0.06
BUYER_CAP = 0.06
STEP = 0.02
# A lesson's weight halves every HALF_LIFE_DAYS: what buyers did last season counts, less
# than what they did this month, and an old opinion fades unless it is re-learned.
HALF_LIFE_DAYS = 60.0


def kind_of(lesson: dict) -> str:
    return "buyer" if lesson.get("subject") in BUYER_SUBJECTS else "internal"


def decay(lesson: dict, now=None) -> float:
    """1.0 for a lesson learned now, halving every HALF_LIFE_DAYS; 1.0 if its age is unknown."""
    from datetime import datetime, timezone

    at = lesson.get("at")
    if not at:
        return 1.0
    try:
        when = datetime.fromisoformat(str(at))
    except ValueError:
        return 1.0
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    now = now or datetime.now(timezone.utc)
    days = max(0.0, (now - when).total_seconds() / 86400.0)
    return 0.5 ** (days / HALF_LIFE_DAYS)


def adjustment_parts(lessons: list[dict], *, step: float = STEP, now=None) -> dict:
    """The nudge split by kind, each decayed and capped on its own."""
    sums = {"internal": 0.0, "buyer": 0.0}
    for lesson in lessons:
        sums[kind_of(lesson)] += step * lesson["direction"] * decay(lesson, now)
    internal = max(-INTERNAL_CAP, min(INTERNAL_CAP, sums["internal"]))
    buyer = max(-BUYER_CAP, min(BUYER_CAP, sums["buyer"]))
    return {"internal": round(internal, 4), "buyer": round(buyer, 4),
            "total": round(internal + buyer, 4)}


def score_adjustment(lessons: list[dict], *, step: float = STEP, cap: float | None = None,
                     now=None) -> float:
    """A bounded nudge from the lessons that apply: favoured up, disfavoured down.

    WS5 E5: internal and buyer lessons are capped separately (each +-0.06), and every
    lesson's weight decays with age. `cap`, when given, bounds the combined nudge too."""
    total = adjustment_parts(lessons, step=step, now=now)["total"]
    if cap is not None:
        total = max(-cap, min(cap, total))
    return round(total, 4)


def concept_text(seed, concept: dict | None = None) -> str:
    """The words a radar concept is matched on (the same text `radar.score` uses)."""
    c = concept or {}
    return " ".join(str(x) for x in (
        seed.slug.replace("-", " "), seed.title, seed.category, seed.season or "",
        seed.rationale, c.get("premise") or "", c.get("motif") or ""))


def rank_adjustments(db, seeds, *, now=None) -> dict[str, float]:
    """WS5 E5: the bounded lesson nudge for each concept, read-only (nothing is recorded as
    acted on: `radar.score` records that when it decides). Used to rank the next concepts."""
    out = {}
    for seed in seeds:
        lessons = [l for l in matching(db, "market_radar", concept_text(seed))
                   if l["direction"]]
        out[seed.slug] = score_adjustment(lessons, now=now) if lessons else 0.0
    return out
