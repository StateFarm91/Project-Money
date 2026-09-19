"""Specialist category pods, and the director that stops them becoming silos.

Requirements 210, 211, 214, 217, 312. The mandate asks for independent specialist cells per
product department, each owning its own history, rubric and opportunity map, and a central
director that deduplicates, routes and holds the company-level view of where Brambleloop is
ahead, at parity or materially behind.

Two things this module refuses to do, both because the alternative is the kind of answer that
looks like intelligence and is not:

**An unclassified listing is not quietly dropped into the nearest pod.** It goes to
`unclassified`, which is a real pod with a real queue, because a market map whose gaps are
invisible reports full coverage of whatever it happened to understand (#207 wants coverage
gaps explicit).

**A dimension with no evidence is `unknown`, never `parity`.** Parity is a finding. Defaulting
to it means a company that has never looked at its benchmark reports itself as level with it,
which is the most comfortable possible wrong answer.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field

UNCLASSIFIED = "unclassified"

# Matching used to be `keyword in text.lower()`, and a substring test fails in both
# directions at once. It missed "Crochet Slipper Boot Pattern" because the keyword was
# "slippers", and "Winter Wonder Cable Mitten Pattern" because the keyword was "mittens" --
# two listings a human would route without hesitating. In the other direction "vest" is
# inside "harvest", "hat" is inside "what", and "top" is inside "tree topper", so a fall
# decor listing could be routed to the garment specialist and nobody would ever see it
# happen, because a wrong pod looks exactly like a right one from the outside.
#
# So matching is on words, with singulars and plurals treated as the same word. The cost of
# the looser rule is a false positive that is invisible; the cost of the stricter one is an
# unclassified listing, which is visible by construction (#207).

_WORD = re.compile(r"[a-z0-9]+")

# "6 Granny Stitch Patterns", "10 Pattern Ebook", "3 pattern Crochet Pattern Ebook": a title
# that counts its own patterns is selling a bundle, whatever the products inside it are.
_COUNTS_PATTERNS = re.compile(r"\b\d+\s+(?:[a-z]+\s+){0,3}patterns?\b")


def _singular(word: str) -> str:
    """One canonical form per word, so "slipper" and "slippers" are the same keyword."""
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if word.endswith("ss") or len(word) <= 3:
        return word
    if word.endswith("es") and word[-3:-2] in ("s", "x", "z", "h"):
        return word[:-2]
    if word.endswith("s"):
        return word[:-1]
    return word


def _words(text: str) -> list[str]:
    return [_singular(w) for w in _WORD.findall((text or "").lower())]


def signals(text: str) -> tuple[frozenset[str], str]:
    """What a title offers a router: its words, and the phrase-searchable form of them.

    Computed once per listing rather than once per pod, because the router runs over a whole
    benchmark catalogue and the pods are consulted in order until one answers.
    """
    words = _words(text)
    return frozenset(words), " ".join(words)


def counts_its_own_patterns(text: str) -> bool:
    """True when the title states how many patterns it contains."""
    return bool(_COUNTS_PATTERNS.search(" ".join(_WORD.findall((text or "").lower()))))


@dataclass(frozen=True)
class Pod:
    """One permanent specialist cell (#312 -- permanent, added to, never pruned for quiet)."""

    key: str
    name: str
    # Ordered most specific first: "stocking" must beat "seasonal", or every Christmas
    # stocking lands in the seasonal pod and the stocking specialist never sees one.
    keywords: tuple[str, ...]
    rubric: tuple[str, ...]
    # Words that describe what a product *depicts*, never what it *is*: pumpkin, gnome,
    # snowman, Christmas. They are consulted only after every pod's form words have failed.
    #
    # This is the second half of the substring lesson. Adding "pumpkin" to the soft-sculpture
    # pod routed "Hello Pumpkin Mosaic Cardigan" and "Pumpkin Pillow Crochet Pattern" to
    # amigurumi -- a cardigan and a cushion, sent to the specialist in stuffing firmness,
    # invisibly, by a fix for exactly that class of error. A motif is not a form, and a form
    # word beats a motif word wherever both appear.
    motifs: tuple[str, ...] = ()
    # Set on the pod that answers for multi-pattern bundles, so a title that counts its own
    # patterns reaches it even when it names no product this vocabulary knows.
    claims_counted_bundles: bool = False

    def matches(self, text: str) -> bool:
        words, phrase = signals(text)
        return (self.matches_signals(words, phrase)
                or self.matches_motifs(words, phrase)
                or (self.claims_counted_bundles and counts_its_own_patterns(text)))

    def _any(self, terms: tuple[str, ...], words: frozenset[str], phrase: str) -> bool:
        for term in terms:
            if " " in term:
                if " ".join(_words(term)) in phrase:
                    return True
            elif _singular(term) in words:
                return True
        return False

    def matches_signals(self, words: frozenset[str], phrase: str) -> bool:
        """Form words only: what the object is."""
        return self._any(self.keywords, words, phrase)

    def matches_motifs(self, words: frozenset[str], phrase: str) -> bool:
        """Motif words only: what the object depicts, or when it is sold."""
        return self._any(self.motifs, words, phrase)


# Ordered most specific first, and every keyword below is a word that appears in an observed
# MJs title. The vocabulary is not allowed to grow from imagination: a keyword nothing matches
# widens the table without widening coverage, and it does it invisibly.
PODS: tuple[Pod, ...] = (
    # First, because a guidebook about sizing is an education product that happens to be a
    # PDF, and the ebook keywords below would otherwise claim it.
    Pod("education", "Education and guidebooks",
        ("guidebook", "guide book", "masterclass", "crochet course", "crochet workshop"),
        ("what the reader can do afterwards", "worked examples over assertions",
         "standalone value without a pattern purchase", "revision and errata policy")),
    # Second, because a six-pattern ebook is a bundle first and a garment second. Routing it
    # to whichever product its title mentions first puts a bundle in a product pod and hides
    # the mechanism -- and bundling is the mechanism MJs uses most visibly.
    Pod("collections", "Multi-pattern collections and ebooks",
        ("ebook", "e book", "pattern collection", "pattern ebook", "collection ebook",
         "crochet collection", "pattern bundle", "pattern pack"),
        ("what holds the set together", "price against the sum of its parts",
         "whether the anchor pattern is the strongest", "seasonal shelf life of the set"),
        claims_counted_bundles=True),
    Pod("stockings", "Christmas stockings",
        ("stocking",),
        ("cuff and heel construction", "name personalisation", "hanging loop strength",
         "mantel presentation")),
    Pod("ornaments", "Ornaments and tree decor",
        ("ornament", "bauble", "tree decor", "garland", "tree skirt"),
        ("hanging behaviour", "thread weight suitability", "batch giftability",
         "thumbnail legibility at small size")),
    # Kitchen and bath textiles: fourteen of the fifty-eight listings the old vocabulary
    # dropped. They are not "home decor" in any useful sense -- they are consumable,
    # washable, stash-busting and bought in sets, and they are the fastest giftables in the
    # benchmark catalogue, which makes them directly relevant to a compressed Christmas.
    Pod("kitchen_bath", "Kitchen and bath textiles",
        ("dishcloth", "dish cloth", "washcloth", "wash cloth", "facecloth", "face cloth",
         "scrubby", "scrubbie", "scrubber", "tea towel", "towel holder", "potholder",
         "pot holder", "hot pad", "trivet", "apron", "mug cozy", "cup cozy",
         "bottle cozy", "coffee cozy"),
        ("absorbency and fibre honesty", "wash and shrink behaviour",
         "set and colourway coherence", "stash-busting yardage",
         "make time against a gifting deadline")),
    # Soft sculpture: amigurumi proper, and the stuffed seasonal objects made the same way.
    # A crochet pumpkin is not decor the way a table runner is decor; it is shaped, stuffed
    # and graded by size, and the specialist who answers for a snowman answers for it.
    Pod("amigurumi", "Amigurumi and soft sculpture",
        ("amigurumi", "plushie", "lovey", "stuffie", "softie", "doll", "rattle", "teether"),
        ("stuffing firmness and seam invisibility", "safety of attached parts",
         "shaping without a chart", "stability when set down", "batch giftability"),
        # Motifs, not forms. "Hello Pumpkin Mosaic Cardigan" and "Pumpkin Pillow Crochet
        # Pattern" are both in the live catalogue; so is "Plush and Blush Crop Top", where
        # "plush" is a colour name. A motif decides only when nothing says what the object is.
        motifs=("gnome", "snowman", "mushroom", "acorn", "pumpkin", "plush", "toy",
                "scarecrow", "reindeer", "bunny", "chick")),
    Pod("garments", "Garments and clothing",
        ("cardigan", "sweater", "jumper", "top", "vest", "shrug", "poncho", "dress",
         "pullover", "shawl", "wrap", "ruana", "skirt", "coverup", "cover up", "kimono",
         "tank", "cropped"),
        ("fit and ease strategy", "grading across sizes", "seam and shaping method",
         "drape of the stated yarn", "modelled fit coverage")),
    Pod("hats", "Hats and wearables",
        ("hat", "beanie", "toque", "tuque", "headband", "ear warmer", "scarf", "mitten",
         "glove", "cowl", "slipper", "sock", "bootie", "scrunchie", "hair tie", "bandana",
         "balaclava"),
        ("head circumference grading", "brim behaviour", "stretch recovery",
         "quick-gift make time")),
    Pod("blankets", "Blankets and throws",
        ("blanket", "throw", "afghan", "quilt"),
        ("finished size honesty", "yardage estimation", "edge treatment",
         "colour architecture across a large field")),
    Pod("bags", "Bags and accessories",
        ("bag", "tote", "purse", "backpack", "pouch", "basket"),
        ("structure and stability", "strap and handle strength", "lining guidance",
         "load-bearing claims")),
    Pod("home_decor", "Home and decor",
        ("coaster", "placemat", "pillow", "cushion", "wall hanging", "rug", "doily",
         "table runner", "plant hanger", "pouf", "poof", "ottoman", "wreath", "banner",
         "bunting"),
        ("washability", "flatness and blocking", "set coherence", "interior styling")),
    # Last, and motif-only but for the one form it owns. "Christmas" says when a product
    # sells, not what it is, so a Christmas stocking is a stocking and a Christmas blanket is
    # a blanket -- both were already true by ordering, and are now true by construction.
    Pod("seasonal_gift", "Seasonal and gift products",
        ("gift set", "advent calendar", "gift tag"),
        ("seasonal palette", "gift framing", "make-time versus the event",
         "bundle logic"),
        motifs=("christmas", "halloween", "easter", "valentine", "thanksgiving", "advent",
                "seasonal", "festive")),
)

POD_KEYS: tuple[str, ...] = tuple(p.key for p in PODS) + (UNCLASSIFIED,)
BY_KEY: dict[str, Pod] = {p.key: p for p in PODS}


def route(title: str, product_type: str = "") -> str:
    """Assign a listing to the pod that answers for it.

    Deterministic and ordered, so the same listing always reaches the same specialist. The
    ordering in `PODS` is the priority: a Christmas stocking is a stocking first, because the
    stocking specialist is the one who knows about heel construction.
    """
    text = f"{title} {product_type}"
    words, phrase = signals(text)
    counted = counts_its_own_patterns(text)
    # Two passes, and the order between them matters more than the order within them. Every
    # pod is asked what the object *is* before any pod is asked what it *depicts*, so a
    # cardigan with a pumpkin on it reaches the garment specialist and a pumpkin reaches the
    # soft-sculpture one.
    for pod in PODS:
        if pod.matches_signals(words, phrase):
            return pod.key
        if counted and pod.claims_counted_bundles:
            return pod.key
    for pod in PODS:
        if pod.matches_motifs(words, phrase):
            return pod.key
    return UNCLASSIFIED


def fingerprint(payload: dict) -> str:
    """Content identity for an observation, so unchanged content is not paid for twice (#212)."""
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Mechanism lessons (#217)
#
# What may be learned from a competitor is *how the merchandising works*, never the protected
# expression. The vocabulary is closed for the same reason evidence kinds are: an open field
# accepts "the stitch instructions for row 14", and the rule that stops it has to be
# mechanical rather than remembered.

MECHANISMS: tuple[str, ...] = (
    "silhouette_strength", "fit_strategy", "styling", "colour_architecture",
    "photography_coverage", "product_family_logic", "beginner_support", "seasonal_timing",
    "thumbnail_clarity", "merchandising", "bundle_logic", "customer_promise",
    "size_presentation", "delivery_format",
)

# Phrases that mean somebody is storing the competitor's product rather than a lesson about
# it. Checked on the free-text note, because that is where it would actually appear.
_PROTECTED_EXPRESSION = (
    "row 1", "row 2", "ch 3", "chain 3", "sc in each", "dc in each", "stitch count",
    "written instructions", "their chart", "pattern text", "copy the pattern",
    "transcribe", "verbatim",
)


class MechanismRefused(Exception):
    """A lesson that is not a mechanism, or that carries a competitor's expression."""


def check_expression(text: str) -> None:
    """Refuse text that is really a competitor's instructions rather than an observation.

    Extracted from `lesson()` so the pods' learning memory can hold the same boundary rather
    than a copy of it. A boundary that exists twice is a boundary that drifts, and the copy
    that drifts is always the newer one.
    """
    low = (text or "").lower()
    for phrase in _PROTECTED_EXPRESSION:
        if phrase in low:
            raise MechanismRefused(
                f"the note contains {phrase!r}, which reads as a competitor's instructions "
                f"rather than an observation about merchandising. Competitor research is for "
                f"demand and merchandising intelligence only")


@dataclass(frozen=True)
class Lesson:
    pod: str
    mechanism: str
    note: str
    evidence_ref: str = ""

    def to_dict(self) -> dict:
        return {"pod": self.pod, "mechanism": self.mechanism, "note": self.note,
                "evidence_ref": self.evidence_ref}


def lesson(pod: str, mechanism: str, note: str, evidence_ref: str = "") -> Lesson:
    """Build a mechanism-level lesson, refusing anything that is really a copy.

    The refusal is deliberately blunt. A competitor's row-by-row instructions are protected
    expression and the standing constraint against copying them is not re-decidable, so the
    check runs at the point of writing rather than at some later review nobody schedules.
    """
    if mechanism not in MECHANISMS:
        raise MechanismRefused(
            f"{mechanism!r} is not a mechanism. Lessons are stored at the mechanism level "
            f"(#217); an open vocabulary is how a competitor's pattern ends up in this table")
    if pod not in POD_KEYS:
        raise MechanismRefused(f"unknown pod {pod!r}")
    check_expression(note)
    if len(note.strip()) < 10:
        raise MechanismRefused("a lesson with no substance is not a lesson")
    return Lesson(pod=pod, mechanism=mechanism, note=note.strip(),
                  evidence_ref=evidence_ref)


# ---------------------------------------------------------------------------
# The director (#211)

AHEAD, PARITY, BEHIND, UNKNOWN = "ahead", "parity", "behind", "unknown"

# The dimensions the company is allowed to claim a position on. Concrete, because "brand
# strength" is not a thing evidence can settle.
DIMENSIONS: tuple[str, ...] = (
    "catalogue_breadth", "photography_coverage", "thumbnail_clarity", "seasonal_timing",
    "size_presentation", "beginner_support", "delivery_format",
)


@dataclass
class Director:
    """Coordinates the pods: deduplicates, routes, and holds the company-level view."""

    seen: set[str] = field(default_factory=set)

    def route_observation(self, title: str, product_type: str = "") -> str:
        return route(title, product_type)

    def is_duplicate(self, payload: dict) -> bool:
        """True when this exact content has already been processed.

        #212 and #225: unchanged listings must not be re-reasoned over. The director is the
        right place for it because two pods can be handed the same cross-category listing.
        """
        fp = fingerprint(payload)
        if fp in self.seen:
            return True
        self.seen.add(fp)
        return False

    @staticmethod
    def cross_category(lessons: list[Lesson], min_pods: int = 2) -> list[dict]:
        """Mechanisms observed in more than one pod -- the thing siloed cells cannot see."""
        by_mechanism: dict[str, set[str]] = {}
        for le in lessons:
            by_mechanism.setdefault(le.mechanism, set()).add(le.pod)
        out = [{"mechanism": m, "pods": sorted(p)}
               for m, p in by_mechanism.items() if len(p) >= min_pods]
        return sorted(out, key=lambda d: (-len(d["pods"]), d["mechanism"]))

    @staticmethod
    def position(dimension: str, ours: float | None, theirs: float | None,
                 *, margin: float = 0.15) -> str:
        """Where the company stands on one concrete dimension.

        Missing evidence on either side is `unknown`. Defaulting to parity would let a company
        that has never looked at its benchmark report itself level with it, which is the most
        comfortable wrong answer available and therefore the one to guard against.
        """
        if dimension not in DIMENSIONS:
            raise ValueError(f"{dimension!r} is not a dimension evidence can settle")
        if ours is None or theirs is None:
            return UNKNOWN
        if theirs == 0:
            return UNKNOWN if ours == 0 else AHEAD
        ratio = ours / theirs
        if ratio >= 1 + margin:
            return AHEAD
        if ratio <= 1 - margin:
            return BEHIND
        return PARITY

    def standing(self, ours: dict[str, float | None],
                 theirs: dict[str, float | None]) -> dict[str, str]:
        return {d: self.position(d, ours.get(d), theirs.get(d)) for d in DIMENSIONS}
