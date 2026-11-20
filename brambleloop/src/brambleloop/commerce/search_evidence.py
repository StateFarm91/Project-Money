"""Search evidence dashboard and Search Supremacy Gate (F-058, F-060; serves F-001/F-002).

F-058 asks for one place that exposes match coverage, rank readiness, visibility warnings,
CTR, conversion and experiments. They existed on five routes; `summary(db)` puts them side by
side per listing, each labelled with its basis, and `GET /api/search-evidence` serves it.
Every number keeps the label it was born with: the coverage proxy is a planning proxy,
observed CTR/conversion exist only from recorded `ListingOutcome` periods, and anything
missing is UNMEASURED, never 0.

F-060: before scaling paid traffic, `supremacy_gate(db)` requires, for every drafted listing:

- **truthful_query_coverage** -- the stored search certificate PASSes (category, attributes,
  copy, true tags and description, hero) and is still bound to the listing and the current
  search guidance (F-242), and stage 1 matched the target queries;
- **competitive_thumbnail** -- frame 1 is certified through the four listing-set gates
  (`ranking_readiness.click_readiness`);
- **conversion_readiness** -- price, disclosure and the first-customer gate pass
  (`ranking_readiness.conversion_readiness`) and the gallery does every applicable job
  (`publish.eligibility.gallery_architecture`, F-030/F-254);
- **no_unresolved_first_party_warning** -- a complete Search Visibility reading is on file
  and no item is open or awaiting a confirming reading (`commerce.search_visibility`).

UNMEASURED is never PASS. `commerce.trust.may_scale_ads` reads this gate beside its own rungs.
"""
from __future__ import annotations

from datetime import datetime, timezone

PASS = "PASS"
FAIL = "FAIL"
UNMEASURED = "UNMEASURED"
RUNGS = ("truthful_query_coverage", "competitive_thumbnail", "conversion_readiness",
         "no_unresolved_first_party_warning")
# Stage 1 must match at least this share of the listing's own target queries. A listing that
# matches under half of the phrases it was built for is not covering its query set, however
# well the matched half is placed. Modelled policy, not an Etsy number.
MIN_MATCH_RATE = 0.5


def _profiles(db) -> list:
    from sqlalchemy import select

    from ..core.models import ListingSearchProfile

    with db.session() as s:
        return [{"slug": r.product_slug, "version": r.version, "verdict": r.verdict,
                 "matrix": list(r.coverage_matrix or []),
                 "certificate": dict(r.certificate or {}) if isinstance(r.certificate, dict)
                 else {}, "taxonomy_path": list(r.taxonomy_path or []),
                 "updated_at": r.updated_at}
                for r in s.scalars(select(ListingSearchProfile)
                                   .order_by(ListingSearchProfile.id))]


def match_stage(matrix: list[dict]) -> dict:
    """Stage 1 (F-001) from the persisted query -> field matrix (F-002)."""
    by_family: dict[str, dict] = {}
    by_field: dict[str, int] = {}
    for row in matrix:
        fam = by_family.setdefault(row.get("family") or "", {"queries": 0, "matched": 0})
        fam["queries"] += 1
        if row.get("field"):
            fam["matched"] += 1
            by_field[row["field"]] = by_field.get(row["field"], 0) + 1
    matched = sum(f["matched"] for f in by_family.values())
    return {"queries": len(matrix), "matched": matched,
            "match_rate": round(matched / len(matrix), 4) if matrix else None,
            "by_family": by_family, "by_field": by_field,
            "basis": "persisted coverage_matrix (listing.seo), lexical match only"}


def _category_for(slug: str) -> tuple[str, int | None, int | None]:
    """(catalogue category, sizes sold, colours) for the release `slug`, from its certified CIR.

    Sizes and colours are read from the same certified CIR (and Launch-0 sibling variants)
    the listing-set gallery frames are drawn from (`visual.launch_imagery._primary_for`):
    sizes = the primary variant plus its siblings sold on the same listing, colours =
    ``len(cir.colors)``. A release with no certified CIR answers None for both -- UNKNOWN,
    never a guessed 1 that would quietly drop SIZING or COLOUR_CONTEXT from the applicable
    jobs (wiring #7)."""
    category = ""
    try:
        from ..runtime.release import _product_record

        category = str((_product_record(slug, {}) or {}).get("category") or "")
    except Exception:  # noqa: BLE001 - an unknown record is an unknown category
        category = ""
    try:
        from ..visual.launch_imagery import _primary_for

        found = _primary_for(slug)
    except Exception:  # noqa: BLE001 - an unreadable CIR is an unknown variant shape
        found = None
    if found is None:
        return category, None, None
    _listing, _title, primary, siblings, cat = found
    return (category or str(cat or "")), 1 + len(siblings), len(primary.colors or {})


def gallery(db, slug: str, version: str) -> dict:
    """The applicable gallery jobs against the valid listing-set certificate's frames."""
    from sqlalchemy import desc, select

    from ..core.models import ListingSetCertificateRecord
    from ..publish import eligibility as el

    with db.session() as s:
        rec = s.scalar(select(ListingSetCertificateRecord).where(
            ListingSetCertificateRecord.product_slug == slug,
            ListingSetCertificateRecord.version == version,
            ListingSetCertificateRecord.state == "valid")
            .order_by(desc(ListingSetCertificateRecord.id)).limit(1))
        jobs = [f.get("job") for f in ((rec.certificate or {}).get("frames") or [])
                if f.get("job")] if rec is not None else None
    category, sizes, colours = _category_for(slug)
    if jobs is None:
        return {"status": UNMEASURED, "why": "no valid listing-set certificate for this release",
                "category": category}
    if sizes is None or colours is None:
        return {"status": UNMEASURED, "category": category,
                "why": "no certified CIR to count the sizes and colours sold from"}
    arch = el.gallery_architecture(category, jobs, sizes=sizes, colours=colours)
    return {"status": PASS if arch["complete"] else FAIL, **arch,
            "sizes": sizes, "colours": colours}


def _experiments(db, slug: str) -> list[dict]:
    from sqlalchemy import select

    from ..core.models import Experiment

    with db.session() as s:
        return [{"name": e.name, "kind": e.kind, "state": e.state}
                for e in s.scalars(select(Experiment).where(Experiment.product_slug == slug))]


def _visibility(db) -> dict:
    from . import search_visibility as sv

    st = sv.state(db)
    if not st["readings_on_file"]:
        return {"status": UNMEASURED, "open": [], "pending": [],
                "why": "no Search Visibility reading is on file (owner intake: "
                       "POST /api/search-visibility; needs a live shop)"}
    unresolved = st["open"] + st["remediated_pending"]
    return {"status": FAIL if unresolved else PASS,
            "open": [r["key"] for r in st["open"]],
            "pending": [r["key"] for r in st["remediated_pending"]],
            "latest_reading_at": st["latest_reading_at"],
            "why": ("unresolved first-party warnings" if unresolved else
                    "the latest complete reading lists nothing unresolved")}


def listing_evidence(db, prof: dict, *, shared: dict, funnel: dict, visibility: dict) -> dict:
    from . import ranking_readiness as rr
    from . import search_policy
    from .search import stored_pass_problems

    slug, version = prof["slug"], prof["version"]
    readiness = rr.profile(db, slug, version, shared=shared)
    stage1 = match_stage(prof["matrix"])
    policy = search_policy.certificate_problems(db, prof["certificate"].get("search_policy"))
    stale = stored_pass_problems(db, slug=slug, version=version) if prof["verdict"] == PASS \
        else [f"stored search verdict is {prof['verdict']}"]
    row = funnel.get(slug) or {}
    imp, visits, orders = (row.get("impressions"), row.get("visits"), row.get("orders"))

    def rate(n, d):
        return (round(n / d, 4) if isinstance(n, int) and isinstance(d, int) and d > 0
                else UNMEASURED)

    gal = gallery(db, slug, version)
    try:
        from ..seo import packages as _packages

        pkg = _packages.current(db, slug, version)
    except Exception:  # noqa: BLE001 - an unreadable package is no package
        pkg = None
    return {
        "search_package": (None if pkg is None else {
            "id": pkg.get("id"), "readiness": pkg.get("readiness"),
            "primary_intent": pkg.get("primary_intent"),
            "tag_basis": (pkg.get("tags") or {}).get("basis_counts"),
            "learning_status": (pkg.get("learning") or {}).get("status"),
            "fingerprint": pkg.get("fingerprint")}),
        "slug": slug, "version": version,
        "match": stage1,
        "query_field_matrix": prof["matrix"],
        "rank_readiness": {"dimensions": rr.summary(readiness),
                           "certificate": prof["verdict"], "certificate_problems": stale,
                           "search_policy": policy},
        "gallery": gal,
        "visibility_warnings": visibility,
        "ctr": {"value": rate(visits, imp), "basis": "ListingOutcome visits / impressions"
                if rate(visits, imp) != UNMEASURED else "no recorded period (live_listings)"},
        "conversion": {"value": rate(orders, visits),
                       "basis": "orders / visits over recorded periods"
                       if rate(orders, visits) != UNMEASURED else
                       "no recorded period (live_listings)"},
        "funnel_stage": row.get("stage", UNMEASURED),
        "experiments": _experiments(db, slug),
        "_readiness": readiness,
    }


def _rungs(ev: dict) -> dict:
    stage1 = ev["match"]
    dims = ev["_readiness"]["dimensions"]

    def dim(name):
        d = dims[name]
        return (UNMEASURED if d["status"] != "MEASURED" else
                PASS if d["verdict"] == "PASS" else FAIL), d.get("why", "")

    cert_ok = ev["rank_readiness"]["certificate"] == PASS and \
        not ev["rank_readiness"]["certificate_problems"]
    rate = stage1["match_rate"]
    coverage = (PASS if cert_ok and rate is not None and rate >= MIN_MATCH_RATE else
                FAIL if ev["rank_readiness"]["certificate"] in ("REFUSED", "STALE")
                or (rate is not None and rate < MIN_MATCH_RATE)
                or ev["rank_readiness"]["certificate_problems"] else UNMEASURED)
    if ev["rank_readiness"]["certificate"] == "PENDING":
        coverage = UNMEASURED
    # W4-SEO: coverage is truthful only for a listing whose search package is on file and
    # bound to the listing as it stands (`seo.packages.current`). Tightens only.
    package_note = ""
    if ev.get("search_package") is None:
        package_note = "; no current search package bound to this listing"
        if coverage == PASS:
            coverage = UNMEASURED
    thumb, thumb_why = dim("click_readiness")
    conv, conv_why = dim("conversion_readiness")
    gal = ev["gallery"]["status"]
    conversion = (FAIL if FAIL in (conv, gal) else
                  UNMEASURED if UNMEASURED in (conv, gal) else PASS)
    return {
        "truthful_query_coverage": {"verdict": coverage, "why": (
            f"certificate {ev['rank_readiness']['certificate']}; match rate {rate}; "
            + "; ".join(ev["rank_readiness"]["certificate_problems"][:2])
            + package_note)[:300]},
        "competitive_thumbnail": {"verdict": thumb, "why": thumb_why[:300]},
        "conversion_readiness": {"verdict": conversion, "why": (
            f"{conv_why}; gallery: {ev['gallery'].get('missing') or ev['gallery'].get('why')}"
            )[:300]},
        "no_unresolved_first_party_warning": {"verdict": ev["visibility_warnings"]["status"],
                                              "why": ev["visibility_warnings"]["why"]},
    }


def _collect(db) -> tuple[list[dict], dict]:
    from . import listing_outcomes
    from . import ranking_readiness as rr

    profiles = _profiles(db)
    shared = rr.shop_wide(db) if profiles else {}
    try:
        funnel = {r["slug"]: r for r in listing_outcomes.funnel(db)}
    except Exception:  # noqa: BLE001 - an unreadable funnel is unmeasured
        funnel = {}
    visibility = _visibility(db)
    rows = [listing_evidence(db, p, shared=shared, funnel=funnel, visibility=visibility)
            for p in profiles]
    return rows, visibility


def supremacy_gate(db) -> dict:
    """F-060: may paid traffic scale on search grounds? Per listing, four rungs, no blend."""
    rows, visibility = _collect(db)
    listings = [{"slug": r["slug"], "version": r["version"], "rungs": _rungs(r)} for r in rows]
    failed = sorted({k for l in listings for k, v in l["rungs"].items()
                     if v["verdict"] == FAIL})
    unmeasured = sorted({k for l in listings for k, v in l["rungs"].items()
                         if v["verdict"] == UNMEASURED})
    if not listings:
        unmeasured = list(RUNGS)
    return {"cleared": bool(listings) and not failed and not unmeasured,
            "failed": failed, "unmeasured": unmeasured, "listings": listings,
            "rungs": list(RUNGS),
            "why": ("no drafted listing has a search profile, so nothing is measured"
                    if not listings else
                    "every listing passes every search rung" if not failed and not unmeasured
                    else f"search rungs failed {failed}, unmeasured {unmeasured}")}


def summary(db) -> dict:
    """The provider-contract reading: one search evidence row per drafted listing (F-058)."""
    from . import search_policy

    rows, visibility = _collect(db)
    items = []
    for r in rows:
        item = {k: v for k, v in r.items() if k != "_readiness"}
        item["rungs"] = _rungs(r)
        items.append(item)
    gate = {"cleared": bool(items) and all(v["verdict"] == PASS for i in items
                                           for v in i["rungs"].values())}
    return {"status": ("UNKNOWN" if not items else "OK" if gate["cleared"] else "DEGRADED"),
            "as_of": datetime.now(timezone.utc).isoformat(),
            "basis": "measured" if items else "unknown",
            "items": items,
            "visibility_warnings": visibility,
            "search_policy": {"stamp": search_policy.stamp(db),
                              "limits": search_policy.limits()},
            "supremacy_gate": gate,
            "reason": None if items else "no drafted listing has a search profile yet",
            "sources": ["listing_search_profiles", "listing_set_certificates",
                        "listing_outcomes", "experiments", "search_visibility_items",
                        "policy_snapshots", "seo_search_packages"]}
