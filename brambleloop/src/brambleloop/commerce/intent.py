"""Buyer language, in the buyer's words, with an honest label on which words are evidence.

Requirement 293. Before a seasonal product launches, its search strategy has to be built from
what buyers actually type, along six facets: the object, the technique, the recipient or use,
the aesthetic, the season or event, and the skill or feature that matters.

The requirement exists because a shop's own vocabulary is invisible to it. "Heirloom mosaic
throw in pine and cream" is how this company thinks about a product and is not a search
anybody performs. The words a buyer uses are blunter and more specific at the same time --
"christmas stocking crochet pattern easy" -- and the gap between the two is a listing that
ranks for nothing while reading beautifully.

Two mechanisms, and the second is the one that matters.

**The facet map refuses our vocabulary.** Brand words, aesthetic adjectives that describe a
feeling rather than a thing, and the generic tokens that make any product sound like any other
are rejected at the door, per facet. A facet filled with our language is worse than an empty
one: it produces phrases that look like research.

**Every phrase is labelled assumed or observed, and nothing here can promote itself.** A
phrase is observed only when a recorded market observation contains it. With no benchmark
credential, every phrase this module produces is assumed -- which is a perfectly good basis
for a first listing and is not the same thing as buyer language, and the difference is stated
on each row rather than in a caveat at the bottom that travels separately from the numbers.
"""
from __future__ import annotations

import html
import re
from dataclasses import dataclass

from ..creative.concept import GENERIC_TOKENS

# Words a buyer genuinely types that mean nothing in a creative premise. The creative
# vocabulary refuses "easy" and "gift" because a concept described that way has not been
# described; a shopper filtering for "easy no sew gift" has told you almost everything about
# the sale. The same word is empty in one place and load-bearing in the other, so the two
# lists are not the same list.
BUYER_QUALIFIERS: frozenset[str] = frozenset({
    "easy", "simple", "quick", "beginner", "gift", "set", "bundle", "pack", "handmade",
    "home", "decor", "blanket", "throw", "scarf", "hat", "bag", "pattern", "crochet",
    "crocheted", "made", "design",
})

EMPTY_FOR_SEARCH: frozenset[str] = GENERIC_TOKENS - BUYER_QUALIFIERS

ASSUMED, OBSERVED = "assumed", "observed"


@dataclass(frozen=True)
class Facet:
    key: str
    what: str
    why: str
    required: bool


FACETS: tuple[Facet, ...] = (
    Facet("object", "the thing itself: stocking, ornament, coaster, throw",
          "a query with no object is a category browse, and a category browse is where a "
          "new shop is invisible", True),
    Facet("technique", "what the maker does: mosaic, tapestry, amigurumi, cables",
          "technique is how an experienced maker shops, and it is the facet a generic "
          "listing never carries", False),
    Facet("recipient_or_use", "who it is for or what it does: teacher gift, mantel, tree",
          "gift buyers search by occasion and recipient before they search by object", True),
    Facet("aesthetic", "the visual register a buyer can name: nordic, retro, farmhouse",
          "the one facet where our language is most likely to leak in, because it is the "
          "one we care about most", False),
    Facet("season_event", "the occasion: christmas, halloween, valentines",
          "seasonal demand is the whole reason a seasonal listing exists", True),
    Facet("skill_feature", "what makes it accessible or different: easy, beginner, chart, "
                           "no sew, video",
          "the qualifier that converts: a buyer filtering for 'no sew' has already decided "
          "to buy something", False),
)

FACET_BY_KEY: dict[str, Facet] = {f.key: f for f in FACETS}

# Words that are ours rather than the buyer's. Brand terms and the feeling-words a listing
# reaches for when nobody has asked what a shopper types.
OUR_VOCABULARY: frozenset[str] = frozenset({
    "brambleloop", "studio", "heirloom", "quietly", "luxurious", "artisan", "curated",
    "bespoke", "premium", "signature", "collection", "story", "crafted", "elevated",
    "considered", "timeless", "refined",
})

# How buyers actually order the words. Object-led is the commonest; season-led is how a
# gifting search starts; recipient-led is how somebody shopping for a person starts.
_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("object_led", ("season_event", "object", "crochet pattern")),
    ("object_skill", ("season_event", "object", "crochet pattern", "skill_feature")),
    ("technique_led", ("technique", "crochet", "object", "pattern")),
    ("gift_led", ("crochet", "object", "for", "recipient_or_use")),
    ("aesthetic_led", ("aesthetic", "crochet", "object", "pattern")),
    ("season_led", ("crochet", "season_event", "decor pattern")),
)

_WORD = re.compile(r"[a-z0-9]+")


class IntentRefused(ValueError):
    """A facet map built from our vocabulary, or missing the facets a search needs."""


def _words(value: str) -> list[str]:
    return _WORD.findall(value.lower())


def map_product(**facets: str) -> dict:
    """Build the six-facet map for one product, refusing the two ways it goes wrong."""
    cleaned: dict[str, str] = {}
    for key, value in facets.items():
        if key not in FACET_BY_KEY:
            raise IntentRefused(
                f"{key!r} is not a search facet: {sorted(FACET_BY_KEY)}. An extra facet is a "
                f"word somebody wanted in the title")
        text = (value or "").strip().lower()
        if not text:
            continue
        ours = [w for w in _words(text) if w in OUR_VOCABULARY]
        if ours:
            raise IntentRefused(
                f"{key}={value!r} uses our vocabulary ({', '.join(sorted(set(ours)))}). A "
                f"facet filled with our language is worse than an empty one, because it "
                f"produces phrases that look like research")
        if all(w in EMPTY_FOR_SEARCH for w in _words(text)):
            raise IntentRefused(
                f"{key}={value!r} is made only of words that describe nothing. A buyer does "
                f"not search for an adjective")
        cleaned[key] = text

    missing = [f.key for f in FACETS if f.required and f.key not in cleaned]
    if missing:
        raise IntentRefused(
            f"missing required facet(s) {missing}: "
            + "; ".join(f"{FACET_BY_KEY[k].key} -- {FACET_BY_KEY[k].why}" for k in missing))
    return cleaned


def observed_phrases(db) -> set[str]:
    """Phrases a recorded market observation actually contains.

    Rows, not arguments. With no benchmark credential this is empty, and everything the
    mapper produces is therefore assumed -- which the strategy says on every row.
    """
    from sqlalchemy import select

    from ..core.models import BenchmarkListing, Keyword

    out: set[str] = set()
    with db.session() as s:
        for row in s.scalars(select(Keyword)):
            if str(getattr(row, "intent", "") or "") == "package:modelled":
                continue   # our own modelled phrase (seo.packages), not market language
            if getattr(row, "phrase", None):
                out.add(row.phrase.strip().lower())
        for row in s.scalars(select(BenchmarkListing)):
            title = (getattr(row, "title", "") or "").strip().lower()
            if title:
                out.add(title)
    return out


def phrases(facet_map: dict, *, observed: set[str] | None = None) -> list[dict]:
    """Every phrase this product could answer, in the orders buyers type them."""
    observed = observed or set()
    seen: set[str] = set()
    out: list[dict] = []
    for name, parts in _PATTERNS:
        words: list[str] = []
        used: list[str] = []
        complete = True
        for part in parts:
            if part in FACET_BY_KEY:
                value = facet_map.get(part)
                if value is None:
                    complete = False
                    break
                words.append(value)
                used.append(part)
            else:
                words.append(part)
        if not complete:
            continue
        phrase = " ".join(" ".join(words).split())
        if phrase in seen:
            continue
        seen.add(phrase)
        hit = any(phrase in o or o == phrase for o in observed)
        out.append({"phrase": phrase, "pattern": name, "facets": used,
                    "evidence": OBSERVED if hit else ASSUMED})
    return out


def strategy(db, *, facet_map: dict) -> dict:
    """The search strategy for one product, with assumed and observed kept apart.

    A first listing built on assumed language is a reasonable thing to publish. It is not
    research, and the two are separated here rather than blended into one ranked list where
    the distinction is lost by the time anybody acts on it.
    """
    rows = phrases(facet_map, observed=observed_phrases(db))
    observed_rows = [r for r in rows if r["evidence"] == OBSERVED]
    assumed_rows = [r for r in rows if r["evidence"] == ASSUMED]
    return {
        "facets": facet_map,
        "facets_used": sorted(facet_map),
        "facets_absent": [f.key for f in FACETS if f.key not in facet_map],
        "observed": observed_rows,
        "assumed": assumed_rows,
        "phrases": len(rows),
        "observed_share": round(len(observed_rows) / len(rows), 3) if rows else None,
        "note": ("no market observation has been recorded, so every phrase here is our best "
                 "guess at buyer language rather than buyer language. That is a fine basis "
                 "for a first listing and it is not research, and #293 is the requirement "
                 "that those two stay distinguishable"
                 if not observed_rows else
                 f"{len(observed_rows)} of {len(rows)} phrases appear in recorded market "
                 f"evidence; the rest are assumed"),
    }


# ---------------------------------------------------------------------------
# Arena language (#293, with the credential that arrived on 2026-09-19)
#
# The requirement asks for buyer language "from Etsy/market evidence". Until the benchmark
# credential existed there was no evidence, so every phrase this module produced was
# `assumed` and said so. There are now 438 observed listings, and the useful question is no
# longer "is this phrase attested" one phrase at a time -- it is "what words does a shopper
# in *this department* actually see", which is what a seasonal brief needs before a launch
# date rather than after it.
#
# What this reads is term frequency across observed titles. That is demand intelligence: how
# a market describes a category. It is not, and must not become, a reproduction of anybody's
# listing, so nothing here emits a title, a phrase longer than a word, or an ordering taken
# from a seller.

# Words that appear in almost every title in this marketplace and therefore distinguish
# nothing. Separated rather than dropped: "pattern" and "pdf" are most of what a shopper
# types, so they belong in a search strategy and not in a creative brief.
MARKETPLACE_FURNITURE: frozenset[str] = frozenset({
    "crochet", "pattern", "patterns", "pdf", "digital", "download", "instant", "video",
    "tutorial", "printable", "ebook", "etsy", "shop", "sale", "new", "the", "and", "with",
    "for", "that", "this", "your", "our", "from", "includes", "included", "size", "sizes",
})

# The facet each observed word speaks to, so a frequency list becomes a brief rather than a
# word cloud. Only words that are unambiguous are classified; the rest are reported as
# unclassified, because a facet map that guesses is the thing #293 refuses.
_FACET_WORDS: dict[str, str] = {}
for _facet, _words_for in (
    ("season_event", ("christmas", "halloween", "easter", "valentine", "thanksgiving",
                      "holiday", "fall", "autumn", "winter", "spring", "summer", "festive",
                      "merry", "advent", "harvest")),
    ("technique", ("mosaic", "tapestry", "amigurumi", "granny", "cable", "cabled", "moss",
                   "star", "herringbone", "waffle", "bobble", "puff", "overlay", "c2c",
                   "corner", "stitch")),
    # "cozy" is deliberately absent: in this marketplace it is as often an object (a mug
    # cozy) as a mood, and a word that means two things classifies as neither.
    ("aesthetic", ("rustic", "farmhouse", "boho", "modern", "vintage", "chunky",
                   "cosy", "woodland", "nordic", "scandi", "coastal", "seaside", "retro",
                   "minimal", "whimsical")),
    ("skill_feature", ("easy", "beginner", "quick", "simple", "friendly", "bulky", "fast",
                       "seamless", "sew", "chart", "written", "stash")),
    ("object", ("stocking", "stockings", "ornament", "ornaments", "garland", "wreath",
                "blanket", "throw", "afghan", "scarf", "cowl", "hat", "beanie", "toque",
                "mitten", "mittens", "glove", "gloves", "slipper", "slippers", "sock",
                "socks", "bag", "tote", "purse", "basket", "pouch", "pillow", "cushion",
                "coaster", "runner", "dishcloth", "washcloth", "scrubby", "potholder",
                "cardigan", "sweater", "pullover", "hoodie", "vest", "shawl", "wrap",
                "poncho", "skirt", "coverup", "pouf", "lovey", "gnome", "snowman",
                "pumpkin")),
    ("recipient_or_use", ("gift", "gifting", "baby", "child", "children", "kids", "men",
                          "mens", "women", "womens", "teacher", "home", "decor", "kitchen",
                          "nursery", "teen", "toddler")),
):
    for _w in _words_for:
        _FACET_WORDS[_w] = _facet


def arena_language(db, *, pod: str, benchmark_key: str = "",
                   min_listings: int = 5, top: int = 12) -> dict:
    """The words a shopper in this department actually sees, counted from observed listings.

    Observed by construction: every term is read from a recorded `BenchmarkListing`, so
    nothing here can be labelled `assumed`. What it is *not* is a claim about search volume
    -- a word being common in a shop's titles says the shop believes shoppers use it, which
    is a different and weaker thing than a shopper using it, and the note says so rather
    than letting a frequency stand in for a search report.
    """
    from sqlalchemy import select

    from ..core.models import BenchmarkListing
    from ..intel import benchmarks

    benchmark_key = benchmark_key or benchmarks.MJS_KEY
    with db.session() as s:
        titles = [(r.title or "") for r in s.scalars(select(BenchmarkListing).where(
            BenchmarkListing.benchmark_key == benchmark_key,
            BenchmarkListing.pod == pod))]

    if len(titles) < min_listings:
        return {
            "pod": pod, "listings": len(titles), "measurable": False,
            "reason": (f"{len(titles)} observed listing(s) in this pod against a floor of "
                       f"{min_listings}. A frequency over four titles is one seller's habit, "
                       f"not a department's language"),
        }

    counts: dict[str, int] = {}
    for title in titles:
        seen = set()
        for word in _WORD.findall(html.unescape(title).lower()):
            if len(word) < 3 or word.isdigit() or word in seen:
                continue
            seen.add(word)
            counts[word] = counts.get(word, 0) + 1

    by_facet: dict[str, list] = {}
    furniture: list[dict] = []
    unclassified: list[dict] = []
    for word, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
        row = {"word": word, "listings": n, "share": round(n / len(titles), 3)}
        if word in MARKETPLACE_FURNITURE:
            furniture.append(row)
        elif word in _FACET_WORDS:
            by_facet.setdefault(_FACET_WORDS[word], []).append(row)
        else:
            unclassified.append(row)

    return {
        "pod": pod,
        "listings": len(titles),
        "measurable": True,
        "evidence": OBSERVED,
        "by_facet": {facet: rows[:top] for facet, rows in sorted(by_facet.items())},
        "marketplace_furniture": furniture[:top],
        "unclassified": unclassified[:top],
        "facets_with_no_observed_word": sorted(
            f.key for f in FACETS if f.key not in by_facet),
        "note": ("Term frequency across observed titles: how this market describes this "
                 "department. It is not a search-volume claim -- a word being common in a "
                 "shop's titles says that shop believes shoppers use it, which is weaker "
                 "than a shopper using it. Marketplace furniture is separated rather than "
                 "dropped: 'pattern' and 'pdf' describe nothing and are most of what a "
                 "shopper types, so they belong in a search strategy and not in a brief."),
    }


# ---------------------------------------------------------------------------
# #293 at launch: the listing's search strategy is built from observed buyer language
#
# `listing.seo` used to build its query set from templates alone. This maps the product to the
# six facets from its own facts (its category or winning concept, its season, its techniques,
# the difficulty its PDF prints), asks `strategy` which of the resulting phrases buyers were
# actually seen using, and hands back the observed ones as queries and tags. Demand is the
# share of observed listing titles carrying the phrase; competition is the captured search
# density where one exists and UNMEASURED otherwise -- in which case the phrase is tagged on
# the strength of being observed, and says so.

CATEGORY_USE: dict[str, str] = {
    "baby": "baby", "pet": "pet", "ornament": "tree", "coaster": "kitchen",
    "placemat": "kitchen", "runner": "home decor", "pillow": "home decor",
    "wall_decor": "home decor", "basket": "home decor", "blanket": "home decor",
    "mosaic_blanket": "home decor", "graphghan": "home decor",
    "seasonal_decor": "home decor", "flower": "home decor", "scarf": "women",
}
CATEGORY_OBJECT: dict[str, str] = {
    "mosaic_blanket": "blanket", "graphghan": "blanket", "seasonal_decor": "decor",
    "wall_decor": "wall hanging", "baby": "baby blanket", "pet": "pet bed",
}


def _serp_density(db, phrase: str) -> int | None:
    from sqlalchemy import desc, select

    from ..core.models import SerpSnapshot

    with db.session() as s:
        row = s.scalar(select(SerpSnapshot).where(SerpSnapshot.query == phrase)
                       .order_by(desc(SerpSnapshot.id)).limit(1))
        return row.total_count if row is not None else None


def listing_language(db, *, slug: str, category: str, season: str | None,
                     difficulty: str, techniques: list[str] | None = None,
                     max_tags: int = 4) -> dict:
    """Observed buyer phrases for one product about to be listed (#293)."""
    import math

    from sqlalchemy import select

    from ..core.models import BenchmarkListing
    from .search import TAG_MAX_CHARS, Query

    brief = None
    try:
        from ..creative.intake import intake_rows

        rows = intake_rows(db, slug=slug, limit=1)
        brief = ((rows[0][2].get("brief") or {}).get("buyer_language") if rows else None)
    except Exception:  # noqa: BLE001 - a product with no intake maps from its own facts
        brief = None
    if brief and brief.get("mapped"):
        facets = dict(brief["facets"])
        source = "the winning concept's facet map"
    else:
        facets = {
            "object": CATEGORY_OBJECT.get(category, category.replace("_", " ")),
            "technique": " ".join(t for t in (techniques or []) if t not in ("texture",)),
            "recipient_or_use": CATEGORY_USE.get(category, ""),
            "season_event": (season or "").split(" (")[0].replace("'s", "").lower(),
            "skill_feature": "beginner" if difficulty == "beginner" else "",
        }
        source = "the product's category, season, techniques and printed difficulty"
    try:
        mapped = map_product(**{k: v for k, v in facets.items() if v})
    except IntentRefused as exc:
        return {"mapped": False, "source": source, "facets": facets, "why": str(exc)[:300],
                "queries": [], "tags": []}
    got = strategy(db, facet_map=mapped)
    with db.session() as s:
        titles = [(r.title or "").lower() for r in s.scalars(select(BenchmarkListing))]
    queries, tags, rows_out = [], [], []
    for row in got["observed"]:
        phrase = row["phrase"]
        words = phrase.split()
        share = (sum(1 for t in titles if all(w in t for w in words)) / len(titles)
                 if titles else 0.0)
        density = _serp_density(db, phrase)
        competition = (round(min(1.0, math.log10(max(1, density)) / 5.0), 3)
                       if density is not None else None)
        if competition is not None:
            # Only a phrase whose competition was measured enters the scored query model; an
            # unmeasured one is tagged on the evidence that buyers use it, never given a
            # competition figure nobody observed.
            queries.append(Query(phrase, round(min(1.0, share), 4), competition, "product"))
        fitted = phrase if len(phrase) <= TAG_MAX_CHARS else " ".join(
            w for i, w in enumerate(words) if len(" ".join(words[:i + 1])) <= TAG_MAX_CHARS)
        if fitted and len(fitted.split()) >= 2 and fitted not in tags and len(tags) < max_tags:
            tags.append(fitted)
        rows_out.append({"phrase": phrase, "pattern": row["pattern"],
                         "observed_title_share": round(share, 4),
                         "serp_density": density,
                         "competition": competition if competition is not None
                         else "UNMEASURED"})
    return {"mapped": True, "source": source, "facets": mapped, "observed": rows_out,
            "assumed": [r["phrase"] for r in got["assumed"]], "queries": queries,
            "tags": tags, "observed_share": got["observed_share"], "note": got["note"]}
