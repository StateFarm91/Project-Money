"""The concept tournament, and the autopsy of everything it kills.

Requirements 84, 94, 104. #84 wants twelve to twenty-five materially different concepts per
opportunity and says plainly what not to accept: superficial colour and name variations.

The word doing the work is *materially*. A field of twenty is trivially produced by varying a
palette twenty times, and it looks like a tournament in every report. So the field itself is
judged before any concept in it is: a field whose mean pairwise distance is below the spread
minimum is refused as not a tournament, and the duplicate pairs are named.

What survives a tournament here is never "the winner". It is the survivors, with the honest
note that structural survival is not desirability — the taste judgement is a separate gate and
currently nobody can make it.

The autopsy is the point as much as the survivors are (#94, #104): a creative system that
cannot say what it stopped making, and why, has no way to get better at making things.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from .concept import Concept, Field
from .jury import (
    APPROVED, Context, FIELD_SPREAD_MINIMUM, MAX_FIELD, MIN_FIELD, NEEDS_TASTE, REJECTED,
    Verdict, judge,
)


class FieldRefused(ValueError):
    """A set of concepts that is not a tournament."""


@dataclass
class Result:
    opportunity: str
    at: str
    field_size: int
    spread: float
    survivors: list[Verdict] = field(default_factory=list)
    rejected: list[Verdict] = field(default_factory=list)
    duplicate_pairs: list[tuple] = field(default_factory=list)

    @property
    def survival_rate(self) -> float:
        return round(len(self.survivors) / self.field_size, 3) if self.field_size else 0.0

    def to_dict(self) -> dict:
        return {
            "opportunity": self.opportunity, "at": self.at,
            "field_size": self.field_size, "spread": self.spread,
            "survivors": [v.to_dict() for v in self.survivors],
            "rejected": [v.to_dict() for v in self.rejected],
            "survival_rate": self.survival_rate,
            "duplicate_pairs": [list(p) for p in self.duplicate_pairs],
            "note": ("Survivors are structurally clean, not desirable. Desirability needs a "
                     "judgement about how the thing looks, and while nothing in this system "
                     "can see, no concept may be marked approved (#83)."),
        }


def check_field(f: Field) -> None:
    """Refuse a field that is a list of recolours wearing a tournament's name."""
    if len(f.concepts) < MIN_FIELD:
        raise FieldRefused(
            f"{len(f.concepts)} concepts is not a tournament: #84 asks for {MIN_FIELD}-"
            f"{MAX_FIELD} materially different ideas, and a short field is how the first "
            f"plausible idea wins by default")
    if len(f.concepts) > MAX_FIELD:
        raise FieldRefused(
            f"{len(f.concepts)} concepts exceeds {MAX_FIELD}: past this the field is padding "
            f"and the judging gets cheaper per concept, which is the wrong direction")

    keys = [c.key for c in f.concepts]
    if len(keys) != len(set(keys)):
        raise FieldRefused("the field contains the same concept twice")

    spread = f.spread()
    if spread < FIELD_SPREAD_MINIMUM:
        duplicates = f.duplicate_pairs()
        raise FieldRefused(
            f"mean pairwise distance is {spread}, below {FIELD_SPREAD_MINIMUM}. This is not a "
            f"diverse field, it is one idea in {len(f.concepts)} costumes — "
            f"{len(duplicates)} pairs are near-identical, closest: "
            f"{duplicates[:3] if duplicates else 'none individually, but the field is flat'}")


def run(f: Field, *, catalogue: list[Concept] | None = None,
        benchmark: list[Concept] | None = None,
        techniques: dict[str, int] | None = None) -> Result:
    """Judge a field. Refuses the field first, then every concept in it."""
    check_field(f)
    techniques = techniques or {}
    now = datetime.now(timezone.utc).isoformat()
    result = Result(opportunity=f.opportunity, at=now, field_size=len(f.concepts),
                    spread=f.spread(), duplicate_pairs=f.duplicate_pairs())

    for concept in f.concepts:
        ctx = Context(field=f, catalogue=catalogue, benchmark=benchmark,
                      techniques=techniques.get(concept.key, 1))
        verdict = judge(concept, ctx)
        (result.survivors if verdict.survives else result.rejected).append(verdict)
    return result


def autopsy(result: Result) -> dict:
    """Why concepts died, aggregated — the input to getting better (#94, #104).

    A creative system that cannot say what it stopped making has no way to improve at making
    things. Counting by critic turns a pile of rejections into a diagnosis: a field dying
    mostly of `sameness` has a generation problem, one dying of `complexity` has a brief
    problem, and those are different fixes.
    """
    by_critic: dict[str, int] = {}
    examples: dict[str, str] = {}
    for verdict in result.rejected:
        for finding in verdict.findings:
            by_critic[finding.critic] = by_critic.get(finding.critic, 0) + 1
            examples.setdefault(finding.critic, finding.problem)

    dominant = max(by_critic, key=by_critic.get) if by_critic else None
    diagnosis = {
        "sameness": "the generator is varying decoration rather than ideas; the fix is in "
                    "what it is allowed to change, not in trying harder",
        "genericness": "briefs are producing product descriptions instead of premises",
        "emotional_appeal": "concepts are not being asked who they are for",
        "derivative": "the field is anchoring too closely on observed competitor products",
        "thumbnail": "ideas depend on detail that does not survive the grid",
        "complexity": "briefs are over-scoped for their make lane",
        "shopping_window": "briefs are being written for an occasion the buyer can no "
                           "longer finish them for; late-window capacity belongs on fast "
                           "makes rather than on products nobody has time to complete",
    }.get(dominant or "", "")

    return {
        "opportunity": result.opportunity,
        "field_size": result.field_size,
        "survival_rate": result.survival_rate,
        "deaths_by_critic": dict(sorted(by_critic.items(), key=lambda kv: -kv[1])),
        "dominant_cause": dominant,
        "diagnosis": diagnosis,
        "examples": examples,
    }


def scorecard(results: list[Result]) -> dict:
    """Creative capability over time (#94), and the direction it must move (#104).

    Survival rate alone would reward a lenient jury, so it is reported beside field spread and
    the death causes: a rising survival rate with falling spread is a jury going soft, not a
    company getting better.
    """
    if not results:
        return {"tournaments": 0,
                "note": "no tournament has been run, so there is no creative capability "
                        "history to report"}

    spreads = [r.spread for r in results]
    rates = [r.survival_rate for r in results]
    causes: dict[str, int] = {}
    for r in results:
        for v in r.rejected:
            for finding in v.findings:
                causes[finding.critic] = causes.get(finding.critic, 0) + 1

    def trend(values: list[float]) -> str:
        if len(values) < 2:
            return "insufficient history"
        first, last = values[0], values[-1]
        if abs(last - first) < 0.02:
            return "flat"
        return "improving" if last > first else "declining"

    return {
        "tournaments": len(results),
        "mean_field_spread": round(sum(spreads) / len(spreads), 4),
        "mean_survival_rate": round(sum(rates) / len(rates), 4),
        "spread_trend": trend(spreads),
        "survival_trend": trend(rates),
        "deaths_by_critic": dict(sorted(causes.items(), key=lambda kv: -kv[1])),
        "warning": ("Survival rising while spread falls means the fields are getting "
                    "narrower, not the ideas better — a jury going soft looks identical to "
                    "progress on survival rate alone."
                    if trend(rates) == "improving" and trend(spreads) == "declining" else ""),
        "north_star": ("Later concepts should be more desirable, distinctive and "
                       "commercially informed than earlier ones (#104). Distinctiveness is "
                       "measured here. Desirability is measurable from 2026-09-19: "
                       "creative/blinded.py runs same-pod blinded head-to-heads against the "
                       "observed human catalogue, and reports `unmeasured` rather than a "
                       "win rate until enough pairs are judged without position bias."),
        "blinded_comparison": ("creative.blinded.run -- the agent side of #94's human/agent "
                               "comparison. Not run from here: it costs model calls against "
                               "the monthly ceiling, so it is invoked deliberately"),
    }
