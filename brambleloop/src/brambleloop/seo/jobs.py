"""The continuous SEO job: `run_cycle(db)` (directive v1.1 section 11).

observe (evidence.ingest) -> decide (taxonomy.readiness, proposals.propose)
-> measure (measure.attribution) -> learn (a changed input re-evaluates the proposal).

**Idempotent.** Each Launch-0 variant's proposal is keyed on an input fingerprint: the
proposal version, the product's verified facts, the evidence set, the competitor-name list,
the current draft on the `listings` row, the observed buyer language and the taxonomy
reading. A cycle whose inputs are unchanged writes nothing -- no proposal, no cycle row, no
audit row -- and returns `changed: False`. When evidence arrives, only proposals whose inputs
changed are re-written; the previous proposal for that slug is marked SUPERSEDED, never
deleted.

No external effect: nothing here writes to Etsy, sends a message or spends. Safe to schedule
at any cadence in SHADOW.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

JOB_TYPE = "seo.cycle"
ACTOR = "seo"


def _fp(*parts) -> str:
    return hashlib.sha256(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()


def run_cycle(db, *, now: datetime | None = None, facts_list=None) -> dict:
    from sqlalchemy import select

    from ..core.models import AuditLog
    from . import evidence as ev_mod
    from . import facts as facts_mod
    from . import measure, proposals, taxonomy, truth
    from ._db import session
    from .models import SeoCycle, SeoProposal, ensure_tables

    now = now or datetime.now(timezone.utc)
    ensure_tables(db)
    facts_list = facts_mod.launch0_facts() if facts_list is None else facts_list
    queries_by_slug = {f.slug: proposals.queries_for(f) for f in facts_list}
    ingested = ev_mod.ingest(db, queries_by_slug=queries_by_slug)
    rows = ev_mod.all_rows(db)
    ev_fp = _fp(sorted(r["fingerprint"] for r in rows))
    competitors = truth.competitor_names(db)
    tax_rows = {r["slug"]: r for r in taxonomy.readiness(db, facts_list, now=now)}

    written, skipped, input_fps = [], [], []
    tags_by_slug: dict[str, list[str]] = {}
    for f in facts_list:
        buyer = proposals._buyer_language(db, f)
        current = proposals._current_draft(db, f.slug)
        tax = tax_rows.get(f.slug, {})
        input_fp = _fp(proposals.PROPOSAL_VERSION, f.fingerprint_material(), ev_fp,
                       competitors, current,
                       {"tags": buyer.get("tags"), "mapped": buyer.get("mapped")},
                       {"status": tax.get("status"), "taxonomy_id": tax.get("taxonomy_id")})
        input_fps.append(input_fp)
        with session(db) as s:
            existing = s.scalar(select(SeoProposal).where(
                SeoProposal.product_slug == f.slug,
                SeoProposal.input_fingerprint == input_fp))
            if existing is not None:
                if existing.state != "PROPOSED":
                    # Inputs returned to an earlier state: that proposal is current again.
                    for other in s.scalars(select(SeoProposal).where(
                            SeoProposal.product_slug == f.slug,
                            SeoProposal.state == "PROPOSED")):
                        other.state, other.superseded_at = "SUPERSEDED", now
                    existing.state, existing.superseded_at = "PROPOSED", None
                    written.append(f.slug)
                else:
                    skipped.append(f.slug)
                tags_by_slug[f.slug] = list((existing.proposal or {}).get("tags") or [])
                continue
        prop = proposals.propose(db, f, evidence_rows=rows, competitors=competitors,
                                 buyer=buyer)
        prop["taxonomy"] = {k: tax.get(k) for k in ("status", "taxonomy_id", "path",
                                                    "category_intent", "why")}
        tags_by_slug[f.slug] = list(prop["tags"])
        with session(db) as s:
            for old in s.scalars(select(SeoProposal).where(
                    SeoProposal.product_slug == f.slug, SeoProposal.state == "PROPOSED")):
                old.state = "SUPERSEDED"
                old.superseded_at = now
            s.add(SeoProposal(product_slug=f.slug, candidate=f.candidate,
                              input_fingerprint=input_fp, state="PROPOSED",
                              ok=1 if prop["ok"] else 0, proposal=prop, created_at=now))
        written.append(f.slug)

    attribution = measure.attribution(db, tags_by_slug, evidence_rows=rows)
    # W4-SEO: every drafted listing's search package is re-assembled from the release
    # records, the evidence store and the recorded Stats periods -- the post-launch update
    # loop. Idempotent: an unchanged package writes nothing.
    try:
        from . import packages as packages_mod

        package_run = packages_mod.refresh(db, now=now)
    except Exception as exc:  # noqa: BLE001 - a package failure never stops the cycle
        package_run = {"packages": 0, "written": [], "unchanged": [], "readiness": {},
                       "error": f"{type(exc).__name__}: {str(exc)[:200]}"}
    changed = bool(written or ingested["added"] or package_run.get("written"))
    cycle_fp = _fp(sorted(input_fps))
    if changed:
        with session(db) as s:
            if s.scalar(select(SeoCycle).where(SeoCycle.fingerprint == cycle_fp)) is None:
                s.add(SeoCycle(at=now, fingerprint=cycle_fp,
                               evidence_added=ingested["added"],
                               proposals_written=len(written),
                               detail={"written": written, "skipped": skipped,
                                       "taxonomy": taxonomy.counts(list(tax_rows.values())),
                                       "attribution_status": attribution["status"]}))
        try:
            with session(db) as s:
                s.add(AuditLog(at=now, actor=ACTOR, action="seo.cycle_changed",
                               artifact=f"seo_cycle:{cycle_fp[:16]}",
                               detail={"evidence_added": ingested["added"],
                                       "proposals_written": written,
                                       "writes_to_etsy": False}))
        except Exception:  # noqa: BLE001 - no audit table on a bare db; the cycle row stands
            pass
    return {"changed": changed, "evidence_added": ingested["added"],
            "evidence_seen": ingested["seen"], "proposals_written": written,
            "proposals_unchanged": skipped, "cycle_fingerprint": cycle_fp,
            "taxonomy": taxonomy.counts(list(tax_rows.values())),
            "attribution_status": attribution["status"], "packages": package_run,
            "writes_to_etsy": False}
