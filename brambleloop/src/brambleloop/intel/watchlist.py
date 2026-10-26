"""The owner's permanent competitor watchlist, and the chain that turns it into decisions.

Owner directive, 2026-10-26 (W4-INTELREC). Four shops, permanent and exact:

* MJsOffTheHookDesigns ("Mrs J") -- the anchor (#301). Her special monitoring is unchanged:
  `mjs.scan` keeps its own cadence, mission and dashboard. This module only reads her rows.
* MadelineMaeCo -- special monitoring. No spec, registry, DECISION_LOG entry or code in this
  repository names her before this directive (INTEL_RECONCILIATION.md records the search), so
  her "original special monitoring" is restored here from the directive itself.
* ZKBDESIGNER and TheEasyDesign -- permanent benchmarks, not replacements.

What runs, all on the existing job framework and agents (market_radar, Intelligence):

1. `intel.watchlist_scan` -- each non-anchor shop through the SAME scan as Mrs J
   (`intel.observe.scan`: official Etsy Open API v3, baseline then change detection, the
   adaptive interval, the no-content rules), the same eight-step mission pipeline
   (`mission_runtime.process`), weekly review themes (`observe.scan_reviews`) and the shop's
   public counters (sales, reviews, favourites, active listings) from `findShops`. A source
   outage for one shop is recorded and never stops the others; nothing is retried in a loop.
2. `intel.watchlist_compare` -- the structured four-shop comparison, evidence-graded figure by
   figure, stored as a daily reading with aliases only (L-3). AI-use is a hypothesis slot
   that stays UNKNOWN: nothing here assumes a shop is AI-operated.
   Arenas two or more watchlist shops occupy that we do not are *validated* opportunities
   (cross-shop corroboration) and enter the existing coverage-gap queue (#314).
3. `intel.opportunity_review` -- delegated by Laura (her `intelligence` provider reads this
   module's `summary`). Each validated opportunity gets one decision: a pool concept answers
   it (radar.score -> the pre-engineering gate -> cir.draft), or a divergent original
   tournament is briefed (creative.tournament -> intake -> cir.draft). A strategy that failed
   twice for an arena is stopped and becomes a lesson; that lesson defers later decisions on
   the same arena. Every decision is a durable memory record.

Nothing here publishes, writes to Etsy, buys a pattern or changes a budget. Paid work it
starts (a tournament) passes the creative director's existing ceilings like any other.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from . import benchmarks

WATCHLIST_KEY = "watchlist"            # the coverage-gap benchmark key for corroborated arenas
SCAN_READING = "intel.watchlist_shop"
COMPARE_READING = "intel.watchlist_compare"
STATE_PREFIX = "intel:watchlist:"
DECISION_PREFIX = "intel:opportunity:"
REVIEW_INTERVAL = timedelta(days=7)
STALE_AFTER = timedelta(hours=48)
OUTAGE_FAILURES = 2
MIN_LISTINGS_FOR_ARENA = 3
MIN_SHOPS_FOR_ARENA = 2
MAX_FAILED_ATTEMPTS = 2
SETTLE = timedelta(days=1)
REVIEW_LIMIT = 3
MISSION_LIMIT = 5

ANCHOR, SPECIAL, PERMANENT = "anchor", "special", "permanent"


@dataclass(frozen=True)
class Member:
    key: str
    shop_name: str
    owner_url: str
    role: str
    special: bool
    label: str = ""


WATCHLIST: tuple[Member, ...] = (
    Member(benchmarks.MJS_KEY, benchmarks.MJS_SHOP,
           "https://www.etsy.com/shop/MJsOffTheHookDesigns", ANCHOR, True, "Mrs J"),
    Member("madeline_mae_co", "MadelineMaeCo", "https://www.etsy.com/shop/MadelineMaeCo",
           SPECIAL, True),
    Member("zkbdesigner", "ZKBDESIGNER", "https://www.etsy.com/ca/shop/ZKBDESIGNER",
           PERMANENT, False),
    Member("the_easy_design", "TheEasyDesign", "https://www.etsy.com/ca/shop/TheEasyDesign",
           PERMANENT, False),
)
BY_KEY = {m.key: m for m in WATCHLIST}

# The owner's monitoring scope, and how each part is read. A part with no compliant source is
# said so; it is never approximated.
SCOPE: dict[str, tuple[str, str]] = {
    "new_or_removed_listings": ("MEASURED", "official API catalogue, fingerprint diff"),
    "categories": ("DERIVED", "our pod routing of each listing (intel.pods)"),
    "catalogue_change": ("MEASURED", "official API catalogue, fingerprint diff"),
    "families_variations": ("MEASURED", "listing options/variations where the API returns them"),
    "price_and_promotions": ("MEASURED", "listing price and is_sale from the API"),
    "seasonal_launches": ("DERIVED", "first_seen dates x seasonal routing"),
    "bundles": ("DERIVED", "deliverable facts read from the listing payload"),
    "presentation_galleries": ("MEASURED", "gallery image counts from the API; vision "
                                           "judgement of images runs for the anchor only, "
                                           "inside market_radar's ceiling"),
    "titles_tags": ("MEASURED", "tags from the API, stored under the existing benchmark rules; "
                                "never reused in our listings"),
    "review_counts_and_sentiment": ("MEASURED", "findShops review_count/review_average; "
                                                "recurring complaint themes counted from "
                                                "getReviewsByShop, never quoted"),
    "public_sales_milestones": ("MEASURED", "findShops transaction_sold_count"),
    "popularity_signals": ("MEASURED", "num_favorers (shop and listing)"),
    "style_trends_positioning": ("DERIVED", "pod mix and price band over time"),
}
SHOP_FIELDS = ("transaction_sold_count", "review_count", "review_average", "num_favorers",
               "listing_active_count")


class _NoReader(Exception):
    pass


# Tests and the HQ worker inject a reader; production builds the official-API reader.
reader_factory = None


def specs() -> tuple:
    """The registry entries for the non-anchor members (declared in `benchmarks`)."""
    return tuple(benchmarks.spec_for(m.key) for m in WATCHLIST if m.role != ANCHOR)


def _now(now=None) -> datetime:
    return now or datetime.now(timezone.utc)


def _state(db, key: str) -> dict:
    from ..autonomy import memory

    rec = memory.get(db, STATE_PREFIX + key)
    return dict((rec or {}).get("body") or {})


def _save_state(db, key: str, body: dict, *, now: datetime) -> None:
    from ..autonomy import memory

    memory.remember(db, STATE_PREFIX + key, kind="intel.watchlist", department="intelligence",
                    subject=f"watchlist {key}", state=body.get("state", "unknown"),
                    body=body, sources=["etsy_open_api_v3"], now=now)


def _reader(env=None):
    if reader_factory is not None:
        return reader_factory()
    from ..integrations.http import UrllibTransport
    from .etsy_public import PublicReader

    r = PublicReader(UrllibTransport(), env=env)
    r._headers()  # noqa: SLF001 - NotConfigured here, before any request
    return r


def scan_member(db, member: Member, reader, *, now: datetime | None = None,
                enqueue=None, force: bool = False) -> dict:
    """One shop: due check, public shop counters, catalogue scan, mission, weekly reviews."""
    from . import mission, mission_runtime, observe
    from .etsy_public import ReadFailed

    now = _now(now)
    st = _state(db, member.key)
    if not force:
        due = observe.scan_due(db, benchmark_key=member.key, now=now)
        if not due["due"] and st.get("state") == "ok":
            return {"key": member.key, "ran": False, "deferred": True, "why": due["why"]}
    try:
        shop = reader.resolve_shop(member.shop_name)
        facts = {f: shop.get(f) for f in SHOP_FIELDS}
        result = observe.scan(db, reader, benchmark_key=member.key,
                              shop_name=member.shop_name, env={})
        report = result.to_report()
        mission.check_report(report, shop_name=member.shop_name)
        reviews = None
        last_rev = st.get("reviews_at")
        if force or not last_rev or now - datetime.fromisoformat(last_rev) >= REVIEW_INTERVAL:
            themes = observe.scan_reviews(db, shop_name=member.shop_name, reader=reader,
                                          benchmark_key=member.key)
            reviews = {"read": themes.get("reviews_read"),
                       "recurring_themes": len(themes.get("recurring") or [])}
    except ReadFailed as exc:
        kind = "credential_refused" if exc.credential_refused else "source_outage"
        st.update(state=kind, last_error=str(exc)[:300], last_attempt_at=now.isoformat(),
                  consecutive_failures=int(st.get("consecutive_failures") or 0) + 1)
        _save_state(db, member.key, st, now=now)
        return {"key": member.key, "ran": False, "state": kind,
                "consecutive_failures": st["consecutive_failures"]}
    except Exception as exc:  # noqa: BLE001 - one shop's fault never stops the others
        st.update(state="source_outage", last_error=f"{type(exc).__name__}: {exc}"[:300],
                  last_attempt_at=now.isoformat(),
                  consecutive_failures=int(st.get("consecutive_failures") or 0) + 1)
        _save_state(db, member.key, st, now=now)
        return {"key": member.key, "ran": False, "state": "source_outage",
                "consecutive_failures": st["consecutive_failures"]}
    history = list(st.get("shop_history") or [])[-29:]
    history.append({"at": now.isoformat(), **facts})
    st.update(state="ok", last_ok_at=now.isoformat(), last_attempt_at=now.isoformat(),
              consecutive_failures=0, last_error="", shop=facts, shop_history=history,
              listings_seen=report["catalogue_coverage"]["listings_seen_this_scan"],
              changes=len(report["changes"]))
    if reviews is not None:
        st.update(reviews_at=now.isoformat(), reviews=reviews)
    _save_state(db, member.key, st, now=now)
    mission_out = None
    if enqueue is not None:
        m = mission_runtime.process(db, enqueue=enqueue, today=now.date(),
                                    benchmark_key=member.key, limit=MISSION_LIMIT)
        mission_out = {"pending": m["pending"], "processed": m["processed"]}
    return {"key": member.key, "ran": True, "listings_seen": st["listings_seen"],
            "changes": st["changes"], "reviews": reviews, "mission": mission_out}


def scan_all(db, *, enqueue=None, env=None, now: datetime | None = None,
             force: bool = False) -> dict:
    from .etsy_public import NotConfigured, auth_refused, last_probe

    now = _now(now)
    members = [m for m in WATCHLIST if m.role != ANCHOR]
    try:
        reader = _reader(env)
    except NotConfigured as exc:
        for m in members:
            st = _state(db, m.key)
            st.update(state="not_configured", last_error=str(exc)[:200],
                      last_attempt_at=now.isoformat())
            _save_state(db, m.key, st, now=now)
        return {"ran": False, "reason": str(exc)[:200], "shops": [],
                "substituted": False}
    if reader_factory is None and auth_refused(last_probe(db)):
        return {"ran": False, "reason": "Etsy refused the read credential at the last "
                                        "etsy.probe; the watchlist waits for a probe to "
                                        "succeed rather than knocking with a refused key",
                "shops": [], "substituted": False}
    shops = [scan_member(db, m, reader, now=now, enqueue=enqueue, force=force)
             for m in members]
    return {"ran": True, "shops": shops,
            "observed": sum(1 for s in shops if s.get("ran")),
            "outages": [s["key"] for s in shops if s.get("state") in
                        ("source_outage", "credential_refused")]}


# ---- the four-shop comparison ------------------------------------------------------------

def _grade(value, source: str, as_of, basis: str = "MEASURED") -> dict:
    if value is None or value == "UNKNOWN":
        return {"value": "UNKNOWN", "grade": "UNKNOWN", "source": source, "as_of": as_of,
                "why": "not observed by a compliant source yet"}
    return {"value": value, "grade": basis, "source": source, "as_of": as_of}


def compare(db, *, now: datetime | None = None) -> dict:
    """The structured comparison: aliases, our own labels and numbers only."""
    import statistics

    from ..runtime.intel_ops import benchmark_alias, snapshot

    now = _now(now)
    snap = snapshot(db, now=now)
    by_alias: dict[str, list] = {}
    for g in snap["groups"]:
        by_alias.setdefault(g["benchmark"], []).append(g)
    shops = []
    arenas: dict[str, list[str]] = {}
    for m in WATCHLIST:
        alias = benchmark_alias(m.key)
        st = _state(db, m.key)
        groups = by_alias.get(alias, [])
        listings = sum(g["listings"] for g in groups)
        prices = [g["price_median_cad"] for g in groups
                  if isinstance(g["price_median_cad"], (int, float))]
        media = [g["median_media"] for g in groups
                 if isinstance(g["median_media"], (int, float))]
        mix = {g["pod"]: g["listings"] for g in groups}
        for pod, n in mix.items():
            if n >= MIN_LISTINGS_FOR_ARENA:
                arenas.setdefault(pod, []).append(alias)
        shop = st.get("shop") or {}
        as_of = st.get("last_ok_at") or (snap["at"] if listings else None)
        src = "etsy open api v3 (stored benchmark_listings)"
        shops.append({
            "alias": alias, "role": m.role, "special_monitoring": m.special,
            "observation": {"state": st.get("state") or ("ok" if listings else "never"),
                            "last_ok_at": st.get("last_ok_at"),
                            "consecutive_failures": st.get("consecutive_failures", 0)},
            "figures": {
                "listings_observed": _grade(listings or None, src, as_of),
                "new_listings_7d": _grade(sum(g["new_7d"] for g in groups) if groups else None,
                                          src, as_of, "DERIVED"),
                "price_median_cad": _grade(round(statistics.median(prices), 2) if prices
                                           else None, src, as_of),
                "on_sale_share": _grade(round(sum(g["on_sale_share"] * g["listings"]
                                                  for g in groups) / listings, 3)
                                        if listings else None, src, as_of),
                "gallery_median_images": _grade(statistics.median(media) if media else None,
                                                src, as_of),
                "category_mix": _grade(dict(sorted(mix.items())) or None, src, as_of,
                                       "DERIVED"),
                "public_sales": _grade(shop.get("transaction_sold_count"), "findShops", as_of),
                "review_count": _grade(shop.get("review_count"), "findShops", as_of),
                "review_average": _grade(shop.get("review_average"), "findShops", as_of),
                "shop_favourites": _grade(shop.get("num_favorers"), "findShops", as_of),
                "recurring_complaint_themes": _grade(
                    (st.get("reviews") or {}).get("recurring_themes"), "getReviewsByShop",
                    st.get("reviews_at"), "DERIVED"),
            },
            # Never assumed. A hypothesis slot with no evidence collected is UNKNOWN.
            "ai_use": {"assessment": "UNKNOWN", "hypothesis_only": True,
                       "evidence": [], "why": "no evidence collected; a shop is never "
                                              "assumed AI-operated"},
        })
    ours = _our_pods(db)
    validated = sorted((pod, sorted(a)) for pod, a in arenas.items()
                       if len(a) >= MIN_SHOPS_FOR_ARENA and pod not in ours)
    return {"at": now.isoformat(), "shops": shops, "scope": {k: v[0] for k, v in SCOPE.items()},
            "validated_arenas": [{"pod": p, "corroborated_by": a} for p, a in validated],
            "copies_competitor_content": False,
            "uncertainty": ("figures are what the official API exposed at as_of; a shop whose "
                            "observation is not ok has UNKNOWN figures, never zeros")}


def _our_pods(db) -> set[str]:
    from sqlalchemy import select

    from ..core.models import Product
    from . import pods

    with db.session() as s:
        titles = [(p.title or p.slug) for p in s.scalars(select(Product))]
    return {pods.route(t, "") for t in titles}


def record_comparison(db, *, now: datetime | None = None) -> dict:
    """Store the day's comparison and put validated arenas on the coverage-gap queue."""
    from ..runtime.etsy_ops import store_reading
    from . import coverage

    now = _now(now)
    rep = compare(db, now=now)
    _assert_no_content(rep)
    store_reading(db, COMPARE_READING, rep, now=now)
    opened = []
    for a in rep["validated_arenas"]:
        gid = coverage.upsert(db, benchmark_key=WATCHLIST_KEY, arena=f"watchlist:{a['pod']}",
                              pod=a["pod"], evidence=None)
        _merge_gap_evidence(db, gid, {"corroborated_by": a["corroborated_by"],
                                      "validated_at": now.isoformat(),
                                      "source": COMPARE_READING})
        opened.append(gid)
    return {"report": rep, "gaps": opened}


def _merge_gap_evidence(db, gap_id: int, extra: dict) -> None:
    from sqlalchemy.orm.attributes import flag_modified

    from ..core.models import CoverageGap

    with db.session() as s:
        g = s.get(CoverageGap, gap_id)
        g.evidence = {**(g.evidence or {}), **extra}
        flag_modified(g, "evidence")


def _assert_no_content(rep: dict) -> None:
    import json

    text = json.dumps(rep)
    for m in WATCHLIST:
        if m.shop_name.lower() in text.lower() or m.key in text:
            raise ValueError("the comparison carries a shop name or key; aliases only (L-3)")


# ---- Laura's provider and the delegated review --------------------------------------------

def summary(db) -> dict:
    """Laura's `intelligence` provider. DEGRADED when a watchlist source is out or a
    validated opportunity waits for a decision; OK otherwise."""
    now = _now()
    outages, stale = [], []
    for m in WATCHLIST:
        if m.role == ANCHOR:
            continue
        st = _state(db, m.key)
        if int(st.get("consecutive_failures") or 0) >= OUTAGE_FAILURES:
            outages.append(f"{benchmark_alias_safe(m.key)}:{st.get('state')}")
        last = st.get("last_ok_at")
        if last and now - datetime.fromisoformat(last) > STALE_AFTER:
            stale.append(benchmark_alias_safe(m.key))
    waiting = [g for g in _open_gaps(db) if not (g["evidence"] or {}).get("design_job_id")
               and not _deferred_today(db, g["id"], now.date())]
    reasons = []
    if waiting:
        reasons.append(f"{len(waiting)} validated watchlist opportunit"
                       f"{'y' if len(waiting) == 1 else 'ies'} awaiting a decision")
    if outages:
        reasons.append(f"source outage: {outages}")
    if stale:
        reasons.append(f"observation older than {int(STALE_AFTER.total_seconds() // 3600)} h: "
                       f"{stale}")
    return {"status": "DEGRADED" if reasons else "OK", "reason": "; ".join(reasons),
            "as_of": now.isoformat(), "waiting": [g["id"] for g in waiting],
            "outages": outages, "stale": stale}


def benchmark_alias_safe(key: str) -> str:
    from ..runtime.intel_ops import benchmark_alias

    return benchmark_alias(key)


def _open_gaps(db) -> list[dict]:
    from sqlalchemy import select

    from ..core.models import CoverageGap
    from . import coverage

    with db.session() as s:
        return [{"id": g.id, "pod": g.pod, "arena": g.arena, "evidence": dict(g.evidence or {})}
                for g in s.scalars(select(CoverageGap).where(
                    CoverageGap.benchmark_key == WATCHLIST_KEY,
                    CoverageGap.state == coverage.UNCOVERED).order_by(CoverageGap.id))]


def _decision(db, gap_id: int) -> dict:
    from ..autonomy import memory

    rec = memory.get(db, f"{DECISION_PREFIX}{gap_id}")
    return dict((rec or {}).get("body") or {})


def _deferred_today(db, gap_id: int, today: date) -> bool:
    d = _decision(db, gap_id)
    return d.get("last") == "deferred_by_lesson" and d.get("on") == today.isoformat()


def _record_decision(db, gap_id: int, decision: str, *, today: date, **detail) -> dict:
    from ..autonomy import memory

    body = _decision(db, gap_id)
    hist = list(body.get("history") or [])[-19:]
    hist.append({"on": today.isoformat(), "decision": decision, **detail})
    body.update(last=decision, on=today.isoformat(), history=hist)
    memory.remember(db, f"{DECISION_PREFIX}{gap_id}", kind="intel.opportunity_decision",
                    department="intelligence", subject=f"watchlist gap {gap_id}",
                    state=decision, body=body, sources=["coverage_gaps", COMPARE_READING])
    return body


def _lesson_statement(pod: str, n: int) -> str:
    return (f"watchlist arena {pod}: {n} original design attempts produced no engineered "
            f"product, so stop re-asking this arena until new evidence arrives")


def review(db, *, enqueue, today: date | None = None, now: datetime | None = None) -> dict:
    """One decision per validated opportunity. Bounded, idempotent, lesson-aware."""
    from sqlalchemy.orm.attributes import flag_modified

    from ..core.models import CoverageGap, Job, JobStatus
    from ..creative import breakthrough
    from ..improve import bus, consume
    from . import coverage, pods

    now = _now(now)
    today = today or now.date()
    decided = []
    for g in _open_gaps(db):
        if len(decided) >= REVIEW_LIMIT:
            break
        ev = g["evidence"]
        attempts = list(ev.get("failed_attempts") or [])
        job_id = ev.get("design_job_id")
        if job_id:
            with db.session() as s:
                j = s.get(Job, job_id)
                status, finished = (j.status, j.finished_at) if j is not None else (None, None)
            if finished is not None and finished.tzinfo is None:
                finished = finished.replace(tzinfo=timezone.utc)
            terminal = status in (JobStatus.DONE, JobStatus.DEAD, JobStatus.CANCELLED)
            if not terminal or (finished is not None and now - finished < SETTLE):
                continue                          # in flight, or not yet settled: wait
            attempts.append({"job_id": job_id, "status": getattr(status, "value", status),
                             "ended": finished.isoformat() if finished else None})
            with db.session() as s:
                row = s.get(CoverageGap, g["id"])
                row.evidence = {**(row.evidence or {}), "failed_attempts": attempts,
                                "design_job_id": None}
                flag_modified(row, "evidence")
            if len(attempts) >= MAX_FAILED_ATTEMPTS:
                lesson = bus.publish(db, origin_cell="product_creativity",
                                     subject="creative_rejection",
                                     statement=_lesson_statement(g["pod"], len(attempts)),
                                     evidence_ref=f"watchlist_gap:{g['id']}",
                                     confidence="observed")
                coverage.advance(db, g["id"], coverage.NOT_PURSUING,
                                 reason=f"{len(attempts)} attempts without an engineered "
                                        f"product (lesson {lesson})")
                decided.append(_record_decision(db, g["id"], "stopped_after_failures",
                                                today=today, lesson=lesson,
                                                attempts=len(attempts)) | {"gap": g["id"]})
                continue
        # A lesson from an earlier stopped arena with the same words defers this one.
        against = [l for l in consume.matching(db, "market_radar",
                                               f"watchlist arena {g['pod']} original design "
                                               f"attempts engineered product")
                   if l["direction"] < 0]
        if against:
            consume.act(db, "market_radar", against,
                        how=f"watchlist gap {g['id']} ({g['pod']}) deferred by the lesson")
            decided.append(_record_decision(db, g["id"], "deferred_by_lesson", today=today,
                                            lessons=[l["id"] for l in against])
                           | {"gap": g["id"]})
            continue
        pod = pods.BY_KEY.get(g["pod"])
        from ..radar.opportunity import POOL

        answered = [sd.slug for sd in POOL if pod is not None
                    and pod.matches(sd.slug.replace("-", " "))]
        attempt = len(attempts) + 1
        if answered:
            job = enqueue("market_radar", "radar.score",
                          {"handoff": {"source": "intel.opportunity_review", "gap": g["id"],
                                       "pool_concepts": answered[:10]}},
                          idempotency_key=f"watchlist_score:{g['id']}:{attempt}")
            how = "pool concepts answer the arena: radar.score -> pre-engineering gate"
        else:
            inputs = breakthrough.release_brief(db, arena=g["pod"], pod=g["pod"],
                                                listing_ref="")
            inputs.update({"watchlist_gap_id": g["id"], "attempt": attempt,
                           "source": "intel.opportunity_review"})
            job = enqueue("creative_director", "creative.tournament", inputs,
                          idempotency_key=f"watchlist_design:{g['id']}:{attempt}")
            how = "no pool concept answers it: an original divergent tournament is briefed"
        if job is None:
            continue                              # this attempt is already queued
        with db.session() as s:
            row = s.get(CoverageGap, g["id"])
            row.evidence = {**(row.evidence or {}), "design_job_id": job.id,
                            "design_started_on": today.isoformat(), "design_how": how}
            flag_modified(row, "evidence")
        decided.append(_record_decision(db, g["id"], "routed", today=today, job_id=job.id,
                                        job_type=job.job_type, how=how, attempt=attempt)
                       | {"gap": g["id"]})
    return {"decisions": decided, "work_done": len(decided)}
