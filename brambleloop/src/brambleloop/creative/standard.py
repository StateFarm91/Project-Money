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


# ---------------------------------------------------------------------------
# #132: the creative department's north-star metrics

# Eleven metrics, and the split that matters: four the company can compute today, seven that
# need customers. Reported together with which is which, because a dashboard showing four
# green numbers and seven blanks is a dashboard somebody reads as four green numbers.
NORTH_STAR: dict[str, tuple[bool, str]] = {
    "concept_to_engineering_survival": (True, "concepts that reached a CIR"),
    "concept_to_launch_survival": (True, "concepts that reached a listing"),
    "blind_grid_score": (True, "how it reads in a grid, judged without its title"),
    "novelty_distance": (True, "how far it sits from the nearest thing we already sell"),
    "ctr": (False, "impressions that became visits"),
    "favourite_rate": (False, "visits that became saves"),
    "conversion": (False, "visits that became orders"),
    "bestseller_incidence": (False, "share of concepts that became a bestseller"),
    "contribution": (False, "what it earned after fees"),
    "collection_attach_rate": (False, "how often it sold beside a sibling"),
    "creative_defect_rate": (False, "released concepts that produced a quality incident"),
}


def north_star(cohorts: dict[str, dict]) -> dict:
    """Is creativity actually getting better, by cohort? (#132)

    Cohorts rather than a running total, because a running average of everything ever made
    moves too slowly to show that anything changed — which makes it indistinguishable from
    nothing changing.
    """
    unknown = {m for c in cohorts.values() for m in c if m not in NORTH_STAR}
    if unknown:
        raise StandardRefused(
            f"{sorted(unknown)} are not north-star metrics: {sorted(NORTH_STAR)}")

    computable = [m for m, (now, _) in NORTH_STAR.items() if now]
    needs_customers = [m for m, (now, _) in NORTH_STAR.items() if not now]

    ordered = sorted(cohorts)
    movement = {}
    if len(ordered) >= 2:
        first, last = cohorts[ordered[0]], cohorts[ordered[-1]]
        for metric in NORTH_STAR:
            before, after = first.get(metric), last.get(metric)
            if before is None or after is None:
                movement[metric] = {"direction": "unmeasured",
                                    "why": "not present in both cohorts"}
                continue
            movement[metric] = {
                "before": before, "after": after,
                "direction": ("improved" if after > before
                              else "regressed" if after < before else "flat"),
            }

    improving = [m for m, v in movement.items() if v.get("direction") == "improved"]
    regressing = [m for m, v in movement.items() if v.get("direction") == "regressed"]
    return {
        "cohorts": ordered,
        "metrics": {m: {"computable_today": now, "meaning": why}
                    for m, (now, why) in NORTH_STAR.items()},
        "computable_today": computable,
        "needs_customers": needs_customers,
        "movement": movement,
        "improving": improving,
        "regressing": regressing,
        "answerable": len(ordered) >= 2,
        "note": ("Four of the eleven can be computed today and seven need customers. They "
                 "are reported together with which is which, because a dashboard showing "
                 "four green numbers and seven blanks is read as four green numbers (#132)."
                 if len(ordered) < 2 else
                 f"{len(improving)} improving, {len(regressing)} regressing between "
                 f"{ordered[0]} and {ordered[-1]}. Cohorts rather than a running total: an "
                 f"average of everything ever made moves too slowly to show that anything "
                 f"changed, which is indistinguishable from nothing changing."),
    }


# ---------------------------------------------------------------------------
# #104's two remaining clauses
#
# "more desirable, distinctive and **commercially informed** than earlier ones", and "if
# creative capability plateaus, the Improvement Department treats that as a top-level
# business defect". Desirability is the blinded comparison and distinctiveness is novelty
# distance; these two were the parts nothing computed.

# A cohort must move by at least this much on a metric to count as having moved at all.
# Below it, a difference is noise wearing a direction -- and `north_star()` above will call
# a 0.001 rise "improved", which is how a plateau is reported as progress for a year.
MEANINGFUL_MOVE = 0.03

# How many consecutive cohorts may fail to move before it is a defect rather than a quiet
# patch. Two is a pause; three is the shape of a company that has stopped learning.
PLATEAU_COHORTS = 3


def commercially_informed(concepts: list, proven: list[dict]) -> dict:
    """What share of a field aims at a market the benchmark was observed selling into.

    This is the difference between a concept that is interesting and one that is aimed. The
    existing catalogue scores near zero against the live matrix, which is not a criticism of
    the ideas -- it is the measured consequence of a generator that was never told where the
    demand was.

    `proven` is the matrix's own proven-and-unserved rows, so this cannot drift into an
    opinion about which markets are good.
    """
    if not concepts:
        return {"concepts": 0, "informed": 0, "share": 0.0,
                "note": "no concept exists, so nothing is aimed anywhere yet"}

    wanted = {(row["event"], row["department"]) for row in proven}
    by_pod = {department for _event, department in wanted}

    aimed, near, rows = 0, 0, []
    for concept in concepts:
        pod = getattr(concept, "pod", "")
        occasion = getattr(concept, "occasion", "")
        # The occasion vocabulary and the matrix's event names are different registers, so
        # the pod is the part that has to match and the occasion is scored separately.
        exact = pod in by_pod and any(
            occasion and occasion.lower() in event.lower() for event, dept in wanted
            if dept == pod)
        in_a_proven_department = pod in by_pod
        aimed += 1 if exact else 0
        near += 1 if in_a_proven_department and not exact else 0
        rows.append({"concept": getattr(concept, "key", ""), "pod": pod,
                     "occasion": occasion,
                     "aim": "proven_arena" if exact
                     else "proven_department" if in_a_proven_department else "unproven"})

    return {
        "concepts": len(concepts),
        "informed": aimed,
        "share": round(aimed / len(concepts), 4),
        "in_a_proven_department": near,
        "unproven": len(concepts) - aimed - near,
        "proven_arenas": len(wanted),
        "rows": rows[:40],
        "note": ("Aimed at a market somebody observed a competitor selling into, not at a "
                 "market this system finds plausible. A concept in a proven department but "
                 "the wrong occasion is counted separately rather than credited (#104)."),
    }


def plateau(history: list[dict], *, metric: str, cohorts: int = PLATEAU_COHORTS) -> dict:
    """Has creative capability stopped moving? (#104)

    The requirement says a plateau is a **top-level business defect**, not a disappointing
    quarter, so the answer has to be checkable rather than a judgement somebody can decline
    to make. Two rules do the work:

      - a move smaller than `MEANINGFUL_MOVE` is not a move. `north_star()` calls any rise
        "improved", including 0.001, which is how a flat line is reported as progress for a
        year;
      - and a metric with no reading is `unmeasured`, never flat. A company that stopped
        measuring looks exactly like a company that stopped improving, and the remedy for
        each is the opposite of the remedy for the other.
    """
    if metric not in NORTH_STAR:
        raise StandardRefused(f"{metric!r} is not a north-star metric: {sorted(NORTH_STAR)}")

    readings = [(h["cohort"], h.get(metric)) for h in history]
    present = [(name, value) for name, value in readings if value is not None]
    if len(present) < cohorts:
        return {
            "metric": metric, "verdict": "unmeasured", "is_defect": False,
            "readings": len(present), "needs": cohorts,
            "reason": (f"{len(present)} cohort(s) carry a reading for {metric!r} and a "
                       f"plateau needs {cohorts}. A company that stopped measuring looks "
                       f"exactly like one that stopped improving, and the remedy for each "
                       f"is the opposite of the remedy for the other"),
        }

    window = present[-cohorts:]
    moves = [round(window[i + 1][1] - window[i][1], 6) for i in range(len(window) - 1)]
    meaningful = [m for m in moves if abs(m) >= MEANINGFUL_MOVE]
    flat = not meaningful
    declining = all(m <= 0 for m in moves) and any(abs(m) >= MEANINGFUL_MOVE for m in moves)

    return {
        "metric": metric,
        "cohorts": [name for name, _ in window],
        "values": [value for _, value in window],
        "moves": moves,
        "threshold": MEANINGFUL_MOVE,
        "verdict": "plateau" if flat else "declining" if declining else "moving",
        "is_defect": flat or declining,
        "reason": (
            f"{len(window)} consecutive cohorts moved by less than {MEANINGFUL_MOVE} on "
            f"{metric!r}. #104 makes that a top-level business defect rather than a "
            f"disappointing quarter" if flat else
            f"{metric!r} has moved backwards across {len(window)} cohorts" if declining else
            f"{metric!r} moved by {max(moves, key=abs)} across {len(window)} cohorts"),
    }
