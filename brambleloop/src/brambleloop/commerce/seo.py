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
                      collapsed_repeats: bool = False) -> str:
    """Assemble the description entirely from verified pattern facts.

    `terminology` is still accepted and no line depends on it any more: both documents ship, so
    the honest sentence names two files rather than one terminology. Kept in the signature
    rather than removed, because every caller passes it and the release chain still records
    which terminology a given render is.
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
