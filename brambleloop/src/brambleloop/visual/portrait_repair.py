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

# Which inherited checks a head-and-shoulders portrait can actually answer.
#
# `photoreal.INHERITED` includes `hands_are_right`, and the approved portrait is a portrait:
# there are no hands in it. So that check came back unjudged on every candidate, `unmade is
# not passed` fired, and all three repairs were reported `unverifiable` -- a floor nothing
# can clear, in the module whose entire job is to stop that.
#
# This is the same reasoning already applied to `MUST_HOLD`, which excludes the morphology
# dimensions because a portrait cannot answer for bust or hips. It was applied to the
# identity half and not to the realism half.
#
# A *failed* hands check still counts: if a rebuilt portrait does show hands and they are
# wrong, that is a real defect. What is dropped is only the requirement that it be judged.
PORTRAIT_ANSWERABLE: tuple[str, ...] = ("skin_looks_real", "processing_is_restrained",
                                        "anatomy_is_possible")

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
    # Only the checks this frame could have answered. A portrait with no hands in it has
    # not failed a hands check; it has not been asked one.
    realism_unmade = sorted(u for u in gate["unjudged"] if u in PORTRAIT_ANSWERABLE)

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


# The owner's authorisation of 2026-09-23, bounded here rather than remembered.
#
# "Generate the minimum bounded number of repair candidates necessary to determine whether
# this method works. Preserve exact spend." Three is that number: one cannot tell a method
# that works from a lucky draw, and a fourth is evidence the method is wrong rather than
# the sample -- the same bound `model_photography.ATTEMPTS` uses and for the same reason.
# The loop stops at the first candidate that clears both floors, so a working method costs
# one render.
MAX_CANDIDATES = 3
CEILING_CAD = 1.00

# What the repair asks for, from the owner's own list of deficiencies.
#
# Every clause is about the photograph. Not one is about her: no adjective describing a
# face, no age, no colouring, no "beautiful". Those would be a description of a type, which
# is how a generator produces a different woman who matches the words -- the exact failure
# `model_photography.prompt_for` already documents. Her appearance is carried entirely by
# the reference image, which is what makes this a repair rather than a casting call.
REPAIR_DIRECTION = (
    "This is a photographic restoration of the attached portrait. Keep the same person "
    "exactly: the same face and its geometry, the same eyes, the same hair, the same "
    "apparent age, the same complexion. Do not beautify, slim, youthen, symmetrise or "
    "otherwise improve her, and do not change her expression or identity in any way. "
    "Change only how the photograph was made. "
    "Restore real skin: visible pores and fine surface texture, uneven natural tone, faint "
    "shine where light falls, ordinary asymmetry between the two sides of the face, and any "
    "lines, marks or blemishes that belong to her. Remove the airbrushed, poreless, "
    "synthetic quality and the heavy beauty retouching. No skin smoothing, no blemish "
    "removal, no eye or teeth brightening, no softening filter. "
    "Render hair as real hair with individual strands, stray flyaways and uneven fall "
    "rather than as a smooth mass. Where hands or fingers are visible they are correctly "
    "formed and correctly numbered, in focus, not blurred or merged. "
    "Light it as a real camera in a real room: one coherent daylight source with natural "
    "falloff and honest shadow, ordinary lens character and grain, no catalogue polish and "
    "no uniform studio backdrop. It should read as an unedited raw frame of this woman "
    "taken by a photographer, not as a finished beauty image."
)


def propose(db, *, work_dir: str, provider_key: str = "", env: dict | None = None,
            generator=None, approved_ref: str = "", **judges) -> dict:
    """Render bounded repair candidates and assess each. Adopts nothing, ever.

    **Refuses to render when the assessment cannot be made.** That is the load-bearing
    guard, not a courtesy: a candidate nobody can judge is indistinguishable from a
    different woman, and the one outcome worse than no repair is an unverified one adopted
    because it looked good. Money spent on an unjudgeable portrait of a person is money
    spent making that mistake possible.

    Stops at the first candidate that clears both floors, because the question the owner
    asked is whether the method works -- not which of three near-identical portraits is
    prettiest, which is a casting decision nobody authorised.
    """
    from ..gateway import images
    from ..ops import funding
    from . import brief, tournament

    approved_ref = approved_ref or brief.approved_portrait()

    held = funding.blocked(db)
    if held.get("blocked") and generator is None:
        return {"ran": False, "waiting_on": "model_provider_balance",
                "spent_cad": 0.0, "candidates": [],
                "why": ("both floors of a repair are vision calls -- the realism judge and "
                        "the identity comparison -- and the balance that serves them is "
                        "spent. Rendering now would buy a portrait of a person that "
                        "nothing could check for drift, which is the one thing this "
                        "authorisation exists to prevent. "
                        + held.get("why_this_stops_spending", ""))}

    # The same selector the production render path uses, rather than a second opinion
    # about which provider is preferred. Two places choosing a provider is how they come
    # to disagree, and the benchmark already decided this one.
    provider = provider_key or tournament.preferred_provider(db, env) or ""
    if not provider and generator is None:
        return {"ran": False, "waiting_on": "image_provider_credential",
                "spent_cad": 0.0, "candidates": [],
                "why": "no verified image provider is available in this environment"}

    spent, candidates = 0.0, []
    for index in range(MAX_CANDIDATES):
        price = _price_of(provider)
        if spent + price > CEILING_CAD:
            break
        try:
            render = (generator(REPAIR_DIRECTION, reference_urls=[approved_ref])
                      if generator else
                      images.generate(REPAIR_DIRECTION, reference_urls=[approved_ref],
                                      env=env, provider_key=provider, size="1024x1024",
                                      work_dir=work_dir))
        except Exception as exc:  # noqa: BLE001 - a refusal is a record, not a crash
            candidates.append({"attempt": index + 1, "made": False,
                               "why": f"{type(exc).__name__}: {exc}"[:240]})
            break

        spent = round(spent + float(render.get("cad") or price), 4)
        found = assess(db, candidate_ref=render.get("image_ref") or "",
                       approved_ref=approved_ref, **judges)
        found["attempt"] = index + 1
        found["made"] = True
        found["provider"] = provider
        candidates.append(found)
        if found.get("verdict") == REPAIRED:
            break

    won = next((c for c in candidates if c.get("verdict") == REPAIRED), None)
    return {
        "ran": True,
        "approved": approved_ref,
        "provider": provider,
        "spent_cad": round(spent, 4),
        "ceiling_cad": CEILING_CAD,
        "candidates": candidates,
        "repaired_candidate": won,
        "verdict": _method_verdict(candidates),
        "adopts_nothing": (
            "no candidate supersedes the canonical reference here. The owner asked to see "
            "the original and the repair side by side with the evidence before anything "
            "replaces her, and freezing is a one-way door"),
        "body_pack_untouched": (
            "this is a portrait repair. The approved bust, torso and body proportions "
            "remain authoritative and nothing here regenerates them"),
    }


def _price_of(provider_key: str) -> float:
    from ..gateway import images

    provider = images.BY_KEY.get(provider_key)
    return round(float(provider.usd_per_image) * images.USD_TO_CAD, 4) if provider else 0.0


def _method_verdict(candidates: list[dict]) -> str:
    """Whether the repair *method* works, which is the question that was asked."""
    made = [c for c in candidates if c.get("made")]
    if not made:
        return UNVERIFIABLE
    if any(c.get("verdict") == REPAIRED for c in made):
        return REPAIRED
    if any(c.get("verdict") == DIFFERENT_WOMAN for c in made):
        # Worth naming even when another candidate merely failed: a method that drifts her
        # identity is not a method to retry, it is one to abandon.
        return DIFFERENT_WOMAN
    if all(c.get("verdict") == UNVERIFIABLE for c in made):
        return UNVERIFIABLE
    return NOT_REPAIRED


def reassess(record: dict) -> dict:
    """Re-derive verdicts from evidence already collected. Makes no call and spends nothing.

    The first live run judged three candidates `unverifiable` because `hands_are_right`
    could not be read on a portrait -- a fault in the rule, not in the evidence. The
    per-candidate failures and drifts were measured correctly and are on file, so the
    corrected verdict is a recomputation rather than a re-judgement.

    Deliberately not a re-run: the owner's instruction is not to re-judge old evidence
    merely because funding returned, and re-rendering would buy answers already paid for.
    """
    candidates = []
    for found in record.get("candidates") or []:
        if not found.get("made"):
            candidates.append(found)
            continue
        still_failing = list(found.get("realism_still_failing") or ())
        unmade = [u for u in (found.get("realism_unjudged") or ())
                  if u in PORTRAIT_ANSWERABLE]
        drifted = list(found.get("identity_drifted") or ())
        unread = list(found.get("identity_unread") or ())
        candidates.append({**found,
                           "verdict": _verdict(still_failing, unmade, drifted, unread),
                           "verdict_recomputed": True,
                           "realism_unjudged_ignored": [
                               u for u in (found.get("realism_unjudged") or ())
                               if u not in PORTRAIT_ANSWERABLE]})

    won = next((c for c in candidates if c.get("verdict") == REPAIRED), None)
    return {**record, "candidates": candidates, "repaired_candidate": won,
            "verdict": _method_verdict(candidates),
            "recomputed": (
                "verdicts re-derived from the evidence already collected, after "
                "`hands_are_right` was found to be unanswerable on a portrait. No render "
                "and no judgement was re-bought")}
