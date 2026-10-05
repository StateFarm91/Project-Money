"""Everything that reads orders, read from the orders (C-64).

Run daily by `commerce.order_readings` and immediately after any ingest that created an
order. Each block reads `customers`, `orders`, the ledger, `listing_outcomes`, `cohorts` and
`price_observations` as they stand, and returns either a measurement or UNMEASURED with the
reason. Nothing here estimates a missing quantity: a CA$0 company produces a reading that
says, block by block, what has never been observed.

What each block *does* with its reading, so that it is not an audit row nobody reads:

* #11/#12 cohorts: the validation cohort's lifetime contribution per buyer is the reward
  ceiling the referral check reads (#256) -- a reward is a cost per acquired customer.
* #13 offers: `offer_results` is what `portfolio.review` passes to `offers.may_retire`
  before any retirement action is issued.
* #22 winners: a credible winner opens a bounded replication study (an
  `operating_readings` row with an end date) that ideation reads into its briefs.
* #49 reinvestment: a non-zero envelope recommendation becomes an owner action -- the CFO
  recommends, the owner decides.
* #233 ladder: empty rungs and too-big steps go to ideation as a brief constraint; the
  discount guard's refusals are read by `pricing.position`.
* #234 bundles: candidate pairs from product facts; `collection.assemble` runs the same
  check on its members.
* #235 promotions: incrementality verdicts; a promotion judged not worth repeating is read
  by `pricing.position`.
* #252 repeat windows and lifetime contribution per first-purchase cohort.
* #256 referral outcome and mechanic checks from attributed customers.
* #271 growth loops: traffic and orders observed per loop from the rows that record them,
  which moves each loop's derived strength.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

KIND = "commerce.orders"
STUDY_KIND = "replication.study"
UNMEASURED = "UNMEASURED"

# Where an order's acquisition source maps to a growth loop (#271). An Etsy receipt carries no
# acquisition channel -- search, Etsy Ads, Offsite Ads, a pin and a link all produce the same
# receipt -- so the ingest records `unknown`, and unknown maps to NO loop (CB2-O06): it is
# counted apart as `unattributed`, never credited to the organic marketplace loop.
SOURCE_TO_LOOP = {"etsy_search": "etsy_organic",
                  "pinterest": "pinterest", "google": "google_seo", "seo": "google_seo",
                  "creator": "creators", "email": "email", "etsy_ads": "paid_ads",
                  "offsite_ads": "paid_ads", "bundle": "bundles"}
UNATTRIBUTED = "unattributed"
REFERRAL_SOURCES = ("referral_code", "unique_link", "recorded_mention", "referral")
# How the money on every row here was arrived at, stated once and carried on each block that
# sums it (CB2-O07): fees are estimated from the schedule, FX is measured or assumed per row.
MONEY_BASIS = {"fees": "estimated", "contribution": "revenue net of refunds less estimated fees",
               "fx": "per order: measured or assumed, see fx_measured"}


def _aware(v):
    if v is None:
        return None
    return v if v.tzinfo else v.replace(tzinfo=timezone.utc)


def _now(today: date | None) -> datetime:
    if today is None:
        return datetime.now(timezone.utc)
    return datetime(today.year, today.month, today.day, tzinfo=timezone.utc) + timedelta(days=1)


def orders(db) -> list[dict]:
    """Every order with its buyer's reference, as plain rows."""
    from sqlalchemy import select

    from ..core.models import Customer, Order

    with db.session() as s:
        refs = {c.id: c.customer_ref for c in s.scalars(select(Customer))}
        return [{"customer_ref": refs.get(o.customer_id, ""), "at": _aware(o.at),
                 "product_slug": o.product_slug, "category": o.category,
                 "season": (o.detail or {}).get("season") or _season(o.product_slug),
                 "offer": o.offer or "single_pattern",
                 "revenue_cad": float(o.revenue_cad or 0.0),
                 "contribution_cad": float(o.contribution_cad or 0.0),
                 "acquisition_source": o.acquisition_source or "unknown",
                 "refunded": bool(o.refunded), "is_repeat": bool(o.is_repeat),
                 # The line's reconciled state and refund (CB2-O01); a row written before
                 # states existed reads as paid or fully refunded from its flag.
                 "state": ((o.detail or {}).get("state")
                           or ("fully_refunded" if o.refunded else "paid")),
                 "refund_cad": float(((o.detail or {}).get("refund") or {}).get("cad")
                                     or 0.0),
                 "fees_basis": (((o.detail or {}).get("money") or {}).get("fees") or {}
                                ).get("basis") or "estimated",
                 "currency": o.currency or "CAD", "fx_measured": bool(o.fx_measured),
                 "fx_usd_per_cad": o.fx_usd_per_cad}
                for o in s.scalars(select(Order).order_by(Order.at))]


def _season(slug: str) -> str:
    from ..radar.opportunity import POOL

    seed = next((c for c in POOL if c.slug == slug), None)
    return (seed.season or "none") if seed else "none"


# ---------------------------------------------------------------------------
# #11 / #12


def cohort_block(db, *, as_of: datetime) -> dict:
    from . import cohorts

    st = cohorts.state(db)
    out = {"customers": st["customers"], "orders": st["orders"],
           "validation_cohort": st["validation_cohort"], "source": st["source"]}
    if not st["customers"]:
        out["reading"] = UNMEASURED
        out["why"] = st["note"]
        out["lifetime_contribution_per_buyer_cad"] = None
        return out
    out["cohorts"] = {f"{c['axis']}={c['value']}":
                      cohorts.metrics(db, c["axis"], c["value"], as_of=as_of)
                      for c in st["cohorts"]}
    validation = cohorts.metrics(db, "validation", "first_hundred", as_of=as_of)
    out["validation"] = validation
    ltv = validation["lifetime_contribution"]
    out["lifetime_contribution_per_buyer_cad"] = ltv.get("value")
    out["reading"] = "measured" if st["readable_cohorts"] else UNMEASURED
    return out


# ---------------------------------------------------------------------------
# #13


def offer_results(db) -> list:
    """One `offers.Result` per (design, offer) that has sold, from the orders.

    Visitors are the product's recorded listing visits for its single-pattern offer and
    None (unmeasured) for any other shape, because no listing records visits per offer.
    """
    from sqlalchemy import select

    from ..core.models import ListingOutcome
    from . import offers

    rows = orders(db)
    with db.session() as s:
        visits: dict[str, int] = {}
        for r in s.scalars(select(ListingOutcome)):
            visits[r.product_slug] = visits.get(r.product_slug, 0) + int(r.visits or 0)
    grouped: dict[tuple[str, str], list[dict]] = {}
    for o in rows:
        if o["offer"] in offers.BY_KEY:
            grouped.setdefault((o["product_slug"], o["offer"]), []).append(o)
    results = []
    for (slug, offer), mine in sorted(grouped.items()):
        kept = [o for o in mine if not o["refunded"]]
        # Revenue on each row is already net of its refund and a refunded row's
        # contribution is its retained fees (a loss), so both are summed over every order
        # the offer took: dropping the refunded rows would drop the losses (CB2-O07).
        results.append(offers.Result(
            design_slug=slug, offer=offer,
            visitors=(visits.get(slug) if offer == offers.SINGLE and slug in visits else None),
            buyers=len({o["customer_ref"] for o in kept}),
            revenue_cad=round(sum(o["revenue_cad"] for o in mine), 2),
            contribution_cad=round(sum(o["contribution_cad"] for o in mine), 2)))
    return results


def offer_block(db) -> dict:
    from . import offers

    results = offer_results(db)
    if not results:
        return {"reading": UNMEASURED, "results": [],
                "why": "no order exists, so no offer has a buyer or a visitor to divide by"}
    return {"reading": "measured", "comparison": offers.compare(results),
            "money_basis": MONEY_BASIS,
            "results": [{"design": r.design_slug, "offer": r.offer, **r.measures()}
                        for r in results]}


# ---------------------------------------------------------------------------
# #22


def _skus(db, rows: list[dict], *, now: datetime) -> list:
    from sqlalchemy import select

    from ..core.models import Listing
    from ..radar.opportunity import POOL
    from .replication import Sku

    with db.session() as s:
        first_listed: dict[str, datetime] = {}
        for r in s.scalars(select(Listing)):
            at = _aware(r.created_at)
            if at and (r.product_slug not in first_listed or at < first_listed[r.product_slug]):
                first_listed[r.product_slug] = at
    counts: dict[str, int] = {}
    first_sale: dict[str, datetime] = {}
    for o in rows:
        if o["refunded"]:
            continue
        counts[o["product_slug"]] = counts.get(o["product_slug"], 0) + 1
        first_sale.setdefault(o["product_slug"], o["at"])
    slugs = sorted(set(counts) | set(first_listed))
    seeds = {c.slug: c for c in POOL}
    out = []
    for slug in slugs:
        since = first_listed.get(slug) or first_sale.get(slug) or now
        seed = seeds.get(slug)
        traits = {}
        if seed is not None:
            traits = {"category": seed.category, "season": seed.season or "evergreen",
                      "price": ("entry" if seed.price_cad <= 6 else
                                "premium" if seed.price_cad <= 14 else "collection"),
                      "bundle": "bundle" if seed.is_bundle else "single"}
        out.append(Sku(slug=slug, orders=counts.get(slug, 0),
                       weeks_live=max(0, (now - since).days // 7), traits=traits))
    return out


def winner_block(db, rows: list[dict], *, now: datetime) -> dict:
    from . import replication

    catalogue = _skus(db, rows, now=now)
    selling = [s for s in catalogue if s.orders > 0]
    if not selling:
        return {"reading": UNMEASURED, "winner": None, "study": None,
                "why": "no product has an order, so nothing can be a winner and no capacity "
                       "moves"}
    top = max(selling, key=lambda s: (s.orders, s.slug))
    verdict = replication.is_winner(top, catalogue)
    out = {"reading": "measured", "top": top.slug, "verdict": verdict, "study": None}
    if verdict["credible"]:
        study = replication.study(top, catalogue,
                                  capacity_share=replication.MAX_CAPACITY_SHARE,
                                  starts=now.date() - timedelta(days=1))
        out["study"] = open_study(db, study)
    return out


def open_study(db, study: dict) -> dict:
    """Persist a replication study unless one for this winner is still running."""
    from sqlalchemy import select

    from ..core.models import OperatingReading

    key = study["winner"][:20]
    with db.session() as s:
        row = s.scalar(select(OperatingReading).where(OperatingReading.kind == STUDY_KIND,
                                                      OperatingReading.period_key == key))
        if row is not None and (row.payload or {}).get("ends", "") >= study["starts"]:
            return {**dict(row.payload), "opened": False}
        if row is None:
            row = OperatingReading(kind=STUDY_KIND, period_key=key)
            s.add(row)
        row.payload = study
    return {**study, "opened": True}


def active_study(db, *, today: date | None = None) -> dict | None:
    """The replication study whose window contains today, if any. Read by ideation."""
    from sqlalchemy import select

    from ..core.models import OperatingReading

    day = (today or date.today()).isoformat()
    with db.session() as s:
        for row in s.scalars(select(OperatingReading).where(
                OperatingReading.kind == STUDY_KIND).order_by(OperatingReading.at.desc())):
            p = row.payload or {}
            if p.get("starts", "9999") <= day <= p.get("ends", ""):
                return dict(p)
    return None


# ---------------------------------------------------------------------------
# #49


def reinvestment_block(db, *, now: datetime) -> dict:
    from sqlalchemy import select

    from ..core.models import LedgerEntry, OwnerAction
    from ..finance import reinvestment

    since = now - timedelta(days=30)
    with db.session() as s:
        gross = sum(float(x.gross_cad or 0.0) - float(x.refunds_cad or 0.0)
                    for x in s.scalars(select(LedgerEntry).where(LedgerEntry.category == "sale"))
                    if _aware(x.at) and _aware(x.at) >= since)
    rec = reinvestment.recommend(
        db, gross_cad=round(gross, 2),
        purpose="reinvestment envelope from the trailing 30 days of recorded sales")
    out = {"gross_cad_30d": round(gross, 2), "recommendation": rec,
           "owner_action": None}
    if rec["recommended_cad"] > 0:
        key = f"reinvestment:{now.date().strftime('%Y-%m')}"
        fields = dict(
            action=(f"Decide whether to reinvest up to CA${rec['recommended_cad']:.2f} "
                    f"(the CFO's confidence-scaled envelope after tax, operating and cash "
                    f"reserves)"),
            reason=rec["envelope"]["note"],
            max_cost_cad=float(rec["recommended_cad"]), minutes=5,
            consequence_of_delay="the envelope stays in reserve; nothing is spent",
            blocks="#49 reinvestment")
        with db.session() as s:
            row = s.scalar(select(OwnerAction).where(OwnerAction.requirement_key == key,
                                                     OwnerAction.done.is_(False)))
            if row is None:
                s.add(OwnerAction(requirement_key=key, **fields))
            else:
                for k, v in fields.items():
                    setattr(row, k, v)
        out["owner_action"] = key
    return out


# ---------------------------------------------------------------------------
# #233


def _tier(slug: str, version: str, price: float, members: int = 0) -> str:
    from . import ladder

    if version == "collection":
        return ladder.FLAGSHIP if members >= 4 or price >= 25 else ladder.MINI
    return ladder.ENTRY if price <= ladder.BY_KEY[ladder.ENTRY].typical_cad[1] else ladder.PREMIUM


def ladder_block(db, rows: list[dict], *, today: date | None = None) -> dict:
    from sqlalchemy import select

    from ..core.models import Listing, PriceObservation
    from ..radar.opportunity import POOL
    from . import cohorts, ladder

    with db.session() as s:
        listed = [(r.product_slug, r.version, float(r.price_cad or 0.0))
                  for r in s.scalars(select(Listing)) if r.state != "withdrawn"]
        observations = list(s.scalars(select(PriceObservation).order_by(PriceObservation.id)))
        obs = [(o.product_slug, bool(o.on_sale), float(o.price_cad or 0.0),
                float(o.regular_price_cad or 0.0), o.from_date or "", o.to_date or "")
               for o in observations]
    families: dict[str, int] = {}
    for c in POOL:
        if c.family and not c.is_bundle:
            families[c.family] = families.get(c.family, 0) + 1
    fam_of = {c.slug: c.family for c in POOL}
    products = [{"slug": slug, "price_cad": price,
                 "tier": _tier(slug, version, price, families.get(fam_of.get(slug) or "", 0))}
                for slug, version, price in listed if price > 0]
    shape = ladder.shape(products) if products else None

    # The discount guard over this shop's own recorded price history.
    guard = []
    tiers = {p["slug"]: p["tier"] for p in products}
    by_slug: dict[str, list] = {}
    for o in obs:
        by_slug.setdefault(o[0], []).append(o)
    today = today or date.today()
    for slug, points in by_slug.items():
        sale = [p for p in points if p[1]]
        if not sale:
            continue
        first = min((p[4] for p in points if p[4]), default=today.isoformat())
        days_live = max(1, (today - date.fromisoformat(first)).days)
        days = 0
        for p in sale:
            start = date.fromisoformat(p[4]) if p[4] else today
            end = date.fromisoformat(p[5]) if p[5] else today
            days += max(1, (min(end, today) - start).days)
        latest = sale[-1]
        full = latest[3] or max((p[2] for p in points if not p[1]), default=latest[2])
        if full <= 0:
            continue
        guard.append(ladder.check_discount(tiers.get(slug, ladder.PREMIUM),
                                           full_price_cad=full, promo_price_cad=latest[2],
                                           days_discounted=days, days_live=days_live)
                     | {"slug": slug})

    # Movement between rungs, from buyers' first and later purchases.
    first_tier: dict[str, str] = {}
    later: dict[str, set] = {}
    for o in rows:
        if o["refunded"]:
            continue
        t = tiers.get(o["product_slug"])
        if t is None:
            continue
        if o["customer_ref"] not in first_tier:
            first_tier[o["customer_ref"]] = t
        else:
            later.setdefault(o["customer_ref"], set()).add(t)
    moves = []
    order = list(ladder.TIERS)
    for lower, upper in zip(order[1:-2], order[2:-1]):
        buyers = [c for c, t in first_tier.items() if t == lower]
        moved = [c for c in buyers if upper in later.get(c, set())]
        moves.append({"from_tier": lower, "to_tier": upper, "buyers": len(buyers),
                      "moved": len(moved)})
    by_customer: dict[str, dict] = {}
    for o in rows:
        b = by_customer.setdefault(o["customer_ref"], {"orders": 0, "contribution_cad": 0.0})
        if not o["refunded"]:
            b["orders"] += 1
        b["contribution_cad"] += o["contribution_cad"]  # losses retained (CB2-O07)
    return {
        "reading": "measured" if products else UNMEASURED,
        "why": "" if products else "no priced listing exists to place on a rung",
        "products": products, "shape": shape, "money_basis": MONEY_BASIS,
        "discount_guard": guard,
        "discount_refused": sorted(g["slug"] for g in guard if not g["ok"]),
        "movement": ladder.movement(moves),
        "lifetime_value": ladder.lifetime_value(list(by_customer.values()),
                                                min_buyers=cohorts.MIN_COHORT_N),
    }


# ---------------------------------------------------------------------------
# #234


def bundle_items(db) -> list:
    """The certified catalogue as bundle `Item`s, from product facts only."""
    from sqlalchemy import select

    from ..core.models import Listing, PatternVersion, Product
    from ..creative.audit import concept_from_design
    from ..products.builder import CATALOGUE
    from ..radar.opportunity import POOL
    from .bundles import Item

    seeds = {c.slug: c for c in POOL}
    with db.session() as s:
        certified = {p.slug for p, _v in s.execute(
            select(Product, PatternVersion).where(PatternVersion.product_id == Product.id,
                                                  PatternVersion.certified.is_(True)))}
        prices = {r.product_slug: float(r.price_cad or 0.0) for r in s.scalars(select(Listing))
                  if r.version != "collection"}
    items = []
    for slug in sorted(certified):
        design = CATALOGUE.get(slug)
        seed = seeds.get(slug)
        if design is None or (seed is not None and seed.is_bundle):
            continue
        concept = concept_from_design(design)
        price = prices.get(slug) or (seed.price_cad if seed else 0.0)
        items.append(Item(slug=slug, pod=concept.pod, form=concept.form, price_cad=price,
                          occasion=(seed.season or "") if seed else concept.occasion,
                          weight=design.yarn_weight,
                          collection=(seed.family or "") if seed else "",
                          recipient=concept.recipient))
    return items


def bundle_block(db) -> dict:
    from . import bundles

    items = bundle_items(db)
    found = bundles.candidates(items)
    return {"reading": "measured" if items else UNMEASURED,
            "why": "" if items else "no certified product to combine",
            "considered": found["considered"], "candidates": found["candidates"],
            "note": found["note"],
            "attribution": bundles.attribution_from_db(db)}


# ---------------------------------------------------------------------------
# #235


# The one promotion/referral verdict contract (CB2-X01). Any other reader of these decisions
# -- the growth operations loop included -- consumes `promotion_block` / `referral_block`
# through `latest()` / `directives()` or states a distinct purpose; it does not recompute a
# verdict from the same rows under different thresholds.
PROMOTION_CONTRACT = {
    "evidence": ("launch cohort arms (`cohorts` rows with arm organic/promoted) and the "
                 "shop's own on-sale price observations"),
    "window": "the recorded sale window (from_date..to_date) per product",
    "verdict": "commerce.promotion.incrementality: 'worth repeating' or not; measurable only "
               "with a full-price arm beside the discounted one",
    "acted_on_by": "pricing.position refuses a sale price for `do_not_repeat` products",
    "canonical_reader": "commerce.order_readings.promotion_block",
}
REFERRAL_CONTRACT = {
    "evidence": ("orders whose acquisition_source is a referral source and is_repeat is "
                 "false; referral_reward ledger entries"),
    "window": "all recorded orders while the order source is live",
    "verdict": "commerce.referral.outcome and per-mechanic check against the validation "
               "cohort's lifetime contribution per buyer",
    "acted_on_by": "the mechanics in `may_run` are the only ones a growth job may operate",
    "canonical_reader": "commerce.order_readings.referral_block",
}


def promotion_block(db) -> dict:
    """The canonical promotion verdicts (#235); see PROMOTION_CONTRACT (CB2-X01)."""
    from sqlalchemy import select

    from ..core.models import Cohort, PriceObservation
    from . import promotion
    from .elasticity import ARMS, Arm, ORGANIC, PROMOTED

    with db.session() as s:
        arms: dict[str, dict[str, Arm]] = {}
        for r in s.scalars(select(Cohort).order_by(Cohort.id)):
            if r.arm in ARMS:
                arms.setdefault(r.product_slug, {})[r.arm] = Arm(
                    key=r.key, product_slug=r.product_slug, arm=r.arm,
                    visits=int(r.visits or 0), orders=int(r.orders or 0),
                    revenue_cad=float(r.revenue_cad or 0.0),
                    spend_cad=float(r.spend_cad or 0.0))
        sales = {}
        for o in s.scalars(select(PriceObservation).where(PriceObservation.on_sale.is_(True))
                           .order_by(PriceObservation.id)):
            sales[o.product_slug] = (float(o.price_cad or 0.0),
                                     float(o.regular_price_cad or 0.0),
                                     o.from_date or "", o.to_date or "")
    verdicts = []
    for slug, (promo, full, start, end) in sorted(sales.items()):
        pair = arms.get(slug, {})
        try:
            p = promotion.Promotion(slug, full, promo, date.fromisoformat(start),
                                    date.fromisoformat(end or start), "recorded sale window")
        except (ValueError, TypeError):
            continue
        if ORGANIC not in pair or PROMOTED not in pair:
            verdicts.append({"slug": slug, "measurable": False,
                             "why": "no full-price arm beside the discounted one"})
            continue
        got = promotion.incrementality(p, full_price_arm=pair[ORGANIC],
                                       discounted_arm=pair[PROMOTED])
        verdicts.append({"slug": slug, **got})
    measured = [v for v in verdicts if v.get("measurable")]
    return {"reading": "measured" if measured else UNMEASURED,
            "why": ("" if measured else
                    "no promotion has run beside a full-price arm, so no discount can be "
                    "shown to be accretive -- and none is assumed to be"),
            "verdicts": verdicts, "contract": PROMOTION_CONTRACT,
            "do_not_repeat": sorted(v["slug"] for v in measured
                                    if v.get("verdict") != "worth repeating")}


# ---------------------------------------------------------------------------
# #252


def repeat_block(rows: list[dict], *, as_of: datetime) -> dict:
    from . import repeat

    if not rows:
        return {"reading": UNMEASURED,
                "windows": repeat.windows([], axis="first_product", value=""),
                "lifetime_contribution": None}
    firsts: dict[str, dict] = {}
    # The first purchase is the earliest paid order, whether or not the money later went
    # back: the same rule `cohorts.reconcile_customer` writes, so this block and the cohort
    # tables cannot disagree about who a buyer's first product was (CB2-O04).
    for o in sorted(rows, key=lambda o: (o["at"], o["customer_ref"])):
        if o["state"] in ("paid", "partially_refunded", "fully_refunded"):
            firsts.setdefault(o["customer_ref"], o)
    out: dict[str, dict] = {}
    for axis, key in (("first_product", "product_slug"), ("first_category", "category"),
                      ("first_season", "season")):
        for value in sorted({f.get(key) or ("none" if axis == "first_season" else "")
                             for f in firsts.values()}):
            if value:
                out[f"{axis}={value}"] = repeat.windows(rows, axis=axis, value=value,
                                                        as_of=as_of)
    per_customer: dict[str, float] = {}
    for o in rows:
        per_customer[o["customer_ref"]] = (per_customer.get(o["customer_ref"], 0.0)
                                           + o["contribution_cad"])  # losses retained
    lifetime = {}
    for label, w in out.items():
        axis, value = label.split("=", 1)
        members = [c for c, f in firsts.items()
                   if (f.get({"first_product": "product_slug", "first_category": "category",
                              "first_season": "season"}[axis]) or "none") == value]
        lifetime[label] = (round(sum(per_customer.get(c, 0.0) for c in members)
                                 / len(members), 2) if members else None)
    measured = [k for k, v in out.items() if v.get("measurable")]
    return {"reading": "measured" if measured else UNMEASURED, "windows": out,
            "lifetime_contribution_per_buyer_cad": lifetime, "money_basis": MONEY_BASIS,
            "next_projects": {f["product_slug"]: [r["slug"] for r in repeat.recommend(
                f["product_slug"]).get("next_project", [])[:3]]
                              for f in firsts.values() if _in_pool(f["product_slug"])}}


def _in_pool(slug: str) -> bool:
    from ..radar.opportunity import POOL

    return any(c.slug == slug for c in POOL)


# ---------------------------------------------------------------------------
# #256


def referral_block(db, rows: list[dict], *, contribution_per_customer: float | None) -> dict:
    from sqlalchemy import select

    from ..core.models import LedgerEntry
    from ..scale.runrate import orders_source_live
    from . import referral

    live = orders_source_live(db)["live"]
    with db.session() as s:
        rewards = sum(float(x.expense_cad or 0.0) for x in s.scalars(
            select(LedgerEntry).where(LedgerEntry.category == "referral_reward")))
    if live:
        attributed = {o["customer_ref"] for o in rows
                      if o["acquisition_source"] in REFERRAL_SOURCES and not o["is_repeat"]}
        contribution = round(sum(o["contribution_cad"] for o in rows
                                 if o["customer_ref"] in attributed), 2)  # losses retained
        result = referral.outcome(attributed_customers=len(attributed),
                                  contribution_cad=contribution, reward_spend_cad=rewards)
    else:
        result = referral.outcome(attributed_customers=None, contribution_cad=None,
                                  reward_spend_cad=rewards)
    checks = [referral.check(m, contribution_per_customer_cad=contribution_per_customer)
              for m in referral.DECLARED]
    return {"outcome": result, "mechanics": checks,
            "may_run": sorted(c["mechanic"] for c in checks if c["ok"]),
            "source_live": live, "contract": REFERRAL_CONTRACT}


# ---------------------------------------------------------------------------
# #271


def loop_block(db, rows: list[dict]) -> dict:
    """Bring each loop's counters to what the reconciled rows now say (#271, CB2-O06).

    Orders are counted per loop as paid events (`orders`), with the refunded ones and the net
    outcome (`net_orders`, `contribution_cad`, losses retained) reported beside them, and
    the registry row is *set* to the facts through `loops.reconcile`, so a refund or a
    correction moves a counter down as readily as a sale moved it up. An order whose
    acquisition is unknown -- every Etsy receipt today -- is counted under `unattributed`
    and credited to no loop.
    """
    from sqlalchemy import select

    from ..core.models import ListingOutcome
    from ..growth import loops

    loops.seed(db)
    with db.session() as s:
        etsy_visits = sum(int(r.visits or 0) for r in s.scalars(select(ListingOutcome)))
    empty = lambda: {"orders": 0, "refunded": 0, "net_orders": 0, "contribution": 0.0}  # noqa: E731
    want: dict[str, dict] = {k: empty() for k in loops.BY_KEY}
    unattributed = empty()
    for o in rows:
        # A row without a state reads from its refunded flag, as `orders()` does.
        state = o.get("state") or ("fully_refunded" if o.get("refunded") else "paid")
        if state not in ("paid", "partially_refunded", "fully_refunded"):
            continue
        key = SOURCE_TO_LOOP.get(o.get("acquisition_source") or "unknown")
        bucket = want[key] if key else unattributed
        bucket["orders"] += 1
        if o.get("refunded") or state == "fully_refunded":
            bucket["refunded"] += 1
        else:
            bucket["net_orders"] += 1
        bucket["contribution"] += float(o.get("contribution_cad") or 0.0)
    moved = {}
    for key, w in want.items():
        # The registry carries the NET outcome: a sale later refunded in full is not an
        # order the loop delivered, so the counter goes down when the refund arrives (Codex
        # CB2-O06). Paid events and refunds stay beside it in `by_loop`.
        got = loops.reconcile(db, key, orders=w["net_orders"],
                              contribution_cad=round(w["contribution"], 2),
                              visits=etsy_visits if key == "etsy_organic" else None)
        if got["changed"]:
            moved[key] = got
    summary = loops.evidence_summary(loops.from_db(db))
    return {"moved": moved, "with_evidence": summary["with_evidence"],
            "loops": summary["loops_detail"], "note": summary["note"],
            "by_loop": {k: {**w, "contribution": round(w["contribution"], 2)}
                        for k, w in want.items() if w["orders"]},
            "unattributed": {**unattributed,
                             "contribution": round(unattributed["contribution"], 2),
                             "why": ("acquisition unknown: an Etsy receipt names no channel, "
                                     "so these orders are credited to no loop rather than "
                                     "assumed organic")},
            "money_basis": MONEY_BASIS}


# ---------------------------------------------------------------------------


def read(db, *, today: date | None = None) -> dict:
    from .orders_ingest import gate

    now = _now(today)
    rows = orders(db)
    cohort = cohort_block(db, as_of=now)
    return {
        "as_of": (today or date.today()).isoformat(),
        "order_source": gate(db),
        "orders": len(rows),
        "cohorts": cohort,
        "offers": offer_block(db),
        "winners": winner_block(db, rows, now=now),
        "reinvestment": reinvestment_block(db, now=now),
        "ladder": ladder_block(db, rows, today=today),
        "bundles": bundle_block(db),
        "promotions": promotion_block(db),
        "repeat": repeat_block(rows, as_of=now),
        "referral": referral_block(db, rows, contribution_per_customer=cohort.get(
            "lifetime_contribution_per_buyer_cad")),
        "loops": loop_block(db, rows),
    }


def record(db, payload: dict) -> dict:
    from sqlalchemy import select

    from ..core.models import OperatingReading

    with db.session() as s:
        row = s.scalar(select(OperatingReading).where(
            OperatingReading.kind == KIND, OperatingReading.period_key == payload["as_of"]))
        if row is None:
            row = OperatingReading(kind=KIND, period_key=payload["as_of"])
            s.add(row)
        row.payload = payload
        row.at = datetime.now(timezone.utc)
        s.flush()
        return {"id": row.id}


def latest(db) -> dict | None:
    from sqlalchemy import select

    from ..core.models import OperatingReading

    with db.session() as s:
        row = s.scalar(select(OperatingReading).where(OperatingReading.kind == KIND)
                       .order_by(OperatingReading.at.desc()).limit(1))
        return dict(row.payload or {}) if row is not None else None


def directives(db, *, today: date | None = None) -> dict:
    """What the latest reading asks later jobs to do: ideation and pricing read this."""
    got = latest(db) or {}
    shape = ((got.get("ladder") or {}).get("shape") or {})
    return {
        "replication": active_study(db, today=today),
        "ladder_gaps": list(shape.get("empty_rungs") or []),
        "ladder_steps_too_big": [s for s in (shape.get("steps") or []) if s.get("too_big")],
        "discount_refused": list((got.get("ladder") or {}).get("discount_refused") or []),
        "promotion_do_not_repeat": list((got.get("promotions") or {}).get("do_not_repeat")
                                        or []),
    }
