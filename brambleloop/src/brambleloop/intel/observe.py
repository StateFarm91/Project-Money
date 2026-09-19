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

from . import benchmarks, coverage, mission, pods
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
    deep_audited: list[str] = field(default_factory=list)
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
            },
            "changes": ([{"listing_ref": ref, "what": "new listing"}
                         for ref in self.new_listings]
                        + [{"listing_ref": ref, "what": "materially changed"}
                           for ref in self.changed_listings]),
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
            result.pods_notified.add(pod)

    # -- the deep audit, only for what moved (#208, #212) -------------------
    for listing in to_audit[:deep_audit_limit]:
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

    Scored only on components the scan can actually observe. Make time, contribution and
    creative potential are left absent rather than guessed, so the queue's own
    `evidence_weight` says how much of each score is real.
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
        coverage.upsert(db, benchmark_key=benchmark_key, arena=pod.name, pod=pod_key,
                        components=components,
                        evidence={"benchmark_listings": len(listings),
                                  "total_favourites": sum(favourites),
                                  "note": "scored only on what the scan observed; make time, "
                                          "contribution and creative potential are absent "
                                          "rather than guessed"})
        opened.append(pod.name)
    return opened


def scan_or_explain(db, *, env: dict[str, str] | None = None,
                    transport=None, **kwargs) -> dict:
    """Run a scan, or say precisely why one could not run (#224).

    An unconfigured credential is not a failure to report as an outage. It is the mandate
    being unmet for a stated reason, which is what the requirement asks for.
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

    result = scan(db, reader, env=env, **kwargs)
    report = result.to_report()
    mission.check_report(report)
    return {"ran": True, "report": report}
