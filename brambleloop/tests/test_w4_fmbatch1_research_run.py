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
