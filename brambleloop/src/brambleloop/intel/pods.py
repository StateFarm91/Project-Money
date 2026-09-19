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
from dataclasses import dataclass, field

UNCLASSIFIED = "unclassified"


@dataclass(frozen=True)
class Pod:
    """One permanent specialist cell (#312 -- permanent, added to, never pruned for quiet)."""

    key: str
    name: str
    # Ordered most specific first: "stocking" must beat "seasonal", or every Christmas
    # stocking lands in the seasonal pod and the stocking specialist never sees one.
    keywords: tuple[str, ...]
    rubric: tuple[str, ...]

    def matches(self, text: str) -> bool:
        low = (text or "").lower()
        return any(k in low for k in self.keywords)


PODS: tuple[Pod, ...] = (
    Pod("stockings", "Christmas stockings",
        ("stocking",),
        ("cuff and heel construction", "name personalisation", "hanging loop strength",
         "mantel presentation")),
    Pod("ornaments", "Ornaments and tree decor",
        ("ornament", "bauble", "tree decor", "garland", "tree skirt"),
        ("hanging behaviour", "thread weight suitability", "batch giftability",
         "thumbnail legibility at small size")),
    Pod("garments", "Garments and clothing",
        ("cardigan", "sweater", "jumper", "top", "vest", "shrug", "poncho", "dress",
         "pullover"),
        ("fit and ease strategy", "grading across sizes", "seam and shaping method",
         "drape of the stated yarn", "modelled fit coverage")),
    Pod("hats", "Hats and wearables",
        ("hat", "beanie", "headband", "ear warmer", "scarf", "mittens", "gloves", "cowl",
         "slippers", "socks"),
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
         "table runner", "plant hanger"),
        ("washability", "flatness and blocking", "set coherence", "interior styling")),
    Pod("seasonal_gift", "Seasonal and gift products",
        ("christmas", "halloween", "easter", "valentine", "thanksgiving", "advent",
         "gift set", "seasonal"),
        ("seasonal palette", "gift framing", "make-time versus the event",
         "bundle logic")),
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
    for pod in PODS:
        if pod.matches(text):
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
