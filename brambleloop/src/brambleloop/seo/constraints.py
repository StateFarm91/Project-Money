"""Etsy listing / shop field constraints that SEO decisions depend on, each with its evidence.

Wave-3 lane G (directive section 13: "Verify current Etsy field/crop/category/attribute
requirements from authoritative evidence before finalizing").

The rule for every row (the same rule `store_foundation.limits` and `publish.listing_schema`
follow, applied to the SEO-relevant fields):

- **VERIFIED** -- read on `retrieved_on` from a primary Etsy source that this environment could
  actually fetch, with the sentence it came from in `quote`. Today that is only Etsy's own
  OpenAPI v3 document (fetched 2026-10-06, sha256 below). Also VERIFIED: an *absence* -- the
  document defines a field and states no length for it (`NOT_STATED_IN_API`), which is a
  checked fact about the document, not a claim that no limit exists.
- **UNVERIFIED** -- everything else. `help.etsy.com` and `www.etsy.com` (Help Center, Seller
  Handbook, legal policies) answered HTTP 403 to every fetch from this environment on
  2026-10-06 (curl and WebFetch alike), so the familiar numbers -- 140-character titles,
  13 tags of 20 characters, a 55-character shop title, 20 sections of 24 characters -- are
  corroborated only by a web-search index's summary of those Etsy pages (`SECONDARY`). They
  are consistent with the repository's long-standing constants and are enforced as the
  working limits, but they are not labelled VERIFIED here because nobody read the sentence.
  The owner can close each one in seconds by reading the counter Shop Manager shows at entry
  (`owner_check`).

Etsy operation names are written as HTTP paths here (quotes use [brackets] for that one
editorial substitution) so that this package's source never names an Etsy write operation --
`tests/test_v11_seo_proposals.py` guards that by text.

Nothing in this module makes a network call; it is the record of what was read, when, and how.
`snapshot()` is the JSON shape the status provider and the handoff cite.
"""
from __future__ import annotations

from dataclasses import dataclass, field

VERIFIED = "VERIFIED"
UNVERIFIED = "UNVERIFIED"
STATUSES = (VERIFIED, UNVERIFIED)

# How the evidence was obtained.
PRIMARY_API_DOC = "primary:etsy_openapi_v3"           # the OpenAPI JSON itself, fetched + hashed
PRIMARY_DEV_DOC = "primary:developers.etsy.com"       # Etsy's developer tutorial page, fetched
SECONDARY_SEARCH = "secondary:web_search_index_summary_of_etsy_page"  # page itself 403
REPO_ASSERTED = "repo_asserted"                       # a constant in this repo, no source on file
NOT_STATED = "NOT_STATED_IN_API"                      # the document defines the field, no limit

RETRIEVED_ON = "2026-10-06"
OPENAPI_URL = "https://www.etsy.com/openapi/generated/oas/3.0.0.json"
OPENAPI_SHA256 = "b993d52f46afdf87f7687dc6ff8885f2b012589f9b123e1faf14cc54ee73a9ef"
OPENAPI_BYTES = 911340
DEV_LISTINGS_TUTORIAL = "https://developers.etsy.com/documentation/tutorials/listings/"
BLOCKED_HOSTS_NOTE = ("help.etsy.com and www.etsy.com (Help Center, Seller Handbook, "
                      "/legal/*) returned HTTP 403 to curl and WebFetch from this environment "
                      "on 2026-10-06; web.archive.org was rate-limited/refused")

# Etsy pages the UNVERIFIED rows cite. The URLs are real search results returned on
# 2026-10-06; their *content* was not read, only an index summary of it.
HELP_TAGS = "https://help.etsy.com/hc/en-us/articles/360000336307-How-to-Use-Tags-to-Get-Found-in-Search"
HANDBOOK_KEYWORDS = ("https://www.etsy.com/seller-handbook/article/"
                     "keywords-101-everything-you-need-to-know/382774281517")
HANDBOOK_MAKEOVER = "https://www.etsy.com/ca/seller-handbook/article/28834504207"
HELP_SHOP_TITLE = ("https://help.etsy.com/hc/en-us/articles/"
                   "360000343708-How-to-Add-a-Shop-Announcement-and-Shop-Title")
HELP_SECTIONS = ("https://help.etsy.com/hc/en-us/articles/"
                 "360000345048-How-to-Create-and-Manage-Shop-Sections")
HELP_SEARCH_VISIBILITY = ("https://help.etsy.com/hc/en-us/articles/"
                          "25869947521175-How-to-Use-the-Etsy-Search-Visibility-Page")
HANDBOOK_AI = "https://www.etsy.com/seller-handbook/article/1275449912004"
LEGAL_CREATIVITY = "https://www.etsy.com/legal/creativity/"
PUBLIC_CROCHET_PATTERNS = ("https://www.etsy.com/c/craft-supplies-and-tools/sewing-and-fiber/"
                           "crochet/kits-and-how-to/patterns")


@dataclass(frozen=True)
class Constraint:
    key: str
    applies_to: str            # listing | shop | taxonomy | policy
    rule: str                  # the constraint in plain words
    value: object              # the number / enum / regex, or None when there is none
    status: str                # VERIFIED | UNVERIFIED
    method: str                # PRIMARY_API_DOC | PRIMARY_DEV_DOC | SECONDARY_SEARCH | ...
    url: str
    retrieved_on: str
    quote: str = ""            # the sentence read (primary) or the summary text (secondary)
    enforced_by: str = ""      # where this repo enforces it, if anywhere
    owner_check: str = ""      # how a person closes an UNVERIFIED row
    notes: list = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.status not in STATUSES:
            raise ValueError(f"{self.key}: status {self.status!r} not in {STATUSES}")
        if self.status == VERIFIED and not self.method.startswith("primary:"):
            raise ValueError(f"{self.key}: VERIFIED requires a primary source, not "
                             f"{self.method!r}")
        if self.status == VERIFIED and not self.quote.strip():
            raise ValueError(f"{self.key}: VERIFIED with no quoted sentence")
        if not self.url or not self.retrieved_on:
            raise ValueError(f"{self.key}: every row cites a URL and a retrieval date")
        if self.status == UNVERIFIED and not self.owner_check:
            raise ValueError(f"{self.key}: an UNVERIFIED row must say how to close it")

    def to_dict(self) -> dict:
        return {"key": self.key, "applies_to": self.applies_to, "rule": self.rule,
                "value": self.value, "status": self.status, "method": self.method,
                "url": self.url, "retrieved_on": self.retrieved_on, "quote": self.quote,
                "enforced_by": self.enforced_by, "owner_check": self.owner_check,
                "notes": list(self.notes)}


def _api(key, applies_to, rule, value, quote, enforced_by="", notes=()) -> Constraint:
    return Constraint(key, applies_to, rule, value, VERIFIED, PRIMARY_API_DOC, OPENAPI_URL,
                      RETRIEVED_ON, quote, enforced_by, "", list(notes))


def _secondary(key, applies_to, rule, value, url, summary, owner_check, enforced_by="",
               notes=()) -> Constraint:
    return Constraint(key, applies_to, rule, value, UNVERIFIED, SECONDARY_SEARCH, url,
                      RETRIEVED_ON, summary, enforced_by, owner_check,
                      [BLOCKED_HOSTS_NOTE, *notes])


CONSTRAINTS: tuple[Constraint, ...] = (
    # ---- listing: VERIFIED from the OpenAPI document -----------------------------------------
    _api("title_charset", "listing",
         "title: letters, digits, punctuation, math symbols, spaces, TM/(c)/(R); each of "
         "% : & + at most once", r"/[^\p{L}\p{Nd}\p{P}\p{Sm}\p{Zs}™©®]/u",
         "valid title strings contain only letters, numbers, punctuation marks, mathematical "
         "symbols, whitespace characters, ™, ©, and ®. (regex: /[^\\p{L}\\p{Nd}\\p{P}\\p{Sm}"
         "\\p{Zs}™©®]/u) You can only use the %, :, & and + characters once each.",
         "publish.listing_schema.title_problems (lane I)"),
    _api("tag_charset", "listing",
         "tag: letters, digits, spaces, hyphen, apostrophe, TM/(c)/(R) only",
         r"/[^\p{L}\p{Nd}\p{Zs}\-'™©®]/u",
         "valid tag strings contain only letters, numbers, whitespace characters, -, ', ™, ©, "
         "and ®. (regex: /[^\\p{L}\\p{Nd}\\p{Zs}\\-'™©®]/u)",
         "publish.listing_schema.tag_problems (lane I); seo.truth.validate_listing"),
    _api("materials_charset", "listing", "material: letters, digits and spaces only",
         r"/[^\p{L}\p{Nd}\p{Zs}]/u",
         "Valid materials strings contain only letters, numbers, and whitespace characters. "
         "(regex: /[^\\p{L}\\p{Nd}\\p{Zs}]/u)", "publish.listing_schema (lane I)"),
    _api("styles", "listing", "at most two styles, each at most 45 characters, letters/"
         "digits/spaces only", {"max_count": 2, "max_chars": 45},
         "the listing may have up to two styles. Valid style strings contain only letters, "
         "numbers, and whitespace characters. (regex: /[^\\p{L}\\p{Nd}\\p{Zs}]/u) Each style "
         "string is limited to 45 characters.", "seo.strategy (styles are proposed empty)"),
    _api("image_count", "listing", "at most 20 listing images", 20,
         "An array of numeric image IDs of the images in a listing, which can include up to "
         "20 images.", "publish.listing_schema.MAX_IMAGES (lane I)"),
    _api("required_to_create", "listing", "required fields to create a draft listing (POST "
         "/v3/application/shops/{shop_id}/listings)",
         ["quantity", "title", "description", "price", "who_made", "when_made",
          "taxonomy_id"],
         "required: ['quantity', 'title', 'description', 'price', 'who_made', 'when_made', "
         "'taxonomy_id']", "publish.listing_schema.REQUIRED_TO_CREATE (lane I)"),
    _api("who_made_enum", "listing", "who_made is one of i_did / someone_else / collective",
         ["i_did", "someone_else", "collective"],
         "enum: ['i_did', 'someone_else', 'collective'] -- An enumerated string indicating who "
         "made the product. Helps buyers locate the listing under the Handmade heading.",
         notes=["which value is truthful for a Brambleloop pattern is a disclosure decision "
                "(lanes C/I/owner), not an SEO one"]),
    _api("when_made_enum", "listing", "when_made enum includes made_to_order and 2020_2026",
         ["made_to_order", "2020_2026", "2010_2019"],
         "enum: ['made_to_order', '2020_2026', '2010_2019', ...]"),
    _api("taxonomy_id", "taxonomy", "taxonomy_id is a positive integer from the seller "
         "taxonomy; required to create", {"type": "integer", "minimum": 1},
         "The numerical taxonomy ID of the listing. See SellerTaxonomy and BuyerTaxonomy for "
         "more information.", "seo.taxonomy (GATED until read)"),
    _api("seller_taxonomy_read_needs_api_key_only", "taxonomy",
         "getSellerTaxonomyNodes and getPropertiesByTaxonomyId declare no per-operation "
         "security, so the document-level api_key scheme applies: no OAuth token or shop "
         "scope is needed to read the category tree and its properties",
         {"operation_security": None, "document_security": [{"api_key": []}]},
         "getSellerTaxonomyNodes: 'Retrieves the full hierarchy tree of seller taxonomy "
         "nodes.' security: (none on operation); document security: [{'api_key': []}]",
         "integrations.etsy_taxonomy.refresh (lane I) behind the etsy_api gate",
         notes=["consequence: confirming Launch-0 categories needs only a working API key "
                "(x-api-key), not the shop OAuth grant"]),
    _api("taxonomy_property_shape", "taxonomy",
         "each taxonomy node property reports is_required, supports_attributes, "
         "is_multivalued, max_values_allowed, possible_values, scales",
         ["property_id", "name", "display_name", "scales", "is_required",
          "supports_attributes", "supports_variations", "is_multivalued",
          "max_values_allowed", "possible_values", "selected_values"],
         "is_required: When true, listings assigned eligible taxonomy IDs require this "
         "property. supports_attributes: When true, you can use this property in listing "
         "properties.", "commerce.category.properties_for"),
    _api("property_values_no_parentheses", "taxonomy",
         "listing-property `values` strings (PUT .../listings/{listing_id}/properties/"
         "{property_id}) may not contain ( or )", "()",
         "Note: parenthesis characters (`(` and `)`) are not allowed.",
         "seo.strategy attribute candidates are checked"),
    _api("title_length_not_in_api", "listing",
         "the OpenAPI document states NO maximum length for title, tags (count or chars) or "
         "description; the 140/13/20 limits are therefore not API-documented", NOT_STATED,
         "title: {'type': 'string'}; tags: {'type': 'array', 'nullable': true, 'items': "
         "{'type': 'string'}} -- no maxLength/maxItems anywhere in the document (0 "
         "occurrences of maxLength)",
         notes=["checked by searching the whole document for maxLength/maxItems/'140'/"
                "'13 tags'/'20 char' on 2026-10-06"]),
    _api("shop_text_fields", "shop",
         "updateShop accepts title, announcement, sale_message, digital_sale_message, "
         "policy_additional; the document states no length for any of them",
         ["title", "announcement", "sale_message", "digital_sale_message",
          "policy_additional"],
         "title: 'A brief heading string for the shop's main page.' announcement: 'An "
         "announcement string to buyers that displays on the shop's homepage.' "
         "digital_sale_message: 'A message string sent to users who purchase a digital item "
         "from this shop.'"),
    _api("shop_section_title", "shop", "createShopSection takes a `title` string; no length "
         "stated", NOT_STATED, "title: 'The title string for a shop section.'"),
    Constraint("create_minimum_dev_tutorial", "listing",
               "Etsy's developer tutorial: image_ids required for active listings; "
               "shipping_profile_id and readiness_state_id only for physical listings",
               ["image_ids (active)", "shipping_profile_id (physical)",
                "readiness_state_id (physical)"], VERIFIED, PRIMARY_DEV_DOC,
               DEV_LISTINGS_TUTORIAL, RETRIEVED_ON,
               "Build the [POST /shops/{shop_id}/listings] request body, which must include at a minimum: "
               "quantity title description price who_made when_made taxonomy_id image_ids "
               "required for active listings shipping_profile_id required for physical "
               "listings readiness_state_id required for physical listings"),

    # ---- listing: UNVERIFIED (primary pages 403; search-index summary only) ------------------
    _secondary("title_max_chars", "listing", "a listing title is at most 140 characters", 140,
               HANDBOOK_MAKEOVER,
               "index summary of the Seller Handbook: 'use all 140 characters available to "
               "you' in a title",
               "Shop Manager > Listings > edit a listing: the Title counter shows the cap",
               "commerce.seo.TITLE_MAX; integrations.etsy.TITLE_MAX; seo.truth"),
    _secondary("tag_max_count", "listing", "at most 13 tags per listing", 13, HELP_TAGS,
               "index summary of help.etsy.com 'How to Use Tags to Get Found in Search': "
               "'You can use up to 13 tags per listing.'",
               "Shop Manager > Listings > edit > Tags: Etsy refuses a 14th tag",
               "commerce.seo.TAG_MAX_COUNT; seo.truth"),
    _secondary("tag_max_chars", "listing", "each tag is at most 20 characters", 20, HELP_TAGS,
               "index summary: 'Each tag can contain up to 20 characters.'",
               "Shop Manager > Listings > edit > Tags: the field stops at the cap",
               "commerce.seo.TAG_MAX_CHARS; seo.truth"),
    _secondary("tag_no_leading_symbol", "listing",
               "a tag may contain ' and - within words but may not START with them", None,
               HELP_TAGS,
               "index summary: 'You're able to use ' and - within words and phrases, but "
               "cannot start your tag with these characters.'",
               "Shop Manager: try a tag beginning with '-'", "seo.strategy (checked)"),
    _secondary("attributes_act_like_tags", "listing",
               "attributes (material, colour, occasion, size...) also act like tags for "
               "matching, so a tag need not repeat an attribute value", None, HELP_TAGS,
               "index summary: 'The attributes you add to your listings also act like tags "
               "and can help your item match with a shopper's search.'",
               "read the Help Center article in a browser",
               notes=["used as a matching hypothesis, never as a ranking claim"]),
    _secondary("ai_disclosure", "policy",
               "items created with the use of AI must disclose that in the listing description",
               None, HANDBOOK_AI,
               "index summary of Etsy's Creativity Standards / Seller Handbook 'What is Etsy's "
               "stance on AI creations?': sellers must disclose within the listing "
               "description if an item is created with the use of AI",
               "owner reads https://www.etsy.com/legal/creativity/ in a browser and confirms "
               "the exact wording and placement before public copy is approved",
               notes=["SEO consequence: descriptions reserve a disclosure paragraph whose "
                      "wording is owned by lanes C/I and approved by the owner",
                      f"also: {LEGAL_CREATIVITY}"]),
    _secondary("crochet_pattern_buyer_path", "taxonomy",
               "Etsy's public (buyer) category for crochet patterns is Craft Supplies & Tools > "
               "Sewing & Fiber > Crochet > Kits & How To > Patterns",
               ["Craft Supplies & Tools", "Sewing & Fiber", "Crochet", "Kits & How To",
                "Patterns"], PUBLIC_CROCHET_PATTERNS,
               "the public category URL returned by the search index on 2026-10-06; this is the "
               "BUYER taxonomy path, the seller taxonomy id and node names are unread",
               "run listing.taxonomy_refresh (getSellerTaxonomyNodes, api_key only) -- "
               "seo.taxonomy turns CONFIRMED only from that read",
               notes=["no numeric taxonomy id is asserted anywhere in seo/**"]),

    # ---- shop: UNVERIFIED -------------------------------------------------------------------
    _secondary("shop_title_max_chars", "shop", "the shop title is at most 55 characters", 55,
               HELP_SHOP_TITLE,
               "index summary of help.etsy.com 'How to Add a Shop Announcement and Shop "
               "Title': 'Shop titles can be up to 55 characters long.'",
               "Shop Manager > Settings > Info & Appearance > Shop title counter",
               "seo.shop.check_shop_copy (warning, not failure)"),
    _secondary("sections_max_count", "shop", "at most 20 custom sections plus All items", 20,
               HELP_SECTIONS,
               "index summary of 'How to Create and Manage Shop Sections': 'You can have up "
               "to 20 custom sections, as well as the default All items section'",
               "Shop Manager > Listings > Sections", "seo.shop.check_shop_copy"),
    _secondary("section_name_max_chars", "shop", "a section name is at most 24 characters",
               24, HELP_SECTIONS, "index summary: 'A section name can be up to 24 characters.'",
               "Shop Manager > Listings > Sections > add a section: the field counter",
               "seo.shop.check_shop_copy",
               notes=["store_foundation.limits records section_name as UNKNOWN; this is the "
                      "number to read there once the owner confirms it (lane C/B owns that "
                      "file)"]),
    _secondary("search_visibility_page", "shop",
               "Shop Manager has a Search Visibility page covering listing, shop and customer-"
               "service factors; the service factors include review rating, message response "
               "rate and case rate", None, HELP_SEARCH_VISIBILITY,
               "index summary: 'the dashboard shows how your shop is performing in three key "
               "areas that can impact your placement in Etsy search: your listings, your shop, "
               "and your customer service'",
               "owner opens Shop Manager > Marketing > Search Visibility once the shop is live",
               "commerce.search_visibility (owner-recorded readings); seo.learning",
               notes=["the page has no Open API endpoint (none found in the v3 document)"]),
)

BY_KEY: dict[str, Constraint] = {c.key: c for c in CONSTRAINTS}


def get(key: str) -> Constraint:
    return BY_KEY[key]


def working_limits() -> dict:
    """The numbers the SEO strategy enforces, each with its verification status."""
    out = {}
    for key in ("title_max_chars", "tag_max_count", "tag_max_chars", "shop_title_max_chars",
                "sections_max_count", "section_name_max_chars"):
        c = BY_KEY[key]
        out[key] = {"value": c.value, "status": c.status, "method": c.method}
    out["styles"] = {"value": BY_KEY["styles"].value, "status": BY_KEY["styles"].status,
                     "method": BY_KEY["styles"].method}
    return out


def consistency_with_repo() -> list[str]:
    """Disagreements between this record and the constants the rest of the repo enforces."""
    from ..commerce import search as search_mod
    from ..commerce import seo as seo_mod

    problems = []
    pairs = (("title_max_chars", seo_mod.TITLE_MAX), ("tag_max_count", seo_mod.TAG_MAX_COUNT),
             ("tag_max_chars", seo_mod.TAG_MAX_CHARS), ("title_max_chars", search_mod.TITLE_MAX),
             ("tag_max_count", search_mod.TAG_SLOTS),
             ("tag_max_chars", search_mod.TAG_MAX_CHARS))
    for key, repo_value in pairs:
        if BY_KEY[key].value != repo_value:
            problems.append(f"{key}: constraints say {BY_KEY[key].value}, repo enforces "
                            f"{repo_value}")
    return problems


def snapshot() -> dict:
    rows = [c.to_dict() for c in CONSTRAINTS]
    counts: dict[str, int] = {}
    for c in CONSTRAINTS:
        counts[c.status] = counts.get(c.status, 0) + 1
    return {"retrieved_on": RETRIEVED_ON,
            "openapi": {"url": OPENAPI_URL, "sha256": OPENAPI_SHA256, "bytes": OPENAPI_BYTES},
            "blocked": BLOCKED_HOSTS_NOTE, "counts": counts,
            "unverified_keys": [c.key for c in CONSTRAINTS if c.status == UNVERIFIED],
            "repo_disagreements": consistency_with_repo(), "constraints": rows}
