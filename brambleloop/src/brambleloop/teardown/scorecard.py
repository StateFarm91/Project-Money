"""Scoring a purchased benchmark, and building a standard out of the best of all of them.

Requirements 151, 161, 162, 163, 164, 169. The laboratory's output is not a review; it is a
standard this company then has to meet. Three rules shape it:

**Never copy one seller wholesale (#162).** The composite takes the best chart practice from
one benchmark, the strongest navigation from another, the best beginner support from a third.
Adopting one shop's product as the target would be imitation with extra steps, and it caps
the company at that shop.

**Parity is a failure (#163).** For every product class the company must name at least one
meaningful advantage beyond what the purchased competitors provide. A composite of other
people's strengths is a floor, not a position.

**A teardown that produces no action is a review (#164).** Every finding carries the
improvement it implies, and a finding without one is refused at the point of recording.
"""
from __future__ import annotations

from dataclasses import dataclass

from .library import check_derived

# The twelve dimensions #161 names. Closed, because a scorecard that grows a dimension per
# product cannot be compared across products, which is the only thing a scorecard is for.
DIMENSIONS: tuple[str, ...] = (
    "product_creativity",
    "pattern_correctness_evidence",
    "instruction_clarity",
    "chart_quality",
    "beginner_support",
    "premium_presentation",
    "video_support",
    "materials_clarity",
    "delivery_packaging",
    "support_experience",
    "listing_promise_alignment",
    "perceived_value",
)

# Scores are 0-5 on a described scale rather than a feeling, because "4/5 premium" means
# nothing next month and nothing at all to a different analyst.
SCALE: dict[int, str] = {
    0: "absent",
    1: "present and actively confusing",
    2: "present and weak",
    3: "competent; what a buyer expects",
    4: "strong; better than the category norm",
    5: "the best example in the library",
}


class ScoreRefused(Exception):
    """A score outside the scale, on a dimension that does not exist, or with no action."""


@dataclass(frozen=True)
class Finding:
    benchmark_ref: str
    dimension: str
    score: int
    mechanism: str
    improvement: str

    def to_dict(self) -> dict:
        return {"benchmark_ref": self.benchmark_ref, "dimension": self.dimension,
                "score": self.score, "mechanism": self.mechanism,
                "improvement": self.improvement}


def finding(benchmark_ref: str, dimension: str, score: int, mechanism: str,
            improvement: str) -> Finding:
    """Build a scored finding, refusing the three ways it goes wrong."""
    if dimension not in DIMENSIONS:
        raise ScoreRefused(f"{dimension!r} is not one of the twelve dimensions")
    if score not in SCALE:
        raise ScoreRefused(f"{score!r} is not on the 0-5 scale: {SCALE}")
    if len(mechanism.strip()) < 15:
        raise ScoreRefused("a score with no mechanism is an opinion; say what produced it")
    if len(improvement.strip()) < 15:
        raise ScoreRefused(
            "every finding names what Brambleloop should do about it. A teardown that "
            "produces no action is a review (#164)")
    check_derived(mechanism)
    check_derived(improvement)
    return Finding(benchmark_ref, dimension, score, mechanism.strip(), improvement.strip())


def record(db, f: Finding) -> int:
    from ..core.models import TeardownFinding

    with db.session() as s:
        row = TeardownFinding(benchmark_ref=f.benchmark_ref, dimension=f.dimension,
                              score=float(f.score), mechanism=f.mechanism,
                              improvement=f.improvement)
        s.add(row)
        s.flush()
        return row.id


def scorecard(db, benchmark_ref: str) -> dict:
    """One benchmark's twelve scores, with the dimensions nobody has looked at named."""
    from sqlalchemy import select

    from ..core.models import TeardownFinding

    with db.session() as s:
        rows = list(s.scalars(select(TeardownFinding).where(
            TeardownFinding.benchmark_ref == benchmark_ref)))

    best: dict[str, dict] = {}
    for r in rows:
        current = best.get(r.dimension)
        if current is None or r.score > current["score"]:
            best[r.dimension] = {"score": r.score, "mechanism": r.mechanism,
                                 "improvement": r.improvement}
    unscored = [d for d in DIMENSIONS if d not in best]
    return {
        "benchmark": benchmark_ref,
        "scores": best,
        "unscored_dimensions": unscored,
        # Averaging over the dimensions somebody happened to score would let a teardown that
        # looked at two things outrank one that looked at twelve.
        "complete": not unscored,
        "mean": (round(sum(v["score"] for v in best.values()) / len(best), 2)
                 if best else None),
    }


def composite_standard(db) -> dict:
    """The Brambleloop Premium Product Standard, assembled best-of-breed (#162).

    Each dimension takes its target from whichever benchmark did it best, so the standard is
    better than every individual product in the library and is nobody's product.

    Ties keep everybody. On a 0-5 scale across twelve dimensions and ten benchmarks, ties are
    ordinary, and resolving one by insertion order would quietly bias the whole composite
    toward whichever product happened to be torn down first -- which is the single-source
    failure this requirement exists to prevent, arriving by accident instead of by choice. If
    two benchmarks reach the same bar by different mechanisms, the standard has two mechanisms
    to learn from and says so.
    """
    from sqlalchemy import select

    from ..core.models import TeardownFinding

    with db.session() as s:
        rows = list(s.scalars(select(TeardownFinding)))

    best_score: dict[str, float] = {}
    for r in rows:
        if r.score > best_score.get(r.dimension, -1.0):
            best_score[r.dimension] = r.score

    by_dimension: dict[str, dict] = {}
    for dimension, top in best_score.items():
        tied = sorted((r for r in rows
                       if r.dimension == dimension and r.score == top),
                      key=lambda r: (r.benchmark_ref, r.id))
        by_dimension[dimension] = {
            "score": top,
            "from_benchmark": tied[0].benchmark_ref,
            "mechanism": tied[0].mechanism,
            "target": tied[0].improvement,
            "contributors": [{"benchmark": t.benchmark_ref, "mechanism": t.mechanism,
                              "target": t.improvement} for t in tied],
        }

    sources = sorted({c["benchmark"] for v in by_dimension.values()
                      for c in v["contributors"]})
    missing = [d for d in DIMENSIONS if d not in by_dimension]
    return {
        "dimensions": by_dimension,
        "source_benchmarks": sources,
        "dimensions_without_evidence": missing,
        # A composite drawn from one seller is that seller's product with extra steps.
        "single_source": len(sources) == 1,
        "usable_as_a_standard": bool(by_dimension) and not missing,
        "note": ("Each dimension takes its target from whichever benchmark did it best, so "
                 "the standard belongs to no single seller and is stronger than any one of "
                 "them." if len(sources) > 1 else
                 "Not yet a composite: every target currently comes from one benchmark, "
                 "which would make this an imitation of that product rather than a standard."),
    }


# ---------------------------------------------------------------------------
# Parity is not a position (#163)

# Advantages this company can actually claim, each anchored in something it already built.
# Free text would accept "better quality", which is not an advantage, it is a hope.
ADVANTAGES: dict[str, str] = {
    "deterministic_validation": "every stitch count, repeat and finished dimension is "
                                "machine-checked and reverse-compiled before release",
    "reverse_compilation": "the written pattern is compiled back and compared to the source, "
                           "so the document and the design cannot disagree",
    "colour_independent_charts": "every chart carries a per-yarn letter in each cell, so it "
                                 "is readable without colour vision",
    "version_aware_support": "answers are given from the exact pattern version the customer "
                             "bought",
    "measured_yardage": "yardage is computed from the twin and calibrated against a physical "
                        "sample, not estimated from the ball band",
    "size_refusal": "a finished dimension the geometry cannot support is refused rather than "
                    "stated",
}


class ParityRefused(Exception):
    """A product class claiming benchmark parity as though it were a position."""


def check_unique_value(product_class: str, advantages: list[str]) -> dict:
    """#163: name at least one real advantage beyond the composite, per product class."""
    unknown = [a for a in advantages if a not in ADVANTAGES]
    if unknown:
        raise ParityRefused(
            f"{sorted(unknown)} are not advantages this company can evidence. An advantage is "
            f"something already built and checkable, not an aspiration")
    if not advantages:
        raise ParityRefused(
            f"{product_class!r} claims no advantage beyond the purchased benchmarks. Parity "
            f"with a composite of other people's strengths is a floor, not a position (#163)")
    return {"product_class": product_class,
            "advantages": {a: ADVANTAGES[a] for a in advantages}}


def delight_question(scores: dict[str, float]) -> dict:
    """#169: 'after paying, does this feel better than expected?'

    Answered from the dimensions that actually produce that feeling rather than from the mean,
    because a product can be average everywhere and delightful nowhere.
    """
    drivers = ("instruction_clarity", "chart_quality", "beginner_support",
               "premium_presentation", "delivery_packaging", "support_experience")
    present = {d: scores[d] for d in drivers if d in scores}
    if not present:
        return {"answerable": False,
                "reason": "none of the dimensions that create post-purchase delight have "
                          "been scored"}
    weakest = min(present, key=present.get)
    return {
        "answerable": True,
        "drivers": present,
        "weakest": weakest,
        "better_than_expected": all(v >= 4 for v in present.values()),
        "note": (f"{weakest} at {present[weakest]} is what a buyer would notice first"
                 if present[weakest] < 4 else
                 "every delight driver scores strong or better"),
    }


def improvement_queue(db, limit: int = 40) -> list[dict]:
    """Findings not yet promoted into the Improvement Department (#164)."""
    from sqlalchemy import select

    from ..core.models import TeardownFinding

    with db.session() as s:
        rows = list(s.scalars(select(TeardownFinding).where(
            TeardownFinding.promoted == False)))  # noqa: E712
        out = [{"id": r.id, "benchmark": r.benchmark_ref, "dimension": r.dimension,
                "score": r.score, "mechanism": r.mechanism, "improvement": r.improvement}
               for r in rows]
    # The strongest thing a competitor does is the most useful thing to copy the mechanism of.
    return sorted(out, key=lambda d: -d["score"])[:limit]


# ---------------------------------------------------------------------------
# Promise-to-delivery (#151)
#
# The single most useful thing a teardown produces, because it is the only one a customer
# experiences directly: the listing said one thing and the download contained another.

# What a listing can promise, mapped to the evidence in the manifest that would settle it.
PROMISES: dict[str, str] = {
    "chart_included": "has_chart",
    "video_included": "has_video",
    "print_edition": "has_print_edition",
    "bonus_included": "has_bonus",
}


def promise_audit(listing_promises: dict, inferred: dict) -> dict:
    """Compare what the listing promised against what the folder actually contains.

    Only the promises the manifest can settle are judged. A promise about sizing depth or
    troubleshooting quality needs somebody to read the document, and claiming to have checked
    it from filenames would be the same error as grading a listing from its thumbnail.
    """
    kept: list[str] = []
    broken: list[dict] = []
    unverifiable: list[str] = []

    for promise, value in (listing_promises or {}).items():
        if promise == "file_count":
            continue  # counted below, where the comparison is a number rather than a flag
        evidence_key = PROMISES.get(promise)
        if evidence_key is None:
            unverifiable.append(promise)
            continue
        delivered = bool(inferred.get(evidence_key))
        if bool(value) == delivered:
            kept.append(promise)
        else:
            broken.append({"promise": promise, "listing_said": bool(value),
                           "download_contains": delivered})

    promised_files = (listing_promises or {}).get("file_count")
    if promised_files is not None and inferred.get("file_count") is not None:
        if int(promised_files) != int(inferred["file_count"]):
            broken.append({"promise": "file_count", "listing_said": int(promised_files),
                           "download_contains": int(inferred["file_count"])})
        else:
            kept.append("file_count")

    return {
        "kept": sorted(kept),
        "broken": broken,
        "unverifiable_from_filenames": sorted(unverifiable),
        "alignment": (round(len(kept) / (len(kept) + len(broken)), 2)
                      if (kept or broken) else None),
        "note": ("Promises about sizing depth, troubleshooting or instruction quality are "
                 "not judged here: settling them means reading the document, and grading "
                 "them from filenames would be guessing."),
    }
