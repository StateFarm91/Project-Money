"""W4-CCFIN: the Command Center's remaining gaps -- Rule #1 state, per-agent status and the
authority ladder/DAG are rendered, read-only, with as-of timestamps; UNKNOWN is never 0.

* `rule1` provider (`autonomy.rule1.summary`): bounded (window, row cap, wall-clock budget),
  read-only (no row written anywhere), UNKNOWN with a reason when unmeasured, as_of carried;
  a department the budget did not reach reads UNKNOWN, never "no defect".
* GET /api/cc/autonomy carries `rule1` and `agents`; GET /api/cc/account carries
  `authority_policy` and `authority_dag`; both stay owner-session gated.
* The PWA views render them (learn.js, account.js) through h() (no innerHTML), with no
  write actions on the authority cards, and every non-envelope section shows a freshness time.

Run: cd brambleloop && PYTHONPATH=src python3 tests/test_w4_ccfin.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import os
import socket
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

_TMP = tempfile.mkdtemp(prefix="w4_ccfin_")
os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{os.path.join(_TMP, 'cc.db')}"
os.environ.pop("DATABASE_URL", None)
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")
os.environ["BRAMBLELOOP_EMBEDDED_WORKER"] = "0"
os.environ.pop("BRAMBLELOOP_REQUIRE_POSTGRES", None)
for _k in list(os.environ):
    if _k.startswith(("ANTHROPIC_API", "ETSY", "OPENAI", "REPLICATE", "FAL_", "GEMINI")):
        os.environ.pop(_k)


def _no_network(*_a, **_k):
    raise OSError("network refused by the W4-CCFIN harness")


socket.socket.connect = _no_network  # type: ignore[assignment]
socket.create_connection = _no_network  # type: ignore[assignment]

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import func, inspect, select, text  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.app import main  # noqa: E402
from brambleloop.app.command_center import auth, providers  # noqa: E402
from brambleloop.autonomy import charters, generators, rule1  # noqa: E402
from brambleloop.core import opsauth  # noqa: E402
from brambleloop.core.models import Job, JobStatus  # noqa: E402

OPS = "c" * 40
PASS = "owner passphrase for the W4-CCFIN harness"
os.environ[opsauth.TOKEN_VAR] = OPS
os.environ[auth.PASSPHRASE_VAR] = auth.hash_passphrase(PASS, iterations=100_000)
main.db.create_all()
Registry(main.db).seed_defaults()
DB = main.db
STATIC = ROOT / "src" / "brambleloop" / "app" / "command_center" / "static"


def session():
    c = TestClient(main.app, base_url="https://testserver", raise_server_exceptions=False)
    r = c.post("/api/cc/auth/login", json={"passphrase": PASS})
    assert r.status_code == 200, r.text
    return c


def _row_counts() -> dict:
    names = inspect(DB.engine).get_table_names()
    with DB.engine.connect() as conn:
        return {n: conn.execute(text(f'SELECT COUNT(*) FROM "{n}"')).scalar() for n in names}


def _add_jobs():
    now = datetime.now(timezone.utc)
    dept_job = next(jt for ch in charters.CHARTERS for jt in sorted(ch.job_types)
                    if charters.department_of(jt) == ch.key and jt != "autonomy.orchestrate")
    with DB.session() as s:
        for i in range(3):
            s.add(Job(agent="orchestrator", job_type=dept_job, inputs={},
                      outputs={"summary": f"r{i}", "count": i + 1},
                      status=JobStatus.DONE, started_at=now - timedelta(minutes=10 + i),
                      finished_at=now - timedelta(minutes=9 + i), run_after=now))
        s.commit()
    return dept_job


# Order matters: the empty-database reading first.

def test_rule1_unmeasured_is_unknown_never_zero():
    with DB.session() as s:
        assert (s.scalar(select(func.count()).select_from(Job)) or 0) == 0
    env = providers.call("rule1", DB)
    assert env["status"] == "UNKNOWN", env
    assert env["reason"] and "not been measured" in env["reason"]
    assert env["as_of"] is None and env["basis"] == "unknown"
    assert env["items"] == []
    assert env["provider"] == "brambleloop.autonomy.rule1.summary"


def test_rule1_reading_is_bounded_read_only_and_dated():
    _add_jobs()
    before = _row_counts()
    t0 = time.monotonic()
    env = providers.call("rule1", DB)
    assert time.monotonic() - t0 < 30
    assert _row_counts() == before, "the Rule #1 reading wrote a row"
    assert env["status"] in ("OK", "DEGRADED", "UNKNOWN"), env
    assert env["as_of"], env
    assert {i["department"] for i in env["items"]} == {ch.key for ch in charters.CHARTERS}
    for it in env["items"]:
        assert it["as_of"], it
        assert it["status"] in providers.STATUSES, it
        if it["status"] == "UNKNOWN":
            assert it["rule1_defect"] is None and it["eligible_untaken"] is None, it
        else:
            assert isinstance(it["rule1_defect"], bool), it
    assert sum(i["done"] for i in env["items"]) >= 3
    w = env["window"]
    assert w["hours"] == rule1.SUMMARY_WINDOW_HOURS and w["max_jobs"] == rule1.SUMMARY_MAX_JOBS


def test_rule1_row_cap_and_budget():
    capped = rule1.summary(DB, max_jobs=1)
    assert capped["window"]["truncated"] is True and capped["window"]["jobs_read"] == 1
    spent = rule1.summary(DB, budget_s=-1)
    assert spent["status"] == "UNKNOWN" and spent["reason"], spent
    assert spent["counts"]["evaluated"] == 0 and spent["counts"]["defects"] is None
    for it in spent["items"]:
        assert it["status"] == "UNKNOWN" and it["rule1_defect"] is None, it
        assert "budget" in it["why"]


def test_rule1_defect_detected_when_idle_with_eligible_work():
    ch = charters.CHARTERS[0]
    real = generators.candidates

    def fake(db, charter, snap):
        if charter.key != ch.key:
            return []
        return [generators.Candidate(department=ch.key, job_type="x.fake", value=1.0,
                                     source="test", reason="eligible test work",
                                     fingerprint="fp-ccfin")]

    generators.candidates = fake
    try:
        env = rule1.summary(DB)
    finally:
        generators.candidates = real
    it = next(i for i in env["items"] if i["department"] == ch.key)
    assert it["idle_now"] is True and it["rule1_defect"] is True, it
    assert it["eligible_untaken"] == 1 and it["status"] == "DEGRADED"
    assert env["status"] == "DEGRADED" and env["counts"]["defects"] == 1, env["counts"]


def test_rule1_provider_failure_and_absence_are_unknown():
    real = generators.Snapshot.read
    generators.Snapshot.read = classmethod(lambda cls, db, now: (_ for _ in ()).throw(
        RuntimeError("boom")))
    try:
        env = providers.call("rule1", DB)
    finally:
        generators.Snapshot.read = real
    assert env["status"] == "UNKNOWN" and "RuntimeError" in env["reason"], env
    prev = sys.modules.get("brambleloop.autonomy.rule1")
    sys.modules["brambleloop.autonomy.rule1"] = None  # type: ignore[assignment]
    try:
        env = providers.call("rule1", DB)
    finally:
        sys.modules["brambleloop.autonomy.rule1"] = prev
    assert env["status"] == "UNKNOWN" and env["reason"] == "not built", env


def test_autonomy_and_account_tabs_carry_the_new_sections():
    anon = TestClient(main.app, base_url="https://testserver", raise_server_exceptions=False)
    for p in ("/api/cc/autonomy", "/api/cc/account"):
        assert anon.get(p).status_code == 401, p
    c = session()
    s = c.get("/api/cc/autonomy").json()["sections"]
    for k in ("rule1", "agents"):
        assert s[k]["status"] in providers.STATUSES, (k, s[k])
        assert "as_of" in s[k] and "basis" in s[k], k
        if s[k]["status"] == "UNKNOWN":
            assert s[k]["reason"], k
        else:
            assert s[k]["as_of"], k
    ag = s["agents"]
    assert ag["items"], ag
    for i in ag["items"]:
        for key in ("agent", "department", "state", "doing_now", "last_useful_result",
                    "blockers", "as_of"):
            assert key in i, (key, i)
    a = c.get("/api/cc/account").json()["sections"]
    for k in ("authority_policy", "authority_dag"):
        assert a[k]["status"] in providers.STATUSES, (k, a[k])
        assert "as_of" in a[k], k
    assert a["authority_dag"]["status"] == "UNKNOWN", a["authority_dag"]
    assert a["authority_dag"]["reason"] == "no work items recorded yet", a["authority_dag"]
    # Before W4-CCFIN both summaries swallowed the Session/Database mismatch as a bare
    # "AttributeError" UNKNOWN; they now read the contract's Session.
    assert a["authority_policy"]["status"] == "OK", a["authority_policy"]
    assert a["authority_policy"]["as_of"] and a["authority_policy"]["phase"]


def test_authority_dag_with_a_work_item_is_dated_and_counted():
    from brambleloop.authority import dag

    dag.submit(DB, key="ccfin:test", department="store_commerce", job_type="store.publish",
               submitted_by="test", title="publish test listing", requires_approval=True)
    env = session().get("/api/cc/account").json()["sections"]["authority_dag"]
    assert env["status"] == "OK" and env["as_of"], env
    assert sum(env["counts"].values()) == 1, env["counts"]


def test_estimate_drift_is_an_envelope_unknown_never_zero():
    from brambleloop.app.command_center import tabs
    from brambleloop.finance import spend_report

    m = session().get("/api/cc/money").json()["sections"]["estimate_drift"]
    assert m["status"] in providers.STATUSES and "basis" in m and "sources" in m, m
    assert m["settlement_against_provider_billing"] == "OWNER-GATED"
    real = spend_report.estimate_drift
    try:
        spend_report.estimate_drift = lambda db: {
            "state": "healthy", "degraded": False, "why": "", "token_priced_calls": 0,
            "purposes_outside_tolerance": {}, "calls_with_no_reservation_share": 0.0,
            "tolerance": 0.25, "purposes_too_few_calls_to_judge": []}
        u = tabs.estimate_drift_reading(DB)
        assert u["status"] == "UNKNOWN" and u["reason"] and u["as_of"], u
        assert u["calls_with_no_reservation_share"] is None and u["basis"] == "unknown", u
        assert u["state"] == "healthy", "state is spend_report's word (verify readback contract)"
        spend_report.estimate_drift = lambda db: {
            "state": "degraded", "degraded": True, "why": "p: outside", "token_priced_calls": 9,
            "purposes_outside_tolerance": {"p": {"calls": 9, "estimated_cad": 0.1,
                                                 "recorded_cad": 0.3, "ratio": 3.0,
                                                 "under_estimated": True}},
            "calls_with_no_reservation_share": 0.0, "tolerance": 0.25}
        d = tabs.estimate_drift_reading(DB)
        assert d["status"] == "DEGRADED" and d["reason"] == "p: outside", d
        assert d["items"][0]["purpose"] == "p" and d["purposes_outside_tolerance"] == ["p"]
        assert d["calls_with_no_reservation_share"] == 0.0 and d["basis"] == "measured"
    finally:
        spend_report.estimate_drift = real
    js = (STATIC / "js" / "views" / "money.js").read_text()
    assert "driftCard(s.estimate_drift, result)" in js and "innerHTML" not in js


def test_pwa_renders_rule1_agents_and_authority_read_only():
    learn = (STATIC / "js" / "views" / "learn.js").read_text()
    acct = (STATIC / "js" / "views" / "account.js").read_text()
    shared = (STATIC / "js" / "views" / "_shared.js").read_text()
    assert "rule1Card(s.rule1, result)" in learn and "agentsCard(s.agents, result)" in learn
    for field in ("doing_now", "last_useful_result", "blockers", "department"):
        assert field in learn, field
    assert "authorityPolicyCard(" in acct and "authorityDagCard(" in acct
    for src in (learn, acct, shared):
        assert "innerHTML" not in src and "insertAdjacentHTML" not in src
        assert "eval(" not in src
    gov = acct[acct.index("export function authorityPolicyCard"):
               acct.index("function appearanceCard")]
    assert "api." not in gov and "button" not in gov and "guardedAction" not in gov, \
        "authority cards must be read-only"
    assert "freshness(env.as_of" in learn and "freshness(env.as_of" in acct
    assert "asOf" in shared and 'class: "tile-meta" }, freshness(' in shared
    html = (STATIC / "index.html").read_text()
    assert "<script>" not in html.replace(" ", "")


if __name__ == "__main__":
    t0 = time.monotonic()
    fails = 0
    tests = [(n, f) for n, f in list(globals().items()) if n.startswith("test_") and callable(f)]
    assert tests
    for name, fn in tests:
        try:
            fn()
            print("OK", name, flush=True)
        except Exception as e:  # noqa: BLE001
            fails += 1
            import traceback

            traceback.print_exc()
            print("FAIL", name, f"{type(e).__name__}: {str(e)[:1500]}", flush=True)
    print(f"{len(tests) - fails}/{len(tests)} passed in {time.monotonic() - t0:.0f}s")
    sys.exit(1 if fails else 0)
