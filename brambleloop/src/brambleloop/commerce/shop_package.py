"""Everything the shop needs on day one that can be decided before there is a shop.

The storefront module already holds the shop's *voice* -- announcement, About, sections,
banner and icon briefs -- and `commerce.terms` already decides what a buyer may do with what
they bought. What was missing between them is the part a digital seller is actually judged
on, and it is missing in a specific way: not absent, but written three times.

Today the licence a buyer reads exists in three places. `commerce.terms` decides that
finished items may be sold "by individual makers and small businesses, not manufactured at
scale". `brand.storefront`'s policy says "sell the items you make from it", with no limit.
`commerce.seo`'s description block says "Sell what you make". Those are three answers to the
single most-asked question in the craft-pattern market, and a buyer who finds the difference
is entitled to rely on the most favourable one. That is requirement 40's drift failure,
already live, in a repository that has never sold anything.

So this module is one source for the customer-facing package, assembled from the decisions
that were already made rather than restating them:

- **the licence and support terms render from `commerce.terms`**, never from prose here;
- **the AI and digital-download disclosures render from `gates.platform_policy`**, which is
  where the policy gate reads them from, so a listing and the FAQ cannot disagree;
- **returns, delivery and the tax position are written here**, because nothing else owns
  them, and each one carries where it came from.

**Every claim about the outside world is labelled by how well it is known.** PRIMARY means
the sentence was read from the document that governs it, on a recorded date, and the sentence
is here. SECONDARY means it was reported by something other than that document -- a search
result, a help centre nobody could fetch, a third party -- and is good enough to act on and
not good enough to rely on. INFERRED means this company reasoned, and the reasoning can be
argued with. The distinction is the whole point: Etsy's help centre and policy pages refuse
automated readers, so the strongest available evidence for several of these is secondary, and
pretending otherwise would make a stale assumption indistinguishable from a checked one.

**Nothing here is legal advice, and the items that genuinely need a lawyer say so** rather
than being answered confidently. `needs_professional_advice` is a field, not a disclaimer.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from ..gates import platform_policy
from . import terms as customer_terms

# How the outside world is known. Ordered weakest-last so a reader can see the direction.
PRIMARY = "primary"
SECONDARY = "secondary"
INFERRED = "inferred"

BASES: tuple[str, ...] = (PRIMARY, SECONDARY, INFERRED)

BASIS_MEANS: dict[str, str] = {
    PRIMARY: ("read from the document that governs it, on the recorded date, with the "
              "sentence kept"),
    SECONDARY: ("reported by something other than the governing document -- a search result, "
                "a help centre that refuses automated readers, or a third party"),
    INFERRED: "this company's reading, which can be argued with",
}

# When the sources below were gathered. Part of every claim, because the claim is about a
# world that changes: Etsy's fees, Etsy's returns policy and the CRA's thresholds have all
# moved within the life of a shop.
RESEARCHED_ON = "2026-09-24"

# Beyond this a source is a historical document. Same reasoning as the platform-policy watch,
# stated separately because this governs a different set of documents.
MAX_AGE_DAYS = 90


class PackageRefused(ValueError):
    """A claim labelled better than its evidence, or a surface with nothing on it."""


@dataclass(frozen=True)
class Source:
    """Where a claim came from, and whether anybody could actually read it.

    `fetched` is separate from `basis` on purpose. A URL that returned 403 to every automated
    reader here is still the right citation and is not evidence that anybody checked it, and
    collapsing those two into one field is how "we cite Etsy's help centre" comes to mean
    "we read a blog about Etsy's help centre".
    """

    key: str
    url: str
    read_on: str
    fetched: bool
    quote: str = ""
    note: str = ""

    def to_dict(self) -> dict:
        return {"key": self.key, "url": self.url, "read_on": self.read_on,
                "fetched": self.fetched, "quote": self.quote, "note": self.note}


SOURCES: dict[str, Source] = {
    "etsy_openapi": Source(
        "etsy_openapi", "https://www.etsy.com/openapi/generated/oas/3.0.0.json",
        RESEARCHED_ON, True,
        quote=("Setting a `draft` listing to `active` will also publish the listing on "
               "etsy.com and requires that the listing have an image set."),
        note="Etsy's own published API description; the only Etsy document that served us."),
    "etsy_shop_api": Source(
        "etsy_shop_api", "https://www.etsy.com/openapi/generated/oas/3.0.0.json",
        RESEARCHED_ON, True,
        quote=("updateShop properties: title, announcement, sale_message, "
               "digital_sale_message, policy_additional"),
        note=("The same document, read for the shop rather than the listing. There is no "
              "write endpoint for the delivery, returns, privacy or FAQ policy text, for "
              "the About story, or for the banner and icon -- only for these five fields "
              "and, separately, for shop sections and return policies.")),
    "etsy_digital_returns": Source(
        "etsy_digital_returns",
        "https://community.etsy.com/t5/Announcements/"
        "An-update-to-our-policy-on-returns-for-digital-items/td-p/139765812",
        RESEARCHED_ON, True,
        quote=("Sellers will no longer be able to accept returns on digital listings given "
               "the nature of the items."),
        note=("Etsy's own announcement. It also says that if a buyer contacts the seller "
              "about a digital listing, \"you're free to resolve the issue as you see "
              "fit\" -- so a goodwill refund remains the seller's to give.")),
    "cra_registration": Source(
        "cra_registration",
        "https://www.canada.ca/en/revenue-agency/services/tax/businesses/topics/"
        "gst-hst-businesses/when-register-charge.html",
        RESEARCHED_ON, True,
        quote=("Your effective date of registration is no later than the day of the supply "
               "that made you exceed $30,000. ... You will have to register within 29 days "
               "of your effective date of registration."),
        note="The CRA's own page on when a small supplier stops being one."),
    "eu_withdrawal": Source(
        "eu_withdrawal",
        "https://eur-lex.europa.eu/EN/legal-content/summary/"
        "consumer-information-right-of-withdrawal-and-other-consumer-rights.html",
        RESEARCHED_ON, False,
        note=("Directive 2011/83/EU. The withdrawal right for digital content not supplied "
              "on a tangible medium is lost where the consumer gives prior express consent "
              "to immediate supply and acknowledges losing it. Read through a search "
              "summary of the EUR-Lex overview rather than from the directive text.")),
    "casl": Source(
        "casl", "https://laws-lois.justice.gc.ca/eng/acts/E-1.6/index.html",
        RESEARCHED_ON, False,
        note=("CASL. A commercial electronic message needs consent, sender identification "
              "and a working unsubscribe. The CRTC's guidance pages refused every automated "
              "read from here. `growth.owned` already encodes the consent bases and their "
              "clocks and is the enforcement point; this records the shop-facing "
              "consequence only.")),
    "etsy_help": Source(
        "etsy_help", "https://help.etsy.com/hc/en-us/",
        RESEARCHED_ON, False,
        note=("Etsy's help centre -- shop policies, fees, Canadian remittances and VAT on "
              "digital items -- returned HTTP 403 to every automated request from this "
              "environment, with and without a browser user agent. Anything attributed to "
              "it here is SECONDARY and needs a human to open the page.")),
}


def _source(key: str) -> Source:
    try:
        return SOURCES[key]
    except KeyError:  # pragma: no cover - a typo in a citation, caught at import
        raise PackageRefused(f"{key!r} is not a recorded source: {sorted(SOURCES)}") from None


@dataclass(frozen=True)
class Claim:
    """One thing believed about the world, with its evidence and its consequence.

    `consequence` is what the shop does about it. A claim with no consequence is a fact in a
    document nobody reads; the reason every entry has one is that this file's whole job is to
    turn what was researched into what the shop says and does on day one.
    """

    key: str
    claim: str
    basis: str
    source_key: str
    consequence: str
    needs_professional_advice: bool = False

    def __post_init__(self) -> None:
        if self.basis not in BASES:
            raise PackageRefused(f"{self.key}: basis {self.basis!r} is not one of "
                                 f"{list(BASES)}")
        source = _source(self.source_key)
        # Reachability first, then the sentence. The order is the argument: a source nobody
        # could open cannot have been read, whatever is quoted next to it, and a rule that
        # complained about the missing quote first would send somebody off to find a
        # sentence for a page they still could not open.
        if self.basis == PRIMARY and not source.fetched:
            raise PackageRefused(
                f"{self.key} is labelled primary and {self.source_key} was never fetched "
                f"from this environment. A citation is not a reading")
        if self.basis == PRIMARY and not source.quote.strip():
            raise PackageRefused(
                f"{self.key} is labelled primary and its source keeps no sentence. A "
                f"primary label with nothing quoted is an assumption that has stopped "
                f"being arguable")

    def to_dict(self) -> dict:
        return {"key": self.key, "claim": self.claim, "basis": self.basis,
                "consequence": self.consequence,
                "needs_professional_advice": self.needs_professional_advice,
                "source": _source(self.source_key).to_dict()}


# ---------------------------------------------------------------------------
# What is known about selling a digital pattern, from Canada, to the world

CLAIMS: tuple[Claim, ...] = (
    Claim("etsy_digital_not_returnable",
          "Etsy does not let a seller accept returns on a digital listing",
          PRIMARY, "etsy_digital_returns",
          ("the returns policy states it in its first sentence, before the sale, and then "
           "says what the shop does instead. A buyer who discovers it afterwards is a "
           "refund request, a support case and a rating")),
    Claim("etsy_goodwill_refund_remains",
          "a seller may still resolve a digital complaint however it chooses",
          PRIMARY, "etsy_digital_returns",
          ("'non-returnable' is not 'no help'. The policy offers the two remedies that cost "
           "nothing and fix the actual problem: re-send the file, or correct the pattern "
           "and re-issue it to everyone who bought it")),
    Claim("etsy_image_before_publish",
          "a listing cannot be made active without at least one listing image",
          PRIMARY, "etsy_openapi",
          ("shop-opening day depends on listing images reaching Etsy. Nothing in this system "
           "uploaded one until 2026-09-25; integrations.etsy.EtsyClient.upload_image now "
           "does, and no upload has ever been confirmed by Etsy because this environment has "
           "no credentials. Still a launch blocker in publish.listing_schema.gaps(), for "
           "that narrower reason")),
    Claim("most_of_the_shop_is_typed_by_a_person",
          "Etsy's API writes five shop text fields, shop sections and return policies, and "
          "nothing else: the policy page, the About story, the banner and the icon have no "
          "write endpoint",
          PRIMARY, "etsy_shop_api",
          ("the package is prepared as text a person pastes, field by field, with the Shop "
           "Manager path beside each one. Preparing it as an integration would be preparing "
           "something that cannot be built")),
    Claim("cra_small_supplier_threshold",
          "a Canadian small supplier must register for GST/HST once taxable supplies exceed "
          "CA$30,000, effective from the sale that crosses it, with 29 days to register",
          PRIMARY, "cra_registration",
          ("the shop opens under the small-supplier position and the threshold is a number "
           "somebody has to watch. It is a revenue figure the finance department can "
           "compute, not a judgement")),
    Claim("etsy_collects_canadian_tax",
          "Etsy acts as a marketplace facilitator and collects GST/HST on sales to Canadian "
          "buyers, and providing a GST/HST number changes who is responsible",
          SECONDARY, "etsy_help",
          ("the shop states that taxes are handled at checkout by Etsy and does not quote a "
           "rate. Whether to give Etsy a GST/HST number is an owner decision with a tax "
           "consequence, not a setting to pick"),
          needs_professional_advice=True),
    Claim("etsy_collects_vat_on_digital",
          "Etsy collects VAT on digital items for buyers in jurisdictions that require it, "
          "so a non-registered seller does not register abroad to sell a PDF",
          SECONDARY, "etsy_help",
          ("international pricing is set in CAD and the shop makes no VAT statement of its "
           "own. Selling the same PDF off-Etsy would be a different question entirely"),
          needs_professional_advice=True),
    Claim("eu_withdrawal_waived_on_consent",
          "an EU buyer's 14-day withdrawal right is lost for digital content supplied "
          "immediately, only where they expressly consented and acknowledged losing it",
          SECONDARY, "eu_withdrawal",
          ("the delivery policy says the file is available immediately and that downloading "
           "it is what ends the right to change your mind. On Etsy the consent is collected "
           "by the platform's checkout, which is a dependency worth naming rather than "
           "assuming"),
          needs_professional_advice=True),
    Claim("casl_governs_our_email",
          "a commercial electronic message to a Canadian recipient needs consent, sender "
          "identification and a working unsubscribe",
          SECONDARY, "casl",
          ("the shop never adds a buyer to a mailing list because they bought something. "
           "`growth.owned` is the gate that decides every send; the privacy policy says so "
           "in the buyer's words")),
    Claim("pattern_copyright_not_the_finished_object",
          "the copyright in a pattern covers the document, its charts and its photographs, "
          "and the terms a seller offers about finished items are a licence that seller "
          "chooses to grant rather than a right the law supplies",
          INFERRED, "casl",
          ("the finished-item answer is stated as what this shop permits, not as what the "
           "law requires, and `commerce.terms.enforceable` stays false until a lawyer has "
           "read it. Over-claiming here is the standard failure of the category"),
          needs_professional_advice=True),
)

CLAIMS_BY_KEY: dict[str, Claim] = {c.key: c for c in CLAIMS}


# ---------------------------------------------------------------------------
# The customer-facing surfaces, rendered from one decision each

# Etsy's own shop policy sections, plus the two this shop adds. `ai` is not one of Etsy's
# sections; it is carried here because the disclosure has to live somewhere a buyer can find
# it and the listing description alone is not a policy.
POLICY_SECTIONS: tuple[str, ...] = ("delivery", "returns", "licence", "support", "privacy",
                                    "ai")

DELIVERY = (
    "Every pattern here is a digital file. There is no processing time and nothing is "
    "posted: the moment your payment clears, the PDF is available from your Etsy account "
    "under Purchases and downloads, and Etsy emails you a link as well. Files are PDFs, "
    "readable on a phone, a tablet or paper. If a download will not start or a file will "
    "not open, message us and we will get it to you.")

RETURNS = (
    "Digital patterns cannot be returned, and Etsy does not allow a seller to accept a "
    "return on a digital listing. We would rather you knew that before you bought than "
    "after. What we do instead, and will do without argument: if a pattern contains an "
    "error, we correct the pattern itself, re-issue it, and send the corrected file to "
    "everyone who bought it. If you cannot open or download your file, we will get it to "
    "you. If a pattern turns out not to be what the listing led you to expect, tell us -- "
    "that is a listing we need to fix, and we will make it right with you.")

PRIVACY = (
    "We only see what Etsy shares with us to fulfil your order. We do not sell or share "
    "your information, and buying something does not put you on a mailing list -- we only "
    "email people who asked us to, and every email we send can be stopped in one click.")


def ai_disclosure() -> str:
    """The disclosure, rendered from the gate that enforces it rather than written again.

    `gates.platform_policy` already owns these sentences because the policy gate checks that
    a release carries them. Writing a second, friendlier version here is how a shop ends up
    disclosing one thing on a listing and a different thing in its About.
    """
    lines = [platform_policy.DISCLOSURES["digital_download"],
             platform_policy.DISCLOSURES["ai_assisted_design"],
             platform_policy.DISCLOSURES["deterministic_render"]]
    return "\n".join(lines)


def licence_text(terms: customer_terms.Terms | None = None) -> str:
    """The buyer's licence, from the one place it was decided."""
    return customer_terms.render(terms or customer_terms.BRAMBLELOOP_TERMS, "listing")


def policies(terms: customer_terms.Terms | None = None) -> dict[str, str]:
    """The six policy surfaces a digital shop opens with."""
    decided = terms or customer_terms.BRAMBLELOOP_TERMS
    return {
        "delivery": DELIVERY,
        "returns": RETURNS,
        "licence": licence_text(decided),
        "support": decided.sentence(customer_terms.SUPPORT_POLICY),
        "privacy": PRIVACY,
        "ai": ai_disclosure(),
    }


# The questions a pattern buyer actually asks, in the order they ask them. The first one is
# the one the whole category answers badly, so it is first and it is answered from the terms
# rather than from a sentence somebody wrote in a support reply.
FAQ_ORDER: tuple[str, ...] = (
    "sell_what_i_make", "is_it_a_finished_item", "where_is_my_file", "can_i_print_it",
    "can_i_teach_from_it", "us_or_uk_terms", "what_if_there_is_a_mistake",
    "can_i_get_a_refund", "was_ai_used", "do_you_ship",
)


def faq(terms: customer_terms.Terms | None = None) -> list[dict]:
    """The FAQ, with every licence answer rendered from `commerce.terms`.

    The answers that are not about the licence are written here because nothing else owns
    them. The ones that are about the licence quote the decision verbatim, which is what
    makes `commerce.terms.consistency` able to check this surface at all.
    """
    decided = terms or customer_terms.BRAMBLELOOP_TERMS
    sell = decided.sentence(customer_terms.FINISHED_ITEM_SALE)
    use = decided.sentence(customer_terms.PDF_USE)
    share = decided.sentence(customer_terms.REDISTRIBUTION)
    support = decided.sentence(customer_terms.SUPPORT_POLICY)
    versions = decided.sentence(customer_terms.VERSION_POLICY)

    answers: dict[str, tuple[str, str]] = {
        "sell_what_i_make": (
            "Can I sell what I make from this pattern?",
            f"Yes: {sell}. You do not owe us a percentage and you do not need to ask. What "
            f"you may not do is pass on the pattern itself -- {share}."),
        "is_it_a_finished_item": (
            "Am I buying a blanket or a pattern?",
            "A pattern. You receive instructions and charts as a PDF; you make the item "
            "yourself. Nothing is shipped."),
        "where_is_my_file": (
            "Where is my file?",
            "In your Etsy account under Purchases and downloads, available as soon as your "
            "payment clears. Etsy also emails you a link. If neither works, message us."),
        "can_i_print_it": (
            "Can I print it?",
            f"Yes. The pattern is {use}."),
        "can_i_teach_from_it": (
            "Can I teach a class from it?",
            f"Yes, on one condition that is in the terms: the pattern is {use}. Each "
            f"participant needs their own copy."),
        "us_or_uk_terms": (
            "US or UK crochet terms?",
            "Both. Every pattern names the terminology it is written in and lists the "
            "equivalent terms in its stitch key, so a UK crocheter can work a US pattern "
            "without translating it in their head."),
        "what_if_there_is_a_mistake": (
            "What if there is a mistake in the pattern?",
            f"Tell us the pattern and the row. {support}. If the pattern is wrong we fix "
            f"the pattern, not just your copy: {versions}."),
        "can_i_get_a_refund": (
            "Can I get a refund?",
            "Digital patterns are not returnable, and Etsy does not allow a seller to "
            "accept a return on a digital listing. If something is wrong -- a file that "
            "will not open, an error in the pattern, a listing that misled you -- message "
            "us and we will put it right."),
        "was_ai_used": (
            "Was this designed by AI?",
            ai_disclosure()),
        "do_you_ship": (
            "Do you ship internationally?",
            "There is nothing to ship. A digital pattern is the same file everywhere, and "
            "any tax due is handled by Etsy at checkout."),
    }
    return [{"key": key, "question": answers[key][0], "answer": answers[key][1]}
            for key in FAQ_ORDER]


# ---------------------------------------------------------------------------
# What a machine can set, and what a person has to type

# Etsy's `updateShop` accepts exactly five text fields, read from its own API document:
# title, announcement, sale_message, digital_sale_message and policy_additional. Everything
# else in this package -- the delivery, returns, privacy and FAQ text, the About story, the
# banner and the icon -- has no write endpoint at all. That is not a limitation to work
# around; it is the shape of the launch. Four of the six policies below are typed into Shop
# Manager by a person, once, and the value of preparing them here is that the person types
# rather than composes.
SHOP_TEXT_FIELDS: tuple[str, ...] = ("title", "announcement", "sale_message",
                                     "digital_sale_message", "policy_additional")

# The message Etsy sends a buyer the moment a digital item is bought. It is the one surface
# that reaches every customer, and a shop that leaves it blank sends nothing at the only
# moment the buyer is certainly paying attention.
DIGITAL_SALE_MESSAGE = (
    "Thank you. Your pattern is ready now: open your Etsy account, go to Purchases and "
    "downloads, and the PDF is there. Etsy has emailed you a link as well.\n\n"
    "Two things worth knowing. You may sell the items you make from this pattern -- you do "
    "not owe us anything and you do not need to ask. And if anything in the pattern does "
    "not add up, reply to this message with the pattern name and the row number: we correct "
    "the pattern itself, re-issue it, and send the corrected file to everyone who bought "
    "it, including you.")


def shop_text(terms: customer_terms.Terms | None = None) -> dict[str, str]:
    """The five shop fields Etsy's API can actually write, ready to send.

    Assembled here so that the day the phase moves, setting them is a call rather than a
    writing session. `policy_additional` carries the licence and the disclosures because it
    is the only policy text with a write endpoint -- the rest of the policy page is typed by
    a person, and this is what stops the two halves saying different things.
    """
    decided = terms or customer_terms.BRAMBLELOOP_TERMS
    return {
        "title": "Crochet patterns checked row by row before they are sold",
        "announcement": "",     # seasonal; `brand.storefront` owns which one is current
        "sale_message": DIGITAL_SALE_MESSAGE,
        "digital_sale_message": DIGITAL_SALE_MESSAGE,
        "policy_additional": "\n\n".join([licence_text(decided), ai_disclosure()]),
    }


# What no endpoint can set. Listed so the owner action is a list of fields to fill rather
# than "set up the shop", which is the difference between twenty minutes and an afternoon.
MANUAL_ONLY: tuple[tuple[str, str], ...] = (
    ("shop_policies_delivery", "Shop Manager > Settings > Policies: processing and delivery"),
    ("shop_policies_returns", "Shop Manager > Settings > Policies: returns and exchanges"),
    ("shop_policies_privacy", "Shop Manager > Settings > Policies: privacy"),
    ("shop_policies_faq", "Shop Manager > Settings > Policies: frequently asked questions"),
    ("about_story", "Shop Manager > Settings > About your shop"),
    ("banner_and_icon", "Shop Manager > Settings > Info & appearance"),
)


# The About page's shape, rather than its words. `brand.storefront.ABOUT` holds the words,
# and a second copy of them here would be the same drift this module exists to stop. What is
# recorded is what an About has to cover before a cautious buyer trusts a shop with no
# reviews, because that is the thing which is easy to leave out and impossible to notice.
ABOUT_SECTIONS: tuple[tuple[str, str], ...] = (
    ("what_we_make", "what the product is, in the first sentence, in the buyer's words"),
    ("how_it_is_made", "the process claim -- what is checked, by what, before release"),
    ("why_it_matters", "the failure this prevents, from the maker's side of it"),
    ("how_ai_is_used", "what a model did and what it did not, said plainly"),
    ("what_happens_if_it_is_wrong", "the promise that costs something to keep"),
)


def check_about(text: str) -> list[str]:
    """Whether an About covers what it has to, measured on substance rather than length.

    `brand.storefront` already checks that the About is not thin. Length is a proxy: four
    hundred characters of atmosphere passes it. This asks whether the five things a buyer
    needs are actually in there, by looking for the vocabulary each one cannot be written
    without.
    """
    markers: dict[str, tuple[str, ...]] = {
        "what_we_make": ("pattern",),
        "how_it_is_made": ("compiler", "checks", "verified", "machine"),
        "why_it_matters": ("row", "mistake", "wrong"),
        "how_ai_is_used": ("ai",),
        "what_happens_if_it_is_wrong": ("corrected", "fix", "re-issue", "reissue"),
    }
    lowered = (text or "").lower()
    problems: list[str] = []
    for key, _why in ABOUT_SECTIONS:
        if not any(word in lowered for word in markers[key]):
            problems.append(
                f"ABOUT_MISSING_{key.upper()}: nothing in the About covers "
                f"{dict(ABOUT_SECTIONS)[key]}")
    return problems


# ---------------------------------------------------------------------------
# The checks


def check_package(terms: customer_terms.Terms | None = None) -> list[str]:
    """What would be wrong with opening this shop tomorrow, in the package's own terms.

    Each check states what it measures. None of them is about taste: an empty policy, a
    licence that does not answer the craft-fair question, a returns policy that does not say
    the word before the sale, and a disclosure that does not mention AI are all things a
    buyer or a platform notices, in that order.
    """
    decided = terms or customer_terms.BRAMBLELOOP_TERMS
    surfaces = policies(decided)
    problems: list[str] = []

    for section in POLICY_SECTIONS:
        if not surfaces.get(section, "").strip():
            problems.append(f"PACKAGE_POLICY_MISSING: {section} has no text, and a shop with "
                            f"an empty policy section is the first thing a cautious buyer "
                            f"sees")

    if "cannot be returned" not in surfaces["returns"].lower():
        problems.append(
            "PACKAGE_RETURNS_UNCLEAR: a digital pattern is non-returnable and that has to be "
            "said before the sale, not discovered after it")
    if "digital" not in surfaces["delivery"].lower():
        problems.append(
            "PACKAGE_DELIVERY_UNCLEAR: the delivery policy must say the product is a file, "
            "because 'when will it arrive' is the question it exists to answer")

    sell = decided.sentence(customer_terms.FINISHED_ITEM_SALE)
    if sell not in surfaces["licence"]:
        problems.append(
            "PACKAGE_LICENCE_SILENT_ON_SELLING: the licence does not carry the decided "
            "finished-item answer, which is the most-asked question in this market")

    entries = faq(decided)
    if entries[0]["key"] != "sell_what_i_make":
        problems.append("PACKAGE_FAQ_ORDER: the finished-item question is not first")
    for entry in entries:
        if not entry["answer"].strip():
            problems.append(f"PACKAGE_FAQ_EMPTY: {entry['key']} has no answer")
    if sell not in entries[0]["answer"]:
        problems.append(
            "PACKAGE_FAQ_DIVERGES: the FAQ answers the finished-item question in its own "
            "words rather than the decided ones, which is how three surfaces come to say "
            "three things (#40)")

    disclosure = surfaces["ai"].lower()
    if "ai" not in disclosure:
        problems.append("PACKAGE_NO_AI_DISCLOSURE: the disclosure does not mention AI")
    if "digital" not in disclosure:
        problems.append(
            "PACKAGE_DISCLOSURE_SILENT_ON_DIGITAL: the disclosure set must say no physical "
            "item is shipped, which is the misunderstanding that produces refunds")

    for claim in CLAIMS:
        if claim.basis == PRIMARY and not _source(claim.source_key).fetched:
            problems.append(f"PACKAGE_CLAIM_OVERSTATED: {claim.key} is primary and its "
                            f"source was never read")

    text = shop_text(decided)
    for key in SHOP_TEXT_FIELDS:
        if key not in text:
            problems.append(f"PACKAGE_SHOP_FIELD_MISSING: {key} is writable through Etsy's "
                            f"API and nothing here decides what to write")
    if not text["digital_sale_message"].strip():
        problems.append(
            "PACKAGE_NO_DIGITAL_SALE_MESSAGE: the message Etsy sends the instant a digital "
            "item is bought is the one surface that reaches every customer, and a blank one "
            "sends nothing at the only moment they are certainly reading")
    if sell not in text["policy_additional"]:
        problems.append(
            "PACKAGE_ADDITIONAL_POLICY_DIVERGES: policy_additional is the only policy text "
            "with a write endpoint, so it is the half that drifts from the half a person "
            "typed")

    return problems


def surface_consistency(*, pdf_text: str, listing_text: str, faq_text: str,
                        terms: customer_terms.Terms | None = None) -> dict:
    """Requirement 40's check, run against this package's own surfaces.

    Delegated to `commerce.terms.consistency` rather than reimplemented: the question is
    whether three surfaces agree with one decision, and the decision's module is the only
    place that knows what agreement means.
    """
    return customer_terms.consistency(pdf_text, listing_text, faq_text,
                                      terms or customer_terms.BRAMBLELOOP_TERMS)


def faq_text(terms: customer_terms.Terms | None = None) -> str:
    """The FAQ as one document, which is the surface #40 checks."""
    parts = [customer_terms.render(terms or customer_terms.BRAMBLELOOP_TERMS, "faq")]
    for entry in faq(terms):
        parts.append(f"{entry['question']}\n{entry['answer']}")
    return "\n\n".join(parts)


def owner_decisions() -> list[dict]:
    """The package's own list of things nobody here can decide.

    Kept separate from `launch.readiness`'s owner queue, which is about opening the shop.
    These are about what the shop *says*, and each one is here because guessing it would be
    either a legal position taken by software or a tax position taken by software.
    """
    return [
        {"key": "legal_review_of_terms",
         "what": ("have a Canadian lawyer read the customer-use terms -- finished-item "
                  "sale, teaching use, redistribution -- and record the review through "
                  "commerce.terms.record_legal_review"),
         "why": ("`Terms.enforceable` is false until somebody qualified has looked. Until "
                 "then these are terms this company offers, not protections it has"),
         "claims": ["pattern_copyright_not_the_finished_object"]},
        {"key": "gst_hst_position",
         "what": ("decide whether to register for GST/HST now or open as a small supplier, "
                  "and whether to give Etsy a GST/HST number"),
         "why": ("giving Etsy the number moves responsibility for the tax. The CA$30,000 "
                 "threshold then has to be watched, and the day it is crossed is the day "
                 "registration takes effect"),
         "claims": ["cra_small_supplier_threshold", "etsy_collects_canadian_tax"]},
        {"key": "international_vat_position",
         "what": "confirm that Etsy's VAT collection covers every market the shop sells into",
         "why": ("selling the same PDF anywhere other than Etsy later is a different tax "
                 "question with the same file"),
         "claims": ["etsy_collects_vat_on_digital", "eu_withdrawal_waived_on_consent"]},
    ]


def describe(terms: customer_terms.Terms | None = None) -> dict:
    """The whole package as data, for the readiness report and the API."""
    decided = terms or customer_terms.BRAMBLELOOP_TERMS
    return {
        "researched_on": RESEARCHED_ON,
        "max_age_days": MAX_AGE_DAYS,
        "basis_means": dict(BASIS_MEANS),
        "policies": policies(decided),
        "policy_sections": list(POLICY_SECTIONS),
        "faq": faq(decided),
        "about_sections": [{"key": k, "covers": v} for k, v in ABOUT_SECTIONS],
        "shop_text": shop_text(decided),
        "manual_only": [{"key": k, "where": v} for k, v in MANUAL_ONLY],
        "ai_disclosure": ai_disclosure(),
        "claims": [c.to_dict() for c in CLAIMS],
        "needs_professional_advice": [c.key for c in CLAIMS
                                      if c.needs_professional_advice],
        "owner_decisions": owner_decisions(),
        "terms": decided.to_dict(),
        "problems": check_package(decided),
        "note": ("Prepared and held. Nothing here has been entered into a shop, because no "
                 "shop exists. Every claim about Etsy, the CRA or EU consumer law carries "
                 "its basis and the date it was read."),
    }


def state() -> dict:
    """A one-line status for the build record, with today's date so staleness is visible."""
    age_days = (date.today() - date.fromisoformat(RESEARCHED_ON)).days
    return {"researched_on": RESEARCHED_ON, "age_days": age_days,
            "stale": age_days > MAX_AGE_DAYS,
            "claims": len(CLAIMS),
            "primary": len([c for c in CLAIMS if c.basis == PRIMARY]),
            "secondary": len([c for c in CLAIMS if c.basis == SECONDARY]),
            "inferred": len([c for c in CLAIMS if c.basis == INFERRED]),
            "problems": check_package()}
