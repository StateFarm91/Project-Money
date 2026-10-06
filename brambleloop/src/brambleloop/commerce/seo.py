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


# F-023: Etsy's own guidance is a concise title of roughly fifteen words. A readability target,
# not a ranking law, so exceeding it is a recorded soft finding rather than a block, and
# `build_title` meets it by dropping its lowest-value tail segments first.
TITLE_WORD_TARGET = 15

# F-024: empty subjective claims. They spend scarce title words on nothing a buyer searches
# for and nothing the pattern data can support, so they are moved to the description (which
# opens with the product name and so keeps them) rather than deleted from the product.
_SUBJECTIVE = re.compile(
    r"\b(cute|beautiful|gorgeous|stunning|lovely|adorable|perfect|amazing|"
    r"elegant|charming|unique|pretty|dreamy|delightful|exquisite)\b", re.I)

_TITLE_WORD = re.compile(r"[a-z0-9]+")


def _title_words(text: str) -> list[str]:
    return _TITLE_WORD.findall(text.lower())


def relocate_subjective(text: str) -> tuple[str, list[str]]:
    """The text with subjective words removed, and the words that were moved (F-024)."""
    moved = [m.group(0) for m in _SUBJECTIVE.finditer(text or "")]
    clean = re.sub(r"\s{2,}", " ", _SUBJECTIVE.sub("", text or "")).strip(" -|,")
    return clean, moved


# F-022: the characters a phone's search grid and a truncated result reliably show. The
# item-defining phrase and the strongest differentiator must both land inside them.
FRONT_SCAN_CHARS = 60


def _title_candidates(category: str, motifs: list[str], season: str | None,
                      sizes: int) -> list[tuple[int, int, str]]:
    """(priority, canonical position, text) for every qualifying title segment."""
    candidates: list[tuple[int, int, str]] = []
    if motifs:
        # "Pet Snuggle Mat | ... | Pet Pet | ..." shipped to production before this guard.
        motif = motifs[0].strip().lower()
        cat_words = category.replace("_", " ").lower().split()
        descriptor = " ".join(w for w in cat_words if w != motif) or cat_words[-1]
        segment = (descriptor if motif in cat_words else f"{motif} {descriptor}").title()
        candidates.append((2, 2, segment))
    if season:
        candidates.append((1, 5, season.split(" (")[0]))
    if sizes > 1:
        candidates.append((3, 3, f"{sizes} Sizes"))
    candidates.append((4, 6, "US and UK Terms"))
    candidates.append((5, 4, "Written Instructions and Chart"))
    return candidates


# Segments every listing carries; never a differentiator, because every listing has them.
_COMMON_SEGMENTS = frozenset({"US and UK Terms", "Written Instructions and Chart"})


def front_scan(title: str, *, differentiator: str | None) -> dict:
    """Whether the item-defining language and the differentiator are early enough (F-022).

    Item-defining language is "crochet pattern": the phrase that tells a shopper what is sold.
    The differentiator is the segment `build_title` chose as this product's strongest; when
    there is none (a plain listing), only the item phrase is required.
    """
    head = (title or "")[:FRONT_SCAN_CHARS].lower()
    problems: list[str] = []
    if "crochet pattern" not in head:
        problems.append(f"TITLE_FRONT_SCAN_ITEM: 'crochet pattern' is not in the first "
                        f"{FRONT_SCAN_CHARS} characters")
    # A differentiator is early when it *starts* inside the window: a truncated result shows
    # its first word, and the first word is the one that differentiates.
    marks = [w for w in _title_words(differentiator or "") if len(w) > 3 or w.isdigit()]
    lowered = (title or "").lower()
    starts = [m.start() for w in marks for m in re.finditer(rf"\b{re.escape(w)}\b", lowered)]
    if differentiator and marks and not (starts and min(starts) < FRONT_SCAN_CHARS):
        problems.append(f"TITLE_FRONT_SCAN_DIFFERENTIATOR: {differentiator!r} is not in the "
                        f"first {FRONT_SCAN_CHARS} characters")
    return {"ok": not problems, "problems": problems, "head": (title or "")[:FRONT_SCAN_CHARS],
            "differentiator": differentiator}


def title_differentiator(product_title: str, category: str, motifs: list[str],
                         season: str | None = None, sizes: int = 1) -> str | None:
    """The strongest segment `build_title` will place directly after the item phrase.

    The highest-priority qualifying segment that adds a word the lead does not already say --
    a season, else the motif, else the size count. The common deliverable segments are never
    differentiators.
    """
    lead, _moved = relocate_subjective(product_title.strip())
    used = set(_title_words(lead)) | {"crochet", "pattern", "pdf"}
    for _prio, _pos, text in sorted(_title_candidates(category, motifs, season, sizes)):
        if text in _COMMON_SEGMENTS:
            continue
        fresh = [t for t in _title_words(text) if t not in used and len(t) > 3]
        if fresh or (text.endswith("Sizes") and "sizes" not in used):
            return text
    return None


def build_title(product_title: str, category: str, motifs: list[str],
                season: str | None = None, sizes: int = 1) -> str:
    """Front-load the phrase a buyer types, then qualify. Never repeat a word.

    Etsy truncates in search results long before 140 characters, so the first sixty carry the
    whole job. Every segment after the product name only adds words the title does not already
    contain (F-021, F-245): "Nordic Forest Mosaic Throw | ... | Nordic Mosaic Blanket |
    Christmas Crochet" repeated three words, which `portfolio.stuffing` reads as stuffing and
    which a buyer reads as a listing nobody proofread. Segments are kept in priority order
    until the fifteen-word target (F-023) would be passed, so the tail goes first.
    """
    lead, _moved = relocate_subjective(product_title.strip())
    fmt = ["Crochet", "Pattern", "PDF"]
    fmt_words = {w.lower() for w in fmt}
    # "Crochet Storage Basket | Pattern PDF" would break the "crochet pattern" phrase the
    # friction audit and every buyer look for; the lead gives up the word instead.
    trimmed = " ".join(w for w in lead.split() if w.lower() not in fmt_words)
    lead = trimmed or lead
    used = set(_title_words(lead)) | fmt_words

    def fresh(text: str) -> str:
        # Only content words count as repeats -- the same rule `portfolio.stuffing` applies
        # (longer than three letters) -- so "US and UK Terms" keeps its "and".
        kept = [w for w in text.split()
                if not {t for t in _title_words(w) if len(t) > 3} <= used
                or all(len(t) <= 3 for t in _title_words(w))]
        return " ".join(kept) if any(t not in used
                                     for w in kept for t in _title_words(w)) else ""

    # (priority, canonical position, text). Lower priority number is kept first.
    # F-022: the strongest differentiator moves to the slot directly after the item phrase,
    # so it survives mobile truncation; everything else keeps its canonical order.
    strongest = title_differentiator(product_title, category, motifs, season, sizes)
    candidates = [(prio, (1 if text == strongest else pos), text)
                  for prio, pos, text in _title_candidates(category, motifs, season, sizes)]

    kept: list[tuple[float, str]] = [(0, lead), (0.5, " ".join(fmt))]
    words = len(_title_words(lead)) + len(fmt)
    for _prio, position, text in sorted(candidates):
        segment = fresh(text)
        if not segment:
            continue
        n = len(_title_words(segment))
        if words + n > TITLE_WORD_TARGET:
            continue
        kept.append((position, segment))
        used |= set(_title_words(segment))
        words += n

    title = ""
    for _position, part in sorted(kept, key=lambda x: x[0]):
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
                      childrens: "ch.RenderedStatements | None" = None,
                      key_phrases: list[str] | None = None,
                      lesson_links: list[dict] | None = None,
                      why_it_matters: str | None = None,
                      yarn_lines: list[str] | None = None) -> str:
    """Assemble the description entirely from verified pattern facts.

    `lesson_links` is `learn.service.listing_help_links(db, cir)` (F-808): approved,
    revision-bound lessons on the owned Learn origin. Empty -- and no section printed --
    until that origin is configured; only entries carrying an absolute https `url` print.

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
    # F-255: the first line says what is sold and why it matters. The value sentence rides
    # on the same line so the key-phrase sentence (F-025) stays in the first two lines.
    lead = (f"{product_title} — a crochet pattern, not a finished item. You receive an "
            f"instant digital download.")
    if why_it_matters and why_it_matters.strip():
        lead = f"{lead} {why_it_matters.strip()}"
    out.append(lead)
    opening = opening_sentence(key_phrases or [])
    if opening:
        # F-025: the listing's most important phrases, placed naturally in the first lines
        # rather than restating the title. Chosen by the caller from the tags it spent slots
        # on, so the description and the tags answer the same queries.
        out.append(opening)
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
    out.append(f"- Two PDFs, one in US terms and one in UK terms — the same pattern, each "
               f"written throughout in its own terminology, with a stitch key to match")
    if pages:
        out.append(f"- {pages}-page PDF, laid out to be readable on a phone or printed")
    out.append("")
    out.append("THE DETAILS")
    if size_label:
        out.append(f"- Finished size: {size_label}, worked at the gauge below")
    out.append(f"- Difficulty: {difficulty}")
    # F-255: materials before gauge -- the yarn (and its fibre where the pattern states it)
    # is what a buyer has to go and buy, and the hook is on the gauge line.
    for line in (yarn_lines or []):
        out.append(f"- {line}")
    if gauge_line:
        out.append(f"- Gauge: {gauge_line}")
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
    help_urls = [link["url"] for link in (lesson_links or [])
                 if str(link.get("url", "")).startswith("https://")]
    if help_urls:
        out.append("TECHNIQUE HELP")
        out.extend(f"- {u}" for u in help_urls)
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


def value_proposition(*, sizes: int = 1, difficulty: str | None = None,
                      colours: int = 0) -> str:
    """Why this pattern is worth buying, from facts the pattern holds (F-255).

    Every clause is a fact the release already verifies -- the size count, the colour count,
    the printed difficulty and the written-plus-charted deliverable -- so the value sentence
    can never promise what the pattern does not do.
    """
    parts: list[str] = []
    if sizes > 1:
        parts.append(f"{sizes} sizes in one pattern")
    if colours == 1:
        parts.append("worked in a single colour")
    elif colours > 1:
        parts.append(f"worked in {colours} colours")
    if difficulty:
        parts.append(f"written for a {difficulty.lower()} maker")
    parts.append("every row written out and charted, so you can follow whichever you prefer")
    return "Why it is worth making: " + ", ".join(parts) + "."


def yarn_lines(materials: list) -> list[str]:
    """The yarn and fibre lines for a description, from the CIR's materials (F-255).

    The fibre is printed only as the pattern states it: `Material.fibre_content` when it is
    set, otherwise the yarn as named, with the composition said to be unstated rather than
    read out of the name.
    """
    out: list[str] = []
    for m in materials or []:
        name = getattr(m, "name", "") or ""
        weight = getattr(m, "yarn_weight", None)
        if not name:
            continue
        out.append(f"Yarn: {name}" + (f" ({weight} weight)" if weight and weight.lower()
                                      not in name.lower() else ""))
        fibre = getattr(m, "fibre_content", ()) or ()
        if fibre:
            out.append("Fibre: " + ", ".join(f"{pct}% {f}" for f, pct in fibre))
    # One line per distinct yarn: a two-colour pattern in one yarn base is one yarn to buy.
    out = list(dict.fromkeys(out))
    if out and not any(line.startswith("Fibre:") for line in out):
        out.append("Fibre: as named above; the pattern does not specify a composition, so "
                   "choose any yarn of the same weight that meets the gauge")
    return out


# F-255: the parts a description must carry, in the order a buyer decides.
DESCRIPTION_PARTS: tuple[tuple[str, str], ...] = (
    ("what_is_sold", r"a crochet pattern, not a finished item"),
    ("why_it_matters", r"why it is worth making"),
    ("difficulty", r"^- difficulty:"),
    ("size", r"^- finished size:"),
    ("yarn", r"^- yarn:"),
    ("fibre", r"^- fibre:"),
    ("gauge_hook", r"^- gauge:.*hook"),
    ("inclusions", r"^what you get$"),
    ("delivery", r"instant digital download"),
    ("support", r"tell us"),
)


def description_architecture(description: str, *, expect: set[str]) -> list[str]:
    """Blocking findings for a description missing a decision-critical part (F-255).

    `expect` names the parts whose facts exist for this product (a pattern with no stated
    size cannot print one); only those are required. The first two parts must be on the
    first line, which is what "lead with what is sold and why it matters" means.
    """
    text = description or ""
    lines = [l.strip().lower() for l in text.splitlines()]
    problems: list[str] = []
    for part, pattern in DESCRIPTION_PARTS:
        if part not in expect:
            continue
        rx = re.compile(pattern, re.I | re.M)
        if part in ("what_is_sold", "why_it_matters"):
            if not (lines and rx.search(lines[0])):
                problems.append(f"DESCRIPTION_ARCHITECTURE: {part} is not on the first line")
        elif not rx.search("\n".join(lines)):
            problems.append(f"DESCRIPTION_ARCHITECTURE: {part} is missing")
    return problems


def opening_sentence(key_phrases: list[str]) -> str:
    """One natural sentence carrying up to three of the listing's key phrases (F-025).

    Phrases that already say "pattern" are used as they are; the others are joined into the
    sentence as what the pattern makes. Empty when there is nothing to say, rather than a
    sentence padded with filler.
    """
    picked: list[str] = []
    for phrase in key_phrases:
        p = " ".join(phrase.lower().split())
        if p and p not in picked and not any(p in q or q in p for q in picked):
            picked.append(p)
        if len(picked) == 3:
            break
    if not picked:
        return ""
    if len(picked) == 1:
        joined = picked[0]
    else:
        joined = ", ".join(picked[:-1]) + " and " + picked[-1]
    return (f"If you are searching for {joined}, this is the one: every row is written out "
            f"and charted, and every stitch count is checked before release.")


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
    # Etsy's tag character rules, including "no leading ' or -" (lane I's
    # `publish.listing_schema.tag_problems`), on the release chain's own drafts too.
    from ..publish import listing_schema as _schema

    problems.extend(f"LISTING_{p}" for p in _schema.tag_problems(list(copy.tags)))
    if len(copy.description) < DESCRIPTION_MIN:
        problems.append(f"LISTING_DESCRIPTION_THIN: {len(copy.description)} characters")
    hit = _UNSUPPORTABLE.search(copy.title + " " + copy.description)
    if hit:
        problems.append(f"LISTING_UNSUPPORTABLE_CLAIM: {hit.group(0)!r}")
    if "pattern" not in copy.title.lower():
        problems.append("LISTING_AMBIGUOUS_PRODUCT: the title must say this is a pattern, "
                        "not a finished item")
    return problems



# ---- the search-copy gate (F-011, F-021, F-023, F-024, F-026, F-245, F-251) ----------------

# How many times one target phrase may appear in the description before it reads as a
# keyword dump rather than a sentence. Three covers the opening, the details and one mention.
DESCRIPTION_PHRASE_REPEAT_MAX = 3
# A line where this many comma/pipe-separated chunks are target phrases is a keyword list.
DESCRIPTION_LIST_CHUNKS = 4

# F-251: the shop language is English (the shop is Canadian and lists in English). A word
# outside this alphabet in a title or tag is a translation, which must be deliberate.
SHOP_LANGUAGE = "en"
_NON_ENGLISH = re.compile(r"[^\x00-\x7f\u2014\u2013\u2019\u00d7]")
# F-251: words that are unmistakably another language even in plain ASCII. Alphabet alone
# let "patron ganchillo manta" through. Only words with no common English sense are listed
# ("patron", "manta", "motif", "schema" and "crochet" itself are English too).
_FOREIGN_ASCII = frozenset({
    # Spanish
    "ganchillo", "patrones", "tejido", "tejer", "cobija", "cesta", "para", "bebe", "mantita",
    # French
    "couverture", "modele", "tricot", "pour", "avec", "panier", "tuto",
    # German
    "hakeln", "haekeln", "anleitung", "haekelanleitung", "hakelanleitung", "decke", "muster",
    "fuer", "und", "korb",
    # Dutch
    "haken", "patroon", "haakpatroon", "deken", "mand",
    # Portuguese / Italian
    "croche", "receita", "cesto", "uncinetto", "coperta", "cestino",
})
# A translation recorded "for impressions" is the bait F-251 refuses: a translation must be
# for buyers who read that language, not for reach.
_BAIT = re.compile(r"\b(impressions?|traffic|reach|more views|visibility|rank(ing)?|"
                   r"keywords?|seo)\b", re.I)


def language_findings(texts: list[str]) -> list[str]:
    """The title/tag strings that are not in the shop language, by alphabet or by word."""
    out: list[str] = []
    for t in texts:
        if _NON_ENGLISH.search(t) or any(w in _FOREIGN_ASCII
                                         for w in re.findall(r"[a-z]+", t.lower())):
            out.append(t)
    return out


def translation_problems(record) -> list[str]:
    """Why a translation record is not a deliberate one (F-251); empty when it is.

    A record must exist, must name the language or market it serves, and must not give
    search reach as its reason. A dict record needs `language` and `reason`.
    """
    if record is None or (isinstance(record, str) and not record.strip()):
        return ["no deliberate translation is recorded"]
    if isinstance(record, dict):
        lang = str(record.get("language") or "").strip()
        reason = str(record.get("reason") or "").strip()
        if not lang or not reason:
            return ["a translation record needs a language and a reason"]
        text = f"{lang} {reason}"
    else:
        text = str(record)
    if _BAIT.search(text):
        return [f"the recorded reason is search reach ({_BAIT.search(text).group(0)!r}); a "
                f"translation is for buyers who read the language, not impression bait"]
    return []


def keyword_dump(description: str, phrases: list[str]) -> list[str]:
    """Blocking findings for a description that lists keywords instead of describing (F-026)."""
    problems: list[str] = []
    flat = " ".join((description or "").lower().split())
    for phrase in sorted({p.lower() for p in phrases if p and len(p.split()) >= 2}):
        n = len(re.findall(rf"\b{re.escape(phrase)}\b", flat))
        if n > DESCRIPTION_PHRASE_REPEAT_MAX:
            problems.append(f"DESCRIPTION_KEYWORD_REPEAT: {phrase!r} appears {n} times")
    targets = {p.lower().strip() for p in phrases}
    for line in (description or "").splitlines():
        chunks = [c.strip().lower() for c in re.split(r"[,|;/#]", line) if c.strip()]
        hits = sum(1 for c in chunks if c in targets)
        if hits >= DESCRIPTION_LIST_CHUNKS:
            problems.append(f"DESCRIPTION_KEYWORD_LIST: a line lists {hits} target phrases: "
                            f"{line[:80]!r}")
    if len(re.findall(r"(?:^|\s)#\w+", description or "")) >= 3:
        problems.append("DESCRIPTION_HASHTAGS: hashtags are keyword stuffing on Etsy")
    return problems


def check_search_copy(copy: ListingCopy, *, phrases: list[str] | None = None,
                      tag_limitation: str | None = None,
                      translation_record: str | dict | None = None,
                      front_scan_differentiator: str | None = None,
                      check_front_scan: bool = False) -> dict:
    """The search-quality gate on a drafted listing: blocking findings and soft ones.

    Separate from `check_listing_limits`, which asks whether Etsy would accept the listing;
    this asks whether it is honest, readable search copy:

    - **13 tags (F-011).** Fewer is blocking unless `tag_limitation` records the documented
      platform limitation that prevents it; the limitation is then carried as a soft finding.
    - **Stuffing (F-021, F-245, F-298).** `portfolio.stuffing` -- a title repeating a word,
      or a tag set spending its slots on one word -- blocks rather than being audited.
    - **Subjective words (F-024)** in the title block; `build_title` relocates them.
    - **Title length (F-023)** above the fifteen-word target is a soft finding.
    - **Keyword dumps (F-026)** in the description block.
    - **Shop language (F-251):** a title or tag outside English blocks unless a deliberate
      `translation_record` exists.
    """
    from .portfolio import stuffing

    blocking: list[str] = []
    soft: list[str] = []
    if len(copy.tags) < TAG_MAX_COUNT:
        gap = (f"LISTING_TAG_SLOTS_UNUSED: {len(copy.tags)} of {TAG_MAX_COUNT} tag slots "
               f"used")
        if tag_limitation and tag_limitation.strip():
            soft.append(f"{gap}; recorded limitation: {tag_limitation.strip()[:200]}")
        else:
            blocking.append(gap + " and no documented platform limitation is recorded")
    stuffed = stuffing(copy.title, copy.tags)
    if stuffed.get("stuffed"):
        blocking.append(f"LISTING_STUFFED: {stuffed['why']}")
    moved = [m.group(0) for m in _SUBJECTIVE.finditer(copy.title)]
    if moved:
        blocking.append(f"LISTING_SUBJECTIVE_IN_TITLE: {moved} belong in the description")
    words = len(_title_words(copy.title))
    if words > TITLE_WORD_TARGET:
        soft.append(f"LISTING_TITLE_LONG: {words} words; the readability target is "
                    f"{TITLE_WORD_TARGET}")
    blocking.extend(keyword_dump(copy.description, list(phrases or []) + list(copy.tags)))
    scan = None
    if check_front_scan:
        # F-022: the release chain asks; ad-hoc callers checking someone else's copy do not.
        scan = front_scan(copy.title, differentiator=front_scan_differentiator)
        blocking.extend(scan["problems"])
    foreign = language_findings([copy.title] + list(copy.tags))
    refused = translation_problems(translation_record) if foreign else []
    if foreign and refused:
        blocking.append(f"LISTING_LANGUAGE: {foreign[:3]} are not in the shop language "
                        f"({SHOP_LANGUAGE}); {refused[0]}")
    return {"blocking": blocking, "soft": soft, "stuffing": stuffed,
            "title_words": words, "front_scan": scan, "ok": not blocking}
