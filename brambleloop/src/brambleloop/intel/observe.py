"""The benchmark scan: baseline, then only what changed.

Requirements 207, 208, 212, 213, 214, 303, 313, 314, 319. The pieces this joins already
exist — the read-only Etsy client, the pods, the coverage queue, the evidence grading — and
what was missing is the thing that drives them on a schedule.

Written now, with no credential in the environment, on purpose. The owner approved the Etsy
application and the key does not exist yet, and the standing rule is to route around a blocked
integration and continue everything else. A pipeline written the day the key arrives is a
pipeline debugged against a live marketplace; this one is driven by an injected reader, so
every branch — first baseline, unchanged catalogue, new listing, changed listing, vanished
listing — is exercised before it ever touches Etsy.

**Baseline once, then change detection (#212).** Re-reading a whole catalogue every few hours
is the expensive way to learn nothing. Each listing carries a content fingerprint; a scan that
finds the fingerprint unchanged does no further work and pays for nothing. The deep audit —
opening the listing, traversing the gallery — runs only for listings that are new or have
actually moved.

**What a scan produces is evidence, not a status line (#319).** Every run records which shop,
at what time, how much of the catalogue is known versus inspected, what changed, which images
were seen, which pods received it and what happened as a result. `mission.check_report()`
refuses anything less.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from . import benchmarks, coverage, deliverable, mission, pods
from .cadence import INTERVALS_SECONDS as _CADENCE_LADDER
from .etsy_public import NotConfigured, PublicReader, ReadFailed

# Fields that decide whether a listing has *commercially* changed. Deliberately not every
# field Etsy returns: `views` moves every hour and means nothing on its own, and treating it
# as a change would make the fingerprint useless by making it always different.
FINGERPRINTED = ("title", "description", "price", "tags", "materials", "state",
                 "last_modified_timestamp", "num_favorers")


@dataclass
class ScanResult:
    benchmark: str
    observed_at: str
    listings_known: int = 0
    listings_seen: int = 0
    new_listings: list[str] = field(default_factory=list)
    changed_listings: list[str] = field(default_factory=list)
    unchanged: int = 0
    withdrawn: list[str] = field(default_factory=list)
    deep_audited: list[str] = field(default_factory=list)
    # Galleries read to close the backlog rather than because the listing moved.
    backfilled: list[str] = field(default_factory=list)
    # Unchanged listings whose description was read for the first time (#2). Separate from
    # `backfilled` because it costs no request: the description came with the catalogue page.
    deliverable_backfilled: list[str] = field(default_factory=list)
    images_inspected: int = 0
    pods_notified: set = field(default_factory=set)
    gaps_opened: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    baseline: bool = False

    def to_report(self) -> dict:
        """The shape #319 demands, and `mission.check_report` enforces."""
        return {
            "benchmark": self.benchmark,
            "observed_at": self.observed_at,
            "catalogue_coverage": {
                "listings_known": self.listings_known,
                "listings_seen_this_scan": self.listings_seen,
                "listings_inspected": len(self.deep_audited),
                "unchanged_skipped": self.unchanged,
                "withdrawn_since_last_scan": len(self.withdrawn),
                "galleries_backfilled": len(self.backfilled),
                "descriptions_read_for_the_first_time": len(self.deliverable_backfilled),
            },
            "changes": ([{"listing_ref": ref, "what": "new listing"}
                         for ref in self.new_listings]
                        + [{"listing_ref": ref, "what": "materially changed"}
                           for ref in self.changed_listings]
                        + [{"listing_ref": ref, "what": "no longer listed"}
                           for ref in self.withdrawn]),
            "listings_inspected": list(self.deep_audited),
            "images_inspected": self.images_inspected,
            "pods_notified": sorted(self.pods_notified),
            "actions": ([f"opened a coverage gap for {arena}" for arena in self.gaps_opened]
                        or ["no new arena required a coverage gap this scan"]),
            "baseline": self.baseline,
            "problems": list(self.problems),
        }


def _price_cad(listing: dict) -> float:
    """Etsy returns money as {amount, divisor, currency_code}."""
    price = listing.get("price") or {}
    if isinstance(price, dict) and price.get("divisor"):
        try:
            return round(float(price["amount"]) / float(price["divisor"]), 2)
        except (TypeError, ValueError, ZeroDivisionError):
            return 0.0
    try:
        return round(float(price), 2)
    except (TypeError, ValueError):
        return 0.0


def fingerprint_of(listing: dict) -> str:
    return pods.fingerprint({k: listing.get(k) for k in FINGERPRINTED})


def scan(db, reader: PublicReader, *, benchmark_key: str = benchmarks.MJS_KEY,
         shop_name: str = benchmarks.MJS_SHOP, deep_audit_limit: int = 25,
         backfill_limit: int = 40,
         env: dict[str, str] | None = None) -> ScanResult:
    """One pass over the benchmark catalogue. Cheap unless something moved."""
    from sqlalchemy import select

    from ..core.models import Benchmark, BenchmarkListing

    now = datetime.now(timezone.utc)
    result = ScanResult(benchmark=shop_name, observed_at=now.isoformat())

    shop = reader.resolve_shop(shop_name)
    shop_id = shop.get("shop_id")
    listings = reader.catalogue(shop_id)
    result.listings_seen = len(listings)

    with db.session() as s:
        known = {row.listing_ref: row for row in s.scalars(
            select(BenchmarkListing).where(
                BenchmarkListing.benchmark_key == benchmark_key))}
    result.baseline = not known

    to_audit: list[dict] = []
    with db.session() as s:
        for listing in listings:
            ref = str(listing.get("listing_id"))
            digest = fingerprint_of(listing)
            title = listing.get("title") or ""
            pod = pods.route(title, listing.get("taxonomy_id") and str(
                listing.get("taxonomy_id")) or "")
            row = known.get(ref)

            if row is None:
                row = BenchmarkListing(benchmark_key=benchmark_key, listing_ref=ref,
                                       first_seen=now)
                s.add(row)
                result.new_listings.append(ref)
                to_audit.append(listing)
            elif row.fingerprint != digest:
                result.changed_listings.append(ref)
                to_audit.append(listing)
                row = s.merge(row)
            else:
                result.unchanged += 1
                row = s.merge(row)
                row.last_seen = now
                # A new reading of a field already in this payload must reach the listings
                # that did not change, or it only ever describes the shop's recent edits.
                # This is what the gallery backlog taught: a reading attached to the
                # new-or-changed branch covered 25 of 438 listings and had no path to the
                # rest. Unlike the gallery this costs nothing -- the description arrived with
                # the catalogue page -- so the whole map closes on the next scan.
                if "deliverable" not in (row.detail or {}):
                    facts = deliverable.read(listing)
                    sizes = deliverable.size_range(listing, pod=row.pod)
                    filled = dict(row.detail or {})
                    if facts is not None:
                        filled["deliverable"] = facts
                    if sizes is not None:
                        filled["size_range"] = sizes
                    if filled != (row.detail or {}):
                        row.detail = filled
                        result.deliverable_backfilled.append(ref)
                continue

            row.title = title
            row.url = listing.get("url") or ""
            row.pod = pod
            row.product_type = str(listing.get("taxonomy_id") or "")
            row.fingerprint = digest
            row.price_cad = _price_cad(listing)
            row.on_sale = bool(listing.get("is_sale") or False)
            row.last_seen = now
            row.audit_state = "queued"
            row.detail = {"tags": listing.get("tags") or [],
                          "materials": listing.get("materials") or [],
                          "num_favorers": listing.get("num_favorers"),
                          "who_made": listing.get("who_made"),
                          "when_made": listing.get("when_made")}
            # #2's last unmeasured weakness: whether the listing says what arrives. The
            # description is already in this payload and nothing was reading it. It is read
            # here and discarded with the payload -- what is stored is the fact set, which is
            # a fact about a category, not the seller's copy.
            facts = deliverable.read(listing)
            if facts is not None:
                row.detail["deliverable"] = facts
            sizes = deliverable.size_range(listing, pod=pod)
            if sizes is not None:
                row.detail["size_range"] = sizes
            result.pods_notified.add(pod)

    # -- the deep audit: what moved first, then the backlog (#208, #212, #303) ----
    #
    # The limit here was a first-scan safeguard and had quietly become a permanent ceiling.
    # A gallery is read when a listing is new or changed, so once the baseline is in, nothing
    # is new, `to_audit` is empty and the deep audit does nothing at all -- which left 413 of
    # 438 galleries unread with no path to ever reading them, and palette permanently absent
    # on 94% of the map. The backfill is the path: changed listings keep their priority, and
    # whatever the shop did not change this cycle is spent on the oldest unread gallery.
    #
    # Cost: at most `deep_audit_limit + backfill_limit` calls per scan, four scans a day,
    # against Etsy's published 5,000 a day. The backlog closes in under a week.
    backfilled: list[str] = []
    if len(to_audit) < deep_audit_limit + backfill_limit:
        audited_refs = {str(x.get("listing_id")) for x in to_audit}
        with db.session() as s:
            pending = [r.listing_ref for r in s.scalars(
                select(BenchmarkListing).where(
                    BenchmarkListing.benchmark_key == benchmark_key).order_by(
                        BenchmarkListing.listing_ref))
                if not (r.detail or {}).get("gallery_audited")
                and r.listing_ref not in audited_refs]
        by_ref = {str(x.get("listing_id")): x for x in listings}
        for ref in pending[:backfill_limit]:
            if ref in by_ref:
                to_audit.append(by_ref[ref])
                backfilled.append(ref)
    result.backfilled = backfilled

    for listing in to_audit[:deep_audit_limit + backfill_limit]:
        ref = str(listing.get("listing_id"))
        try:
            images = reader.images(ref)
        except ReadFailed as e:
            result.problems.append(f"{ref}: gallery unreadable ({e})")
            continue
        result.images_inspected += len(images)
        result.deep_audited.append(ref)

        with db.session() as s:
            row = s.scalar(select(BenchmarkListing).where(
                BenchmarkListing.benchmark_key == benchmark_key,
                BenchmarkListing.listing_ref == ref))
            if row is not None:
                row.media_count = len(images)
                row.audit_state = "audited"
                detail = dict(row.detail or {})
                detail["gallery_audited"] = True
                # Video presence: one of the three weakness signals #2 names that the
                # observation did not carry. A separate call, taken here because this is
                # the listing whose gallery is already being read.
                try:
                    detail["has_video"] = bool(reader.videos(ref))
                except ReadFailed:
                    detail.pop("has_video", None)
                # Etsy publishes its own per-image colour statistics, so palette evidence is
                # available with no vision model at all. What it does not give is judgement
                # about the shot -- that needs the model provider, and until then this is a
                # gallery inventory rather than a gallery analysis.
                detail["palette"] = [
                    {"rank": img.get("rank"), "hex": img.get("hex_code"),
                     "hue": img.get("hue"), "saturation": img.get("saturation"),
                     "brightness": img.get("brightness"),
                     "black_and_white": img.get("is_black_and_white")}
                    for img in images[:12]]
                detail["image_urls"] = [img.get("url_fullxfull") for img in images[:12]]
                row.detail = detail

    # -- reconciliation: what was there last time and is not now ----------
    #
    # A vanished listing is a commercial event -- withdrawn, sold out, renamed or delisted --
    # and deleting the row would destroy the longitudinal evidence that makes it readable. So
    # the row is marked and kept: "we saw this for six weeks and then it stopped" is a
    # finding, and an absent row says nothing at all.
    seen_refs = {str(listing.get("listing_id")) for listing in listings}
    with db.session() as s:
        for ref, row in known.items():
            if ref in seen_refs:
                continue
            live = s.merge(row)
            if live.audit_state != "withdrawn":
                live.audit_state = "withdrawn"
                live.detail = {**(live.detail or {}),
                               "withdrawn_first_noticed": now.isoformat()}
                result.withdrawn.append(ref)

    with db.session() as s:
        result.listings_known = len(list(s.scalars(select(BenchmarkListing).where(
            BenchmarkListing.benchmark_key == benchmark_key))))
        bench = s.scalar(select(Benchmark).where(Benchmark.key == benchmark_key))
        if bench is not None:
            bench.last_scan_at = now
            if result.baseline:
                bench.last_baseline_at = now
            if result.new_listings or result.changed_listings:
                bench.last_change_at = now

    # -- turn uncovered arenas into queued work (#314) ---------------------
    result.gaps_opened = _open_gaps(db, benchmark_key)

    # -- record the evidence at the grade it earns (#224) ------------------
    mission.record(db, benchmark_key=benchmark_key, kind="official_api_read",
                   detail=result.to_report(),
                   pods_notified=tuple(sorted(result.pods_notified)),
                   actions=tuple(f"coverage gap: {a}" for a in result.gaps_opened),
                   env=env)
    return result


def _open_gaps(db, benchmark_key: str) -> list[str]:
    """One gap per pod the benchmark sells into and Brambleloop does not.

    Scored on every component the database can answer: apparent demand and portfolio fit
    from the scan, seasonal timing from the calendar and lead-time engine, search opportunity
    from captured search-result density, and make time from the arena's make hours (#314).
    Expected contribution and creative potential have no evidence yet and stay absent rather
    than guessed, so the queue's own `evidence_weight` says how much of each score is real.
    """
    from sqlalchemy import select

    from ..core.models import BenchmarkListing, Product

    with db.session() as s:
        rows = list(s.scalars(select(BenchmarkListing).where(
            BenchmarkListing.benchmark_key == benchmark_key)))
        ours = [p.slug for p in s.scalars(select(Product))]

    by_pod: dict[str, list] = {}
    for row in rows:
        by_pod.setdefault(row.pod or pods.UNCLASSIFIED, []).append(row)

    opened: list[str] = []
    for pod_key, listings in by_pod.items():
        if pod_key == pods.UNCLASSIFIED:
            continue
        pod = pods.BY_KEY.get(pod_key)
        if pod is None:
            continue
        # Do we already sell into this arena? Matched on the pod's own keywords against our
        # slugs, which is the same routing rule applied to our catalogue.
        covered = any(pod.matches(slug.replace("-", " ")) for slug in ours)
        if covered:
            continue

        favourites = [int(l.detail.get("num_favorers") or 0) for l in listings]
        # A pod the benchmark lists many favourited products in is a pod with demand.
        demand = min(1.0, (sum(favourites) / 2000.0)) if favourites else 0.0
        components = {"apparent_demand": round(demand, 3),
                      "portfolio_fit": min(1.0, len(listings) / 10.0)}
        extra, basis = gap_components(db, pod_key, listings)
        components.update(extra)
        coverage.upsert(db, benchmark_key=benchmark_key, arena=pod.name, pod=pod_key,
                        components=components,
                        evidence={"benchmark_listings": len(listings),
                                  "total_favourites": sum(favourites),
                                  "basis": basis,
                                  "note": "expected contribution and creative potential are "
                                          "absent rather than guessed"})
        opened.append(pod.name)
    return opened


# #314's computable components. The status each lead-time plan reads as, scored: a window a
# maker can still comfortably hit is worth most, a missed one nothing.
TIMING_SCORE: dict[str, float] = {"on_track": 1.0, "past_preferred": 0.6, "at_risk": 0.3,
                                  "missed": 0.0}
# Search results at which a department's shelf counts as fully crowded (log scale).
SERP_CROWDED_AT = 100_000
# A make this long scores zero on make time: nobody finishes it for a near occasion.
MAKE_HOURS_CEILING = 90.0


def gap_components(db, pod_key: str, listings: list) -> tuple[dict, dict]:
    """Seasonal timing, search opportunity and make time for one pod, from rows (#314)."""
    import math

    from sqlalchemy import desc, select

    from ..core.models import SerpSnapshot
    from ..radar.market import SEASONAL_EVENTS
    from ..seasonal.calendar import DEFAULT_DEPARTMENTS, EVENT_DEPARTMENTS
    from ..seasonal.leadtime import compile_launch, next_occurrence
    from .mission_runtime import ARENA_MAKE_HOURS, arena_for

    out: dict[str, float] = {}
    basis: dict[str, str] = {}
    arenas: dict[str, int] = {}
    for row in listings:
        a = arena_for(row.title or "", pod_key)
        if a:
            arenas[a] = arenas.get(a, 0) + 1
    hours = [ARENA_MAKE_HOURS[a] for a in arenas if a in ARENA_MAKE_HOURS]
    if hours:
        mid = sorted(hours)[len(hours) // 2]
        out["make_time"] = round(max(0.0, 1.0 - mid / MAKE_HOURS_CEILING), 3)
        basis["make_time"] = f"median arena make time {mid} h (assumed, radar.market)"
        today = datetime.now(timezone.utc).date()
        events = [e for e in SEASONAL_EVENTS
                  if pod_key in EVENT_DEPARTMENTS.get(e.name, DEFAULT_DEPARTMENTS)]
        if events:
            soonest = min(events, key=lambda e: next_occurrence(e.event_date, today))
            plan = compile_launch(soonest.name, next_occurrence(soonest.event_date, today),
                                  make_hours=mid)
            status = plan.status(today)
            out["seasonal_timing"] = TIMING_SCORE.get(status, 0.0)
            basis["seasonal_timing"] = (f"{soonest.name}: {status}, latest effective launch "
                                        f"{plan.latest_effective_launch.isoformat()}")
    spec = pods.BY_KEY.get(pod_key)
    words = {w.lower() for w in (spec.keywords if spec is not None else ()) if w} | set(arenas)
    with db.session() as s:
        snaps = [(r.query.lower(), r.total_count) for r in s.scalars(
            select(SerpSnapshot).order_by(desc(SerpSnapshot.id)).limit(500))]
    counts = [n for q, n in snaps if n is not None and any(w in q for w in words)]
    if counts:
        density = max(counts)
        out["search_opportunity"] = round(max(0.0, 1.0 - math.log10(max(1, density))
                                              / math.log10(SERP_CROWDED_AT)), 3)
        basis["search_opportunity"] = (f"{density} results on the most crowded captured "
                                       f"query naming this department")
    return out, basis


# ---------------------------------------------------------------------------
# #313: the scan interval follows the benchmark shop's own posting behaviour

# The fixed interval this replaces, and the one used whenever history is too thin to adapt.
FIXED_INTERVAL_SECONDS = 6 * 60 * 60
# Bounds. The floor is courtesy to a sanctioned API and the cost of a scan that finds nothing;
# the ceiling is how stale the named benchmark is ever allowed to get.
ADAPTIVE_FLOOR_SECONDS = 2 * 60 * 60
ADAPTIVE_CEILING_SECONDS = 24 * 60 * 60
# Posting events needed, and the span they must cover, before the history is believed.
MIN_POSTING_EVENTS = 4
MIN_HISTORY_DAYS = 7
# Scans per mean posting gap. Four means a new listing waits on average an eighth of the gap.
SAMPLES_PER_POSTING_GAP = 4
# A run this close to due counts as due, so window jitter cannot skip a whole period.
DUE_TOLERANCE = 0.95
# #213's second input: during a seasonal ramp the interval may not exceed this, whatever the
# posting history says. The cadence ladder's release-run rung (`cadence.INTERVALS_SECONDS[1]`),
# taken from there so the two cannot drift. A quiet shop in October is still a shop whose
# Christmas release, when it comes, is the one the mission exists to catch.
SEASONAL_CEILING_SECONDS = _CADENCE_LADDER[1]


def _aware(value):
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def adaptive_interval(db, *, benchmark_key: str = benchmarks.MJS_KEY,
                      now: datetime | None = None,
                      seasonal: bool | None = None) -> dict:
    """How often to scan, from when the benchmark shop actually posts (#313).

    Posting history is read from `BenchmarkObservation` rows the scan itself writes: each
    non-baseline scan that found a new or materially changed listing is one posting event.
    The mean gap between events, divided by SAMPLES_PER_POSTING_GAP and clamped to
    [floor, ceiling], is the interval. With fewer than MIN_POSTING_EVENTS events or less than
    MIN_HISTORY_DAYS of history the interval is the fixed six hours, and the reason says so:
    adapting to three data points is a guess with a formula attached.
    """
    from sqlalchemy import select

    from ..core.models import BenchmarkObservation

    now = now or datetime.now(timezone.utc)
    with db.session() as s:
        rows = [(_aware(r.at), r.detail or {}) for r in s.scalars(
            select(BenchmarkObservation).where(
                BenchmarkObservation.benchmark_key == benchmark_key,
                BenchmarkObservation.kind == "official_api_read")
            .order_by(BenchmarkObservation.at))]

    scans = [at for at, _d in rows]
    events = [at for at, d in rows
              if not d.get("baseline")
              and any(c.get("what") in ("new listing", "materially changed")
                      for c in (d.get("changes") or []))]
    last_scan = scans[-1] if scans else None
    # #213: seasonal urgency is the second input. Read from the one seasonal calendar through
    # `cadence.seasonal_pressure`, never a second list, so the scanner and the ladder agree on
    # what a ramp is. Injectable so a test can hold the calendar still.
    if seasonal is None:
        from .cadence import seasonal_pressure
        seasonal = seasonal_pressure(now.date())
    base = {"benchmark": benchmark_key, "scans": len(scans), "posting_events": len(events),
            "last_scan_at": last_scan.isoformat() if last_scan else None,
            "floor_seconds": ADAPTIVE_FLOOR_SECONDS,
            "ceiling_seconds": ADAPTIVE_CEILING_SECONDS,
            "seasonal_pressure": bool(seasonal),
            "seasonal_ceiling_seconds": SEASONAL_CEILING_SECONDS}

    def _seasonal(out: dict) -> dict:
        if not seasonal or out["interval_seconds"] <= SEASONAL_CEILING_SECONDS:
            return out
        return {**out, "interval_seconds": SEASONAL_CEILING_SECONDS,
                "bounded_by": "seasonal",
                "reason": (out["reason"] + f"; a commercially meaningful event is inside the "
                           f"planning window, so the interval is held at "
                           f"{SEASONAL_CEILING_SECONDS // 3600} hours (#213 seasonal "
                           f"urgency)")}

    span_days = ((events[-1] - events[0]).total_seconds() / 86400) if len(events) > 1 else 0
    if len(events) < MIN_POSTING_EVENTS or span_days < MIN_HISTORY_DAYS:
        return _seasonal(
            {**base, "adaptive": False, "interval_seconds": FIXED_INTERVAL_SECONDS,
             "reason": (f"history too thin to adapt: {len(events)} posting event(s) over "
                        f"{span_days:.1f} days, against at least {MIN_POSTING_EVENTS} "
                        f"over {MIN_HISTORY_DAYS} days. Using the fixed "
                        f"{FIXED_INTERVAL_SECONDS // 3600}-hour interval")})

    gaps = [(b - a).total_seconds() for a, b in zip(events, events[1:])]
    mean_gap = sum(gaps) / len(gaps)
    raw = mean_gap / SAMPLES_PER_POSTING_GAP
    interval = int(min(ADAPTIVE_CEILING_SECONDS, max(ADAPTIVE_FLOOR_SECONDS, raw)))
    bound = ("floor" if raw < ADAPTIVE_FLOOR_SECONDS else
             "ceiling" if raw > ADAPTIVE_CEILING_SECONDS else "none")
    return _seasonal({**base, "adaptive": True, "interval_seconds": interval,
            "mean_posting_gap_hours": round(mean_gap / 3600, 2), "bounded_by": bound,
            "reason": (f"the shop posted {len(events)} times over {span_days:.1f} days, a "
                       f"mean of {mean_gap / 3600:.1f} hours apart; scanning "
                       f"{SAMPLES_PER_POSTING_GAP} times per gap gives "
                       f"{interval / 3600:.1f} hours"
                       + (f" (held at the {bound})" if bound != "none" else ""))})


def scan_due(db, *, benchmark_key: str = benchmarks.MJS_KEY,
             now: datetime | None = None, seasonal: bool | None = None) -> dict:
    """Whether the adaptive interval has elapsed since the last recorded scan.

    Both of #213's inputs reach the decision: the shop's posting history and, through
    `adaptive_interval`, the seasonal calendar.
    """
    now = now or datetime.now(timezone.utc)
    cadence = adaptive_interval(db, benchmark_key=benchmark_key, now=now, seasonal=seasonal)
    last = cadence["last_scan_at"]
    if last is None:
        return {"due": True, "why": "no scan has been recorded", "cadence": cadence}
    elapsed = (now - datetime.fromisoformat(last)).total_seconds()
    due = elapsed >= cadence["interval_seconds"] * DUE_TOLERANCE
    return {"due": due, "elapsed_seconds": int(elapsed), "cadence": cadence,
            "why": (f"{elapsed / 3600:.1f} hours since the last scan against an interval of "
                    f"{cadence['interval_seconds'] / 3600:.1f}")}


def scan_or_explain(db, *, env: dict[str, str] | None = None,
                    transport=None, adaptive: bool = True, now: datetime | None = None,
                    **kwargs) -> dict:
    """Run a scan, or say precisely why one could not run (#224).

    An unconfigured credential is not a failure to report as an outage. It is the mandate
    being unmet for a stated reason, which is what the requirement asks for.

    With `adaptive` (the default), a scan the adaptive interval says is not yet due is
    deferred rather than run (#313): the cadence can then fire at the floor and the shop's
    own posting rhythm decides how many of those firings do any work.
    """
    from ..integrations.http import UrllibTransport

    try:
        reader = PublicReader(transport or UrllibTransport(), env=env)
        reader._headers()  # noqa: SLF001 - fail here, before any request is built
    except NotConfigured as e:
        return {"ran": False, "reason": str(e),
                "requirements_unmet": [206, 207, 208, 209, 212, 303],
                "substituted": False,
                "note": ("No observation was performed and nothing was approximated from "
                         "search results, screenshots or fixtures (#224).")}

    if adaptive:
        due = scan_due(db, benchmark_key=kwargs.get("benchmark_key", benchmarks.MJS_KEY),
                       now=now)
        if not due["due"]:
            return {"ran": False, "deferred": True,
                    "reason": f"adaptive interval (#313): not due -- {due['why']}",
                    "cadence": due["cadence"]}

    result = scan(db, reader, env=env, **kwargs)
    report = result.to_report()
    mission.check_report(report)
    return {"ran": True, "report": report}


def reclassify(db, *, benchmark_key: str = "", dry_run: bool = False) -> dict:
    """Re-route every stored listing through the current pod vocabulary.

    The scanner routes a listing once, when it first sees it, and then short-circuits on an
    unchanged fingerprint -- which is right for cost and wrong for coverage. It means every
    improvement to the pod vocabulary applies only to listings the benchmark shop happens to
    edit afterwards, so a widening drawn from 58 unrouted titles would leave all 58 unrouted.

    This costs nothing: it re-reads titles already in the table, not Etsy.
    """
    from sqlalchemy import select

    from ..core.models import BenchmarkListing

    benchmark_key = benchmark_key or benchmarks.MJS_KEY
    moves: list[dict] = []
    with db.session() as s:
        rows = list(s.scalars(select(BenchmarkListing).where(
            BenchmarkListing.benchmark_key == benchmark_key)))
        for row in rows:
            current = pods.route(row.title or "", row.product_type or "")
            if current == (row.pod or pods.UNCLASSIFIED):
                continue
            moves.append({"listing_ref": row.listing_ref, "title": (row.title or "")[:120],
                          "from": row.pod or pods.UNCLASSIFIED, "to": current})
            if not dry_run:
                row.pod = current
        if dry_run:
            s.rollback()

    by_move: dict[str, int] = {}
    for m in moves:
        by_move[f'{m["from"]} -> {m["to"]}'] = by_move.get(f'{m["from"]} -> {m["to"]}', 0) + 1
    return {
        "benchmark_key": benchmark_key, "listings": len(rows), "moved": len(moves),
        "dry_run": dry_run,
        "by_move": dict(sorted(by_move.items(), key=lambda kv: -kv[1])),
        "moves": moves[:200],
        "note": ("Re-routing reads titles already stored; it makes no Etsy call and costs "
                 "nothing. A vocabulary improvement that cannot reach the catalogue it was "
                 "drawn from is not an improvement."),
    }


# ---------------------------------------------------------------------------
# Complaint themes (#2's third weakness signal, and #98's customer_pain domain)
#
# A review is a buyer describing a problem with a product in this category. That is demand
# intelligence of the most direct kind available to a shop with no customers of its own, and
# it is the only honest route to the `customer_pain` domain -- which this system had recorded
# as unfeedable on the grounds that "inferring complaints from a competitor's catalogue is
# inventing them". Reading actual reviews is not inferring. It is observing, and the
# distinction is the whole of the difference.
#
# What is stored is a **count per theme**. Never a review's text, never a reviewer, never a
# quotation. A complaint theme is a fact about this category; a review is somebody's words.

COMPLAINT_THEMES: dict[str, tuple[str, ...]] = {
    "instructions_unclear": ("confusing", "unclear", "hard to follow", "couldn't follow",
                             "didn't understand", "poorly written", "vague", "no explanation"),
    "counts_wrong": ("stitch count", "doesn't add up", "wrong count", "error in row",
                     "mistake in the pattern", "typo", "errata", "doesn't work out"),
    "sizing_wrong": ("too small", "too big", "wrong size", "sizing is off",
                     "didn't fit", "runs small", "runs large"),
    "yarn_estimate_wrong": ("ran out of yarn", "not enough yarn", "more yarn than",
                            "yardage", "used way more"),
    "photos_misleading": ("looks different", "not as pictured", "doesn't look like",
                          "misleading photo"),
    "support_slow": ("no response", "never replied", "didn't answer", "waiting for a reply"),
    "delivery_problem": ("didn't receive", "no download", "couldn't download",
                         "link didn't work", "never arrived"),
}

# A theme claimed from fewer reviews than this is one customer's bad day, not a category
# problem. #2 asks for *recurring* complaints, and the word is doing work.
RECURRING_AT = 3


def complaint_themes(reviews: list[dict]) -> dict:
    """Count which problems recur, from review text, without storing any of it.

    Deterministic and keyword-based on purpose. A model reading reviews would summarise them,
    and a summary of somebody's words is a paraphrase of somebody's words -- which is the
    thing the standing constraint is about. A count of matches is a statistic.
    """
    counts: dict[str, int] = {}
    rated = 0
    low_rated = 0
    for review in reviews:
        text = str(review.get("review") or "").lower()
        rating = review.get("rating")
        if isinstance(rating, (int, float)):
            rated += 1
            if rating <= 3:
                low_rated += 1
        if not text:
            continue
        for theme, needles in COMPLAINT_THEMES.items():
            if any(needle in text for needle in needles):
                counts[theme] = counts.get(theme, 0) + 1

    recurring = {t: n for t, n in counts.items() if n >= RECURRING_AT}
    return {
        "reviews_read": len(reviews),
        "reviews_rated": rated,
        "low_rated": low_rated,
        "low_rated_share": round(low_rated / rated, 3) if rated else None,
        "themes": dict(sorted(counts.items(), key=lambda kv: -kv[1])),
        "recurring": dict(sorted(recurring.items(), key=lambda kv: -kv[1])),
        "recurring_at": RECURRING_AT,
        "measurable": bool(reviews),
        "note": ("Counts of classified themes, never a review's text, a reviewer or a "
                 "quotation. A complaint theme is a fact about this category; a review is "
                 "somebody's words. A theme below the recurrence floor is one customer's "
                 "bad day rather than a category problem (#2)."),
    }


def scan_reviews(db, *, shop_name: str = "", reader=None, benchmark_key: str = "",
                 limit: int = 100) -> dict:
    """Read the benchmark shop's reviews and record which complaints recur.

    Stored as a `BenchmarkObservation`, so it carries a date and sits with the rest of the
    mission's evidence rather than in a variable somebody trusts.
    """
    from ..core.models import BenchmarkObservation
    from ..integrations.http import UrllibTransport

    shop_name = shop_name or benchmarks.MJS_SHOP
    benchmark_key = benchmark_key or benchmarks.MJS_KEY
    # Built the way every other reader in this module is built. `PublicReader()` with no
    # transport raises, and the cadence died four times on it before anything was read.
    reader = reader or PublicReader(UrllibTransport())

    shop = reader.resolve_shop(shop_name)
    reviews = reader.reviews(shop.get("shop_id"), limit=limit)
    themes = complaint_themes(reviews)

    with db.session() as s:
        s.add(BenchmarkObservation(
            benchmark_key=benchmark_key, kind="official_api_read",
            grade="mandated", satisfies_mandate=True,
            actions=[f"{themes['reviews_read']} reviews read; "
                     f"{len(themes['recurring'])} recurring complaint theme(s)"],
            detail={"reviews": themes}))
    return themes
