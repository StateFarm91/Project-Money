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

Store copy v2 (wave 3, lane C): every customer-facing store string -- tagline, announcement,
About, delivery/returns/privacy wording, FAQ answers, disclosure block, support, section
names, trust copy -- now lives in `store_foundation.copy_v2`; `commerce.shop_package` reads it
there, and the licence and AI-disclosure sentences inside it are still rendered from
`commerce.terms` and `gates.platform_policy`. The names below are kept as re-exports.

Words formerly owned here, because nothing owned them: the PIPEDA/CASL privacy addendum, the
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
    #: W4-STORE: the live shop's status for this surface (`live_state.annotate`); None when
    #: no database was given, which reports UNKNOWN.
    live: dict | None = None

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
                "entered_on_etsy": (self.live or {}).get("entered_on_etsy", UNKNOWN),
                "live": dict(self.live) if self.live else None}


# ---- words owned here --------------------------------------------------------------------

ETSY_HANDLE = "BrambleloopStudio"   # opened 2026-09-19 (build2.executor, gate etsy_shop)

# Store copy v2 (wave 3, lane C) owns every customer-facing store string. These names are
# kept as re-exports so existing readers keep working; the words are in `copy_v2`.
from . import copy_v2  # noqa: E402

PRIVACY_ADDENDUM = copy_v2.PRIVACY_ADDENDUM
SUPPORT_CONTACT = copy_v2.SUPPORT_CONTACT
TrustSignal = copy_v2.TrustSignal
TRUST_KINDS = copy_v2.TRUST_KINDS
# Only signals with a mechanism or a decision behind them. There are no review, sales,
# favourite or years-in-business signals because there are none to show, and the preview
# says so ("New shop -- no reviews yet") instead of leaving a gap a buyer reads as hiding.
TRUST_SIGNALS = copy_v2.TRUST_SIGNALS
VOICE_PRINCIPLES = copy_v2.VOICE_PRINCIPLES


def _extra_faq() -> list[dict]:
    """The first-purchase questions `commerce.shop_package.faq` does not carry."""
    return copy_v2.faq_extra()


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
        ("licence_in_faq", "Enter the licence as the FAQ answers (sell, print, teach, "
                           "share, corrections). Leave 'additional policies' empty: Etsy "
                           "accepts that field only from EU shops (OpenAPI, verified by "
                           "integrations.etsy_constraints)",
         where["shop_policies_faq"], 3),
        ("digital_sale_message", "Paste the message to buyers of digital items",
         "Shop Manager > Settings > Info & appearance > Message to buyers", 2),
        ("sections", "Create the populated shop sections", "Shop Manager > Listings > "
                                                           "Sections", 3),
        ("location_currency", "Confirm shop location Canada and currency CAD",
         "Shop Manager > Settings > Info & appearance / Payment settings", 2),
        ("two_factor", "Turn on two-factor sign-in for the Etsy account",
         "Etsy account settings > Security", 3),
        ("creativity_classification", "At each listing: choose 'Designed by' the seller (a "
                                       "digital pattern made with AI tools) and keep the AI "
                                       "disclosure in the description (Etsy Creativity "
                                       "Standards, read via secondary sources; Etsy page 403)",
         "Listing editor > About this listing (who made it / what is it)", 1),
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


def _sections(storefront, populated: dict[str, int]) -> list[dict]:
    """Owner-nav section names (copy_v2) over the storefront's slugs, in the owner's order.

    A section with no Launch-0 product is PLANNED and not shown: an empty shelf implies
    products the shop does not have.
    """
    known = {s.slug for s in storefront.SECTIONS}
    rows = []
    for sc in sorted(copy_v2.SECTIONS, key=lambda x: x.order):
        n = populated.get(sc.slug, 0)
        rows.append({"name": sc.name, "slug": sc.slug, "blurb": sc.blurb, "listings": n,
                     "shown": bool(n), "status": "live" if n else "planned",
                     "known_slug": sc.slug in known})
    for s in storefront.SECTIONS:
        if s.slug not in copy_v2.SECTION_BY_SLUG:
            n = populated.get(s.slug, 0)
            rows.append({"name": s.name, "slug": s.slug, "blurb": "", "listings": n,
                         "shown": bool(n), "status": "live" if n else "planned",
                         "known_slug": True})
    return rows


# ---- the model ---------------------------------------------------------------------------

def build(db=None, *, today=None) -> dict[str, Surface]:
    """Every store surface, keyed. Pure apart from the optional read of drafted listings and
    an applied seasonal takeover (both need a `core.db.Database`)."""
    from ..brand import storefront
    from ..commerce import shop_package
    from . import assets, brand_face

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

    announcement = store.announcement
    if announcement == storefront.ANNOUNCEMENT_TEMPLATES.get("evergreen"):
        announcement = copy_v2.ANNOUNCEMENT          # no takeover banner applied
    about = copy_v2.ABOUT
    if store.seasonal_copy:
        about = f"{about}\n\n{store.seasonal_copy}"

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
        S("brand_face", "Brand face (Laura)", "identity", brand_face.brand_face(),
          "store_foundation.brand_face (visual.canonical, D-FB-11/D-FB-12)",
          "Shop Manager > Settings > About > Shop owner photo; banner; About; seasonal",
          OWNER_MANUAL, customer_facing=False,
          notes=[brand_face.PREVIEW_IMAGE_LABEL]),
        S("shop_title", "Shop title (tagline)", "text", text["title"],
          "store_foundation.copy_v2.TAGLINE (via commerce.shop_package.shop_text)",
          "Shop Manager > Settings > Info & appearance", API_WRITABLE, "shop_title"),
        S("announcement", "Announcement", "text", announcement,
          "store_foundation.copy_v2.ANNOUNCEMENT / takeover banner when one is applied",
          "Shop Manager > Settings > Info & appearance", API_WRITABLE, "announcement",
          notes=[takeover_note] if takeover_note else []),
        S("about", "About / shop story", "text", about,
          "store_foundation.copy_v2.ABOUT (+ applied seasonal copy)",
          shop_package.MANUAL_ONLY[4][1], OWNER_MANUAL, "about"),
        S("policy_delivery", "Delivery (digital)", "policy", pol["delivery"],
          "store_foundation.copy_v2.DELIVERY (via commerce.shop_package)",
          shop_package.MANUAL_ONLY[0][1], OWNER_MANUAL,
          "policy_text"),
        S("policy_returns", "Returns and refunds", "policy", pol["returns"],
          "store_foundation.copy_v2.RETURNS (via commerce.shop_package)",
          shop_package.MANUAL_ONLY[1][1], OWNER_MANUAL,
          "policy_text"),
        S("policy_licence", "Pattern licence and customer use", "policy", pol["licence"],
          "commerce.terms via commerce.shop_package.licence_text",
          "Shop Manager > Settings > Policies: FAQ (licence answers; policy_additional is "
          "EU-only and not used)", OWNER_MANUAL,
          "policy_text"),
        S("policy_privacy", "Privacy", "policy", pol["privacy"] + "\n\n" + PRIVACY_ADDENDUM,
          "store_foundation.copy_v2.PRIVACY + PRIVACY_ADDENDUM (via commerce.shop_package)",
          shop_package.MANUAL_ONLY[2][1], OWNER_MANUAL, "policy_text"),
        S("disclosures", "AI-use, digital-item and image disclosures", "disclosure",
          copy_v2.store_disclosure(),
          "store_foundation.copy_v2.store_disclosure: gates.platform_policy.DISCLOSURES "
          "(digital_download, ai_assisted_design, deterministic_render, disclosed_render) "
          "verbatim + Laura and account-holder lines",
          "every listing description (Etsy: 'Seller-prompted AI creations must disclose the "
          "use of AI.') and the shop FAQ/About", OWNER_MANUAL, "policy_text"),
        S("faq", "Frequently asked questions", "help",
          [dict(f) for f in shop_package.faq()] + _extra_faq(),
          "store_foundation.copy_v2 (faq_core via commerce.shop_package.faq + faq_extra)",
          shop_package.MANUAL_ONLY[3][1], OWNER_MANUAL, "faq_entry"),
        S("support_contact", "Support and contact", "help", SUPPORT_CONTACT,
          "store_foundation.copy_v2.SUPPORT_CONTACT (consistent with terms.SUPPORT_POLICY)",
          "About section and FAQ (Etsy's Message button is automatic)", OWNER_MANUAL,
          "faq_entry"),
        S("digital_sale_message", "Message to buyers of digital items", "help",
          text["digital_sale_message"],
          "store_foundation.copy_v2.DIGITAL_SALE_MESSAGE (via commerce.shop_package)",
          "Shop Manager > Settings > Info & appearance", API_WRITABLE,
          "digital_sale_message"),
        S("sections", "Shop sections", "merch",
          _sections(storefront, populated),
          "store_foundation.copy_v2.SECTIONS (owner nav) over brand.storefront.SECTIONS "
          "slugs, populated from the Launch-0 products; unpopulated = planned, not shown",
          "Shop Manager > Listings > Sections", OWNER_MANUAL, "section_name"),
        S("opening_grid", "Opening grid (Launch-0 products)", "merch", products,
          "products.launch0 (+ drafted listings rows when present)",
          "Shop home page grid", INTERNAL, "listing_title"),
        S("trust_signals", "Trust signals", "trust", [t.to_dict() for t in TRUST_SIGNALS],
          "store_foundation.copy_v2.TRUST_SIGNALS", "About section, banner area, listings",
          OWNER_MANUAL),
        S("voice", "Brand voice", "brand", list(VOICE_PRINCIPLES),
          "store_foundation.copy_v2.VOICE_PRINCIPLES; brand.bible", "applies to every surface",
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
    out = {s.key: s for s in surfaces}
    if db is not None and hasattr(db, "session"):
        # W4-STORE: the live shop is authoritative; annotate what has been read back.
        from . import live_state

        try:
            live_state.annotate(db, out)
        except Exception:  # noqa: BLE001 - an unreadable live state stays UNKNOWN
            pass
    return out
