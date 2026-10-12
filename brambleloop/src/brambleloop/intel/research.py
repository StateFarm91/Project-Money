"""Research tasks: unknowns routed to a queue, findings labelled, dated and set to expire.

Final Master F-403 (Unknown Detection), F-409 (Fact / Claim / Inference Separation), F-424
(Research Reproducibility), F-431 (Durable Knowledge Promotion) and F-433 (Research Freshness).

Before this module an UNKNOWN was an honest state on a page and nothing more: the learning radar
named domains nobody had observed, the children's-safety module named constraints that rest on
pages nobody fetched, and neither became work. Research conclusions lived in research/*.md prose
with no class, no query, no decision they fed and no expiry.

A `ResearchTask` is one question with:

* its **trigger** (the unknown that raised it) and the **decision** it serves (`decision_ref`);
* the **query terms** used, so the search can be repeated (F-424);
* the **internal evidence** already held (lessons and observations matching the terms), searched
  first, because the cheapest research is reading what the company already measured;
* its **sources**, each with retrieval class (fetched / search_summary / repository /
  rendered_image / internal) and the date read;
* its **findings**, each labelled with one claim class (F-409):
  ``fact``          -- established by a source this system read in full, or measured internally;
  ``source_claim``  -- somebody said it; we have their words, not the thing itself;
  ``inference``     -- reasoned from facts or claims, with the refs it rests on;
  ``hypothesis``    -- a testable guess, not yet tested;
  ``unresolved``    -- the question remains open; recorded so it is not re-asked blindly;
* a **stop condition** and a **spend bound** (default CA$0: this module spends nothing itself);
* on answering, ``expires_on`` from the domain's freshness: a learning domain's
  ``fresh_for_days`` (marketplace policy 21 days, techniques 365...) or an improvement world's
  speed from `improve.freshness` -- ``mathematical`` findings never expire on a date (F-433).

Discipline enforced in code, not prose: a ``fact`` must cite a ``fetched``, ``repository``,
``rendered_image`` or ``internal`` source -- a search summary can only support a
``source_claim``. An ``inference`` must name the findings or sources it rests on.
"""
from __future__ import annotations

import hashlib
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import JSON, DateTime, Float, Integer, String, Text, or_, select
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db import Base

OPEN, ANSWERED, STOPPED, EXPIRED = "open", "answered", "stopped", "expired"

CLAIM_CLASSES = ("fact", "source_claim", "inference", "hypothesis", "unresolved")
RETRIEVAL_CLASSES = ("fetched", "search_summary", "repository", "rendered_image", "internal")
FACT_GRADE = {"fetched", "repository", "rendered_image", "internal"}


class ResearchTask(Base):
    __tablename__ = "research_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                         default=lambda: datetime.now(timezone.utc), index=True)
    question: Mapped[str] = mapped_column(Text)
    trigger: Mapped[str] = mapped_column(String(200), index=True)
    dedupe_key: Mapped[str] = mapped_column(String(64), index=True)
    decision_ref: Mapped[str] = mapped_column(String(200), default="")
    domain: Mapped[str] = mapped_column(String(40), default="", index=True)
    state: Mapped[str] = mapped_column(String(12), default=OPEN, index=True)
    query_terms: Mapped[list] = mapped_column(JSON, default=list)
    internal_evidence: Mapped[list] = mapped_column(JSON, default=list)
    sources: Mapped[list] = mapped_column(JSON, default=list)
    findings: Mapped[list] = mapped_column(JSON, default=list)
    stop_condition: Mapped[str] = mapped_column(Text, default="")
    spend_bound_cad: Mapped[float] = mapped_column(Float, default=0.0)
    spend_cad: Mapped[float] = mapped_column(Float, default=0.0)
    confidence: Mapped[str] = mapped_column(String(20), default="")
    outcome: Mapped[str] = mapped_column(Text, default="")
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_on: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ResearchRefused(ValueError):
    """A task or finding that would blur fact, claim and inference, or lose its provenance."""


def _now(now: datetime | None = None) -> datetime:
    return now or datetime.now(timezone.utc)


def _aware(v: datetime | None) -> datetime | None:
    return None if v is None else (v if v.tzinfo else v.replace(tzinfo=timezone.utc))


def _key(trigger: str) -> str:
    return hashlib.sha256(trigger.strip().lower().encode()).hexdigest()


def _ensure(db) -> None:
    ResearchTask.__table__.create(bind=db.engine, checkfirst=True)


# ---- freshness (F-433) ------------------------------------------------------------------

def freshness_for(domain: str) -> tuple[int | None, str]:
    """(days a finding in this domain stays fresh, why). None means never on a date."""
    from . import learning

    d = learning.DOMAIN_BY_KEY.get(domain)
    if d is not None:
        return d.fresh_for_days, f"learning domain {domain}: {d.why}"
    from ..improve import freshness

    if domain in freshness.WORLD_SPEED:
        hours, why = freshness.WORLD_SPEED[domain]
        return (None if hours is None else max(1, -(-hours // 24))), f"{domain} world: {why}"
    world = freshness.CELL_WORLD.get(domain)
    if world is not None:
        hours, why = freshness.WORLD_SPEED[world]
        return (None if hours is None else max(1, -(-hours // 24))), f"cell {domain} ({world}): {why}"
    raise ResearchRefused(
        f"{domain!r} has no freshness: name a learning domain, a freshness world or an "
        f"improvement cell. A default expiry is the single global constant F-433 removes")


# ---- internal evidence first ------------------------------------------------------------

def search_internal(db, terms) -> list[dict]:
    """Lessons and learning observations whose text mentions every term (case-insensitive)."""
    from ..core.models import LearningObservation, Lesson

    terms = [str(t).strip() for t in terms or () if str(t).strip()]
    if not terms:
        return []
    out = []
    with db.session() as s:
        q = select(Lesson)
        for t in terms:
            q = q.where(or_(Lesson.statement.ilike(f"%{t}%"), Lesson.subject.ilike(f"%{t}%")))
        for r in s.scalars(q.limit(20)):
            out.append({"ref": f"lessons:{r.id}", "kind": "lesson", "text": r.statement[:300],
                        "confidence": r.confidence, "retrieval": "internal"})
        q = select(LearningObservation)
        for t in terms:
            q = q.where(LearningObservation.summary.ilike(f"%{t}%"))
        for r in s.scalars(q.limit(20)):
            out.append({"ref": f"learning_observations:{r.id}", "kind": "external_signal",
                        "text": r.summary[:300], "retrieval": "internal"})
    return out


# ---- tasks --------------------------------------------------------------------------------

def open_question(db, *, question: str, trigger: str, decision_ref: str, domain: str,
                  query_terms=(), stop_condition: str = "", spend_bound_cad: float = 0.0,
                  now: datetime | None = None) -> dict:
    """Open a research task once per trigger while one is open. Internal evidence is attached."""
    _ensure(db)
    if len(str(question).split()) < 5:
        raise ResearchRefused("a research question has to be a question, not a label")
    if not trigger.strip() or not decision_ref.strip():
        raise ResearchRefused("a task names the unknown that raised it and the decision it "
                              "serves; research for no decision is reading (F-424)")
    freshness_for(domain)  # refuses an unknown domain before anything is written
    terms = [str(t).strip() for t in query_terms if str(t).strip()]
    key = _key(trigger)
    with db.session() as s:
        existing = s.scalar(select(ResearchTask).where(ResearchTask.dedupe_key == key,
                                                       ResearchTask.state == OPEN))
        if existing is not None:
            return {"task": existing.id, "opened": False}
    internal = search_internal(db, terms)
    with db.session() as s:
        row = ResearchTask(question=question.strip(), trigger=trigger.strip()[:200],
                           dedupe_key=key, decision_ref=decision_ref.strip()[:200],
                           domain=domain, query_terms=terms, internal_evidence=internal,
                           stop_condition=(stop_condition or "answered with at least one fact "
                                           "or explicitly recorded unresolved").strip(),
                           spend_bound_cad=max(0.0, float(spend_bound_cad or 0.0)),
                           at=_now(now))
        s.add(row)
        s.flush()
        return {"task": row.id, "opened": True, "internal_evidence": len(internal)}


def add_source(db, task_id: int, *, source: str, citation: str, retrieval: str,
               read_on: date) -> int:
    if retrieval not in RETRIEVAL_CLASSES:
        raise ResearchRefused(f"retrieval {retrieval!r} is not one of {RETRIEVAL_CLASSES}")
    if not source.strip() or not citation.strip():
        raise ResearchRefused("a source names where it is and how to find it again")
    with db.session() as s:
        row = s.get(ResearchTask, task_id)
        if row is None:
            raise ResearchRefused(f"no research task {task_id}")
        srcs = list(row.sources or [])
        srcs.append({"ref": f"S{len(srcs) + 1}", "source": source.strip(),
                     "citation": citation.strip(), "retrieval": retrieval,
                     "read_on": read_on.isoformat()})
        row.sources = srcs
        return len(srcs)


def add_finding(db, task_id: int, *, statement: str, claim_class: str, rests_on=(),
                confidence: str = "") -> str:
    """One labelled finding. `rests_on` names sources (S1..), internal refs or findings (F1..)."""
    if claim_class not in CLAIM_CLASSES:
        raise ResearchRefused(f"claim_class must be one of {CLAIM_CLASSES} (F-409)")
    refs = [str(r) for r in rests_on or () if str(r).strip()]
    with db.session() as s:
        row = s.get(ResearchTask, task_id)
        if row is None:
            raise ResearchRefused(f"no research task {task_id}")
        srcs = {x["ref"]: x for x in row.sources or []}
        internal = {x["ref"] for x in row.internal_evidence or []}
        found = {x["ref"] for x in row.findings or []}
        unknown = [r for r in refs if r not in srcs and r not in internal and r not in found]
        if unknown:
            raise ResearchRefused(f"finding rests on refs this task does not hold: {unknown}")
        if claim_class == "fact":
            grade = [r for r in refs if (r in srcs and srcs[r]["retrieval"] in FACT_GRADE)
                     or r in internal]
            if not grade:
                raise ResearchRefused(
                    "a fact needs a source this system read in full (fetched, repository, "
                    "rendered image) or internal evidence; a search summary supports only a "
                    "source_claim")
        if claim_class in ("source_claim", "inference") and not refs:
            raise ResearchRefused(f"a {claim_class} names what it rests on")
        fs = list(row.findings or [])
        ref = f"F{len(fs) + 1}"
        fs.append({"ref": ref, "statement": statement.strip(), "claim_class": claim_class,
                   "rests_on": refs, "confidence": confidence})
        row.findings = fs
        return ref


def answer(db, task_id: int, *, outcome: str, confidence: str = "",
           now: datetime | None = None) -> dict:
    """Close a task. It must hold a fact or an explicit `unresolved` finding; expiry is set."""
    t = _now(now)
    with db.session() as s:
        row = s.get(ResearchTask, task_id)
        if row is None:
            raise ResearchRefused(f"no research task {task_id}")
        classes = {f["claim_class"] for f in row.findings or []}
        if not classes & {"fact", "unresolved"}:
            raise ResearchRefused(
                "a task is answered by at least one fact, or by recording that it is "
                "unresolved -- otherwise claims and guesses close it looking like knowledge")
        if float(row.spend_cad or 0.0) > float(row.spend_bound_cad or 0.0):
            raise ResearchRefused("spend exceeded the task's bound")
        days, why = freshness_for(row.domain)
        row.state = ANSWERED
        row.outcome = outcome.strip()
        row.confidence = confidence
        row.answered_at = t
        row.expires_on = None if days is None else t + timedelta(days=days)
        return {"task": row.id, "state": ANSWERED,
                "expires_on": row.expires_on.isoformat() if row.expires_on else None,
                "freshness_why": why}


def expire_due(db, *, now: datetime | None = None) -> list[int]:
    """Answered tasks past their expiry become EXPIRED and the question re-opens (once)."""
    _ensure(db)
    t = _now(now)
    out = []
    with db.session() as s:
        for row in s.scalars(select(ResearchTask).where(ResearchTask.state == ANSWERED,
                                                        ResearchTask.expires_on.is_not(None))):
            if _aware(row.expires_on) <= t:
                row.state = EXPIRED
                out.append((row.id, row.question, row.trigger, row.decision_ref, row.domain,
                            list(row.query_terms or [])))
    for tid, q, trig, dec, dom, terms in out:
        open_question(db, question=q, trigger=f"{trig}#after:{tid}", decision_ref=dec,
                      domain=dom, query_terms=terms, now=t)
    return [x[0] for x in out]


def tasks(db, *, state: str | None = None) -> list[dict]:
    _ensure(db)
    with db.session() as s:
        q = select(ResearchTask).order_by(ResearchTask.id.desc())
        if state:
            q = q.where(ResearchTask.state == state)
        return [{"id": r.id, "question": r.question, "trigger": r.trigger,
                 "decision_ref": r.decision_ref, "domain": r.domain, "state": r.state,
                 "query_terms": list(r.query_terms or []),
                 "internal_evidence": len(r.internal_evidence or []),
                 "sources": list(r.sources or []), "findings": list(r.findings or []),
                 "stop_condition": r.stop_condition, "spend_bound_cad": r.spend_bound_cad,
                 "expires_on": _aware(r.expires_on).isoformat() if r.expires_on else None,
                 "at": _aware(r.at).isoformat() if r.at else None}
                for r in s.scalars(q.limit(200))]


# ---- unknown detection (F-403) -----------------------------------------------------------

def detect_unknowns(db, *, today: date | None = None, now: datetime | None = None) -> dict:
    """Route the UNKNOWN/UNMEASURED readings on decision paths into research questions.

    Two sources to start, as F-403 names: learning domains nobody has observed, and the
    children's-safety constraints that rest on pages this build could not fetch. Idempotent:
    an open task per trigger is never duplicated.
    """
    from . import childrens, learning

    opened, kept = [], []
    radar = learning.radar(db, today=today)
    for d in radar["unobserved"]:
        r = open_question(
            db, question=f"What is currently true about {d['what']} for crochet pattern buyers?",
            trigger=f"learning.unobserved:{d['domain']}",
            decision_ref=f"intel.learning.radar:{d['domain']}", domain=d["domain"],
            query_terms=[d["domain"].replace("_", " ")],
            stop_condition="one dated, cited observation recorded in this domain", now=now)
        (opened if r["opened"] else kept).append(r["task"])
    for key in childrens.unfetched_sources():
        src = childrens.SOURCES.get(key)
        title = src.title if src is not None else key
        r = open_question(
            db, question=f"What does the primary text of '{title}' actually say, read in full?",
            trigger=f"childrens.unfetched:{key}",
            decision_ref="intel.childrens.constraints (children's-product publication gate)",
            domain="marketplace_policy", query_terms=[key.replace("_", " ")],
            stop_condition="the page fetched and read, or recorded unresolved with why", now=now)
        (opened if r["opened"] else kept).append(r["task"])
    return {"opened": opened, "already_open": kept,
            "unobserved_domains": len(radar["unobserved"]),
            "unfetched_sources": len(childrens.unfetched_sources())}
