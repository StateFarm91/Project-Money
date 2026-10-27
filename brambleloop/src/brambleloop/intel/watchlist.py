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
# Review INTELREC M-3: the watchlist runs the mission for non-anchor shops WITHOUT starting
# paid work. These job types spend (model/render/vision); a non-anchor mission step that asks
# for one is recorded as withheld. Paid design stays the creative director's own budgeted
# cadence; widening it is an owner spend decision.
# Review 720b291 N-7: derived from the worker's own model-bearing list (never hand-copied),
# plus the render jobs, which spend but are not model jobs. Read as `PAID_JOB_TYPES`.
RENDER_JOB_TYPES = frozenset({"assets.owned_photography", "assets.model_photography"})


def paid_job_types() -> frozenset:
    from ..runtime.worker import MODEL_JOB_TYPES

    return frozenset(MODEL_JOB_TYPES) | RENDER_JOB_TYPES


def __getattr__(name):  # PEP 562: lazy, so importing this module never imports the worker
    if name == "PAID_JOB_TYPES":
        return paid_job_types()
    raise AttributeError(name)


# L-6: a shop whose reads fail is retried with exponential backoff, never every run.
BACKOFF_BASE = timedelta(hours=6)
BACKOFF_CAP = timedelta(days=7)
# N-1: the exponent is capped BEFORE the multiplication (6 h x 2^5 > 7 days), so a shop that
# has failed for months never overflows timedelta.
BACKOFF_MAX_EXPONENT = 5


def backoff_for(fails: int) -> timedelta:
    return min(BACKOFF_CAP, BACKOFF_BASE * (2 ** min(max(fails - 1, 0), BACKOFF_MAX_EXPONENT)))

ANCHOR, SPECIAL, PERMANENT = "anchor", "special", "permanent"
# D-W4-OWNER-SEEDSHOPS (2026-10-27): the original spec/05 seed shops, preserved.
SEED = "seed"
# A shop the sanctioned read path cannot reach (closed, renamed, not found). Recorded as a
# dated limitation; the member and its monitoring job are kept; it is never "scanned".
NOT_ACCESSIBLE = "not_accessible"
NOT_FOUND_STATUSES = (404, 410)


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
) + tuple(
    # D-W4-OWNER-SEEDSHOPS: "preserve the original seed-shop requirements for HanJanCrochet,
    # IvyLoop, LoveandStitchDesigns and FireflyCrochets. Do not silently drop any original
    # benchmark."
    Member(spec.key, spec.shop_name, spec.owner_supplied_url, SEED, False)
    for spec in benchmarks.SEED_SHOPS
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


class _OnceReader:
    """Review L-6: one scan resolves the shop once, not once per step (scan, reviews)."""

    def __init__(self, inner):
        self._inner, self._shops = inner, {}

    def resolve_shop(self, name):
        if name not in self._shops:
            self._shops[name] = self._inner.resolve_shop(name)
        return self._shops[name]

    def __getattr__(self, attr):
        return getattr(self._inner, attr)


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
        fails = int(st.get("consecutive_failures") or 0)
        last = st.get("last_attempt_at")
        if fails and last and st.get("state") in ("source_outage", "credential_refused",
                                                   NOT_ACCESSIBLE):
            wait = backoff_for(fails)
            if now - datetime.fromisoformat(last) < wait:
                return {"key": member.key, "ran": False, "deferred": True,
                        "state": st.get("state"),
                        "why": f"backoff after {fails} failure(s): next read after "
                               f"{(datetime.fromisoformat(last) + wait).isoformat()}"}
    reader = _OnceReader(reader)
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
            read = int(themes.get("reviews_read") or 0)
            # L-2: zero reviews read is UNMEASURED, not "no recurring complaint".
            reviews = {"read": read,
                       "recurring_themes": (len(themes.get("recurring") or [])
                                            if read else None)}
    except ReadFailed as exc:
        if not exc.credential_refused and _not_found(exc):
            return _record_not_accessible(db, member, st, str(exc), now=now)
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
        withheld: list[str] = []
        paid = paid_job_types()

        def unpaid(agent, job_type, inputs, **kw):
            if job_type in paid:
                withheld.append(job_type)
                return None
            return enqueue(agent, job_type, inputs, **kw)
        # N-5: the mission reads this and records "withheld", never "already queued".
        unpaid.withholds = paid

        m = mission_runtime.process(db, enqueue=unpaid, today=now.date(),
                                    benchmark_key=member.key, limit=MISSION_LIMIT)
        mission_out = {"pending": m["pending"], "processed": m["processed"],
                       "paid_work_withheld": withheld}
    return {"key": member.key, "ran": True, "listings_seen": st["listings_seen"],
            "changes": st["changes"], "reviews": reviews, "mission": mission_out}


def _not_found(exc) -> bool:
    """The shop itself is not reachable by name (closed, renamed, not found) -- as distinct
    from an outage of the source, which says nothing about the shop."""
    return (getattr(exc, "status", None) in NOT_FOUND_STATUSES
            or "was not found exactly" in str(exc))


def alternative_evidence(member: Member) -> str:
    """The permitted alternative evidence for a shop the read path cannot reach: the dated
    public-profile observation the owner seeded (commercial signals only), if one exists."""
    from ..radar.market import COMPETITORS

    prof = next((c for c in COMPETITORS if c.shop.lower() == member.shop_name.lower()), None)
    if prof is None:
        return "none on file"
    return (f"radar.market.COMPETITORS[{prof.shop}] public-profile seed observation, "
            f"observed {prof.observed_on} (price band, formats, badges; no content)")


def _record_not_accessible(db, member: Member, st: dict, reason: str, *,
                           now: datetime) -> dict:
    """D-W4-OWNER-SEEDSHOPS: "Where a shop cannot be accessed through an authorized source,
    record the limitation, preserve the monitoring job and use permitted alternative evidence.
    Do not pretend an inaccessible shop was scanned." Nothing scan-shaped is written: no
    last_ok_at, no listings_seen, no shop counters, no mission."""
    limitation = f"not accessible: {reason}"[:300]
    st.update(state=NOT_ACCESSIBLE, limitation=limitation, limitation_on=now.date().isoformat(),
              last_error=limitation, last_attempt_at=now.isoformat(),
              consecutive_failures=int(st.get("consecutive_failures") or 0) + 1,
              alternative_evidence=alternative_evidence(member), monitoring="kept")
    _save_state(db, member.key, st, now=now)
    return {"key": member.key, "ran": False, "scanned": False, "state": NOT_ACCESSIBLE,
            "limitation": limitation, "on": now.date().isoformat(),
            "alternative_evidence": st["alternative_evidence"],
            "consecutive_failures": st["consecutive_failures"]}


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
        # Review M-1: recorded per shop, so Laura's provider does not read an unobserved
        # watchlist as OK.
        for m in members:
            st = _state(db, m.key)
            st.update(state="credential_refused", last_attempt_at=now.isoformat(),
                      last_error="Etsy refused the read credential at the last etsy.probe")
            _save_state(db, m.key, st, now=now)
        return {"ran": False, "reason": "Etsy refused the read credential at the last "
                                        "etsy.probe; the watchlist waits for a probe to "
                                        "succeed rather than knocking with a refused key",
                "shops": [], "substituted": False}
    shops = []
    for m in members:
        # N-1: one shop's unexpected fault never stops the others or fails the job.
        try:
            shops.append(scan_member(db, m, reader, now=now, enqueue=enqueue, force=force))
        except Exception as exc:  # noqa: BLE001
            st = _state(db, m.key)
            st.update(state="source_outage", last_attempt_at=now.isoformat(),
                      last_error=f"{type(exc).__name__}: {exc}"[:300],
                      consecutive_failures=int(st.get("consecutive_failures") or 0) + 1)
            _save_state(db, m.key, st, now=now)
            shops.append({"key": m.key, "ran": False, "state": "source_outage",
                          "consecutive_failures": st["consecutive_failures"]})
    return {"ran": True, "shops": shops,
            "observed": sum(1 for s in shops if s.get("ran")),
            "outages": [s["key"] for s in shops if s.get("state") in
                        ("source_outage", "credential_refused")],
            "not_accessible": [{"key": s["key"], "limitation": s.get("limitation"),
                                "on": s.get("on")} for s in shops
                               if s.get("state") == NOT_ACCESSIBLE]}


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
        state = st.get("state") or ("rows_present" if listings else "never")
        # Review L-1: a figure carried over from an earlier read while this shop's latest
        # read failed is STALE, not MEASURED. (L-3: the anchor has no watchlist read state;
        # stored rows are labelled rows_present, never "ok".)
        fresh = state in ("ok", "rows_present")

        def G(value, source, at, basis="MEASURED"):
            return _grade(value, source, at, basis if fresh else "STALE")
        shops.append({
            "alias": alias, "role": m.role, "special_monitoring": m.special,
            "observation": {"state": state,
                            "last_ok_at": st.get("last_ok_at"),
                            "consecutive_failures": st.get("consecutive_failures", 0)},
            "figures": {
                "listings_observed": G(listings or None, src, as_of),
                "new_listings_7d": G(sum(g["new_7d"] for g in groups) if groups else None,
                                          src, as_of, "DERIVED"),
                "price_median_cad": G(round(statistics.median(prices), 2) if prices
                                           else None, src, as_of),
                "on_sale_share": G(round(sum(g["on_sale_share"] * g["listings"]
                                                  for g in groups) / listings, 3)
                                        if listings else None, src, as_of),
                "gallery_median_images": G(statistics.median(media) if media else None,
                                                src, as_of),
                "category_mix": G(dict(sorted(mix.items())) or None, src, as_of,
                                       "DERIVED"),
                "public_sales": G(shop.get("transaction_sold_count"), "findShops", as_of),
                "review_count": G(shop.get("review_count"), "findShops", as_of),
                "review_average": G(shop.get("review_average"), "findShops", as_of),
                "shop_favourites": G(shop.get("num_favorers"), "findShops", as_of),
                "recurring_complaint_themes": G(
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
        task = _research_question(db, gid, a["pod"], now=now)
        if task is not None:
            _merge_gap_evidence(db, gid, {"research_task_id": task})
        opened.append(gid)
    return {"report": rep, "gaps": opened}


def _research_question(db, gap_id: int, pod: str, *, now: datetime) -> int | None:
    """G6 (F-401/F-429): every validated arena is also a question for the Research Agent --
    durable demand or a passing trend? Opened once per gap (research dedupes on the
    trigger), answered from internal evidence first by `research.sweep`/`investigate`."""
    from . import research

    try:
        got = research.open_question(
            db, question=(f"Is buyer demand in the {pod} arena durable across the owner's "
                          f"watchlist shops, or a passing trend?"),
            trigger=f"watchlist_gap:{gap_id}",
            decision_ref=f"intel.opportunity_review:gap:{gap_id}", domain="market_radar",
            query_terms=[pod],
            evidence_needed=("new-listing cadence and favourites in this arena across "
                             "successive watchlist scans, and our own lessons about it"),
            stop_condition="answered from internal evidence, or the time bound passes",
            if_unresolved=("decide from the cross-shop corroboration alone and record the "
                           "uncertainty on the decision"),
            time_bound_days=14, now=now)
    except Exception:  # noqa: BLE001 - research never blocks the comparison
        return None
    return got.get("task")


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
    """Laura's `intelligence` provider.

    Review M-1: UNKNOWN while any watchlist shop has never been read, or cannot be read
    (no credential / refused credential) -- an unobserved watchlist is not OK. DEGRADED on a
    source outage, a stale observation, or a validated opportunity awaiting a decision.
    """
    now = _now()
    outages, stale, unobserved, limited = [], [], [], []
    for m in WATCHLIST:
        if m.role == ANCHOR:
            continue
        st = _state(db, m.key)
        alias = benchmark_alias_safe(m.key)
        state = st.get("state")
        last = st.get("last_ok_at")
        if state == "source_outage" and \
                int(st.get("consecutive_failures") or 0) >= OUTAGE_FAILURES:
            outages.append(f"{alias}:{state}")
        if state == NOT_ACCESSIBLE:
            # D-W4-OWNER-SEEDSHOPS: a recorded limitation, never an observation.
            limited.append(f"{alias}:not accessible since {st.get('limitation_on')}")
            continue
        if state in ("not_configured", "credential_refused") or not last:
            unobserved.append(f"{alias}:{state or 'never'}")
            continue
        if now - datetime.fromisoformat(last) > STALE_AFTER:
            stale.append(alias)
    waiting = [g for g in _open_gaps(db) if not (g["evidence"] or {}).get("design_job_ids")
               and not _parked(db, g, now.date())]
    reasons = []
    if unobserved:
        reasons.append(f"not observed: {unobserved}")
    if waiting:
        reasons.append(f"{len(waiting)} validated watchlist opportunit"
                       f"{'y' if len(waiting) == 1 else 'ies'} awaiting a decision")
    if outages:
        reasons.append(f"source outage: {outages}")
    if limited:
        reasons.append(f"limitation recorded (monitoring kept): {limited}")
    if stale:
        reasons.append(f"observation older than {int(STALE_AFTER.total_seconds() // 3600)} h: "
                       f"{stale}")
    # N-6: a known problem (outage, stale, waiting) is DEGRADED even when another shop is
    # unobserved; UNKNOWN only when being unobserved is the whole story.
    status = ("DEGRADED" if (outages or stale or waiting or limited) else
              "UNKNOWN" if unobserved else "OK")
    return {"status": status, "reason": "; ".join(reasons),
            "as_of": now.isoformat(), "waiting": [g["id"] for g in waiting],
            "outages": outages, "stale": stale, "unobserved": unobserved,
            "not_accessible": limited}


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


PARKED = ("deferred_by_lesson", "needs_original_design", "route_refused",
          "repeat_measurement")
REDECIDE_AFTER = timedelta(days=7)


def _fingerprint(g: dict) -> list:
    return sorted((g.get("evidence") or {}).get("corroborated_by") or [])


def _parked(db, g: dict, today: date) -> bool:
    """Review L-4: a deferred or needs-original-design gap is not re-decided every day. It is
    re-opened when the corroborating shops change, or after REDECIDE_AFTER."""
    d = _decision(db, g["id"])
    if d.get("last") not in PARKED or not d.get("on"):
        return False
    if d.get("fingerprint") is not None and d["fingerprint"] != _fingerprint(g):
        return False
    return today - date.fromisoformat(d["on"]) < REDECIDE_AFTER


def _record_decision(db, gap_id: int, decision: str, *, today: date, **detail) -> dict:
    from ..autonomy import memory

    body = _decision(db, gap_id)
    hist = list(body.get("history") or [])[-19:]
    hist.append({"on": today.isoformat(), "decision": decision, **detail})
    body.update(last=decision, on=today.isoformat(), history=hist,
                fingerprint=detail.get("fingerprint"))
    memory.remember(db, f"{DECISION_PREFIX}{gap_id}", kind="intel.opportunity_decision",
                    department="intelligence", subject=f"watchlist gap {gap_id}",
                    state=decision, body=body, sources=["coverage_gaps", COMPARE_READING])
    return body


def _research_state(db, task_id) -> str:
    if not task_id:
        return "none opened"
    from .research import ResearchTask

    with db.session() as s:
        t = s.get(ResearchTask, int(task_id))
        return "missing" if t is None else str(t.state)


def _lesson_statement(pod: str, n: int) -> str:
    return (f"watchlist arena {pod}: {n} scored attempts with pool concepts did not clear "
            f"promotion, so stop re-asking this arena until new evidence arrives")


def score_outcome(db, job_ids, *, now: datetime, settle: timedelta = SETTLE) -> dict:
    """Review H-1 / L-5: what the routed radar.score jobs actually produced.

    wait          -- a job is still in flight or has not settled
    progressed    -- a concept was promoted (scored and cleared the pre-engineering gate)
    failed        -- concepts were MEASURED (a score was computed) and none was promoted
    not_attempted -- nothing was measured: refused, parked, dead or missing jobs are not
                     an attempt and teach nothing
    """
    from ..core.models import Job, JobStatus

    measured, promoted, refused = [], [], []
    for jid in job_ids or []:
        with db.session() as s:
            j = s.get(Job, int(jid))
            if j is None:
                refused.append({"job_id": jid, "why": "missing"})
                continue
            status, finished, out = j.status, j.finished_at, dict(j.outputs or {})
        if finished is not None and finished.tzinfo is None:
            finished = finished.replace(tzinfo=timezone.utc)
        if status not in (JobStatus.DONE, JobStatus.DEAD, JobStatus.CANCELLED):
            return {"outcome": "wait", "why": f"job {jid} is {getattr(status, 'value', status)}"}
        if finished is not None and now - finished < settle:
            return {"outcome": "wait", "why": f"job {jid} has not settled"}
        gate = out.get("gate") or {}
        if status != JobStatus.DONE or not isinstance(out.get("score"), (int, float)):
            refused.append({"job_id": jid, "status": getattr(status, "value", status),
                            "why": str(out.get("reason") or j.last_error or "no score")[:120]})
        elif not out.get("promoted") and (str(gate.get("decision") or "").lower() == "waiting"
                                          or gate.get("unmeasured")):
            # N-3: the gate is waiting on a judgement nobody has made -- nothing was measured.
            refused.append({"job_id": jid, "status": "gate_waiting",
                            "why": f"gate waiting on {gate.get('waiting_on') or gate.get('unmeasured')}"[:120]})
        elif out.get("promoted"):
            promoted.append({"job_id": jid, "slug": out.get("slug"), "score": out["score"]})
        else:
            measured.append({"job_id": jid, "slug": out.get("slug"), "score": out["score"],
                             "discount": (out.get("evidence") or {}).get("discount")})
    if promoted:
        return {"outcome": "progressed", "promoted": promoted, "measured": measured,
                "refused": refused}
    if measured:
        return {"outcome": "failed", "measured": measured, "refused": refused,
                "signature": sorted([m["slug"] or "", m["score"], m["discount"]]
                                    for m in measured)}
    return {"outcome": "not_attempted", "refused": refused}


def queue_scores(db, enqueue, slugs, *, key: str, context: dict, today: date) -> list[int]:
    """Non-spending route: one radar.score per pool concept (score + pre-engineering gate).
    Review M-2/M-4: Laura-delegable work never queues a paid job."""
    from ..radar.intake import pool_with_intake
    from ..radar.opportunity import score_concept

    # W5-CONCEPT: POOL plus the concepts radar.intake approved from recorded evidence.
    by_slug = {sd.slug: sd for sd in pool_with_intake(db)}
    ids = []
    for slug in slugs:
        sd = by_slug.get(slug)
        if sd is None:
            continue
        payload = score_concept(sd, today).to_dict()
        payload.update(context)
        job = enqueue("market_radar", "radar.score", payload,
                      idempotency_key=f"{key}:{slug}")
        if job is not None:
            ids.append(job.id)
    return ids


def review(db, *, enqueue, today: date | None = None, now: datetime | None = None) -> dict:
    """One decision per validated opportunity. Bounded, idempotent, lesson-aware, and
    non-spending: the only job it queues is radar.score. An arena no pool concept answers
    is recorded `needs_original_design` (an original paid design is the creative
    director's own budgeted cadence, not Laura's CA$0 delegation -- G14)."""
    from sqlalchemy.orm.attributes import flag_modified

    from ..core.models import CoverageGap
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
        job_ids = ev.get("design_job_ids")
        if job_ids:
            res = score_outcome(db, job_ids, now=now)
            if res["outcome"] == "wait":
                continue
            with db.session() as s:
                row = s.get(CoverageGap, g["id"])
                upd = {"design_job_ids": None}
                sig = {"fingerprint": _fingerprint(g), "scores": res.get("signature")}
                repeat = bool(res["outcome"] == "failed" and attempts
                              and attempts[-1].get("signature") == sig)
                if res["outcome"] == "failed" and not repeat:
                    attempts.append({"job_ids": job_ids, "measured": res["measured"],
                                     "signature": sig, "on": today.isoformat()})
                    upd["failed_attempts"] = attempts
                elif res["outcome"] == "not_attempted":
                    upd["refused_routes"] = (list(ev.get("refused_routes") or [])[-9:]
                                             + [{"job_ids": job_ids, "on": today.isoformat(),
                                                 "refused": res["refused"]}])
                row.evidence = {**(row.evidence or {}), **upd}
                flag_modified(row, "evidence")
            if res["outcome"] == "progressed":
                slug = res["promoted"][0]["slug"] or ""
                coverage.advance(db, g["id"], coverage.CONCEPTING,
                                 reason=f"radar.score promoted {slug} for this arena",
                                 product_slug=slug)
                decided.append(_record_decision(db, g["id"], "progressed", today=today,
                                                promoted=res["promoted"]) | {"gap": g["id"]})
                continue
            if repeat:
                # N-3: the same deterministic measurement on the same evidence is one
                # measurement, not a second independent attempt. Parked (L-4).
                decided.append(_record_decision(db, g["id"], "repeat_measurement",
                                                today=today, fingerprint=_fingerprint(g))
                               | {"gap": g["id"]})
                continue
            if res["outcome"] == "not_attempted":
                # Parked like a deferral (L-4): re-routed after REDECIDE_AFTER or new evidence.
                decided.append(_record_decision(db, g["id"], "route_refused", today=today,
                                                fingerprint=_fingerprint(g),
                                                refused=res["refused"][:5])
                               | {"gap": g["id"]})
                continue
            if len(attempts) >= MAX_FAILED_ATTEMPTS:
                lesson = bus.publish(db, origin_cell="product_creativity",
                                     subject="creative_rejection",
                                     statement=_lesson_statement(g["pod"], len(attempts)),
                                     evidence_ref=f"watchlist_gap:{g['id']}",
                                     confidence="observed")
                coverage.advance(db, g["id"], coverage.NOT_PURSUING,
                                 reason=f"{len(attempts)} measured attempts without a "
                                        f"promoted concept (lesson {lesson})")
                decided.append(_record_decision(db, g["id"], "stopped_after_failures",
                                                today=today, lesson=lesson,
                                                attempts=len(attempts)) | {"gap": g["id"]})
                continue
        if _parked(db, g, today):
            continue
        against = [l for l in consume.matching(db, "market_radar",
                                               f"watchlist arena {g['pod']} scored attempts "
                                               f"pool concepts promotion")
                   if l["direction"] < 0]
        if against:
            consume.act(db, "market_radar", against,
                        how=f"watchlist gap {g['id']} ({g['pod']}) deferred by the lesson")
            decided.append(_record_decision(db, g["id"], "deferred_by_lesson", today=today,
                                            fingerprint=_fingerprint(g),
                                            lessons=[l["id"] for l in against])
                           | {"gap": g["id"]})
            continue
        pod = pods.BY_KEY.get(g["pod"])
        from ..radar.intake import pool_with_intake

        # W5-CONCEPT: an arena an approved intake concept answers is routed like a POOL one.
        answered = [sd.slug for sd in pool_with_intake(db) if pod is not None
                    and pod.matches(sd.slug.replace("-", " "))]
        if not answered:
            decided.append(_record_decision(
                db, g["id"], "needs_original_design", today=today,
                fingerprint=_fingerprint(g),
                how=("no pool concept answers this arena; an original design is paid "
                     "creative work outside Laura's CA$0 delegation (G14, proposed)"))
                | {"gap": g["id"]})
            continue
        attempt = len(attempts) + 1
        route = int(ev.get("routes") or 0) + 1       # a refused route is retried on a fresh key
        ids = queue_scores(db, enqueue, answered[:10],
                           key=f"watchlist_score:{g['id']}:{route}",
                           context={"coverage_gaps": [g["id"]],
                                    "source": "intel.opportunity_review"}, today=today)
        if not ids:
            continue                              # this attempt is already queued
        how = "pool concepts answer the arena: radar.score -> pre-engineering gate"
        with db.session() as s:
            row = s.get(CoverageGap, g["id"])
            row.evidence = {**(row.evidence or {}), "design_job_ids": ids, "routes": route,
                            "design_started_on": today.isoformat(), "design_how": how}
            flag_modified(row, "evidence")
        decided.append(_record_decision(db, g["id"], "routed", today=today, job_ids=ids,
                                        job_type="radar.score", how=how, attempt=attempt,
                                        research_task_id=ev.get("research_task_id"),
                                        research=_research_state(db, ev.get(
                                            "research_task_id")))
                       | {"gap": g["id"]})
    return {"decisions": decided, "work_done": len(decided)}
