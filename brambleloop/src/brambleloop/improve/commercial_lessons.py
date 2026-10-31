"""Measured listing performance, turned into lessons the next product decision reads.

Owner directive (P0, §16): performance data must "feed evidence into future product
selection", "suggest original follow-on products" and "identify strong and weak products",
without inventing data while the store has no sales. Final Master #89 / Build 2 #97 already
say the same thing from the other side: Market Radar reads its lesson inbox where it decides
(`improve.consume`), and a matching lesson nudges `radar.score` within a bound (+-0.06).

What was missing is the writer. `listing.outcomes` records each listing's visits, favourites
and orders; `creative.outcome_learning` and the kill table read them; none of them published a
lesson, so a product category that converts three times better than the shop changed nothing
about which concept is engineered next. This module is that writer.

**What it measures, and only that.** Per product category (the radar concept's own category,
so the lesson speaks the radar's language), over `ListingOutcome` rows written by the owner
export intake (`commerce.listing_outcomes.EXPORT_SOURCE`, F-297: a fixture or hand-inserted row
is not measurement) whose orders were recorded: visits, favourites, orders and orders per
visit. A category is MEASURED only with at least `MIN_VISITS` visits, and a comparison needs at
least two measured categories, because "better than the shop" needs a shop.

**What it says.**

* a category converting at least `WIN_RATIO` times the shop rate, on at least `MIN_ORDERS`
  orders, is published as `commercial_demand` (a favouring subject);
* a category converting at most `LOSE_RATIO` times the shop rate on at least
  `2 * MIN_VISITS` visits is published as `commercial_underperformance` (a disfavouring one).

Each lesson names the category and the uncertified radar concepts in that category or in the
measured products' families -- the follow-on products the evidence points at -- so
`improve.consume.matching` ties it to exactly those concepts. The nudge is the bus's existing
bounded one; nothing here changes a score, a gate or a threshold directly, and no concept
skips the pre-engineering gate because it sells.

**Idempotent and honest.** A lesson is keyed by its evidence (category, verdict, the measured
window); the same evidence is one lesson however often the job runs. When a category's verdict
changes, the earlier lesson is withdrawn with the new evidence. With nothing measured the job
publishes nothing and says why (UNMEASURED, never "no demand").

Thresholds are this module's own: no requirement row gives figures. `MIN_VISITS` is the
company's measured-sample floor (`growth.loops.MEASURED_SAMPLE`).

GREEN: reads `listing_outcomes` only; the `orders` table is not read (orders come from the same export row,
so numerator and denominator share one source), writes lessons. No model, network or spend.
"""
from __future__ import annotations

from dataclasses import dataclass

MIN_VISITS = 200          # growth.loops.MEASURED_SAMPLE
MIN_ORDERS = 3
WIN_RATIO = 1.5
LOSE_RATIO = 0.5
MAX_NAMED_CONCEPTS = 6

ORIGIN_CELL = "portfolio"
DEMAND = "commercial_demand"
UNDERPERFORMANCE = "commercial_underperformance"
SUBJECTS = (DEMAND, UNDERPERFORMANCE)
MEASURED = "MEASURED"
UNMEASURED = "UNMEASURED"
EVIDENCE_PREFIX = "commercial:"


@dataclass
class Group:
    category: str
    products: set
    families: set
    visits: int = 0
    favourites: int = 0
    orders: int = 0
    first: str = ""
    last: str = ""

    @property
    def rate(self) -> float | None:
        return (self.orders / self.visits) if self.visits else None


def _category_and_family(slug: str) -> tuple[str, str | None]:
    """The radar's category and family for a product, from its concept seed, else its record."""
    from ..runtime.pipeline import product_seed

    seed = product_seed(slug)
    if seed is not None:
        return seed.category, seed.family
    from ..visual.laura_home import category_of_slug

    return category_of_slug(slug) or "", None


def measured_groups(db) -> dict[str, Group]:
    """Per-category totals from export-intake outcome rows that carry orders."""
    from sqlalchemy import select

    from ..commerce.listing_outcomes import EXPORT_SOURCE
    from ..core.models import ListingOutcome

    groups: dict[str, Group] = {}
    with db.session() as s:
        rows = list(s.scalars(select(ListingOutcome)
                              .where(ListingOutcome.source.like(f"{EXPORT_SOURCE}%"))
                              .order_by(ListingOutcome.id)))
        for r in rows:
            if r.orders is None or r.visits is None:
                continue          # a row without its orders measures nothing about conversion
            category, family = _category_and_family(r.product_slug)
            if not category:
                continue
            g = groups.setdefault(category, Group(category=category, products=set(),
                                                  families=set()))
            g.products.add(r.product_slug)
            if family:
                g.families.add(family)
            g.visits += int(r.visits)
            g.orders += int(r.orders)
            g.favourites += int(r.favourites or 0)
            g.first = min(filter(None, (g.first, r.period_start)), default=r.period_start)
            g.last = max(filter(None, (g.last, r.period_end)), default=r.period_end)
    return groups


def follow_ons(category: str, families: set, products: set) -> list:
    """Radar concepts the evidence points at: same category or family, not already a product."""
    from ..products import launch0
    from ..radar.opportunity import POOL

    sold_concepts = {launch0.radar_concept_for(p) or p for p in products}
    out = [s for s in POOL
           if (s.category == category or (s.family and s.family in families))
           and s.slug not in sold_concepts and s.slug not in products and not s.is_bundle]
    return sorted(out, key=lambda s: s.slug)[:MAX_NAMED_CONCEPTS]


def _words(text: str) -> str:
    return text.replace("_", " ").replace("-", " ")


def verdicts(db) -> dict:
    """Every category's reading and verdict. Read-only."""
    groups = measured_groups(db)
    measured = {k: g for k, g in groups.items() if g.visits >= MIN_VISITS}
    out = {"categories": {}, "shop": None, "measurable": False, "why": ""}
    for k, g in sorted(groups.items()):
        out["categories"][k] = {"visits": g.visits, "orders": g.orders,
                                "favourites": g.favourites, "products": sorted(g.products),
                                "rate": round(g.rate, 5) if g.rate is not None else None,
                                "state": MEASURED if k in measured else UNMEASURED,
                                "verdict": None, "window": [g.first, g.last]}
    if len(measured) < 2:
        out["why"] = (f"{len(measured)} category measured at >= {MIN_VISITS} visits from "
                      f"export-intake rows with orders; a comparison needs two. UNMEASURED, "
                      f"never 'no demand'")
        return out
    visits = sum(g.visits for g in measured.values())
    orders = sum(g.orders for g in measured.values())
    shop = orders / visits if visits else 0.0
    out.update(shop={"visits": visits, "orders": orders, "rate": round(shop, 5)},
               measurable=True)
    for k, g in measured.items():
        rec = out["categories"][k]
        if shop > 0 and g.orders >= MIN_ORDERS and g.rate >= WIN_RATIO * shop:
            rec["verdict"] = DEMAND
        elif shop > 0 and g.visits >= 2 * MIN_VISITS and g.rate <= LOSE_RATIO * shop:
            rec["verdict"] = UNDERPERFORMANCE
        if rec["verdict"]:
            rec["follow_ons"] = [s.slug for s in follow_ons(k, g.families, g.products)]
            rec["families"] = sorted(g.families)
    return out


def _statement(category: str, rec: dict, shop: dict, concepts: list) -> str:
    named = "; ".join(_words(f"{s.slug} {s.title}") for s in concepts) or "none yet in the pool"
    pct = f"{rec['rate'] * 100:.2f}%"
    base = f"{shop['rate'] * 100:.2f}%"
    cat = _words(category)
    if rec["verdict"] == DEMAND:
        return (f"Measured demand: our own {cat} listings converted {pct} of {rec['visits']} "
                f"visits ({rec['orders']} orders) against a shop rate of {base}. Pursue "
                f"original {cat} follow-on concepts first: {named}.")
    return (f"Measured underperformance: our own {cat} listings converted {pct} of "
            f"{rec['visits']} visits ({rec['orders']} orders) against a shop rate of {base}. "
            f"Engineer further {cat} concepts later, after the listing presentation is "
            f"reviewed: {named}.")


def record_lessons(db) -> dict:
    """Publish one lesson per category verdict, withdrawing ones the evidence no longer supports."""
    from sqlalchemy import select

    from ..core.models import Lesson
    from . import bus

    v = verdicts(db)
    published, withdrawn = [], []
    current_refs: set[str] = set()
    if v["measurable"]:
        for category, rec in sorted(v["categories"].items()):
            if not rec["verdict"]:
                continue
            concepts = follow_ons(category, set(rec.get("families") or ()),
                                  set(rec["products"]))
            ref = (f"{EVIDENCE_PREFIX}{category}:{rec['verdict']}:{rec['window'][0]}"
                   f"..{rec['window'][1]}:{rec['visits']}:{rec['orders']}")[:200]
            current_refs.add(ref)
            lid = bus.publish(db, origin_cell=ORIGIN_CELL, subject=rec["verdict"],
                              statement=_statement(category, rec, v["shop"], concepts),
                              evidence_ref=ref, confidence="measured")
            published.append({"lesson": lid, "category": category, "subject": rec["verdict"],
                              "follow_ons": [s.slug for s in concepts]})
    with db.session() as s:
        stale = [(r.id, r.evidence_ref) for r in s.scalars(
            select(Lesson).where(Lesson.subject.in_(SUBJECTS),
                                 Lesson.origin_cell == ORIGIN_CELL,
                                 Lesson.evidence_ref.like(f"{EVIDENCE_PREFIX}%"),
                                 Lesson.withdrawn_at.is_(None)))
                 if r.evidence_ref not in current_refs]
    for lid, ref in stale:
        category = ref[len(EVIDENCE_PREFIX):].split(":", 1)[0]
        newer = next((p for p in published if p["category"] == category), None)
        bus.withdraw(db, lid, reason=("superseded by newer measured evidence" if newer else
                                      "no longer supported by the measured window"),
                     evidence_ref=(f"lesson:{newer['lesson']}" if newer else
                                   f"{EVIDENCE_PREFIX}{category}:unmeasured"),
                     withdrawn_by="analyst")
        withdrawn.append(lid)
    return {"measurable": v["measurable"], "why": v["why"], "shop": v["shop"],
            "categories": v["categories"], "published": published, "withdrawn": withdrawn,
            "work_done": len(published) + len(withdrawn)}
