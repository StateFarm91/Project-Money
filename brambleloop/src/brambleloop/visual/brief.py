"""The owner's aesthetic direction for the canonical model (#198), as code rather than chat.

Given on 2026-09-21. It lives here because a brief that exists only in a conversation is a
brief that gets paraphrased differently by whoever writes the next prompt -- and the whole
point of a canonical model is that nothing about her is re-decided per listing.

Three things this file is deliberately *not*:

**Not a likeness of anybody.** The direction arrived alongside a photograph of a real,
identifiable public figure. It is not used, referenced or conditioned on: building a
persistent commercial brand identity from a real person's photograph creates that person's
likeness for commercial use, and the owner's own direction rules out celebrity resemblance
in the same breath. `FORBIDDEN` states it so a later prompt cannot quietly reintroduce it.

**Not a face.** The owner was explicit after the first reference-conditioned trial came back
with the right face on a different body: the canonical identity is the entire woman. The
morphology half of `visual.identity` is where that is enforced; this file is where it is
said.

**Not a style guide for the product.** She is the recurring model and the crochet is the
hero. `SHE_COMMUNICATES` is the list of jobs she does for the product, and there is no entry
on it for being attractive at the product's expense.
"""
from __future__ import annotations

GIVEN_AT = "2026-09-21"
REQUIREMENT = 198

AGE_BAND = "late twenties to early thirties in apparent age"

# The physical direction the owner asked for on 2026-09-21, as generic attributes.
#
# It was given by pointing at a photograph of a real public figure and saying "ideally the
# body and facial features I'm looking for -- not exactly her". That is a legitimate way to
# specify a type, and the type is what is recorded: dark hair, light blue-green eyes, strong
# brows, defined cheekbones, a lean athletic build. Many thousands of people look like that,
# and none of those attributes belongs to anybody.
#
# What is not recorded, and is refused in `FORBIDDEN`, is the photograph itself or the
# person. A generated candidate that reads as a recognisable public figure is excluded on
# the rule rather than on its score, however it was arrived at -- which matters more here
# than it did before, because aiming at a type a celebrity exemplifies is exactly the
# circumstance in which a generator drifts towards the celebrity.
#
# One tension is resolved deliberately. The photograph is heavily styled glamour and the
# owner's own direction rules out excessive glamour, influencer caricature and
# model-perfection. So the *structure* is taken -- colouring, features, proportions -- and
# the *register* stays the brief's: warm, natural, unstyled, believable as a real person.
# Revised 2026-09-21 (second direction). The owner rejected all five tournament finalists
# and supplied their own generated concept as the canonical candidate, so the attributes
# below are read off that concept rather than off the earlier type: brunette with warm
# lighter highlights rather than uniformly dark, worn up as often as down, and a fuller bust
# than the first direction asked for.
PHYSICAL_DIRECTION: dict[str, str] = {
    "hair": ("brunette with warm lighter highlights through the mid-lengths and ends, "
             "worn in a soft relaxed updo with loose face-framing pieces, or down with a "
             "natural wave"),
    "eyes": "light blue-green, bright and clear",
    "brows": "strong, well-defined, darker than the hair",
    "face": "oval to softly heart-shaped, high defined cheekbones, straight nose, full lips",
    "complexion": ("light with a warm sun-warmed undertone, natural skin texture, visible "
                   "pores, light freckling across the nose and cheeks"),
    "stature": "average to tall",
    "build": "lean and athletic, visibly toned rather than soft",
    "shoulders": "straight, moderate width, not broad",
    "torso": "long, narrow waist, flat midriff",
    # Revised on the owner's instruction of 2026-09-21: "slightly bigger breast". Moderate
    # rather than small-to-moderate, and still in proportion with a lean athletic frame --
    # the register stays the brief's, which rules out glamour and exaggeration. This is a
    # pinned identity dimension rather than a styling choice, which is why it is a number in
    # the pack and a required hard-floor dimension in the drift check.
    "bust": "moderate and naturally full, in proportion with a lean athletic frame",
    "hips": "narrow to moderate, close to the waist measurement",
    "limbs": "long, slim, defined",
}

PHYSICAL_DIRECTION_IS_A_TYPE = (
    "a physical type, not a person. Every attribute here is a generic description that "
    "thousands of people match. The photograph it was communicated by is not used, and a "
    "candidate that reads as a recognisable public figure is excluded on the rule"
)

# What she should feel like. Kept as the owner's own phrasing: a brief rewritten in somebody
# else's words is a brief that has already drifted once before anything was rendered.
QUALITIES: tuple[str, ...] = (
    "naturally beautiful rather than artificial or model-perfect",
    "approachable and warm",
    "premium and aspirational without looking inaccessible",
    "contemporary",
    "believable as a real person",
    "appropriate for upscale Etsy, Pinterest, lifestyle and editorial imagery",
    "able to carry fall, Christmas, winter, spring and summer styling without her identity "
    "becoming seasonal",
)

AVOID: tuple[str, ...] = (
    "influencer caricature",
    "excessive glamour",
    "plastic or over-retouched skin",
    "exaggerated AI beauty",
    "celebrity resemblance",
    "teenage appearance",
    "overly fashion-editorial posing that competes with the crochet product",
)

# Hard prohibitions, separate from `AVOID` because these are not matters of taste. A
# reference image of a real person cannot be used to build her, whoever supplies it and
# however it is framed.
FORBIDDEN: tuple[tuple[str, str], ...] = (
    ("real_person_reference",
     "no photograph of a real, identifiable person is used as a reference, a conditioning "
     "source or a described target. A persistent commercial brand identity built from "
     "somebody's photograph is that person's likeness in commercial use, and it is also the "
     "celebrity resemblance the direction rules out"),
    ("public_figure_likeness",
     "no candidate is accepted that reads as a recognisable public figure, however it was "
     "arrived at"),
)

# ---------------------------------------------------------------------------
# The owner's candidate (second direction, 2026-09-21)
#
# The tournament ran, presented five finalists with their measured results, and the owner
# rejected all five and supplied their own generated concept instead. That is the tournament
# working rather than failing: its whole purpose was to stop a candidate becoming canonical
# by topping a table, and "none of these" is one of the answers it exists to make possible.
#
# What is different about this candidate, and what is not:
#
# **It is a generated image, supplied by the owner as their own concept.** It is not a
# photograph of a real, identifiable person, so conditioning on it does not create anybody's
# likeness -- which is the thing `FORBIDDEN` exists to prevent, and it still prevents it.
#
# **The public-figure screen still applies.** A generated candidate that reads as a
# recognisable public figure is excluded on the rule however it was arrived at, and being
# owner-supplied does not exempt it. That check is run against this candidate like any other.
#
# **It is not canonical.** The owner was explicit: build the reference pack, prove face and
# whole-person morphology hold, present everything, and wait for approval before freezing.
# So nothing in this file or in `visual.reference_pack` selects her either.
CANDIDATE_GIVEN_AT = "2026-09-21"

CANDIDATE_IS_OWNER_SUPPLIED = (
    "a generated concept supplied by the owner as their own canonical-model direction, not "
    "a photograph of a real person. Conditioning on it creates no living person's likeness, "
    "and the public-figure screen still applies to what it produces"
)

REJECTED_FINALISTS_NOTE = (
    "the five tournament finalists were rejected by the owner on 2026-09-21. They remain "
    "evidence -- what the field looked like, what the floors measured -- and are not "
    "eligible for automatic selection. Nothing promotes a rejected finalist"
)


def owner_candidate_supplied() -> bool:
    """Whether the owner has supplied a candidate of their own.

    This is what closes the tournament. Once the owner has looked at a field and said "none
    of these, *this* one", rendering another twenty women is not a search -- it is spending
    money on a question that has been answered. The tournament's results stay as evidence.
    """
    from pathlib import Path

    return Path(candidate_reference()).is_file()


def candidate_reference() -> str:
    """The conditioning source: one clean frame of the owner's concept.

    Deliberately not the whole collage and not the hero frame. A generator handed a grid of
    seven photographs renders a grid, and the hero frame carries the Brambleloop wordmark
    across it -- a generator handed text renders text, which is how a brand lockup ends up
    baked into a model's face at 1024 pixels.
    """
    from pathlib import Path

    return str(Path(__file__).resolve().parent / "assets" / "owner_candidate_reference.png")


def candidate_concept() -> str:
    """The owner's concept as supplied, kept whole as the direction of record."""
    from pathlib import Path

    return str(Path(__file__).resolve().parent / "assets" / "owner_candidate_concept.jpg")


# The two frames a reference pack needs before any scene is rendered, and the reason the
# first pack could not be measured: every finalist's reference was a head-and-shoulders
# crop, so stature, torso, bust, waist and hips were `unmeasurable` on the reference itself.
# A floor that can only ever return `unverifiable` is not a floor. The full-length frame is
# what makes the morphology half of the identity checkable at all.
REFERENCE_FRAMES: tuple[tuple[str, str], ...] = (
    ("neutral_portrait",
     "Neutral head-and-shoulders portrait in even, soft daylight against a plain warm-grey "
     "background. Relaxed natural expression, direct gaze, hair worn down and away from the "
     "face, simple plain crew-neck top, no jewellery, no makeup beyond natural. The face is "
     "unobstructed and evenly lit."),
    # The bridge frame, and the one the first pack was missing. A portrait shows a face and
    # no body; a full-length shows a body and a face too small to read. Neither can answer
    # the owner's two required dimensions -- chest and torso -- so the first build measured
    # bust in one scene of four and torso in none, and was correctly unapprovable. This
    # frame is deliberately built to be readable on exactly those two, while still showing a
    # face the judge can match: it is what joins the portrait to the full-length.
    ("torso_fit_reference",
     "Waist-up photograph from mid-thigh to the top of the head, standing squarely facing "
     "the camera in even, soft daylight against a plain warm-grey background. Wearing a "
     "plain close-fitting sleeveless top tucked into plain fitted trousers, arms relaxed "
     "and clear of the body, hair behind the shoulders. Shoulder width, chest and bust "
     "proportion, torso length and waist are all clearly and unambiguously readable, and "
     "her face is fully visible and evenly lit. Nothing loose, draped, layered or held in "
     "front of the body."),
    ("full_length_standing",
     "Full-length standing photograph, head to feet entirely in frame and filling the full "
     "height of the picture, even soft daylight against a plain warm-grey background. "
     "Standing straight and relaxed, arms at her sides and clear of the torso, facing the "
     "camera. Wearing a plain fitted sleeveless top and plain fitted trousers so that "
     "stature, shoulder width, torso length, bust, waist, hips and limb proportions are all "
     "clearly readable. No loose or draped clothing, no crop, nothing obscuring the "
     "silhouette, and no empty space above her head or below her feet."),
)

# Which reference frame is authoritative for which drift dimension. A frame is asked only
# what it is in a position to know: the portrait cannot answer for hips, and a full-length
# standing shot at 1024 pixels cannot answer for the chest, which is exactly why the first
# build's own reference came back with `bust: unmeasurable` pinned into the pack.
FRAME_AUTHORITY: dict[str, tuple[str, ...]] = {
    "neutral_portrait": ("face", "hair", "eyes", "age", "stylisation"),
    "torso_fit_reference": ("bust", "torso", "waist", "shoulders", "build"),
    "full_length_standing": ("stature", "hips", "limbs", "build", "shoulders"),
}


# What she is for. The order is the owner's.
SHE_COMMUNICATES: tuple[str, ...] = (
    "garment fit", "scale", "lifestyle", "use", "warmth", "aspiration", "emotional appeal",
    "brand continuity",
)

PRODUCT_IS_THE_HERO = (
    "She is the recurring Brambleloop model and the crochet product remains the hero. She "
    "does not dominate product imagery merely because she is attractive."
)

# What a candidate is screened on before it can be a finalist (#199).
SCREEN_ON: tuple[str, ...] = (
    "attractiveness", "warmth_approachability", "distinctiveness", "realism", "brand_fit",
    "non_celebrity_appearance", "suitability_across_seasons",
    "suitability_for_crochet_garments", "provider_reproducibility", "absence_of_ai_artifacts",
)

TARGET_CANDIDATES = (20, 30)
TARGET_FINALISTS = 5

# The controlled situations every finalist is rendered in before the owner sees any of them.
# Materially different on purpose: a set of five flattering portraits proves only that the
# generator can repeat a portrait.
STRESS_SCENES: tuple[tuple[str, str], ...] = (
    ("neutral_reference",
     "Neutral three-quarter portrait in even daylight against a plain warm-grey background, "
     "relaxed natural expression, simple crew-neck top, no styling."),
    ("fitted_garment",
     "Wearing a close-fitting hand-crocheted cream wool cardigan, buttoned, three-quarter "
     "length editorial photograph in soft daylight. The garment's fit through the shoulders, "
     "bust and waist is clearly readable."),
    # Added 2026-09-21 after the first three-frame pack. The four scenes the owner listed
    # are the real commercial world -- a loose sweater, a winter scarf, a seated lifestyle
    # frame -- and in every one of them the chest and torso are genuinely obscured, which
    # the rule correctly reports as unmeasurable. A set with no frame in which fit through
    # the bust is readable also fails the product: a buyer choosing a fitted crocheted
    # garment is buying exactly that.
    ("fitted_garment_close",
     "Waist-up photograph in a close-fitting hand-crocheted fine-gauge top, standing "
     "squarely facing the camera in soft daylight against a plain warm background. The "
     "garment's fit through the shoulders, bust and waist is the subject of the "
     "photograph and is clearly readable, and her face is fully visible. Nothing draped, "
     "layered or held in front of the body."),
    ("loose_layered_garment",
     "Wearing an oversized loose hand-crocheted oatmeal wool sweater layered over a slim "
     "top, standing, soft window light. The garment is deliberately loose."),
    ("winter_seasonal",
     "Outdoors in soft winter light beside evergreen branches, wearing a hand-crocheted "
     "mustard beanie and a chunky cream scarf, warm seasonal styling."),
    ("non_garment_lifestyle",
     "Seated in a bright living room holding a hand-crocheted wool storage basket, natural "
     "afternoon light, wearing plain clothes so the crocheted object is the styled item."),
)

# What the stress test measures. The first two are independent hard floors and the rest are
# quality; the split is the owner's instruction after the body-drift failure.
HARD_FLOORS: tuple[str, ...] = ("facial_identity", "whole_person_morphology")

# Named by the owner on 2026-09-21 as explicit hard-floor dimensions: *chest/bust and torso
# continuity*. They are not merely two of the eight morphology dimensions to be averaged in
# with the rest -- the failure that prompted the whole morphology half of this system was a
# convincing face above a chest that had changed, so a pack that cannot evidence these two
# has not evidenced the thing that went wrong. `identity.REQUIRED_MORPHOLOGY` enforces it.
REQUIRED_MORPHOLOGY: tuple[str, ...] = ("bust", "torso")
STRESS_MEASURES: tuple[str, ...] = HARD_FLOORS + (
    "chest_torso_continuity", "stature_build_continuity",
    "shoulder_waist_hip_continuity", "skin_hair_continuity", "realism",
    "garment_fit_interpretability", "provider_repeatability", "cross_scene_identity_drift",
)


def physical_sentence() -> str:
    """The owner's physical direction as one descriptive sentence."""
    return (
        f"Hair {PHYSICAL_DIRECTION['hair']}. Eyes {PHYSICAL_DIRECTION['eyes']}, brows "
        f"{PHYSICAL_DIRECTION['brows']}. Face {PHYSICAL_DIRECTION['face']}. Complexion "
        f"{PHYSICAL_DIRECTION['complexion']}. Build: {PHYSICAL_DIRECTION['stature']} height, "
        f"{PHYSICAL_DIRECTION['build']}, shoulders {PHYSICAL_DIRECTION['shoulders']}, "
        f"{PHYSICAL_DIRECTION['torso']}, bust {PHYSICAL_DIRECTION['bust']}, hips "
        f"{PHYSICAL_DIRECTION['hips']}, limbs {PHYSICAL_DIRECTION['limbs']}.")


def base_prompt(seed_note: str = "") -> str:
    """The shared description every candidate is generated from.

    Deliberately one prompt with a varying note rather than twenty different prompts: the
    tournament is choosing between women within one direction, and twenty differently-worded
    briefs would be comparing the prompts instead.

    Since the owner narrowed the physical direction, the note varies *within* the type rather
    than across all types -- a different woman each time, recognisably in the direction asked
    for. A field that ignored the direction would not be a choice the owner asked to make,
    and one that produced the same woman twenty times would not be a choice at all.
    """
    return (
        f"Editorial portrait photograph of an attractive, warm, contemporary adult woman, "
        f"{AGE_BAND}. {physical_sentence()} "
        f"She is naturally beautiful rather than model-perfect, approachable, "
        f"premium without looking inaccessible, and entirely believable as a real person. "
        f"Natural skin texture with visible pores and no retouching. Soft daylight, neutral "
        f"warm background, relaxed genuine expression, simple plain clothing. "
        f"Not a celebrity and not resembling any known public figure. No influencer styling, "
        f"no heavy glamour makeup, no exaggerated features."
        + (f" {seed_note}" if seed_note else ""))


def state() -> dict:
    """The brief, readable wherever a decision cites it."""
    return {
        "requirement": REQUIREMENT,
        "given_at": GIVEN_AT,
        "age_band": AGE_BAND,
        "physical_direction": dict(PHYSICAL_DIRECTION),
        "physical_direction_is_a_type": PHYSICAL_DIRECTION_IS_A_TYPE,
        "qualities": list(QUALITIES),
        "avoid": list(AVOID),
        "forbidden": [{"rule": k, "why": v} for k, v in FORBIDDEN],
        "she_communicates": list(SHE_COMMUNICATES),
        "product_is_the_hero": PRODUCT_IS_THE_HERO,
        "identity_is_the_whole_woman": (
            "the canonical identity is the entire woman, not merely her face. A face match "
            "may never compensate for body or morphology drift, and an obscured proportion "
            "is unmeasurable rather than a pass"),
        "screen_on": list(SCREEN_ON),
        "target_candidates": list(TARGET_CANDIDATES),
        "target_finalists": TARGET_FINALISTS,
        "stress_scenes": [{"key": k, "prompt": v} for k, v in STRESS_SCENES],
        "hard_floors": list(HARD_FLOORS),
        "required_morphology_dimensions": list(REQUIRED_MORPHOLOGY),
        "stress_measures": list(STRESS_MEASURES),
        "owner_candidate": {
            "given_at": CANDIDATE_GIVEN_AT,
            "is": CANDIDATE_IS_OWNER_SUPPLIED,
            "rejected_finalists": REJECTED_FINALISTS_NOTE,
            "reference_frames": [{"key": k, "prompt": v} for k, v in REFERENCE_FRAMES],
            "not_canonical_yet": (
                "the pack is built and presented; the owner approves before anything is "
                "frozen. Nothing here selects her"),
        },
        "selection_is_the_owners": (
            "the finalists are presented with their controlled comparison sets and measured "
            "results. Nothing selects itself; a candidate that became canonical by being "
            "first is an identity nobody chose"),
    }
