"""Confidence tracking (Master Plan section 3).

Section 3 asks for Arithmetic, Instruction, Chart, Gauge, Yardage, Visual and Physical
confidence to be tracked **separately**. That separation is the whole point. A single
"quality score" averages a thing we can prove with a thing we are guessing at, and the average
is more confident than the guess and less confident than the proof — which is exactly the
wrong answer in both directions.

Concretely, for the flagship today: arithmetic confidence is near-total, because a compiler
checked every row and an independent reverse compiler reconstructed the pattern from the
customer text alone. Yardage confidence is low, because nobody has crocheted it and the
estimate is a model with a stated tolerance. Averaging those into "87% confident" would let a
listing imply the yarn figure is as solid as the stitch counts. It is not, and the listing
says so, because this module keeps them apart.

Physical confidence starts at zero and can only be raised by a real sample. No amount of
computation moves it, by construction.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from ..cir.compiler import CompileResult
from ..cir.model import CIR
from ..cir.twin import TwinModel


class Dimension(str, Enum):
    ARITHMETIC = "arithmetic"
    INSTRUCTION = "instruction"
    CHART = "chart"
    GAUGE = "gauge"
    YARDAGE = "yardage"
    VISUAL = "visual"
    PHYSICAL = "physical"


# What each dimension means in one sentence, so a number is never shown without its meaning.
MEANINGS: dict[Dimension, str] = {
    Dimension.ARITHMETIC: "every row's stitch count was verified by the compiler",
    Dimension.INSTRUCTION: "an independent reverse compiler reconstructed the pattern from "
                           "the customer text alone and agreed",
    Dimension.CHART: "the chart is generated from the same compiled data as the words",
    Dimension.GAUGE: "the gauge is declared and the finished size follows from it",
    Dimension.YARDAGE: "yarn quantities are an uncalibrated model with a stated tolerance",
    Dimension.VISUAL: "imagery is rendered from the twin and checked by Asset Truth",
    Dimension.PHYSICAL: "a real person has crocheted this and measured the result",
}

# The ceiling each dimension can reach without physical evidence. Yardage and physical are
# capped hard: no amount of arithmetic tells you how much yarn a given maker's tension eats.
UNCALIBRATED_CEILING: dict[Dimension, float] = {
    Dimension.ARITHMETIC: 1.00,
    Dimension.INSTRUCTION: 1.00,
    Dimension.CHART: 1.00,
    Dimension.GAUGE: 0.85,
    Dimension.YARDAGE: 0.45,
    Dimension.VISUAL: 0.80,
    Dimension.PHYSICAL: 0.00,
}

# Below this, a claim resting on that dimension may not be stated without its caveat.
CLAIMABLE = 0.70


@dataclass
class ConfidenceProfile:
    scores: dict[Dimension, float] = field(default_factory=dict)
    notes: dict[Dimension, str] = field(default_factory=dict)

    def get(self, dim: Dimension) -> float:
        return self.scores.get(dim, 0.0)

    def claimable(self, dim: Dimension) -> bool:
        return self.get(dim) >= CLAIMABLE

    def weakest(self) -> tuple[Dimension, float]:
        dim = min(self.scores, key=lambda d: self.scores[d])
        return dim, self.scores[dim]

    def to_dict(self) -> dict:
        return {
            "scores": {d.value: round(v, 3) for d, v in self.scores.items()},
            "meanings": {d.value: MEANINGS[d] for d in self.scores},
            "notes": {d.value: n for d, n in self.notes.items()},
            "claimable": {d.value: self.claimable(d) for d in self.scores},
            "weakest": self.weakest()[0].value,
            # Deliberately absent: a single overall score. Section 3 asks for these to be
            # tracked separately, and an average would let a listing imply the yarn estimate
            # is as solid as the stitch counts.
        }


def assess(cir: CIR, result: CompileResult, twin: TwinModel | None, *,
           reverse_findings: list | None = None,
           asset_findings: list | None = None,
           physical_passed: bool | None = None) -> ConfidenceProfile:
    """Score each dimension from the evidence that actually exists for it.

    `twin` may be None, because the twin refuses to model a pattern that failed compilation.
    That case still has a confidence profile and it is an informative one: arithmetic zero,
    and everything downstream of the twin zero with it.
    """
    p = ConfidenceProfile()

    # Arithmetic: the compiler either proved every row or it did not.
    if result.ok:
        p.scores[Dimension.ARITHMETIC] = 1.0 if not result.warnings else 0.92
        p.notes[Dimension.ARITHMETIC] = (
            f"{len(result.rows)} rows compiled clean"
            + (f", {len(result.warnings)} warnings" if result.warnings else ""))
    else:
        p.scores[Dimension.ARITHMETIC] = 0.0
        p.notes[Dimension.ARITHMETIC] = f"{len(result.errors)} compile errors"

    # Instruction: did an independent parser agree with the source?
    findings = reverse_findings or []
    p.scores[Dimension.INSTRUCTION] = 1.0 if not findings else 0.0
    p.notes[Dimension.INSTRUCTION] = (
        "reverse compilation agreed on every row" if not findings
        else f"{len(findings)} reverse-compile disagreements")

    # Chart: generated from the same data, so it cannot disagree -- unless nothing rendered.
    has_cells = bool(twin and twin.cells)
    p.scores[Dimension.CHART] = 1.0 if has_cells else 0.0
    p.notes[Dimension.CHART] = ("generated from the compiled twin" if has_cells
                                else "no cells to chart")

    # Gauge: declared and internally consistent, but unverified against real fabric.
    if cir.gauge and twin and twin.width_cm and twin.height_cm:
        p.scores[Dimension.GAUGE] = UNCALIBRATED_CEILING[Dimension.GAUGE]
        p.notes[Dimension.GAUGE] = ("declared gauge, finished size computed from it; not "
                                    "verified against a worked swatch")
    else:
        p.scores[Dimension.GAUGE] = 0.2
        p.notes[Dimension.GAUGE] = ("no finished size can be claimed: "
                                    + ("the pattern does not compile" if twin is None
                                       else "no gauge declared"))

    # Yardage: a model. Capped low on purpose until a physical test calibrates it.
    if twin is None:
        p.scores[Dimension.YARDAGE] = 0.0
        p.notes[Dimension.YARDAGE] = "no twin: the pattern does not compile"
    elif twin.calibrated:
        p.scores[Dimension.YARDAGE] = 0.85
        p.notes[Dimension.YARDAGE] = "calibrated against a physically worked sample"
    else:
        p.scores[Dimension.YARDAGE] = UNCALIBRATED_CEILING[Dimension.YARDAGE]
        p.notes[Dimension.YARDAGE] = (
            f"uncalibrated estimate, +/-{twin.yardage_tolerance * 100:.0f}%; yarn use varies "
            f"with yarn, hook and tension and no sample has been worked")

    # Visual: rendered from the twin and checked, but still a render.
    errors = [f for f in (asset_findings or []) if getattr(f, "is_error", False)]
    if twin is None:
        p.scores[Dimension.VISUAL] = 0.0
        p.notes[Dimension.VISUAL] = "no twin: nothing can be rendered from this pattern"
    elif errors:
        p.scores[Dimension.VISUAL] = 0.0
        p.notes[Dimension.VISUAL] = f"{len(errors)} Asset Truth errors"
    else:
        p.scores[Dimension.VISUAL] = UNCALIBRATED_CEILING[Dimension.VISUAL]
        p.notes[Dimension.VISUAL] = ("rendered from the twin and cleared by Asset Truth; no "
                                     "photograph of a finished object exists")

    # Physical: only a real sample moves this, ever.
    if physical_passed is True:
        p.scores[Dimension.PHYSICAL] = 1.0
        p.notes[Dimension.PHYSICAL] = "a worked sample passed"
    elif physical_passed is False:
        p.scores[Dimension.PHYSICAL] = 0.0
        p.notes[Dimension.PHYSICAL] = "a worked sample failed"
    else:
        p.scores[Dimension.PHYSICAL] = 0.0
        p.notes[Dimension.PHYSICAL] = ("nobody has crocheted this. No amount of computation "
                                       "changes that.")
    return p


# Which confidence dimension each customer-facing claim actually rests on. A claim may not be
# stated plainly when the dimension underneath it is not claimable.
CLAIM_DEPENDENCIES: dict[str, Dimension] = {
    "stitch_counts": Dimension.ARITHMETIC,
    "row_instructions": Dimension.INSTRUCTION,
    "chart_matches_text": Dimension.CHART,
    "finished_size": Dimension.GAUGE,
    "yarn_required": Dimension.YARDAGE,
    "imagery_shows_the_pattern": Dimension.VISUAL,
    "fit": Dimension.PHYSICAL,
    "drape": Dimension.PHYSICAL,
}


def check_claims(profile: ConfidenceProfile, claims: list[str]) -> list[str]:
    """Refuse claims whose evidence is not there yet.

    This is where separate tracking earns its keep. "Every stitch count is verified" is
    supported; "uses 400 m of yarn" is not, and must carry its range and its caveat; "drapes
    beautifully" rests on physical confidence, which is zero, so it cannot be said at all.
    """
    problems: list[str] = []
    for claim in claims:
        dim = CLAIM_DEPENDENCIES.get(claim)
        if dim is None:
            problems.append(f"CONFIDENCE_UNKNOWN_CLAIM: {claim!r} maps to no evidence")
            continue
        if not profile.claimable(dim):
            problems.append(
                f"CONFIDENCE_TOO_LOW: {claim!r} rests on {dim.value} confidence "
                f"({profile.get(dim):.2f} < {CLAIMABLE}). {MEANINGS[dim]} — and that has not "
                f"happened. {profile.notes.get(dim, '')}")
    return problems
