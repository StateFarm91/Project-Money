"""A pattern listing needs an unedited photograph of a sample made from THIS release.

W4-LAUNCHFIX (W-IMAGEPOLICY, f8b21390, research/final_build/w4/ETSY_IMAGE_COMPLIANCE.md). Etsy's
Help Center, read through its public article API on 2026-10-27:

* 44297885802647 (edited 2026-10-16): "Craft patterns, recipes, seeds, or similar items: Include
  at least one real, unedited photo of something made using your product. AI-generated images
  cannot be the only images used to show the finished result."
* 115015663347 (edited 2026-10-22): "If you sell functional guides like patterns, recipes, or
  instructions, you'll also need to show an actual result made using your instructions, not an
  AI-generated or simulated result, so buyers know what to expect." and "Make your first
  listing photo the clearest, most realistic representation of the item buyers will receive."

So, before a pattern's draft is created or submitted for activation (`release_gates.for_publish`
runs at both), its CERTIFIED gallery must hold at least one photograph that is, all at once:

1. recorded through the one photograph intake, `publish.physical_upgrade.intake` (bytes on
   file under their SHA-256, a rights basis) -- there is no other way in;
2. attested unedited at intake (`detail.unedited is True`) and not marked edited or
   AI-processed -- a render, a generation, an owner image upload (`publish.owner_images`,
   provenance `ai_generated_owner_submitted`) or a stock image never enters that intake;
3. of this exact release: the photo row names this slug@version and its `physical_test_id`
   is a passed, completed FULL physical make bound to this release's content hash by the
   certificate's own binding (`gates.first_customer.physical_binding`) -- a photo of another
   release, of an older text, or with no sample behind it binds nothing;
4. a frame of the valid listing-set certificate for this release (so it went through
   re-certification), and the FIRST frame of it. Renders, charts and the PDF page preview
   may follow, labelled.

This gate only adds a refusal. It never satisfies or relaxes any other gate, and it encodes no
answer to whether Etsy's "AI-generated functional instructions" rule reaches Brambleloop
patterns: that is the owner's decision.
"""
from __future__ import annotations

CODE = "SAMPLE_PHOTO_REQUIRED"
PHOTO_CLASS = "PHYSICAL_PRODUCT_PHOTO"

ETSY_SOURCES = (
    {"article": "44297885802647", "edited_at": "2026-10-16T14:41:39Z",
     "quote": ("Craft patterns, recipes, seeds, or similar items: Include at least one real, "
               "unedited photo of something made using your product. AI-generated images "
               "cannot be the only images used to show the finished result.")},
    {"article": "115015663347", "edited_at": "2026-10-22T13:45:42Z",
     "quote": ("If you sell functional guides like patterns, recipes, or instructions, you'll "
               "also need to show an actual result made using your instructions, not an "
               "AI-generated or simulated result, so buyers know what to expect.")},
)


def _release(db, slug: str, version: str):
    from sqlalchemy import select

    from ..core.models import PatternVersion, Product

    with db.session() as s:
        product = s.scalar(select(Product).where(Product.slug == slug))
        pv = None if product is None else s.scalar(select(PatternVersion).where(
            PatternVersion.product_id == product.id, PatternVersion.version == version))
        if pv is None or not pv.certified or not pv.cir_json:
            return None, None
        return pv.release_hash or "", dict(pv.cir_json)


def _bound_full_makes(db, cir_json: dict) -> set:
    from ..cir.model import CIR
    from ..gates.first_customer import physical_binding
    from ..gates.risk_matrix import FULL_PHYSICAL_MAKE

    binding = physical_binding(db, CIR.from_dict(cir_json))
    classes = binding.get("bound_classes") or {}
    return {ref for ref in binding.get("bound") or []
            if classes.get(ref) == FULL_PHYSICAL_MAKE}


def qualifying_photos(db, slug: str, version: str) -> dict:
    """Every photograph on file for slug@version and why each does or does not qualify."""
    from sqlalchemy import select

    from ..core.models import PhysicalPhoto
    from .physical_upgrade import bytes_on_file

    release, cir_json = _release(db, slug, version)
    if release is None:
        return {"release": None, "qualifying": [], "rejected": [],
                "why": f"{slug}@{version} has no certified release on file"}
    try:
        bound = _bound_full_makes(db, cir_json)
    except Exception as exc:  # noqa: BLE001 - an unreadable binding binds nothing
        bound = set()
        binding_error = type(exc).__name__
    else:
        binding_error = None
    from ..core.models import PhysicalTest

    with db.session() as s:
        # A compatible-variant declaration binds another product's sample to this content for
        # pattern truth; a photograph must show a sample of THIS release itself.
        bound = {t.id for t in s.scalars(select(PhysicalTest).where(
            PhysicalTest.id.in_(list(bound) or [-1])))
            if t.product_slug == slug and t.version == version}
        photos = [(p.id, p.product_slug, p.version, p.sha256, p.rights_basis, p.state,
                   p.physical_test_id, dict(p.detail or {}))
                  for p in s.scalars(select(PhysicalPhoto).where(
                      PhysicalPhoto.product_slug == slug).order_by(PhysicalPhoto.id))]
    qualifying, rejected = [], []
    for pid, pslug, pver, sha, rights, state, test_id, detail in photos:
        why = []
        if pver != version:
            why.append(f"a photo of {pslug}@{pver or '?'}, not of this release")
        if not rights:
            why.append("no rights basis")
        if detail.get("unedited") is not True:
            why.append("not attested unedited at intake")
        if detail.get("edited") or detail.get("ai_processed"):
            why.append("marked edited or AI-processed")
        if test_id is None or test_id not in bound:
            why.append("not bound to a passed full make of this release's content"
                       + (f" (binding unreadable: {binding_error})" if binding_error else ""))
        if not why and not bytes_on_file(db, sha):
            why.append("its bytes are not in the artefact store under its SHA-256")
        (rejected if why else qualifying).append(
            {"photo_id": pid, "sha256": sha, "physical_test_id": test_id,
             **({"why": "; ".join(why)} if why else {})})
    return {"release": release, "qualifying": qualifying, "rejected": rejected}


def requirement(db, slug: str, version: str, *, release: str = "") -> dict:
    """Whether the certified gallery of slug@version leads with a qualifying sample photo.

    Returns `{"satisfied", "reasons", "qualifying", "rejected", "first_frame"}`. Unreadable is
    not satisfied."""
    try:
        q = qualifying_photos(db, slug, version)
    except Exception as exc:  # noqa: BLE001
        return {"satisfied": False, "qualifying": [], "rejected": [], "first_frame": None,
                "reasons": [f"{CODE}: the photograph evidence could not be read "
                            f"({type(exc).__name__})"]}
    out = {"satisfied": False, "qualifying": q["qualifying"], "rejected": q["rejected"],
           "first_frame": None, "etsy_sources": [s["article"] for s in ETSY_SOURCES]}
    if q.get("release") is None:
        out["reasons"] = [f"{CODE}: {q.get('why')}"]
        return out
    if not q["qualifying"]:
        detail = "; ".join(f"photo {r['photo_id']}: {r['why']}" for r in q["rejected"][:3])
        out["reasons"] = [
            f"{CODE}: no unedited photograph of a sample made from this release is on file "
            f"(Etsy Help 44297885802647: a pattern listing must 'Include at least one real, "
            f"unedited photo of something made using your product'). A render can never "
            f"satisfy this" + (f"; {detail}" if detail else "")]
        return out
    try:
        from ..runtime.etsy_ops import certified_frames

        cert = certified_frames(db, slug, version, release=release or q["release"])
    except Exception as exc:  # noqa: BLE001
        cert = {"frames": [], "problems": [f"unreadable: {type(exc).__name__}"]}
    frames = cert.get("frames") or []
    first = frames[0] if frames else None
    out["first_frame"] = None if first is None else {
        "position": first.get("position"), "sha256": first.get("sha256")}
    shas = {p["sha256"] for p in q["qualifying"]}
    if first is None or cert.get("problems"):
        out["reasons"] = [f"{CODE}: the qualifying photograph is not in a valid listing-set "
                          f"certificate for this release yet (re-certification after "
                          f"physical_upgrade); {'; '.join(cert.get('problems') or [])[:200]}"]
        return out
    if str(first.get("sha256") or "") not in shas:
        out["reasons"] = [f"{CODE}: the first image of the certified gallery is not the "
                          f"unedited sample photograph (Etsy Help 115015663347: the first "
                          f"photo should be 'the clearest, most realistic representation of "
                          f"the item buyers will receive')"]
        return out
    out.update(satisfied=True, reasons=[])
    return out


def disclosure_copy(*, photographed_sample: bool) -> str:
    """The images disclosure, generated from whether a qualifying photo exists. Without one it
    is exactly `platform_policy.DISCLOSURES["disclosed_render"]` (which says no sample has
    been photographed); with one it says which images are renders and which is the photo."""
    from ..gates.platform_policy import DISCLOSURES
    from ..visual.render_contract import DISCLOSURE

    if not photographed_sample:
        return DISCLOSURES["disclosed_render"]
    return ("About the images: the first image is an unedited photograph of a sample made "
            "from this pattern. Every image captioned \"" + DISCLOSURE + "\" is a digital "
            "rendering drawn from the pattern itself at the stated gauge, with a centimetre "
            "scale, and is not a photograph. Your finished piece will vary with yarn and "
            "tension.")


def copy_problems(description: str, *, photographed_sample: bool) -> list[str]:
    """The listing copy must say what the gallery is: the no-photo sentence never stands
    beside a photo, and the photo sentence never stands without one."""
    from ..gates.platform_policy import DISCLOSURES

    text = description or ""
    if photographed_sample and DISCLOSURES["disclosed_render"] in text:
        return [f"{CODE}: the listing copy still says no sample has been photographed; "
                f"regenerate the disclosure (listing.seo) now that the photograph exists"]
    if not photographed_sample and disclosure_copy(photographed_sample=True) in text:
        return [f"{CODE}: the listing copy claims an unedited sample photograph that the "
                f"certified gallery does not lead with"]
    return []
