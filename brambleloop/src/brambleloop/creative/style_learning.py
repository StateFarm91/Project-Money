"""Creative performance by asset style, and the narrow door into brand knowledge (#82).

Requirement 82: after launch, measure search-grid CTR, first-frame engagement, listing
conversion and creative experiment outcomes *by asset style*; high performers become brand
knowledge, and performance never overrides Product Truth, policy or identity continuity.

Three parts, and only the first works without launch data.

**Tagging is deterministic and needs nothing but the frame record.** A `ListingAsset` already
says what class of image it is, which job it does in the gallery and what it claims. From
those the style is read -- where the pixels came from (twin render, photograph, generated,
infographic), whether a person is in the frame, and the shot or role it plays. No model is
asked to look at the picture: a style label a model invented is a label nobody can re-derive,
and a learning loop keyed on it would be learning about the labeller.

**Aggregation refuses below a stated minimum.** CTR over a hundred impressions is a coin
toss described to five decimals. Every metric here is `measured` with its n, or `UNMEASURED`
with the reason and the n it needs. Nothing defaults to zero, because zero is a finding.

**Promotion is the only write, and it is a preference, never a law.** A style may be recorded
as preferred for a gallery role when it beat the pooled alternative by a stated margin on a
measured sample. A promotion whose rule would touch what the product *is* (Product Truth),
what the platform or the asset-truth gate allows (policy), or who the brand is (identity) is
refused before a row exists -- whatever the numbers say. Deterministic validation wins even
if every metric disagrees.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

MEASURED = "measured"
UNMEASURED = "UNMEASURED"

# The minimums. Stated, not tuned: each is the floor below which the number is a rumour.
# Same exposure floor as a listing test (commerce.listing_tests.MIN_EXPOSURE) -- a style
# credited with fewer impressions than a single test must reach has not been seen.
MIN_IMPRESSIONS = 200
# Same sample floor as growth.loops.MEASURED_SAMPLE, applied to visits and first-frame views.
MIN_VISITS = 200
MIN_FIRST_FRAME_VIEWS = 200
# A style measured on one listing is a fact about that listing's product, not its style.
MIN_LISTINGS = 3
# Decisive listing tests (supported or disproved) before an experiment record is summarised.
MIN_TESTS = 3
# How far a style's CTR must sit above the pooled alternative before it may be preferred.
PROMOTION_MIN_LIFT = 0.10

KIND = "creative_style"

# Where the pixels came from, by asset class. Closed: an unknown class is tagged `unknown`,
# which is visible, rather than guessed into a neighbour.
SOURCE_BY_CLASS: dict[str, str] = {
    "DIGITAL_TWIN_RENDER": "twin_render",
    "AI_LIFESTYLE_CONCEPT": "generated",
    "PHYSICAL_PRODUCT_PHOTO": "photograph",
    "INFOGRAPHIC": "infographic",
    "PATTERN_PREVIEW": "pattern_preview",
}

# Gallery roles that show a person wearing or holding the product. `fit` and `detail` are
# the shot names publish.model_photography writes; the rest are the vocabulary a lifestyle
# frame would use. A frame's own `carries_model` claim outranks this list.
MODEL_ROLES: frozenset[str] = frozenset({"fit", "detail", "on_model", "lifestyle", "worn"})

# Gallery roles whose job is to prove a fact about the product. A generated image may never
# be preferred for these: what it would be preferred *as* is evidence, and it is not.
PROOF_ROLES: frozenset[str] = frozenset({
    "whats_included", "size", "materials", "pattern_preview", "chart"})

# What a promotion rule may change: the look of a frame, never what it asserts.
STYLE_FIELDS: frozenset[str] = frozenset({
    "shot", "composition", "crop", "framing", "background", "lighting", "frame_order",
    "prop_styling", "angle"})

# What no amount of performance may change. Checked by name, before any evidence is read.
PROTECTED: dict[str, frozenset[str]] = {
    "product_truth": frozenset({
        "finished_size", "dimensions", "width_cm", "height_cm", "stitch_count", "gauge",
        "yarn", "yarn_weight", "colors", "colours", "colourway", "difficulty", "make_time",
        "materials", "what_is_included", "pages", "construction", "motif_geometry"}),
    "policy": frozenset({
        "asset_class", "ai_disclosure", "disclosure", "provenance", "asset_truth", "claims",
        "price_claim", "discount", "reviews", "listing_policy", "consent_ref"}),
    "identity": frozenset({
        "model_identity", "canonical_model", "face", "brand_voice", "brand_palette", "logo",
        "wordmark", "typography", "house_style_bible"}),
}

RULE_KEYS: frozenset[str] = frozenset({"prefer", "for_role", "changes", "note"})


class StyleLearningRefused(ValueError):
    """An outcome row that cannot be true, or a promotion that is not a preference."""


class PromotionRefused(StyleLearningRefused):
    """A promotion below the minimum, or one that would change truth, policy or identity."""


def _unmeasured(why: str, needs: str) -> dict:
    return {"status": UNMEASURED, "value": None, "why": why, "needs": needs}


def _measured(value, **extra) -> dict:
    return {"status": MEASURED, "value": value, **extra}


# ---------------------------------------------------------------------------
# Tagging


def tag(asset_class: str, role: str, claims: dict | None = None) -> dict:
    """The style of one frame, read from its record. Deterministic; no model call."""
    claims = dict(claims or {})
    source = SOURCE_BY_CLASS.get(str(asset_class or ""), "unknown")
    # A frame that says it was generated was generated, whatever class it was filed under.
    if claims.get("generated") is True and source != "photograph":
        source = "generated"
    model_bearing = bool(claims.get("carries_model")) or (role or "") in MODEL_ROLES
    subject = "model_bearing" if model_bearing else "product_first"
    composition = str(claims.get("shot") or claims.get("composition") or role or "unknown")
    return {
        "style": f"{source}/{subject}/{composition}",
        "source": source,
        "subject": subject,
        "composition": composition,
        "deterministic_render": source == "twin_render",
        "generated": source == "generated",
    }


def tag_asset(row) -> dict:
    """Tag one `ListingAsset` row."""
    out = tag(row.asset_class, row.role, row.claims)
    out.update({"product_slug": row.product_slug, "version": row.version,
                "position": row.position, "role": row.role})
    return out


def tag_all(db) -> list[dict]:
    """Every recorded frame, tagged."""
    from sqlalchemy import select

    from ..core.models import ListingAsset

    with db.session() as s:
        rows = list(s.scalars(select(ListingAsset).order_by(
            ListingAsset.product_slug, ListingAsset.version, ListingAsset.position)))
        return [tag_asset(r) for r in rows]


def listing_styles(db, product_slug: str, version: str = "") -> tuple[str, list[str]]:
    """The hero (search-grid) style and the full style mix of one listing's frame plan."""
    from sqlalchemy import select

    from ..core.models import ListingAsset

    with db.session() as s:
        q = select(ListingAsset).where(ListingAsset.product_slug == product_slug)
        if version:
            q = q.where(ListingAsset.version == version)
        rows = list(s.scalars(q.order_by(ListingAsset.version, ListingAsset.position)))
    if not rows:
        return "", []
    if not version:
        latest = rows[-1].version
        rows = [r for r in rows if r.version == latest]
    tagged = [tag_asset(r) for r in rows]
    hero = min(tagged, key=lambda t: t["position"])["style"]
    return hero, sorted({t["style"] for t in tagged})


# ---------------------------------------------------------------------------
# Recording outcomes


def _count(name: str, value, *, optional: bool = False) -> int | None:
    if value is None and optional:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise StyleLearningRefused(f"{name} must be a non-negative whole count, got {value!r}")
    return value


def record_outcome(db, *, product_slug: str, version: str = "", period_start: str,
                   period_end: str, impressions: int, visits: int, source: str,
                   favourites: int | None = None, first_frame_views: int | None = None,
                   first_frame_engagements: int | None = None, orders: int | None = None,
                   test_key: str = "") -> dict:
    """Write one listing's measured period, tagged with the style it was showing.

    Refuses the impossible rather than storing it: more visits than impressions, more
    engagements than views, more orders than visits, a period that ends before it starts,
    and a number with no source.
    """
    from sqlalchemy import select

    from ..core.models import ListingOutcome

    if not (source or "").strip():
        raise StyleLearningRefused("an outcome with no source is a number somebody typed")
    try:
        start = date.fromisoformat(period_start)
        end = date.fromisoformat(period_end)
    except (TypeError, ValueError) as exc:
        raise StyleLearningRefused(f"period dates must be ISO dates: {exc}") from exc
    if end < start:
        raise StyleLearningRefused("a period cannot end before it starts")
    impressions = _count("impressions", impressions)
    visits = _count("visits", visits)
    favourites = _count("favourites", favourites, optional=True)
    ffv = _count("first_frame_views", first_frame_views, optional=True)
    ffe = _count("first_frame_engagements", first_frame_engagements, optional=True)
    orders = _count("orders", orders, optional=True)
    if visits > impressions:
        raise StyleLearningRefused("more visits than impressions is a counting fault")
    if ffe is not None and (ffv is None or ffe > ffv):
        raise StyleLearningRefused("first-frame engagements need views, and cannot exceed them")
    if orders is not None and orders > visits:
        raise StyleLearningRefused("more orders than visits is a counting fault")

    hero, styles = listing_styles(db, product_slug, version)
    with db.session() as s:
        row = s.scalar(select(ListingOutcome).where(
            ListingOutcome.product_slug == product_slug,
            ListingOutcome.period_start == period_start,
            ListingOutcome.period_end == period_end))
        if row is None:
            row = ListingOutcome(product_slug=product_slug, period_start=period_start,
                                 period_end=period_end, source=source)
            s.add(row)
        row.version = version
        row.impressions, row.visits, row.favourites = impressions, visits, favourites
        row.first_frame_views, row.first_frame_engagements = ffv, ffe
        row.orders = orders
        row.hero_style, row.styles = hero, styles
        row.test_key, row.source = test_key or "", source
    return {"recorded": True, "product_slug": product_slug, "hero_style": hero or None,
            "styles": styles,
            "untagged": not hero,
            "note": ("no frame record exists for this listing, so its period is stored but "
                     "credited to no style" if not hero else "")}


# ---------------------------------------------------------------------------
# Aggregation


def _orders_for(s, row) -> int:
    """A period's orders: the row's own count, else the orders table over the period."""
    from sqlalchemy import func, select

    from ..core.models import Order

    if row.orders is not None:
        return row.orders
    start = datetime.fromisoformat(row.period_start).replace(tzinfo=timezone.utc)
    end = datetime.fromisoformat(row.period_end).replace(tzinfo=timezone.utc)
    return s.scalar(select(func.count(Order.id)).where(
        Order.product_slug == row.product_slug, Order.refunded == False,  # noqa: E712
        Order.at >= start, Order.at < end.replace(hour=23, minute=59, second=59))) or 0


def _rows(db) -> tuple[list[dict], dict[str, str]]:
    from sqlalchemy import select

    from ..core.models import ListingMemory, ListingOutcome

    with db.session() as s:
        rows = []
        for r in s.scalars(select(ListingOutcome)):
            rows.append({"slug": r.product_slug, "hero": r.hero_style,
                         "styles": list(r.styles or []), "impressions": r.impressions,
                         "visits": r.visits, "ffv": r.first_frame_views,
                         "ffe": r.first_frame_engagements, "orders": _orders_for(s, r),
                         "test_key": r.test_key})
        memory = {m.test_key: m.outcome for m in s.scalars(select(ListingMemory))}
    return rows, memory


def _ctr(rows: list[dict]) -> dict:
    impressions = sum(r["impressions"] for r in rows)
    visits = sum(r["visits"] for r in rows)
    listings = len({r["slug"] for r in rows})
    if listings < MIN_LISTINGS:
        return _unmeasured(f"{listings} listing(s) against a floor of {MIN_LISTINGS}; a style "
                           f"seen on fewer is a fact about those products",
                           f"n >= {MIN_LISTINGS} listings and >= {MIN_IMPRESSIONS} impressions")
    if impressions < MIN_IMPRESSIONS:
        return _unmeasured(f"{impressions} impressions against a floor of {MIN_IMPRESSIONS}",
                           f"n >= {MIN_IMPRESSIONS} impressions")
    return _measured(round(visits / impressions, 5), n=impressions, listings=listings,
                     visits=visits)


def by_style(db) -> dict:
    """CTR, first-frame engagement, conversion and experiment outcomes, per asset style."""
    rows, memory = _rows(db)
    tags = tag_all(db)
    styles = sorted({t["style"] for t in tags} | {r["hero"] for r in rows if r["hero"]})
    if not rows:
        return {
            "status": UNMEASURED,
            "why": ("no listing outcome has been recorded: nothing is live, so no style has "
                    "been shown to anybody. Tags exist; performance does not"),
            "needs": (f"listing_outcomes rows from a Stats export: per style n >= "
                      f"{MIN_IMPRESSIONS} impressions across >= {MIN_LISTINGS} listings for "
                      f"CTR, >= {MIN_VISITS} visits for conversion, >= "
                      f"{MIN_FIRST_FRAME_VIEWS} first-frame views, >= {MIN_TESTS} decisive "
                      f"tests"),
            "styles_tagged": styles, "frames_tagged": len(tags), "by_style": {},
            "minimums": minimums()}

    out: dict[str, dict] = {}
    for style in styles:
        hero_rows = [r for r in rows if r["hero"] == style]
        mix_rows = [r for r in rows if style in r["styles"]]

        entry: dict[str, dict] = {"search_grid_ctr": _ctr(hero_rows)}

        ff = [r for r in hero_rows if r["ffv"] is not None]
        views = sum(r["ffv"] for r in ff)
        if not ff:
            entry["first_frame_engagement"] = _unmeasured(
                "no period for this style carries first-frame views; the platform exposes "
                "them only where it chooses to", f"n >= {MIN_FIRST_FRAME_VIEWS} views")
        elif views < MIN_FIRST_FRAME_VIEWS:
            entry["first_frame_engagement"] = _unmeasured(
                f"{views} first-frame views against a floor of {MIN_FIRST_FRAME_VIEWS}",
                f"n >= {MIN_FIRST_FRAME_VIEWS} views")
        else:
            entry["first_frame_engagement"] = _measured(
                round(sum(r["ffe"] or 0 for r in ff) / views, 5), n=views)

        visits = sum(r["visits"] for r in mix_rows)
        listings = len({r["slug"] for r in mix_rows})
        if listings < MIN_LISTINGS or visits < MIN_VISITS:
            entry["conversion"] = _unmeasured(
                f"{visits} visits across {listings} listing(s) carrying this style, against "
                f"floors of {MIN_VISITS} visits and {MIN_LISTINGS} listings",
                f"n >= {MIN_VISITS} visits across >= {MIN_LISTINGS} listings")
        else:
            orders = sum(r["orders"] for r in mix_rows)
            entry["conversion"] = _measured(round(orders / visits, 5), n=visits,
                                            orders=orders, listings=listings,
                                            attribution=("listing-level: every style in a "
                                                         "listing's frame plan is credited "
                                                         "with its conversion"))

        outcomes = [memory[r["test_key"]] for r in hero_rows
                    if r["test_key"] and r["test_key"] in memory]
        decisive = [o for o in outcomes if o in ("supported", "disproved")]
        if len(decisive) < MIN_TESTS:
            entry["experiment_outcomes"] = _unmeasured(
                f"{len(decisive)} decisive listing test(s) against a floor of {MIN_TESTS}",
                f"n >= {MIN_TESTS} supported-or-disproved tests in listing_memory")
        else:
            entry["experiment_outcomes"] = _measured(
                {"supported": outcomes.count("supported"),
                 "disproved": outcomes.count("disproved"),
                 "inconclusive": outcomes.count("inconclusive")}, n=len(decisive))
        out[style] = entry

    measured = sorted(s for s, e in out.items()
                      if any(m["status"] == MEASURED for m in e.values()))
    return {"status": MEASURED if measured else UNMEASURED,
            "why": ("" if measured else "outcomes exist but no style reaches a minimum n"),
            "styles_tagged": styles, "frames_tagged": len(tags), "by_style": out,
            "measured_styles": measured, "minimums": minimums()}


def minimums() -> dict:
    return {"impressions": MIN_IMPRESSIONS, "visits": MIN_VISITS,
            "first_frame_views": MIN_FIRST_FRAME_VIEWS, "listings": MIN_LISTINGS,
            "decisive_tests": MIN_TESTS, "promotion_min_lift": PROMOTION_MIN_LIFT}


# ---------------------------------------------------------------------------
# Promotion into brand knowledge


def check_rule(style: str, rule: dict) -> None:
    """Refuse a rule that would change truth, policy or identity. Evidence is not consulted."""
    unknown_keys = set(rule) - RULE_KEYS
    if unknown_keys:
        raise PromotionRefused(f"rule keys {sorted(unknown_keys)} are not part of a style "
                               f"preference: {sorted(RULE_KEYS)}")
    if rule.get("prefer") != style:
        raise PromotionRefused("a rule must prefer the style whose evidence promotes it")
    changes = set(rule.get("changes") or ())
    for domain, fields in PROTECTED.items():
        hit = sorted(changes & fields)
        if hit:
            raise PromotionRefused(
                f"{hit} belong to {domain}. Performance never overrides Product Truth, policy "
                f"or identity continuity (#82): a style that sells better by changing what "
                f"the product is, what may be claimed or who the brand is has not won, it has "
                f"cheated")
    stray = sorted(changes - STYLE_FIELDS)
    if stray:
        raise PromotionRefused(f"{stray} are not style fields ({sorted(STYLE_FIELDS)}); an "
                               f"unknown change is refused rather than assumed harmless")
    role = str(rule.get("for_role") or "")
    if not role:
        raise PromotionRefused("a preference applies to a gallery role; name it")
    source = style.split("/", 1)[0]
    if source == "generated" and role in PROOF_ROLES:
        raise PromotionRefused(
            f"a generated image cannot be preferred for {role!r}: that frame's job is to "
            f"prove a fact about the product, and asset truth (policy) forbids generated "
            f"evidence however well it performs")


def promote(db, style: str, *, rule: dict) -> dict:
    """Record a style as preferred, only on measured evidence and only as a preference."""
    from sqlalchemy import select

    from ..core.models import BrandKnowledge

    check_rule(style, rule)
    report = by_style(db)
    entry = report["by_style"].get(style)
    if entry is None or entry["search_grid_ctr"]["status"] != MEASURED:
        why = (entry["search_grid_ctr"]["why"] if entry else
               report.get("why") or "no outcome row credits this style")
        raise PromotionRefused(f"{style}: search-grid CTR is UNMEASURED ({why}); nothing is "
                               f"promoted below the minimum n")
    rows, _ = _rows(db)
    rest = [r for r in rows if r["hero"] and r["hero"] != style]
    baseline = _ctr(rest)
    if baseline["status"] != MEASURED:
        raise PromotionRefused(f"the alternative to {style} is UNMEASURED ({baseline['why']}); "
                               f"a style cannot beat a comparison nobody measured")
    ctr = entry["search_grid_ctr"]["value"]
    base = baseline["value"]
    lift = (ctr - base) / base if base else None
    if lift is None or lift < PROMOTION_MIN_LIFT:
        raise PromotionRefused(f"{style} CTR {ctr} against pooled {base}: lift "
                               f"{None if lift is None else round(lift, 4)} is below "
                               f"{PROMOTION_MIN_LIFT}")
    key = f"{rule['for_role']}:{style}"
    evidence = {"ctr": entry["search_grid_ctr"], "baseline": baseline,
                "lift": round(lift, 4), "conversion": entry["conversion"],
                "at": datetime.now(timezone.utc).isoformat()}
    statement = (f"For the {rule['for_role']} frame, prefer {style}: CTR {ctr} against "
                 f"{base} pooled over n={entry['search_grid_ctr']['n']} impressions. A "
                 f"preference among honest frames; every gate still applies")
    with db.session() as s:
        row = s.scalar(select(BrandKnowledge).where(BrandKnowledge.kind == KIND,
                                                    BrandKnowledge.key == key))
        if row is None:
            row = BrandKnowledge(kind=KIND, key=key, statement=statement)
            s.add(row)
        row.statement, row.rule, row.evidence, row.active = statement, dict(rule), evidence, True
    return {"promoted": True, "key": key, "statement": statement, "evidence": evidence}


def knowledge(db) -> list[dict]:
    from sqlalchemy import select

    from ..core.models import BrandKnowledge

    with db.session() as s:
        return [{"key": r.key, "statement": r.statement, "rule": r.rule,
                 "evidence": r.evidence, "active": r.active}
                for r in s.scalars(select(BrandKnowledge).where(BrandKnowledge.kind == KIND))]


def learn(db) -> dict:
    """The daily pass: aggregate, and try the hero preference for every measured style."""
    report = by_style(db)
    promoted, refused = [], []
    for style, entry in report["by_style"].items():
        if entry["search_grid_ctr"]["status"] != MEASURED:
            continue
        try:
            promoted.append(promote(db, style, rule={"prefer": style, "for_role": "hero",
                                                     "changes": []})["key"])
        except PromotionRefused as e:
            refused.append({"style": style, "why": str(e)})
    return {"status": report["status"], "why": report.get("why", ""),
            "styles_tagged": len(report["styles_tagged"]),
            "frames_tagged": report["frames_tagged"],
            "measured_styles": report.get("measured_styles", []),
            "promoted": promoted, "refused": refused}


def state() -> dict:
    return {"minimums": minimums(), "protected": {k: sorted(v) for k, v in PROTECTED.items()},
            "style_fields": sorted(STYLE_FIELDS), "proof_roles": sorted(PROOF_ROLES),
            "note": ("Styles are tagged from the frame record, deterministically. Performance "
                     "is measured per style above stated minimums or reported UNMEASURED. A "
                     "promotion is a preference among honest frames and is refused if it "
                     "would change Product Truth, policy or identity (#82).")}
