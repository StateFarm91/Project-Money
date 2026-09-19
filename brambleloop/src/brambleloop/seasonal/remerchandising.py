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


def plan(db, *, event: str, available: tuple[str, ...] = ()) -> dict:
    """Every re-merchandising opportunity for one occasion, with proof stated as it is."""
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
