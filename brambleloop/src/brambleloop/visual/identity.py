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
    # Named because the catalogue has them and they were being labelled by their
    # construction instead: a graphghan is a blanket with a picture on it, and a snuggle
    # mat is a mat. The verdict was already right -- an unclassified form is photographed
    # as an object -- but a frame captioned `flat_rows` is a frame nobody can shot-plan.
    "graphghan", "afghan", "mat", "motif",
})

# Forms a buyer genuinely cannot judge without a body on the other side of the fabric:
# how it sits, where it ends, whether it fits. These are the *only* forms the model gate
# applies to, and the list is an allowlist rather than the complement of the one above.
#
# The complement was the bug. `form_of` falls back to the CIR's *construction* when the
# slug carries no form word, so `winter-village-graphghan` -- a blanket -- reported its
# form as `flat_rows`, which is not in `PRODUCT_FIRST_FORMS`, so it was classed as needing
# the model. Four catalogue products were, including a pet snuggle mat and a wall hanging.
# A construction is not a form, and "not on the product-first list" is not the same claim
# as "somebody has to wear it".
#
# The default therefore has to be the other way round. #74 says the model gate applies only
# where human modelling materially *helps* the buyer, which makes her the exception rather
# than the fallback: a form nobody has classified is photographed as an object, and the
# cost of being wrong is a flat photograph of a scarf rather than a woman draped in a
# blanket and a render nobody should have paid for.
WORN_FORMS: frozenset[str] = frozenset({
    "garment", "cardigan", "sweater", "jumper", "shawl", "wrap", "poncho", "scarf",
    "cowl", "snood", "hat", "beanie", "bonnet", "headband", "earwarmer", "mitten",
    "glove", "sock", "slipper", "bag", "tote", "dress", "top", "vest",
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


# What an owner decision to replace the canonical identity has to look like (#200).
#
# The same shape as `freeze.OWNER_APPROVAL`, because a replacement is an approval of the
# same weight as the original and must be recorded the same way: as code, quoting the owner,
# not as a flag on a call. `supersedes_version` has to name the version being retired so a
# stale approval cannot be replayed against a later identity, and `scope` says which of the
# two things the owner is deciding -- repairing the photograph of the woman they chose, or
# choosing a different woman. Those are different decisions and the record says which.
# `approved_by` is required and audited exactly as given (certification C-26): an unsigned
# record must not be attributed to the owner by a default.
REDESIGN_APPROVAL_KEYS: tuple[str, ...] = ("at", "decision", "supersedes_version", "scope",
                                           "approved_by")
REDESIGN_SCOPES: frozenset[str] = frozenset({"portrait_repair", "redesign"})


def validate_redesign_approval(record: dict | None, *, existing: ReferencePack) -> dict:
    """The owner's replacement decision, or `IdentityRefused` saying exactly what is missing.

    Nothing here is inferred. A record with the right keys and the wrong version is refused
    rather than corrected, because an approval that applies to whichever version happens
    to be current is an approval of nothing in particular.
    """
    if not isinstance(record, dict) or not record:
        raise IdentityRefused(
            "a canonical identity already exists. Replacing her is a redesign, which needs "
            "explicit owner approval as a separate decision rather than as a side effect of "
            "a selection call (#200)")
    missing = [k for k in REDESIGN_APPROVAL_KEYS if not str(record.get(k) or "").strip()]
    if missing:
        raise IdentityRefused(
            f"the replacement approval lacks {missing}. It must carry "
            f"{list(REDESIGN_APPROVAL_KEYS)}: when the owner decided, what they decided, "
            f"which version it retires and whether it is a portrait repair or a redesign")
    scope = str(record["scope"]).strip()
    if scope not in REDESIGN_SCOPES:
        raise IdentityRefused(
            f"the replacement approval's scope is {scope!r}; it must be one of "
            f"{sorted(REDESIGN_SCOPES)}, because repairing her photograph and choosing a "
            f"different woman are different decisions and the record has to say which")
    raw_version = record["supersedes_version"]
    # A true integer only (certification C-25). `int(1.9)` is 1 and `int(True)` is 1: a
    # validator that truncates has corrected the record rather than checked it. A decimal
    # string such as "1" is accepted because it names exactly one integer.
    if isinstance(raw_version, bool):
        supersedes = None
    elif isinstance(raw_version, int):
        supersedes = raw_version
    elif isinstance(raw_version, str) and raw_version.strip().isdigit():
        supersedes = int(raw_version.strip())
    else:
        supersedes = None
    if supersedes is None:
        raise IdentityRefused(
            f"the replacement approval's supersedes_version {raw_version!r} is not an "
            f"integer version number. It is refused rather than truncated")
    at = str(record["at"]).strip()
    try:
        datetime.fromisoformat(at.replace("Z", "+00:00"))
    except ValueError:
        raise IdentityRefused(
            f"the replacement approval's `at` {record['at']!r} is not an ISO 8601 date. When "
            f"the owner decided is part of the record, and an unparseable date is no "
            f"date") from None
    approved_by = str(record["approved_by"]).strip()
    if supersedes != existing.version:
        raise IdentityRefused(
            f"the replacement approval retires version {supersedes} and the canonical "
            f"identity is version {existing.version}. An approval that does not name the "
            f"version it replaces cannot be replayed against a later one, so it is refused "
            f"rather than applied to whatever is current")
    return {**record, "scope": scope, "supersedes_version": supersedes, "at": at,
            "approved_by": approved_by}


def select(candidate: Candidate, *, owner_approved: bool,
           existing: ReferencePack | None = None,
           redesign_approval: dict | None = None) -> ReferencePack:
    """Freeze a candidate as canonical. Only the owner can do this, and only once.

    Replacing an existing canonical identity is a redesign, which #200 reserves to the owner
    explicitly — so it is refused here even when `owner_approved` is true, because "approved"
    on a selection call is not the same as approving a redesign. The one path past that is
    `redesign_approval`: an owner record shaped like `freeze.OWNER_APPROVAL` naming the
    version it retires, validated by `validate_redesign_approval`. With it the new pack is
    `existing.version + 1`; the retired version is the caller's to keep, never to delete.
    """
    if not owner_approved:
        raise IdentityRefused(
            f"{candidate.key} cannot become canonical without the owner's selection. A "
            f"candidate that becomes canonical by being first is an identity nobody chose, "
            f"and it is discovered a hundred listings later")
    version = 1
    if existing is not None:
        validate_redesign_approval(redesign_approval, existing=existing)
        version = existing.version + 1
    missing = [f for f in IDENTITY_FIELDS if not candidate.fields.get(f)]
    if missing:
        raise IdentityRefused(
            f"the reference pack would be incomplete: {missing}. An unpinned field is a field "
            f"that drifts, and drift is what the pack exists to prevent")
    return ReferencePack(version=version, fields=dict(candidate.fields),
                         approved_by_owner_at=datetime.now(timezone.utc).isoformat())


# ---------------------------------------------------------------------------
# Provenance: was this frame conditioned on the approved bytes?

# The three reference frames a pack pins by hash, and the key under which a frozen pack
# and a frame record both carry them. The face is required of every model-bearing frame;
# a body frame is required when the record says one was used.
REFERENCE_HASH_KEYS: tuple[str, ...] = ("neutral_portrait", "torso_fit_reference",
                                        "full_length_standing")
FACE_HASH_KEY = "neutral_portrait"

PROVENANCE_VERIFIED = "verified"
PROVENANCE_MISMATCH = "mismatch"
PROVENANCE_UNVERIFIABLE = "unverifiable"


def _is_sha256(value) -> bool:
    text = str(value or "").strip().lower()
    return len(text) == 64 and all(c in "0123456789abcdef" for c in text)


def provenance_check(frame_record: dict | None, pack: ReferencePack | None) -> dict:
    """Whether a frame was conditioned on the frozen pack's exact reference bytes.

    Deterministic and offline: it compares the sha256 values the frame record says it was
    conditioned on (`conditioned_on.reference_hashes`) against the ones the frozen pack
    carries (`fields.reference_hashes`). No file is opened and no judge is asked, because
    the question is not "does she look right" -- `drift_check` answers that -- but "was
    the reference the approved one", and a hash either equals another hash or it does not.

    Three answers. `verified`: every hash the frame names equals the pack's, the face is
    among them, and so is the body frame the record says it used. `mismatch`: at least one
    named hash differs -- the frame was conditioned on other bytes. `unverifiable`: a hash
    is missing, malformed, or the pack never recorded any. A path is not a hash: a record
    that names `reference_image: /tmp/x.jpg` and nothing else has described where the bytes
    were, not what they were, and unhashed is unverifiable rather than fine.
    """
    if pack is None:
        return {"verdict": PROVENANCE_UNVERIFIABLE, "compared": {}, "missing": [],
                "blocks_release": True,
                "why": "no canonical pack is frozen, so there is nothing to have been "
                       "conditioned on"}
    expected = dict((pack.fields or {}).get("reference_hashes") or {})
    if not any(_is_sha256(v) for v in expected.values()):
        return {"verdict": PROVENANCE_UNVERIFIABLE, "compared": {}, "missing": [],
                "blocks_release": True,
                "why": ("the frozen pack records no reference hashes, so no frame's "
                        "provenance can be checked against it. Unrecorded is not verified")}

    conditioned = dict((frame_record or {}).get("conditioned_on") or {})
    claimed = dict(conditioned.get("reference_hashes") or {})
    body_frame = str(conditioned.get("body_reference_frame") or "").strip()

    required = [FACE_HASH_KEY] + ([body_frame] if body_frame else [])
    missing = [k for k in required if not _is_sha256(claimed.get(k))]
    malformed = [k for k, v in claimed.items() if not _is_sha256(v)]

    compared: dict[str, dict] = {}
    mismatched: list[str] = []
    for key, value in claimed.items():
        if not _is_sha256(value):
            continue
        want = str(expected.get(key) or "").lower()
        same = bool(want) and want == str(value).lower()
        compared[key] = {"claimed": str(value)[:12], "expected": want[:12] or "unpinned",
                         "same": same}
        if not same:
            mismatched.append(key)

    if mismatched:
        verdict = PROVENANCE_MISMATCH
        why = (f"this frame was conditioned on different bytes for {mismatched} than the "
               f"frozen pack pins. Whatever it looks like, it was not made from her "
               f"approved reference, and a frame that agrees with the wrong reference is "
               f"the failure nothing downstream can see")
    elif missing or malformed:
        verdict = PROVENANCE_UNVERIFIABLE
        why = (f"the frame record carries no usable sha256 for {sorted(set(missing + malformed))}. "
               f"A path says where the reference was; only a hash says what it was, and "
               f"unhashed is unverifiable rather than fine")
    else:
        verdict = PROVENANCE_VERIFIED
        why = (f"every reference hash the frame names ({sorted(compared)}) equals the "
               f"frozen pack's")
    return {"verdict": verdict, "compared": compared, "mismatched": mismatched,
            "missing": sorted(set(missing + malformed)), "body_frame": body_frame,
            "blocks_release": verdict != PROVENANCE_VERIFIED, "why": why}


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
