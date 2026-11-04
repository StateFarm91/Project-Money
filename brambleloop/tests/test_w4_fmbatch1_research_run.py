"""W4-FMBATCH1: F-431 Durable Knowledge Promotion -- the research run (fetch + promotion).

F-431: "Validated research findings become structured durable knowledge, regression tests,
capability metadata, architecture notes or decision records so later agents reuse them."
CLOSE5: the research run and the fetch step were missing. Every HTTP answer here is a stub;
sockets are refused for the whole file, so no test can reach the network.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import socket
import sys
import tempfile
import pytest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
_TMP = tempfile.mkdtemp(prefix="fmb1_rrun_")


def _no_network(*_a, **_k):
    raise OSError("network refused by this test")


socket.socket.connect = _no_network  # type: ignore[assignment]
socket.create_connection = _no_network  # type: ignore[assignment]

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog, Lesson  # noqa: E402
from brambleloop.intel import childrens, research as R, research_fetch as F  # noqa: E402

NOW = datetime(2026, 10, 26, 12, tzinfo=timezone.utc)
_n = [0]
SPEC = {"stop_condition": "the page read", "evidence_needed": "the primary text",
        "if_unresolved": "a person reads the page"}


def _db():
    _n[0] += 1
    db = Database(f"sqlite:///{_TMP}/r{_n[0]}.sqlite")
    db.create_all()
    return db


class Stub:
    """Recorded answers by URL; anything unrecorded is a 404. Logs every request."""

    def __init__(self, pages: dict, robots: str | None = "User-agent: *\nAllow: /\n"):
        self.pages, self.robots, self.calls = pages, robots, []

    def __call__(self, url, **_kw):
        self.calls.append(url)
        if url.endswith("/robots.txt"):
            return (200, self.robots.encode()) if self.robots is not None else (503, b"")
        if url in self.pages:
            return 200, self.pages[url].encode()
        return 404, b""


def _no_sleep(_s):
    return None


def test_only_allowlisted_https_urls_without_credentials_are_fetchable():
    assert F.check_url("https://www.cpsc.gov/Business--Manufacturing") == "www.cpsc.gov"
    for bad, why in (("http://www.cpsc.gov/x", "https"),
                     ("https://www.etsy.com/legal/policy", "allowlist"),
                     ("https://user:pw@www.cpsc.gov/x", "credentials"),
                     ("https://www.cpsc.gov/x?api_key=abc", "secret")):
        try:
            F.check_url(bad)
        except F.FetchRefused as exc:
            assert why in str(exc), (bad, exc)
        else:
            raise AssertionError(f"{bad} was not refused")
    paid = {"api.openai.com", "api.anthropic.com", "api.bfl.ai", "fal.run"}
    assert not paid & set(F.ALLOWED_HOSTS)


def test_robots_is_obeyed_and_unreadable_robots_is_a_refusal():
    db = _db()
    tid = R.open_question(db, question="What does the CPSC rule on crib mobiles say?",
                          trigger="t:cpsc", decision_ref="intel.childrens.constraints",
                          domain="marketplace_policy", now=NOW, **SPEC)["task"]
    url = "https://www.cpsc.gov/rule"
    deny = Stub({url: "x" * 100}, robots="User-agent: *\nDisallow: /\n")
    out = F.fetch_for_task(db, tid, url, get=deny, now=NOW, sleep=_no_sleep)
    assert out["fetched"] is False and "disallows" in out["why"]
    assert deny.calls == ["https://www.cpsc.gov/robots.txt"]          # the page was not asked
    down = Stub({url: "x"}, robots=None)
    out = F.fetch_for_task(db, tid, url, get=down, now=NOW, sleep=_no_sleep)
    assert out["fetched"] is False and "unreadable" in out["why"]
    ok = Stub({url: "<html>Crib mobiles must ...</html>"})
    out = F.fetch_for_task(db, tid, url, get=ok, now=NOW, sleep=_no_sleep)
    assert out["fetched"] is True and out["source_ref"] == "S1" and out["spend_cad"] == 0.0
    src = R.tasks(db)[0]["sources"][0]
    assert src["retrieval"] == "fetched" and src["citation"] == url
    with db.session() as s:
        assert s.query(AuditLog).filter(AuditLog.action == F.FETCH_ACTION).count() == 3


def test_the_run_plans_allowlisted_childrens_sources_and_is_off_unless_switched_on():
    db = _db()
    R.detect_unknowns(db, today=NOW.date(), now=NOW)
    planned = F.plan_fetches(db)
    hosts = {F.check_url(u) for _t, u in planned}
    assert planned and hosts <= set(F.ALLOWED_HOSTS)
    assert "www.etsy.com" not in hosts and "publications.aap.org" not in hosts
    off = F.run(db, now=NOW, env={})
    assert off["fetches"]["enabled"] is False and "not 1" in off["fetches"]["why"]
    pages = {u: f"<html>{u}</html>" for _t, u in planned}
    stub = Stub(pages)
    on = F.run(db, get=stub, now=NOW, sleep=_no_sleep)
    assert on["fetches"]["enabled"] is True
    assert all(r["fetched"] for r in on["fetches"]["results"]), on
    assert len(on["fetches"]["results"]) == min(len(planned), F.MAX_FETCHES_PER_RUN)
    again = F.plan_fetches(db)                 # fetched sources are not planned again
    assert len(again) == len(planned) - len(on["fetches"]["results"])


def _answered(db, domain="marketplace_policy"):
    tid = R.open_question(db, question="What does the CPSC rule on crib mobiles require?",
                          trigger=f"t:{domain}", decision_ref="intel.childrens.constraints",
                          domain=domain, now=NOW, **SPEC)["task"]
    url = "https://www.cpsc.gov/rule"
    F.fetch_for_task(db, tid, url, get=Stub({url: "rule text"}), now=NOW, sleep=_no_sleep)
    R.add_finding(db, tid, statement="mobiles must not be reachable by the infant",
                  claim_class="fact", rests_on=("S1",))
    R.answer(db, tid, outcome="a reach rule applies", confidence="high", now=NOW,
             effect={"kind": "constraint_established", "statement": "reach rule"},
             conclusion={"alternatives": [], "constraints": ["out of reach"],
                         "unresolved": [], "next_test": None, "applicability": None})
    return tid


def test_an_answered_fact_becomes_a_routed_lesson_once_and_is_withdrawn_on_expiry():
    db = _db()
    tid = _answered(db)
    out = F.promote(db)
    assert len(out["promoted"]) == 1
    with db.session() as s:
        lesson = s.get(Lesson, out["promoted"][0])
        assert lesson.subject == "platform_policy" and lesson.evidence_ref == f"research_tasks:{tid}"
        assert "seo_search" in (lesson.routed_to or [])
    assert F.promote(db)["promoted"] == []                  # idempotent
    R.expire_due(db, now=NOW + timedelta(days=30))           # marketplace_policy: 21 days
    gone = F.promote(db)
    assert gone["withdrawn"] == out["promoted"], gone


@pytest.mark.parametrize("after_create", [False, True])
def test_learn_worker_recovers_interrupted_expiry_reopen(monkeypatch, after_create):
    from brambleloop.agents.registry import Registry
    from brambleloop.core.models import Job, JobStatus
    from brambleloop.learn import runtime  # noqa: F401 - registers learn.scan
    from brambleloop.queue.durable import JobQueue
    from brambleloop.runtime.worker import Worker

    db = _db()
    Registry(db).seed_defaults()
    tid = _answered(db)
    with db.session() as s:
        source = s.get(R.ResearchTask, tid)
        source.expires_on = datetime.now(timezone.utc) - timedelta(days=1)
        reopen_key = R._key(f"{source.trigger}#after:{tid}")
    real_open = R.open_question

    def interrupted(*args, **kwargs):
        if kwargs.get("trigger", "").endswith(f"#after:{tid}"):
            if after_create:
                real_open(*args, **kwargs)
            raise RuntimeError("fixture interruption during expiry handoff")
        return real_open(*args, **kwargs)

    monkeypatch.setattr(R, "open_question", interrupted)
    q = JobQueue(db)
    first = q.enqueue("learn", "learn.scan", {}, idempotency_key="expiry-interrupted")
    assert Worker(db, "expiry-interrupted", job_types=["learn.scan"]).run_once()
    with db.session() as s:
        assert s.get(Job, first.id).status == JobStatus.DONE
        assert s.get(Job, first.id).outputs["research"].get("error")
        assert s.get(R.ResearchTask, tid).state == R.EXPIRED
    monkeypatch.setattr(R, "open_question", real_open)
    second = q.enqueue("learn", "learn.scan", {}, idempotency_key="expiry-restart")
    assert Worker(db, "expiry-restart", job_types=["learn.scan"]).run_once()
    with db.session() as s:
        assert s.get(Job, second.id).status == JobStatus.DONE
        assert not s.get(Job, second.id).outputs["research"].get("error")
        matches = list(s.scalars(R.select(R.ResearchTask).where(
            R.ResearchTask.dedupe_key == reopen_key)))
        assert len(matches) == 1
        assert s.get(R.ResearchTask, tid).detail["expiry_reopen_task"] == matches[0].id


@pytest.mark.parametrize("conflict", ["foreign_key", "invalid_marker"])
def test_expiry_recovery_holds_conflicting_replacement_identity(conflict):
    db = _db()
    tid = _answered(db)
    with db.session() as s:
        source = s.get(R.ResearchTask, tid)
        source.state = R.EXPIRED
        if conflict == "invalid_marker":
            source.detail = {**source.detail, "expiry_reopen_task": 999999}
        else:
            trigger = f"{source.trigger}#after:{tid}"
            s.add(R.ResearchTask(question="This is a different unrelated research question",
                                 trigger=trigger, dedupe_key=R._key(trigger),
                                 decision_ref="foreign", domain=source.domain, state=R.OPEN))
    assert R.expire_due(db, now=NOW + timedelta(days=30)) == []
    with db.session() as s:
        source = s.get(R.ResearchTask, tid)
        assert "conflicts" in source.detail["expiry_reopen_hold"]
        if conflict == "foreign_key":
            assert not source.detail.get("expiry_reopen_task")


@pytest.mark.parametrize("invalid", ["time_bound", "question", "stop_condition", "terms"])
def test_learn_worker_reopens_valid_expiry_despite_malformed_neighbor(invalid):
    from brambleloop.agents.registry import Registry
    from brambleloop.core.models import Job, JobStatus
    from brambleloop.learn import runtime  # noqa: F401
    from brambleloop.queue.durable import JobQueue
    from brambleloop.runtime.worker import Worker

    db = _db()
    Registry(db).seed_defaults()
    bad = _answered(db, domain="marketplace_policy")
    good = _answered(db, domain="techniques")
    with db.session() as s:
        bad_row = s.get(R.ResearchTask, bad)
        good_row = s.get(R.ResearchTask, good)
        bad_row.expires_on = good_row.expires_on = datetime.now(timezone.utc) - timedelta(days=1)
        if invalid == "time_bound":
            bad_row.detail = {**bad_row.detail, "time_bound_days": "not-a-number"}
        elif invalid == "question":
            bad_row.question = "invalid"
        elif invalid == "stop_condition":
            bad_row.detail = {**bad_row.detail, "if_unresolved": ["not", "text"]}
        else:
            bad_row.query_terms = 0
        good_key = R._key(f"{good_row.trigger}#after:{good}")
    job = JobQueue(db).enqueue("learn", "learn.scan", {}, idempotency_key=f"expiry-isolate-{invalid}")
    assert Worker(db, "expiry-isolate", job_types=["learn.scan"]).run_once()
    with db.session() as s:
        done = s.get(Job, job.id)
        assert done.status == JobStatus.DONE, done.last_error
        assert not done.outputs["research"].get("error")
        assert s.get(R.ResearchTask, bad).detail["expiry_reopen_hold"] == "invalid expired task metadata"
        replacements = list(s.scalars(R.select(R.ResearchTask).where(
            R.ResearchTask.dedupe_key == good_key)))
        assert len(replacements) == 1
        assert s.get(R.ResearchTask, good).detail["expiry_reopen_task"] == replacements[0].id


def test_learn_worker_withdraws_orphan_lesson_after_restart(monkeypatch):
    from brambleloop.agents.registry import Registry
    from brambleloop.core.models import Job, JobStatus
    from brambleloop.queue.durable import JobQueue
    from brambleloop.runtime.worker import Worker
    from brambleloop.learn import runtime  # noqa: F401 - registers learn.scan
    from brambleloop.learn import metrics

    db = _db()
    Registry(db).seed_defaults()
    tid = _answered(db)
    original = F._set

    def interrupted(db_, task, **values):
        if "promoted_lesson" in values:
            raise RuntimeError("fixture interruption after lesson publication")
        return original(db_, task, **values)

    monkeypatch.setattr(F, "_set", interrupted)
    with pytest.raises(RuntimeError):
        F.promote(db, now=NOW)
    monkeypatch.setattr(F, "_set", original)
    with db.session() as s:
        task = s.get(R.ResearchTask, tid)
        assert not (task.detail or {}).get("promoted_lesson")
        task.expires_on = datetime.now(timezone.utc) - timedelta(days=1)
        lesson = s.scalar(R.select(Lesson).where(Lesson.evidence_ref == f"research_tasks:{tid}"))
        lid = lesson.id
        assert lesson.withdrawn_at is None
    checked = []

    def calendar_after_withdrawal(db_, *, metrics):
        with db_.session() as s:
            assert s.get(Lesson, lid).withdrawn_at is not None
        checked.append(True)
        return {"_moves": []}

    monkeypatch.setattr(metrics, "calendar", calendar_after_withdrawal)
    job = JobQueue(db).enqueue("learn", "learn.scan", {}, idempotency_key="lesson-restart")
    assert Worker(db, "lesson-recovery", job_types=["learn.scan"]).run_once()
    with db.session() as s:
        done = s.get(Job, job.id)
        assert done.status == JobStatus.DONE, done.last_error
        assert not done.outputs["research"].get("error")
        assert s.get(Lesson, lid).withdrawn_at is not None
        assert s.get(R.ResearchTask, tid).detail["promoted_lesson"] == lid
    assert checked
    assert F.promote(db)["withdrawn"] == []


@pytest.mark.parametrize("conflict", ["statement", "subject"])
def test_learn_worker_holds_calendar_when_lesson_provenance_conflicts(monkeypatch, conflict):
    from brambleloop.agents.registry import Registry
    from brambleloop.core.models import Job, JobStatus
    from brambleloop.learn import metrics, runtime  # noqa: F401
    from brambleloop.queue.durable import JobQueue
    from brambleloop.runtime.worker import Worker

    db = _db()
    Registry(db).seed_defaults()
    tid = _answered(db)
    out = F.promote(db, now=NOW)
    with db.session() as s:
        lesson = s.get(Lesson, out["promoted"][0])
        if conflict == "statement":
            lesson.statement = "a conflicting historical statement"
        else:
            lesson.subject = "palette"
    def unexpected_calendar(*_args, **_kwargs):
        raise AssertionError("calendar must hold on ambiguous lesson provenance")
    monkeypatch.setattr(metrics, "calendar", unexpected_calendar)
    job = JobQueue(db).enqueue("learn", "learn.scan", {}, idempotency_key="conflicting-lesson")
    assert Worker(db, "lesson-hold", job_types=["learn.scan"]).run_once()
    with db.session() as s:
        done = s.get(Job, job.id)
        assert done.status == JobStatus.DONE, done.last_error
        assert done.outputs["research_lesson_maintenance"]["held"][0]["task"] == tid
        assert done.outputs["lesson_moves"] == []


def test_radar_worker_stops_using_research_lesson_when_its_source_expires():
    from brambleloop.agents.registry import Registry
    from brambleloop.core.models import Job, JobStatus
    from brambleloop.queue.durable import JobQueue
    from brambleloop.runtime import pipeline  # noqa: F401 - register handler
    from brambleloop.runtime.worker import Worker

    db = _db()
    Registry(db).seed_defaults()
    tid = _answered(db, domain="techniques")
    with db.session() as s:
        s.get(R.ResearchTask, tid).outcome = "chunky ribbed scarf construction evidence"
    lid = F.promote(db)["promoted"][0]
    q = JobQueue(db)

    def score(key):
        job = q.enqueue("market_radar", "radar.score", {"slug": "chunky-ribbed-scarf"},
                        idempotency_key=key)
        assert Worker(db, key, job_types=["radar.score"]).run_once()
        with db.session() as s:
            row = s.get(Job, job.id)
            assert row.status == JobStatus.DONE, row.last_error
            return dict(row.outputs)

    assert score("research-lesson-current")["lesson_adjustment"] > 0
    with db.session() as s:
        s.get(R.ResearchTask, tid).expires_on = datetime.now(timezone.utc) - timedelta(seconds=1)
        assert s.get(Lesson, lid).withdrawn_at is None
    assert score("research-lesson-expired")["lesson_adjustment"] == 0


@pytest.mark.parametrize("failure", ["missing_task", "missing_pointer", "changed_statement",
                                    "stopped_task", "changed_finding"])
def test_research_inbox_holds_unbound_lessons_without_blocking_other_lessons(failure):
    from brambleloop.improve import bus

    db = _db()
    tid = _answered(db, domain="techniques")
    lid = F.promote(db)["promoted"][0]
    other = bus.publish(db, origin_cell="learn", subject="construction_preference",
                        statement="Fixture ordinary construction guidance remains available here",
                        evidence_ref="fixture:other")
    assert {lid, other} <= {r["id"] for r in bus.inbox(db, "market_radar")}
    with db.session() as s:
        task = s.get(R.ResearchTask, tid)
        if failure == "missing_task":
            s.delete(task)
        elif failure == "missing_pointer":
            task.detail = {**task.detail, "promoted_lesson": None}
        elif failure == "changed_statement":
            s.get(Lesson, lid).statement = "a modified research lesson statement"
        elif failure == "stopped_task":
            task.state = R.STOPPED
        else:
            task.findings = [{**f, "statement": "changed source finding"} for f in task.findings]
    ids = {r["id"] for r in bus.inbox(db, "market_radar")}
    assert lid not in ids and other in ids


def test_a_domain_with_no_subject_is_reported_not_forced():
    db = _db()
    _answered(db, domain="competitor_positioning")
    out = F.promote(db)
    assert out["promoted"] == [] and out["unrouted"][0]["domain"] == "competitor_positioning"


# ---- independent review F-2 / F-8 ----------------------------------------------------------

def test_review_f2_redirects_off_the_allowlist_or_to_http_are_refused():
    import urllib.request

    h = F._redirect_handler()
    req = urllib.request.Request("https://www.cpsc.gov/a")
    for bad in ("https://evil.example/x", "http://www.cpsc.gov/a",
                "http://169.254.169.254/latest/meta-data", "https://www.cpsc.gov:8443/a"):
        try:
            h.redirect_request(req, None, 302, "Found", {}, bad)
            raise AssertionError(f"redirect to {bad} was followed")
        except F.FetchRefused:
            pass
    ok = h.redirect_request(req, None, 302, "Found", {}, "https://www.cpsc.gov/b")
    assert ok is not None and ok.full_url == "https://www.cpsc.gov/b"


def test_review_f2_a_refused_redirect_is_recorded_not_stored():
    db = _db()
    tid = R.open_question(db, question="What does the CPSC rule on crib mobiles require?",
                          trigger="t:marketplace_policy", decision_ref="x",
                          domain="marketplace_policy", now=NOW, **SPEC)["task"]
    url = "https://www.cpsc.gov/rule"

    def get(u):
        if u.endswith("/robots.txt"):
            return 404, b""
        raise F.FetchRefused("'evil.example' is not on the research allowlist")

    out = F.fetch_for_task(db, tid, url, get=get, now=NOW, sleep=_no_sleep)
    assert out["fetched"] is False and "redirect refused" in out["why"]
    assert R.tasks(db)[0]["sources"] == []
    with db.session() as s:
        assert s.query(AuditLog).filter(AuditLog.action == F.FETCH_ACTION).count() == 1


def test_review_f2_non_default_port_and_oversized_robots_are_refused():
    try:
        F.check_url("https://en.wikipedia.org:8443/wiki/X")
        raise AssertionError("a non-default port was allowed")
    except F.FetchRefused:
        pass
    big = b"User-agent: *\nAllow: /\n" + b"#" * (F.MAX_BYTES + 10)
    ok, why = F.robots_allows("https://www.cpsc.gov/a", get=lambda u: (200, big))
    assert ok is False and "byte cap" in why


def test_review_f8_a_network_error_is_not_fetched_and_promotion_still_runs():
    db = _db()
    R.detect_unknowns(db, today=NOW.date(), now=NOW)
    planned = F.plan_fetches(db)
    assert planned

    def down(u):
        raise F.FetchUnavailable("URLError: <urlopen error [Errno -2] Name or service not known>")

    out = F.run(db, get=down, now=NOW, sleep=_no_sleep)
    assert out["fetches"]["enabled"] is True
    assert all(r["fetched"] is False and "not reachable" in r["why"]
               for r in out["fetches"]["results"]), out
    assert {"promoted", "withdrawn", "unrouted"} <= set(out)          # promote() ran


def test_learn_worker_retries_transient_fetch_after_backoff_without_network(monkeypatch):
    from brambleloop.agents.registry import Registry
    from brambleloop.core.models import Job, JobStatus
    from brambleloop.learn import runtime  # noqa: F401 - register learn.scan
    from brambleloop.queue.durable import JobQueue
    from brambleloop.runtime.worker import Worker

    db = _db()
    Registry(db).seed_defaults()
    url = "https://www.cpsc.gov/fixture-transient"
    tid = R.open_question(db, question="What does the fixture safety policy require?",
                          trigger="test:transient-fetch", decision_ref="test:policy",
                          domain="marketplace_policy", **SPEC)["task"]
    with db.session() as s:
        row = s.get(R.ResearchTask, tid)
        row.detail = {**row.detail, "fetch_urls": [url]}
    failed_at = datetime.now(timezone.utc) - F.TRANSIENT_RETRY_BASE - timedelta(minutes=1)
    out = F.fetch_for_task(db, tid, url, now=failed_at, sleep=_no_sleep,
                           get=lambda _u: (_ for _ in ()).throw(OSError("fixture offline")))
    assert not out["fetched"] and out["retryable"] is True
    assert (tid, url) not in F.plan_fetches(db, now=failed_at + timedelta(hours=1))
    stub = Stub({url: "fixture policy text"})
    monkeypatch.setattr(F, "_default_get", stub)
    monkeypatch.setenv(F.ENABLE_VAR, "1")
    monkeypatch.setattr(F, "MIN_SECONDS_PER_HOST", 0.0)
    job = JobQueue(db).enqueue("learn", "learn.scan", {}, idempotency_key="fetch-retry")
    assert Worker(db, "fetch-retry", job_types=["learn.scan"]).run_once()
    with db.session() as s:
        done = s.get(Job, job.id)
        assert done.status == JobStatus.DONE, done.last_error
        assert any(src.get("citation") == url for src in s.get(R.ResearchTask, tid).sources)
    idx = stub.calls.index(url)
    assert idx > 0 and stub.calls[idx - 1] == "https://www.cpsc.gov/robots.txt"


def test_permanent_refusal_and_retry_limit_do_not_schedule_more_fetches():
    db = _db()
    R.detect_unknowns(db, today=NOW.date(), now=NOW)
    tid, url = F.plan_fetches(db, now=NOW)[0]
    denied = F.fetch_for_task(db, tid, url, now=NOW, sleep=_no_sleep,
                             get=Stub({url: "unused"}, robots="User-agent: *\nDisallow: /\n"))
    assert denied["retryable"] is False
    assert (tid, url) not in F.plan_fetches(db, now=NOW + timedelta(days=30))

    other = R.open_question(db, question="What does the separate fixture page establish?",
                            trigger="test:retry-limit", decision_ref="test:retry",
                            domain="marketplace_policy", now=NOW, **SPEC)["task"]
    other_url = "https://www.cpsc.gov/fixture-retry-limit"
    with db.session() as s:
        row = s.get(R.ResearchTask, other)
        row.detail = {**row.detail, "fetch_urls": [other_url]}
    for offset in (0, 7, 20):
        assert F.fetch_for_task(db, other, other_url, now=NOW + timedelta(hours=offset),
                                sleep=_no_sleep, get=lambda _u: (_ for _ in ()).throw(
                                    OSError("fixture offline")))["retryable"] is True
    assert (other, other_url) not in F.plan_fetches(db, now=NOW + timedelta(days=30))


def test_malformed_fetch_history_holds_the_attributable_task_without_crashing():
    db = _db()
    tid = R.open_question(db, question="What does the fixture safety page establish?",
                          trigger="test:bad-history", decision_ref="test:bad-history",
                          domain="marketplace_policy", now=NOW, **SPEC)["task"]
    url = "https://www.cpsc.gov/fixture-bad-history"
    with db.session() as s:
        row = s.get(R.ResearchTask, tid)
        row.detail = {**row.detail, "fetch_urls": [url]}
        s.add(AuditLog(actor="learn", action=F.FETCH_ACTION, at=NOW,
                       detail={"task": tid, "url": [url], "fetched": False}))
        s.add(AuditLog(actor="learn", action=F.FETCH_ACTION, at=NOW,
                       detail={"task": [tid], "url": {"bad": url}, "fetched": False}))
    assert (tid, url) not in F.plan_fetches(db, now=NOW + timedelta(days=2))


@pytest.mark.parametrize("status,retryable", [(503, True), (429, False), (403, False)])
def test_http_failures_have_conservative_retry_classification(status, retryable):
    db = _db()
    tid = R.open_question(db, question="What does the fixture resource actually establish?",
                          trigger="test:http-classification", decision_ref="test:http",
                          domain="marketplace_policy", now=NOW, **SPEC)["task"]
    url = "https://www.cpsc.gov/fixture-http-classification"
    with db.session() as s:
        row = s.get(R.ResearchTask, tid)
        row.detail = {**row.detail, "fetch_urls": [url]}

    def fixture_get(requested):
        if requested.endswith("/robots.txt"):
            return 200, b"User-agent: *\nAllow: /\n"
        return status, b""

    result = F.fetch_for_task(db, tid, url, now=NOW, sleep=_no_sleep, get=fixture_get)
    assert result["retryable"] is retryable
    assert ((tid, url) in F.plan_fetches(db, now=NOW + timedelta(hours=7))) is retryable


def test_learn_worker_recovers_when_fetched_source_audit_write_fails(monkeypatch):
    from sqlalchemy.orm import Session
    from brambleloop.agents.registry import Registry
    from brambleloop.core.models import Job, JobStatus
    from brambleloop.learn import runtime  # noqa: F401
    from brambleloop.queue.durable import JobQueue
    from brambleloop.runtime.worker import Worker

    db = _db()
    Registry(db).seed_defaults()
    url = "https://www.cpsc.gov/fixture-atomic-source"
    tid = R.open_question(db, question="What does the fixture official safety source state?",
                          trigger="test:atomic-source", decision_ref="test:atomic",
                          domain="marketplace_policy", **SPEC)["task"]
    with db.session() as s:
        row = s.get(R.ResearchTask, tid)
        row.detail = {**row.detail, "fetch_urls": [url]}
    monkeypatch.setenv(F.ENABLE_VAR, "1")
    monkeypatch.setattr(F, "_default_get", Stub({url: "fixture atomic source text"}))
    monkeypatch.setattr(F, "MIN_SECONDS_PER_HOST", 0.0)
    real_add = Session.add

    def fail_audit(session, instance, *args, **kwargs):
        if (isinstance(instance, AuditLog) and instance.action == F.FETCH_ACTION
                and instance.detail.get("url") == url and instance.detail.get("fetched")):
            raise RuntimeError("fixture audit storage interruption")
        return real_add(session, instance, *args, **kwargs)

    monkeypatch.setattr(Session, "add", fail_audit)
    q = JobQueue(db)
    first = q.enqueue("learn", "learn.scan", {}, idempotency_key="fetch-atomic-first")
    assert Worker(db, "fetch-atomic-first", job_types=["learn.scan"]).run_once()
    with db.session() as s:
        assert s.get(Job, first.id).status == JobStatus.DONE
        assert not [v for v in s.get(R.ResearchTask, tid).sources if v.get("citation") == url]
        assert not list(s.scalars(R.select(Job).where(
            Job.idempotency_key.like(f"research.fetch.followup:{tid}:%"))))
    monkeypatch.setattr(Session, "add", real_add)
    second = q.enqueue("learn", "learn.scan", {}, idempotency_key="fetch-atomic-restart")
    assert Worker(db, "fetch-atomic-restart", job_types=["learn.scan"]).run_once()
    with db.session() as s:
        source = next(v for v in s.get(R.ResearchTask, tid).sources if v.get("citation") == url)
        audit = s.scalar(R.select(AuditLog).where(AuditLog.action == F.FETCH_ACTION,
                          AuditLog.detail["url"].as_string() == url,
                          AuditLog.detail["fetched"].as_boolean() == True))  # noqa: E712
        assert audit is not None
        assert source["sha256"] == audit.detail["sha256"]
        assert source["bytes"] == audit.detail["bytes"]


def test_fetched_bytes_are_not_attached_after_task_stops():
    db = _db()
    tid = R.open_question(db, question="What does this safety resource actually state?",
                          trigger="test:closed-fetch", decision_ref="test:closed",
                          domain="marketplace_policy", now=NOW, **SPEC)["task"]
    url = "https://www.cpsc.gov/fixture-closed"

    def changing_get(requested):
        if requested.endswith("/robots.txt"):
            return 200, b"User-agent: *\nAllow: /\n"
        with db.session() as s:
            s.get(R.ResearchTask, tid).state = R.STOPPED
        return 200, b"fixture data"

    out = F.fetch_for_task(db, tid, url, get=changing_get, now=NOW, sleep=_no_sleep)
    assert out["fetched"] is False
    with db.session() as s:
        assert not s.get(R.ResearchTask, tid).sources


def test_fetch_followup_is_durable_and_resumes_research_on_same_day(monkeypatch):
    from brambleloop.agents.registry import Registry
    from brambleloop.core.models import Job, JobStatus
    from brambleloop.intel import research_agent as RA
    from brambleloop.learn import runtime  # noqa: F401
    from brambleloop.queue.durable import JobQueue
    from brambleloop.runtime import intel_ops  # noqa: F401
    from brambleloop.runtime.worker import Worker

    db = _db()
    Registry(db).seed_defaults()
    tid = R.open_question(db, question="What does Etsy currently say about digital refunds?",
                          trigger="test:fetch-followup", decision_ref="test:refund",
                          domain="marketplace_policy", query_terms=["refund"], **SPEC)["task"]
    monkeypatch.setenv(F.ENABLE_VAR, "1")
    monkeypatch.setattr(F, "MIN_SECONDS_PER_HOST", 0.0)
    monkeypatch.setattr(R, "detect_unknowns", lambda *_a, **_kw: {"opened": [], "already_open": []})
    urls = RA.official_sources("marketplace_policy", ["refund"])
    monkeypatch.setattr(F, "_default_get", Stub({urls[0]: "fixture official refund text"}))
    q = JobQueue(db)
    first = q.enqueue("research_agent", "research.investigate", {"task_id": tid},
                      idempotency_key="fetch-followup-initial")
    assert Worker(db, "initial-research", job_types=["research.investigate"]).run_once()
    with db.session() as s:
        assert s.get(Job, first.id).outputs["status"] == RA.AWAITING_EXTERNAL
    scan = q.enqueue("learn", "learn.scan", {}, idempotency_key="fetch-followup-scan")
    assert Worker(db, "source-scan", job_types=["learn.scan"]).run_once()
    with db.session() as s:
        assert s.get(Job, scan.id).status == JobStatus.DONE
        source = next(x for x in s.get(R.ResearchTask, tid).sources if x.get("citation") == urls[0])
        followup_id = source["followup_job_id"]
        followup = s.get(Job, followup_id)
        assert followup.job_type == "research.investigate" and followup.status == JobStatus.PENDING
    assert Worker(db, "followup-research", job_types=["research.investigate"]).run_once()
    with db.session() as s:
        assert s.get(Job, followup_id).outputs["status"] == RA.EVIDENCE_GATHERED


def test_fetch_followup_enqueue_failure_rolls_back_source_and_audit(monkeypatch):
    db = _db()
    tid = R.open_question(db, question="What does the fixture safety policy require now?",
                          trigger="test:followup-rollback", decision_ref="test:rollback",
                          domain="marketplace_policy", **SPEC)["task"]
    url = "https://www.cpsc.gov/fixture-followup-rollback"
    def fail_enqueue(*_args, **_kwargs):
        raise RuntimeError("fixture queue failure")
    with pytest.raises(RuntimeError):
        F.fetch_for_task(db, tid, url, get=Stub({url: "fixture safety page"}),
                         sleep=_no_sleep, enqueue=fail_enqueue)
    with db.session() as s:
        assert s.get(R.ResearchTask, tid).sources == []
        assert not [a for a in s.scalars(R.select(AuditLog).where(
            AuditLog.action == F.FETCH_ACTION)) if a.detail.get("url") == url]


@pytest.mark.parametrize("status", ["cancelled", "dead"])
def test_retention_preserves_fetched_source_followup_job_and_key(monkeypatch, status):
    from brambleloop.agents.registry import Registry
    from brambleloop.core.models import Job, JobStatus
    from brambleloop.learn import runtime  # noqa: F401
    from brambleloop.ops import retention
    from brambleloop.queue.durable import JobQueue
    from brambleloop.runtime.worker import Worker

    db = _db()
    Registry(db).seed_defaults()
    url = "https://www.cpsc.gov/fixture-retention"
    tid = R.open_question(db, question="What does this fixture safety source actually require?",
                          trigger="test:source-retention", decision_ref="test:retention",
                          domain="marketplace_policy", **SPEC)["task"]
    with db.session() as s:
        row = s.get(R.ResearchTask, tid)
        row.detail = {**row.detail, "fetch_urls": [url]}
    monkeypatch.setenv(F.ENABLE_VAR, "1")
    monkeypatch.setattr(F, "MIN_SECONDS_PER_HOST", 0.0)
    monkeypatch.setattr(F, "_default_get", Stub({url: "fixture source"}))
    monkeypatch.setattr(R, "detect_unknowns", lambda *_a, **_kw: {"opened": [], "already_open": []})
    JobQueue(db).enqueue("learn", "learn.scan", {}, idempotency_key="source-retention-scan")
    assert Worker(db, "source-retention", job_types=["learn.scan"]).run_once()
    with db.session() as s:
        source = next(v for v in s.get(R.ResearchTask, tid).sources if v.get("citation") == url)
        jid = source["followup_job_id"]
        job = s.get(Job, jid)
        key = job.idempotency_key
        job.status = JobStatus.CANCELLED if status == "cancelled" else JobStatus.DEAD
        job.last_error = "capability not enabled: fixture" if status == "dead" else "fixture cancellation"
        job.finished_at = datetime.now(timezone.utc) - timedelta(days=200)
        for i in range(30):
            s.add(Job(agent="research_agent", job_type="research.investigate",
                      inputs={"task_id": tid}, status=JobStatus.CANCELLED,
                      idempotency_key=f"retention-unrelated-{i}",
                      finished_at=datetime.now(timezone.utc) - timedelta(days=200)))
    future = datetime.now(timezone.utc) + timedelta(days=200)
    result = retention.apply(db, now=future)
    assert result["removed"]["jobs"] > 0
    with db.session() as s:
        assert s.get(Job, jid) is not None and s.get(Job, jid).idempotency_key == key
        assert s.get(R.ResearchTask, tid).sources[0]["followup_job_id"] == jid


def test_malformed_followup_reference_holds_job_retention():
    from brambleloop.ops import retention

    db = _db()
    tid = R.open_question(db, question="What does the fixture safety source actually require?",
                          trigger="test:malformed-retention", decision_ref="test:retention",
                          domain="marketplace_policy", **SPEC)["task"]
    with db.session() as s:
        s.get(R.ResearchTask, tid).sources = [{"followup_job_id": ["invalid"]}]
    with pytest.raises(retention.RetentionRefused):
        retention.job_plan(db)
    with pytest.raises(retention.RetentionRefused):
        retention.dead_letter_plan(db)


def test_review_f8_default_get_turns_network_errors_into_fetch_unavailable():
    import urllib.request

    real = urllib.request.OpenerDirector.open

    def boom(self, *a, **k):
        raise OSError("[Errno 110] Connection timed out")

    urllib.request.OpenerDirector.open = boom
    try:
        try:
            F._default_get("https://www.cpsc.gov/a")
            raise AssertionError("a network error escaped as a crash or a success")
        except F.FetchUnavailable as exc:
            assert "timed out" in str(exc)
    finally:
        urllib.request.OpenerDirector.open = real


def test_review_n5_an_unencodable_redirect_target_is_a_refusal_with_its_audit():
    """Review cbd4ff1 N-5: urllib raises UnicodeEncodeError on an IDN redirect target before
    the allowlist sees it; that must surface as FetchRefused so the fetch is recorded."""
    import urllib.request

    real = urllib.request.OpenerDirector.open

    def idn(self, *a, **k):
        "https://\u0435n.wikipedia.org/x".encode("iso-8859-1")   # what http_error_302 does

    urllib.request.OpenerDirector.open = idn
    try:
        try:
            F._default_get("https://www.cpsc.gov/a")
            raise AssertionError("an unencodable redirect escaped")
        except F.FetchRefused as exc:
            assert "redirect target" in str(exc)
    finally:
        urllib.request.OpenerDirector.open = real


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
