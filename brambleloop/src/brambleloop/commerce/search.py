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

ASSUMED = "assumed"
OBSERVED_PREFIX = "observed:"
# An observed phrase older than this is stale evidence; it is labelled, not silently trusted.
OBSERVED_MAX_AGE_DAYS = 90


@dataclass(frozen=True)
class Query:
    """One search phrase we might try to cover."""

    phrase: str
    demand: float          # 0-1, relative search volume
    competition: float     # 0-1, how entrenched the incumbents are
    intent: str = "product"    # product | seasonal | technique | gift | category
    # F-020: where the phrase and its numbers came from. "assumed" is every template phrase:
    # its demand and competition are hand-set constants, not observations, and nothing that
    # reads a coverage report may present them as evidence. "observed:<source>" is a phrase
    # read from real listings or search results, with `read_at` the ISO date it was read.
    provenance: str = ASSUMED
    read_at: str | None = None
    family: str = ""

    @property
    def observed(self) -> bool:
        return self.provenance.startswith(OBSERVED_PREFIX)

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
    # "handmade gift crochet pattern" lived here and was removed (F-008): "handmade gift" is
    # finished-item phrasing on a digital pattern. A gift phrase now names the making.
    "gift": [
        ("diy gift crochet pattern", 0.22, 0.52, "gift"),
    ],
    # F-011: the families above yielded nine or ten acceptable tags for most of the catalogue,
    # so four slots of thirteen went unused on every listing. These widen the set with phrases
    # that are true of every product by construction -- it is a crochet pattern, delivered as
    # a PDF, made by the buyer -- and are assumed like every template phrase.
    "object": [
        ("crochet {category}", 0.50, 0.66, "product"),
        ("diy {category}", 0.20, 0.40, "product"),
    ],
    "format": [
        ("pdf crochet pattern", 0.35, 0.60, "product"),
        ("digital download", 0.25, 0.55, "product"),
        ("instant download pdf", 0.18, 0.46, "product"),
        ("printable pdf chart", 0.10, 0.30, "technique"),
        ("yarn craft project", 0.15, 0.40, "product"),
        ("row by row pattern", 0.08, 0.25, "technique"),
        ("fiber art project", 0.08, 0.30, "product"),
    ],
    # Gated on the printed difficulty (F-008): "easy" and "beginner" are claims.
    "skill:beginner": [
        ("easy crochet project", 0.30, 0.62, "product"),
        ("beginner crochet", 0.40, 0.70, "product"),
    ],
    "skill:confident beginner": [
        ("beginner crochet", 0.40, 0.70, "product"),
    ],
    "skill:intermediate": [
        ("intermediate crochet", 0.14, 0.40, "product"),
    ],
    "seasonal:extra": [
        ("{season} diy", 0.22, 0.44, "seasonal"),
        ("{season} craft", 0.20, 0.45, "seasonal"),
        ("diy {season} decor", 0.18, 0.42, "seasonal"),
    ],
}

# The shelf a catalogue category sits on, as buyers phrase it. Assumed, like the templates.
_FAMILY_PHRASES: dict[str, tuple[str, ...]] = {
    "home": ("crochet home decor", "home decor diy"),
    "baby": ("baby crochet diy", "baby shower diy"),
    "toy": ("crochet toy pattern", "stuffed toy diy"),
    "accessory": ("crochet accessories", "diy accessories"),
    "clothing": ("crochet clothing", "wearable crochet"),
    "holiday": ("holiday crochet", "holiday decor diy"),
    "pet": ("pet bed diy", "crochet for pets"),
    "wedding": ("wedding decor diy", "wedding crochet"),
    "flower": ("crochet flowers", "flower applique"),
}
_CATEGORY_FAMILY: dict[str, str] = {
    "mosaic_blanket": "home", "blanket": "home", "graphghan": "home", "basket": "home",
    "coaster": "home", "placemat": "home", "runner": "home", "pillow": "home",
    "wall_decor": "home", "baby": "baby", "nursery": "baby", "amigurumi": "toy",
    "hat": "accessory", "scarf": "accessory", "shawl": "accessory", "bag": "accessory",
    "garment": "clothing", "ornament": "holiday", "stocking": "holiday",
    "seasonal_decor": "holiday", "pet": "pet", "wedding": "wedding", "flower": "flower",
}


def build_query_set(category: str, motifs: list[str], season: str | None,
                    techniques: list[str] | None = None,
                    difficulty: str | None = None) -> list[Query]:
    """Every phrase this product could plausibly answer, with its reachability.

    `techniques` gates the technique families. A query family is only added when the pattern
    genuinely uses that technique -- section 8 asks for *qualified* search share, and a
    listing that ranks for something it is not is a bounce, not a win. `difficulty` gates the
    skill family the same way (F-008): without it no skill phrase is added, because an
    unknown difficulty is not a beginner one. Every phrase here is `assumed` (F-020).
    """
    out: dict[str, Query] = {}
    cat = category.replace("_", " ")

    def add(template: str, demand: float, competition: float, intent: str,
            family: str = "", **kw) -> None:
        try:
            phrase = template.format(category=cat, **kw).strip().lower()
        except KeyError:
            return
        phrase = re.sub(r"\s+", " ", phrase)
        words = phrase.split()
        if len(words) != len(set(words)):
            return   # "shawl shawl pattern": a motif word that is the category word
        if phrase and phrase not in out and not tag_truth(phrase, difficulty=difficulty):
            out[phrase] = Query(phrase, demand, competition, intent, family=family)

    for t, d, c, i in _TEMPLATES["core"]:
        add(t, d, c, i, "core")
    for motif in motifs[:3]:
        for t, d, c, i in _TEMPLATES["motif"]:
            add(t, d, c, i, "motif", motif=motif.lower())
    for technique in ["always"] + [t.lower() for t in (techniques or [])]:
        for t, d, c, i in _TEMPLATES.get(f"technique:{technique}", []):
            add(t, d, c, i, f"technique:{technique}")
    if season:
        s = season.split(" (")[0].lower()
        for t, d, c, i in _TEMPLATES["seasonal"] + _TEMPLATES["seasonal:extra"]:
            add(t, d, c, i, "seasonal", season=s)
    for t, d, c, i in _TEMPLATES["gift"]:
        add(t, d, c, i, "gift")
    for t, d, c, i in _TEMPLATES["object"]:
        add(t, d, c, i, "object")
    for t, d, c, i in _TEMPLATES["format"]:
        add(t, d, c, i, "format")
    if difficulty:
        for t, d, c, i in _TEMPLATES.get(f"skill:{difficulty.lower()}", []):
            add(t, d, c, i, "skill")
    for phrase in _FAMILY_PHRASES.get(_CATEGORY_FAMILY.get(category, ""), ()):
        add(phrase, 0.20, 0.50, "category", "family")
    return sorted(out.values(), key=lambda q: (-q.value, q.phrase))


# ---- truth of a phrase (F-008) ---------------------------------------------

# Finished-item phrasing: this company sells a PDF, and a tag promising a finished object is
# a misdescription however well it ranks.
_FINISHED_ITEM = re.compile(r"\b(handmade gift|ready to ship|finished (item|product)|"
                            r"made to order|gift for (her|him|mom|dad))\b")
_EASY = re.compile(r"\b(easy|simple|quick)\b")
_BEGINNER = re.compile(r"\bbeginners?\b")


def tag_truth(phrase: str, *, difficulty: str | None) -> str | None:
    """Why a phrase may not be claimed for this product, or None when it may.

    Difficulty-gated: "easy" only on a beginner pattern, "beginner" only on a beginner or
    confident-beginner one, "intermediate"/"advanced" only when that is the printed level --
    an unknown difficulty supports none of them. No finished-item phrasing, and a "gift"
    phrase must name the making (pattern, diy, pdf, crochet), never a gift that ships.
    """
    p = (phrase or "").lower()
    level = (difficulty or "").lower()
    if _FINISHED_ITEM.search(p):
        return f"TAG_FINISHED_ITEM: {phrase!r} describes a finished item; this is a pattern"
    if "gift" in p.split() and not ({"pattern", "diy", "pdf", "crochet"} & set(p.split())):
        return f"TAG_FINISHED_ITEM: {phrase!r} offers a gift, not a pattern to make one"
    if _EASY.search(p) and level != "beginner":
        return (f"TAG_DIFFICULTY_UNTRUE: {phrase!r} claims easy on a "
                f"{level or 'unknown-difficulty'} pattern")
    if _BEGINNER.search(p) and level not in ("beginner", "confident beginner"):
        return (f"TAG_DIFFICULTY_UNTRUE: {phrase!r} claims beginner on a "
                f"{level or 'unknown-difficulty'} pattern")
    for word in ("intermediate", "advanced"):
        if word in p.split() and level != word:
            return (f"TAG_DIFFICULTY_UNTRUE: {phrase!r} claims {word} on a "
                    f"{level or 'unknown-difficulty'} pattern")
    return None


def tags_truth(tags: list[str], *, difficulty: str | None) -> list[str]:
    """Blocking findings for a finished tag set, wherever its phrases came from."""
    return [p for p in (tag_truth(t, difficulty=difficulty) for t in tags) if p]


# ---- coverage --------------------------------------------------------------


def _normalise(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", text.lower())


def covers(query: Query, *, title: str, tags: list[str], description: str,
           category_path: list[str] | None = None,
           attribute_values: list[str] | None = None) -> str | None:
    """Where, if anywhere, a query is covered. Order matters: a tag beats a mention.

    `category_path` and `attribute_values` are the structured fields (F-002, F-006): a query
    whose words the chosen category path or a set attribute already supplies is covered by
    that field, which is how Etsy matches it -- a subcategory inherits its parents' names.
    """
    phrase = _normalise(query.phrase)
    words = phrase.split()
    if any(_normalise(t) == phrase for t in tags):
        return "tag_exact"
    if phrase in _normalise(title):
        return "title_phrase"
    if all(w in _normalise(title).split() for w in words):
        return "title_words"
    structured = set(_normalise(" ".join(category_path or [])).split())
    if words and structured and all(w in structured for w in words):
        return "category"
    attrs = set(_normalise(" ".join(attribute_values or [])).split())
    if words and attrs and all(w in (attrs | structured) for w in words):
        return "attribute"
    if phrase in _normalise(description):
        return "description"
    return None


# A description mention is worth far less than a tag or title placement; a structured field
# is as good as a title word, because Etsy matches it the same way.
PLACEMENT_WEIGHT = {"tag_exact": 1.0, "title_phrase": 1.0, "title_words": 0.7,
                    "category": 0.7, "attribute": 0.7, "description": 0.25}


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
    matrix: list[dict] = field(default_factory=list)
    observed_captured: float = 0.0
    observed_reachable: float = 0.0

    @property
    def share(self) -> float:
        return (round(self.captured_value / self.total_reachable_value, 4)
                if self.total_reachable_value else 0.0)

    @property
    def evidence_share(self) -> float | None:
        """Share over observed phrases only (F-015, F-020); None when there are none.

        `share` is computed over assumed template phrases whose demand and competition are
        constants, so it is a planning proxy. This is the only number here resting on
        observation, and an empty observed set is UNMEASURED rather than zero.
        """
        return (round(self.observed_captured / self.observed_reachable, 4)
                if self.observed_reachable else None)

    def to_dict(self) -> dict:
        return {"queries": self.queries, "reachable": self.reachable,
                "covered": self.covered, "covered_reachable": self.covered_reachable,
                "captured_value": round(self.captured_value, 4),
                "total_reachable_value": round(self.total_reachable_value, 4),
                "share": self.share, "share_basis": "assumed+observed (planning proxy)",
                "evidence_share": (self.evidence_share if self.evidence_share is not None
                                   else "UNMEASURED"),
                "gaps": list(self.gaps), "matrix": list(self.matrix)}


def score_coverage(queries: list[Query], *, title: str, tags: list[str],
                   description: str, category_path: list[str] | None = None,
                   attribute_values: list[str] | None = None) -> CoverageReport:
    """How much of the reachable demand this listing actually answers.

    Scored against reachable value rather than all value on purpose. A listing that covers
    every long-tail phrase and misses the head term is doing the right thing for a new shop;
    scoring it against the head term would tell it to do the wrong thing.

    The report carries the whole query -> field matrix (F-002): every phrase, its family, its
    provenance and the field supplying it, or None. It used to compute `where` and drop it.
    """
    where: dict[str, str] = {}
    captured = 0.0
    reachable_value = 0.0
    covered = 0
    covered_reachable = 0
    obs_captured = obs_reachable = 0.0
    matrix: list[dict] = []

    for q in queries:
        placement = covers(q, title=title, tags=tags, description=description,
                           category_path=category_path, attribute_values=attribute_values)
        if q.reachable:
            reachable_value += q.value
            if q.observed:
                obs_reachable += q.value
        matrix.append({"phrase": q.phrase, "family": q.family or q.intent,
                       "intent": q.intent, "provenance": q.provenance,
                       "read_at": q.read_at, "reachable": q.reachable, "field": placement})
        if placement:
            covered += 1
            where[q.phrase] = placement
            if q.reachable:
                covered_reachable += 1
                captured += q.value * PLACEMENT_WEIGHT[placement]
                if q.observed:
                    obs_captured += q.value * PLACEMENT_WEIGHT[placement]

    gaps = [{"phrase": q.phrase, "value": q.value, "intent": q.intent,
             "provenance": q.provenance}
            for q in queries if q.reachable and q.phrase not in where][:10]
    return CoverageReport(queries=len(queries),
                          reachable=sum(1 for q in queries if q.reachable),
                          covered=covered, covered_reachable=covered_reachable,
                          captured_value=captured, total_reachable_value=reachable_value,
                          gaps=gaps, where=where, matrix=matrix,
                          observed_captured=obs_captured, observed_reachable=obs_reachable)


def tag_provenance(tags: list[str], queries: list[Query],
                   observed_tags: list[str] | None = None) -> list[dict]:
    """Where every chosen tag came from (F-020): observed with its source and date, or assumed.

    An assumed tag is labelled, never dropped: it can still earn a slot, but nothing may cite
    it as evidence of demand.
    """
    by_phrase = {q.phrase: q for q in queries}
    observed = set(observed_tags or [])
    out = []
    for t in tags:
        q = by_phrase.get(t)
        if q is None:
            q = next((x for x in queries if x.phrase.startswith(t + " ")), None)
        if t in observed:
            prov = q.provenance if (q and q.observed) else "observed:buyer_language"
        else:
            prov = q.provenance if q else ASSUMED
        out.append({"tag": t, "provenance": prov,
                    "read_at": q.read_at if q else None,
                    "evidence": prov.startswith(OBSERVED_PREFIX)})
    return out


def structured_duplicates(tags: list[str], structured: list[str]) -> list[str]:
    """Tags that only repeat a phrase the category path or an attribute already supplies."""
    have = {_normalise(p).strip() for p in structured if p}
    return [t for t in tags if _normalise(t).strip() in have]


# ---- tag selection ---------------------------------------------------------


def choose_tags(queries: list[Query], *, must_include: list[str] | None = None,
                exclude: list[str] | None = None) -> list[str]:
    """Spend thirteen slots on the queries we can actually place for.

    A tag over twenty characters is truncated by Etsy mid-word, so a phrase that does not fit
    is dropped rather than mangled -- a slot spent on "mosaic blanket patte" is a slot spent
    on nothing. `exclude` is the phrases the structured fields already supply (F-014): a tag
    repeating the category path or an attribute value wastes a slot on a match Etsy already
    makes, so it is never chosen and the slot goes to the next phrase.
    """
    banned = {_normalise(p).strip() for p in (exclude or []) if p}
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
            if phrase and _normalise(phrase).strip() in banned:
                continue
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


# ---- attribute truth (F-008) ----------------------------------------------

def attribute_truth(attrs: dict, *, difficulty: str, colors: list[str],
                    season: str | None) -> list[str]:
    """Blocking findings for an attribute set that claims something the pattern is not.

    `season` is the product's seasonal premise *after* positioning (None for an evergreen
    pivot). Colours must be colours the pattern is worked in; the skill level must be the
    printed difficulty; an occasion needs a seasonal premise; and a digital pattern has no
    recipient or material to claim.
    """
    problems: list[str] = []
    if attrs.get("skill_level") and attrs["skill_level"] != difficulty:
        problems.append(f"ATTRIBUTE_UNTRUE: skill_level {attrs['skill_level']!r} is not the "
                        f"printed difficulty {difficulty!r}")
    for key in ("primary_color", "secondary_color"):
        value = attrs.get(key)
        if value is not None and value not in colors:
            problems.append(f"ATTRIBUTE_UNTRUE: {key} {value!r} is not a colour the pattern "
                            f"is worked in")
    occasion = attrs.get("occasion")
    if occasion and not season:
        problems.append(f"ATTRIBUTE_IRRELEVANT: occasion {occasion!r} on a product with no "
                        f"seasonal premise")
    if occasion and season and occasion != season.split(" (")[0]:
        problems.append(f"ATTRIBUTE_UNTRUE: occasion {occasion!r} is not the product's "
                        f"season {season!r}")
    for key in ("recipient", "material", "materials", "holiday_recipient"):
        if attrs.get(key):
            problems.append(f"ATTRIBUTE_IRRELEVANT: {key} {attrs[key]!r} on a digital pattern")
    if attrs.get("digital") is not True or attrs.get("file_type") != "PDF":
        problems.append("ATTRIBUTE_UNTRUE: the product is a digital PDF")
    return problems


# ---- the search certificate (F-004) ---------------------------------------

PASS = "PASS"
REFUSED = "REFUSED"


def search_certificate(*, category: dict, properties: dict, attribute_problems: list[str],
                       copy_gate: dict, tag_problems: list[str],
                       description_problems: list[str], hero: dict | None = None) -> dict:
    """Holistic search certification: never from title and tags alone.

    Every check must PASS: the category is CHOSEN from a stored Etsy snapshot (UNKNOWN
    refuses -- there is no default node), the node's properties are complete, the attributes
    are true, the copy passes the search-copy gate, the tags are true, the description is not
    a keyword dump, and the hero is ready. `hero` is None at drafting time, when the release's
    frames have not been through the four gates; the certificate is then PENDING on it, and
    `publish.release_gates.search_gate` completes it from the listing-set verdict. PENDING is
    not PASS.
    """
    checks: dict[str, dict] = {
        "category": {"ok": category.get("status") == "CHOSEN",
                     "why": category.get("why", "")},
        "attributes": {"ok": bool(properties.get("complete")) and not attribute_problems,
                       "why": "; ".join(list(properties.get("gaps") or [])[:4]
                                        + attribute_problems[:4])
                              or properties.get("why", "")},
        "copy": {"ok": bool(copy_gate.get("ok")),
                 "why": "; ".join(copy_gate.get("blocking") or [])[:400]},
        "tags": {"ok": not tag_problems, "why": "; ".join(tag_problems)[:400]},
        "description": {"ok": not description_problems,
                        "why": "; ".join(description_problems)[:400]},
        "hero": ({"ok": None, "why": "pending: the hero is judged by the listing-set gates "
                                     "at publish"} if hero is None else
                 {"ok": bool(hero.get("ok")), "why": hero.get("why", "")}),
    }
    failed = [k for k, v in checks.items() if v["ok"] is False]
    pending = [k for k, v in checks.items() if v["ok"] is None]
    verdict = REFUSED if failed else ("PENDING" if pending else PASS)
    return {"verdict": verdict, "checks": checks, "failed": failed, "pending": pending,
            "reasons": [f"{k}: {checks[k]['why']}" for k in failed],
            "basis": "category + attributes + copy + tags + description + hero (F-004)"}


# ---- the hero, judged on the certified listing set, written back (F-004) ----------------

HERO_JUDGED_ACTION = "listing.search_hero_judged"


def _recount(checks: dict) -> dict:
    """Verdict, failed and pending from a full set of checks, as `search_certificate` counts.

    A check whose `ok` is anything but True or False (missing, None, malformed) is pending:
    unjudged evidence is never a pass.
    """
    failed = [k for k, v in checks.items() if isinstance(v, dict) and v.get("ok") is False]
    pending = [k for k, v in checks.items()
               if not isinstance(v, dict) or v.get("ok") not in (True, False)]
    verdict = REFUSED if failed else ("PENDING" if pending else PASS)
    return {"verdict": verdict, "failed": failed, "pending": pending,
            "reasons": [f"{k}: {checks[k].get('why', '')}" for k in failed]}


def _certified_set(db, slug: str, version: str, record_id) -> dict | None:
    """The valid listing-set certificate record `record_id`, reduced to what binds the hero."""
    from sqlalchemy import select

    from ..core.models import ListingSetCertificateRecord, PatternVersion, Product

    if record_id is None:
        return None
    with db.session() as s:
        rec = s.get(ListingSetCertificateRecord, int(record_id))
        if (rec is None or rec.state != "valid" or rec.product_slug != slug
                or rec.version != version):
            return None
        frames = sorted((rec.certificate or {}).get("frames") or [],
                        key=lambda f: int(f.get("position") or 0))
        product = s.scalar(select(Product).where(Product.slug == slug))
        pv = (s.scalar(select(PatternVersion).where(PatternVersion.product_id == product.id,
                                                    PatternVersion.version == version))
              if product is not None else None)
        return {"record_id": rec.id, "release_hash": rec.release_hash or "",
                "pattern_release_hash": (pv.release_hash or "") if pv is not None else None,
                "pattern_certified": bool(pv is not None and pv.certified),
                "frame_1": next((f for f in frames if int(f.get("position") or 0) == 1),
                                None)}


def judge_hero(db, *, slug: str, version: str, set_verdict: dict | None,
               gate: dict | None = None) -> dict:
    """Complete the stored search certificate with the hero, judged on the certified set.

    `listing.seo` writes the certificate before any listing image set is certified, so its
    hero check is PENDING and the stored verdict cannot be PASS. Once a listing-set
    certificate is valid for this release -- the disclosed render set for Launch-0, or the
    gated frames -- frame 1 is judged by the same four gates `release_gates.search_gate`
    reads at publish, and the result is written back to the profile together with the
    evidence it used: the certificate record, frame 1's hash and the release it was issued
    for. PASS is written only when every check passes *and* the publish-time search gate
    passes on the listing as it stands (fingerprint current, category CHOSEN); PENDING is
    never promoted. No valid certificate leaves the hero pending, never passed.
    """
    from datetime import datetime, timezone

    from sqlalchemy import select

    from ..core.models import ListingSearchProfile
    from ..publish.release_gates import search_gate

    with db.session() as s:
        row = s.scalar(select(ListingSearchProfile).where(
            ListingSearchProfile.product_slug == slug,
            ListingSearchProfile.version == version))
        if row is None:
            return {"judged": False, "verdict": None,
                    "why": "listing.seo has recorded no search profile"}
        stored = dict(row.certificate) if isinstance(row.certificate, dict) else {}
    set_verdict = set_verdict or {}
    cert = set_verdict.get("certificate") or {}
    bound = (_certified_set(db, slug, version, cert.get("record_id"))
             if cert.get("valid") is True else None)
    frames = set_verdict.get("frames") or []
    hero_frame = next((f for f in frames if f.get("position") == 1), None)
    evidence = None
    if hero_frame is None:
        hero = {"ok": None, "why": "pending: no frame 1 has been judged by the listing-set "
                                   "gates for this release"}
    elif not hero_frame.get("may_export"):
        hero = {"ok": False, "why": ("frame 1 is not export-ready: "
                                     f"{hero_frame.get('why') or 'a gate did not pass'}")[:300]}
    elif bound is None or bound["frame_1"] is None:
        hero = {"ok": None, "why": ("pending: no valid listing-set certificate covers this "
                                    "release, so frame 1 is not judged on a certified set"
                                    + (f" ({cert.get('why')})" if cert.get("why") else ""))[:300]}
    elif not bound["pattern_certified"] or (bound["release_hash"]
                                            != bound["pattern_release_hash"]):
        hero = {"ok": False, "why": "the listing-set certificate was issued for "
                                    f"release {bound['release_hash'][:12]!r}, not the "
                                    "certified release on file"}
    else:
        evidence = {"listing_set_record_id": bound["record_id"],
                    "release_hash": bound["release_hash"],
                    "frame_1_sha256": bound["frame_1"].get("sha256"),
                    "frame_1_asset_id": bound["frame_1"].get("asset_id"),
                    "frame_1_kind": bound["frame_1"].get("kind", "")}
        hero = {"ok": True, "why": "frame 1 passed all four gates on certified listing set "
                                   f"{bound['record_id']}", "evidence": evidence}
    gate = gate if gate is not None else search_gate(db, slug=slug, version=version,
                                                     set_verdict=set_verdict)
    checks = dict(stored.get("checks")) if isinstance(stored.get("checks"), dict) else {}
    for key in ("category", "attributes", "copy", "tags", "description"):
        if not isinstance(checks.get(key), dict):
            checks[key] = {"ok": None, "why": "required search check missing or malformed"}
    checks["hero"] = hero
    counted = _recount(checks)
    verdict = counted["verdict"]
    gate_reasons = list(gate.get("reasons") or [])
    if verdict == PASS and not (gate.get("ok") is True and evidence is not None):
        # Every stored check passes but the listing as it stands does not (edited copy,
        # UNKNOWN category): the certificate does not describe it, so it is refused.
        verdict = REFUSED
    completed = {**stored, "checks": checks, "verdict": verdict,
                 "failed": counted["failed"], "pending": counted["pending"],
                 "reasons": counted["reasons"] + ([r for r in gate_reasons]
                                                  if verdict == REFUSED else []),
                 "hero_evidence": evidence,
                 "hero_judged_at": datetime.now(timezone.utc).isoformat(),
                 "basis": stored.get("basis") or
                 "category + attributes + copy + tags + description + hero (F-004)"}
    import json as _json

    with db.session() as s:
        row = s.scalar(select(ListingSearchProfile).where(
            ListingSearchProfile.product_slug == slug,
            ListingSearchProfile.version == version))
        completed["bound_fingerprint"] = row.fingerprint
        row.verdict = verdict
        row.certificate = _json.loads(_json.dumps(completed, default=str))
        row.updated_at = datetime.now(timezone.utc)
    return {"judged": hero.get("ok") is not None, "verdict": verdict,
            "hero": hero, "evidence": evidence, "gate_ok": gate.get("ok") is True,
            "reasons": completed["reasons"][:6]}


def stored_pass_problems(db, *, slug: str, version: str, row=None) -> list[str]:
    """Why a stored PASS no longer describes this listing; empty when it still does.

    A PASS is bound to the listing-set certificate it judged the hero on and to the listing
    copy it certified. Either changing -- the set superseded or invalidated, the release
    re-certified, the title/description/tags/taxonomy/properties edited -- leaves the stored
    verdict describing something else, and it is not a PASS for what would be sent.
    """
    from sqlalchemy import select

    from ..core.models import Listing, ListingSearchProfile
    from ..publish.release_gates import search_fingerprint

    with db.session() as s:
        if row is None:
            row = s.scalar(select(ListingSearchProfile).where(
                ListingSearchProfile.product_slug == slug,
                ListingSearchProfile.version == version))
        if row is None:
            return ["no search profile"]
        if row.verdict != PASS:
            return [f"stored search verdict is {row.verdict}, not PASS"]
        cert = row.certificate if isinstance(row.certificate, dict) else {}
        listing = s.scalar(select(Listing).where(Listing.product_slug == slug,
                                                 Listing.version == version))
        listing_now = (None if listing is None else search_fingerprint(
            title=listing.title, description=listing.description, tags=listing.tags,
            taxonomy_id=row.taxonomy_id, properties=row.properties))
        fingerprint = row.fingerprint
    problems: list[str] = []
    checks = cert.get("checks") if isinstance(cert.get("checks"), dict) else {}
    if _recount(checks)["verdict"] != PASS or set(checks) < {
            "category", "attributes", "copy", "tags", "description", "hero"}:
        problems.append("stored PASS is not backed by a full set of passing checks")
    if listing_now is None or listing_now != fingerprint \
            or cert.get("bound_fingerprint") != fingerprint:
        problems.append("the listing changed after search certification (F-294)")
    evidence = cert.get("hero_evidence") if isinstance(cert.get("hero_evidence"), dict) else None
    if evidence is None:
        problems.append("the hero was never judged on a certified listing set")
    else:
        bound = _certified_set(db, slug, version, evidence.get("listing_set_record_id"))
        if bound is None:
            problems.append("the listing-set certificate the hero was judged on is no longer "
                            "valid")
        elif ((bound["frame_1"] or {}).get("sha256") != evidence.get("frame_1_sha256")
              or bound["release_hash"] != evidence.get("release_hash")
              or bound["release_hash"] != bound["pattern_release_hash"]
              or not bound["pattern_certified"]):
            problems.append("the hero evidence no longer matches the certified set and release")
    return problems
