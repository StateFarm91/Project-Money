"""The bar, which has to move, and the rejection that has to be allowed.

Requirements 124, 125, 127, 129. A creative standard fixed in code is a standard the company
grows past and keeps meeting. Six months of learning produces better concepts, the threshold
that once rejected two thirds of them now rejects none, and nothing has gone wrong that
anybody can point at — the pass rate improved.

**The floor is the company's own trailing work (#124).** Not a constant. The minimum is the
median of the last cohort, so a concept that would have passed six months ago can fail today
because the company has learned enough to demand better. That is what "continuous improvement
raises the release bar" has to mean mechanically, and it is the only version that cannot be
satisfied by leaving a number alone.

**Flagships aim at the top decile, not the mean (#125).** Competitive parity is the floor and
the composite standard already encodes it. The aspiration is a different number: the ninetieth
percentile of the category, and an experiment is allowed to be scored against exceeding it
rather than against clearing the floor. Aiming at the mean of a category produces the mean of
a category, which is the definition of forgettable.

**Boring is a valid rejection (#129).** The single most important sentence in this section:
agents must be able to reject technically valid ideas. Every gate in this system is a
correctness gate, and a concept can pass all of them and be the ninth version of a thing
nobody remembers. So `boring` is a first-class verdict with no correctness content, and a
correctness score can never override it.

**A rejection nobody recorded teaches nothing (#127).** Autopsies are kept with the reason
and the cohort, because the useful output of a tournament that rejected forty concepts is the
pattern in the forty, and it is available only if somebody wrote them down.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import date

# How many recent concepts define the floor. Small enough to move, large enough that one
# unusual week does not set the bar for the quarter.
COHORT_SIZE = 20

# The floor never falls below this, however weak a cohort was. A trailing median alone would
# let a bad quarter permanently lower the company's standard, which is the same failure as a
# fixed threshold arriving from the other direction.
ABSOLUTE_FLOOR = 0.45

# Where a flagship aims (#125).
TOP_DECILE = 0.90

# Rejections that carry no correctness content. #129's requirement made into a vocabulary,
# because "reject it if it is boring" is not actionable and "score below 0.6" is not the
# same judgement.
TASTE_REJECTIONS: dict[str, str] = {
    "boring": "technically fine and there is no reason to look at it twice",
    "obvious": "the first thing anybody would think of for this brief",
    "forgettable": "indistinguishable from the rest of the grid an hour later",
    "derivative_feeling": "not a copy, and it feels like one",
    "explains_itself": "the idea only works once somebody has described it",
}


class StandardRefused(ValueError):
    """A floor that fell, or a rejection with no reason."""


@dataclass(frozen=True)
class Scored:
    key: str
    score: float
    cohort: str = ""
    make_lane: str = ""

    def to_dict(self) -> dict:
        return {"key": self.key, "score": self.score, "cohort": self.cohort,
                "make_lane": self.make_lane}


def floor(history: list[Scored], *, cohort_size: int = COHORT_SIZE) -> dict:
    """The current minimum, from the company's own trailing work (#124).

    With too little history the floor is the absolute one and says so: deriving a moving bar
    from four concepts produces a bar that moves with whichever four they were.
    """
    recent = history[-cohort_size:]
    if len(recent) < 5:
        return {
            "floor": ABSOLUTE_FLOOR,
            "derived_from": "absolute",
            "cohort": len(recent),
            "reason": (f"{len(recent)} scored concepts is too few to derive a moving bar; a "
                       f"median of four moves with whichever four they were"),
        }
    median = statistics.median(s.score for s in recent)
    value = max(ABSOLUTE_FLOOR, round(median, 3))
    return {
        "floor": value,
        "derived_from": "trailing_median",
        "cohort": len(recent),
        "trailing_median": round(median, 3),
        "absolute_floor": ABSOLUTE_FLOOR,
        "held_by_absolute": value == ABSOLUTE_FLOOR and median < ABSOLUTE_FLOOR,
        "note": ("The bar is the company's own recent median, so a concept that would have "
                 "passed six months ago can fail today. A trailing median alone would also "
                 "let a bad quarter lower the standard permanently, which is a fixed "
                 "threshold arriving from the other direction -- hence the absolute floor "
                 "underneath it (#124)."),
    }


def aspiration(benchmark_scores: list[float]) -> dict:
    """Where a flagship aims: the category's top decile, not its mean (#125)."""
    if len(benchmark_scores) < 5:
        return {"measurable": False,
                "reason": (f"{len(benchmark_scores)} benchmark scores cannot produce a "
                           f"percentile. A top decile estimated from three products is the "
                           f"best of three"),
                "top_decile": None}
    ordered = sorted(benchmark_scores)
    index = min(len(ordered) - 1, int(round(TOP_DECILE * (len(ordered) - 1))))
    return {
        "measurable": True,
        "top_decile": round(ordered[index], 3),
        "category_mean": round(statistics.fmean(ordered), 3),
        "sample": len(ordered),
        "note": ("Parity with the mean is the floor and this is the target. Aiming at the "
                 "mean of a category produces the mean of a category, which is the "
                 "definition of forgettable (#125)."),
    }


def meets_standard(score: float, *, make_lane: str, history: list[Scored],
                   benchmark_scores: list[float] | None = None,
                   taste_rejection: str | None = None) -> dict:
    """Does this concept clear the bar that applies to it today?

    A taste rejection ends the question. No correctness score overrides it, because the
    correctness score is the thing a boring concept passes (#129).
    """
    if taste_rejection is not None:
        if taste_rejection not in TASTE_REJECTIONS:
            raise StandardRefused(
                f"{taste_rejection!r} is not a taste rejection: {sorted(TASTE_REJECTIONS)}. "
                f"An open field here becomes 'not sure', which is not a judgement")
        return {
            "passes": False,
            "rejected_on": "taste",
            "reason": taste_rejection,
            "meaning": TASTE_REJECTIONS[taste_rejection],
            "score": score,
            "note": ("A taste rejection carries no correctness content and cannot be "
                     "overridden by a correctness score -- the correctness score is exactly "
                     "what a boring concept passes. Agents must be able to reject "
                     "technically valid ideas (#129)."),
        }

    current = floor(history)
    required = current["floor"]
    target = None
    if make_lane == "FLAGSHIP":
        aim = aspiration(benchmark_scores or [])
        if aim["measurable"]:
            target = aim["top_decile"]

    return {
        "passes": score >= required,
        "rejected_on": None if score >= required else "floor",
        "score": score,
        "floor": required,
        "floor_derived_from": current["derived_from"],
        "flagship_target": target,
        "meets_flagship_target": (None if target is None else score >= target),
        "note": (f"clears the floor of {required} and is below the flagship target of "
                 f"{target}: acceptable, and not what a flagship is for"
                 if target is not None and required <= score < target else
                 current.get("note", "")),
    }


# ---------------------------------------------------------------------------
# #127: the failure autopsy


def autopsy(db, *, concept_key: str, cohort: str, reason: str, detail: str,
            score: float = 0.0) -> int:
    """Record why a concept failed, so forty rejections become one lesson.

    The useful output of a tournament that rejected forty concepts is the pattern in the
    forty, and it exists only if somebody wrote them down.
    """
    from ..core.models import AuditLog

    if reason not in TASTE_REJECTIONS and reason not in ("floor", "jury", "feasibility",
                                                         "rights", "silhouette"):
        raise StandardRefused(
            f"{reason!r} is not a recorded failure reason. Free text here produces forty "
            f"autopsies with forty reasons and no pattern")
    if len(detail.split()) < 5:
        raise StandardRefused(
            "an autopsy says what specifically was wrong; a category alone is the thing "
            "already recorded in `reason`")
    with db.session() as s:
        row = AuditLog(actor="product_creativity", action="concept.autopsy",
                       artifact=concept_key,
                       detail={"cohort": cohort, "reason": reason, "detail": detail.strip(),
                               "score": score, "on": date.today().isoformat()})
        s.add(row)
        s.flush()
        return row.id


def autopsy_patterns(db, *, cohort: str = "") -> dict:
    """What the rejections have in common, which is the point of keeping them (#127)."""
    from sqlalchemy import select

    from ..core.models import AuditLog

    with db.session() as s:
        rows = [a.detail or {} for a in s.scalars(select(AuditLog).where(
            AuditLog.action == "concept.autopsy"))]
    if cohort:
        rows = [r for r in rows if r.get("cohort") == cohort]

    if not rows:
        return {"autopsies": 0, "patterns": {},
                "note": ("no rejection has been recorded. A tournament that rejected forty "
                         "concepts and kept none of the reasons has produced a shortlist "
                         "and no learning")}

    by_reason: dict[str, int] = {}
    for r in rows:
        key = r.get("reason", "unrecorded")
        by_reason[key] = by_reason.get(key, 0) + 1
    dominant = max(by_reason, key=by_reason.get)
    return {
        "autopsies": len(rows),
        "patterns": dict(sorted(by_reason.items(), key=lambda kv: -kv[1])),
        "dominant_reason": dominant,
        "share": round(by_reason[dominant] / len(rows), 3),
        "note": (f"{by_reason[dominant]} of {len(rows)} rejections were {dominant!r}: that "
                 f"is a brief problem rather than forty concept problems, and it is only "
                 f"visible because the reasons were recorded (#127)."),
    }
