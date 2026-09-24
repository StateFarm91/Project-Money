"""The standard a Brambleloop listing image must meet, written before anything can meet it.

Set by the owner on 2026-09-24, and recorded here rather than in prose because a standard
that lives in a document is a standard somebody re-reads charitably when a result is nearly
good enough. Written before the photographic bridge exists, so it cannot be shaped by what
that bridge turns out to be able to do -- the same reason `visual.reliability` was written
before the first render rate was measured.

**The deterministic pipeline is not the aesthetic.** It exists to make Product Truth
constructible rather than hoped for. It is an internal authoritative layer, and a customer
must never be able to tell it is there. The reaction a finished listing image has to produce
is "that is a beautiful photograph of a real person wearing a real crochet product" -- not
render, not CGI, not AI, not composite, not fake crochet.

**Three floors, independent, and none may pay for another.** This is the part that gets
eroded first, because two passes and a near-miss always feels like progress. It is not:

    product truth PASS + identity PASS + realism FAIL  ->  FAIL
    product truth PASS + realism PASS + identity FAIL  ->  FAIL
    identity PASS + realism PASS + product truth FAIL  ->  FAIL

**Identity is itself two floors, not one.** A matching face on a different body fails. A
matching body with a different face fails. They are checked separately and neither averages
into the other, because the failure mode of a generative model asked for a specific person is
a beautiful, plausible, subtly different one -- and a system that scored face and body
together would let a good face carry a wrong body over the line.

**UNMEASURABLE is never PASS.** A floor nobody could evaluate is a floor that did not hold.
This is the single rule that has caught the most defects in this codebase and it is restated
here because an image pipeline offers more ways to lose an answer than anything else does.

**A technique that alters the certified product is rejected, not accommodated.** If a
photographic stage makes the picture better and changes the crochet, the asset fails and the
technique is the thing that has to change. The product is constructed; it is not a suggestion
to a renderer.
"""
from __future__ import annotations

from dataclasses import dataclass, field

STANDARD_SET_AT = "2026-09-24"

PASS, FAIL, UNMEASURABLE = "pass", "fail", "unmeasurable"

# The three floors. Named rather than numbered so a log line says which one fell.
PRODUCT_TRUTH = "product_truth"
MODEL_IDENTITY = "model_identity"
PHOTOGRAPHIC_REALISM = "photographic_realism"
FLOORS = (PRODUCT_TRUTH, MODEL_IDENTITY, PHOTOGRAPHIC_REALISM)

# Identity's two halves, checked independently and never averaged.
IDENTITY_FACE = "face"
IDENTITY_MORPHOLOGY = "morphology"
IDENTITY_HALVES = (IDENTITY_FACE, IDENTITY_MORPHOLOGY)

# What morphology means, so "the body matches" is a set of answerable questions rather than an
# impression. Taken from the owner's list; stature through limbs are whole-person properties a
# portrait cannot answer, which is why a portrait-only check can never clear this floor.
MORPHOLOGY_DIMENSIONS = (
    "stature", "shoulders", "torso", "bust", "waist", "hips", "limbs", "overall_build",
)

FACE_DIMENSIONS = ("face", "eyes", "hair", "age")

# What a photograph has to have. Absence of a defect is not presence of realism, so these are
# stated as things that must be there rather than as things that must not.
REALISM_REQUIRES = (
    "skin_has_texture_and_pores",
    "hair_is_believable",
    "hands_and_fingers_are_anatomically_correct",
    "eyes_are_realistic",
    "fabric_folds_naturally",
    "crochet_drape_is_physically_plausible",
    "garment_contacts_the_body_coherently",
    "occlusion_is_correct",
    "gravity_is_plausible",
    "shadows_are_coherent",
    "lighting_is_realistic",
    "depth_of_field_is_believable",
    "has_ordinary_photographic_imperfection",
    "camera_characteristics_are_consistent",
    "environment_is_a_believable_real_place",
)

# And what disqualifies it however well it scores elsewhere.
REALISM_REJECTS = (
    "plastic_skin",
    "beauty_filter_appearance",
    "impossible_hands",
    "floating_garment",
    "garment_body_intersection",
    "melted_yarn",
    "synthetic_stitch_texture",
    "impossible_shadows",
    "excessive_hdr",
    "generic_ai_interior",
    "fake_typography_or_logos",
    "catalogue_perfect_sterility",
)


class StandardViolation(AssertionError):
    """Raised when something tries to ship an asset this standard does not clear."""


@dataclass
class FloorResult:
    floor: str
    verdict: str                       # pass | fail | unmeasurable
    why: str = ""
    failed_checks: tuple[str, ...] = ()
    unjudged_checks: tuple[str, ...] = ()

    @property
    def clears(self) -> bool:
        return self.verdict == PASS


@dataclass
class AssetVerdict:
    """Whether one candidate listing image may ship. Nothing here is advisory."""

    asset_ref: str = ""
    floors: dict[str, FloorResult] = field(default_factory=dict)
    identity_halves: dict[str, FloorResult] = field(default_factory=dict)

    @property
    def ships(self) -> bool:
        """Every floor passes, and identity passes in both halves. No exceptions."""
        if set(self.floors) != set(FLOORS):
            return False
        if not all(f.clears for f in self.floors.values()):
            return False
        if set(self.identity_halves) != set(IDENTITY_HALVES):
            return False
        return all(h.clears for h in self.identity_halves.values())

    @property
    def blocked_by(self) -> tuple[str, ...]:
        out = [name for name, f in sorted(self.floors.items()) if not f.clears]
        out += [f"{MODEL_IDENTITY}.{n}" for n, h in sorted(self.identity_halves.items())
                if not h.clears]
        missing = [n for n in FLOORS if n not in self.floors]
        out += [f"{n} (never evaluated)" for n in missing]
        missing_halves = [n for n in IDENTITY_HALVES if n not in self.identity_halves]
        out += [f"{MODEL_IDENTITY}.{n} (never evaluated)" for n in missing_halves]
        return tuple(sorted(set(out)))

    @property
    def why(self) -> str:
        if self.ships:
            return ("all three floors pass independently, with identity clearing face and "
                    "morphology separately")
        return ("blocked by " + ", ".join(self.blocked_by) +
                ". The floors do not compensate for one another: two passes and a failure "
                "is a failure")

    def to_dict(self) -> dict:
        return {
            "asset": self.asset_ref, "ships": self.ships, "why": self.why,
            "blocked_by": list(self.blocked_by),
            "standard_set_at": STANDARD_SET_AT,
            "floors": {n: {"verdict": f.verdict, "why": f.why,
                           "failed": list(f.failed_checks),
                           "unjudged": list(f.unjudged_checks)}
                       for n, f in sorted(self.floors.items())},
            "identity": {n: {"verdict": h.verdict, "why": h.why,
                             "failed": list(h.failed_checks),
                             "unjudged": list(h.unjudged_checks)}
                         for n, h in sorted(self.identity_halves.items())},
        }


def judge_floor(floor: str, *, failed: tuple[str, ...], unjudged: tuple[str, ...],
                asked: tuple[str, ...]) -> FloorResult:
    """One floor's verdict from its checks. Absence of an answer is never an answer.

    Order matters and is deliberate. A check that failed is a failure even if others could
    not be judged -- a known defect is not excused by an unknown. Only when nothing failed
    does an unjudged check make the floor `unmeasurable`, which blocks exactly as a failure
    does but says something different about what to do next: one needs a fix, the other needs
    a measurement.
    """
    if not asked:
        return FloorResult(floor, UNMEASURABLE,
                           "no check was asked, so this floor was never put to the question")
    if failed:
        return FloorResult(floor, FAIL, f"{list(failed)} failed", tuple(failed),
                           tuple(unjudged))
    if unjudged:
        return FloorResult(floor, UNMEASURABLE,
                           f"{list(unjudged)} could not be judged, and a floor nobody could "
                           f"evaluate is a floor that did not hold",
                           (), tuple(unjudged))
    return FloorResult(floor, PASS, f"all {len(asked)} checks passed")


def refuse_unless_it_ships(verdict: AssetVerdict) -> None:
    """The gate itself. Call before anything publishes, exports or presents an asset."""
    if not verdict.ships:
        raise StandardViolation(
            f"{verdict.asset_ref or 'asset'} does not meet the Brambleloop listing standard: "
            f"{verdict.why}")


def product_lock_held(before: dict, after: dict) -> FloorResult:
    """Did the photographic stage leave the certified product alone?

    `before` and `after` are the structural measurements of the product region -- texture
    signature, geometry, counts -- taken from the deterministic asset and then from the
    presented one. The presentation layer may light it, pose it, shade it and place it in a
    room; it may not change what it is.

    Compared field by field rather than scored, because "mostly the same garment" is not a
    thing a certified pattern can promise. Anything that moved is named.
    """
    if not before or not after:
        return FloorResult(PRODUCT_TRUTH, UNMEASURABLE,
                           "the product region was not measured on both sides of the "
                           "presentation stage, so whether it survived is unknown")
    drifted = tuple(sorted(k for k in before if before[k] != after.get(k)))
    if drifted:
        return FloorResult(PRODUCT_TRUTH, FAIL,
                           f"the presentation stage changed {list(drifted)}. An asset that "
                           f"looks better and shows a different garment is a failure, and "
                           f"the technique is what has to change",
                           drifted)
    return FloorResult(PRODUCT_TRUTH, PASS,
                       f"every measured structural property survived presentation unchanged "
                       f"({len(before)} compared)")
