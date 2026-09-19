"""From a teardown finding to a promoted improvement, and the challenge before launch.

Requirements 164 and 168. Both exist because a teardown that ends in a document is a hobby.

**#164 is a pipeline, not a hand-off.** A finding becomes a hypothesis owned by an improvement
cell, tested in the sandbox, compared against the current Brambleloop standard, and promoted
only when the number moved. Every one of those steps already exists in `improve/`; what was
missing was the join, and a join that is a convention rather than a function is one that stops
being followed in the third week.

The join is deliberately narrow. `promote()` refuses to invent the surface a change touches,
the cell that owns it, or the way back — `improve.governance` would refuse an undeclared
surface anyway, and routing through it means a teardown finding that says "loosen the claim
gates so our listings look as confident as theirs" is refused by the same rule that refuses it
when a cell proposes it directly. A competitor doing something this company is not allowed to
do is not an improvement hypothesis; it is a finding about the competitor.

**#168 is a gate, not a report.** Before a live launch, representative Brambleloop products are
compared against category-matched purchased benchmarks across the dimensions a buyer actually
experiences. Materially inferior on a critical dimension blocks the release unless somebody
declared the tradeoff in advance and named what is gained instead — and "named" means one of
the advantages this company can evidence, because a tradeoff justified by an aspiration is an
excuse with a form attached.

An unrun challenge is not a pass. With no category-matched benchmark the verdict is
`unavailable` and the release is blocked, for the same reason the canonical-identity drift
check blocks without a pack: a gate that waves things through when its evidence is missing is
not a gate, and the moment it matters most is exactly the moment the evidence is thin.
"""
from __future__ import annotations

from .scorecard import ADVANTAGES, DIMENSIONS, SCALE

# Which improvement cell owns which dimension. Closed, because "whoever picks it up" is how a
# finding sits in a queue for a quarter.
CELL_FOR_DIMENSION: dict[str, str] = {
    "product_creativity": "product_creativity",
    "pattern_correctness_evidence": "pattern_engineering",
    "instruction_clarity": "pattern_engineering",
    "chart_quality": "creative_assets",
    "beginner_support": "customer_experience",
    "premium_presentation": "creative_assets",
    "video_support": "creative_assets",
    "materials_clarity": "pattern_engineering",
    "delivery_packaging": "customer_experience",
    "support_experience": "customer_experience",
    "listing_promise_alignment": "quality",
    "perceived_value": "pricing",
}

assert set(CELL_FOR_DIMENSION) == set(DIMENSIONS)

# The dimensions #168 names as the ones a buyer experiences directly in the first ten minutes
# after paying. Being behind on video support is a gap; being behind on instruction clarity is
# a refund.
CRITICAL_DIMENSIONS: tuple[str, ...] = (
    "listing_promise_alignment",
    "delivery_packaging",
    "instruction_clarity",
    "chart_quality",
    "premium_presentation",
    "support_experience",
    "perceived_value",
)

# A full point on a described scale is a category a buyer would name out loud: "competent" to
# "strong" is not a rounding difference.
MATERIAL_GAP = 1.0


class PipelineRefused(Exception):
    """A finding that cannot become a hypothesis, or a tradeoff that is an excuse."""


class ChallengeRefused(Exception):
    """A pre-launch comparison that cannot be made honestly."""


# ---------------------------------------------------------------------------
# #164: finding -> hypothesis -> test -> promotion


def promote(db, finding_id: int, *, touches: tuple[str, ...], rollback_ref: str,
            cell: str = "", expected_effect: str = "") -> dict:
    """Turn one recorded teardown finding into an improvement hypothesis.

    Routed through `improve.cells.propose`, so the baseline is captured now and the
    governance boundary applies unchanged. A finding whose implied action would weaken a
    protected gate is refused here by the same rule that refuses it anywhere else.
    """
    from ..core.models import TeardownFinding
    from ..improve import cells

    with db.session() as s:
        row = s.get(TeardownFinding, finding_id)
        if row is None:
            raise PipelineRefused(f"no teardown finding {finding_id}")
        if row.promoted:
            raise PipelineRefused(
                f"finding {finding_id} was already promoted as improvement "
                f"{(row.detail or {}).get('improvement_id')}. Promoting it twice would give "
                f"one observation two baselines and make whichever ran second look like a win")
        dimension = row.dimension
        mechanism = row.mechanism
        improvement_text = row.improvement
        benchmark = row.benchmark_ref
        score = row.score
        detail = dict(row.detail or {})

    owner = cell or CELL_FOR_DIMENSION.get(dimension, "")
    if not owner:
        raise PipelineRefused(
            f"{dimension!r} has no improvement cell. An unowned finding is one nobody is "
            f"accountable for, which is indistinguishable from one nobody recorded")
    if not touches:
        raise PipelineRefused(
            "name the surface this change touches. An undeclared surface is refused by "
            "improve.governance anyway, and declaring it here is what makes the refusal "
            "arrive before the work rather than after it")
    if not rollback_ref:
        raise PipelineRefused(
            "no rollback reference. A teardown-driven change is still a change (#93)")

    hypothesis = (
        f"{benchmark} scores {int(score)} on {dimension} ({SCALE[int(score)]}); "
        f"{improvement_text}")
    effect = expected_effect or (
        f"a measurable move in {owner}'s metric, compared against the current Brambleloop "
        f"standard rather than against the benchmark")

    improvement_id = cells.propose(
        db, cell=owner, hypothesis=hypothesis, expected_effect=effect,
        rollback_ref=rollback_ref, touches=tuple(touches))

    with db.session() as s:
        row = s.get(TeardownFinding, finding_id)
        row.promoted = True
        detail.update({"improvement_id": improvement_id, "cell": owner,
                       "touches": list(touches)})
        row.detail = detail

    return {"finding": finding_id, "improvement": improvement_id, "cell": owner,
            "dimension": dimension, "hypothesis": hypothesis, "mechanism": mechanism}


def status(db) -> dict:
    """The honest funnel: recorded, hypothesised, tested, promoted.

    #164 ends at "promote only measurable improvements", so the interesting number is not how
    many findings were promoted into hypotheses — that is filing — but how many of those
    hypotheses beat a baseline. A finding that became a hypothesis nobody tested has changed
    nothing, and counting it as progress is how a laboratory reports throughput while the
    product stays the same.
    """
    from sqlalchemy import select

    from ..core.models import Improvement, TeardownFinding
    from ..improve import cells

    with db.session() as s:
        findings = list(s.scalars(select(TeardownFinding)))
        improvement_ids = [(f.detail or {}).get("improvement_id") for f in findings]
        improvement_ids = [i for i in improvement_ids if i]
        improvements = (list(s.scalars(select(Improvement).where(
            Improvement.id.in_(improvement_ids)))) if improvement_ids else [])

    by_state: dict[str, int] = {}
    for i in improvements:
        by_state[i.state] = by_state.get(i.state, 0) + 1

    promoted = by_state.get(cells.PROMOTED, 0)
    tested = promoted + by_state.get(cells.TESTING, 0) + by_state.get(cells.REJECTED, 0)
    return {
        "findings_recorded": len(findings),
        "findings_promoted_to_hypothesis": sum(1 for f in findings if f.promoted),
        "hypotheses_by_state": by_state,
        "hypotheses_tested": tested,
        "improvements_promoted": promoted,
        "unpromoted_findings": sum(1 for f in findings if not f.promoted),
        "note": ("Findings promoted into hypotheses is filing; hypotheses that beat a "
                 "baseline is improvement. The second number is the one #164 asks for."
                 if promoted < len(findings) else
                 "every recorded finding has produced a measured improvement"),
    }


# ---------------------------------------------------------------------------
# #168: the pre-launch benchmark challenge


def _best_by_dimension(db, category: str) -> dict[str, dict]:
    from sqlalchemy import select

    from ..core.models import BenchmarkProduct, TeardownFinding

    with db.session() as s:
        refs = [b.ref for b in s.scalars(select(BenchmarkProduct).where(
            BenchmarkProduct.category == category))] if category else [
            b.ref for b in s.scalars(select(BenchmarkProduct))]
        if not refs:
            return {}
        rows = list(s.scalars(select(TeardownFinding).where(
            TeardownFinding.benchmark_ref.in_(refs))))

    best: dict[str, dict] = {}
    for r in rows:
        current = best.get(r.dimension)
        if current is None or r.score > current["score"]:
            best[r.dimension] = {"score": r.score, "benchmark": r.benchmark_ref,
                                 "mechanism": r.mechanism}
    return best


def check_tradeoff(dimension: str, declared: dict) -> dict:
    """A deliberate tradeoff, or an excuse with a form attached.

    #168 allows being behind on a dimension when the tradeoff was deliberate. Deliberate
    means decided before the comparison and paid for with something real, so the gained
    advantage must be one of the ones this company can evidence (#163).
    """
    reason = str((declared or {}).get("reason") or "").strip()
    gained = str((declared or {}).get("gains") or "").strip()
    if len(reason) < 20:
        raise PipelineRefused(
            f"{dimension}: a tradeoff has to say what was traded. 'Deliberate' with no "
            f"reason is the same sentence as 'we did not get to it'")
    if gained not in ADVANTAGES:
        raise PipelineRefused(
            f"{dimension}: {gained!r} is not something this company can evidence as gained. "
            f"A tradeoff justified by an aspiration is an excuse with a form attached: "
            f"{sorted(ADVANTAGES)}")
    return {"dimension": dimension, "reason": reason, "gains": gained,
            "gains_description": ADVANTAGES[gained]}


def challenge(db, *, product_slug: str, category: str, our_scores: dict,
              tradeoffs: dict | None = None) -> dict:
    """Compare one Brambleloop product against the best category-matched benchmark (#168).

    Returns a verdict and, more importantly, whether the release is blocked. An unrun
    challenge blocks: a gate that passes when its evidence is missing is not a gate.
    """
    tradeoffs = tradeoffs or {}
    unknown = [d for d in our_scores if d not in DIMENSIONS]
    if unknown:
        raise ChallengeRefused(f"{sorted(unknown)} are not scorecard dimensions")
    if not category:
        raise ChallengeRefused(
            "a challenge with no category compares this product against whatever happened to "
            "be bought. #168 asks for a category-matched benchmark, and widening the pool "
            "until something matches is how a gate is passed without being met")

    best = _best_by_dimension(db, category)
    if not best:
        return {
            "product": product_slug, "category": category,
            "verdict": "unavailable",
            "comparable": False,
            "blocks_release": True,
            "reason": ("no category-matched purchased benchmark has been torn down, so the "
                       "comparison #168 requires cannot be made. An unrun challenge is not a "
                       "pass — the release is blocked until a benchmark exists to lose to"),
            "unblocked_by": ("the owner's benchmark purchases, then a teardown of at least "
                             "one product in this category"),
            "rows": [],
        }

    rows = []
    blocking = []
    excused = []
    for dimension in DIMENSIONS:
        bench = best.get(dimension)
        if bench is None:
            continue
        ours = our_scores.get(dimension)
        critical = dimension in CRITICAL_DIMENSIONS
        if ours is None:
            row = {"dimension": dimension, "critical": critical,
                   "benchmark": bench["benchmark"], "benchmark_score": bench["score"],
                   "our_score": None, "gap": None,
                   "state": "unscored"}
            rows.append(row)
            if critical:
                # Not scoring a critical dimension is not the same as passing it.
                blocking.append({**row, "why": (
                    "a critical dimension this product was never scored on. Leaving it "
                    "unscored would let the challenge be passed by omission")})
            continue

        gap = round(bench["score"] - float(ours), 2)
        materially_behind = gap >= MATERIAL_GAP
        row = {"dimension": dimension, "critical": critical,
               "benchmark": bench["benchmark"], "benchmark_score": bench["score"],
               "our_score": float(ours), "gap": gap,
               "state": ("behind" if materially_behind else
                         "ahead" if gap < 0 else "level")}
        if materially_behind and critical:
            declared = tradeoffs.get(dimension)
            if declared:
                row["tradeoff"] = check_tradeoff(dimension, declared)
                row["state"] = "behind_by_choice"
                excused.append(row)
            else:
                blocking.append({**row, "why": (
                    f"materially inferior on a critical dimension: {bench['benchmark']} "
                    f"scores {bench['score']:.0f} ({SCALE[int(bench['score'])]}) and this "
                    f"product scores {float(ours):.0f}, with no declared tradeoff")})
        rows.append(row)

    ahead = [r for r in rows if r["state"] == "ahead"]
    return {
        "product": product_slug,
        "category": category,
        "verdict": "blocked" if blocking else "passed",
        "comparable": True,
        "blocks_release": bool(blocking),
        "rows": rows,
        "blocking": blocking,
        "behind_by_choice": excused,
        "ahead_on": [r["dimension"] for r in ahead],
        "benchmarks_compared": sorted({r["benchmark"] for r in rows}),
        "note": ("Materially inferior on a critical dimension blocks the release for "
                 "remediation. A declared tradeoff unblocks it only when it names an "
                 "advantage this company can evidence as gained instead (#168, #163)."),
    }


def readiness_requirement(db, *, product_slug: str, category: str, our_scores: dict,
                          tradeoffs: dict | None = None) -> dict:
    """The challenge in the shape launch readiness reads, so it can block rather than inform."""
    result = challenge(db, product_slug=product_slug, category=category,
                       our_scores=our_scores, tradeoffs=tradeoffs)
    return {
        "key": "benchmark_challenge",
        "description": ("the representative product has beaten, or deliberately traded "
                        "against, the best category-matched purchased benchmark"),
        "ready": not result["blocks_release"],
        "blocked_by": None if not result["blocks_release"] else (
            "build" if result["comparable"] else "owner"),
        "evidence": result,
    }
