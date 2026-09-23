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

# The rendering method. Part of what makes an existing asset count as current, for the
# reason every other versioned thing in this build learned the hard way: an asset made by a
# method that has since been corrected is not the asset the corrected method would make, and
# reading it as "already done" is how a correction never runs.
# v4, because v3 checked the render against a chart it had never shown it.
#
# The attempts and the assets belong to the method: a v3 asset is evidence about v3, and
# reading it back as "this release already has one" is how a corrected render never runs.
METHOD_VERSION = "v4-the-chart-is-shown-not-only-described"

# The disclosure that travels with the asset. #79's rule, carried as data rather than left
# to whoever writes the listing to remember.
DISCLOSURE = ("AI-assisted illustration of the finished object, generated from this "
              "pattern's own verified data. Not a photograph of a made item.")

# Product forms that are photographed alone. The canonical model is a separate, owner-gated
# decision, and a product-first form does not wait on it (#204).
from ..visual.identity import PRODUCT_FIRST_FORMS  # noqa: E402


def form_of(cir) -> str:
    """The product's form, as the shot plan and the styling both need it.

    Both vocabularies, because this knew only one of them and that made the fallback do
    the classifying. A slug with no product-first word returned the CIR's *construction*
    -- `flat_rows` for a graphghan -- and every caller then asked whether a construction
    was a product-first form. It is not, and neither is it a worn one: a construction is
    not a form at all, and the question was a category error either way.
    """
    # Hyphens normalised, because the form words are written with underscores and
    # `cottage-wall-hanging` therefore matched none of them and fell through to its
    # construction.
    slug = (cir.slug or "").lower().replace("-", "_")
    from ..visual.identity import WORN_FORMS

    # Longest first, so `earwarmer` is not read as `warmer` and `wall_hanging` beats
    # nothing: a shorter word inside a longer one would classify by accident.
    for form in sorted(PRODUCT_FIRST_FORMS | WORN_FORMS, key=len, reverse=True):
        if form in slug:
            return form
    return (cir.construction or "").lower() or "object"


def needs_no_model(cir) -> bool:
    """Whether this product can be photographed without the canonical model.

    A property of the *form*, not of the model's approval state: a blanket is shot flat
    whatever the identity register says, and #204 is that a clean product-only hero
    outsells a modelled one for exactly these forms anyway.

    Answered from the worn list rather than from the absence of the product-first one.
    `form_of` falls back to the CIR's construction when a slug carries no form word, so
    asking "is this not product-first" classed `winter-village-graphghan` -- a blanket
    whose form read as `flat_rows` -- as needing a model, along with three other flat
    catalogue products. A construction is not a form. #74 makes her the exception rather
    than the fallback, so an unclassified form is photographed as an object.
    """
    from ..visual.identity import WORN_FORMS

    return form_of(cir) not in WORN_FORMS


def model_bearing_refusal(db, cir) -> dict:
    """Why a worn form cannot be photographed yet, read rather than remembered.

    This used to be one hardcoded sentence -- "she is built but not approved" -- and on
    2026-09-22 that sentence became false while still being returned: the owner approved
    and froze the canonical identity, and a hat went on being refused for a reason that
    had expired. A refusal that states a condition rather than reading it is the same
    defect as a gate reading configuration instead of demonstrated capability, and it is
    worse in a message, because the message is what the next session believes.

    Two genuinely different states now, and they have different fixes:

      no canonical identity -- a model-bearing frame is blocked rather than faked, and
      that is the owner's decision to make;
      an approved identity and no model-bearing render path -- she exists, she is
      enforced, and nothing yet builds a frame with her in it. That is this build's work,
      not a decision.
    """
    from ..visual import model_registry

    pack = model_registry.canonical_pack(db)
    form = form_of(cir)
    if pack is None:
        return {"waiting_on": "canonical_model",
                "why": (f"{form!r} is a form whose listing needs the canonical model, and "
                        f"no canonical identity has been approved. A model-bearing frame "
                        f"is blocked rather than faked")}
    return {"waiting_on": "model_bearing_render_path",
            "why": (f"{form!r} needs the canonical model, and she is approved and frozen "
                    f"at pack version {pack.version} -- what is missing is the render "
                    f"path: nothing here yet conditions a frame on her reference and "
                    f"sends the result through the identity gate. That is buildable work "
                    f"rather than a decision, and #72/#73 is where it belongs")}


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
        f"plain warm neutral surface in soft natural daylight.{size} {motif_sentence(cir)} "
        f"The crochet fabric's stitch texture is clearly visible and the piece lies as real "
        f"crocheted fabric lies.{occasion_line} No people, no hands, no text, no logos, no "
        f"brand marks, no packaging. The object is the entire subject of the frame."
    )


def motif_sentence(cir) -> str:
    """The fabric's own motif, stated rather than left to the generator.

    The first render of this asset was a clean, believable crocheted blanket in the right
    two colours -- worked in a checkerboard, while the certified pattern makes a diamond
    lattice. A listing image whose fabric is not the fabric is the refund a buyer opens
    after making it, and it is the same failure as a beauty image with guessed
    instructions: the picture and the pattern describing different objects.
    """
    from . import motif_fidelity

    named = motif_fidelity.motif_name(cir)
    colours = len(cir.colors or {})
    count = {1: "one colour", 2: "exactly two colours", 3: "exactly three colours"}.get(
        colours, f"exactly {colours} colours")
    # Stated whether or not prose names the motif, because it is the one fabric fact that
    # is true of every certified pattern -- and it is the one the live renders kept
    # breaking, returning a three-colour granny shell for a two-colour hat.
    palette = (f"The fabric works {count}: {', '.join(sorted(cir.colors))}. No other "
               f"colour appears anywhere in the crochet.")
    if named:
        return f"The fabric is worked in this pattern's own motif: {named}. {palette}"
    # No motif in prose. Saying "plain single-colour fabric with no motif" here would be a
    # claim about the fabric made from the absence of a sentence about it -- and for every
    # product the seasonal cycle authors, that absence is guaranteed. The chart is what the
    # render is conditioned on and what the result is checked against, so the chart is what
    # the prompt points at -- and `make` passes that chart as a reference image, so the
    # thing this sentence points at is actually in the request.
    return (f"The fabric is worked exactly as the accompanying stitch chart shows, stitch "
            f"for stitch and row for row. {palette}")


def make(db, cir, twin, *, occasion: str = "", env: dict | None = None,
         work_dir: str | None = None, provider_key: str = "", generator=None,
         inspector=None, motif_judger=None) -> dict:
    """Render one owned product image and judge it. Returns a record, never an assertion."""
    from ..gateway import images
    from ..visual import inspect as inspection_mod

    from ..ops import funding

    held = funding.blocked(db)
    if held.get("blocked") and generator is None:
        # Rendering is prepaid at a different provider and would succeed. What it produced
        # could not be described, compared, gated or disclosed -- so this is money spent to
        # make something unusable, and the honest thing is to wait.
        return {"made": False, "slug": cir.slug,
                "why": ("the model provider's balance is spent, so an asset rendered now "
                        "could not be checked. " + held["why_this_stops_spending"]),
                "waiting_on": "model_provider_balance"}

    if not needs_no_model(cir):
        refusal = model_bearing_refusal(db, cir)
        return {"made": False, "slug": cir.slug, "form": form_of(cir),
                "waiting_on": refusal["waiting_on"], "why": refusal["why"]}

    from . import motif_fidelity

    prompt = prompt_for(cir, twin, occasion=occasion)
    claim = claim_for(cir, twin)

    # Named explicitly, because `generate` without one falls back to
    # `BRAMBLELOOP_IMAGE_PROVIDER` -- a variable nobody has set, which is how the first live
    # run of this job died inside the gateway with `'NoneType' object has no attribute
    # 'account'`. The benchmark already decided which model renders listing imagery; using
    # its measured leader is what that measurement was for.
    from ..visual import tournament

    provider = provider_key or tournament.preferred_provider(db, env)
    if not provider and generator is None:
        return {"made": False, "slug": cir.slug,
                "why": ("no verified image provider is available in this environment. The "
                        "capability probe records what can render; nothing can")}

    # The chart is shown, not only described.
    #
    # This path asked the generator to work a pattern "exactly as the accompanying stitch
    # chart shows" and then passed `reference_urls=None` -- so there was no accompanying
    # chart. The comment in `motif_sentence` above said the render "is conditioned on" the
    # chart and it was not: a sentence asserting a property the code did not have, which
    # is the same defect as a test asserting one.
    #
    # The consequence, read from production on 2026-09-23: `cloudline-baby-blanket` came
    # back `verdict: clear` -- every asset-truth check passed -- and `motif: mismatch`, so
    # the asset was unusable. The render was being failed for not reproducing information
    # it was never given, which is a floor nothing can clear. The model path had already
    # been fixed this way and its `product_truth` went from fail to pass on the change.
    chart = motif_fidelity.chart_image(cir, twin, work_dir=work_dir or "")
    references = [chart] if chart else None

    try:
        render = (generator(prompt, env=env, size="1024x1024", reference_urls=references)
                  if generator else
                  images.generate(prompt, env=env, provider_key=provider,
                                  size="1024x1024", work_dir=work_dir,
                                  reference_urls=references))
    except Exception as exc:  # noqa: BLE001 - a refusal is a record, not a crash
        return {"made": False, "slug": cir.slug, "prompt": prompt,
                "why": f"{type(exc).__name__}: {exc}"[:300]}

    image_ref = render.get("image_ref") or ""
    spent = float(render.get("cad") or 0.0)
    inspected = (inspector or inspection_mod.inspect_image)(image_ref, db=db, claim=claim)
    verdict = inspection_mod.gate(inspected)

    # Does the fabric in the picture work the pattern the buyer will make? Asked against the
    # chart, which renders from the same verified data as the written instructions, rather
    # than against a sentence -- a generator that produced squares will happily be told they
    # are diamonds.
    from . import motif_fidelity

    motif = motif_fidelity.check(db, image_ref, cir, twin, judger=motif_judger)

    from ..visual import tournament

    return {
        "made": True,
        "slug": cir.slug,
        "version": cir.version,
        "method_version": METHOD_VERSION,
        # A product-first listing's one frame is its hero, and #75's GALLERY check reads
        # the role: a frame with no declared job cannot be distinguished from filler.
        "role": "hero",
        "readable_at_grid": (
            None if not inspected.get("described")
            else (inspected.get("description") or {}).get("clarity") != "unreadable"),
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
        "motif_claimed": motif_sentence(cir),
        "motif": motif,
        "motif_verified": motif["verdict"] == motif_fidelity.MATCH,
        "motif_why": motif["why"],
        "usable_as_listing_asset": (verdict["verdict"] == "clear"
                                    and motif["verdict"] == motif_fidelity.MATCH),
        "usable_why": (
            "every asset-truth check passed and the fabric works the chart's pattern"
            if verdict["verdict"] == "clear" and motif["verdict"] == motif_fidelity.MATCH
            else f"motif: {motif['why']}" if verdict["verdict"] == "clear"
            else verdict["why"]),
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
            if (detail.get("made")
                    and detail.get("method_version") == METHOD_VERSION
                    and (not slug or detail.get("slug") == slug)):
                return detail
    return None


# How many times one release may be re-photographed when the asset comes back unusable.
#
# Matching `model_photography.ATTEMPTS` for the same reason: a fourth attempt is evidence
# that the method is wrong rather than the sample, and the record says so instead of paying
# to find out again.
ATTEMPTS = 3


def assets_for(db, *, slug: str, version: str) -> list[dict]:
    """Every asset this method made for this exact release, newest first."""
    from sqlalchemy import desc, select

    from ..core.models import AuditLog

    out: list[dict] = []
    with db.session() as s:
        for row in s.scalars(select(AuditLog).where(AuditLog.action == ACTION)
                             .order_by(desc(AuditLog.id)).limit(200)):
            detail = row.detail or {}
            if (detail.get("made")
                    and detail.get("method_version") == METHOD_VERSION
                    and detail.get("slug") == slug
                    and detail.get("version") == version):
                out.append(detail)
    return out


def usable_asset(db, *, slug: str, version: str) -> dict | None:
    """An asset that actually cleared its checks. The only kind a listing may use."""
    for asset in assets_for(db, slug=slug, version=version):
        if asset.get("usable_as_listing_asset"):
            return asset
    return None


def what_to_do_next(db, *, slug: str, version: str) -> dict:
    """Whether to photograph, and if not, which of two different reasons not to.

    The product-first counterpart of `model_photography.what_to_do_next`, and it exists
    because only the model path was ever given one. This path's idempotency asked whether
    a row existed for the release and answered "this release already has an owned asset"
    -- which is exactly B-631, the defect the model path was rescued from, left standing on
    the path that carries the entire shippable catalogue.

    Production, 2026-09-23: that reply came back carrying `verdict: "unjudged"`. An asset
    whose checks were never made was being reported as a finished release, every day, by a
    cadence that looked healthy while doing nothing. Unjudged is not usable, here as
    everywhere else.
    """
    good = usable_asset(db, slug=slug, version=version)
    if good:
        return {"render": False, "reason": "usable_asset_on_file",
                "why": "this release already has an asset that cleared every check",
                "verdict": good.get("verdict"),
                "attempts": len(assets_for(db, slug=slug, version=version))}

    spent = len(assets_for(db, slug=slug, version=version))
    if spent >= ATTEMPTS:
        return {"render": False, "reason": "attempts_exhausted", "attempts": spent,
                "why": (f"{spent} assets for {slug} {version} were rendered by "
                        f"{METHOD_VERSION} and none cleared its checks. A further render "
                        f"would be the same method asked the same question, so what needs "
                        f"changing is the method -- a code change and a new "
                        f"METHOD_VERSION, not more spend")}
    return {"render": True, "reason": "no_usable_asset_yet", "attempts": spent,
            "why": (f"{spent} of {ATTEMPTS} attempts used; no asset for this release has "
                    f"cleared its checks")}


def coverage(db, *, slugs: list[str], versions: dict[str, str]) -> dict:
    """Which certified products actually have a usable listing asset, and which do not.

    The question nobody was asking. `_representative_slug` returned the first product-first
    slug by row id and returned the same one every day, so one product was photographed
    for ever and the other ten never were -- while the cadence reported success. A
    catalogue-wide count is the difference between "the photography job ran" and "the
    catalogue can be listed".
    """
    usable, unusable, missing = [], [], []
    # Why each failure failed, not just that it did. Without this the next decision --
    # render the rest, or fix the method first -- cannot be made without spending to find
    # out, and tonight's whole lesson is that a method which fails every time it is asked
    # will fail the next eight times too.
    diagnosis: dict[str, dict] = {}
    for slug in slugs:
        version = versions.get(slug, "")
        if usable_asset(db, slug=slug, version=version):
            usable.append(slug)
        elif (tried := assets_for(db, slug=slug, version=version)):
            unusable.append(slug)
            latest = tried[0]
            diagnosis[slug] = {
                "attempts": len(tried),
                "verdict": latest.get("verdict"),
                "why": (latest.get("why") or "")[:300],
                "motif": (latest.get("motif") or {}).get("verdict"),
            }
        else:
            missing.append(slug)
    return {
        "certified": len(slugs),
        "with_usable_asset": sorted(usable),
        "with_only_unusable_assets": sorted(unusable),
        "with_no_asset_at_all": sorted(missing),
        "why_each_unusable_one_failed": diagnosis,
        "listable": len(usable),
        "complete": bool(slugs) and len(usable) == len(slugs),
        "why_it_is_counted": (
            "a cadence that photographs one representative product for ever reports "
            "success every day while the catalogue stays unlistable. Counting every "
            "certified product is what tells those two apart"),
    }
