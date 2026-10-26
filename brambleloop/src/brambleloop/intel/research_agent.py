"""The Research Agent (Final Master s44: F-401, F-402, F-429, F-430, F-435, F-436, F-437).

`intel.research` already holds research as data: a task per unknown, its sources, its
labelled findings (fact / source_claim / inference / hypothesis / unresolved) and its expiry.
What it lacked was somebody to do the research. This module is that agent's method:

* **F-401: invokable and self-triggered.** Any agent may request research
  (`request_research`, which queues `research.investigate` for `research_agent`), and the
  agent's own daily `research.sweep` turns the open unknowns into investigations.
* **F-402 / F-436: the lowest-cost adequate method, internal first.** Every investigation
  reads what the company already holds (lessons, learning observations, the repository's own
  research record) before anything else. The method ladder names each method's cost rank,
  which domains it is adequate for, and whether it is available to this agent right now.
  An adequate method that is not available is named with what would make it available; it
  is never substituted by a cheaper inadequate one presented as an answer.
* **F-437: primary documentation for platform behaviour.** For marketplace policy and media
  capability only official documentation (or a bounded experiment) is adequate. Internal
  notes about a policy are evidence of what somebody once read, not the policy.
* **F-435: machine-usable output.** Each investigation returns and audits one structured
  conclusion: question, status, confidence, evidence, alternatives, constraints,
  applicability, unresolved issues and the recommended bounded next test.
* **F-429 / F-430: it may challenge the architecture, never the floors.** When evidence the
  task holds contradicts a stated assumption, the agent records a flag that the weekly
  evolution review reads. A flag changes nothing by itself, and it can never relax a hard
  floor (certification, Shadow Mode, spend, the owner gates).

Constraints in code: CA$0, no network call, no model call. The only writes are research-task
rows (through `intel.research`) and audit rows. Nothing is presented as known that a source
did not establish: findings this agent writes on its own are `unresolved`, never `fact`.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from . import research as R

AGENT = "research_agent"
INVESTIGATED = "research.investigated"
FLAGGED = "research.architecture_flag"
REINVESTIGATE_DAYS = 7
REPO_RESEARCH = Path(__file__).resolve().parents[3] / "research"
REPO_HITS_MAX = 8

# Statuses of a structured conclusion.
EVIDENCE_GATHERED = "EVIDENCE_GATHERED"      # held evidence found; a reader must weigh it
UNRESOLVED = "UNRESOLVED"                    # recorded as open, with the next bounded test
BLOCKED_ON_METHOD = "BLOCKED_ON_METHOD"      # the adequate method is not available here
NOT_OPEN = "NOT_OPEN"


@dataclass(frozen=True)
class Method:
    key: str
    cost_rank: int
    what: str
    available: bool
    why_unavailable: str = ""


def _repo_available() -> bool:
    return REPO_RESEARCH.is_dir()


def methods() -> tuple[Method, ...]:
    """F-436's ladder, cheapest first, with what this agent can use today."""
    return (
        Method("internal_retrieval", 0, "lessons and learning observations already held", True),
        Method("repository_inspection", 0, "the repository's own research record",
               _repo_available(),
               "" if _repo_available() else "the research record is not in this image"),
        Method("official_docs", 1, "current official documentation, read in full", False,
               "no sanctioned fetch path for this agent; an owner-approved documentation "
               "fetcher would make it available"),
        Method("marketplace_observation", 2, "market_radar's sanctioned scans", False,
               "delegated: market_radar observes on its own cadence; this agent reads what "
               "it stored (internal retrieval)"),
        Method("web_search", 2, "a web search provider", False,
               "no search provider is connected (a provider is an owner decision)"),
        Method("academic_literature", 3, "published literature", False,
               "no literature access is connected"),
        Method("controlled_browser", 4, "a controlled browser session", False,
               "browser work is an owner-supervised action"),
        Method("bounded_experiment", 5, "a pre-registered bounded experiment", False,
               "delegated: growth.experiments pre-registers tests with thresholds; this agent "
               "recommends one rather than running it"),
    )


# Which methods can answer a question in each domain (F-436, F-437). Anything not named here
# uses DEFAULT_ADEQUATE.
ADEQUATE: dict[str, tuple[str, ...]] = {
    "techniques": ("internal_retrieval", "repository_inspection", "academic_literature",
                   "bounded_experiment"),
    "aesthetics": ("internal_retrieval", "marketplace_observation", "web_search"),
    "seasonal_behaviour": ("internal_retrieval", "marketplace_observation",
                           "bounded_experiment"),
    # F-437: platform behaviour is read from the platform's own documentation.
    "marketplace_policy": ("official_docs",),
    "media_capability": ("official_docs", "bounded_experiment"),
    "search_behaviour": ("internal_retrieval", "marketplace_observation", "official_docs",
                         "bounded_experiment"),
    "competitor_positioning": ("internal_retrieval", "marketplace_observation"),
    "customer_pain": ("internal_retrieval", "marketplace_observation"),
}
DEFAULT_ADEQUATE = ("internal_retrieval", "repository_inspection", "bounded_experiment")

# F-430: what a research flag may never relax. A flag naming one is refused.
HARD_FLOORS: tuple[str, ...] = ("certification", "certify", "shadow mode", "spend",
                                "budget", "owner approval", "owner gate", "kyc",
                                "legal acceptance", "fake review", "captcha")


def select_method(domain: str) -> dict:
    """The lowest-cost adequate method, and every alternative with why it was not chosen."""
    adequate = ADEQUATE.get(domain, DEFAULT_ADEQUATE)
    ladder = methods()
    chosen = next((m for m in ladder if m.key in adequate and m.available), None)
    lowest = next((m for m in ladder if m.key in adequate), None)
    alternatives = []
    for m in ladder:
        if chosen is not None and m.key == chosen.key:
            continue
        why = ("not adequate for this domain" if m.key not in adequate else
               (m.why_unavailable if not m.available else
                "adequate but costlier than the chosen method"))
        alternatives.append({"method": m.key, "cost_rank": m.cost_rank, "adequate":
                             m.key in adequate, "available": m.available, "why": why})
    return {"domain": domain, "adequate": list(adequate),
            "chosen": chosen.key if chosen else None,
            "blocked_on": (lowest.key if chosen is None and lowest is not None else None),
            "blocked_why": (lowest.why_unavailable if chosen is None and lowest else ""),
            "alternatives": alternatives}


def _repo_hits(terms) -> list[dict]:
    """Repository research files that mention every term (read-only, bounded)."""
    terms = [str(t).strip().lower() for t in terms or () if str(t).strip()]
    if not terms or not _repo_available():
        return []
    out = []
    for p in sorted(REPO_RESEARCH.rglob("*.md")):
        try:
            text = p.read_text(encoding="utf-8", errors="ignore").lower()
        except OSError:
            continue
        if all(t in text for t in terms):
            out.append({"path": str(p.relative_to(REPO_RESEARCH.parent)),
                        "bytes": len(text)})
            if len(out) >= REPO_HITS_MAX:
                break
    return out


def _task(db, task_id: int):
    R._ensure(db)
    with db.session() as s:
        row = s.get(R.ResearchTask, task_id)
        if row is None:
            return None
        return {"id": row.id, "question": row.question, "domain": row.domain,
                "state": row.state, "decision_ref": row.decision_ref,
                "terms": list(row.query_terms or []),
                "internal": list(row.internal_evidence or []),
                "sources": list(row.sources or []), "findings": list(row.findings or [])}


def investigate(db, task_id: int, *, today: date | None = None) -> dict:
    """Run the cheapest adequate research this agent can on one open task (CA$0)."""
    today = today or datetime.now(timezone.utc).date()
    t = _task(db, task_id)
    if t is None or t["state"] != R.OPEN:
        return {"task": task_id, "status": NOT_OPEN, "work_done": 0}
    plan = select_method(t["domain"])
    # F-402: internal evidence first, refreshed (a lesson may have arrived since opening).
    internal = R.search_internal(db, t["terms"])
    with db.session() as s:
        row = s.get(R.ResearchTask, task_id)
        have = {x["ref"] for x in row.internal_evidence or []}
        new_internal = [x for x in internal if x["ref"] not in have]
        if new_internal:
            row.internal_evidence = list(row.internal_evidence or []) + new_internal
    added_sources = []
    if "repository_inspection" in plan["adequate"] or plan["chosen"] == "repository_inspection":
        cited = {x["citation"] for x in t["sources"]}
        for hit in _repo_hits(t["terms"]):
            if hit["path"] in cited:
                continue
            R.add_source(db, task_id, source="repository research record",
                         citation=hit["path"], retrieval="repository", read_on=today)
            added_sources.append(hit["path"])
    t = _task(db, task_id)
    evidence = [x["ref"] for x in t["internal"]] + [x["ref"] for x in t["sources"]]
    if plan["chosen"] is None:
        status = BLOCKED_ON_METHOD
        next_test = (f"use {plan['blocked_on']} ({plan['blocked_why']}); internal evidence is "
                     f"attached, but it is not adequate for {t['domain']}")
    elif evidence:
        status = EVIDENCE_GATHERED
        next_test = ("weigh the attached evidence against the decision "
                     f"{t['decision_ref']!r}; if it does not settle it, pre-register a bounded "
                     f"experiment (growth.experiments)")
    else:
        status = UNRESOLVED
        next_test = ("no held evidence mentions " + ", ".join(t["terms"] or ["the question"])
                     + "; the next bounded step is the cheapest adequate method not yet "
                       "available: " + next((a["method"] for a in plan["alternatives"]
                                             if a["adequate"] and not a["available"]),
                                            "a pre-registered bounded experiment"))
    answered = None
    if status in (UNRESOLVED, BLOCKED_ON_METHOD):
        # Recorded once as unresolved, so the question is not re-asked blindly; the task's
        # domain freshness re-opens it later (intel.research.expire_due).
        if not any(f["claim_class"] == "unresolved" for f in t["findings"]):
            R.add_finding(db, task_id, statement=f"{status}: {next_test}",
                          claim_class="unresolved", confidence="none")
        if status == UNRESOLVED or not evidence:
            answered = R.answer(db, task_id, outcome=f"{status}: {next_test}",
                                confidence="none")
    conclusion = {
        "task": task_id, "question": t["question"], "status": status,
        "confidence": "none" if status != EVIDENCE_GATHERED else "low",
        "evidence": evidence, "new_internal": len(new_internal),
        "new_sources": added_sources, "method": plan,
        "constraints": ["CA$0", "no network call", "no model call",
                        "findings it writes alone are 'unresolved', never 'fact'"],
        "applicability": {"domain": t["domain"], "decision": t["decision_ref"]},
        "unresolved": [] if status == EVIDENCE_GATHERED else [next_test],
        "next_test": next_test, "answered": answered,
        "work_done": 1,
    }
    return conclusion


def flag_architecture(db, task_id: int, *, assumption: str, evidence_refs, why: str) -> dict:
    """F-429: record that evidence this task holds contradicts a current assumption.

    The flag is an `inference` finding resting on the named evidence, plus an audit row the
    weekly evolution review reads. It changes nothing. F-430: an assumption that is a hard
    floor cannot be flagged for relaxation.
    """
    text = f"{assumption} {why}".lower()
    floor = next((f for f in HARD_FLOORS if f in text), None)
    if floor:
        raise R.ResearchRefused(
            f"a research flag cannot challenge the hard floor {floor!r} (F-430); floors "
            f"change only by the owner's decision")
    if not str(assumption).strip() or not str(why).strip():
        raise R.ResearchRefused("a flag names the assumption and why the evidence contradicts it")
    t = _task(db, task_id)
    if t is None:
        raise R.ResearchRefused(f"no research task {task_id}")
    srcs = {x["ref"]: x for x in t["sources"]}
    internal = {x["ref"] for x in t["internal"]}
    refs = [str(r) for r in evidence_refs or ()]
    graded = [r for r in refs if r in internal
              or (r in srcs and srcs[r]["retrieval"] in R.FACT_GRADE)]
    if not graded:
        raise R.ResearchRefused(
            "an architecture flag rests on evidence read in full or measured internally; a "
            "search summary or a hunch does not challenge the design")
    ref = R.add_finding(db, task_id, claim_class="inference", rests_on=refs,
                        statement=f"contradicts the assumption: {assumption.strip()} -- "
                                  f"{why.strip()}", confidence="flagged for review")
    from ..core.models import AuditLog

    with db.session() as s:
        row = AuditLog(actor=AGENT, action=FLAGGED, artifact=f"research_task:{task_id}",
                       detail={"assumption": assumption.strip()[:500], "why": why.strip()[:1000],
                               "evidence": refs, "finding": ref, "changes_nothing": True})
        s.add(row)
        s.flush()
        return {"flag": row.id, "finding": ref, "task": task_id}


def architecture_flags(db, *, days: int = 35) -> list[dict]:
    """The flags the weekly evolution review reads (newest first)."""
    from sqlalchemy import select

    from ..core.models import AuditLog

    since = datetime.now(timezone.utc) - timedelta(days=days)
    with db.session() as s:
        return [{"id": a.id, "task": a.artifact, **{k: (a.detail or {}).get(k)
                                                     for k in ("assumption", "why", "evidence")}}
                for a in s.scalars(select(AuditLog).where(AuditLog.action == FLAGGED,
                                                          AuditLog.at >= since)
                                   .order_by(AuditLog.id.desc()).limit(50))]


def due_for_investigation(db, *, now: datetime | None = None) -> list[int]:
    """Open tasks not investigated in the last REINVESTIGATE_DAYS."""
    from sqlalchemy import select

    from ..core.models import AuditLog

    now = now or datetime.now(timezone.utc)
    R._ensure(db)
    since = now - timedelta(days=REINVESTIGATE_DAYS)
    with db.session() as s:
        recent = {a for (a,) in s.execute(select(AuditLog.artifact).where(
            AuditLog.action == INVESTIGATED, AuditLog.at >= since)).all()}
        return [r.id for r in s.scalars(select(R.ResearchTask).where(
            R.ResearchTask.state == R.OPEN).order_by(R.ResearchTask.id))
                if f"research_task:{r.id}" not in recent]


def request_research(ctx, *, question: str, trigger: str, decision_ref: str, domain: str,
                     query_terms=()) -> object:
    """F-401: how any agent invokes the Research Agent from inside its own job."""
    return ctx.enqueue("research_agent", "research.investigate",
                       {"question": question, "trigger": trigger,
                        "decision_ref": decision_ref, "domain": domain,
                        "query_terms": list(query_terms)},
                       idempotency_key=f"research:{R._key(trigger)[:32]}")


def request_architecture_review(ctx, *, task_id: int, assumption: str, evidence_refs,
                                why: str) -> object:
    """F-429: how an agent holding contradicting evidence asks the Research Agent to flag it
    (the flag is still checked against the task's evidence and the hard floors)."""
    return ctx.enqueue("research_agent", "research.flag_architecture",
                       {"task_id": int(task_id), "assumption": assumption,
                        "evidence_refs": list(evidence_refs), "why": why},
                       idempotency_key=f"research.flag:{task_id}:{R._key(assumption)[:24]}")
