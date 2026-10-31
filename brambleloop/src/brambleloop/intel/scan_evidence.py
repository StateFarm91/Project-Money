"""Production evidence that the competitor scans ran (P0-COMPETITOR-EVIDENCE).

Owner directive (P0 §7): every monitored shop must have an authorised collection method, a
scheduled scan, the last attempted scan, the last successful scan, a source timestamp, source
provenance, the data that was accessible, recorded limitations, the failure reason and the
downstream research output. "A shop on a watchlist is not proof that it has actually been
scanned. An inaccessible shop must be recorded as inaccessible."

The scanners already keep this, in three places: the anchor shop's `Benchmark` row and its
`mjs.scan` jobs, the watchlist members' state in company memory (`intel.watchlist`), and the
listings each scan observed (`benchmark_listings`). Nothing joined them per shop. This module
does, read-only, for the owner's named shops -- the anchor, the permanent watchlist and the
original seed shops -- and for the two MJ's reference listings the owner named.

States are derived, never declared:

    scanned                 a successful scan is recorded, with its time
    attempted_not_scanned   attempts are recorded, none succeeded; the last failure is given
    not_accessible          the read path could not reach the shop by name (recorded by the
                            watchlist scan); the limitation and its date are given
    never_attempted         registered for scanning, no attempt recorded yet
    not_registered          named by the owner but not in this build's scan registry; no scan
                            can have run (the seed shops join it with W-CONCEPT,
                            D-W4-OWNER-SEEDSHOPS)

No count is invented: a shop with no observed listings reports 0 observed with the state that
explains it. No competitor title, description, image or URL of a listing is copied into the
evidence; listing references are Etsy ids already held. No network, no model, CA$0.
"""
from __future__ import annotations

from datetime import datetime, timezone

READING_KIND = "intel.scan_evidence"
SCANNED = "scanned"
ATTEMPTED = "attempted_not_scanned"
NOT_ACCESSIBLE = "not_accessible"
NEVER = "never_attempted"
NOT_REGISTERED = "not_registered"

METHOD = ("Etsy Open API v3, read-only public endpoints with the API key only "
          "(intel.etsy_public.ALLOWED); no OAuth scope, no scraping")

# The owner's named shops, in the owner's order (P0 directive 2026-10-27 / 2026-10-30).
OWNER_SHOPS: tuple[tuple[str, str, str], ...] = (
    ("MJsOffTheHookDesigns", "https://www.etsy.com/shop/MJsOffTheHookDesigns", "anchor"),
    ("MadelineMaeCo", "https://www.etsy.com/shop/MadelineMaeCo", "permanent"),
    ("ZKBDESIGNER", "https://www.etsy.com/ca/shop/ZKBDESIGNER", "permanent"),
    ("TheEasyDesign", "https://www.etsy.com/ca/shop/TheEasyDesign", "permanent"),
    ("HanJanCrochet", "https://www.etsy.com/ca/shop/HanJanCrochet", "seed"),
    ("IvyLoop", "https://www.etsy.com/ca/shop/IvyLoop", "seed"),
    ("LoveandStitchDesigns", "https://www.etsy.com/ca/shop/LoveandStitchDesigns", "seed"),
    ("FireflyCrochets", "https://www.etsy.com/ca/shop/FireflyCrochets", "seed"),
)

# The owner's two MJ's reference listings (P0 directive 2026-10-30 §7): references for
# presentation, education, families, photography and pricing; never copied.
REFERENCE_LISTINGS: tuple[tuple[str, str], ...] = (
    ("1767833856", "Fall for Granny Baskets"),
    ("4295011799", "Homebody Baskets"),
)


def _iso(v):
    if v is None:
        return None
    if isinstance(v, str):
        return v
    return (v if v.tzinfo else v.replace(tzinfo=timezone.utc)).isoformat()


def _cadence(job_type: str) -> dict | None:
    from ..runtime.worker import CADENCES

    for name, agent, jt, period in CADENCES:
        if jt == job_type:
            return {"cadence": name, "agent": agent, "job_type": jt, "every_hours": period / 3600}
    return None


def _jobs(db, job_type: str, limit: int = 50) -> list:
    from sqlalchemy import desc, select

    from ..core.models import Job

    with db.session() as s:
        return [{"id": j.id, "status": j.status.value, "created_at": _iso(j.created_at),
                 "finished_at": _iso(j.finished_at), "outputs": dict(j.outputs or {}),
                 "error": (j.last_error or "")[:300]}
                for j in s.scalars(select(Job).where(Job.job_type == job_type)
                                   .order_by(desc(Job.id)).limit(limit))]


def _observed(db, key: str | None) -> dict:
    from sqlalchemy import func, select

    from ..core.models import BenchmarkListing

    if not key:
        return {"listings_observed": 0, "first_seen": None, "last_seen": None}
    with db.session() as s:
        n, first, last = s.execute(
            select(func.count(), func.min(BenchmarkListing.first_seen),
                   func.max(BenchmarkListing.last_seen))
            .where(BenchmarkListing.benchmark_key == key)).one()
    return {"listings_observed": int(n or 0), "first_seen": _iso(first), "last_seen": _iso(last)}


def _seed_observation(shop: str) -> dict | None:
    """The owner-seeded dated public-profile observation, if any: alternative evidence."""
    from ..radar.market import COMPETITORS

    prof = next((c for c in COMPETITORS if c.shop.lower() == shop.lower()), None)
    if prof is None:
        return None
    return {"source": f"radar.market.COMPETITORS[{prof.shop}]",
            "observed_on": str(getattr(prof, "observed_on", "") or ""),
            "kind": "public-profile seed observation (price band, formats; no content)"}


def _anchor(db) -> dict:
    from sqlalchemy import select

    from ..core.models import Benchmark
    from . import benchmarks

    with db.session() as s:
        row = s.scalar(select(Benchmark).where(Benchmark.key == benchmarks.MJS_KEY))
        bench = None if row is None else {"last_scan_at": _iso(row.last_scan_at),
                                          "last_change_at": _iso(row.last_change_at),
                                          "scan_health": dict(row.scan_health or {})}
    jobs = _jobs(db, "mjs.scan")
    attempted = jobs[0] if jobs else None
    ok = next((j for j in jobs if j["status"] == "done" and j["outputs"].get("ran") is not False),
              None)
    fail = next((j for j in jobs if j["status"] in ("dead", "failed")
                 or j["outputs"].get("ran") is False), None)
    last_ok = (bench or {}).get("last_scan_at") or (ok or {}).get("finished_at")
    if last_ok:
        state = SCANNED
    elif attempted:
        state = ATTEMPTED
    else:
        state = NEVER
    reason = None
    if fail is not None and (ok is None or fail["id"] > ok["id"]):
        # Only a failure newer than the last success is the shop's current failure.
        reason = fail["error"] or str(fail["outputs"].get("reason") or "")[:300] or None
    return {"key": benchmarks.MJS_KEY, "registered_as": "benchmark anchor (intel.benchmarks.MJS)",
            "schedule": _cadence("mjs.scan"), "state": state,
            "last_attempted": (attempted or {}).get("finished_at") or (attempted or {}).get(
                "created_at"),
            "last_successful": last_ok, "source_timestamp": last_ok,
            "provenance": "benchmarks row + mjs.scan jobs",
            "failure_reason": reason,
            "limitations": ["the API gives the catalogue, not the rendered page (badges, sale "
                            "banners as shown, thumbnails as displayed)"],
            "scan_health": (bench or {}).get("scan_health")}


def _watched(db, member) -> dict:
    from . import watchlist

    st = watchlist._state(db, member.key)
    state = st.get("state")
    if state == "ok" or st.get("last_ok_at"):
        derived = SCANNED
    elif state == "not_accessible":
        derived = NOT_ACCESSIBLE
    elif st.get("last_attempt_at"):
        derived = ATTEMPTED
    else:
        derived = NEVER
    limits = ["the API gives the catalogue, not the rendered page"]
    if st.get("limitation"):
        limits.append(f"{st['limitation']} (recorded {st.get('limitation_on')})")
    return {"key": member.key, "registered_as": f"watchlist member ({member.role})",
            "schedule": _cadence("intel.watchlist_scan"), "state": derived,
            "last_attempted": st.get("last_attempt_at"), "last_successful": st.get("last_ok_at"),
            "source_timestamp": st.get("last_ok_at"),
            "provenance": f"company_memory {watchlist.STATE_PREFIX}{member.key}",
            "failure_reason": (st.get("last_error") if derived != SCANNED else None),
            "consecutive_failures": int(st.get("consecutive_failures") or 0),
            "listings_seen_last_scan": st.get("listings_seen"),
            "limitations": limits,
            "alternative_evidence": st.get("alternative_evidence")}


def report(db, *, now: datetime | None = None) -> dict:
    """Per-shop scan evidence and the reference listings. Read-only."""
    from . import benchmarks, etsy_public, watchlist

    now = now or datetime.now(timezone.utc)
    probe = etsy_public.last_probe(db)
    credential = ("UNKNOWN: no etsy.probe recorded" if probe is None else
                  "refused" if etsy_public.auth_refused(probe) else
                  "usable" if probe.get("ok") else f"not usable: {str(probe)[:160]}")
    by_shop = {m.shop_name.lower(): m for m in watchlist.WATCHLIST}
    shops = []
    for shop, url, role in OWNER_SHOPS:
        if shop.lower() == benchmarks.MJS_SHOP.lower():
            rec = _anchor(db)
        elif shop.lower() in by_shop:
            rec = _watched(db, by_shop[shop.lower()])
        else:
            seed = _seed_observation(shop)
            rec = {"key": None, "registered_as": None, "schedule": None,
                   "state": NOT_REGISTERED, "last_attempted": None, "last_successful": None,
                   "source_timestamp": None, "provenance": None,
                   "failure_reason": ("not in this build's scan registry, so no scan can have "
                                      "run; the seed shops join the watchlist with W-CONCEPT "
                                      "(D-W4-OWNER-SEEDSHOPS)"),
                   "limitations": ["no scheduled scan on this build"],
                   "alternative_evidence": seed}
        rec.update({"shop": shop, "owner_url": url, "owner_role": role, "method": METHOD,
                    "downstream": _observed(db, rec.get("key"))})
        shops.append(rec)
    refs = _references(db)
    counts: dict[str, int] = {}
    for r in shops:
        counts[r["state"]] = counts.get(r["state"], 0) + 1
    return {"as_of": now.isoformat(), "credential": credential, "method": METHOD,
            "shops": shops, "counts": counts, "reference_listings": refs,
            "scanned": [r["shop"] for r in shops if r["state"] == SCANNED],
            "not_scanned": [{"shop": r["shop"], "state": r["state"],
                             "why": r.get("failure_reason")}
                            for r in shops if r["state"] != SCANNED]}


def _references(db) -> list[dict]:
    from sqlalchemy import select

    from ..core.models import BenchmarkListing
    from . import benchmarks

    out = []
    with db.session() as s:
        for ref, name in REFERENCE_LISTINGS:
            row = s.scalar(select(BenchmarkListing).where(
                BenchmarkListing.benchmark_key == benchmarks.MJS_KEY,
                BenchmarkListing.listing_ref == ref))
            out.append({"listing_id": ref, "owner_name": name,
                        "url": f"https://www.etsy.com/ca/listing/{ref}/",
                        "observed": row is not None,
                        "first_seen": _iso(row.first_seen) if row is not None else None,
                        "last_seen": _iso(row.last_seen) if row is not None else None,
                        "pod": row.pod if row is not None else None,
                        "why": (None if row is not None else
                                "not among the anchor's observed listings yet; it is observed "
                                "when an mjs.scan reads it (sold out or delisted listings are "
                                "not returned by the active-listings endpoint)"),
                        "use": "presentation, education, families, photography and pricing "
                               "reference only; never copied"})
    return out


def record(db, rep: dict) -> dict:
    """One durable reading per UTC day (`operating_readings`, which retention does not prune)."""
    from sqlalchemy import select

    from ..core.models import OperatingReading

    period = rep["as_of"][:10]
    with db.session() as s:
        row = s.scalar(select(OperatingReading).where(
            OperatingReading.kind == READING_KIND, OperatingReading.period_key == period))
        if row is None:
            s.add(OperatingReading(kind=READING_KIND, period_key=period, payload=rep))
            created = True
        else:
            row.payload = rep
            created = False
    return {"kind": READING_KIND, "period_key": period, "created": created}


def latest(db) -> dict | None:
    from sqlalchemy import select

    from ..core.models import OperatingReading

    with db.session() as s:
        row = s.scalar(select(OperatingReading).where(OperatingReading.kind == READING_KIND)
                       .order_by(OperatingReading.id.desc()).limit(1))
        return dict(row.payload) if row is not None else None
