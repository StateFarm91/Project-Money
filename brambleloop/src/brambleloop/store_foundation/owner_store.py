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
    "key": "CAP-1",
    "question": ("Approve the 3 products CAP-1 brought into Launch-0 scope? The owner approved "
                 "the cap change 5 -> 8 as configuration only (launch0.CATALOGUE_FLOOR_APPROVED); "
                 "the products themselves are not approved, drafted or published."),
    "where": "products.launch0.CATALOGUE_FLOOR_APPROVED (cap) + per-product publication approval",
    "how": ("Each product still has to pass its gates and receive your publication approval. "
            "Until every gate passes it stays off the customer preview."),
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
        return {"status": "NOT_CHECKED", "build": build, "path": None}
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
        blockers.append({"what": "Owner decision on the catalogue floor (cap)", "clearer": "OWNER"})
    if p["launch_status"] == "CAP1_SCOPE":
        blockers.append({"what": "Product not approved: gates pending (CAP-1 is configuration only)",
                         "clearer": "OWNER"})
    if q.get("status") != "OK":
        blockers.append({"what": f"Pattern quality: {q.get('status')}", "clearer": "COMPANY"})
    if img.get("pieces_finding"):
        blockers.append({"what": f"Listing picture misleading: {img['pieces_finding']}",
                         "clearer": "COMPANY"})
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
#: How long a request waits for a full (pictures + quality) catalogue before it is answered with
#: the quick one. The full one keeps computing in the background and is cached for the next call.
FULL_WAIT_SECONDS = 4.0
_WARMING: dict = {}


def catalogue(db=None, *, verify_images: bool = True, quality: bool = True,
              wait: float | None = None) -> dict:
    """The owner catalogue. Rendering and checking eight pictures takes tens of seconds on a
    cold process, so the full result is computed once in the background and reused for
    CACHE_SECONDS (`generated_at` says when). A phone never waits on that: after `wait` seconds
    it gets the quick catalogue -- same products, prices and listings, pictures and quality
    marked NOT_CHECKED / UNKNOWN (never a pass) -- with `preparing: True`."""
    import threading
    import time

    key = (id(db), verify_images, quality)
    hit = _CACHE.get(key)
    if hit and time.monotonic() - hit[0] < CACHE_SECONDS:
        return hit[1]
    if not (verify_images or quality):
        out = _catalogue(db, verify_images=False, quality=False)
        _CACHE[key] = (time.monotonic(), out)
        return out
    job = _WARMING.get(key)
    if job is None or not job.is_alive():
        def run():
            try:
                out = _catalogue(db, verify_images=verify_images, quality=quality)
                _CACHE[key] = (time.monotonic(), out)
            finally:
                _WARMING.pop(key, None)

        job = threading.Thread(target=run, name="owner-store-catalogue", daemon=True)
        _WARMING[key] = job
        job.start()
    job.join(FULL_WAIT_SECONDS if wait is None else wait)
    hit = _CACHE.get(key)
    if hit and time.monotonic() - hit[0] < CACHE_SECONDS:
        return hit[1]
    quick = dict(catalogue(db, verify_images=False, quality=False))
    quick["preparing"] = True
    quick["preparing_note"] = ("pictures and pattern checks are being computed; they appear on "
                               "the next refresh. Until then they read NOT_CHECKED / UNKNOWN.")
    return quick


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
            "on_customer_page": (p["launch_status"] == "LAUNCH_0" or (
                p["launch_status"] == storefront.CAP1_SCOPE
                and storefront.customer_gates_pass(p, db)[0])),
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
    cap1 = [p for p in products if p["launch_status"] == storefront.CAP1_SCOPE]
    return {
        "generated_at": _now(), "products": products,
        "counts": {"collection": len(products), "launch0": len(launch),
                   "proposed": len(proposed), "cap1": len(cap1),
                   "cap1_approved": sum(1 for p in cap1 if p["on_customer_page"]),
                   "images_verified": (sum(1 for p in products if p["image"].get("status") == "VERIFIED")
                                       if verify_images else None),
                   "quality_ok": (sum(1 for p in products if p["quality"].get("status") == "OK")
                                  if quality else None)},
        "decision": {**DECISION, "cap_approved": len(proposed) == 0,
                     "approved": bool(cap1) and all(p["on_customer_page"] for p in cap1)},
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
