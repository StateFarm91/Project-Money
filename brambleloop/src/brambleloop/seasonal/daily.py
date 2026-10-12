"""The 365-day seasonal engine, run daily and written down (certification repair W6).

Requirements 33, 38, 131, 267, 286, 287, 289, 290, 291. Each of these had a library and no
runtime: the rolling calendar was served by an API and computed by nothing on a schedule,
strike teams were computed per page view and never persisted, the engine's allocation and
breakout mode never ran, storefront takeovers were never planned, roll-forward and the demand
curve were uncalled, collections were never assembled, the fast lane never admitted or
refused anything, culture signals carried no half-life, and trend rows no provenance.

`run()` does all of it from the database, once a day, and `record()` writes the reading. It
publishes nothing and spends nothing: a takeover is a scheduled plan, not a storefront change,
and every factor the engine cannot observe is UNMEASURED rather than defaulted -- which today
means no occasion scores and the compression seed stays in force, labelled as a seed.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

UNMEASURED = "UNMEASURED"
KIND = "seasonal.daily"

# Pool category to the ecosystem department it covers (#288's departments), so the rolling
# calendar reports coverage from the catalogue rather than from an empty dict.
DEPARTMENT_OF: dict[str, str] = {
    "mosaic_blanket": "blankets", "blanket": "blankets", "graphghan": "blankets",
    "baby": "blankets", "ornament": "ornaments", "stocking": "stockings",
    "seasonal_decor": "home_decor", "runner": "home_decor", "placemat": "home_decor",
    "wall_decor": "home_decor", "coaster": "home_decor", "pillow": "home_decor",
    "basket": "home_decor", "nursery": "home_decor", "flower": "home_decor",
    "hat": "hats", "bag": "bags", "garment": "garments", "shawl": "garments",
    "scarf": "garments", "amigurumi": "seasonal_gift", "pet": "seasonal_gift",
    "wedding": "seasonal_gift",
}

# Calendar event names to the concept vocabulary's occasions and the motif grammar's seasons.
CONCEPT_OCCASION: dict[str, str] = {
    "Christmas": "christmas", "Halloween": "halloween", "Thanksgiving (CA)": "thanksgiving",
    "Valentine's": "valentines", "Easter": "easter", "Mother's Day": "mothers_day",
}

# How far ahead a takeover is planned. The calendar's longest surface lead is the promotional
# ramp; an occasion further out than this has nothing to schedule yet.
TAKEOVER_HORIZON_DAYS = 120
FASTLANE_HORIZON_DAYS = 150
BREAKOUT_WINDOW_DAYS = 14


def _aware(value):
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _catalogue(db) -> dict:
    """Products that exist, with their seed, certification and certificate stages."""
    from sqlalchemy import select

    from ..core.models import Listing, PatternVersion, Product
    from ..radar.opportunity import POOL

    seeds = {m.slug: m for m in POOL}
    out: dict[str, dict] = {}
    with db.session() as s:
        listed = {r.product_slug for r in s.scalars(select(Listing))}
        for p in s.scalars(select(Product)):
            pv = s.scalar(select(PatternVersion).where(
                PatternVersion.product_id == p.id,
                PatternVersion.certified == True))  # noqa: E712
            seed = seeds.get(p.slug)
            out[p.slug] = {
                "slug": p.slug, "seed": seed,
                "season": seed.season if seed else None,
                "category": seed.category if seed else "",
                "certified": pv is not None,
                "stages": list(((pv.certificate or {}) if pv else {}).get("stages_run") or []),
                "cir": dict(pv.cir_json or {}) if pv else {},
                "listed": p.slug in listed,
                "is_bundle": bool(seed and seed.is_bundle),
            }
    return out


def _covered(catalogue: dict) -> dict[str, tuple[str, ...]]:
    covered: dict[str, set] = {}
    for item in catalogue.values():
        if not item["certified"] or not item["season"]:
            continue
        dept = DEPARTMENT_OF.get(item["category"])
        if dept:
            covered.setdefault(item["season"], set()).add(dept)
    return {k: tuple(sorted(v)) for k, v in covered.items()}


# ---- #33: the engine's scores, allocation and breakouts ------------------------------------

def opportunities(db, rolling: dict, catalogue: dict, *, samples: int, today: date) -> dict:
    """Score every event whose seven factors are all observed; list the rest as unscored.

    Three factors are arithmetic over this company's own catalogue and calendar (time
    remaining, product fit, production feasibility). Four need the market: expected demand
    (Insights search counts), achievable visibility (recorded impressions), contribution
    potential (recorded order contribution) and competitive weakness (the API search index's
    listing count for the occasion's query, relative to the most crowded occasion). An event with any factor unobserved is not scored: a factor left
    out of a product is a factor silently set to one, and a factor set to zero scores the
    occasion dead because nobody looked.
    """
    from sqlalchemy import select

    from ..core.models import InsightsSnapshot, ListingOutcome, Order
    from ..scale.runrate import orders_source_live
    from .calendar import lane_feasibility
    from .engine import Opportunity

    with db.session() as s:
        insights = list(s.scalars(select(InsightsSnapshot)))
        outcomes = list(s.scalars(select(ListingOutcome)))
        from ..commerce import orders_ingest as _oi

        orders = _oi.countable_orders(s)  # rc1-ORD2
    live = orders_source_live(db)["live"]

    demand_by_event: dict[str, float] = {}
    for snap in insights:
        if snap.search_count is None:
            continue
        for event in rolling["events"]:
            needle = event["event"].split(" ")[0].split("'")[0].lower()
            if needle and needle in (snap.keyword or "").lower():
                demand_by_event[event["event"]] = demand_by_event.get(event["event"], 0.0) \
                    + float(snap.search_count)
    peak_demand = max(demand_by_event.values(), default=0.0)
    total_impressions = sum(int(o.impressions or 0) for o in outcomes)

    # #33 competitive weakness (certification: "no source" was not true once the API search
    # index was captured). The listing count the index reports for the occasion's own query,
    # relative to the most crowded occasion: fewer competing listings reads weaker incumbents.
    # Labelled api_index_count; an occasion whose query was never captured stays unmeasured.
    from ..intel import serp

    density = serp.density(db)
    count_by_event: dict[str, int] = {}
    for event in rolling["events"]:
        word = serp.event_word(event["event"])
        reading = density.get(serp.query_for(word)) if word else None
        if reading is not None:
            count_by_event[event["event"]] = int(reading["count"])
    densest = max(count_by_event.values(), default=0)

    scored, unscored = [], []
    for event in rolling["events"]:
        name, days = event["event"], int(event["days_away"])
        slugs = [x["slug"] for x in catalogue.values() if x["season"] == name]
        lanes = lane_feasibility(days, samples=samples, today=today)
        open_lanes = sum(1 for lane in lanes if lane["verdict"] != "infeasible")
        spread = len(event["departments"]) or 1
        factors: dict[str, float | None] = {
            "time_remaining": round(open_lanes / len(lanes), 4) if lanes else 0.0,
            "product_fit": round(len(event["covered"]) / spread, 4),
            "production_feasibility": 1.0 if event["heaviest_lane_still_launchable"] else 0.0,
            "expected_demand": (round(demand_by_event[name] / peak_demand, 4)
                                if name in demand_by_event and peak_demand else None),
            "achievable_visibility": None,
            "contribution_potential": None,
            "competitive_weakness": (round(1.0 - count_by_event[name] / densest, 4)
                                     if name in count_by_event and densest else None),
        }
        if total_impressions:
            shown = sum(int(o.impressions or 0) for o in outcomes if o.product_slug in slugs)
            factors["achievable_visibility"] = round(shown / total_impressions, 4)
        if live and orders:
            event_orders = [o for o in orders if o.product_slug in slugs]
            total = sum(float(o.contribution_cad or 0.0) for o in orders)
            if total > 0:
                factors["contribution_potential"] = round(
                    max(0.0, sum(float(o.contribution_cad or 0.0) for o in event_orders))
                    / total, 4)
        missing = sorted(k for k, v in factors.items() if v is None)
        if missing:
            unscored.append({"event": name, "days_away": days, "unmeasured": missing,
                             "measured": {k: v for k, v in factors.items() if v is not None}})
            continue
        scored.append(Opportunity(event=name, days_away=days, factors=factors,
                                  basis="observed: insights, listing outcomes, orders, "
                                        "calendar arithmetic"))
    return {"scored": scored, "unscored": unscored}


def breakouts(db, catalogue: dict, *, today: date) -> dict:
    """Breakout mode for any SKU running far above its category's velocity (#33).

    Velocity is orders over the trailing fortnight and the baseline is the category's mean
    over the other SKUs. With no live order source neither exists, and nothing is called a
    breakout: every first product would otherwise be an emergency.
    """
    from sqlalchemy import select

    from ..core.models import Order
    from ..scale.runrate import orders_source_live
    from .engine import breakout

    if not orders_source_live(db)["live"]:
        return {"evaluated": 0, "breakouts": [], "reading": UNMEASURED,
                "why": "no order source is live, so no SKU has a velocity"}
    since = datetime(today.year, today.month, today.day, tzinfo=timezone.utc) \
        - timedelta(days=BREAKOUT_WINDOW_DAYS)
    with db.session() as s:
        from ..commerce import orders_ingest as _oi

        counts: dict[str, int] = {}
        for o in _oi.countable_orders(s):  # rc1-ORD2
            if _aware(o.at) >= since:
                counts[o.product_slug] = counts.get(o.product_slug, 0) + 1
    rows = []
    for slug, item in sorted(catalogue.items()):
        velocity = counts.get(slug, 0) / BREAKOUT_WINDOW_DAYS
        peers = [counts.get(x, 0) / BREAKOUT_WINDOW_DAYS for x, other in catalogue.items()
                 if x != slug and other["category"] == item["category"]]
        baseline = sum(peers) / len(peers) if peers else 0.0
        verdict = breakout(sku=slug, velocity=velocity, baseline=baseline,
                           requests=("capacity_allocation", "content_priority"))
        rows.append(verdict)
    return {"evaluated": len(rows), "breakouts": [r["sku"] for r in rows if r["breakout"]],
            "rows": rows}


# ---- #287: persisted teams with ownership ---------------------------------------------------

def persist_teams(db, allocation: dict, rolling: dict, catalogue: dict,
                  opportunity: dict, *, today: date) -> dict:
    """Write each team with what it owns; disband a team whose occasion has passed."""
    from sqlalchemy import select

    from ..core.models import BenchmarkListing, SeasonalTeam
    from ..creative.invention import MOTIF_GRAMMAR
    from .calendar import MILESTONES

    events = {e["event"]: e for e in rolling["events"]}
    unscored = {u["event"]: u for u in opportunity["unscored"]}
    scored = {o.event: o.to_dict() for o in opportunity["scored"]}
    now = datetime.now(timezone.utc)
    written, disbanded = [], []
    with db.session() as s:
        bench = list(s.scalars(select(BenchmarkListing)))
        for team in allocation["teams"]:
            event = events.get(team["event"], {})
            year = int(str(event.get("event_date", today.isoformat()))[:4])
            products = sorted(x["slug"] for x in catalogue.values()
                              if x["season"] == team["event"])
            when = date.fromisoformat(event["event_date"]) if event else today
            season = CONCEPT_OCCASION.get(team["event"], "")
            grammar_key = {"thanksgiving": "fall", "easter": "spring",
                           "mothers_day": "spring"}.get(season, season)
            needle = team["event"].split(" ")[0].split("'")[0].lower()
            owns = {
                "opportunity_map": scored.get(team["event"]) or unscored.get(
                    team["event"], {"reading": UNMEASURED}),
                "product_gaps": list(event.get("gaps", [])),
                "colour_motif_language": {
                    "season": grammar_key or None,
                    "motifs": sorted(MOTIF_GRAMMAR.get(grammar_key, ())) or UNMEASURED},
                "deadlines": [{"milestone": k,
                               "due": (when - timedelta(days=d)).isoformat()}
                              for k, d, _ in MILESTONES],
                "benchmark_changes": {"listings_mentioning": sum(
                    1 for b in bench
                    if needle and needle in ((b.title or "") + " "
                                             + (b.seasonal or "")).lower())},
                "revenue_target": {"reading": UNMEASURED,
                                   "why": "no order has been recorded, so a revenue target "
                                          "would be a wish written as a number"},
            }
            row = s.scalar(select(SeasonalTeam).where(SeasonalTeam.event == team["event"],
                                                      SeasonalTeam.year == year))
            if row is None:
                row = SeasonalTeam(event=team["event"], year=year)
                s.add(row)
            row.state, row.share, row.standing = "active", team["share"], team["standing"]
            # C-60 (#287): the agent that owns the team's next piece of work, read from the
            # team's own products -- not one name for every team.
            row.owner_agent, owns["owner_reason"] = owner_for(products, owns["product_gaps"],
                                                              catalogue)
            row.products, row.owns, row.reason = products, owns, team["doing"]
            row.updated_at = now
            written.append(team["event"])
        for gone in allocation["disbanded"]:
            for row in s.scalars(select(SeasonalTeam).where(
                    SeasonalTeam.event == gone["event"], SeasonalTeam.state == "active")):
                row.state, row.share, row.reason = "disbanded", 0.0, gone["why"]
                row.updated_at = now
                disbanded.append(gone["event"])
        for refused in allocation["refused"]:
            for row in s.scalars(select(SeasonalTeam).where(
                    SeasonalTeam.event == refused["event"], SeasonalTeam.state == "active")):
                row.state, row.reason = "refused", str(refused.get("why", ""))[:500]
                row.updated_at = now
    return {"active": written, "disbanded": disbanded}


def owner_for(products: list[str], gaps: list, catalogue: dict) -> tuple[str, str]:
    """Which agent owns a team's next step, from what the team's products are waiting on.

    An uncertified product is engineering's; a certified one with no listing is the listing
    agent's; with everything listed and departments still uncovered it is creative
    development's; with nothing uncovered and everything listed, growth's.
    """
    uncertified = [p for p in products if not catalogue.get(p, {}).get("certified")]
    unlisted = [p for p in products if catalogue.get(p, {}).get("certified")
                and not catalogue.get(p, {}).get("listed")]
    if uncertified:
        return "crochet_engineer", f"{len(uncertified)} product(s) not yet certified"
    if unlisted:
        return "listing", f"{len(unlisted)} certified product(s) with no listing"
    if gaps or not products:
        return "creative_director", (f"{len(gaps)} department(s) the occasion spans are "
                                     f"uncovered" if gaps else "the team has no product yet")
    return "growth", "every product is certified and listed; the work is demand"


def active_shares(db) -> dict[str, float]:
    """The capacity each active strike team holds (#287), for the work selectors to obey."""
    from sqlalchemy import select

    from ..core.models import SeasonalTeam

    with db.session() as s:
        return {r.event: float(r.share or 0.0) for r in s.scalars(select(SeasonalTeam).where(
            SeasonalTeam.state == "active")) if (r.share or 0) > 0}


# ---- #128: breakout mining ------------------------------------------------------------------

BREAKOUT_KIND = "seasonal.breakout_mining"
ADJACENT_AXES: tuple[tuple[str, str], ...] = (
    ("format", "what other made object carries the same mechanism for the same buyer?"),
    ("recipient", "who else would want this mechanism, and what would they need it to be?"),
    ("complexity", "what is the quick-make version, and what is the heirloom version?"),
    ("bundle_position", "what entry product or companion piece sits beside it in a set?"),
)


def _traits(item: dict) -> dict:
    seed = item.get("seed")
    if seed is None:
        return {}
    text = f"{seed.title} {seed.rationale}".lower()
    return {"category": seed.category, "season": seed.season or "evergreen",
            "price": ("under_6" if seed.price_cad < 6 else "6_to_10" if seed.price_cad < 10
                      else "over_10"),
            "sewing": "no_sew" if "no-sew" in text or "no sew" in text else "sewn_or_na",
            "aesthetic": seed.family or seed.category,
            "bundle": "bundle" if seed.is_bundle else "single"}


def mine_breakouts(db, catalogue: dict, breakout: dict, *, today: date) -> dict:
    """Decompose each breakout's winning mechanism and brief adjacent ORIGINAL work (#128).

    The decomposition is `commerce.replication.candidates` over the catalogue with the order
    counts the breakout was computed from, stored as a reading. The brief holds the most
    distinguishable dimension and changes format, recipient, complexity and bundle position --
    never only the palette, which `replication.check_proposal` refuses by name.
    """
    from sqlalchemy import select

    from ..commerce import replication
    from ..core.models import OperatingReading, Order

    winners = list(breakout.get("breakouts") or [])
    if not winners:
        return {"reading": breakout.get("reading", "none"), "mined": [], "requests": []}
    with db.session() as s:
        from ..commerce import orders_ingest as _oi

        counts: dict[str, int] = {}
        for o in _oi.countable_orders(s):  # rc1-ORD2
            counts[o.product_slug] = counts.get(o.product_slug, 0) + 1
    skus = [replication.Sku(slug=slug, orders=counts.get(slug, 0), weeks_live=0,
                            traits=_traits(item)) for slug, item in catalogue.items()]
    mined, requests = [], []
    for slug in winners:
        winner = next((x for x in skus if x.slug == slug), None)
        if winner is None:
            continue
        why = replication.candidates(winner, skus)
        hold = [r["dimension"] for r in why["ranked"][:1]]
        seed = (catalogue.get(slug) or {}).get("seed")
        from ..intel import pods

        pod = pods.route(f"{seed.title} {seed.category}") if seed else ""
        proposal = replication.check_proposal(
            replication.Proposal(slug=f"{slug}-adjacent", holds=tuple(hold or ["category"]),
                                 changes=tuple(d for d in ("price", "bundle", "sewing")
                                               if d not in hold)), winner)
        mined.append({"winner": slug, "explanations": why["ranked"],
                      "confounded": why["confounded"], "attributable": why["attributable"],
                      "holds": hold, "proposal": proposal})
        requests.append({
            "lane": "breakout_adjacent", "arena": pod, "pod": pod,
            "objective": (f"adjacent ORIGINAL opportunities to the breakout {slug}: hold "
                          f"{hold or ['its category']} and change format, recipient, "
                          f"complexity and bundle position while the window is open -- "
                          f"never a recolour or a clone of it"),
            "diverged_from": slug,
            "trigger": {"kind": "breakout", "slug": slug, "as_of": today.isoformat()},
            "briefs": [{"axis": a, "question": q, "claims_market_gap": False,
                        "vocabulary": []} for a, q in ADJACENT_AXES]})
    payload = {"as_of": today.isoformat(), "mined": mined}
    with db.session() as s:
        row = s.scalar(select(OperatingReading).where(
            OperatingReading.kind == BREAKOUT_KIND,
            OperatingReading.period_key == today.isoformat()))
        if row is None:
            s.add(OperatingReading(kind=BREAKOUT_KIND, period_key=today.isoformat(),
                                   payload=payload))
        else:
            row.payload = payload
    return {"reading": "measured", "mined": mined, "requests": requests}


# ---- #131: takeovers --------------------------------------------------------------------------

def takeovers(db, rolling: dict, catalogue: dict, *, today: date) -> dict:
    from sqlalchemy import select

    from ..brand import takeover
    from ..core.models import Collection

    with db.session() as s:
        collections = {c.season: c.title for c in s.scalars(select(Collection)) if c.season}
    planned, refused = [], []
    for event in rolling["events"]:
        if event["days_away"] > TAKEOVER_HORIZON_DAYS:
            continue
        name = event["event"]
        members = sorted(x["slug"] for x in catalogue.values()
                         if x["season"] == name and x["certified"] and not x["is_bundle"])
        if not members:
            refused.append({"event": name, "why": "no certified product targets it, so a "
                                                  "takeover would feature nothing"})
            continue
        changes = {
            "banner": f"{name}: {len(members)} Brambleloop crochet patterns for {name}",
            "featured_collection": collections.get(name) or ", ".join(members[:4]),
            "shop_content": f"a {name} section holding {', '.join(members[:4])}",
            "thumbnails": f"{name} thumbnail treatment on {len(members)} listing(s)",
        }
        bundles = sorted(x["slug"] for x in catalogue.values()
                         if x["season"] == name and x["is_bundle"] and x["listed"])
        if bundles:
            changes["bundles"] = ", ".join(bundles)
        problems = takeover.check(takeover.Takeover(
            event=name, event_date=date.fromisoformat(event["event_date"]),
            surfaces=tuple(changes), changes=changes))
        if problems:
            refused.append({"event": name, "problems": problems})
            continue
        try:
            plan = takeover.plan(name, date.fromisoformat(event["event_date"]), changes,
                                 today=today)
        except takeover.TakeoverRefused as exc:
            refused.append({"event": name, "why": str(exc)})
            continue
        planned.append(plan)
    # C-69 (#131): the executor applies each planned surface on its transition date and
    # reverts it on its revert date, on the drafted storefront.
    executed = takeover.execute(db, planned, today=today)
    return {"planned": planned, "refused": refused,
            "overdue_surfaces": sum(len(p["overdue"]) for p in planned),
            "executed": {k: executed[k] for k in ("applied", "reverted", "refused")},
            "active": executed["active"],
            "note": ("applied to and reverted from the drafted storefront on schedule; the "
                     "marketplace write is withheld in shadow mode")}


# ---- #289: collections from the catalogue's concepts ---------------------------------------

def collections(catalogue: dict) -> dict:
    from ..creative.audit import catalogue_concepts
    from . import collections as coll

    concepts = [c for c in catalogue_concepts()
                if c.key in catalogue and catalogue[c.key]["certified"]]
    out = []
    for event, occasion in CONCEPT_OCCASION.items():
        members = [c for c in concepts if c.occasion == occasion]
        for story in sorted({c.palette_story for c in members}):
            # The concept vocabulary's occasion, not the calendar's name: `assemble` keeps
            # only candidates whose occasion equals the one it is given, and "Christmas" is
            # never equal to "christmas" -- every engine collection read empty (C-60).
            report = coll.assemble(occasion, key=f"{occasion}:{story}", palette_story=story,
                                   visual_language=f"{occasion} {story}",
                                   candidates=members)
            out.append({**report, "calendar_event": event})
    return {"assessed": len(out), "coherent": [c["collection"] for c in out if c["coherent"]],
            "collections": out}


def persist_collections(db, reading: dict) -> dict:
    """A coherent engine collection becomes a `Collection` row; an incoherent one does not.

    `takeovers()` features a season's Collection row, so this is where the assessment acts:
    an incoherent grouping is never featured, and a row for a grouping that has stopped being
    coherent is withdrawn from its season (#289).
    """
    from sqlalchemy import select

    from ..core.models import Collection

    written, withdrawn = [], []
    by_key = {c["collection"]: c for c in reading.get("collections") or []}
    with db.session() as s:
        for key, c in by_key.items():
            slug = "engine-" + "".join(ch if ch.isalnum() else "-" for ch in key.lower())[:70]
            row = s.scalar(select(Collection).where(Collection.slug == slug))
            if c.get("coherent"):
                if row is None:
                    row = Collection(slug=slug, family=c.get("visual_language") or key)
                    s.add(row)
                row.title = f"{c.get('visual_language') or key}".title()[:200]
                row.season = c.get("calendar_event") or c.get("event")
                row.story = f"engine collection {key}: members {c.get('members')}"[:2000]
                written.append(slug)
            elif row is not None and row.season:
                row.season = None
                withdrawn.append(slug)
    return {"written": written, "withdrawn": withdrawn}


# ---- #290/#291: half-life and the fast lane --------------------------------------------------

def half_lives(db) -> dict:
    """Classify every culture signal's half-life and stamp it on the signal row (#290)."""
    from sqlalchemy import select

    from ..core.models import CultureSignal
    from ..culture import radar
    from .fastlane import FastLaneRefused, classify_half_life

    recurring = set(radar.memory(db)["recurring_annually"])
    classified, refused = {}, []
    with db.session() as s:
        for row in s.scalars(select(CultureSignal)):
            try:
                got = classify_half_life(domain=row.domain, recurring=row.key in recurring)
            except FastLaneRefused as exc:
                refused.append({"signal": row.key, "why": str(exc)})
                continue
            score = dict(row.score or {})
            score["half_life"] = got
            row.score = score
            classified[row.key] = got["half_life"]
    return {"classified": classified, "refused": refused}


def fast_lane(db, rolling: dict, catalogue: dict) -> dict:
    """Admit or refuse each near-season certified product, and check admitted releases."""
    from sqlalchemy import select

    from ..core.models import CultureSignal
    from ..culture.score import MIN_EVIDENCE_WEIGHT
    from .fastlane import (
        CONDITIONAL_GATES, Candidate, FastLaneRefused, admit, check_release,
        classify_half_life,
    )
    from .leadtime import classify

    near = {e["event"] for e in rolling["events"] if e["days_away"] <= FASTLANE_HORIZON_DAYS}
    with db.session() as s:
        evidence: dict[str, float] = {}
        for row in s.scalars(select(CultureSignal)):
            sc = row.score or {}
            if isinstance(sc.get("score"), (int, float)) and \
                    float(sc.get("evidence_weight") or 0.0) >= MIN_EVIDENCE_WEIGHT:
                evidence[(row.topic or row.key).lower()] = float(sc["score"])

    decisions, releases = [], []
    for slug, item in sorted(catalogue.items()):
        seed = item["seed"]
        if seed is None or item["is_bundle"] or not item["certified"]:
            continue
        if item["season"] and item["season"] not in near:
            continue
        cir = item["cir"]
        components = len(cir.get("components") or []) or 1
        colours = len(cir.get("colours") or cir.get("colors") or cir.get("palette") or [])
        life = classify_half_life(domain="", season=item["season"],
                                  evergreen=not item["season"])
        confidence = next((v for k, v in evidence.items()
                           if item["season"] and item["season"].lower().split(" ")[0] in k),
                          None)
        candidate = Candidate(slug=slug, half_life=life["half_life"],
                              make_lane=classify(max(seed.maker_hours)),
                              risk_class=seed.risk_class, components=components,
                              colours=colours or 1, new_techniques=0,
                              evidence_confidence=confidence)
        verdict = admit(candidate)
        verdict["half_life"] = life
        decisions.append(verdict)
        if verdict["admitted"]:
            owed = tuple(g for g in CONDITIONAL_GATES
                         if (g in ("asset_truth", "policy") and item["listed"])
                         or (g == "geometry" and "geometry" in item["stages"]))
            try:
                releases.append(check_release(slug, gates_passed=tuple(item["stages"]),
                                              applicable_conditional=owed))
            except FastLaneRefused as exc:
                releases.append({"slug": slug, "ok": False, "refused": str(exc)})
    return {"evaluated": len(decisions),
            "admitted": [d["slug"] for d in decisions if d["admitted"]],
            "decisions": decisions, "release_checks": releases}


# ---- the run ---------------------------------------------------------------------------------

# #147 (W4-B2): Seasonal Planning reads its lesson inbox where it plans. `culture.radar`
# publishes cultural_territory and cultural_timing lessons routed to `portfolio` -- the cell
# that holds the seasonal programme -- and until now nothing in the seasonal engine read them,
# so the planning half of "findings flow into Seasonal Planning" was a route with no reader.
SEASONAL_CELL = "portfolio"
CULTURE_SUBJECTS = frozenset({"cultural_territory", "cultural_timing"})


def culture_lessons(db, calendar: dict) -> dict:
    """Attach each cultural lesson that names an occasion to that occasion's plan.

    A lesson applies to an event when its words share the occasion's name (or the concept
    vocabulary's word for it); the plan carries the lesson and the decision is recorded through
    `bus.acted_on`. An occasion no lesson names carries nothing -- never an invented signal.
    """
    from ..improve import consume

    events = list(calendar.get("events") or [])
    applied = []
    for event in events:
        name = event["event"]
        text = " ".join([name, CONCEPT_OCCASION.get(name, "").replace("_", " ")])
        hits = [h for h in consume.matching(db, SEASONAL_CELL, text, min_shared=1,
                                            subjects=CULTURE_SUBJECTS)
                if h["direction"] >= 0]
        if not hits:
            continue
        consume.act(db, SEASONAL_CELL, hits,
                    how=f"seasonal.engine plan for {name} carries the cultural lesson")
        applied.append({"event": name, "days_away": event.get("days_away"),
                        "lessons": [{"id": int(h["id"]), "subject": h["subject"],
                                     "statement": h["statement"]} for h in hits]})
    return {"events_read": len(events), "applied": applied, "cell": SEASONAL_CELL,
            "basis": "improve.bus lessons from culture.radar (reference-reading proxy)"}


def run(db, *, today: date | None = None) -> dict:
    """One day of the seasonal engine. Reads, computes, and persists teams and stamps."""
    from ..radar import provenance
    from . import engine, rollforward, teams, uncertainty
    from .calendar import rolling as rolling_calendar
    from .compression import priority_shares

    today = today or date.today()
    samples = uncertainty.sample_count(db)
    catalogue = _catalogue(db)

    # #287 first, so the calendar can name each event's team.
    team_alloc = teams.allocate(db, today=today, samples=samples)
    try:
        teams.check(team_alloc)
        team_problem = ""
    except teams.TeamRefused as exc:
        team_problem = str(exc)

    # #286: every horizon, 30 to 365 days, from today.
    calendar = rolling_calendar(today, covered=_covered(catalogue),
                                strike_teams={t["event"]: f"team:{t['event']}"
                                              for t in team_alloc["teams"]})

    # #33: scores where every factor is observed, the allocation they imply, and breakouts.
    opp = opportunities(db, calendar, catalogue, samples=samples, today=today)
    allocation = engine.allocate(opp["scored"])
    squads = [engine.squad_state(o, currently_active=o.event in {t["event"] for t in
                                                                 team_alloc["teams"]},
                                 alternatives=opp["scored"]) for o in opp["scored"]]
    shares = priority_shares({o.event: o.score for o in opp["scored"]})
    persisted = persist_teams(db, team_alloc, calendar, catalogue, opp, today=today)

    # #267: capacity roll-forward and each occasion's structural demand floor.
    rolled = rollforward.roll_forward(today, samples=samples)
    curves = [rollforward.demand_curve(date.fromisoformat(e["event_date"]), today)
              for e in calendar["events"]]

    lives = half_lives(db)
    return {
        "period": today.isoformat(),
        "rolling_calendar": calendar,
        "engine": {"allocation": allocation, "scored": [o.to_dict() for o in opp["scored"]],
                   "unscored": opp["unscored"], "squads": squads,
                   "priority_shares": shares,
                   "breakout": (bo := breakouts(db, catalogue, today=today)),
                   "breakout_mining": mine_breakouts(db, catalogue, bo, today=today)},
        "teams": {**team_alloc, "problem": team_problem, "persisted": persisted},
        "takeovers": takeovers(db, calendar, catalogue, today=today),
        "rollforward": rolled,
        "demand_curves": curves,
        "collections": (coll_reading := collections(catalogue)),
        "collections_persisted": persist_collections(db, coll_reading),
        "half_lives": lives,
        "culture_lessons": culture_lessons(db, calendar),
        "fast_lane": fast_lane(db, calendar, catalogue),
        "provenance": provenance.stamp_all(db, today=today,
                                           half_lives=lives["classified"]),
    }


def record(db, payload: dict) -> dict:
    from sqlalchemy import select

    from ..core.models import OperatingReading

    with db.session() as s:
        row = s.scalar(select(OperatingReading).where(
            OperatingReading.kind == KIND, OperatingReading.period_key == payload["period"]))
        if row is None:
            row = OperatingReading(kind=KIND, period_key=payload["period"])
            s.add(row)
        row.payload = payload
        row.at = datetime.now(timezone.utc)
        s.flush()
        return {"id": row.id, "period": payload["period"]}
