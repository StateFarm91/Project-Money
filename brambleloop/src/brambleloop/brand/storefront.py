"""Storefront Director (Master Plan section 6).

Section 6 gives this role a specific inventory: banner, icon, About, policies, sections,
announcement, thumbnails and grid coherence. Those are the parts of a shop a customer reads
before they trust it, and on Etsy they are also the parts a new shop most obviously gets
wrong -- an empty About, no policies, and a section list invented one listing at a time.

Everything here is drafted, never published. Shadow mode means the storefront is prepared and
held, so that on the day publishing is enabled the shop opens complete rather than accreting
in public.

The policies matter beyond tidiness. A digital pattern is non-returnable, and Canadian
consumer-protection rules expect that to be disclosed plainly before purchase rather than
discovered afterwards. So the refund policy states it in the first sentence and then says
what we will actually do instead, which is fix the pattern.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..commerce import shop_package
from . import bible

SHOP_NAME = "Brambleloop Studio"

ANNOUNCEMENT_MAX = 160
ABOUT_MIN = 400


@dataclass
class Section:
    name: str
    slug: str
    categories: tuple[str, ...]


# Sections are declared up front rather than accumulated. A shop whose sections were invented
# one listing at a time reads as a stall; a shop with a stated shape reads as a studio.
SECTIONS: list[Section] = [
    Section("Blankets & Throws", "blankets", ("mosaic_blanket", "blanket", "graphghan")),
    Section("Seasonal & Holiday", "seasonal",
            ("seasonal_decor", "ornament", "stocking", "tree_skirt")),
    Section("Home & Table", "home", ("runner", "placemat", "coaster", "basket", "pillow",
                                     "wall_decor", "flower")),
    Section("Baby & Nursery", "baby", ("baby", "nursery")),
    Section("To Wear", "wear", ("garment", "hat", "scarf", "shawl", "bag")),
    Section("Collections & Bundles", "collections", ()),
]


def section_for(category: str, is_bundle: bool = False) -> str:
    if is_bundle:
        return "collections"
    for s in SECTIONS:
        if category in s.categories:
            return s.slug
    return "home"


ABOUT = f"""{SHOP_NAME} makes crochet patterns the way software gets made: written once,
then checked by a machine before anyone is asked to pay for them.

Every pattern here starts as a formal, machine-readable description of the fabric — every
stitch, every row, every colour change. A compiler then works through it row by row and
checks that the counts actually add up, that repeats divide evenly, and that what the chart
shows is what the words say. A second program reads only the finished customer pattern, with
no access to the original, and reconstructs it from scratch; if the two disagree anywhere,
the pattern does not ship.

That sounds like a strange amount of machinery for a blanket. It exists because of what goes
wrong with crochet patterns: you are thirty hours into a throw when a row stops working, and
there is no way to tell whether the mistake is yours or the designer's. We would rather spend
the effort up front than have you find out at row 94.

The designs are developed with AI assistance and the arithmetic is verified by code. Neither
of those is a substitute for the other, and we say which is which.

If something in one of our patterns does not add up, tell us. We fix the pattern itself, put
out a corrected version, and send it to everyone who bought it — rather than answering your
question and leaving the next person to find the same problem."""

# The policies are not written here any more.
#
# They were, and all five of them were prose somebody typed once. The licence was the one
# that mattered: it said "sell the items you make from it", with no limit, while
# `commerce.terms` had decided that finished items may be sold "by individual makers and
# small businesses, not manufactured at scale" and `commerce.seo`'s description block said a
# third thing. Three answers to the most-asked question in the craft-pattern market, in one
# repository, before a single sale -- which is requirement 40's drift failure, arriving
# exactly the way #40 says it arrives: written at different times by different parts of the
# system, and never read side by side.
#
# `commerce.shop_package` now renders all of them from the decisions that own them, so the
# storefront shows what was decided rather than what was remembered. The name is kept because
# the shop still has policies; what changed is where they come from.
POLICIES: dict[str, str] = shop_package.policies()

ANNOUNCEMENT_TEMPLATES: dict[str, str] = {
    "Christmas": ("Christmas blankets take real hours — this is the month to start. "
                  "Every pattern is compiler-checked row by row."),
    "Halloween": "Quick autumn makes, checked row by row before they ship.",
    "Thanksgiving (CA)": "Table pieces for the long weekend, with every stitch count verified.",
    "evergreen": ("Crochet patterns with the arithmetic checked by machine before release. "
                  "Charts and written instructions always agree."),
}


@dataclass
class Storefront:
    shop_name: str
    announcement: str
    about: str
    policies: dict[str, str]
    sections: list[dict]
    banner_brief: str
    icon_brief: str
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems

    def to_dict(self) -> dict:
        return {"shop_name": self.shop_name, "announcement": self.announcement,
                "about": self.about, "policies": dict(self.policies),
                "sections": list(self.sections), "banner_brief": self.banner_brief,
                "icon_brief": self.icon_brief, "problems": list(self.problems)}


def _banner_brief() -> str:
    return (
        f"Shop banner, 1600x400. Flat-lay of finished crochet fabric in "
        f"{bible.PALETTE['pine']} and {bible.PALETTE['cream']} on {bible.LIGHTING['background']}, "
        f"{bible.LIGHTING['direction']}. Wordmark '{SHOP_NAME.upper()}' set in "
        f"{bible.TYPOGRAPHY['display']} at left, generous space around it. No collage, no "
        f"stock gloss, nothing in the outer "
        f"{int(bible.CROP_RULES['safe_margin_pct'] * 100)}% of the frame.")


def _icon_brief() -> str:
    return (
        f"Shop icon, 500x500. A single loop-and-bramble mark in {bible.PALETTE['pine']} on "
        f"{bible.PALETTE['cream']}, centred, heavy enough to read at 40px. No text — an icon "
        f"with a shop name in it is illegible at the size it is actually shown.")


def build_storefront(season: str | None = None) -> Storefront:
    announcement = ANNOUNCEMENT_TEMPLATES.get(season or "", ANNOUNCEMENT_TEMPLATES["evergreen"])
    store = Storefront(
        shop_name=SHOP_NAME,
        announcement=announcement,
        about=ABOUT,
        policies=dict(POLICIES),
        sections=[{"name": s.name, "slug": s.slug, "categories": list(s.categories)}
                  for s in SECTIONS],
        banner_brief=_banner_brief(),
        icon_brief=_icon_brief(),
    )
    store.problems = check_storefront(store)
    return store


def check_storefront(store: Storefront) -> list[str]:
    """Everything a shopper checks before trusting a new shop, checked before they do."""
    problems: list[str] = []
    if len(store.announcement) > ANNOUNCEMENT_MAX:
        problems.append(f"STORE_ANNOUNCEMENT_TOO_LONG: {len(store.announcement)} characters")
    if not store.announcement.strip():
        problems.append("STORE_NO_ANNOUNCEMENT")
    if len(store.about) < ABOUT_MIN:
        problems.append(f"STORE_ABOUT_THIN: {len(store.about)} characters; an empty About is "
                        f"the first thing a cautious buyer notices")
    # The section list is the package's, not a copy of it. A second list is a second answer
    # to "which policies does this shop have", and the AI disclosure is exactly the section
    # a hand-maintained list forgets: it was not a policy section until Etsy made it one.
    for required in shop_package.POLICY_SECTIONS:
        if not store.policies.get(required, "").strip():
            problems.append(f"STORE_POLICY_MISSING: {required}")
    returns = store.policies.get("returns", "").lower()
    if "cannot be returned" not in returns:
        problems.append(
            "STORE_RETURNS_UNCLEAR: a digital pattern is non-returnable and that has to be "
            "said plainly before purchase, not discovered after it")
    if not store.sections:
        problems.append("STORE_NO_SECTIONS")
    slugs = [s["slug"] for s in store.sections]
    if len(slugs) != len(set(slugs)):
        problems.append("STORE_DUPLICATE_SECTIONS")
    if len(store.sections) > 20:
        problems.append(f"STORE_TOO_MANY_SECTIONS: {len(store.sections)} exceeds Etsy's 20")
    for brief, name in ((store.banner_brief, "banner"), (store.icon_brief, "icon")):
        if not brief.strip():
            problems.append(f"STORE_NO_{name.upper()}_BRIEF")
    return problems
