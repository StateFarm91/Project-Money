"""Store copy v2: every customer-facing word of the Brambleloop shop, in one place.

Wave-3 lane C (owner directive 2026-10-06, sections 3, 6, 7, 14 and 16). Store copy v1 led with
compilers, row checking and implementation mechanics; the owner rejected it. v2 leads with
crochet patterns people want to make, with taste, warmth and trust, and turns the reliability
work into what a maker actually gets from it: clear instructions, charts that agree with the
words, consistent terms, corrections that reach every buyer, confidence while making. The
unusual checking process is explained, truthfully, deeper in the About, after Laura and the
reason the patterns are worth making.

This module is the interface other lanes read (lane B renders the store from it):

    TAGLINE, TAGLINE_CANDIDATES, tagline_candidates()   -- the shop title and its alternatives
    BANNER                                               -- descriptor + script line + nav words
    ANNOUNCEMENT, SEASONAL_ANNOUNCEMENTS
    ABOUT, ABOUT_PARAGRAPHS, ABOUT_LAURA_INTRO, SELLER_CAPTION, LAURA_FAQ
    DELIVERY, RETURNS, PRIVACY, PRIVACY_ADDENDUM, DIGITAL_SALE_MESSAGE, SUPPORT_CONTACT
    faq_core(terms, ai_answer), faq(terms), store_disclosure()
    SECTIONS (owner nav: Home, Baby, Wearables, Gifts, Seasonal; live vs planned)
    PAGE_HEADINGS, TRUST_HEADLINE, TRUST_SIGNALS, TRUST_KINDS, VOICE_PRINCIPLES
    ABOVE_THE_FOLD, BANNED_TECHNICAL_TERMS, export()

Truth rules this copy keeps (D-FB-11..13, spec/07):
  * Laura is Brambleloop's AI founder and the face of the shop. She is always disclosed as an
    AI, never claimed to be human, never said to have crocheted, tested or photographed
    anything, and never named as the legal owner or seller of record. The shop is sold on
    Etsy by its human account holder, and the copy says so once, plainly.
  * Images are digital renderings of the finished design, never photographs, and no sample
    has been made. Said where it matters (FAQ, disclosures, About), not as the headline.
  * The licence sentences are rendered from `commerce.terms`, never paraphrased (#40).
  * The AI disclosure a listing carries is owned by `gates.platform_policy`; the FAQ answer
    "Was this designed by AI?" is that disclosure verbatim, so the shop and the listing
    cannot disagree.
  * Every string here passes `store_foundation.lint` (truth and voice). The lint is not
    weakened to make copy pass: a candidate the lint refuses is held back and reported
    (see `tagline_candidates()`), and the next lint-clean candidate is used instead.

Nothing here publishes, writes to Etsy, or contacts any network.
"""
from __future__ import annotations

from dataclasses import dataclass

VERSION = "copy_v2"
WRITTEN_ON = "2026-10-06"

SHOP_NAME = "Brambleloop Studio"
BRAND_NAME = "Brambleloop"

# ---- field limits this copy is written to -------------------------------------------------
#
# Etsy's limits come from `integrations.etsy_constraints` (lane I, read from Etsy's own help
# articles through the Help Center API, 2026-10-06; VERIFIED_HELP). If that module is absent
# the secondary figures below stand, labelled SECONDARY. The announcement has no published
# Etsy limit ("keep it short and sweet"); it is held to this shop's own 160 because a phone
# shows only its opening.
SECONDARY = "SECONDARY"
REPO_ASSERTED = "UNVERIFIED_REPO_ASSERTED"
VERIFIED_ETSY = "VERIFIED_HELP_CENTER"


@dataclass(frozen=True)
class Constraint:
    key: str
    max_chars: int
    basis: str
    source: str

    def to_dict(self) -> dict:
        return {"key": self.key, "max_chars": self.max_chars, "basis": self.basis,
                "source": self.source}


_FALLBACK: tuple[Constraint, ...] = (
    Constraint("shop_title", 55, SECONDARY,
               "https://www.outfy.com/blog/etsy-character-limit/ (search 2026-10-06)"),
    Constraint("section_name", 24, SECONDARY,
               "https://community.etsy.com/t5/Etsy-Success/Are-there-character-limitations-"
               "for-Shop-Sections/td-p/41665589 (search 2026-10-06)"),
    Constraint("about", 5000, REPO_ASSERTED, "brand.storefront.ABOUT_MAX"),
    Constraint("sections_count", 20, REPO_ASSERTED, "brand.storefront.check_storefront"),
)
_ETSY_KEYS = {"shop_title": "shop_title_max_chars", "section_name": "section_name_max_chars",
              "about": "about_max_chars", "sections_count": "sections_max"}


def _constraints() -> dict[str, Constraint]:
    out = {c.key: c for c in _FALLBACK}
    try:
        from ..integrations import etsy_constraints as ec

        for key, ekey in _ETSY_KEYS.items():
            c = ec.CONSTRAINTS.get(ekey)
            if c is not None and c.basis in ec.VERIFIED_BASES and isinstance(c.value, int):
                src = ec.SOURCES.get(c.source)
                out[key] = Constraint(key, c.value, VERIFIED_ETSY,
                                      f"integrations.etsy_constraints.{ekey}: "
                                      f"{src.url if src else c.source} -- {c.quote!r}")
    except Exception:  # noqa: BLE001 - lane I's module absent: secondary figures stand
        pass
    out["announcement"] = Constraint(
        "announcement", 160, REPO_ASSERTED,
        "brand.storefront.ANNOUNCEMENT_MAX: this shop's phone-first ceiling; Etsy publishes "
        "no number")
    out["announcement_first_sentence"] = Constraint(
        "announcement_first_sentence", 86, REPO_ASSERTED,
        "brand.storefront_preview.PHONE_ANNOUNCEMENT_CHARS (assumed phone window)")
    out["faq_answer"] = Constraint(
        "faq_answer", 1200, REPO_ASSERTED,
        "this module's own ceiling for a readable answer; Etsy publishes no FAQ limit")
    return out


CONSTRAINTS: dict[str, Constraint] = _constraints()

# ---- tagline -------------------------------------------------------------------------------
#
# The owner's brand concept (logo + banner, 2026-10-06) sets the descriptor "Crochet
# Patterns" and the line "Patterns for a More Handmade Life". The shop title is the one line
# Etsy search reads under the shop name, so the title form carries the category words
# ("crochet", "pattern") that `brand.storefront.check_shop_seo` requires.
#
# Preference order. The first candidate that passes every check below is the chosen tagline.
TAGLINE_CANDIDATES: tuple[str, ...] = (
    "Crochet patterns for a more handmade life",          # owner's line, with the category
    "Crochet patterns for a life you make by hand",       # same meaning, lint-clean wording
    "Crochet patterns worth making, clearly written",
    "Beautiful crochet patterns, written to be followed",
    "Crochet patterns for a warmer, calmer home",
)

# The banner's script line, from the owner's concept. Same selection rule; the banner already
# shows "Crochet Patterns" as its descriptor, so the line itself need not repeat it.
BANNER_LINE_CANDIDATES: tuple[str, ...] = (
    "Patterns for a More Handmade Life",                  # owner's exact line
    "For a life you make by hand",
    "Patterns worth making",
)


def _lint_findings(text: str) -> list[dict]:
    from . import lint

    return lint.lint(text, surface="copy_v2")


def _title_problems(text: str, *, needs_category: bool) -> list[str]:
    import re

    problems = [f"{f['code']}: {f['match']!r}" for f in _lint_findings(text)]
    words = re.findall(r"[a-z]+", text.lower())
    stems = {w[:-1] if w.endswith("s") and len(w) > 3 else w for w in words}
    if needs_category:
        for w in ("crochet", "pattern"):
            if w not in stems:
                problems.append(f"SEO_CATEGORY_SILENT: no {w!r}")
        lim = CONSTRAINTS["shop_title"]
        if len(text) > lim.max_chars:
            problems.append(f"TOO_LONG: {len(text)} > {lim.max_chars} ({lim.basis})")
    seen: dict[str, int] = {}
    for w in words:
        s = w[:-1] if w.endswith("s") and len(w) > 3 else w
        seen[s] = seen.get(s, 0) + 1
    rep = sorted(w for w, n in seen.items() if n > 1 and len(w) > 3)
    if rep:
        problems.append(f"REPEATED_WORD: {rep}")
    return problems


def tagline_candidates() -> list[dict]:
    """Every candidate with its problems; the chosen one is the first with none."""
    out = []
    chosen = None
    for i, t in enumerate(TAGLINE_CANDIDATES):
        p = _title_problems(t, needs_category=True)
        if not p and chosen is None:
            chosen = t
        out.append({"rank": i + 1, "text": t, "chars": len(t), "problems": p,
                    "owner_concept": i == 0, "chosen": False})
    for row in out:
        row["chosen"] = row["text"] == chosen
    return out


def banner_line_candidates() -> list[dict]:
    out = []
    chosen = None
    for i, t in enumerate(BANNER_LINE_CANDIDATES):
        p = _title_problems(t, needs_category=False)
        if not p and chosen is None:
            chosen = t
        out.append({"rank": i + 1, "text": t, "problems": p, "owner_concept": i == 0,
                    "chosen": False})
    for row in out:
        row["chosen"] = row["text"] == chosen
    return out


def _chosen(rows: list[dict]) -> str:
    for r in rows:
        if r["chosen"]:
            return r["text"]
    raise RuntimeError("copy_v2: no candidate passes the lint; a tagline is never forced "
                       f"through a refused rule: {rows}")


TAGLINE: str = _chosen(tagline_candidates())

# Lint finding the integrator should know about: the owner's line is truthful (the
# "handmade life" is the customer's, made with the pattern), but TRUTH_PHYSICAL_MAKING's
# `hand[- ]?made` alternative refuses it because Brambleloop itself makes nothing by hand.
# The rule is not weakened here; the next candidate is used and the case is reported in the
# lane C handoff for a narrowly scoped rule decision.
LINT_MISFIRES: tuple[dict, ...] = (
    {"text": "Patterns for a More Handmade Life", "rule": "TRUTH_PHYSICAL_MAKING",
     "why_truthful": ("'handmade' describes the maker's life and the items the customer makes "
                      "with the pattern, not a claim that Brambleloop hand-makes anything"),
     "proposal": ("allow 'handmade' only in the fixed phrases 'handmade life' / 'more handmade' "
                  "/ 'handmade home', keeping every seller-made reading refused; integrator "
                  "decision, not applied by lane C")},
)

BANNER: dict = {
    "wordmark": BRAND_NAME,
    "descriptor": "Crochet Patterns",
    "line": _chosen(banner_line_candidates()),
    "owner_line": BANNER_LINE_CANDIDATES[0],
    "nav": ("Home", "Baby", "Wearables", "Gifts", "Seasonal"),
    "nav_note": ("the owner's nav order; only Home and Baby hold Launch-0 patterns today, so a "
                 "live banner shows only the populated words or the nav is presented as "
                 "'coming' -- see SECTIONS"),
}

# ---- announcement ---------------------------------------------------------------------------

ANNOUNCEMENT = ("Welcome to Brambleloop. Calm, beautiful crochet patterns for home and "
                "nursery, written clearly, with free corrections for every buyer.")

# Drafts for a seasonal takeover. Shown only when the takeover is applied and its products
# exist (brand.takeover decides); until then the evergreen line stands.
SEASONAL_ANNOUNCEMENTS: dict[str, str] = {
    "Christmas": ("Start your holiday making early. Cosy crochet patterns for home and "
                  "nursery, written clearly, with free corrections."),
    "Halloween": ("Quick autumn makes for slow evenings. Crochet patterns with clear "
                  "instructions and charts you can rely on."),
    "Thanksgiving (CA)": ("Pieces for the long-weekend table. Crochet coasters and baskets "
                          "with clear, row-by-row instructions."),
    "evergreen": ANNOUNCEMENT,
}

# ---- Laura -----------------------------------------------------------------------------------

SELLER_CAPTION = "Laura · Brambleloop's AI founder"

# Where Laura appears, and where she must not (Etsy help 115015651948 and 360000336867, via
# integrations.etsy_constraints): the account profile picture is the signed-in account
# holder's own, and a shop-team "Owner" is the real person responsible for the account. Laura
# is neither. She is the brand face in the banner, the About story and seasonal creative,
# always with her AI disclosure; her portrait is used only once it passes the publication gate.
LAURA_PLACEMENT: dict[str, str] = {
    "banner": "yes, as the brand face, when a publication-approved image exists",
    "about_story": "yes: About paragraph 2, ABOUT_LAURA_INTRO, the 'Meet Laura' heading",
    "about_photos": "yes, captioned with SELLER_CAPTION, once publication-approved",
    "seasonal": "yes, same canonical Laura",
    "account_profile_photo": "no: it presents the persona as the account holder",
    "shop_team_owner_role": "no: Etsy's Owner role is the real responsible owner",
    "listing_thumbnails": "product first; Laura only where it is commercially stronger",
}

ABOUT_LAURA_INTRO = ("Laura is Brambleloop's AI founder and the face of this shop. She is an "
                     "AI, not a human, and every pattern she puts her name to is checked row "
                     "by row before it reaches you.")

LAURA_FAQ = {
    "key": "who_is_laura",
    "question": "Who is Laura?",
    "answer": ("Laura is Brambleloop's AI founder and the face of the studio. She is an AI, "
               "not a human: she has not crocheted these pieces, and her portrait is a "
               "generated image, not a photograph. The shop is sold on Etsy by its human "
               "account holder, who is responsible for every order and every promise made "
               "here."),
}

# ---- About ------------------------------------------------------------------------------------
#
# Order is the argument: what we make and why it is worth making; Laura; what the maker gets;
# then, deeper, how that is earned; then the plain truths (AI, renders, no sample); then the
# promise that costs something to keep; then who is responsible and how to reach us.
ABOUT_PARAGRAPHS: tuple[str, ...] = (
    ("Brambleloop Studio makes crochet patterns for the pieces you want around you: a soft "
     "blanket for a new baby, baskets that bring a little order to a shelf, small things for "
     "the table that make a room feel cared for. Quiet colours, natural textures and shapes "
     "meant to be lived with, not just admired."),
    ("Brambleloop is Laura's studio. Laura is its AI founder and the face you will see here. "
     "She is an AI, not a human, and she will never pretend otherwise; what she holds every "
     "pattern to is the standard below."),
    ("A pattern should be a pleasure to follow. Each one is written in plain, consistent "
     "language, with a chart that says exactly what the words say, the hook, yarn weight "
     "and gauge stated up front, and every stitch named before you begin. Each pattern "
     "comes as two complete PDFs, one in US terms and one in UK terms, so you never have to "
     "translate in your head."),
    ("Behind that is an unusual amount of checking. Every design is drawn up stitch by stitch "
     "before a word of the pattern is written, and the arithmetic of every row is verified "
     "before release: the counts add up, the repeats divide evenly, and the chart matches the "
     "text. Then a separate check reads only the finished pattern, the way you will, and "
     "rebuilds the design from it. If the two disagree anywhere, the pattern is not released. "
     "It exists for one reason: so you never reach row 94 of a blanket and wonder whether "
     "the mistake is yours."),
    ("The designs are developed with AI, and the arithmetic is verified by code; neither "
     "replaces the other. The pictures are digital renderings of each finished design, not "
     "photographs. No sample has been photographed, and we have not yet worked a physical "
     "sample, so make a gauge swatch first: your yarn, hook and tension decide the finished "
     "size."),
    ("If something in a pattern does not add up, tell us. We correct the pattern itself and "
     "send the corrected file to everyone who bought it, so the next maker never meets the "
     "same problem."),
    ("Brambleloop Studio is sold on Etsy by the human holder of this shop account, who is "
     "responsible for every order. What you may make, sell, print and teach from a pattern "
     "is set out in the FAQ, and questions come to us through Etsy Messages."),
)

ABOUT = "\n\n".join(ABOUT_PARAGRAPHS)

# ---- policies ------------------------------------------------------------------------------

DELIVERY = (
    "Every pattern here is a digital file, so there is no processing time and nothing is "
    "posted. As soon as your payment clears, your PDFs are waiting in your Etsy account under "
    "Purchases and downloads, and Etsy emails you a link as well. They read comfortably on a "
    "phone or tablet and print cleanly on paper. If a download will not start or a file will "
    "not open, message us and we will get it to you.")

RETURNS = (
    "Digital patterns cannot be returned, and Etsy does not allow a seller to accept a return "
    "on a digital listing; we would rather you knew that before you buy. Here is what we do "
    "instead. If a pattern contains an error, we correct the pattern itself and send the "
    "corrected file to everyone who bought it. If you cannot open or download your file, we "
    "will get it to you. If a pattern is not what the listing led you to expect, tell us: "
    "that is our listing to fix, and we will make it right with you.")

PRIVACY = (
    "We only see what Etsy shares with us to fulfil your order. We do not sell or share your "
    "information, and buying a pattern never puts you on a mailing list. We only email people "
    "who asked us to, and every email can be stopped with one click.")

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


def digital_sale_message(terms=None) -> str:
    """The note Etsy sends the moment a pattern is bought.

    v1 said "You may sell the items you make from this pattern" with no limit, which is the
    drift #40 forbids: the decided sentence limits sale to individual makers and small
    businesses. v2 quotes the decided sentence.
    """
    from ..commerce import terms as customer_terms

    decided = terms or customer_terms.BRAMBLELOOP_TERMS
    sell = decided.sentence(customer_terms.FINISHED_ITEM_SALE)
    return (
        "Thank you, and happy making. Your pattern is ready now: open your Etsy account, go "
        "to Purchases and downloads, and both PDFs (US and UK terms) are there. Etsy has "
        "emailed you a link as well.\n\n"
        f"Two things worth knowing. Under our pattern terms, {sell}. And if anything in the "
        "pattern does not add up, reply to this message with the pattern name and the row "
        "number: we correct the pattern itself and send the corrected file to everyone who "
        "bought it, including you.")


DIGITAL_SALE_MESSAGE = digital_sale_message()

# ---- FAQ -----------------------------------------------------------------------------------

FAQ_ORDER: tuple[str, ...] = (
    "sell_what_i_make", "is_it_a_finished_item", "where_is_my_file", "can_i_print_it",
    "can_i_teach_from_it", "us_or_uk_terms", "what_if_there_is_a_mistake",
    "can_i_get_a_refund", "was_ai_used", "do_you_ship",
)


def faq_core(terms=None, ai_answer: str | None = None) -> list[dict]:
    """The ten core answers, licence answers quoted from `commerce.terms` verbatim.

    `ai_answer` is the gate-owned AI disclosure (`commerce.shop_package.ai_disclosure`),
    passed in so this module never writes a second, friendlier version of it.
    """
    from ..commerce import terms as customer_terms

    decided = terms or customer_terms.BRAMBLELOOP_TERMS
    sell = decided.sentence(customer_terms.FINISHED_ITEM_SALE)
    use = decided.sentence(customer_terms.PDF_USE)
    share = decided.sentence(customer_terms.REDISTRIBUTION)
    support = decided.sentence(customer_terms.SUPPORT_POLICY)
    versions = decided.sentence(customer_terms.VERSION_POLICY)
    if ai_answer is None:
        from ..gates import platform_policy

        ai_answer = "\n".join([platform_policy.DISCLOSURES["digital_download"],
                               platform_policy.DISCLOSURES["ai_assisted_design"],
                               platform_policy.DISCLOSURES["deterministic_render"]])
    answers: dict[str, tuple[str, str]] = {
        "sell_what_i_make": (
            "Can I sell what I make from this pattern?",
            f"Yes: {sell}. You do not owe us a percentage and you do not need to ask. What "
            f"you may not do is pass on the pattern itself: {share}."),
        "is_it_a_finished_item": (
            "Am I buying a finished piece or a pattern?",
            "A pattern. You receive the instructions and chart as PDFs and make the piece "
            "yourself, in your own yarn. Nothing is shipped."),
        "where_is_my_file": (
            "Where is my file?",
            "In your Etsy account under Purchases and downloads, as soon as your payment "
            "clears. Etsy also emails you a link. If neither works, message us and we will "
            "get it to you."),
        "can_i_print_it": (
            "Can I print it?",
            f"Yes, as often as you like. The pattern is {use}."),
        "can_i_teach_from_it": (
            "Can I teach a class from it?",
            f"Yes, on one condition from our terms: the pattern is {use}. Each participant "
            f"needs their own copy."),
        "us_or_uk_terms": (
            "US or UK crochet terms?",
            "Both. Every pattern comes as two complete PDFs, one written throughout in US "
            "terms and one in UK terms, each with its own stitch key, so you never have to "
            "translate in your head."),
        "what_if_there_is_a_mistake": (
            "What if I find a mistake?",
            f"Tell us the pattern and the row. {support[0].upper() + support[1:]}. If the "
            f"pattern is wrong we fix the pattern, not just your copy: {versions}."),
        "can_i_get_a_refund": (
            "Can I get a refund?",
            "Digital patterns cannot be returned, and Etsy does not allow a seller to accept "
            "a return on a digital listing. If something is wrong (a file that will not "
            "open, an error in the pattern, a listing that misled you), message us and we "
            "will put it right."),
        "was_ai_used": ("Was this designed with AI?", ai_answer),
        "do_you_ship": (
            "Do you ship internationally?",
            "There is nothing to ship. A digital pattern is the same file everywhere, and any "
            "tax due is handled by Etsy at checkout."),
    }
    return [{"key": k, "question": answers[k][0], "answer": answers[k][1]} for k in FAQ_ORDER]


def faq_extra() -> list[dict]:
    """The questions a careful first buyer asks of a new shop, answered truthfully."""
    from ..gates import platform_policy

    return [
        {"key": "skill_level", "question": "What skill level do I need?",
         "answer": ("Each listing states a difficulty and names every stitch the pattern "
                    "uses, with the hook size and gauge, so you can judge before you buy. "
                    "If you are unsure, message us and we will tell you honestly.")},
        {"key": "are_images_photos", "question": "Are the pictures photographs?",
         "answer": platform_policy.DISCLOSURES["disclosed_render"]},
        {"key": "sample_made", "question": "Has this pattern been made up in yarn?",
         "answer": ("Not yet by us. Every row's stitch count is checked and the finished "
                    "sizes are calculated from the stated gauge, but we have not yet worked a "
                    "physical sample of these designs. Your finished size will vary with "
                    "yarn, hook and tension, so make a gauge swatch first.")},
        dict(LAURA_FAQ),
        {"key": "contact", "question": "How do I reach you?", "answer": SUPPORT_CONTACT},
    ]


def faq(terms=None, ai_answer: str | None = None) -> list[dict]:
    """The full store FAQ: the core answers, then the first-purchase questions."""
    return faq_core(terms, ai_answer) + faq_extra()


# ---- disclosures (store level) -------------------------------------------------------------


def store_disclosure() -> str:
    """The shop's disclosure block: proportionate, complete, and in the gate's own words.

    Carries the gate-owned digital, AI and render sentences verbatim (a listing and the shop
    must not disagree), plus the two store-level truths no gate owned: who Laura is, and who
    is responsible for the shop.
    """
    from ..gates import platform_policy

    d = platform_policy.DISCLOSURES
    return "\n".join([
        d["digital_download"],
        d["ai_assisted_design"],
        d["deterministic_render"],
        d["disclosed_render"],
        ("Laura, the face of this shop, is Brambleloop's AI founder. She is an AI, not a "
         "human, and her portrait is a generated image, not a photograph."),
        ("The shop is sold on Etsy by its human account holder, who is responsible for every "
         "order."),
    ])


# ---- sections ------------------------------------------------------------------------------
#
# The owner's nav (HOME · BABY · WEARABLES · GIFTS · SEASONAL), mapped onto the shop's
# section slugs (`brand.storefront.SECTIONS`, read-only here). Only sections holding a
# Launch-0 pattern go live; the rest are PLANNED and are never shown as empty shelves, which
# would imply products the shop does not have.


@dataclass(frozen=True)
class SectionCopy:
    slug: str            # brand.storefront section slug (or a planned new one)
    name: str            # the Etsy section name
    blurb: str           # one line for the shop home / section header
    order: int
    planned_note: str = ""

    def to_dict(self) -> dict:
        return {"slug": self.slug, "name": self.name, "blurb": self.blurb,
                "order": self.order, "planned_note": self.planned_note}


SECTIONS: tuple[SectionCopy, ...] = (
    SectionCopy("home", "Home", "Baskets, coasters and quiet pieces for every room.", 1),
    SectionCopy("baby", "Baby", "Soft, simple patterns for the nursery.", 2),
    SectionCopy("wear", "Wearables", "Pieces to wear, when the patterns are ready.", 3,
                "planned: no wearable pattern in Launch-0"),
    SectionCopy("collections", "Gifts", "Sets and pieces made for giving.", 4,
                "planned: maps the shop's bundles/collections slug; no bundle in Launch-0"),
    SectionCopy("seasonal", "Seasonal", "Patterns for the season, as each one arrives.", 5,
                "planned: no seasonal pattern in Launch-0"),
    SectionCopy("blankets", "Blankets", "Throws and blankets worth the hours.", 6,
                "planned, and not in the owner's nav: a blanket section is proposed for when "
                "throws launch; baby blankets stay in Baby"),
)

SECTION_BY_SLUG: dict[str, SectionCopy] = {s.slug: s for s in SECTIONS}


def section_name(slug: str) -> str:
    s = SECTION_BY_SLUG.get(slug)
    return s.name if s else slug


# ---- page headings and trust ---------------------------------------------------------------

PAGE_HEADINGS: dict[str, str] = {
    "shop": "The patterns",
    "laura": "Meet Laura",
    "about": "About Brambleloop",
    "promise": "Made to be followed",
    "faq": "Questions",
    "policies": "Policies",
    "support": "Questions and support",
    "seasonal": "For the season",
    "new_shop": "A new shop, with no reviews yet",
}

TRUST_HEADLINE = "Made to be followed, from the first stitch to the last row."

TRUST_KINDS = ("verified_process", "policy_commitment", "platform_fact")


@dataclass(frozen=True)
class TrustSignal:
    key: str
    text: str
    kind: str
    evidence: tuple[str, ...]
    note: str = ""

    def to_dict(self) -> dict:
        return {"key": self.key, "text": self.text, "kind": self.kind,
                "evidence": list(self.evidence), "note": self.note}


# Customer value first; each still has a mechanism or decision behind it (evidence paths).
TRUST_SIGNALS: tuple[TrustSignal, ...] = (
    TrustSignal("compiler_checked", "Clear instructions, checked row by row before release",
                "verified_process",
                ("src/brambleloop/cir/compiler.py", "src/brambleloop/gates/certificate.py")),
    TrustSignal("reverse_checked", "Charts that say exactly what the words say",
                "verified_process", ("src/brambleloop/cir/reverse.py",)),
    TrustSignal("us_uk", "US and UK terms, each a complete PDF", "verified_process",
                ("src/brambleloop/publish/pdf.py",), "publish.pdf.TERMINOLOGIES"),
    TrustSignal("corrections", "Free corrections, sent to everyone who bought the pattern",
                "policy_commitment", ("src/brambleloop/commerce/terms.py",),
                "terms.VERSION_POLICY"),
    TrustSignal("licence", "Sell what you make, by hand or in small batches",
                "policy_commitment", ("src/brambleloop/commerce/terms.py",),
                "terms.FINISHED_ITEM_SALE: individual makers and small businesses, not "
                "manufactured at scale"),
    TrustSignal("renders_labelled", "Every picture labelled as a rendering, never a photo",
                "verified_process", ("src/brambleloop/publish/disclosed_listing.py",)),
    TrustSignal("instant", "Instant PDF download through Etsy", "platform_fact",
                ("src/brambleloop/commerce/shop_package.py",)),
    TrustSignal("answers", "Questions answered against the exact version you bought",
                "policy_commitment", ("src/brambleloop/commerce/terms.py",),
                "terms.SUPPORT_POLICY"),
)

VOICE_PRINCIPLES = (
    "Lead with the piece and the pleasure of making it; reliability is the reason to trust it.",
    "Warm and calm: no exclamation marks, no emoji, no capitals for emphasis.",
    "Specific about what a maker gets: clear instructions, charts that agree, both US and UK "
    "terms, free corrections.",
    "Plain about limits, in their place: renders not photographs, no worked sample, Laura is "
    "an AI.",
    "No borrowed credibility: no superlatives, counts, endorsements or invented history.",
    "No machinery in the shop window: methods are explained in the About, never sold as the "
    "headline.",
)

# ---- what a buyer sees first, and what must never be in it ---------------------------------

# Words that read as a software project in the shop window. Banned from above-the-fold copy;
# the first group is banned from all customer copy in this module.
BANNED_EVERYWHERE: tuple[str, ...] = (
    "compiler", "compiled", "cir", "llm", "claude", "anthropic", "openai", "gpt", "gemini",
    "codex", "fable", "agent", "agents", "pipeline", "deterministic", "machine-readable",
    "machine readable", "algorithm", "neural", "prompt", "autonomous",
)
BANNED_TECHNICAL_TERMS: tuple[str, ...] = BANNED_EVERYWHERE + (
    "machine", "software", "code", "verified by", "formal", "validator", "ai-generated",
    "model",
)


def above_the_fold() -> dict[str, str]:
    """The copy a buyer meets before scrolling: banner, title, announcement, first lines."""
    out = {
        "tagline": TAGLINE,
        "announcement": ANNOUNCEMENT,
        "banner_descriptor": BANNER["descriptor"],
        "banner_line": BANNER["line"],
        "about_opening": ABOUT_PARAGRAPHS[0],
        "trust_headline": TRUST_HEADLINE,
    }
    for s in SECTIONS:
        out[f"section:{s.slug}"] = s.name
        out[f"section_blurb:{s.slug}"] = s.blurb
    for t in TRUST_SIGNALS:
        out[f"trust:{t.key}"] = t.text
    for k, v in SEASONAL_ANNOUNCEMENTS.items():
        out[f"announcement:{k}"] = v
    return out


ABOVE_THE_FOLD: dict[str, str] = above_the_fold()


def customer_copy() -> dict[str, str]:
    """Every customer-facing string in this module, keyed, for the lints and tests."""
    out = dict(ABOVE_THE_FOLD)
    out.update({
        "seller_caption": SELLER_CAPTION, "about_laura_intro": ABOUT_LAURA_INTRO,
        "about": ABOUT, "delivery": DELIVERY, "returns": RETURNS, "privacy": PRIVACY,
        "privacy_addendum": PRIVACY_ADDENDUM, "support_contact": SUPPORT_CONTACT,
        "digital_sale_message": DIGITAL_SALE_MESSAGE, "store_disclosure": store_disclosure(),
    })
    for k, v in PAGE_HEADINGS.items():
        out[f"heading:{k}"] = v
    for f in faq():
        out[f"faq_q:{f['key']}"] = f["question"]
        out[f"faq_a:{f['key']}"] = f["answer"]
    return out


def export() -> dict:
    """The whole copy set as JSON-serialisable data (lane B and the Command Center read this)."""
    return {
        "version": VERSION, "written_on": WRITTEN_ON, "shop_name": SHOP_NAME,
        "tagline": TAGLINE, "tagline_candidates": tagline_candidates(),
        "banner": {**BANNER, "nav": list(BANNER["nav"]),
                   "line_candidates": banner_line_candidates()},
        "announcement": ANNOUNCEMENT, "seasonal_announcements": dict(SEASONAL_ANNOUNCEMENTS),
        "seller_caption": SELLER_CAPTION, "about_laura_intro": ABOUT_LAURA_INTRO,
        "about": ABOUT, "about_paragraphs": list(ABOUT_PARAGRAPHS),
        "policies": {"delivery": DELIVERY, "returns": RETURNS, "privacy": PRIVACY,
                     "privacy_addendum": PRIVACY_ADDENDUM},
        "digital_sale_message": DIGITAL_SALE_MESSAGE, "support_contact": SUPPORT_CONTACT,
        "faq": faq(), "store_disclosure": store_disclosure(),
        "sections": [s.to_dict() for s in SECTIONS],
        "page_headings": dict(PAGE_HEADINGS), "trust_headline": TRUST_HEADLINE,
        "trust_signals": [t.to_dict() for t in TRUST_SIGNALS],
        "voice": list(VOICE_PRINCIPLES), "constraints": {k: c.to_dict()
                                                         for k, c in CONSTRAINTS.items()},
        "lint_misfires": [dict(m) for m in LINT_MISFIRES],
        "laura_placement": dict(LAURA_PLACEMENT),
        "above_the_fold_keys": sorted(ABOVE_THE_FOLD),
    }
