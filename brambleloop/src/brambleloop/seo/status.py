"""Provider contract for the Owner Command Center (lane C) and the orchestrator (lane A).

`summary(db) -> dict` -- keyword / taxonomy / search readiness.
Always returns a JSON-serialisable dict with:

    status   "OK" | "DEGRADED" | "BLOCKED" | "UNKNOWN"
    as_of    UTC ISO 8601 of the last SEO cycle that changed something, or None
    basis    "measured" | "estimated" | "modelled" | "unknown"
    items    one dict per Launch-0 variant: slug, proposal ok, title, tag count, tag basis
             counts, taxonomy status, attribution status
    sources  provenance strings (tables / modules read)
    reason   why the status is what it is
    kpis     F-918 outcome KPIs, each with its basis, plus `guardrails`
    taxonomy readiness rows (computed even before any cycle)

Never raises; an empty or unmigrated database is `UNKNOWN` with a reason. Read-only: it
creates no table and writes no row.

`next_work(db) -> list[dict]` -- the SEO department's unblocked and gated work, most urgent
first. Each item:

    key            stable id (safe as an idempotency key)
    department     "seo"
    title          one line
    kind           "internal" (the orchestrator may run it) | "owner" (needs the owner) |
                   "gated" (waits on a gate; do not run)
    action         what to run: a dotted callable ("brambleloop.seo.jobs.run_cycle") or a job
                   type ("listing.taxonomy_refresh"), or an owner instruction
    priority       int, 1 = most urgent
    gated_by       gate key ("etsy_api", "live_listings") or None
    why            the evidence for the item
    external_effect False for every item this package emits (no Etsy write, no spend)
    sources        provenance strings

Never raises; on failure returns a single `seo.run_cycle` item with the error in `why`.
"""
from __future__ import annotations

from datetime import timezone

SOURCES = ["seo_keyword_evidence", "seo_proposals", "seo_cycles", "etsy_taxonomy_snapshots",
           "listing_outcomes", "operating_readings:attribution.stats", "insights_snapshots",
           "serp_snapshots", "benchmark_listings", "keywords", "listings",
           "products.launch0", "commerce.search", "commerce.seo"]

GUARDRAILS = [
    "F-918: no KPI may be improved by keyword stuffing, untraceable or misleading tags, "
    "competitor brand terms or protected IP (seo.truth.validate_listing is blocking)",
    "a modelled phrase's demand is never reported as measured (evidence basis per row)",
    "UNKNOWN is never rendered as 0: a term with no Stats row is UNKNOWN",
    "proposals are never written to Etsy by this department (writes_to_etsy=False)",
    "F-929: an unconfirmed category stays GATED(etsy_api); no remembered taxonomy id is used",
]


def _iso(dt) -> str | None:
    if dt is None:
        return None
    dt = dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _latest_proposals(db) -> tuple[list[dict], object]:
    from sqlalchemy import desc, select

    from ._db import session
    from .models import SeoCycle, SeoProposal

    with session(db) as s:
        props = [{"slug": r.product_slug, "candidate": r.candidate, "ok": bool(r.ok),
                  "created_at": _iso(r.created_at), "proposal": dict(r.proposal or {})}
                 for r in s.scalars(select(SeoProposal).where(SeoProposal.state == "PROPOSED")
                                    .order_by(SeoProposal.product_slug))]
        last = s.scalar(select(SeoCycle).order_by(desc(SeoCycle.at), desc(SeoCycle.id))
                        .limit(1))
        last_at = last.at if last is not None else None
    return props, last_at


def _taxonomy(db) -> list[dict]:
    try:
        from . import taxonomy

        return taxonomy.readiness(db)
    except Exception as exc:  # noqa: BLE001
        return [{"status": "UNKNOWN", "why": f"taxonomy readiness failed: {exc!s}"[:300]}]


def _w3(db) -> dict:
    """Wave-3 additions: Etsy constraint verification, Launch-0 strategy, learning hooks.

    Never raises; each part degrades to an UNKNOWN record with its reason."""
    out: dict = {}
    try:
        from . import constraints

        snap = constraints.snapshot()
        out["constraints"] = {"counts": snap["counts"], "retrieved_on": snap["retrieved_on"],
                              "unverified_keys": snap["unverified_keys"],
                              "repo_disagreements": snap["repo_disagreements"],
                              "openapi_sha256": snap["openapi"]["sha256"]}
    except Exception as exc:  # noqa: BLE001
        out["constraints"] = {"status": "UNKNOWN", "why": f"{type(exc).__name__}: {exc!s}"[:200]}
    try:
        from . import strategy

        plan = strategy.plan(db)
        out["strategy"] = {"version": plan["version"], "ok": plan["ok"],
                           "unverified_limits": plan["unverified_limits"],
                           "products": [{"slug": p["slug"], "ok": p["ok"],
                                         "title": p["title"], "tags": len(p["tags"]),
                                         "tag_basis_counts": p["tag_basis_counts"],
                                         "category_status": p["category"]["status"],
                                         "blocking": p["blocking"][:3]}
                                        for p in plan["products"]],
                           "demand_basis": "modelled unless a tag's basis says measured"}
    except Exception as exc:  # noqa: BLE001
        out["strategy"] = {"status": "UNKNOWN", "why": f"{type(exc).__name__}: {exc!s}"[:200]}
    try:
        from . import learning

        f = learning.funnel(db)
        out["learning"] = {"search_visibility": {k: f["search_visibility"].get(k)
                                                 for k in ("status", "value", "why")},
                           "per_product": {s: {k: (v.get("status") if isinstance(v, dict)
                                                   and "status" in v else None)
                                               for k, v in row.items()
                                               if k in ("impressions", "clicks",
                                                        "favourites", "carts", "orders")}
                                           for s, row in f["per_product"].items()},
                           "thresholds": f["thresholds"]}
    except Exception as exc:  # noqa: BLE001
        out["learning"] = {"status": "UNKNOWN", "why": f"{type(exc).__name__}: {exc!s}"[:200]}
    return out


def summary(db) -> dict:
    out = _summary_core(db)
    if db is not None:
        out["w3"] = _w3(db)
    return out


def _summary_core(db) -> dict:
    base = {"status": "UNKNOWN", "as_of": None, "basis": "unknown", "items": [],
            "sources": list(SOURCES), "kpis": {}, "guardrails": list(GUARDRAILS)}
    if db is None:
        return {**base, "reason": "no database handle", "taxonomy": []}
    try:
        from .models import tables_exist

        tax = _taxonomy(db)
        if not tables_exist(db):
            return {**base, "taxonomy": tax,
                    "reason": "seo tables not created: seo.jobs.run_cycle has never run"}
        props, last_at = _latest_proposals(db)
        if not props:
            return {**base, "taxonomy": tax, "as_of": _iso(last_at),
                    "reason": "no SEO proposal exists yet: seo.jobs.run_cycle has not "
                              "produced one"}
        from . import evidence as ev_mod

        rows = ev_mod.all_rows(db)
        counts = ev_mod.basis_counts(rows)
        tax_by = {t.get("slug"): t for t in tax}
        items = []
        measured_tags = total_tags = 0
        for p in props:
            body = p["proposal"]
            tb = body.get("tag_basis_counts") or {}
            measured_tags += tb.get("measured", 0)
            total_tags += len(body.get("tags") or [])
            t = tax_by.get(p["slug"], {})
            items.append({"slug": p["slug"], "candidate": p["candidate"], "ok": p["ok"],
                          "title": body.get("title"), "tags": len(body.get("tags") or []),
                          "tag_basis_counts": tb,
                          "blocking": (body.get("validation") or {}).get("blocking", [])[:5],
                          "taxonomy_status": t.get("status", "UNKNOWN"),
                          "taxonomy_why": t.get("why", ""),
                          "proposed_at": p["created_at"], "writes_to_etsy": False})
        all_ok = all(i["ok"] for i in items)
        none_ok = not any(i["ok"] for i in items)
        tax_confirmed = sum(1 for t in tax if t.get("status") == "CONFIRMED")
        if none_ok:
            status, reason = "BLOCKED", "no Launch-0 proposal passes the truthful-tag validator"
        elif all_ok and tax and tax_confirmed == len(tax):
            status, reason = "OK", "every proposal passes truth checks and every category is confirmed"
        else:
            gated = sorted({t.get("status") for t in tax if t.get("status") != "CONFIRMED"})
            reason = ("proposals ready; " if all_ok else "some proposals fail truth checks; ")
            reason += (f"taxonomy not confirmed ({', '.join(gated)})" if gated
                       else "taxonomy confirmed")
            status = "DEGRADED"
        basis = "measured" if measured_tags else "modelled"
        kpis = {
            "proposals_passing_truth": {"value": sum(1 for i in items if i["ok"]),
                                        "of": len(items), "basis": "measured"},
            "taxonomy_confirmed": {"value": tax_confirmed, "of": len(tax),
                                   "basis": "measured"},
            "tags_with_measured_evidence": {"value": measured_tags, "of": total_tags,
                                            "basis": "measured"},
            "keyword_evidence_by_basis": {"value": counts, "basis": "measured"},
            "search_outcomes": {"value": None, "status": "UNKNOWN",
                                "basis": "unknown",
                                "why": "no live listing outcomes are attributed to keywords "
                                       "yet (see seo.measure)"},
        }
        try:
            from . import measure

            att = measure.attribution(db, {i["slug"]: [] for i in items}, evidence_rows=rows)
            if att["status"] != "UNKNOWN":
                kpis["search_outcomes"] = {"value": att["listings_with_outcomes"],
                                           "status": att["status"], "basis": "measured",
                                           "why": "listings with recorded outcomes"}
        except Exception:  # noqa: BLE001
            pass
        return {**base, "status": status, "as_of": _iso(last_at), "basis": basis,
                "items": items, "reason": reason, "kpis": kpis, "taxonomy": tax}
    except Exception as exc:  # noqa: BLE001 - a provider never raises
        return {**base, "reason": f"seo summary failed: {type(exc).__name__}: {exc!s}"[:400],
                "taxonomy": []}


def _evidence_stale(db) -> tuple[bool, str]:
    """Would a cycle ingest anything new? Read-only comparison of source vs store."""
    from sqlalchemy import select

    from . import evidence as ev_mod
    from . import facts as facts_mod
    from . import proposals
    from ._db import session
    from .models import SeoKeywordEvidence, tables_exist

    if not tables_exist(db):
        return True, "seo.jobs.run_cycle has never run"
    q = {f.slug: proposals.queries_for(f) for f in facts_mod.launch0_facts()}
    fresh = {r["fingerprint"] for r in ev_mod.collect(db, queries_by_slug=q)}
    with session(db) as s:
        have = set(s.scalars(select(SeoKeywordEvidence.fingerprint)))
    new = fresh - have
    if new:
        return True, f"{len(new)} new evidence row(s) are available to ingest"
    return False, ""


def next_work(db) -> list[dict]:
    def item(key, title, kind, action, priority, why, gated_by=None, sources=None):
        return {"key": key, "department": "seo", "title": title, "kind": kind,
                "action": action, "priority": priority, "gated_by": gated_by, "why": why,
                "external_effect": False, "sources": list(sources or [])}

    try:
        out: list[dict] = []
        stale, why = _evidence_stale(db)
        if stale:
            out.append(item("seo.run_cycle", "Re-evaluate SEO proposals on new evidence",
                            "internal", "brambleloop.seo.jobs.run_cycle", 1, why,
                            sources=["seo_keyword_evidence"]))
        tax = _taxonomy(db)
        gated = [t["slug"] for t in tax if t.get("status") == "GATED(etsy_api)"]
        pending = [t["slug"] for t in tax if t.get("status") == "PENDING_REFRESH"]
        if pending:
            out.append(item("seo.taxonomy_refresh", "Read Etsy's taxonomy to confirm "
                            "Launch-0 categories", "internal", "listing.taxonomy_refresh", 1,
                            f"{len(pending)} variant(s) have no Etsy-read category",
                            sources=["etsy_taxonomy_snapshots"]))
        if gated:
            out.append(item("seo.taxonomy_confirm", "Confirm Launch-0 Etsy categories",
                            "gated", "listing.taxonomy_refresh", 2,
                            f"{len(gated)} variant(s) assume their category "
                            f"({', '.join(sorted(gated))}); the etsy_api gate is closed",
                            gated_by="etsy_api", sources=["etsy_taxonomy_snapshots"]))
        from .models import tables_exist

        if tables_exist(db):
            props, _ = _latest_proposals(db)
            for p in props:
                body = p["proposal"]
                if not p["ok"]:
                    out.append(item(f"seo.review:{p['slug']}",
                                    f"Fix the SEO proposal for {p['slug']}", "internal",
                                    "brambleloop.seo.proposals.propose", 2,
                                    "; ".join((body.get("validation") or {})
                                              .get("blocking", [])[:3]) or "proposal not ok",
                                    sources=[f"seo_proposals:{p['slug']}"]))
                diff = body.get("diff") or {}
                if diff and (diff.get("title_changed") or diff.get("tags_added")):
                    out.append(item(f"seo.adopt:{p['slug']}",
                                    f"Proposal differs from the {p['slug']} draft", "internal",
                                    "listing.seo (re-draft through the release chain)", 4,
                                    f"title changed: {diff.get('title_changed')}; tags added: "
                                    f"{diff.get('tags_added', [])[:4]}",
                                    sources=[f"seo_proposals:{p['slug']}", "listings"]))
            from . import evidence as ev_mod

            try:
                from . import constraints as cons

                unv = [k for k, v in cons.working_limits().items()
                       if v["status"] != cons.VERIFIED]
            except Exception:  # noqa: BLE001
                unv = []
            if unv:
                out.append(item("seo.verify_limits", "Owner: confirm Etsy field limits in "
                                "Shop Manager", "owner",
                                "owner: read the counters named in seo.constraints "
                                "owner_check", 4,
                                f"{len(unv)} working limit(s) are UNVERIFIED (Etsy help "
                                f"pages refused automated reads): {', '.join(unv)}",
                                sources=["seo.constraints"]))
            if not any(r["source"] == "etsy_stats_export" for r in ev_mod.all_rows(db)):
                out.append(item("seo.stats_export", "Owner: export Etsy Stats search terms",
                                "gated", "owner: POST /api/attribution/stats with the CSV", 3,
                                "no Etsy Stats export is ingested, so every keyword outcome "
                                "is UNKNOWN; the shop must be live first",
                                gated_by="live_listings",
                                sources=["operating_readings:attribution.stats"]))
        return sorted(out, key=lambda x: (x["priority"], x["key"]))
    except Exception as exc:  # noqa: BLE001
        return [{"key": "seo.run_cycle", "department": "seo",
                 "title": "Re-evaluate SEO proposals", "kind": "internal",
                 "action": "brambleloop.seo.jobs.run_cycle", "priority": 1, "gated_by": None,
                 "why": f"next_work failed: {type(exc).__name__}: {exc!s}"[:300],
                 "external_effect": False, "sources": []}]
