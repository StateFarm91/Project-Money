"""Ranking readiness: five independent things Etsy's search and a buyer judge, never blended.

F-003. A listing's chance of being found and bought rests on several separate things, and the
system had each of them in a different place: the search certificate (`listing.seo`), the
listing-set certificate's frame 1 (`publish.release_gates`), the price/disclosure/first-
customer gate, the storefront checks, and support's service level. Nothing put them side by
side for one listing, so `/api/catalogue` showed a single planning proxy (`seo_score`, the
assumed+observed query share) as if it were search readiness.

`profile(db, slug)` reports five dimensions, each **MEASURED** (with a PASS/FAIL verdict and
the evidence it rests on) or **UNMEASURED** (with why). There is deliberately no overall
score: a blend lets a strong dimension hide a failed one, and averaging an UNMEASURED
dimension in as anything at all would be inventing it. UNMEASURED is never PASS.

A dimension made of several components is MEASURED only when every component was measured;
one measured failure makes it a MEASURED FAIL, because a known failure is a measurement.

The click and conversion dimensions here are *pre-traffic*: they read whether the things that
earn a click and a sale are in place. Observed click-through and conversion exist only for a
live listing (gate `live_listings`) and belong to `growth`, not here.
"""
from __future__ import annotations

MEASURED = "MEASURED"
UNMEASURED = "UNMEASURED"
PASS = "PASS"
FAIL = "FAIL"

DIMENSIONS: tuple[str, ...] = ("listing_quality", "click_readiness", "conversion_readiness",
                               "shop_quality", "service_quality")


def _measured(ok: bool, basis: str, why: str, evidence: dict | None = None) -> dict:
    return {"status": MEASURED, "verdict": PASS if ok else FAIL, "basis": basis, "why": why,
            "evidence": evidence or {}}


def _unmeasured(basis: str, why: str, evidence: dict | None = None) -> dict:
    return {"status": UNMEASURED, "verdict": None, "basis": basis, "why": why,
            "evidence": evidence or {}}


def _combine(basis: str, parts: dict[str, dict]) -> dict:
    """Components -> one dimension, by the rule in the module docstring."""
    failed = [k for k, p in parts.items() if p["status"] == MEASURED and p["verdict"] != PASS]
    unmeasured = [k for k, p in parts.items() if p["status"] != MEASURED]
    evidence = {"components": parts}
    if failed:
        return _measured(False, basis, "failed: " + "; ".join(
            f"{k}: {parts[k]['why']}" for k in failed)[:400], evidence)
    if unmeasured:
        return _unmeasured(basis, "not measured: " + "; ".join(
            f"{k}: {parts[k]['why']}" for k in unmeasured)[:400], evidence)
    return _measured(True, basis, "every component passed", evidence)


# ---- the five dimensions ----------------------------------------------------------------

def search_certificate(db, slug: str, version: str) -> dict:
    """The stored search certificate's standing, for display beside a listing.

    NONE when listing.seo has written no profile, STALE when the listing changed after it
    was issued, otherwise the certificate's own verdict (PASS / REFUSED).
    """
    from sqlalchemy import select

    from ..core.models import Listing, ListingSearchProfile
    from ..publish.release_gates import search_fingerprint

    with db.session() as s:
        prof = s.scalar(select(ListingSearchProfile).where(
            ListingSearchProfile.product_slug == slug, ListingSearchProfile.version == version))
        listing = s.scalar(select(Listing).where(Listing.product_slug == slug,
                                                 Listing.version == version))
        if prof is None:
            return {"verdict": "NONE", "current": None, "category_status": None,
                    "why": "listing.seo has recorded no search profile"}
        current = listing is not None and search_fingerprint(
            title=listing.title, description=listing.description, tags=listing.tags,
            taxonomy_id=prof.taxonomy_id, properties=prof.properties) == prof.fingerprint
        return {"verdict": prof.verdict if current else "STALE", "current": current,
                "category_status": prof.category_status,
                "why": ("the certificate covers the listing as it stands" if current else
                        "the listing changed after certification (F-294)")}


def listing_quality(db, slug: str, version: str) -> dict:
    """The search certificate at the publish gate's own standard, hero excluded.

    The hero is the click dimension's, so it is not counted twice: one failed frame 1 would
    otherwise fail two dimensions and read as two problems.
    """
    from ..publish.release_gates import search_gate

    cert = search_certificate(db, slug, version)
    basis = "publish.release_gates.search_gate (search certificate F-004/F-294), hero excluded"
    if cert["verdict"] == "NONE":
        return _unmeasured(basis, cert["why"])
    gate = search_gate(db, slug=slug, version=version, set_verdict=None)
    reasons = [r for r in gate["reasons"] if " hero:" not in r]
    return _measured(not reasons, basis,
                     "the search certificate is current and every check passed"
                     if not reasons else "; ".join(reasons)[:400],
                     {"certificate": cert, "category_status": gate.get("category_status"),
                      "reasons": reasons[:6]})


def click_readiness(db, slug: str, version: str) -> dict:
    """Frame 1 certified through all four gates: what a search thumbnail is judged on."""
    from sqlalchemy import desc, select

    from ..core.models import ListingAsset, ListingSetCertificateRecord

    basis = ("listing-set certificate (#70) naming frame 1, else frame 1's own block "
             "reasons; observed CTR is post-traffic (gate live_listings)")
    with db.session() as s:
        recs = list(s.scalars(select(ListingSetCertificateRecord).where(
            ListingSetCertificateRecord.product_slug == slug,
            ListingSetCertificateRecord.version == version)
            .order_by(desc(ListingSetCertificateRecord.id))))
        hero_row = s.scalar(select(ListingAsset).where(
            ListingAsset.product_slug == slug, ListingAsset.version == version,
            ListingAsset.position == 1))
        hero_blocked = list(hero_row.blocked_reasons or []) if hero_row is not None else []
    valid = next((r for r in recs if r.state == "valid"), None)
    if valid is not None:
        hero = next((f for f in (valid.certificate or {}).get("frames") or []
                     if f.get("position") == 1), None)
        return _measured(hero is not None, basis,
                         "frame 1 is certified for export" if hero else
                         "the valid certificate names no frame 1",
                         {"certificate_id": valid.id, "hero_job": (hero or {}).get("job")})
    if recs:
        return _measured(False, basis, f"no valid listing-set certificate: the latest is "
                                       f"{recs[0].state} by {recs[0].invalidated_by}",
                         {"certificate_id": recs[0].id, "state": recs[0].state})
    if hero_blocked:
        return _measured(False, basis, "frame 1 is blocked: " + "; ".join(
            str(r) for r in hero_blocked)[:300])
    return _unmeasured(basis, "no listing-set certificate is on file for this release")


def conversion_readiness(db, slug: str, version: str, *, first_customer: dict | None) -> dict:
    """Price, the digital-download disclosure, and the before-the-first-customer gate."""
    from sqlalchemy import select

    from ..core.models import Listing
    from ..gates.platform_policy import DISCLOSURES

    with db.session() as s:
        listing = s.scalar(select(Listing).where(Listing.product_slug == slug,
                                                 Listing.version == version))
        price = listing.price_cad if listing else None
        description = listing.description if listing else ""
    parts: dict[str, dict] = {}
    if listing is None:
        parts["price"] = _unmeasured("listings.price_cad", "no drafted listing")
        parts["disclosure"] = _unmeasured("listings.description", "no drafted listing")
    else:
        parts["price"] = _measured((price or 0) > 0, "listings.price_cad",
                                   f"CA${price:.2f}" if price else "unpriced")
        line = DISCLOSURES["digital_download"]
        parts["disclosure"] = _measured(line in (description or ""),
                                        "gates.platform_policy.DISCLOSURES[digital_download]",
                                        "the description says no physical item is shipped"
                                        if line in (description or "") else
                                        "the description does not carry the digital-download "
                                        "disclosure")
    if first_customer is None:
        parts["first_customer"] = _unmeasured("commerce.first_hundred",
                                              "the before-the-first-customer reading failed")
    else:
        outstanding = first_customer.get("outstanding") or []
        parts["first_customer"] = _measured(not outstanding,
                                            "commerce.first_hundred.before_the_first_customer",
                                            "all four are ready" if not outstanding else
                                            f"not ready: {outstanding}")
    return _combine("price, disclosure and the first-customer gate (pre-traffic; observed "
                    "conversion is post-traffic, gate live_listings)", parts)


def shop_quality(db) -> dict:
    from ..brand.storefront import build_storefront
    from . import shop_package

    store = build_storefront(db=db)
    package = shop_package.check_package()
    problems = list(store.problems) + list(package)
    return _measured(not problems, "brand.storefront.check_storefront + "
                                   "commerce.shop_package.check_package (shop-wide)",
                     "the storefront and the shop package pass" if not problems else
                     "; ".join(problems)[:400], {"problems": problems[:8]})


def service_quality(db) -> dict:
    from ..support.service import service_level

    level = service_level(db)
    basis = "support.service.service_level (shop-wide, sent responses only)"
    if level.get("meets_target") is None:
        return _unmeasured(basis, level.get("note") or "no timed response in the window",
                           {"cases": level.get("cases"), "timed": level.get("timed")})
    return _measured(bool(level["meets_target"]), basis,
                     f"floor {level['floor']}: canonical {level['canonical']['within_target']}, "
                     f"escalated {level['escalated']['within_target']}",
                     {"cases": level.get("cases"), "timed": level.get("timed")})


# ---- the profile ------------------------------------------------------------------------

def shop_wide(db) -> dict:
    """The dimensions that do not vary by listing, computed once for a whole catalogue."""
    try:
        from .first_hundred import before_the_first_customer

        first = before_the_first_customer(db=db)
    except Exception:  # noqa: BLE001 - an unreadable gate is unmeasured, not passed
        first = None
    return {"shop_quality": shop_quality(db), "service_quality": service_quality(db),
            "first_customer": first}


def _latest_version(db, slug: str) -> str | None:
    from sqlalchemy import desc, select

    from ..core.models import Listing

    with db.session() as s:
        return s.scalar(select(Listing.version).where(
            Listing.product_slug == slug, Listing.state != "withdrawn")
            .order_by(desc(Listing.id)).limit(1))


def profile(db, slug: str, version: str | None = None, *, shared: dict | None = None) -> dict:
    """Five independent dimensions for one listing. No blended score, by design."""
    version = version or _latest_version(db, slug)
    shared = shared if shared is not None else shop_wide(db)
    if version is None:
        dims = {d: _unmeasured("listings", "no drafted listing for this product")
                for d in DIMENSIONS[:3]}
    else:
        dims = {"listing_quality": listing_quality(db, slug, version),
                "click_readiness": click_readiness(db, slug, version),
                "conversion_readiness": conversion_readiness(
                    db, slug, version, first_customer=shared.get("first_customer"))}
    dims["shop_quality"] = shared["shop_quality"]
    dims["service_quality"] = shared["service_quality"]
    return {
        "slug": slug, "version": version,
        "dimensions": dims,
        "measured": [d for d in DIMENSIONS if dims[d]["status"] == MEASURED],
        "unmeasured": [d for d in DIMENSIONS if dims[d]["status"] == UNMEASURED],
        "failing": [d for d in DIMENSIONS if dims[d]["verdict"] == FAIL],
        "search_certificate": (search_certificate(db, slug, version)
                               if version else {"verdict": "NONE", "current": None}),
        "blended_score": None,
        "why_no_blend": ("five independent dimensions; averaging lets a strong one hide a "
                         "failed one, and an UNMEASURED one has no value to average"),
    }


def summary(prof: dict) -> dict:
    """The profile as one line per dimension, for listing tables."""
    return {d: (v["verdict"] if v["status"] == MEASURED else UNMEASURED)
            for d, v in prof["dimensions"].items()}
