"""A styled product image this company owns, made from the certified pattern and checked.

Requirements 292 and 300 both end at the same place: the company can engineer a seasonal
product, certify it and prepare its listing, and then has no photograph of the thing. Charts
and schematics render deterministically from the CIR; a styled image of the finished object
does not, and for months that half was parked on a capability that did not exist. It exists
now, so this is the half that was waiting.

Four rules, each against a specific way a generated product image goes wrong.

**It is an illustration and it says so.** Nothing here produces a photograph of an object
this company has made, because this company has not made one. The asset is generated, it is
disclosed as generated, and the gallery rules already refuse an undisclosed generated hero.
Presenting a render as a photograph of a finished item would be a fabricated proof of a
product's existence, which is the one thing a benchmark-honest build cannot do.

**The prompt is derived from the certified CIR, not written.** The colours, the form, the
motif and the finished size come from the object the compiler validated. A prompt somebody
typed is a second, unvalidated description of the product, and the two drift.

**The picture is judged against the pattern, by a describer that never sees the claim.**
`visual.inspect` describes the image and `compare` checks the description against what the
CIR says is there. A grader shown the expected answer grades toward it.

**An unmade check is not a pass.** `inspect.gate` already has three verdicts; this keeps all
three. A render whose realism checks could not be made does not become an asset.
"""
from __future__ import annotations

ACTION = "assets.owned_photography"

# The disclosure that travels with the asset. #79's rule, carried as data rather than left
# to whoever writes the listing to remember.
DISCLOSURE = ("AI-assisted illustration of the finished object, generated from this "
              "pattern's own verified data. Not a photograph of a made item.")

# Product forms that are photographed alone. The canonical model is a separate, owner-gated
# decision, and a product-first form does not wait on it (#204).
from ..visual.identity import PRODUCT_FIRST_FORMS  # noqa: E402


def form_of(cir) -> str:
    """The product's form, as the shot plan and the styling both need it."""
    slug = (cir.slug or "").lower()
    for form in PRODUCT_FIRST_FORMS:
        if form in slug:
            return form
    return (cir.construction or "").lower() or "object"


def needs_no_model(cir) -> bool:
    """Whether this product can be photographed without the canonical model.

    The distinction matters right now: the canonical identity is built and unapproved, so
    every model-bearing frame is blocked. A blanket does not care -- and #204 says a clean
    product-only hero outsells a modelled one for exactly these forms anyway.
    """
    return form_of(cir) in PRODUCT_FIRST_FORMS


def claim_for(cir, twin) -> dict:
    """What the picture has to show, taken from the certified object."""
    return {
        "shows_finished_object": True,
        "shows_worn_garment": False,
        "shows_size_reference": False,
        "colours": sorted((cir.colors or {}).keys()),
        "form": form_of(cir),
        "finished_cm": ([round(twin.width_cm), round(twin.height_cm)]
                        if twin and twin.width_cm and twin.height_cm else None),
    }


def prompt_for(cir, twin, *, occasion: str = "") -> str:
    """The render brief, derived from the CIR rather than written beside it."""
    # The colour *names*, not the hex values the twin renders with. `cir.colors` maps a
    # name to a hex code, and a prompt asking for "#1A2B3C" describes nothing to a
    # generator and nothing to a reader of this prompt either.
    names = sorted((cir.colors or {}).keys()) or ["undyed natural wool"]
    colours = (" and ".join(names) if len(names) < 3
               else ", ".join(names[:-1]) + f" and {names[-1]}")
    size = ""
    if twin and twin.width_cm and twin.height_cm:
        size = f" It measures about {twin.width_cm:.0f} by {twin.height_cm:.0f} cm."
    occasion_line = (f" Styled for {occasion}, with restraint: the occasion is a setting, "
                     f"not a costume." if occasion else "")
    return (
        f"A finished hand-crocheted {form_of(cir)} in {colours}, photographed alone on a "
        f"plain warm neutral surface in soft natural daylight.{size} The crochet fabric's "
        f"stitch texture is clearly visible and the piece lies as real crocheted fabric "
        f"lies.{occasion_line} No people, no hands, no text, no logos, no brand marks, no "
        f"packaging. The object is the entire subject of the frame."
    )


def make(db, cir, twin, *, occasion: str = "", env: dict | None = None,
         work_dir: str | None = None, generator=None, inspector=None) -> dict:
    """Render one owned product image and judge it. Returns a record, never an assertion."""
    from ..gateway import images
    from ..visual import inspect as inspection_mod

    if not needs_no_model(cir):
        return {"made": False, "slug": cir.slug,
                "why": (f"{form_of(cir)!r} is a form whose listing needs the canonical "
                        f"model, and she is built but not approved. A model-bearing frame "
                        f"is blocked rather than faked")}

    prompt = prompt_for(cir, twin, occasion=occasion)
    claim = claim_for(cir, twin)
    try:
        render = (generator(prompt, env=env, size="1024x1024", reference_urls=None)
                  if generator else
                  images.generate(prompt, env=env, size="1024x1024", work_dir=work_dir))
    except Exception as exc:  # noqa: BLE001 - a refusal is a record, not a crash
        return {"made": False, "slug": cir.slug, "prompt": prompt,
                "why": f"{type(exc).__name__}: {exc}"[:300]}

    image_ref = render.get("image_ref") or ""
    spent = float(render.get("cad") or 0.0)
    inspected = (inspector or inspection_mod.inspect_image)(image_ref, db=db, claim=claim)
    verdict = inspection_mod.gate(inspected)

    from ..visual import tournament

    return {
        "made": True,
        "slug": cir.slug,
        "version": cir.version,
        "form": form_of(cir),
        "occasion": occasion or None,
        "prompt": prompt,
        "claim": claim,
        "image": tournament._keep(image_ref),
        "image_ref": image_ref,
        "provider": render.get("provider"),
        "generated": True,
        "disclosed_as_illustration": True,
        "disclosure": DISCLOSURE,
        "inspection": {k: inspected.get(k) for k in
                       ("described", "realism_judged", "realism", "realism_unjudged",
                        "semantic", "description_error", "realism_error")},
        "verdict": verdict["verdict"],
        "why": verdict["why"],
        "usable_as_listing_asset": verdict["verdict"] == "clear",
        "spent_cad": round(spent, 4),
        "never_a_photograph": (
            "this is a generated illustration of the certified object and is disclosed as "
            "one everywhere it appears. This company has not photographed a made item, and "
            "a render presented as one would be a fabricated proof that a product exists"),
    }


def last_asset(db, *, slug: str = "") -> dict | None:
    """The most recent owned asset on file, optionally for one product.

    Read rather than regenerated: the seasonal cycle reports what exists, and a report that
    rendered an image every time somebody opened an endpoint would spend money to answer a
    question about the past.
    """
    from sqlalchemy import desc, select

    from ..core.models import AuditLog

    with db.session() as s:
        for row in s.scalars(select(AuditLog).where(AuditLog.action == ACTION)
                             .order_by(desc(AuditLog.id)).limit(20)):
            detail = row.detail or {}
            if detail.get("made") and (not slug or detail.get("slug") == slug):
                return detail
    return None
