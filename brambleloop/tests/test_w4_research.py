"""W4-RESEARCH: research tasks, unknown detection, claim classes, reproducibility, expiry.

Rows: F-403, F-409, F-424, F-431, F-433.
Run: cd brambleloop && PYTHONPATH=src:tests .venv/bin/python tests/test_w4_research.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
_TMP = tempfile.mkdtemp(prefix="w4_research_")

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import Lesson  # noqa: E402
from brambleloop.intel import childrens, learning, research  # noqa: E402

NOW = datetime(2026, 10, 12, 12, tzinfo=timezone.utc)
_n = [0]


def _db() -> Database:
    _n[0] += 1
    db = Database(f"sqlite:///{_TMP}/d{_n[0]}.sqlite")
    db.create_all()
    return db


def _refused(fn) -> str:
    try:
        fn()
    except (research.ResearchRefused, learning.LearningRefused) as exc:
        return str(exc)
    raise AssertionError("expected a refusal")


# W4-FMBATCH1 (F-405): the internal search now also reads the repository's BUILD_STATE /
# DECISION_LOG and the test names. Point them at an empty fixture so these counts measure
# the lessons/observations this file writes, not whatever the repository says today.
_EMPTY = Path(_TMP) / "no-docs"
_EMPTY.mkdir(exist_ok=True)
research.DOCUMENTS = {name: _EMPTY / name for name in research.DOCUMENTS}
research.TESTS_DIR = _EMPTY

# W4-FMBATCH1 (F-419/F-444/F-420/F-435): a task defines its evidence, stop condition and
# fallback action, and an answer states its effect and a structured conclusion.
_SPEC = {"stop_condition": "the policy page read in full",
         "evidence_needed": "the platform's published file-count rule",
         "if_unresolved": "owner reads the policy page and records it"}


def _closed(**kw):
    return {"effect": kw.pop("effect", {"kind": "stop_justified",
                                         "statement": "no primary text could be read"}),
            "conclusion": {"alternatives": [], "constraints": [], "unresolved": [],
                           "next_test": None, "applicability": None}}


def _task(db, domain="marketplace_policy", **kw):
    for k, v in _SPEC.items():
        kw.setdefault(k, v)
    return research.open_question(
        db, question="Does the platform allow pattern bundles of more than ten files?",
        trigger=kw.pop("trigger", "test:bundles"), decision_ref="listing.bundle_policy",
        domain=domain, query_terms=kw.pop("query_terms", ("bundle", "files")), now=NOW, **kw)


def test_unknowns_on_decision_paths_open_research_questions_once():
    db = _db()
    out = research.detect_unknowns(db, today=NOW.date(), now=NOW)
    n_domains = len(learning.DOMAINS)  # nothing observed: every domain is an unknown
    n_unfetched = len(childrens.unfetched_sources())
    assert n_unfetched > 0, "fixture: the children's module should name unfetched pages"
    assert len(out["opened"]) == n_domains + n_unfetched, out
    again = research.detect_unknowns(db, today=NOW.date(), now=NOW)
    assert again["opened"] == [] and len(again["already_open"]) == n_domains + n_unfetched
    rows = research.tasks(db)
    assert all(r["decision_ref"] and r["query_terms"] and r["stop_condition"] for r in rows)
    assert {r["trigger"].split(":")[0] for r in rows} == {"learning.unobserved",
                                                          "childrens.unfetched"}


def test_an_observed_domain_is_no_longer_an_unknown():
    db = _db()
    learning.record(db, domain="techniques", source="blog", citation="https://x.example/a",
                    summary="tunisian crochet is being taught again in several new books",
                    observed_on=NOW.date() - timedelta(days=3))
    out = research.detect_unknowns(db, today=NOW.date(), now=NOW)
    triggers = {r["trigger"] for r in research.tasks(db)}
    assert "learning.unobserved:techniques" not in triggers
    assert len(out["opened"]) == len(learning.DOMAINS) - 1 + len(childrens.unfetched_sources())


def test_internal_evidence_is_searched_first():
    db = _db()
    with db.session() as s:
        s.add(Lesson(origin_cell="seo_search", subject="bundle titles",
                     statement="bundle listings with 12 files converted worse in our test",
                     evidence_ref="experiments:4"))
    r = _task(db, query_terms=("bundle",))
    t = research.tasks(db)[0]
    assert r["internal_evidence"] == 1 and t["internal_evidence"] == 1


def test_claim_classes_are_enforced():
    db = _db()
    tid = _task(db)["task"]
    research.add_source(db, tid, source="etsy help", citation="https://help.etsy.com/x",
                        retrieval="search_summary", read_on=NOW.date())
    assert "search summary" in _refused(lambda: research.add_finding(
        db, tid, statement="bundles over ten files are prohibited", claim_class="fact",
        rests_on=("S1",)))
    assert research.add_finding(db, tid, statement="the help page snippet says bundles are "
                                "limited", claim_class="source_claim", rests_on=("S1",)) == "F1"
    assert "names what it rests on" in _refused(lambda: research.add_finding(
        db, tid, statement="so bundles are risky", claim_class="inference"))
    assert research.add_finding(db, tid, statement="so large bundles are a listing risk",
                                claim_class="inference", rests_on=("F1",)) == "F2"
    assert "does not hold" in _refused(lambda: research.add_finding(
        db, tid, statement="x", claim_class="source_claim", rests_on=("S9",)))
    assert "F-409" in _refused(lambda: research.add_finding(
        db, tid, statement="x", claim_class="opinion"))
    research.add_source(db, tid, source="etsy policy page", citation="https://etsy.com/p",
                        retrieval="fetched", read_on=NOW.date())
    assert research.add_finding(db, tid, statement="the policy page sets no file count limit",
                                claim_class="fact", rests_on=("S2",)) == "F3"


def test_claims_and_guesses_cannot_close_a_task():
    db = _db()
    tid = _task(db)["task"]
    research.add_finding(db, tid, statement="bundles may convert better", claim_class="hypothesis")
    assert "unresolved" in _refused(lambda: research.answer(db, tid, outcome="done", now=NOW))
    research.add_finding(db, tid, statement="no primary text could be read",
                         claim_class="unresolved")
    assert research.answer(db, tid, outcome="open: page refused", now=NOW, **_closed())["state"] == "answered"


def test_answers_expire_by_their_domain_and_mathematical_never_does():
    db = _db()
    tid = _task(db, domain="marketplace_policy")["task"]
    research.add_finding(db, tid, statement="unresolved for now", claim_class="unresolved")
    out = research.answer(db, tid, outcome="x", now=NOW, **_closed())
    assert out["expires_on"] == (NOW + timedelta(days=21)).isoformat(), out
    t2 = _task(db, domain="mathematical", trigger="test:maths")["task"]
    research.add_finding(db, t2, statement="unresolved", claim_class="unresolved")
    assert research.answer(db, t2, outcome="x", now=NOW, **_closed())["expires_on"] is None
    t3 = _task(db, domain="pricing", trigger="test:pricing")["task"]  # an improvement cell
    research.add_finding(db, t3, statement="unresolved", claim_class="unresolved")
    assert research.answer(db, t3, outcome="x", now=NOW, **_closed())["expires_on"] == (
        NOW + timedelta(days=3)).isoformat()
    assert "freshness" in _refused(lambda: _task(db, domain="vibes", trigger="test:v"))
    assert research.expire_due(db, now=NOW + timedelta(days=2)) == []  # nothing due yet
    reopened = research.expire_due(db, now=NOW + timedelta(days=22))
    assert sorted(reopened) == sorted([tid, t3])  # 21-day policy and 3-day market expired
    states = {r["id"]: r["state"] for r in research.tasks(db)}
    assert states[tid] == "expired" and states[t3] == "expired" and states[t2] == "answered"
    assert list(states.values()).count("open") == 2  # each expired question re-opened once
    assert research.expire_due(db, now=NOW + timedelta(days=23)) == []


def test_tasks_need_a_decision_and_spend_nothing_by_default():
    db = _db()
    assert "decision" in _refused(lambda: research.open_question(
        db, question="What do buyers think about pastel colours now?", trigger="t",
        decision_ref="", domain="aesthetics"))
    tid = _task(db)["task"]
    assert research.tasks(db)[0]["spend_bound_cad"] == 0.0 and tid


def test_learning_observations_carry_class_terms_and_decision():
    db = _db()
    learning.record(db, domain="aesthetics", source="trend report", citation="https://t.example",
                    summary="sage green palettes keep appearing in nursery listings this season",
                    observed_on=NOW.date(), query_terms=("sage green", "nursery"),
                    decision_ref="product.palette:baby-blanket")
    o = learning.observations(db, today=NOW.date())[0]
    assert o["claim_class"] == "source_claim" and o["query_terms"] == ["sage green", "nursery"]
    assert o["decision_ref"] == "product.palette:baby-blanket"
    assert "claim_class" in _refused(lambda: learning.record(
        db, domain="aesthetics", source="s", citation="c",
        summary="a summary long enough to be an observation here", observed_on=NOW.date(),
        claim_class="gospel"))


def test_learn_scan_routes_unknowns():
    from brambleloop.learn import runtime  # noqa: F401 - registers learn.scan
    from brambleloop.queue.durable import JobQueue
    from brambleloop.runtime.worker import Worker

    db = _db()
    Registry(db).seed_defaults()
    JobQueue(db).enqueue("learn", "learn.scan", {})
    Worker(db, job_types=["learn.scan"]).run_once()
    assert research.tasks(db, state="open"), "learn.scan opened no research question"


def test_research_tasks_are_a_non_rederivable_record():
    from brambleloop.core import continuity

    assert "research_tasks" in continuity.NON_REDERIVABLE


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
