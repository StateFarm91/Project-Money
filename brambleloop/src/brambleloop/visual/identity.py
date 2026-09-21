"""The canonical model system, built for an identity nobody has chosen yet.

Requirements 200, 201, 202, 203, 204. The owner will select one fictional model who becomes
Brambleloop's recurring face, and after that selection her identity is frozen: the company may
improve photography, posing, wardrobe and merchandising, and may not redesign her without
explicit approval.

Nothing has been selected. That is the fact this module is organised around, because the
tempting shortcut is to let the first generated face become canonical by being first — nobody
decides, the reference pack fills up with whatever was produced, and by the time anybody
notices, a hundred listings carry a woman nobody chose.

So there are two distinct states and no path between them that does not go through the owner:

- **candidates** — as many as generation produces, none of them canonical, none usable in a
  published asset.
- **canonical** — exactly one, frozen at selection, with a versioned reference pack.

`canonical()` returns `None` today and every function that would use it says so rather than
falling back to a candidate. The anti-drift evaluator reports `unavailable` for the same
reason: drift is measured against a reference pack, and there is no reference pack to measure
against. A drift check that passed because it had nothing to compare with would be worse than
no drift check, because it would be believed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

# What a reference pack has to pin (#200).
#
# The face half was here from the start. The body half was added on 2026-09-21 after the
# first reference-conditioned trial showed the failure mode the owner named: the face came
# back convincingly the same woman while the chest and upper-torso morphology changed
# substantially. That is not identity consistency, and it is worse than an obvious miss,
# because a familiar face is exactly what stops anybody looking further down the frame.
#
# It matters most for the thing this company sells. Garment fit cannot be compared across
# images if the body under the garment is changing: the fit reads as a property of the
# pattern when it is a property of whichever body the generator invented that time.
FACE_FIELDS: tuple[str, ...] = (
    "facial_geometry", "hair", "eyes", "age_band", "complexion", "representative_angles",
    "representative_expressions",
)

MORPHOLOGY_FIELDS: tuple[str, ...] = (
    "stature", "overall_build", "shoulder_proportions", "torso_length",
    "bust_proportions", "waist_proportions", "hip_proportions", "limb_proportions",
)

IDENTITY_FIELDS: tuple[str, ...] = FACE_FIELDS + MORPHOLOGY_FIELDS

CANDIDATE = "candidate"
CANONICAL = "canonical"
RETIRED = "retired"

# Drift dimensions (#201), in the two groups that are independent hard floors. A beautiful
# image of the wrong woman fails, and so does a correct face on a different body: a face
# match may never compensate for morphology drift, which is what a single blended score
# would quietly let it do.
FACE_DIMENSIONS: tuple[str, ...] = ("face", "hair", "eyes", "age", "stylisation")
MORPHOLOGY_DIMENSIONS: tuple[str, ...] = (
    "stature", "build", "shoulders", "torso", "bust", "waist", "hips", "limbs",
)
DRIFT_DIMENSIONS: tuple[str, ...] = FACE_DIMENSIONS + MORPHOLOGY_DIMENSIONS

# Which pack field each drift dimension is compared against.
DIMENSION_FIELD: dict[str, str] = {
    "face": "facial_geometry", "hair": "hair", "eyes": "eyes", "age": "age_band",
    "stylisation": "representative_expressions",
    "stature": "stature", "build": "overall_build", "shoulders": "shoulder_proportions",
    "torso": "torso_length", "bust": "bust_proportions", "waist": "waist_proportions",
    "hips": "hip_proportions", "limbs": "limb_proportions",
}

# The three answers a dimension may have. `UNMEASURABLE` exists because clothing, pose and
# perspective genuinely obscure anatomy, and the owner's rule is explicit: when a dimension
# cannot be defensibly evaluated it is marked unmeasurable and never automatically passed.
# Counting it as a match is how a loose cardigan silently certifies a different body.
MATCH = "match"
DRIFT = "drift"
UNMEASURABLE = "unmeasurable"

# How much of a group has to be readable before the group can be said to have been checked.
# Below this the frame is unverifiable rather than passing: two measurable dimensions out of
# eight is not a morphology check, it is a coincidence with a verdict attached.
MIN_MEASURABLE = {"face": 3, "morphology": 3}

# Dimensions that must be readable before a morphology group counts as checked at all, named
# by the owner on 2026-09-21: *chest/bust and torso continuity are explicit hard-floor
# dimensions*. Three readable dimensions out of eight clears `MIN_MEASURABLE`, and if the
# three are stature, shoulders and limbs then the exact failure this system was built for --
# a convincing face above a chest that changed -- is still unexamined. A count is not a
# substitute for looking at the thing that went wrong.
REQUIRED_MEASURABLE: dict[str, tuple[str, ...]] = {
    "face": (),
    "morphology": ("bust", "torso"),
}

# Products where a clean product-only hero outsells a modelled one (#204). Product truth and
# category fit outrank compulsory model presence, so this is a list of exceptions rather than
# a preference.
PRODUCT_FIRST_FORMS: frozenset[str] = frozenset({
    "blanket", "throw", "coaster", "placemat", "runner", "basket", "pillow", "wall_hanging",
    "ornament", "garland", "wreath", "toy",
})


class IdentityUnavailable(RuntimeError):
    """Something needs the canonical model and no model has been selected."""


class IdentityRefused(ValueError):
    """An attempt to change an identity that only the owner may change."""


@dataclass(frozen=True)
class ReferencePack:
    """The frozen description of the canonical model, versioned (#200)."""

    version: int
    fields: dict
    approved_by_owner_at: str

    def missing(self) -> list[str]:
        return [f for f in IDENTITY_FIELDS if not self.fields.get(f)]

    def complete(self) -> bool:
        return not self.missing()


@dataclass
class Candidate:
    """One generated face. Not canonical, and not usable in anything published."""

    key: str
    fields: dict = field(default_factory=dict)
    state: str = CANDIDATE
    note: str = ""

    def to_dict(self) -> dict:
        return {"key": self.key, "state": self.state,
                "described": sorted(k for k in self.fields if self.fields[k]),
                "note": self.note}


def canonical(packs: list[ReferencePack] | None = None) -> ReferencePack | None:
    """The selected model, or None.

    Returns None today. Every caller is expected to handle that rather than fall back to a
    candidate, because a candidate promoted by being first is an identity nobody chose.
    """
    approved = [p for p in (packs or []) if p.approved_by_owner_at]
    return max(approved, key=lambda p: p.version) if approved else None


def select(candidate: Candidate, *, owner_approved: bool,
           existing: ReferencePack | None = None) -> ReferencePack:
    """Freeze a candidate as canonical. Only the owner can do this, and only once.

    Replacing an existing canonical identity is a redesign, which #200 reserves to the owner
    explicitly — so it is refused here even when `owner_approved` is true, because "approved"
    on a selection call is not the same as approving a redesign.
    """
    if not owner_approved:
        raise IdentityRefused(
            f"{candidate.key} cannot become canonical without the owner's selection. A "
            f"candidate that becomes canonical by being first is an identity nobody chose, "
            f"and it is discovered a hundred listings later")
    if existing is not None:
        raise IdentityRefused(
            "a canonical identity already exists. Replacing her is a redesign, which needs "
            "explicit owner approval as a separate decision rather than as a side effect of "
            "a selection call (#200)")
    missing = [f for f in IDENTITY_FIELDS if not candidate.fields.get(f)]
    if missing:
        raise IdentityRefused(
            f"the reference pack would be incomplete: {missing}. An unpinned field is a field "
            f"that drifts, and drift is what the pack exists to prevent")
    return ReferencePack(version=1, fields=dict(candidate.fields),
                         approved_by_owner_at=datetime.now(timezone.utc).isoformat())


VERDICTS: frozenset[str] = frozenset({MATCH, DRIFT, UNMEASURABLE})


def _classify(want, got) -> str:
    """One dimension's answer, three-valued.

    `got` is either a direct verdict -- `match`, `drift` or `unmeasurable`, from a judge
    that was shown both photographs -- or a description to compare against the pack.

    The direct verdict is the path that works. The first live tournament compared two
    free-text descriptions by exact string equality and reported every dimension of every
    scene of every finalist as drift, which is what that comparison always does: two honest
    descriptions of the same woman are never byte-identical. "Warm mid-brown, shoulder
    length" and "mid-brown, falls to the shoulders" are the same hair and a failed string
    match. A check that cannot return `match` is as useless as one that cannot return
    `drift`, and it is more dangerous, because it looks strict.

    The string path is kept for a pack field compared against a literal, which is what the
    tests exercise and what a hand-recorded observation would produce.
    """
    if isinstance(got, str) and got.strip().lower() in VERDICTS:
        return got.strip().lower()
    if want is None:
        # The pack never pinned it, so nothing can be compared. Unmeasurable, not a match:
        # an unpinned field is exactly the field that drifts.
        return UNMEASURABLE
    if got is None or str(got).strip().lower() in ("", "unmeasurable", "unclear", "unknown",
                                                   "obscured", "not visible"):
        return UNMEASURABLE
    return MATCH if str(want).strip().lower() == str(got).strip().lower() else DRIFT


def _group_verdict(scored: dict, dimensions: tuple[str, ...], floor: int,
                   required: tuple[str, ...] = ()) -> dict:
    drifted = [d for d in dimensions if scored.get(d) == DRIFT]
    measurable = [d for d in dimensions if scored.get(d) in (MATCH, DRIFT)]
    unmeasurable = [d for d in dimensions if scored.get(d) == UNMEASURABLE]
    required_missing = [d for d in required if d not in measurable]
    if drifted:
        verdict = "fail"
    elif len(measurable) < floor or required_missing:
        verdict = "unverifiable"
    else:
        verdict = "pass"
    return {"verdict": verdict, "drifted": drifted, "measurable": measurable,
            "unmeasurable": unmeasurable, "floor": floor,
            "required": list(required), "required_unreadable": required_missing}


def drift_check(observed: dict, pack: ReferencePack | None,
                *, tolerance: float = 0.15) -> dict:
    """Compare an asset's rendered identity against the canonical reference (#201).

    Two independent hard floors, face and whole-person morphology, because a single blended
    verdict lets a convincing face carry a different body -- which is the exact failure the
    first reference-conditioned trial produced, and the one that makes garment fit
    uninterpretable. Either group failing fails the frame; neither can compensate for the
    other, and there is no average in which they could.

    Garment- and pose-aware by construction: a dimension the photograph does not show is
    `unmeasurable` rather than a match. A group with too little readable is `unverifiable`
    rather than passing, because a morphology check that could read two dimensions out of
    eight has not checked morphology.

    With no pack the verdict is `unavailable`, never `pass`. A drift check that passed
    because it had nothing to compare against would be worse than no check at all, because
    it would be believed.
    """
    if pack is None:
        return {
            "verdict": "unavailable",
            "reason": ("no canonical model has been selected, so there is no reference pack "
                       "to measure drift against. This is not a pass"),
            "blocks_release": True,
            "dimensions": {}, "face": {}, "morphology": {},
        }

    scored = {d: _classify(pack.fields.get(DIMENSION_FIELD[d]), observed.get(d))
              for d in DRIFT_DIMENSIONS}
    face = _group_verdict(scored, FACE_DIMENSIONS, MIN_MEASURABLE["face"],
                          REQUIRED_MEASURABLE["face"])
    morphology = _group_verdict(scored, MORPHOLOGY_DIMENSIONS, MIN_MEASURABLE["morphology"],
                                REQUIRED_MEASURABLE["morphology"])

    failed = face["drifted"] + morphology["drifted"]
    groups_ok = face["verdict"] == "pass" and morphology["verdict"] == "pass"
    verdict = "pass" if groups_ok else ("fail" if failed else "unverifiable")

    reasons = []
    if face["drifted"]:
        reasons.append(f"face identity drifted on {face['drifted']}: a beautiful image of "
                       f"the wrong woman fails (#201)")
    if morphology["drifted"]:
        reasons.append(
            f"whole-person morphology drifted on {morphology['drifted']} -- a face match "
            f"does not compensate, and garment fit cannot be compared across images if the "
            f"body under the garment is changing")
    if not failed and face["verdict"] == "unverifiable":
        reasons.append(f"only {len(face['measurable'])} face dimensions were readable, "
                       f"below the floor of {face['floor']}")
    if not failed and morphology["verdict"] == "unverifiable":
        if morphology["required_unreadable"]:
            reasons.append(
                f"{morphology['required_unreadable']} could not be read, and chest/bust and "
                f"torso continuity are hard-floor dimensions rather than two of eight to be "
                f"counted in with the rest. Unmeasurable is not a pass")
        else:
            reasons.append(f"only {len(morphology['measurable'])} morphology dimensions "
                           f"were readable, below the floor of {morphology['floor']}. "
                           f"Unmeasurable is not a pass")

    return {
        "verdict": verdict,
        "dimensions": scored,
        "face": face,
        "morphology": morphology,
        "failed": failed,
        "blocks_release": verdict != "pass",
        "reason": "; ".join(reasons),
        "floors_are_independent": (
            "face identity and whole-person morphology are separate hard floors. Neither "
            "averages into the other, because a blended score is precisely how a familiar "
            "face waves a different body through"),
    }


def shot_plan(*, product_form: str, has_model: bool = True) -> dict:
    """The gallery a product deserves (#203, #204, #80).

    Two rules shape it. Model presence is not compulsory: for a blanket, a clean product-only
    hero outsells a modelled one, and product truth outranks brand recognition. And the plan
    is a list of *jobs* rather than a target count — #80 asks for minimum quality, not minimum
    count, so every frame here has a commercial job it must do or be dropped.
    """
    product_first = product_form in PRODUCT_FIRST_FORMS
    frames = [
        {"role": "hero", "job": "create desire and comprehension in one frame at grid size",
         "model": not product_first and has_model},
        {"role": "detail", "job": "prove the texture and stitch definition are real",
         "model": False},
        {"role": "scale", "job": "answer 'how big is it' without a stated dimension",
         "model": not product_first and has_model},
        {"role": "construction", "job": "show how it goes together where that is the risk",
         "model": False},
        {"role": "evidence", "job": "substantiate size, materials, files and chart quality",
         "model": False},
    ]
    if not product_first and has_model:
        frames.insert(1, {"role": "fit", "job": "show the garment on a body, truthfully",
                          "model": True})
    return {
        "product_form": product_form,
        "product_first": product_first,
        "frames": frames,
        "model_frames": sum(1 for f in frames if f["model"]),
        "note": ("A clean product-only hero is commercially stronger for this form, so the "
                 "model is not forced into it: product truth and category fit outrank "
                 "compulsory model presence (#204)."
                 if product_first else
                 "A modelled hero earns its place on this form, and every frame still has a "
                 "job it must do (#80)."),
    }


def status(packs: list[ReferencePack] | None = None,
           candidates: list[Candidate] | None = None) -> dict:
    pack = canonical(packs)
    return {
        "canonical_selected": pack is not None,
        "version": pack.version if pack else None,
        "candidates": [c.to_dict() for c in (candidates or [])],
        "identity_fields_required": list(IDENTITY_FIELDS),
        "drift_check": "operative" if pack else "unavailable — no reference pack",
        "note": ("Nothing has been selected, and nothing will select itself. A candidate that "
                 "became canonical by being first is an identity nobody chose, discovered a "
                 "hundred listings later."
                 if pack is None else
                 "The canonical identity is frozen; improving photography, posing and "
                 "wardrobe is allowed, redesigning her is the owner's decision."),
    }
