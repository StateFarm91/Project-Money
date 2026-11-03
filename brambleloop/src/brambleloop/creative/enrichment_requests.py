"""A4b: a refused or held draft goes back to Research with exactly what it lacks, and comes
back to Product Development when Research answers (owner directive 2026-11-02; queue Q26).

`cir.draft` refuses a concept whose construction the fallback cannot make honestly and records
`cir.draft_refused` with `gate: "construction"`, the category and what the construction needs.
Nothing consumed those rows, and `draft:<slug>` is spent, so a concept fixed later could never
be drafted again. This module is the Product Development side of that loop; Research's side --
producing an enriched concept -- calls `open_requests` and `answer`.

It also reads the construction registry's `cir.draft_held` rows when that module is present
(research briefs held for `research_enrichment`), so the loop does not change shape when the
registry is integrated.

Rules.

* **One request per slug.** A slug refused again updates its open request; never a second.
* **Precise.** Each item names the field, why it was refused, and what the construction needs.
* **Re-checked before any draft.** `answer` runs the enriched concept through the same rule that
  refused it (`fallback_constructions.plan`, or the registry). Only a concept that now routes
  to a construction is drafted under `draft:<slug>:enrich:<round>`. The original
  `draft:<slug>` is spent. Each round has a single durable queue key, and its payload
  records the enrichment fingerprint.
* **Bounded.** At most MAX_ROUNDS answers per slug; then the request is closed `exhausted` and
  never re-opened: no correction loop runs forever.
* **Durable.** All state is audit rows, read back on every call; a restart resumes exactly where
  it stopped. CA$0, deterministic, never publishes.
"""
from __future__ import annotations

import hashlib
import json

REQUESTED = "research.enrichment_requested"
ANSWERED = "research.enrichment_answered"
OPEN, RESOLVED, EXHAUSTED = "open", "resolved", "exhausted"
MAX_ROUNDS = 2
REFUSED_ACTION = "cir.draft_refused"
ENRICH = "research_enrichment"


def _registry():
    try:
        from . import construction_registry
    except ImportError:          # not integrated on this base
        return None
    return construction_registry


def _rows(db, action: str) -> list[tuple[int, str, dict]]:
    from sqlalchemy import select

    from ..core.models import AuditLog

    with db.session() as s:
        return [(r.id, r.artifact or "", dict(r.detail or {})) for r in s.scalars(
            select(AuditLog).where(AuditLog.action == action).order_by(AuditLog.id))]


def fingerprint(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()
                          ).hexdigest()[:12]


def _holds(db) -> list[tuple[int, str, list[dict], dict]]:
    """(row id, slug, items, context) for every refusal or hold Research can answer."""
    out = []
    for rid, slug, d in _rows(db, REFUSED_ACTION):
        if d.get("gate") != "construction":
            continue                              # funnel/engine refusals are not Research's
        out.append((rid, slug, [{"field": "construction", "why": str(d.get("reason") or ""),
                                 "needs": str(d.get("needs") or ""),
                                 "resolved_by": ENRICH}],
                    {"kind": "radar", "category": d.get("category")}))
    reg = _registry()
    if reg is not None:
        for rid, slug, d in _rows(db, reg.HELD_ACTION):
            items = [u for u in d.get("unresolved") or [] if u.get("resolved_by") == reg.ENRICH]
            if items and not any(u.get("resolved_by") == reg.ENGINE
                                 for u in d.get("unresolved") or []):
                out.append((rid, slug, items, {"kind": "registry",
                                                "request": d.get("request") or {}}))
    return sorted(out, key=lambda x: x[0])


def state(db) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for _id, slug, detail in _rows(db, REQUESTED):
        out[slug] = {**detail, "slug": slug, "requested_row": _id}
    for _id, slug, detail in _rows(db, ANSWERED):
        if slug in out:
            out[slug]["rounds"] = max(out[slug].get("rounds", 0), int(detail.get("round", 0)))
            out[slug]["state"] = detail.get("state", out[slug].get("state"))
            out[slug]["answered_row"] = _id
    for _id, slug, detail in _rows(db, REQUESTED):
        if slug in out and _id > out[slug].get("answered_row", 0) and \
                out[slug].get("state") == RESOLVED and detail.get("state") == OPEN:
            out[slug]["state"] = OPEN
    return out


def open_requests(db) -> list[dict]:
    return [r for r in state(db).values() if r.get("state") == OPEN]


def sweep(db, *, audit) -> dict:
    """Open or update one request for every refusal or hold Research can answer."""
    known = state(db)
    opened, updated = [], []
    # The most recent refusal is the current need. Replaying historical rows in
    # turn makes differing asks alternate forever and creates permanent audit churn.
    latest = {}
    for rid, slug, items, context in _holds(db):
        latest[slug] = (rid, items, context)
    for slug, (rid, items, context) in latest.items():
        prior = known.get(slug)
        if prior and prior.get("state") == EXHAUSTED:
            continue
        if prior and prior.get("state") == RESOLVED:
            if rid <= prior.get("answered_row", 0):
                continue
            if int(prior.get("rounds", 0)) >= MAX_ROUNDS:
                audit(ANSWERED, artifact=slug, detail={"round": MAX_ROUNDS,
                    "state": EXHAUSTED, "reason": "last redraft was refused"})
                known[slug] = {**prior, "state": EXHAUSTED}
                updated.append(slug)
                continue
            prior = {**prior, "asks": None}
        if prior and (rid <= int(prior.get("held_row") or 0)
                      or prior.get("asks") == items):
            continue
        row = {"state": OPEN, "asks": items, "context": context,
               "rounds": (prior or {}).get("rounds", 0), "held_row": rid}
        audit(REQUESTED, artifact=slug, detail=row)
        known[slug] = {**row, "slug": slug}
        (updated if prior else opened).append(slug)
    return {"opened": opened, "updated": updated,
            "open": sum(1 for r in known.values() if r.get("state") == OPEN),
            "work_done": len(opened) + len(updated)}


def _recheck(context: dict, payload: dict, brief: dict | None) -> list[dict]:
    """What the enriched concept still lacks, read by the rule that refused it."""
    if context.get("kind") == "registry":
        reg = _registry()
        from .concept import Concept

        c = Concept(**{k: v for k, v in (payload.get("concept") or payload).items()
                       if k in Concept.__dataclass_fields__})
        req = reg.request_for(c, brief) if reg else None
        if req is None:
            return [{"field": "construction", "why": "no construction serves it",
                     "resolved_by": ENRICH}]
        return list(req.unresolved)
    from . import fallback_constructions as FC

    route = FC.plan(category=str(payload.get("category") or context.get("category") or ""),
                    title=str(payload.get("title") or ""), slug=str(payload.get("slug") or ""),
                    rationale=str(payload.get("rationale") or ""))
    if route.get("family") == FC.REFUSED:
        return [{"field": "construction", "why": route.get("why"),
                 "needs": route.get("needs"), "resolved_by": ENRICH}]
    return []


def answer(db, slug: str, payload: dict, brief: dict | None = None, *, audit,
           enqueue) -> dict:
    """Research's enriched concept for an open request: re-checked, then drafted under
    draft:<slug>:enrich:<round>, or kept open with what is still missing, or exhausted."""
    req_state = state(db).get(slug)
    if req_state is None or req_state.get("state") != OPEN:
        return {"slug": slug, "accepted": False,
                "why": f"no open enrichment request for {slug!r}"}
    rounds = int(req_state.get("rounds", 0)) + 1
    context = req_state.get("context") or {}
    still = _recheck(context, payload, brief)
    if not still:
        data = {**payload, "slug": slug, "enrichment_round": rounds}
        if brief is not None:
            data["brief"] = dict(brief)
        fp = fingerprint({k: v for k, v in data.items() if k != "enrichment_round"})
        # A single key per slug and round prevents two concurrent answers with
        # different payloads from queuing two drafts. Keep the fingerprint in
        # the durable inputs for provenance and conflict investigation.
        data["enrichment_fingerprint"] = fp
        job = enqueue("crochet_engineer", "cir.draft", data,
                      idempotency_key=f"draft:{slug}:enrich:{rounds}")
        if job is None:
            # A crash may occur after the durable queue insert but before the
            # answer audit. Recover only the exact queued payload; a competing
            # answer cannot take credit for another writer's round.
            from sqlalchemy import select
            from ..core.models import Job, JobStatus

            key = f"draft:{slug}:enrich:{rounds}"
            with db.session() as session:
                old = session.scalar(select(Job).where(Job.idempotency_key == key))
                matches = (old is not None and old.agent == "crochet_engineer"
                           and old.job_type == "cir.draft" and old.inputs == data)
                if not matches:
                    return {"slug": slug, "accepted": False, "state": OPEN,
                            "round": rounds, "why": "round already used or not queued"}
                if old.status in (JobStatus.DEAD, JobStatus.CANCELLED) or (
                        old.status == JobStatus.DONE and not (old.outputs or {}).get("drafted")):
                    return {"slug": slug, "accepted": False, "state": OPEN,
                            "round": rounds, "why": "existing draft was not completed successfully"}
                job_id = old.id
        else:
            job_id = getattr(job, "id", None)
        audit(ANSWERED, artifact=slug, detail={"round": rounds, "state": RESOLVED,
                                                "fingerprint": fp})
        return {"slug": slug, "accepted": True, "state": RESOLVED, "round": rounds,
                "fingerprint": fp, "job": job_id}
    final = EXHAUSTED if rounds >= MAX_ROUNDS else OPEN
    audit(ANSWERED, artifact=slug, detail={"round": rounds, "state": final,
                                            "still_missing": still})
    if final == OPEN:
        audit(REQUESTED, artifact=slug, detail={"state": OPEN, "rounds": rounds,
                                                "context": context, "asks": still})
    return {"slug": slug, "accepted": False, "state": final, "round": rounds,
            "still_missing": still}
