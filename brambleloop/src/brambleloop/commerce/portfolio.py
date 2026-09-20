"""Whether the catalogue competes with itself, and whether it is stuffing to avoid it.

Requirement 240. *Do not make all products compete for 'crochet pattern'.* Build clusters
around intent, recipient, season, technique, object, aesthetic, skill level and use case, and
maximise relevant coverage **without keyword stuffing**.

Two failure modes, and they are opposites, which is the whole difficulty. A catalogue whose
listings all reach for the same head term has one product's worth of visibility spread over
eleven listings -- every one of them ranked against every other, and against everybody else's
too. Fixing that by loading each listing with every term anybody might type produces the
second failure, and platforms demote for it.

So this measures both, from the listings themselves.

**Concentration is counted per facet.** `commerce/intent` already holds the facet vocabulary
the requirement names. A catalogue occupying one value of `object` across every listing is
concentrated on object; one occupying eleven is spread. The measure is the same shape as the
anti-fragility rule's, because it is the same question asked about queries instead of
dependencies.

**Cannibalisation is counted per pair.** Two listings whose facet values are identical are
two listings competing for one query, and the second one does not add reach -- it splits it.

**Stuffing is counted per listing.** A tag set that spends its slots on variations of one
term, or a title that repeats a word, is reaching for coverage it will be demoted for. The
existing `search.choose_tags` already budgets words per slot; this reports when a listing
that already exists has blown that budget.
"""
from __future__ import annotations

import re
from collections import Counter

from .intent import FACETS, MARKETPLACE_FURNITURE, _FACET_WORDS

_WORD = re.compile(r"[a-z0-9]+")

# Above this share of the catalogue sharing one facet value, the catalogue is competing with
# itself on that facet. Matches the anti-fragility threshold, because it is the same
# judgement about the same kind of evidence.
CONCENTRATED_ABOVE = 0.60

# A tag set that spends more than this share of its slots on one word is reaching for
# coverage rather than describing a product.
STUFFED_WORD_SHARE = 0.40

# Two listings sharing at least this share of their stated facet values are competing for the
# same queries rather than covering different ones.
CANNIBAL_OVERLAP = 0.80


class PortfolioRefused(ValueError):
    """A diversification report asked for where there is no catalogue to report on."""


def _facets_of(text: str) -> dict[str, set]:
    """Which facet values a piece of listing text states, using the shared vocabulary."""
    found: dict[str, set] = {}
    for word in _WORD.findall((text or "").lower()):
        if word in MARKETPLACE_FURNITURE:
            continue
        facet = _FACET_WORDS.get(word)
        if facet:
            found.setdefault(facet, set()).add(word)
    return found


def listing_facets(title: str, tags: list[str], description: str = "") -> dict:
    """The facet values one listing actually claims, and the ones it leaves empty."""
    combined = " ".join([title or "", " ".join(tags or []), description or ""])
    found = _facets_of(combined)
    return {
        "stated": {facet: sorted(values) for facet, values in sorted(found.items())},
        "empty": sorted(f.key for f in FACETS if f.key not in found),
        "required_missing": sorted(f.key for f in FACETS
                                   if f.required and f.key not in found),
    }


def stuffing(title: str, tags: list[str]) -> dict:
    """Whether this listing is reaching for coverage rather than describing a product."""
    slots = [t for t in (tags or []) if t.strip()]
    if not slots:
        return {"stuffed": False, "measurable": False,
                "why": "this listing has no tags, which is a different problem"}

    words = Counter(w for tag in slots for w in _WORD.findall(tag.lower())
                    if w not in MARKETPLACE_FURNITURE)
    worst = words.most_common(1)[0] if words else ("", 0)
    share = round(worst[1] / len(slots), 3) if slots else 0.0

    # Furniture is excluded from the *tag* count and deliberately not from the title. A tag
    # set where every slot contains "crochet" is ordinary -- that is how tags work. A title
    # reading "Crochet Pattern Crochet Blanket Crochet Throw" is the commonest form of
    # stuffing there is, and excluding furniture from it would make the check blind to
    # exactly the case it exists for.
    title_words = _WORD.findall((title or "").lower())
    repeated = [w for w, n in Counter(title_words).items() if n > 1 and len(w) > 3]

    stuffed = share > STUFFED_WORD_SHARE or bool(repeated)
    return {
        "stuffed": stuffed,
        "measurable": True,
        "tag_slots": len(slots),
        "most_repeated_word": worst[0],
        "share_of_slots": share,
        "repeated_in_title": repeated,
        "threshold": STUFFED_WORD_SHARE,
        "why": (f"{worst[0]!r} appears in {share:.0%} of the tag slots"
                if share > STUFFED_WORD_SHARE else
                f"{repeated} repeated in the title" if repeated else
                "the tags spend their slots on different words"),
    }


def diversification(db) -> dict:
    """Does this catalogue cover different queries, or the same one many times?

    The finding is not a score. It is which facet the catalogue is concentrated on and which
    pairs of listings are competing with each other, because those are the two things
    somebody can act on.
    """
    from sqlalchemy import select

    from ..core.models import Listing

    with db.session() as s:
        listings = [{"slug": r.product_slug, "title": r.title, "tags": list(r.tags or []),
                     "description": r.description} for r in s.scalars(select(Listing))]

    if not listings:
        return {"measurable": False,
                "reason": ("no listing exists, so whether the catalogue competes with itself "
                           "is not a question it can answer yet. An empty catalogue is not a "
                           "diversified one")}

    facets = {row["slug"]: listing_facets(row["title"], row["tags"], row["description"])
              for row in listings}

    # Concentration per facet: how much of the catalogue shares one value.
    per_facet = {}
    for facet in FACETS:
        values = Counter(
            value for slug in facets
            for value in facets[slug]["stated"].get(facet.key, []))
        stating = [slug for slug in facets if facets[slug]["stated"].get(facet.key)]
        if not stating:
            per_facet[facet.key] = {
                "measurable": False, "what": facet.what, "required": facet.required,
                "why": (f"no listing states a {facet.key}. "
                        + (facet.why if facet.required else
                           "not required, and absent rather than diverse"))}
            continue
        top, count = values.most_common(1)[0]
        share = round(count / len(stating), 3)
        # One listing cannot be ranked against itself. A facet a single listing states is a
        # lone occupant, not a concentration -- reporting it at 100% would flag the least
        # crowded facet in the catalogue as its most crowded, which is the finding exactly
        # inverted.
        lone = len(stating) < 2
        concentrated = (not lone) and share > CONCENTRATED_ABOVE
        per_facet[facet.key] = {
            "measurable": True, "what": facet.what, "required": facet.required,
            "listings_stating_it": len(stating), "distinct_values": len(values),
            "most_common": top, "share": share,
            "concentrated": concentrated,
            "sole_occupant": lone,
            "why": (f"only one listing states a {facet.key}, so there is nothing for it to "
                    f"compete with. That is thin coverage rather than concentration"
                    if lone else
                    f"{share:.0%} of the listings that state a {facet.key} state "
                    f"{top!r}. Above {CONCENTRATED_ABOVE:.0%} they are ranked against each "
                    f"other rather than reaching different shoppers"
                    if concentrated else
                    f"{len(values)} distinct values across {len(stating)} listings"),
        }

    # Cannibalisation: pairs whose stated facets are close to identical.
    slugs = sorted(facets)
    competing = []
    for i, left in enumerate(slugs):
        for right in slugs[i + 1:]:
            a = {(f, v) for f, vs in facets[left]["stated"].items() for v in vs}
            b = {(f, v) for f, vs in facets[right]["stated"].items() for v in vs}
            if not a or not b:
                continue
            overlap = len(a & b) / len(a | b)
            if overlap >= CANNIBAL_OVERLAP:
                competing.append({"between": [left, right], "overlap": round(overlap, 3)})

    stuffed = {row["slug"]: stuffing(row["title"], row["tags"]) for row in listings}
    stuffing_now = [slug for slug, report in stuffed.items() if report["stuffed"]]

    concentrated = [key for key, row in per_facet.items()
                    if row.get("concentrated")]
    return {
        "measurable": True,
        "listings": len(listings),
        "facets": per_facet,
        "concentrated_on": concentrated,
        "competing_pairs": competing,
        "stuffing": stuffing_now,
        "required_facets_missing": sorted({
            facet for row in facets.values() for facet in row["required_missing"]}),
        "why": ("the two failures are opposites, which is the difficulty: a catalogue "
                "reaching for one head term ranks its own listings against each other, and "
                "a catalogue fixing that by loading every term anybody might type gets "
                "demoted for it. Both are counted here from the listings themselves (#240)"),
    }
