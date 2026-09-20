"""The flow from truth to creative, and the one direction creative may not go.

Requirement 63. The required flow is named in the requirement itself: CIR, compiled twin
truth, engineering evidence, a creative brief constrained by that truth, conversion creative,
an independent Asset Truth comparison, the layout, commercial and policy gates, and then
listing export. And the sentence that makes it a requirement rather than a diagram:
*creative systems may improve presentation but may never invent motifs, dimensions, texture,
construction or included deliverables.*

The CIR-to-evidence half was already built. What was missing is the constraint in the middle,
and it has a shape worth stating precisely.

**Creative may select from truth; it may never extend it.** That asymmetry is the whole rule.
A hero image showing three of the seven stitch types is fine -- it is a photograph of part of
a thing, and no listing shows everything. A hero image showing an eighth is not a
presentation choice, it is a claim about a pattern that does not contain it, and the buyer
who counts on it has been told something untrue by an image nobody thought of as a statement.
So the brief carries the sets the twin established, and the check is *subset*, in one
direction, on every one of the five categories the requirement names.

**A brief written after the creative describes it rather than constraining it.** The flow is
ordered and the order is load-bearing: a creative brief produced once the conversion creative
exists is a caption. So stages advance one at a time, a skip is refused, and the brief
records that it was derived from the evidence rather than from the artwork. The same shape as
a forecast dated after its period, and it arrives here for the same reason -- because the
convenient order is the wrong one and nothing else notices.

**The Asset Truth comparison is independent or it is decoration.** The requirement says
independent and means it: the actor that produced the creative cannot be the actor that
signs off whether it matches the twin. This is `improve.roles`' separation of proposing from
judging, applied to pictures.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# The flow, in the requirement's own order. Closed and ordered: both properties are the point.
CIR = "cir"
TWIN = "compiled_twin_truth"
EVIDENCE = "engineering_evidence"
BRIEF = "creative_brief"
CREATIVE = "conversion_creative"
ASSET_TRUTH = "independent_asset_truth"
GATES = "layout_commercial_policy_gates"
EXPORT = "listing_export"

FLOW: tuple[str, ...] = (CIR, TWIN, EVIDENCE, BRIEF, CREATIVE, ASSET_TRUTH, GATES, EXPORT)

STAGE_MEANS: dict[str, str] = {
    CIR: "the formal pattern, which is where everything true about the product starts",
    TWIN: "what the compiler and the twin agree the pattern produces",
    EVIDENCE: "charts and renders generated from that agreement, truthful by construction",
    BRIEF: "what creative is allowed to work with, derived from the evidence",
    CREATIVE: "the images made to sell it, constrained by the brief",
    ASSET_TRUTH: "a comparison against the twin, by somebody who did not make the creative",
    GATES: "layout, commercial and policy, per requirement 58",
    EXPORT: "the listing a buyer sees",
}

# The five things creative may never invent. The requirement lists them; the vocabulary is
# closed so that "style" cannot be used to smuggle a sixth.
MOTIFS = "motifs"
DIMENSIONS = "dimensions"
TEXTURE = "texture"
CONSTRUCTION = "construction"
DELIVERABLES = "included_deliverables"

CONSTRAINED: tuple[str, ...] = (MOTIFS, DIMENSIONS, TEXTURE, CONSTRUCTION, DELIVERABLES)

CONSTRAINT_MEANS: dict[str, str] = {
    MOTIFS: "what is depicted -- a leaf the pattern does not make is a leaf nobody gets",
    DIMENSIONS: "how big it is, which the geometry object alone decides",
    TEXTURE: "what the fabric does, which follows from the stitches",
    CONSTRUCTION: "how it is built -- seamed, worked in the round, joined as you go",
    DELIVERABLES: "what arrives when they pay",
}


class BriefRefused(ValueError):
    """Creative that invented something, a stage out of order, or a sign-off by its author."""


@dataclass(frozen=True)
class Brief:
    """What creative may work with, derived from the evidence rather than from the artwork."""

    product_slug: str
    version: str
    derived_from: str                        # the evidence artefact this came from
    allows: dict[str, tuple[str, ...]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.derived_from.strip():
            raise BriefRefused(
                f"{self.product_slug}: a brief names the evidence it was derived from. One "
                f"that does not is a caption for creative that already exists, and a brief "
                f"written after the artwork describes it rather than constraining it")
        unknown = sorted(set(self.allows) - set(CONSTRAINED))
        if unknown:
            raise BriefRefused(
                f"{self.product_slug}: {unknown} are not constrained categories: "
                f"{list(CONSTRAINED)}. The list is closed so that 'style' cannot be used to "
                f"smuggle a sixth")
        missing = sorted(set(CONSTRAINED) - set(self.allows))
        if missing:
            raise BriefRefused(
                f"{self.product_slug}: {missing} have no entry. A category the brief is "
                f"silent about is a category creative may fill in, which is the opposite of "
                f"a constraint")

    def to_dict(self) -> dict:
        return {"product_slug": self.product_slug, "version": self.version,
                "derived_from": self.derived_from,
                "allows": {k: list(v) for k, v in sorted(self.allows.items())},
                "means": dict(CONSTRAINT_MEANS)}


def brief_from_truth(*, product_slug: str, version: str, evidence_ref: str,
                     motifs: tuple[str, ...], dimensions: tuple[str, ...],
                     texture: tuple[str, ...], construction: tuple[str, ...],
                     deliverables: tuple[str, ...]) -> Brief:
    """Build a brief from what the twin established. Nothing else may add to it."""
    return Brief(product_slug=product_slug, version=version, derived_from=evidence_ref,
                 allows={MOTIFS: tuple(motifs), DIMENSIONS: tuple(dimensions),
                         TEXTURE: tuple(texture), CONSTRUCTION: tuple(construction),
                         DELIVERABLES: tuple(deliverables)})


def check_creative(brief: Brief, produced: dict[str, tuple[str, ...]]) -> dict:
    """Whether the creative stayed inside the brief. Subset in one direction only.

    Showing less than the truth is a composition choice and is allowed: no listing shows
    everything, and a hero depicting three of seven stitch types is a photograph of part of a
    thing. Showing more is not a presentation improvement -- it is a claim about a pattern
    that does not contain it.
    """
    unknown = sorted(set(produced) - set(CONSTRAINED))
    if unknown:
        raise BriefRefused(
            f"{brief.product_slug}: {unknown} are not constrained categories: "
            f"{list(CONSTRAINED)}")

    invented: list[dict] = []
    omitted: dict[str, list[str]] = {}
    for category in CONSTRAINED:
        allowed = set(brief.allows.get(category, ()))
        shown = set(produced.get(category, ()))
        extra = sorted(shown - allowed)
        if extra:
            invented.append({
                "category": category, "invented": extra,
                "why": (f"{extra} appear in the creative and not in the truth. "
                        f"{CONSTRAINT_MEANS[category]}. Presentation may select from what is "
                        f"there; it may not add to it")})
        left_out = sorted(allowed - shown)
        if left_out:
            omitted[category] = left_out

    return {
        "product_slug": brief.product_slug,
        "ok": not invented,
        "invented": invented,
        "omitted": omitted,
        "why": ("the creative is a subset of the truth in every constrained category"
                if not invented else
                f"invented in {len(invented)} categor{'y' if len(invented) == 1 else 'ies'}"),
        "omission_is_allowed": (
            "showing less than the truth is a composition choice: no listing shows "
            "everything, and a hero depicting three of seven stitch types is a photograph of "
            "part of a thing rather than a lie about the whole"),
    }


# ---- the order is load-bearing --------------------------------------------

def advance(current: str, to: str) -> dict:
    """Move one stage, refusing a skip and refusing to go backwards silently."""
    if current not in FLOW:
        raise BriefRefused(f"{current!r} is not a stage: {list(FLOW)}")
    if to not in FLOW:
        raise BriefRefused(f"{to!r} is not a stage: {list(FLOW)}")
    here, there = FLOW.index(current), FLOW.index(to)
    if there == here + 1:
        return {"advanced": True, "from": current, "to": to,
                "why": f"{STAGE_MEANS[to]}"}
    if there <= here:
        return {"advanced": False, "from": current, "to": to,
                "why": (f"{to} is not after {current}. Going back is a real thing to do -- a "
                        f"defect found at the gates sends work back to the brief -- but it "
                        f"restarts the flow rather than continuing it, and the difference "
                        f"matters because the evidence downstream is now about an older "
                        f"version")}
    skipped = list(FLOW[here + 1:there])
    return {"advanced": False, "from": current, "to": to, "skipped": skipped,
            "why": (f"{skipped} would be skipped. The order is the requirement: a creative "
                    f"brief produced once the conversion creative exists is a caption, and "
                    f"an asset-truth comparison run before the creative exists has compared "
                    f"nothing")}


def check_independence(*, produced_by: str, compared_by: str) -> dict:
    """The Asset Truth comparison is independent or it is decoration."""
    if not produced_by.strip() or not compared_by.strip():
        raise BriefRefused(
            "both the maker of the creative and the checker of it are named, or independence "
            "cannot be established either way")
    if produced_by == compared_by:
        return {"independent": False, "produced_by": produced_by,
                "why": (f"{produced_by} made the creative and signed off whether it matches "
                        f"the twin. The requirement says independent and means it: the "
                        f"author of a picture has been thinking about what it does well, "
                        f"which is the same failure the challenger league refuses when a "
                        f"configuration brings its own tasks")}
    return {"independent": True, "produced_by": produced_by, "compared_by": compared_by,
            "why": "the comparison was made by somebody who did not make the creative"}


def state() -> dict:
    """The flow, the five things creative may not invent, and the one-way rule."""
    return {
        "requirement": 63,
        "flow": [{"stage": s, "means": STAGE_MEANS[s]} for s in FLOW],
        "constrained": dict(CONSTRAINT_MEANS),
        "refuses": [
            "creative naming a motif, dimension, texture, construction or deliverable the "
            "truth does not contain",
            "a brief that does not name the evidence it was derived from",
            "a brief silent about a constrained category, which creative may then fill in",
            "a stage skipped in the flow",
            "an asset-truth comparison signed off by whoever made the creative",
        ],
        "one_way_rule": (
            "creative may select from truth and may never extend it. Showing less is a "
            "composition choice; showing more is a claim about a pattern that does not "
            "contain it, made by an image nobody thought of as a statement"),
    }
