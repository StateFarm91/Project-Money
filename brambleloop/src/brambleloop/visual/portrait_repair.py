"""Whether a repaired canonical portrait is still the same woman, and actually repaired.

The owner's instruction of 2026-09-23 is the shape of this module: *"My intent remains to
preserve the approved woman and repair/rebuild deficient canonical reference photography if
possible, rather than casually replacing her."*

That reframes the canonical-model blocker. The problem is not that the wrong woman was
chosen -- she was chosen, deliberately, from five finalists. The problem is that the
photograph of her fails `skin_looks_real` and `processing_is_restrained`, and every pack
built from it inherits that. So the thing to fix is the photograph.

**The hazard that makes this module necessary.** A repair is a generative act on an image
of a person, and the failure mode is not subtle to describe and very hard to see: an
image-to-image pass asked to restore skin texture can return something beautiful, real and
*not her*. Nothing downstream would catch it. `face_identity` compares a render against the
pack, so once a drifted portrait becomes the pack, every later frame agrees with it
perfectly -- the reference that is supposed to be the check has become the thing being
checked. A silently replaced identity would pass every gate this system has.

So a repair must clear two floors that cannot substitute for each other:

  REPAIRED    -- the checks a render inherits from her now pass on the portrait itself
  STILL HER   -- an independent judge, shown the approved portrait and the candidate,
                 finds no drift on the dimensions that make her recognisably herself

Passing one and failing the other has a name here, and the names are different because the
responses are opposite. A prettier picture of a different woman is a **replacement**, which
the owner reserved to themselves. A picture of the right woman that is still airbrushed is
simply **not repaired yet**.

This module assesses; it never generates. Producing a candidate repair is spend and a
decision the owner has not given, and the judging balance is empty besides.
"""
from __future__ import annotations

ACTION = "visual.portrait_repair"

# What must not have drifted for a repair to still be a repair.
#
# Taken from `identity.FACE_DIMENSIONS` rather than invented here, so the two cannot drift
# apart -- a private list of dimension names would silently stop matching the judge's
# vocabulary and report every repair as unverifiable, which is the floor-nothing-can-clear
# defect arriving through a typo.
#
# `stylisation` is deliberately excluded. The owner said "repair/rebuild", and a rebuilt
# photograph of the same woman may legitimately carry a different expression -- that is
# governed by the character bible, not by whether she is herself. The morphology dimensions
# are excluded for the same reason: this is a portrait, and a head-and-shoulders frame
# cannot answer for bust or hips. Asking it to would fail every candidate for a reason that
# is about the crop.
MUST_HOLD: tuple[str, ...] = ("face", "hair", "eyes", "age")

REPAIRED = "repaired"
NOT_REPAIRED = "not_repaired"
DIFFERENT_WOMAN = "different_woman"
UNVERIFIABLE = "unverifiable"


def assess(db, *, candidate_ref: str, approved_ref: str = "", provider=None,
           realism_judger=None) -> dict:
    """Judge a candidate repair on both floors. Renders nothing, replaces nothing.

    `approved_ref` defaults to the committed portrait, which is the only thing a repair can
    honestly be measured against: the file every pack carries and every render inherits.
    """
    from . import brief, identity, model_registry, photoreal

    approved_ref = approved_ref or brief.approved_portrait()
    if not candidate_ref or not approved_ref:
        return {"assessed": False,
                "why": ("a repair is judged against the approved portrait, so it needs "
                        "both images. This is not a finding about either of them")}

    # Floor one: is the deficiency actually fixed, on the portrait itself.
    reading = photoreal.judge(candidate_ref, db=db, provider=realism_judger)
    gate = photoreal.gate(reading)
    still_failing = sorted(f for f in gate["failed"] if f in photoreal.INHERITED)
    realism_unmade = sorted(u for u in gate["unjudged"] if u in photoreal.INHERITED)

    # Floor two: is it still her. Asked of a judge shown both photographs, which is the
    # only comparison that can answer it -- a description of her compared against a
    # description of the candidate would let two different women match the same adjectives.
    comparison = model_registry.compare_identity(db, approved_ref, candidate_ref,
                                                 provider=provider)
    if comparison.get("error"):
        return {"assessed": False, "verdict": UNVERIFIABLE,
                "why": (f"the identity comparison could not be made: "
                        f"{comparison['error']}. Unverified is not the same as unchanged, "
                        f"and a repair adopted without it would make the reference agree "
                        f"with itself for ever"),
                "realism_still_failing": still_failing}

    # `compare_identity` returns a flat {dimension: verdict}, and every value it does not
    # recognise it has already downgraded to `unmeasurable` -- a judge that wandered off
    # the vocabulary has not said she is the same woman.
    drifted = sorted(n for n in MUST_HOLD if comparison.get(n) == identity.DRIFT)
    unread = sorted(n for n in MUST_HOLD if comparison.get(n) != identity.MATCH
                    and n not in drifted)

    return {
        "assessed": True,
        "candidate": candidate_ref,
        "approved": approved_ref,
        "realism_still_failing": still_failing,
        "realism_unjudged": realism_unmade,
        "identity_drifted": drifted,
        "identity_unread": unread,
        "verdict": _verdict(still_failing, realism_unmade, drifted, unread),
        "what_to_do": _what_to_do(still_failing, realism_unmade, drifted, unread),
        "replaces_nothing": (
            "this assesses a candidate and adopts nothing. Replacing the approved portrait "
            "is the owner's decision, and freezing is a one-way door"),
    }


def _verdict(still_failing, realism_unmade, drifted, unread) -> str:
    # Drift is checked first and on purpose. A candidate that fixed the skin *and* changed
    # the woman is the outcome the owner reserved to themselves, and reporting it as
    # "repaired" because the realism floor passed would be the system quietly making that
    # decision on their behalf.
    if drifted:
        return DIFFERENT_WOMAN
    if unread or realism_unmade:
        return UNVERIFIABLE
    if still_failing:
        return NOT_REPAIRED
    return REPAIRED


def _what_to_do(still_failing, realism_unmade, drifted, unread) -> str:
    if drifted:
        return (f"this candidate differs from the approved portrait on {drifted}, so it is "
                f"a replacement rather than a repair however good it looks. Adopting it "
                f"would swap the identity the owner chose, and nothing downstream could "
                f"detect that afterwards: once a drifted portrait is the pack, every frame "
                f"conditioned on it agrees with it perfectly")
    if unread:
        return (f"{unread} could not be read, so whether this is still her is unproven "
                f"rather than confirmed. A comparison that could not see the face has not "
                f"checked the face")
    if realism_unmade:
        return (f"{realism_unmade} were not judged on the candidate, and unmade is not "
                f"passed. Ask again before adopting anything")
    if still_failing:
        return (f"it is still her and the photograph still fails {still_failing}, so the "
                f"repair did not take. That is a further attempt at the photography, not a "
                f"different woman")
    return ("the photograph clears the checks every pack inherits from it and the "
            "comparison finds no drift on the dimensions that make her herself. This is a "
            "candidate the owner can decide on")
