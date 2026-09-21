"""Selling what already exists into a new season, without pretending it is a new product.

Requirement 292. Periodically inspect proven evergreen products for legitimate seasonal
re-merchandising: new colourways, styled photography, bundles, compatible add-ons, seasonal
search positioning. The requirement's closing instruction is the interesting one -- avoid
unnecessary new product creation -- and it is the opposite of the instinct. Making something
new is more satisfying than re-photographing something old, and it is usually the worse trade:
an existing certified pattern has already paid for its engineering, its physical test and its
gates, and a seasonal colourway costs a photograph.

Two rules keep this honest.

**A re-merchandising move is never counted as a new product.** This is the whole risk. A
recolour presented as a launch inflates every number the company steers by: catalogue size,
release rate, the apparent breadth of a collection. The concept engine already scores a pure
recolour at zero distance, and this module refuses to describe one as anything else.

**"Proven" is a claim about sales, and this company has none.** So candidates are *eligible*
rather than proven, and the difference is stated on every row. Re-merchandising an unproven
product is not forbidden -- with no sales at all, everything is unproven and the work still
has to start somewhere -- but calling it proven would be the sentence that makes the whole
exercise fiction.
"""
from __future__ import annotations

from dataclasses import dataclass

# The moves that re-merchandise rather than re-engineer. Each keeps the pattern identical:
# same construction, same rows, same stitch counts, same certificate.
MOVES: dict[str, str] = {
    "colourway": "the same pattern photographed and listed in a seasonal palette",
    "styled_photography": "the same object styled for the occasion it is being sold into",
    "bundle": "sold with an existing product a buyer would want alongside it",
    "add_on": "a small existing make offered as a companion",
    "search_positioning": "seasonal buyer language added to the listing's own vocabulary",
}

# What each move needs before it can happen. Named so a move nobody can do is visible as
# blocked rather than quietly missing from the list.
MOVE_NEEDS: dict[str, str] = {
    "colourway": "a rendered image in the new palette",
    "styled_photography": "an image-generation or photography capability",
    "bundle": "a second certified product",
    "add_on": "a second certified product in a faster make lane",
    "search_positioning": "the buyer-language map for the occasion",
}

# Fields a re-merchandising move may never change. Changing one makes it a new product, which
# is a different pipeline with a tournament, a compile and a physical test in it.
IMMUTABLE: tuple[str, ...] = ("construction", "form", "rows", "stitch_counts", "gauge",
                              "release_hash")


class RemerchandisingRefused(ValueError):
    """A new product wearing a re-merchandising label, or a claim of proof without sales."""


@dataclass(frozen=True)
class Candidate:
    slug: str
    title: str
    certified: bool
    orders: int

    @property
    def proven(self) -> bool:
        return self.orders > 0


def candidates(db) -> dict:
    """Certified products that could be sold into a season, with proof stated honestly."""
    from sqlalchemy import select

    from ..core.models import LedgerEntry, PatternVersion, Product

    with db.session() as s:
        products = list(s.scalars(select(Product)))
        certified = {v.product_id for v in s.scalars(select(PatternVersion))
                     if getattr(v, "certified", False)}
        sales = [e for e in s.scalars(select(LedgerEntry))
                 if e.category == "sale"]

    by_slug: dict[str, int] = {}
    for sale in sales:
        ref = (sale.evidence_ref or "")
        for product in products:
            if product.slug and product.slug in ref:
                by_slug[product.slug] = by_slug.get(product.slug, 0) + 1

    rows = [Candidate(slug=p.slug, title=p.title, certified=p.id in certified,
                      orders=by_slug.get(p.slug, 0))
            for p in products]
    eligible = [c for c in rows if c.certified]
    proven = [c for c in eligible if c.proven]

    return {
        "products": len(rows),
        "eligible": [{"slug": c.slug, "title": c.title, "orders": c.orders,
                      "proven": c.proven} for c in eligible],
        "proven": [c.slug for c in proven],
        "proof_measurable": bool(sales),
        "note": ("no sale has been recorded, so 'proven' cannot be established and every "
                 "candidate here is eligible rather than proven. Re-merchandising an "
                 "unproven product is not forbidden -- with no sales at all, everything is "
                 "unproven and the work still has to start somewhere -- but calling it "
                 "proven is the sentence that makes the exercise fiction"
                 if not sales else
                 f"{len(proven)} of {len(eligible)} certified products have recorded sales"),
    }


def moves_for(candidate: dict, *, available: tuple[str, ...] = ()) -> list[dict]:
    """Which re-merchandising moves this product could take, and what each is waiting on."""
    out = []
    for move, what in MOVES.items():
        ready = move in available
        out.append({
            "move": move, "what": what, "needs": MOVE_NEEDS[move], "available": ready,
            "counts_as_new_product": False,
        })
    return out


def check_move(*, move: str, changes: tuple[str, ...]) -> dict:
    """Refuse a move that changes the pattern. That is a new product, not a new photograph."""
    if move not in MOVES:
        raise RemerchandisingRefused(
            f"{move!r} is not a re-merchandising move: {sorted(MOVES)}")
    illegal = [field for field in changes if field in IMMUTABLE]
    if illegal:
        raise RemerchandisingRefused(
            f"this move changes {illegal}, which makes it a new product rather than a new "
            f"presentation of an existing one. That is a different pipeline, with a "
            f"tournament, a compile and a physical test in it, and routing it through here "
            f"would put an unengineered product in front of a buyer")
    return {"move": move, "changes": list(changes), "counts_as_new_product": False,
            "note": ("a re-merchandising move never increments the catalogue: a recolour "
                     "presented as a launch inflates catalogue size, release rate and the "
                     "apparent breadth of a collection all at once")}


def plan(db, *, event: str, available: tuple[str, ...] | None = None,
         pod: str = "", benchmark_key: str = "") -> dict:
    """Every re-merchandising opportunity for one occasion, with proof stated as it is.

    Availability is computed unless a caller insists otherwise. It used to default to the
    empty tuple, so the endpoint -- which passed nothing -- reported every move unavailable
    whatever the company could actually do, and went on reporting it after the capability
    arrived. `capabilities()` was written to stop a review taking its capability list from
    its caller; `plan()` was never wired to it, which left the same defect one layer up
    with the fix sitting next to it.
    """
    if available is None:
        available = tuple(capabilities(db, pod=pod, benchmark_key=benchmark_key)["available"])
    pool = candidates(db)
    rows = [{"slug": c["slug"], "title": c["title"], "proven": c["proven"],
             "moves": moves_for(c, available=available)}
            for c in pool["eligible"]]
    ready = sum(1 for r in rows for m in r["moves"] if m["available"])
    return {
        "event": event,
        "candidates": rows,
        "proof_measurable": pool["proof_measurable"],
        "available_moves": sorted(available),
        "ready_moves": ready,
        "catalogue_growth": 0,
        "note": (
            "no certified product exists to re-merchandise yet" if not rows else
            f"{len(rows)} candidate(s) and {ready} move(s) that can be taken today. "
            f"Re-merchandising never increments the catalogue: an existing certified pattern "
            f"has already paid for its engineering, its physical test and its gates, and a "
            f"seasonal colourway costs a photograph (#292)"),
    }


# ---------------------------------------------------------------------------
# What is actually available today (#292)
#
# `plan()` took `available` from its caller, which meant the answer to "what can we do this
# season" depended on what the caller believed rather than on what the company can do. That
# is the same shape as a gate reading a configured variable instead of a recorded success:
# it produces a confident list that nobody checked.
#
# So availability is computed from evidence. `search_positioning` became genuinely available
# on 2026-09-20, when the benchmark credential made a per-occasion buyer-language map
# readable; the two image moves are still blocked and say what on.


def capabilities(db, *, pod: str = "", benchmark_key: str = "") -> dict:
    """Which of the five moves the company can actually take, and what the rest wait on.

    Each answer is a reading rather than a setting. A move reported available here is one
    whose prerequisite has been observed to exist, not one somebody enabled.
    """
    from ..commerce import intent
    from ..gateway import images

    pool = candidates(db)
    certified = len(pool["eligible"])

    # Asked, or not asked. The distinction is the whole reason this is three-valued: the
    # buyer-language map is per-occasion, so with no pod named nobody looked -- and
    # reporting that as `available: False, waiting_on: the buyer-language map` says the
    # company lacks a capability it has had since 2026-09-20. `/api/seasonal/remerchandising`
    # passed no pod by default and had been printing exactly that, which is a verdict
    # computed from a question nobody asked.
    asked = bool(pod)
    language = (intent.arena_language(db, pod=pod, benchmark_key=benchmark_key) if asked
                else {"measurable": False})

    # Both image moves wait on the same capability, read from evidence: a recorded
    # successful generation, not a variable.
    #
    # This asked `os.environ.get("BRAMBLELOOP_IMAGE_KEY")` until 2026-09-21, and that
    # variable stopped existing when credentials moved to one key per provider account. So
    # a capability that had been rendering in production for a day read as absent here, and
    # two requirements stayed parked on it -- the familiar defect (a gate reading
    # configuration rather than demonstrated capability) with an extra twist: the
    # configuration it read had been renamed out from under it, so the check could no
    # longer come true at all.
    can_render = images.usable(db)
    state: dict[str, dict] = {
        "colourway": {
            "available": can_render,
            "waiting_on": MOVE_NEEDS["colourway"],
            "evidence": "a recorded successful image generation (ops.capability_probes)"},
        "styled_photography": {
            "available": can_render,
            "waiting_on": MOVE_NEEDS["styled_photography"],
            "evidence": "a recorded successful image generation (ops.capability_probes)"},
        # A bundle of one product is a product. Two certified products is the real floor and
        # it is a count, not a judgement.
        "bundle": {"available": certified >= 2,
                   "waiting_on": MOVE_NEEDS["bundle"],
                   "certified_products": certified},
        "add_on": {"available": certified >= 2,
                   "waiting_on": MOVE_NEEDS["add_on"],
                   "certified_products": certified},
        "search_positioning": {
            "available": asked and bool(language.get("measurable")),
            "measurable": asked,
            "waiting_on": (MOVE_NEEDS["search_positioning"] if asked else
                           "an occasion to read it for -- no pod was named, so nobody "
                           "looked. This is unmeasurable, not unavailable"),
            "pod": pod or None,
            "note": ("the buyer-language map became readable on 2026-09-20, when the "
                     "benchmark credential made a department's observed titles countable"),
        },
    }
    unmeasurable = {k: v["waiting_on"] for k, v in state.items()
                    if not v["available"] and v.get("measurable") is False}
    return {
        "moves": state,
        "available": tuple(sorted(k for k, v in state.items() if v["available"])),
        # Blocked means the prerequisite was looked for and is not there. A move nobody
        # asked about is not blocked, and folding the two together is how a report says
        # "the company cannot do this" when it means "nobody named an occasion".
        "blocked": {k: v["waiting_on"] for k, v in state.items()
                    if not v["available"] and k not in unmeasurable},
        "unmeasurable": unmeasurable,
        "note": ("Read rather than set. A move is available because its prerequisite was "
                 "observed to exist, which is a different claim from somebody having "
                 "enabled it (#292)."),
    }


def review(db, *, event: str, pod: str = "", benchmark_key: str = "") -> dict:
    """The periodic inspection #292 asks for, with availability computed rather than passed.

    "Periodically inspect proven evergreen products" is a cadence, not a function somebody
    remembers to call, and a review that took its own capability list as an argument was
    only ever as honest as its caller.
    """
    from ..creative.audit import concept_from_design
    from ..products.builder import CATALOGUE

    state = capabilities(db, pod=pod, benchmark_key=benchmark_key)
    report = plan(db, event=event, available=state["available"])
    report["capabilities"] = state
    report["inspected_pod"] = pod or None

    # Concrete pairs rather than a `bundle: available` flag. The form and lane of each
    # certified product are read from the design it was built from, so a pair is never made
    # from a guessed form.
    forms, lanes = {}, {}
    for design in CATALOGUE.values():
        concept = concept_from_design(design)
        forms[concept.key] = concept.form
        lanes[concept.key] = concept.make_lane
    report["bundles"] = bundle_pairs(db, forms=forms, lanes=lanes)
    return report


# ---------------------------------------------------------------------------
# A bundle opportunity is a pair, not a checkbox (#292)
#
# `moves_for` reported `bundle: available` once two certified products existed, which is
# true and useless: it says the company *could* bundle something without saying what with
# what. The requirement asks for inspection of opportunities, and an opportunity a reader
# cannot act on is a checkbox.

# Forms that genuinely sit together in one purchase, as a room or an outfit rather than as a
# discount. Each pair is a reason somebody buys both, and the reason is stated because a
# bundle whose logic nobody can say is a discount with extra steps.
COMPLEMENTS: tuple[tuple[str, str, str], ...] = (
    ("rectangle_throw", "pillow", "the two objects a sofa is dressed with"),
    ("rectangle_throw", "coaster", "a whole living-room surface, blanket and table"),
    ("runner", "coaster", "one table, dressed"),
    ("runner", "pillow", "a dining room and the chairs in it"),
    ("wall_hanging", "pillow", "two soft-furnishing gestures in one room"),
    ("garland", "ornament", "one tree, or one mantel, finished"),
    ("garland", "stocking", "a mantel dressed for the occasion"),
    ("stocking", "ornament", "the two things a Christmas mantel carries"),
    ("hat", "scarf", "the pair a person puts on together"),
    ("hat", "bag", "an outfit's accessories"),
    ("fitted_garment", "hat", "a garment and the accessory that finishes it"),
    ("draped_garment", "bag", "a garment and the accessory that finishes it"),
    ("toy", "flat_panel", "a soft toy and the mat it belongs on"),
)

COMPLEMENT_BY_PAIR: dict[frozenset, str] = {
    frozenset({a, b}): why for a, b, why in COMPLEMENTS}


class PairRefused(RemerchandisingRefused):
    """A bundle that is one product twice, or a pair with no reason to exist."""


def pair_reason(form_a: str, form_b: str) -> str:
    """Why a buyer would want these two together, or a refusal.

    Two rules. A product cannot be bundled with itself in a different colour -- that is the
    catalogue-inflation move this whole module exists to refuse, wearing a bundle label. And
    a pair with no stated reason is refused rather than allowed with a blank: "these two
    happen to both exist" is not a reason, and a bundle built on it is a discount.
    """
    if form_a == form_b:
        raise PairRefused(
            f"two {form_a}s is one product offered twice. A buyer who wanted two would buy "
            f"two; a bundle has to be two different things")
    why = COMPLEMENT_BY_PAIR.get(frozenset({form_a, form_b}))
    if not why:
        raise PairRefused(
            f"no stated reason a buyer wants a {form_a} and a {form_b} in one purchase. "
            f"'Both exist' is not a reason, and a bundle built on it is a discount")
    return why


def bundle_pairs(db, *, forms: dict[str, str] | None = None,
                 lanes: dict[str, str] | None = None) -> dict:
    """Concrete bundle and add-on proposals across the certified catalogue.

    `forms` and `lanes` map slug to form and make lane; where a product's form is unknown the
    product is reported as unpairable rather than paired on a guess, because a bundle built
    from a guessed form is a bundle nobody checked.

    An add-on is the same pairing seen from the other end: the cheaper, faster half offered
    beside the slower one. It is reported separately because it is a different offer, not a
    different bundle.
    """
    from ..creative.family import LANE_ORDER

    pool = candidates(db)
    eligible = pool["eligible"]
    forms = forms or {}
    lanes = lanes or {}

    known = [c for c in eligible if forms.get(c["slug"])]
    unpairable = [c["slug"] for c in eligible if not forms.get(c["slug"])]

    pairs: list[dict] = []
    for i, first in enumerate(known):
        for second in known[i + 1:]:
            try:
                why = pair_reason(forms[first["slug"]], forms[second["slug"]])
            except PairRefused:
                continue
            lane_a = lanes.get(first["slug"], "")
            lane_b = lanes.get(second["slug"], "")
            add_on = ""
            if lane_a in LANE_ORDER and lane_b in LANE_ORDER and lane_a != lane_b:
                # The faster half is the add-on: a small make offered beside a longer one is
                # an easy yes, and the same two products offered the other way round is a
                # bigger commitment wearing a smaller label.
                add_on = (first["slug"] if LANE_ORDER.index(lane_a) < LANE_ORDER.index(lane_b)
                          else second["slug"])
            pairs.append({
                "products": [first["slug"], second["slug"]],
                "forms": [forms[first["slug"]], forms[second["slug"]]],
                "why": why,
                "add_on": add_on or None,
                "proven": bool(first["proven"] and second["proven"]),
            })

    return {
        "certified": len(eligible),
        "pairable": len(known),
        "unpairable": unpairable,
        "pairs": pairs,
        "add_ons": [p for p in pairs if p["add_on"]],
        "proof_measurable": pool["proof_measurable"],
        "catalogue_growth": 0,
        "note": ("Every pair states why a buyer wants both, because a bundle whose logic "
                 "nobody can say is a discount with extra steps. A product is never bundled "
                 "with itself in another colour -- that is the catalogue-inflation move this "
                 "module exists to refuse, wearing a bundle label. 'Proven' stays false "
                 "until both halves have sold" if pairs else
                 "no two certified products complement each other, which is a statement "
                 "about how narrow this catalogue is rather than about bundling"),
    }
