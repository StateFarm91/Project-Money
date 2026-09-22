"""A listing frame with the canonical model in it, conditioned on her and checked after.

The path #72, #130 and #202 all waited on, and the one that kept #300 from completing:
she was approved, frozen and enforced, and nothing built a frame with her in it. Every
worn form refused, correctly, with `waiting_on: model_bearing_render_path`.

The shape is the whole point, and it is the opposite of trusting the generator.

**Conditioned, not described.** The render is given the frozen pack's own reference image.
A prompt that says "dark brunette, light eyes" is a description of a type and produces a
different woman every time, which is exactly what the identity lock exists to prevent. The
reference goes in as a reference.

**Verified afterwards by something that did not render it.** Conditioning is a request, not
a result: a provider may ignore it, drift, or return a plausible stranger. So the frame is
described by a vision model that never sees the prompt, compared against the *persisted*
pack, and judged by `identity.drift_check` -- the same function the release gate uses. The
generator is never asked whether it complied.

**Six independent floors, none of which can cover for another.** Face identity and
whole-person morphology are two (a familiar face over a different body is the failure the
owner named). Product truth is the third: the motif judge compares the fabric against the
deterministically rendered chart, so a beautiful photograph of the wrong crochet fails.
Photographic realism is the fourth and the asset-truth checks are the fifth. The sixth is
the character bible -- makeup, expression, wardrobe and lighting -- because the identity
gate would accept exactly the right woman in glamour makeup under coloured light in a
printed dress that competes with the crochet, every dimension it measures still matching.
A frame ships only when all six clear, and `unmeasurable` is never a pass in any of them.

**The product stays the hero.** She is the recurring brand identity and the crochet is what
is being sold. `visual.bible` holds those styling rules as closed questions about the
rendered frame, so #202 is enforced rather than merely requested.
"""
from __future__ import annotations

ACTION = "assets.model_photography"

# Part of what decides whether a frame on file answers the question being asked. A frame
# rendered by an earlier method is evidence about that method, and reading it back as
# "this release already has one" is how a corrected prompt quietly never runs.
METHOD_VERSION = "v6-the-portrait-is-sent-as-a-jpeg-and-styling-is-read-off-the-fit-frame"

# How many times one release may be re-rendered when the frame comes back unusable.
#
# The first live frame was a head-and-shoulders crop: face identity passed and three floors
# returned `unverifiable` because nothing in the frame could answer them. That is a failed
# render, not a finding about the product -- and the handler's idempotency read it as "this
# release already has a model frame", which is the existence of a row standing in for the
# capability the row was supposed to evidence.
#
# Bounded at three for the reason the reference pack bounds its own retries: a fourth
# attempt is evidence that the prompt is wrong rather than the sample, and the record says
# so instead of paying to find out again. Each attempt is one render and four judgements,
# about CA$0.30.
ATTEMPTS = 3

DISCLOSURE = (
    "Illustration generated from the certified pattern, featuring Brambleloop's fictional "
    "brand model. Not a photograph of a made item and not a photograph of a real person.")


class ModelPhotographyRefused(ValueError):
    """A model frame that would be built without her, or shipped without being checked."""


def prompt_for(cir, twin, pack, *, occasion: str = "", plan: str = "") -> str:
    """What to render: the certified product, on her, photographed like a photograph.

    Her appearance is carried by the reference image rather than by adjectives -- the pack
    fields are the thing the result is *checked* against, and putting them in the prompt as
    well would let a generator satisfy the words while missing the woman.
    """
    from ..publish import owned_photography as owned
    from ..visual import bible, brief, photoreal

    form = owned.form_of(cir)
    occasion_line = f" styled for {occasion}," if occasion else ""
    return (
        f"A photograph of the woman in the reference image wearing or presenting a "
        f"handmade crochet {form}.{occasion_line} "
        f"{owned.motif_sentence(cir)} "
        f"The {form} measures roughly {twin.width_cm:.0f} by {twin.height_cm:.0f} cm in "
        f"{', '.join(cir.colors)}. "
        f"She is the same woman as the reference image: same face, same hair, same "
        f"colouring, same build and proportions. "
        f"{plan or SHOT_PLAN} "
        f"{brief.PRODUCT_IS_THE_HERO} She is present to show fit, scale and use. "
        f"{bible.direction()} "
        f"{photoreal.DIRECTION}"
    )


# What the frame has to *show*, as opposed to what it has to contain.
#
# The first live model frame came back with three of its five floors `unverifiable`: a
# head-and-shoulders crop of a woman in a hat cannot evidence bust or torso, and fabric
# that small cannot be compared against a stitch chart. Those are honest readings and the
# right answer is not to relax the floors -- the owner's rule is that unmeasurable is
# never a pass -- but to render a frame that can actually satisfy them. A three-quarter
# shot showing the product and the upper body is an ordinary listing photograph and it is
# checkable; a tight crop is neither.
SHOT_PLAN = (
    "Framed three-quarter length, from above the head to below the hips, standing "
    "squarely and evenly lit, so that her shoulders, chest, torso, waist and hips are all "
    "clearly visible and nothing obscures them. The crochet is worn and clearly visible."
)

# And the frame that answers the other question, because one frame cannot answer both.
#
# The first correctly-framed live attempt proved it. A three-quarter shot of a woman in a
# crocheted hat shows the whole body -- and the motif judge read the fabric as
# `unmeasurable` and said exactly what it needed: "a closer or flatter frame". At 1024
# pixels a hat occupies a few hundred of them and no stitch in it can be counted. Pulling
# in far enough to count stitches loses the hips; standing back far enough to show the hips
# loses the stitches. The two floors are not in tension because either is wrong: they are in
# tension because they are questions about different photographs.
#
# Which is what a listing gallery has always been. #75 asks for "a complete purposeful
# sequence without filler" and this is the smallest sequence that is complete: one frame
# that shows the garment on a body and one that shows the fabric it is made of.
DETAIL_PLAN = (
    "A close photograph of the crocheted piece as she is wearing it, filling the frame, "
    "sharply in focus and lit so the fabric's texture is modelled by the light. Close "
    "enough that individual stitches, the repeat of the pattern and the way the colours "
    "are placed can all be counted and followed. Part of her is in the frame so the piece "
    "is plainly being worn rather than laid flat."
)

# Each shot, what to ask for, and which floor it is the authority on. The shared floors --
# realism, styling and asset truth -- are asked of every frame, because any frame that
# ships is a customer-facing asset in its own right.
SHOTS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    # Styling belongs here rather than in the shared set. Five of the bible's fourteen
    # questions are about wardrobe, and a frame cropped to a hat cannot answer one of
    # them -- the first live sequence returned `styling: unjudged` on the detail frame
    # for exactly that reason, which made a sixth floor unclearable by the same mistake
    # the morphology floor had just been rescued from. The fit frame shows the whole
    # styling, so the fit frame is asked. A styling *failure* seen anywhere still blocks.
    ("fit", SHOT_PLAN, ("face_identity", "whole_person_morphology", "styling")),
    ("detail", DETAIL_PLAN, ("product_truth",)),
)

SHARED_FLOORS: tuple[str, ...] = ("photographic_realism", "asset_truth")


def _merge_observations(face_seen: dict, body_seen: dict, *, has_body: bool) -> dict:
    """One reading of thirteen dimensions, each taken from the comparison that could see it.

    Never permissive about the half that was not looked at. With no body reference the
    morphology dimensions are `unmeasurable` -- which is what they honestly are, and which
    `drift_check` correctly refuses to pass.
    """
    from ..visual import identity

    seen = {d: face_seen.get(d, identity.UNMEASURABLE) for d in identity.FACE_DIMENSIONS}
    for d in identity.MORPHOLOGY_DIMENSIONS:
        seen[d] = (body_seen.get(d, identity.UNMEASURABLE) if has_body
                   else identity.UNMEASURABLE)
    return seen


def make(db, cir, twin, *, shot: str = "fit", occasion: str = "", env: dict | None = None,
         work_dir: str | None = None, provider_key: str = "", generator=None,
         observer=None, inspector=None, motif_judger=None, realism_judger=None,
         styling_judger=None) -> dict:
    """Render one frame of the sequence and check it. A record, never a claim.

    The frame reports every reading it could make and which floors it is the authority on.
    It does not decide whether the listing may use the sequence -- `sequence` does, because
    a decision made per frame cannot see that the fit shot answered for the body and the
    detail shot answered for the fabric.
    """
    from ..gateway import images
    from ..ops import funding
    from ..publish import motif_fidelity, owned_photography as owned
    from ..visual import bible, freeze, identity, inspect as inspection_mod
    from ..visual import model_registry, photoreal, tournament

    pack = model_registry.canonical_pack(db)
    if pack is None:
        return {"made": False, "slug": cir.slug, "waiting_on": "canonical_model",
                "why": ("no canonical identity is frozen, so there is nobody to condition "
                        "on and nothing to check the result against. A model frame built "
                        "now would be a stranger with a caption")}

    refs = freeze.reference_paths(db)
    reference = refs["face"] or str(pack.fields.get("reference_image") or "")
    body_reference = refs["body"]
    if not reference:
        return {"made": False, "slug": cir.slug, "waiting_on": "canonical_model",
                "why": ("the frozen pack carries no reference image, so conditioning is "
                        "impossible and the comparison afterwards would have nothing to "
                        "compare against")}

    held = funding.blocked(db)
    if held.get("blocked") and generator is None:
        return {"made": False, "slug": cir.slug, "waiting_on": "model_provider_balance",
                "why": ("the model provider's balance is spent, so a frame rendered now "
                        "could not be described, compared or gated. "
                        + held["why_this_stops_spending"])}

    provider = provider_key or tournament.preferred_provider(db, env)
    if not provider and generator is None:
        return {"made": False, "slug": cir.slug,
                "why": "no verified image provider is available in this environment"}

    plan = dict((name, text) for name, text, _ in SHOTS).get(shot, SHOT_PLAN)
    answers_for = dict((name, floors) for name, _, floors in SHOTS).get(shot, ())
    prompt = prompt_for(cir, twin, pack, occasion=occasion, plan=plan)
    claim = owned.claim_for(cir, twin)

    try:
        conditioning = [r for r in (reference, body_reference) if r]
        render = (generator(prompt, env=env, size="1024x1024",
                            reference_urls=conditioning)
                  if generator else
                  images.generate(prompt, env=env, provider_key=provider,
                                  size="1024x1024", work_dir=work_dir,
                                  reference_urls=conditioning))
    except Exception as exc:  # noqa: BLE001 - a refusal is a record, not a crash
        return {"made": False, "slug": cir.slug, "shot": shot, "prompt": prompt,
                "why": f"{type(exc).__name__}: {exc}"[:300]}

    image_ref = render.get("image_ref") or ""
    spent = float(render.get("cad") or 0.0)
    if not image_ref:
        return {"made": False, "slug": cir.slug, "shot": shot, "prompt": prompt,
                "why": "the provider answered without an image"}

    # 1 and 2. Identity, by something that did not render it and never saw the prompt --
    # and asked of the reference that is in a position to answer. A portrait cannot say
    # anything about a waist, so comparing the whole frame against the portrait returned
    # `unmeasurable` for every body dimension however well the frame was shot. Face against
    # the portrait, body against the pack's own body frame.
    look = observer or model_registry.compare_identity
    face_seen = look(db, reference, image_ref)
    body_seen = look(db, body_reference, image_ref) if body_reference else {}
    seen = _merge_observations(face_seen, body_seen, has_body=bool(body_reference))
    drift = identity.drift_check(seen, pack)

    # 3. Product truth, against the chart rather than against a sentence.
    motif = motif_fidelity.check(db, image_ref, cir, twin, judger=motif_judger)

    # 4. Photographic realism, and the asset-truth checks that were already here.
    realism = photoreal.gate((realism_judger or photoreal.judge)(image_ref, db=db))
    inspected = (inspector or inspection_mod.inspect_image)(image_ref, db=db, claim=claim)
    asset_truth = inspection_mod.gate(inspected)

    # 5. The character bible: makeup, expression, wardrobe and lighting (#73, #202). The
    # identity gate would accept exactly the right woman in glamour makeup under coloured
    # light in a printed dress, because every dimension it measures would still match.
    styling = bible.gate((styling_judger or bible.judge)(image_ref, db=db))

    floors = {
        "face_identity": drift["face"].get("verdict", "unverifiable"),
        "whole_person_morphology": drift["morphology"].get("verdict", "unverifiable"),
        "product_truth": ("pass" if motif["verdict"] == motif_fidelity.MATCH
                          else "fail" if motif["verdict"] == motif_fidelity.MISMATCH
                          else "unverifiable"),
        "photographic_realism": ("pass" if realism["verdict"] == "clear"
                                 else "fail" if realism["verdict"] == "blocked"
                                 else "unverifiable"),
        "asset_truth": ("pass" if asset_truth["verdict"] == "clear"
                        else "fail" if asset_truth["verdict"] == "blocked"
                        else "unverifiable"),
        "styling": ("pass" if styling["verdict"] == "clear"
                    else "fail" if styling["verdict"] == "blocked"
                    else "unverifiable"),
    }
    # Every floor must say `pass`. Not an average, not a majority, and `unverifiable` is
    # not on the pass side of the line -- which is the whole reason the verdicts are three
    # -valued rather than boolean.
    usable = all(v == "pass" for v in floors.values())

    description = (inspected.get("description") or {})
    return {
        "made": True,
        "shot": shot,
        # The gallery role this frame plays, which is what #75's GALLERY check reads: a
        # frame with no declared job is filler by definition. The shot names are the
        # gallery's own vocabulary, so a sequence is a gallery rather than two pictures.
        "role": shot,
        # And whether it survives Etsy's search thumbnail, which is where the buying
        # decision actually starts. `None` when nobody looked -- not True.
        "readable_at_grid": (None if not inspected.get("described")
                             else description.get("clarity") != "unreadable"),
        "answers_for": list(answers_for),
        "slug": cir.slug,
        "version": cir.version,
        "method_version": METHOD_VERSION,
        "form": owned.form_of(cir),
        "occasion": occasion or None,
        "carries_model": True,
        "prompt": prompt,
        "claim": claim,
        "image": tournament._keep(image_ref, db=db, why=(
            "a model-bearing listing frame: the customer-facing evidence for #72")),
        "image_ref": image_ref,
        "provider": render.get("provider") or provider,
        "generated": True,
        "disclosed_as_illustration": True,
        "disclosure": DISCLOSURE,
        "conditioned_on": {
            "reference_image": reference,
            "body_reference_image": body_reference,
            "body_reference_frame": refs["body_frame"],
            "why_two": refs["why_the_face_is_separate"],
            "pack_version": pack.version,
            "approved_at": pack.approved_by_owner_at,
            "how": ("passed to the provider as a reference image, not described in words. "
                    "A prompt that lists her features produces a different woman who "
                    "matches the adjectives"),
        },
        "identity": {
            "observed": seen,
            "observed_face": face_seen,
            "observed_body": body_seen,
            "face": drift["face"],
            "morphology": drift["morphology"],
            "verdict": drift["verdict"],
            "blocks_release": drift["blocks_release"],
            "checked_by": ("a vision model that never saw the prompt, against the pack "
                           "read out of the database -- the generator is never asked "
                           "whether it complied"),
        },
        "motif": motif,
        "motif_verified": motif["verdict"] == motif_fidelity.MATCH,
        "photographic_realism": realism,
        "inspection": {k: inspected.get(k) for k in
                       ("described", "realism_judged", "realism", "realism_unjudged",
                        "semantic", "description_error", "realism_error")},
        "asset_truth": asset_truth,
        "styling": styling,
        "bible_version": bible.BIBLE_VERSION,
        "floors": floors,
        "usable_as_listing_asset": usable,
        "why": ("every floor cleared" if usable else
                "; ".join(f"{k}: {v}" for k, v in sorted(floors.items()) if v != "pass")),
        "floors_never_average": (
            "face identity, whole-person morphology, product truth, photographic realism, "
            "asset truth and styling are six independent floors. A frame ships when every "
            "one of them says pass; `unverifiable` is not on the pass side, because a "
            "check nobody could make is not a check that passed"),
        "spent_cad": round(spent, 4),
    }


FLOORS: tuple[str, ...] = ("face_identity", "whole_person_morphology", "product_truth",
                           "photographic_realism", "asset_truth", "styling")


def sequence(db, cir, twin, **kw) -> dict:
    """The smallest complete gallery, and the only thing that decides whether it may ship.

    Two frames, because the floors ask about two photographs. The fit shot is the authority
    on the body; the detail shot is the authority on the fabric. Realism, styling and asset
    truth are asked of both, because either frame is a customer-facing asset on its own.

    Combined conservatively in both directions: an authoritative frame's verdict stands even
    when another frame happens to read better, and a shared floor takes the worst answer any
    frame gave. Nothing here averages, and `unverifiable` is never on the pass side.
    """
    frames: list[dict] = []
    for name, _, _floors in SHOTS:
        frame = make(db, cir, twin, shot=name, **kw)
        frames.append(frame)
        if not frame.get("made"):
            # One frame that could not be rendered is a sequence that does not exist.
            # Reported as the refusal it is, carrying the first frame's reason rather than
            # a summary of a set that was never completed.
            return {"made": False, "slug": cir.slug, "shot": name,
                    "waiting_on": frame.get("waiting_on"),
                    "frames": frames, "usable_as_listing_asset": False,
                    "why": frame.get("why", "")}

    floors = _combine_floors(frames)
    usable = all(v == "pass" for v in floors.values())
    first = frames[0]
    return {
        "made": True,
        "slug": cir.slug,
        "version": cir.version,
        "method_version": METHOD_VERSION,
        "form": first.get("form"),
        "occasion": first.get("occasion"),
        "carries_model": True,
        "generated": True,
        "disclosed_as_illustration": True,
        "disclosure": DISCLOSURE,
        "conditioned_on": first.get("conditioned_on"),
        "shots": [f["shot"] for f in frames],
        "frames": frames,
        "image": first.get("image"),
        "image_ref": first.get("image_ref"),
        "provider": first.get("provider"),
        "floors": floors,
        "floor_sources": {name: _authority_for(name) for name in FLOORS},
        "usable_as_listing_asset": usable,
        "why": ("every floor cleared across the sequence" if usable else
                "; ".join(f"{k}: {v}" for k, v in sorted(floors.items()) if v != "pass")),
        "why_two_frames": (
            "a three-quarter frame shows the body and cannot show a stitch; a frame close "
            "enough to count stitches cannot show the hips. The floors are not in tension "
            "because either is wrong -- they are questions about different photographs, "
            "which is what a listing gallery has always been"),
        "floors_never_average": (
            "each floor is taken from the frame in a position to answer it, and the shared "
            "floors take the worst answer any frame gave. A sequence ships when every floor "
            "says pass; `unverifiable` is not on the pass side, because a check nobody "
            "could make is not a check that passed"),
        "spent_cad": round(sum(float(f.get("spent_cad") or 0.0) for f in frames), 4),
    }


def _authority_for(floor: str) -> str:
    """Which shot decides a floor. Shared floors are decided by all of them."""
    for name, _, floors in SHOTS:
        if floor in floors:
            return name
    return "every frame"


_WORST = {"fail": 0, "unverifiable": 1, "pass": 2}


def _combine_floors(frames: list[dict]) -> dict:
    out: dict[str, str] = {}
    for floor in FLOORS:
        source = _authority_for(floor)
        relevant = [f for f in frames
                    if source == "every frame" or f.get("shot") == source]
        readings = [str((f.get("floors") or {}).get(floor, "unverifiable"))
                    for f in relevant]
        # No reading at all is `unverifiable`, not a pass. A floor whose authoritative
        # frame is missing has not been checked, and saying so is the whole point.
        verdict = (min(readings, key=lambda v: _WORST.get(v, 1)) if readings
                   else "unverifiable")

        # An authoritative frame decides what `unverifiable` means -- the detail shot
        # cannot answer for hips and should not drag the body floor down for it. It does
        # not get to overrule a failure seen elsewhere: a face that drifted in the detail
        # frame is a face that drifted, and that frame ships too.
        if any(str((f.get("floors") or {}).get(floor)) == "fail" for f in frames):
            verdict = "fail"
        out[floor] = verdict
    return out


def _frames(db, *, slug: str = "", limit: int = 60) -> list[dict]:
    """Every frame this method rendered, newest first."""
    from sqlalchemy import desc, select

    from ..core.models import AuditLog

    out: list[dict] = []
    with db.session() as s:
        for row in s.scalars(select(AuditLog).where(AuditLog.action == ACTION)
                             .order_by(desc(AuditLog.id)).limit(limit)):
            detail = row.detail or {}
            if (detail.get("made")
                    and detail.get("method_version") == METHOD_VERSION
                    and (not slug or detail.get("slug") == slug)):
                out.append(detail)
    return out


def last_asset(db, *, slug: str = "") -> dict | None:
    """The most recent model-bearing frame on file, optionally for one product."""
    frames = _frames(db, slug=slug, limit=20)
    return frames[0] if frames else None


def usable_asset(db, *, slug: str = "", version: str = "") -> dict | None:
    """A frame that actually cleared every floor. The only kind a listing may use."""
    for frame in _frames(db, slug=slug):
        if frame.get("usable_as_listing_asset") and (not version
                                                     or frame.get("version") == version):
            return frame
    return None


def attempts_for(db, *, slug: str, version: str) -> int:
    """How many times this method has already tried this exact release."""
    return sum(1 for f in _frames(db, slug=slug) if f.get("version") == version)


def what_to_do_next(db, *, slug: str, version: str) -> dict:
    """Whether to render, and if not, which of two different reasons not to.

    Three outcomes rather than two, because "this release has a usable frame" and "this
    release has burned its attempts on frames that failed" need opposite next moves and
    only one of them is good news. The handler used to conflate them into "already has a
    model frame", which reported an unusable frame as a finished one.
    """
    good = usable_asset(db, slug=slug, version=version)
    if good:
        return {"render": False, "reason": "usable_frame_on_file",
                "why": "this release already has a frame that cleared every floor",
                "attempts": attempts_for(db, slug=slug, version=version)}

    spent = attempts_for(db, slug=slug, version=version)
    if spent >= ATTEMPTS:
        return {"render": False, "reason": "attempts_exhausted", "attempts": spent,
                "why": (f"{spent} frames for {slug} {version} were rendered by "
                        f"{METHOD_VERSION} and none cleared every floor. A further render "
                        f"would be the same method asked the same question, so what needs "
                        f"changing is the method -- which is a code change and a new "
                        f"METHOD_VERSION, not more spend")}
    return {"render": True, "reason": "no_usable_frame_yet", "attempts": spent,
            "why": (f"{spent} of {ATTEMPTS} attempts used; no frame for this release has "
                    f"cleared every floor")}
