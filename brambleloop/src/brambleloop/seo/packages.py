"""The Etsy search package: one durable, evidence-labelled search record per drafted listing.

Wave-4 lane W4-SEO. The release chain's `listing.seo` handler decides a listing's search
fields once, at release time, and spreads the result over four places: the `listings` row
(title, tags, description, price), the `listing_search_profiles` row (category, attributes,
property payload, query -> field matrix, tag provenance, the F-004 search certificate), the
`listing.seo_drafted` audit row (intent coverage, match/rank stages, buyer language) and the
`pricing.positioned` audit row (price, band, basis). Nothing put them back together, so no
reader could answer "what is this product's search package, how do we know each part, and is
it ready?" in one place. This module does, and stores the answer:

- `assemble(db, slug, version)` reads those records (read-only) and returns the package:
  primary and secondary search intents, the title, the 13 tags with the dedupe findings, the
  attributes and property payload, the category / taxonomy reading, the description, the
  price with the competitive band it sits in, seasonality, evidence and provenance for every
  tag, the search certificate and its stored-PASS re-check, a readiness state and, once
  stats exist, what the marketplace taught (the `learning` block).
- `record(db, package)` persists it in `seo_search_packages`: idempotent on a content
  fingerprint; a changed package supersedes the previous one (never deleted).
- `refresh(db)` re-assembles every drafted listing's package -- the post-launch update loop.
  `seo.jobs.run_cycle` (the scheduled `seo.cycle`) calls it, so when an owner Stats export
  is recorded (`commerce.listing_outcomes.submit_export` -> `produce`) or a search-term
  export arrives (`POST /api/attribution/stats` -> `seo.evidence`), the next cycle writes a
  new package version whose `learning` block carries impressions / clicks / favourites /
  carts / purchases and the funnel diagnosis, and whose tag evidence carries the measured
  term outcomes.
- `current(db, slug, version)` is the consumer read: the package, but only while it still
  describes the listing as it stands (its `listing_fingerprint` equals the profile's).
  `commerce.search_evidence` reads it for the dashboard and the supremacy gate.

Honesty rules (the company's, applied here):

- **No invented volume.** A tag's basis is `observed` (seen in real buyer language, dated),
  `measured` (an Etsy Stats figure the owner exported) or `modelled` (a template phrase the
  query model wrote). The query model's hand-set `demand` / `competition` constants are never
  copied into a package.
- **UNKNOWN is never 0.** A signal with no source is `None` with a reason.
- **No category is assumed.** Until Etsy's seller taxonomy is read, `taxonomy_id` is None, the
  certificate's category check fails and the package is `EXTERNAL_GATED`, naming the gate.
- Nothing here imports an Etsy client: `writes_to_etsy` is False by construction.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

PACKAGE_VERSION = "seo-package-v1"

# Readiness states.
CERTIFIED = "CERTIFIED"            # stored F-004 certificate PASS and still bound
EXTERNAL_GATED = "EXTERNAL_GATED"  # every check we control passes; Etsy taxonomy unread
PENDING = "PENDING"                # a check is unjudged (the hero), nothing failed
BLOCKED = "BLOCKED"                # a check this company controls failed
READINESS = (CERTIFIED, EXTERNAL_GATED, PENDING, BLOCKED)

TAXONOMY_GATE = ("etsy_taxonomy_read: listing.taxonomy_refresh needs the app keystring "
                 "(ETSY_KEYSTRING / ETSY_API_KEY, read-only GET /seller-taxonomy/*); no Etsy "
                 "taxonomy snapshot is stored, so no category id is chosen and none is assumed")

# Families whose phrases name the product (the primary intent is the product, not the format).
_PRIMARY_FAMILIES = ("buyer_language", "core", "object", "motif", "family", "seasonal")
_TITLE_FIELDS = ("title_front", "title", "title_words")


def _fp(*parts) -> str:
    return hashlib.sha256(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()


def _jsonable(v):
    return json.loads(json.dumps(v, default=str))


# ---- readers (read-only) ----------------------------------------------------------------

def _profile(s, slug: str, version: str):
    from sqlalchemy import select

    from ..core.models import ListingSearchProfile

    return s.scalar(select(ListingSearchProfile).where(
        ListingSearchProfile.product_slug == slug, ListingSearchProfile.version == version))


def _listing(s, slug: str, version: str):
    from sqlalchemy import select

    from ..core.models import Listing

    return s.scalar(select(Listing).where(Listing.product_slug == slug,
                                          Listing.version == version))


def _latest_audit(s, action: str | tuple, artifact: str) -> dict | None:
    from sqlalchemy import desc, select

    from ..core.models import AuditLog

    actions = (action,) if isinstance(action, str) else tuple(action)
    row = s.scalar(select(AuditLog).where(AuditLog.action.in_(actions),
                                          AuditLog.artifact == artifact)
                   .order_by(desc(AuditLog.id)).limit(1))
    return None if row is None else {"action": row.action, "detail": dict(row.detail or {}),
                                     "at": row.at.isoformat() if row.at else None}


# ---- the parts --------------------------------------------------------------------------

def intents(matrix: list[dict], intent_reading: dict | None) -> tuple[dict | None, list[dict]]:
    """(primary, secondary) search intents from the persisted query -> field matrix.

    Primary: the product-naming phrase the title answers (families in `_PRIMARY_FAMILIES`,
    in that order, title fields first). Secondary: one representative matched phrase per
    other (intent, family) pair the listing covers. Ordinal only -- no volume is implied.
    """
    matched = [r for r in matrix if r.get("field")]
    primary = None
    for fam in _PRIMARY_FAMILIES:
        rows = [r for r in matched if r.get("family") == fam]
        rows.sort(key=lambda r: (r.get("field") not in _TITLE_FIELDS,
                                 not str(r.get("provenance", "")).startswith("observed")))
        if rows:
            r = rows[0]
            primary = {"phrase": r["phrase"], "intent": r.get("intent"), "family": fam,
                       "answered_by": r.get("field"),
                       "basis": "observed" if str(r.get("provenance", "")).startswith(
                           "observed") else "modelled",
                       "why": "the product-naming phrase the title answers (ordinal choice, "
                              "no search volume implied)"}
            break
    seen_pairs = {((primary or {}).get("intent"), (primary or {}).get("family"))}
    secondary = []
    for r in matched:
        pair = (r.get("intent"), r.get("family"))
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)
        secondary.append({"phrase": r["phrase"], "intent": r.get("intent"),
                          "family": r.get("family"), "answered_by": r.get("field"),
                          "basis": "observed" if str(r.get("provenance", "")).startswith(
                              "observed") else "modelled"})
    unmatched = [r["phrase"] for r in matrix if not r.get("field")]
    return primary, secondary + ([{"unanswered": unmatched,
                                   "missing_intents": list((intent_reading or {}).get(
                                       "missing") or [])}] if unmatched else [])


def tag_evidence(tags: list[str], provenance: list[dict], evidence_rows: list[dict]) -> list[dict]:
    """Per tag: where it came from and the strongest evidence basis held for it."""
    from . import evidence as ev_mod

    by_tag = {p.get("tag"): p for p in provenance or []}
    phrases = ev_mod.by_phrase(evidence_rows) if evidence_rows else {}
    out = []
    for t in tags:
        p = by_tag.get(t) or {}
        prov = str(p.get("provenance") or "assumed")
        e = phrases.get(" ".join(t.lower().split())) or {}
        basis = ("measured" if e.get("basis") == "measured" else
                 "observed" if prov.startswith("observed") or e.get("basis") == "observed"
                 else "modelled")
        row = {"tag": t, "chars": len(t), "basis": basis, "provenance": prov,
               "read_at": p.get("read_at"),
               "measured": dict(e.get("measured") or {}) or None,
               "sources": list(e.get("sources") or [])[:4]}
        if e.get("vanity"):
            row["learning"] = ("VANITY: shown in the Stats export and never ordered; "
                               "listing.seo re-spends this slot on its next draft")
        elif e.get("earning"):
            row["learning"] = "EARNING: ordered from in the Stats export; keep"
        out.append(row)
    return out


def tag_rules(tags: list[str], *, difficulty: str | None) -> dict:
    """The K1 / G tag rules re-run on the finished set: count, length, charset, dedupe, truth."""
    from ..commerce import search as search_mod
    from ..publish import listing_schema
    from . import constraints

    limits = constraints.working_limits()
    max_n, max_c = limits["tag_max_count"]["value"], limits["tag_max_chars"]["value"]
    problems = []
    if len(tags) != max_n:
        problems.append(f"TAG_COUNT: {len(tags)} tags, {max_n} slots")
    problems += [f"TAG_TOO_LONG: {t!r}" for t in tags if len(t) > max_c]
    lowered = [t.lower().strip() for t in tags]
    problems += [f"TAG_EXACT_DUPLICATE: {t!r}" for t in sorted({t for t in lowered
                                                               if lowered.count(t) > 1})]
    problems += search_mod.tag_diversity_problems(tags)
    problems += search_mod.tags_truth(tags, difficulty=difficulty)
    try:
        problems += list(listing_schema.tag_problems(tags))
    except Exception:  # noqa: BLE001 - the schema check is optional evidence here
        pass
    return {"ok": not problems, "problems": problems,
            "limits": {"tag_max_count": limits["tag_max_count"],
                       "tag_max_chars": limits["tag_max_chars"]},
            "rules": "count == slots, length, exact + semantic duplicates (F-013 intent_key), "
                     "tag truth (F-008), charset/leading-character (listing_schema)"}


def pricing_context(db, slug: str, category: str | None, priced: dict | None) -> dict:
    """The decided price, its basis, and the dated competitor shelf it sits on."""
    from ..commerce import pricing_intel

    d = (priced or {}).get("detail") or {}
    band = d.get("band_cad")
    shelf = pricing_intel.scan_band(pricing_intel.observations_from_competitors(
        category or "unknown"), category or "unknown").to_dict()
    observed_on = sorted({o.observed_on for o in pricing_intel.observations_from_competitors(
        category or "unknown")})
    price = d.get("price_cad")
    position = None
    if isinstance(price, (int, float)) and shelf["observations"]:
        position = ("below shelf low" if price < shelf["low_cad"] else
                    "above shelf high" if price > shelf["high_cad"] else
                    "at or below shelf median" if price <= shelf["median_cad"] else
                    "above shelf median")
    return {"price_cad": price, "net_cad": d.get("net_cad"),
            "band_cad": band, "basis": d.get("basis") or (
                "commerce.pricing decide_price" if price is not None else None),
            "reasons": list(d.get("reasons") or [])[:4],
            "competitive_shelf": {**shelf, "observed_on": observed_on,
                                  "source": "radar/market.py COMPETITORS (shop-level observed "
                                            "price bands of profiled crochet-pattern shops; "
                                            "not category-specific)",
                                  "basis": "observed" if shelf["observations"] else "unknown"},
            "position": position,
            "decided_at": (priced or {}).get("at"),
            "status": "DECIDED" if price is not None else "UNKNOWN"}


def competitive_findings(db, category: str | None, price_cad=None) -> dict:
    """The benchmark seller's stored findings (intel.findings, W4-MJS) for this product's pod.

    Read from the latest `mjs.findings` OperatingReading only -- no network. One benchmark
    seller's shelf is not the Etsy market: prices are `observed` for that seller, favourites
    are a `proxy` for demand, seasonal pods a `proxy` for seasonality. No reading -> UNKNOWN.
    """
    from ..seasonal.daily import DEPARTMENT_OF

    pod = DEPARTMENT_OF.get(str(category or ""))
    try:
        from ..intel import findings as F

        reading = F.latest(db)
    except Exception as exc:  # noqa: BLE001 - unreadable evidence is unknown, never zero
        reading, why = None, f"unreadable: {type(exc).__name__}"
    else:
        why = "no mjs.findings reading stored yet (intel.findings.refresh has not run)"
    if not reading:
        return {"status": "UNKNOWN", "pod": pod, "why": why, "price": None,
                "demand_proxy": None, "seasonality": None, "observed_window": None}
    by_key = {f.get("key"): f for f in (reading.get("findings") or [])}

    def _prov(f):
        p = (f or {}).get("provenance") or {}
        return {"benchmark_key": p.get("benchmark_key"), "source": p.get("source"),
                "sample": p.get("sample"), "grade": ((f or {}).get("confidence") or {})
                .get("grade"), "basis": ((f or {}).get("confidence") or {}).get("basis")}

    pr = by_key.get("pricing")
    band = (((pr or {}).get("metrics") or {}).get("by_pod") or {}).get(pod) if pod else None
    price = None
    if band:
        position = None
        if isinstance(price_cad, (int, float)) and band.get("median") is not None:
            position = ("below benchmark p25" if price_cad < band.get("p25", band["median"])
                        else "above benchmark p75" if price_cad > band.get("p75", band["median"])
                        else "inside benchmark IQR")
        price = {"median_cad": band.get("median"), "p25_cad": band.get("p25"),
                 "p75_cad": band.get("p75"), "n": band.get("n"),
                 "our_price_cad": price_cad, "position": position, **_prov(pr)}
    dm = by_key.get("demand_by_pod")
    favs = (((dm or {}).get("metrics") or {}).get("median_favourites") or {}).get(pod)
    demand = None if favs is None else {
        "median_favourites": favs,
        "underserved_pod": pod in (((dm or {}).get("metrics") or {}).get("underserved") or []),
        **_prov(dm), "note": "favourites are a demand PROXY, not sales or search volume"}
    se = by_key.get("seasonality")
    season = None if se is None else {
        "season_pods": (se.get("metrics") or {}).get("season_pods"),
        "upcoming": [{k: e.get(k) for k in ("event", "date")}
                     for e in ((se.get("metrics") or {}).get("upcoming") or [])],
        "pod_is_seasonal": pod in ((se.get("metrics") or {}).get("season_pods") or {}),
        **_prov(se)}
    window = None
    if pr or dm or se:
        p = (pr or dm or se).get("provenance") or {}
        window = {"as_of": reading.get("as_of"), "observed_from": p.get("observed_from"),
                  "observed_to": p.get("observed_to")}
    return {"status": "OBSERVED" if (price or demand) else "UNKNOWN", "pod": pod,
            "why": None if (price or demand) else f"no benchmark finding for pod {pod!r}",
            "price": price, "demand_proxy": demand, "seasonality": season,
            "observed_window": window,
            "scope": "one benchmark seller (intel.findings); not the Etsy market; no "
                     "competitor title, tag or copy is stored or reused"}


def seasonality(db, slug: str, version: str, record: dict | None) -> dict:
    try:
        from ..publish.release_gates import window_decision

        w = window_decision(db, slug=slug, version=version)
    except Exception as exc:  # noqa: BLE001 - an unreadable window is unknown, not open
        w = {"action": None, "occasion": None, "why": f"unreadable: {type(exc).__name__}"}
    season = (record or {}).get("season")
    return {"season": season, "occasion": w.get("occasion"), "window_action": w.get("action"),
            "may_launch_seasonally": w.get("may_launch_seasonally"),
            "positioning": "seasonal" if season else "evergreen",
            "why": w.get("why"), "source": "publish.release_gates.window_decision + "
                                           + str((record or {}).get("source"))}


def readiness(cert: dict, verdict: str, stored_problems: list[str], *,
              category_status: str | None, listing_present: bool,
              draft_blocking: list[str]) -> dict:
    """One readiness state with the exact gate, from the certificate as stored."""
    checks = cert.get("checks") if isinstance(cert.get("checks"), dict) else {}
    failed = [k for k, v in checks.items() if isinstance(v, dict) and v.get("ok") is False]
    pending = [k for k, v in checks.items()
               if not isinstance(v, dict) or v.get("ok") not in (True, False)]
    if not listing_present:
        return {"state": BLOCKED, "gate": "listing.seo blocked the draft",
                "why": draft_blocking[:6] or ["no drafted listing row"]}
    if verdict == "PASS" and not stored_problems:
        return {"state": CERTIFIED, "gate": None,
                "why": ["F-004 search certificate PASS, still bound to the listing"]}
    taxonomy_only = (set(failed) <= {"category", "attributes"} and "category" in failed
                     and category_status != "CHOSEN")
    if failed and taxonomy_only:
        return {"state": EXTERNAL_GATED, "gate": TAXONOMY_GATE,
                "why": [f"{k}: {checks[k].get('why', '')}"[:240] for k in failed]
                + ([f"also pending: {pending}"] if pending else [])}
    if failed or (verdict == "PASS" and stored_problems):
        return {"state": BLOCKED, "gate": "search certificate",
                "why": ([f"{k}: {checks[k].get('why', '')}"[:240] for k in failed]
                        + stored_problems)[:8]}
    return {"state": PENDING, "gate": f"unjudged checks {pending}",
            "why": [f"{k}: {(checks.get(k) or {}).get('why', '')}"[:240] for k in pending]}


def learning(db, slug: str, tag_rows: list[dict]) -> dict:
    """What the marketplace has taught about this listing. UNKNOWN until a reading exists."""
    from ..commerce import listing_outcomes
    from . import learning as learn_mod

    try:
        row = next((r for r in listing_outcomes.funnel(db) if r["slug"] == slug), None)
    except Exception as exc:  # noqa: BLE001 - an unreadable funnel is unmeasured
        row = None
        why = f"funnel unreadable ({type(exc).__name__})"
    else:
        why = "no recorded Stats period for this listing (not live, or no export yet)"
    keys = ("impressions", "visits", "favourites", "carts", "orders")
    if not row or not row.get("periods"):
        signals = {k: {"value": None, "status": "UNKNOWN", "why": why} for k in keys}
        return {"status": "UNKNOWN", "signals": signals, "periods": 0, "diagnosis": None,
                "next_action": None, "term_learning": [],
                "sources": ["listing_outcomes", "seo_keyword_evidence"]}

    def sig(k):
        v = row.get(k)
        if v == listing_outcomes.UNKNOWN or v is None:
            return {"value": None, "status": "UNKNOWN",
                    "why": f"{k} not recorded in the reading"}
        return {"value": int(v), "status": "MEASURED", "sources": row.get("sources")}

    signals = {k: sig(k) for k in keys}
    o = {"impressions": signals["impressions"]["value"] or 0,
         "visits": signals["visits"]["value"] or 0,
         "orders": signals["orders"]["value"]}
    diag = learn_mod.diagnose(o)
    terms = [{"tag": t["tag"], "learning": t["learning"]} for t in tag_rows if t.get("learning")]
    return {"status": "MEASURED", "signals": signals, "periods": row.get("periods"),
            "rates": learn_mod._rates(o), "stage": row.get("stage"),
            "diagnosis": diag, "next_action": diag.get("next"),
            "term_learning": terms,
            "sources": list(row.get("sources") or []),
            "writes_to_etsy": False}


# ---- assemble / record / refresh / current ----------------------------------------------

def assemble(db, slug: str, version: str, *, evidence_rows: list[dict] | None = None) -> dict | None:
    """The search package for one drafted release, or None when listing.seo never ran."""
    from ..commerce.search import stored_pass_problems
    from ..runtime.release import _product_record
    from . import constraints
    from . import evidence as ev_mod
    from ._db import as_database

    db = as_database(db)
    with db.session() as s:
        prof = _profile(s, slug, version)
        if prof is None:
            return None
        listing = _listing(s, slug, version)
        p = {"category_status": prof.category_status, "taxonomy_id": prof.taxonomy_id,
             "taxonomy_path": list(prof.taxonomy_path or []),
             "attributes": dict(prof.attributes or {}),
             "properties": list(prof.properties or []),
             "matrix": list(prof.coverage_matrix or []),
             "tag_provenance": list(prof.tag_provenance or []),
             "verdict": prof.verdict, "certificate": dict(prof.certificate or {}),
             "fingerprint": prof.fingerprint, "snapshot_id": prof.snapshot_id,
             "updated_at": prof.updated_at.isoformat() if prof.updated_at else None}
        lst = None if listing is None else {
            "title": listing.title, "tags": list(listing.tags or []),
            "description": listing.description, "price_cad": listing.price_cad,
            "state": listing.state, "release_hash": listing.release_hash,
            "etsy_listing_id": listing.etsy_listing_id or None}
        drafted = _latest_audit(s, ("listing.seo_drafted", "listing.seo_blocked"),
                                f"{slug}@{version}")
        priced = _latest_audit(s, "pricing.positioned", slug)
    record = _product_record(slug, {}) or {}
    detail = (drafted or {}).get("detail") or {}
    if evidence_rows is None:
        try:
            evidence_rows = ev_mod.all_rows(db)
        except Exception:  # noqa: BLE001 - no evidence table is no evidence
            evidence_rows = []
    tags = list((lst or {}).get("tags") or [])
    difficulty = p["attributes"].get("skill_level")
    tag_rows = tag_evidence(tags, p["tag_provenance"], evidence_rows)
    stored = (stored_pass_problems(db, slug=slug, version=version)
              if p["verdict"] == "PASS" else [])
    limits = constraints.working_limits()
    title = (lst or {}).get("title")
    primary, secondary = intents(p["matrix"], detail.get("intent_coverage"))
    cert = p["certificate"]
    basis_counts = {b: sum(1 for t in tag_rows if t["basis"] == b)
                    for b in ("measured", "observed", "modelled")}
    pkg = {
        "package_version": PACKAGE_VERSION,
        "slug": slug, "version": version,
        "product": {"source": record.get("source"), "kind": record.get("kind"),
                    "category": record.get("category"), "launch0": record.get("launch0"),
                    "product_key": (str(record.get("source") or "").split(":", 1)[-1]
                                    or slug)},
        "primary_intent": primary,
        "secondary_intents": secondary,
        "title": {"text": title, "chars": len(title or ""),
                  "limit": limits["title_max_chars"],
                  "front_scan": detail.get("front_scan")},
        "tags": {"values": tags, "count": len(tags), "evidence": tag_rows,
                 "basis_counts": basis_counts,
                 "rules": tag_rules(tags, difficulty=difficulty)},
        "attributes": p["attributes"],
        "category": {"status": p["category_status"], "taxonomy_id": p["taxonomy_id"],
                     "path": p["taxonomy_path"], "snapshot_id": p["snapshot_id"],
                     "intent": record.get("category"),
                     "property_payload": p["properties"],
                     "gate": None if p["category_status"] == "CHOSEN" else TAXONOMY_GATE},
        "description": {"text": (lst or {}).get("description"),
                        "chars": len((lst or {}).get("description") or ""),
                        "checks": (cert.get("checks") or {}).get("description")},
        "pricing": pricing_context(db, slug, record.get("category"), priced),
        "seasonality": seasonality(db, slug, version, record),
        "competitive": competitive_findings(
            db, record.get("category"),
            (((priced or {}).get("detail") or {}).get("price_cad"))),
        "search_stages": detail.get("search_stages"),
        "intent_coverage": detail.get("intent_coverage"),
        "buyer_language": detail.get("buyer_language"),
        "evidence": {
            "demand_basis": ("measured" if basis_counts["measured"] else
                             "observed" if basis_counts["observed"] else "modelled"),
            "volumes": None,
            "volumes_why": "no measured Etsy search volume exists for any phrase; the query "
                           "model's demand/competition constants are modelled and are not "
                           "copied here (F-020)",
            "sources": ["listing_search_profiles", "listings", "audit_log:listing.seo_*",
                        "audit_log:pricing.positioned", "seo_keyword_evidence",
                        "seo.constraints", "radar/market.py", "listing_outcomes",
                        "operating_readings:mjs.findings (intel.findings)"],
            "constraints_status": {k: v["status"] for k, v in limits.items()},
        },
        "certificate": {"verdict": p["verdict"], "checks": cert.get("checks"),
                        "failed": cert.get("failed"), "pending": cert.get("pending"),
                        "reasons": list(cert.get("reasons") or [])[:8],
                        "search_policy": cert.get("search_policy"),
                        "stored_pass_problems": stored,
                        "basis": cert.get("basis")},
        "readiness": readiness(cert, p["verdict"], stored,
                               category_status=p["category_status"],
                               listing_present=lst is not None,
                               draft_blocking=list(detail.get("blocking") or [])),
        "listing": {k: (lst or {}).get(k) for k in ("state", "release_hash",
                                                    "etsy_listing_id", "price_cad")},
        "listing_fingerprint": p["fingerprint"],
        "profile_updated_at": p["updated_at"],
        "learning": learning(db, slug, tag_rows),
        "writes_to_etsy": False,
    }
    pkg = _jsonable(pkg)
    pkg["fingerprint"] = _fp({k: v for k, v in pkg.items()
                              if k not in ("profile_updated_at", "fingerprint")}
                             | {"pricing": {k: v for k, v in pkg["pricing"].items()
                                            if k != "decided_at"},
                                "competitive": {k: v for k, v in pkg["competitive"].items()
                                                if k != "observed_window"}})
    return pkg


def record(db, pkg: dict, *, now: datetime | None = None) -> dict:
    """Persist a package; idempotent on its fingerprint. A change supersedes the old one."""
    from sqlalchemy import select

    from ._db import session
    from .models import SeoSearchPackage, ensure_tables

    now = now or datetime.now(timezone.utc)
    ensure_tables(db)
    slug, version = pkg["slug"], pkg["version"]
    with session(db) as s:
        same = s.scalar(select(SeoSearchPackage).where(
            SeoSearchPackage.product_slug == slug, SeoSearchPackage.version == version,
            SeoSearchPackage.fingerprint == pkg["fingerprint"]))
        if same is not None and same.state == "CURRENT":
            return {"written": False, "id": same.id, "state": same.state}
        for old in s.scalars(select(SeoSearchPackage).where(
                SeoSearchPackage.product_slug == slug, SeoSearchPackage.version == version,
                SeoSearchPackage.state == "CURRENT")):
            old.state, old.superseded_at = "SUPERSEDED", now
        if same is not None:            # inputs returned to an earlier package
            same.state, same.superseded_at = "CURRENT", None
            s.flush()
            return {"written": True, "id": same.id, "state": "CURRENT", "restored": True}
        row = SeoSearchPackage(
            product_slug=slug, version=version, package_version=pkg["package_version"],
            fingerprint=pkg["fingerprint"], listing_fingerprint=pkg["listing_fingerprint"] or "",
            state="CURRENT", readiness=pkg["readiness"]["state"],
            verdict=pkg["certificate"]["verdict"] or "",
            learning_status=pkg["learning"]["status"], package=pkg, created_at=now)
        s.add(row)
        s.flush()
        return {"written": True, "id": row.id, "state": "CURRENT"}


KEYWORD_INTENT_PREFIX = "package:"   # Keyword.intent for rows this module owns
_BASIS_RANK = {"modelled": 0, "observed": 1, "measured": 2}


def keyword_phrases(pkg: dict) -> dict[str, str]:
    """{phrase: basis} for the phrases a package's listing answers (tags + matched intents)."""
    out: dict[str, str] = {}

    def _add(phrase, basis):
        phrase = " ".join(str(phrase or "").lower().split())[:120]
        if not phrase:
            return
        basis = basis if basis in _BASIS_RANK else "modelled"
        if _BASIS_RANK[basis] >= _BASIS_RANK.get(out.get(phrase, "modelled"), 0):
            out[phrase] = basis

    for t in ((pkg.get("tags") or {}).get("evidence") or []):
        _add(t.get("tag"), t.get("basis"))
    for i in [pkg.get("primary_intent")] + list(pkg.get("secondary_intents") or []):
        if i and i.get("phrase") and i.get("answered_by"):
            _add(i["phrase"], i.get("basis"))
    return out


def sync_keywords(db, pkg: dict, *, now: datetime | None = None) -> dict:
    """Persist the package's answered phrases as `Keyword` rows (W4L-1, for Learn's cell).

    Rows this module owns carry `intent = "package:<basis>"` and `covered_by` lists the
    releases (`slug@version`) whose CURRENT package answers the phrase, so coverage is a
    deterministic fact about our own listings. No volume is written: `est_demand` /
    `est_competition` keep the column default, and every reader skips package rows for
    those columns (seo.evidence) or for observed-language / query-budget purposes
    (commerce.intent, intel.insights_budget). A row someone else owns only gains coverage.
    """
    from sqlalchemy import select

    from ..core.models import Keyword
    from ._db import session

    now = now or datetime.now(timezone.utc)
    slug, version = pkg["slug"], pkg["version"]
    ref = f"{slug}@{version}"
    wanted = keyword_phrases(pkg)
    added, removed = 0, 0
    with session(db) as s:
        rows = {r.phrase: r for r in s.scalars(select(Keyword))}
        for phrase, row in rows.items():   # drop this release's stale coverage
            cov = list(row.covered_by or [])
            if ref in cov and phrase not in wanted:
                cov.remove(ref)
                row.covered_by, row.updated_at = cov, now
                if not cov and str(row.intent or "").startswith(KEYWORD_INTENT_PREFIX):
                    s.delete(row)
                    removed += 1
        for phrase, basis in wanted.items():
            row = rows.get(phrase)
            if row is None:
                s.add(Keyword(phrase=phrase, intent=f"{KEYWORD_INTENT_PREFIX}{basis}",
                              covered_by=[ref], coverage=1.0, updated_at=now))
                added += 1
                continue
            cov = list(row.covered_by or [])
            if ref not in cov:
                row.covered_by = cov + [ref]
                row.updated_at = now
            row.coverage = max(float(row.coverage or 0.0), 1.0)
            owned = str(row.intent or "")
            if owned.startswith(KEYWORD_INTENT_PREFIX) and _BASIS_RANK.get(basis, 0) > \
                    _BASIS_RANK.get(owned[len(KEYWORD_INTENT_PREFIX):], 0):
                row.intent = f"{KEYWORD_INTENT_PREFIX}{basis}"
    return {"phrases": len(wanted), "added": added, "removed": removed}


def record_from_release(db, slug: str, version: str) -> dict:
    """Assemble and persist one release's package (the listing.seo / seo.cycle producer)."""
    pkg = assemble(db, slug, version)
    if pkg is None:
        return {"written": False, "why": "no search profile"}
    out = record(db, pkg)
    out["keywords"] = sync_keywords(db, pkg)
    return {**out, "readiness": pkg["readiness"]["state"],
            "verdict": pkg["certificate"]["verdict"]}


def refresh(db, *, now: datetime | None = None) -> dict:
    """Re-assemble every drafted listing's package (the post-launch update loop)."""
    from sqlalchemy import select

    from ..core.models import ListingSearchProfile
    from . import evidence as ev_mod
    from ._db import as_database

    db = as_database(db)
    with db.session() as s:
        keys = [(r.product_slug, r.version) for r in s.scalars(
            select(ListingSearchProfile).order_by(ListingSearchProfile.id))]
    try:
        rows = ev_mod.all_rows(db)
    except Exception:  # noqa: BLE001
        rows = []
    written, unchanged, readiness_counts = [], [], {}
    for slug, version in keys:
        pkg = assemble(db, slug, version, evidence_rows=rows)
        if pkg is None:
            continue
        out = record(db, pkg, now=now)
        sync_keywords(db, pkg, now=now)
        (written if out["written"] else unchanged).append(f"{slug}@{version}")
        st = pkg["readiness"]["state"]
        readiness_counts[st] = readiness_counts.get(st, 0) + 1
    return {"packages": len(keys), "written": written, "unchanged": unchanged,
            "readiness": readiness_counts, "writes_to_etsy": False}


def current(db, slug: str, version: str) -> dict | None:
    """The CURRENT package, only while it is bound to the listing as it stands."""
    from sqlalchemy import desc, select

    from ._db import session
    from .models import SeoSearchPackage, tables_exist

    if not tables_exist(db):
        return None
    with session(db) as s:
        row = s.scalar(select(SeoSearchPackage).where(
            SeoSearchPackage.product_slug == slug, SeoSearchPackage.version == version,
            SeoSearchPackage.state == "CURRENT").order_by(desc(SeoSearchPackage.id)).limit(1))
        if row is None:
            return None
        prof = _profile(s, slug, version)
        if prof is None or (prof.fingerprint or "") != (row.listing_fingerprint or ""):
            return None
        return {**dict(row.package or {}), "id": row.id,
                "created_at": row.created_at.isoformat() if row.created_at else None}


def history(db, slug: str, version: str) -> list[dict]:
    from sqlalchemy import select

    from ._db import session
    from .models import SeoSearchPackage, tables_exist

    if not tables_exist(db):
        return []
    with session(db) as s:
        return [{"id": r.id, "state": r.state, "readiness": r.readiness,
                 "verdict": r.verdict, "learning_status": r.learning_status,
                 "fingerprint": r.fingerprint,
                 "created_at": r.created_at.isoformat() if r.created_at else None}
                for r in s.scalars(select(SeoSearchPackage).where(
                    SeoSearchPackage.product_slug == slug,
                    SeoSearchPackage.version == version).order_by(SeoSearchPackage.id))]
