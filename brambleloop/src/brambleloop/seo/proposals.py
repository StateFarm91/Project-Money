"""Title / tag / attribute proposals for Launch-0 drafts. Proposals only -- never written to Etsy.

The proposal reuses the release chain's own builders (`commerce.seo.build_title`,
`commerce.search.build_query_set` / `choose_tags` / `listing_attributes`,
`commerce.intent.listing_language`) so a proposal and a release draft are produced by the same
rules. What this module adds is the evidence loop and the truth guardrail:

- **Evidence first.** A term the owner's Etsy Stats export shows *earning* (orders > 0) is
  offered a slot first; a term it shows as *vanity* (shown, never ordered) is withheld. Observed
  buyer language (`intent.listing_language`) comes next. Everything else is a modelled template
  phrase, labelled `modelled` on the proposal -- never presented as demand evidence.
- **Truth always.** Every candidate phrase, from any source, must pass
  `seo.truth.check_term` against the product's verified facts before it may hold a slot, and
  the finished title + tag set must pass `seo.truth.validate_listing`. Evidence never overrides
  truth: an earning term this product cannot truthfully claim is rejected and reported.

Nothing here imports an Etsy client; `writes_to_etsy` is False on every proposal by
construction. Applying a proposal is a separate, authority-gated publish decision.
"""
from __future__ import annotations

PROPOSAL_VERSION = "seo-proposal-v1"


def _current_draft(db, slug: str) -> dict | None:
    from sqlalchemy import desc, select

    from ..core.models import Listing
    from ._db import session

    try:
        with session(db) as s:
            row = s.scalar(select(Listing).where(Listing.product_slug == slug)
                           .order_by(desc(Listing.id)).limit(1))
            if row is None:
                return None
            return {"listing_id": row.id, "version": row.version, "title": row.title,
                    "tags": list(row.tags or []), "state": row.state,
                    "etsy_listing_id": row.etsy_listing_id or None}
    except Exception:  # noqa: BLE001 - no listings table: no draft
        return None


def queries_for(facts) -> list:
    from ..commerce import search as search_mod

    return search_mod.build_query_set(facts.category, list(facts.qualifiers), facts.season,
                                      list(facts.techniques), difficulty=facts.difficulty)


def _buyer_language(db, facts) -> dict:
    from ..commerce import intent as intent_mod
    from ._db import as_database

    try:
        return intent_mod.listing_language(as_database(db), slug=facts.slug,
                                           category=facts.category, season=facts.season,
                                           difficulty=facts.difficulty,
                                           techniques=list(facts.techniques))
    except Exception as exc:  # noqa: BLE001 - no benchmark tables: no observed language
        return {"mapped": False, "tags": [], "queries": [],
                "why": f"buyer language unavailable ({type(exc).__name__})"}


def propose(db, facts, *, evidence_rows: list[dict] | None = None,
            competitors: list[str] | None = None, buyer: dict | None = None) -> dict:
    """One proposal for one Launch-0 variant."""
    from ..commerce import search as search_mod
    from ..commerce import seo as seo_mod
    from . import evidence as ev_mod
    from . import truth

    competitors = truth.competitor_names(db) if competitors is None else competitors
    rows = ev_mod.all_rows(db) if evidence_rows is None else evidence_rows
    ev = ev_mod.by_phrase(rows)
    queries = queries_for(facts)
    buyer = _buyer_language(db, facts) if buyer is None else buyer

    rejected: list[dict] = []

    def truthful(phrase: str, origin: str) -> bool:
        v = truth.check_term(phrase, facts, competitors=competitors)
        if not v.ok:
            rejected.append({"phrase": phrase, "origin": origin, "findings": v.findings})
        return v.ok

    vanity = {p for p, e in ev.items() if e.get("vanity")}
    earning = sorted((p for p, e in ev.items() if e.get("earning")),
                     key=lambda p: -(ev[p]["measured"].get("stats_orders") or 0))
    must: list[str] = []
    for p in earning:
        if len(p) <= seo_mod.TAG_MAX_CHARS and truthful(p, "etsy_stats_export:earning"):
            must.append(p)
    for p in buyer.get("tags") or []:
        if p not in must and p not in vanity and truthful(p, "intent.listing_language"):
            must.append(p)
    must = must[:6]   # evidence earns slots; it does not take the whole set

    pool = [q for q in queries + list(buyer.get("queries") or [])
            if q.phrase not in vanity and truthful(q.phrase, f"query:{q.provenance}")]
    tags = search_mod.choose_tags(pool, must_include=must)
    # Belt and braces: whatever choose_tags trimmed must still be true.
    tags = [t for t in tags if truth.check_term(t, facts, competitors=competitors).ok]

    title = seo_mod.build_title(facts.cir_title, facts.category, list(facts.qualifiers),
                                facts.season, sizes=1)
    attributes = search_mod.listing_attributes(category=facts.category,
                                               difficulty=facts.difficulty,
                                               colors=list(facts.colors), season=facts.season)
    attribute_problems = (search_mod.check_attributes(attributes)
                          + search_mod.attribute_truth(attributes, difficulty=facts.difficulty,
                                                       colors=list(facts.colors),
                                                       season=facts.season))
    validation = truth.validate_listing(title, tags, facts, competitors=competitors)

    by_q = {q.phrase: q for q in queries}
    provenance = []
    for t in tags:
        e = ev.get(t)
        basis = e["basis"] if e else ("modelled" if t in by_q else "unknown")
        origin = ("etsy_stats_export:earning" if t in earning else
                  "intent.listing_language" if t in (buyer.get("tags") or []) else
                  f"commerce.search template ({by_q[t].family})" if t in by_q else "derived")
        provenance.append({"tag": t, "basis": basis, "origin": origin,
                           "measured": dict(e["measured"]) if e else {},
                           "sources": list(e["sources"])[:5] if e else [],
                           "trace": truth.check_term(t, facts, competitors=competitors).trace})

    current = _current_draft(db, facts.slug)
    diff = None
    current_validation = None
    if current is not None:
        cur_tags = [t.lower() for t in current["tags"]]
        diff = {"title_changed": current["title"] != title,
                "tags_added": [t for t in tags if t not in cur_tags],
                "tags_removed": [t for t in cur_tags if t not in tags]}
        current_validation = truth.validate_listing(current["title"], current["tags"], facts,
                                                    competitors=competitors)

    basis_of_tags: dict[str, int] = {}
    for p in provenance:
        basis_of_tags[p["basis"]] = basis_of_tags.get(p["basis"], 0) + 1
    ok = validation["ok"] and not attribute_problems
    return {
        "version": PROPOSAL_VERSION, "slug": facts.slug, "candidate": facts.candidate,
        "state": "PROPOSED", "writes_to_etsy": False, "ok": ok,
        "title": title, "tags": tags, "attributes": attributes,
        "attribute_problems": attribute_problems, "validation": validation,
        "tag_provenance": provenance, "tag_basis_counts": basis_of_tags,
        "rejected_candidates": rejected[:40],
        "withheld_vanity_terms": sorted(vanity)[:20],
        "buyer_language": {"mapped": buyer.get("mapped"), "tags": list(buyer.get("tags") or []),
                           "why": buyer.get("why", "")},
        "current_draft": current, "current_validation": current_validation, "diff": diff,
        "facts": facts.to_dict(),
        "note": ("a proposal; nothing here is written to Etsy. Tag demand figures are "
                 "modelled unless a tag's basis says measured"),
    }
