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


def _fetch_on() -> bool:
    from . import research_fetch

    return research_fetch.fetch_enabled()


def methods() -> tuple[Method, ...]:
    """F-436's ladder, cheapest first, with what this agent can use today."""
    return (
        Method("internal_retrieval", 0, "lessons and learning observations already held", True),
        Method("repository_inspection", 0, "the repository's own research record",
               _repo_available(),
               "" if _repo_available() else "the research record is not in this image"),
        # INTEG7 (breakpoint 5): FMBATCH1's allowlisted fetch run (`intel.research_fetch`,
        # learn.scan) reads official documentation for allowlisted hosts when its switch is on.
        Method("official_docs", 1, "current official documentation, read in full",
               _fetch_on(),
               "" if _fetch_on() else
               "the allowlisted research fetch step is off (BRAMBLELOOP_RESEARCH_FETCH is not "
               "1 in this deployment)"),
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


# F-405: the repository's own records, read when they are present (they are not copied into
# the production image, so there this is honestly unavailable rather than silently empty).
REPO_RECORDS = (REPO_RESEARCH.parent / "BUILD_STATE.md", REPO_RESEARCH.parent / "DECISION_LOG.md")
STOPPED_NO_CHANGE = "STOPPED_NO_CHANGE"
NO_CHANGE_LIMIT = 2
ESCALATIONS = "research.escalations"
METRICS = "research.metrics"


def _repo_hits(terms) -> list[dict]:
    """Repository records and research files that mention every term (read-only, bounded):
    BUILD_STATE and DECISION_LOG first (F-405), then the research record."""
    terms = [str(t).strip().lower() for t in terms or () if str(t).strip()]
    if not terms or not _repo_available():
        return []
    out = []
    files = [p for p in REPO_RECORDS if p.is_file()] + sorted(REPO_RESEARCH.rglob("*.md"))
    for p in files:
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


def _all_terms(text: str, terms) -> bool:
    t = (text or "").lower()
    return all(x.lower() in t for x in terms)


def internal_evidence(db, terms, *, exclude_task: int | None = None) -> list[dict]:
    """F-405 (INTEG7 reconciliation): FMBATCH1's `intel.research.search_internal_report` is the
    internal search. This agent adds only its two extra corpora, the listing-test memory and
    earlier answered research, as refs that the task's findings may rest on (retrieval
    `internal`)."""
    from sqlalchemy import select

    terms = [str(t).strip() for t in terms or () if str(t).strip()]
    if not terms:
        return []
    out, _searched = R.search_internal_report(db, terms)
    out = list(out)
    from ..core.models import ListingMemory

    with db.session() as s:
        for r in s.scalars(select(ListingMemory).limit(500)):
            if _all_terms(f"{r.idea} {r.context} {r.note}", terms):
                out.append({"ref": f"listing_memory:{r.id}", "kind": "listing_test",
                            "text": f"{r.idea} {r.outcome} in {r.context}"[:300],
                            "retrieval": "internal"})
        for r in s.scalars(select(R.ResearchTask).where(R.ResearchTask.state == R.ANSWERED)
                           .limit(500)):
            if r.id != exclude_task and _all_terms(f"{r.question} {r.outcome}", terms):
                out.append({"ref": f"research_tasks:{r.id}", "kind": "prior_research",
                            "text": f"{r.question} -> {r.outcome}"[:300],
                            "retrieval": "internal"})
    return out


def _unchanged_runs(db, task_id: int, evidence: list[str]) -> int:
    """How many most-recent investigations of this task ended with exactly this evidence."""
    from sqlalchemy import select

    from ..core.models import AuditLog

    n = 0
    with db.session() as s:
        for a in s.scalars(select(AuditLog).where(
                AuditLog.action == INVESTIGATED,
                AuditLog.artifact == f"research_task:{task_id}").order_by(AuditLog.id.desc())
                           .limit(10)):
            if sorted((a.detail or {}).get("evidence") or []) == sorted(evidence):
                n += 1
            else:
                break
    return n


def smallest_action(domain: str) -> str:
    """F-444 (INTEG7): the smallest action that resolves a question research cannot, named up
    front. It is the cheapest adequate method that is not available here, and what it needs."""
    plan = select_method(domain)
    missing = [a for a in plan["alternatives"] if a["adequate"] and not a["available"]]
    if missing:
        return f"make {missing[0]['method']} available: {missing[0]['why']}"
    return "pre-register a bounded experiment in growth.experiments"


def _stop(db, task_id: int, why: str, remains_unknown: str) -> dict:
    """Stop through FMBATCH1's `R.stop`, so the stop carries its F-444 escalation. The smallest
    action is the one named when the task opened; the method ladder supplies it for a task
    opened without one."""
    with db.session() as s:
        row = s.get(R.ResearchTask, task_id)
        named = str((row.detail or {}).get("if_unresolved") or "").strip() if row else ""
        domain = row.domain if row else ""
    return R.stop(db, task_id, why=why[:2000], remains_unknown=remains_unknown[:1000],
                  smallest_action="" if named else smallest_action(domain))


def stale_domains_to_research(db, *, today: date | None = None) -> dict:
    """F-404: a learning domain whose only observations have gone stale is a decision being
    made on stale evidence -- it becomes a research question (once per stale episode)."""
    from . import learning

    from sqlalchemy import select

    radar = learning.radar(db, today=today)
    opened, kept = [], []
    now = datetime.now(timezone.utc)
    for d in radar["stale"]:
        trigger = f"learning.stale:{d['domain']}"
        R._ensure(db)
        with db.session() as s:
            live = [r for r in s.scalars(select(R.ResearchTask).where(
                R.ResearchTask.dedupe_key == R._key(trigger),
                R.ResearchTask.state == R.ANSWERED))
                if R._aware(r.expires_on) is None or R._aware(r.expires_on) > now]
            # INTEG7: research that could not resolve the episode stops with an escalation
            # (R.stop). That escalation stands for the domain's freshness window, so the same
            # stale episode is not re-opened and re-stopped every day.
            days, _why = R.freshness_for(d["domain"])
            live += [r for r in s.scalars(select(R.ResearchTask).where(
                R.ResearchTask.dedupe_key == R._key(trigger),
                R.ResearchTask.state == R.STOPPED))
                if days is None or (R._aware(r.answered_at) is not None
                                    and R._aware(r.answered_at) + timedelta(days=days) > now)]
        if live:
            # this stale episode was already researched; its own expiry re-opens it
            kept.append(live[0].id)
            continue
        r = R.open_question(
            db, question=f"What is currently true about {d['what']}? The newest observation "
                         f"here has gone stale.",
            trigger=trigger,
            decision_ref=f"intel.learning.radar:{d['domain']}", domain=d["domain"],
            query_terms=[d["domain"].replace("_", " ")],
            evidence_needed=f"one observation of {d['what']} fresher than "
                            f"{d['fresh_for_days']} days",
            stop_condition=f"one observation fresher than {d['fresh_for_days']} days, or "
                           f"recorded unresolved with why",
            if_unresolved=smallest_action(d["domain"]))
        (opened if r["opened"] else kept).append(r["task"])
    return {"opened": opened, "already_open": kept, "stale_domains": len(radar["stale"])}


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
    # F-432: reuse of an answered, fresh question happens when the task opens
    # (`R.open_question`); an open task is always researched.
    plan = select_method(t["domain"])
    # F-402 / F-405: every internal record first, refreshed (evidence may have arrived since).
    internal = internal_evidence(db, t["terms"], exclude_task=task_id)
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
    # F-420: research must change something. An investigation that adds no evidence to a task
    # still open is counted; after NO_CHANGE_LIMIT in a row the task is stopped with the
    # justification and its next test, instead of being re-read every week for show.
    unchanged_runs = _unchanged_runs(db, task_id, evidence)
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
    stopped = None
    if status in (EVIDENCE_GATHERED, BLOCKED_ON_METHOD) and evidence \
            and unchanged_runs >= NO_CHANGE_LIMIT:
        stopped = (f"{STOPPED_NO_CHANGE}: {unchanged_runs + 1} investigations in a row added "
                   f"no evidence; stopped rather than re-read. Next: {next_test}")
        _stop(db, task_id, stopped, remains_unknown=t["question"])
    if status in (UNRESOLVED, BLOCKED_ON_METHOD) and stopped is None:
        # Recorded once as unresolved, so the question is not re-asked blindly; the task's
        # domain freshness re-opens it later (intel.research.expire_due).
        if not any(f["claim_class"] == "unresolved" for f in t["findings"]):
            R.add_finding(db, task_id, statement=f"{status}: {next_test}",
                          claim_class="unresolved", confidence="none")
        if status == UNRESOLVED or not evidence:
            # INTEG7 (breakpoint 2): "could not resolve" is FMBATCH1's STOPPED state with its
            # escalation, not an answer (an answer must name its effect and a conclusion).
            stopped = f"{status}: {next_test}"
            answered = _stop(db, task_id, stopped, remains_unknown=t["question"])
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
        "changed": bool(new_internal or added_sources) or unchanged_runs == 0,
        "unchanged_runs": unchanged_runs, "stopped": stopped,
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


# ---- F-444 escalation and F-449 metrics --------------------------------------------------

def escalations(db) -> list[dict]:
    """F-444 (INTEG7): FMBATCH1's escalation report (`R.escalations`) is the one report."""
    return R.escalations(db)


def metrics(db) -> dict:
    """F-449 (INTEG7): FMBATCH1's research metrics (`R.metrics`), with this agent's own
    counters beside them. A measure with no source stays UNMEASURED or None, never 0."""
    from sqlalchemy import func, select

    from ..core.models import AuditLog

    R._ensure(db)
    out = dict(R.metrics(db))
    with db.session() as s:
        investigations = s.scalar(select(func.count()).select_from(AuditLog).where(
            AuditLog.action == INVESTIGATED)) or 0
        stopped_no_change = sum(1 for r in s.scalars(select(R.ResearchTask).where(
            R.ResearchTask.state == R.STOPPED))
            if STOPPED_NO_CHANGE in str(((r.detail or {}).get("escalation") or {})
                                        .get("why_stopped") or ""))
    out["agent"] = {"investigations": investigations, "stopped_no_change": stopped_no_change}
    return out
