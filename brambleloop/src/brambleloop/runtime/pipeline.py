"""Shadow-mode release pipeline (Master Plan section 36, acceptance Gate F).

Wires the release chain into real queued jobs so one product can travel from a market brief to
a release certificate with no human intervention:

    radar.scan -> radar.score -> cir.draft -> cir.compile -> gate.asset_truth
        -> gate.policy -> gate.certify -> listing.draft -> (store.publish blocked in shadow)

In SHADOW the store operator refuses to publish, by design: section 26 forbids connecting a
newly built autonomous system to live listings on day one. The refusal is the feature.

Pattern authoring here is deliberately deterministic template code, not a model call. A model
proposes *concepts*; the CIR that gets compiled is constructed by code whose output is
reproducible. That is what section 2 means by "never ask an LLM to guess instructions".
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import func

from ..cir.compiler import compile_cir
from ..cir.model import CIR, Component, Gauge, Material, Op, Repeat, Row
from ..core.models import Phase, Product, PatternVersion
from ..gates.asset_truth import Asset, AssetClass, Claims, Provenance
from ..gates.certificate import DOC_VERSION, certify
from ..gates.incidents import IncidentTracker
from ..gates.policy import ListingDraft
from ..radar.opportunity import POOL, ConceptSeed, score_concept, select_portfolio
from ..integrations.etsy import EtsyClient as _StockEtsyClient

# Bound at import, not looked up per call: a harness that rebinds `etsy.EtsyClient` must not
# make its stand-in count as the stock client whose create-hook order is known (FB2-R2 #1).
_STOCK_PUBLISH = _StockEtsyClient.publish
from .worker import CapabilityNotEnabled, JobContext, handlers, protected_phase

PROMOTION_THRESHOLD = 0.55
"""Below this a concept is not worth engineering time. Set from the pool: roughly the top
third clears it, which is the intake rate the release chain can actually absorb."""


class ShadowModeRefusal(CapabilityNotEnabled):
    """A production-only action attempted before its gate has passed.

    Subclasses CapabilityNotEnabled so the worker treats it as terminal rather than retrying
    against a mode that will not change between attempts.
    """


class ParityRefusal(CapabilityNotEnabled):
    """Listing export blocked by the eight-part creative parity gate (#75).

    Terminal for the same reason as a shadow refusal: re-running the same job against the
    same frames asks the same question. What changes a parity verdict is a different frame
    or a comparison that has not been made, neither of which a retry produces.
    """


# ---- concept -> CIR ------------------------------------------------------


@dataclass
class Concept:
    slug: str
    title: str
    category: str
    stitch_repeat: list[tuple[str, int]]   # e.g. [("sc", 3), ("dc", 1)]
    width_stitches: int
    rows: int
    colors: dict[str, str]
    opportunity_score: float = 0.0
    season: str | None = None
    risk_class: str = "A"
    # The yarn the pattern is written for. The gauge is derived from it (F-116), never typed.
    yarn_weight: str = "worsted"
    source_brief: dict | None = None
    source_provenance: str | None = None


# The producer chain `concept_to_cir` names when its caller does not say more.
CONCEPT_TO_CIR_PRIMITIVES: tuple[str, ...] = (
    "runtime.pipeline.concept_to_cir", "creative.prototype.gauge_for")


def concept_to_cir(c: Concept, version: str = "1.0.0",
                   primitives: tuple[str, ...] = CONCEPT_TO_CIR_PRIMITIVES) -> CIR:
    """Build a machine-verifiable CIR from a concept.

    Only produces geometry the compiler can check: a flat two-colour panel worked over a
    foundation that the repeat divides evenly. If the repeat does not divide the width, this
    returns a CIR that will *fail* compilation rather than quietly fudging the numbers.
    """
    from ..creative.prototype import gauge_for, source_provenance

    unit = sum(n for _, n in c.stitch_repeat)
    palette = list(c.colors)
    rows: list[Row] = []
    for i in range(1, c.rows + 1):
        color = palette[(i - 1) % len(palette)] if palette else None
        if i == 1:
            ops = [Op("sc", c.width_stitches)]
        elif i % 2 == 0:
            ops = [Repeat([Op(code, n) for code, n in c.stitch_repeat], times=None)]
        else:
            ops = [Op("sc", c.width_stitches)]
        rows.append(Row(index=i, ops=ops, declared_count=c.width_stitches,
                        turning_chain=1, color=color))

    return CIR(
        slug=c.slug,
        title=c.title,
        version=version,
        construction="flat_rows",
        risk_class=c.risk_class,
        colors=dict(c.colors),
        # F-116: the gauge is the middle of the declared yarn's published band, the same
        # derivation `creative.prototype` authors with. This line used to be a typed
        # Gauge(16, 14) against worsted -- a fabric worsted cannot make (band 11-14 sc/10cm),
        # so every templated concept certified with a size and yardage its own yarn could not
        # produce.
        gauge=gauge_for(c.yarn_weight),
        materials=[Material(name=f"{c.yarn_weight} acrylic", yarn_weight=c.yarn_weight,
                            color_id=p)
                   for p in palette],
        components=[Component(name="panel", construction="flat_rows", rows=rows,
                              foundation=c.width_stitches, foundation_kind="chain")],
        designer_notes=f"{c.category} concept, unit repeat {unit} sts",
        provenance=source_provenance(c.slug,
            {**c.__dict__, "provenance": c.source_provenance}, c.source_brief,
            tuple(primitives)),
    )


# Per-category geometry. Deliberately a lookup table rather than a model call: the stitch
# structure of a product is an engineering decision that must be reproducible, and section 2
# forbids asking a model to supply instructions. Every entry is a repeat whose unit divides
# the stated width, so the compiler's divisibility check passes for a reason rather than by
# luck.
_GEOMETRY: dict[str, dict] = {
    # Mosaic and graphghan size truth: both are throws. At 24 rows they drafted 128 x 20 and
    # 112 x 17 cm strips, which the blanket band refused. Every catalogue seed in these
    # categories is engineered (its own chart), so only research and radar concepts use these
    # plain templates, and their row counts are not tied to a chart.
    "mosaic_blanket": {"stitch_repeat": [["sc", 3], ["dc", 1]], "width": 160, "rows": 188},
    # Blanket size truth: a throw is about 127 x 152 cm (Craft Yarn Council standard blanket
    # sizes). 24 rows drafted a 128 x 22 cm strip that certification called a blanket.
    "blanket":        {"stitch_repeat": [["dc", 2], ["sc", 2]], "width": 160, "rows": 168},
    "graphghan":      {"stitch_repeat": [["sc", 4]],            "width": 140, "rows": 192},
    "baby":           {"stitch_repeat": [["sc", 2], ["dc", 2]], "width": 100, "rows": 20},
    "seasonal_decor": {"stitch_repeat": [["sc", 2], ["dc", 2]], "width": 40,  "rows": 12},
    "runner":         {"stitch_repeat": [["sc", 3], ["dc", 1]], "width": 40,  "rows": 148},
    "placemat":       {"stitch_repeat": [["sc", 3], ["dc", 1]], "width": 56,  "rows": 37},
    # A4A-1: a dishcloth is its own object, not a placemat: a square of about 22 x 22 cm at
    # the certified worsted gauge (28 sts x 27 rows), inside the size band certification
    # enforces (`gates.certificate.OBJECT_SIZE_BANDS`).
    "dishcloth":      {"stitch_repeat": [["sc", 3], ["dc", 1]], "width": 28,  "rows": 27},
    "coaster":        {"stitch_repeat": [["sc", 2], ["dc", 2]], "width": 12,  "rows": 11},
    "basket":         {"stitch_repeat": [["sc", 4]],            "width": 48,  "rows": 14},
    "pillow":         {"stitch_repeat": [["dc", 2], ["sc", 2]], "width": 52,  "rows": 46},
    # S1 Product Truth: a wall hanging is a portrait panel of about 40 x 60 cm (the
    # prototype's `wall_hanging` form), not the 35 x 14 cm strip this drafted.
    "wall_decor":     {"stitch_repeat": [["sc", 2], ["dc", 2]], "width": 52,  "rows": 66},
    "flower":         {"stitch_repeat": [["sc", 2], ["dc", 2]], "width": 24,  "rows": 8},
    # S1 Product Truth: a flat pet mat is about 50 x 45 cm (a cat or small dog lies on it),
    # not the 48 x 15 cm strip this drafted. A pet bed is a vessel (fallback_constructions).
    "pet":            {"stitch_repeat": [["sc", 3], ["dc", 1]], "width": 64,  "rows": 50},
    "scarf":          {"stitch_repeat": [["dc", 2], ["sc", 2]], "width": 24,  "rows": 168},
    "ornament":       {"stitch_repeat": [["sc", 2], ["dc", 2]], "width": 24,  "rows": 8},
}
_DEFAULT_GEOMETRY = {"stitch_repeat": [["sc", 3], ["dc", 1]], "width": 40, "rows": 12}

# S1 Product Truth (size-family routing): the object a title names decides the size where the
# category alone cannot. The `baby` category holds hats, blankets and small items, so a "Baby
# Blanket" on its template was refused by the blanket band; and a ring cushion is a small
# square, not a pillow or the default strip. First match wins; each entry's size sits inside
# the band certification holds that object to (`gates.certificate.OBJECT_SIZE_BANDS`).
_TITLE_GEOMETRY: tuple[tuple[str, frozenset | None, dict], ...] = (
    # A ring bearer's cushion: about 19 x 19 cm.
    (r"\bring[- ]?(?:bearer\s+)?(?:cushion|pillow)s?\b", None,
     {"stitch_repeat": [["dc", 2], ["sc", 2]], "width": 24, "rows": 21}),
    # A baby (stroller) blanket: about 80 x 89 cm (Craft Yarn Council: 76 x 89 cm stroller).
    (r"\b(?:blanket|afghan|throw|blankie)s?\b", frozenset({"baby"}),
     {"stitch_repeat": [["sc", 2], ["dc", 2]], "width": 100, "rows": 98}),
)


def _geometry_entry(category: str, title: str | None) -> dict:
    """The template `concept_geometry` uses: a title-named object first, then the category."""
    import re as _re

    from ..creative.fallback_constructions import fold_title

    folded = fold_title(title)
    for pattern, categories, entry in _TITLE_GEOMETRY:
        if (categories is None or category in categories) and _re.search(pattern, folded):
            return entry
    return _GEOMETRY.get(category, _DEFAULT_GEOMETRY)

_PALETTES: dict[str, dict[str, str]] = {
    "nordic-forest": {"forest": "#244A3A", "cream": "#FAF6EB"},
    "autumn-oak": {"wine": "#6E1F2A", "gold": "#C49545"},
    "cloudline": {"cream": "#FAF6EB", "ink": "#1A2B3C"},
}
_DEFAULT_PALETTE = {"forest": "#244A3A", "cream": "#FAF6EB"}


def _template_size(stitch_repeat: tuple, width: int, rows: int) -> tuple[float, float]:
    """The finished (width, height) in cm a template makes: its own twin, measured once."""
    key = (stitch_repeat, width, rows)
    if key not in _TEMPLATE_SIZE:
        from ..cir.compiler import compile_cir
        from ..cir.twin import build_twin

        probe = Concept(slug="size-probe", title="size probe", category="probe",
                        stitch_repeat=[tuple(x) for x in stitch_repeat], width_stitches=width,
                        rows=rows, colors=dict(_DEFAULT_PALETTE))
        cir = concept_to_cir(probe)
        twin = build_twin(cir, compile_cir(cir))
        _TEMPLATE_SIZE[key] = (float(twin.width_cm), float(twin.height_cm))
    return _TEMPLATE_SIZE[key]


_TEMPLATE_SIZE: dict[tuple, tuple[float, float]] = {}


def _sized(g: dict, width: int, target: tuple[float, float]) -> tuple[int, int]:
    """Stitches and rows that make `target` (short, long) cm on template `g`, keeping the
    template's orientation (a runner stays long in rows, a placemat wide in stitches).

    S1 review 6958883678 H2: a title's requested size is drafted, not replaced by the
    template's. Scaled from the template's own measured twin, so the result is the same
    deterministic arithmetic the twin will check."""
    from ..creative import size_truth

    unit = sum(n for _, n in g["stitch_repeat"])
    w0, h0 = _template_size(tuple(tuple(x) for x in g["stitch_repeat"]), width, g["rows"])
    short, long_ = target
    if size_truth._met(short, min(w0, h0)) and size_truth._met(long_, max(w0, h0)):
        # The template already makes the asked size: its numbers (and every release
        # fingerprint drafted from them) stay as they are.
        return width, g["rows"]
    tw, th = (short, long_) if w0 <= h0 else (long_, short)
    sts = max(unit, int(round(width * tw / w0 / unit)) * unit)
    rows = max(2, int(round(g["rows"] * th / h0)))
    return sts, rows


def drafted_size(category: str | None, title: str | None) -> tuple[float, float]:
    """The finished (width, height) in cm the flat template drafts for this title: the
    `concept_geometry` numbers, measured by their own compiled twin (S1F2-LOW: the plan checks
    this size with the certificate's size check, so plan and certify agree)."""
    from types import SimpleNamespace

    g = concept_geometry(SimpleNamespace(category=category, title=title, family=None))
    return _template_size(tuple(tuple(x) for x in g["stitch_repeat"]), g["width_stitches"],
                          g["rows"])


def concept_geometry(seed: ConceptSeed) -> dict:
    """Turn a market concept into the numbers the CIR builder needs."""
    from ..creative import size_truth

    g = _geometry_entry(seed.category, seed.title)
    unit = sum(n for _, n in g["stitch_repeat"])
    width = g["width"]
    if width % unit:
        # Round up to a multiple of the repeat rather than emitting a CIR we know will fail.
        width += unit - (width % unit)
    rows = g["rows"]
    req = size_truth.request(seed.category, seed.title)
    if req["target"] is not None and not req["refused"]:
        width, rows = _sized(g, width, req["target"])
    return {
        "stitch_repeat": [list(x) for x in g["stitch_repeat"]],
        "width_stitches": width,
        "rows": rows,
        "colors": dict(_PALETTES.get(seed.family or "", _DEFAULT_PALETTE)),
    }


def _seed_for(slug: str, db=None) -> ConceptSeed | None:
    """The radar concept `slug` names: the static POOL first (unchanged), then -- when a
    database is given -- a concept `radar.intake` approved from recorded evidence (W5-CONCEPT).
    """
    seed = next((s for s in POOL if s.slug == slug), None)
    if seed is None and db is not None:
        from ..radar import intake

        seed = intake.seed_for(db, slug)
    return seed


def product_seed(slug: str, db=None) -> ConceptSeed | None:
    """The radar concept a PRODUCT slug was scored as: its own, or its retired alias (D-W5-7).

    For readers keyed on a certified product (teardown class, benchmark challenge, storefront
    strength). `_seed_for` stays exact for the drafting path, where a seed decides whether a
    payload is a new concept for the pre-engineering gate.
    """
    seed = _seed_for(slug, db)      # F6: an approved intake concept answers too
    if seed is None:
        from ..products import launch0 as l0

        alias = l0.radar_concept_for(slug)
        seed = _seed_for(alias, db) if alias else None
    return seed


# ---- job handlers --------------------------------------------------------


@handlers.register("radar.scan")
def handle_radar_scan(ctx: JobContext) -> dict:
    """Score the real opportunity pool and emit the release candidates.

    Section 33: the pool is at least 30 concepts across several categories, scored before any
    SKU is committed. `select_portfolio` applies the structural constraints -- flagship
    seasonal, several fast low-price makes, a bundle-ready family, an evergreen search
    product, Class C capped -- so a run cannot quietly become ten Christmas blankets.
    """
    today = _scan_date(ctx)
    target = int(ctx.job.inputs.get("target", 10))
    # C-60 (#2): the observed market scores -- the nine-dimension arbitrage card and its
    # weakness hunt -- steer the pool before selection, so the hunt decides what gets made.
    from ..radar import arbitrage, intake
    from ..radar.opportunity import score_pool

    # W5-CONCEPT: POOL plus the concepts `radar.intake` approved from recorded evidence,
    # scored by the same `score_concept`. With no approved row this is exactly POOL.
    steered, steering = arbitrage.steer_concepts(
        ctx.db, score_pool(intake.pool_with_intake(ctx.db), today=today))
    # WS5 E5: the same bounded lesson nudge `radar.score` applies (internal and buyer lessons
    # capped separately, decayed with age) also orders the candidates, so a measured buyer
    # signal can change which concept comes next. Read-only here: no lesson is marked acted.
    from dataclasses import replace as _replace

    from ..improve import consume as _consume

    nudges = _consume.rank_adjustments(ctx.db, [x.seed for x in steered])
    steered = [_replace(x, score=round(x.score + nudges.get(x.seed.slug, 0.0), 4))
               if nudges.get(x.seed.slug) else x for x in steered]
    # ENG-RECOVERY (prod 2026-11-19: original_product 0/0/0 for 7 days with 18 undrafted
    # concepts in the pool): `select_portfolio` ranks by score alone, so every scan returned
    # the same top 11, all drafted long ago, whose `draft:<slug>` keys were taken -- the
    # radar.score jobs promoted them and enqueued nothing. The portfolio is now chosen from
    # the concepts not yet drafted (the same section-33 rules, the same score threshold, risk
    # class and pre-engineering gate in radar.score and cir.draft); only when every concept
    # has been drafted does it fall back to the full pool, which is the `pool_exhausted`
    # stall the supply reading reports.
    #
    # Fix round 1 (review M1): "undrafted" was not enough. On the production pool (34
    # concepts, 16 drafted) it made three drafts and then re-selected the same ten every scan
    # -- eight refused by #88 (a radar slot with no premise or storyboard is not a concept),
    # one under the threshold -- and called that supply. The scan now selects from the
    # undrafted concepts `radar.score` would promote today (`promotion_verdict`: the same
    # threshold, risk class and pre-engineering gate). Only when none is, it selects as
    # before (undrafted, then the full pool) and the supply reading records the stall as
    # `selection_unpromotable` with each held concept's reason. No gate is relaxed here.
    from ..ops import flow_health as _fh

    try:
        _drafted = _fh.drafted_slugs(ctx.db, {c.slug for c in steered})
    except Exception:  # noqa: BLE001 - an unreadable draft record selects as before
        _drafted = set()
    undrafted = [c for c in steered if c.slug not in _drafted]
    promotable, held = promotable_now(ctx.db, undrafted, today) if undrafted else ([], {})
    # ENG-DEMAND-STALL: a promoted concept already offered and waiting on an engine that is
    # not certified is engine demand, not supply. Re-selecting it every scan while nothing can
    # draft it was a hidden stall. It stays queued in `supply` (admitted once its engine
    # certifies) and is reported as `engine_demand_undrafted`, held with its reason.
    try:
        from ..products import supply as _supply

        _waiting_engine = _supply.engine_demand_waiting(ctx.db)
    except Exception:  # noqa: BLE001 - an unreadable queue judges as before
        _waiting_engine = {}
    engine_demand = {c.slug: _waiting_engine[c.slug] for c in promotable
                     if c.slug in _waiting_engine}
    if engine_demand:
        promotable = [c for c in promotable if c.slug not in engine_demand]
        held = {**held, **engine_demand}
    portfolio, selection_pool = None, "promotable_undrafted"
    for tier, candidates in (("promotable_undrafted", promotable), ("undrafted", undrafted),
                             ("full_pool", steered)):
        if candidates:
            portfolio = select_portfolio(candidates, target=target, today=today)
            if portfolio.selected:
                selection_pool = tier
                break
    if portfolio is None:
        portfolio = select_portfolio(steered, target=target, today=today)
        selection_pool = "full_pool"

    ctx.audit("radar.scanned", detail={
        # L1: the full section-33 pool, and the sub-pool the selection was made from
        "pool": len(steered),
        "selection_pool": selection_pool,
        "selection_pool_size": len(portfolio.selected) + len(portfolio.rejected),
        "selected": len(portfolio.selected),
        "constraints_met": portfolio.constraints_met,
        "as_of": today.isoformat(),
        "arbitrage": steering,
        "drafted_excluded": len(steered) - len(undrafted),
        "unpromotable_excluded": len(held),
    })
    if not portfolio.ok:
        # Never silently ship a portfolio that violates section 33; say which rule broke.
        unmet = [k for k, v in portfolio.constraints_met.items() if not v]
        ctx.audit("radar.portfolio_constraints_unmet", detail={"unmet": unmet,
                                                              "reasons": portfolio.reasons})

    # #114: a wave is segmented by skill level, or it is one kind of work that looks busy.
    # Measured on the wave actually selected, and a missing level is written as a creative
    # brief -- the gap is filled by ideation, never by relabelling a product's difficulty.
    from ..creative import preengineering

    skills = preengineering.wave_skill_portfolio([c.seed for c in portfolio.selected])
    ctx.audit("radar.skill_portfolio", detail={**skills, "as_of": today.isoformat()})
    missing = preengineering.missing_skill_levels(skills["wave"])
    excess = [g["level"] for g in skills["wave"]["gaps"] if "want_at_most" in g]
    if missing or excess:
        ctx.audit("radar.skill_gap", detail={
            "missing": missing, "over": excess, "gaps": skills["wave"]["gaps"],
            "brief": (f"ideate new concepts at {missing} for this wave; they enter "
                      f"engineering only through the pre-engineering gate"
                      if missing else "the wave leans on one level; ideate the others"),
            "as_of": today.isoformat()})

    # W5-A7 (P0-SUPPLY-STALL): `draft:<slug>` is permanent, so a selected concept that was
    # drafted already can never become a new product. When nothing selected is undrafted the
    # company has no new concept supply; that is recorded once per scan date, never silent.
    # A reading fault never costs the scan.
    try:
        supply = _record_supply_stall(ctx, [c.slug for c in steered],
                                      [c.slug for c in portfolio.selected], today,
                                      promotable=[c.slug for c in promotable], held=held,
                                      engine_demand=sorted(engine_demand))
    except Exception as exc:  # noqa: BLE001
        supply = {"measured": False, "why": f"{type(exc).__name__}: {str(exc)[:160]}"}

    for c in portfolio.selected:
        ctx.enqueue("market_radar", "radar.score", c.to_dict(),
                    idempotency_key=f"score:{c.slug}:{today.isoformat()}")

    # A4(a) continuation: every scan also works the coverage-gap queue (radar.score with no
    # slug -> `_score_coverage_handoff`), so a gap whose ideation finished is followed by the
    # next eligible gap on this cadence with no session. Only when an open gap exists; keyed
    # per scan job, so a re-delivered scan queues nothing new.
    if _open_gap_count(ctx.db):
        ctx.enqueue("market_radar", "radar.score",
                    {"handoff": {"source": "radar.scan", "scan_job": ctx.job.id},
                     "as_of": today.isoformat()},
                    idempotency_key=f"coverage-handoff:scan:{ctx.job.id}")

    # F-051: observed demand in a pod our catalogue does not cover becomes a coverage gap on
    # the queue radar.score's gap handoff already works -- expansion by new queries, never
    # by near-duplicate SKUs. A planner fault never costs the scan.
    try:
        from ..commerce import portfolio as portfolio_mod

        expansion = portfolio_mod.expansion_plan(ctx.db)
    except Exception as exc:  # noqa: BLE001
        expansion = {"measurable": False, "why": f"{type(exc).__name__}: {str(exc)[:160]}"}

    return {
        "expansion": {k: expansion.get(k) for k in ("measurable", "opportunities", "why")},
        "pool_size": len(steered),
        "selection_pool": selection_pool,
        "selection_pool_size": len(portfolio.selected) + len(portfolio.rejected),
        "selected": [c.slug for c in portfolio.selected],
        "constraints_met": portfolio.constraints_met,
        "swaps": portfolio.reasons,
        "arbitrage_steered": [m["slug"] for m in steering["steered"]],
        "concept_supply": supply,
        "skill_portfolio": {"segmented": skills["wave"]["segmented"],
                            "shares": skills["wave"]["shares"], "missing": missing,
                            "over": excess},
        "as_of": today.isoformat(),
    }


def _record_supply_stall(ctx: JobContext, pool: list[str], selected: list[str],
                         today: date, *, promotable: list[str] | None = None,
                         held: dict[str, str] | None = None,
                         engine_demand: list[str] | None = None) -> dict:
    """W5-A7 (P0-SUPPLY-STALL): the next-product supply reading of one `radar.scan`.

    Supply is a selected concept with no `draft:<slug>` job that `radar.score` would promote
    today (`promotion_verdict`); `radar.score` is the only path that turns one into a
    `cir.draft`, under that same permanent key, so a drafted slug is never drafted twice and
    is not supply, and neither is a concept the score threshold, risk class or
    pre-engineering gate refuses. With none, one `OperatingReading`
    (`flow_health.SUPPLY_STALL_KIND`, period = the scan date) and one audit record the stall:
    `pool_exhausted` when every concept in POOL plus approved intake is drafted;
    `selection_unpromotable` (ENG-RECOVERY fix round 1, review M1) when undrafted concepts
    remain but none would be promoted (each held concept's reason is recorded);
    `promotable_not_selectable` when promotable ones exist but section 33 could not select
    them on their own; `engine_demand` when every undrafted concept left is a promoted
    concept waiting in the supply queue for an engine that is not certified yet (such a
    concept is counted as `engine_demand_undrafted`, never as `promotable_undrafted`);
    `selection_all_drafted` when promotability was not judged. Deterministic, deduplicated per period, and read-only for the
    queue: it enqueues nothing.

    `promotable` None means the caller did not judge promotability (the W5-A7 reading).
    """
    from sqlalchemy import select
    from sqlalchemy.exc import IntegrityError

    from ..core.models import OperatingReading
    from ..ops import flow_health

    drafted = flow_health.drafted_slugs(ctx.db, set(pool) | set(selected))
    undrafted_pool = sorted(s for s in set(pool) if s not in drafted)
    judged = promotable is not None
    can = set(promotable or ()) if judged else set(undrafted_pool)
    undrafted_selected = [s for s in selected if s not in drafted]
    supply_selected = [s for s in undrafted_selected if s in can]
    held = dict(held or {})
    waiting_engine = set(engine_demand or ()) & set(undrafted_pool)
    can -= waiting_engine
    supply_selected = [s for s in supply_selected if s not in waiting_engine]
    out = {"measured": True, "pool": len(set(pool)), "drafted": len(drafted & set(pool)),
           "undrafted_pool": len(undrafted_pool), "undrafted_selected": len(undrafted_selected),
           "promotable_undrafted": len(can & set(undrafted_pool)) if judged else None,
           "engine_demand_undrafted": len(waiting_engine),
           "supply_selected": len(supply_selected),
           "stalled": not supply_selected, "recorded": False}
    if supply_selected:
        return out
    if not undrafted_pool:
        reason = "pool_exhausted"
    elif judged and waiting_engine and not (set(undrafted_pool) - waiting_engine):
        reason = "engine_demand"
    elif judged and not (can & set(undrafted_pool)):
        reason = "selection_unpromotable"
    elif judged:
        # promotable concepts exist but section 33 could not select them on their own (a
        # lone bundle is held unless its members are selected with it)
        reason = "promotable_not_selectable"
    else:
        reason = "selection_all_drafted"
    out["reason"] = reason
    if waiting_engine:
        out["engine_demand"] = sorted(waiting_engine)[:50]
    if reason in ("selection_unpromotable", "engine_demand"):
        out["held"] = {k: held[k] for k in sorted(held)[:50]}
    period = today.isoformat()
    payload = {"reason": reason,
               "pool": out["pool"], "drafted": out["drafted"],
               "undrafted_pool": undrafted_pool[:50], "selected": list(selected)[:50],
               "held": out.get("held") or {},
               "engine_demand": out.get("engine_demand") or [],
               "as_of": period, "job_id": ctx.job.id}
    try:
        with ctx.db.session() as s:
            if s.scalar(select(OperatingReading.id).where(
                    OperatingReading.kind == flow_health.SUPPLY_STALL_KIND,
                    OperatingReading.period_key == period)) is not None:
                return out
            s.add(OperatingReading(kind=flow_health.SUPPLY_STALL_KIND, period_key=period,
                                   payload=payload))
    except IntegrityError:          # a concurrent scan recorded this period first
        return out
    out["recorded"] = True
    ctx.audit("radar.supply_stall", detail=payload)
    return out


def _scan_date(ctx: JobContext) -> date:
    raw = ctx.job.inputs.get("as_of")
    return date.fromisoformat(raw) if raw else date.today()


def _scan_date_utc(ctx: JobContext) -> date:
    """`_scan_date` on the UTC calendar. Portfolio work is keyed by ISO week, and a host-local
    date would move a week boundary by the host's offset (review PORTFOLIO ee5dbeee N6)."""
    from datetime import datetime, timezone

    raw = ctx.job.inputs.get("as_of")
    return date.fromisoformat(raw) if raw else datetime.now(timezone.utc).date()


_OPEN_GAP_STATES = ("uncovered", "concepting")


def _open_gap_count(db) -> int:
    from sqlalchemy import func, select

    from ..core.models import CoverageGap

    with db.session() as s:
        return int(s.scalar(select(func.count(CoverageGap.id))
                            .where(CoverageGap.state.in_(_OPEN_GAP_STATES))) or 0)


def _score_coverage_handoff(ctx: JobContext, inputs: dict) -> dict:
    """radar.score without a concept: score the open coverage-gap queue (#314) by concept.

    One implementation of two independent fixes (INTEG3 89af16b, W4-B2CLOSE 2190561). Every
    open gap (uncovered / concepting) is answered by the pool concepts that serve it:
    the product it names (`product_slug`, set once work entered the arena), and otherwise the
    concepts its pod routes (the same `Pod.matches` rule `intel.observe` uses to decide an
    arena is uncovered). Each concept is re-scored through the ordinary per-slug radar.score
    -- same steering, evidence discount, lesson nudge and pre-engineering gate, not a second
    scorer -- keyed like `radar.scan` (`score:<slug>:<date>`), so a concept already queued
    today is not queued twice. A gap no concept answers is reported (an ideation need), never
    scored as zero and never answered with a guessed concept.
    """
    from sqlalchemy import select

    from ..core.models import CoverageGap
    from ..intel import pods
    from ..radar import intake

    today = _scan_date(ctx)
    handoff = inputs.get("handoff") or {}
    pool = intake.pool_with_intake(ctx.db)
    with ctx.db.session() as s:
        gaps = list(s.execute(select(CoverageGap.id, CoverageGap.pod, CoverageGap.arena,
                                     CoverageGap.product_slug)
                              .where(CoverageGap.state.in_(_OPEN_GAP_STATES))
                              .order_by(CoverageGap.id)).all())

    matched: dict[str, list[int]] = {}
    unanswered: list[dict] = []
    for gap_id, pod_key, arena, product_slug in gaps:
        named = _seed_for(product_slug, ctx.db) if product_slug else None
        if named is not None:
            seeds = [named]
        else:
            pod = pods.BY_KEY.get(pod_key)
            seeds = [sd for sd in pool
                     if pod is not None and pod.matches(sd.slug.replace("-", " "))]
        if not seeds:
            unanswered.append({"gap": gap_id, "pod": pod_key, "arena": arena})
        for sd in seeds:
            matched.setdefault(sd.slug, []).append(gap_id)

    queued: list[str] = []
    already: list[str] = []
    for slug in sorted(matched):
        payload = score_concept(_seed_for(slug, ctx.db), today).to_dict()
        payload["coverage_gaps"] = matched[slug]
        job = ctx.enqueue("market_radar", "radar.score", payload,
                          idempotency_key=f"score:{slug}:{today.isoformat()}")
        (queued if job is not None else already).append(slug)
    # A4(a) P0-RESEARCH-TO-CONCEPT: a gap no concept answers is an ideation need, and it now
    # becomes one research task per gap carrying the ideation brief {gap, pod, arena}; the
    # research step answers it from recorded observations and proposes a concept to intake.
    # Bounded (radar.ideation.MAX_IN_FLIGHT) and idempotent per gap; never a guessed concept.
    from ..radar import ideation

    ideated = ideation.open_briefs(ctx, unanswered, today=today)
    ctx.audit("radar.gap_queue_scored", detail={
        "source": sorted(k for k in inputs if k != "slug") or ["no inputs"],
        "open_gaps": len(gaps), "queued": queued, "already_queued": already,
        "without_a_pool_concept": unanswered[:50], "handoff": handoff,
        "ideation": {k: ideated[k] for k in ("opened", "already", "waiting", "completed")},
        "as_of": today.isoformat()})
    return {"slug": None, "score": None, "promoted": False, "mode": "coverage_handoff",
            "open_gaps": len(gaps), "queued": queued, "already_queued": already,
            "without_a_pool_concept": len(unanswered), "unanswered": unanswered[:50],
            "ideation": ideated,
            "reason": ("coverage-gap queue: each open gap's pool concepts re-scored by slug"
                       if queued or already else
                       "no open coverage gap has a concept in the radar pool; nothing to "
                       "score (UNKNOWN, not zero)")}


def promotion_verdict(db, seed, c: dict, today: date) -> dict:
    """Whether `radar.score` promotes this concept now, and every number it decides on.

    Read-only: the records (`radar.evidence_discount`, the lesson acts, the gate record) are
    written by `radar.score` itself. ENG-RECOVERY fix round 1 (review M1): `radar.scan` asks
    this same function before it selects, so a concept refused here -- under
    PROMOTION_THRESHOLD, outside risk class A/B, or not passed by the pre-engineering gate
    (#88's premise and storyboard first) -- is not selected as new supply. One rule, two
    callers; the gate is not re-implemented or relaxed anywhere.
    """
    from ..creative import preengineering
    from ..improve import consume
    from ..radar import arbitrage
    from ..radar import provenance as trend_provenance

    rescored = score_concept(seed, today)
    # #2: the same steering as the scan, so a concept is promoted on the score it was selected
    # on rather than on a base score the market evidence has already moved. Then the #38
    # evidence discount and the #97 lesson nudge apply to the steered score, in that order.
    rescored = arbitrage.steer_concepts(db, [rescored])[0][0]
    # #38 (C-69): the score is discounted by the stamped trend evidence about this concept --
    # stale or foreign-population evidence lowers it, and the discounted score is the one
    # that decides promotion.
    evidence = trend_provenance.evidence_for(db, seed, today=today)
    evidence_score = round(rescored.score * evidence["discount"], 4)
    # #97 / #147: Market Radar reads its lesson inbox where it decides. A lesson whose words
    # match this concept nudges the score within a bound; `radar.score` records the act.
    concept_text = consume.concept_text(seed, c)
    radar_lessons = [l for l in consume.matching(db, "market_radar", concept_text)
                     if l["direction"]]
    lesson_adjustment = consume.score_adjustment(radar_lessons)
    adjusted = round(evidence_score + lesson_adjustment, 4)
    promote = adjusted >= PROMOTION_THRESHOLD and seed.risk_class in ("A", "B")
    # The pre-engineering gate (#83, #87, #88, #108, #110, #115, #125, #126). An opportunity
    # score says a slot is worth filling; it says nothing about whether *this idea* deserves
    # engineering. A design the catalogue already has is a rebuild and passes as one; anything
    # else is a new concept and must clear the whole deterministic sequence, or it is not
    # engineered -- refused back to creative development, or left waiting, unpassed, on a
    # judgement nobody can make yet.
    gate = None
    exempt = None
    if promote:
        exempt = (preengineering.established(db, seed.slug)
                  or ("a bundle is assembled from its members' releases, not engineered"
                      if seed.is_bundle else None))
        if not exempt:
            gate = preengineering.gate_concept(db, c, today=today)
            promote = gate["engineer"]
    why = None if promote else (
        "Class C requires physical testing that does not exist yet"
        if seed.risk_class == "C" else
        gate["consequence"] if gate is not None else
        f"score {evidence_score} below promotion threshold {PROMOTION_THRESHOLD}"
        + (f" after the evidence discount ({evidence['why']})"
           if evidence.get("measured") else ""))
    return {"rescored": rescored, "evidence": evidence, "evidence_score": evidence_score,
            "radar_lessons": radar_lessons, "lesson_adjustment": lesson_adjustment,
            "adjusted": adjusted, "promote": promote, "gate": gate, "exempt": exempt,
            "concept_text": concept_text, "why": why}


def _score_inputs(db, scored) -> dict:
    """The inputs `radar.score` would judge a scanned concept on (`radar.scan` enqueues
    `scored.to_dict()`; an intake concept is judged on its database row, F2)."""
    c = scored.to_dict()
    if scored.seed.origin:
        from ..radar import intake

        c = intake.gate_inputs(db, scored.seed.slug, c)
    return c


def promotable_now(db, scored_concepts, today: date) -> tuple[list, dict[str, str]]:
    """(the concepts `radar.score` would promote today, {slug: why not} for the rest)."""
    keep, held = [], {}
    for x in scored_concepts:
        try:
            seed = _seed_for(x.seed.slug, db) or x.seed
            v = promotion_verdict(db, seed, _score_inputs(db, x), today)
        except Exception as exc:  # noqa: BLE001 - a verdict that cannot be read is no promotion
            held[x.seed.slug] = f"unreadable verdict: {type(exc).__name__}: {str(exc)[:120]}"
            continue
        if v["promote"]:
            keep.append(x)
        else:
            gate = v["gate"] or {}
            detail = (f" (failed {gate.get('failed')}; waiting on {gate.get('waiting_on')}: "
                      f"{'; '.join(gate.get('reasons') or [])[:160]})" if gate else "")
            held[x.seed.slug] = (str(v["why"] or "not promoted") + detail)[:400]
    return keep, held


@handlers.register("radar.score")
def handle_radar_score(ctx: JobContext) -> dict:
    """Re-score the candidate on its own and promote it only if it still clears the bar.

    Scoring happens twice on purpose. `radar.scan` scores to *rank* a pool; this re-scores a
    single candidate at the moment it is about to consume engineering effort, because a job
    can sit in the queue for days and a seasonal window can close underneath it.
    """
    c = dict(ctx.job.inputs)
    if not c.get("slug"):
        # A mission rather than a concept: the Intelligence charter generates radar.score
        # from its CoverageGap handoff ("scores the coverage gap queue", autonomy/charters.py)
        # and Laura's follow-on proposals do the same. This read `c["slug"]` and production
        # 7bbbe72 dead-lettered two (KeyError 'slug', 2026-10-12T18:06Z) -- #195's window.
        return _score_coverage_handoff(ctx, c)
    seed = _seed_for(c["slug"], ctx.db)
    if seed is None:
        ctx.audit("radar.unknown_concept", artifact=c.get("slug"))
        return {"slug": c.get("slug"), "promoted": False, "reason": "not in the pool"}
    intake_fields: dict = {}
    if seed.origin:
        # W5-CONCEPT: an intake concept is judged on the concept and brief its database row
        # holds (and the vision judge's record, if any) -- read here, never from the job.
        from ..radar import intake

        # F2 (review 933bf74): the job's own concept/brief/taste fields are dropped, not merged.
        intake_fields = intake.gate_inputs(ctx.db, seed.slug, {})
        c = intake.gate_inputs(ctx.db, seed.slug, c)

    today = _scan_date(ctx)
    # ENG-RECOVERY fix round 1 (review M1): the decision is `promotion_verdict`, the one
    # function `radar.scan` also asks before it selects, so the scan can never select a
    # concept this handler would refuse on the same inputs. The records are written here.
    v = promotion_verdict(ctx.db, seed, c, today)
    rescored, evidence, evidence_score = v["rescored"], v["evidence"], v["evidence_score"]
    radar_lessons, lesson_adjustment = v["radar_lessons"], v["lesson_adjustment"]
    adjusted, promote, gate, exempt = v["adjusted"], v["promote"], v["gate"], v["exempt"]
    concept_text = v["concept_text"]
    from ..improve import consume

    ctx.audit("radar.evidence_discount", artifact=seed.slug,
              detail={"raw_score": rescored.score, "score": evidence_score, **evidence})
    if radar_lessons:
        consume.act(ctx.db, "market_radar", radar_lessons,
                    how=f"radar.score of {seed.slug} moved {lesson_adjustment:+} to {adjusted} "
                        f"(evidence-discounted {evidence_score})")
    if exempt:
        ctx.audit("concept.gate_exempt", artifact=seed.slug,
                  detail={"reason": exempt, "source": "radar.score"})
    elif gate is not None:
        from ..creative import preengineering

        preengineering.record(ctx, gate, source="radar.score")

    ctx.audit("radar.scored", artifact=seed.slug, detail={
        "score": adjusted, "raw_score": rescored.score, "evidence_score": evidence_score,
        "evidence_discount": evidence["discount"], "components": rescored.components,
        "lesson_adjustment": lesson_adjustment,
        "lessons": [l["id"] for l in radar_lessons],
        "promoted": promote,
        "gate": (gate or {}).get("decision") or ("exempt" if exempt else None),
    })
    if promote:
        payload = rescored.to_dict()
        payload.update(intake_fields)
        payload.update(concept_geometry(seed))
        if gate is not None:
            payload["gate"] = {"decision": gate["decision"], "as_of": gate["as_of"]}
        # #97: Pattern Engineering prioritises what its lessons favour. A favoured lesson
        # matching this concept is a *heuristic* reason to claim the draft earlier inside its
        # band (`swarm.orchestrate.HEURISTIC_KEY`, bounded to one step) -- never a CAD value:
        # a lesson match is not a sourced estimate of what the work is worth (C-66 / M05),
        # and the currency fields stay for estimates that say where they came from. The
        # benefit of the nudge is recorded as unmeasured until the draft's outcome is read.
        eng_lessons = [l for l in consume.matching(ctx.db, "pattern_engineering",
                                                   concept_text) if l["direction"] > 0]
        if eng_lessons:
            from ..swarm.orchestrate import HEURISTIC_KEY, MAX_HEURISTIC_STEPS

            payload[HEURISTIC_KEY] = {
                "source": "pattern_engineering lessons (#97)",
                "lessons": [l["id"] for l in eng_lessons],
                "steps": min(MAX_HEURISTIC_STEPS, len(eng_lessons)),
                "reason": (f"{len(eng_lessons)} favouring lesson(s) match this concept: "
                           + "; ".join(", ".join(l["shared"][:3]) for l in eng_lessons))[:200],
                "benefit": "unmeasured: a bounded heuristic nudge, not an expected value"}
            payload["lessons"] = [l["id"] for l in eng_lessons]
            consume.act(ctx.db, "pattern_engineering", eng_lessons,
                        how=(f"cir.draft of {seed.slug} moved up to {MAX_HEURISTIC_STEPS} "
                             f"step inside its band by a lesson heuristic; benefit unmeasured "
                             f"until the draft's outcome is read"))
        # ENG-SUPPLY: offered to the capacity-aware admission controller, not enqueued
        # directly. Admitted at once when there is room (the same `draft:<slug>` job and
        # payload), otherwise it waits in the supply queue for the next free slot.
        from ..products import supply

        admission = supply.offer(ctx, slug=seed.slug, payload=payload,
                                 key=f"draft:{seed.slug}", source="radar.score",
                                 family=seed.family, demand=adjusted,
                                 research=bool(seed.origin))
    return {"slug": seed.slug, "score": adjusted,
            "admission": admission if promote else None, "raw_score": rescored.score,
            "evidence_score": evidence_score,
            "evidence": {k: evidence.get(k) for k in ("measured", "discount", "rows",
                                                      "mean_weight", "why")},
            "promoted": promote,
            "lesson_adjustment": lesson_adjustment, "adjusted_score": adjusted,
            "components": rescored.components,
            "gate": (None if gate is None else
                     {k: gate[k] for k in ("decision", "failed", "unmeasured", "reasons",
                                           "waiting_on", "consequence")}),
            "gate_exempt": exempt,
            "reason": v["why"]}


# Concepts whose pattern is engineered rather than templated. The generic builder below makes
# a striped panel, which proves the machinery and is not a product; where a real design exists
# it wins. A slug absent from here is not a failure -- it means that concept has not been
# through design yet, and the templated geometry stands in until it has.
# Concepts whose pattern is engineered rather than templated. The generic builder below makes
# a striped panel, which proves the machinery and is not a product. A slug absent from here is
# not a failure -- it means that concept has not been through design yet, and the templated
# geometry stands in until it has.
#
# `nordic_forest` stays a module of its own because it is the flagship and its motif was
# hand-placed; everything else is generated from the motif library by `products.builder`,
# which is how twelve exceptional products are achievable without twelve chances to slip.
# "module" or "module:function", so one module can hold several engineered designs.
ENGINEERED: dict[str, str] = {
    "nordic-forest-mosaic-throw": "brambleloop.products.nordic_forest",
    # Both of these were flat rectangles named for shapes they did not make: the basket was a
    # side panel with no seaming instructions, the "hexagon" coaster had the same stitch
    # count on every row. They are worked in the round now (B-059).
    #
    # PT-11: they were registered here under the radar concepts' slugs (`market-basket-trio`,
    # `hexie-coaster-set`), which made the medium Launch-0 basket and the Launch-0 coaster set
    # buildable as second, out-of-scope products. The Launch-0 variants are the engineered
    # designs now, under their own slugs; the concept slugs are retired
    # (`products.launch0.LEGACY_DUPLICATES`) and routed to these by `cir.draft`.
    "market-basket-small": "launch0:basket_small",
    "market-basket-medium": "launch0:basket_medium",
    "market-basket-large": "launch0:basket_large",
    "hexagon-coaster-set": "launch0:hexagon_coasters",
    # And three more named for techniques their patterns could not contain: a cable throw
    # with no crossing, a bobble pillow with no bobble, a ribbed scarf with no rib. All three
    # were plain sc/dc colourwork (B-080).
    "heirloom-cable-blanket": "brambleloop.products.texture:build_cable_throw",
    "bobble-floor-pillow": "brambleloop.products.texture:build_bobble_pillow",
    "chunky-ribbed-scarf": "brambleloop.products.texture:build_ribbed_scarf",
    # W4-PIPE2: the moment-first creative candidates. A candidate that clears the taste gate
    # (regate -> ENGINEERING -> `cir.draft`) builds its engineered CIR, never a prototype.
    "reading-nook-cable-wrap": "brambleloop.products.moment_candidates:reading_nook_cable_wrap",
    "mothers-day-heart-tea-cosy":
        "brambleloop.products.moment_candidates:mothers_day_heart_tea_cosy",
    "snowfall-advent-garland": "brambleloop.products.moment_candidates:snowfall_advent_garland",
    "heart-row-ring-pillow": "brambleloop.products.moment_candidates:heart_row_ring_pillow",
    "housewarming-key-basket": "brambleloop.products.moment_candidates:housewarming_key_basket",
    "spring-garden-kneeler": "brambleloop.products.moment_candidates:spring_garden_kneeler",
}
# W4-PRODUCT: the Nordic Forest baby size is a catalogue-floor PROPOSAL product under its own
# size slug (the throw stays the concept slug above). It is registered only once the owner
# approves raising the Launch-0 cap (`products.launch0.CATALOGUE_FLOOR_APPROVED`); until then
# `products.launch0.cir_for("nordic_forest_baby")` builds it for measurement.
PROPOSED_ENGINEERED: dict[str, str] = {
    "nordic-forest-mosaic-throw-baby": "launch0:nordic_forest_baby",
}


def _merge_approved_proposal() -> None:
    from ..products.launch0 import CATALOGUE_FLOOR_APPROVED

    if CATALOGUE_FLOOR_APPROVED:
        ENGINEERED.update(PROPOSED_ENGINEERED)


_merge_approved_proposal()


def _engineered_cir(slug: str, version: str | None = None) -> CIR | None:
    """The engineered design for `slug`. With no `version`, the builder's own released
    version: a design whose content changed carries a new version (patterns are software
    releases), and a caller defaulting to "1.0.0" here would stamp new content with the old
    release number."""
    module_path = ENGINEERED.get(slug)
    if module_path and module_path.startswith("launch0:"):
        # A Launch-0 variant keeps its own slug: it is the product, not a concept's headline.
        from ..products import launch0 as l0

        return l0.cir_for(module_path.partition(":")[2], version)
    if module_path:
        import importlib

        name, _, function = module_path.partition(":")
        module = importlib.import_module(name)
        make = getattr(module, function or "build")
        cir = make() if version is None else make(version=version)
        # Keep the concept's slug so the radar, the portfolio and the product row agree on the
        # name; the size-specific slugs are for the variants, not the headline product.
        return CIR.from_dict({**cir.to_dict(), "slug": slug})

    from ..products.builder import for_slug

    return for_slug(slug) if version is None else for_slug(slug, version)


@handlers.register("creative.candidates_file")
def handle_creative_candidates_file(ctx: JobContext) -> dict:
    """File concept boards and taste-gate registrations for the engineered creative candidates.

    W4-PIPE2 engineered the moment-first candidates and proved, on a scratch database, that
    `creative.intake.regate_held` holds each at the taste gate once its board and its intake
    row exist. Production's database had neither, so the gate never saw them. This job puts
    them there, idempotently:

    * a board is filed only when none is on file for the candidate's current version and
      fingerprint (a re-engineered CIR gets a fresh board; an unchanged one does not);
    * a candidate is registered only when no intake row exists for it -- the gate's own
      verdict, never a judgement (only a vision judge bound to the board's bytes sets one).

    GREEN: deterministic renders and audit rows. No model call, no spend, no publication.
    """
    from ..creative import intake
    from ..products import moment_candidates as mc
    from ..products.pipeline_board import CREATIVE_ENGINEERED

    slugs = sorted(CREATIVE_ENGINEERED)
    boards_filed, registered, unchanged = [], [], []
    errors: dict[str, str] = {}
    for slug in slugs:
        try:
            cir = mc.creative_cir(slug)
            rec = mc.board_record(ctx.db, slug)
            if rec is None or rec.get("version") != cir.version \
                    or rec.get("fingerprint") != cir.fingerprint:
                mc.file_board(ctx.db, cir)
                boards_filed.append(slug)
            if not intake.intake_rows(ctx.db, slug=slug, limit=1):
                out = mc.register_for_taste_gate(ctx.db, slug)
                if out.get("registered"):
                    registered.append({"slug": slug, "decision": out.get("decision"),
                                       "waiting_on": out.get("waiting_on")})
                else:
                    errors[slug] = str(out.get("why") or "not registered")[:240]
            if slug not in boards_filed and not any(r["slug"] == slug for r in registered):
                unchanged.append(slug)
        except Exception as exc:  # noqa: BLE001 - one candidate never stops the others
            errors[slug] = f"{type(exc).__name__}: {exc}"[:240]
    return {"candidates": len(slugs), "boards_filed": boards_filed, "registered": registered,
            "unchanged": unchanged, "errors": errors}


def _draft_garment(ctx: JobContext, slug: str, i: dict) -> dict:
    """ENG-GARMENT: route, build every size, gate the run, then compile and certify each size.

    The garment is drafted only into a family `construction_families.garment_route` admits
    (a pinned end-to-end proof for its category and body table). Every size is built from one
    step list (`products.garment_families`), certified through the release chain and the
    garment gates (`products.garment_release.certify`); a run with any refused size or gate
    finding is held with its reasons. A granted run sends each size's CIR through the same
    `cir.compile` -> `gate.certify` chain every product takes."""
    from types import SimpleNamespace

    from ..creative import construction_families as CF
    from ..products import garment_release as GR

    title, category = str(i.get("title") or ""), str(i.get("category") or "")
    route = CF.route(category=category, title=title, form="fitted_garment",
                     construction=str(i.get("construction") or ""), slug=slug,
                     premise=str(i.get("premise") or ""))

    def held(reason: str, gate: str = "construction") -> dict:
        ctx.audit("cir.draft_refused", artifact=slug,
                  detail={"reason": reason[:400], "gate": gate, "category": category,
                          "hold": reason.split(" ", 1)[0]})
        return {"artifact": slug, "drafted": False, "gate": gate, "construction": "garment",
                "hold": reason.split(" ", 1)[0], "reasons": [reason[:300]]}

    if not route["admitted"]:
        return held(route["reason"])
    concept = SimpleNamespace(
        key=slug, title=title, form="fitted_garment",
        construction=str(i.get("construction") or ""), premise=str(i.get("premise") or ""),
        notes=str(i.get("notes") or ""), recipient=str(i.get("recipient") or "self"),
        feeling=str(i.get("feeling") or "serene"))
    try:
        spec = GR.spec_for(concept)
    except GR.GarmentRefused as exc:
        return held(str(exc))
    if spec.audience != route.get("audience"):
        return held(f"{CF.HOLD_PREFIX}{route['family']} -- the concept's recipient sizes it "
                    f"for {spec.audience} but its title and category say {route.get('audience')}")
    release = GR.certify(GR.build(spec))
    if not release.granted:
        return held(f"{CF.HOLD_PREFIX}{route['family']} -- the garment run is refused: "
                    + "; ".join(release.reasons()[:3]), gate="garment")
    queued = []
    for size, cir in release.cirs.items():
        ctx.enqueue("validator", "cir.compile", {"cir": cir.to_dict()},
                    idempotency_key=f"compile:{cir.slug}:{cir.version}:{cir.fingerprint}")
        queued.append(f"{cir.slug}@{cir.version}")
    ctx.audit("cir.drafted", artifact=slug,
              detail={"source": "products.garment_release", "family": route["family"],
                      "sizes": list(release.sizes), "queued": queued})
    return {"artifact": slug, "drafted": True, "construction": route["family"],
            "garment": {"family": route["family"], "audience": spec.audience,
                        "sizes": list(release.sizes), "queued": queued,
                        "construction": spec.construction},
            "rows": sum(len(c.rows) for c in next(iter(release.cirs.values())).components)}


@handlers.register("cir.draft")
def handle_cir_draft(ctx: JobContext) -> dict:
    slug = ctx.job.inputs["slug"]

    # PT-11: a retired concept slug whose design is a Launch-0 variant is routed to the
    # Launch-0 slugs, recorded, and never drafted under its own name.
    from ..products import launch0 as _l0

    retired = _l0.LEGACY_DUPLICATES.get(slug)
    if retired is not None:
        routed = []
        for target in retired["superseded_by"]:
            cir = _engineered_cir(target)
            if cir is None:      # pragma: no cover - every target is in ENGINEERED
                continue
            ctx.enqueue("validator", "cir.compile", {"cir": cir.to_dict()},
                        idempotency_key=f"compile:{cir.slug}:{cir.version}:{cir.fingerprint}")
            routed.append(f"{cir.slug}@{cir.version}")
        ctx.audit("cir.draft_routed", artifact=slug,
                  detail={"retired_alias": slug, "candidate": retired["candidate"],
                          "routed_to": routed, "why": retired["why"]})
        return {"artifact": slug, "drafted": False, "retired_alias": True,
                "routed_to": routed}

    # A bundle is not a pattern. Drafting one produced a certified "Nordic Forest Collection
    # Bundle" whose PDF was a twelve-row striped panel -- a product that would have been sold
    # as three patterns and delivered as one invented swatch. Bundles route to collection
    # assembly instead, which builds the listing out of its members' real releases.
    seed = _seed_for(slug, ctx.db)
    if seed is None:
        # G1 (review bb680ec): a draft queued for an intake concept that has since been
        # withdrawn (or never approved) is refused at execution time. Without this it fell
        # through to the raw-geometry fallback below with no pre-engineering gate. Checked
        # from the database and the job's declared provenance; an established design is a
        # rebuild and is never blocked by an intake row that happens to share its slug.
        from ..creative import preengineering as _pe
        from ..radar import intake as _intake

        declared = str(ctx.job.inputs.get("provenance") or "")
        if (not _pe.established(ctx.db, slug)
                and (declared.startswith("radar.intake:") or _intake.has_rows(ctx.db, slug))):
            state = _intake.latest_state(ctx.db, slug)
            ctx.audit("cir.draft_refused", artifact=slug, detail={
                "gate": "radar.intake", "state": state or "no row",
                "reason": (f"intake concept {slug!r} is not currently approved "
                           f"({state or 'no row'}); a queued draft does not outlive its "
                           f"approval")})
            return {"artifact": slug, "drafted": False, "gate": "radar.intake",
                    "reasons": [f"intake concept not currently approved ({state or 'no row'})"]}
    if seed is not None and seed.is_bundle:
        ctx.audit("cir.skipped_bundle", artifact=slug,
                  detail={"reason": "a bundle has no pattern of its own; it is its members"})
        from .release import chain_key

        ctx.enqueue("listing", "collection.assemble",
                    {"slug": slug, "family": seed.family},
                    idempotency_key=chain_key("collection", slug, "collection"))
        return {"artifact": slug, "drafted": False, "is_bundle": True}

    # The engineering entry point holds the same gate `radar.score` applies, so a new concept
    # cannot reach engineering by being enqueued here directly. A rebuild of an established
    # design (chain.rebuild re-drafting a certified product) is not a new concept and passes.
    # A payload that is neither a radar slot nor a creative concept is raw test geometry with
    # no idea attached; it is compiled so the compiler's refusals stay reachable.
    from ..creative import preengineering

    if (not preengineering.established(ctx.db, slug)
            and (seed is not None or isinstance(ctx.job.inputs.get("concept"), dict))):
        gate_inputs = dict(ctx.job.inputs)
        if seed is not None and seed.origin:
            # F2: an intake concept is gated on its database row and the vision judge's
            # record here too, so a directly enqueued cir.draft cannot carry its own taste.
            from ..radar import intake as _intake

            gate_inputs = _intake.gate_inputs(ctx.db, slug, gate_inputs)
        gate = preengineering.gate_concept(ctx.db, gate_inputs)
        if not gate["engineer"]:
            effects = preengineering.record(ctx, gate, source="cir.draft")
            return {"artifact": slug, "drafted": False, "gate": gate["decision"],
                    "reasons": gate["reasons"][:5], "unmeasured": gate["unmeasured"],
                    "consequence": gate["consequence"], "effects": effects}

    creative = (isinstance(ctx.job.inputs.get("concept"), dict)
                and not preengineering.established(ctx.db, slug))
    if creative:
        # #3: a new creative concept is engineered only when the staged funnel carried it to
        # prototype. Asked of the recorded run behind this slug's winner intake, never of the
        # job's own inputs, so a caller cannot enqueue its way past the tournament.
        from ..creative import intake as winner_intake

        funnel = winner_intake.verify_funnel(ctx.db, slug)
        if not funnel["carried"]:
            ctx.audit("cir.draft_refused", artifact=slug,
                      detail={"reason": funnel["why"][:400], "gate": "funnel.may_engineer"})
            return {"artifact": slug, "drafted": False, "gate": "funnel",
                    "reasons": [funnel["why"][:300]]}
        return _draft_creative(ctx, slug)

    engineered = _engineered_cir(slug)
    if engineered is not None:
        ctx.audit("cir.drafted", artifact=f"{engineered.slug}@{engineered.version}",
                  detail={"source": "engineered design", "rows": sum(
                      len(c.rows) for c in engineered.components)})
        compile_inputs = {"cir": engineered.to_dict()}
        if isinstance(ctx.job.inputs.get("correction"), dict):
            compile_inputs["correction"] = ctx.job.inputs["correction"]  # CB2-O09
        ctx.enqueue("validator", "cir.compile", compile_inputs,
                    idempotency_key=(f"compile:{engineered.slug}:{engineered.version}"
                                     f":{engineered.fingerprint}"))
        # W4-AUTO: `drafted` is the declared work key (WORK_KEYS); the success paths omitted
        # it, so every CIR this department drafted was judged a no-op (Product & Design 0%).
        return {"artifact": f"{engineered.slug}@{engineered.version}", "drafted": True,
                "rows": len(engineered.components[0].rows), "engineered": True}

    i = ctx.job.inputs
    concept = Concept(
        slug=i["slug"], title=i["title"], category=i["category"],
        stitch_repeat=[(s, n) for s, n in i["stitch_repeat"]],
        width_stitches=i["width_stitches"], rows=i["rows"], colors=i["colors"],
        opportunity_score=i.get("score", i.get("opportunity_score", 0.0)),
        season=i.get("season"), risk_class=i.get("risk_class", "A"),
    )
    if i.get("form") == "fitted_garment":
        # ENG-GARMENT: a graded garment is one release of every size, never a flat panel.
        return _draft_garment(ctx, slug, i)
    lineage = _fallback_lineage(seed, dict(i), concept)
    from ..creative import fallback_constructions as FC
    from ..creative.prototype import PrototypeRefused, source_provenance
    from ..creative import homedecor as _HD

    # OPUS2-P0 (P0-DRAFT-CONSTRUCTIONS): the shape the concept's stitches are worked into is
    # decided before any CIR exists. A shaped form no fallback rule makes is refused by name
    # rather than drafted as a flat panel under that name.
    route = FC.plan(category=concept.category, title=concept.title,
                    is_bundle=bool(seed.is_bundle) if seed is not None else False,
                    slug=concept.slug, rationale=seed.rationale if seed is not None else "")
    from ..creative.construction_families import draft_hold

    if route["family"] == FC.REFUSED:
        # ENG-FAMILIES: the refusal names the family it holds, the label intake uses, so the
        # production inventory shows a construction hold, never "drafted, not compiled".
        hold = draft_hold(concept.category, concept.title)
        ctx.audit("cir.draft_refused", artifact=slug,
                  detail={"reason": route["why"][:400], "gate": "construction",
                          "category": concept.category, "needs": route["needs"][:200],
                          "hold": hold})
        return {"artifact": slug, "drafted": False, "gate": "construction",
                "construction": FC.REFUSED, "hold": hold, "reasons": [route["why"][:300]]}
    try:
        if route["family"] == FC.VESSEL:
            provenance = None
            if lineage["known"]:
                concept.source_provenance = lineage["source"]
                concept.source_brief = lineage["brief"]
                primitives = (FC.VESSEL_PRIMITIVES
                              + tuple(p for p in lineage["primitives"]
                                      if p != "runtime.pipeline.concept_to_cir"))
                provenance = source_provenance(
                    concept.slug, {**concept.__dict__, "provenance": concept.source_provenance},
                    concept.source_brief, primitives)
            cir = FC.vessel(concept, provenance=provenance)
        elif route["family"] in _HD.VARIANTS:
            # ENG-HOMEDECOR: vessel variants (round base, bowl, lid, cut-out handles).
            provenance = None
            if lineage["known"]:
                concept.source_provenance = lineage["source"]
                concept.source_brief = lineage["brief"]
                primitives = (FC.VESSEL_PRIMITIVES + _HD.PRIMITIVES[route["family"]]
                              + tuple(p for p in lineage["primitives"]
                                      if p != "runtime.pipeline.concept_to_cir"))
                provenance = source_provenance(
                    concept.slug, {**concept.__dict__, "provenance": concept.source_provenance},
                    concept.source_brief, primitives)
            cir = _HD.build(route["family"], concept, provenance=provenance)
        elif route["family"] == FC.COSY:
            provenance = None
            if lineage["known"]:
                concept.source_provenance = lineage["source"]
                concept.source_brief = lineage["brief"]
                primitives = (FC.COSY_PRIMITIVES
                              + tuple(p for p in lineage["primitives"]
                                      if p != "runtime.pipeline.concept_to_cir"))
                provenance = source_provenance(
                    concept.slug, {**concept.__dict__, "provenance": concept.source_provenance},
                    concept.source_brief, primitives)
            cir = FC.cosy(concept, provenance=provenance)
        elif route["family"] == FC.TOTE:
            provenance = None
            if lineage["known"]:
                concept.source_provenance = lineage["source"]
                concept.source_brief = lineage["brief"]
                primitives = (FC.TOTE_PRIMITIVES
                              + tuple(p for p in lineage["primitives"]
                                      if p != "runtime.pipeline.concept_to_cir"))
                provenance = source_provenance(
                    concept.slug, {**concept.__dict__, "provenance": concept.source_provenance},
                    concept.source_brief, primitives)
            cir = FC.tote(concept, provenance=provenance)
        elif route["family"] == FC.STOCKING:
            provenance = None
            if lineage["known"]:
                concept.source_provenance = lineage["source"]
                concept.source_brief = lineage["brief"]
                primitives = (FC.STOCKING_PRIMITIVES
                              + tuple(p for p in lineage["primitives"]
                                      if p != "runtime.pipeline.concept_to_cir"))
                provenance = source_provenance(
                    concept.slug, {**concept.__dict__, "provenance": concept.source_provenance},
                    concept.source_brief, primitives)
            cir = FC.stocking(concept, provenance=provenance)
        elif route["family"] == FC.TAPESTRY:
            if len(set((concept.colors or {}).values())) < 2:
                hold = draft_hold(concept.category, concept.title, FC.TAPESTRY)
                ctx.audit("cir.draft_refused", artifact=slug,
                          detail={"reason": "tapestry needs two distinct colours",
                                  "gate": "construction", "category": concept.category,
                                  "needs": "a second, distinct colour in the palette",
                                  "hold": hold})
                return {"artifact": slug, "drafted": False, "gate": "construction",
                        "construction": FC.REFUSED, "hold": hold,
                        "reasons": ["tapestry needs two distinct colours"]}
            provenance = None
            if lineage["known"]:
                concept.source_provenance = lineage["source"]
                concept.source_brief = lineage["brief"]
                primitives = (FC.TAPESTRY_PRIMITIVES
                              + tuple(p for p in lineage["primitives"]
                                      if p != "runtime.pipeline.concept_to_cir"))
                provenance = source_provenance(
                    concept.slug, {**concept.__dict__, "provenance": concept.source_provenance},
                    concept.source_brief, primitives)
            cir = FC.tapestry_basket(concept, provenance=provenance)
        elif route["family"] == FC.COLOURWORK_TAPESTRY:
            # ENG-COLOURWORK: an original chart generated from the motif library; the motif
            # it draws is a declared primitive, so name truth can back the title's motif word.
            from ..creative import colourwork as CW

            if len(set((concept.colors or {}).values())) < 2:
                hold = draft_hold(concept.category, concept.title, FC.COLOURWORK_TAPESTRY)
                ctx.audit("cir.draft_refused", artifact=slug,
                          detail={"reason": "tapestry needs two distinct colours",
                                  "gate": "construction", "category": concept.category,
                                  "needs": "a second, distinct colour in the palette",
                                  "hold": hold})
                return {"artifact": slug, "drafted": False, "gate": "construction",
                        "construction": FC.REFUSED, "hold": hold,
                        "reasons": ["tapestry needs two distinct colours"]}
            build = CW.basket_wall if concept.category == "basket" else CW.flat_piece
            base = CW.BASKET_PRIMITIVES if concept.category == "basket" else CW.FLAT_PRIMITIVES
            motif = CW.motif_primitive(CW.design(concept.slug, concept.title)["motif"])
            provenance = None
            if lineage["known"]:
                concept.source_provenance = lineage["source"]
                concept.source_brief = lineage["brief"]
                primitives = (base + (motif,)
                              + tuple(p for p in lineage["primitives"]
                                      if p != "runtime.pipeline.concept_to_cir"))
                provenance = source_provenance(
                    concept.slug, {**concept.__dict__, "provenance": concept.source_provenance},
                    concept.source_brief, primitives)
            cir = build(concept, provenance=provenance)
        elif route["family"] == FC.AMIGURUMI:
            provenance = None
            if lineage["known"]:
                concept.source_provenance = lineage["source"]
                concept.source_brief = lineage["brief"]
                primitives = (FC.AMIGURUMI_PRIMITIVES
                              + tuple(p for p in lineage["primitives"]
                                      if p != "runtime.pipeline.concept_to_cir"))
                provenance = source_provenance(
                    concept.slug, {**concept.__dict__, "provenance": concept.source_provenance},
                    concept.source_brief, primitives)
            cir = FC.amigurumi(concept, provenance=provenance)
        elif route["family"] in (FC.ENVELOPE, FC.APPLIQUE, FC.LOVEY):
            # ENG-PLUSH slices 2-3: cushion covers (creative.cushions) and loveys
            # (creative.baby), drafted from modelled pieces only.
            from ..creative import baby as _baby
            from ..creative import cushions as _cushions

            builder = {FC.ENVELOPE: "creative.cushions.envelope_cover",
                       FC.APPLIQUE: "creative.cushions.envelope_cover",
                       FC.LOVEY: "creative.baby.lovey"}[route["family"]]
            provenance = None
            if lineage["known"]:
                concept.source_provenance = lineage["source"]
                concept.source_brief = lineage["brief"]
                primitives = ((builder, "cir.assembly._surface_join") + tuple(
                    p for p in lineage["primitives"] if p != "runtime.pipeline.concept_to_cir"))
                provenance = source_provenance(
                    concept.slug, {**concept.__dict__, "provenance": concept.source_provenance},
                    concept.source_brief, primitives)
            if route["family"] == FC.LOVEY:
                cir = _baby.lovey(concept, provenance=provenance)
            else:
                cir = _cushions.envelope_cover(concept, provenance=provenance,
                                               applique=route.get("applique"))
        elif route["family"] == FC.POUCH:
            provenance = None
            if lineage["known"]:
                concept.source_provenance = lineage["source"]
                concept.source_brief = lineage["brief"]
                primitives = (FC.POUCH_PRIMITIVES
                              + tuple(p for p in lineage["primitives"]
                                      if p != "runtime.pipeline.concept_to_cir"))
                provenance = source_provenance(
                    concept.slug, {**concept.__dict__, "provenance": concept.source_provenance},
                    concept.source_brief, primitives)
            cir = FC.pouch(concept, provenance=provenance)
        elif route["family"] == FC.TRIANGLE:
            provenance = None
            if lineage["known"]:
                concept.source_provenance = lineage["source"]
                concept.source_brief = lineage["brief"]
                primitives = (FC.TRIANGLE_PRIMITIVES
                              + tuple(p for p in lineage["primitives"]
                                      if p != "runtime.pipeline.concept_to_cir"))
                provenance = source_provenance(
                    concept.slug, {**concept.__dict__, "provenance": concept.source_provenance},
                    concept.source_brief, primitives)
            cir = FC.triangle(concept, provenance=provenance)
        elif lineage["known"]:
            concept.source_provenance = lineage["source"]
            concept.source_brief = lineage["brief"]
            extra = FC.PANEL_PAIR_PRIMITIVES if route["family"] == FC.PANEL_PAIR else ()
            cir = concept_to_cir(concept, primitives=tuple(lineage["primitives"]) + extra)
        else:
            cir = concept_to_cir(concept)
        if route["family"] == FC.PANEL_PAIR:
            cir = FC.panel_pair(cir)
    except PrototypeRefused as exc:
        # Malformed benchmark identities are unknown lineage, never stringified into a record.
        ctx.audit("cir.draft_refused", artifact=slug,
                  detail={"reason": str(exc)[:400], "gate": "provenance"})
        return {"artifact": slug, "drafted": False, "reasons": [str(exc)[:300]]}
    except (ValueError, KeyError) as exc:
        # Review OPUS2C N3.3: a construction that cannot be built from these inputs (an empty
        # repeat, no colours, a stitch outside the taxonomy) is a named refusal, not a crash.
        why = f"{type(exc).__name__}: {str(exc)[:300]}"
        hold = draft_hold(concept.category, concept.title, route["family"])
        ctx.audit("cir.draft_refused", artifact=slug,
                  detail={"reason": why[:400], "gate": "construction",
                          "category": concept.category,
                          "needs": f"inputs the {route['family']} construction can work",
                          "hold": hold})
        return {"artifact": slug, "drafted": False, "gate": "construction",
                "construction": route["family"], "hold": hold, "reasons": [why[:300]]}
    # OPUS2-P0: the publish gate's name-truth rule, read at draft time for the constructions
    # this fallback now makes. Recorded, never a refusal here: publication refuses it
    # (NAME_OUTRUNS_PATTERN), and the count shows what the fallback cannot yet chart.
    name_problems: list[str] = []
    if route["family"] != FC.FLAT_PANEL:
        try:
            from ..publish.eligibility import name_truth

            name_problems = [str(p)[:200] for p in name_truth(cir, None)]
        except Exception as exc:  # noqa: BLE001 - a reading, never a reason to fail a draft
            name_problems = [f"UNKNOWN: {type(exc).__name__}"]
    advice = _learning_advice(ctx, cir, family=route["family"])
    ctx.audit("cir.drafted", artifact=f"{cir.slug}@{cir.version}",
              detail={"source": "concept_to_cir fallback", "construction": route["family"],
                      "name_truth": name_problems, "learning_advice": advice,
                      "provenance": ("recorded" if cir.provenance is not None
                                     else "UNKNOWN: " + lineage["why"]),
                      "benchmarks_consulted": (list(cir.provenance.benchmarks_consulted)
                                               if cir.provenance is not None else None)})
    ctx.enqueue("validator", "cir.compile", {"cir": cir.to_dict()},
                idempotency_key=f"compile:{cir.slug}:{cir.version}")
    return {"artifact": f"{cir.slug}@{cir.version}", "drafted": True,
            "construction": route["family"], "rows": len(cir.components[0].rows),
            "learning_advice": advice}


def _learning_advice(ctx: JobContext, cir: CIR, *, family: str = "") -> dict:
    """ENG-LEARN: the measured engineering regions this draft falls in (`learning.
    pattern_lessons.advise`). A reading recorded with the draft, never a refusal: the
    compiler and the certificate decide; a lesson never stands in for a gate."""
    try:
        from ..learning import pattern_lessons

        a = pattern_lessons.advise(ctx.db, cir=cir.to_dict(), family=str(family or ""))
        return {"avoid": [h["key"] for h in a["avoid"]][:6],
                "prefer": [h["key"] for h in a["prefer"]][:6],
                "measured_regions": a["measured_regions"]}
    except Exception as exc:  # noqa: BLE001 - advice is a reading; it never fails a draft
        return {"status": "UNKNOWN", "why": f"{type(exc).__name__}"[:80]}


def _fallback_lineage(seed: ConceptSeed | None, inputs: dict, concept: Concept) -> dict:
    """The real lineage of a `concept_to_cir` fallback draft (G-R2), or why it is unknown.

    Recorded only from what actually produced the design: the radar pool seed the slot came
    from (code, not a job input), the deterministic `concept_geometry` table -- verified by
    recomputing it against the queued geometry -- the yarn's gauge derivation, and whatever
    brief/benchmark lineage the queued inputs carry. Nothing is asserted that did not happen:
    a payload with no radar seed, or geometry the table did not produce, is unknown lineage
    and gets no provenance, so the originality gate refuses it (PROVENANCE_MISSING) rather
    than passing a generic label.
    """
    if seed is None:
        return {"known": False,
                "why": "no radar seed: raw caller-supplied geometry is not an approved source"}
    expected = concept_geometry(seed)
    queued = {"stitch_repeat": [list(x) for x in inputs.get("stitch_repeat") or []],
              "width_stitches": inputs.get("width_stitches"), "rows": inputs.get("rows"),
              "colors": dict(inputs.get("colors") or {})}
    if queued != expected or inputs.get("category") != seed.category:
        return {"known": False,
                "why": (f"queued geometry for {seed.slug} is not what concept_geometry "
                        f"produces for category {seed.category!r}; its source is unknown")}
    if inputs.get("brief") is not None and not isinstance(inputs.get("brief"), dict):
        return {"known": False, "why": "queued brief is not an object; lineage unknown"}
    from ..creative import preengineering

    _, brief, _ = preengineering.concept_from(inputs)
    declared = str(inputs.get("provenance") or "").strip()
    # A declared benchmark lineage is carried (source_provenance appends it to the consulted
    # set); otherwise the design's source is the radar pool seed itself.
    source = (declared if declared.startswith("benchmark:")
              else seed.origin or f"radar.pool:{seed.slug}")
    return {"known": True, "source": source, "brief": brief or None, "why": "",
            "primitives": ("runtime.pipeline.concept_to_cir",
                           f"runtime.pipeline.concept_geometry:{seed.category}",
                           f"creative.prototype.gauge_for:{concept.yarn_weight}")}


def _draft_creative(ctx: JobContext, slug: str) -> dict:
    """Author the CIR a tournament winner describes, deterministically (C-61).

    The geometry is computed, never asked for: a garment is a graded design from sourced body
    tables (`creative.garment_design`), everything else is authored from its form's finished
    size and the yarn's published gauge (`creative.prototype.author`). A form or
    construction the engine has no rule for is refused by name.
    """
    from ..creative.concept import Concept as CreativeConcept
    from ..creative.prototype import PrototypeRefused, author

    raw = dict(ctx.job.inputs["concept"])
    concept = CreativeConcept(**{k: v for k, v in raw.items()
                                 if k in CreativeConcept.__dataclass_fields__})
    try:
        cir = author(concept, version=str(ctx.job.inputs.get("version") or "1.0.0"),
                     brief=ctx.job.inputs.get("brief"))
    except PrototypeRefused as exc:
        ctx.audit("cir.draft_refused", artifact=slug,
                  detail={"reason": str(exc)[:400], "gate": "engine"})
        return {"artifact": slug, "drafted": False, "reasons": [str(exc)[:300]]}
    cir = CIR.from_dict({**cir.to_dict(), "slug": slug, "title": concept.title})
    advice = _learning_advice(ctx, cir, family=concept.form)
    ctx.audit("cir.drafted", artifact=f"{cir.slug}@{cir.version}",
              detail={"source": "tournament winner", "form": concept.form,
                      "learning_advice": advice,
                      "construction": cir.construction, "pod": concept.pod,
                      "mjs_event_id": ctx.job.inputs.get("mjs_event_id"),
                      "rows": sum(len(c.rows) for c in cir.components)})
    ctx.enqueue("validator", "cir.compile", {"cir": cir.to_dict()},
                idempotency_key=f"compile:{cir.slug}:{cir.version}:{cir.fingerprint}")
    return {"artifact": f"{cir.slug}@{cir.version}", "drafted": True, "creative": True,
            "form": concept.form, "rows": sum(len(c.rows) for c in cir.components),
            "learning_advice": advice}


@handlers.register("cir.compile")
def handle_cir_compile(ctx: JobContext) -> dict:
    cir = CIR.from_dict(ctx.job.inputs["cir"])
    result = compile_cir(cir)
    ctx.audit("cir.compiled", artifact=f"{cir.slug}@{cir.version}",
              detail={"ok": result.ok, "errors": len(result.errors)})
    if not result.ok:
        # A failing compile is a real outcome, not an exception. W4-AGENTS batch 3: it is
        # handed to the Crochet Engineer once (`cir.revise`, deterministic repair rules); a
        # revision that does not compile, or a second failure, ends the concept here.
        revise_job = None
        from .engineering_ops import MAX_REVISIONS

        prior = max(0, int(ctx.job.inputs.get("revision") or 0))   # I-3: never negative
        if prior < MAX_REVISIONS:
            revise_job = ctx.enqueue(
                "crochet_engineer", "cir.revise",
                {"cir": ctx.job.inputs["cir"],
                 "revision": prior},
                idempotency_key=f"revise:{cir.slug}:{cir.version}:{cir.fingerprint}")
        return {"artifact": f"{cir.slug}@{cir.version}", "compiled": False,
                "errors": [str(f) for f in result.errors],
                "revise_job": getattr(revise_job, "id", None)}
    certify_inputs = {"cir": ctx.job.inputs["cir"]}
    if isinstance(ctx.job.inputs.get("correction"), dict):
        certify_inputs["correction"] = ctx.job.inputs["correction"]  # CB2-O09
    ctx.enqueue("quality_director", "gate.certify", certify_inputs,
                idempotency_key=(f"certify:{cir.slug}:{cir.version}:{cir.fingerprint}"
                                 f":d{DOC_VERSION}"))
    return {"artifact": f"{cir.slug}@{cir.version}", "compiled": True,
            "counts": result.counts(cir.components[0].name)}


def _certify_listing(ctx: JobContext, cir: CIR):
    """The listing copy the certificate examines, and a record of where it came from (PT-01).

    This was a hard-coded placeholder tagged "mosaic blanket" and priced CA$11.99 for every
    product, so the certificate never saw the copy a buyer would read. Now, in order:

    1. the REAL stored listing for this slug@version, when one exists and names the product
       the CIR makes (`first_customer.product_type_findings`). A stored copy that names
       another product is recorded as refused -- the publish gate refuses it too -- and is
       not attested; listing.seo re-drafts it after a grant.
    2. otherwise a draft from the product's own record: its Launch-0 identity or its radar
       seed, with that record's kind and price. No default product type.
    3. with no record at all, no listing is examined (None), and that is recorded.
    """
    from sqlalchemy import select

    from ..core.models import Listing
    from ..gates import first_customer
    from ..products import launch0 as l0

    with ctx.db.session() as s:
        row = s.scalar(select(Listing).where(Listing.product_slug == cir.slug,
                                             Listing.version == cir.version))
        stored = None if row is None else {
            "title": row.title or "", "description": row.description or "",
            "tags": list(row.tags or []), "price_cad": float(row.price_cad or 0.0)}
    refused: list[str] = []
    if stored is not None:
        refused = first_customer.product_type_findings(cir, title=stored["title"],
                                                       tags=stored["tags"])
        if not refused:
            return (ListingDraft(**stored),
                    {"source": "stored Listing row", "title": stored["title"][:140]})
        ctx.audit("gate.listing_copy_refused", artifact=f"{cir.slug}@{cir.version}",
                  detail={"findings": refused[:5], "title": stored["title"][:140],
                          "tags": stored["tags"][:13],
                          "why": "the stored copy names a product the CIR does not make; it "
                                 "is not attested and publication refuses it"})

    identity = l0.listing_identity(cir.slug)
    seed = _seed_for(cir.slug, ctx.db)
    if identity is not None:
        launch = l0.launch_price(cir.slug) or {}
        kind, price = identity.kind, launch.get("price_cad") or l0.candidate_for_cir(
            cir.slug).price.proposed_cad
        source = "products.launch0 listing identity"
    elif seed is not None:
        kind, price = seed.category.replace("_", " "), seed.price_cad
        source = seed.origin or f"radar.pool:{seed.slug}"
    else:
        return None, {"source": None, "stored_copy_refused": refused,
                      "why": "no stored listing and no product record: no copy examined"}
    draft = ListingDraft(
        title=f"{cir.title} | Crochet Pattern PDF with Charts",
        description=(f"{cir.title}. Written pattern with stitch counts for every row, "
                     f"as two PDFs -- one written throughout in US terms and one in UK "
                     f"terms. Created with AI assistance; every row's stitch count is "
                     f"checked before release."),
        # The product's own kind, as a tag (Etsy caps a tag at 20 characters).
        tags=["crochet pattern", kind[:20].strip(), "pdf pattern"],
        price_cad=float(price),
    )
    return draft, {"source": source, "title": draft.title, "stored_copy_refused": refused}


@handlers.register("gate.certify")
def handle_certify(ctx: JobContext) -> dict:
    cir = CIR.from_dict(ctx.job.inputs["cir"])

    # Publication is halted while a P0/P1 defect is open against this product.
    tracker = IncidentTracker(ctx.db)
    # PHYSFIX G4, integrator decision (SECREVIEW 8da830d R28): every halt -- a physical size
    # halt included -- is product-wide. No design digest decides whether this release may
    # certify past a halt; a size halt is lifted only by the owner, on qualifying evidence
    # (`runtime.release.lift_size_halt`). Certifying lifts nothing.
    if tracker.publication_halted(cir.slug):
        ctx.audit("gate.halted", artifact=f"{cir.slug}@{cir.version}",
                  detail={"reason": "open P0/P1 incident"})
        return {"artifact": f"{cir.slug}@{cir.version}", "granted": False,
                "halted_by_incident": True}

    # W4-LISTREADY (review F5): a halted certification's retry and the normal chain can each
    # queue a certify for the same slug@version. Whichever runs second finds the identical
    # release already certified after it was queued and stops, so it is certified once. The
    # halt check above is unchanged and always runs first.
    from .release_recovery import duplicate_certification, newer_certified

    # W4-LISTREADY (delta review N1): an older version is never newly certified after a newer
    # one -- that is the out-of-order state every "current release" reader has to survive.
    # A version already certified may still be re-certified (a document refresh).
    newer = newer_certified(ctx.db, cir.slug, cir.version)
    if newer and not _stored_release_hash(ctx, cir):
        ctx.audit("gate.certify_older_than_newest", artifact=f"{cir.slug}@{cir.version}",
                  detail={"newer_certified": newer})
        return {"artifact": f"{cir.slug}@{cir.version}", "granted": False,
                "refused": "older_than_newest", "reasons": [
                    f"{cir.slug}@{cir.version} is older than the certified {newer}"]}

    duplicate = duplicate_certification(ctx.db, ctx.job, cir)
    if duplicate:
        ctx.audit("gate.certify_duplicate", artifact=f"{cir.slug}@{cir.version}",
                  detail={"why": duplicate})
        return {"artifact": f"{cir.slug}@{cir.version}", "granted": True,
                "duplicate": True, "why": duplicate}

    hero = Asset(
        asset_id=f"{cir.slug}-hero",
        asset_class=AssetClass.DIGITAL_TWIN_RENDER,
        provenance=Provenance(source="twin", created_by="asset_truth", tool="digital_twin@1"),
        depicts_stitches=sorted({op.stitch for c in cir.components for r in c.rows
                                 for op in _flatten_stitches(r.ops)}),
        depicts_colors=sorted(cir.colors),
        is_hero=True,
        claims=Claims(materials=[m.name for m in cir.materials]),
    )
    listing, listing_reading = _certify_listing(ctx, cir)

    from ..quality.physical import calibration_from_db

    from ..gates.platform_policy import policy_stamp

    cert = certify(cir, assets=[hero], listing=listing, db=ctx.db,
                   calibration=calibration_from_db(ctx.db, cir),
                   # #39: the certificate records which reading of the platform's rules it
                   # was issued under, so it can be re-examined when they change.
                   platform_policy=policy_stamp(ctx.db),
                   # F-078 / F-081: physical evidence is read from the stored tests and bound
                   # to the content by the certificate itself -- never a constant False (which
                   # left Class C blocked forever) and never a bare True.
                   physical_evidence=physical_evidence_rows(ctx.db, cir.slug),
                   # F-090: the class this product has held before, so a downgrade has to
                   # bring evidence rather than a deadline.
                   prior_risk_class=_prior_risk_class(ctx.db, cir.slug),
                   # F-074: primitives a passed, content-bound sample has actually measured.
                   calibrated_primitives=calibrated_primitives(ctx.db))
    # PT-03: a certified slug@version is immutable. Different content -- a different design,
    # or the same design now stating different customer-visible figures -- under a version
    # that is already certified is refused here, with an incident, and nothing downstream is
    # touched: two buyers holding "1.1.0" must hold the same pattern. A re-certification of
    # identical content (a new document build, a policy re-read) is still allowed.
    conflict = _version_conflict(ctx, cir, cert) if cert.granted else None
    if conflict is not None:
        _refuse_version_conflict(ctx, cir, conflict)
        return {"artifact": f"{cir.slug}@{cir.version}", "granted": False,
                "refused": "version_immutable", "reasons": [conflict["why"]]}

    ctx.audit("gate.certified" if cert.granted else "gate.blocked",
              artifact=f"{cir.slug}@{cir.version}",
              policy_version=cert.policy_version,
              # `content_hash` is recorded granted or not: it is what a tester's sample,
              # recorded later without a hash of its own, is bound to (F-078).
              detail={"granted": cert.granted, "reasons": cert.blocking_reasons[:5],
                      # PT-01: which listing copy the certificate examined, and why.
                      "listing_examined": listing_reading,
                      "content_hash": cert.content_hash,
                      "physical_test_required": cert.physical_test_required,
                      "physical_evidence": cert.physical_evidence})

    # F-078: a material change invalidated physical evidence this product's class requires.
    # The re-test is requested here, as an owner spend approval for an independent tester
    # (never the owner's labour, F-071), instead of the block only saying "needs a re-test".
    _request_physical_retest(ctx, cir, cert)

    if cert.granted:
        previous_hash = _stored_release_hash(ctx, cir)
        _persist_release(ctx, cir, cert.to_dict(), cert.release_hash)
        # W6 support-defect (review dd05e389 F-1): a release that just became the one on sale
        # inherits any active support-defect hold now, not at the next hourly triage.
        # store.publish reconciles again immediately before its gates, and fails closed.
        from ..support import defects as _support_defects

        try:
            _support_defects.reconcile_holds(ctx.db)
        except Exception as exc:  # noqa: BLE001
            ctx.audit("support.defect_reconcile_failed", artifact=f"{cir.slug}@{cir.version}",
                      detail={"error": type(exc).__name__, "at": "gate.certify"})
        # #42 (C-64): a correcting release finds the buyers who hold what it corrects, from
        # the version map written at sale time, and prepares their notice. Sending it is the
        # owner's (an owner action is raised); nothing is sent from here.
        from ..commerce import buyer_trust

        # A release is a correction only when the job that certified it says so
        # (`inputs.correction`, carried from the engineering job that made the change);
        # a routine newer version prepares nothing (CB2-O09).
        correction = buyer_trust.on_certified(
            ctx.db, product_slug=cir.slug, version=cir.version,
            release_hash=cert.release_hash or "", previous_release_hash=previous_hash,
            correction=ctx.job.inputs.get("correction"))
        if correction["affected_count"]:
            ctx.audit("buyer_trust.correction_prepared", artifact=f"{cir.slug}@{cir.version}",
                      detail={k: correction[k] for k in ("affected_count", "affected_orders",
                                                         "owner_action",
                                                         "version_unknown_orders", "states")})
        elif correction.get("correction"):
            ctx.audit("buyer_trust.correction_unprepared",
                      artifact=f"{cir.slug}@{cir.version}",
                      detail={"why": correction.get("why", ""),
                              "eligible": correction.get("eligible"),
                              "version_unknown_orders":
                                  correction.get("version_unknown_orders", [])})
        # #70: a revision that changes geometry or claims invalidates the listing-set
        # certificate issued against the old ones, recomputed here rather than remembered,
        # and the affected frames lose their approval until the chain re-certifies them.
        _recheck_listing_certificates(ctx, cir)
        # Lane routing for the newly certified release (cadence and grant integrated).
        ctx.enqueue("quality_director", "gate.lanes", {},
                    idempotency_key=f"lanes:{cir.slug}:{cert.release_hash}")
        # A certified member is the event its collections wait on (C-73).
        from .release import enqueue_member_collections

        enqueue_member_collections(ctx, cir.slug, cert.release_hash or "")

        # #163 / #169: the teardown lab's QA of our own product. A product class that can
        # name no evidenced advantage beyond the purchased benchmarks is withheld here, with
        # the reason audited, before anything downstream is built for it.
        from ..teardown import lab as teardown_lab

        seed = product_seed(cir.slug, ctx.db)
        teardown = teardown_lab.product_qa(
            ctx.db, cir.slug,
            product_class=(getattr(cir, "category", "") or (seed.category if seed else "")))
        _mark_withheld(ctx, cir, (("teardown QA (#163): "
                                   + str(teardown["unique_value"].get("reason", ""))[:300])
                                  if teardown.get("blocks_release") else None))
        if teardown.get("blocks_release"):
            ctx.audit("gate.release_withheld", artifact=f"{cir.slug}@{cir.version}",
                      detail={"reason": "teardown QA (#163): "
                                        + str(teardown["unique_value"].get("reason", ""))[:300],
                              "product_class": teardown.get("product_class")})
            return {"artifact": f"{cir.slug}@{cir.version}", "granted": cert.granted,
                    "release_hash": cert.release_hash, "withheld": True,
                    "reasons": [teardown["unique_value"].get("reason", "")][:1]}
        # #228: an owner veto on this product withholds it at certification, before anything
        # downstream is built for it. The owner lifts it by ruling again. Recorded on the
        # release's one withholding record (C-67 / M10) so the rebuild and draft paths refuse
        # on it too, under its own kind, beside -- never instead of -- the teardown QA's.
        from ..intel.mission_runtime import active_veto

        veto = active_veto(ctx.db, cir.slug)
        _mark_withheld(ctx, cir, (f"owner veto (#228): {veto['why']}" if veto["vetoed"]
                                  else None), kind="owner_veto")
        if veto["vetoed"]:
            ctx.audit("gate.release_withheld", artifact=f"{cir.slug}@{cir.version}",
                      detail={"reason": f"owner veto (#228): {veto['why']}",
                              "ruling": veto.get("ruling_id")})
            return {"artifact": f"{cir.slug}@{cir.version}", "granted": cert.granted,
                    "release_hash": cert.release_hash, "withheld": True,
                    "reasons": [f"owner veto (#228): {veto['why']}"]}
        from .release import chain_key

        ctx.enqueue("listing", "listing.draft",
                    {"slug": cir.slug, "version": cir.version,
                     "release": cert.release_hash},
                    idempotency_key=chain_key("listing", cir.slug, cir.version,
                                              cert.release_hash or ""))
    else:
        _withdraw_listing(ctx, cir)

    return {"artifact": f"{cir.slug}@{cir.version}", "granted": cert.granted,
            "release_hash": cert.release_hash,
            "reasons": cert.blocking_reasons[:5]}


CERTIFY_ACTIONS: tuple[str, ...] = ("gate.certified", "gate.blocked")


def _request_physical_retest(ctx: JobContext, cir: CIR, cert) -> dict | None:
    """Queue one owner action when required physical evidence was invalidated (F-078).

    Only an *invalidated* binding raises it: that is the case where a tester has already
    worked this product and a material change made their evidence stale, so the request is
    for a specific, known re-test. A product that never had evidence is reported by launch
    readiness and the tester plan instead of being pushed into the owner queue ahead of a
    tester roster existing. Keyed on slug@version and the new content hash, so one change is
    one request however many times certification re-runs.
    """
    from sqlalchemy import select

    from ..core.models import OwnerAction
    from ..gates import risk_matrix

    matrix = cert.risk_matrix or {}
    status = matrix.get("requirement") or {}
    if not status.get("retest_required"):
        return None
    twin = cert.twin_summary or {}
    try:
        from ..seasonal.leadtime import estimate_for

        hours = estimate_for(cir, compile_cir(cir)).hours
    except Exception:  # noqa: BLE001 - an estimate we cannot make widens nothing; swatch scope
        hours = None
    spec = risk_matrix.owner_action_spec(
        slug=cir.slug, version=cir.version, content_hash=cert.content_hash,
        required=status["required"], effective_class=matrix.get("effective", "C"),
        make_hours=hours, yarn_metres=sum((twin.get("yarn_metres") or {}).values()) or None,
        retest=True)
    fields = {k: spec[k] for k in ("action", "reason", "max_cost_cad", "minutes",
                                   "consequence_of_delay", "blocks")}
    with ctx.db.session() as s:
        existing = s.scalar(select(OwnerAction).where(
            OwnerAction.requirement_key == spec["requirement_key"]))
        if existing is None:
            s.add(OwnerAction(requirement_key=spec["requirement_key"], **fields))
            state = "queued"
        else:
            state = "already_decided" if existing.done else "restated"
            if not existing.done:
                for name, value in fields.items():
                    setattr(existing, name, value)
    ctx.audit("physical.retest_requested", artifact=f"{cir.slug}@{cir.version}",
              detail={"owner_action": state, "requirement_key": spec["requirement_key"],
                      "required": status["required"], "cost_basis": spec["cost_basis"],
                      "why": status.get("why")})
    return {"state": state, **spec}


def _naive_utc(dt):
    """SQLite hands datetimes back naive; everything here is UTC, so compare naive."""
    if dt is None:
        return None
    return dt.replace(tzinfo=None) if dt.tzinfo is not None else dt


def _content_certified_at(s, slug: str, version: str, when) -> str | None:
    """The content hash the chain last examined for slug@version at or before `when`.

    A sample recorded through `physical.record` carries no hash of its own; the tester was
    handed whatever the chain had most recently examined for that release. That is read off
    the append-only audit log, so the binding cannot be edited after the fact, and a sample
    completed before the chain ever examined the release binds to nothing.
    """
    from sqlalchemy import select

    from ..core.models import AuditLog

    when = _naive_utc(when)
    latest = None
    for row in s.scalars(select(AuditLog).where(
            AuditLog.artifact == f"{slug}@{version}",
            AuditLog.action.in_(CERTIFY_ACTIONS)).order_by(AuditLog.id)):
        at = _naive_utc(row.at)
        if when is not None and at is not None and at > when:
            break
        latest = (row.detail or {}).get("content_hash") or latest
    return latest


def physical_evidence_rows(db, slug: str) -> list[dict]:
    """Every stored physical test that could be evidence for `slug`, reduced for binding.

    Rows for this slug, and rows for any other slug that declare a compatible variant --
    which is why the whole table is read rather than filtered by slug: a declaration lives on
    the tested release, not on the variant it vouches for. The table is small (one row per
    sample somebody actually crocheted).
    """
    from sqlalchemy import select

    from ..core.models import PhysicalTest

    out: list[dict] = []
    with db.session() as s:
        for t in s.scalars(select(PhysicalTest).order_by(PhysicalTest.id)):
            measured = t.measured or {}
            variants = measured.get("compatible_variants") or []
            if t.product_slug != slug and not any(
                    isinstance(v, dict) and v.get("slug") == slug for v in variants):
                continue
            content = (measured.get("content_hash") or measured.get("release_hash")
                       or (_content_certified_at(s, t.product_slug, t.version,
                                                 t.completed_at)
                           if t.completed_at is not None else None))
            # F-072: the evidence class the sample was recorded as (partial or full make).
            from ..gates.risk_matrix import physical_class_of

            cls, legacy = physical_class_of(measured)
            # SECREVIEW F3: whether the row proved the finished size. Stamped by
            # `physical.record` from W-PHYSFIX on; an older row proved it only if its size
            # was compared and agreed, and it was not a swatch.
            proof = measured.get("size_proof")
            if proof is None:
                proof = (measured.get("size_agrees") is True
                         and measured.get("scope") != "swatch")
            out.append({"id": t.id, "slug": t.product_slug, "version": t.version,
                        "passed": t.passed, "completed_at": t.completed_at,
                        "content_hash": content, "compatible_variants": variants,
                        "evidence_class": cls, "legacy_unstamped": legacy,
                        "size_proof": bool(proof)})
    return out


def _prior_risk_class(db, slug: str) -> str | None:
    """The highest risk class this product has been stored under, or None if never stored."""
    from sqlalchemy import select

    rank = {"A": 0, "B": 1, "C": 2}
    seen: list[str] = []
    with db.session() as s:
        product = s.scalar(select(Product).where(Product.slug == slug))
        if product is None:
            return None
        if product.risk_class in rank:
            seen.append(product.risk_class)
        for pv in s.scalars(select(PatternVersion).where(
                PatternVersion.product_id == product.id)):
            rc = (pv.cir_json or {}).get("risk_class")
            if rc in rank:
                seen.append(rc)
    return max(seen, key=rank.__getitem__) if seen else None


def calibrated_primitives(db) -> frozenset[str]:
    """Stitches a passed physical sample has measured: every primitive in a tested release.

    Only a passed, completed test whose release is stored counts, and only the stitches that
    release actually uses -- a sample of a plain basket calibrates nothing about bobbles.
    """
    from sqlalchemy import select

    from ..core.models import PhysicalTest

    out: set[str] = set()
    with db.session() as s:
        for t in s.scalars(select(PhysicalTest).where(
                PhysicalTest.passed == True)):  # noqa: E712
            if t.completed_at is None:
                continue
            product = s.scalar(select(Product).where(Product.slug == t.product_slug))
            if product is None:
                continue
            pv = s.scalar(select(PatternVersion).where(
                PatternVersion.product_id == product.id, PatternVersion.version == t.version))
            if pv is None or not pv.cir_json:
                continue
            try:
                stored = CIR.from_dict(pv.cir_json)
            except Exception:  # noqa: BLE001 - a record that no longer parses calibrates nothing
                continue
            for _, row in stored.iter_rows():
                out.update(op.stitch for op in _flatten_stitches(row.ops))
    return frozenset(out)


def _mark_withheld(ctx: JobContext, cir: CIR, reason: str | None,
                   kind: str = "teardown_qa") -> None:
    """Record one withholding reason on the stored release itself (C-69, #163; C-67, M10).

    The release is persisted before the teardown QA runs (the QA reads it), so the withhold
    has to live on the row every later stage reads -- `chain.rebuild`, `listing.draft` --
    rather than only in an audit row they never consult. The row carries one record keyed by
    reason kind (`publish.withholding`): clearing this kind never clears another, and the
    `withheld` summary the build stages read is derived from every build-blocking kind.
    """
    from ..publish import withholding

    withholding.record(ctx.db, cir.slug, cir.version, kind=kind, reason=reason)


def _withheld_reason(db, slug: str, version: str) -> str | None:
    """Every build-blocking reason on the release's withholding record, re-read live."""
    from ..publish import withholding

    return withholding.current(db, slug, version, stage="build")["summary"]


def _recheck_listing_certificates(ctx: JobContext, cir: CIR) -> list[dict]:
    """Run `listing_set.still_valid` over this release's certificates against the new design."""
    from ..gates.policy import POLICY_VERSION
    from ..publish import release_gates as gates_mod

    frames = gates_mod._frames(ctx.db, cir.slug, cir.version)
    listing = gates_mod._listing(ctx.db, cir.slug, cir.version)
    twin = gates_mod._twin(ctx.db, cir)
    results = gates_mod.recheck(ctx.db, slug=cir.slug, version=cir.version,
                                geometry=gates_mod.geometry_of(twin, cir),
                                claims=gates_mod.claims_of(listing, frames),
                                policy_version=POLICY_VERSION)
    for r in results:
        ctx.audit("listing_set.valid" if r["valid"] else "listing_set.invalidated",
                  artifact=f"{cir.slug}@{cir.version}",
                  detail={k: r[k] for k in ("record_id", "valid", "invalidated_by",
                                            "affected_assets", "why")})
    return results


def _withdraw_listing(ctx: JobContext, cir: CIR) -> None:
    """A product that no longer certifies must not keep a listing marked ready to publish.

    Refusing the certificate and leaving the storefront untouched means the store still holds
    a draft for something the release chain has just rejected -- and the only thing standing
    between that draft and a customer is shadow mode, which is a phase, not a guarantee.
    """
    from sqlalchemy import select

    from ..core.models import Listing

    with ctx.db.session() as s:
        listings = list(s.scalars(
            select(Listing).where(Listing.product_slug == cir.slug,
                                  Listing.state != "withdrawn")))
        for listing in listings:
            listing.state = "withdrawn"
    if listings:
        ctx.audit("listing.withdrawn", artifact=f"{cir.slug}@{cir.version}",
                  detail={"listings": len(listings),
                          "reason": "certification refused for this product"})


def _flatten_stitches(ops) -> list:
    out = []
    for o in ops:
        if isinstance(o, Repeat):
            out.extend(_flatten_stitches(o.ops))
        else:
            out.append(o)
    return out


def _version_conflict(ctx: JobContext, cir: CIR, cert) -> dict | None:
    """Why `cert` may not be stored under cir.slug@cir.version, or None when it may (PT-03).

    Content is the design (the stored CIR, normalised through CIR.from_dict so two spellings
    of one design compare equal) and the figures the certificate tells the buyer
    (`gates.certificate.claims_fingerprint` over its twin block). Either differing from the
    certified record of the same version is a new release that has to carry a new version.
    """
    from sqlalchemy import select

    from ..gates.certificate import claims_fingerprint

    with ctx.db.session() as s:
        row = s.scalar(select(PatternVersion).join(Product).where(
            Product.slug == cir.slug, PatternVersion.version == cir.version,
            PatternVersion.certified == True))  # noqa: E712
        if row is None:
            return None
        stored_json, stored_cert = row.cir_json, dict(row.certificate or {})
    try:
        stored_fp = CIR.from_dict(stored_json).fingerprint
    except Exception:  # noqa: BLE001 - an unreadable stored design is not "the same"
        stored_fp = "unreadable"
    new_fp = cir.fingerprint
    old_claims = claims_fingerprint(stored_cert.get("twin"))
    new_claims = claims_fingerprint(cert.to_dict().get("twin"))
    if stored_fp != new_fp:
        return {"kind": "content", "stored": stored_fp, "offered": new_fp,
                "why": (f"{cir.slug}@{cir.version} is already certified with design "
                        f"{stored_fp}; this job offers design {new_fp} under the same version. "
                        f"A certified version is immutable: bump the version")}
    if old_claims and new_claims and old_claims != new_claims:
        return {"kind": "claims", "stored": old_claims, "offered": new_claims,
                "why": (f"{cir.slug}@{cir.version} is already certified stating figures "
                        f"{old_claims}; the same design now states {new_claims} (size or "
                        f"yardage moved). A certified version is immutable: bump the version")}
    return None


def _refuse_version_conflict(ctx: JobContext, cir: CIR, conflict: dict) -> None:
    from ..ops.incident_lifecycle import open_or_restate

    ctx.audit("gate.version_conflict", artifact=f"{cir.slug}@{cir.version}",
              detail={k: conflict[k] for k in ("kind", "stored", "offered", "why")})
    with ctx.db.session() as s:
        open_or_restate(
            s, signature=f"release.version_immutable:{cir.slug}@{cir.version}",
            severity="P2", product_slug=cir.slug, halts_publication=False,
            summary=conflict["why"],
            detail={"kind": conflict["kind"], "stored": conflict["stored"],
                    "offered": conflict["offered"], "version": cir.version,
                    "job_id": ctx.job.id})


def _stored_release_hash(ctx: JobContext, cir: CIR) -> str:
    """The release hash already stored for this product and version, or ""."""
    from sqlalchemy import select

    with ctx.db.session() as s:
        row = s.scalar(select(PatternVersion).join(Product).where(
            Product.slug == cir.slug, PatternVersion.version == cir.version))
        return (row.release_hash or "") if row is not None else ""


def _persist_release(ctx: JobContext, cir: CIR, certificate: dict, release_hash: str) -> None:
    from sqlalchemy import select

    with ctx.db.session() as s:
        product = s.scalar(select(Product).where(Product.slug == cir.slug))
        if product is None:
            product = Product(slug=cir.slug, title=cir.title, status="certified",
                              risk_class=cir.risk_class)
            s.add(product)
            s.flush()
        else:
            product.status = "certified"
        existing = s.scalar(
            select(PatternVersion).where(PatternVersion.product_id == product.id,
                                         PatternVersion.version == cir.version)
        )
        if existing is None:
            existing = PatternVersion(product_id=product.id, version=cir.version,
                                      cir_json=cir.to_dict(), release_hash=release_hash,
                                      certified=True, certificate=certificate)
            s.add(existing)
        elif existing.release_hash != release_hash:
            # Re-certification of a version that already exists. Insert-if-absent was how the
            # agent-permission fix failed to reach production (B-027), and it would fail the
            # same way here: the stored certificate would keep describing a document the
            # writer no longer produces, while the PDF regenerates from the new one. The
            # record is replaced and the change is audited rather than left to be discovered.
            previous = existing.release_hash
            # Review OPUS2B2 F2.1: a failed re-verification survives the replacement (fail
            # closed) and the checks are queued now, so the new content clears it promptly.
            from ..publish import withholding as _withholding

            certificate, carried = _withholding.carry_reverification(
                existing.certificate, certificate)
            existing.cir_json = cir.to_dict()
            existing.release_hash = release_hash
            # PHYSFIX: a permanent withholding (the version a sample measured at the wrong
            # size) survives the replaced certificate -- re-certifying never un-withholds it.
            existing.certificate = _withholding.carry_permanent(existing.certificate,
                                                                certificate)
            existing.certified = True
            if carried:
                ctx.enqueue("quality_director", "gate.quality", {},
                            idempotency_key=f"reverify-after-recert:{cir.slug}@{cir.version}:"
                                            f"{release_hash[:16]}")
            ctx.audit("gate.recertified", artifact=f"{cir.slug}@{cir.version}",
                      detail={"previous_release_hash": previous,
                              "release_hash": release_hash,
                              "doc_version": DOC_VERSION})
        s.flush()

        # The certificate is the first derived artefact of a release, and it is recorded
        # against the *stored* design rather than the CIR in hand: `current_from_db`
        # fingerprints `cir_json`, and a second spelling of the same design would make every
        # certificate read stale the moment it was issued (#171). No `chain:release` input
        # on purpose -- the certificate is a fact about the design and the gates, not about
        # the post-certification chain, and a chain bump must not revoke it.
        from ..ops import artefacts as provenance

        inputs = {f"cir:{cir.slug}": provenance.fingerprint(existing.cir_json)}
        if release_hash:
            inputs[f"release:{cir.slug}"] = release_hash[:16]
        # C-69 (#171): the twin, the geometry proof and the reverse compiler's reading are
        # derived artefacts of the design in their own right, recorded here against the same
        # stored design so a CIR change invalidates them -- they were ARTEFACT_CLASSES nothing
        # ever wrote. Each carries the fingerprint of what that stage concluded, and the
        # certificate names them as its parents, so the rebuild graph follows design ->
        # twin/geometry/reverse -> certificate -> everything downstream.
        stages = list(certificate.get("stages_run") or [])
        base = provenance.release_key(cir.slug, cir.version)
        stage_rows = {
            "twin": ("twin" in stages, {"twin": certificate.get("twin")}),
            "geometry_proof": ("geometry" in stages, {
                "findings": [f for f in certificate.get("findings") or []
                             if str(f.get("code", "")).upper().startswith("GEOM")]}),
            "reverse_result": ("reverse" in stages, {
                "findings": [f for f in certificate.get("findings") or []
                             if str(f.get("code", "")).upper().startswith(("REV", "REVERSE"))]}),
        }
        parents: list[str] = []
        for cls, (ran, reading) in stage_rows.items():
            if not ran:
                continue
            key = f"{base}#{cls}"
            provenance.record_lineage(
                s, artefact_class=cls, artefact_key=key, product_slug=cir.slug,
                inputs=inputs, chain_version=str(DOC_VERSION),
                lineage=provenance.Lineage(
                    created_by=ctx.job.agent, job_id=ctx.job.id,
                    validation_status="passed",
                    publication_authority=ctx.phase.value if ctx.phase else "shadow",
                    evidence={"stage": cls, "reading_fingerprint":
                              provenance.fingerprint(reading)}))
            parents.append(f"{cls}:{key}")
        provenance.record_lineage(
            s, artefact_class="certificate",
            artefact_key=provenance.release_key(cir.slug, cir.version),
            product_slug=cir.slug, inputs=inputs, chain_version=str(DOC_VERSION),
            lineage=provenance.Lineage(
                created_by=ctx.job.agent, job_id=ctx.job.id,
                sha256=release_hash if len(release_hash or "") == 64 else "",
                validation_status="certified", parents=tuple(parents),
                publication_authority=ctx.phase.value if ctx.phase else "shadow"))


@handlers.register("listing.draft")
def handle_listing_draft(ctx: JobContext) -> dict:
    """Hand a certified pattern to the second half of the chain.

    Asset rendering comes before listing copy, not after, because the listing quotes the
    assets: page count, finished size, yardage range. Writing the copy first and rendering
    afterwards is how a description ends up promising a PDF that does not exist.
    """
    slug = ctx.job.inputs["slug"]
    version = ctx.job.inputs["version"]
    withheld = _withheld_reason(ctx.db, slug, version)
    if withheld:
        # #163 / C-69: a release the teardown QA withheld gets no listing, whoever asked.
        ctx.audit("listing.refused_withheld", artifact=f"{slug}@{version}",
                  detail={"why": withheld})
        return {"artifact": slug, "drafted": False, "withheld": withheld}
    ctx.audit("listing.drafted", artifact=slug)
    from .release import chain_key

    release = ctx.job.inputs.get("release", "")
    token = ctx.job.inputs.get("rebuild", "")
    ctx.enqueue("publishing", "assets.build",
                {"slug": slug, "version": version, "release": release, "rebuild": token},
                idempotency_key=chain_key("assets", slug, version, release, token))
    # #41: an owed purchase disclosure missing from the draft's copy is a finding on it.
    # On a first release there is no stored copy yet and this reads UNMEASURED (C-47); the
    # check that measures runs in `listing.seo` right after the Listing row is written, and
    # again at publish. This one still catches a re-draft whose stored copy has drifted.
    from ..commerce.buyer_trust import listing_disclosure_finding

    disclosure = listing_disclosure_finding(ctx.db, slug=slug, version=version)
    if disclosure.get("finding"):
        ctx.audit("listing.disclosure_finding", artifact=f"{slug}@{version}", detail=disclosure)
    return {"artifact": slug, "drafted": True, "disclosures": disclosure}


def _certified_pdf_hashes(db, slug: str, version: str, release: str) -> dict | None:
    """The per-terminology PDF hashes `assets.build` recorded for (slug, version, release).

    Read from the `assets.built` audit row and the job that wrote it: the row carries the
    stored files (`pdfs`), the job's inputs carry the release and its outputs carry
    `pdf_sha256_by_terminology`. Newest first; a release given must match the job's release.
    None when nothing on record certifies a file for this release.
    """
    from sqlalchemy import desc, select

    from ..core.models import AuditLog, Job

    with db.session() as s:
        rows = list(s.scalars(select(AuditLog).where(
            AuditLog.action == "assets.built", AuditLog.artifact == f"{slug}@{version}")
            .order_by(desc(AuditLog.id))))
        for row in rows:
            job = s.get(Job, row.job_id) if row.job_id else None
            inputs = (job.inputs or {}) if job is not None else {}
            outputs = (job.outputs or {}) if job is not None else {}
            if release and (inputs.get("release") or outputs.get("release") or "") != release:
                continue
            detail = row.detail or {}
            hashes = (detail.get("pdf_sha256_by_terminology")
                      or outputs.get("pdf_sha256_by_terminology")
                      or {t: (v or {}).get("sha256")
                          for t, v in (detail.get("pdfs") or {}).items()})
            hashes = {t: h for t, h in (hashes or {}).items() if h}
            if hashes:
                return hashes
    return None


def check_pdf_hashes(db, *, slug: str, version: str, release: str,
                     rendered: dict[str, bytes]) -> dict:
    """Refuse an upload whose re-rendered PDF is not the file `assets.build` certified.

    `store.publish` renders the customer's documents again at upload time. The release date
    is pinned so the bytes should be identical; if they are not, something changed between
    certification and upload (the writer, the renderer, the design) and the buyer would
    download a file nobody certified. That is `PDF_HASH_DRIFT`, a PermanentError, because
    retrying renders the same drifted bytes.
    """
    import hashlib

    from ..core.resilience import PermanentError

    certified = _certified_pdf_hashes(db, slug, version, release)
    if not certified:
        raise PermanentError(
            f"PDF_HASH_DRIFT: no assets.built hash is on record for {slug}@{version} "
            f"release {release or '(none)'}, so the file about to be uploaded cannot be shown "
            f"to be the certified one")
    actual = {t: hashlib.sha256(b).hexdigest() for t, b in rendered.items()}
    drift = {t: {"certified": certified.get(t), "rendered": h}
             for t, h in actual.items() if certified.get(t) != h}
    if drift:
        raise PermanentError(
            f"PDF_HASH_DRIFT: the re-rendered PDF for {slug}@{version} differs from the "
            f"certified file for {sorted(drift)}: {drift}")
    return {"verified": sorted(actual), "certified": certified}


@handlers.register("store.publish")
def handle_store_publish(ctx: JobContext) -> dict:
    """In SHADOW this must refuse. Publishing is a production capability with its own gate.

    Past shadow, this is where the Etsy client is asked -- and the client has its own three
    refusals in front of it, so "the phase allows it" is the first of four conditions rather
    than the only one. Nothing in this environment satisfies the others: there are no
    credentials and no owner grant.
    """
    # The eight-part creative parity gate (#75). *Computed* before the phase check and
    # *enforced* after it, and the split is deliberate.
    #
    # Computed first, because a gate that only runs once the phase allows publishing is a
    # gate nobody has ever seen run, and the first listing it judged would be a live one.
    # This reads evidence already on file -- no render, no model call, no network -- so
    # running it on every refused attempt costs nothing and produces the record of it
    # working that Shadow Mode otherwise makes impossible to gather.
    #
    # Enforced after, because Shadow Mode is the outermost boundary and must stay the
    # reason. A system that refuses to publish for a creative reason before establishing
    # that it is allowed to publish at all has inverted its own gates, and the refusal
    # `/api/verify` counts as evidence of Shadow Mode working would start saying something
    # else.
    # W4-WRAPTEST: an uncertified EXPERIMENT never reaches publication, in any phase.
    # W6 support-defect (review dd05e389 F-1): the holds are reconciled FIRST, before any
    # gate reads them (`_release_gates` below), so a release that became current since the
    # last triage (a new certification, a rollback) can never be published in that window.
    # A reconcile that cannot run refuses the publish (fail closed).
    from ..support import defects as _support_defects

    try:
        _support_defects.reconcile_holds(ctx.db)
    except Exception as exc:  # noqa: BLE001
        ctx.audit("store.publish_refused", artifact=ctx.job.inputs.get("slug"),
                  detail={"reason": f"support-defect holds could not be reconciled: "
                                    f"{type(exc).__name__}"})
        raise RuntimeError("support-defect holds could not be reconciled before publish; "
                           "refusing to publish") from exc
    from ..visual.experiment import refuse_if_experiment

    refuse_if_experiment(ctx.db, ctx.job.inputs.get("slug"), ctx.job.inputs.get("version"),
                         action="store.publish")
    parity_verdict = _listing_parity(ctx)
    # P0-CHAIN-DEADENDS (3): the row names the release it judged, so a verdict for one
    # version is never read as another's (W-INVENTORY found it bound to the slug alone).
    # Review OPUS2B2 F1.2: the version defaults as the verdict's does.
    ctx.audit("listing.parity", artifact=ctx.job.inputs.get("slug"),
              detail={**parity_verdict, "version": ctx.job.inputs.get("version", "1.0.0"),
                      "release": ctx.job.inputs.get("release", "")})

    # The release-chain publish gates (#58, #60, #65, #66, #70, #80, #172, #173, #297), on
    # the same split as parity: computed on every attempt from evidence on file, so Shadow
    # Mode produces the record of them working, and enforced below after the capability
    # gates and before anything is uploaded.
    release_gates = _release_gates(ctx)
    ctx.audit("store.release_gates", artifact=ctx.job.inputs.get("slug"),
              detail=release_gates)

    # rc1-AUTH A1: the phase is re-resolved here (owner's recorded phase AND environment),
    # not taken from the worker's boot reading.
    phase_now = protected_phase(ctx)
    if phase_now is Phase.SHADOW:
        ctx.audit("store.publish_refused", artifact=ctx.job.inputs.get("slug"),
                  detail={"reason": "shadow mode: no live publication",
                          "creative_parity": parity_verdict["verdict"],
                          "parity_would_block": parity_verdict["blocks_release"],
                          "release_gates_would_block": release_gates["blocks_release"],
                          "release_gate_reasons": release_gates["reasons"][:5]})
        raise ShadowModeRefusal(
            "store.publish is a production capability; the system is in SHADOW mode and has "
            "no live Etsy connection. Draft retained for review."
        )


    import os

    from sqlalchemy import select

    from ..core.models import Listing
    from ..integrations.etsy import Credentials, EtsyClient, build_payload
    from ..integrations.http import UrllibTransport

    slug = ctx.job.inputs["slug"]
    version = ctx.job.inputs.get("version", "1.0.0")

    transport = UrllibTransport()
    client = EtsyClient(
        transport,
        # The transport is handed to the credentials so that an OAuth token which has
        # expired -- Etsy's access tokens live one hour -- is refreshed rather than sent.
        # Without it this job works for an hour after a human pasted a token and then fails
        # with a 401 that looks exactly like a revoked app.
        #
        # The database is handed over for the other half of the same problem. Etsy issues a
        # **new refresh token on every refresh** and spends the old one, so a refresh that is
        # not written down survives exactly as long as this container does. With `db` the
        # provider reads the sealed credential from `oauth_credentials` and writes each
        # rotation back under compare-and-set, which is what makes an unattended publish job
        # still authenticated next week.
        credentials=Credentials.from_env(transport=transport, db=ctx.db),
        phase=phase_now.value,
        # A separate fact from having a key: publishing is RED in the authority matrix.
        # FB3-P: this environment flag is only the global kill-switch (it can deny, never
        # grant). The owner's authority itself is the durable, sealed, release-bound grant in
        # `ops.publication_authority`, resolved in `_revalidate_publish_effect` before the
        # durable intent is claimed and again immediately before the create request.
        owner_authorised=os.environ.get("BRAMBLELOOP_PUBLISH_AUTHORISED", "") == "1")

    refusal = client.refusal()
    if refusal is not None:
        ctx.audit("store.publish_refused", artifact=f"{slug}@{version}",
                  detail={"reason": refusal})
        raise ShadowModeRefusal(refusal)

    # Enforced here: after every question about whether this system may publish at all,
    # and before anything is sent. Phase, credentials and the authority matrix are
    # capability gates and stay outermost; parity is the question of whether *this listing*
    # is good enough, which is only worth asking of a system that could publish it.
    if parity_verdict["blocks_release"]:
        ctx.audit("store.publish_refused", artifact=f"{slug}@{version}",
                  detail={"reason": f"creative parity (#75): {parity_verdict['why']}"})
        raise ParityRefusal(
            f"listing export is blocked by the eight-part creative parity gate: "
            f"{parity_verdict['why']}")

    with ctx.db.session() as s:
        listing = s.scalar(select(Listing).where(Listing.product_slug == slug,
                                                 Listing.version == version))
        if listing is None:
            raise ValueError(f"no drafted listing for {slug}@{version}: publishing cannot "
                             f"precede the listing the gates checked")
        copy = dict(title=listing.title, description=listing.description,
                    price_cad=listing.price_cad, tags=list(listing.tags))
        already = listing.etsy_listing_id
        manual = listing.state == "published_manually"
        release = ctx.job.inputs.get("release") or listing.release_hash or ""

    if already:
        # Publishing twice must not create a second listing. Updating an existing one is a
        # different operation with a different risk profile, so it is refused here rather
        # than guessed at. W-ADOPT: a listing the owner made by hand and adopted
        # (`listing.adopt_manual`) stops here the same way.
        ctx.audit("store.publish_refused", artifact=f"{slug}@{version}",
                  detail={"reason": f"already on Etsy as listing {already}"
                                    + (" (published manually and adopted)" if manual else ""),
                          "published_manually": manual})
        return {"slug": slug, "version": version, "published": False,
                "etsy_listing_id": already,
                "reason": "already published manually" if manual else "already published"}

    # C-49: both names live in their own modules; importing them here is what lets a
    # non-shadow publish run at all rather than die with NameError on its first line.
    from ..cir.twin import build_twin
    from ..quality.physical import calibration_from_db
    from .release import _load_cir

    cir = _load_cir(ctx, slug, version)
    # One builder for publish, activation and the census (runtime.etsy_ops), so the draft
    # read back and the listing census compare against exactly what was sent. Taxonomy
    # flows through `build_payload` unchanged.
    from . import etsy_ops

    payload = etsy_ops.certified_payload(ctx.db, slug, version)

    # The bytes have to exist. Without durable storage they may not, and the client refuses
    # an empty upload rather than creating a listing that delivers nothing.
    from ..core.artifacts import ArtifactStore
    from ..core.resilience import PermanentError, TransientError
    from ..publish.pdf import TERMINOLOGIES, build_pattern_pdf, pattern_filename

    result = compile_cir(cir)
    # C-50: the calibration `assets.build` rendered with, or the yardage lines differ and the
    # certified file and the uploaded file are two different documents.
    twin = build_twin(cir, result, calibration=calibration_from_db(ctx.db, cir))
    # Pinned to the release date, not to the day of the upload. This render is the file the
    # customer actually downloads, and `assets.build` recorded a hash for it earlier; left to
    # default, the release date printed on the cover would be today's and the two would be
    # different files for no reason connected to the pattern.
    from .release import _released_on

    released_on = _released_on(ctx, slug, version)
    from ..learn.service import pdf_help_links
    lesson_links = pdf_help_links(ctx.db, cir.to_dict())
    docs = {t: build_pattern_pdf(cir, twin=twin, terminology=t, released_on=released_on,
                                 lesson_links=lesson_links)
            for t in TERMINOLOGIES}
    doc = docs["US"]
    # The file uploaded must be the file certified: compared per terminology against the
    # `assets.built` hashes for this release, before anything is stored or sent.
    try:
        hash_check = check_pdf_hashes(
            ctx.db, slug=slug, version=version, release=release,
            rendered={t: d.pdf_bytes for t, d in docs.items()})
    except PermanentError as e:
        ctx.audit("store.publish_refused", artifact=f"{slug}@{version}",
                  detail={"reason": str(e)[:500], "code": "PDF_HASH_DRIFT"})
        raise
    ctx.audit("store.pdf_hash_verified", artifact=f"{slug}@{version}", detail=hash_check)
    # #126, release half (after parity and the hash check, before anything is stored or
    # sent): the product must have cleared the blind search-grid tournament.
    # No recorded verdict reads as not cleared -- a threshold cleared by default is the
    # favouritism the requirement forbids -- and the refusal is an audited block.
    from ..creative import preengineering

    grid = preengineering.release_grid_verdict(ctx.db, slug)
    if not grid["cleared"]:
        ctx.audit("store.publish_blocked", artifact=f"{slug}@{version}",
                  detail={"reasons": [f"search-grid tournament (#126): {grid.get('why')}"],
                          "grid": grid})
        return {"slug": slug, "version": version, "published": False, "blocked": True,
                "reasons": [f"search-grid tournament (#126): {grid.get('why')}"]}

    # The release-chain gates, enforced after the file to be uploaded
    # has been shown to be the certified one and before anything is stored or sent. An
    # audited, reasoned block rather than an exception: the job completes, says it did not
    # publish and why, and the reasons are what a rebuild or re-certification has to clear.
    if release_gates["blocks_release"]:
        ctx.audit("store.publish_blocked", artifact=f"{slug}@{version}",
                  detail={"reasons": release_gates["reasons"][:10],
                          "certificate": (release_gates.get("listing_set") or {})
                          .get("certificate")})
        return {"slug": slug, "version": version, "published": False, "blocked": True,
                "reasons": release_gates["reasons"]}

    # F-524: the certified listing image bytes, in the listing-set certificate's frame
    # order. Read before anything is created on Etsy: a draft with no image can never be
    # activated, so a set whose bytes are missing or unreadable refuses here rather than
    # leaving an unactivatable listing in the shop.
    listing_images = etsy_ops.certified_images(
        ctx.db, slug, version, release=release, store_root=ctx.job.inputs.get("artifact_dir"))
    if listing_images["problems"]:
        reasons = [f"certified listing images (F-524): {p}"
                   for p in listing_images["problems"][:5]]
        ctx.audit("store.publish_blocked", artifact=f"{slug}@{version}",
                  detail={"reasons": reasons, "certificate": listing_images["record_id"]})
        return {"slug": slug, "version": version, "published": False, "blocked": True,
                "reasons": reasons}

    store = ArtifactStore(ctx.job.inputs.get("artifact_dir"))
    stored_by_terminology = {
        t: store.put(f"{slug}/{version}/{pattern_filename(t)}", d.pdf_bytes,
                     "application/pdf")
        for t, d in docs.items()}
    stored = stored_by_terminology["US"]

    return _publish_guarded(
        ctx, client, slug=slug, version=version, release=release, payload=payload,
        docs=docs, hash_check=hash_check, stored=stored,
        stored_by_terminology=stored_by_terminology, listing_images=listing_images)


def _publish_guarded(ctx: JobContext, client, **kw) -> dict:
    """`_publish_and_read_back`, with an Etsy credential failure turned into owner work.

    F-541: invalid_grant, revoked access, a spent refresh token or a scope the grant lacks
    all raise `EtsyAuthNeedsOwner`, and each becomes one idempotent owner action plus one
    incident rather than a dead job nobody reads. Still raised afterwards: it is terminal,
    and retrying sends the same refused proof.
    """
    from ..integrations.etsy_oauth import EtsyAuthNeedsOwner
    from . import etsy_ops

    try:
        return _publish_and_read_back(ctx, client, **kw)
    except EtsyAuthNeedsOwner as e:
        raised = etsy_ops.record_auth_needs_owner(ctx.db, e, where="store.publish")
        ctx.audit("store.publish_auth_needs_owner",
                  artifact=f"{kw.get('slug')}@{kw.get('version')}",
                  detail={**raised, "error": str(e)[:300]})
        raise


def _publish_content_digest(release, payload, docs, listing_images):
    import hashlib
    import json
    from . import etsy_ops
    binding = {"release": release,
               "pdfs": {t: hashlib.sha256(doc.pdf_bytes).hexdigest() for t, doc in docs.items()},
               "images": [(name, hashlib.sha256(data).hexdigest()) for name, data in listing_images["images"]],
               "image_order": listing_images.get("order"), "listing_set": listing_images.get("record_id"),
               "payload": etsy_ops.sent_fields(payload)}
    return hashlib.sha256(json.dumps(binding, sort_keys=True).encode()).hexdigest()


def _revalidate_publish_effect(ctx, *, slug, version, release, payload, docs, listing_images,
                               reserved_digest=None, stage="before_create"):
    """Current evidence bound to the exact bytes about to leave; unknown is a refusal.

    Owner publication authority is a durable, sealed, content-bound grant
    (`ops.publication_authority`), resolved anew here at both boundaries; the
    `BRAMBLELOOP_PUBLISH_AUTHORISED` environment flag is only a global kill-switch that can
    deny, never grant. `stage` names the boundary in the audit row: `pre_claim` (before the
    durable intent is claimed) or `before_create` (inside the client, immediately before the
    createDraftListing request), so each run of the full check is separately evidenced.
    """
    import hashlib
    import os
    from types import SimpleNamespace
    from copy import copy
    from sqlalchemy import select
    from ..core.models import Listing
    from ..core.resilience import PermanentError
    from ..integrations.etsy import PHASES_THAT_MAY_PUBLISH
    from ..ops import publication_authority
    from ..publish.pdf import TERMINOLOGIES
    from . import etsy_ops
    grant_id = None
    approval_input = (getattr(ctx.job, "inputs", None) or {}).get(
        "owner_publication_approval_id")
    try:
        if reserved_digest is not None and reserved_digest != _publish_content_digest(
                release, payload, docs, listing_images):
            raise ValueError("actual content changed after durable intent reservation")
        phase = protected_phase(ctx).value
        # F-299: the environment alone no longer decides the phase -- it must agree with the
        # owner's latest recorded PhaseTransition, else the more restrictive one applies.
        from ..core.phase import effective as effective_phase
        configured = effective_phase(ctx.db)
        refusal, grant_id = publication_authority.resolve(
            ctx.db, slug=slug, version=version, release=release, approval_id=approval_input)
        if refusal is not None:
            raise ValueError(f"current owner publication authority absent: {refusal}")
        if phase not in PHASES_THAT_MAY_PUBLISH or configured not in PHASES_THAT_MAY_PUBLISH:
            raise ValueError("current runtime phase forbids publication")
        # Historical replay dates cannot stand in for current execution evidence.
        inputs = dict(ctx.job.inputs)
        inputs.pop("as_of", None)
        inputs.update(slug=slug, version=version, release=release)
        current_ctx = copy(ctx)
        current_ctx.job = SimpleNamespace(**{**vars(ctx.job), "inputs": inputs})
        parity, gates = _listing_parity(current_ctx), _release_gates(current_ctx)
        if parity.get("blocks_release") is not False or gates.get("blocks_release") is not False:
            raise ValueError("current parity/release gate refuses or is UNKNOWN")
        with ctx.db.session() as session:
            listing = session.scalar(select(Listing).where(
                Listing.product_slug == slug, Listing.version == version))
            pv = session.scalar(select(PatternVersion).join(Product).where(
                Product.slug == slug, PatternVersion.version == version))
            if (not release or listing is None or pv is None or not pv.certified
                    or listing.release_hash != release or pv.release_hash != release):
                raise ValueError("current certified release binding differs or is absent")
        if etsy_ops.sent_fields(etsy_ops.certified_payload(ctx.db, slug, version)) != etsy_ops.sent_fields(payload):
            raise ValueError("actual payload differs from current certified listing")
        if set(docs) != set(TERMINOLOGIES):
            raise ValueError("actual document set differs from certified terminology set")
        check_pdf_hashes(ctx.db, slug=slug, version=version, release=release,
                         rendered={t: docs[t].pdf_bytes for t in TERMINOLOGIES})
        current = etsy_ops.certified_images(ctx.db, slug, version, release=release,
                                          store_root=inputs.get("artifact_dir"))
        def image_binding(value):
            return (value["record_id"], value["order"],
                    [(name, hashlib.sha256(data).hexdigest()) for name, data in value["images"]])
        if current.get("problems") != [] or not current.get("images"):
            raise ValueError("current image evidence refuses or is UNKNOWN")
        if image_binding(current) != image_binding(listing_images):
            raise ValueError("actual images differ from current certified image set")
        final_refusal, final_grant = publication_authority.resolve(
            ctx.db, slug=slug, version=version, release=release, approval_id=approval_input)
        if (final_refusal is not None or final_grant != grant_id
                or protected_phase(ctx).value not in PHASES_THAT_MAY_PUBLISH
                or effective_phase(ctx.db) not in PHASES_THAT_MAY_PUBLISH):
            raise ValueError("owner authority or runtime phase changed during revalidation")
    except Exception as exc:
        ctx.audit("store.execution_refused", artifact=f"{slug}@{version}",
                  detail={"release": release, "stage": stage, "reason": str(exc)[:500],
                          "owner_publication_grant": grant_id})
        raise PermanentError("PUBLISH_EXECUTION_REFUSED: " + str(exc)) from exc
    ctx.audit("store.execution_revalidated", artifact=f"{slug}@{version}",
              detail={"release": release, "current_evidence": True, "stage": stage,
                      "owner_publication_grant": grant_id,
                      "content_digest": reserved_digest})


def _reaches_network(transport, depth: int = 3) -> bool:
    """Whether `transport` is, or wraps, the production HTTP transport (UrllibTransport),
    looking through instance attributes up to `depth` levels."""
    from ..integrations.http import UrllibTransport

    seen: set[int] = set()

    def walk(obj, level: int) -> bool:
        if obj is None or id(obj) in seen:
            return False
        seen.add(id(obj))
        if isinstance(obj, UrllibTransport):
            return True
        if level >= depth:
            return False
        try:
            attrs = vars(obj)
        except TypeError:
            return False
        return any(walk(v, level + 1) for v in attrs.values()
                   if not isinstance(v, (str, bytes, int, float, bool, dict, list, tuple)))

    return walk(transport, 0)


def real_draft_credential_refusal(db, client) -> str | None:
    """Why a real Etsy draft may not be created with this credential now, or None.

    A real draft is one whose requests can reach Etsy: the client's base is Etsy
    (`etsy_probe.against_etsy`) AND it sends through the production HTTP transport
    (`integrations.http.UrllibTransport`, what `etsy_ops.build_client` always uses). An
    in-memory transport or a local fake server is not a real draft. For a real one,
    `intel.etsy_public.credential_usable` must be True; an unreadable judgement refuses."""
    from ..integrations import etsy_probe

    if getattr(client, "BASE", None) is None or not etsy_probe.against_etsy(client):
        return None
    # Review 6954619488 (LOW): a wrapped production transport is still the production
    # transport. `isinstance(transport, UrllibTransport)` alone let a wrapper (retry, logging,
    # pinning) around the real sender skip this check; the real sender is now looked for
    # inside the transport too. An in-memory transport that holds no real sender is still
    # not a real draft.
    if not _reaches_network(getattr(client, "transport", None)):
        return None
    try:
        from ..intel import etsy_public

        judged = etsy_public.credential_usable(db)
    except Exception as exc:  # noqa: BLE001 - unreadable is not usable
        return f"Etsy credential usability is UNKNOWN ({type(exc).__name__}); no real draft"
    if judged.get("usable") is not True:
        return ("Etsy credential is not usable for a real draft: "
                + (judged.get("why") or "UNKNOWN"))
    return None


#: ENG-ETSY-PUBLISH slice 2: how many times a draft that read back short is completed in place
#: and read again before it is left `incomplete_on_etsy` behind its incident.
MAX_COMPLETION_ROUNDS = 2


def _complete_draft(client, listing_id: str, *, slug: str, docs: dict, listing_images: dict,
                    payload, grant_fn, force_images: bool = False) -> dict:
    """Bring an existing draft up to the certified set, in place (ENG-ETSY-PUBLISH slice 2).

    Used for an adopted draft and for a draft whose read-back came up short. It sends only
    what Etsy does not already hold, so a second round never doubles anything:

    * each certified PDF (US and UK) whose file name is not attached is attached;
    * the images: none on Etsy uploads the certified set in rank order with its alt text.
      A set that differs in count or alt text is re-sent rank by rank with `overwrite`
      (Etsy replaces the image at that rank). More images on Etsy than certified is reported,
      never guessed at, because this client has no image delete;
    * the listing properties are written again (an idempotent PUT).

    Every write carries the publication grant (`PUBLISH_COMPLETE`: only this grant's own draft).

    Review b17-d A1: with `force_images` (an adopted draft, or a read-back whose image ranks
    are unproven) every certified rank is re-sent with `overwrite`, whatever alt text Etsy
    holds, so the read-back can hash bytes this job really uploaded. `sent_ranks` maps rank
    -> SHA-256 of each payload that was accepted.
    """
    import hashlib

    from ..core.resilience import PermanentError, TransientError
    from ..publish.pdf import TERMINOLOGIES, pattern_filename

    problems: list[str] = []
    files: dict[str, bool] = {}
    sent_ranks: dict[int, str] = {}
    try:
        held = {str(r.get("filename") or "") for r in client.get_listing_files(listing_id) or []}
    except (TransientError, PermanentError) as e:
        return {"files": {}, "images_uploaded": 0, "sent_ranks": {},
                "problems": [f"files unread: {e}"[:300]]}
    for t in TERMINOLOGIES:
        name = f"{slug}-{pattern_filename(t)}"
        if name in held:
            files[t] = True
            continue
        try:
            files[t] = bool(client.attach_file(listing_id, filename=name,
                                               data=docs[t].pdf_bytes, grant=grant_fn()))
        except (TransientError, PermanentError) as e:
            files[t] = False
            problems.append(f"the {t} pattern could not be attached to {listing_id}: {e}"[:300])
    want = list(listing_images.get("images") or [])
    want_alt = [str(getattr(e, "alt_text", "") or (e[2] if len(e) > 2 else "") or "")
                for e in want]
    uploaded = 0
    try:
        remote = sorted(client.get_listing_images(listing_id) or [],
                        key=lambda r: int(r.get("rank") or 0))
    except (TransientError, PermanentError) as e:
        remote = None
        problems.append(f"images unread: {e}"[:300])
    if remote is not None:
        have_alt = [str(r.get("alt_text") or "") for r in remote]
        if len(remote) > len(want):
            problems.append(f"draft {listing_id} holds {len(remote)} images and {len(want)} are "
                            "certified; extra images are not removed automatically")
        elif force_images or have_alt != want_alt:
            for rank, entry in enumerate(want, start=1):
                try:
                    client.upload_image(listing_id, filename=entry[0], data=entry[1],
                                        rank=rank, alt_text=want_alt[rank - 1],
                                        overwrite=rank <= len(remote), grant=grant_fn())
                    uploaded += 1
                    sent_ranks[rank] = hashlib.sha256(entry[1]).hexdigest()
                except (TransientError, PermanentError) as e:
                    problems.append(f"image {rank} was not uploaded to {listing_id}: {e}"[:300])
    for prop in getattr(payload, "properties", None) or []:
        try:
            client.set_listing_property(listing_id, prop, grant=grant_fn())
        except (TransientError, PermanentError) as e:
            problems.append(f"listing property {prop.get('property_id')} write failed: {e}"[:300])
    return {"files": files, "images_uploaded": uploaded, "sent_ranks": sent_ranks,
            "problems": problems}


def _publish_and_read_back(ctx: JobContext, client, *, slug: str, version: str,
                           release: str, payload, docs: dict, hash_check: dict, stored,
                           stored_by_terminology: dict, listing_images: dict) -> dict:
    """Create the draft with its certified images and files, then read it back (F-542).

    A 2xx on each write is Etsy accepting a request. The listing is recorded as published
    only when a separate `getListing` and `getAllListingFiles` afterwards show the certified
    fields, the certified number of images, the draft state and exactly the certified files.
    Anything else is `store.publish_incomplete` plus a halting incident on the product.
    """
    from sqlalchemy import select

    from ..core.models import Listing
    from ..core.resilience import PermanentError, TransientError
    from ..publish.pdf import TERMINOLOGIES, pattern_filename
    from . import etsy_ops

    doc = docs["US"]
    # The uploaded name comes from the same place as the stored one. It was spelled out here,
    # so the file in the buyer's downloads folder and the file in the artifact store could have
    # been named by two different rules.
    from ..publish import draft_intent
    content_digest = _publish_content_digest(release, payload, docs, listing_images)
    # FB2-R2 #1: the pre-create evidence (owner publication authority, runtime phase, the
    # `assets.built` PDF hashes, parity, gates, payload and images) is checked *before* the
    # durable intent is claimed. A refusal here provably precedes any createDraftListing
    # request, so it must not park the version behind RECONCILE_REQUIRED and a halting
    # incident: nothing was sent, and the retry after the condition clears creates once.
    # The same check still runs inside the client immediately before the create request
    # (`before_create`); a refusal *there* happens after the claim and stays conservative.
    # An intent that already exists is reported first: its unknown outcome outranks today's
    # evidence.
    #
    # The early check applies to the stock `EtsyClient.publish`, which is known to run
    # `before_create` strictly before `create_draft`: for it, this only moves a refusal that
    # would have happened anyway to before the claim. A publish implementation of unknown
    # order is handled exactly as before (its own hook use decides), and any failure of it
    # stays RECONCILE_REQUIRED below.
    known_order = getattr(type(client), "publish", None) is _STOCK_PUBLISH
    draft_intent.refuse_if_existing(ctx.db, slug, version)
    # Review 6818959626 (E3 HIGH): a REAL draft (a client whose requests go to Etsy) needs a
    # credential that is usable now -- a recent successful read, an openable OAuth grant and
    # every needed scope -- not merely configured. Checked before the intent is claimed, so a
    # refusal provably sent nothing. A client pointed anywhere else (the local fake) is not a
    # real draft and is unaffected; its own gates still apply.
    credential_refusal = real_draft_credential_refusal(ctx.db, client)
    if credential_refusal:
        ctx.audit("store.execution_refused", artifact=f"{slug}@{version}",
                  detail={"release": release, "stage": "credential",
                          "reason": credential_refusal[:500]})
        raise PermanentError("PUBLISH_EXECUTION_REFUSED: " + credential_refusal)
    if known_order:
        _revalidate_publish_effect(ctx, slug=slug, version=version, release=release,
                                   payload=payload, docs=docs, listing_images=listing_images,
                                   reserved_digest=content_digest, stage="pre_claim")
    intent_key, intent_token = draft_intent.claim(
        ctx.db,slug=slug,version=version,release=release,content_digest=content_digest)
    # Whether the create request could have left. For any publish implementation other than
    # the stock one the request is presumed possibly sent (fail closed).
    hook = {"entered": not known_order}

    def before_create():
        hook["entered"] = True
        _revalidate_publish_effect(
            ctx, slug=slug, version=version, release=release,
            payload=payload, docs=docs, listing_images=listing_images,
            reserved_digest=content_digest, stage="before_create")
        # ENG-ETSY-PUBLISH: a draft already on Etsy for this release, with no local intent,
        # is adopted rather than duplicated (`publish.draft_adoption`). Read only after the
        # full revalidation above, so a refused gate still sends no request at all, and only
        # for the stock client (production's), whose create follows this hook. Any outcome
        # but "none" leaves here before createDraftListing, so nothing was created.
        if known_order:
            _duplicate_check(ctx, client, slug=slug, version=version, release=release,
                             hook=hook)

    from ..integrations.etsy import OwnerGrant

    def _publication_grant():
        # One grant, resolved anew by the client at every effect boundary (rc1-AUTH D3;
        # J-product P-5: post-create writes complete only the draft this grant created).
        return OwnerGrant(ctx.db, action=OwnerGrant.PUBLISH,
                          approval_id=(ctx.job.inputs or {}).get(
                              "owner_publication_approval_id"),
                          slug=slug, version=version, release=release)

    try:
        outcome = client.publish(payload=payload,
                                 filename=f"{slug}-{pattern_filename('US')}",
                                 data=doc.pdf_bytes, images=listing_images["images"],
                                 before_create=before_create,
                                 # rc1-AUTH D3: the client re-verifies the sealed grant and
                                 # the live phase itself, immediately before the create.
                                 grant=_publication_grant(),
                                 on_created=lambda remote_id: draft_intent.checkpoint(
                                     ctx.db,intent_key,intent_token,remote_id))
    except _AdoptInstead as adopt:
        return _adopt_and_complete(
            ctx, client, slug=slug, version=version, release=release, payload=payload,
            docs=docs, hash_check=hash_check, stored=stored,
            stored_by_terminology=stored_by_terminology, listing_images=listing_images,
            listing_id=adopt.listing_id, intent_key=intent_key,
            intent_token=intent_token, found=adopt.found)
    except BaseException:
        # Hard process death cannot run this block; the committed CREATING intent still
        # blocks the next attempt. Ordinary failures additionally open a visible incident.
        if hook.get("duplicate_refused"):
            # The duplicate check refused before createDraftListing: provably unsent.
            draft_intent.release_unsent(ctx.db,intent_key,intent_token)
            raise
        if hook["entered"]:
            draft_intent.uncertain(ctx.db,intent_key,intent_token)
        else:
            draft_intent.release_unsent(ctx.db,intent_key,intent_token)
        raise
    if not outcome.listing_id:
        if hook["entered"]:
            draft_intent.uncertain(ctx.db,intent_key,intent_token)
        else:
            # The client refused before reaching the create hook: no request was sent.
            draft_intent.release_unsent(ctx.db,intent_key,intent_token)


    # The second file, attached after the first.
    #
    # `assets.build` renders both terminologies and the listing claims both, so a listing that
    # delivers only the US document takes money for something it did not sell. `client.publish`
    # creates the draft and attaches one file, which is the right shape for the transaction it
    # names; the rest are ordinary `attach_file` calls against a listing that now exists.
    #
    # Recorded per file rather than folded into one boolean: a listing with the US pattern and
    # no UK pattern is a real, deliverable, partly-wrong state, and "published: true" would
    # hide it. That is the half-done case this handler already refuses to round off.
    extra_files: dict[str, bool] = {}
    extra_problems: list[str] = []
    if outcome.listing_id:
        for prop in payload.properties:
            try:
                client.set_listing_property(outcome.listing_id, prop,
                                            grant=_publication_grant())
            except (TransientError, PermanentError) as e:
                extra_problems.append(f"listing property {prop['property_id']} write failed: {e}")

    if outcome.listing_id and outcome.file_uploaded:
        for terminology in TERMINOLOGIES[1:]:
            try:
                extra_files[terminology] = client.attach_file(
                    outcome.listing_id,
                    filename=f"{slug}-{pattern_filename(terminology)}",
                    data=docs[terminology].pdf_bytes, grant=_publication_grant())
            except (TransientError, PermanentError) as e:
                extra_files[terminology] = False
                extra_problems.append(
                    f"listing {outcome.listing_id} has the US pattern attached and not the "
                    f"{terminology} one, which the listing copy promises: {e}")
            else:
                if not extra_files[terminology]:
                    extra_problems.append(
                        f"listing {outcome.listing_id} accepted the {terminology} pattern "
                        f"upload without returning a file id, so the buyer may receive only "
                        f"the US document the listing copy promises alongside it")

    return _read_back_and_record(
        ctx, client, outcome=outcome, extra_files=extra_files, extra_problems=extra_problems,
        slug=slug, version=version, release=release, payload=payload, docs=docs,
        hash_check=hash_check, stored=stored, stored_by_terminology=stored_by_terminology,
        listing_images=listing_images, grant_fn=_publication_grant)


class _AdoptInstead(Exception):
    """Raised from `before_create` when an existing draft is to be adopted: no create."""

    def __init__(self, listing_id: str, found: list):
        super().__init__(listing_id)
        self.listing_id, self.found = listing_id, found


def _duplicate_check(ctx, client, *, slug, version, release, hook) -> None:
    """ENG-ETSY-PUBLISH: none returns (create proceeds); adopt raises `_AdoptInstead`;
    escalate raises PermanentError; unread raises TransientError. Nothing is written."""
    from ..core.resilience import PermanentError, TransientError
    from ..publish import draft_adoption

    existing = draft_adoption.check(ctx.db, client, slug=slug, version=version)
    verdict = existing["verdict"]
    if verdict == draft_adoption.NONE:
        return
    if verdict == draft_adoption.ADOPT:
        raise _AdoptInstead(existing["listing_id"], existing["found"])
    hook["duplicate_refused"] = True
    if verdict == draft_adoption.UNREAD:
        _dead_letter_if_unread_too_often(ctx, slug=slug, version=version, release=release,
                                         why=str(existing["why"]))
        ctx.audit("store.execution_refused", artifact=f"{slug}@{version}",
                  detail={"release": release, "stage": "duplicate_check",
                          "reason": f"the shop could not be read for an existing draft: "
                                    f"{existing['why']}"[:500]})
        raise TransientError("DRAFT_DUPLICATE_CHECK_UNREAD: the shop's listings could not be "
                             "read, so no create is sent: " + str(existing["why"])[:300])
    ctx.audit(draft_adoption.ESCALATED, artifact=f"{slug}@{version}",
              detail={"release": release, "why": existing["why"],
                      "found": existing["found"][:10]})
    raise PermanentError("DRAFT_ADOPTION_ESCALATED: " + str(existing["why"]))


#: Review b17-d A3: consecutive UNREAD duplicate checks for one release before the job is
#: dead-lettered behind a single P2 incident. It still fails closed: nothing is created.
MAX_CONSECUTIVE_UNREAD = 5


def _unread_streak(ctx, *, slug: str, version: str, release: str) -> int:
    """Consecutive UNREAD duplicate-check refusals for this release, newest first, ended by any
    other duplicate-check outcome (adopted, escalated) or a publish record for the version."""
    from sqlalchemy import select

    from ..core.models import AuditLog
    from ..publish import draft_adoption

    ends = {draft_adoption.ADOPTED, draft_adoption.ESCALATED, "store.published",
            "store.publish_incomplete"}
    streak = 0
    with ctx.db.session() as s:
        rows = s.scalars(select(AuditLog).where(AuditLog.artifact == f"{slug}@{version}")
                         .order_by(AuditLog.id.desc()).limit(500)).all()
        for row in rows:
            detail = row.detail or {}
            if row.action in ends:
                break
            if (row.action == "store.execution_refused"
                    and detail.get("stage") == "duplicate_check"
                    and detail.get("release") == release):
                streak += 1
    return streak


def _dead_letter_if_unread_too_often(ctx, *, slug: str, version: str, release: str,
                                     why: str) -> None:
    """Review b17-d A3: after `MAX_CONSECUTIVE_UNREAD` unread shops in a row, stop retrying.

    One P2 incident `store.draft_adoption:unread:<slug>@<version>` (deduplicated while open)
    and a PermanentError, which dead-letters the job. Nothing is sent to Etsy either way.
    """
    from sqlalchemy import select

    from ..core.models import Incident
    from ..core.resilience import PermanentError

    streak = _unread_streak(ctx, slug=slug, version=version, release=release) + 1
    if streak < MAX_CONSECUTIVE_UNREAD:
        return
    signature = f"store.draft_adoption:unread:{slug}@{version}"
    with ctx.db.session() as s:
        open_row = s.scalar(select(Incident).where(Incident.signature == signature,
                                                   Incident.resolved.is_(False)))
        if open_row is None:
            s.add(Incident(severity="P2", product_slug=slug, signature=signature,
                           summary=(f"The shop could not be read for an existing draft of "
                                    f"{slug}@{version} {streak} times in a row; the publish "
                                    f"job is dead-lettered and nothing was created."),
                           halts_publication=False,
                           detail={"release": release, "streak": streak, "why": why[:300]}))
        else:
            open_row.report_count = int(open_row.report_count or 0) + 1
    ctx.audit("store.execution_refused", artifact=f"{slug}@{version}",
              detail={"release": release, "stage": "duplicate_check_dead_letter",
                      "streak": streak, "reason": why[:500]})
    raise PermanentError(f"DRAFT_DUPLICATE_CHECK_UNREAD_DEAD_LETTER: the shop could not be "
                         f"read {streak} times in a row for {slug}@{version}; nothing was "
                         f"created: {why[:200]}")


def _refuse_held_pattern_files(ctx, client, listing_id: str, *, slug: str, version: str,
                               release: str) -> None:
    """Review b17-d A2: an adopted draft that already holds a file named like one of ours is
    escalated. The read-back compares files by name and size, so an earlier release's PDF of
    the same size would pass it; this client has no file delete to replace it under the
    grant. An unreadable file list is left to `_complete_draft`, which reports it."""
    from ..core.resilience import PermanentError, TransientError
    from ..publish import draft_adoption
    from ..publish.pdf import TERMINOLOGIES, pattern_filename

    try:
        held = {str(r.get("filename") or "") for r in client.get_listing_files(listing_id) or []}
    except (TransientError, PermanentError):
        return
    ours = sorted(held & {f"{slug}-{pattern_filename(t)}" for t in TERMINOLOGIES})
    if not ours:
        return
    why = (f"adopted draft {listing_id} already holds {', '.join(ours)}; the bytes cannot be "
           "proven to be this release's and the client has no file delete to replace them")
    ctx.audit(draft_adoption.ESCALATED, artifact=f"{slug}@{version}",
              detail={"release": release, "why": why, "etsy_listing_id": listing_id,
                      "held_files": ours})
    raise PermanentError("DRAFT_ADOPTION_ESCALATED: " + why)


def _adopt_and_complete(ctx: JobContext, client, *, slug, version, release, payload, docs,
                        hash_check, stored, stored_by_terminology, listing_images,
                        listing_id: str, intent_key, intent_token, found) -> dict:
    """ENG-ETSY-PUBLISH slice 2: the draft is already on Etsy; adopt it, never create.

    The intent claimed for this release is checkpointed to the existing id, which is the path a
    successful create takes, so the local listing and the intent record it together. The draft
    is then completed in place under the same publication grant (only its own draft) and read
    back exactly like a new one. If the checkpoint fails, the intent goes to reconciliation:
    the existing draft is never doubled.
    """
    from ..core.resilience import PermanentError
    from ..integrations.etsy import OwnerGrant, PublishOutcome
    from ..publish import draft_adoption, draft_intent

    try:
        draft_intent.checkpoint(ctx.db, intent_key, intent_token, listing_id)
    except BaseException:
        draft_intent.uncertain(ctx.db, intent_key, intent_token)
        raise
    ctx.audit(draft_adoption.ADOPTED, artifact=f"{slug}@{version}",
              detail={"release": release, "etsy_listing_id": listing_id,
                      "found": list(found)[:10]})

    def _grant():
        return OwnerGrant(ctx.db, action=OwnerGrant.PUBLISH,
                          approval_id=(ctx.job.inputs or {}).get(
                              "owner_publication_approval_id"),
                          slug=slug, version=version, release=release)

    # Review b17-d A2: a held file with one of our names may be an earlier release's PDF of
    # the same size; the read-back compares name and size only, so it could pass. This client
    # has no file delete, so such a draft is escalated to the owner, never adopted as verified.
    _refuse_held_pattern_files(ctx, client, listing_id, slug=slug, version=version,
                               release=release)
    try:
        # Review b17-d A1: every rank is re-sent, so the read-back hashes our own bytes.
        done = _complete_draft(client, listing_id, slug=slug, docs=docs,
                               listing_images=listing_images, payload=payload, grant_fn=_grant,
                               force_images=True)
    except PermanentError:
        done = {"files": {}, "images_uploaded": 0, "sent_ranks": {},
                "problems": ["completion refused"]}
    outcome = PublishOutcome(published=bool(done["files"].get("US")), listing_id=listing_id,
                             file_uploaded=bool(done["files"].get("US")),
                             images_uploaded=done["images_uploaded"],
                             image_sha256_by_rank=dict(done.get("sent_ranks") or {}),
                             problems=list(done["problems"]))
    extra_files = {t: ok for t, ok in done["files"].items() if t != "US"}
    return _read_back_and_record(
        ctx, client, outcome=outcome, extra_files=extra_files, extra_problems=[],
        slug=slug, version=version, release=release, payload=payload, docs=docs,
        hash_check=hash_check, stored=stored, stored_by_terminology=stored_by_terminology,
        listing_images=listing_images, grant_fn=_grant,
        adopted={"etsy_listing_id": listing_id, "found": list(found)[:10]})


def _read_back_and_record(ctx: JobContext, client, *, outcome, extra_files: dict,
                          extra_problems: list, slug: str, version: str, release: str,
                          payload, docs: dict, hash_check: dict, stored,
                          stored_by_terminology: dict, listing_images: dict, grant_fn,
                          adopted: dict | None = None) -> dict:
    """Read the draft back, complete it in place within bounds, record the outcome.

    ENG-ETSY-PUBLISH slice 2: a draft that reads back short is completed in place
    (`_complete_draft`, sending only what Etsy lacks) and read again, at most
    `MAX_COMPLETION_ROUNDS` times. A field mismatch that completion cannot fix ends the loop
    at once, so the bound is a ceiling and not a schedule.
    """
    from sqlalchemy import select

    from ..core.models import Listing
    from ..publish.pdf import TERMINOLOGIES, pattern_filename
    from . import etsy_ops

    # F-542 / F-559: read the draft and its files back. Only what Etsy holds afterwards
    # decides whether this is published; the writes' own 2xx responses cannot.
    certified = hash_check.get("certified") or {}
    # Review b17-d A1: rank -> SHA-256 of image bytes actually uploaded in this job.
    uploaded_images: dict[int, str] = dict(getattr(outcome, "image_sha256_by_rank", None) or {})
    sent_docs = {f"{slug}-{pattern_filename(t)}": docs[t].pdf_bytes
                 for t in TERMINOLOGIES
                 if t == "US" and outcome.file_uploaded or extra_files.get(t)}
    expected_files = etsy_ops.file_expectations(
        {f"{slug}-{pattern_filename(t)}": docs[t].pdf_bytes for t in TERMINOLOGIES},
        {f"{slug}-{pattern_filename(t)}": certified.get(t) for t in TERMINOLOGIES})
    readback: dict = {"verified": False, "reasons": ["no listing was created"]}
    completion_rounds: list[dict] = []

    def _read():
        return etsy_ops.read_back(
            client, outcome.listing_id, sent=etsy_ops.sent_fields(payload),
            expected_files=expected_files, expected_images=len(listing_images["images"]),
            # PT-12: the certified alt text (the disclosure) is read back from Etsy too.
            expected_alt_texts=[str(getattr(e, "alt_text", "") or
                                    (e[2] if len(e) > 2 else "") or "")
                                for e in listing_images["images"]],
            sent_images=listing_images, uploaded_images=uploaded_images)

    if outcome.listing_id:
        readback = _read()
        while (not readback["verified"] and len(completion_rounds) < MAX_COMPLETION_ROUNDS
               and etsy_ops.completable(readback)):
            images_rb = readback.get("images") or {}
            done = _complete_draft(client, outcome.listing_id, slug=slug, docs=docs,
                                   listing_images=listing_images, payload=payload,
                                   grant_fn=grant_fn,
                                   force_images=bool(images_rb) and not images_rb.get(
                                       "verified"))
            uploaded_images.update(done.get("sent_ranks") or {})
            completion_rounds.append({"files": done["files"],
                                      "images_uploaded": done["images_uploaded"],
                                      "problems": done["problems"][:4]})
            for t, ok in done["files"].items():
                if t != "US":
                    extra_files[t] = ok
            if done["files"].get("US"):
                outcome.file_uploaded = True
            readback = _read()
        if readback["verified"]:
            # The writes' own errors are superseded by what Etsy holds once completed.
            extra_problems[:] = []
            outcome.problems = []
            outcome.published = True
            outcome.file_uploaded = True
            outcome.images_uploaded = len(listing_images["images"])
    published = bool(outcome.published and outcome.activatable and not extra_problems
                     and readback["verified"])

    if outcome.listing_id:
        with ctx.db.session() as s:
            row = s.scalar(select(Listing).where(Listing.product_slug == slug,
                                                 Listing.version == version))
            if row is not None:
                row.etsy_listing_id = outcome.listing_id
                row.state = "published" if published else "incomplete_on_etsy"

    ctx.audit("store.published" if published else "store.publish_incomplete",
              artifact=f"{slug}@{version}",
              detail={"etsy_listing_id": outcome.listing_id,
                      "file_uploaded": outcome.file_uploaded,
                      "images_uploaded": outcome.images_uploaded,
                      "image_order": listing_images["order"],
                      "listing_set_certificate": listing_images["record_id"],
                      "pdf_sha256": stored.sha256,
                      "pdf_sha256_by_terminology": {
                          t: art.sha256
                          for t, art in sorted(stored_by_terminology.items())},
                      "files_attached_by_terminology": {
                          "US": outcome.file_uploaded, **extra_files},
                      "files_sent": [f for f in expected_files if f["name"] in sent_docs],
                      "read_back": readback,
                      "completion_rounds": completion_rounds,
                      "adopted": adopted,
                      "problems": (outcome.problems + extra_problems
                                   + readback.get("reasons", []))[:8]})

    # ENG-ETSY-PUBLISH slice 2: the one "Approve first public listing (step-up)" card follows
    # the evidence (raised only with a verified read-back, both PDF hashes, image hashes and
    # gate results). It grants nothing; a failure here never changes the publish outcome.
    try:
        from ..publish import first_listing_card

        first_listing_card.refresh(ctx.db)
    except Exception as exc:  # noqa: BLE001
        ctx.audit("first_listing.card_refresh_failed", artifact=f"{slug}@{version}",
                  detail={"error": f"{type(exc).__name__}: {str(exc)[:200]}"})

    if outcome.listing_id and not published:
        etsy_ops.open_publish_incomplete(
            ctx.db, slug=slug, version=version, listing_id=outcome.listing_id,
            reasons=(outcome.problems + extra_problems + readback.get("reasons", [])))
    if published:
        # The activation handler reads this draft back again, checks it against the certified
        # listing and the release gates, and refuses unless the owner's authority is present
        # at that moment. Queuing it here is what makes the verification half run for every
        # draft; the activation half stays refused without a launch authorisation.
        from .release import chain_key

        ctx.enqueue("store_operator", "store.activate",
                    {"slug": slug, "version": version, "release": release},
                    idempotency_key=chain_key("activate", slug, version, release,
                                              outcome.listing_id or ""))

    if outcome.needs_completion:
        # A listing on Etsy with no file attached would take money and deliver nothing.
        from ..gates.incidents import DefectReport, IncidentTracker

        IncidentTracker(ctx.db).report(DefectReport(
            product_slug=slug, pattern_version=version, component=None, row=None,
            customer_ref=f"etsy:{outcome.listing_id}",
            text=(f"Etsy listing {outcome.listing_id} exists with no digital file attached. "
                  f"It must be completed or deleted before it can take an order.")))

    return {"slug": slug, "version": version, "published": published,
            "etsy_listing_id": outcome.listing_id,
            "file_uploaded": outcome.file_uploaded,
            "images_uploaded": outcome.images_uploaded,
            "files_attached_by_terminology": {"US": outcome.file_uploaded, **extra_files},
            "read_back_verified": readback["verified"],
            "completion_rounds": len(completion_rounds),
            "adopted_existing_draft": bool(adopted),
            "problems": outcome.problems + extra_problems + readback.get("reasons", [])}


@handlers.register("store.activate")
def handle_store_activate(ctx: JobContext) -> dict:
    """Draft to live (F-543): only when Etsy's draft is the certified listing and the owner
    has authorised publication *at the moment this runs*.

    Order, and why:

    1. The release gates and creative parity are recomputed now, from evidence on file, and
       recorded -- as store.publish does -- so Shadow Mode still produces the record.
    2. SHADOW refuses, first and always.
    3. The remote draft is read back and compared with the certified listing: every field
       sent (title, description, tags, materials, price, quantity, taxonomy, type), the draft
       state, the image count against the listing-set certificate's frames, the customer's
       files by name and exact size against the files the verified publish sent (whose bytes
       were hash-checked against the release), and the owed disclosures on the copy **as Etsy
       holds it**. Any gap is a reasoned block, never an activation.
    4. Authority is revalidated at execution (F-835): the phase resolved now (rc1-AUTH A1:
       the owner's recorded phase AND the environment, not the worker's boot reading), the owner's
       publishing grant read from the environment *now*, a recorded content-bound owner
       approval resolved from its ID, and the daily spend ceiling including the listing fee.
       Nothing the job carried from when it was planned counts.
    5. Only then `EtsyClient.activate`, which re-checks image and file itself, and a
       read-back that the listing is `active` before anything records it as live.

    WS4-8 (Stage A use path): a job marked `standing_activation` carries no approval. It finds
    the standing activation grant the policy issuer bound to THIS job, consumes it once, and
    goes through every step above unchanged -- the grant (`seg:<id>`, re-checked by
    `standing_activation.use_refusal`) only takes the place of the owner's per-product
    approval. After the read-back shows the listing `active` it is recorded in SP lineage;
    a retry after a crash past the Etsy request reconciles from the read-back instead of
    sending again. Off in code with `standing_activation.STAGE_A_ENABLED`.
    """
    import os

    from sqlalchemy import select

    from ..core.models import Listing
    from ..integrations.etsy import LISTING_FEE_USD, PHASES_THAT_MAY_PUBLISH, Authority
    from ..integrations.etsy_oauth import EtsyAuthNeedsOwner
    from . import etsy_ops

    i = ctx.job.inputs or {}
    slug, version = i["slug"], i.get("version", "1.0.0")
    artifact = f"{slug}@{version}"
    parity_verdict = _listing_parity(ctx)
    release_gates = _release_gates(ctx, stage="activation")
    ctx.audit("store.activate_gates", artifact=artifact,
              detail={"parity_blocks": parity_verdict["blocks_release"],
                      "release_gates_block": release_gates["blocks_release"],
                      "reasons": release_gates["reasons"][:5]})

    # rc1-AUTH A1: the phase is the owner's recorded phase AND the environment, resolved
    # now -- an owner rollback recorded after this worker booted stops activation.
    phase_now = protected_phase(ctx)
    if phase_now is Phase.SHADOW:
        ctx.audit("store.activate_refused", artifact=artifact,
                  detail={"reason": "shadow mode: no listing is ever activated",
                          "effective_phase": phase_now.value})
        raise ShadowModeRefusal(
            "store.activate publishes a listing on etsy.com; the system is in SHADOW mode.")

    with ctx.db.session() as s:
        listing = s.scalar(select(Listing).where(Listing.product_slug == slug,
                                                 Listing.version == version))
        listing_id = listing.etsy_listing_id if listing is not None else ""
        local_state = listing.state if listing is not None else ""
    if not listing_id:
        ctx.audit("store.activate_refused", artifact=artifact,
                  detail={"reason": "no Etsy draft is recorded for this release"})
        return {"slug": slug, "version": version, "activated": False,
                "reasons": ["no Etsy draft is recorded for this release"]}
    standing = bool(i.get("standing_activation"))
    already = {"slug": slug, "version": version, "activated": False,
               "etsy_listing_id": listing_id, "reasons": ["already active"]}
    # MEDIUM-1: a standing job whose listing already reads active locally may be the retry of
    # an attempt that stopped between the active commit and its Stage A lineage; it reaches
    # the reconcile below (which sends nothing) before it can stop here.
    if local_state == "active" and not standing:
        return already

    # Read at execution: the grant may have been withdrawn since this job was queued.
    owner_authorised = os.environ.get("BRAMBLELOOP_PUBLISH_AUTHORISED", "") == "1"
    client = etsy_ops.build_client(ctx.db, phase_now.value, owner_authorised=owner_authorised)
    if client.credentials is None:
        ctx.audit("store.activate_refused", artifact=artifact,
                  detail={"reason": client.refusal_for(Authority.READ)})
        raise ShadowModeRefusal(client.refusal_for(Authority.READ) or "no credentials")

    try:
        remote = etsy_ops.with_properties(client, listing_id, client.get_listing(listing_id))
        remote_files = client.get_listing_files(listing_id)
    except EtsyAuthNeedsOwner as e:
        raised = etsy_ops.record_auth_needs_owner(ctx.db, e, where="store.activate")
        ctx.audit("store.activate_refused", artifact=artifact,
                  detail={"reason": "Etsy credential needs the owner", **raised})
        raise

    # WS4-8: a standing job's authority is the grant the issuer bound to this job, found in
    # the grant store -- never anything the job carried. One authority per job.
    seg_id = None
    if standing:
        from ..ops import standing_activation_flow as stage_a

        if i.get("owner_activation_approval_id") not in (None, ""):
            why = "a job carries one authority: a standing job never also names an owner approval"
            ctx.audit("store.activate_refused", artifact=artifact, detail={"reason": why})
            return {"slug": slug, "version": version, "activated": False,
                    "etsy_listing_id": listing_id, "reasons": [why]}
        found = stage_a.grant_for_job(ctx.db, ctx.job.id)
        seg_id = found["grant_id"]
        if seg_id is None and local_state == "active":
            return already
        if seg_id is None:
            ctx.audit("store.activate_refused", artifact=artifact,
                      detail={"reason": found["why"], "authority": "standing"})
            return {"slug": slug, "version": version, "activated": False,
                    "etsy_listing_id": listing_id, "reasons": [found["why"]]}
        if local_state == "active" and \
                stage_a.lineage_recorded(ctx.db, seg_id, str(listing_id)):
            return already
        # A retry after a crash past the Etsy request (or after the active commit, before its
        # lineage was recorded): Etsy's read-back decides, nothing is sent again and the fee
        # is not reserved twice.
        reconciled = stage_a.reconcile(ctx, grant_id=seg_id, listing_id=str(listing_id),
                                       remote=remote, slug=slug, version=version)
        if reconciled is not None:
            return reconciled
        if local_state == "active":
            # Recorded active here, but no lineage and nothing this job can reconcile from
            # (Etsy does not read it active, or the intent is not this job's): send nothing,
            # and never leave a live listing outside lineage silently.
            if str(remote.get("state") or "").lower() == "active" and \
                    stage_a.owner_activated(ctx.db, str(listing_id)):
                # Verdict 7012067586 item 2: the owner made it live between grant issue and
                # this run (per-product approval). Not this grant's listing: no lineage, no P1.
                ctx.audit("store.activate_refused", artifact=artifact,
                          detail={"reason": "already active: activated by the owner",
                                  "authority": "standing", "grant_id": seg_id})
                return {**already, "reasons": ["already active: activated by the owner"]}
            if str(remote.get("state") or "").lower() == "active":
                written = stage_a.open_lineage_unrecorded(
                    ctx.db, grant_id=seg_id, listing_id=str(listing_id), artifact=artifact,
                    why="the listing reads active but this job holds no applied activation "
                        "intent to reconcile it from")
                if not written:
                    # Verdict 7012067586 item 1: no lineage and no incident is never silent.
                    raise stage_a.LineageUnrecorded(
                        f"listing {listing_id} reads active with no lineage and its incident "
                        f"could not be written")
            return already

    from ..integrations import etsy_verify

    frames = etsy_ops.certified_frames(ctx.db, slug, version, release=i.get("release", ""))
    expected_files = etsy_ops.published_files(ctx.db, slug, version, listing_id)
    verdict = etsy_verify.activation_readiness(
        sent=etsy_ops.sent_fields(etsy_ops.certified_payload(ctx.db, slug, version)),
        remote=remote, remote_files=remote_files,
        expected_files=expected_files or [], expected_images=len(frames["frames"]),
        listing_id=listing_id, disclosure=etsy_ops.disclosure_on_remote(remote))
    reasons = list(verdict["reasons"]) + list(frames["problems"])
    if expected_files is None:
        reasons.append("no verified store.published record names the files sent to this "
                       "draft, so the customer's download cannot be checked")
    if parity_verdict["blocks_release"]:
        reasons.append(f"creative parity (#75): {parity_verdict['why']}")
    if release_gates["blocks_release"]:
        reasons.extend(f"release gate: {r}" for r in release_gates["reasons"][:10])
    ctx.audit("store.activation_verified", artifact=artifact,
              detail={"etsy_listing_id": listing_id, "ready": not reasons,
                      "reasons": reasons[:15], "fields": verdict["fields"],
                      "files": verdict["files"], "disclosure": verdict["disclosure"]})
    if reasons:
        return {"slug": slug, "version": version, "activated": False, "blocked": True,
                "etsy_listing_id": listing_id, "reasons": reasons}

    # The draft is the certified listing: whatever read-back incident the publish left is
    # closed by this reading.
    from ..ops import incident_lifecycle as lifecycle

    with ctx.db.session() as s:
        lifecycle.resolve_signatures(
            s, [f"{etsy_ops.PUBLISH_INCOMPLETE}{slug}@{version}"],
            resolution=f"store.activate read listing {listing_id} back and it matches the "
                       f"certified listing field by field, with its images and files")

    from ..ops import activation_authority

    if standing:
        from ..ops import standing_activation

        authorisation = f"{standing_activation.SEG_PREFIX}{seg_id}"
    else:
        authorisation = i.get("owner_activation_approval_id")

    def _authority_refusal():
        """The job's one authority, resolved anew each time it is asked."""
        if standing:
            # Everything `use_refusal` checks except the write-ahead intent, which cannot
            # exist yet; the client re-checks with the intent immediately before the request.
            return standing_activation.use_refusal(
                ctx.db, authorisation, slug=slug, version=version, listing_id=str(listing_id),
                release=i.get("release", ""), job_id=ctx.job.id, remote=remote,
                at_effect=False)
        return activation_authority.validate(
            ctx.db, authorisation, slug=slug, version=version,
            listing_id=listing_id, release=i.get("release", ""))

    refusal = client.refusal_for(Authority.ACTIVATE)
    if refusal is None and standing:
        # Consumed once, by this job, after the draft read back as the certified listing.
        refusal = stage_a.claim(ctx.db, seg_id, job_id=ctx.job.id)
    if refusal is None:
        refusal = _authority_refusal()
    from ..finance import listing_costs
    from ..core.fx import ASSUMED_CAD_PER_USD
    fee_cad = round(LISTING_FEE_USD * ASSUMED_CAD_PER_USD, 2)
    pending_fee = listing_costs.pending(ctx.db, listing_id, fee_cad)
    if refusal is None:
        agent = ctx.registry.get(ctx.job.agent)
        spent = ctx.registry.spend_today(ctx.job.agent)
        if spent + pending_fee > agent.daily_cost_ceiling_cad:
            refusal = (f"the listing fee (about CA${fee_cad:.2f}) would take "
                       f"{ctx.job.agent} past its daily ceiling of "
                       f"CA${agent.daily_cost_ceiling_cad:.2f} (spent CA${spent:.2f})")
    if refusal is None:
        # ENG-APPROVALS: the owner's opening-catalogue listing-fee budget (CA$6 in total,
        # reservations counted; D-OWNER-STANDING-INTERNAL). `reserve` re-checks it under the
        # accounting lock; this is the early, audited refusal.
        refusal = listing_costs.opening_budget_refusal(ctx.db, listing_id, fee_cad)
    if refusal is not None:
        ctx.audit("store.activate_refused", artifact=artifact,
                  detail={"reason": refusal, "verified": True,
                          "etsy_listing_id": listing_id})
        return {"slug": slug, "version": version, "activated": False, "verified": True,
                "etsy_listing_id": listing_id, "reasons": [refusal]}

    # Read authority and mutable gates again after read-back/budget work, directly at
    # the effect boundary. A queued magic string is never owner evidence.
    final_gates, final_parity = (_release_gates(ctx, stage="activation"),
                                  _listing_parity(ctx))
    refusal = _authority_refusal()
    if os.environ.get("BRAMBLELOOP_PUBLISH_AUTHORISED", "") != "1":
        refusal = "owner publishing grant withdrawn"
    if final_gates["blocks_release"] or final_parity["blocks_release"]:
        refusal = "release/parity gates changed before activation"
    phase_live = protected_phase(ctx).value
    if phase_live not in PHASES_THAT_MAY_PUBLISH:
        refusal = (f"runtime phase is now {phase_live!r} (owner's recorded phase and the "
                   f"environment); activation refused")
    if refusal:
        ctx.audit("store.activate_refused", artifact=artifact, detail={"reason": refusal})
        return {"activated": False, "blocked": True, "reasons": [refusal]}
    listing_costs.reserve(ctx.db, listing_id=listing_id, amount=fee_cad,
                          agent=ctx.job.agent, ceiling=ctx.registry.get(ctx.job.agent).daily_cost_ceiling_cad,
                          job_id=ctx.job.id)
    # Reserving can wait on another accounting transaction. Authority and product truth
    # must be current after that wait; a revoked attempt retains conservative exposure.
    final_gates, final_parity = (_release_gates(ctx, stage="activation"),
                                  _listing_parity(ctx))
    refusal = _authority_refusal()
    if os.environ.get("BRAMBLELOOP_PUBLISH_AUTHORISED", "") != "1":
        refusal = "owner publishing grant withdrawn during reservation"
    if final_gates["blocks_release"] or final_parity["blocks_release"]:
        refusal = "release/parity gates changed during reservation"
    phase_live = protected_phase(ctx).value
    if phase_live not in PHASES_THAT_MAY_PUBLISH:
        refusal = (f"runtime phase is now {phase_live!r} (owner's recorded phase and the "
                   f"environment) during reservation; activation refused")
    if refusal:
        ctx.audit("store.activate_refused", artifact=artifact, detail={"reason": refusal})
        return {"activated": False, "blocked": True, "reasons": [refusal]}
    ctx.audit("store.activation_authority_used", artifact=artifact,
              detail={"approval_id": authorisation if standing else int(authorisation),
                      "authority": "standing" if standing else "owner",
                      "etsy_listing_id": listing_id})
    # Immediately before the request: the phase once more, then the client itself re-verifies
    # the sealed grant and the live phase (rc1-AUTH D3) before it sends updateListing.
    phase_live = protected_phase(ctx).value
    if phase_live not in PHASES_THAT_MAY_PUBLISH:
        refusal = (f"runtime phase is now {phase_live!r} immediately before activation; "
                   f"activation refused")
        ctx.audit("store.activate_refused", artifact=artifact, detail={"reason": refusal})
        return {"activated": False, "blocked": True, "reasons": [refusal]}
    from ..integrations.etsy import OwnerGrant

    grant = OwnerGrant(ctx.db, action=OwnerGrant.ACTIVATE, approval_id=authorisation,
                       slug=slug, version=version, release=i.get("release", ""),
                       listing_id=str(listing_id), job_id=ctx.job.id)
    # Audit ddf9c6e L-1: the activation (a listing fee) is at-most-one automatic attempt per
    # listing + approval. A reclaimed or retried run finds the write-ahead intent and is
    # refused for reconciliation instead of re-sending; a stale worker stops at the lease check.
    from ..queue.effects import EffectAlreadyApplied, EffectNotSent, guard as effect_guard

    try:
        try:
            with effect_guard(ctx, "etsy.activate", f"{listing_id}:{authorisation}") as intent:
                try:
                    client.activate(listing_id,
                                    launch_authorisation=(f"standing-grant:{authorisation}"
                                                          if standing else
                                                          f"owner-approval:{authorisation}"),
                                    grant=grant)
                except EtsyAuthNeedsOwner as e:
                    # Refused for authentication: the activation was not performed, so the
                    # intent is released and a run after the owner re-authorises may try.
                    raise EffectNotSent(str(e)) from e
                intent.applied(f"etsy_listing:{listing_id}")
        except EffectNotSent as ns:
            raise ns.__cause__ if isinstance(ns.__cause__, EtsyAuthNeedsOwner) else ns
        after = client.get_listing(listing_id)
    except EffectAlreadyApplied:
        after = client.get_listing(listing_id)
    except EtsyAuthNeedsOwner as e:
        etsy_ops.record_auth_needs_owner(ctx.db, e, where="store.activate")
        raise
    live = str(after.get("state") or "") == "active"
    with ctx.db.session() as s:
        row = s.scalar(select(Listing).where(Listing.product_slug == slug,
                                             Listing.version == version))
        if row is not None and live:
            row.state = "active"
    ctx.audit("store.activated" if live else "store.activate_incomplete", artifact=artifact,
              detail={"etsy_listing_id": listing_id, "state_on_etsy": after.get("state"),
                      "authority": "standing" if standing else "owner",
                      **({"grant_id": seg_id} if standing else {})})
    if live:
        try:
            from ..publish import first_listing_card

            first_listing_card.refresh(ctx.db)   # closes the card: a listing is live
        except Exception as exc:  # noqa: BLE001
            ctx.audit("first_listing.card_refresh_failed", artifact=artifact,
                      detail={"error": f"{type(exc).__name__}: {str(exc)[:200]}"})
    lineage_recorded = None
    if standing and live:
        # L-B: only now -- after `store.activated` and a read-back showing it active -- is
        # the listing in SP lineage, which is what the rollback plan and withdrawal read.
        lineage_recorded = stage_a.record_live(ctx, grant_id=seg_id,
                                               listing_id=str(listing_id), after=after,
                                               artifact=artifact)
    if not live:
        etsy_ops.open_publish_incomplete(
            ctx.db, slug=slug, version=version, listing_id=listing_id,
            reasons=[f"activation was accepted and Etsy reports state "
                     f"{after.get('state')!r}"])
    return {"slug": slug, "version": version, "activated": live,
            "etsy_listing_id": listing_id, "state_on_etsy": after.get("state"),
            **({"lineage_recorded": lineage_recorded} if standing else {})}


def _release_gates(ctx: JobContext, stage: str = "draft") -> dict:
    """The publish gates for the listing this job would export, never raising.

    A gate that crashed has not passed, so an error is reported as a block with its reason
    rather than raised -- raising here would replace the Shadow Mode refusal with a stack
    trace and publish nothing either way, but say so less clearly.
    """
    from datetime import date as _date

    from ..publish import release_gates as gates_mod

    i = ctx.job.inputs or {}
    slug, version = i.get("slug", ""), i.get("version", "1.0.0")
    try:
        verdict = gates_mod.for_publish(
            ctx.db, slug=slug, version=version,
            today=_date.fromisoformat(i["as_of"]) if i.get("as_of") else None,
            positioning=i.get("positioning"), store_root=i.get("artifact_dir"),
            read_only=True, stage=stage)
    except Exception as e:  # noqa: BLE001 - a crashed gate is a closed gate
        return {"slug": slug, "version": version, "blocks_release": True,
                "reasons": [f"release gates could not be evaluated: "
                            f"{type(e).__name__}: {str(e)[:300]}"]}
    return verdict


@handlers.register("ops.heartbeat")
def handle_heartbeat(ctx: JobContext) -> dict:
    q = ctx.queue.counts()
    dead = len(ctx.queue.dead_letters())
    ctx.audit("ops.heartbeat", detail={"queue": q, "dead_letters": dead})
    return {"queue": q, "dead_letters": dead}


# What a cadence reports when it did something. A handler that ran and moved none of these
# did no work, whatever its `ran` flag says -- and the flag is the unreliable half: the
# discovery cadence reported `ran: true, proposed: 0, cost_cad: 0` for two consecutive runs
# because a truncated prompt returned no concepts, and a rule reading only the flag left it
# waiting a week for a window it had already spent.
WORK_COUNTERS: tuple[str, ...] = (
    "proposed", "survivors", "judged", "requeued", "recadenced", "new", "reclassified",
    "inspected", "moved", "enqueued", "listings_known", "dead_letters",
    # A tournament that generated eighty concepts and kept none of them did its job. Reading
    # only `survivors` would call the most informative possible result a no-op and re-drive
    # it, which would pay for the same answer again.
    "generated", "reviews_read",
    # Audit ddf9c6e H-1: the generic counters an undeclared handler can report work through.
    "created", "opened", "written", "posted", "matched", "pruned", "deleted", "published",
    "promoted", "recorded", "drafted", "compiled", "certified", "escalated", "resolved",
    "new_finding", "new_brief", "lessons_routed", "evidence_added", "proposals_written",
)

# Durable artefacts an undeclared handler may report having produced (H-1). A reading row a
# cadence writes on every run (`reading_id`) is deliberately NOT here: an identical reading of
# an empty database is a measurement of nothing, not an artefact.
DURABLE_KEYS: tuple[str, ...] = ("artifact", "artifact_id", "created_ids", "written_ids",
                                 "pdf_sha256", "release_hash")

# Audit ddf9c6e H-1: the explicit per-job-type declaration of which output keys MEASURE
# work. A job of a declared type did useful work only when one of these is positive (a number
# > 0, True, a non-empty list/dict/string -- dicts read recursively; dotted keys reach into a
# nested reading). Everything else in its outputs (state readings, configuration echoes,
# `UNMEASURED` labels, per-run reading ids) is context, not work. An empty tuple declares a
# job type that never counts as useful work on its own (pure liveness).
WORK_KEYS: dict[str, tuple[str, ...]] = {
    # W4-AGENTS cadences and generatable types: each handler reports a measured `work_done`
    # (rows recorded, checks run, jobs queued), which `did_no_work` reads first; declared
    # here so the useful-work judge knows the key rather than falling back to the counters.
    "creative.capability_scorecard": ("work_done",),
    "creative.family_engine": ("work_done",),
    "creative.photo_principles": ("work_done",),
    "creative.salvage_review": ("work_done",),
    "gate.quality": ("work_done",),
    "intel.children_portfolio": ("work_done",),
    # OPUS2-P0 (P0-CHAIN-DEADENDS): dead ends re-driven or resolved.
    "chain.successors": ("work_done",),
    # ENG-SUPPLY: products admitted into engineering this run.
    "supply.admit": ("admitted",),
    # OPUS2-P0 (P0-COMPETITOR-EVIDENCE): shops evaluated into the daily evidence reading.
    "intel.scan_evidence": ("work_done",),
    # WS4-5: shadow decisions recorded (none when no policy is approved).
    "policy.issuer_shadow": ("work_done",),
    # WS4 stop watch: one reading per watched standing policy.
    "policy.stop_watch": ("work_done",),
    # WS4-8 Stage A: standing activations scheduled plus shadow decisions recorded.
    "policy.activation_schedule": ("work_done",),
    # OPUS2-P0: lessons published or withdrawn from measured listing performance.
    "improve.commercial_lessons": ("work_done",),
    "learning.loops": ("work_done",),
    # OPUS2-P0 (P0-LEARNING-GAPS): gaps recorded or reference purchases recommended.
    "learning.knowledge_gaps": ("work_done",),
    "listing.cross_sell_graph": ("work_done",),
    # W4-C12 wiring: Search Visibility aging, boost-window captures, dashboard task harvest.
    "listing.search_visibility_aging": ("work_done",),
    "listing.window_captures": ("work_done",),
    "etsy.dashboard_harvest": ("work_done",),
    "radar.competitor_snapshot": ("work_done",),
    "radar.concept_intake": ("work_done",),
    "intel.watchlist_scan": ("work_done",),
    "intel.watchlist_compare": ("work_done",),
    "intel.benchmark_shopping": ("work_done",),
    "intel.opportunity_review": ("work_done",),
    "research.sweep": ("work_done",),
    "storefront.review": ("work_done",),
    "visual.model_ledger": ("work_done",),
    "ads.adjust": ("enqueued", "escalations"),
    "assets.build": ("pdf_sha256",),
    "autonomy.department_review": ("new_finding", "lessons_routed"),
    "autonomy.morning_handoff": ("new_brief",),
    "autonomy.orchestrate": ("enqueued",),
    "build.tick": ("unparked",),
    "chain.rebuild": ("certified", "restarted", "redrafted", "collections_restarted"),
    "cir.compile": ("compiled",),
    "cir.draft": ("drafted",),
    "cir.reengineer": ("work_done",),     # W4-C07 F-114
    "collection.assemble": ("requeued", "assembled"),
    "commerce.order_readings": ("study_opened", "reinvestment_owner_action"),
    "commerce.orders_ingest": ("orders_created", "orders_reconciled", "customers_created",
                               "ledger_entries", "versions_recorded", "reconciliations"),
    "commerce.readings": ("acted",),
    "creative.benchmark_memory": ("judged_listings", "rewarded"),
    "creative.blind_review": ("returned_to_development", "counts.inferior",
                              "counts.not_inferior"),
    "creative.four_season": (),
    "creative.grid_tournament": ("pods", "concepts"),
    "creative.model_reference_pack": ("built",),
    "creative.north_star": ("improving", "regressing", "incident"),
    "creative.outcome_learning": ("concepts_with_outcomes",),
    "creative.style_learning": ("measured_styles", "promoted"),
    "creative.white_space": ("hypotheses", "complaints"),
    "creative.candidates_file": ("boards_filed", "registered"),
    "culture.sweep": ("recorded", "discovered", "placed", "routed", "demand_points"),
    "etsy.credential_health": ("findings",),
    "etsy.probe": ("ok",),
    "finance.accounting.cycle": ("posting.posted", "posting.reversed", "matching.matched",
                                 "posting_after_match.posted", "anomalies.findings",
                                 "anomalies.opened"),
    "finance.accounting.period_pack": ("work_done",),  # W3-D (wired by W3-WIRE4)
    "finance.challenge": ("challenges", "blocking"),
    "finance.escalation_check": ("required", "owner_action"),
    "finance.governor": ("paused", "incidents", "agents_spiking", "ceilings_changed"),
    "finance.reconcile": ("pl.gross_sales_cad", "pl.net_sales_cad", "pl.refunds_cad",
                          "pl.platform_fees_cad"),
    # W4-AUTO: a refusal with deterministic reasons is Product Truth doing its job (a defective
    # release blocked), not a no-op; repeats of the same refusal dedupe by fingerprint.
    "gate.certify": ("granted", "reasons"),
    # W4-AUTO: launch.plan was undeclared, so the generic counters never saw the dated plan
    # (and the publish/marketing hand-off) it produces for each certified release.
    "launch.plan": ("launch_on", "held", "withheld"),
    "gate.lanes": ("release_refused", "withdrawn", "testers_assigned"),
    "growth.conclude": ("concluded", "killed"),
    "growth.distribution": ("pins_ready", "pins_amplified", "clusters_buildable",
                            "video_modules", "video_stale_replanned", "creators_stopped",
                            "testers_graduated", "tools_hostable"),
    "growth.experiments": ("created",),
    "growth.journey": ("listings_audited", "friction_incidents", "proof_recorded",
                       "promotions"),
    "growth.preproduction": ("prepared", "acted_on"),
    "growth.steer": ("moved", "job_ids", "experiments_prioritised"),
    "improve.league": ("challengers_registered.registered", "compared", "promoted",
                       "rolled_back", "cards_closed", "owner_cards"),
    "improve.measure": ("measured",),
    "improve.mine": ("published", "regression_fixtures", "routed_to"),
    # ENG-LEARN: `promoted` is the standing count of promoted rows, not work this run did;
    # it made every idle sweep read as useful. Judging, reverting and trial judging are work.
    "improve.monitor": ("judged", "reverted", "rollback_proposals", "trial_monitoring.judged"),
    "improve.nightly": ("total_found",),
    "improve.retrospective": ("promotions_assessed", "returned", "regressed_promotions"),
    "improve.role_work": ("proposed", "kept"),
    "improve.sandbox": ("sandboxed", "tested", "approved", "promoted", "executed",
                        "rejected"),
    "improve.weekly": ("executed", "queued_for_authority", "added"),
    "intel.acceptance": ("passed",),
    "intel.benchmark_health": ("incidents_opened",),
    "intel.benchmark_refresh": ("triggers", "raised"),
    # OPUS2 (INTEG-LISTING-JOB): a listing package assembled or changed.
    "listing.package": ("work_done",),
    "intel.panel_discovery": ("joined", "scanned"),
    "intel.pod_learning": ("records", "judgements", "measured"),
    "laura.executive_tick": ("work_done",),  # W3-D (wired by W3-WIRE4)
    "launch.readiness": ("owner_actions_added", "owner_actions_closed"),
    "learn.scan": ("queued", "generated", "published"),
    "listing.draft": ("drafted",),
    "listing.outcomes": ("exports_processed", "recorded_listings"),  # W3 K3 via D (WIRE4)
    # OPUS2 (P0-PHOTO-ASSET-REVIEW): a photo frame approved by the deterministic review.
    "assets.photo_review": ("work_done",),
    "listing.seo": ("listing",),
    "marketing.ads_readiness": ("rechecked", "campaign_activated"),
    "marketing.schedule": ("pieces",),
    "mjs.seasonal_sentinel": ("incidents_opened", "queued", "reallocated"),
    "model.probe": ("ok",),
    "ops.provider_credentials": ("checked",),
    "ops.capability_probes": ("working",),
    "ops.capacity": ("reallocation.move",),
    "ops.continuity": ("retained.archive_id",),
    "ops.dependencies": ("opened", "resolved"),
    "ops.health": ("escalated", "recovered", "repaired_elsewhere", "must_escalate"),
    "ops.heartbeat": (),
    "ops.maturity_disagreements": ("opened", "resolved"),
    "ops.offsite_archive": ("ok",),
    "ops.policy_watch": ("changes_opened", "incidents_opened", "incidents_resolved",
                         "seeded"),
    "ops.provenance_backfill": ("backfilled",),
    "ops.queue_check": ("requeued", "recadenced"),
    "ops.sentinel": ("rebuild_enqueued", "publication_blocked"),
    "ops.slo": ("incidents.opened", "incidents.resolved", "incidents.restated"),
    "ops.thrash": ("tripped", "cancelled", "backoff.applied", "backoff.lifted"),
    "ops.daily_ledger": ("recorded",),
    "physical.upgrade_impact": ("upgrades", "measured"),
    "plan.cycle": ("planned",),
    "portfolio.review": ("actions",),
    "pricing.position": ("price_cad",),
    "radar.scan": ("selected",),
    "radar.score": ("score", "queued"),  # W4-B2CLOSE: a gap-queue run (no slug) fans out
    "scale.trajectory": ("constraint_changed",),
    "seasonal.engine": ("breakouts", "takeovers_planned", "fast_lane_admitted",
                        "trend_rows_stamped", "teams_disbanded", "scored_events"),
    "seasonal.harvest": ("measured",),
    "seasonal.remerchandising": ("ready_moves", "catalogue_growth", "derived"),
    "seasonal.sentinel": ("at_risk", "missed"),
    "seo.cycle": ("changed", "evidence_added", "proposals_written"),
    "support.triage": ("cases", "escalated", "triage.triaged", "triage.reply_jobs"),
    "swarm.allocate": ("backlog_batch", "spend_increase_cad"),
    "swarm.backlog": ("enqueued",),
    "swarm.orphans": ("reassigned", "incident_owners_assigned", "surfaced_as_incident"),
    "swarm.review": ("enacted", "retire", "merge"),
    "teardown.enforce": ("binding", "provisional", "blocked", "lessons"),
    "visual.identity_drift": ("gradual_drift", "incidents_opened"),
    "visual.rnd.cycle": ("work_done",),  # W3-D (wired by W3-WIRE4)
    # Capability-gated cadences: shadow/credential-less runs report `ran: false` (no-op);
    # these keys are what they report when the capability is open and they did the work.
    "assets.model_photography": ("made",),
    "assets.owned_photography": ("made", "attempted"),
    "assets.motif_backlog": ("work_done",),  # ENG-MOTIF-BACKLOG
    "creative.blinded": ("judged",),
    "creative.expedition": ("proposed", "survivors", "judged", "generated"),
    "creative.image_benchmark": ("winner", "locked"),
    "creative.model_tournament": ("finalists",),
    "creative.reference_reading": ("read", "decompositions_stored"),
    "creative.tournament": ("proposed", "survivors", "judged", "generated"),
    "etsy.listing_census": ("observed",),
    "etsy.shop_snapshot": ("failures", "incidents_opened"),
    # F-514: drift in a classified surface is work; a CURRENT re-verification is an honest
    # no-op (the audit row still records it).
    "etsy.openapi_reverify": ("affected",),
    # W4-STORE: live-vs-canonical drift read-back (stored readings only, writes_performed 0).
    "store.live_drift": ("findings", "proposals", "incidents_opened"),
    "store.draft_reconcile": ("resolved", "escalated"),
    "improve.replay": ("runs", "challengers_registered", "proposed", "retired"),
    "intel.gallery_analysis": ("judged",),
    "intel.serp_capture": ("captured",),
    "listing.search_visibility_watch": ("read_today", "card_raised"),
    "listing.taxonomy_refresh": ("new_snapshot",),
    "mjs.reviews": ("reviews_read",),
    # W4-MJS: findings synthesis counts only when a finding changed since the previous day's
    # `mjs.findings` reading (`findings.changed`); a re-publish of the same digest, or the
    # `{"error": ...}` a failed synthesis records, is not work.
    "mjs.scan": ("new", "reclassified", "inspected", "learning_domains", "findings.changed"),
    "ops.retention": ("removed",),
    # ENG-APPROVALS: work is an owner card moved under the standing authority.
    "ops.owner_queue_consolidate": ("work_done",),
    "plan.strategy": (),
    "seasonal.cycle_proof": ("complete", "assets_state"),
}


def _positive(value) -> bool:
    if value is None or isinstance(value, bool):
        return value is True
    if isinstance(value, (int, float)):
        return value > 0
    if isinstance(value, dict):
        return any(_positive(v) for v in value.values())
    if isinstance(value, (list, tuple, set)):
        return len(value) > 0
    if isinstance(value, str):
        return bool(value.strip()) and value.strip().lower() not in (
            "none", "unmeasured", "unknown", "no_evidence")
    return bool(value)


def _read(outputs: dict, key: str):
    cur = outputs
    for part in key.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def reported_no_work(outputs: dict) -> bool:
    """The narrow, pre-H-1 rule: the handler itself SAID nothing happened (`ran: false`, or
    `ran: true` with every legacy work counter zero). Used only by `ops.queue_check` to
    decide what to re-drive once per deploy -- a cost decision, deliberately narrower than
    the usefulness judge so an honest "nothing to do" does not re-run on every deploy."""
    if outputs.get("ran") is False:
        return True
    if outputs.get("ran") is not True:
        return False
    counters = [outputs.get(key) for key in WORK_COUNTERS[:14] if key in outputs]
    return bool(counters) and not any(counters)


def did_no_work(outputs: dict, job_type: str | None = None) -> bool:
    """True when a completed job did no useful work. THE judge (audit ddf9c6e H-1).

    Proxy is not measurement, so the default is "no work" unless the outputs show some:
      * empty outputs, `ran: false`, or `measurable: false` -> no work;
      * a handler may state it directly with `work_done` (a count; <= 0 is no work);
      * a job type declared in WORK_KEYS did work only when a declared key is positive;
      * an undeclared type did work only when a generic work counter is > 0 or it names a
        durable artefact it produced (DURABLE_KEYS).
    So `{"cases": 0}`, `{"checked": 0}`, `{"measurable": false}`, `{"products": 0, ...}`
    and a hardcoded `generated: 1` from a self-review (now removed) are all no-ops."""
    if not outputs:
        return True
    if outputs.get("ran") is False or outputs.get("measurable") is False:
        return True
    if "work_done" in outputs:
        return not _positive(outputs.get("work_done"))
    declared = WORK_KEYS.get(job_type) if job_type else None
    if declared is not None:
        return not any(_positive(_read(outputs, k)) for k in declared)
    if any(_positive(outputs.get(k)) for k in WORK_COUNTERS):
        return False
    if any(_positive(outputs.get(k)) for k in DURABLE_KEYS):
        return False
    return True


@handlers.register("ops.queue_check")
def handle_queue_check(ctx: JobContext) -> dict:
    """Re-drive what a deploy fixed: dead letters, and cadences that wrongly said "nothing".

    Two failure shapes, one bound. A dead letter caused by a defect is work the company still
    owes. And a cadence that *completed* reporting nothing to do is the same debt wearing a
    success: the weekly discovery run reported "no proven-and-unserved arena is observed"
    against a matrix holding twenty-seven of them, because a reader had the wrong key. It
    consumed its window, so without this it would sit idle for seven days after the fix, and
    the dead-letter re-drive cannot help because the job did not fail.

    The fix for a defect is a deploy, so a deploy is the event that retries it -- once. A
    commit that did not fix it produces the same no-op or the same failure and waits for the
    next one, which is what stops this being a loop. A cadence whose last run *succeeded*
    with real work is never re-enqueued, so a run that costs money costs it once.

    Deliberate refusals are never re-driven: `requeue_dead` skips anything whose error carries
    a refusal marker, so Shadow Mode's publication refusals stay refused.
    """
    from sqlalchemy import desc, select

    from ..core import build
    from ..core.models import AuditLog, Job
    from ..queue.durable import DuplicateJob
    from .worker import CADENCES

    dead = ctx.queue.dead_letters()
    if dead:
        ctx.audit("ops.dead_letters_present", detail={"ids": [d.id for d in dead][:20]})

    here = build.commit() or "unknown"
    if here == "unknown":
        return {"dead_letters": len(dead), "requeued": 0, "recadenced": 0,
                "reason": ("the deployed commit is unknown, so 'once per deploy' has no "
                           "meaning and a retry here would be an unbounded loop")}

    with ctx.db.session() as s:
        seen = list(s.scalars(
            select(AuditLog).where(AuditLog.action == "ops.requeued_for_commit")
            .order_by(desc(AuditLog.id)).limit(20)))
    if any((row.detail or {}).get("commit") == here for row in seen):
        return {"dead_letters": len(dead), "requeued": 0, "recadenced": 0,
                "reason": "this commit has already re-driven them"}

    requeued: list[int] = []
    if dead:
        result = ctx.queue.requeue_dead(
            job_types=sorted({j.job_type for j in dead if j.job_type != "store.publish"}))
        requeued = list(result.get("requeued") or [])

    # The no-op half. Only the last attempt matters: a cadence that has since run properly
    # is finished with, and one still reporting nothing gets exactly one more chance.
    recadenced: list[str] = []
    with ctx.db.session() as s:
        for name, agent, job_type, _period in CADENCES:
            last = list(s.scalars(select(Job).where(Job.job_type == job_type)
                                  .order_by(desc(Job.id)).limit(1)))
            if not last:
                continue
            if reported_no_work(last[0].outputs or {}):
                recadenced.append(name)

    for name, agent, job_type, _period in CADENCES:
        if name not in recadenced:
            continue
        try:
            ctx.enqueue(agent, job_type, {"cadence": name, "retry_for_commit": here},
                        idempotency_key=f"cadence:{name}:retry:{here}")
        except DuplicateJob:
            continue

    ctx.audit("ops.requeued_for_commit",
              detail={"commit": here, "requeued": requeued, "recadenced": recadenced})
    return {"dead_letters": len(dead), "requeued": len(requeued),
            "recadenced": len(recadenced), "cadences": recadenced, "commit": here}


@handlers.register("plan.cycle")
def handle_plan_cycle(ctx: JobContext) -> dict:
    """One planning cycle: re-run the radar over the whole pool and re-select the portfolio.

    Re-running rather than freezing matters. The pool does not change often, but the date
    does, and a concept that was three weeks early last month is in its window this month.
    """
    today = _scan_date(ctx)
    ctx.enqueue("market_radar", "radar.scan",
                {"target": 10, "as_of": today.isoformat()},
                idempotency_key=f"radar.scan:{today.isoformat()}")
    return {"planned": True, "as_of": today.isoformat()}


@handlers.register("portfolio.review")
def handle_portfolio_review(ctx: JobContext) -> dict:
    """Classify every SKU and say what to do next (section 12).

    Two questions, answered separately. Which products *should* exist, which is the radar's
    portfolio re-run against today's calendar; and how the products that *do* exist are
    actually performing, which is section 12's classification.

    The second question currently has no evidence behind it, and the classifier says so rather
    than guessing. Every SKU has zero impressions, and a system that read that as
    "underperforming" would retire a catalogue nobody has been shown.
    """
    from sqlalchemy import select

    from ..core.models import Incident, PortfolioReview, SupportCase
    from ..growth.portfolio import SkuMetrics, review_portfolio

    today = _scan_date_utc(ctx)
    portfolio = select_portfolio(today=today)
    should_exist = {c.slug for c in portfolio.selected}

    with ctx.db.session() as s:
        products = list(s.scalars(select(Product)))
        built = {p.slug for p in products}
        cases: dict[str, int] = {}
        for case in s.scalars(select(SupportCase)):
            if case.product_slug:
                cases[case.product_slug] = cases.get(case.product_slug, 0) + 1
        p1: dict[str, int] = {}
        for inc in s.scalars(select(Incident).where(Incident.resolved == False)):  # noqa: E712
            if inc.product_slug and inc.severity in ("P0", "P1"):
                p1[inc.product_slug] = p1.get(inc.product_slug, 0) + 1

    # #47 (C-64): impressions, clicks (visits), favourites and orders are read from the rows
    # that record them -- listing outcomes and ingested orders -- so the ladder diagnoses the
    # stage that is failing the day there is exposure, and says NO_EVIDENCE only while there
    # is none. Days live are counted from the product's published listing.
    from datetime import datetime, timezone

    from ..core.models import Listing, ListingOutcome, Order

    with ctx.db.session() as s:
        exposure: dict[str, dict] = {}
        for r in s.scalars(select(ListingOutcome)):
            e = exposure.setdefault(r.product_slug, {"impressions": 0, "clicks": 0,
                                                     "favourites": 0})
            e["impressions"] += int(r.impressions or 0)
            e["clicks"] += int(r.visits or 0)
            e["favourites"] += int(r.favourites or 0)
        sold: dict[str, dict] = {}
        from ..commerce import orders_ingest as _oi

        _held = _oi.held_refs(s)
        for o in _oi.booked_orders(s):  # rc1-ORD2: unreconciled/held orders move nothing
            x = sold.setdefault(o.product_slug, {"orders": 0, "revenue": 0.0, "refunds": 0})
            if not _oi.countable(o, _held):
                x["refunds"] += 1
            else:
                x["orders"] += 1
                x["revenue"] += float(o.revenue_cad or 0.0)
        live_since: dict[str, datetime] = {}
        from ..core.listing_state import LIVE_ON_ETSY

        for r in s.scalars(select(Listing).where(Listing.state.in_(LIVE_ON_ETSY))):
            at = r.created_at if r.created_at.tzinfo else r.created_at.replace(
                tzinfo=timezone.utc)
            if r.product_slug not in live_since or at < live_since[r.product_slug]:
                live_since[r.product_slug] = at
    now = datetime(today.year, today.month, today.day, tzinfo=timezone.utc)
    metrics = [SkuMetrics(slug=p.slug, support_cases=cases.get(p.slug, 0),
                          open_p1_incidents=p1.get(p.slug, 0),
                          impressions=exposure.get(p.slug, {}).get("impressions", 0),
                          clicks=exposure.get(p.slug, {}).get("clicks", 0),
                          favourites=exposure.get(p.slug, {}).get("favourites", 0),
                          orders=sold.get(p.slug, {}).get("orders", 0),
                          revenue_cad=round(sold.get(p.slug, {}).get("revenue", 0.0), 2),
                          refunds=sold.get(p.slug, {}).get("refunds", 0),
                          days_live=(max(0, (now - live_since[p.slug]).days)
                                     if p.slug in live_since else 0))
               for p in products]
    verdict = review_portfolio(metrics, today=today)

    # #13 (C-64): a design is never retired or reworked on one offer's evidence. Every
    # discard-shaped verdict consults `offers.may_retire` over the offers the orders show it
    # has worn; a refusal replaces the discard with the cheapest untried offer.
    from ..commerce import offers as offers_mod
    from ..commerce.order_readings import offer_results
    from ..growth.portfolio import APPEAL_PROBLEM, LADDERS, OFFER_UNTESTED, RETIRE, REWORK

    results = offer_results(ctx.db)
    offer_guard = []
    for c in verdict.classifications:
        if c.label not in (RETIRE, REWORK, APPEAL_PROBLEM):
            continue
        ruling = offers_mod.may_retire(c.slug, [r for r in results
                                                if r.design_slug == c.slug])
        offer_guard.append({"slug": c.slug, "label": c.label, **ruling})
        if not ruling["may_retire"]:
            # The refusal changes the classification itself, not only its prose (CB2-O08):
            # a design the guard protects is not RETIRE/REWORK/APPEAL_PROBLEM in the stored
            # review or its summary, so nothing that reads the label can discard it. Its
            # ladder is the offer ladder; the discard-shaped verdict is kept as evidence.
            nxt = (ruling.get("try_next") or {}).get("offer")
            c.evidence["offer_guard"] = ruling["reasons"]
            c.evidence["discard_verdict_withheld"] = c.label
            c.label = OFFER_UNTESTED
            c.reason = (f"{c.evidence['discard_verdict_withheld']} withheld: {c.reason}. "
                        f"The design has worn too few offer families for the verdict to be "
                        f"about the design")
            c.interventions = ([f"fix the offer before discarding the design: try {nxt}"
                                if nxt else "fix the offer before discarding the design"]
                               + list(LADDERS[OFFER_UNTESTED]))
            verdict.actions.append(
                f"{c.slug}: {c.evidence['discard_verdict_withheld']} is a verdict about an "
                f"offer until it has worn {offers_mod.MIN_OFFER_FAMILIES_BEFORE_RETIRING} "
                f"offer families -- {'try ' + nxt if nxt else 'fix the offer'} before "
                f"discarding it (#13).")

    missing = sorted(should_exist - built)
    off_portfolio = sorted(built - should_exist)

    with ctx.db.session() as s:
        review_row = PortfolioReview(as_of=today.isoformat(),
                                     classifications=verdict.summary(),
                                     actions=list(verdict.actions),
                                     evidence_available=verdict.evidence_available)
        s.add(review_row)
        s.flush()
        review_id = review_row.id
    # P0-PORTFOLIO-ACT: the final labels (after the offer guard) become bounded, keyed work.
    from ..growth import portfolio_act

    # Review ee5dbeee N5: the review row is already committed, so a failure while acting must
    # not fail (and on retry duplicate) the classification. It is audited and reported.
    try:
        acted = portfolio_act.act(ctx, verdict.classifications, today=today,
                                  review_id=review_id)
    except Exception as exc:  # noqa: BLE001
        acted = {"week": portfolio_act.week_of(today), "review_id": review_id, "acted": [],
                 "skipped": [], "capped": [],
                 "error": f"{type(exc).__name__}: {exc}"[:500]}
        ctx.audit(portfolio_act.ACT_FAILED, detail=acted)

    ctx.audit("portfolio.reviewed", detail={
        "as_of": today.isoformat(),
        "in_portfolio": len(should_exist),
        "built": len(built),
        "missing": missing[:20],
        "off_portfolio": off_portfolio[:20],
        "constraints_met": portfolio.constraints_met,
        "classifications": verdict.summary(),
        "classifications_detail": [c.to_dict() for c in verdict.classifications],
        "evidence_available": verdict.evidence_available,
        "offer_guard": offer_guard,
        "exposure_read": {"listing_outcomes": sum(1 for m in metrics if m.impressions),
                          "selling": sum(1 for m in metrics if m.orders)},
    })
    for slug in missing:
        ctx.enqueue("market_radar", "radar.score",
                    next(c.to_dict() for c in portfolio.selected if c.slug == slug),
                    idempotency_key=f"score:{slug}:{today.isoformat()}")

    return {"as_of": today.isoformat(), "missing": missing,
            "off_portfolio": off_portfolio,
            "constraints_met": portfolio.constraints_met,
            "classifications": verdict.summary(),
            "evidence_available": verdict.evidence_available,
            "actions": verdict.actions, "offer_guard": offer_guard,
            "acted": {k: acted[k] for k in ("week", "acted", "skipped", "capped", "error")
                      if k in acted}}


@handlers.register("finance.reconcile")
def handle_finance_reconcile(ctx: JobContext) -> dict:
    """The books, section 15's full list, from observed entries only.

    Reports zero revenue because revenue is zero. Building the accounting before there is
    anything to flatter is the point: a P&L that first appears alongside the first sale is a
    P&L nobody has checked.
    """
    from sqlalchemy import select

    from ..core.models import Listing, PatternVersion
    from ..finance.books import Books

    books = Books(ctx.db)
    pl = books.profit_and_loss()

    with ctx.db.session() as s:
        validated = s.scalar(select(func.count()).select_from(PatternVersion).where(
            PatternVersion.certified == True)) or 0  # noqa: E712
        listings = s.scalar(select(func.count()).select_from(Listing)) or 0

    economics = books.unit_economics(products_validated=validated, listings_drafted=listings)
    ctx.audit("finance.reconciled", detail={"pl": pl.to_dict(), "unit": economics})
    ctx.enqueue("cfo", "finance.challenge", {}, idempotency_key=None)
    return {"pl": pl.to_dict(), "unit_economics": economics}


@handlers.register("finance.challenge")
def handle_finance_challenge(ctx: JobContext) -> dict:
    """The CFO/Skeptic (section 14), as a function rather than a personality.

    It reports concerns even when everything is nominally fine, because a reviewer who only
    speaks up during a crisis is a reviewer nobody has calibrated.
    """
    from sqlalchemy import select

    from ..core.models import SpendLimit
    from ..finance.books import Books, cfo_challenge, trajectory
    from ..finance.spend_policy import INFRA_CEILING_CAD, INFRA_MONTHLY_CAD

    # Declared by the owner, not observed from a bill: `spend_policy.INFRA_BASIS` says so.
    infra = float(ctx.job.inputs.get("infra_monthly_cad", INFRA_MONTHLY_CAD))
    ceiling = float(ctx.job.inputs.get("infra_ceiling_cad", INFRA_CEILING_CAD))

    books = Books(ctx.db)
    pl = books.profit_and_loss()
    with ctx.db.session() as s:
        limits = list(s.scalars(select(SpendLimit)))

    challenges = cfo_challenge(pl, limits=limits, infra_monthly_cad=infra,
                               infra_ceiling_cad=ceiling)
    blocks = [c for c in challenges if c.severity == "block"]
    ctx.audit("finance.challenged", detail={
        "challenges": [c.to_dict() for c in challenges],
        "blocking": len(blocks)})
    return {"challenges": [c.to_dict() for c in challenges],
            "blocking": len(blocks),
            "trajectory": trajectory(pl)}


@handlers.register("finance.escalation_check")
def handle_finance_escalation_check(ctx: JobContext) -> dict:
    """Tell the owner at four-fifths of the month, as a job rather than as a page.

    `spend_policy.escalation` carried the six fields the owner asked for and was computed in
    exactly one place: the GET handler for /api/spend-report. An escalation that exists only
    when somebody fetches it is a report, not an escalation -- a month that reached 80% with
    nobody looking reached the first refusal with nobody told, which is the outcome the
    policy's "approaching the ceiling is a report, never a quiet downgrade" exists to
    prevent.

    One owner action per calendar month, keyed `spend.ceiling.<YYYY-MM>`. A rerun in the same
    month restates the figures on the open row rather than adding a second; a row the owner
    has already closed is left closed, because "done" is their decision and not this job's to
    re-open. Under the line it writes nothing but the audit of having looked.

    `as_of` in the inputs pins the instant for a deterministic run; production passes none.
    """
    from datetime import datetime, timezone

    from sqlalchemy import select

    from ..core.models import OwnerAction
    from ..finance import spend_policy

    raw = ctx.job.inputs.get("as_of")
    now = datetime.fromisoformat(raw) if raw else datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    report = spend_policy.escalation(ctx.db, now=now)
    key = spend_policy.escalation_key(now)
    result = {"as_of": now.isoformat(), "required": bool(report["required"]),
              "share_of_ceiling": report.get("share_of_ceiling", report.get("share")),
              "requirement_key": key, "owner_action": None}

    if not report["required"]:
        ctx.audit("finance.escalation_checked", detail={**result, "why": report.get("why")})
        return result

    fields = spend_policy.owner_action_fields(report)
    with ctx.db.session() as s:
        existing = s.scalar(select(OwnerAction).where(OwnerAction.requirement_key == key))
        if existing is None:
            s.add(OwnerAction(requirement_key=key, **fields))
            result["owner_action"] = "queued"
        elif existing.done:
            result["owner_action"] = "already_decided"
        else:
            for name, value in fields.items():
                setattr(existing, name, value)
            result["owner_action"] = "restated"

    ctx.audit("finance.escalation_checked", detail={
        **result, "current_spend_cad": report["current_spend_cad"],
        "ceiling_cad": report["ceiling_cad"],
        "proposed_ceiling_cad": report["proposed_ceiling_cad"],
        "what_is_constrained": report["what_is_constrained"]})
    return result


@handlers.register("plan.strategy")
def handle_plan_strategy(ctx: JobContext) -> dict:
    """Monthly strategy recalibration and CA$100K trajectory (section 13).

    Deliberately produces a refusal today rather than a forecast: with no orders there is no
    run rate, and the CA$100K figure is the one most likely to be quoted back as though it
    were a projection.
    """
    from ..finance.books import Books, trajectory

    today = _scan_date(ctx)
    pl = Books(ctx.db).profit_and_loss()
    traj = trajectory(pl, today=today)
    portfolio = select_portfolio(today=today)

    ctx.audit("plan.strategy_reviewed", detail={
        "as_of": today.isoformat(),
        "trajectory": traj,
        "portfolio_size": len(portfolio.selected),
        "constraints_met": portfolio.constraints_met})
    ctx.enqueue("orchestrator", "portfolio.review", {"as_of": today.isoformat()},
                idempotency_key=f"portfolio.review:{today.isoformat()}")
    return {"as_of": today.isoformat(), "trajectory": traj,
            "is_forecast": traj["is_forecast"]}




# Importing the back half registers its handlers. Kept at the bottom because `release` imports
# job-context helpers from this module's neighbours, and a top-of-file import would be a cycle.
from . import release  # noqa: E402,F401
from . import commerce_readings  # noqa: E402,F401  (C-59: gated machinery, run daily)
from . import orders  # noqa: E402,F401  (C-64: order ingest and everything that reads orders)
from . import growth_ops  # noqa: E402,F401  (C-60: growth, ads, journey, steer)
from . import etsy_ops  # noqa: E402,F401  (FB-1 B: Etsy read-back, census, shop snapshot)
from . import ops_watch  # noqa: E402,F401  (FB-4: F-125 maturity disagreements cadence)
from . import storefront_watch  # noqa: E402,F401  (F-280: launch-week Search Visibility)
from . import storefront_ops  # noqa: E402,F401  (W4-AGENTS: Storefront Director)
from . import quality_ops  # noqa: E402,F401  (W4-AGENTS: Quality & Compliance re-verification)
from . import engineering_ops  # noqa: E402,F401  (W4-AGENTS: cir.revise)
from . import intel_ops  # noqa: E402,F401  (W4-AGENTS: radar.competitor_snapshot)
from . import photo_review_ops  # noqa: E402,F401  (OPUS2: assets.photo_review)
from . import listing_package_ops  # noqa: E402,F401  (OPUS2: listing.package)
from . import motif_backlog_ops  # noqa: E402,F401  (ENG-MOTIF-BACKLOG: assets.motif_backlog)
from . import c12_ops  # noqa: E402,F401  (W4-C12 wiring: SV aging, window captures, harvest)
from . import commercial_ops  # noqa: E402,F401  (OPUS2-P0: improve.commercial_lessons)
from . import learning_ops  # noqa: E402,F401  (ENG-LEARN: learning.loops)
from . import learning_gaps_ops  # noqa: E402,F401  (OPUS2-P0: learning.knowledge_gaps)
from . import evidence_ops  # noqa: E402,F401  (OPUS2-P0: intel.scan_evidence)
from . import standing_policy_ops  # noqa: E402,F401  (WS4-5: policy.issuer_shadow)
from . import owner_queue_ops  # noqa: E402,F401  (ENG-APPROVALS: ops.owner_queue_consolidate)


def _listing_parity(ctx: JobContext) -> dict:
    """#75 for the listing this job would export, from evidence already on file.

    Never renders and never asks a model anything: every dimension is a reading of an
    asset record that exists, or `unjudged`. The benchmark comparison is passed through
    when one has been made and left absent when none has -- assuming this company compares
    well beside MJs is the one answer nobody has evidence for.
    """
    from ..publish import listing_asset
    from ..visual import parity

    slug = ctx.job.inputs.get("slug", "")
    version = ctx.job.inputs.get("version", "1.0.0")
    frames = listing_asset.frames_for(ctx.db, slug=slug)
    # #81: the deterministic rung is available when a certified CIR exists to render the
    # chart and twin from -- which is what `assets.build` does, free and truthful.
    deterministic = _certified_release(ctx.db, slug, version)
    try:
        from ..visual.gallery import escalation_progress, gates_now

        # C-80 defect 8 (Codex P11): the ladder resumes from the rung results the
        # photography job persisted, so change_composition and change_tool are reached.
        progress = escalation_progress(ctx.db, slug=slug, version=version)
        verdict = parity.assess(frames, benchmark_quality=_benchmark_quality(ctx.db, slug),
                                deterministic_available=(
                                    deterministic is not None
                                    or parity._deterministic_available(frames)),
                                gate_open=gates_now(ctx.db),
                                start_attempt=progress["start_attempt"])
        if verdict.get("escalation") is not None:
            verdict["escalation"]["rung_results"] = progress["results"]
    except parity.ParityRefused as exc:
        # A partial set cannot satisfy #75, and the refusal is the gate working. Reported
        # as blocking rather than raised, so the publish attempt records why.
        return {"verdict": parity.UNJUDGED, "blocks_release": True,
                "why": str(exc)[:300], "dimensions": {}, "slug": slug}
    verdict = {**verdict, "slug": slug, "frames_judged": len(frames)}

    # #81: a ladder that is only recorded is a plan nobody executes. When the deterministic
    # rung is taken, the render it names is enqueued -- once per failure and evidence state,
    # so a refused publish retried on the same evidence does not queue it again. Gated rungs
    # (generation, physical proof) are never started from here, and release stays blocked
    # until parity passes on the new frames.
    escalation = verdict.get("escalation") or {}
    if escalation.get("taken") in ("regenerate_constrained", "change_composition",
                                   "change_tool"):
        # C-69 (#81): the image gate is open, so the first rung is attempted: the product's
        # own photography job, carrying the failure as its brief. That job budget-checks,
        # reserves and gates itself; nothing here spends.
        import hashlib

        from ..products.builder import for_slug

        cir_ = for_slug(slug)
        job_type = ("assets.model_photography"
                    if cir_ is not None and listing_asset.needs_the_model(cir_)
                    else "assets.owned_photography")
        state = hashlib.sha256(repr(sorted(verdict.get("failed") or [])).encode()
                               ).hexdigest()[:12]
        job = ctx.enqueue("publishing", job_type,
                          {"slug": slug, "version": version,
                           "reason": f"parity_escalation:{escalation['taken']}",
                           "rung": escalation["taken"], "failed": verdict.get("failed")},
                          idempotency_key=f"parity-rung:{slug}:{escalation['taken']}:{state}")
        escalation["enqueued"] = {"job_type": job_type, "job_id": getattr(job, "id", None),
                                  "already_queued": job is None}
        ctx.audit("creative.escalation_taken", artifact=f"{slug}@{version}",
                  detail={"failed": verdict.get("failed"), "rung": escalation["taken"],
                          **escalation["enqueued"]})
    if escalation.get("taken") == "deterministic_representation" and deterministic:
        import hashlib

        from .release import chain_key

        release = ctx.job.inputs.get("release") or (
            deterministic if deterministic != "certified" else "")
        state = hashlib.sha256(repr((sorted(verdict.get("failed") or []), sorted(
            str(f.get("image_ref") or f.get("image") or "") for f in frames))).encode()
        ).hexdigest()[:16]
        token = f"parity-escalation:{state}"
        job = ctx.enqueue("publishing", "assets.build",
                          {"slug": slug, "version": version, "release": release,
                           "rebuild": token},
                          idempotency_key=chain_key("assets", slug, version, release, token))
        escalation["enqueued"] = {"job_type": "assets.build", "rebuild": token,
                                  "job_id": getattr(job, "id", None),
                                  "already_queued": job is None}
        ctx.audit("creative.escalation_taken", artifact=f"{slug}@{version}",
                  detail={"failed": verdict.get("failed"), "rung": escalation["taken"],
                          **escalation["enqueued"]})

    # #61 (C-69): every listing frame must have been independently reviewed and cleared.
    # Unreviewed (the vision gate is closed) is not a pass.
    from .release import frame_review_state

    review = frame_review_state(ctx.db, slug, version)
    verdict["frame_review"] = review
    if not review["reviewed"]:
        verdict["blocks_release"] = True
        verdict["why"] = f"{verdict['why']}; {review['why']}"
    # W4-DISCLOSEDQA: a disclosed listing uploads its certified set, not the stored frames,
    # so #61 must also have reviewed exactly those (`visual.exported_review`). Tightens only.
    from ..visual import exported_review

    exported = exported_review.review_state(ctx.db, slug, version)
    verdict["exported_frame_review"] = exported
    if not exported["reviewed"]:
        verdict["blocks_release"] = True
        verdict["why"] = f"{verdict['why']}; {exported['why']}"

    # #41 re-checked at publish: an owed purchase disclosure missing from the stored copy
    # blocks export, whatever parity says. UNMEASURED (no copy) is reported; publication
    # itself refuses a listing that was never drafted.
    from ..commerce.buyer_trust import listing_disclosure_finding

    disclosure = listing_disclosure_finding(ctx.db, slug=slug, version=version)
    verdict["disclosures"] = disclosure
    if disclosure.get("finding"):
        verdict["blocks_release"] = True
        missing = [m["disclosure"] for m in disclosure.get("missing", [])] + [
            m["disclosure"] for m in disclosure.get("misplaced", [])]
        verdict["why"] = (f"{verdict['why']}; listing disclosures (#41) missing or "
                          f"misplaced: {missing}")

    # #35 re-checked at publish: the release must have been classified when its listing was
    # written, with no refused asset and its class enabled against a current policy reading.
    classified = _release_classification(ctx.db, slug, version)
    verdict["classification"] = classified
    if not classified.get("ok"):
        verdict["blocks_release"] = True
        verdict["why"] = f"{verdict['why']}; Etsy creativity/AI classification (#35): " \
                         f"{classified.get('why')}"
    return verdict


def _release_classification(db, slug: str, version: str) -> dict:
    """The newest `listing.classified` row for this release, read as a publish condition."""
    from sqlalchemy import desc, select

    from ..core.models import AuditLog
    from ..gates import platform_policy

    with db.session() as s:
        row = s.scalar(select(AuditLog).where(
            AuditLog.action == platform_policy.CLASSIFIED_ACTION,
            AuditLog.artifact == f"{slug}@{version}").order_by(desc(AuditLog.id)).limit(1))
        detail = dict(row.detail or {}) if row is not None else None
    if detail is None:
        return {"ok": False, "reading": "UNMEASURED",
                "why": "this release was never classified, so its disclosures are unknown"}
    problems = list(detail.get("problems") or [])
    enabled = (detail.get("class_enablement") or {}).get("enabled")
    if problems:
        return {"ok": False, "why": f"classification refused assets: {problems[:3]}",
                "audit": detail}
    if not enabled:
        return {"ok": False, "why": ("the product class was not enabled against a current "
                                     "policy reading: "
                                     + str((detail.get("class_enablement") or {}).get("why"))[:300]),
                "audit": {k: detail.get(k) for k in ("classification", "class_enablement")}}
    return {"ok": True, "why": "classified, disclosures generated, class enabled",
            "disclosures": (detail.get("classification") or {}).get("disclosures")}


def _certified_release(db, slug: str, version: str) -> str | None:
    """The release hash of a certified version of this product, or None."""
    from sqlalchemy import select

    from ..core.models import PatternVersion, Product

    with db.session() as s:
        row = s.scalar(select(PatternVersion).join(Product, Product.id == PatternVersion.product_id)
                       .where(Product.slug == slug, PatternVersion.version == version,
                              PatternVersion.certified.is_(True)))
        return (row.release_hash or "certified") if row is not None else None


def _benchmark_quality(db, slug: str) -> dict | None:
    """The blind comparison against observed benchmark listings, if one has been made.

    None rather than a favourable default. `parity` reads the absence as `unjudged`, which
    blocks -- which is correct: #75 asks for a comparison, and a comparison nobody made is
    not a comparison that went well.
    """
    # C-45: this product's own newest row, filtered in the query, and only while current.
    # It read the newest ten rows of any product, so with eleven in the catalogue one was
    # permanently unjudged, and a months-old verdict counted as today's.
    from ..creative import blind_review

    return blind_review.current_review(db, slug=slug)

from ..learn import runtime as learn_runtime  # noqa: E402,F401; Learn launch scanner


# v1.1 lane A: the company loop's own handlers (autonomy.orchestrate, autonomy.department_review,
# autonomy.morning_handoff). Imported here because this module is the one every runtime entry
# point (runner, worker_entry) imports to register handlers.
from ..autonomy import handlers as _autonomy_handlers  # noqa: E402,F401
# v1.1 integrator wiring: seo.cycle (G), finance.accounting.cycle (E), ops.slo (I) and
# marketing.ads_readiness (H).
from . import v11_wiring as _v11_wiring  # noqa: E402,F401
