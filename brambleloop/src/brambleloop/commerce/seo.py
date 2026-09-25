"""Etsy listing and search draft (Master Plan sections 7, 10).

The constraint that shapes this file is that every word must be true *and* defensible from
the compiled pattern. It is trivially easy to write a listing that converts and is a lie --
"fits a queen bed", "uses only 800 m of yarn", "beginner friendly" -- and each of those is a
refund, a bad review and, under Canadian consumer-protection law, a misrepresentation.

So the draft is assembled from facts the digital twin can produce, and the Policy Gate and
Asset Truth then check it independently. Nothing here trusts itself.

Etsy's own limits are enforced structurally rather than trimmed silently: a title cut off
mid-phrase by the platform reads as carelessness on the shop's part, which is the opposite of
the premium positioning this brand is for.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..intel import childrens as ch
from . import terms as customer_terms

TITLE_MAX = 140
TAG_MAX_CHARS = 20
TAG_MAX_COUNT = 13
DESCRIPTION_MIN = 300

# Terms that make a claim the pattern data cannot support on its own.
_UNSUPPORTABLE = re.compile(
    r"\b(guaranteed|best|#1|number one|fastest|easiest|professional[- ]grade|luxury|"
    r"heirloom quality|perfect for everyone|never fails|world[- ]class)\b", re.I)


@dataclass
class ListingCopy:
    title: str
    tags: list[str]
    description: str
    materials: list[str]
    price_cad: float
    supported_claims: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"title": self.title, "tags": list(self.tags),
                "description": self.description, "materials": list(self.materials),
                "price_cad": self.price_cad,
                "supported_claims": list(self.supported_claims),
                "notes": list(self.notes)}


def _clean_tag(tag: str) -> str:
    """Normalise to Etsy's 20-character limit at a word boundary, or give up on the tag.

    A hard slice produces "mosaic blanket patte", which is not a phrase anyone searches and
    reads to a shopper as carelessness. Losing the tag entirely is better than spending one
    of thirteen scarce slots on a word fragment.
    """
    tag = re.sub(r"\s+", " ", tag.strip().lower())
    if len(tag) <= TAG_MAX_CHARS:
        return tag
    words = tag.split(" ")
    out = ""
    for word in words:
        candidate = f"{out} {word}".strip()
        if len(candidate) > TAG_MAX_CHARS:
            break
        out = candidate
    # A single surviving word is usually too generic to rank for; drop it rather than pad.
    return out if len(out.split(" ")) >= 2 else ""


def build_tags(category: str, motifs: list[str], season: str | None,
               extra: list[str] | None = None) -> list[str]:
    """Thirteen tags, deduplicated, each within Etsy's twenty-character limit.

    Multi-word phrases beat single words on Etsy because the search index matches phrases, and
    a one-word tag competes with the entire category. Tags are ordered by how specific they
    are: the most specific ones are the only ones a new shop can realistically rank for.
    """
    base = [
        f"{category.replace('_', ' ')} pattern",
        "crochet pattern pdf",
        "crochet chart pattern",
    ]
    motif_tags = [f"{m} crochet" for m in motifs[:3]] + [f"{m} pattern" for m in motifs[:2]]
    seasonal = []
    if season:
        s = season.split(" (")[0].lower()
        seasonal = [f"{s} crochet", f"{s} pattern", f"{s} gift diy"]
    tail = ["written and chart", "us and uk terms", "digital download", "crochet gift idea",
            "instant download"]

    out: list[str] = []
    for tag in motif_tags + base + seasonal + (extra or []) + tail:
        t = _clean_tag(tag)
        if t and t not in out:
            out.append(t)
        if len(out) == TAG_MAX_COUNT:
            break
    return out


def build_title(product_title: str, category: str, motifs: list[str],
                season: str | None = None, sizes: int = 1) -> str:
    """Front-load the phrase a buyer types, then qualify. Never exceed the platform limit.

    Etsy truncates in search results long before 140 characters, so the first sixty carry the
    whole job; the tail exists for the exact-phrase index, not for a human.
    """
    lead = product_title.strip()
    parts = [lead, "Crochet Pattern PDF"]
    if motifs:
        # "Pet Snuggle Mat | ... | Pet Pet | ..." shipped to production before this guard. A
        # motif word that is also the category word produces a stutter, and a stuttering title
        # is the clearest possible signal that nobody read the listing before it went up.
        motif = motifs[0].strip().lower()
        cat_words = category.replace("_", " ").lower().split()
        descriptor = " ".join(w for w in cat_words if w != motif) or cat_words[-1]
        segment = (descriptor if motif in cat_words
                   else f"{motif} {descriptor}")
        segment = segment.title()
        if segment.lower() not in lead.lower():
            parts.append(segment)
    if sizes > 1:
        parts.append(f"{sizes} Sizes")
    parts.append("Written Instructions and Chart")
    if season:
        parts.append(f"{season.split(' (')[0]} Crochet")
    parts.append("US and UK Terms")

    title = ""
    for part in parts:
        candidate = part if not title else f"{title} | {part}"
        if len(candidate) > TITLE_MAX:
            break
        title = candidate
    return title


def build_description(product_title: str, *, size_label: str | None,
                      yardage_lines: list[str], tolerance_pct: int,
                      difficulty: str, colors: list[str], terminology: str,
                      gauge_line: str | None, stitches: list[str],
                      season: str | None = None, pages: int | None = None,
                      collapsed_repeats: bool = False,
                      childrens: "ch.RenderedStatements | None" = None) -> str:
    """Assemble the description entirely from verified pattern facts.

    `terminology` is still accepted and no line depends on it any more: both documents ship, so
    the honest sentence names two files rather than one terminology. Kept in the signature
    rather than removed, because every caller passes it and the release chain still records
    which terminology a given render is.

    `childrens` is the rendered statement set from `intel.childrens`, for a product
    merchandised to a child. Left None the description carries no safety section, which is
    correct for a table runner and wrong for a baby blanket -- so a caller that has a
    children's product and does not pass it produces a listing `childrens_listing_audit`
    fails. It is an argument rather than a lookup because this module assembles copy from
    facts it is given and does not know which CIR it is describing.
    """
    out: list[str] = []
    out.append(f"{product_title} — a crochet pattern, not a finished item. You receive an "
               f"instant digital download.")
    out.append("")
    out.append("WHAT YOU GET")
    if collapsed_repeats:
        # Say what the PDF does. A buyer who is told "every single row" and opens a document
        # that stops printing rows at 48 has been misled, even though collapsing the repeat
        # is what makes the pattern usable.
        out.append("- Written instructions row by row, with a stitch count on each — the "
                   "repeated section is written once, the way a printed pattern does it, "
                   "rather than retyped for every pass")
    else:
        out.append("- Written instructions for every row, with a stitch count on each")
    out.append(f"- A colour chart generated from the same data as the written instructions, "
               f"so the two cannot disagree")
    # What actually ships, named as two files.
    #
    # This line read "{terminology} terms, with the equivalent terms listed in the stitch key"
    # and the stitch key lists one terminology's tokens -- the key is built from the rendered
    # instructions, and the instructions are rendered in one terminology. The listing title
    # says "US and UK Terms" and the release chain shipped `pattern-us.pdf` alone, so the
    # claim was unsupportable on both counts. `assets.build` now renders and stores both
    # documents and `store.publish` attaches both, so the claim is true and is stated as the
    # thing the buyer can count: two files.
    out.append(f"- Two PDFs, one in US terms and one in UK terms -- the same pattern, each "
               f"written throughout in its own terminology, with a stitch key to match")
    if pages:
        out.append(f"- {pages}-page PDF, laid out to be readable on a phone or printed")
    out.append("")
    out.append("THE DETAILS")
    if size_label:
        out.append(f"- Finished size: {size_label}, worked at the gauge below")
    if gauge_line:
        out.append(f"- Gauge: {gauge_line}")
    out.append(f"- Difficulty: {difficulty}")
    if stitches:
        out.append(f"- Stitches used: {', '.join(stitches)}")
    if colors:
        out.append(f"- Colours: {len(colors)} ({', '.join(colors)})")
    for line in yardage_lines:
        out.append(f"- {line}")
    if yardage_lines:
        out.append(f"- Yarn quantities are estimates with a +/-{tolerance_pct}% range, not "
                   f"measurements. Yarn use varies with yarn, hook and tension.")
    out.append("")
    if season:
        out.append(f"MAKING IT IN TIME FOR {season.split(' (')[0].upper()}")
        out.append("Start early. A large piece takes real hours, and the whole point of "
                   "buying the pattern now is having the weeks to make it.")
        out.append("")
    if childrens is not None:
        # Above the "how this was made" block and well above the licence, because it is a
        # suitability fact rather than a disclosure: the buyer is still deciding here.
        out.extend(childrens_listing_block(childrens))
        out.append("")
    out.append("HOW THIS PATTERN WAS MADE")
    out.append("The design was developed with AI assistance, and every stitch count was "
               "verified row by row by an automated pattern compiler before release. If "
               "anything in it does not add up, tell us: we fix the pattern itself and "
               "re-issue it, rather than only answering the question.")
    out.append("")
    # Rendered from `commerce.terms`, not written here.
    #
    # This was the third of three answers to the most-asked question in this market. The
    # decision says finished items may be sold "by individual makers and small businesses, not
    # manufactured at scale"; `brand.storefront` said "sell the items you make from it" with no
    # limit; this line said "Sell what you make", also with no limit; and the pattern PDF said
    # a fourth thing. `brand.storefront` and the PDF now render from the decision, and this is
    # the last copy. Owner ruling 2026-09-25: one conservative source, no divergent copies.
    #
    # Only the heading is this module's: the surfaces are allowed different headings and are
    # not allowed different answers, and every other section label in this description is set
    # in capitals. The body is passed through untouched, which is what `terms.consistency`
    # measures.
    rendered = customer_terms.render(customer_terms.BRAMBLELOOP_TERMS, "listing").split("\n")
    out.append(rendered[0].upper())
    out.extend(rendered[1:])
    return "\n".join(out)


# ---- the children's statements that belong in the advertisement -------------
#
# Not all of them, and the split is a decision rather than a convenience.
#
# The test is **does the buyer need this before they pay**. A statement that changes whether
# somebody buys, or what they buy it for, belongs where they decide; a statement that tells a
# maker how to work belongs in the pattern, where they work. Putting all ten in the listing
# would be the other failure: ten safety paragraphs in an advertisement is a wall nobody
# reads, and a real warning buried in nine irrelevant ones has been hidden rather than given.
#
# **What is deliberately NOT claimed here.** 15 U.S.C. 1278(c) requires the choking
# cautionary statement in any advertisement offering "a product for which a cautionary
# statement is required under subsection (a) or (b)" -- read from the statute at
# uscode.house.gov on 2026-09-25. Subsections (a) and (b) attach to a toy, game, ball, marble
# or balloon. **The product on our listing is a PDF, not a toy**, so that advertising
# requirement does not reach us, and this module does not pretend it does. The choking
# statement is in the list below because a buyer choosing a gift for a particular child needs
# it before they pay, which is our reason and not a regulator's.
LISTING_STATEMENTS: tuple[str, ...] = (
    "age_suitability", "choking_small_parts", "safe_sleep", "selling_finished_items",
)

WHY_IN_THE_LISTING: dict[str, str] = {
    "age_suitability": ("the buyer is choosing for one particular child and the age band is "
                        "the fact that decides whether this is the right pattern for them"),
    "choking_small_parts": ("where it applies at all, it is a gift-suitability fact: a buyer "
                            "shopping for a three-year-old decides at the listing"),
    "safe_sleep": ("a baby blanket is bought for a cot unless somebody says otherwise, and "
                   "the place to say otherwise is before the money, not after the download"),
    "selling_finished_items": ("a maker buying this in order to sell what they make is "
                               "taking on manufacturer obligations, and finding that out "
                               "after purchase is finding it out too late"),
}

WHY_NOT_IN_THE_LISTING: dict[str, str] = {
    "face_construction": ("an instruction about how to work the piece. It changes nothing "
                          "about whether to buy the pattern and everything about how to make "
                          "it, so it belongs in the pattern"),
    "supervision": ("about using the finished object, which the buyer of a pattern does not "
                    "yet have. It is in the pattern, next to the toy it is about"),
    "construction_integrity": ("gauge, seam and closing-round guidance: pattern content by "
                               "definition, and unreadable out of the context of the rows"),
    "fibre_and_care": ("the listing already states the yarn weight, the gauge and the "
                       "quantities; the care statement is about the finished object the "
                       "buyer has not made yet, and the ball band of the yarn they choose "
                       "governs it, not us"),
    "mobile_removal": ("about the finished mobile in a cot. It is a making-and-using fact "
                       "and it is in the pattern"),
    "not_legal_advice": ("a disclaimer over a safety reading. The listing carries an "
                         "abbreviated set, so the full reading and its disclaimer travel "
                         "together in the document rather than being split"),
}


def childrens_listing_statements(rendered: "ch.RenderedStatements") -> tuple[str, ...]:
    """Which of a product's required statements this listing carries.

    Measures: the intersection of the product's required set with `LISTING_STATEMENTS`.
    Why: computed from the obligation rather than listed per product, for the same reason
    `launch0` computes its committed set -- a hand-kept list of "the safety lines for the
    baby blanket" is a second copy of an obligation that already exists.
    """
    return tuple(k for k in rendered.required if k in LISTING_STATEMENTS)


def childrens_listing_block(rendered: "ch.RenderedStatements") -> list[str]:
    """The safety section of the listing description, in the pattern's own words.

    The text is `intel.childrens`'s, not a shortened restatement of it. Requirement 40's
    lesson applies here exactly: the licence diverged across four surfaces because each
    surface wrote its own version of one decision. A listing paraphrase of a safety statement
    is the same defect with a worse consequence, so the listing prints the sentences the
    document prints.
    """
    out: list[str] = ["SAFETY AND SUITABILITY"]
    for key in childrens_listing_statements(rendered):
        if key not in rendered.text:
            continue
        heading = rendered.headings[key]
        body = " ".join(rendered.text[key].split())
        out.append(f"- {heading}: {body}")
    out.append("The pattern itself carries the full set of safety notes for a children's "
               "item, each with its source, and states the date the guidance was compiled.")
    return out


def childrens_listing_audit(description: str,
                            rendered: "ch.RenderedStatements") -> dict:
    """Whether a finished description carries the statements a children's listing must carry.

    Measures: each statement's marker phrase against the assembled description text.
    Why: the auditor reads the artefact rather than asking the generator whether its own
    output is correct -- the discipline `commerce/friction.py` already states for this module.
    A listing assembled by hand, or by a caller that forgot to pass the statements, fails
    here rather than going up.
    """
    flat = " ".join((description or "").split())
    expected = childrens_listing_statements(rendered)
    present = [k for k in expected if ch.STATEMENT_SET[k].marker in flat]
    return {
        "expected": expected,
        "present": tuple(present),
        "missing": tuple(k for k in expected if k not in present),
        "complete": len(present) == len(expected),
        "not_in_the_listing": tuple(k for k in rendered.required
                                    if k not in LISTING_STATEMENTS),
        "why_not": {k: WHY_NOT_IN_THE_LISTING.get(k, "") for k in rendered.required
                    if k not in LISTING_STATEMENTS},
    }


def check_listing_limits(copy: ListingCopy) -> list[str]:
    """Structural problems that would make the listing invalid or misleading."""
    problems: list[str] = []
    if not copy.title.strip():
        problems.append("LISTING_NO_TITLE: a listing must have a title")
    if len(copy.title) > TITLE_MAX:
        problems.append(f"LISTING_TITLE_TOO_LONG: {len(copy.title)} > {TITLE_MAX}")
    if len(copy.tags) > TAG_MAX_COUNT:
        problems.append(f"LISTING_TOO_MANY_TAGS: {len(copy.tags)} > {TAG_MAX_COUNT}")
    for t in copy.tags:
        if len(t) > TAG_MAX_CHARS:
            problems.append(f"LISTING_TAG_TOO_LONG: {t!r} is {len(t)} characters")
    if len(copy.tags) != len(set(copy.tags)):
        problems.append("LISTING_DUPLICATE_TAGS: duplicate tags waste a scarce slot")
    if len(copy.description) < DESCRIPTION_MIN:
        problems.append(f"LISTING_DESCRIPTION_THIN: {len(copy.description)} characters")
    hit = _UNSUPPORTABLE.search(copy.title + " " + copy.description)
    if hit:
        problems.append(f"LISTING_UNSUPPORTABLE_CLAIM: {hit.group(0)!r}")
    if "pattern" not in copy.title.lower():
        problems.append("LISTING_AMBIGUOUS_PRODUCT: the title must say this is a pattern, "
                        "not a finished item")
    return problems
