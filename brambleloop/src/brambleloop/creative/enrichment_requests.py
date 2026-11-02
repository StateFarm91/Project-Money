"""The research-enrichment consumer: a held brief goes back to Research with exactly what it
lacks, and comes back to Product Development when Research answers (OPUS2R-7; owner
directive 2026-11-02, item 5).

`construction_registry` holds a brief it cannot build honestly and names every missing item
(`cir.draft_held`). An item resolved by `research_enrichment` (a motif with no backed chart, a
title the construction does not make, a size that does not fit, a one-colour palette) is a
question for Research, but nothing read those rows: a held brief was a dead end.

This module is the Product Development side of that loop. Research's side -- producing an
enriched brief from an open request -- is W-CONCEPT's (research-to-concept intake); it calls
`open_requests` and `answer`. Coordination: PR #22, 2026-11-02.

Rules.

* **One request per brief.** A request is keyed by the brief's slug. A brief held again (a
  re-run of the same draft job) updates the open request; it never opens a second.
* **Precise.** Each item names the field, why it is held, and the values the construction
  would accept (the backed chart words, the sizes that fit, the title heads the family makes).
* **Re-checked before any draft.** `answer` runs the enriched brief through the registry
  again. Only a brief that now resolves is drafted, under a fresh idempotency key
  (`draft:{slug}:enrich:{round}`: the original `draft:{slug}` key is spent, OPUS2R-10).
* **Bounded.** At most MAX_ROUNDS answers per slug; then the request is closed `exhausted`,
  and the brief stops: no correction loop runs forever. An engine-decision hold never opens a
  request (Research cannot answer it; `intel.knowledge_gaps` counts it).
* **Durable.** All state is audit rows, read back on every call, so a restart resumes exactly
  where it stopped. CA$0, deterministic, never publishes.
"""
from __future__ import annotations

from . import construction_registry as R

REQUESTED = "research.enrichment_requested"     # opened or updated (the open request's state)
ANSWERED = "research.enrichment_answered"       # Research answered; the outcome is recorded
OPEN, RESOLVED, EXHAUSTED = "open", "resolved", "exhausted"
MAX_ROUNDS = 2


def _accepts(item: dict, request: dict) -> list[str]:
    """The values the construction would accept for a held field."""
    field = item.get("field")
    family = request.get("family")
    if field == "motif" and family == "tapestry":
        from .fallback_constructions import LIBRARY_CHART_WORDS, _TAPESTRY_CHART_WORDS, \
            tapestry_charts

        backed = set(tapestry_charts())
        return sorted(w for w, c in {**_TAPESTRY_CHART_WORDS, **LIBRARY_CHART_WORDS}.items()
                      if c in backed)
    if field == "motif" and family == "amigurumi":
        return sorted(R.AMIGURUMI_KINDS)
    if field == "size":
        return list(R.SIZE_WORDS)
    if field == "palette":
        return ["two distinct colours in the palette story"]
    if field == "title" and family:
        from . import fallback_constructions as FC

        # FAMILY_HEADS is the shared name/object allowlist (OPUS2T-3, PR #3); before it is
        # integrated, the request names the family's route instead.
        heads = getattr(FC, "FAMILY_HEADS", {}).get(family)
        return sorted(heads) if heads else [f"a title the {family} route drafts"]
    return []


def _rows(db, action: str) -> list[tuple[int, str, dict]]:
    from sqlalchemy import select

    from ..core.models import AuditLog

    with db.session() as s:
        return [(r.id, r.artifact or "", dict(r.detail or {})) for r in s.scalars(
            select(AuditLog).where(AuditLog.action == action).order_by(AuditLog.id))]


def state(db) -> dict[str, dict]:
    """Every request by slug, as its latest row says, with the rounds answered so far."""
    out: dict[str, dict] = {}
    for _id, slug, detail in _rows(db, REQUESTED):
        out[slug] = {**detail, "slug": slug}
    for _id, slug, detail in _rows(db, ANSWERED):
        if slug in out:
            out[slug]["rounds"] = max(out[slug].get("rounds", 0), int(detail.get("round", 0)))
            out[slug]["state"] = detail.get("state", out[slug].get("state"))
            out[slug]["answered_row"] = _id
    for _id, slug, detail in _rows(db, REQUESTED):
        # a request re-opened after an answer (a resolved brief held again) is open again
        if slug in out and _id > out[slug].get("answered_row", 0) and \
                out[slug].get("state") == RESOLVED and detail.get("state") == OPEN:
            out[slug]["state"] = OPEN
    return out


def open_requests(db) -> list[dict]:
    """What Research is asked for now: every open request, oldest first."""
    return [r for r in state(db).values() if r.get("state") == OPEN]


def sweep(db, *, audit) -> dict:
    """Open or update a request for every brief held for research enrichment.

    `audit(action, artifact=, detail=)` writes the row (the job context's audit)."""
    known = state(db)
    opened, updated = [], []
    for _id, slug, detail in _rows(db, R.HELD_ACTION):
        items = [u for u in detail.get("unresolved") or [] if u.get("resolved_by") == R.ENRICH]
        if not items or any(u.get("resolved_by") == R.ENGINE
                            for u in detail.get("unresolved") or []):
            continue                      # an engine hold is not Research's to answer
        request = dict(detail.get("request") or {})
        asks = [{**u, "accepts": _accepts(u, request)} for u in items]
        prior = known.get(slug)
        if prior and prior.get("state") == EXHAUSTED:
            continue                      # MAX_ROUNDS answered: closed for good
        if prior and prior.get("state") == RESOLVED:
            if _id <= prior.get("answered_row", 0) or \
                    int(prior.get("rounds", 0)) >= MAX_ROUNDS:
                continue                  # the hold it answered, or no round left
            prior = {**prior, "asks": None}   # the re-draft was held again: re-open it
        if prior and prior.get("asks") == asks:
            continue                      # the same hold again: nothing new to say
        row = {"state": OPEN, "asks": asks, "request": request,
               "rounds": (prior or {}).get("rounds", 0), "held_row": _id}
        audit(REQUESTED, artifact=slug, detail=row)
        known[slug] = {**row, "slug": slug}
        (updated if prior else opened).append(slug)
    return {"opened": opened, "updated": updated,
            "open": sum(1 for r in known.values() if r.get("state") == OPEN),
            "work_done": len(opened) + len(updated)}


def answer(db, slug: str, concept: dict, brief: dict | None, *, audit, enqueue) -> dict:
    """Research's enriched brief for an open request.

    The brief is re-checked by the registry. If it resolves, `cir.draft` is enqueued under a
    fresh key and the request is resolved; if not, the request stays open with what is still
    missing, until MAX_ROUNDS answers, after which it is exhausted."""
    from .concept import Concept

    req_state = state(db).get(slug)
    if req_state is None or req_state.get("state") != OPEN:
        return {"slug": slug, "accepted": False,
                "why": f"no open enrichment request for {slug!r}"}
    rounds = int(req_state.get("rounds", 0)) + 1
    c = Concept(**{k: v for k, v in concept.items() if k in Concept.__dataclass_fields__})
    req = R.request_for(c, brief)
    if req is not None and not req.unresolved:
        job = enqueue("crochet_engineer", "cir.draft",
                      {"slug": slug, "concept": c.to_dict(), "brief": dict(brief or {}),
                       "enrichment_round": rounds},
                      idempotency_key=f"draft:{slug}:enrich:{rounds}")
        audit(ANSWERED, artifact=slug, detail={"round": rounds, "state": RESOLVED,
                                                "request": req.to_dict()})
        return {"slug": slug, "accepted": True, "state": RESOLVED, "round": rounds,
                "job": getattr(job, "id", None)}
    still = list(req.unresolved) if req is not None else [
        {"field": "construction", "why": "no construction serves this form and construction",
         "resolved_by": R.ENRICH}]
    final = EXHAUSTED if rounds >= MAX_ROUNDS else OPEN
    audit(ANSWERED, artifact=slug, detail={"round": rounds, "state": final,
                                            "still_missing": still})
    if final == OPEN:
        audit(REQUESTED, artifact=slug, detail={
            "state": OPEN, "rounds": rounds, "request": req_state.get("request"),
            "asks": [{**u, "accepts": _accepts(u, req_state.get("request") or {})}
                     for u in still]})
    return {"slug": slug, "accepted": False, "state": final, "round": rounds,
            "still_missing": still}
