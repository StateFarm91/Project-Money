"""The canonical Etsy surface registry: what software may do with each Shop Manager page.

Research: `research/ETSY_SURFACE_REGISTRY.md`, 2026-09-25.

Every earlier document in this repository answered a narrower question -- can we create a
listing (`publish/listing_schema.py`), can we reach the wire (`integrations/etsy.py`), what
must a person type (`commerce/shop_package.py`). None of them answered the one an autonomous
operator actually needs: **for each surface of the shop, what can this company see, what can
it change, and what can only a person do?** Without that answer the system's default is to
treat a surface it has never looked at as a surface with nothing wrong on it, which is this
repository's recurring defect -- a verdict computed from the absence of evidence.

So the registry is built to make that failure impossible to commit by accident.

**Six verdicts, and the two that are easy to confuse are kept apart by force.**
`UNSUPPORTED` is a claim about Etsy: it offers no API for this surface. `NOT_APPLICABLE` is a
claim about us: a digital-pattern shop has nothing here. Shipping profiles are the clean
example -- Etsy ships thirteen endpoints for them and `shipping_profile_id` is *"Required when
listing type is `physical`"*, so the API is rich and the surface is still nothing to do with
us. Etsy Ads is the other -- it is central to how sellers are told to grow, and there is no
endpoint, no scope and no field. `check_registry()` refuses a surface that claims one verdict
with the other's evidence: `UNSUPPORTED` must carry a recorded absence probe, and
`NOT_APPLICABLE` must carry a reason in words.

**An absence is evidence only when it is reproducible.** Every `UNSUPPORTED` verdict rests on
`ABSENCE_PROBES`: search terms counted in Etsy's own published OpenAPI document, with the
document's version and SHA-256 recorded beside them. `verify_absence()` recounts them against
a document handed to it and reports every term whose count has moved. The day Etsy ships an
Ads API, this registry says so out loud instead of ageing quietly into a lie.

**Emptiness is never a pass.** `EvidenceState` has four values and only one of them is good.
A surface with no collector is `NO_COLLECTOR`; a collector that has never run is `NO_EVIDENCE`;
a record older than its surface's tolerance is `STALE`. `SurfaceStatus.green` is true for
`FRESH` with clean checks and for nothing else. The same rule runs one level down: in
`assess_shop`, a field Etsy returned as `null` is a **FAIL** (the thing is not set) and a field
the snapshot does not contain at all is **NO_EVIDENCE** (nobody looked), and those are
different facts that a boolean would have merged into "false, so fine".

**A verdict names a scope, and a scope we were not granted is not a capability.** Etsy granted
this shop `listings_r listings_w listings_d shops_r shops_w` on 2026-09-25 (`BUILD_STATE.md`,
read off the callback's own success page). Every receipt, payment and ledger endpoint requires
`transactions_r`, which is **not in that set**. So the honest reading of the Orders surface
today is not "we can read orders"; it is "Etsy offers a read we are not authorised to make",
and `scope_gaps()` computes that rather than leaving it to be remembered.

Nothing in this module calls Etsy. It was built from Etsy's published OpenAPI description and
its developer documentation, both fetched on 2026-09-25, and from evidence already recorded in
this repository. No authenticated call was made, no listing was touched, nothing was spent.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

# ---------------------------------------------------------------------------
# Verdicts
# ---------------------------------------------------------------------------

#: Etsy exposes the surface's own state to a read this company may make.
OBSERVE = "OBSERVE"
#: Etsy exposes nothing for this surface; a legitimate **proxy** is computable from data it
#: does expose, and the proxy is labelled a proxy everywhere it is used.
ANALYZE = "ANALYZE"
#: Etsy exposes a write this company may make, so software can change the surface's state.
ACT = "ACT"
#: No API, and something here is a person's job. Carries an owner-action entry, always.
OWNER_ONLY = "OWNER_ONLY"
#: The surface does not apply to a shop that sells digital patterns. Carries a reason.
NOT_APPLICABLE = "NOT_APPLICABLE"
#: Etsy offers no API for it. Carries a reproducible absence probe, always.
UNSUPPORTED = "UNSUPPORTED"

VERDICTS = (OBSERVE, ANALYZE, ACT, OWNER_ONLY, NOT_APPLICABLE, UNSUPPORTED)

# Work classes, from the owner's rule: Build 2 may finish with B, C and D outstanding.
CLASS_A = "A"   # first-sale blocker
CLASS_B = "B"   # launch week
CLASS_C = "C"   # post-launch continuous improvement
CLASS_D = "D"   # parked on real-world evidence: customers, settlements, traffic
CLASS_NONE = "-"
WORK_CLASSES = (CLASS_A, CLASS_B, CLASS_C, CLASS_D, CLASS_NONE)

# Who says a surface is required before the first sale. Kept separate from the boolean,
# because "Etsy will not let you" and "we decided" are different kinds of requirement and
# only one of them is negotiable.
BY_ETSY = "etsy"
BY_US = "this_company"
BY_LAW = "law_or_regulator"
NOT_REQUIRED = "not_required"
REQUIREMENT_BASES = (BY_ETSY, BY_US, BY_LAW, NOT_REQUIRED)

# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Source:
    """One document, with what happened when this build tried to read it.

    `http_status` is recorded even when it is 403, because a policy page that refuses
    automated readers is the reason a claim resting on it is secondary, and a reader three
    months from now needs to know that was tried rather than assumed.
    """

    key: str
    url: str
    fetched_on: str | None
    http_status: int | None
    sha256: str | None = None
    note: str = ""

    @property
    def readable(self) -> bool:
        return self.http_status == 200

    def to_dict(self) -> dict:
        return {"key": self.key, "url": self.url, "fetched_on": self.fetched_on,
                "http_status": self.http_status, "sha256": self.sha256,
                "readable": self.readable, "note": self.note}


#: The exact document this registry's PRIMARY claims are read from.
OPENAPI_URL = "https://www.etsy.com/openapi/generated/oas/3.0.0.json"
OPENAPI_VERSION = "3.0.0"
OPENAPI_SHA256 = "e6f95f1a38810cadf920796bc0e08797fb499312c8b50f317454e6ebd39531f7"
READ_ON = "2026-09-25"

SOURCES: dict[str, Source] = {s.key: s for s in (
    Source("openapi", OPENAPI_URL, READ_ON, 200, OPENAPI_SHA256,
           "Etsy Open API v3 description, document version 3.0.0, 908,638 bytes, "
           "76 paths, 108 operations."),
    Source("dev_webhooks", "https://developer.etsy.com/documentation/essentials/webhooks/",
           READ_ON, 200, None,
           "The only order-event push Etsy offers, and the portal that configures it."),
    Source("dev_auth", "https://developer.etsy.com/documentation/essentials/authentication/",
           READ_ON, 200, None, "Scope table and OAuth 2.0 flow."),
    Source("dev_shopmanagement",
           "https://developer.etsy.com/documentation/tutorials/shopmanagement/",
           READ_ON, 200, None, "Etsy's own tutorial for what updateShop changes."),
    Source("dev_ratelimits",
           "https://developer.etsy.com/documentation/essentials/rate-limits/",
           READ_ON, 200, None,
           "QPS/QPD sliding window; any collector's call budget comes from here."),
    Source("help_etsy", "https://help.etsy.com/hc/en-us/", READ_ON, 403, None,
           "HTTP 403 to every automated request from this environment, with and without a "
           "browser user agent. Anything resting on it is SECONDARY."),
    Source("etsy_legal_fees", "https://www.etsy.com/legal/fees/", READ_ON, 403, None,
           "HTTP 403. The fee schedule cannot be read from here."),
    Source("build_state", "brambleloop/BUILD_STATE.md", READ_ON, None, None,
           "This repository's own build record: the granted scope set, read off the OAuth "
           "callback's success page on 2026-09-25."),
    Source("shop_manager_nav", "owner-supplied Shop Manager navigation", READ_ON, None, None,
           "The surface names and their locations come from the owner's own reading of Shop "
           "Manager. Nobody here has seen the page: help.etsy.com is 403 and no shop of ours "
           "was open to look at. Surface *names* are therefore SECONDARY; every verdict "
           "about what the API does is PRIMARY."),
)}

# Evidence kinds.
OPENAPI_SAYS = "openapi_says"          # a sentence or schema element in Etsy's document
OPENAPI_ABSENCE = "openapi_absence"    # a counted, reproducible absence in that document
DEV_DOC_SAYS = "developer_doc_says"    # a sentence on developer.etsy.com
SECONDARY_CLAIM = "secondary"          # from a source this environment could not read
OUR_DECISION = "our_decision"          # a decision of this company, not a fact about Etsy
INFERRED = "inferred"                  # our reading, arguable
UNKNOWN = "unknown"                    # genuinely not established
EVIDENCE_KINDS = (OPENAPI_SAYS, OPENAPI_ABSENCE, DEV_DOC_SAYS, SECONDARY_CLAIM,
                  OUR_DECISION, INFERRED, UNKNOWN)


@dataclass(frozen=True)
class Evidence:
    kind: str
    statement: str
    source: str

    @property
    def primary(self) -> bool:
        """Whether this rests on a document this build actually read."""
        return self.kind in (OPENAPI_SAYS, OPENAPI_ABSENCE, DEV_DOC_SAYS)

    def to_dict(self) -> dict:
        return {"kind": self.kind, "statement": self.statement, "source": self.source,
                "primary": self.primary}


# ---------------------------------------------------------------------------
# Reproducible absence
# ---------------------------------------------------------------------------

#: Case-insensitive occurrence counts in Etsy's OpenAPI document, version 3.0.0, SHA-256
#: above, counted on 2026-09-25. These are what every UNSUPPORTED verdict below rests on.
#: A non-zero count is recorded too, with what the occurrences actually are, because "the
#: word appears" and "the capability exists" are not the same claim, and the gap between them
#: is exactly where a confident wrong answer lives.
ABSENCE_PROBES: dict[str, tuple[int, str]] = {
    "advertis": (0, "no advertising anything: no Ads endpoint, scope, field or enum"),
    "offsite": (0, "Offsite Ads is not named once, not even as a fee line"),
    "campaign": (0, "no ad campaign object"),
    "budget": (0, "no budget field anywhere, so no ad spend ceiling can be read or set"),
    "impression": (0, "no impression counter"),
    "stats": (0, "no shop statistics resource"),
    "statistic": (0, "the same claim, spelled out"),
    "traffic": (0, "no traffic resource"),
    "visit": (0, "no visit counter"),
    "insight": (0, "no Marketplace Insights resource"),
    "dashboard": (0, "the Shop Manager dashboard has no API representation"),
    "violation": (0, "no policy-violation or takedown-notice resource"),
    "infringement": (0, "the same, for intellectual-property claims"),
    "subscription": (0, "no subscription or Etsy Plus resource"),
    "shared access": (0, "no shared-access user management"),
    "social": (0, "no social-media posting resource"),
    "seo": (0, "no search-visibility resource"),
    "keyword": (18, "all 18 are the public listing-search `keywords` parameter and its sort "
                    "notes -- a marketplace search, never our own search performance"),
    "coupon": (8, "all 8 are read-only amounts on a receipt; nothing creates a coupon"),
    "discount": (21, "read-only: receipt discount amounts, and the buyer-facing price block "
                     "on /listings/batch that reports a promotion someone else created"),
    "conversation": (1, "the single occurrence is the description of `vacation_autoreply`: "
                        "'displayed in new conversations'. There is no Messages resource"),
    "favorite": (3, "read-only counters on Shop and Listing; nothing reads who, and nothing "
                    "could create one, which is the point"),
}


def verify_absence(document_text: str) -> list[dict]:
    """Recount every probe against a document and report each term whose count has moved.

    The whole negative half of this registry is one claim -- *Etsy offers no API for this* --
    and a claim like that decays silently. This makes it falsifiable by anybody holding the
    current document: hand it the bytes, and either the list is empty or the registry is out
    of date and says which line.

    Deliberately not an HTTP client. A fetcher here would make the check depend on a network
    this environment does not always have, and a check that skips when the network is down is
    a check that passes when the network is down.
    """
    lowered = (document_text or "").lower()
    drift: list[dict] = []
    for term, (expected, _why) in sorted(ABSENCE_PROBES.items()):
        actual = lowered.count(term)
        if actual != expected:
            drift.append({"term": term, "expected": expected, "actual": actual,
                          "direction": "appeared" if actual > expected else "vanished"})
    return drift


def document_fingerprint(document_text: str) -> str:
    """SHA-256 of a document, so `verify_absence` drift can be attributed to a version."""
    return hashlib.sha256((document_text or "").encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# The operations Etsy actually publishes
# ---------------------------------------------------------------------------

#: Every operationId in Etsy's OpenAPI document, version 3.0.0, SHA-256 above: 105 of them
#: across 76 paths. Held here so that a surface cannot cite an endpoint that does not exist.
#: An invented operation name is the most natural way for a registry like this to drift into
#: fiction -- it reads exactly like a real one, it never gets called in shadow mode, and the
#: first thing that disproves it is a 404 during a launch. `check_registry()` refuses one.
ETSY_OPERATIONS: frozenset[str] = frozenset({
    "consolidateShopReturnPolicies", "createDraftListing",
    "createListingTranslation", "createReceiptShipment",
    "createShopReadinessStateDefinition", "createShopReturnPolicy",
    "createShopSection", "createShopShippingProfile",
    "createShopShippingProfileDestination", "createShopShippingProfileUpgrade",
    "deleteListing", "deleteListingFile", "deleteListingImage",
    "deleteListingPersonalization", "deleteListingProperty", "deleteListingVideo",
    "deleteShopReadinessStateDefinition", "deleteShopReturnPolicy",
    "deleteShopSection", "deleteShopShippingProfile",
    "deleteShopShippingProfileDestination", "deleteShopShippingProfileUpgrade",
    "deleteUserAddress", "findAllActiveListingsByShop", "findAllListingsActive",
    "findShops", "getAllListingFiles", "getBuyerTaxonomyNodes",
    "getFeaturedListingsByShop", "getHolidayPreferences", "getListing",
    "getListingFile", "getListingImage", "getListingImages", "getListingInventory",
    "getListingOffering", "getListingPersonalization", "getListingProduct",
    "getListingProperties", "getListingProperty", "getListingTranslation",
    "getListingVariationImages", "getListingVideo", "getListingVideos",
    "getListingsByListingIds", "getListingsByShop", "getListingsByShopReceipt",
    "getListingsByShopReturnPolicy", "getListingsByShopSectionId",
    "getListingsInventoryByListingIds", "getListingsShippingByListingIds", "getMe",
    "getPaymentAccountLedgerEntryPayments", "getPayments",
    "getPropertiesByBuyerTaxonomyId", "getPropertiesByTaxonomyId",
    "getReviewsByListing", "getReviewsByShop", "getSellerTaxonomyNodes",
    "getShippingCarriers", "getShop", "getShopByOwnerUserId",
    "getShopPaymentAccountLedgerEntries", "getShopPaymentAccountLedgerEntry",
    "getShopPaymentByReceiptId", "getShopProductionPartners",
    "getShopReadinessStateDefinition", "getShopReadinessStateDefinitions",
    "getShopReceipt", "getShopReceiptTransaction",
    "getShopReceiptTransactionsByListing", "getShopReceiptTransactionsByReceipt",
    "getShopReceiptTransactionsByShop", "getShopReceipts", "getShopReturnPolicies",
    "getShopReturnPolicy", "getShopSection", "getShopSections",
    "getShopShippingProfile", "getShopShippingProfileDestinationsByShippingProfile",
    "getShopShippingProfileUpgrades", "getShopShippingProfiles", "getUser",
    "getUserAddress", "getUserAddresses", "ping", "tokenScopes",
    "updateHolidayPreferences", "updateListing", "updateListingInventory",
    "updateListingPersonalization", "updateListingProperty",
    "updateListingTranslation", "updateShop", "updateShopReadinessStateDefinition",
    "updateShopReceipt", "updateShopReturnPolicy", "updateShopSection",
    "updateShopShippingProfile", "updateShopShippingProfileDestination",
    "updateShopShippingProfileUpgrade", "updateVariationImages",
    "uploadListingFile", "uploadListingImage", "uploadListingVideo",
})


# ---------------------------------------------------------------------------
# Scopes
# ---------------------------------------------------------------------------

#: Etsy's twelve OAuth scopes, in Etsy's own wording, from the OpenAPI security scheme.
SCOPE_MEANINGS: dict[str, str] = {
    "address_r": "see billing and shipping addresses",
    "address_w": "update billing and shipping addresses",
    "email_r": "read a user profile",
    "listings_d": "delete listings",
    "listings_r": "see all listings (including expired etc)",
    "listings_w": "create/edit listings",
    "profile_r": "see all profile data",
    "profile_w": "update user profile, avatar, etc",
    "shops_r": "see private shop info",
    "shops_w": "update shop",
    "transactions_r": "see all checkout/payment data",
    "transactions_w": "update receipts",
}

#: What Etsy actually granted this shop, from `BUILD_STATE.md`'s record of the 2026-09-25
#: authorization. Held as data with its date rather than imported from the OAuth module,
#: because what we *asked for* and what Etsy *granted* are different facts and only the
#: second one is a capability.
GRANTED_SCOPES: tuple[str, ...] = ("listings_r", "listings_w", "listings_d",
                                   "shops_r", "shops_w")
GRANTED_ON = "2026-09-25"


# ---------------------------------------------------------------------------
# Owner actions
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OwnerAction:
    """One thing only a person can do, in the format the Execution Directive requires.

    `evidence_required` is the field that keeps this honest. Without it an owner action is
    closed by somebody saying they did it, which is exactly the verdict-from-assertion this
    registry exists to stop. With it, closing the action means producing something a check
    can read.
    """

    key: str
    surface: str
    action: str
    why_software_cannot: str
    minutes: int
    risk: str
    evidence_required: str
    max_cost_cad: float = 0.0
    consequence_of_delay: str = ""
    blocks_first_sale: bool = False

    def to_dict(self) -> dict:
        return {"key": self.key, "surface": self.surface, "action": self.action,
                "why_software_cannot": self.why_software_cannot, "minutes": self.minutes,
                "risk": self.risk, "evidence_required": self.evidence_required,
                "max_cost_cad": self.max_cost_cad,
                "consequence_of_delay": self.consequence_of_delay,
                "blocks_first_sale": self.blocks_first_sale}


# ---------------------------------------------------------------------------
# Collectors
# ---------------------------------------------------------------------------

#: The only collectors that exist. A name here is a promise that a function in this module
#: turns a recorded observation into checks; it is **not** a promise that the observation has
#: ever been made. `EvidenceState` carries that second fact and refuses to conflate them.
COLLECTORS: dict[str, str] = {
    "shop_snapshot": "assess_shop(): the fields `getShop` returns, checked one at a time",
    "listing_census": "listing_census_drift(): our listing set against what the shop shows",
}


@dataclass(frozen=True)
class Surface:
    key: str
    name: str
    where: str
    what: str
    verdict: str
    evidence: tuple[Evidence, ...]
    operations: tuple[str, ...] = ()
    scopes: tuple[str, ...] = ()
    required_before_first_sale: bool = False
    requirement_basis: str = NOT_REQUIRED
    why_required: str = ""
    work_class: str = CLASS_NONE
    collector: str | None = None
    owner_action: OwnerAction | None = None
    not_applicable_because: str | None = None
    max_age_days: int | None = None
    unknowns: tuple[str, ...] = ()

    @property
    def primary_evidence(self) -> tuple[Evidence, ...]:
        return tuple(e for e in self.evidence if e.primary)

    def missing_scopes(self, granted: Iterable[str]) -> tuple[str, ...]:
        held = set(granted)
        return tuple(s for s in self.scopes if s not in held)

    def to_dict(self) -> dict:
        return {"key": self.key, "name": self.name, "where": self.where, "what": self.what,
                "verdict": self.verdict, "operations": list(self.operations),
                "scopes": list(self.scopes),
                "required_before_first_sale": self.required_before_first_sale,
                "requirement_basis": self.requirement_basis,
                "why_required": self.why_required, "work_class": self.work_class,
                "collector": self.collector,
                "owner_action": self.owner_action.to_dict() if self.owner_action else None,
                "not_applicable_because": self.not_applicable_because,
                "unknowns": list(self.unknowns),
                "evidence": [e.to_dict() for e in self.evidence]}


# ---------------------------------------------------------------------------
# The registry
# ---------------------------------------------------------------------------
#
# One entry per Shop Manager surface, in the order the brief named them, followed by the
# surfaces that are not pages in Shop Manager but are part of running the shop and would
# otherwise have no home: shop sections, digital files, taxonomy, reviews, webhooks and the
# developer portal.
#
# Reading an entry: `verdict` is what software may do with the surface *as a whole*. Several
# surfaces are split down the middle -- Messages has exactly one automated write and no read;
# Sales & Discounts has a read and no write -- and where that happens the verdict names the
# governing half and the evidence names the other one. The verdict is never the more
# flattering half.

_SURFACES: tuple[Surface, ...] = (

    # -- 1. Dashboard ------------------------------------------------------
    Surface(
        key="dashboard",
        name="Dashboard",
        where="Shop Manager > Dashboard",
        what="Etsy's landing page for a seller: orders awaiting action, recent activity, a "
             "stats snapshot, ad performance and whatever notices Etsy wants seen.",
        verdict=UNSUPPORTED,
        operations=(),
        evidence=(
            Evidence(OPENAPI_ABSENCE, "'dashboard' appears 0 times in Etsy's OpenAPI "
                                      "document.", "openapi"),
            Evidence(OPENAPI_SAYS, "The document's 27 tags are User, Shop, ShopListing, "
                                   "Receipt, Payment, Ledger Entry, Taxonomy, Review and "
                                   "their sub-resources. None of them is an aggregate view.",
                     "openapi"),
            Evidence(INFERRED, "The dashboard is a composition of surfaces below, so it "
                               "inherits their verdicts rather than having one of its own. "
                               "Nothing is lost by having no API for the composition; what "
                               "is lost is the notices Etsy only shows here, which is "
                               "handled under policy_violations.", "openapi"),
        ),
        work_class=CLASS_NONE,
        requirement_basis=NOT_REQUIRED,
    ),

    # -- 2. Listings -------------------------------------------------------
    Surface(
        key="listings",
        name="Listings",
        where="Shop Manager > Listings",
        what="Creating, editing, activating, deactivating and deleting the shop's listings, "
             "with their images, files, attributes and price.",
        verdict=ACT,
        operations=("createDraftListing", "updateListing", "updateListingInventory",
                    "uploadListingImage", "uploadListingFile", "uploadListingVideo",
                    "updateListingProperty", "getListingsByShop", "getListing",
                    "getListingImages", "deleteListing"),
        scopes=("listings_w", "listings_r", "listings_d"),
        evidence=(
            Evidence(OPENAPI_SAYS, "POST /shops/{shop_id}/listings creates a draft; PATCH "
                                   "/shops/{shop_id}/listings/{listing_id} updates it; both "
                                   "list application/x-www-form-urlencoded as their only "
                                   "media type and both require listings_w.", "openapi"),
            Evidence(OPENAPI_SAYS, "\"Setting a `draft` listing to `active` will also publish "
                                   "the listing on etsy.com and requires that the listing "
                                   "have an image set.\"", "openapi"),
            Evidence(OPENAPI_SAYS, "updateListing has no `price` property: price is set by "
                                   "PUT /listings/{listing_id}/inventory, which is the only "
                                   "application/json write in the whole document.", "openapi"),
            Evidence(INFERRED, "The write path is implemented in `integrations/etsy.py` and "
                               "has never created a listing on Etsy. ACT here means Etsy "
                               "offers the write and we hold the scope, not that the round "
                               "trip has been demonstrated.", "build_state"),
        ),
        required_before_first_sale=True,
        requirement_basis=BY_ETSY,
        why_required="There is no sale without an active listing, and Etsy refuses to "
                     "activate one that has no image.",
        work_class=CLASS_A,
        collector="listing_census",
        max_age_days=1,
    ),

    # -- 3. Messages -------------------------------------------------------
    Surface(
        key="messages",
        name="Messages",
        where="Shop Manager > Messages",
        what="The buyer-seller inbox: questions before a sale, problems after one, and "
             "Etsy's own response-time expectations.",
        verdict=OWNER_ONLY,
        operations=("updateShop",),
        scopes=("shops_w",),
        evidence=(
            Evidence(OPENAPI_ABSENCE, "'conversation' appears once in the whole document, in "
                                      "the description of `vacation_autoreply`. There is no "
                                      "Messages, Conversation or Thread resource, no read, "
                                      "no send, no scope.", "openapi"),
            Evidence(DEV_DOC_SAYS, "The one message the API can cause: updateShop sets "
                                   "`digital_sale_message`, \"A message sent to the buyer's "
                                   "Etsy messages when they purchase any digital product "
                                   "from this shop\".", "dev_shopmanagement"),
            Evidence(OPENAPI_SAYS, "A receipt carries `message_from_buyer`, \"An optional "
                                   "message string from the buyer\" -- the note attached to "
                                   "an order, not the inbox, and it needs transactions_r.",
                     "openapi"),
            Evidence(OUR_DECISION, "Verdict is OWNER_ONLY rather than ACT because the "
                                   "governing half of this surface -- reading a buyer's "
                                   "question and answering it -- is a person's, and calling "
                                   "the surface ACT because one automated message exists "
                                   "would be the flattering half.", "shop_manager_nav"),
        ),
        required_before_first_sale=True,
        requirement_basis=BY_US,
        why_required="`digital_sale_message` is delivered at the instant of purchase and "
                     "cannot be retrofitted to a sale already made, so it has to be set "
                     "before the first one. The reply protocol itself is a person's job from "
                     "the first buyer onwards.",
        work_class=CLASS_A,
        owner_action=OwnerAction(
            key="messages_watch",
            surface="messages",
            action="Confirm Etsy message notifications reach an inbox you read daily "
                   "(Shop Manager > Settings > Emails), and agree a reply window. Nothing "
                   "in this system will ever see a buyer message.",
            why_software_cannot="Etsy publishes no messaging API at all: no endpoint, no "
                                "scope, no field. There is nothing to poll and nothing to "
                                "send.",
            minutes=10,
            risk="Low to perform. High to skip: an unanswered pre-sale question is a lost "
                 "sale, and an unanswered post-sale problem becomes a case.",
            evidence_required="A screenshot or statement of which address Etsy message "
                              "notifications go to, recorded against this action's key.",
            consequence_of_delay="Until the first buyer, none. From the first buyer, every "
                                 "message is unread until somebody happens to look.",
            blocks_first_sale=False,
        ),
    ),

    # -- 4. Orders ---------------------------------------------------------
    Surface(
        key="orders",
        name="Orders & Delivery",
        where="Shop Manager > Orders & Delivery",
        what="Receipts, their transactions, their buyers and their fulfilment state.",
        verdict=OBSERVE,
        operations=("getShopReceipts", "getShopReceipt", "getShopReceiptTransactionsByShop",
                    "getShopReceiptTransactionsByReceipt", "getListingsByShopReceipt"),
        scopes=("transactions_r",),
        evidence=(
            Evidence(OPENAPI_SAYS, "GET /shops/{shop_id}/receipts and five related reads "
                                   "return the whole order: status (`paid`, `completed`, "
                                   "`open`, `payment processing`, `canceled`), totals, tax, "
                                   "VAT, discount, the buyer's message and the transactions.",
                     "openapi"),
            Evidence(DEV_DOC_SAYS, "Etsy pushes four webhook events and all four are orders: "
                                   "order.paid, order.canceled, order.shipped, "
                                   "order.delivered. \"order.paid -- delivered immediately "
                                   "when an order receives payment.\"", "dev_webhooks"),
            Evidence(OPENAPI_SAYS, "Every one of those reads requires the transactions_r "
                                   "scope.", "openapi"),
            Evidence(INFERRED, "transactions_r is NOT in the scope set Etsy granted this "
                               "shop on 2026-09-25. As things stand this system cannot see "
                               "its own first sale -- not the order, not the buyer's note, "
                               "not the money. The read exists; the authorisation does not.",
                     "build_state"),
            Evidence(OPENAPI_SAYS, "updateShopReceipt and createReceiptShipment exist and "
                                   "write fulfilment state; for a digital download there is "
                                   "nothing to ship, so this company will not call them.",
                     "openapi"),
        ),
        required_before_first_sale=True,
        requirement_basis=BY_US,
        why_required="Etsy delivers a digital file without us, so a sale completes whether "
                     "or not we can see it. What breaks without transactions_r is every "
                     "downstream obligation: knowing a customer exists, version-aware "
                     "support, the first-hundred programme, and any revenue figure that is "
                     "not a guess.",
        work_class=CLASS_A,
        owner_action=OwnerAction(
            key="reauthorise_transactions_r",
            surface="orders",
            action="Re-authorise the Brambleloop app in a browser with transactions_r added "
                   "to the scope set (listings_r listings_w listings_d shops_r shops_w "
                   "transactions_r). Start the flow at /api/etsy/oauth/start as before.",
            why_software_cannot="Etsy grants scope only through the authorization-code flow, "
                                "which requires a human to approve the consent screen in a "
                                "browser. A refresh grant \"has the same scope as the token "
                                "granted by the initial Authorization Code grant\", so no "
                                "amount of refreshing widens it.",
            minutes=6,
            risk="Moderate and reversible. The new grant replaces the stored credential; if "
                 "the flow fails midway the old refresh token may already be spent, and the "
                 "write path is down until the flow is completed. Do it while you are at a "
                 "keyboard, not before a launch window.",
            evidence_required="A /api/etsy/oauth/status response whose granted scope list "
                              "contains transactions_r, plus the credential still openable.",
            consequence_of_delay="The shop can sell and this system will not know. Every "
                                 "customer-facing promise that depends on knowing who bought "
                                 "what is unenforceable until it is done.",
            blocks_first_sale=False,
        ),
        collector=None,
        unknowns=("Whether Etsy's consent screen re-grants the existing five scopes silently "
                  "or presents them again for approval. Settled by doing it once.",),
    ),

    # -- 5. Etsy Search Visibility ----------------------------------------
    Surface(
        key="search_visibility",
        name="Etsy Search Visibility",
        where="Shop Manager > Marketing > Etsy Search Visibility",
        what="Etsy's own report of which searches showed the shop's listings, and where.",
        verdict=ANALYZE,
        operations=("findAllListingsActive",),
        evidence=(
            Evidence(OPENAPI_ABSENCE, "'seo' 0, 'impression' 0, 'visit' 0, 'traffic' 0. Etsy "
                                      "publishes none of its own search-visibility numbers.",
                     "openapi"),
            Evidence(OPENAPI_SAYS, "What does exist is the public marketplace search: GET "
                                   "/listings/active takes `keywords`, `taxonomy_id`, "
                                   "`min_price`, `max_price` and `sort_on=score`, on the API "
                                   "key alone.", "openapi"),
            Evidence(INFERRED, "So a rank probe is computable -- does our listing appear in "
                               "the API's ranked results for keyword K, and at what "
                               "position. It is a **proxy**: it measures the API's search "
                               "index, not the buyer-facing etsy.com ranking, and it cannot "
                               "see impressions at all. Anywhere it is used it must say so.",
                     "openapi"),
        ),
        work_class=CLASS_C,
        requirement_basis=NOT_REQUIRED,
        why_required="",
        collector=None,
        unknowns=("Whether /listings/active's `score` ordering is the same ranking buyers "
                  "see. Etsy does not say. Not settleable without a live listing to compare "
                  "against a browser search.",),
    ),

    # -- 6. Stats / Shop Traffic ------------------------------------------
    Surface(
        key="stats",
        name="Stats (Shop Traffic)",
        where="Shop Manager > Stats",
        what="Visits, views, favourites, conversion rate and their sources over time.",
        verdict=UNSUPPORTED,
        operations=(),
        evidence=(
            Evidence(OPENAPI_ABSENCE, "'stats' 0, 'statistic' 0, 'traffic' 0, 'visit' 0, "
                                      "'impression' 0 in Etsy's OpenAPI document.",
                     "openapi"),
            Evidence(OPENAPI_SAYS, "The nearest readable numbers are counters on other "
                                   "objects -- Shop.num_favorers, Listing.num_favorers, "
                                   "Shop.review_count, Shop.transaction_sold_count. They are "
                                   "totals with no time series and no source breakdown.",
                     "openapi"),
            Evidence(OUR_DECISION, "A paste-in ingest, where the owner copies figures out of "
                                   "Shop Manager, is buildable and is not a collector. If it "
                                   "is ever built its records must be labelled as owner-"
                                   "reported, never merged into anything that reads as "
                                   "measured.", "shop_manager_nav"),
        ),
        work_class=CLASS_D,
        requirement_basis=NOT_REQUIRED,
    ),

    # -- 7. Marketplace Insights ------------------------------------------
    Surface(
        key="marketplace_insights",
        name="Marketplace Insights",
        where="Shop Manager > Marketing > Marketplace Insights",
        what="Etsy's aggregate demand and search-trend reporting for sellers.",
        verdict=UNSUPPORTED,
        operations=(),
        evidence=(
            Evidence(OPENAPI_ABSENCE, "'insight' 0 in Etsy's OpenAPI document.", "openapi"),
            Evidence(INFERRED, "`radar/` and `intel/` already compute demand signals from the "
                               "public listing search and from the benchmark shop. Those are "
                               "our measurements of the marketplace, not Etsy's insights, and "
                               "conflating them would put Etsy's authority behind our "
                               "arithmetic.", "openapi"),
        ),
        work_class=CLASS_C,
        requirement_basis=NOT_REQUIRED,
    ),

    # -- 8. Customer Service Stats ----------------------------------------
    Surface(
        key="customer_service_stats",
        name="Customer Service Stats",
        where="Shop Manager > Stats > Customer Service",
        what="Etsy's measure of a shop's service: response time, case rate, review average "
             "and the thresholds attached to seller standing.",
        verdict=UNSUPPORTED,
        operations=(),
        evidence=(
            Evidence(OPENAPI_ABSENCE, "'stats' 0 and no case, dispute-count or response-time "
                                      "resource. 'dispute' appears twice, both in "
                                      "Shop.include_dispute_form_link, a boolean about "
                                      "whether the shop's policies link to the EU online "
                                      "dispute form.", "openapi"),
            Evidence(OPENAPI_SAYS, "Shop.review_count is \"Number of reviews of shop listings "
                                   "in the past year\" and Shop.review_average is the mean. "
                                   "Those are reviews, which is a different surface, and "
                                   "using them as a service metric would be a category "
                                   "error.", "openapi"),
        ),
        work_class=CLASS_D,
        requirement_basis=NOT_REQUIRED,
    ),

    # -- 9. Policy Violations ---------------------------------------------
    Surface(
        key="policy_violations",
        name="Policy Violations",
        where="Shop Manager > Policy Violations (and Dashboard notices)",
        what="Etsy's notices that a listing was removed, a policy was breached or an IP "
             "claim was made, and the appeal route.",
        verdict=OWNER_ONLY,
        operations=("getListingsByShop",),
        scopes=("listings_r",),
        evidence=(
            Evidence(OPENAPI_ABSENCE, "'violation' 0 and 'infringement' 0 in Etsy's OpenAPI "
                                      "document. There is no notice, case or appeal "
                                      "resource.", "openapi"),
            Evidence(OPENAPI_SAYS, "The one indirect signal: getListingsByShop (listings_r) "
                                   "returns each listing's state, and the document's own "
                                   "state note includes \"seller flags: SUPRESSED (frozen)\". "
                                   "A listing that disappears or changes state is visible; "
                                   "the reason is not.", "openapi"),
            Evidence(INFERRED, "So the honest design is an alarm, not a report: "
                               "`listing_census_drift()` detects that something happened to "
                               "a listing and hands it to a person, who is the only one who "
                               "can read why. It must never be allowed to print a reason.",
                     "openapi"),
        ),
        work_class=CLASS_B,
        requirement_basis=NOT_REQUIRED,
        collector="listing_census",
        max_age_days=1,
        owner_action=OwnerAction(
            key="policy_violations_check",
            surface="policy_violations",
            action="After the first listings go live, open Shop Manager > Policy Violations "
                   "and confirm it is empty; check it again whenever the listing census "
                   "alarm fires.",
            why_software_cannot="Etsy publishes no violations API. The only machine-readable "
                                "trace of a takedown is a listing that is no longer there, "
                                "which is also what a mistake of ours looks like.",
            minutes=5,
            risk="Low to perform. The risk of not looking is that the first notice of a "
                 "problem is a suspension, and the appeal windows are short.",
            evidence_required="A dated statement of the page's contents, recorded against "
                              "this key -- 'empty on <date>' is evidence; silence is not.",
            consequence_of_delay="A removed listing looks to this system exactly like a "
                                 "listing we forgot to renew.",
        ),
    ),

    # -- 10. Etsy Ads ------------------------------------------------------
    Surface(
        key="etsy_ads",
        name="Etsy Ads",
        where="Shop Manager > Marketing > Etsy Ads",
        what="On-Etsy paid promotion with a daily budget, per-listing selection and "
             "performance reporting.",
        verdict=UNSUPPORTED,
        operations=(),
        evidence=(
            Evidence(OPENAPI_ABSENCE, "'advertis' 0, 'campaign' 0, 'budget' 0, 'impression' "
                                      "0. There is no Ads resource, no scope and no field.",
                     "openapi"),
            Evidence(OPENAPI_SAYS, "Nor is ad spend separately readable after the fact: the "
                                   "ledger entry description enumerates its kinds as \"a "
                                   "payment, refund, reversal of a failed refund, "
                                   "disbursement, returned disbursement, recoupment, "
                                   "miscellaneous credit, miscellaneous debit, or bill "
                                   "payment\" -- advertising is not among them.", "openapi"),
            Evidence(INFERRED, "This is a governance finding, not just a capability gap. The "
                               "Execution Directive requires budget ceilings enforced in "
                               "code. For Etsy Ads that is impossible: software can neither "
                               "set a budget nor read the spend. The only control available "
                               "is that nobody turns it on, which is a promise rather than a "
                               "ceiling, and it has to be recorded as one.", "openapi"),
        ),
        work_class=CLASS_D,
        requirement_basis=NOT_REQUIRED,
        owner_action=OwnerAction(
            key="etsy_ads_off",
            surface="etsy_ads",
            action="Leave Etsy Ads off, and confirm once that it is off. If you ever turn it "
                   "on, tell this system the daily budget and the date, because nothing here "
                   "can see either.",
            why_software_cannot="No Ads endpoint exists in any form, and ad spend does not "
                                "appear as its own ledger kind, so a code-enforced budget "
                                "ceiling is not available for this surface.",
            minutes=3,
            risk="The risk is entirely in the other direction: an ads budget set in a "
                 "browser spends real money that no ceiling in this repository can stop.",
            evidence_required="A dated statement that Etsy Ads is off, recorded against this "
                              "key; and if it is ever enabled, the budget and start date.",
            consequence_of_delay="None while it stays off. Phase is shadow and CA$0.",
        ),
    ),

    # -- 11. Offsite Ads ---------------------------------------------------
    Surface(
        key="offsite_ads",
        name="Offsite Ads",
        where="Shop Manager > Marketing > Offsite Ads",
        what="Etsy advertising the shop's listings on external platforms and charging a fee "
             "on orders it attributes to those ads.",
        verdict=UNSUPPORTED,
        operations=(),
        evidence=(
            Evidence(OPENAPI_ABSENCE, "'offsite' appears 0 times in Etsy's OpenAPI document "
                                      "-- not as an endpoint, not as a setting, and not as a "
                                      "fee line on a receipt, a payment or a ledger entry.",
                     "openapi"),
            Evidence(SECONDARY_CLAIM, "Widely reported third-party figures put the fee at 12% "
                                      "or 15% of the order total on attributed orders, with "
                                      "participation compulsory above a revenue threshold. "
                                      "Etsy's own fees page is HTTP 403 from this "
                                      "environment, so this is SECONDARY and the rate is not "
                                      "treated as known.", "etsy_legal_fees"),
            Evidence(INFERRED, "The combination is what matters: the largest fee this shop "
                               "may pay is one it cannot opt out of by API, cannot see by "
                               "API, and cannot attribute to an order by API. The only "
                               "defence available to software is a price that survives it, "
                               "which is why `commerce/pricing.py` now carries the fee as an "
                               "explicitly unmodelled one.", "etsy_legal_fees"),
        ),
        work_class=CLASS_D,
        requirement_basis=NOT_REQUIRED,
        owner_action=OwnerAction(
            key="offsite_ads_fee_readout",
            surface="offsite_ads",
            action="On the first order, read the fee lines in Shop Manager > Finances > "
                   "Payment account and report every one by name and amount -- in "
                   "particular whether an Offsite Ads fee and a Regulatory Operating Fee "
                   "appear, and at what rates.",
            why_software_cannot="Etsy's fee schedule is 403 to automated readers, and no fee "
                                "line in the API is named for Offsite Ads, so the rate "
                                "cannot be derived from a settlement either.",
            minutes=5,
            risk="None to perform. The risk of not doing it is a pricing floor that is "
                 "quietly optimistic by an unknown amount in the wrong direction.",
            evidence_required="The fee lines from one real order, by name and amount, so "
                              "`commerce.pricing.UNMODELLED_FEES` can be replaced by "
                              "measured rates.",
            consequence_of_delay="Every margin figure this company produces stays a floor "
                                 "computed from an incomplete fee model.",
        ),
    ),

    # -- 12. Sales & Discounts --------------------------------------------
    Surface(
        key="sales_and_discounts",
        name="Sales & Discounts",
        where="Shop Manager > Marketing > Sales and Discounts",
        what="Running a sale, issuing coupon codes and targeted offers.",
        verdict=OBSERVE,
        operations=("getListingsByListingIds",),
        evidence=(
            Evidence(OPENAPI_ABSENCE, "'coupon' 8 and 'discount' 21, and every one of the 29 "
                                      "is read-only. No endpoint creates a sale, a coupon or "
                                      "an offer.", "openapi"),
            Evidence(OPENAPI_SAYS, "GET /listings/batch returns a buyer-price block with "
                                   "`has_discount`, `discount_percentage`, `discount_amount`, "
                                   "`discount_start_epoch` and `discount_end_epoch`, and the "
                                   "document says it is \"Currently only supported on the "
                                   "/listings/batch endpoint\" and \"Requires buyer_country "
                                   "parameter\".", "openapi"),
            Evidence(INFERRED, "So a sale started in a browser is observable and a sale is "
                               "not creatable. That asymmetry is useful rather than annoying: "
                               "it means a discount nobody here authorised would be visible.",
                     "openapi"),
            Evidence(OUR_DECISION, "Section 9 forbids the category's near-universal fake "
                                   "sale. Whatever this surface could do, a struck-through "
                                   "price this shop never charged is not available to it, "
                                   "and `commerce.pricing.check_no_fake_discount` already "
                                   "refuses one.", "shop_manager_nav"),
        ),
        work_class=CLASS_C,
        requirement_basis=NOT_REQUIRED,
        collector=None,
    ),

    # -- 13. Social Media --------------------------------------------------
    Surface(
        key="social_media",
        name="Social Media",
        where="Shop Manager > Marketing > Social Media",
        what="Etsy's built-in composer for posting listings to external social accounts.",
        verdict=UNSUPPORTED,
        operations=(),
        evidence=(
            Evidence(OPENAPI_ABSENCE, "'social' 0 in Etsy's OpenAPI document.", "openapi"),
            Evidence(INFERRED, "Nothing is lost by the absence: this company's owned-channel "
                               "work lives in `growth/owned.py` under a CASL consent gate, "
                               "and routing posts through Etsy's composer would put content "
                               "outside that gate.", "openapi"),
        ),
        work_class=CLASS_C,
        requirement_basis=NOT_REQUIRED,
    ),

    # -- 14. Share & Save --------------------------------------------------
    Surface(
        key="share_and_save",
        name="Share & Save",
        where="Shop Manager > Marketing > Share & Save",
        what="An Etsy programme that reduces the fee on orders arriving through a seller's "
             "own share links.",
        verdict=UNSUPPORTED,
        operations=(),
        evidence=(
            Evidence(OPENAPI_ABSENCE, "No term for it appears in Etsy's OpenAPI document: no "
                                      "enrolment flag, no share-link resource, and no fee "
                                      "line that could show its effect.", "openapi"),
            Evidence(SECONDARY_CLAIM, "What the programme actually is, and what it costs or "
                                      "saves, is described only on help.etsy.com, which is "
                                      "403 from here. The description above is SECONDARY and "
                                      "should be confirmed by the owner in a browser before "
                                      "any decision rests on it.", "help_etsy"),
        ),
        work_class=CLASS_D,
        requirement_basis=NOT_REQUIRED,
        unknowns=("Whether enrolling changes the transaction fee on non-attributed orders, "
                  "which would move the pricing floor. Unreadable from here.",),
    ),

    # -- 15. Payment Account ----------------------------------------------
    Surface(
        key="payment_account",
        name="Payment Account",
        where="Shop Manager > Finances > Payment account",
        what="The ledger: every credit and debit, the current balance, and what Etsy paid "
             "out.",
        verdict=OBSERVE,
        operations=("getShopPaymentAccountLedgerEntries", "getShopPaymentAccountLedgerEntry",
                    "getPayments", "getShopPaymentByReceiptId",
                    "getPaymentAccountLedgerEntryPayments"),
        scopes=("transactions_r",),
        evidence=(
            Evidence(OPENAPI_SAYS, "GET /shops/{shop_id}/payment-account/ledger-entries "
                                   "returns entry_id, amount, currency, balance, "
                                   "create_date, ledger_type, reference_type and "
                                   "reference_id, and requires min_created and max_created.",
                     "openapi"),
            Evidence(OPENAPI_SAYS, "Payment carries amount_gross, amount_fees, amount_net and "
                                   "their posted and adjusted forms, so per-order economics "
                                   "are readable once a payment exists.", "openapi"),
            Evidence(OPENAPI_SAYS, "The ledger entry `description` enumerates the kinds of "
                                   "entry and names no advertising fee, so fee attribution "
                                   "is coarser than Shop Manager's own view.", "openapi"),
            Evidence(INFERRED, "Requires transactions_r, which this shop has not granted. "
                               "Today the verdict is a capability Etsy offers and we are not "
                               "authorised to use.", "build_state"),
        ),
        work_class=CLASS_D,
        requirement_basis=NOT_REQUIRED,
        why_required="",
        collector=None,
    ),

    # -- 16. Monthly Statements -------------------------------------------
    Surface(
        key="monthly_statements",
        name="Monthly Statements",
        where="Shop Manager > Finances > Monthly statements",
        what="Etsy's per-month statement of fees, sales and payouts, as a downloadable "
             "document.",
        verdict=UNSUPPORTED,
        operations=(),
        evidence=(
            Evidence(OPENAPI_ABSENCE, "'statement' appears twice and both are \"shipment "
                                      "statements\" on a receipt. There is no statement "
                                      "document, no download and no monthly aggregate.",
                     "openapi"),
            Evidence(OPENAPI_SAYS, "The underlying entries are readable through the ledger "
                                   "(see payment_account), so the *data* is reachable with "
                                   "transactions_r even though the *document* is not.",
                     "openapi"),
            Evidence(INFERRED, "The statement is still the authority for what Etsy charged, "
                               "and the ledger is our reconstruction of it. Where the two "
                               "disagree the statement wins, which is the reason to keep the "
                               "owner action below rather than declaring the ledger "
                               "sufficient.", "openapi"),
        ),
        work_class=CLASS_D,
        requirement_basis=NOT_REQUIRED,
        owner_action=OwnerAction(
            key="first_monthly_statement",
            surface="monthly_statements",
            action="Download the first monthly statement once one exists and give the "
                   "finance department its fee lines and totals.",
            why_software_cannot="Etsy publishes no statement endpoint; the document exists "
                                "only as a download behind the seller login.",
            minutes=10,
            risk="None to perform.",
            evidence_required="The statement's fee lines and totals for one month, against "
                              "which the ledger reconstruction can be reconciled.",
            consequence_of_delay="The fee model stays unreconciled against Etsy's own "
                                 "authority for what it charged.",
        ),
    ),

    # -- 17. Payment Settings ---------------------------------------------
    Surface(
        key="payment_settings",
        name="Payment Settings",
        where="Shop Manager > Finances > Payment settings",
        what="The bank account Etsy deposits into, the deposit schedule, the billing card "
             "for fees, and Etsy Payments enrolment.",
        verdict=OWNER_ONLY,
        operations=("getShop",),
        evidence=(
            Evidence(OPENAPI_ABSENCE, "No banking, payout, deposit or billing resource "
                                      "exists. 'payout' 0, 'deposit' 0; the single "
                                      "occurrence of 'bank' is inside an unrelated word.",
                     "openapi"),
            Evidence(OPENAPI_SAYS, "One bit of it is observable: Shop.is_etsy_payments_"
                                   "onboarded, \"When true, the shop has onboarded onto Etsy "
                                   "Payments\" -- readable on the API key alone through "
                                   "getShop, which makes it a check rather than an "
                                   "assertion.", "openapi"),
            Evidence(INFERRED, "That one boolean is the difference between this surface and "
                               "legal_and_tax: the owner's action here produces evidence a "
                               "collector can read back.", "openapi"),
        ),
        required_before_first_sale=True,
        requirement_basis=BY_ETSY,
        why_required="Without Etsy Payments onboarding and a deposit account, Etsy has "
                     "nowhere to send money and in most jurisdictions the shop cannot open.",
        work_class=CLASS_A,
        collector="shop_snapshot",
        max_age_days=7,
        owner_action=OwnerAction(
            key="payment_settings_setup",
            surface="payment_settings",
            action="In Shop Manager > Finances > Payment settings, complete Etsy Payments "
                   "onboarding: deposit account, billing card for fees, and the deposit "
                   "schedule.",
            why_software_cannot="Etsy exposes no banking endpoint of any kind, and the "
                                "process is identity-bound: a bank account may only be added "
                                "by the account holder.",
            minutes=20,
            risk="Handle the account details only in the browser. Nothing here should ever "
                 "receive them, and nothing here asks for them.",
            evidence_required="getShop returning is_etsy_payments_onboarded true -- which "
                              "`assess_shop` checks, so this action closes on a reading "
                              "rather than on a statement.",
            max_cost_cad=0.0,
            consequence_of_delay="No sale can be paid out. This is a hard first-sale "
                                 "blocker.",
            blocks_first_sale=True,
        ),
    ),

    # -- 18. Legal and tax information -------------------------------------
    Surface(
        key="legal_and_tax",
        name="Legal and tax information",
        where="Shop Manager > Finances > Legal and tax information",
        what="Identity verification, the legal entity, the taxpayer identification, and any "
             "GST/HST number given to Etsy.",
        verdict=OWNER_ONLY,
        operations=(),
        evidence=(
            Evidence(OPENAPI_ABSENCE, "'identity' 0, 'kyc' 0, 'gst' 0. No identity, entity or "
                                      "tax-registration resource exists. The 190 occurrences "
                                      "of 'tax' are receipt tax amounts and the taxonomy, "
                                      "neither of which is a tax setting.", "openapi"),
            Evidence(OUR_DECISION, "The non-negotiables forbid bypassing KYC, identity "
                                   "verification or legal acceptance, so even if an endpoint "
                                   "existed this company would not use it.",
                     "shop_manager_nav"),
            Evidence(INFERRED, "Whether to register for GST/HST, and whether to give Etsy the "
                               "number, is a tax position with a consequence and is the "
                               "owner's alone. `commerce/shop_package.CLAIMS` carries the CRA "
                               "primary source and the reasoning; it deliberately takes no "
                               "position.", "openapi"),
        ),
        required_before_first_sale=True,
        requirement_basis=BY_LAW,
        why_required="Etsy requires identity verification before a shop can sell, and the "
                     "tax position has to be chosen before the first invoice rather than "
                     "corrected after it.",
        work_class=CLASS_A,
        collector=None,
        owner_action=OwnerAction(
            key="legal_and_tax_setup",
            surface="legal_and_tax",
            action="Complete identity verification and the legal/tax information, and decide "
                   "the GST/HST position: register now or open as a small supplier, and "
                   "whether to give Etsy a GST/HST number.",
            why_software_cannot="Identity verification is the one thing an autonomous system "
                                "must never do on someone's behalf, and there is no endpoint "
                                "for it in any case. The tax position is a decision with "
                                "legal consequence, which software must not take.",
            minutes=30,
            risk="Getting the tax position wrong is a correction to file later rather than a "
                 "failure now. Giving Etsy a GST/HST number moves collection and remittance "
                 "responsibility to you.",
            evidence_required="A statement of the position chosen and its date, so "
                              "`commerce.shop_package` can record it as decided rather than "
                              "open; identity verification is evidenced by the shop being "
                              "able to open at all.",
            max_cost_cad=250.0,
            consequence_of_delay="No shop, and from the first sale onward the wrong tax "
                                 "position is a correction rather than a decision.",
            blocks_first_sale=True,
        ),
    ),

    # -- 19. Apps (Shop Manager) -------------------------------------------
    Surface(
        key="apps",
        name="Apps",
        where="Shop Manager > Apps",
        what="Third-party applications a seller installs to extend their shop.",
        verdict=NOT_APPLICABLE,
        operations=(),
        not_applicable_because="This company integrates with Etsy through its own registered "
                               "application, which it controls end to end. Installing a "
                               "third-party app would put shop writes behind software this "
                               "repository cannot inspect, audit or gate, and the Execution "
                               "Directive's refusal ladder could not reach them.",
        evidence=(
            Evidence(OPENAPI_ABSENCE, "No resource lists or manages installed apps, so a "
                                      "third-party app installed in a browser would also be "
                                      "invisible to this system.", "openapi"),
            Evidence(OUR_DECISION, "NOT_APPLICABLE rather than UNSUPPORTED: the deciding "
                                   "fact is our decision not to use the surface, which makes "
                                   "the API question moot.", "shop_manager_nav"),
        ),
        work_class=CLASS_NONE,
        requirement_basis=NOT_REQUIRED,
        owner_action=OwnerAction(
            key="apps_none_installed",
            surface="apps",
            action="Confirm once that no third-party app is installed on the shop, and "
                   "install none without telling this system.",
            why_software_cannot="Etsy exposes no list of installed applications, so an app "
                                "with write access to the shop would be invisible here.",
            minutes=2,
            risk="Low. This is a standing security check, not a setup step.",
            evidence_required="A dated statement that the Apps page is empty.",
            consequence_of_delay="An unlisted app holding listing write scope would be "
                                 "indistinguishable from our own writes.",
        ),
    ),

    # -- 20. Help ----------------------------------------------------------
    Surface(
        key="help",
        name="Help",
        where="Shop Manager > Help",
        what="Etsy's documentation and the route to Etsy support.",
        verdict=NOT_APPLICABLE,
        operations=(),
        not_applicable_because="The surface carries no shop state: nothing here can be right "
                               "or wrong, fresh or stale. That is a claim about state, not "
                               "about usefulness -- it is the escape hatch when something "
                               "goes wrong, and it is reached under policy_violations.",
        evidence=(
            Evidence(OPENAPI_ABSENCE, "No support-case resource exists; 'case' appears 23 "
                                      "times, all in unrelated words such as 'in case' and "
                                      "'lowercase'.", "openapi"),
            Evidence(SECONDARY_CLAIM, "help.etsy.com returns HTTP 403 to every automated "
                                      "request from this environment, which is why a great "
                                      "deal of this registry's context is secondary and says "
                                      "so.", "help_etsy"),
        ),
        work_class=CLASS_NONE,
        requirement_basis=NOT_REQUIRED,
    ),

    # -- 21. Your Shop -----------------------------------------------------
    Surface(
        key="your_shop",
        name="Your Shop (storefront)",
        where="Shop Manager > Your shop",
        what="The page a buyer sees: title, announcement, sections, featured listings, "
             "About, reviews and the shop's own policies.",
        verdict=ACT,
        operations=("updateShop", "createShopSection", "getShop", "getShopSections"),
        scopes=("shops_w", "shops_r"),
        evidence=(
            Evidence(OPENAPI_SAYS, "PUT /shops/{shop_id} accepts exactly five fields: title, "
                                   "announcement, sale_message, digital_sale_message, "
                                   "policy_additional. That is the whole write surface of "
                                   "the shop object.", "openapi"),
            Evidence(DEV_DOC_SAYS, "Etsy's own shop-management tutorial lists four of them -- "
                                   "\"title, announcement, sale_message, "
                                   "digital_sale_message\" -- and omits policy_additional, "
                                   "which the request schema does accept. The schema is the "
                                   "stronger evidence; the discrepancy is recorded rather "
                                   "than resolved.", "dev_shopmanagement"),
            Evidence(OPENAPI_SAYS, "getShop returns the storefront's readable state on the "
                                   "API key alone: title, announcement, all six policy "
                                   "strings, icon_url_fullxfull, image_url_760x100, "
                                   "listing_active_count, digital_listing_count, "
                                   "review_count, num_favorers.", "openapi"),
            Evidence(INFERRED, "Verdict is ACT because the fields that carry this company's "
                               "decisions are writable and the rest is at least readable. "
                               "The About story, banner and icon are not, and live under "
                               "info_and_appearance.", "openapi"),
        ),
        required_before_first_sale=True,
        requirement_basis=BY_US,
        why_required="A storefront with a blank announcement and no digital sale message "
                     "sells to nobody and tells a buyer nothing after they pay. Both are "
                     "writable, so leaving them empty would be a choice.",
        work_class=CLASS_A,
        collector="shop_snapshot",
        max_age_days=7,
    ),

    # -- 22. Info & Appearance ---------------------------------------------
    Surface(
        key="info_and_appearance",
        name="Info & Appearance",
        where="Shop Manager > Settings > Info & appearance",
        what="Shop title, banner, icon, the About story, shop members and photos.",
        verdict=OWNER_ONLY,
        operations=("updateShop", "getShop"),
        scopes=("shops_w",),
        evidence=(
            Evidence(OPENAPI_SAYS, "Shop.image_url_760x100 (banner) and "
                                   "Shop.icon_url_fullxfull are read-only URLs on the Shop "
                                   "object. updateShop's request schema contains no image "
                                   "field and no About field.", "openapi"),
            Evidence(OPENAPI_SAYS, "Only `title` from this page is writable, through "
                                   "updateShop.", "openapi"),
            Evidence(INFERRED, "The bulk of the page -- the two images and the About story, "
                               "which are the whole of a first impression -- can only be "
                               "typed and uploaded by a person, so the verdict is "
                               "OWNER_ONLY even though one field is writable.", "openapi"),
            Evidence(OUR_DECISION, "That a shop needs a banner, an icon and an About before "
                                   "opening is this company's judgement about buyer trust at "
                                   "zero reviews, not a rule of Etsy's that we have read. "
                                   "Labelled BY_US deliberately.", "shop_manager_nav"),
        ),
        required_before_first_sale=True,
        requirement_basis=BY_US,
        why_required="A shop with no icon, no banner and no About reads as abandoned to the "
                     "only buyer we will ever get -- one with no reviews to reassure them.",
        work_class=CLASS_A,
        collector="shop_snapshot",
        max_age_days=7,
        owner_action=OwnerAction(
            key="info_and_appearance_setup",
            surface="info_and_appearance",
            action="Upload the shop banner and icon and paste the About story from "
                   "`brand/storefront.ABOUT` into Shop Manager > Settings > Info & "
                   "appearance.",
            why_software_cannot="updateShop writes five text fields and none of them is an "
                                "image or the About story; Etsy publishes no shop-image "
                                "upload endpoint at all.",
            minutes=20,
            risk="Low. The assets and the words are prepared; this is pasting and "
                 "uploading, not composing.",
            evidence_required="getShop returning non-empty icon_url_fullxfull and "
                              "image_url_760x100 -- checked by `assess_shop`, so this closes "
                              "on a reading.",
            consequence_of_delay="The storefront reads as abandoned to the first buyer who "
                                 "reaches it.",
            blocks_first_sale=True,
        ),
    ),

    # -- 23. Options -------------------------------------------------------
    Surface(
        key="options",
        name="Options",
        where="Shop Manager > Settings > Options",
        what="Vacation mode, the shop's language, country and currency, digital-download "
             "settings, name changes and closing the shop.",
        verdict=OBSERVE,
        operations=("getShop",),
        evidence=(
            Evidence(OPENAPI_SAYS, "is_vacation, vacation_message, vacation_autoreply, "
                                   "currency_code, languages, shop_location_country_iso and "
                                   "shop_name are all present on the Shop object and none of "
                                   "them is in updateShop's request schema.", "openapi"),
            Evidence(OPENAPI_SAYS, "updateHolidayPreferences (PUT, shops_w) exists but "
                                   "governs shipping holidays, which a digital shop does not "
                                   "have.", "openapi"),
            Evidence(INFERRED, "So every setting on this page is readable and none is "
                               "writable: OBSERVE exactly. That makes them checkable, which "
                               "is worth more here than writable -- a shop left in vacation "
                               "mode, or set to the wrong currency, is silent failure, and "
                               "`assess_shop` checks both.", "openapi"),
        ),
        required_before_first_sale=True,
        requirement_basis=BY_US,
        why_required="Vacation mode on means no sales at all, and the wrong shop currency "
                     "makes every price decision in this repository wrong by an exchange "
                     "rate.",
        work_class=CLASS_A,
        collector="shop_snapshot",
        max_age_days=7,
    ),

    # -- 24. Shared Access -------------------------------------------------
    Surface(
        key="shared_access",
        name="Shared Access",
        where="Shop Manager > Settings > Shared access",
        what="Additional people granted access to the shop, and what each may do.",
        verdict=OWNER_ONLY,
        operations=(),
        evidence=(
            Evidence(OPENAPI_ABSENCE, "'shared access' 0 in Etsy's OpenAPI document. No "
                                      "resource lists, grants or revokes shop access.",
                     "openapi"),
            Evidence(INFERRED, "This is a security surface rather than an operational one. "
                               "An attacker who reached the account once would persist here, "
                               "and nothing in this repository could see it. Cheap to check, "
                               "invisible to software, so it becomes a standing owner "
                               "action rather than a gap we note and forget.", "openapi"),
        ),
        work_class=CLASS_B,
        requirement_basis=NOT_REQUIRED,
        owner_action=OwnerAction(
            key="shared_access_empty",
            surface="shared_access",
            action="Confirm the Shared Access list is empty (or contains only people you "
                   "intend), and re-check it after any account recovery.",
            why_software_cannot="Etsy publishes no shared-access API, so a second person "
                                "with listing permissions would be indistinguishable from "
                                "us.",
            minutes=2,
            risk="Low to perform; it is the cheapest check on this list and the only one "
                 "that would catch a persistent intruder.",
            evidence_required="A dated statement of who appears on the page.",
            consequence_of_delay="An unnoticed grant is indefinite.",
        ),
    ),

    # -- 25. Delivery Settings ---------------------------------------------
    Surface(
        key="delivery_settings",
        name="Delivery Settings",
        where="Shop Manager > Settings > Delivery settings",
        what="Shipping profiles, destinations, upgrades, carriers and processing times.",
        verdict=NOT_APPLICABLE,
        operations=("getShopShippingProfiles",),
        not_applicable_because="Everything on this page describes moving a physical object. "
                               "A digital pattern is delivered by Etsy as a download the "
                               "instant payment clears; there is no origin, no carrier, no "
                               "processing time and no destination.",
        evidence=(
            Evidence(OPENAPI_SAYS, "Etsy ships thirteen shipping-profile operations, a full "
                                   "CRUD surface -- so this is emphatically not a case of "
                                   "Etsy offering nothing.", "openapi"),
            Evidence(OPENAPI_SAYS, "And it still does not apply: shipping_profile_id is "
                                   "\"Required when listing type is `physical`\", and "
                                   "readiness_state_id is \"Returned only when the listing is "
                                   "`active` and of type `physical`\".", "openapi"),
            Evidence(INFERRED, "This entry is the reason the registry keeps NOT_APPLICABLE "
                               "and UNSUPPORTED apart. Recorded as UNSUPPORTED it would say "
                               "something false about Etsy; recorded as a gap it would put "
                               "thirteen endpoints on a build list forever.", "openapi"),
        ),
        work_class=CLASS_NONE,
        requirement_basis=NOT_REQUIRED,
    ),

    # -- 26. Policy Settings -----------------------------------------------
    Surface(
        key="policy_settings",
        name="Policy Settings",
        where="Shop Manager > Settings > Policies",
        what="The policies a buyer reads before buying: delivery, returns and exchanges, "
             "payment, privacy, FAQs and additional terms.",
        verdict=OWNER_ONLY,
        operations=("updateShop", "getShop", "getShopReturnPolicies"),
        scopes=("shops_w",),
        evidence=(
            Evidence(OPENAPI_SAYS, "Shop carries policy_welcome, policy_payment, "
                                   "policy_shipping, policy_refunds, policy_additional, "
                                   "policy_seller_info and policy_privacy, each \"(may be "
                                   "blank)\". updateShop's request schema contains exactly "
                                   "one of them: policy_additional.", "openapi"),
            Evidence(OPENAPI_SAYS, "The structured return-policy resource "
                                   "(createShopReturnPolicy and four others) exists, and "
                                   "return_policy_id is \"Required for active physical "
                                   "listings\" -- so it is not the surface a download shop "
                                   "needs.", "openapi"),
            Evidence(SECONDARY_CLAIM, "Etsy's own announcement: \"Sellers will no longer be "
                                      "able to accept returns on digital listings given the "
                                      "nature of the items\", quoted in "
                                      "`commerce/shop_package.py` from Etsy's community "
                                      "announcement.", "help_etsy"),
            Evidence(INFERRED, "Six of the seven policy strings a buyer actually reads can "
                               "only be typed. They are written and held in "
                               "`commerce/shop_package.policies()`; what is missing is a "
                               "person to paste them. That they are *readable* is what makes "
                               "the paste checkable.", "openapi"),
        ),
        required_before_first_sale=True,
        requirement_basis=BY_US,
        why_required="A shop whose policy pages are blank is selling a non-returnable "
                     "digital item with no stated position on returns, which is the single "
                     "most likely first complaint.",
        work_class=CLASS_A,
        collector="shop_snapshot",
        max_age_days=7,
        owner_action=OwnerAction(
            key="policy_settings_paste",
            surface="policy_settings",
            action="Paste the six prepared policies from `commerce.shop_package.policies()` "
                   "into Shop Manager > Settings > Policies. They are written; this is "
                   "copying, not drafting.",
            why_software_cannot="updateShop writes exactly one policy field "
                                "(policy_additional). Etsy publishes no write endpoint for "
                                "the delivery, returns, payment, privacy or FAQ text.",
            minutes=25,
            risk="Low. The words are already consistent with the licence in "
                 "`commerce/terms.py`, and changing them while pasting would reintroduce the "
                 "three-surface drift that module exists to prevent.",
            evidence_required="getShop returning non-blank policy_payment, policy_shipping, "
                              "policy_refunds, policy_privacy and policy_seller_info -- "
                              "which `assess_shop` checks field by field.",
            consequence_of_delay="The shop opens with blank policies, which is both a buyer-"
                                 "trust problem and the weakest possible position in a "
                                 "dispute.",
            blocks_first_sale=True,
        ),
    ),

    # -- 27. Partners You Work With ----------------------------------------
    Surface(
        key="production_partners",
        name="Partners You Work With",
        where="Shop Manager > Settings > Production partners",
        what="The outside people or businesses that help make what a shop sells, which Etsy "
             "requires disclosed.",
        verdict=NOT_APPLICABLE,
        operations=("getShopProductionPartners",),
        scopes=("shops_r",),
        not_applicable_because="A production partner is somebody who helps make the physical "
                               "item a buyer receives. This shop sells a document it wrote "
                               "and compiled itself; there is no third party in the making "
                               "of it.",
        evidence=(
            Evidence(OPENAPI_SAYS, "getShopProductionPartners is read-only and requires "
                                   "shops_r. No endpoint creates or edits one, so even a "
                                   "shop that needed partners would declare them in a "
                                   "browser.", "openapi"),
            Evidence(INFERRED, "The trap worth naming: an empty partner list is what a "
                               "correctly configured shop looks like **and** what a shop "
                               "nobody has read looks like. No check in this repository may "
                               "turn that emptiness into a pass -- which is exactly why "
                               "`EvidenceState` exists.", "openapi"),
            Evidence(UNKNOWN, "Whether Etsy considers a generative model used for listing "
                              "imagery a production partner. Etsy's guidance is on "
                              "help.etsy.com, which is 403 here. The AI-disclosure question "
                              "is handled in `gates/platform_policy` and in the listing "
                              "description; this entry records the doubt rather than "
                              "resolving it.", "help_etsy"),
        ),
        work_class=CLASS_NONE,
        requirement_basis=NOT_REQUIRED,
    ),

    # -- 28. Subscription / Etsy Plus --------------------------------------
    Surface(
        key="subscription",
        name="Subscription (Etsy Plus)",
        where="Shop Manager > Settings > Subscriptions",
        what="Etsy's paid seller subscription and whatever it bundles.",
        verdict=OWNER_ONLY,
        operations=(),
        evidence=(
            Evidence(OPENAPI_ABSENCE, "'subscription' 0 in Etsy's OpenAPI document. No "
                                      "subscription state, no enrolment, no charge line.",
                     "openapi"),
            Evidence(INFERRED, "A subscription is a recurring charge that software here can "
                               "neither see nor stop, which makes it the same class of "
                               "problem as Etsy Ads: a spend outside every ceiling this "
                               "repository enforces. The control available is a person "
                               "confirming it is off.", "openapi"),
        ),
        work_class=CLASS_B,
        requirement_basis=NOT_REQUIRED,
        owner_action=OwnerAction(
            key="subscription_none",
            surface="subscription",
            action="Confirm no paid Etsy subscription is active, and do not start one "
                   "without recording the monthly amount here.",
            why_software_cannot="No subscription resource exists in the API, and the charge "
                                "does not appear as its own ledger kind.",
            minutes=2,
            risk="Low to perform. Unchecked, it is a recurring charge invisible to every "
                 "budget ceiling in this system.",
            evidence_required="A dated statement that no subscription is active.",
            consequence_of_delay="A monthly charge could run for months before appearing in "
                                 "any figure this company computes.",
        ),
    ),

    # -- 29. Sales channels ------------------------------------------------
    Surface(
        key="sales_channels",
        name="Sales channels",
        where="Shop Manager > Settings > Sales channels",
        what="Selling somewhere other than the etsy.com marketplace -- Etsy's Pattern "
             "websites and external channels.",
        verdict=NOT_APPLICABLE,
        operations=(),
        scopes=(),
        not_applicable_because="This company sells on etsy.com and nowhere else. Pattern is a "
                               "separate paid subscription and no decision to buy one exists; "
                               "opening a second storefront before the first has a customer "
                               "would be building a channel for a product with no shown "
                               "demand.",
        evidence=(
            Evidence(OPENAPI_SAYS, "The channel of a sale is observable after the fact, "
                                   "under the orders surface and its transactions_r scope: "
                                   "ShopReceipt.receipt_type is \"0 or 5 for Etsy.com, 1 for "
                                   "a Pattern shop\". It is recorded under orders rather "
                                   "than here so that this entry does not appear as a scope "
                                   "gap for a surface we have decided not to use.",
                     "openapi"),
            Evidence(OPENAPI_SAYS, "And the listing-state note mentions seller flags "
                                   "\"CUSTOM_SHOPS (pattern), SELL_ON_FACEBOOK\", so "
                                   "channels exist as flags on objects rather than as a "
                                   "manageable resource.", "openapi"),
            Evidence(INFERRED, "No endpoint enables, disables or configures a channel. If "
                               "this decision is ever revisited, the work is a browser "
                               "action and a subscription, not an integration.", "openapi"),
        ),
        work_class=CLASS_NONE,
        requirement_basis=NOT_REQUIRED,
    ),

    # -- 30. Shop sections --------------------------------------------------
    Surface(
        key="shop_sections",
        name="Shop sections",
        where="Shop Manager > Your shop > Sections",
        what="The categories a buyer uses to browse a shop.",
        verdict=ACT,
        operations=("createShopSection", "updateShopSection", "deleteShopSection",
                    "getShopSections"),
        scopes=("shops_w",),
        evidence=(
            Evidence(OPENAPI_SAYS, "POST /shops/{shop_id}/sections takes one required field, "
                                   "`title`, form-encoded, under shops_w. Reading sections "
                                   "needs no OAuth scope at all.", "openapi"),
            Evidence(INFERRED, "The six sections are already decided in "
                               "`brand/storefront.py`; creating them is a call nobody has "
                               "written yet. It is a launch-week task rather than a blocker: "
                               "a shop with three listings and no sections is untidy, not "
                               "unsellable.", "openapi"),
        ),
        work_class=CLASS_B,
        requirement_basis=NOT_REQUIRED,
        collector=None,
    ),

    # -- 31. Digital files --------------------------------------------------
    Surface(
        key="digital_files",
        name="Digital files",
        where="Shop Manager > Listings > (a listing) > Digital files",
        what="The files a buyer downloads after paying.",
        verdict=ACT,
        operations=("uploadListingFile", "getAllListingFiles", "getListingFile",
                    "deleteListingFile"),
        scopes=("listings_w", "listings_r"),
        evidence=(
            Evidence(OPENAPI_SAYS, "POST /shops/{shop_id}/listings/{listing_id}/files, "
                                   "multipart/form-data, with the binary in a part named "
                                   "`file` -- distinct from the images endpoint, whose part "
                                   "is named `image`.", "openapi"),
            Evidence(INFERRED, "The two endpoints disagreeing about the part name is a "
                               "defect this repository has already hit once: a single "
                               "hard-coded `file` produced a well-formed upload in which "
                               "Etsy found no image.", "openapi"),
            Evidence(UNKNOWN, "Etsy's per-file size and count limits for digital listings are "
                              "not in the OpenAPI document and the help page that carries "
                              "them is 403 here. A deliverable larger than the limit would "
                              "fail at upload, not at compile.", "help_etsy"),
        ),
        required_before_first_sale=True,
        requirement_basis=BY_ETSY,
        why_required="A digital listing with no file sells a buyer nothing, and Etsy "
                     "delivers whatever is attached without asking us.",
        work_class=CLASS_A,
        collector=None,
    ),

    # -- 32. Taxonomy and attributes ---------------------------------------
    Surface(
        key="taxonomy_and_attributes",
        name="Category & attributes",
        where="Shop Manager > Listings > (a listing) > Category",
        what="The taxonomy node a listing sits in, and the properties that node requires.",
        verdict=OBSERVE,
        operations=("getSellerTaxonomyNodes", "getPropertiesByTaxonomyId",
                    "getListingProperties", "updateListingProperty"),
        scopes=("listings_w",),
        evidence=(
            Evidence(OPENAPI_SAYS, "taxonomy_id is in createDraftListing's required array, "
                                   "and getSellerTaxonomyNodes needs no OAuth scope -- the "
                                   "API key alone reads the whole tree.", "openapi"),
            Evidence(OPENAPI_SAYS, "\"is_required: When true, listings assigned eligible "
                                   "taxonomy IDs require this property.\" So a node can "
                                   "refuse a listing that omits an attribute.", "openapi"),
            Evidence(UNKNOWN, "This repository sends TAXONOMY_PATTERNS = 66 and has never "
                              "read it back from Etsy. The OpenAPI document contains no "
                              "taxonomy ids at all -- 'craft_supplies' appears zero times -- "
                              "so it cannot be settled from the document. One unauthenticated "
                              "GET to getSellerTaxonomyNodes with the API key settles it, and "
                              "this lane is forbidden from making it.", "openapi"),
        ),
        required_before_first_sale=True,
        requirement_basis=BY_ETSY,
        why_required="A listing cannot be created without a taxonomy_id, and a wrong one is "
                     "a listing in the wrong category -- which Etsy accepts silently, so "
                     "nothing fails and nobody finds it.",
        work_class=CLASS_A,
        collector=None,
        unknowns=("Whether taxonomy id 66 is the crochet-patterns node, and whether that node "
                  "marks any property is_required. One API-key GET answers both.",),
    ),

    # -- 33. Reviews --------------------------------------------------------
    Surface(
        key="reviews",
        name="Reviews",
        where="Shop Manager > Your shop > Reviews",
        what="What buyers said, and the shop's average.",
        verdict=OBSERVE,
        operations=("getReviewsByShop", "getReviewsByListing", "getShop"),
        evidence=(
            Evidence(OPENAPI_SAYS, "GET /shops/{shop_id}/reviews and "
                                   "/listings/{listing_id}/reviews require no OAuth scope, "
                                   "and Shop carries review_count and review_average.",
                     "openapi"),
            Evidence(OPENAPI_SAYS, "There is no write of any kind: no reply endpoint, no "
                                   "rating, no flag. Reviews can be read and nothing else.",
                     "openapi"),
            Evidence(OUR_DECISION, "The non-negotiables forbid fake reviews, fake buyers and "
                                   "artificial engagement absolutely. Recorded here because "
                                   "this is the surface where the temptation lives, and "
                                   "because 'favorite' appearing only as a read-only counter "
                                   "means there is no mechanism to abuse either.",
                     "shop_manager_nav"),
        ),
        work_class=CLASS_D,
        requirement_basis=NOT_REQUIRED,
        collector=None,
    ),

    # -- 34. Webhooks -------------------------------------------------------
    Surface(
        key="webhooks",
        name="Webhooks (order events)",
        where="Developer Portal > Manage your apps > Webhook portal",
        what="Etsy's push notifications for order events, and the portal that subscribes to "
             "them.",
        verdict=OWNER_ONLY,
        operations=(),
        evidence=(
            Evidence(DEV_DOC_SAYS, "\"We currently support the following events: order.paid, "
                                   "order.canceled, order.shipped, order.delivered.\" All "
                                   "four are orders; nothing else pushes.", "dev_webhooks"),
            Evidence(DEV_DOC_SAYS, "Subscriptions are created only in the portal: \"Navigate "
                                   "to Manage your apps in the Developer Portal. Click the "
                                   "dropdown menu for your commercial app and select Go to "
                                   "Webhook portal... Choose +Add Endpoint.\" There is no "
                                   "management endpoint in the OpenAPI document.",
                     "dev_webhooks"),
            Evidence(DEV_DOC_SAYS, "Deliveries are signed: HMAC-SHA256 over "
                                   "webhook-id + '.' + webhook-timestamp + '.' + raw_body, "
                                   "with the secret base64-decoded after its whsec_ prefix, "
                                   "and a stale timestamp rejected beyond 300 seconds.",
                     "dev_webhooks"),
            Evidence(INFERRED, "A webhook would remove the need to poll for orders, but the "
                               "payload carries only event_type, resource_url and shop_id -- "
                               "reading the order still needs transactions_r. So this is "
                               "worth doing after the scope is widened, not instead of it.",
                     "dev_webhooks"),
        ),
        work_class=CLASS_B,
        requirement_basis=NOT_REQUIRED,
        unknowns=("Whether a personal (non-commercial) application can subscribe. The page "
                  "says webhooks are \"available for both commercial and personal "
                  "applications\" and then describes the portal as reached through \"your "
                  "commercial app\". Settled by opening the portal once.",),
        owner_action=OwnerAction(
            key="webhook_order_paid",
            surface="webhooks",
            action="In the Developer Portal's Webhook portal, add an endpoint for order.paid "
                   "pointing at this service's callback, and give this system the signing "
                   "secret through the environment -- never through this repository.",
            why_software_cannot="Etsy's OpenAPI document contains no webhook resource; "
                                "subscriptions exist only as a page in the developer portal.",
            minutes=10,
            risk="Moderate: the signing secret is a credential. It belongs in the hosting "
                 "environment beside the other secrets, and a subscription pointed at the "
                 "wrong URL leaks order metadata to whoever owns it.",
            evidence_required="The subscription visible in the portal, plus one delivery "
                              "recorded by the receiving route with a verified signature.",
            consequence_of_delay="Order discovery stays a poll, which is acceptable at this "
                                 "volume and is not a blocker.",
        ),
    ),

    # -- 35. Developer portal ------------------------------------------------
    Surface(
        key="developer_portal",
        name="Your Apps (developer portal)",
        where="https://www.etsy.com/developers/your-apps",
        what="The application's keystring and shared secret, its access level, its rate "
             "limits and its webhook portal.",
        verdict=OWNER_ONLY,
        operations=(),
        evidence=(
            Evidence(OPENAPI_SAYS, "Etsy's own security scheme points at it: \"Your keystring "
                                   "and shared secret are available on the Your Apps page.\"",
                     "openapi"),
            Evidence(DEV_DOC_SAYS, "Rate limits are per API key and visible only there: "
                                   "\"You can see your application's current rate limits in "
                                   "the Developer Portal\", and a higher quota is requested "
                                   "by emailing developer@etsy.com.", "dev_ratelimits"),
            Evidence(INFERRED, "Every quota this company's collectors must live inside is "
                               "readable only by a person. Designing a polling cadence "
                               "without that number is guessing, and the guess is cheap to "
                               "replace.", "dev_ratelimits"),
        ),
        work_class=CLASS_B,
        requirement_basis=NOT_REQUIRED,
        owner_action=OwnerAction(
            key="developer_portal_quota",
            surface="developer_portal",
            action="Read this application's x-limit-per-second and x-limit-per-day from the "
                   "Developer Portal and report both figures.",
            why_software_cannot="The quota is shown on the portal page. It is also returned "
                                "in response headers, but only to a caller already making "
                                "authenticated requests, which this lane must not do.",
            minutes=5,
            risk="None to perform.",
            evidence_required="The two numbers, so any polling cadence is set against a "
                              "known quota rather than a guess.",
            consequence_of_delay="Collector cadences stay guesses, and the first symptom of "
                                 "a wrong guess is a 429 during a launch.",
        ),
    ),
)

SURFACES: dict[str, Surface] = {s.key: s for s in _SURFACES}


def surfaces() -> tuple[Surface, ...]:
    """Every surface, in registry order."""
    return _SURFACES


def by_verdict(verdict: str) -> tuple[Surface, ...]:
    return tuple(s for s in _SURFACES if s.verdict == verdict)


# ---------------------------------------------------------------------------
# Registry invariants
# ---------------------------------------------------------------------------


def check_registry(registry: Iterable[Surface] | None = None) -> list[str]:
    """Every rule that keeps a verdict from being a mood. Empty means the registry holds.

    These are not style checks. Each one closes a specific way this registry could tell a
    comfortable lie: an ACT with no endpoint behind it, an UNSUPPORTED resting on nobody
    having looked, a NOT_APPLICABLE with no reason, an OWNER_ONLY with no action, a
    first-sale requirement that somehow is not class A, an endpoint that does not exist.

    Takes a registry so a test can hand it a deliberately broken surface and prove the rule
    fires. A checker that can only be run against the one input that passes is not a checker.
    """
    surfaces_to_check = tuple(_SURFACES if registry is None else registry)
    problems: list[str] = []
    seen: set[str] = set()
    for s in surfaces_to_check:
        if s.key in seen:
            problems.append(f"{s.key}: duplicate surface key")
        seen.add(s.key)
        if s.verdict not in VERDICTS:
            problems.append(f"{s.key}: unknown verdict {s.verdict!r}")
        if s.work_class not in WORK_CLASSES:
            problems.append(f"{s.key}: unknown work class {s.work_class!r}")
        if s.requirement_basis not in REQUIREMENT_BASES:
            problems.append(f"{s.key}: unknown requirement basis {s.requirement_basis!r}")
        if not s.evidence:
            problems.append(f"{s.key}: a verdict with no evidence is an opinion")
        for e in s.evidence:
            if e.kind not in EVIDENCE_KINDS:
                problems.append(f"{s.key}: unknown evidence kind {e.kind!r}")
            if e.source not in SOURCES:
                problems.append(f"{s.key}: evidence cites unknown source {e.source!r}")

        for op in s.operations:
            if op not in ETSY_OPERATIONS:
                problems.append(f"{s.key}: cites operation {op!r}, which is not in Etsy's "
                                f"published document -- an endpoint we invented")

        if s.verdict in (ACT, OBSERVE) and not s.operations:
            problems.append(f"{s.key}: {s.verdict} with no Etsy operation behind it")
        if s.verdict == ANALYZE and not s.operations:
            problems.append(f"{s.key}: ANALYZE with no data source for the proxy")
        if s.verdict == UNSUPPORTED:
            if s.operations:
                problems.append(f"{s.key}: UNSUPPORTED while naming operations "
                                f"{s.operations}")
            if not any(e.kind == OPENAPI_ABSENCE for e in s.evidence):
                problems.append(f"{s.key}: UNSUPPORTED with no recorded absence probe -- "
                                f"that is a verdict computed from nobody having looked")
        if s.verdict == NOT_APPLICABLE and not (s.not_applicable_because or "").strip():
            problems.append(f"{s.key}: NOT_APPLICABLE with no reason")
        if s.verdict != NOT_APPLICABLE and s.not_applicable_because:
            problems.append(f"{s.key}: carries a not-applicable reason without the verdict")
        if s.verdict == OWNER_ONLY and s.owner_action is None:
            problems.append(f"{s.key}: OWNER_ONLY with no owner action -- the claim that a "
                            f"person must act, with nothing asked of them")

        if s.required_before_first_sale:
            if s.work_class != CLASS_A:
                problems.append(f"{s.key}: required before the first sale but classed "
                                f"{s.work_class}")
            if s.requirement_basis == NOT_REQUIRED:
                problems.append(f"{s.key}: required before the first sale by nobody")
            if not (s.why_required or "").strip():
                problems.append(f"{s.key}: required before the first sale with no reason")
        elif s.requirement_basis != NOT_REQUIRED:
            problems.append(f"{s.key}: names a requirement basis but is not required")

        if s.collector is not None and s.collector not in COLLECTORS:
            problems.append(f"{s.key}: claims collector {s.collector!r}, which does not exist")
        if s.collector is not None and s.max_age_days is None:
            problems.append(f"{s.key}: has a collector and no staleness tolerance, so its "
                            f"evidence could never go stale")
        if s.owner_action is not None and s.owner_action.surface != s.key:
            problems.append(f"{s.key}: owner action names surface "
                            f"{s.owner_action.surface!r}")
        if s.owner_action is not None and not s.owner_action.evidence_required.strip():
            problems.append(f"{s.key}: owner action with no evidence requirement closes on "
                            f"somebody's word")
    return problems


def scope_gaps(granted: Iterable[str] = GRANTED_SCOPES) -> list[dict]:
    """Surfaces whose operations need a scope Etsy has not granted this shop.

    The distinction this draws is the whole point: an endpoint that exists and an endpoint we
    may call are different, and only the second is a capability. Sorted so the first-sale
    ones come first.
    """
    held = set(granted)
    gaps: list[dict] = []
    for s in _SURFACES:
        missing = s.missing_scopes(held)
        if missing:
            gaps.append({"surface": s.key, "verdict": s.verdict,
                         "missing_scopes": list(missing),
                         "meanings": [SCOPE_MEANINGS.get(m, "unknown scope") for m in missing],
                         "operations": list(s.operations),
                         "required_before_first_sale": s.required_before_first_sale})
    gaps.sort(key=lambda g: (not g["required_before_first_sale"], g["surface"]))
    return gaps


def owner_queue(*, first_sale_only: bool = False) -> list[OwnerAction]:
    """Every owner action the registry carries, blockers first, then by cost in minutes."""
    actions = [s.owner_action for s in _SURFACES if s.owner_action is not None]
    if first_sale_only:
        actions = [a for a in actions if a.blocks_first_sale]
    actions.sort(key=lambda a: (not a.blocks_first_sale, a.minutes, a.key))
    return actions


def first_sale_blockers() -> tuple[Surface, ...]:
    return tuple(s for s in _SURFACES if s.required_before_first_sale)


def work_plan() -> dict[str, list[str]]:
    """A / B / C / D, as surface keys. `-` holds the surfaces with no work attached."""
    plan: dict[str, list[str]] = {c: [] for c in WORK_CLASSES}
    for s in _SURFACES:
        plan[s.work_class].append(s.key)
    return plan


def coverage() -> dict:
    """One honest summary line per verdict, plus what is not evidenced at all."""
    counts = {v: len(by_verdict(v)) for v in VERDICTS}
    return {
        "surfaces": len(_SURFACES),
        "verdicts": counts,
        "required_before_first_sale": [s.key for s in first_sale_blockers()],
        "with_collector": [s.key for s in _SURFACES if s.collector],
        "without_collector": [s.key for s in _SURFACES if not s.collector],
        "owner_actions": len(owner_queue()),
        "first_sale_owner_actions": len(owner_queue(first_sale_only=True)),
        "scope_gaps": scope_gaps(),
        "unknowns": {s.key: list(s.unknowns) for s in _SURFACES if s.unknowns},
        "problems": check_registry(),
    }


# ---------------------------------------------------------------------------
# Evidence state: the reason an empty record cannot read as green
# ---------------------------------------------------------------------------

NO_COLLECTOR = "NO_COLLECTOR"   # nothing could produce evidence for this surface
NO_EVIDENCE = "NO_EVIDENCE"     # a collector exists and has never returned anything
STALE = "STALE"                 # a record exists and is older than the surface tolerates
FRESH = "FRESH"                 # a record exists and is current
EVIDENCE_STATES = (NO_COLLECTOR, NO_EVIDENCE, STALE, FRESH)

PASS = "PASS"
FAIL = "FAIL"
UNEVIDENCED = "NO_EVIDENCE"


@dataclass(frozen=True)
class Check:
    key: str
    result: str          # PASS / FAIL / UNEVIDENCED
    detail: str

    def to_dict(self) -> dict:
        return {"key": self.key, "result": self.result, "detail": self.detail}


@dataclass(frozen=True)
class SurfaceStatus:
    surface: str
    verdict: str
    evidence_state: str
    checks: tuple[Check, ...] = ()
    observed_at: float | None = None
    note: str = ""

    @property
    def green(self) -> bool:
        """True only for a fresh record whose every check passed.

        There is deliberately no path to True through an empty record, a missing collector or
        an unevidenced check. This property is the one line that the repository's recurring
        defect has to get past, so it is written to have no other way through.
        """
        if self.evidence_state != FRESH:
            return False
        if not self.checks:
            return False
        return all(c.result == PASS for c in self.checks)

    @property
    def failures(self) -> tuple[Check, ...]:
        return tuple(c for c in self.checks if c.result == FAIL)

    @property
    def unevidenced(self) -> tuple[Check, ...]:
        return tuple(c for c in self.checks if c.result == UNEVIDENCED)

    def to_dict(self) -> dict:
        return {"surface": self.surface, "verdict": self.verdict,
                "evidence_state": self.evidence_state, "green": self.green,
                "observed_at": self.observed_at, "note": self.note,
                "checks": [c.to_dict() for c in self.checks]}


def evidence_state(surface: Surface, record: Mapping | None, *, now: float) -> str:
    """Which of the four states a surface's evidence is in. Never a boolean."""
    if surface.collector is None:
        return NO_COLLECTOR
    if not record or record.get("observed_at") is None:
        return NO_EVIDENCE
    max_age = surface.max_age_days
    if max_age is None:
        return NO_EVIDENCE
    age_days = (now - float(record["observed_at"])) / 86400.0
    if age_days < 0:
        # A record from the future is a clock problem, and a clock problem is not freshness.
        return STALE
    return FRESH if age_days <= max_age else STALE


# ---------------------------------------------------------------------------
# Collector 1: the shop snapshot
# ---------------------------------------------------------------------------

#: Each check is (key, field, kind, why). `kind` decides how the value is judged:
#:   "nonblank" -- a string that must have content
#:   "true"     -- a boolean that must be true
#:   "false"    -- a boolean that must be false
#:   "equals"   -- compared against the expected value in `expect`
#:   "atleast"  -- a number at or above `expect`
#: Every one of them is a field `getShop` returns, so every one of them closes an owner
#: action on a reading rather than on a statement.
SHOP_CHECKS: tuple[tuple[str, str, str, object, str], ...] = (
    ("icon_set", "icon_url_fullxfull", "nonblank", None,
     "a shop with no icon reads as abandoned; closes info_and_appearance_setup"),
    ("banner_set", "image_url_760x100", "nonblank", None,
     "the banner is the first thing a buyer sees; closes info_and_appearance_setup"),
    ("title_set", "title", "nonblank", None,
     "written by updateShop, so a blank one means the write never happened"),
    ("announcement_set", "announcement", "nonblank", None,
     "written by updateShop"),
    ("digital_sale_message_set", "digital_sale_message", "nonblank", None,
     "the only message that reaches every buyer, delivered at purchase and unretrofittable"),
    ("policy_payment_set", "policy_payment", "nonblank", None,
     "typed by a person; closes policy_settings_paste"),
    ("policy_shipping_set", "policy_shipping", "nonblank", None,
     "delivery policy -- for a download this is where the file is and what to do if it fails"),
    ("policy_refunds_set", "policy_refunds", "nonblank", None,
     "the most likely first complaint is about a return on a non-returnable item"),
    ("policy_privacy_set", "policy_privacy", "nonblank", None,
     "CASL and buyer trust; buying must not put anybody on a list"),
    ("policy_additional_set", "policy_additional", "nonblank", None,
     "the only policy field the API writes: licence and AI disclosure"),
    ("etsy_payments_onboarded", "is_etsy_payments_onboarded", "true", None,
     "no payout route without it; closes payment_settings_setup"),
    ("not_on_vacation", "is_vacation", "false", None,
     "vacation mode is a silent zero-sales failure"),
    ("currency_is_cad", "currency_code", "equals", "CAD",
     "every price decision in this repository is computed in CAD"),
    ("has_a_digital_listing", "digital_listing_count", "atleast", 1,
     "a shop with no digital listing cannot make the sale this is all for"),
)


def assess_shop(snapshot: Mapping | None, *, now: float,
                max_age_days: int = 7) -> SurfaceStatus:
    """Check a `getShop` response field by field, distinguishing absent from empty.

    The distinction is the whole design. Etsy returning ``"policy_refunds": null`` means the
    policy is not set -- a **FAIL**, and an owner action. A snapshot that simply does not
    contain the key means nobody read that field -- **NO_EVIDENCE**, and a different problem
    with a different fix. A truthiness test would have merged them into one comfortable
    "false", and the comfortable half is the wrong one.

    `snapshot` is a recorded observation, not a call: this module never speaks to Etsy. It
    carries `observed_at` (epoch seconds) and `shop`, the response body.
    """
    if not snapshot or snapshot.get("observed_at") is None:
        return SurfaceStatus(
            surface="shop_snapshot", verdict=OBSERVE, evidence_state=NO_EVIDENCE,
            note="no getShop observation has ever been recorded, so nothing here is known "
                 "to be right or wrong")
    body = snapshot.get("shop")
    if not isinstance(body, Mapping):
        return SurfaceStatus(
            surface="shop_snapshot", verdict=OBSERVE, evidence_state=NO_EVIDENCE,
            observed_at=float(snapshot["observed_at"]),
            note="the record carries a timestamp and no shop body, which is an empty "
                 "observation rather than an observation of an empty shop")

    observed_at = float(snapshot["observed_at"])
    age_days = (now - observed_at) / 86400.0
    state = FRESH if 0 <= age_days <= max_age_days else STALE

    checks: list[Check] = []
    for key, field_name, kind, expect, why in SHOP_CHECKS:
        if field_name not in body:
            checks.append(Check(key, UNEVIDENCED,
                                f"{field_name} is not in the recorded response: nobody read "
                                f"it. ({why})"))
            continue
        value = body[field_name]
        if kind == "nonblank":
            ok = isinstance(value, str) and value.strip() != ""
            detail = (f"{field_name} is set" if ok else
                      f"{field_name} is {value!r}: Etsy returned it and it is empty. ({why})")
        elif kind == "true":
            ok = value is True
            detail = (f"{field_name} is true" if ok else
                      f"{field_name} is {value!r}, not true. ({why})")
        elif kind == "false":
            ok = value is False
            detail = (f"{field_name} is false" if ok else
                      f"{field_name} is {value!r}, not false. ({why})")
        elif kind == "equals":
            ok = value == expect
            detail = (f"{field_name} is {expect!r}" if ok else
                      f"{field_name} is {value!r}, expected {expect!r}. ({why})")
        elif kind == "atleast":
            ok = isinstance(value, (int, float)) and not isinstance(value, bool) \
                and value >= float(expect)  # type: ignore[arg-type]
            detail = (f"{field_name} is {value!r}" if ok else
                      f"{field_name} is {value!r}, expected at least {expect!r}. ({why})")
        else:  # pragma: no cover -- a kind nobody wrote a judgement for must not pass
            ok = False
            detail = f"{field_name}: unknown check kind {kind!r}, refusing to judge it"
        checks.append(Check(key, PASS if ok else FAIL, detail))

    note = "" if state == FRESH else (
        f"the observation is {age_days:.1f} days old against a {max_age_days}-day tolerance; "
        f"every check below describes the shop as it was, not as it is")
    return SurfaceStatus(surface="shop_snapshot", verdict=OBSERVE, evidence_state=state,
                         checks=tuple(checks), observed_at=observed_at, note=note)


# ---------------------------------------------------------------------------
# Collector 2: the listing census
# ---------------------------------------------------------------------------


def listing_census_drift(expected: Mapping[str, str] | None,
                         observed: Sequence[Mapping] | None, *,
                         observed_at: float | None = None,
                         now: float | None = None,
                         max_age_days: int = 1) -> SurfaceStatus:
    """Our listing set against what the shop actually shows, as an alarm and nothing more.

    This is the only machine-readable trace a policy takedown leaves: a listing that is no
    longer active, or no longer there. It cannot say why, and it must never guess -- a
    removed listing, an expired listing and a listing we deactivated ourselves are the same
    shape from here. So the output is "a person must look at Policy Violations", never a
    reason.

    `expected` maps listing_id to the state we believe it is in. `observed` is the results
    array from getListingsByShop. Passing `None` for `observed` is **not** "no drift": it is
    NO_EVIDENCE, which is the case this function exists to keep separate.
    """
    if observed is None or observed_at is None:
        return SurfaceStatus(
            surface="listing_census", verdict=OBSERVE, evidence_state=NO_EVIDENCE,
            note="no getListingsByShop observation has been recorded. Nothing is known "
                 "about the shop's listings, which is not the same as nothing being wrong")
    now = now if now is not None else observed_at
    age_days = (now - observed_at) / 86400.0
    state = FRESH if 0 <= age_days <= max_age_days else STALE

    expected = dict(expected or {})
    seen: dict[str, str] = {}
    for row in observed:
        listing_id = str(row.get("listing_id"))
        seen[listing_id] = str(row.get("state"))

    checks: list[Check] = []
    if not expected:
        checks.append(Check("census_known", UNEVIDENCED,
                            "this system holds no record of which listings it created, so "
                            "nothing can be compared and an empty shop would look correct"))
    for listing_id, want in sorted(expected.items()):
        if listing_id not in seen:
            checks.append(Check(
                f"listing_{listing_id}", FAIL,
                f"listing {listing_id} is not in the shop's listing set at all. A person "
                f"must open Shop Manager > Policy Violations; this check cannot tell a "
                f"takedown from a deletion"))
        elif seen[listing_id] != want:
            checks.append(Check(
                f"listing_{listing_id}", FAIL,
                f"listing {listing_id} is {seen[listing_id]!r}, expected {want!r}. A person "
                f"must look; the reason is not readable from here"))
        else:
            checks.append(Check(f"listing_{listing_id}", PASS,
                                f"listing {listing_id} is {want!r} as expected"))
    for listing_id, state_seen in sorted(seen.items()):
        if listing_id not in expected:
            checks.append(Check(
                f"unexpected_{listing_id}", FAIL,
                f"the shop shows listing {listing_id} ({state_seen!r}) which this system did "
                f"not create. Either a person made it or something else holds write scope"))

    note = "" if state == FRESH else (
        f"the census is {age_days:.1f} days old against a {max_age_days}-day tolerance")
    return SurfaceStatus(surface="listing_census", verdict=OBSERVE, evidence_state=state,
                         checks=tuple(checks), observed_at=observed_at, note=note)


# ---------------------------------------------------------------------------
# Consistency with what the rest of the repository already decided
# ---------------------------------------------------------------------------

#: `commerce.shop_package.MANUAL_ONLY` lists what a person must type. Each of its keys is
#: mapped here to the surface that owns it, so the two cannot drift apart without a test
#: failing. Anything in MANUAL_ONLY that is not in this map is a manual action with no
#: surface, which means nobody owns its evidence.
MANUAL_ONLY_SURFACES: dict[str, str] = {
    "shop_policies_delivery": "policy_settings",
    "shop_policies_returns": "policy_settings",
    "shop_policies_privacy": "policy_settings",
    "shop_policies_faq": "policy_settings",
    "about_story": "info_and_appearance",
    "banner_and_icon": "info_and_appearance",
}


def manual_only_consistency(manual_only: Iterable[tuple[str, str]]) -> list[str]:
    """Check `commerce.shop_package.MANUAL_ONLY` against this registry, both ways."""
    problems: list[str] = []
    keys = set()
    for key, _where in manual_only:
        keys.add(key)
        surface_key = MANUAL_ONLY_SURFACES.get(key)
        if surface_key is None:
            problems.append(f"{key}: a manual-only action with no surface in this registry")
            continue
        surface = SURFACES.get(surface_key)
        if surface is None:
            problems.append(f"{key}: maps to unknown surface {surface_key!r}")
        elif surface.owner_action is None:
            problems.append(f"{key}: maps to {surface_key}, which carries no owner action")
    for key in sorted(set(MANUAL_ONLY_SURFACES) - keys):
        problems.append(f"{key}: this registry maps a manual-only key that "
                        f"shop_package.MANUAL_ONLY no longer has")
    return problems


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def render() -> str:
    """The registry as text, for the build record and for a person reading it once."""
    lines = [
        f"Etsy surface registry -- {len(_SURFACES)} surfaces, read {READ_ON} from "
        f"OpenAPI {OPENAPI_VERSION} ({OPENAPI_SHA256[:12]}...)",
        "",
        "| surface | verdict | class | first sale | collector | scopes |",
        "|---|---|---|---|---|---|",
    ]
    for s in _SURFACES:
        lines.append(
            f"| {s.name} | {s.verdict} | {s.work_class} | "
            f"{'yes' if s.required_before_first_sale else 'no'} | "
            f"{s.collector or '--'} | {' '.join(s.scopes) or '--'} |")
    gaps = scope_gaps()
    lines += ["", f"Scope gaps against the {GRANTED_ON} grant "
                  f"({' '.join(GRANTED_SCOPES)}): {len(gaps)}"]
    for g in gaps:
        lines.append(f"  - {g['surface']}: needs {' '.join(g['missing_scopes'])}")
    queue = owner_queue()
    lines += ["", f"Owner actions: {len(queue)} "
                  f"({len(owner_queue(first_sale_only=True))} block the first sale)"]
    for a in queue:
        flag = "BLOCKER " if a.blocks_first_sale else ""
        lines.append(f"  - {flag}{a.key} ({a.minutes} min): {a.action}")
    problems = check_registry()
    lines += ["", f"Registry problems: {len(problems)}"]
    lines += [f"  - {p}" for p in problems]
    return "\n".join(lines)
