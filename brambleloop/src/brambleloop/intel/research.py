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
from pathlib import Path

from sqlalchemy import JSON, DateTime, Float, Integer, String, Text, or_, select
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db import Base

OPEN, ANSWERED, STOPPED, EXPIRED = "open", "answered", "stopped", "expired"

CLAIM_CLASSES = ("fact", "source_claim", "inference", "hypothesis", "unresolved")
RETRIEVAL_CLASSES = ("fetched", "search_summary", "repository", "rendered_image", "internal")
FACT_GRADE = {"fetched", "repository", "rendered_image", "internal"}

# W4-FMBATCH1 additions.
QUESTION, METHOD_ADOPTION = "question", "method_adoption"
KINDS = (QUESTION, METHOD_ADOPTION)
DEFAULT_TIME_BOUND_DAYS, MAX_TIME_BOUND_DAYS = 30, 365
REOPEN_REASONS = ("new_evidence", "changed_assumptions")
#: F-420: what a research task must have done to be closed as answered.
EFFECTS = ("confidence_changed", "alternatives_narrowed", "constraint_established",
           "hypothesis_produced", "stop_justified")
#: F-411: the dimensions an established method's transfer is judged on before adoption.
APPLICABILITY_DIMENSIONS = ("assumptions", "topology", "scale", "data", "runtime",
                            "failure_modes")
APPLICABILITY_VERDICTS = ("transfers", "does_not_transfer", "unknown")
#: F-435: the machine-usable conclusion every answered task carries.
CONCLUSION_FIELDS = ("question", "status", "confidence", "evidence", "alternatives",
                     "constraints", "applicability", "unresolved", "next_test")
_STOP = frozenset("a an the of for to in on and or is are was were be what which how does do "
                  "did can could should would will with by about at from this that these "
                  "those it its currently now".split())


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
    # W4-FMBATCH1 (F-419/F-432/F-435/F-444): the task's bound, its spec and its conclusion.
    # Additive columns (core.migrate adds them to an existing table; old rows read None).
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=dict)


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

def question_key(question: str, domain: str, decision_ref: str) -> str:
    """F-432: a materially equivalent premise -- the same content words (order, case and
    function words ignored), in the same domain, for the same decision."""
    import re

    words = sorted({w for w in re.findall(r"[a-z0-9]+", str(question).lower())
                    if w not in _STOP})
    blob = " ".join(words) + "|" + str(domain).strip() + "|" + str(decision_ref).strip().lower()
    return hashlib.sha256(blob.encode()).hexdigest()


#: F-405: repository documents searched when this runtime carries them. The deploy image does
#: not (it carries src/, release/ and tests/ only), so there they are reported unavailable --
#: never silently skipped. Tests point these at fixtures.
DOCUMENTS = {
    "BUILD_STATE.md": Path(__file__).resolve().parents[3] / "BUILD_STATE.md",
    "DECISION_LOG.md": Path(__file__).resolve().parents[3] / "DECISION_LOG.md",
}
TESTS_DIR = Path(__file__).resolve().parents[3] / "tests"


def _like_all(col, terms):
    from sqlalchemy import and_

    return and_(*[col.ilike(f"%{t}%") for t in terms])


def search_internal_report(db, terms) -> tuple[list[dict], list[dict]]:
    """F-405: every internal corpus, searched before anything external.

    Returns (evidence, searched). `searched` lists each corpus with how many hits it gave or
    why it could not be read, so "searched internally first" is a record, not a claim.
    Corpora: lessons, learning observations, incidents, experiments (section 9 and the
    pre-registered growth experiments), prior failures (improvement failure memory),
    benchmark listings, the repository's BUILD_STATE and DECISION_LOG when present, and test
    names (the regression evidence that a behaviour was already pinned).
    """
    from ..core.models import (BenchmarkListing, Experiment, Incident, LearningObservation,
                               Lesson, RegisteredExperiment)

    terms = [str(t).strip() for t in terms or () if str(t).strip()]
    out: list[dict] = []
    searched: list[dict] = []
    if not terms:
        return out, [{"corpus": "*", "hits": 0, "why": "no query terms: nothing searched"}]

    def table(name, model, cols, ref, kind, text, extra=None):
        try:
            with db.session() as s:
                from sqlalchemy import or_ as _or

                q = select(model).where(_or(*[_like_all(c, terms) for c in cols]))
                rows = list(s.scalars(q.limit(20)))
                for r in rows:
                    item = {"ref": f"{ref}:{r.id}", "kind": kind, "text": text(r)[:300],
                            "retrieval": "internal"}
                    item.update((extra or (lambda _r: {}))(r))
                    out.append(item)
            searched.append({"corpus": name, "hits": len(rows)})
        except Exception as exc:  # noqa: BLE001 - an unreadable corpus is reported, not passed
            searched.append({"corpus": name, "hits": None,
                             "why": f"unreadable: {type(exc).__name__}: {str(exc)[:120]}"})

    table("lessons", Lesson, (Lesson.statement, Lesson.subject), "lessons", "lesson",
          lambda r: r.statement, lambda r: {"confidence": r.confidence})
    table("learning_observations", LearningObservation, (LearningObservation.summary,),
          "learning_observations", "external_signal", lambda r: r.summary)
    table("incidents", Incident, (Incident.summary, Incident.signature), "incidents",
          "incident", lambda r: f"{r.signature}: {r.summary}")
    table("experiments", Experiment, (Experiment.hypothesis, Experiment.name), "experiments",
          "experiment", lambda r: f"{r.name}: {r.hypothesis} (state {r.state})")
    table("registered_experiments", RegisteredExperiment, (RegisteredExperiment.hypothesis,),
          "registered_experiments", "experiment", lambda r: r.hypothesis)
    try:
        from ..improve.failure_memory import FailureRecord

        table("failure_memory", FailureRecord, (FailureRecord.method, FailureRecord.reason),
              "failure_memory", "prior_failure", lambda r: f"{r.method}: {r.reason}")
    except Exception as exc:  # noqa: BLE001
        searched.append({"corpus": "failure_memory", "hits": None,
                         "why": f"unreadable: {type(exc).__name__}"})
    table("benchmark_listings", BenchmarkListing, (BenchmarkListing.title,),
          "benchmark_listings", "benchmark", lambda r: r.title)
    for name, path in DOCUMENTS.items():
        if not Path(path).is_file():
            searched.append({"corpus": name, "hits": None,
                             "why": "not present in this runtime (the deploy image carries "
                                    "no repository documents)"})
            continue
        hits = 0
        for n, line in enumerate(Path(path).read_text(encoding="utf-8",
                                                      errors="replace").splitlines(), 1):
            low = line.lower()
            if all(t.lower() in low for t in terms):
                out.append({"ref": f"{name}:{n}", "kind": "document", "text": line[:300],
                            "retrieval": "internal"})
                hits += 1
                if hits >= 10:
                    break
        searched.append({"corpus": name, "hits": hits})
    hits = 0
    if Path(TESTS_DIR).is_dir():
        for f in sorted(Path(TESTS_DIR).glob("test_*.py")):
            for n, line in enumerate(f.read_text(encoding="utf-8",
                                                 errors="replace").splitlines(), 1):
                if line.startswith("def test_") and all(
                        t.lower().replace(" ", "_") in line.lower() for t in terms):
                    out.append({"ref": f"tests/{f.name}:{n}", "kind": "test",
                                "text": line[4:120], "retrieval": "internal"})
                    hits += 1
            if hits >= 10:
                break
        searched.append({"corpus": "tests", "hits": hits})
    else:
        searched.append({"corpus": "tests", "hits": None, "why": "no tests/ in this runtime"})
    return out, searched


def search_internal(db, terms) -> list[dict]:
    """The internal evidence matching every term (F-405; see `search_internal_report`)."""
    return search_internal_report(db, terms)[0]


# ---- tasks --------------------------------------------------------------------------------

def open_question(db, *, question: str, trigger: str, decision_ref: str, domain: str,
                  query_terms=(), stop_condition: str = "", spend_bound_cad: float = 0.0,
                  evidence_needed: str = "", if_unresolved: str = "",
                  time_bound_days: int = DEFAULT_TIME_BOUND_DAYS, consequential: bool = False,
                  kind: str = QUESTION, prior_confidence: str = "unknown",
                  reopen_because: dict | None = None, now: datetime | None = None) -> dict:
    """Open a research task once per trigger while one is open. Internal evidence is attached.

    F-419: the task defines its question, the evidence that would answer it, a time bound and
    a spend bound, and its stop condition. F-444: it also names, up front, the smallest
    owner/external action that resolves it if research cannot. F-432: a materially equivalent
    question (same normalised question, domain and decision) that is already answered and
    not expired is reused, not re-researched, unless `reopen_because` names new evidence or
    changed assumptions.
    """
    _ensure(db)
    if len(str(question).split()) < 5:
        raise ResearchRefused("a research question has to be a question, not a label")
    if not trigger.strip() or not decision_ref.strip():
        raise ResearchRefused("a task names the unknown that raised it and the decision it "
                              "serves; research for no decision is reading (F-424)")
    missing = [n for n, v in (("evidence_needed", evidence_needed),
                              ("stop_condition", stop_condition),
                              ("if_unresolved", if_unresolved)) if not str(v or "").strip()]
    if missing:
        raise ResearchRefused(
            f"a research task defines {missing} before it starts (F-419 question, evidence "
            f"needed, bound and stop condition; F-444 the smallest action if it cannot be "
            f"resolved) -- otherwise research is endless exploration")
    try:
        days = int(time_bound_days)
    except (TypeError, ValueError):
        days = 0
    if not 1 <= days <= MAX_TIME_BOUND_DAYS:
        raise ResearchRefused(f"time_bound_days must be 1..{MAX_TIME_BOUND_DAYS} (F-419)")
    if kind not in KINDS:
        raise ResearchRefused(f"kind must be one of {KINDS}")
    if reopen_because is not None and (
            reopen_because.get("reason") not in REOPEN_REASONS
            or not str(reopen_because.get("note") or "").strip()):
        raise ResearchRefused(f"reopening an answered question needs a reason in "
                              f"{REOPEN_REASONS} and a note saying what changed (F-432)")
    freshness_for(domain)  # refuses an unknown domain before anything is written
    terms = [str(t).strip() for t in query_terms if str(t).strip()]
    key = _key(trigger)
    qkey = question_key(question, domain, decision_ref)
    t = _now(now)
    reopens = None
    with db.session() as s:
        existing = s.scalar(select(ResearchTask).where(ResearchTask.dedupe_key == key,
                                                       ResearchTask.state == OPEN))
        if existing is None:
            for row in s.scalars(select(ResearchTask).where(ResearchTask.state == OPEN)):
                if (row.detail or {}).get("question_key") == qkey:
                    existing = row
                    break
        if existing is not None:
            d = dict(existing.detail or {})
            d["duplicate_asks"] = int(d.get("duplicate_asks") or 0) + 1
            existing.detail = d
            return {"task": existing.id, "opened": False, "reason": "already open"}
        for row in s.scalars(select(ResearchTask).where(ResearchTask.state == ANSWERED)
                             .order_by(ResearchTask.id.desc())):
            if (row.detail or {}).get("question_key") != qkey:
                continue
            if _aware(row.expires_on) is not None and _aware(row.expires_on) <= t:
                continue                       # stale: expire_due re-opens it
            if reopen_because is None:
                d = dict(row.detail or {})
                d["reuse_count"] = int(d.get("reuse_count") or 0) + 1
                d["spend_avoided_cad"] = round(float(d.get("spend_avoided_cad") or 0.0)
                                               + float(row.spend_cad or 0.0), 4)
                row.detail = d
                return {"task": row.id, "opened": False, "reused": True,
                        "reason": "answered and fresh: reused (F-432)",
                        "outcome": row.outcome,
                        "conclusion": (row.detail or {}).get("conclusion")}
            reopens = row.id
            break
    internal, searched = search_internal_report(db, terms)
    with db.session() as s:
        row = ResearchTask(question=question.strip(), trigger=trigger.strip()[:200],
                           dedupe_key=key, decision_ref=decision_ref.strip()[:200],
                           domain=domain, query_terms=terms, internal_evidence=internal,
                           stop_condition=stop_condition.strip(),
                           spend_bound_cad=max(0.0, float(spend_bound_cad or 0.0)),
                           at=t, deadline=t + timedelta(days=days),
                           detail={"question_key": qkey,
                                   "evidence_needed": evidence_needed.strip(),
                                   "if_unresolved": if_unresolved.strip(),
                                   "time_bound_days": days, "consequential": bool(consequential),
                                   "kind": kind, "prior_confidence": prior_confidence or "unknown",
                                   "searched_corpora": searched,
                                   "reopens": reopens, "reopen_because": reopen_because})
        s.add(row)
        s.flush()
        return {"task": row.id, "opened": True, "internal_evidence": len(internal),
                "reopens": reopens}


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


def _publisher(src: dict) -> str:
    """Who stands behind a source: the citation's host, else the source's name (F-408)."""
    from urllib.parse import urlparse

    host = urlparse(str(src.get("citation") or "")).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host or str(src.get("source") or "").strip().lower()


def add_finding(db, task_id: int, *, statement: str, claim_class: str, rests_on=(),
                confidence: str = "", contradicts=(), single_source_reason: str = "") -> str:
    """One labelled finding. `rests_on` names sources (S1..), internal refs or findings (F1..).

    F-426: `contradicts` names earlier findings this one conflicts with; the task cannot be
    answered until each conflict is reconciled (`reconcile`) or recorded unresolved.
    F-408: on a consequential task a `fact` from external sources needs two independent
    publishers, or a stated `single_source_reason` (cross-checking "where practical").
    """
    if claim_class not in CLAIM_CLASSES:
        raise ResearchRefused(f"claim_class must be one of {CLAIM_CLASSES} (F-409)")
    refs = [str(r) for r in rests_on or () if str(r).strip()]
    conflicts = [str(r) for r in contradicts or () if str(r).strip()]
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
        bad = [r for r in conflicts if r not in found]
        if bad:
            raise ResearchRefused(f"contradicts names findings this task does not hold: {bad}")
        if claim_class == "fact":
            grade = [r for r in refs if (r in srcs and srcs[r]["retrieval"] in FACT_GRADE)
                     or r in internal]
            if not grade:
                raise ResearchRefused(
                    "a fact needs a source this system read in full (fetched, repository, "
                    "rendered image) or internal evidence; a search summary supports only a "
                    "source_claim")
            if (row.detail or {}).get("consequential") and not any(r in internal for r in refs):
                publishers = {_publisher(srcs[r]) for r in refs
                              if r in srcs and srcs[r]["retrieval"] in FACT_GRADE}
                if len(publishers) < 2 and not single_source_reason.strip():
                    raise ResearchRefused(
                        "a consequential fact is cross-checked against two independent "
                        f"sources (publishers here: {sorted(publishers)}), or the reason a "
                        "second is not practical is recorded (F-408)")
        if claim_class in ("source_claim", "inference") and not refs:
            raise ResearchRefused(f"a {claim_class} names what it rests on")
        fs = list(row.findings or [])
        ref = f"F{len(fs) + 1}"
        item = {"ref": ref, "statement": statement.strip(), "claim_class": claim_class,
                "rests_on": refs, "confidence": confidence}
        if conflicts:
            item["contradicts"] = conflicts
        if single_source_reason.strip():
            item["single_source_reason"] = single_source_reason.strip()
        fs.append(item)
        row.findings = fs
        return ref


def reconcile(db, task_id: int, *, kept: str, rejected: str, why: str) -> dict:
    """F-426: an explicit reconciliation of two conflicting findings, with the reason."""
    if not why.strip():
        raise ResearchRefused("a reconciliation says why one finding is kept (F-426)")
    with db.session() as s:
        row = s.get(ResearchTask, task_id)
        if row is None:
            raise ResearchRefused(f"no research task {task_id}")
        found = {x["ref"] for x in row.findings or []}
        if kept not in found or rejected not in found or kept == rejected:
            raise ResearchRefused("reconcile two distinct findings this task holds")
        d = dict(row.detail or {})
        rec = list(d.get("reconciliations") or [])
        rec.append({"kept": kept, "rejected": rejected, "why": why.strip()})
        d["reconciliations"] = rec
        row.detail = d
        return {"task": row.id, "reconciliations": len(rec)}


def contradictions(row) -> list[dict]:
    """Conflicting finding pairs, each reconciled, recorded unresolved, or open (F-426)."""
    fs = list(row.findings or [])
    rec = (row.detail or {}).get("reconciliations") or []
    out = []
    for f in fs:
        for other in f.get("contradicts") or []:
            pair = {f["ref"], other}
            how = "open"
            if any({r["kept"], r["rejected"]} == pair for r in rec):
                how = "reconciled"
            elif any(g["claim_class"] == "unresolved" and pair <= set(g.get("rests_on") or [])
                     for g in fs):
                how = "unresolved"
            out.append({"findings": sorted(pair), "state": how})
    return out


def _check_conclusion(row, effect, conclusion, confidence) -> dict:
    """F-420, F-411, F-435: what an answer must show it did, in a machine-usable shape."""
    detail = row.detail or {}
    fs = list(row.findings or [])
    classes = {f["claim_class"] for f in fs}
    if not isinstance(effect, dict) or effect.get("kind") not in EFFECTS \
            or not str(effect.get("statement") or "").strip():
        raise ResearchRefused(
            f"an answer names what the research changed -- effect kind in {EFFECTS} with a "
            "statement; sources collected without changing anything are theatre (F-420)")
    if not isinstance(conclusion, dict):
        raise ResearchRefused("an answer carries a structured conclusion (F-435)")
    need = ("alternatives", "constraints", "unresolved", "next_test", "applicability")
    absent = [k for k in need if k not in conclusion]
    if absent:
        raise ResearchRefused(f"the conclusion states {absent} explicitly, even when empty "
                              "(F-435)")
    cited = {r for f in fs for r in f.get("rests_on") or []}
    uncited = [x["ref"] for x in row.sources or [] if x["ref"] not in cited]
    if uncited:
        raise ResearchRefused(f"sources {uncited} support no finding: collecting sources to "
                              "look rigorous is refused (F-420)")
    kind = effect["kind"]
    alts = conclusion.get("alternatives") or []
    if kind == "confidence_changed" and (not confidence or confidence ==
                                         detail.get("prior_confidence", "unknown")):
        raise ResearchRefused("confidence_changed needs a confidence different from the "
                              f"prior {detail.get('prior_confidence', 'unknown')!r} (F-420)")
    if kind == "alternatives_narrowed" and not any(
            isinstance(a, dict) and a.get("status") == "rejected" and a.get("why")
            for a in alts):
        raise ResearchRefused("alternatives_narrowed names at least one alternative rejected "
                              "and why (F-420)")
    if kind == "constraint_established" and not (conclusion.get("constraints")
                                                 and "fact" in classes):
        raise ResearchRefused("constraint_established states the constraint and rests on a "
                              "fact (F-420)")
    if kind == "hypothesis_produced":
        nt = conclusion.get("next_test")
        if "hypothesis" not in classes or not isinstance(nt, dict) or not str(
                nt.get("what") or "").strip() or not str(nt.get("falsified_if") or "").strip():
            raise ResearchRefused("hypothesis_produced records the hypothesis and a bounded "
                                  "next test: what, and what result would falsify it (F-420)")
    if kind == "stop_justified" and "unresolved" not in classes:
        raise ResearchRefused("stop_justified records what remained unresolved (F-420)")
    app = conclusion.get("applicability")
    adopt = None
    if detail.get("kind") == METHOD_ADOPTION:
        if not isinstance(app, dict):
            raise ResearchRefused("a method-adoption answer judges applicability (F-411)")
        missing = [k for k in APPLICABILITY_DIMENSIONS
                   if not isinstance(app.get(k), dict)
                   or app[k].get("verdict") not in APPLICABILITY_VERDICTS
                   or not str(app[k].get("why") or "").strip()]
        if missing:
            raise ResearchRefused(f"applicability is judged on {list(APPLICABILITY_DIMENSIONS)} "
                                  f"each with a verdict in {APPLICABILITY_VERDICTS} and a why; "
                                  f"missing or malformed: {missing} (F-411)")
        adopt = all(app[k]["verdict"] == "transfers" for k in APPLICABILITY_DIMENSIONS)
    nt = conclusion.get("next_test")
    if isinstance(nt, dict) and nt:
        try:
            days = int(nt.get("max_days") or 0)
            spend = float(nt.get("max_spend_cad") or 0.0)
        except (TypeError, ValueError):
            days, spend = 0, -1.0
        if not 1 <= days <= 90 or spend < 0:
            raise ResearchRefused("a next test is bounded: max_days 1..90 and max_spend_cad "
                                  ">= 0 (F-435)")
    return {"question": row.question,
            "status": "unresolved" if kind == "stop_justified" else "answered",
            "confidence": confidence or detail.get("prior_confidence", "unknown"),
            "evidence": sorted({f["ref"] for f in fs if f["claim_class"] != "unresolved"}
                               | cited),
            "alternatives": alts, "constraints": list(conclusion.get("constraints") or []),
            "applicability": app, "adopt": adopt,
            "unresolved": list(conclusion.get("unresolved") or [])
            + [f["statement"] for f in fs if f["claim_class"] == "unresolved"],
            "next_test": nt or None, "effect": effect, "decision_ref": row.decision_ref}


def answer(db, task_id: int, *, outcome: str, confidence: str = "", effect: dict | None = None,
           conclusion: dict | None = None, now: datetime | None = None) -> dict:
    """Close a task. It must hold a fact or an explicit `unresolved` finding; expiry is set.

    W4-FMBATCH1: it must also show what the research changed (F-420), leave no conflict
    silently decided (F-426), judge a method's applicability before adoption (F-411), and
    carry a machine-usable conclusion (F-435), stored on the task and returned.
    """
    t = _now(now)
    with db.session() as s:
        row = s.get(ResearchTask, task_id)
        if row is None:
            raise ResearchRefused(f"no research task {task_id}")
        if row.state != OPEN:
            raise ResearchRefused(f"task {task_id} is {row.state}, not open")
        classes = {f["claim_class"] for f in row.findings or []}
        if not classes & {"fact", "unresolved"}:
            raise ResearchRefused(
                "a task is answered by at least one fact, or by recording that it is "
                "unresolved -- otherwise claims and guesses close it looking like knowledge")
        if float(row.spend_cad or 0.0) > float(row.spend_bound_cad or 0.0):
            raise ResearchRefused("spend exceeded the task's bound")
        open_conflicts = [c["findings"] for c in contradictions(row) if c["state"] == "open"]
        if open_conflicts:
            raise ResearchRefused(f"conflicting findings {open_conflicts} are neither "
                                  "reconciled nor recorded unresolved; the convenient one is "
                                  "not chosen silently (F-426)")
        concl = _check_conclusion(row, effect, conclusion, confidence)
        days, why = freshness_for(row.domain)
        row.state = ANSWERED
        row.outcome = outcome.strip()
        row.confidence = confidence
        row.answered_at = t
        row.expires_on = None if days is None else t + timedelta(days=days)
        d = dict(row.detail or {})
        d["conclusion"] = concl
        row.detail = d
        return {"task": row.id, "state": ANSWERED,
                "expires_on": row.expires_on.isoformat() if row.expires_on else None,
                "freshness_why": why, "conclusion": concl}


def conclusion(db, task_id: int) -> dict | None:
    """F-435: the stored machine-usable conclusion of an answered task."""
    _ensure(db)
    with db.session() as s:
        row = s.get(ResearchTask, task_id)
        return None if row is None else (row.detail or {}).get("conclusion")


def stop(db, task_id: int, *, why: str, remains_unknown: str, smallest_action: str = "",
         now: datetime | None = None) -> dict:
    """F-444: research that cannot resolve its unknown stops with an escalation.

    The escalation reports what was searched (query terms, internal corpora and hits,
    sources read), what remains unknown, why it matters (the decision it serves) and the
    smallest owner/external action that would resolve it -- the one named when the task
    opened unless a better one is given now.
    """
    t = _now(now)
    with db.session() as s:
        row = s.get(ResearchTask, task_id)
        if row is None:
            raise ResearchRefused(f"no research task {task_id}")
        if row.state != OPEN:
            raise ResearchRefused(f"task {task_id} is {row.state}, not open")
        d = dict(row.detail or {})
        action = (smallest_action or d.get("if_unresolved") or "").strip()
        if not why.strip() or not remains_unknown.strip() or not action:
            raise ResearchRefused("a stopped task reports why, what remains unknown and the "
                                  "smallest action that would resolve it (F-444)")
        d["escalation"] = {
            "searched": {"query_terms": list(row.query_terms or []),
                         "internal_corpora": d.get("searched_corpora") or [],
                         "internal_hits": len(row.internal_evidence or []),
                         "sources": [{"ref": x["ref"], "source": x["source"],
                                      "retrieval": x["retrieval"]} for x in row.sources or []]},
            "remains_unknown": remains_unknown.strip(),
            "why_it_matters": (f"it serves {row.decision_ref}"
                               + (" (consequential)" if d.get("consequential") else "")),
            "smallest_action": action, "why_stopped": why.strip(), "at": t.isoformat()}
        row.detail = d
        row.state = STOPPED
        row.answered_at = t
        return {"task": row.id, "state": STOPPED, "escalation": d["escalation"]}


def stop_overdue(db, *, now: datetime | None = None) -> list[int]:
    """F-419: the time bound is enforced -- an open task past its deadline stops, escalated."""
    _ensure(db)
    t = _now(now)
    due = []
    with db.session() as s:
        for row in s.scalars(select(ResearchTask).where(ResearchTask.state == OPEN,
                                                        ResearchTask.deadline.is_not(None))):
            if _aware(row.deadline) <= t:
                due.append(row.id)
    out = []
    for tid in due:
        try:
            stop(db, tid, why="the task's time bound passed without an answer (F-419)",
                 remains_unknown="the question as asked", now=t)
            out.append(tid)
        except ResearchRefused:
            continue        # a pre-W4-FMBATCH1 row with no named action stays open, visibly
    return out


def escalations(db) -> list[dict]:
    """Stopped tasks and their escalations, newest first (F-444)."""
    _ensure(db)
    with db.session() as s:
        return [{"task": r.id, "question": r.question, "decision_ref": r.decision_ref,
                 **((r.detail or {}).get("escalation") or {})}
                for r in s.scalars(select(ResearchTask).where(ResearchTask.state == STOPPED)
                                   .order_by(ResearchTask.id.desc()).limit(200))]


def metrics(db) -> dict:
    """F-449: research quality, each figure measured from the task rows or None with why.

    Never a zero for "nothing to measure": with no tasks every rate is None.
    """
    _ensure(db)
    with db.session() as s:
        rows = list(s.scalars(select(ResearchTask)))
    if not rows:
        return {"tasks": 0, "why": "no research task exists yet: every figure is unmeasured",
                "resolved": None, "reuse_rate": None, "stale_refreshed": None,
                "duplicates_avoided": None, "experiments_prevented": None,
                "spend_avoided_cad": None, "source_quality": None,
                "decisions_changed": None}
    det = [r.detail or {} for r in rows]
    answered = [r for r in rows if r.state in (ANSWERED, EXPIRED)]
    reuses = sum(int(d.get("reuse_count") or 0) for d in det)
    dups = sum(int(d.get("duplicate_asks") or 0) for d in det)
    asks = len(rows) + reuses + dups
    expired_ids = {r.id for r in rows if r.state == EXPIRED}
    refreshed = sum(1 for r in rows if r.state in (ANSWERED, EXPIRED)
                    and any(r.trigger.endswith(f"#after:{i}") for i in expired_ids))
    srcs = [x for r in rows for x in r.sources or []]
    concl = [d.get("conclusion") for d in det if d.get("conclusion")]
    prevented = sum(1 for c in concl if c.get("adopt") is False
                    or (c.get("effect") or {}).get("kind") == "stop_justified")
    changed = sum(1 for c in concl if (c.get("effect") or {}).get("kind")
                  in ("confidence_changed", "alternatives_narrowed", "constraint_established"))
    return {"tasks": len(rows), "resolved": len(answered),
            "stopped_escalated": sum(1 for r in rows if r.state == STOPPED),
            "reuse_rate": round(reuses / asks, 4) if asks else None,
            "stale_refreshed": refreshed if expired_ids else None,
            "duplicates_avoided": reuses + dups,
            "experiments_prevented": prevented if concl else None,
            "spend_avoided_cad": round(sum(float(d.get("spend_avoided_cad") or 0.0)
                                           for d in det), 4),
            "source_quality": (round(sum(1 for x in srcs if x["retrieval"] in FACT_GRADE)
                                     / len(srcs), 4) if srcs else None),
            "decisions_changed": changed if concl else None,
            "definitions": {
                "reuse_rate": "answers reused / (tasks opened + reuses + duplicate asks)",
                "experiments_prevented": "answered tasks whose method did not transfer "
                                         "(F-411 adopt false) or that justified stopping",
                "decisions_changed": "answered tasks whose recorded effect changed confidence, "
                                     "narrowed alternatives or established a constraint for "
                                     "their decision_ref -- 'materially improved' is a "
                                     "downstream outcome this table cannot see",
                "spend_avoided_cad": "spend of the answered tasks reused instead of redone"}}


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
                d = row.detail or {}
                out.append((row.id, row.question, row.trigger, row.decision_ref, row.domain,
                            list(row.query_terms or []), row.stop_condition or "",
                            d.get("evidence_needed") or "", d.get("if_unresolved") or "",
                            int(d.get("time_bound_days") or DEFAULT_TIME_BOUND_DAYS),
                            bool(d.get("consequential")), d.get("kind") or QUESTION,
                            row.confidence or d.get("prior_confidence") or "unknown"))
    for (tid, q, trig, dec, dom, terms, stop_c, need, action, days, cons, kind,
         prior) in out:
        # A row from before W4-FMBATCH1 has no evidence_needed / action: the re-opened task
        # says so instead of inventing them.
        open_question(db, question=q, trigger=f"{trig}#after:{tid}", decision_ref=dec,
                      domain=dom, query_terms=terms,
                      stop_condition=stop_c or "answered with a fact or recorded unresolved",
                      evidence_needed=need or f"what answered task {tid} relied on, re-read",
                      if_unresolved=action or "a person re-reads the sources of task "
                                              f"{tid} and records the result",
                      time_bound_days=days, consequential=cons, kind=kind,
                      prior_confidence=prior, now=t)
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
                 "evidence_needed": (r.detail or {}).get("evidence_needed"),
                 "if_unresolved": (r.detail or {}).get("if_unresolved"),
                 "deadline": _aware(r.deadline).isoformat() if r.deadline else None,
                 "conclusion": (r.detail or {}).get("conclusion"),
                 "escalation": (r.detail or {}).get("escalation"),
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
            stop_condition="one dated, cited observation recorded in this domain",
            evidence_needed=f"a dated, cited observation of {d['what']}",
            if_unresolved=(f"owner or a tester records one dated observation of {d['what']} "
                           "(learning.record) from a source they read"), now=now)
        (opened if r["opened"] else kept).append(r["task"])
    for key in childrens.unfetched_sources():
        src = childrens.SOURCES.get(key)
        title = src.title if src is not None else key
        r = open_question(
            db, question=f"What does the primary text of '{title}' actually say, read in full?",
            trigger=f"childrens.unfetched:{key}",
            decision_ref="intel.childrens.constraints (children's-product publication gate)",
            domain="marketplace_policy", query_terms=[key.replace("_", " ")],
            stop_condition="the page fetched and read, or recorded unresolved with why",
            evidence_needed=f"the primary text of '{title}', fetched and read in full",
            if_unresolved=(f"a person opens '{title}' in a browser and records what it says "
                           "(the page refuses this system's fetcher)"),
            consequential=True, now=now)
        (opened if r["opened"] else kept).append(r["task"])
    return {"opened": opened, "already_open": kept,
            "unobserved_domains": len(radar["unobserved"]),
            "unfetched_sources": len(childrens.unfetched_sources())}
