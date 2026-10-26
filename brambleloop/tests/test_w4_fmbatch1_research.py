"""W4-FMBATCH1 batch R: research discipline in intel/research.py.

Rows and their criteria (Final Master v1.0, quoted):
- F-405 "Search BUILD_STATE, DECISION_LOG, experiments, incidents, durable lessons, benchmarks,
  source data, prior failures, tests and current production evidence before paying to
  rediscover an answer externally."
- F-408 "Consequential findings should be cross-checked against multiple independent sources
  where practical. A single search result is not automatically established truth."
- F-411 "Finding an established method does not authorize adoption. Evaluate whether its
  assumptions, topology, scale, data, runtime and failure modes transfer..."
- F-419 "Each substantial research task defines the question, evidence needed, time/spend
  bound and stop condition so research cannot become endless exploration."
- F-420 "Do not collect sources merely to appear rigorous. Research must change confidence,
  narrow alternatives, establish a constraint, produce a testable hypothesis or justify
  stopping."
- F-426 "Conflicting credible sources trigger explicit reconciliation or an unresolved state.
  Do not choose the convenient source silently."
- F-432 "Before starting research, check whether the same question or materially equivalent
  premise has already been answered. Reopen only with new evidence, changed assumptions or
  expired/stale findings."
- F-435 "Produce structured conclusions including question, answer/status, confidence,
  evidence, alternatives, constraints, applicability, unresolved issues and recommended
  bounded next test."
- F-444 "If research cannot resolve a material unknown, report what was searched, what remains
  unknown, why it matters and the smallest owner/external action capable of resolving it."
- F-449 "Track research questions resolved, reuse rate, stale findings refreshed, duplicate
  research avoided, experiments prevented, spend avoided, source quality and downstream
  decisions materially improved."
No network call; spends nothing.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
_TMP = Path(tempfile.mkdtemp(prefix="fmb1_research_"))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import Experiment, Incident, Lesson  # noqa: E402
from brambleloop.intel import research as R  # noqa: E402

NOW = datetime(2026, 10, 21, 12, tzinfo=timezone.utc)
_n = [0]
_DOCS = _TMP / "docs"
_DOCS.mkdir()
_TESTS = _TMP / "tests"
_TESTS.mkdir()
R.DOCUMENTS = {"BUILD_STATE.md": _DOCS / "BUILD_STATE.md",
               "DECISION_LOG.md": _DOCS / "DECISION_LOG.md"}
R.TESTS_DIR = _TESTS


def _db() -> Database:
    _n[0] += 1
    db = Database(f"sqlite:///{_TMP}/d{_n[0]}.sqlite")
    db.create_all()
    return db


def _refused(fn) -> str:
    try:
        fn()
    except R.ResearchRefused as exc:
        return str(exc)
    raise AssertionError("expected a refusal")


SPEC = {"stop_condition": "the rule read in the platform's own text",
        "evidence_needed": "the platform's published rule on pattern bundle file counts",
        "if_unresolved": "owner reads Etsy's digital-file help page and records the rule"}


def _open(db, question="Does the platform limit how many files a pattern bundle holds?",
          trigger="t:bundle", domain="marketplace_policy", decision="listing.bundle_policy",
          terms=("bundle",), **kw):
    spec = {**SPEC, **kw}
    return R.open_question(db, question=question, trigger=trigger, decision_ref=decision,
                           domain=domain, query_terms=terms, now=NOW, **spec)


def _empty(**kw):
    c = {"alternatives": [], "constraints": [], "unresolved": [], "next_test": None,
         "applicability": None}
    c.update(kw)
    return c


def _row(db, tid):
    with db.session() as s:
        r = s.get(R.ResearchTask, tid)
        s.expunge(r)
        return r


# ---- F-419 / F-444 ----------------------------------------------------------------------

def test_f419_a_task_defines_evidence_needed_bound_stop_condition_and_fallback():
    db = _db()
    for missing in ("evidence_needed", "stop_condition", "if_unresolved"):
        msg = _refused(lambda: _open(db, **{missing: "  "}))
        assert missing in msg and "F-419" in msg, msg
    assert "time_bound_days" in _refused(lambda: _open(db, time_bound_days=0))
    assert "time_bound_days" in _refused(lambda: _open(db, time_bound_days=400))
    tid = _open(db, time_bound_days=7)["task"]
    t = R.tasks(db)[0]
    assert t["evidence_needed"] == SPEC["evidence_needed"] and t["if_unresolved"]
    assert t["deadline"] == (NOW + timedelta(days=7)).isoformat() and tid


def test_f419_f444_an_overdue_task_stops_with_a_full_escalation():
    db = _db()
    with db.session() as s:
        s.add(Lesson(origin_cell="seo_search", subject="bundle",
                     statement="bundle listings with 12 files converted worse in our test",
                     evidence_ref="experiments:4"))
    tid = _open(db, time_bound_days=3)["task"]
    R.add_source(db, tid, source="forum", citation="https://forum.example/t/1",
                 retrieval="search_summary", read_on=NOW.date())
    assert R.stop_overdue(db, now=NOW + timedelta(days=2)) == []           # not due yet
    assert R.stop_overdue(db, now=NOW + timedelta(days=3, minutes=1)) == [tid]
    esc = R.escalations(db)[0]
    assert esc["task"] == tid and esc["smallest_action"] == SPEC["if_unresolved"]
    assert esc["remains_unknown"] and "listing.bundle_policy" in esc["why_it_matters"]
    searched = esc["searched"]
    assert searched["query_terms"] == ["bundle"] and searched["internal_hits"] >= 1
    assert searched["sources"][0]["retrieval"] == "search_summary"
    assert any(c["corpus"] == "lessons" for c in searched["internal_corpora"])
    assert R.tasks(db)[0]["state"] == R.STOPPED
    assert "not open" in _refused(lambda: R.stop(db, tid, why="x", remains_unknown="y"))


def test_f444_a_manual_stop_needs_what_remains_unknown():
    db = _db()
    tid = _open(db)["task"]
    assert "F-444" in _refused(lambda: R.stop(db, tid, why="page refused", remains_unknown=""))
    out = R.stop(db, tid, why="page refused", remains_unknown="the file-count rule",
                 smallest_action="owner pastes the help page text (10 minutes)")
    assert out["escalation"]["smallest_action"].startswith("owner pastes")


# ---- F-405 -------------------------------------------------------------------------------

def test_f405_every_internal_corpus_is_searched_first_and_absent_ones_are_named():
    db = _db()
    with db.session() as s:
        s.add(Incident(signature="listing:bundle-rejected", summary="Etsy refused a bundle "
                       "upload with 25 files", severity="P2"))
        s.add(Experiment(name="bundle-size", kind="price", hypothesis="smaller bundle sells "
                         "better"))
        s.add(Lesson(origin_cell="seo_search", subject="bundle", statement="bundle titles "
                     "should name the file count", evidence_ref="x"))
    from brambleloop.improve.failure_memory import FailureRecord

    with db.session() as s:
        s.add(FailureRecord(fingerprint="f" * 64, cell="seo_search", method="bundle of 30",
                            source="test", reason="bundle upload failed at 20 files"))
    (_DOCS / "DECISION_LOG.md").write_text("## D-9 bundle cap: we cap a bundle at 5 files\n")
    (_TESTS / "test_bundles.py").write_text("def test_bundle_cap_is_five():\n    pass\n")
    try:
        evidence, searched = R.search_internal_report(db, ["bundle"])
    finally:
        (_DOCS / "DECISION_LOG.md").unlink()
        (_TESTS / "test_bundles.py").unlink()
    kinds = {e["kind"] for e in evidence}
    assert {"incident", "experiment", "lesson", "prior_failure", "document", "test"} <= kinds
    by = {c["corpus"]: c for c in searched}
    for corpus in ("lessons", "learning_observations", "incidents", "experiments",
                   "registered_experiments", "failure_memory", "benchmark_listings",
                   "DECISION_LOG.md", "BUILD_STATE.md", "tests"):
        assert corpus in by, corpus
    assert by["BUILD_STATE.md"]["hits"] is None and "not present" in by["BUILD_STATE.md"]["why"]
    tid = _open(db)["task"]
    assert R.tasks(db)[0]["internal_evidence"] >= 3 and tid
    assert any(c["corpus"] == "incidents" and c["hits"] == 1
               for c in _row(db, tid).detail["searched_corpora"])


# ---- F-408 / F-426 -----------------------------------------------------------------------

def test_f408_a_consequential_fact_needs_two_independent_publishers():
    db = _db()
    tid = _open(db, consequential=True)["task"]
    R.add_source(db, tid, source="Etsy Help", citation="https://help.etsy.com/a/1",
                 retrieval="fetched", read_on=NOW.date())
    R.add_source(db, tid, source="Etsy Help again", citation="https://www.help.etsy.com/a/2",
                 retrieval="fetched", read_on=NOW.date())
    msg = _refused(lambda: R.add_finding(db, tid, statement="bundles cap at 20 files",
                                         claim_class="fact", rests_on=("S1", "S2")))
    assert "F-408" in msg and "help.etsy.com" in msg       # same publisher twice is one source
    R.add_source(db, tid, source="Etsy seller handbook", citation="https://www.etsy.com/h/3",
                 retrieval="fetched", read_on=NOW.date())
    assert R.add_finding(db, tid, statement="bundles cap at 20 files", claim_class="fact",
                         rests_on=("S1", "S3")) == "F1"
    ref = R.add_finding(db, tid, statement="the API takes at most 5 files per listing",
                        claim_class="fact", rests_on=("S2",),
                        single_source_reason="the API reference is the only primary text")
    assert ref == "F2"
    # A non-consequential task keeps the single-source rule it had.
    t2 = _open(db, trigger="t:other", question="Which colour names do buyers search for now?",
               domain="aesthetics", decision="palette.names")["task"]
    R.add_source(db, t2, source="Etsy", citation="https://etsy.com/x", retrieval="fetched",
                 read_on=NOW.date())
    assert R.add_finding(db, t2, statement="x", claim_class="fact", rests_on=("S1",)) == "F1"


def test_f426_a_conflict_blocks_the_answer_until_reconciled_or_unresolved():
    db = _db()
    tid = _open(db)["task"]
    R.add_source(db, tid, source="A", citation="https://a.example/1", retrieval="fetched",
                 read_on=NOW.date())
    R.add_source(db, tid, source="B", citation="https://b.example/1", retrieval="fetched",
                 read_on=NOW.date())
    R.add_finding(db, tid, statement="limit is 5 files", claim_class="fact", rests_on=("S1",))
    R.add_finding(db, tid, statement="limit is 20 files", claim_class="fact", rests_on=("S2",),
                  contradicts=("F1",))
    assert "does not hold" in _refused(lambda: R.add_finding(
        db, tid, statement="x", claim_class="hypothesis", contradicts=("F9",)))
    effect = {"kind": "constraint_established", "statement": "a cap exists"}
    conc = _empty(constraints=["a per-listing file cap exists"])
    msg = _refused(lambda: R.answer(db, tid, outcome="cap 20", effect=effect,
                                    conclusion=conc, now=NOW))
    assert "F-426" in msg and "F1" in msg and "F2" in msg
    assert "why" in _refused(lambda: R.reconcile(db, tid, kept="F2", rejected="F1", why=""))
    R.reconcile(db, tid, kept="F2", rejected="F1", why="S2 is dated after S1 and names it")
    out = R.answer(db, tid, outcome="cap 20", effect=effect, conclusion=conc, now=NOW)
    assert out["state"] == "answered"
    # The other honest exit: record the conflict unresolved.
    t2 = _open(db, trigger="t:2", question="Does the platform allow bundles of zip files?")["task"]
    R.add_source(db, t2, source="A", citation="https://a.example/2", retrieval="fetched",
                 read_on=NOW.date())
    R.add_finding(db, t2, statement="zip allowed", claim_class="fact", rests_on=("S1",))
    R.add_finding(db, t2, statement="zip refused", claim_class="source_claim",
                  rests_on=("S1",), contradicts=("F1",))
    R.add_finding(db, t2, statement="the two readings disagree", claim_class="unresolved",
                  rests_on=("F1", "F2"))
    assert R.answer(db, t2, outcome="open", now=NOW,
                    effect={"kind": "stop_justified", "statement": "sources disagree"},
                    conclusion=_empty())["conclusion"]["status"] == "unresolved"


# ---- F-420 / F-435 / F-411 ---------------------------------------------------------------

def test_f420_an_answer_must_change_something_and_cite_every_source():
    db = _db()
    tid = _open(db, prior_confidence="low")["task"]
    R.add_source(db, tid, source="Etsy", citation="https://etsy.com/p", retrieval="fetched",
                 read_on=NOW.date())
    R.add_source(db, tid, source="padding", citation="https://pad.example", retrieval="fetched",
                 read_on=NOW.date())
    R.add_finding(db, tid, statement="no cap is published", claim_class="fact",
                  rests_on=("S1",))
    assert "F-420" in _refused(lambda: R.answer(db, tid, outcome="x", conclusion=_empty(),
                                                now=NOW))
    msg = _refused(lambda: R.answer(db, tid, outcome="x", confidence="high", now=NOW,
                                    effect={"kind": "confidence_changed", "statement": "s"},
                                    conclusion=_empty()))
    assert "S2" in msg and "F-420" in msg and "rigorous" in msg   # uncited source
    R.add_finding(db, tid, statement="the second page repeats the first",
                  claim_class="source_claim", rests_on=("S2",))
    assert "prior" in _refused(lambda: R.answer(
        db, tid, outcome="x", confidence="low", now=NOW,
        effect={"kind": "confidence_changed", "statement": "s"}, conclusion=_empty()))
    assert "rejected" in _refused(lambda: R.answer(
        db, tid, outcome="x", confidence="high", now=NOW,
        effect={"kind": "alternatives_narrowed", "statement": "s"},
        conclusion=_empty(alternatives=[{"option": "cap at 5", "status": "kept"}])))
    out = R.answer(db, tid, outcome="no published cap", confidence="high", now=NOW,
                   effect={"kind": "confidence_changed", "statement": "low -> high"},
                   conclusion=_empty())
    assert out["state"] == "answered"


def test_f435_f412_the_conclusion_is_structured_and_the_next_test_bounded():
    db = _db()
    tid = _open(db)["task"]
    R.add_source(db, tid, source="Etsy", citation="https://etsy.com/p", retrieval="fetched",
                 read_on=NOW.date())
    R.add_finding(db, tid, statement="no cap is published", claim_class="fact",
                  rests_on=("S1",))
    R.add_finding(db, tid, statement="bundles of 5 convert better than 20",
                  claim_class="hypothesis")
    eff = {"kind": "hypothesis_produced", "statement": "a testable bundle-size hypothesis"}
    assert "F-435" in _refused(lambda: R.answer(db, tid, outcome="x", effect=eff,
                                                conclusion={"alternatives": []}, now=NOW))
    assert "falsif" in _refused(lambda: R.answer(db, tid, outcome="x", effect=eff, now=NOW,
                                                 conclusion=_empty(next_test={"what": "x"})))
    unbounded = {"what": "A/B two bundle sizes", "falsified_if": "no difference",
                 "max_days": 400, "max_spend_cad": 0}
    assert "bounded" in _refused(lambda: R.answer(db, tid, outcome="x", effect=eff, now=NOW,
                                                  conclusion=_empty(next_test=unbounded)))
    nt = dict(unbounded, max_days=14)
    out = R.answer(db, tid, outcome="hypothesis to test", effect=eff, now=NOW,
                   conclusion=_empty(next_test=nt, constraints=["no published cap"]))
    c = R.conclusion(db, tid)
    assert c == out["conclusion"]
    for field in R.CONCLUSION_FIELDS:
        assert field in c, field
    assert c["status"] == "answered" and c["next_test"]["max_days"] == 14
    assert {"F1", "F2", "S1"} <= set(c["evidence"]) and c["decision_ref"]


def test_f411_a_method_is_adopted_only_when_every_dimension_transfers():
    db = _db()
    tid = _open(db, kind=R.METHOD_ADOPTION, trigger="t:method", domain="mathematical",
                question="Does a knitting-simulation yarn model transfer to crochet charts?",
                decision="visual.chart_renderer")["task"]
    R.add_source(db, tid, source="paper", citation="https://arxiv.org/abs/1",
                 retrieval="fetched", read_on=NOW.date())
    R.add_finding(db, tid, statement="the model assumes interlocked loops in rows",
                  claim_class="fact", rests_on=("S1",))
    eff = {"kind": "constraint_established", "statement": "topology differs"}
    assert "F-411" in _refused(lambda: R.answer(db, tid, outcome="x", effect=eff, now=NOW,
                                                conclusion=_empty(constraints=["c"])))
    partial = {"assumptions": {"verdict": "transfers", "why": "w"}}
    assert "topology" in _refused(lambda: R.answer(
        db, tid, outcome="x", effect=eff, now=NOW,
        conclusion=_empty(constraints=["c"], applicability=partial)))
    app = {k: {"verdict": "transfers", "why": "checked"} for k in R.APPLICABILITY_DIMENSIONS}
    app["topology"] = {"verdict": "does_not_transfer",
                       "why": "crochet stitches are not knitted loops"}
    out = R.answer(db, tid, outcome="do not adopt", effect=eff, now=NOW,
                   conclusion=_empty(constraints=["crochet topology"], applicability=app))
    assert out["conclusion"]["adopt"] is False
    assert R.metrics(db)["experiments_prevented"] == 1


# ---- F-432 / F-449 -----------------------------------------------------------------------

def _answered(db, **kw):
    tid = _open(db, **kw)["task"]
    R.add_finding(db, tid, statement="nothing readable", claim_class="unresolved")
    R.answer(db, tid, outcome="unresolved", now=NOW,
             effect={"kind": "stop_justified", "statement": "page refused"},
             conclusion=_empty())
    return tid


def test_f432_an_equivalent_answered_question_is_reused_and_reopens_only_for_a_reason():
    db = _db()
    tid = _answered(db)
    # Same content words, reordered and re-phrased: a materially equivalent premise.
    again = _open(db, trigger="t:different-trigger",
                  question="Pattern bundle: does the platform limit how many files it holds?")
    assert again["opened"] is False and again["reused"] is True and again["task"] == tid
    assert again["conclusion"]["status"] == "unresolved"
    other = _open(db, trigger="t:x", question="How many files does the platform limit a "
                  "pattern bundle to?", decision="listing.other_decision")
    assert other["opened"] is True                       # a different decision is a new premise
    assert "F-432" in _refused(lambda: _open(db, trigger="t:y", reopen_because={
        "reason": "boredom", "note": "x"}))
    re = _open(db, trigger="t:y", reopen_because={"reason": "new_evidence",
                                                  "note": "Etsy published a new help page"})
    assert re["opened"] is True and re["reopens"] == tid
    # Stale (expired) answers are not reused: marketplace_policy is fresh for 21 days.
    db2 = _db()
    t0 = _answered(db2)
    with db2.session() as s:
        s.get(R.ResearchTask, t0).expires_on = NOW - timedelta(days=1)
    assert _open(db2, trigger="t:z")["opened"] is True


def test_f449_metrics_are_measured_or_none_never_a_default_zero():
    db = _db()
    m = R.metrics(db)
    assert m["tasks"] == 0 and m["reuse_rate"] is None and m["source_quality"] is None
    tid = _answered(db)
    _open(db, trigger="t:dup")                          # reused (equivalent question)
    t2 = _open(db, trigger="t:open", question="Which yarn weights do buyers filter by now?",
               domain="techniques", decision="listing.attributes")["task"]
    _open(db, trigger="t:open", question="Which yarn weights do buyers filter by now?",
          domain="techniques", decision="listing.attributes")          # duplicate ask
    R.add_source(db, t2, source="Etsy", citation="https://etsy.com/f", retrieval="fetched",
                 read_on=NOW.date())
    R.add_source(db, t2, source="blog", citation="https://b.example", retrieval="search_summary",
                 read_on=NOW.date())
    m = R.metrics(db)
    assert m["tasks"] == 2 and m["resolved"] == 1 and m["duplicates_avoided"] == 2
    assert m["reuse_rate"] == round(1 / 4, 4) and m["source_quality"] == 0.5
    assert m["experiments_prevented"] == 1 and m["decisions_changed"] == 0
    assert m["stale_refreshed"] is None and "definitions" in m and tid


def test_learn_scan_enforces_the_time_bound():
    from brambleloop.agents.registry import Registry
    from brambleloop.learn import runtime  # noqa: F401 - registers learn.scan
    from brambleloop.queue.durable import JobQueue
    from brambleloop.runtime.worker import Worker

    db = _db()
    Registry(db).seed_defaults()
    past = datetime.now(timezone.utc) - timedelta(days=10)
    tid = R.open_question(db, question="Does the platform limit how many files a bundle "
                          "holds?", trigger="t:overdue", decision_ref="listing.bundle_policy",
                          domain="marketplace_policy", query_terms=("bundle",),
                          time_bound_days=2, now=past, **SPEC)["task"]
    JobQueue(db).enqueue("learn", "learn.scan", {})
    Worker(db, job_types=["learn.scan"]).run_once()
    assert _row(db, tid).state == R.STOPPED
    assert any(e["task"] == tid for e in R.escalations(db))


def test_f412_a_hypothesis_becomes_the_smallest_bounded_experiment_once():
    from brambleloop.core.models import Improvement

    db = _db()
    tid = _open(db)["task"]
    R.add_source(db, tid, source="Etsy", citation="https://etsy.com/p", retrieval="fetched",
                 read_on=NOW.date())
    R.add_finding(db, tid, statement="no cap is published", claim_class="fact",
                  rests_on=("S1",))
    R.add_finding(db, tid, statement="bundles of five files convert better than twenty",
                  claim_class="hypothesis")
    assert "only an answered" in _refused(lambda: R.bridge(db, tid, cell="pricing",
                                                         rollback_ref="none needed"))
    nt = {"what": "list one product as a 5-file and a 20-file bundle for two weeks",
          "falsified_if": "conversion is equal within noise", "max_days": 14,
          "max_spend_cad": 0}
    R.answer(db, tid, outcome="test it", now=NOW,
             effect={"kind": "hypothesis_produced", "statement": "bundle size hypothesis"},
             conclusion=_empty(next_test=nt))
    out = R.bridge(db, tid, cell="pricing", rollback_ref="restore the single-bundle listing")
    assert out["bridged"] is True
    with db.session() as s:
        imp = s.get(Improvement, out["improvement"])
        assert imp.state == "proposed" and imp.cell == "pricing"
        assert "falsified if conversion is equal" in imp.hypothesis
        assert "at most 14 days" in imp.hypothesis and imp.rollback_ref
    again = R.bridge(db, tid, cell="pricing", rollback_ref="x")
    assert again["bridged"] is False and again["improvement"] == out["improvement"]
    # A method that did not transfer has nothing to test.
    t2 = _open(db, kind=R.METHOD_ADOPTION, trigger="t:m2", domain="mathematical",
               question="Does a knitting yarn model transfer to crochet chart rendering?",
               decision="visual.renderer")["task"]
    R.add_source(db, t2, source="paper", citation="https://arxiv.org/abs/2",
                 retrieval="fetched", read_on=NOW.date())
    R.add_finding(db, t2, statement="assumes knitted loops", claim_class="fact",
                  rests_on=("S1",))
    app = {k: {"verdict": "does_not_transfer", "why": "topology"}
           for k in R.APPLICABILITY_DIMENSIONS}
    R.answer(db, t2, outcome="no", now=NOW,
             effect={"kind": "constraint_established", "statement": "topology differs"},
             conclusion=_empty(constraints=["crochet topology"], applicability=app))
    assert "did not transfer" in _refused(lambda: R.bridge(db, t2, cell="pricing",
                                                          rollback_ref="x"))


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print("OK  ", t.__name__)
        except Exception as exc:  # noqa: BLE001
            failed += 1
            import traceback
            traceback.print_exc()
            print("FAIL", t.__name__, exc)
    print(f"{len(tests) - failed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
