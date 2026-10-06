"""The store content model: every store-level surface, assembled from the module that owns it.

Each `Surface` says what it is, where it goes in Shop Manager, whether Etsy's API could ever
write it (`updateShop` takes five text fields, read from Etsy's own OpenAPI document --
`commerce.shop_package.SOURCES['etsy_shop_api']`) or a person must type it, which Etsy field
limit applies, and which module owns its words. In shadow mode *nothing* is entered by this
system either way: `entry` describes the eventual path, and every surface's
`entered_on_etsy` is UNKNOWN because the live shop is not read here.

Words owned elsewhere are imported, never copied:
    brand.storefront          -- shop name, About, announcement, sections, banner/icon briefs
    commerce.shop_package     -- shop title, delivery, returns, licence, privacy, FAQ,
                                 digital sale message, manual-only fields
    commerce.terms            -- the licence and support sentences
    gates.platform_policy     -- the AI, digital and render disclosures

Words owned here, because nothing owned them: the PIPEDA/CASL privacy addendum, the
support/contact surface, the FAQ entries the buyer-trust audit found missing (skill level,
whether the images are photographs, whether a sample was made), the trust-signal register and
the settings checklist.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

UNKNOWN = "UNKNOWN"

API_WRITABLE = "api_writable_after_owner_authority"   # an updateShop field
OWNER_MANUAL = "owner_types_in_shop_manager"          # no write endpoint exists
INTERNAL = "internal_not_a_shop_field"                # a readiness view, not shop content

REPO_ROOT = Path(__file__).resolve().parents[3]       # brambleloop/


# Keys whose values are identifiers, provenance or bookkeeping, never shown to a buyer.
# Everything else is collected for the lint (default-include).
_INTERNAL_KEYS = frozenset({
    "key", "slug", "cir_slug", "candidate", "build", "kind", "evidence", "source",
    "title_basis", "price_basis", "minutes_basis", "basis", "status", "entered_on_etsy",
    "etsy_handle", "svg", "png", "data_uri", "href", "url", "path", "sha256",
})


def _collect_text(v, parts: list[str]) -> None:
    if isinstance(v, str):
        parts.append(v)
    elif isinstance(v, dict):
        for k, x in v.items():
            if str(k) in _INTERNAL_KEYS:
                continue
            _collect_text(x, parts)
    elif isinstance(v, (list, tuple)):
        for x in v:
            _collect_text(x, parts)


@dataclass
class Surface:
    key: str
    label: str
    group: str
    value: object
    source: str
    etsy_location: str
    entry: str
    limit_key: str | None = None
    customer_facing: bool = True
    notes: list[str] = field(default_factory=list)

    def text(self) -> str:
        """Every customer-readable string in this surface, joined, for the lints.

        Recursive over dicts and lists (J-product P-4): a grid tile's `title`, a FAQ row's
        `body` or a story nested in a list are all customer-facing and all linted. Only keys
        that are internal identifiers or provenance notes (`_INTERNAL_KEYS`) are skipped;
        an unknown key is linted, so a new field is covered by default.
        """
        parts: list[str] = []
        _collect_text(self.value, parts)
        return "\n".join(parts)

    def to_dict(self) -> dict:
        v = self.value
        if self.key in ("icon", "banner"):
            v = {"svg_bytes": len(str(v)), "format": "image/svg+xml"}
        return {"key": self.key, "label": self.label, "group": self.group, "value": v,
                "source": self.source, "etsy_location": self.etsy_location,
                "entry": self.entry, "limit_key": self.limit_key,
                "customer_facing": self.customer_facing, "notes": list(self.notes),
                "entered_on_etsy": UNKNOWN}


# ---- words owned here --------------------------------------------------------------------

ETSY_HANDLE = "BrambleloopStudio"   # opened 2026-09-19 (build2.executor, gate etsy_shop)

PRIVACY_ADDENDUM = (
    "What we receive. When you buy, Etsy shares what is needed to fulfil the order: your Etsy "
    "username, your name, the item and the order details, and anything you write to us. We "
    "use it only to deliver your pattern, answer your questions and send corrections for the "
    "version you bought.\n\n"
    "Who sees it. Only Brambleloop Studio. We do not sell it, rent it or share it with "
    "advertisers. Etsy's own privacy policy covers what Etsy collects.\n\n"
    "Email. We send commercial email only to people who have expressly agreed to receive it. "
    "Every such email says who we are and how to reach us, and has an unsubscribe that works, "
    "as Canada's Anti-Spam Legislation (CASL) requires.\n\n"
    "Your rights. You may ask what personal information we hold about you, ask us to correct "
    "it, or ask us to delete what we are not required to keep, by messaging us on Etsy. We "
    "handle personal information in line with Canada's Personal Information Protection and "
    "Electronic Documents Act (PIPEDA).\n\n"
    "Records. We keep order records for as long as Canadian tax rules require, and no longer "
    "than we need them.")

SUPPORT_CONTACT = (
    "Questions go through Etsy Messages: use the message button on this shop page or on your "
    "order. Tell us the pattern name, which file you are using (US or UK terms) and the row "
    "or round number, and we will answer against the exact version you bought. If the "
    "problem is in the pattern, we correct the pattern itself and send the corrected file to "
    "everyone who bought it.")

# Questions a cautious buyer asks before a first purchase from a shop with no reviews, which
# `commerce.shop_package.faq` did not answer. Answers are true today and say what is not done.
def _extra_faq() -> list[dict]:
    from ..gates import platform_policy

    return [
        {"key": "skill_level", "question": "What skill level do I need?",
         "answer": ("Each listing states a difficulty and names every stitch the pattern "
                    "uses, with the gauge and hook size, so you can judge before you buy.")},
        {"key": "are_images_photos", "question": "Are the pictures photographs?",
         "answer": platform_policy.DISCLOSURES["disclosed_render"]},
        {"key": "sample_made", "question": "Has this pattern been made up in yarn?",
         "answer": ("Not yet by us. Every row's stitch count is checked by a compiler and the "
                    "finished sizes are calculated from the stated gauge, but we have not yet "
                    "worked a physical sample of these designs. Your finished size will vary "
                    "with yarn, hook and tension, so work a gauge swatch first.")},
        {"key": "contact", "question": "How do I reach you?", "answer": SUPPORT_CONTACT},
    ]


@dataclass(frozen=True)
class TrustSignal:
    key: str
    text: str
    kind: str                       # verified_process | policy_commitment | platform_fact
    evidence: tuple[str, ...]       # repository paths that implement or decide it
    note: str = ""

    def to_dict(self) -> dict:
        return {"key": self.key, "text": self.text, "kind": self.kind,
                "evidence": list(self.evidence), "note": self.note}


TRUST_KINDS = ("verified_process", "policy_commitment", "platform_fact")

# Only signals with a mechanism or a decision behind them. There are no review, sales,
# favourite or years-in-business signals because there are none to show, and the preview
# says so ("New shop -- no reviews yet") instead of leaving a gap a buyer reads as hiding.
TRUST_SIGNALS: tuple[TrustSignal, ...] = (
    TrustSignal("compiler_checked", "Every row's stitch count checked by a compiler",
                "verified_process",
                ("src/brambleloop/cir/compiler.py", "src/brambleloop/gates/certificate.py")),
    TrustSignal("reverse_checked", "Each pattern re-read from the finished text before release",
                "verified_process", ("src/brambleloop/cir/reverse.py",)),
    TrustSignal("us_uk", "US and UK terms, as two complete PDFs", "verified_process",
                ("src/brambleloop/publish/pdf.py",), "publish.pdf.TERMINOLOGIES"),
    TrustSignal("corrections", "Corrections sent free to every buyer", "policy_commitment",
                ("src/brambleloop/commerce/terms.py",), "terms.VERSION_POLICY"),
    TrustSignal("licence", "Sell what you make, by hand or in small batches",
                "policy_commitment", ("src/brambleloop/commerce/terms.py",),
                "terms.FINISHED_ITEM_SALE: individual makers and small businesses, not "
                "manufactured at scale"),
    TrustSignal("renders_labelled", "Every image labelled as a rendering, never a photo",
                "verified_process", ("src/brambleloop/publish/disclosed_listing.py",)),
    TrustSignal("instant", "Instant PDF download through Etsy", "platform_fact",
                ("src/brambleloop/commerce/shop_package.py",)),
)

VOICE_PRINCIPLES = (
    "Specific over atmospheric: say what is checked, by what, before release.",
    "Calm: no exclamation marks, no emoji, no capitals for emphasis.",
    "Plain about limits: say what has not been done (no worked sample, renders not photos).",
    "Buyer's words first: crochet pattern, PDF, US and UK terms, sizes in centimetres.",
    "No borrowed credibility: no superlatives, counts, endorsements or invented history.",
)


def settings_checklist() -> list[dict]:
    """What only the account holder can set, field by field (no Etsy write in shadow)."""
    from ..commerce import shop_package

    where = dict(shop_package.MANUAL_ONLY)
    rows = [
        ("shop_name", "Confirm the public shop name (Etsy handle BrambleloopStudio; brand "
                      "display 'Brambleloop Studio')",
         "Shop Manager > Settings > Info & appearance", 2),
        ("shop_title", "Paste the shop title", "Shop Manager > Settings > Info & appearance", 2),
        ("icon", "Upload the shop icon (export icon SVG to PNG)", where["banner_and_icon"], 5),
        ("banner", "Upload the banner, or choose no banner deliberately",
         where["banner_and_icon"], 5),
        ("about", "Paste the About story", where["about_story"], 5),
        ("announcement", "Paste the announcement", "Shop Manager > Settings > Info & "
                                                   "appearance > Announcement", 2),
        ("policy_delivery", "Paste the delivery policy", where["shop_policies_delivery"], 3),
        ("policy_returns", "Set returns: digital items not returnable; paste the text",
         where["shop_policies_returns"], 3),
        ("policy_privacy", "Paste the privacy policy (after legal review)",
         where["shop_policies_privacy"], 3),
        ("faq", "Enter the FAQ entries", where["shop_policies_faq"], 10),
        ("policy_additional", "Paste the licence and disclosures as additional terms",
         "Shop Manager > Settings > Policies: additional policies", 3),
        ("digital_sale_message", "Paste the message to buyers of digital items",
         "Shop Manager > Settings > Info & appearance > Message to buyers", 2),
        ("sections", "Create the populated shop sections", "Shop Manager > Listings > "
                                                           "Sections", 3),
        ("location_currency", "Confirm shop location Canada and currency CAD",
         "Shop Manager > Settings > Info & appearance / Payment settings", 2),
        ("two_factor", "Turn on two-factor sign-in for the Etsy account",
         "Etsy account settings > Security", 3),
        ("search_visibility", "After the first listings are live, read Search Visibility and "
                              "record it (POST /api/search-visibility)",
         "Shop Manager > Marketing > Search Visibility", 5),
    ]
    return [{"key": k, "what": w, "where": loc, "minutes_estimated": m, "max_cost_cad": 0.0,
             "status": "OWNER_LOGIN_REQUIRED", "entered_on_etsy": UNKNOWN,
             "minutes_basis": "ESTIMATED"} for k, w, loc, m in rows]


# ---- Launch-0 opening grid ---------------------------------------------------------------

def _session_rows(db, stmt) -> list:
    """Run a select on either a `core.db.Database` or a bare SQLAlchemy Session."""
    if db is None:
        return []
    if hasattr(db, "scalars") and not hasattr(db, "session"):
        return list(db.scalars(stmt))
    with db.session() as s:
        rows = list(s.scalars(stmt))
        for r in rows:
            s.expunge(r)
        return rows


def launch0_products(db=None) -> list[dict]:
    """One row per Launch-0 *product*. Sizes are variants inside a product, never products."""
    from ..commerce import seo
    from ..products import launch0 as l0
    from ..brand import storefront

    drafted: dict[str, object] = {}
    read_error = None
    if db is not None:
        try:
            from sqlalchemy import select

            from ..core.models import Listing

            slugs = sorted(l0.launch_scope_slugs())
            for row in _session_rows(db, select(Listing).where(
                    Listing.product_slug.in_(slugs), Listing.state != "withdrawn")
                    .order_by(Listing.id)):
                drafted[row.product_slug] = row
        except Exception as exc:  # noqa: BLE001 - unreadable is said, not hidden
            read_error = f"{type(exc).__name__}: {str(exc)[:160]}"

    out = []
    for slug in l0.LAUNCH0_SLUGS:
        cand = l0.candidate(slug)
        ident = l0.listing_identity(slug)
        variants = list(cand.variants)
        rep = variants[len(variants) // 2]
        cirs = [l0.cir_for(v.build) for v in variants]
        rep_cir = l0.cir_for(rep.build)
        price = l0.launch_price(rep_cir.slug) or {}
        row = next((drafted[c.slug] for c in [rep_cir] + cirs if c.slug in drafted), None)
        if row is not None:
            title, title_basis = row.title, f"drafted_listing:listings.id={row.id}"
            description = row.description
            price_cad = row.price_cad
            price_basis = f"drafted_listing:listings.id={row.id}"
        else:
            title = seo.build_title(rep_cir.title, ident.etsy_category, list(ident.qualifiers),
                                    None, sizes=len(variants))
            title_basis = ("derived: commerce.seo.build_title on the CIR title -- the release "
                           "chain's title builder; no drafted listing row read")
            description = cand.what_it_is
            price_cad = price.get("price_cad")
            price_basis = price.get("basis") or UNKNOWN
        out.append({
            "candidate": slug, "plan_title": cand.title, "title": title,
            "title_basis": title_basis, "description": description,
            "price_cad": price_cad, "price_basis": price_basis,
            "sizes": [{"key": v.key, "label": v.label, "cir_slug": c.slug}
                      for v, c in zip(variants, cirs)],
            "variant_count": len(variants),
            "representative": {"build": rep.build, "cir_slug": rep_cir.slug,
                               "cir_fingerprint": rep_cir.fingerprint},
            "kind": ident.kind, "qualifiers": list(ident.qualifiers),
            "etsy_category": ident.etsy_category,
            "section": storefront.section_for(ident.etsy_category),
            "audience": cand.audience,
        })
    if read_error:
        for r in out:
            r["db_read_error"] = read_error
    return out


# ---- the model ---------------------------------------------------------------------------

def build(db=None, *, today=None) -> dict[str, Surface]:
    """Every store surface, keyed. Pure apart from the optional read of drafted listings and
    an applied seasonal takeover (both need a `core.db.Database`)."""
    from ..brand import storefront
    from ..commerce import shop_package
    from ..gates import platform_policy
    from . import assets

    store = None
    takeover_note = None
    if db is not None and hasattr(db, "session"):
        try:
            store = storefront.build_storefront(db=db, today=today)
        except Exception as exc:  # noqa: BLE001
            takeover_note = f"takeover not read: {type(exc).__name__}"
    if store is None:
        store = storefront.build_storefront()
        takeover_note = takeover_note or "no database: evergreen announcement, no takeover"
    pol = shop_package.policies()
    text = shop_package.shop_text()
    products = launch0_products(db)
    populated: dict[str, int] = {}
    for p in products:
        populated[p["section"]] = populated.get(p["section"], 0) + 1

    S = Surface
    surfaces = [
        S("shop_name", "Shop name", "identity",
          {"display": storefront.SHOP_NAME, "etsy_handle": ETSY_HANDLE},
          "brand.storefront.SHOP_NAME; handle from build2.executor (etsy_shop gate)",
          "Shop Manager > Settings > Info & appearance", OWNER_MANUAL, "shop_name"),
        S("icon", "Shop icon", "identity", assets.icon_svg(),
          "store_foundation.assets.icon_svg (brief: brand.storefront._icon_brief)",
          "Shop Manager > Settings > Info & appearance", OWNER_MANUAL, "icon_px",
          customer_facing=False),
        S("banner", "Shop banner", "identity", assets.banner_svg(),
          "store_foundation.assets.banner_svg (brief: brand.storefront._banner_brief)",
          "Shop Manager > Settings > Info & appearance", OWNER_MANUAL, "banner_px",
          customer_facing=False),
        S("shop_title", "Shop title (tagline)", "text", text["title"],
          "commerce.shop_package.shop_text()['title']",
          "Shop Manager > Settings > Info & appearance", API_WRITABLE, "shop_title"),
        S("announcement", "Announcement", "text", store.announcement,
          "brand.storefront.ANNOUNCEMENT_TEMPLATES / takeover",
          "Shop Manager > Settings > Info & appearance", API_WRITABLE, "announcement",
          notes=[takeover_note] if takeover_note else []),
        S("about", "About / shop story", "text", store.about, "brand.storefront.ABOUT",
          shop_package.MANUAL_ONLY[4][1], OWNER_MANUAL, "about"),
        S("policy_delivery", "Delivery (digital)", "policy", pol["delivery"],
          "commerce.shop_package.DELIVERY", shop_package.MANUAL_ONLY[0][1], OWNER_MANUAL,
          "policy_text"),
        S("policy_returns", "Returns and refunds", "policy", pol["returns"],
          "commerce.shop_package.RETURNS", shop_package.MANUAL_ONLY[1][1], OWNER_MANUAL,
          "policy_text"),
        S("policy_licence", "Pattern licence and customer use", "policy", pol["licence"],
          "commerce.terms via commerce.shop_package.licence_text",
          "Shop Manager > Settings > Policies: additional (policy_additional)", API_WRITABLE,
          "policy_text"),
        S("policy_privacy", "Privacy", "policy", pol["privacy"] + "\n\n" + PRIVACY_ADDENDUM,
          "commerce.shop_package.PRIVACY + store_foundation.content.PRIVACY_ADDENDUM",
          shop_package.MANUAL_ONLY[2][1], OWNER_MANUAL, "policy_text"),
        S("disclosures", "AI-use, digital-item and image disclosures", "disclosure",
          pol["ai"] + "\n" + platform_policy.DISCLOSURES["disclosed_render"],
          "gates.platform_policy.DISCLOSURES (ai_assisted_design, digital_download, "
          "deterministic_render, disclosed_render)",
          "Shop Manager > Settings > Policies: additional (policy_additional) and every "
          "listing description", API_WRITABLE, "policy_text"),
        S("faq", "Frequently asked questions", "help",
          [dict(f) for f in shop_package.faq()] + _extra_faq(),
          "commerce.shop_package.faq + store_foundation.content._extra_faq",
          shop_package.MANUAL_ONLY[3][1], OWNER_MANUAL, "faq_entry"),
        S("support_contact", "Support and contact", "help", SUPPORT_CONTACT,
          "store_foundation.content.SUPPORT_CONTACT (consistent with terms.SUPPORT_POLICY)",
          "About section and FAQ (Etsy's Message button is automatic)", OWNER_MANUAL,
          "faq_entry"),
        S("digital_sale_message", "Message to buyers of digital items", "help",
          text["digital_sale_message"], "commerce.shop_package.DIGITAL_SALE_MESSAGE",
          "Shop Manager > Settings > Info & appearance", API_WRITABLE,
          "digital_sale_message"),
        S("sections", "Shop sections", "merch",
          [{"name": s.name, "slug": s.slug, "listings": populated.get(s.slug, 0),
            "shown": bool(populated.get(s.slug))} for s in storefront.SECTIONS],
          "brand.storefront.SECTIONS, populated from the Launch-0 products",
          "Shop Manager > Listings > Sections", OWNER_MANUAL, "section_name"),
        S("opening_grid", "Opening grid (Launch-0 products)", "merch", products,
          "products.launch0 (+ drafted listings rows when present)",
          "Shop home page grid", INTERNAL, "listing_title"),
        S("trust_signals", "Trust signals", "trust", [t.to_dict() for t in TRUST_SIGNALS],
          "store_foundation.content.TRUST_SIGNALS", "About section, banner area, listings",
          OWNER_MANUAL),
        S("voice", "Brand voice", "brand", list(VOICE_PRINCIPLES),
          "store_foundation.content.VOICE_PRINCIPLES; brand.bible", "applies to every surface",
          INTERNAL, customer_facing=False),
        S("settings_checklist", "Settings checklist (owner login)", "settings",
          settings_checklist(), "store_foundation.content.settings_checklist",
          "Shop Manager", INTERNAL, customer_facing=False),
        S("search_readiness", "Search visibility readiness", "readiness",
          {"tagline": text["title"]}, "brand.storefront.check_shop_seo; "
          "commerce.search_visibility", "Shop Manager > Marketing > Search Visibility",
          INTERNAL, customer_facing=False),
        S("support_readiness", "Customer-support readiness", "readiness",
          {"channel": "Etsy Messages"}, "support.department; commerce.shop_package",
          "Etsy Messages", INTERNAL, customer_facing=False),
    ]
    return {s.key: s for s in surfaces}
