"""MJs findings: what the stored competitor evidence says, written where product work reads it.

Wave 4, lane W4-MJS. The benchmark spine has been observing for weeks -- in production the
`mjs.scan` cadence has read MJsOffTheHookDesigns' 440-listing catalogue every few hours since
2026-09-19 -- and the readers of that evidence each answer one narrow question for one caller
(the outcome price anchor reads a pod's median price, arbitrage reads favourites, the mission
pipeline reads a single new listing). Nothing turned the whole of it into statements a
department can act on: what sells, at what price, presented how, in which season, with what
complaints, and where the opening is.

This module is that synthesis, and it is deliberately small and deterministic:

* `gather(db)` reads only rows earlier scans stored (benchmark listings, review-theme
  observations, judged gallery images, SERP snapshots, coverage gaps, blocked-source audit
  rows). It makes no network call, so it cannot fetch anything the existing provenance,
  robots and authority controls have not already allowed.
* `synthesize(evidence)` turns that into findings. Every finding carries its provenance
  (source, tables, sample size, observation window), a confidence grade -- `observed`,
  `proxy` (a stand-in for the thing named, e.g. favourites for sales) or `unmeasured` -- and
  the downstream consumer it is written for. UNKNOWN is never 0: a quantity with no
  observation is reported as unmeasured with the reason, never as a zero.
* `refresh(db)` stores the findings as one `OperatingReading` per day (kind `mjs.findings`)
  and publishes the actionable ones to the cross-department lesson bus, where the existing
  consumers read them: `radar.score` (Market Radar's `consume.matching`), every creative
  tournament/expedition brief (`creative.ideation.lessons` -> `bus.brief_lessons`), and the
  pricing / portfolio / pattern-engineering / customer-experience inboxes. A finding whose
  numbers have not changed republishes nothing (idempotent on its digest); one whose numbers
  moved supersedes its previous lesson, so an inbox never holds two versions of one fact.

What is never stored or published here: a competitor's title, description, tag list, review
text, image or chart. Findings are counts, medians and shares -- facts about a category --
and the statements are written in this company's words (#224, the standing originality
constraint). Competitor research is demand and merchandising intelligence only.
"""
from __future__ import annotations

import hashlib
import re
from collections import Counter
from datetime import date, datetime, timezone
from statistics import median

KIND = "mjs.findings"
ORIGIN_CELL = "learn"      # external evidence is Learn's to bring in; routing excludes origin
LESSON_PREFIX = "mjs_finding:"
MIN_POD_LISTINGS = 5       # below this a pod median is one seller's decision, not a band
NEUTRAL_SATURATION = 15    # Etsy's per-image saturation, 0-100
SEASON_POD = {"stockings": "Christmas", "ornaments": "Christmas"}
SEASON_WORDS: dict[str, tuple[str, ...]] = {
    "Christmas": ("christmas", "xmas", "santa", "stocking", "ornament", "reindeer", "elf",
                  "snowman", "nordic", "fair isle", "holiday", "gingerbread", "winter"),
    "Halloween": ("halloween", "pumpkin", "ghost", "witch", "spooky", "bat ", "skeleton"),
    "Thanksgiving (CA)": ("thanksgiving", "harvest", "autumn", "fall ", "turkey", "maple"),
    "Valentine's": ("valentine", "heart", "love "),
    "Easter": ("easter", "bunny", "egg ", "spring"),
    "Mother's Day": ("mother", "mom ", "mum "),
}
# Which bus subject carries which finding, and the reader that consumes it. Named so the
# report and the test check the same path.
CONSUMERS: dict[str, dict] = {
    "pricing_response": {"cells": ("pricing", "portfolio", "finance"),
                         "readers": ["improve.bus inbox: pricing/portfolio/finance",
                                     "runtime.release._outcome_price (same BenchmarkListing "
                                     "medians)"]},
    "seasonal_timing": {"cells": ("market_radar", "growth", "portfolio", "product_creativity"),
                        "readers": ["runtime.pipeline radar.score -> improve.consume.matching"
                                    "('market_radar')",
                                    "creative.ideation.lessons -> improve.bus.brief_lessons"]},
    "thumbnail": {"cells": ("creative_assets", "seo_search", "product_creativity"),
                  "readers": ["creative.ideation.lessons -> improve.bus.brief_lessons",
                              "runtime.release listing.seo -> improve.consume.matching"
                              "('seo_search')"]},
    "palette": {"cells": ("product_creativity", "creative_assets"),
                "readers": ["creative.ideation.lessons -> improve.bus.brief_lessons"]},
    "instruction_clarity": {"cells": ("pattern_engineering", "quality", "customer_experience"),
                            "readers": ["runtime.pipeline radar.score -> improve.consume."
                                        "matching('pattern_engineering')",
                                        "runtime.release support -> improve.consume.matching"
                                        "('customer_experience')"]},
    "delivery_experience": {"cells": ("customer_experience", "creative_assets", "quality"),
                            "readers": ["runtime.release support -> improve.consume.matching"
                                        "('customer_experience')"]},
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    return str(value)


def seasonal_positioning(text: str) -> str:
    """The occasion a listing's own words position it for, or '' when none is stated."""
    low = (text or "").lower()
    for event, needles in SEASON_WORDS.items():
        if any(re.search(rf"\b{re.escape(n.strip())}s?\b", low) for n in needles):
            return event
    return ""


def _quantile(values: list[float], q: float) -> float:
    vals = sorted(values)
    if not vals:
        raise ValueError("no values")
    pos = (len(vals) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(vals) - 1)
    return round(vals[lo] + (vals[hi] - vals[lo]) * (pos - lo), 2)


# ---------------------------------------------------------------------------------------
# Evidence: one shape, two sources (the database the cadence reads, or a public snapshot)

def _empty_pod() -> dict:
    return {"listings": 0, "prices": [], "images": [], "on_sale": 0, "video_audited": 0,
            "video_with": 0, "dominant_saturation": [], "favourites": [],
            "favourites_median": None, "deliverable_read": 0, "deliverable_unclear": 0,
            "silent_on": Counter(), "bundled": None, "seasonal": Counter(),
            "seasonal_measured": 0, "shot_types": Counter()}


def gather(db, *, benchmark_key: str = "") -> dict:
    """Everything the stored observations say, in the shape `synthesize` reads. No network."""
    from sqlalchemy import desc, select

    from ..core.models import AuditLog, BenchmarkListing, BenchmarkObservation, CoverageGap
    from . import benchmarks, pods as pod_vocab

    key = benchmark_key or benchmarks.MJS_KEY
    pods: dict[str, dict] = {}
    seen: list[datetime] = []
    with db.session() as s:
        rows = list(s.scalars(select(BenchmarkListing).where(
            BenchmarkListing.benchmark_key == key,
            BenchmarkListing.audit_state != "withdrawn")))
        for r in rows:
            p = pods.setdefault(r.pod or "unclassified", _empty_pod())
            d = r.detail or {}
            p["listings"] += 1
            if r.price_cad and r.price_cad > 0:
                p["prices"].append(float(r.price_cad))
            p["images"].append(int(r.media_count or 0))
            p["on_sale"] += 1 if r.on_sale else 0
            if "has_video" in d:
                p["video_audited"] += 1
                p["video_with"] += 1 if d["has_video"] else 0
            palette = d.get("palette") or []
            if palette:
                first = palette[0]
                if first.get("saturation") is not None:
                    p["dominant_saturation"].append(int(first["saturation"]))
            if d.get("num_favorers") is not None:
                p["favourites"].append(int(d["num_favorers"]))
            facts = d.get("deliverable")
            if facts:
                p["deliverable_read"] += 1
                clarity = facts.get("clarity")
                if clarity is not None and clarity < 0.6:
                    p["deliverable_unclear"] += 1
                p["silent_on"].update(facts.get("missing") or [])
            title = r.title or ""
            if title:
                p["bundled"] = (p["bundled"] or 0) + (
                    1 if pod_vocab.counts_its_own_patterns(title) else 0)
                p["seasonal_measured"] += 1
                event = r.seasonal or seasonal_positioning(
                    " ".join([title, *[str(t) for t in (d.get("tags") or [])]]))
                if event:
                    p["seasonal"][event] += 1
            if r.last_seen:
                seen.append(r.last_seen)
        pod_of = {r.listing_ref: (r.pod or "unclassified") for r in rows}
        for obs in s.scalars(select(BenchmarkObservation).where(
                BenchmarkObservation.benchmark_key == key,
                BenchmarkObservation.kind == "gallery_image_observation")):
            shot = ((obs.detail or {}).get("observation") or {}).get("shot_type")
            pod = pod_of.get(obs.listing_ref)
            if shot and pod in pods:
                pods[pod]["shot_types"][str(shot)] += 1
        reviews = None
        reviews_at = ""
        for obs in s.scalars(select(BenchmarkObservation).where(
                BenchmarkObservation.benchmark_key == key,
                BenchmarkObservation.kind == "official_api_read")
                .order_by(desc(BenchmarkObservation.id)).limit(200)):
            if (obs.detail or {}).get("reviews"):
                reviews, reviews_at = obs.detail["reviews"], _iso(obs.at)
                break
        gaps = [{"arena": g.arena, "pod": g.pod, "state": g.state, "score": g.score}
                for g in s.scalars(select(CoverageGap).where(
                    CoverageGap.benchmark_key == key))]
        blocked = []
        for action in ("intel.gallery_analysis_blocked", "serp.capture_blocked",
                       "mjs.scan_blocked", "intel.panel_discovery_blocked",
                       "mjs.reviews_blocked"):
            row = s.scalar(select(AuditLog).where(AuditLog.action == action)
                           .order_by(desc(AuditLog.id)).limit(1))
            if row is not None:
                blocked.append({"source": action, "latest": _iso(row.at),
                                "reason": str((row.detail or {}).get("reason", ""))[:240]})
    serp = _serp(db)
    return {"source": "database", "benchmark_key": key, "pods": pods,
            "observed_from": _iso(min(seen)) if seen else "",
            "observed_to": _iso(max(seen)) if seen else "",
            "reviews": reviews, "reviews_observed_at": reviews_at, "gaps": gaps,
            "serp": serp, "blocked": blocked + STANDING_BLOCKS}


def _serp(db) -> list[dict]:
    from sqlalchemy import desc, select

    from ..core.models import SerpSnapshot

    out: dict[str, dict] = {}
    with db.session() as s:
        for snap in s.scalars(select(SerpSnapshot).order_by(desc(SerpSnapshot.id)).limit(200)):
            if snap.query in out:
                continue
            ranks = snap.rank_list or []
            prices = [float(r["price"]) for r in ranks if r.get("price")]
            out[snap.query] = {"query": snap.query, "api_index_count": snap.total_count,
                               "top_n": len(ranks),
                               "median_price": round(median(prices), 2) if prices else None,
                               "captured_at": _iso(snap.captured_at)}
    return sorted(out.values(), key=lambda r: r["query"])


# Sources this company has decided not to read, or cannot, recorded on every reading so a
# finding is never mistaken for coverage it does not have.
STANDING_BLOCKS: list[dict] = [
    {"source": "etsy.com rendered search / shop pages",
     "reason": "HTTP 403 to automated readers; not scraped (rendered_pages gate, #39)"},
    {"source": "Etsy Marketplace Insights",
     "reason": "no API endpoint; owner-recorded only (intel.insights, #236)"},
    {"source": "competitor sales counts / revenue",
     "reason": "not exposed by the sanctioned API; favourites are used as a labelled proxy"},
]


def evidence_from_public_snapshot(snapshot: dict) -> dict:
    """The same evidence shape from the production command center's public read endpoints.

    `snapshot` holds the JSON of `/api/teardown` (its `mjs_market_map`),
    `/api/arbitrage/departments`, `/api/arbitrage?pod=<pod>` per pod, `/api/gallery-
    intelligence` and the latest `mjs.reviews` audit row. Those endpoints expose no titles,
    so seasonal positioning is unmeasured from this source and says so.
    """
    pods: dict[str, dict] = {}
    seen = []
    for row in (snapshot.get("market_map") or {}).get("rows") or []:
        p = pods.setdefault(row.get("pod") or "unclassified", _empty_pod())
        a = row.get("attributes") or {}
        p["listings"] += 1
        price = (a.get("visible_pricing") or {}).get("price_cad")
        if price:
            p["prices"].append(float(price))
        p["on_sale"] += 1 if (a.get("visible_pricing") or {}).get("on_sale") else 0
        p["images"].append(int((a.get("gallery_structure") or {}).get("images") or 0))
        palette = a.get("palette") or []
        if palette and palette[0].get("saturation") is not None:
            p["dominant_saturation"].append(int(palette[0]["saturation"]))
        if row.get("observed_on"):
            seen.append(row["observed_on"])
    for dept in (snapshot.get("departments") or {}).get("scored") or []:
        p = pods.get(dept.get("market"))
        if p is not None:
            p["favourites_median"] = (dept.get("observed") or {}).get("median_favourites")
    for pod, arb in (snapshot.get("arbitrage") or {}).items():
        p = pods.get(pod)
        hunt = (arb or {}).get("weakness_hunt") or {}
        if p is None or not hunt.get("measurable"):
            continue
        video = hunt.get("video") or {}
        if video.get("measurable"):
            p["video_audited"] = int(video.get("audited") or 0)
            p["video_with"] = int(video.get("with_video") or 0)
        deliv = hunt.get("deliverable") or {}
        if deliv.get("measurable"):
            p["deliverable_read"] = int(deliv.get("read") or 0)
            p["deliverable_unclear"] = int(deliv.get("unclear") or 0)
            p["silent_on"] = Counter(deliv.get("silent_on") or {})
        bundles = hunt.get("bundles") or {}
        if bundles.get("measurable"):
            p["bundled"] = int(bundles.get("bundled") or 0)
    for pod, g in ((snapshot.get("gallery") or {}).get("by_pod") or {}).items():
        if pod in pods:
            for read in g.get("reads") or []:
                if re.fullmatch(r"[a-z]+(_[a-z]+)+", str(read)):
                    pods[pod]["shot_types"][read] += 1
    reviews = snapshot.get("reviews") or {}
    return {"source": "public_api_snapshot", "benchmark_key": snapshot.get("benchmark_key", ""),
            "pods": pods, "observed_from": min(seen) if seen else "",
            "observed_to": max(seen) if seen else "",
            "reviews": reviews.get("themes"), "reviews_observed_at": reviews.get("at", ""),
            "gaps": snapshot.get("gaps") or [], "serp": snapshot.get("serp") or [],
            "blocked": (snapshot.get("blocked") or []) + STANDING_BLOCKS}


# ---------------------------------------------------------------------------------------
# Synthesis

def _our_pool_prices() -> dict[str, list[float]]:
    """Brambleloop's own concept-pool prices per benchmark pod (radar.opportunity)."""
    from ..radar.opportunity import _pool
    from ..seasonal.daily import DEPARTMENT_OF

    out: dict[str, list[float]] = {}
    for seed in _pool():
        pod = DEPARTMENT_OF.get(seed.category)
        if pod and not seed.is_bundle:
            out.setdefault(pod, []).append(float(seed.price_cad))
    return out


def _finding(key, category, statement, *, metrics, confidence, basis, provenance,
             subject=None, opportunity="") -> dict:
    consumer = ({"bus_subject": subject, "cells": list(CONSUMERS[subject]["cells"]),
                 "readers": CONSUMERS[subject]["readers"]} if subject else
                {"bus_subject": None, "cells": [], "readers": provenance.pop("readers", [])})
    digest = hashlib.sha256(statement.encode()).hexdigest()[:10]
    return {"key": key, "category": category, "statement": statement, "metrics": metrics,
            "confidence": {"grade": confidence, "basis": basis},
            "provenance": provenance, "consumer": consumer, "opportunity": opportunity,
            "digest": digest}


def synthesize(evidence: dict, *, today: date | None = None) -> dict:
    """Findings from evidence. Deterministic: the same evidence gives the same findings."""
    today = today or _now().date()
    pods = evidence.get("pods") or {}
    total = sum(p["listings"] for p in pods.values())
    base_prov = {"benchmark_key": evidence.get("benchmark_key", ""),
                 "source": evidence.get("source", ""),
                 "method": "Etsy Open API v3 public read-only observations stored by mjs.scan; "
                           "aggregated deterministically by intel.findings",
                 "observed_from": evidence.get("observed_from", ""),
                 "observed_to": evidence.get("observed_to", "")}
    findings: list[dict] = []
    unmeasured: list[dict] = []
    if not total:
        return {"as_of": today.isoformat(), "listings": 0, "findings": [],
                "unmeasured": [{"key": "catalogue", "reason": "no benchmark listing has been "
                                "observed, so there is nothing to synthesise"}],
                "blocked_sources": evidence.get("blocked") or []}
    sized = {k: p for k, p in pods.items() if p["listings"] >= MIN_POD_LISTINGS
             and k != "unclassified"}

    # 1. Assortment: where a proven seller has put its shelf space (proxy for demand).
    share = {k: round(p["listings"] / total, 3) for k, p in pods.items()}
    top = sorted(share.items(), key=lambda kv: -kv[1])[:4]
    findings.append(_finding(
        "assortment", "category_opportunity",
        "The benchmark allocates its catalogue " + ", ".join(
            f"{k} {round(v * 100)}%" for k, v in top) + f" of {total} observed listings",
        metrics={"listings": total, "share_by_pod": share}, confidence="proxy",
        basis="shelf allocation of one successful seller; where it invests, not what sells",
        provenance={**base_prov, "tables": ["benchmark_listings"], "sample": total,
                    "readers": ["intel.findings OperatingReading 'mjs.findings'",
                                "seasonal benchmark-matrix (same rows)"]}))

    # 2. Demand: favourites by pod, and depth against demand.
    fav = {}
    for k, p in sized.items():
        if p["favourites"]:
            fav[k] = float(median(p["favourites"]))
        elif p.get("favourites_median") is not None:
            fav[k] = float(p["favourites_median"])
    if fav:
        ranked = sorted(fav.items(), key=lambda kv: -kv[1])
        median_share = median(share[k] for k in fav)
        underserved = [k for k, v in ranked[: max(1, len(ranked) // 2)]
                       if share[k] < median_share]
        findings.append(_finding(
            "demand_by_pod", "what_is_selling",
            "Median favourites per benchmark listing rank " + ", ".join(
                f"{k} {int(v)}" for k, v in ranked[:5]) +
            (f"; {', '.join(underserved)} draw above-median favourites on below-median shelf "
             f"depth" if underserved else ""),
            metrics={"median_favourites": dict(ranked), "underserved": underserved},
            confidence="proxy", basis="favourites are a demand proxy, not sales",
            provenance={**base_prov, "tables": ["benchmark_listings.detail.num_favorers"],
                        "sample": sum(sized[k]["listings"] for k in fav),
                        "readers": ["radar.arbitrage.score_observed (demand dimension)"]},
            opportunity=(f"prioritise original concepts in {', '.join(underserved)}: demand "
                         f"per listing is high and the benchmark's range there is thin"
                         if underserved else "")))
    else:
        unmeasured.append({"key": "demand_by_pod",
                           "reason": "no favourites observed for any pod with "
                                     f"{MIN_POD_LISTINGS}+ listings"})

    # 3. Pricing, against Brambleloop's own concept pool.
    ours = _our_pool_prices()
    price_rows = {}
    for k, p in sized.items():
        if len(p["prices"]) >= MIN_POD_LISTINGS:
            row = {"n": len(p["prices"]), "median": round(median(p["prices"]), 2),
                   "p25": _quantile(p["prices"], 0.25), "p75": _quantile(p["prices"], 0.75)}
            if ours.get(k):
                row["brambleloop_pool_median"] = round(median(ours[k]), 2)
                row["gap_pct"] = round(100 * (row["brambleloop_pool_median"] - row["median"])
                                       / row["median"], 1)
            price_rows[k] = row
    if price_rows:
        below = {k: r for k, r in price_rows.items() if r.get("gap_pct", 0) <= -25}
        sale = sum(p["on_sale"] for p in pods.values())
        findings.append(_finding(
            "pricing", "pricing",
            "Observed benchmark pattern prices: " + "; ".join(
                f"{k} median CA${r['median']} (IQR {r['p25']}-{r['p75']}, n={r['n']})"
                for k, r in sorted(price_rows.items())) +
            (". Brambleloop concept pool prices sit " + ", ".join(
                f"{k} {r['gap_pct']}%" for k, r in below.items()) + " "
             f"against those medians; release pricing already anchors on the observed median "
             f"(runtime.release._outcome_price) but radar scoring still uses the pool "
             f"prices" if below else "") +
            f". {sale} of {total} listings were on sale when observed",
            metrics={"by_pod": price_rows, "on_sale": sale, "listings": total},
            confidence="observed", basis="listed prices converted to CAD at observation",
            provenance={**base_prov, "tables": ["benchmark_listings.price_cad",
                                                "radar.opportunity._pool"],
                        "sample": sum(r["n"] for r in price_rows.values())},
            subject="pricing_response",
            opportunity=("test launch prices inside the observed interquartile band before "
                         "any discount; the benchmark does not rely on sales"
                         if below else "")))

    # 4. Bundles: whether multi-pattern collections carry a premium.
    coll = pods.get("collections")
    singles = [x for k, p in sized.items() if k != "collections" for x in p["prices"]]
    if coll and len(coll["prices"]) >= MIN_POD_LISTINGS and singles:
        ratio = round(median(coll["prices"]) / median(singles), 2)
        bundled = sum((p["bundled"] or 0) for p in pods.values() if p["bundled"] is not None)
        findings.append(_finding(
            "bundle_premium", "category_opportunity",
            f"Benchmark bundle and collection listings sell at median CA${median(coll['prices'])} "
            f"against CA${median(singles)} for single patterns ({ratio}x, n={len(coll['prices'])}); "
            f"a bundle collection family is a pricing lever, not only a convenience",
            metrics={"collection_median": median(coll["prices"]),
                     "single_median": median(singles), "ratio": ratio,
                     "collections": coll["listings"], "titles_counting_patterns": bundled},
            confidence="observed", basis="listed prices; whether bundles sell is unmeasured",
            provenance={**base_prov, "tables": ["benchmark_listings"],
                        "sample": coll["listings"] + len(singles)},
            subject="pricing_response",
            opportunity="plan each launch family with a priced bundle from day one"))

    # 5. Presentation: gallery depth, video, shot types.
    imgs = [i for p in pods.values() for i in p["images"]]
    v_aud = sum(p["video_audited"] for p in pods.values())
    v_with = sum(p["video_with"] for p in pods.values())
    shots = Counter()
    for p in pods.values():
        shots.update(p["shot_types"])
    ten = sum(1 for i in imgs if i >= 10)
    thin = sum(1 for i in imgs if i < 5)
    video_txt = (f"{v_with} of {v_aud} gallery-audited listings carry a video"
                 if v_aud else "video is unmeasured (no gallery audited)")
    shot_txt = (", most judged shots are " + ", ".join(f"{k} {n}" for k, n in
                                                        shots.most_common(3))
                if shots else "")
    findings.append(_finding(
        "presentation", "presentation",
        f"Benchmark listing galleries hold a median of {median(imgs):g} images ({ten} of "
        f"{len(imgs)} at ten or more, {thin} under five); {video_txt}{shot_txt}. Brambleloop "
        f"thumbnail and gallery plans should meet ten images and carry a technique video",
        metrics={"median_images": median(imgs), "ten_plus": ten, "under_five": thin,
                 "listings": len(imgs), "video_audited": v_aud, "video_with": v_with,
                 "shot_types": dict(shots.most_common(8))},
        confidence="observed", basis="Etsy image counts and video endpoint; shot types are "
                                     "vision judgements where image_vision has run",
        provenance={**base_prov, "tables": ["benchmark_listings.media_count",
                                            "benchmark_listings.detail.has_video",
                                            "benchmark_observations(gallery_image_observation)"],
                    "sample": len(imgs)},
        subject="thumbnail",
        opportunity="a ten-image gallery with video is table stakes; thin galleries in the "
                    "benchmark are the opening"))
    if not v_aud:
        unmeasured.append({"key": "video", "reason": "no gallery audit has recorded video"})

    # 6. Palette.
    sats = [x for p in pods.values() for x in p["dominant_saturation"]]
    if len(sats) >= MIN_POD_LISTINGS:
        neutral = sum(1 for x in sats if x < NEUTRAL_SATURATION)
        findings.append(_finding(
            "palette", "presentation",
            f"{neutral} of {len(sats)} benchmark hero palettes are low-saturation neutrals "
            f"(dominant colour saturation under {NEUTRAL_SATURATION}); neutral palette "
            f"photography is the category default, so a saturated colourway palette stands "
            f"apart in a search grid",
            metrics={"neutral": neutral, "palettes": len(sats),
                     "median_saturation": median(sats)},
            confidence="observed", basis="Etsy per-image colour statistics, first image",
            provenance={**base_prov, "tables": ["benchmark_listings.detail.palette"],
                        "sample": len(sats)},
            subject="palette",
            opportunity="test a saturated colourway against a neutral one in concept briefs"))
    else:
        unmeasured.append({"key": "palette", "reason": "fewer than five galleries read"})

    # 7. Seasonality: what the benchmark positions for, and the windows now open.
    from ..radar.market import SEASONAL_EVENTS

    upcoming = sorted([e for e in SEASONAL_EVENTS if 0 <= (e.event_date - today).days <= 120],
                      key=lambda e: e.event_date)
    measured = sum(p["seasonal_measured"] for p in pods.values())
    positioned = Counter()
    for p in pods.values():
        positioned.update(p["seasonal"])
    season_pods = {k: pods[k]["listings"] for k in SEASON_POD if k in pods}
    christmas = [e for e in upcoming if e.name == "Christmas"]
    if christmas or season_pods:
        when = (f"Christmas ({christmas[0].event_date.isoformat()}) is inside the buying "
                f"window" if christmas else "Christmas is outside the 120-day window")
        pos_txt = (f"; {sum(positioned.values())} of {measured} titled listings are "
                   f"positioned for an occasion (" + ", ".join(
                       f"{k} {n}" for k, n in positioned.most_common(3)) + ")"
                   if measured else "; title-level seasonal positioning is unmeasured in "
                                    "this evidence")
        findings.append(_finding(
            "seasonality", "seasonality",
            f"{when}: the benchmark carries {season_pods.get('stockings', 0)} christmas "
            f"stocking and {season_pods.get('ornaments', 0)} ornament listings{pos_txt}. "
            f"Christmas stocking and ornament concepts are quick makes that still sell late "
            f"in the season",
            metrics={"upcoming": [{"event": e.name, "date": e.event_date.isoformat(),
                                   "days_away": (e.event_date - today).days}
                                  for e in upcoming],
                     "season_pods": season_pods, "positioned": dict(positioned),
                     "titled_listings": measured},
            confidence="observed" if measured else "proxy",
            basis=("seasonal words in observed titles and tags" if measured else
                   "seasonal pods (stockings, ornaments) as a proxy; titles not in evidence"),
            provenance={**base_prov, "tables": ["benchmark_listings", "radar.market."
                                                "SEASONAL_EVENTS"],
                        "sample": total},
            subject="seasonal_timing",
            opportunity="prioritise christmas stocking and ornament quick makes now"))
    if not measured:
        unmeasured.append({"key": "seasonal_positioning",
                           "reason": "no listing title in this evidence; counted from pods only"})

    # 8. Customer pain: recurring review themes (counts only, never text).
    rv = evidence.get("reviews")
    if rv and rv.get("measurable"):
        rec = rv.get("recurring") or {}
        findings.append(_finding(
            "customer_pain", "customer_expectations",
            f"Of {rv.get('reviews_read')} benchmark reviews read, {rv.get('low_rated')} are rated "
            f"three or lower; recurring complaint themes: " +
            (", ".join(f"{k.replace('_', ' ')} {n}" for k, n in rec.items()) or "none above the "
             f"floor of {rv.get('recurring_at')}") +
            ". Clear row-by-row instructions with stitch counts and stated US terms answer "
            "the commonest complaint",
            metrics={k: rv.get(k) for k in ("reviews_read", "low_rated", "low_rated_share",
                                            "themes", "recurring", "recurring_at")},
            confidence="observed", basis="keyword-classified review themes; counts only",
            provenance={**base_prov, "tables": ["benchmark_observations.detail.reviews"],
                        "sample": rv.get("reviews_read"),
                        "observed_from": evidence.get("reviews_observed_at", ""),
                        "observed_to": evidence.get("reviews_observed_at", "")},
            subject="instruction_clarity" if rec else None,
            opportunity="ship instruction clarity as a feature: stitch counts, photo steps"
            if rec else ""))
    else:
        unmeasured.append({"key": "customer_pain", "reason": "no review read is stored"})

    # 9. Deliverable clarity: what competitor listings fail to tell a buyer.
    d_read = sum(p["deliverable_read"] for p in pods.values())
    if d_read:
        silent = Counter()
        for p in pods.values():
            silent.update(p["silent_on"])
        unclear = sum(p["deliverable_unclear"] for p in pods.values())
        top_silent = [(k, n) for k, n in silent.most_common(5) if n]
        findings.append(_finding(
            "deliverable_gaps", "weak_spots",
            f"{unclear} of {d_read} benchmark descriptions read state too little for a buyer "
            f"to know what arrives; most often silent on " +
            ", ".join(f"{k.replace('_', ' ')} ({n})" for k, n in top_silent) +
            ". Brambleloop listings should state delivery, page extent, finished size, hook "
            "and yarn in every description",
            metrics={"read": d_read, "unclear": unclear, "silent_on": dict(silent)},
            confidence="observed", basis="eight boolean facts per description (intel."
                                         "deliverable); copy is never stored",
            provenance={**base_prov, "tables": ["benchmark_listings.detail.deliverable"],
                        "sample": d_read},
            subject="delivery_experience",
            opportunity="a complete 'what you get' block is a cheap, durable advantage"))
    else:
        unmeasured.append({"key": "deliverable_gaps", "reason": "no description read"})

    # 10. Coverage gaps: arenas the benchmark proves and Brambleloop has no answer in.
    gaps = [g for g in evidence.get("gaps") or [] if g.get("state") == "uncovered"]
    if gaps:
        gaps.sort(key=lambda g: -(g.get("score") or 0))
        findings.append(_finding(
            "coverage_gaps", "category_opportunity",
            f"{len(gaps)} benchmark arenas have no Brambleloop answer; first in the queue: " +
            ", ".join(g["arena"] + (f" ({g['pod']})" if g.get("pod") else "")
                      for g in gaps[:6]),
            metrics={"uncovered": len(gaps), "top": gaps[:10]}, confidence="observed",
            basis="coverage gap queue (intel.coverage)",
            provenance={**base_prov, "tables": ["coverage_gaps"], "sample": len(gaps),
                        "readers": ["intel.mission_runtime.consume_concepting",
                                    "intel.coverage gap queue"]},
            opportunity="the gap queue's top arenas are the next original-concept briefs"))

    # 11. SERP (API search index), where captured.
    serp = evidence.get("serp") or []
    if serp:
        findings.append(_finding(
            "search_index", "what_is_selling",
            f"{len(serp)} target queries captured from the API search index; " + "; ".join(
                f"{r['query']}: {r['api_index_count']} results, top-{r['top_n']} median "
                f"CA${r['median_price']}" for r in serp[:5]),
            metrics={"queries": serp}, confidence="proxy",
            basis="API index order (sort_on=score), directional; not the rendered search page",
            provenance={**base_prov, "tables": ["serp_snapshots"], "sample": len(serp),
                        "readers": ["radar.arbitrage.steering (listing density)"]}))
    else:
        unmeasured.append({"key": "search_index",
                           "reason": "no SERP snapshot stored (intel.serp_capture has not run "
                                     "in this environment)"})

    return {"as_of": today.isoformat(), "listings": total, "findings": findings,
            "unmeasured": unmeasured, "blocked_sources": evidence.get("blocked") or [],
            "never_stored": ["competitor titles, descriptions, tags, review text, images, "
                             "charts or instructions"]}


# ---------------------------------------------------------------------------------------
# Durable record + lesson bus

def refresh(db, *, today: date | None = None, benchmark_key: str = "") -> dict:
    """Synthesize from stored rows, persist the day's reading, publish what changed."""
    from sqlalchemy import select

    from ..core.models import Lesson, OperatingReading
    from ..improve import bus

    today = today or _now().date()
    result = synthesize(gather(db, benchmark_key=benchmark_key), today=today)
    with db.session() as s:
        prev_rows = list(s.scalars(select(OperatingReading).where(
            OperatingReading.kind == KIND, OperatingReading.period_key != today.isoformat())
            .order_by(OperatingReading.id.desc()).limit(1)))
        previous = {f["key"]: f["digest"] for f in
                    ((prev_rows[0].payload or {}).get("findings") or [])} if prev_rows else {}
    changed = [f["key"] for f in result["findings"] if previous.get(f["key"]) != f["digest"]]

    published, superseded = [], []
    for f in result["findings"]:
        subject = f["consumer"]["bus_subject"]
        if not subject:
            continue
        ref = f"{LESSON_PREFIX}{f['key']}:{f['digest']}"
        lesson_id = bus.publish(db, origin_cell=ORIGIN_CELL, subject=subject,
                                statement=f["statement"], evidence_ref=ref,
                                confidence="observed")
        f["lesson_id"] = lesson_id
        published.append(lesson_id)
        with db.session() as s:
            for old in s.scalars(select(Lesson).where(
                    Lesson.evidence_ref.like(f"{LESSON_PREFIX}{f['key']}:%"),
                    Lesson.evidence_ref != ref, Lesson.superseded_by.is_(None))):
                old.superseded_by = lesson_id
                superseded.append(old.id)

    payload = {**result, "changed_since_previous": changed, "lessons": sorted(set(published)),
               "superseded": superseded, "generated_at": _now().isoformat()}
    with db.session() as s:
        row = s.scalar(select(OperatingReading).where(
            OperatingReading.kind == KIND, OperatingReading.period_key == today.isoformat()))
        if row is None:
            s.add(OperatingReading(kind=KIND, period_key=today.isoformat(), payload=payload))
        else:
            row.payload = payload
    return {"findings": len(result["findings"]), "changed": changed,
            "lessons": sorted(set(published)), "superseded": superseded,
            "unmeasured": [u["key"] for u in result["unmeasured"]], "as_of": today.isoformat()}


def latest(db) -> dict | None:
    """The most recent stored findings reading, for any reader (CC, briefs, reports)."""
    from sqlalchemy import select

    from ..core.models import OperatingReading

    with db.session() as s:
        row = s.scalar(select(OperatingReading).where(OperatingReading.kind == KIND)
                       .order_by(OperatingReading.id.desc()).limit(1))
        return dict(row.payload or {}) if row is not None else None
