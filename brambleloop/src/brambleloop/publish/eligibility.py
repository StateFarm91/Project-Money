"""What an asset is made of, what it is for, and why those are different questions.

Requirements 57, 58, 65 and 69. Four gates before customer use; explicit classes separating
engineering evidence from conversion creative; exactly one commercial job per frame; and a
label distinguishing a render from a photograph wherever that distinction is material.

`gates.asset_truth.AssetClass` already says what an asset is *made of* — a twin render, a
photograph, an infographic, a pattern preview. #57 is asking a different question, and the
requirement's own sentence gives it away: *a technically correct chart cannot be promoted to
hero merely because it rendered successfully.* Rendering successfully is a fact about the
medium. Being the hero is a question about the purpose, and nothing in the system held one.

So purpose is a second axis, orthogonal to medium. A stitch chart is a `DIGITAL_TWIN_RENDER`
by medium and `ENGINEERING_EVIDENCE` by purpose, and the second is what decides where it may
appear. `ENGINEERING_EVIDENCE` can never be the hero — not because charts are ugly, but
because the hero's job is desire and instant comprehension and a chart is neither, and the
only reason a chart ever becomes a hero is that it was the asset that finished rendering.

**One job per frame, and duplicate jobs are the defect, not duplicate images (#65).** "Prevent
five technically different images from communicating essentially the same thing" is not about
pixels: five genuinely different charts all doing DETAIL is exactly the failure, and every
pixel-level check passes it. So the set is checked for job collision, and a frame whose job
nothing buys is removed rather than reordered.

**Four gates, and a gate that did not run has not passed (#58).** Each of DATA_TRUTH,
LAYOUT_QA, COMMERCIAL_QA and POLICY_PROVENANCE reports `passed`, `failed` or `not_run`, and
export requires all four to have *run and passed*. This build has met the alternative four
times in other costumes; the version here would be a listing exported because the commercial
check was never wired up and therefore raised nothing.

**A label is not a licence (#69).** The requirement says it plainly — *do not use a disclaimer
as permission to make a misleading hero* — and the implementation has to make that structural
rather than stated, because a disclaimer is the cheapest possible fix for a truthfulness
problem and it is always available. So the honesty label is computed from the medium rather
than chosen, it is required wherever the render/photograph distinction is material, and
`may_export` consults the truth gate's verdict *independently* of whether a label is present.
A labelled asset that fails DATA_TRUTH fails; there is no ordering in which the label helps.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..gates.asset_truth import AssetClass

# ---- what an asset is for (#57) -------------------------------------------

ENGINEERING_EVIDENCE = "ENGINEERING_EVIDENCE"
CUSTOMER_INFORMATION = "CUSTOMER_INFORMATION"
CONVERSION_CREATIVE = "CONVERSION_CREATIVE"
PHYSICAL_PROOF = "PHYSICAL_PROOF"

PURPOSES: dict[str, str] = {
    ENGINEERING_EVIDENCE: ("produced by the deterministic layer to prove the pattern is "
                           "correct. Truthful by construction and customer-facing by nobody's "
                           "decision"),
    CUSTOMER_INFORMATION: ("tells a buyer something they need in order to buy: size, "
                           "contents, materials, difficulty"),
    CONVERSION_CREATIVE: ("exists to make somebody want the thing, and is held to the truth "
                          "gates precisely because that is what it is for"),
    PHYSICAL_PROOF: ("a photograph of a finished object somebody actually made. The only "
                     "class that can settle what the thing really looks like"),
}

# Which medium can serve which purpose. A medium may serve several; what it may never do is
# claim one it cannot support -- an AI lifestyle concept is not physical proof whatever it is
# labelled, and that is the single most important row here.
MEDIUM_PURPOSES: dict[AssetClass, tuple[str, ...]] = {
    AssetClass.PHYSICAL_PRODUCT_PHOTO: (PHYSICAL_PROOF, CONVERSION_CREATIVE,
                                        CUSTOMER_INFORMATION),
    AssetClass.DIGITAL_TWIN_RENDER: (ENGINEERING_EVIDENCE, CUSTOMER_INFORMATION,
                                     CONVERSION_CREATIVE),
    AssetClass.AI_LIFESTYLE_CONCEPT: (CONVERSION_CREATIVE,),
    AssetClass.INFOGRAPHIC: (CUSTOMER_INFORMATION,),
    AssetClass.PATTERN_PREVIEW: (ENGINEERING_EVIDENCE, CUSTOMER_INFORMATION),
}

# ---- what a frame is for (#65) --------------------------------------------

DESIRE = "DESIRE"
SCALE = "SCALE"
DETAIL = "DETAIL"
CONTENTS = "CONTENTS"
DIFFICULTY = "DIFFICULTY"
MATERIALS = "MATERIALS"
SIZING = "SIZING"
PATTERN_PREVIEW = "PATTERN_PREVIEW"
PROOF = "PROOF"
CROSS_SELL = "CROSS_SELL"

JOBS: dict[str, str] = {
    DESIRE: "make somebody want it, at thumbnail scale, in under a second",
    SCALE: "how big the finished thing is, against something a person knows",
    DETAIL: "what the stitch and texture actually look like up close",
    CONTENTS: "what arrives when they pay",
    DIFFICULTY: "whether this buyer can make it",
    MATERIALS: "what they have to buy besides the pattern",
    SIZING: "which size variants exist and how they differ",
    PATTERN_PREVIEW: "what the document itself looks like to work from",
    PROOF: "that somebody has made this and it worked",
    CROSS_SELL: "what else in the shop goes with it",
}

# Which purposes can do which job. The hero row is the requirement's own example, encoded:
# engineering evidence cannot do DESIRE, so a chart cannot become the hero by rendering.
JOB_PURPOSES: dict[str, tuple[str, ...]] = {
    DESIRE: (CONVERSION_CREATIVE, PHYSICAL_PROOF),
    SCALE: (CUSTOMER_INFORMATION, PHYSICAL_PROOF, CONVERSION_CREATIVE),
    DETAIL: (PHYSICAL_PROOF, ENGINEERING_EVIDENCE, CONVERSION_CREATIVE),
    CONTENTS: (CUSTOMER_INFORMATION,),
    DIFFICULTY: (CUSTOMER_INFORMATION,),
    MATERIALS: (CUSTOMER_INFORMATION,),
    SIZING: (CUSTOMER_INFORMATION,),
    PATTERN_PREVIEW: (ENGINEERING_EVIDENCE, CUSTOMER_INFORMATION),
    PROOF: (PHYSICAL_PROOF,),
    CROSS_SELL: (CONVERSION_CREATIVE, CUSTOMER_INFORMATION),
}

# The hero is always frame one and its job is always DESIRE. Stated rather than derived so
# that a listing cannot be built with a hero whose job is DETAIL and pass every other check.
HERO_JOB = DESIRE

# ---- the four gates (#58) -------------------------------------------------

DATA_TRUTH = "DATA_TRUTH"
LAYOUT_QA = "LAYOUT_QA"
COMMERCIAL_QA = "COMMERCIAL_QA"
POLICY_PROVENANCE = "POLICY_PROVENANCE"

GATES: tuple[str, ...] = (DATA_TRUTH, LAYOUT_QA, COMMERCIAL_QA, POLICY_PROVENANCE)

GATE_MEANS: dict[str, str] = {
    DATA_TRUTH: "every value matches the CIR, the gauge and the compiled version",
    LAYOUT_QA: "nothing clips, overflows, overlaps or is too small to read",
    COMMERCIAL_QA: "the frame has one defined job and holds up at search-grid scale",
    POLICY_PROVENANCE: "asset type, disclosure and rights satisfy the current marketplace rules",
}

PASSED = "passed"
FAILED = "failed"
NOT_RUN = "not_run"


class EligibilityRefused(ValueError):
    """An asset claiming a purpose its medium cannot serve, or a gate nobody ran."""


# ---- the honesty label (#69) ----------------------------------------------

RENDER_LABEL = "Digital render of the pattern, not a photograph of a finished item"
PREVIEW_LABEL = "Preview of the pattern document"
CONCEPT_LABEL = "Illustrative concept image, AI-assisted; not a photograph of a finished item"
PHOTO_LABEL = ""      # a photograph needs no disclaimer; it is the thing itself

# Where the render/photograph distinction is material: any frame a buyer could reasonably
# read as evidence of what the finished object looks like. On a materials list it is not
# material, and labelling everything trains buyers to read nothing.
MATERIAL_JOBS: tuple[str, ...] = (DESIRE, DETAIL, PROOF, SCALE)

LABEL_FOR: dict[AssetClass, str] = {
    AssetClass.PHYSICAL_PRODUCT_PHOTO: PHOTO_LABEL,
    AssetClass.DIGITAL_TWIN_RENDER: RENDER_LABEL,
    AssetClass.AI_LIFESTYLE_CONCEPT: CONCEPT_LABEL,
    AssetClass.INFOGRAPHIC: "",
    AssetClass.PATTERN_PREVIEW: PREVIEW_LABEL,
}


def honesty_label(medium: AssetClass, job: str) -> dict:
    """The label this asset must carry, computed from the medium rather than chosen.

    Computed rather than supplied because a disclaimer is the cheapest available fix for a
    truthfulness problem, and one somebody writes is one somebody can write differently.
    """
    if job not in JOBS:
        raise EligibilityRefused(f"{job!r} is not a frame job: {sorted(JOBS)}")
    text = LABEL_FOR[medium]
    required = bool(text) and job in MATERIAL_JOBS
    return {
        "medium": medium.value, "job": job,
        "label": text, "required": required,
        "why": (f"a {medium.value} doing {job} could be read as evidence of what the "
                f"finished object looks like, so the distinction is material"
                if required else
                ("a photograph is the thing itself and needs no disclaimer"
                 if medium == AssetClass.PHYSICAL_PRODUCT_PHOTO else
                 f"the render/photograph distinction is not material for {job}, and "
                 f"labelling everything trains buyers to read nothing")),
        "not_a_licence": ("a label never turns a failing asset into a passing one. The truth "
                          "gate is consulted independently, and there is no ordering in "
                          "which the disclaimer helps"),
    }


# ---- an asset, with both axes ---------------------------------------------

@dataclass(frozen=True)
class Candidate:
    """One asset offered for a frame, with what it is made of and what it is for."""

    asset_id: str
    medium: AssetClass
    purpose: str
    job: str
    position: int

    def __post_init__(self) -> None:
        if self.purpose not in PURPOSES:
            raise EligibilityRefused(
                f"{self.asset_id}: {self.purpose!r} is not a purpose: {sorted(PURPOSES)}")
        if self.job not in JOBS:
            raise EligibilityRefused(
                f"{self.asset_id}: {self.job!r} is not a frame job: {sorted(JOBS)}. A frame "
                f"whose job nothing buys is removed rather than reordered")
        allowed = MEDIUM_PURPOSES[self.medium]
        if self.purpose not in allowed:
            raise EligibilityRefused(
                f"{self.asset_id}: a {self.medium.value} cannot serve {self.purpose}; it can "
                f"serve {list(allowed)}. An AI concept is not physical proof whatever it is "
                f"labelled, and a label is where that gets claimed")
        if self.position < 1:
            raise EligibilityRefused(f"{self.asset_id}: frame positions start at 1")

    @property
    def is_hero(self) -> bool:
        return self.position == 1


def may_serve(candidate: Candidate) -> dict:
    """Whether this asset's purpose can do this frame's job.

    The requirement's own example lives here: a technically correct chart is
    ENGINEERING_EVIDENCE, DESIRE does not accept it, and so rendering successfully cannot
    make it the hero.
    """
    allowed = JOB_PURPOSES[candidate.job]
    if candidate.purpose not in allowed:
        return {"may_serve": False, "asset_id": candidate.asset_id,
                "job": candidate.job, "purpose": candidate.purpose,
                "why": (f"{candidate.job} is served by {list(allowed)}, not by "
                        f"{candidate.purpose}. {JOBS[candidate.job]} -- and "
                        f"{PURPOSES[candidate.purpose]}")}
    if candidate.is_hero and candidate.job != HERO_JOB:
        return {"may_serve": False, "asset_id": candidate.asset_id,
                "job": candidate.job, "purpose": candidate.purpose,
                "why": (f"frame one is the hero and its job is {HERO_JOB}, not "
                        f"{candidate.job}. A listing whose first frame documents rather than "
                        f"sells has spent the only frame most shoppers see")}
    return {"may_serve": True, "asset_id": candidate.asset_id, "job": candidate.job,
            "purpose": candidate.purpose,
            "why": f"{candidate.purpose} can do {candidate.job}"}


# ---- the frame set (#65) --------------------------------------------------

def check_set(candidates: list[Candidate]) -> dict:
    """The whole listing set: one job each, no collisions, and a hero that sells.

    Job collision rather than image similarity is the check, because five genuinely different
    charts all doing DETAIL is the failure the requirement names and every pixel-level
    comparison passes it.
    """
    if not candidates:
        raise EligibilityRefused("a listing set with no frames is not a set")

    problems: list[dict] = []
    by_position: dict[int, list[Candidate]] = {}
    for c in candidates:
        by_position.setdefault(c.position, []).append(c)
    for position, rows in sorted(by_position.items()):
        if len(rows) > 1:
            problems.append({"kind": "position_collision", "position": position,
                             "why": f"{len(rows)} assets claim frame {position}"})

    jobs: dict[str, list[str]] = {}
    for c in candidates:
        jobs.setdefault(c.job, []).append(c.asset_id)
    for job, ids in sorted(jobs.items()):
        if len(ids) > 1:
            problems.append({
                "kind": "duplicate_job", "job": job, "assets": sorted(ids),
                "why": (f"{len(ids)} frames all do {job}. Five technically different images "
                        f"communicating the same thing is the defect, and no comparison of "
                        f"the images themselves would find it")})

    heroes = [c for c in candidates if c.is_hero]
    if not heroes:
        problems.append({"kind": "no_hero",
                         "why": "no frame in position one, which is the frame most shoppers "
                                "see and often the only one"})
    for c in candidates:
        verdict = may_serve(c)
        if not verdict["may_serve"]:
            problems.append({"kind": "job_purpose_mismatch", "asset": c.asset_id,
                             "why": verdict["why"]})

    return {
        "frames": len(candidates),
        "jobs_covered": sorted(jobs),
        "jobs_missing": sorted(set(JOBS) - set(jobs)),
        "problems": problems,
        "ok": not problems,
        "note": ("missing jobs are listed and not refused: a small listing does not need all "
                 "ten, and a shop that added a frame per uncovered job would be padding the "
                 "gallery to satisfy a checklist"),
    }


# ---- the four gates (#58) -------------------------------------------------

@dataclass(frozen=True)
class GateResult:
    """One gate's verdict, which is never simply a boolean."""

    gate: str
    outcome: str
    why: str = ""
    detail: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.gate not in GATES:
            raise EligibilityRefused(f"{self.gate!r} is not a promotion gate: {list(GATES)}")
        if self.outcome not in (PASSED, FAILED, NOT_RUN):
            raise EligibilityRefused(
                f"{self.outcome!r} is not an outcome: {[PASSED, FAILED, NOT_RUN]}. A boolean "
                f"here makes a gate that never ran indistinguishable from one that passed")
        if self.outcome == FAILED and not self.why.strip():
            raise EligibilityRefused(f"{self.gate} failed and did not say why")

    def to_dict(self) -> dict:
        return {"gate": self.gate, "means": GATE_MEANS[self.gate],
                "outcome": self.outcome, "why": self.why, "detail": dict(self.detail)}


def may_export(candidate: Candidate, results: list[GateResult], *,
               truth_verdict: str | None = None) -> dict:
    """Whether this asset may reach a customer. All four gates, all having run.

    `truth_verdict` is the independent reading from `gates.asset_truth`, consulted separately
    from the label, because #69's rule is that a disclaimer is never permission. There is no
    argument order in which a label makes a failing asset exportable.
    """
    by_gate = {r.gate: r for r in results}
    duplicated = sorted({r.gate for r in results
                         if sum(1 for o in results if o.gate == r.gate) > 1})
    if duplicated:
        raise EligibilityRefused(
            f"{candidate.asset_id}: {duplicated} reported twice. Two verdicts for one gate "
            f"means somebody chooses which to read")

    outcomes = {}
    for gate in GATES:
        result = by_gate.get(gate)
        outcomes[gate] = (result.to_dict() if result else
                          {"gate": gate, "means": GATE_MEANS[gate], "outcome": NOT_RUN,
                           "why": "no result was reported for this gate", "detail": {}})

    failed = [g for g in GATES if outcomes[g]["outcome"] == FAILED]
    unrun = [g for g in GATES if outcomes[g]["outcome"] == NOT_RUN]

    label = honesty_label(candidate.medium, candidate.job)
    serves = may_serve(candidate)

    blockers: list[str] = []
    if failed:
        blockers.append(f"failed: {', '.join(failed)}")
    if unrun:
        blockers.append(
            f"never ran: {', '.join(unrun)}. A gate that did not run has not passed, and a "
            f"listing exported because a check was never wired up is the commonest way an "
            f"unchecked asset reaches a customer")
    if not serves["may_serve"]:
        blockers.append(serves["why"])
    if label["required"] and not label["label"]:
        blockers.append("an honesty label is required here and none is defined for this medium")
    if truth_verdict == FAILED:
        blockers.append(
            "the asset truth gate refused this asset. The honesty label is consulted "
            "separately and does not change it: a disclaimer is not permission")

    return {
        "asset_id": candidate.asset_id,
        "may_export": not blockers,
        "gates": outcomes,
        "purpose": candidate.purpose, "medium": candidate.medium.value,
        "job": candidate.job, "position": candidate.position,
        "honesty_label": label,
        "blockers": blockers,
        "why": ("all four gates ran and passed, the purpose can do the job, and the honesty "
                "label is satisfied" if not blockers else "; ".join(blockers)),
    }


def state() -> dict:
    """The two axes, the ten jobs, the four gates, and what the label cannot do."""
    return {
        "requirements": [57, 58, 65, 69],
        "purposes": dict(PURPOSES),
        "jobs": dict(JOBS),
        "gates": dict(GATE_MEANS),
        "medium_purposes": {k.value: list(v) for k, v in MEDIUM_PURPOSES.items()},
        "hero_job": HERO_JOB,
        "material_jobs": list(MATERIAL_JOBS),
        "refuses": [
            "an asset claiming a purpose its medium cannot serve",
            "engineering evidence doing DESIRE, which is the chart-as-hero case by name",
            "a frame in position one whose job is not DESIRE",
            "two frames doing the same job, which no image comparison would find",
            "an export while any of the four gates has not run",
            "two verdicts for one gate, which lets somebody choose which to read",
        ],
        "note": ("AssetClass says what an asset is made of; purpose says what it is allowed "
                 "to do. A technically correct chart cannot be promoted to hero merely "
                 "because it rendered successfully -- rendering is a fact about the medium "
                 "and being the hero is a question about the purpose"),
        "label_is_not_a_licence": (
            "the honesty label is computed from the medium rather than chosen, and the truth "
            "gate is consulted independently of it. There is no ordering in which a "
            "disclaimer makes a misleading asset exportable"),
    }
