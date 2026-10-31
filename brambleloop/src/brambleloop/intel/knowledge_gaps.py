"""OPUS2-P0: P0-LEARNING-GAPS -- what the studio cannot yet make well, and which purchase would teach it.

Owner directive 2026-10-31 (§3 items 17-18, §4): the Learning Department identifies knowledge
gaps and recommends future reference purchases, and the shortlist is driven by Brambleloop's
intended product lines, demonstrated technical gaps and library coverage -- never by
collecting random patterns. `intel.benchmark_refresh` already recommends a purchase when the
*market* moves; this module recommends one when *our own capability* is the gap.

A gap is one of the owner's intended product lines, described only by counted evidence:

- ``certified``         -- certified releases in the line (zero is the gap itself);
- ``construction_refusals`` -- `cir.draft_refused` rows whose gate is ``construction``: a
  concept in this line reached drafting and no deterministic rule could make it
  (`creative.fallback_constructions`);
- ``compile_failures``  -- `cir.compiled` rows with ``ok: False`` for this line's products;
- ``library``           -- purchased `BenchmarkProduct` rows in the line's pod.

The score is the sum of those counts with a fixed weight each, so a reviewer can recompute
it by hand. A gap the library already covers is recorded as "covered; learning pending" and
never asks for another purchase (duplicate information, #166). For the highest uncovered gaps
-- at most `MAX_OPEN` open at once -- one owner action names the single listing
`purchase_selection` would buy for that pod and its observed price as the maximum cost. No
observed listing means no request: the owner is never asked to go and find one.

Nothing here buys anything, calls a model or the network, or spends: purchasing is the owner's
consequential spend. With no evidence it records the gaps it can count and raises nothing.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

KIND = "learning.knowledge_gaps"
ACTION_PREFIX = "knowledge_gap:"
MAX_OPEN = 2
WINDOW_DAYS = 30

# Fixed weights: an empty product line is the strongest signal, then a concept we could not
# draft at all, then one we drafted wrong.
W_NO_CERTIFIED = 3
W_REFUSAL = 1
W_COMPILE_FAIL = 1
CAP_REFUSALS = 3
CAP_COMPILE_FAILS = 2


@dataclass(frozen=True)
class Line:
    key: str
    label: str
    pod: str                       # intel.pods key a benchmark for this line is filed under
    categories: frozenset[str]     # catalogue categories that belong to the line
    teaches: str                   # what a reference in this line would teach


# The owner's intended product lines (directive §5), in the owner's order.
LINES: tuple[Line, ...] = (
    Line("womens_garments", "women's clothing", "garments", frozenset({"garment"}),
         "graded sizing, schematics and fit ease"),
    Line("cardigans_sweaters", "cardigans and sweaters", "garments",
         frozenset({"cardigan", "sweater"}),
         "panel and yoke construction, button bands, grading across sizes"),
    Line("shawls_accessories", "shawls and accessories", "garments",
         frozenset({"shawl", "scarf", "accessory"}),
         "triangle and crescent increase placement, edging and blocking"),
    Line("blankets_throws", "blankets and throws", "blankets",
         frozenset({"blanket", "mosaic_blanket"}),
         "border finishing, large-chart layout and yardage per size"),
    Line("baby_nursery", "baby and nursery", "blankets", frozenset({"baby", "nursery"}),
         "safety-led construction and small-piece assembly"),
    Line("baskets_storage", "baskets and home storage", "bags", frozenset({"basket"}),
         "base-to-wall transitions and structure without stiffeners"),
    Line("home_decor", "home decor", "home_decor",
         frozenset({"pillow", "wall_decor", "runner", "placemat", "coaster", "flower"}),
         "closures, mounting and flat-piece finishing"),
    Line("seasonal", "seasonal collections", "seasonal_gift",
         frozenset({"seasonal_decor", "ornament", "stocking"}),
         "small closed shapes, hanging loops and coordinated sets"),
    Line("amigurumi", "amigurumi", "amigurumi", frozenset({"amigurumi", "toy"}),
         "shaping in the round, stuffing, safe joins and face placement"),
    Line("bags", "bags", "bags", frozenset({"bag"}),
         "strap joins, load-bearing fabric and linings"),
    Line("pet", "pet products", "home_decor", frozenset({"pet"}),
         "durable fabric and washable construction"),
    Line("advanced_chart", "advanced stitch and chart projects", "blankets",
         frozenset({"graphghan"}),
         "chart legibility, colour-change management and stitch-pattern notation"),
)

LINE_BY_CATEGORY: dict[str, str] = {c: ln.key for ln in LINES for c in ln.categories}


def category_of(slug: str) -> str:
    """A product's catalogue category: its radar seed's, else where the imagery reads it."""
    from ..runtime import pipeline

    seed = pipeline.product_seed(slug)
    if seed is not None:
        return seed.category
    try:
        from ..visual.laura_home import category_of_slug

        return category_of_slug(slug) or ""
    except Exception:  # noqa: BLE001 - an unknown slug has no category, not a crash
        return ""


def _slug_of(artifact: str | None) -> str:
    return (artifact or "").split("@", 1)[0]


def evidence(db, *, today: date) -> dict:
    """Counted evidence per line. Reads this database only."""
    from sqlalchemy import select

    from ..core.models import AuditLog, BenchmarkProduct, PatternVersion, Product

    since = datetime.combine(today - timedelta(days=WINDOW_DAYS), datetime.min.time(),
                             tzinfo=timezone.utc)
    per = {ln.key: {"certified": 0, "certified_slugs": [], "construction_refusals": 0,
                    "refused": [], "needs": [], "compile_failures": 0, "library": 0}
           for ln in LINES}
    with db.session() as s:
        certified = {p.slug for p, _ in s.execute(
            select(Product, PatternVersion).join(PatternVersion,
                                                 PatternVersion.product_id == Product.id)
            .where(PatternVersion.certified == True))}  # noqa: E712
        refusals = [(r.artifact, dict(r.detail or {})) for r in s.scalars(
            select(AuditLog).where(AuditLog.action == "cir.draft_refused",
                                   AuditLog.at >= since))]
        failures = [r.artifact for r in s.scalars(
            select(AuditLog).where(AuditLog.action == "cir.compiled", AuditLog.at >= since))
            if (r.detail or {}).get("ok") is False]
        library = [b.pod for b in s.scalars(select(BenchmarkProduct)) if b.pod]
    for slug in sorted(certified):
        line = LINE_BY_CATEGORY.get(category_of(slug))
        if line:
            per[line]["certified"] += 1
            per[line]["certified_slugs"].append(slug)
    for artifact, detail in refusals:
        if detail.get("gate") != "construction":
            continue
        slug = _slug_of(artifact)
        line = LINE_BY_CATEGORY.get(str(detail.get("category") or "") or category_of(slug))
        if line:
            per[line]["construction_refusals"] += 1
            if slug not in per[line]["refused"]:
                per[line]["refused"].append(slug)
            need = str(detail.get("needs") or "")
            if need and need not in per[line]["needs"]:
                per[line]["needs"].append(need)
    for artifact in failures:
        line = LINE_BY_CATEGORY.get(category_of(_slug_of(artifact)))
        if line:
            per[line]["compile_failures"] += 1
    for ln in LINES:
        per[ln.key]["library"] = sum(1 for pod in library if pod == ln.pod)
    return per


def score(ev: dict) -> int:
    return ((W_NO_CERTIFIED if ev["certified"] == 0 else 0)
            + W_REFUSAL * min(ev["construction_refusals"], CAP_REFUSALS)
            + W_COMPILE_FAIL * min(ev["compile_failures"], CAP_COMPILE_FAILS))


def gaps(db, *, today: date) -> list[dict]:
    """Every line with a positive score, highest first (ties in the owner's order)."""
    ev = evidence(db, today=today)
    order = {ln.key: i for i, ln in enumerate(LINES)}
    out = []
    for ln in LINES:
        e = ev[ln.key]
        sc = score(e)
        if sc <= 0:
            continue
        why = []
        if e["certified"] == 0:
            why.append("no certified release in this line")
        if e["construction_refusals"]:
            why.append(f"{e['construction_refusals']} concept(s) refused at drafting for want "
                       f"of a construction rule ({', '.join(e['refused'][:3])})")
        if e["compile_failures"]:
            why.append(f"{e['compile_failures']} failed compile(s) in {WINDOW_DAYS} days")
        out.append({"line": ln.key, "label": ln.label, "pod": ln.pod, "score": sc,
                    "teaches": ln.teaches, "covered_by_library": e["library"] > 0,
                    "why": "; ".join(why), **{k: e[k] for k in (
                        "certified", "construction_refusals", "compile_failures", "library",
                        "refused", "needs")}})
    out.sort(key=lambda g: (-g["score"], order[g["line"]]))
    return out


def assess(db, *, today: date | None = None, pick=None) -> dict:
    """Record the gaps and raise at most `MAX_OPEN` purchase recommendations for approval."""
    from sqlalchemy import select

    from ..core.models import OperatingReading, OwnerAction
    from . import benchmark_refresh

    today = today or datetime.now(timezone.utc).date()
    pick = pick or benchmark_refresh._pick
    found = gaps(db, today=today)
    raised, held, unrecommended = [], [], []
    with db.session() as s:
        open_rows = {r.requirement_key: r for r in s.scalars(select(OwnerAction).where(
            OwnerAction.requirement_key.like(f"{ACTION_PREFIX}%"),
            OwnerAction.done == False))}  # noqa: E712
        asked_pods = set()
        for g in found:
            key = f"{ACTION_PREFIX}{g['line']}"
            if g["covered_by_library"]:
                unrecommended.append({"line": g["line"], "why": (
                    f"the library already holds {g['library']} {g['pod']} benchmark(s); "
                    f"learning from them is pending, so no second purchase")})
                continue
            if key in open_rows:
                held.append({"line": g["line"], "why": "already asked; not asked twice"})
                asked_pods.add(g["pod"])
                continue
            if g["pod"] in asked_pods:
                held.append({"line": g["line"], "why": (
                    f"a {g['pod']} purchase is already recommended; one benchmark per pod "
                    f"at a time")})
                continue
            if len(open_rows) >= MAX_OPEN:
                held.append({"line": g["line"], "why": (
                    f"{MAX_OPEN} knowledge-gap purchases already open; no indiscriminate "
                    f"spending")})
                continue
            chosen = pick(db, g["pod"])
            if not chosen:
                unrecommended.append({"line": g["line"], "why": (
                    f"no observed {g['pod']} listing to recommend; the owner is never asked "
                    f"to go and find one")})
                continue
            row = OwnerAction(
                requirement_key=key,
                action=(f"Approve buying one reference pattern for private analysis: "
                        f"{str(chosen['title'])[:80]!r} ({chosen['url']})"),
                reason=(f"Knowledge gap in {g['label']} (score {g['score']}): {g['why']}. "
                        f"A reference here would teach {g['teaches']}. It answers: "
                        f"{chosen.get('answers', '')}"[:900]),
                max_cost_cad=round(float(chosen.get("price_cad") or 0.0), 2), minutes=10,
                consequence_of_delay=("this product line keeps being refused or drafted "
                                      "without reference knowledge; the gap is re-assessed "
                                      "weekly"),
                blocks="owner-directive-2026-10-31-learning-18")
            s.add(row)
            open_rows[key] = row
            asked_pods.add(g["pod"])
            raised.append({"line": g["line"], "key": key, "max_cost_cad": row.max_cost_cad,
                           "listing_ref": chosen.get("listing_ref")})
        payload = {"as_of": today.isoformat(), "window_days": WINDOW_DAYS,
                   "weights": {"no_certified": W_NO_CERTIFIED, "refusal": W_REFUSAL,
                               "compile_failure": W_COMPILE_FAIL},
                   "gaps": found, "raised": raised, "held": held,
                   "unrecommended": unrecommended}
        row = s.scalar(select(OperatingReading).where(
            OperatingReading.kind == KIND, OperatingReading.period_key == today.isoformat()))
        if row is None:
            s.add(OperatingReading(kind=KIND, period_key=today.isoformat(), payload=payload))
        else:
            row.payload = payload
    return payload


def latest(db) -> dict | None:
    """The newest recorded gap reading, for Product Development and the owner view."""
    from sqlalchemy import desc, select

    from ..core.models import OperatingReading

    with db.session() as s:
        row = s.scalar(select(OperatingReading).where(OperatingReading.kind == KIND)
                       .order_by(desc(OperatingReading.period_key)).limit(1))
        return dict(row.payload or {}) if row is not None else None
