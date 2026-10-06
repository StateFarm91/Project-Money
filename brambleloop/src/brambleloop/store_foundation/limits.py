"""Etsy field limits for the store surfaces, each labelled by how well it is actually known.

The rule for this file: a number appears with VERIFIED only when the repository records it as
read from Etsy's own published material. A number that exists in this repository's code with
no recorded source is REPO_ASSERTED -- checked, but a breach is a warning, not a failure, and
the review says the number needs reading. A field whose limit nobody here has read is UNKNOWN
and carries no number at all: inventing a plausible one would make an unchecked guess look
like a measurement (the owner's rule: UNKNOWN is never rendered as a value).

Etsy's help and policy pages refuse automated readers from this environment
(`commerce.shop_package.SOURCES['etsy_help']`), so most shop-level limits are UNKNOWN until a
person reads them in Shop Manager, where Etsy shows its own character counters at entry.
"""
from __future__ import annotations

from dataclasses import dataclass

VERIFIED = "VERIFIED"
REPO_ASSERTED = "UNVERIFIED_REPO_ASSERTED"
UNKNOWN = "UNVERIFIED_UNKNOWN"

BASES = (VERIFIED, REPO_ASSERTED, UNKNOWN)


@dataclass(frozen=True)
class FieldLimit:
    key: str
    what: str
    max_chars: int | None
    basis: str
    source: str

    def __post_init__(self) -> None:
        if self.basis not in BASES:
            raise ValueError(f"{self.key}: basis {self.basis!r} not in {BASES}")
        if self.basis == UNKNOWN and self.max_chars is not None:
            raise ValueError(f"{self.key}: an UNKNOWN limit may not carry a number")
        if self.basis != UNKNOWN and self.max_chars is None:
            raise ValueError(f"{self.key}: a {self.basis} limit needs its number")

    def to_dict(self) -> dict:
        return {"key": self.key, "what": self.what, "max_chars": self.max_chars,
                "basis": self.basis, "source": self.source}


def _limits() -> dict[str, FieldLimit]:
    from ..brand import storefront
    from ..integrations import etsy
    from ..publish import disclosed_listing

    rows = (
        FieldLimit("listing_title", "a listing title", etsy.TITLE_MAX, VERIFIED,
                   "integrations.etsy.TITLE_MAX ('Etsy's own limits, as published')"),
        FieldLimit("alt_text", "a listing image's alt text", disclosed_listing.ALT_TEXT_MAX,
                   VERIFIED, "integrations.etsy.ALT_TEXT_MAX (uploadListingImage schema: "
                             "'Max length 500 characters')"),
        FieldLimit("announcement", "the shop announcement", storefront.ANNOUNCEMENT_MAX,
                   REPO_ASSERTED, "brand.storefront.ANNOUNCEMENT_MAX -- no Etsy source "
                                  "recorded for the number"),
        FieldLimit("about", "the About / shop story", storefront.ABOUT_MAX, REPO_ASSERTED,
                   "brand.storefront.ABOUT_MAX ('Etsy's shop story field cap') -- no Etsy "
                   "source recorded for the number"),
        FieldLimit("sections_count", "the number of shop sections", 20, REPO_ASSERTED,
                   "brand.storefront.check_storefront ('exceeds Etsy's 20') -- no Etsy "
                   "source recorded"),
        FieldLimit("shop_title", "the shop title (tagline under the shop name)", None,
                   UNKNOWN, "not on file; Etsy shows a counter in Shop Manager > Info & "
                            "appearance"),
        FieldLimit("shop_name", "the shop name", None, UNKNOWN,
                   "Etsy's shop-name rules are not on file. The handle BrambleloopStudio "
                   "was accepted by Etsy on 2026-09-19 (build2.executor etsy_shop gate), "
                   "which evidences that handle only"),
        FieldLimit("section_name", "one shop section name", None, UNKNOWN,
                   "not on file; brand.storefront_preview.SECTION_LABEL_MAX (30) is an "
                   "ASSUMED phone-menu line, not Etsy's limit"),
        FieldLimit("policy_text", "one shop-policy text block", None, UNKNOWN,
                   "not on file"),
        FieldLimit("faq_entry", "one FAQ question or answer", None, UNKNOWN, "not on file"),
        FieldLimit("faq_count", "the number of FAQ entries", None, UNKNOWN, "not on file"),
        FieldLimit("digital_sale_message", "the message to buyers of digital items", None,
                   UNKNOWN, "not on file; the field itself is in Etsy's updateShop schema "
                            "(commerce.shop_package.SOURCES['etsy_shop_api'])"),
        FieldLimit("banner_px", "banner pixel dimensions", None, UNKNOWN,
                   "Etsy's recommended banner size is not on file; Shop.image_url_760x100 "
                   "is a read-only URL variant, not an upload rule"),
        FieldLimit("icon_px", "shop icon pixel dimensions", None, UNKNOWN,
                   "Etsy's recommended icon size is not on file"),
    )
    return {r.key: r for r in rows}


LIMITS: dict[str, FieldLimit] = _limits()


def check_length(limit_key: str | None, text: str) -> list[dict]:
    """Findings for one text against its field's limit. Never a pass on an UNKNOWN limit."""
    if limit_key is None:
        return []
    lim = LIMITS[limit_key]
    n = len(text or "")
    if lim.basis == UNKNOWN:
        return [{"code": "LIMIT_UNVERIFIED", "severity": "unverified",
                 "detail": f"{lim.what}: {n} characters; Etsy's limit is not on file "
                           f"({lim.source}). Check the counter in Shop Manager at entry."}]
    if n <= lim.max_chars:
        if lim.basis == REPO_ASSERTED:
            return [{"code": "LIMIT_REPO_ASSERTED", "severity": "unverified",
                     "detail": f"{lim.what}: {n}/{lim.max_chars} characters against an "
                               f"unsourced limit ({lim.source})"}]
        return []
    sev = "fail" if lim.basis == VERIFIED else "unverified"
    return [{"code": "LIMIT_EXCEEDED", "severity": sev,
             "detail": f"{lim.what}: {n} characters exceeds {lim.max_chars} "
                       f"({lim.basis}: {lim.source})"}]
