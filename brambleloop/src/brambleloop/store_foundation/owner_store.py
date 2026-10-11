"""Owner Store data for the Command Center (W4-STOREFRONT): catalogue, product detail, assets.

Read-only. Serves the phone Store area: the 8-product launch collection (Launch-0 plus the
catalogue-floor proposal awaiting owner decision D-FB-9), per-product readiness and quality
computed now from the CIR, listing and price facts with their basis, image status (verified
disclosed rendering or withheld), PDF availability, Etsy integration status and what Etsy lets
the shop control. Images and PDFs are served only to an owner session by the API
(`/api/cc/store/image/{build}`, `/api/cc/store/pdf/{slug}`); an unverified image is never
served. UNKNOWN is never shown as 0 or as a pass.
"""
from __future__ import annotations

from datetime import datetime, timezone

UNKNOWN = "UNKNOWN"
TERMINOLOGIES = ("US", "UK")
IMAGE_PATH = "/api/cc/store/image/{build}"
PDF_PATH = "/api/cc/store/pdf/{slug}?terms={terms}"
PREVIEW_PATH = "/cc/store-preview"

DECISION = {
    "key": "D-FB-9",
    "question": ("Open with the 5 Launch-0 patterns, or add the 3 prepared patterns so the "
                 "opening catalogue reaches the 8-product floor (launch.readiness "
                 "MIN_LISTINGS_TO_OPEN = 8)?"),
    "where": "products.launch0.CATALOGUE_FLOOR_APPROVED",
    "how": ("Owner decision only. Nothing here changes it; the 3 prepared patterns stay "
            "outside launch scope and off the customer preview until it is made."),
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _quality(build: str) -> dict:
    """Compile and certify the representative CIR now (deterministic; never a stored verdict)."""
    try:
        from ..cir.compiler import compile_cir
        from ..gates.certificate import certify
        from ..products import launch0 as l0

        cir = l0.cir_for(build)
        result = compile_cir(cir)
        cert = certify(cir)
        errors = [f for f in cert.findings
                  if str(getattr(f, "severity", "")).upper().endswith("ERROR")]
        status = "OK" if result.ok and cert.granted and not errors else "BLOCKED"
        return {"status": status, "compiles": bool(result.ok),
                "compile_warnings": len(result.warnings), "certified": bool(cert.granted),
                "certificate_errors": [str(f)[:240] for f in errors][:5],
                "release_hash": (cert.release_hash or "")[:12] or None,
                "cir_version": cir.version, "basis": "measured",
                "source": "cir.compiler.compile_cir + gates.certificate.certify (now)"}
    except Exception as exc:  # noqa: BLE001 - unknown is said, never a pass
        return {"status": UNKNOWN, "basis": "unknown",
                "reason": f"{type(exc).__name__}: {str(exc)[:200]}"}


def _listing(p: dict) -> dict:
    from ..integrations import etsy

    title = p.get("title") or ""
    return {"title": title, "title_chars": len(title), "title_max": etsy.TITLE_MAX,
            "title_ok": len(title) <= etsy.TITLE_MAX, "title_basis": p.get("title_basis"),
            "price_cad": p.get("price_cad"), "price_basis": p.get("price_basis") or UNKNOWN,
            "digital_label": p.get("digital_label"),
            "on_etsy": UNKNOWN, "on_etsy_note": ("nothing is entered on Etsy by this system; "
                                                 "the live listing state is not read here")}


def _image(build: str, verify: bool) -> dict:
    if not verify:
        return {"status": "NOT_CHECKED", "build": build}
    from .preview import hero_frame

    f = hero_frame(build)
    out = {k: v for k, v in f.items() if k != "png"}
    out["path"] = IMAGE_PATH.format(build=build) if f.get("status") == "VERIFIED" else None
    out["sha256"] = (out.get("sha256") or "")[:16] or None
    return out


def _readiness(p: dict, q: dict, img: dict) -> dict:
    """One status per product: what stands between it and a listing, with who clears it."""
    blockers = []
    if p["launch_status"] == "PROPOSED":
        blockers.append({"what": "Owner decision D-FB-9 (catalogue floor)", "clearer": "OWNER"})
    if q.get("status") != "OK":
        blockers.append({"what": f"Pattern quality: {q.get('status')}", "clearer": "COMPANY"})
    if img.get("status") not in ("VERIFIED", "NOT_CHECKED"):
        blockers.append({"what": "Listing picture withheld (did not verify)", "clearer": "COMPANY"})
    blockers.append({"what": "Shop open and listing entered on Etsy (owner sign-in)",
                     "clearer": "OWNER"})
    status = ("BLOCKED" if any(b["clearer"] == "COMPANY" for b in blockers)
              else "OWNER_GATED")
    return {"status": status, "blockers": blockers,
            "note": "Publication is the owner's authorisation and is never performed here."}


def _etsy_status(db) -> dict:
    if db is None:
        return {"status": UNKNOWN, "reason": "no database in this call"}
    try:
        from sqlalchemy import select

        from ..core.models import OAuthCredential

        with db.session() as s:
            rows = [r for r in s.scalars(select(OAuthCredential))
                    if str(r.provider or "").lower().startswith("etsy")]
            items = [{"provider": r.provider, "scopes": (r.scopes or "").split(),
                      "token_fingerprint": r.token_fingerprint,
                      "updated_at": r.updated_at.isoformat() if r.updated_at else None}
                     for r in rows]
    except Exception as exc:  # noqa: BLE001
        return {"status": UNKNOWN, "reason": f"{type(exc).__name__}: {str(exc)[:160]}"}
    if not items:
        return {"status": "NOT_CONNECTED", "items": [],
                "reason": "no Etsy OAuth credential is recorded",
                "source": "oauth_credentials"}
    scopes = sorted({sc for i in items for sc in i["scopes"]})
    return {"status": "CONNECTED", "items": items, "scopes": scopes,
            "can_write_listings": "listings_w" in scopes, "source": "oauth_credentials",
            "note": "Connection only; nothing is published by this view."}


_CACHE: dict = {}
CACHE_SECONDS = 120


def catalogue(db=None, *, verify_images: bool = True, quality: bool = True) -> dict:
    """The owner catalogue. Rendering and certifying eight designs takes seconds, so a result
    is reused for CACHE_SECONDS (its `generated_at` says when it was computed)."""
    import time

    key = (id(db), verify_images, quality)
    hit = _CACHE.get(key)
    if hit and time.monotonic() - hit[0] < CACHE_SECONDS:
        return hit[1]
    out = _catalogue(db, verify_images=verify_images, quality=quality)
    _CACHE[key] = (time.monotonic(), out)
    return out


def _catalogue(db=None, *, verify_images: bool = True, quality: bool = True) -> dict:
    from . import storefront

    rows = storefront.collection(db)
    products = []
    for p in rows:
        build = p["representative"]["build"]
        img = _image(build, verify_images)
        q = _quality(build) if quality else {"status": UNKNOWN, "basis": "unknown",
                                             "reason": "not computed in this call"}
        products.append({
            "slug": p["slug"], "name": p["name"], "summary": p["summary"],
            "description": p["description"], "section": p["section"], "kind": p["kind"],
            "launch_status": p["launch_status"], "launch_status_note": p["launch_status_note"],
            "price_cad": p["price_cad"], "digital_label": p["digital_label"],
            "sizes": p["sizes"], "variant_count": p["variant_count"],
            "representative": p["representative"], "image": img, "quality": q,
            "listing": _listing(p), "readiness": _readiness(p, q, img),
            "pdf": {"terms": list(TERMINOLOGIES),
                    "paths": {t: PDF_PATH.format(slug=p["slug"], terms=t) for t in TERMINOLOGIES},
                    "note": ("rendered on request from the current CIR; the sold file is the "
                             "released, hashed PDF")},
        })
    launch = [p for p in products if p["launch_status"] == "LAUNCH_0"]
    proposed = [p for p in products if p["launch_status"] == "PROPOSED"]
    return {
        "generated_at": _now(), "products": products,
        "counts": {"collection": len(products), "launch0": len(launch),
                   "proposed": len(proposed),
                   "images_verified": (sum(1 for p in products if p["image"].get("status") == "VERIFIED")
                                       if verify_images else None),
                   "quality_ok": (sum(1 for p in products if p["quality"].get("status") == "OK")
                                  if quality else None)},
        "decision": {**DECISION, "approved": len(proposed) == 0},
        "etsy": _etsy_status(db),
        "etsy_controls": storefront.etsy_controls(),
        "preview": {"path": PREVIEW_PATH, "default_variant": storefront.VARIANT,
                    "variants": ["storefront", "v2", "compare", "standard", "brand_face"]},
        "sources": ["store_foundation.storefront.collection", "products.launch0",
                    "store_foundation.preview.hero_frame", "cir.compiler", "gates.certificate",
                    "integrations.etsy_constraints", "oauth_credentials"],
    }


def product(db, slug: str) -> dict | None:
    cat = catalogue(db)
    return next((p for p in cat["products"] if p["slug"] == slug), None)


def image_png(build: str) -> bytes | None:
    """The verified hero frame for a collection build, or None. Never an unverified image."""
    from . import storefront
    from .preview import hero_frame

    builds = {p["representative"]["build"] for p in storefront.collection(None)}
    if build not in builds:
        return None
    f = hero_frame(build)
    return f["png"] if f.get("status") == "VERIFIED" and f.get("png") else None


def pattern_pdf(slug: str, terms: str = "US") -> tuple[bytes, str] | None:
    """The pattern PDF for a collection product, rendered now from its representative CIR."""
    from ..products import launch0 as l0
    from ..publish.pdf import build_pattern_pdf, pattern_filename
    from . import storefront

    terms = str(terms or "US").upper()
    if terms not in TERMINOLOGIES:
        return None
    rows = {p["slug"]: p for p in storefront.collection(None)}
    if slug not in rows:
        return None
    cir = l0.cir_for(rows[slug]["representative"]["build"])
    doc = build_pattern_pdf(cir, terminology=terms)
    return doc.pdf_bytes, f"{slug}-{pattern_filename(terms)}"
