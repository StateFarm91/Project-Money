"""F-475: one place any agent asks "what does this company already know about X?".

`intel.research.search_internal_report` already searches lessons, learning observations,
incidents, experiments, failure memory, benchmark listings, BUILD_STATE/DECISION_LOG and test
names, but only from inside a research task. Provenance records, pod lessons (`intel.memory`),
trend provenance and company memory were reachable only through their own modules. This index
searches all of them for a subject and returns each hit with its corpus, ref and retrieval
class, plus the per-corpus record of what was searched (hits, or why a corpus was
unreadable), so "no prior evidence" is a searched result rather than an assumption.

Read-only. Served at `/api/evidence?subject=` (operator-only).
"""
from __future__ import annotations

import re

MAX_PER_CORPUS = 20


def _terms(subject: str) -> list[str]:
    return [t for t in re.split(r"[\s,]+", (subject or "").strip().lower()) if len(t) >= 3][:6]


def search(db, subject: str) -> dict:
    from sqlalchemy import and_, or_, select

    from ..autonomy.models import CompanyMemory
    from ..core.models import ArtefactProvenance, PodLesson, TrendProvenance
    from . import research

    terms = _terms(subject)
    if not terms:
        return {"subject": subject, "terms": [], "hits": [], "searched": [],
                "why": "no searchable term (3+ characters)"}
    hits, searched = research.search_internal_report(db, terms)

    def table(name, model, cols, text):
        try:
            with db.session() as s:
                cond = or_(*[and_(*[c.ilike(f"%{t}%") for t in terms]) for c in cols])
                rows = list(s.scalars(select(model).where(cond).limit(MAX_PER_CORPUS)))
                for r in rows:
                    hits.append({"ref": f"{name}:{r.id}", "kind": name, "text": text(r)[:300],
                                 "retrieval": "internal"})
            searched.append({"corpus": name, "hits": len(rows)})
        except Exception as exc:  # noqa: BLE001 - an unreadable corpus is named, not skipped
            searched.append({"corpus": name, "hits": None,
                             "why": f"{type(exc).__name__}: {str(exc)[:120]}"})

    table("artefact_provenance", ArtefactProvenance,
          (ArtefactProvenance.artefact_key, ArtefactProvenance.product_slug,
           ArtefactProvenance.artefact_class),
          lambda r: f"{r.artefact_class} {r.artefact_key} ({r.product_slug})")
    table("pod_lessons", PodLesson, (PodLesson.subject, PodLesson.statement),
          lambda r: f"[{r.pod}] {r.subject}: {r.statement}")
    table("trend_provenance", TrendProvenance, (TrendProvenance.topic, TrendProvenance.source),
          lambda r: f"{r.topic} <- {r.source}")
    table("company_memory", CompanyMemory, (CompanyMemory.subject, CompanyMemory.key),
          lambda r: f"[{r.kind}] {r.subject or r.key}")
    by_corpus: dict[str, int] = {}
    for h in hits:
        by_corpus[h["kind"]] = by_corpus.get(h["kind"], 0) + 1
    return {"subject": subject, "terms": terms, "count": len(hits), "by_kind": by_corpus,
            "hits": hits, "searched": searched}
