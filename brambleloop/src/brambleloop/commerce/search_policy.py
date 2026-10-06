"""Official search policy snapshot and search/ads policy watch (F-242, F-291).

The search limits the listing chain enforces -- 13 tags, 20 characters a tag, 140 characters a
title, no tag starting with ' or -, attributes acting like tags -- used to be undated
constants. They are now conclusions of a watched policy reading, `search_guidance`
(`gates.platform_policy.POLICY_SOURCES`, built from lane G's dated `seo.constraints` record),
and every search certificate `listing.seo` issues is stamped with the snapshot it was issued
under. A later snapshot recorded as a MATERIAL change invalidates every certificate issued
before it: `commerce.search.stored_pass_problems` refuses the stale PASS at publish, and
`gates.platform_policy.unreviewed_changes` raises the publishing incident until the change is
reviewed and re-tested.

The paid-media side (F-291) is the same mechanism on `advertising_rules`, which now holds the
F-264/F-265 onsite-ads thresholds, so a change to them moves that reading's digest too.

Re-fetching is not automated: help.etsy.com and etsy.com/legal answer HTTP 403 to automated
fetchers (`gates.policy_knowledge.RETRIEVAL_BLOCK`). A new reading arrives through
`platform_policy.record_page_reading` (the owner's page reading) or a repository reading;
either one goes through `record_snapshot`, which is where material change is decided.
"""
from __future__ import annotations

import re

SOURCE = "search_guidance"
ADS_SOURCE = "advertising_rules"


def _snapshots(db, source: str) -> list:
    from sqlalchemy import select

    from ..core.models import PolicySnapshot

    with db.session() as s:
        rows = list(s.scalars(select(PolicySnapshot).where(PolicySnapshot.source == source)
                              .order_by(PolicySnapshot.id)))
        return [{"id": r.id, "digest": r.digest, "checked_on": r.checked_on,
                 "version": r.version, "material_change": bool(r.material_change),
                 "reviewed_at": (r.detail or {}).get("reviewed_at")} for r in rows]


def stamp(db, source: str = SOURCE) -> dict:
    """The snapshot a certificate is issued under: id, digest and date, or NEVER_READ."""
    rows = _snapshots(db, source)
    if not rows:
        return {"source": source, "status": "NEVER_READ", "snapshot_id": None,
                "digest": None, "checked_on": None}
    last = rows[-1]
    return {"source": source, "status": "READ", "snapshot_id": last["id"],
            "digest": last["digest"], "checked_on": last["checked_on"]}


def certificate_problems(db, cert_stamp: dict | None, source: str = SOURCE) -> list[str]:
    """Why a certificate issued under `cert_stamp` no longer stands; empty when it does.

    A material change recorded after the certificate's snapshot (or after issue, when the
    certificate was issued before any reading existed) invalidates it, reviewed or not: the
    certificate described the listing against guidance that is no longer current, and only a
    fresh `listing.seo` run re-certifies it.
    """
    rows = _snapshots(db, source)
    after = (cert_stamp or {}).get("snapshot_id")
    later = [r for r in rows if r["material_change"] and (after is None or r["id"] > after)]
    if not later:
        return []
    r = later[-1]
    return [f"SEARCH_POLICY_CHANGED: the {source} reading changed materially on "
            f"{r['checked_on']} (snapshot {r['id']}) after this certificate was issued "
            f"(F-242); re-run listing.seo under the current guidance"]


def limits() -> dict:
    """Every search limit the code enforces, with the dated reading it rests on (F-242)."""
    from ..gates.policy_knowledge import READINGS
    from . import search as search_mod
    from . import seo as seo_mod
    from ..publish import listing_schema

    reading = READINGS[SOURCE]
    by_rule = {c["rule"]: c for c in reading.conclusions}
    enforced = {"title_max_chars": seo_mod.TITLE_MAX, "tag_max_count": seo_mod.TAG_MAX_COUNT,
                "tag_max_chars": seo_mod.TAG_MAX_CHARS,
                "tag_no_leading_symbol": listing_schema.TAG_NO_LEADING}
    rows = []
    for rule, value in enforced.items():
        c = by_rule.get(rule)
        rows.append({"rule": rule, "enforced": value,
                     "reading_value": (c or {}).get("value"),
                     "status": (c or {}).get("status", "NO_READING"),
                     "read_on": reading.read_on if c else None,
                     "agrees": c is not None and (c.get("value") in (None, value))})
    also = {"search.TAG_SLOTS": search_mod.TAG_SLOTS,
            "search.TAG_MAX_CHARS": search_mod.TAG_MAX_CHARS,
            "search.TITLE_MAX": search_mod.TITLE_MAX}
    return {"source": SOURCE, "read_on": reading.read_on, "basis": reading.basis,
            "digest": reading.digest(), "limits": rows, "aliases": also,
            "disagreements": [r["rule"] for r in rows if not r["agrees"]]}


def watch(db) -> dict:
    """The search and ads policy watch (F-291): each reading, its freshness and its changes."""
    from ..gates.platform_policy import freshness, unreviewed_changes

    fresh = freshness(db)
    changes = [c for c in unreviewed_changes(db) if c["source"] in (SOURCE, ADS_SOURCE)]
    out = {}
    for source in (SOURCE, ADS_SOURCE):
        state = ("never_checked" if source in fresh.get("never_checked", []) else
                 "stale" if source in fresh.get("stale", []) else "current")
        out[source] = {"stamp": stamp(db, source), "freshness": state,
                       "unreviewed_change": any(c["source"] == source for c in changes)}
    return {"sources": out, "unreviewed_changes": changes,
            "refetch": ("not automated: Etsy help/legal pages answer HTTP 403 to automated "
                        "fetchers; a new reading arrives through the owner's page reading "
                        "(platform_policy.record_page_reading) and material change is decided "
                        "by record_snapshot"),
            "ads_terms": onsite_ads_terms()}


# ---- F-264 / F-265 onsite-ads thresholds, read from the watched reading (F-291) ----------

def _usd(text: str, pattern: str) -> float | None:
    m = re.search(pattern, text)
    return float(m.group(1)) if m else None


def onsite_ads_terms() -> dict:
    """The onsite Etsy Ads thresholds, read out of `advertising_rules` and never restated."""
    from ..gates.policy_knowledge import READINGS

    reading = READINGS[ADS_SOURCE]
    by_rule = {c.get("rule"): c for c in reading.conclusions}
    lo = by_rule.get("onsite_ads_min_daily_budget") or {}
    hi = by_rule.get("onsite_ads_per_listing_controls_threshold") or {}
    return {"min_daily_usd": _usd(lo.get("text", ""), r"US\$(\d+(?:\.\d+)?)-"),
            "recommended_daily_usd": _usd(lo.get("text", ""), r"US\$\d+-(\d+(?:\.\d+)?)"),
            "per_listing_controls_min_daily_usd": _usd(hi.get("text", ""),
                                                       r"at least US\$(\d+(?:\.\d+)?)"),
            "status": {"min": lo.get("status"), "controls": hi.get("status")},
            "reading": {"source": ADS_SOURCE, "read_on": reading.read_on,
                        "digest": reading.digest()}}


def ads_plan_findings(*, daily_usd: float, per_listing_controls: bool = False) -> list[str]:
    """What an onsite-ads plan claims that the current guidance does not support (F-264/265)."""
    terms = onsite_ads_terms()
    out: list[str] = []
    floor = terms["min_daily_usd"]
    if floor is not None and daily_usd < floor:
        out.append(f"ADS_BUDGET_BELOW_LEARNING_FLOOR: US${daily_usd:.2f}/day is under the "
                   f"US${floor:g}/day the current guidance recommends to learn anything")
    ctl = terms["per_listing_controls_min_daily_usd"]
    if per_listing_controls and ctl is not None and daily_usd < ctl:
        out.append(f"ADS_CONTROLS_UNAVAILABLE: per-listing strategy controls need US${ctl:g}/"
                   f"day; at US${daily_usd:.2f} they are not available and may not be planned")
    return out
