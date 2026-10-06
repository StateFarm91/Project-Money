"""Etsy commerce knowledge as dated, sourced, digested readings (#35, #39, #40 and the Build 2
commerce-knowledge closeout).

Why this exists. `platform_policy` watches six policy surfaces and refuses to certify against
one that has never been read. No policy reader is connected, and on 2026-09-26 direct
retrieval of every Etsy legal and help page was refused with HTTP 403 by Etsy's bot
protection from two independent fetchers (the deployed system's and this build session's).
That is a proven external block on AUTOMATED retrieval, not on knowledge: the official pages
are indexed by search engines, and their indexed excerpts carry the substance of each rule.

So a reading here is a structured conclusion with three things attached: the official URL it
concerns, the verbatim excerpt it rests on (short, quoted, attributed), and a declared BASIS.
`basis` is never hidden: "search_engine_excerpt_of_official_page" means what it says, and a
reading of the page itself by the owner (basis "page") supersedes it. Nothing here is legal
advice; every entry is the company's own conservative reading, re-checkable by its digest.

What this module does NOT do: it does not fetch, it does not claim the page text, and it
does not mark a reading fresh forever. A reading carries `read_on`; `platform_policy`'s
30-day freshness rule applies to it exactly as to any other snapshot, so a reading seeded
from here goes stale on schedule and the watch says so.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

from .platform_policy import POLICY_SOURCES, MAX_AGE_DAYS

BASIS_EXCERPT = "search_engine_excerpt_of_official_page"
BASIS_PAGE = "page"
RETRIEVAL_BLOCK = ("direct retrieval of etsy.com/legal and help.etsy.com pages returned HTTP 403 "
                   "to automated fetchers on 2026-09-26 (two independent fetchers); readings rest on "
                   "search-engine excerpts of the official pages until the owner records a page reading")


@dataclass(frozen=True)
class Excerpt:
    url: str
    text: str


@dataclass(frozen=True)
class Reading:
    source: str                  # a POLICY_SOURCES key, or a knowledge topic key
    read_on: str                 # ISO date
    basis: str
    urls: tuple[str, ...]
    conclusions: tuple[dict, ...]
    excerpts: tuple[Excerpt, ...]
    limits: str = "not legal advice; the company's conservative reading"
    effective: str = ""          # the policy's own effective date where the excerpt states it

    def canonical_text(self) -> str:
        """The text the freshness digest is taken over: conclusions and excerpts, nothing else."""
        return json.dumps({"source": self.source, "read_on": self.read_on, "basis": self.basis,
                           "conclusions": list(self.conclusions),
                           "excerpts": [{"url": e.url, "text": e.text} for e in self.excerpts]},
                          sort_keys=True)

    def digest(self) -> str:
        return hashlib.sha256(self.canonical_text().encode("utf-8")).hexdigest()

    def to_dict(self) -> dict:
        return {"source": self.source, "read_on": self.read_on, "basis": self.basis, "urls": list(self.urls),
                "effective": self.effective, "conclusions": list(self.conclusions),
                "excerpts": [{"url": e.url, "text": e.text} for e in self.excerpts], "limits": self.limits,
                "digest": self.digest()}


READ_ON = "2026-09-26"


def _r(source, urls, conclusions, excerpts, effective=""):
    return Reading(source=source, read_on=READ_ON, basis=BASIS_EXCERPT, urls=tuple(urls),
                   conclusions=tuple(conclusions), excerpts=tuple(Excerpt(u, t) for u, t in excerpts), effective=effective)


# ---------------------------------------------------------------------------
# The six watched surfaces (POLICY_SOURCES keys)

READINGS: dict[str, Reading] = {
    "seller_policy": _r("seller_policy", ["https://www.etsy.com/legal/sellers/", "https://help.etsy.com/hc/en-us/articles/360000572888-Refunds-Returns-and-Exchanges-for-Sellers",
                                          "https://help.etsy.com/hc/en-us/articles/7471925990807-Etsy-s-Purchase-Protection-Program"], [
        {"rule": "ai_disclosure_required", "text": "an item created with the use of AI must be disclosed in the relevant listing; this is part of the Seller Policy", "affects": ["listing", "publishing"]},
        {"rule": "accurate_representation", "text": "listings must accurately represent the item's condition, quality and quantity", "affects": ["listing", "creative_assets"]},
        {"rule": "digital_not_returnable", "text": "digital listings cannot be returned or cancelled by the buyer; Purchase Protection covers not-as-described or never-delivered files, and a buyer must download an instant download before opening a case", "affects": ["support", "publishing"]},
        {"rule": "messages_on_platform", "text": "communication stays on Etsy Messages; sharing contact or payment details to move a transaction off-platform is prohibited; unsolicited promotion by message is spam", "affects": ["support", "growth"]},
        {"rule": "response_standard", "text": "responding to a buyer's first message within 48 hours is an Etsy customer-service standard (Brambleloop's own targets are stricter: 5 minutes canonical, 24 hours escalation)", "affects": ["support"]},
        {"rule": "shop_policies", "text": "sellers set shop policies (cancellations, returns, exchanges); Etsy provides a preset delivery policy for instant downloads", "affects": ["publishing", "support"]},
    ], [
        ("https://www.etsy.com/legal/sellers/", "If an item is created through the use of artificial intelligence, you must disclose this in your relevant listings."),
        ("https://help.etsy.com/hc/en-us/articles/360000572888-Refunds-Returns-and-Exchanges-for-Sellers", "Digital listings are not able to be returned or canceled."),
        ("https://help.etsy.com/hc/en-us/articles/7471925990807-Etsy-s-Purchase-Protection-Program", "For instant download items, buyers must download the item before opening a case."),
        ("https://www.etsy.com/legal/policy/off-platform-transactions/1254654515806", "It is prohibited to share contact information or QR codes for the purposes of making an off-platform transaction."),
    ]),
    "creativity_standards": _r("creativity_standards", ["https://www.etsy.com/legal/creativity", "https://www.etsy.com/seller-handbook/article/1275449912004",
                                                        "https://help.etsy.com/hc/en-us/articles/34707360607511-Reasons-a-Listing-May-Be-Removed-Under-Etsy-s-Creativity-Standards"], [
        {"rule": "four_categories", "text": "items must be made by, designed by, sourced by or handpicked by the seller", "affects": ["product_creation"]},
        {"rule": "designed_by_covers_digital_patterns", "text": "'designed by a seller' covers original designs offered as a digital download, including seller-prompted AI art; Brambleloop's patterns are seller-designed digital downloads", "affects": ["product_creation", "publishing"]},
        {"rule": "ai_allowed_with_creative_role_and_disclosure", "text": "AI may be used where the seller plays a clear creative role and is transparent; AI use must be disclosed in the listing description; machine output may not be passed off as handmade", "affects": ["publishing", "creative_assets"]},
        {"rule": "prompt_bundles_prohibited", "text": "packages of AI prompts may not be sold", "affects": ["product_creation"]},
        {"rule": "originality", "text": "reselling or misrepresenting another maker's design is a removal reason; every Brambleloop design must carry its own originality record", "affects": ["product_creation"]},
    ], [
        ("https://www.etsy.com/legal/creativity", "Designed by a seller: original designs by a seller or seller-prompted AI art offered as a digital download or produced/printed by a third-party."),
        ("https://www.etsy.com/seller-handbook/article/1275449912004", "Etsy does not allow items that simply offer packages of prompts."),
        ("https://www.etsy.com/seller-handbook/article/1275449912004", "Sellers must disclose within their listing description if an item is created with the use of AI."),
    ]),
    "listing_image_rules": _r("listing_image_rules", ["https://www.etsy.com/legal/policy/listing-image-requirements/253962679005",
                                                      "https://help.etsy.com/hc/en-us/articles/115015663347-Requirements-and-Best-Practices-for-Images-in-Your-Etsy-Shop"], [
        {"rule": "own_images_of_the_item", "text": "listing images must be the seller's own photographs or video of the item, not stock photos, artistic renderings or other sellers' images; the first image should show the actual item the buyer receives", "affects": ["creative_assets", "publishing"]},
        {"rule": "mockups_only_after_a_real_first_image", "text": "computer-generated mock-ups may appear in additional images for personalised or production-partner items only when the first image is a finished real item", "affects": ["creative_assets"]},
        {"rule": "generated_hero_not_evidence", "text": "consistent with platform_policy.ASSET_ROLES: a generated image of a finished object cannot be the primary listing image; a render of the pattern document or chart is the artefact itself and is permitted with labelling", "affects": ["creative_assets", "publishing"]},
        {"rule": "specs", "text": "up to 10 images; JPG/PNG/GIF; at least 2000 px on the shortest side recommended; 4:5 thumbnail crop; 10 MB per image", "affects": ["creative_assets"]},
        {"rule": "ai_images_disclosed", "text": "AI-generated images require disclosure in the listing", "affects": ["creative_assets", "publishing"]},
    ], [
        ("https://www.etsy.com/legal/policy/listing-image-requirements/253962679005", "Your own photographs or video content--not stock photos, artistic renderings, or photos used by other sellers or sites are required for listings."),
        ("https://www.etsy.com/legal/policy/listing-image-requirements/253962679005", "Computer-generated mockups may be used in additional listing images to showcase customization options -- just make sure your first image is the real deal."),
        ("https://help.etsy.com/hc/en-us/articles/115015663347-Requirements-and-Best-Practices-for-Images-in-Your-Etsy-Shop", "at least 2000 pixels on the shortest side"),
    ]),
    "advertising_rules": _r("advertising_rules", ["https://www.etsy.com/legal/advertising/", "https://help.etsy.com/hc/en-us/articles/360000338367-How-Etsy-s-Offsite-Ads-Work"], [
        {"rule": "offsite_ads_fee", "text": "15% of the order total attributed to an Offsite Ad while lifetime shop sales stay under US$10,000 in any 365 days; 12% once the shop has passed that; fee capped at US$100 per order; attribution window 30 days from the click", "affects": ["growth", "paid_media", "finance"]},
        {"rule": "offsite_ads_mandatory_above_threshold", "text": "participation is optional under US$10,000 in any consecutive 365 days and mandatory for the shop's lifetime once reached", "affects": ["growth", "paid_media"]},
        {"rule": "onsite_etsy_ads", "text": "Etsy Ads (onsite) are a separate daily-budget product; ads may not make claims the listing does not", "affects": ["paid_media"]},
        {"rule": "no_spend_without_owner", "text": "Brambleloop: no paid media until the owner grants ad authority (#242-#245 remain owner-gated)", "affects": ["paid_media"]},
        # F-264 / F-265 thresholds, held in the watched reading (F-291) so a guidance change
        # moves the digest and invalidates the assumptions built on them. Their basis is the
        # owner's master spec v0.8 statement of current Etsy guidance; the Etsy Ads help page
        # itself was not read (HTTP 403), which `status` says.
        {"rule": "onsite_ads_min_daily_budget", "text": "Etsy guidance recommends at least US$3-5 per day initially and, when practical, promoting all active listings to gather engagement data", "affects": ["paid_media", "growth"], "status": "UNVERIFIED: owner master spec v0.8 F-264; Etsy Ads help page not read (403)"},
        {"rule": "onsite_ads_per_listing_controls_threshold", "text": "per-listing strategies (visibility / efficient / lower click cost) need a daily budget of at least US$25; below it those controls are not available", "affects": ["paid_media"], "status": "UNVERIFIED: owner master spec v0.8 F-265; Etsy Ads help page not read (403)"},
    ], [
        ("https://help.etsy.com/hc/en-us/articles/360000338367-How-Etsy-s-Offsite-Ads-Work", "If your shop has made $10,000 USD or more in any consecutive 365-day period, participation in Offsite Ads is required."),
        ("https://help.etsy.com/hc/en-us/articles/360000338367-How-Etsy-s-Offsite-Ads-Work", "you'll be charged a 15% fee on the order total for an order attributed to an Offsite Ad ... a discounted fee of 12%"),
        ("https://help.etsy.com/hc/en-us/articles/360000338367-How-Etsy-s-Offsite-Ads-Work", "The Offsite Ads fee will never exceed $100 USD"),
        ("https://help.etsy.com/hc/en-us/articles/360000338367-How-Etsy-s-Offsite-Ads-Work", "Orders are attributed to Offsite Ads when a buyer clicks on an ad and completes a purchase from your shop within 30 days."),
    ]),
    "shilling_and_reviews": _r("shilling_and_reviews", ["https://www.etsy.com/legal/policy/shilling/243317364583", "https://www.etsy.com/legal/prohibited/"], [
        {"rule": "no_shilling", "text": "sellers may not have friends, family or compensated third parties buy items and leave biased reviews; free or reduced items, samples or cash for a positive review are prohibited", "affects": ["growth", "support", "portfolio"]},
        {"rule": "friends_and_family_honest_reviews", "text": "a friend's or relative's review is permitted only when the transaction happened on Etsy, there is no shared financial interest, no compensation beyond what every buyer gets, and the purchase was not made solely to review", "affects": ["growth"]},
        {"rule": "brambleloop_rule", "text": "consistent with the Execution Directive: no fake reviews, buyers, favourites, sock puppets or incentivised reviews; tester programmes never trade a review for a free pattern (#250 guard)", "affects": ["growth", "support"]},
    ], [
        ("https://www.etsy.com/legal/policy/shilling/243317364583", "Sellers are prohibited from having friends or family members purchase items and leave biased reviews, or compensating third parties through free or reduced items, samples, cash, or other compensation to purchase and leave biased, inauthentic, or untruthful positive reviews."),
    ]),
    "children_and_baby": _r("children_and_baby", ["https://www.etsy.com/legal/policy/childrens-clothing-and-products/239344787532", "https://www.etsy.com/legal/prohibited/",
                                                  "https://www.etsy.com/seller-handbook/article/1053896188509"], [
        {"rule": "patterns_and_instructions_in_scope", "text": "Etsy prohibits the patterns, designs and instructions for making prohibited children's items, not only the items; the refusal belongs before a CIR is written", "affects": ["product_creation", "publishing"]},
        {"rule": "prohibited_children_items", "text": "prohibited or restricted: infant sleep accessories and sleep products (crib bumpers, positioners), cribs and infant-sleep furniture, car seats and accessories, strollers, small parts and choking hazards for under-3s, upper-body outerwear with drawstrings (hoods and necks), bejewelled pacifiers, infant neck floaties, magnets, water beads, novelty lighters, baby formula", "affects": ["product_creation"]},
        {"rule": "sleepwear", "text": "loose-fitting non-flame-resistant sleepwear or loungewear for children from 10 months to size 14 is prohibited; tight-fitting sleepwear and flame-resistant fibres (polyester, acrylic) are generally permitted; a crochet garment is not to be sold or described as sleepwear unless it meets that", "affects": ["product_creation", "listing"]},
        {"rule": "drawstrings", "text": "children's hooded cardigans may not carry drawstrings or cords at the hood or neck; a button closure is the compliant design (Bench2's cardigan is button-closed)", "affects": ["product_creation"]},
        {"rule": "seller_compliance", "text": "sellers must meet the safety laws of the markets they sell into (Canada: Health Canada children's product regulations; US: CPSIA) and Etsy may remove recalled or hazardous items even without a recall", "affects": ["publishing"]},
    ], [
        ("https://www.etsy.com/legal/policy/childrens-clothing-and-products/239344787532", "Etsy also prohibits patterns, designs, or instructions for making these items."),
        ("https://www.etsy.com/legal/policy/childrens-clothing-and-products/239344787532", "Etsy prohibits loose-fitting, non-flame resistant sleepwear/loungewear for children sized from 10 months, up to size 14."),
        ("https://www.etsy.com/legal/policy/childrens-clothing-and-products/239344787532", "Children's Loungewear and Sleepwear, Cribs and Furniture for Infant Sleeping, Infant Neck Floaties, Infant Sleeping Accessories, Magnets, Novelty Lighters, Small Parts and Choking Hazards, Strollers, Upper-body Outerwear with Drawstrings, and Water Beads"),
    ], effective="updated 2026-08-11 (section 2); earlier effective 2026-06-02"),
}

# ---------------------------------------------------------------------------
# Further commerce topics the closeout requires (not watched surfaces; knowledge only)

TOPICS: dict[str, Reading] = {
    "fees": _r("fees", ["https://www.etsy.com/ca/legal/fees/", "https://help.etsy.com/hc/en-us/articles/115015628847-What-are-Payment-Processing-Fees-for-Selling-on-Etsy",
                        "https://help.etsy.com/hc/en-us/articles/360035902374-Etsy-Fee-Basics"], [
        {"fee": "listing", "amount": "US$0.20 per listing, lasts four months or until sold; renewals cost the same", "code": "scale.target.LISTING_FEE_USD, integrations.etsy.LISTING_FEE_USD"},
        {"fee": "transaction", "amount": "6.5% of the sale price including shipping and gift wrap; for a digital download, 6.5% of the item price", "code": "commerce.pricing.TRANSACTION_FEE, scale.target.TRANSACTION_FEE_RATE, finance.currency"},
        {"fee": "payment_processing_canada", "amount": "3% + CA$0.25 per order for a Canadian shop on Etsy Payments (help page states 3-4% + CA$0.25 depending on country)", "code": "radar.market note"},
        {"fee": "currency_conversion", "amount": "2.5% when the listing currency differs from the payment-account currency; Brambleloop lists in CAD with a CAD payment account to avoid it", "code": "finance.currency"},
        {"fee": "regulatory_operating", "amount": "charged in certain countries including Canada; the exact Canadian percentage was not stated in the indexed excerpts and is recorded as UNKNOWN until the owner reads the fees page", "code": "UNKNOWN"},
        {"fee": "offsite_ads", "amount": "15% (12% above US$10,000 trailing-365-day sales) of attributed orders, capped at US$100 per order", "code": "advertising_rules"},
        {"fee": "etsy_ads", "amount": "optional daily budget set by the seller; owner-gated", "code": "paid_media"},
    ], [
        ("https://help.etsy.com/hc/en-us/articles/115015628847-What-are-Payment-Processing-Fees-for-Selling-on-Etsy", "there is a 3-4% + CA$0.25 payment processing fee when an item is sold"),
        ("https://help.etsy.com/hc/en-us/articles/360035902374-Etsy-Fee-Basics", "Your first item costs $0.20 USD to list, and a listing lasts for four months or until the item is sold."),
        ("https://help.etsy.com/hc/en-us/articles/360035902374-Etsy-Fee-Basics", "there is a 6.5% transaction fee on the sale price (including the postage price you set)"),
    ]),
    "digital_downloads": _r("digital_downloads", ["https://help.etsy.com/hc/en-us/articles/115015628347-How-to-Manage-Your-Digital-Listings",
                                                  "https://help.etsy.com/hc/en-us/articles/115013328108-How-to-Download-a-Digital-Item"], [
        {"rule": "files", "text": "up to five files per listing, 20 MB each; file names up to 70 characters of letters, digits, periods, underscores and hyphens, shown to the buyer as named", "code": "publish.delivery / release bundle"},
        {"rule": "instant_download_requires_file", "text": "an instant-download listing cannot be published or saved without its file attached", "code": "publishing"},
        {"rule": "two_kinds", "text": "instant downloads (ready files) and made-to-order downloads (custom files, delivered within 7 days or the buyer may be refunded)", "code": "publishing"},
        {"rule": "no_returns", "text": "digital purchases cannot be returned or cancelled; Purchase Protection covers not-as-described or undelivered files", "code": "support"},
    ], [
        ("https://help.etsy.com/hc/en-us/articles/115015628347-How-to-Manage-Your-Digital-Listings", "You can upload up to five digital files, with a maximum size of 20MB for each file."),
        ("https://help.etsy.com/hc/en-us/articles/115015628347-How-to-Manage-Your-Digital-Listings", "File names are limited to 70 alphanumeric characters, periods, underscores, or hyphens."),
        ("https://help.etsy.com/hc/en-us/articles/115015628347-How-to-Manage-Your-Digital-Listings", "You will be unable to publish or save an instant digital listing if there is no file attached to it."),
    ]),
    "intellectual_property": _r("intellectual_property", ["https://www.etsy.com/legal/ip/", "https://www.etsy.com/legal/ip-dmca/", "https://www.etsy.com/legal/ip-counter/",
                                                          "https://help.etsy.com/hc/en-us/articles/360034079714-What-to-Do-if-You-Receive-a-Notice-of-Intellectual-Property-Infringement"], [
        {"rule": "seller_responsible", "text": "the seller must hold every right to the content it lists; repeat reports can close every shop the seller operates", "code": "product_creation provenance record"},
        {"rule": "reporting", "text": "rights holders report through the Etsy Reporting Portal; Etsy removes on a compliant report and notifies the seller", "code": "support workflow"},
        {"rule": "counter_notice", "text": "DMCA counter notices are accepted for US-based copyright reports only; if the claimant does not file for a court order within 10 business days the listing may be reactivated", "code": "support workflow"},
        {"rule": "no_relisting_while_disputed", "text": "do not create new listings for disputed content until the dispute is resolved", "code": "publishing"},
        {"rule": "brambleloop_originality", "text": "each design carries an originality/provenance record naming its source code and generator; purchased benchmark patterns are research evidence only and never a design source", "code": "products provenance"},
    ], [
        ("https://www.etsy.com/legal/ip/", "Etsy only accepts reports of infringement from the intellectual property owner or the owner's authorized agent."),
        ("https://help.etsy.com/hc/en-us/articles/360040496854-How-to-File-a-DMCA-Counter-Notice", "Etsy accepts counter notices for US-based copyright infringement reports only."),
    ]),
    "customer_communication": _r("customer_communication", ["https://www.etsy.com/legal/policy/off-platform-transactions/1254654515806", "https://www.etsy.com/seller-handbook/article/26590492608",
                                                            "https://help.etsy.com/hc/en-us/articles/23948455256983-Why-were-My-Messages-Muted"], [
        {"rule": "on_platform", "text": "keep all order communication in Etsy Messages; never share contact details or payment links for off-platform transactions", "code": "support"},
        {"rule": "no_spam", "text": "no unsolicited advertising by message; spam mutes messaging for 48 hours", "code": "growth, support"},
        {"rule": "prompt_reply", "text": "reply to first messages within 48 hours (Etsy standard); Brambleloop targets 5 minutes / 24 hours", "code": "support.service"},
        {"rule": "casl", "text": "Canada: CASL applies to any commercial electronic message Brambleloop sends outside Etsy (consent, identification, unsubscribe)", "code": "growth.owned CASL gate"},
    ], [
        ("https://www.etsy.com/legal/policy/off-platform-transactions/1254654515806", "keep your communication on the Etsy platform via Messages"),
        ("https://help.etsy.com/hc/en-us/articles/23948455256983-Why-were-My-Messages-Muted", "your messages will be muted for 48 hours"),
    ]),
    "refunds_digital": _r("refunds_digital", ["https://help.etsy.com/hc/en-us/articles/360000572888-Refunds-Returns-and-Exchanges-for-Sellers",
                                              "https://help.etsy.com/hc/en-us/articles/7471925990807-Etsy-s-Purchase-Protection-Program"], [
        {"rule": "policy", "text": "digital items are not returnable or cancellable; a seller may still refund voluntarily; Purchase Protection refunds the buyer (up to US$250) when a file is not as described or never delivered and the seller is not charged where the order met the programme's requirements", "code": "support.refunds"},
        {"rule": "brambleloop_stance", "text": "a defective pattern is a support incident that triggers a re-validated release (gates.incidents), never a silent patch; refunds for a proven defect are honoured", "code": "gates.incidents"},
    ], [
        ("https://help.etsy.com/hc/en-us/articles/7471925990807-Etsy-s-Purchase-Protection-Program", "Etsy will refund buyers up to $250 USD (including shipping & taxes) and sellers will not be held responsible."),
    ]),
    "listing_metadata": _r("listing_metadata", ["https://help.etsy.com/hc/en-us/articles/115015628707-How-to-Create-a-Listing"], [
        {"rule": "fields", "text": "title, description, up to 13 tags, category (taxonomy id), attributes, 'who made it / what is it / when was it made' creativity answers, digital-item flag with files, price, quantity; the taxonomy id must be read back from Etsy's API (publish.listing_schema records that gap)", "code": "publish.listing_schema"},
        {"rule": "ai_disclosure_field", "text": "the listing form carries an AI-use disclosure; Brambleloop's disclosure lines are platform_policy.DISCLOSURES and are applied by the disclosure gate", "code": "gates.platform_policy.classify"},
    ], [
        ("https://help.etsy.com/hc/en-us/articles/115015628707-How-to-Create-a-Listing", "How to Create a Listing"),
    ]),
}


def _search_guidance() -> Reading:
    """The search guidance reading (F-242), built from lane G's dated constraint record.

    Every limit the search code enforces (`commerce.search` / `commerce.seo` constants and
    `publish.listing_schema`'s tag rule) is a conclusion here, with the excerpt and date it
    rests on, so a changed reading changes this digest and the watch sees it.
    """
    from ..seo import constraints as SC

    keys = ("title_max_chars", "tag_max_count", "tag_max_chars", "tag_no_leading_symbol",
            "attributes_act_like_tags", "search_visibility_page")
    rows = [SC.BY_KEY[k] for k in keys if k in SC.BY_KEY]
    return Reading(
        source="search_guidance", read_on=SC.RETRIEVED_ON, basis=BASIS_EXCERPT,
        urls=tuple(dict.fromkeys(r.url for r in rows)),
        conclusions=tuple({"rule": r.key, "text": r.rule, "value": r.value,
                           "status": r.status, "affects": ["listing", "search"]}
                          for r in rows),
        excerpts=tuple(Excerpt(r.url, r.quote) for r in rows if r.quote))


READINGS["search_guidance"] = _search_guidance()


def all_readings() -> dict[str, Reading]:
    return {**READINGS, **TOPICS}


def describe() -> dict:
    return {"read_on": READ_ON, "basis": BASIS_EXCERPT, "retrieval_block": RETRIEVAL_BLOCK, "max_age_days": MAX_AGE_DAYS,
            "surfaces": {k: v.to_dict() for k, v in READINGS.items()}, "topics": {k: v.to_dict() for k, v in TOPICS.items()},
            "supersession": "a reading with basis 'page' recorded by the owner (record_snapshot with the page text) supersedes the excerpt reading of the same source"}


def seed_snapshots(db, *, today=None) -> dict:
    """Record the repository's reading of each watched surface that has never been read.

    Only never-read sources are seeded: an existing snapshot (page-based or a previous seed)
    is never overwritten, and a stale one is left stale so the watch keeps saying so. The
    snapshot carries the reading's date, not today's, so a reading older than MAX_AGE_DAYS
    is immediately reported stale rather than laundered fresh by being seeded late.
    """
    from datetime import date

    from .platform_policy import freshness, record_snapshot

    today = today or date.today()
    report = freshness(db, today=today)
    seeded = []
    for source in report["never_checked"]:
        reading = READINGS.get(source)
        if reading is None:
            continue
        res = record_snapshot(db, source, text=reading.canonical_text(), version=f"{reading.read_on}:{reading.basis}",
                              summary=f"repository reading of {reading.read_on} on basis {reading.basis}: " + "; ".join(c.get("rule", c.get("fee", "")) for c in reading.conclusions),
                              checked_on=reading.read_on)
        seeded.append({"source": source, "snapshot_id": res["id"], "digest": res["digest"], "basis": reading.basis, "read_on": reading.read_on})
    return {"seeded": seeded, "basis": BASIS_EXCERPT, "retrieval_block": RETRIEVAL_BLOCK,
            "after": {k: v for k, v in freshness(db, today=today).items() if k in ("current", "stale", "never_checked", "all_fresh")}}
