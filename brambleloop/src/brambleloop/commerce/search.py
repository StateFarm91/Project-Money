"""Search Domination (Master Plan section 8).

Section 8's objective is qualified search share through MATCH -> CLICK -> CONVERT -> DELIGHT,
built from query coverage across every product, category and season, accurate categories and
attributes, and all thirteen tag slots used well.

The honest framing for a shop with no history: we cannot outrank an incumbent on
"crochet blanket pattern", and pretending otherwise wastes all thirteen slots on queries we
will never appear for. What a new shop can win is the long tail -- specific, lower-volume
phrases where the shelf is thin and intent is high. So coverage here is scored against a
*reachable* set of queries rather than the biggest ones, and the model says which is which.

The hard rule from section 8 is carried in code elsewhere and restated here because it bounds
everything in this file: no fake reviews, purchases, favourites or fabricated engagement.
Search share has to come from real buyers. Nothing in this module simulates traffic.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# Etsy's limits.
TAG_SLOTS = 13
TAG_MAX_CHARS = 20
TITLE_MAX = 140

# Above this, a new shop with no reviews and no sales history is not going to place, however
# good the listing is. Section 8 is about qualified share, not vanity terms.
REACHABLE_COMPETITION = 0.72


@dataclass(frozen=True)
class Query:
    """One search phrase we might try to cover."""

    phrase: str
    demand: float          # 0-1, relative search volume
    competition: float     # 0-1, how entrenched the incumbents are
    intent: str = "product"    # product | seasonal | technique | gift | category

    @property
    def reachable(self) -> bool:
        return self.competition <= REACHABLE_COMPETITION

    @property
    def value(self) -> float:
        """Demand we can plausibly capture. A head term we cannot place for is worth nothing."""
        return round(self.demand * (1.0 - self.competition), 4)


# Query families, expanded per product. Derived from the categories section 4 lists and the
# phrasing patterns visible in the competitor listings we profiled.
_TEMPLATES: dict[str, list[tuple[str, float, float, str]]] = {
    "core": [
        ("{category} pattern", 0.95, 0.88, "category"),
        ("crochet {category} pattern", 0.90, 0.86, "category"),
        ("{category} crochet pattern pdf", 0.55, 0.62, "product"),
        ("easy {category} pattern", 0.45, 0.70, "product"),
    ],
    "motif": [
        ("{motif} crochet pattern", 0.40, 0.48, "product"),
        ("{motif} {category} pattern", 0.30, 0.34, "product"),
        ("crochet {motif} chart", 0.18, 0.28, "technique"),
    ],
    # Gated on techniques the pattern actually uses. Tagging a plain basket "overlay mosaic"
    # buys traffic that bounces, which is worse than no traffic: it is a click we paid for in
    # search position and a shopper who now distrusts the shop.
    "technique:mosaic": [
        ("overlay mosaic crochet", 0.35, 0.52, "technique"),
        ("mosaic crochet chart pattern", 0.28, 0.44, "technique"),
    ],
    "technique:always": [
        ("written and chart crochet pattern", 0.22, 0.36, "technique"),
        ("us and uk terms crochet", 0.10, 0.20, "technique"),
    ],
    "technique:texture": [
        ("textured crochet pattern", 0.24, 0.46, "technique"),
        ("crochet stitch pattern chart", 0.18, 0.40, "technique"),
    ],
    "seasonal": [
        ("{season} crochet pattern", 0.70, 0.74, "seasonal"),
        ("{season} {category} crochet", 0.42, 0.50, "seasonal"),
        ("crochet {season} gift", 0.38, 0.62, "gift"),
        ("{season} crochet decor pattern", 0.30, 0.46, "seasonal"),
    ],
    "gift": [
        ("handmade gift crochet pattern", 0.32, 0.58, "gift"),
        ("crochet pattern for beginners gift", 0.26, 0.64, "gift"),
    ],
}


def build_query_set(category: str, motifs: list[str], season: str | None,
                    techniques: list[str] | None = None) -> list[Query]:
    """Every phrase this product could plausibly answer, with its reachability.

    `techniques` gates the technique families. A query family is only added when the pattern
    genuinely uses that technique -- section 8 asks for *qualified* search share, and a
    listing that ranks for something it is not is a bounce, not a win.
    """
    out: dict[str, Query] = {}
    cat = category.replace("_", " ")

    def add(template: str, demand: float, competition: float, intent: str, **kw) -> None:
        try:
            phrase = template.format(category=cat, **kw).strip().lower()
        except KeyError:
            return
        phrase = re.sub(r"\s+", " ", phrase)
        if phrase and phrase not in out:
            out[phrase] = Query(phrase, demand, competition, intent)

    for t, d, c, i in _TEMPLATES["core"]:
        add(t, d, c, i)
    for motif in motifs[:3]:
        for t, d, c, i in _TEMPLATES["motif"]:
            add(t, d, c, i, motif=motif.lower())
    for technique in ["always"] + [t.lower() for t in (techniques or [])]:
        for t, d, c, i in _TEMPLATES.get(f"technique:{technique}", []):
            add(t, d, c, i)
    if season:
        s = season.split(" (")[0].lower()
        for t, d, c, i in _TEMPLATES["seasonal"]:
            add(t, d, c, i, season=s)
    for t, d, c, i in _TEMPLATES["gift"]:
        add(t, d, c, i)
    return sorted(out.values(), key=lambda q: (-q.value, q.phrase))


# ---- coverage --------------------------------------------------------------


def _normalise(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", text.lower())


def covers(query: Query, *, title: str, tags: list[str], description: str) -> str | None:
    """Where, if anywhere, a query is covered. Order matters: a tag beats a mention."""
    phrase = _normalise(query.phrase)
    if any(_normalise(t) == phrase for t in tags):
        return "tag_exact"
    if phrase in _normalise(title):
        return "title_phrase"
    words = phrase.split()
    if all(w in _normalise(title).split() for w in words):
        return "title_words"
    if phrase in _normalise(description):
        return "description"
    return None


@dataclass
class CoverageReport:
    queries: int
    reachable: int
    covered: int
    covered_reachable: int
    captured_value: float
    total_reachable_value: float
    gaps: list[dict] = field(default_factory=list)
    where: dict[str, str] = field(default_factory=dict)

    @property
    def share(self) -> float:
        return (round(self.captured_value / self.total_reachable_value, 4)
                if self.total_reachable_value else 0.0)

    def to_dict(self) -> dict:
        return {"queries": self.queries, "reachable": self.reachable,
                "covered": self.covered, "covered_reachable": self.covered_reachable,
                "captured_value": round(self.captured_value, 4),
                "total_reachable_value": round(self.total_reachable_value, 4),
                "share": self.share, "gaps": list(self.gaps)}


def score_coverage(queries: list[Query], *, title: str, tags: list[str],
                   description: str) -> CoverageReport:
    """How much of the reachable demand this listing actually answers.

    Scored against reachable value rather than all value on purpose. A listing that covers
    every long-tail phrase and misses the head term is doing the right thing for a new shop;
    scoring it against the head term would tell it to do the wrong thing.
    """
    where: dict[str, str] = {}
    captured = 0.0
    reachable_value = 0.0
    covered = 0
    covered_reachable = 0

    for q in queries:
        placement = covers(q, title=title, tags=tags, description=description)
        if q.reachable:
            reachable_value += q.value
        if placement:
            covered += 1
            where[q.phrase] = placement
            if q.reachable:
                covered_reachable += 1
                # A description mention is worth far less than a tag or title placement.
                weight = {"tag_exact": 1.0, "title_phrase": 1.0, "title_words": 0.7,
                          "description": 0.25}[placement]
                captured += q.value * weight

    gaps = [{"phrase": q.phrase, "value": q.value, "intent": q.intent}
            for q in queries if q.reachable and q.phrase not in where][:10]
    return CoverageReport(queries=len(queries),
                          reachable=sum(1 for q in queries if q.reachable),
                          covered=covered, covered_reachable=covered_reachable,
                          captured_value=captured, total_reachable_value=reachable_value,
                          gaps=gaps, where=where)


# ---- tag selection ---------------------------------------------------------


def choose_tags(queries: list[Query], *, must_include: list[str] | None = None) -> list[str]:
    """Spend thirteen slots on the queries we can actually place for.

    A tag over twenty characters is truncated by Etsy mid-word, so a phrase that does not fit
    is dropped rather than mangled -- a slot spent on "mosaic blanket patte" is a slot spent
    on nothing.
    """
    chosen: list[str] = []
    budget: dict[str, int] = {}

    def take(phrase: str) -> None:
        chosen.append(phrase)
        for w in phrase.split():
            budget[w] = budget.get(w, 0) + 1

    for tag in (must_include or []):
        t = tag.strip().lower()
        if t and len(t) <= TAG_MAX_CHARS and t not in chosen:
            take(t)

    ranked = sorted(queries, key=lambda x: (-x.value, x.phrase))

    # Two passes. The first spends slots on distinct concepts under a strict word budget; the
    # second fills whatever is left over with the best remaining phrases. Leaving slots empty
    # to protect diversity trades one waste for another -- an unused tag slot covers nothing
    # at all.
    # The relaxed pass loosens the budget; it does not remove it. Unlimited reuse filled six
    # of thirteen slots with the word "mosaic", which is one query answered six times.
    for limit in (_MAX_SLOTS_PER_WORD, _MAX_SLOTS_PER_WORD + 1):
        for q in ranked:
            if len(chosen) >= TAG_SLOTS:
                break
            if not q.reachable:
                continue
            phrase = _fit_tag(q.phrase)
            if phrase and _acceptable_tag(phrase, chosen, budget, limit):
                take(phrase)
        if len(chosen) >= TAG_SLOTS:
            break
    return chosen[:TAG_SLOTS]


def _fit_tag(phrase: str) -> str | None:
    """Trim to the character limit at a word boundary, or give the slot up."""
    if len(phrase) <= TAG_MAX_CHARS:
        return phrase
    trimmed = ""
    for w in phrase.split():
        candidate = f"{trimmed} {w}".strip()
        if len(candidate) > TAG_MAX_CHARS:
            break
        trimmed = candidate
    return trimmed if len(trimmed.split()) >= 2 else None


# How many of the thirteen slots any single word may appear in. Without a budget the set
# fills with one concept restated: "mosaic blanket", "christmas mosaic", "nordic mosaic",
# "forest mosaic" are four slots answering approximately one query.
_MAX_SLOTS_PER_WORD = 3

# A phrase trimmed to fit the character limit must still be a phrase. "crochet pattern for"
# is not something anyone searches, and it costs a full slot.
_TRAILING_STOPWORDS = frozenset({
    "for", "and", "with", "the", "a", "an", "of", "to", "in", "on", "by", "your", "my",
})


def _acceptable_tag(phrase: str, chosen: list[str], budget: dict[str, int],
                    max_per_word: int = _MAX_SLOTS_PER_WORD) -> bool:
    words = phrase.split()
    if len(words) < 2:
        return False
    if words[-1] in _TRAILING_STOPWORDS:
        return False
    if phrase in chosen:
        return False
    for existing in chosen:
        ew = set(existing.split())
        if set(words) <= ew or ew <= set(words):
            return False   # one tag wholly contains the other; the narrower one is wasted
    return all(budget.get(w, 0) < max_per_word for w in words)


# ---- attributes ------------------------------------------------------------


def listing_attributes(*, category: str, difficulty: str, colors: list[str],
                       season: str | None, terminology: str = "US") -> dict:
    """Etsy's structured attributes, produced from pattern data rather than skipped.

    Attributes are a ranking and filtering input, so leaving them blank is a decision to be
    less findable. Every value here is something the compiled pattern already knows, which
    means they cannot drift away from the product the way hand-entered attributes do.
    """
    return {
        "digital": True,
        "instant_download": True,
        "file_type": "PDF",
        "craft_type": "crochet",
        "pattern_type": category.replace("_", " "),
        "skill_level": difficulty,
        "primary_color": colors[0] if colors else None,
        "secondary_color": colors[1] if len(colors) > 1 else None,
        "occasion": season.split(" (")[0] if season else None,
        "terminology": f"{terminology} terms",
        "includes_chart": True,
        "includes_written_instructions": True,
    }


def check_attributes(attrs: dict) -> list[str]:
    problems: list[str] = []
    for required in ("digital", "file_type", "craft_type", "pattern_type", "skill_level"):
        if not attrs.get(required):
            problems.append(f"SEO_ATTRIBUTE_MISSING: {required}")
    if attrs.get("primary_color") is None:
        problems.append("SEO_ATTRIBUTE_MISSING: primary_color — colour is a filter buyers use")
    return problems
