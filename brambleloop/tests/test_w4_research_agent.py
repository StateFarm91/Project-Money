"""W4-AGENTS W3: the Research Agent (Final Master s44: F-401, F-429, F-430, F-435, F-436, F-437).

Invokable by any agent and self-triggered; the lowest-cost adequate method, internal first;
official documentation for platform behaviour; machine-usable conclusions; architecture flags
for the weekly review that never relax a hard floor. CA$0, no network, no model.

Run: cd brambleloop && PYTHONPATH=src:tests $PY tests/test_w4_research_agent.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import socket
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import DEFAULT_AGENTS, Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog, Job, Lesson, Phase  # noqa: E402
from brambleloop.intel import research as R  # noqa: E402
from brambleloop.intel import research_agent as RA  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: E402,F401 - registers handlers
from brambleloop.runtime.worker import CADENCES, JobContext, handlers  # noqa: E402

_N = [0]
_TMP = tempfile.mkdtemp(prefix="w4res_")


def _db() -> Database:
    _N[0] += 1
    db = Database(f"sqlite:///{_TMP}/r{_N[0]}.db")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _open(db, **kw):
    """INTEG7: FMBATCH1's `R.open_question` requires the F-419/F-444 fields up front."""
    kw.setdefault("evidence_needed", "a held record or source that answers the question")
    kw.setdefault("stop_condition", "a fact-grade finding, or recorded unresolved with why")
    kw.setdefault("if_unresolved", RA.smallest_action(kw.get("domain", "")))
    return R.open_question(db, **kw)


def _run(db, agent, jt, inputs=None):
    job = JobQueue(db).enqueue(agent, jt, inputs or {})
    return handlers.get(jt)(JobContext(job=job, db=db, queue=JobQueue(db),
                                       registry=Registry(db), phase=Phase.SHADOW)), job


def _no_network():
    real = socket.socket.connect

    def refuse(*_a, **_k):
        raise AssertionError("the Research Agent made a network call")
    socket.socket.connect = refuse
    return real


def test_the_agent_is_declared_chartered_classed_and_scheduled():
    from brambleloop.authority.classes import JOB_CLASS
    from brambleloop.autonomy import charters

    spec = next(a for a in DEFAULT_AGENTS if a["name"] == RA.AGENT)
    assert spec["daily_cost_ceiling_cad"] == 0.0
    assert set(spec["allowed_job_types"]) == {"research.investigate", "research.sweep",
                                              "research.flag_architecture"}
    assert RA.AGENT in charters.BY_KEY["intelligence"].agents
    assert charters.validate() == []
    for jt in spec["allowed_job_types"]:
        assert handlers.get(jt) is not None and jt in JOB_CLASS, jt
    assert ("research_sweep", RA.AGENT, "research.sweep", 86400) in CADENCES
    reg = Registry(_db())
    for jt in spec["allowed_job_types"]:
        reg.authorize(RA.AGENT, jt)


def test_method_selection_is_lowest_cost_adequate_and_names_what_is_missing():
    tech = RA.select_method("techniques")
    assert tech["chosen"] == "internal_retrieval" and tech["blocked_on"] is None
    # F-437: platform policy is never "answered" from internal notes
    pol = RA.select_method("marketplace_policy")
    assert pol["chosen"] is None and pol["blocked_on"] == "official_docs"
    assert "fetch" in pol["blocked_why"]
    by = {a["method"]: a for a in pol["alternatives"]}
    assert by["internal_retrieval"]["adequate"] is False
    ranks = [m.cost_rank for m in RA.methods()]
    assert ranks == sorted(ranks)
    assert len(RA.methods()) == 8
    for m in RA.methods():
        assert m.available or m.why_unavailable, m


def test_an_agent_can_invoke_research_and_internal_evidence_comes_first():
    db = _db()
    with db.session() as s:
        s.add(Lesson(origin_cell="test", subject="tapestry crochet", statement="tapestry crochet colour carry "
                     "shows through on light yarn; measured on three swatches",
                     confidence="medium"))
    # another agent's job asks for research (F-401)
    caller = JobQueue(db).enqueue("orchestrator", "autonomy.department_review", {})
    ctx = JobContext(job=caller, db=db, queue=JobQueue(db), registry=Registry(db),
                     phase=Phase.SHADOW)
    RA.request_research(ctx, question="Does tapestry crochet colour carry show through on "
                        "light yarn?", trigger="test:tapestry", decision_ref="cir.draft colour",
                        domain="techniques", query_terms=["tapestry crochet"])
    with db.session() as s:
        job = s.scalar(select(Job).where(Job.job_type == "research.investigate"))
        assert job.agent == RA.AGENT
    real = _no_network()
    try:
        out = handlers.get("research.investigate")(JobContext(
            job=job, db=db, queue=JobQueue(db), registry=Registry(db), phase=Phase.SHADOW))
    finally:
        socket.socket.connect = real
    assert out["status"] == RA.EVIDENCE_GATHERED and out["method"]["chosen"] == \
        "internal_retrieval"
    assert any(e.startswith("lessons:") for e in out["evidence"])
    # F-435: the conclusion is machine-usable
    for k in ("question", "status", "confidence", "evidence", "method", "constraints",
              "applicability", "unresolved", "next_test"):
        assert k in out, k
    # it never wrote a fact on its own
    t = R.tasks(db)[0]
    assert not [f for f in t["findings"] if f["claim_class"] == "fact"]
    with db.session() as s:
        assert s.scalar(select(AuditLog).where(AuditLog.action == RA.INVESTIGATED)) is not None


def test_no_evidence_is_recorded_unresolved_with_the_next_bounded_test():
    db = _db()
    opened = _open(db, question="What palettes are rising for nursery blankets "
                             "this season?", trigger="test:palettes", decision_ref="x.y",
                             domain="aesthetics", query_terms=["zzqq-no-such-term"])
    out, _ = _run(db, RA.AGENT, "research.investigate", {"task_id": opened["task"]})
    # INTEG7: research that cannot resolve stops through FMBATCH1's R.stop with its F-444
    # escalation (what was searched, what remains unknown, the smallest action).
    assert out["status"] == RA.UNRESOLVED and out["answered"]["state"] == R.STOPPED
    assert "web_search" in out["next_test"] or "marketplace_observation" in out["next_test"]
    esc = out["answered"]["escalation"]
    assert esc["remains_unknown"] and esc["smallest_action"] and esc["why_stopped"]
    assert esc["searched"]["query_terms"] == ["zzqq-no-such-term"]
    t = R.tasks(db)[0]
    assert [f["claim_class"] for f in t["findings"]] == ["unresolved"]
    assert t["state"] == R.STOPPED
    again, _ = _run(db, RA.AGENT, "research.investigate", {"task_id": opened["task"]})
    assert again["ran"] is False and again["work_done"] == 0


def test_platform_policy_is_blocked_on_official_docs_not_guessed():
    db = _db()
    opened = _open(db, question="What does Etsy currently require for digital "
                             "download licence wording?", trigger="test:policy",
                             decision_ref="listing policy", domain="marketplace_policy",
                             query_terms=["zzqq-nothing"])
    out, _ = _run(db, RA.AGENT, "research.investigate", {"task_id": opened["task"]})
    assert out["status"] == RA.BLOCKED_ON_METHOD and "official_docs" in out["next_test"]


def test_the_sweep_self_triggers_investigations_once_per_task():
    db = _db()
    _open(db, question="What is currently true about crochet search ranking?",
                    trigger="test:sweep", decision_ref="seo", domain="search_behaviour",
                    query_terms=["ranking"])
    out, _ = _run(db, RA.AGENT, "research.sweep")
    assert out["queued"] >= 1 and out["due"] >= 1
    with db.session() as s:
        jobs = list(s.scalars(select(Job).where(Job.job_type == "research.investigate")))
    assert jobs and all(j.agent == RA.AGENT for j in jobs)
    for j in jobs:
        handlers.get("research.investigate")(JobContext(job=j, db=db, queue=JobQueue(db),
                                                        registry=Registry(db),
                                                        phase=Phase.SHADOW))
    # investigated tasks are not due again inside the window
    assert not set(RA.due_for_investigation(db)) & {j.inputs["task_id"] for j in jobs}


def test_an_architecture_flag_needs_graded_evidence_and_never_relaxes_a_floor():
    db = _db()
    with db.session() as s:
        s.add(Lesson(origin_cell="test", subject="hero frames", statement="product-only hero frames outsold "
                     "modelled frames for blankets", confidence="medium"))
    opened = _open(db, question="Do product-only hero frames outsell modelled "
                             "ones for blankets?", trigger="test:hero", decision_ref="visual",
                             domain="aesthetics", query_terms=["hero frames"])
    tid = opened["task"]
    ref = R.tasks(db)[0]
    with db.session() as s:
        row = s.get(R.ResearchTask, tid)
        lesson_ref = row.internal_evidence[0]["ref"]
    out, _ = _run(db, RA.AGENT, "research.flag_architecture",
                  {"task_id": tid, "assumption": "every hero frame needs a model",
                   "evidence_refs": [lesson_ref], "why": "the lesson measured the opposite"})
    assert out["flag"] and out["changes_nothing"] is True, out
    flags = RA.architecture_flags(db)
    assert flags and flags[0]["assumption"] == "every hero frame needs a model"
    # no graded evidence: refused
    bad, _ = _run(db, RA.AGENT, "research.flag_architecture",
                  {"task_id": tid, "assumption": "x is wrong", "evidence_refs": ["S9"],
                   "why": "a hunch"})
    assert bad["ran"] is False
    # F-430: a hard floor is never flagged for relaxation
    floor, _ = _run(db, RA.AGENT, "research.flag_architecture",
                    {"task_id": tid, "assumption": "certification slows launches",
                     "evidence_refs": [lesson_ref], "why": "skip it"})
    assert floor["ran"] is False and "F-430" in floor["why"]
    assert ref["id"] == tid


def test_the_weekly_review_reads_the_flags():
    src = (ROOT / "src/brambleloop/runtime/release.py").read_text()
    assert '"research_architecture_flags": _research_flags(ctx.db)' in src
    db = _db()
    assert RA.architecture_flags(db) == []


# ---- batch W4: F-405 internal evidence first, F-432 research memory, F-404 confidence trigger

def test_f405_every_internal_store_is_searched_before_any_external_method():
    from datetime import date as _date

    from brambleloop.core.models import Incident, RegisteredExperiment
    from brambleloop.improve.failure_memory import FailureRecord

    db = _db()
    with db.session() as s:
        s.add(Incident(severity="P3", signature="test:bobble", summary="bobble stitch "
                       "rows pucker on the twin"))
        s.add(RegisteredExperiment(key="x:bobble", product_slug="x", hypothesis="a bobble "
                                   "stitch hero earns a click", metric="m", design="holdout",
                                   success_threshold=1, failure_threshold=0, minimum_sample=1,
                                   higher_is_better=True, stop_on=_date.today().isoformat(),
                                   cost_cad=0, owner="o", state="registered"))
        s.add(FailureRecord(fingerprint="f" * 64, cell="visual", method="bobble stitch "
                            "displacement render", source="test", reason="bobble stitch "
                            "shading flattened"))
    opened = _open(db, question="Why do bobble stitch rows pucker in the twin?",
                             trigger="test:bobble-q", decision_ref="cir.twin",
                             domain="techniques", query_terms=["bobble stitch"])
    out = RA.investigate(db, opened["task"])
    kinds = {e.split(":")[0] for e in out["evidence"]}
    assert {"incidents", "registered_experiments", "failure_memory"} <= kinds, out["evidence"]  # INTEG7: the rules name pre-registered experiments by their table
    assert out["status"] == RA.EVIDENCE_GATHERED


# INTEG7: the agent's F-432 duplicate check (prior_answer, STOPPED_DUPLICATE) is dropped in favour
# of FMBATCH1's open-time reuse (R.open_question question_key), which
# test_w4_fmbatch1_research covers. See DEPARTMENTS.md, "Reconciliation with FMBATCH1".


def test_f404_a_stale_domain_becomes_one_research_question_per_episode():
    from datetime import date as _date, datetime as _dt, timedelta as _td, timezone as _tz

    from brambleloop.core.models import LearningObservation

    db = _db()
    with db.session() as s:
        s.add(LearningObservation(domain="marketplace_policy", source="test", citation="c",
                                  observed_on=_dt.now(_tz.utc) - _td(days=60),
                                  summary="an old reading of the policy"))
    first = RA.stale_domains_to_research(db)
    assert len(first["opened"]) == 1 and first["stale_domains"] >= 1
    assert RA.stale_domains_to_research(db)["opened"] == []          # still open: once
    tid = first["opened"][0]
    out = RA.investigate(db, tid)                                     # blocked: official docs
    assert out["status"] == RA.BLOCKED_ON_METHOD
    # INTEG7: with FMBATCH1's wider internal search the task holds evidence (a repository
    # test record), so it stays open for the no-change stop; with none it would stop
    # escalated. Either way the same stale episode is not opened again.
    assert (out["answered"] is None) == bool(out["evidence"])
    assert RA.stale_domains_to_research(db)["opened"] == []          # once per episode
    assert isinstance(_date.today(), _date)


# ---- batch W5: F-420 no research theatre, F-444 escalation, F-449 metrics, retention ------

def test_f420_investigations_that_add_nothing_are_stopped_with_a_justification():
    db = _db()
    with db.session() as s:
        s.add(Lesson(origin_cell="test", subject="moss stitch", statement="moss stitch "
                     "edges curl less than single crochet on blankets", confidence="medium"))
    opened = _open(db, question="Do moss stitch edges curl less on blankets?",
                             trigger="test:moss", decision_ref="cir.draft edge",
                             domain="techniques", query_terms=["moss stitch"])
    tid = opened["task"]
    runs = []
    for _ in range(3):
        out, _job = _run(db, RA.AGENT, "research.investigate", {"task_id": tid})
        runs.append(out)
    assert runs[0]["changed"] is True and runs[0]["stopped"] is None
    assert runs[1]["changed"] is False and runs[1]["unchanged_runs"] == 1
    assert runs[2]["stopped"] and RA.STOPPED_NO_CHANGE in runs[2]["stopped"]
    assert "Next:" in runs[2]["stopped"]
    assert {t["id"]: t["state"] for t in R.tasks(db)}[tid] == R.STOPPED
    # INTEG7: routed through R.stop, so the stop carries its F-444 escalation
    esc = next(e for e in R.escalations(db) if e["task"] == tid)
    assert RA.STOPPED_NO_CHANGE in esc["why_stopped"] and esc["smallest_action"]


def test_f444_and_f449_the_sweep_stores_escalations_and_metrics():
    from brambleloop.core.models import OperatingReading

    db = _db()
    pol = _open(db, question="What does Etsy currently require for digital "
                          "download licence wording?", trigger="test:esc", decision_ref=
                          "listing policy gate", domain="marketplace_policy",
                          query_terms=["zzqq-nothing"])
    RA.investigate(db, pol["task"])
    esc = RA.escalations(db)                 # INTEG7: FMBATCH1's R.escalations
    item = next(e for e in esc if e["task"] == pol["task"])
    assert item["why_it_matters"].startswith("it serves listing policy gate")
    assert "official_docs" in item["smallest_action"]
    assert item["searched"]["query_terms"] == ["zzqq-nothing"] and item["remains_unknown"]
    out, _ = _run(db, RA.AGENT, "research.sweep")
    with db.session() as s:
        kinds = {r.kind: r.payload for r in s.scalars(select(OperatingReading))}
    assert kinds[RA.ESCALATIONS]["count"] >= 1
    m = kinds[RA.METRICS]                    # INTEG7: R.metrics plus the agent counters
    assert m["tasks"] >= 1 and m["stopped_escalated"] >= 1
    assert m["agent"]["investigations"] >= 0 and "stopped_no_change" in m["agent"]
    # nothing answered with a conclusion yet: unmeasured is None, never 0
    for k in ("experiments_prevented", "decisions_changed"):
        assert m[k] is None, (k, m[k])


def test_retention_protects_the_storefront_grant_chain_and_classifies_research_reads():
    from brambleloop.ops import retention
    from brambleloop.ops import storefront_authority as sfa
    from brambleloop.runtime import quality_ops

    for a in (sfa.APPROVED, sfa.REVOKED, sfa.REBASED):
        assert a in retention.PROTECTED_ACTIONS, a
    for a in (RA.INVESTIGATED, RA.FLAGGED, quality_ops.READING):
        assert a in retention.KNOWN_READ_ACTIONS, a
    assert RA.INVESTIGATED in retention.PROTECTED_ACTIONS     # metrics count every row


# ---- W4-INTELREC C05: F-406 external research escalation --------------------------------

def _fixture_get(pages):
    def get(url, **_kw):
        if url.endswith("/robots.txt"):
            return 404, b""
        return (200, pages[url].encode()) if url in pages else (404, b"")
    return get


def test_f406_a_platform_question_internal_evidence_cannot_settle_plans_its_primary_pages():
    import os
    from unittest.mock import patch

    from brambleloop.intel import research_fetch

    urls = RA.official_sources("marketplace_policy", ["refund"])
    assert urls and all(u.startswith("https://help.etsy.com/") for u in urls), urls
    assert RA.official_sources("marketplace_policy", ["zzqq-nothing"]) == []

    # fetch step OFF: blocked and stopped, and the stop names the pages and the switch
    db = _db()
    off = _open(db, question="What does Etsy currently say about refunds for digital "
                "downloads?", trigger="test:f406-off", decision_ref="listing policy",
                domain="marketplace_policy", query_terms=["refund"])
    with patch.dict(os.environ, {research_fetch.ENABLE_VAR: "0"}):
        out = RA.investigate(db, off["task"])
    assert out["status"] == RA.BLOCKED_ON_METHOD and out["external_planned"] == urls
    assert "switching the fetch step on would read" in out["next_test"]

    # fetch step ON: the task waits open for the read, the fetch step plans the page, and
    # after the (fixture) read the task holds a fetched source
    db = _db()
    on = _open(db, question="What does Etsy currently say about refunds for digital "
               "downloads?", trigger="test:f406-on", decision_ref="listing policy",
               domain="marketplace_policy", query_terms=["refund"])
    tid = on["task"]
    with patch.dict(os.environ, {research_fetch.ENABLE_VAR: "1"}):
        waiting = RA.investigate(db, tid)
        assert waiting["status"] == RA.AWAITING_EXTERNAL and waiting["stopped"] is None
        planned = research_fetch.plan_fetches(db)
        assert (tid, urls[0]) in planned, planned
        research_fetch.run(db, get=_fixture_get({urls[0]: "Digital listings are not able to "
                                                            "be returned. " * 20}),
                           sleep=lambda _s: None)
        after = RA.investigate(db, tid)
    t = next(x for x in R.tasks(db) if x["id"] == tid)
    assert any(src["retrieval"] == "fetched" and src["citation"] == urls[0]
               for src in t["sources"]), t["sources"]
    assert after["status"] == RA.EVIDENCE_GATHERED, after["status"]


def test_f406_a_page_the_fetch_step_failed_to_read_is_not_retried_every_run():
    import os
    from unittest.mock import patch

    from brambleloop.intel import research_fetch

    db = _db()
    task = _open(db, question="What does Etsy currently say about refunds for digital "
                 "downloads?", trigger="test:f406-fail", decision_ref="listing policy",
                 domain="marketplace_policy", query_terms=["refund"])
    with patch.dict(os.environ, {research_fetch.ENABLE_VAR: "1"}):
        RA.investigate(db, task["task"])
        first = [p for p in research_fetch.plan_fetches(db) if p[0] == task["task"]]
        research_fetch.run(db, get=_fixture_get({}), sleep=lambda _s: None)   # all 404
        second = [p for p in research_fetch.plan_fetches(db) if p[0] == task["task"]]
    assert first and first[0] not in second


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                fails += 1
                print("FAIL", name, repr(e))
                traceback.print_exc()
    print(f"{fails} failed")
    sys.exit(1 if fails else 0)
