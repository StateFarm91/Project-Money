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

**WS6 E1: the official basis.** Without owner exports nothing above ever measured, so no buyer
evidence reached a ranking. A second, separate basis now reads only official Etsy data:

* the numerator is the countable orders ingested from `getShopReceipts` (`transactions_r`;
  `Order.source == orders_ingest.SOURCE`, refs `etsy:<receipt>:<transaction>`), excluding
  orders Etsy attributes to Offsite Ads (paid traffic is not organic demand);
* the denominator is listing VIEWS from the official listing reads (`getListingsByShop`,
  cumulative `views`, differenced between the earliest and latest daily snapshot of each
  listing) -- labelled views, never visits. Impressions, visits, carts, conversion and traffic
  sources stay UNKNOWN: the API has none of them;
* orders count only inside the window the views cover, per product.

The two bases are never mixed: each is compared with its own shop rate, and a lesson names its
basis in its evidence (`commercial:official:<category>:...`). Export lessons keep their refs.

GREEN: reads `listing_outcomes`, the official listing snapshots and receipt-ingested orders;
writes lessons. No model, network or spend.
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
EXPORT = "export"            # owner Etsy Stats export: orders per visit
OFFICIAL = "official"        # WS6 E1: receipt orders per official listing view
BASES = (EXPORT, OFFICIAL)
MIN_VIEWS = MIN_VISITS       # the same measured-sample floor, on the views denominator


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


def _non_overlapping(rows: list) -> list:
    """Review OPUS2B2 F4.1: one product's overlapping export periods are counted once.

    Two owner exports whose periods overlap (October, then the second half of October) are
    different rows for the same days. Per product, the widest periods are kept first and a row
    whose period overlaps one already kept is dropped, so no day's visits or orders count twice.
    A row without both dates cannot be compared and is kept as recorded.
    """
    from datetime import date

    def period(r):
        try:
            return date.fromisoformat(str(r.period_start)), date.fromisoformat(str(r.period_end))
        except (TypeError, ValueError):
            return None

    kept, by_slug = [], {}
    for r in sorted(rows, key=lambda r: (-((period(r)[1] - period(r)[0]).days
                                           if period(r) else -1), r.id)):
        p = period(r)
        if p is None:
            kept.append(r)
            continue
        taken = by_slug.setdefault(r.product_slug, [])
        if any(p[0] <= end and start <= p[1] for start, end in taken):
            continue
        taken.append(p)
        kept.append(r)
    return sorted(kept, key=lambda r: r.id)


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
        for r in _non_overlapping(rows):
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


def _view_windows(db) -> dict[str, dict]:
    """Per product: views over the official snapshot window, and that window's days.

    Each listing's views are its latest daily snapshot minus its earliest (cumulative counts);
    a listing whose count fell, or that appears in only one snapshot, contributes nothing (its
    period is UNKNOWN, never zero). Listings map to products through `listings`."""
    from sqlalchemy import select

    from ..commerce.listing_outcomes import SNAPSHOT_KIND
    from ..core.models import Listing, OperatingReading

    with db.session() as s:
        snaps = [(r.period_key, dict((r.payload or {}).get("listings") or {}))
                 for r in s.scalars(select(OperatingReading)
                                    .where(OperatingReading.kind == SNAPSHOT_KIND)
                                    .order_by(OperatingReading.period_key))]
        ours = {str(r.etsy_listing_id): r.product_slug
                for r in s.scalars(select(Listing).where(Listing.etsy_listing_id != ""))}
    first: dict[str, tuple[str, int]] = {}
    last: dict[str, tuple[str, int]] = {}
    for day, listings in snaps:
        for lid, rec in listings.items():
            v = (rec or {}).get("views")
            if not isinstance(v, int) or isinstance(v, bool) or v < 0:
                continue
            first.setdefault(lid, (day, v))
            last[lid] = (day, v)
    out: dict[str, dict] = {}
    for lid, (d0, v0) in first.items():
        d1, v1 = last[lid]
        slug = ours.get(lid)
        if not slug or d1 <= d0 or v1 < v0:
            continue
        w = out.setdefault(slug, {"views": 0, "first": d0, "last": d1})
        w["views"] += v1 - v0
        w["first"], w["last"] = min(w["first"], d0), max(w["last"], d1)
    return out


def official_groups(db) -> dict[str, Group]:
    """WS6 E1: per-category receipt orders over official listing views, inside the views
    window. Offsite-Ads-attributed orders are excluded (paid traffic)."""
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import select

    from ..commerce.orders_ingest import SOURCE, countable_orders
    from ..core.models import Order

    windows = _view_windows(db)
    groups: dict[str, Group] = {}
    if not windows:
        return groups
    with db.session() as s:
        for slug, w in sorted(windows.items()):
            start = datetime.fromisoformat(w["first"]).replace(tzinfo=timezone.utc)
            end = datetime.fromisoformat(w["last"]).replace(tzinfo=timezone.utc) + timedelta(
                days=1)
            orders = [o for o in countable_orders(s, select(Order).where(
                Order.product_slug == slug, Order.source == SOURCE,
                Order.external_ref.like("etsy:%"), Order.at >= start, Order.at < end))
                      if not o.offsite_ad_attributed]
            category, family = _category_and_family(slug)
            if not category:
                continue
            g = groups.setdefault(category, Group(category=category, products=set(),
                                                  families=set()))
            g.products.add(slug)
            if family:
                g.families.add(family)
            g.visits += int(w["views"])        # the denominator here is VIEWS (see module doc)
            g.orders += len(orders)
            g.first = min(filter(None, (g.first, w["first"])), default=w["first"])
            g.last = max(filter(None, (g.last, w["last"])), default=w["last"])
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


def verdicts(db, basis: str = EXPORT) -> dict:
    """Every category's reading and verdict on one basis. Read-only.

    `EXPORT`: owner export rows, orders per VISIT. `OFFICIAL` (WS6 E1): receipt orders per
    official listing VIEW; its `visits` fields hold views (the reading says so)."""
    groups = measured_groups(db) if basis == EXPORT else official_groups(db)
    floor = MIN_VISITS if basis == EXPORT else MIN_VIEWS
    measured = {k: g for k, g in groups.items() if g.visits >= floor}
    out = {"categories": {}, "shop": None, "measurable": False, "why": "", "basis": basis,
           "denominator": "visits" if basis == EXPORT else "views",
           "unknown": ([] if basis == EXPORT else
                       ["impressions", "visits", "carts", "conversion_rate",
                        "traffic_sources"])}
    for k, g in sorted(groups.items()):
        out["categories"][k] = {"visits": g.visits, "orders": g.orders,
                                "favourites": g.favourites, "products": sorted(g.products),
                                "rate": round(g.rate, 5) if g.rate is not None else None,
                                "state": MEASURED if k in measured else UNMEASURED,
                                "verdict": None, "window": [g.first, g.last]}
    if len(measured) < 2:
        source = ("export-intake rows with orders" if basis == EXPORT else
                  "official listing views (getListingsByShop) with receipt orders")
        out["why"] = (f"{len(measured)} category measured at >= {floor} "
                      f"{out['denominator']} from {source}; a comparison needs two. "
                      f"UNMEASURED, never 'no demand'")
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
        elif shop > 0 and g.visits >= 2 * floor and g.rate <= LOSE_RATIO * shop:
            rec["verdict"] = UNDERPERFORMANCE
        if rec["verdict"]:
            rec["follow_ons"] = [s.slug for s in follow_ons(k, g.families, g.products)]
            rec["families"] = sorted(g.families)
    return out


def _statement(category: str, rec: dict, shop: dict, concepts: list,
               basis: str = EXPORT) -> str:
    named = "; ".join(_words(f"{s.slug} {s.title}") for s in concepts) or "none yet in the pool"
    pct = f"{rec['rate'] * 100:.2f}%"
    base = f"{shop['rate'] * 100:.2f}%"
    cat = _words(category)
    unit = ("visits" if basis == EXPORT else
            "Etsy listing views (official API; visits UNKNOWN)")
    orders = ("orders" if basis == EXPORT else "receipt orders")
    if rec["verdict"] == DEMAND:
        return (f"Measured demand: our own {cat} listings converted {pct} of {rec['visits']} "
                f"{unit} ({rec['orders']} {orders}) against a shop rate of {base}. Pursue "
                f"original {cat} follow-on concepts first: {named}.")
    return (f"Measured underperformance: our own {cat} listings converted {pct} of "
            f"{rec['visits']} {unit} ({rec['orders']} {orders}) against a shop rate of "
            f"{base}. Engineer further {cat} concepts later, after the listing presentation "
            f"is reviewed: {named}.")


def _ref_basis_and_category(ref: str) -> tuple[str, str]:
    """(basis, category) of a lesson's evidence ref. Export refs predate the basis and carry
    none (`commercial:<category>:...`); official ones are `commercial:official:<category>:...`."""
    parts = ref[len(EVIDENCE_PREFIX):].split(":")
    if parts and parts[0] == OFFICIAL and len(parts) > 1:
        return OFFICIAL, parts[1]
    return EXPORT, parts[0] if parts else ""


def record_lessons(db) -> dict:
    """Publish one lesson per category verdict on each basis, withdrawing ones the evidence no
    longer supports. The bases are separate evidence: neither supersedes the other's lessons."""
    from sqlalchemy import select

    from ..core.models import Lesson
    from . import bus

    readings = {b: verdicts(db, b) for b in BASES}
    published, withdrawn = [], []
    current_refs: set[str] = set()
    for basis, v in readings.items():
        if not v["measurable"]:
            continue
        for category, rec in sorted(v["categories"].items()):
            if not rec["verdict"]:
                continue
            concepts = follow_ons(category, set(rec.get("families") or ()),
                                  set(rec["products"]))
            tag = "" if basis == EXPORT else f"{OFFICIAL}:"
            ref = (f"{EVIDENCE_PREFIX}{tag}{category}:{rec['verdict']}:{rec['window'][0]}"
                   f"..{rec['window'][1]}:{rec['visits']}:{rec['orders']}")[:200]
            current_refs.add(ref)
            lid = bus.publish(db, origin_cell=ORIGIN_CELL, subject=rec["verdict"],
                              statement=_statement(category, rec, v["shop"], concepts, basis),
                              evidence_ref=ref, confidence="measured")
            published.append({"lesson": lid, "category": category, "subject": rec["verdict"],
                              "basis": basis, "follow_ons": [s.slug for s in concepts]})
    with db.session() as s:
        stale = [(r.id, r.evidence_ref) for r in s.scalars(
            select(Lesson).where(Lesson.subject.in_(SUBJECTS),
                                 Lesson.origin_cell == ORIGIN_CELL,
                                 Lesson.evidence_ref.like(f"{EVIDENCE_PREFIX}%"),
                                 Lesson.withdrawn_at.is_(None)))
                 if r.evidence_ref not in current_refs]
    for lid, ref in stale:
        basis, category = _ref_basis_and_category(ref)
        newer = next((p for p in published
                      if p["category"] == category and p["basis"] == basis), None)
        tag = "" if basis == EXPORT else f"{OFFICIAL}:"
        bus.withdraw(db, lid, reason=("superseded by newer measured evidence" if newer else
                                      "no longer supported by the measured window"),
                     evidence_ref=(f"lesson:{newer['lesson']}" if newer else
                                   f"{EVIDENCE_PREFIX}{tag}{category}:unmeasured"),
                     withdrawn_by="analyst")
        withdrawn.append(lid)
    export = readings[EXPORT]
    return {"measurable": any(v["measurable"] for v in readings.values()),
            "why": export["why"], "shop": export["shop"], "categories": export["categories"],
            "official": {k: readings[OFFICIAL][k] for k in ("measurable", "why", "shop",
                                                             "categories", "denominator",
                                                             "unknown")},
            "published": published, "withdrawn": withdrawn,
            "work_done": len(published) + len(withdrawn)}
