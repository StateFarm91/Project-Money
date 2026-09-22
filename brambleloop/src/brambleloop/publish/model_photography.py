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

**Four independent floors, none of which can cover for another.** Face identity and
whole-person morphology are two (a familiar face over a different body is the failure the
owner named). Product truth is the third: the motif judge compares the fabric against the
deterministically rendered chart, so a beautiful photograph of the wrong crochet fails.
Photographic realism is the fourth. A frame ships only when all four clear, and
`unmeasurable` is never a pass in any of them.

**The product stays the hero.** She is the recurring brand identity and the crochet is what
is being sold; the brief's styling rules are in the prompt and #202 is the check on them.
"""
from __future__ import annotations

ACTION = "assets.model_photography"
METHOD_VERSION = "v1-conditioned-on-the-frozen-pack-and-verified-after"

DISCLOSURE = (
    "Illustration generated from the certified pattern, featuring Brambleloop's fictional "
    "brand model. Not a photograph of a made item and not a photograph of a real person.")


class ModelPhotographyRefused(ValueError):
    """A model frame that would be built without her, or shipped without being checked."""


def prompt_for(cir, twin, pack, *, occasion: str = "") -> str:
    """What to render: the certified product, on her, photographed like a photograph.

    Her appearance is carried by the reference image rather than by adjectives -- the pack
    fields are the thing the result is *checked* against, and putting them in the prompt as
    well would let a generator satisfy the words while missing the woman.
    """
    from ..publish import owned_photography as owned
    from ..visual import brief, photoreal

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
        f"{brief.PRODUCT_IS_THE_HERO} The crochet is sharply in focus and occupies the "
        f"frame; she is present to show fit, scale and use. "
        f"{photoreal.DIRECTION}"
    )


def make(db, cir, twin, *, occasion: str = "", env: dict | None = None,
         work_dir: str | None = None, provider_key: str = "", generator=None,
         observer=None, inspector=None, motif_judger=None, realism_judger=None) -> dict:
    """Render one model-bearing frame and check it four ways. A record, never a claim."""
    from ..gateway import images
    from ..ops import funding
    from ..publish import motif_fidelity, owned_photography as owned
    from ..visual import identity, inspect as inspection_mod, model_registry, photoreal
    from ..visual import tournament

    pack = model_registry.canonical_pack(db)
    if pack is None:
        return {"made": False, "slug": cir.slug, "waiting_on": "canonical_model",
                "why": ("no canonical identity is frozen, so there is nobody to condition "
                        "on and nothing to check the result against. A model frame built "
                        "now would be a stranger with a caption")}

    reference = str(pack.fields.get("reference_image") or "")
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

    prompt = prompt_for(cir, twin, pack, occasion=occasion)
    claim = owned.claim_for(cir, twin)

    try:
        render = (generator(prompt, env=env, size="1024x1024",
                            reference_urls=[reference])
                  if generator else
                  images.generate(prompt, env=env, provider_key=provider,
                                  size="1024x1024", work_dir=work_dir,
                                  reference_urls=[reference]))
    except Exception as exc:  # noqa: BLE001 - a refusal is a record, not a crash
        return {"made": False, "slug": cir.slug, "prompt": prompt,
                "why": f"{type(exc).__name__}: {exc}"[:300]}

    image_ref = render.get("image_ref") or ""
    spent = float(render.get("cad") or 0.0)
    if not image_ref:
        return {"made": False, "slug": cir.slug, "prompt": prompt,
                "why": "the provider answered without an image"}

    # 1 and 2. Identity, by something that did not render it and never saw the prompt.
    seen = (observer or model_registry.compare_identity)(db, reference, image_ref)
    drift = identity.drift_check(seen, pack)

    # 3. Product truth, against the chart rather than against a sentence.
    motif = motif_fidelity.check(db, image_ref, cir, twin, judger=motif_judger)

    # 4. Photographic realism, and the asset-truth checks that were already here.
    realism = photoreal.gate((realism_judger or photoreal.judge)(image_ref, db=db))
    inspected = (inspector or inspection_mod.inspect_image)(image_ref, db=db, claim=claim)
    asset_truth = inspection_mod.gate(inspected)

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
    }
    # Every floor must say `pass`. Not an average, not a majority, and `unverifiable` is
    # not on the pass side of the line -- which is the whole reason the verdicts are three
    # -valued rather than boolean.
    usable = all(v == "pass" for v in floors.values())

    return {
        "made": True,
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
            "pack_version": pack.version,
            "approved_at": pack.approved_by_owner_at,
            "how": ("passed to the provider as a reference image, not described in words. "
                    "A prompt that lists her features produces a different woman who "
                    "matches the adjectives"),
        },
        "identity": {
            "observed": seen,
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
        "floors": floors,
        "usable_as_listing_asset": usable,
        "why": ("every floor cleared" if usable else
                "; ".join(f"{k}: {v}" for k, v in sorted(floors.items()) if v != "pass")),
        "floors_never_average": (
            "face identity, whole-person morphology, product truth, photographic realism "
            "and asset truth are five independent floors. A frame ships when every one of "
            "them says pass; `unverifiable` is not on the pass side, because a check "
            "nobody could make is not a check that passed"),
        "spent_cad": round(spent, 4),
    }


def last_asset(db, *, slug: str = "") -> dict | None:
    """The most recent model-bearing frame on file, optionally for one product."""
    from sqlalchemy import desc, select

    from ..core.models import AuditLog

    with db.session() as s:
        for row in s.scalars(select(AuditLog).where(AuditLog.action == ACTION)
                             .order_by(desc(AuditLog.id)).limit(20)):
            detail = row.detail or {}
            if (detail.get("made")
                    and detail.get("method_version") == METHOD_VERSION
                    and (not slug or detail.get("slug") == slug)):
                return detail
    return None
