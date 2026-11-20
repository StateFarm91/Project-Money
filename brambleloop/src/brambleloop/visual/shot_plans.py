"""Gallery shot plans per category, for every Launch-0 product (W-OWNERIMG).

A shot plan is the ordered list of gallery roles a listing needs. Each role names:

* its job (`publish.eligibility.JOBS`);
* why it applies;
* which requirement rows ask for it;
* which sources can truthfully fill it.

**No filler.** A role is in a plan only if its job applies to the category
(`eligibility.gallery_jobs_for`), with one exception: PROOF, which is conditional on a
physical sample photograph existing.

**Sources** (VISGATE §2, with the code that enforces each):

* `disclosed_render`: the certified deterministic frames (`disclosed_render`,
  `gallery_frames`, the vessel angle view, `contents_frame`), verified on their bytes against
  the CIR.
* `generated`: AI-generated imagery. It does not matter whether the autonomous workflow made
  it or the owner submitted it: the class is the same and so are the gates. The role must
  accept the medium's purpose (`AI_LIFESTYLE_CONCEPT` serves only CONVERSION_CREATIVE). Today,
  F-852 (`eligibility.may_export`) refuses generated product imagery in every listing role,
  so the plan marks this source `blocked_f852`. That changes only by an owner policy decision.
  Code never changes it on its own.
* `photo`: a camera photograph of a physically made sample (`physical_upgrade.intake`). It is
  the only source for PROOF and FIT.

The requirement words come from VISGATE §1:

* F-030: angles, detail, texture, scale, lifestyle/use, sizing, inclusions, category-specific
  proof.
* F-254: hero, alternate angle, stitch/motif detail, scale/context, construction detail,
  colour context, fit/worn.
"""
from __future__ import annotations

from ..publish import eligibility as el

DISCLOSED, GENERATED, PHOTO = "disclosed_render", "generated", "photo"
SATISFIES, NOT_DRAWABLE, PURPOSE_REFUSED, BLOCKED_F852 = (
    "satisfies", "not_drawable", "purpose_refused", "blocked_f852")

# Gallery order. The hero is always first (eligibility.HERO_JOB).
ORDER: tuple[str, ...] = (el.DESIRE, el.LIFESTYLE, el.DETAIL, el.SCALE, el.SIZING, el.ANGLE,
                          el.CONSTRUCTION, el.COLOUR_CONTEXT, el.FIT, el.MATERIALS,
                          el.CONTENTS, el.PROOF)

# The role key the intake and the orchestrator use for each job (release_gates.ROLE_JOBS
# names: hero, size, whats_included, ...).
ROLE_OF_JOB: dict[str, str] = {
    el.DESIRE: "hero", el.LIFESTYLE: "lifestyle", el.DETAIL: "detail", el.SCALE: "size",
    el.SIZING: "sizing", el.ANGLE: "angle", el.CONSTRUCTION: "construction",
    el.COLOUR_CONTEXT: "colour_context", el.FIT: "fit", el.MATERIALS: "materials",
    el.CONTENTS: "whats_included", el.PROOF: "proof",
}
JOB_OF_ROLE: dict[str, str] = {r: j for j, r in ROLE_OF_JOB.items()}

REQUIRED_BY: dict[str, tuple[str, ...]] = {
    el.DESIRE: ("F-254", "F-278"), el.LIFESTYLE: ("F-030",),
    el.DETAIL: ("F-030", "F-254"), el.SCALE: ("F-030", "F-254"), el.SIZING: ("F-030",),
    el.ANGLE: ("F-030", "F-254"), el.CONSTRUCTION: ("F-254",),
    el.COLOUR_CONTEXT: ("F-254",), el.FIT: ("F-254",), el.MATERIALS: ("#65 base set",),
    el.CONTENTS: ("F-030",), el.PROOF: ("F-030 (AMBIGUOUS: 'category-specific proof')",),
}

# What the disclosed deterministic set can do per job (VISGATE §2) and the medium/purpose it
# is certified as. LIFESTYLE is not drawable (`gallery_frames.NOT_DRAWABLE`); PROOF and FIT
# are photograph-only (`eligibility.JOB_PURPOSES`).
_DISCLOSED: dict[str, tuple[str, str, str] | None] = {
    el.DESIRE: (SATISFIES, "DIGITAL_TWIN_RENDER", el.CONVERSION_CREATIVE),
    el.DETAIL: (SATISFIES, "DIGITAL_TWIN_RENDER", el.ENGINEERING_EVIDENCE),
    el.SCALE: (SATISFIES, "DIGITAL_TWIN_RENDER", el.CUSTOMER_INFORMATION),
    el.SIZING: (SATISFIES, "INFOGRAPHIC", el.CUSTOMER_INFORMATION),
    el.ANGLE: (SATISFIES, "DIGITAL_TWIN_RENDER", el.ENGINEERING_EVIDENCE),
    el.CONSTRUCTION: (SATISFIES, "INFOGRAPHIC", el.CUSTOMER_INFORMATION),
    el.COLOUR_CONTEXT: (SATISFIES, "INFOGRAPHIC", el.CUSTOMER_INFORMATION),
    el.MATERIALS: (SATISFIES, "INFOGRAPHIC", el.CUSTOMER_INFORMATION),
    el.CONTENTS: (SATISFIES, "PATTERN_PREVIEW", el.CUSTOMER_INFORMATION),
    el.LIFESTYLE: None, el.FIT: None, el.PROOF: None,
}

# Briefs for the generated source. They are code defaults. A change is adopted only as a
# promoted `improve.league` prompt version (`image_production.PROMPT_KEY`), never edited
# around a gate.
LIFESTYLE_BRIEF: dict[str, tuple[bool, str]] = {
    "blanket": (True, "the finished blanket draped over Laura's lap on a sofa, soft daylight"),
    "baby": (True, "the finished baby blanket folded over Laura's arm beside a nursery chair"),
    "basket": (False, "the finished basket(s) on a shelf holding everyday things"),
    "coaster": (False, "all coasters on a wooden table, a mug beside (never on) one"),
    "placemat": (False, "both placemats set on a dining table with plates beside them"),
    "garment": (True, "Laura wearing the finished garment, full length, natural light"),
}


def _sources(job: str) -> dict[str, str]:
    d = _DISCLOSED.get(job)
    gen = (BLOCKED_F852 if el.CONVERSION_CREATIVE in el.JOB_PURPOSES[job] and job != el.DESIRE
           else PURPOSE_REFUSED)
    photo = SATISFIES if el.PHYSICAL_PROOF in el.JOB_PURPOSES[job] else PURPOSE_REFUSED
    return {DISCLOSED: d[0] if d else NOT_DRAWABLE, GENERATED: gen, PHOTO: photo}


def _preferred(job: str, srcs: dict[str, str]) -> str:
    # The disclosed set wherever it is truthful. Otherwise a photograph of a made sample: a
    # generated LIFESTYLE candidate is still produced and judged so the owner sees it, and it
    # stays refused while F-852 stands.
    return DISCLOSED if srcs[DISCLOSED] == SATISFIES else PHOTO


# Measured engineering gaps where the disclosed producer does not yet draw an applicable job
# (VISGATE §4 / V5). These are recorded, not hidden by dropping the role.
PRODUCT_GAPS: dict[str, dict[str, str]] = {
    "nordic-star-ornaments": {
        el.ANGLE: ("refused by the producer: 'a flat piece's back is its front'. Applicability "
                   "should follow geometry, not the category name (decision pending, V5a)"),
        el.CONSTRUCTION: ("no truthful producer yet for flat multi-piece panels (V5b)")},
}
NO_PRODUCER = "no_producer"


def plan_for_category(category: str, *, sizes: int = 1, colours: int = 1,
                      extra: dict[str, str] | None = None) -> dict:
    applicable = dict(el.gallery_jobs_for(category, sizes=sizes, colours=colours))
    applicable.update(extra or {})
    applicable.setdefault(el.PROOF, "conditional: only once a physical sample photograph "
                                    "exists (F-030 'category-specific proof')")
    roles = []
    for job in ORDER:
        if job not in applicable:
            continue
        srcs = _sources(job)
        laura, brief = LIFESTYLE_BRIEF.get(category, (False, "the finished piece in use"))
        roles.append({
            "position": len(roles) + 1, "role": ROLE_OF_JOB[job], "job": job,
            "why": applicable[job], "required_by": list(REQUIRED_BY[job]),
            "sources": srcs, "preferred_source": _preferred(job, srcs),
            "disclosed_medium": (_DISCLOSED.get(job) or (None, None, None))[1:],
            "conditional": job == el.PROOF,
            "laura": bool(job == el.LIFESTYLE and laura),
            "brief": brief if job == el.LIFESTYLE else ""})
    return {"category": category, "sizes": sizes, "colours": colours, "roles": roles,
            "image_count": len([r for r in roles if not r["conditional"]]),
            "image_count_with_conditional": len(roles)}


# A wearable template, even though none of the eight is worn: fit (photo only), front/back
# (ANGLE) and construction are added because a garment is judged on them (F-254, F-225).
def wearable_template(*, sizes: int = 1, colours: int = 1) -> dict:
    return plan_for_category("garment", sizes=sizes, colours=colours, extra={
        el.ANGLE: "front and back: a worn piece is bought on both views",
        el.CONSTRUCTION: "seams, shaping and the yoke or raglan line"})


def _listing_shape(slug: str) -> tuple[str, int, int, str]:
    from .launch_imagery import _listing_parts

    _cand, cirs, category = _listing_parts(slug)
    colours = len(cirs[0].colors or {})
    return category, len(cirs), colours, cirs[0].slug


def plan_for(slug: str) -> dict:
    """The shot plan for one Launch-0 listing (by listing slug)."""
    category, sizes, colours, primary = _listing_shape(slug)
    out = plan_for_category(category, sizes=sizes, colours=colours)
    for r in out["roles"]:
        gap = PRODUCT_GAPS.get(slug, {}).get(r["job"])
        if gap:
            r["sources"] = {**r["sources"], DISCLOSED: NO_PRODUCER}
            r["preferred_source"], r["gap"] = "none_yet", gap
    out.update(listing=slug, primary_release_slug=primary)
    return out


def all_plans() -> dict:
    from ..products import launch0

    plans = {s: plan_for(s) for s in launch0.LAUNCH0_SLUGS}
    return {"plans": plans, "wearable_template": wearable_template(),
            "basis": "publish.eligibility.gallery_jobs_for + VISGATE §2 + F-852"}


# D-W4-LAURA-FLUX3 §6: the campaign. A typical set of seven is a lifestyle hero, a product
# full view, Laura using it from another angle, a verified close-up, a second lifestyle,
# size/scale and a detail or customer-information frame. The roles adapt to the category, and
# each keeps exactly one job, because #65's one-job rule and `check_set`'s duplicate-job refusal
# still apply. The ruling's three Laura frames map onto three distinct applicable jobs:
# LIFESTYLE, SCALE ("against something a person knows": her) and COLOUR_CONTEXT ("the
# colourway ... in a room"). Under today's gates the hero stays the disclosed render: a
# generated image may not be the hero (ASSET_CONCEPT_AS_HERO). `ruling_conflicts` records
# that rather than hiding it.
CAMPAIGN_GENERATED: dict[str, str] = {
    el.LIFESTYLE: "lifestyle: Laura using the piece where it lives",
    el.SCALE: "Laura using it from another angle, which also shows its size",
    el.COLOUR_CONTEXT: "second lifestyle: the colourway in the room",
}
# W5-V1 (audit P1-c): a listing whose shot plan has no Laura is generated product-only ("The
# product alone; no person."), so its briefs never ask for her. The same three jobs, without a
# person; size is shown against everyday objects of known size.
CAMPAIGN_GENERATED_PRODUCT_ONLY: dict[str, str] = {
    el.LIFESTYLE: "lifestyle: the piece in use where it lives, no person",
    el.SCALE: "the piece from another angle beside everyday objects of known size, which "
              "also shows its size; no person",
    el.COLOUR_CONTEXT: "second lifestyle: the colourway in the room, no person",
}


# ENG-VISUAL: the campaign standard's floor. The ruling's "typical set of seven" adapts its roles
# to the category (each frame one job), so seven is the minimum a gallery is certified with,
# never a count padded to: a plan that cannot reach it is refused, not filled with repeats.
CAMPAIGN_MIN_FRAMES = 7


def campaign_standard(plan: dict) -> dict:
    """Whether a campaign plan meets the seven-frame standard: >= CAMPAIGN_MIN_FRAMES slots,
    each a distinct job. Read-only; `image_production.gallery_view` refuses on it."""
    roles = list(plan.get("roles") or [])
    jobs = [r.get("job") for r in roles]
    dup = sorted({j for j in jobs if jobs.count(j) > 1 and j is not None})
    problems = []
    if len(roles) < CAMPAIGN_MIN_FRAMES:
        problems.append({"kind": "campaign_below_standard", "frames": len(roles),
                         "minimum": CAMPAIGN_MIN_FRAMES})
    if dup:
        problems.append({"kind": "campaign_duplicate_job", "jobs": dup})
    return {"ok": not problems, "frames": len(roles), "minimum": CAMPAIGN_MIN_FRAMES,
            "problems": problems}


def campaign_briefs(laura: bool) -> dict[str, str]:
    """The generated-campaign briefs for a listing with or without Laura."""
    return CAMPAIGN_GENERATED if laura else CAMPAIGN_GENERATED_PRODUCT_ONLY


def campaign_plan(listing: str) -> dict:
    plan = plan_for(listing)
    has_lifestyle = any(r["job"] == el.LIFESTYLE for r in plan["roles"])
    laura = any(r["laura"] for r in plan["roles"])
    briefs = campaign_briefs(laura)
    slots = []
    for r in plan["roles"]:
        if r["conditional"]:
            continue
        gen = has_lifestyle and r["job"] in CAMPAIGN_GENERATED
        gap_gen = (r["sources"][DISCLOSED] == NO_PRODUCER
                   and r["sources"][GENERATED] == BLOCKED_F852)
        slots.append({**r, "generate": gen or gap_gen,
                      "laura": bool(gen and laura),
                      "campaign_role": briefs.get(r["job"], r["role"]) if gen
                      else ("product full view" if r["job"] == el.DESIRE else r["role"]),
                      "fallback": DISCLOSED if r["sources"][DISCLOSED] == SATISFIES else None,
                      "brief": r["brief"] or (briefs[r["job"]] if gen else "")})
    return {**plan, "roles": slots, "image_count": len(slots),
            "one_outfit": True, "laura_in_campaign": any(s["laura"] for s in slots),
            "ruling_conflicts": ([
                "D-W4-LAURA-FLUX3 §6 names a lifestyle hero; ASSET_CONCEPT_AS_HERO and F-852 keep "
                "a generated image out of position 1, so the hero is the disclosed product "
                "view until an owner policy decision"] if has_lifestyle else [])}


def generated_roles(plan: dict) -> list[dict]:
    """Roles the autonomous workflow generates candidates for (from a campaign plan)."""
    if not any("generate" in r for r in plan["roles"]):
        plan = campaign_plan(plan["listing"])
    return [r for r in plan["roles"] if r.get("generate")]


# ---- D-OWNER-FLUX-GALLERY: the seven-frame FLUX campaign, per family ------------------------
#
# The owner's P0 "PERFECT FLUX 3 LISTING IMAGES": a whole gallery generated from deterministic
# CIR reference renders (`eligibility.GALLERY_ROUTE`), certified only when every frame passes
# every gate on its exact bytes. Seven frames, one job each (#65 still refuses a duplicate):
#
#   1 hero (DESIRE)            5 stitch close-up (DETAIL)
#   2 full product / flat-lay  6 scale / fit / in use (SCALE)
#     (COLOUR_CONTEXT)         7 download information (CONTENTS): the deterministic
#   3 lifestyle (LIFESTYLE)      pattern-preview frame from the certified PDF, never generated
#   4 alternative / back angle
#     (ANGLE)
#
# Families adapt the briefs and where Laura appears. Garments are worn by Laura front, back and
# for fit; pillows and stuffed animals get styled rooms and texture close-ups; small goods get
# construction and usage views. Lifestyle rooms, people, angles and lighting vary; the product
# and (within a listing) Laura's outfit do not. A "fit" frame is a SCALE frame on Laura: it is
# a render, never evidence of how a made garment sits (FIT stays photograph-only).
FLUX_ROUTE = el.GALLERY_ROUTE
FLUX_SLOTS: tuple[tuple[str, str], ...] = (
    (el.DESIRE, "hero"), (el.COLOUR_CONTEXT, "colour_context"), (el.LIFESTYLE, "lifestyle"),
    (el.ANGLE, "angle"), (el.DETAIL, "detail"), (el.SCALE, "size"),
    (el.CONTENTS, "whats_included"))
WORN_FAMILY, SOFT_FAMILY, LIVED_FAMILY, SMALL_FAMILY = "worn", "soft", "lived_with", "small_goods"
_SOFT = frozenset({"pillow", "amigurumi", "toy", "stuffed_animal", "cushion"})
_SMALL = frozenset({"coaster", "placemat", "basket", "ornament", "bag", "runner", "flower",
                    "seasonal_decor", "stocking", "pet", "wall_decor"})

# family -> job -> (Laura appears, brief). The product is "the finished piece" made exactly to
# the certified pattern; briefs never describe its construction (the references carry it).
FLUX_BRIEFS: dict[str, dict[str, tuple[bool, str]]] = {
    WORN_FAMILY: {
        el.DESIRE: (True, "hero: Laura wearing the finished piece, front view, natural light"),
        el.COLOUR_CONTEXT: (False, "the finished piece laid flat, full length, every part "
                                   "visible, plain neutral surface"),
        el.LIFESTYLE: (True, "Laura wearing the finished piece outdoors or in a styled "
                             "room, relaxed and candid"),
        el.ANGLE: (True, "Laura wearing the finished piece, back view, same outfit"),
        el.DETAIL: (False, "close-up of the stitch texture and edging of the finished piece"),
        el.SCALE: (True, "Laura wearing the finished piece, three-quarter view showing how it "
                         "fits and its length on her"),
    },
    SOFT_FAMILY: {
        el.DESIRE: (False, "hero: the finished piece styled in a warm, lived-in room"),
        el.COLOUR_CONTEXT: (False, "the finished piece alone, full view, plain backdrop, "
                                   "every component visible"),
        el.LIFESTYLE: (True, "Laura holding or arranging the finished piece in a styled room"),
        el.ANGLE: (False, "the finished piece from the back or side, showing seams and "
                          "closures"),
        el.DETAIL: (False, "texture close-up of the stitches and surface of the finished "
                           "piece"),
        el.SCALE: (False, "the finished piece beside everyday objects of known size on a "
                          "sofa or bed, showing its size"),
    },
    LIVED_FAMILY: {
        el.DESIRE: (False, "hero: the finished piece in the room it lives in, soft daylight"),
        el.COLOUR_CONTEXT: (False, "the finished piece laid flat, unfolded, every edge in "
                                   "view, plain surface"),
        el.LIFESTYLE: (True, "Laura using the finished piece where it lives"),
        el.ANGLE: (False, "the finished piece folded or draped from another angle, "
                          "showing the reverse"),
        el.DETAIL: (False, "close-up of the stitch texture and motif of the finished piece"),
        el.SCALE: (True, "the finished piece with Laura, showing its size against her"),
    },
    SMALL_FAMILY: {
        el.DESIRE: (False, "hero: the finished piece in use, styled table or shelf"),
        el.COLOUR_CONTEXT: (False, "the finished piece(s) flat-lay, every piece visible, "
                                   "plain surface"),
        el.LIFESTYLE: (False, "the finished piece in everyday use, no person"),
        el.ANGLE: (False, "the finished piece from another angle showing its construction: "
                          "base, joins or back"),
        el.DETAIL: (False, "close-up of the stitch texture of the finished piece"),
        el.SCALE: (False, "the finished piece beside everyday objects of known size"),
    },
}
CONTENTS_BRIEF = ("download information: the deterministic preview of the certified US and "
                  "UK pattern PDFs (never generated)")


def flux_family(category: str) -> str:
    cat = (category or "").lower()
    if cat in el._WORN:
        return WORN_FAMILY
    if cat in _SOFT:
        return SOFT_FAMILY
    if cat in _SMALL:
        return SMALL_FAMILY
    return LIVED_FAMILY


def flux_campaign_for(category: str, *, listing: str = "") -> dict:
    """The seven-frame FLUX campaign for a category (D-OWNER-FLUX-GALLERY)."""
    family = flux_family(category)
    briefs = FLUX_BRIEFS[family]
    slots = []
    for pos, (job, role) in enumerate(FLUX_SLOTS, start=1):
        generated = job != el.CONTENTS
        laura, brief = briefs.get(job, (False, CONTENTS_BRIEF))
        slots.append({
            "position": pos, "role": role, "job": job, "route": FLUX_ROUTE,
            "why": el.JOBS[job], "required_by": list(REQUIRED_BY.get(job, ("F-254",))),
            "conditional": False, "generate": generated, "laura": bool(generated and laura),
            "campaign_role": brief.split(":")[0] if ":" in brief else role,
            "brief": brief if generated else CONTENTS_BRIEF,
            # A generated slot has no fallback in this route: a frame that fails is repaired
            # or the gallery is held, never quietly swapped for another source.
            "sources": ({DISCLOSED: "not_in_route", GENERATED: SATISFIES, PHOTO: PURPOSE_REFUSED}
                        if generated else
                        {DISCLOSED: SATISFIES, GENERATED: PURPOSE_REFUSED,
                         PHOTO: PURPOSE_REFUSED}),
            "preferred_source": GENERATED if generated else DISCLOSED,
            "disclosed_medium": ((None, None) if generated
                                 else ("PATTERN_PREVIEW", el.CUSTOMER_INFORMATION)),
            "fallback": None})
    return {"listing": listing, "category": category, "family": family, "route": FLUX_ROUTE,
            "roles": slots, "image_count": len(slots), "one_outfit": True,
            "laura_in_campaign": any(s["laura"] for s in slots), "ruling_conflicts": [],
            "basis": "D-OWNER-FLUX-GALLERY seven-frame campaign"}


def flux_campaign_plan(listing: str) -> dict:
    """`flux_campaign_for` for a Launch-0 listing (by listing slug)."""
    category, _sizes, _colours, primary = _listing_shape(listing)
    return {**flux_campaign_for(category, listing=listing), "primary_release_slug": primary}
