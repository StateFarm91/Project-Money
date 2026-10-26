"""F-448: what the owner discovers becomes research evidence, not chat history.

Owner-supplied URLs, notes and terminology arrive through `POST /api/research/evidence`
(operator credential). Each becomes a `learning_observations` row in a named domain with
`claim_class="source_claim"` (the owner said it; nobody has read the thing yet), its source
tier from `intel.evidence`, `retrieval="search_summary"` unless the owner says they read the
page, and `detail.kind="owner_supplied"`. Terms the owner supplies (`"term": [synonyms]`)
are recorded too, and `search_strategy` reads them as glossary equivalents, so the next
internal search uses the owner's vocabulary.
"""
from __future__ import annotations

from datetime import date

KIND = "owner_supplied"


class OwnerEvidenceRefused(ValueError):
    pass


def record(db, payload: dict, *, today: date | None = None) -> dict:
    from . import evidence, learning

    if not isinstance(payload, dict):
        raise OwnerEvidenceRefused("a JSON object is required")
    domain = str(payload.get("domain") or "").strip()
    note = str(payload.get("note") or "").strip()
    url = str(payload.get("url") or "").strip()
    terms = payload.get("terms") or {}
    if not isinstance(terms, dict) or not all(
            isinstance(k, str) and k.strip() and isinstance(v, list)
            and all(isinstance(x, str) and x.strip() for x in v) for k, v in terms.items()):
        raise OwnerEvidenceRefused('terms must map a term to a list of equivalents')
    if not (url or terms):
        raise OwnerEvidenceRefused("evidence needs a url or terms")
    read = bool(payload.get("owner_read_the_page"))
    retrieval = evidence.FETCHED if read else evidence.SEARCH_SUMMARY
    try:
        rid = learning.record(
            db, domain=domain, source="owner", citation=url or "owner:terminology",
            summary=note or f"owner-supplied terminology: {', '.join(sorted(terms))} and "
                            f"equivalents for internal search",
            observed_on=today or date.today(), claim_class="source_claim",
            retrieval=retrieval, query_terms=sorted(terms),
            decision_ref=str(payload.get("decision_ref") or ""),
            detail={"kind": KIND,
                    "terms": {k.strip().lower(): [x.strip().lower() for x in v]
                              for k, v in terms.items()}})
    except learning.LearningRefused as exc:
        raise OwnerEvidenceRefused(str(exc)) from exc
    return {"recorded": rid, "domain": domain, "source_tier": evidence.tier_for(url)
            if url else evidence.PRIMARY, "retrieval": retrieval,
            "terms": sorted(terms)}


def owner_terms(db) -> dict[str, tuple[str, ...]]:
    """Every owner-supplied term -> equivalents, newest wins per term."""
    from sqlalchemy import select

    from ..core.models import LearningObservation

    out: dict[str, tuple[str, ...]] = {}
    with db.session() as s:
        for r in s.scalars(select(LearningObservation).where(
                LearningObservation.source == "owner").order_by(LearningObservation.id)):
            d = dict(r.detail or {})
            if d.get("kind") == KIND:
                for k, v in (d.get("terms") or {}).items():
                    out[k] = tuple(v)
    return out
