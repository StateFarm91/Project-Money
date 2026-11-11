"""P1 6783107211 / review 6785727146: the liveness basis is visible where it is read.

* /api/verify: `worker_is_alive` evidence carries `alive_basis` and `busy`; the advisory
  `worker_handler_within_expected_time` is false on `handler_long` but never turns the verify
  verdict (advisory checks are excluded from `ok`); anonymously it is name and ok only.
* the mobile dashboard's worker card reads "busy" while a handler keeps the worker alive.
* ops/readback: a false advisory reads WARN (not PASS, not FAIL); overall WARN; and
  ops/rollback_decision treats WARN as degraded, never as a containment trigger.

Run: cd brambleloop && PYTHONPATH=src:tests $PY tests/test_p1_worker_liveness_surfaces.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT.parent))
_TMP = tempfile.TemporaryDirectory()
os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{_TMP.name}/app.sqlite"
os.environ["BRAMBLELOOP_EMBEDDED_WORKER"] = "0"
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP.name, "artifacts")

from fastapi.testclient import TestClient  # noqa: E402

from brambleloop.app import main as app_main, runner  # noqa: E402
from ops import readback, rollback_decision  # noqa: E402

TOKEN = "p1-surfaces-operator-" + "k" * 24


class _W:
    current = None


def _state(seconds_running: float | None):
    w = _W()
    now = datetime.now(timezone.utc)
    if seconds_running is not None:
        w.current = {"job_id": 42, "job_type": "plan.cycle",
                     "started_at": now - timedelta(seconds=seconds_running)}
    return runner.RunnerState(enabled=True, worker_name="w0",
                              worker_started_at=now - timedelta(hours=2),
                              worker_last_tick=now - timedelta(seconds=900),
                              scheduler_last_tick=now, worker_ref=w)


def _verify(state):
    saved, old = runner.STATE, os.environ.get("BRAMBLELOOP_OPS_TOKEN")
    runner.STATE = state
    os.environ["BRAMBLELOOP_OPS_TOKEN"] = TOKEN
    try:
        with TestClient(app_main.app) as c:
            body = c.get("/api/verify", headers={"Authorization": f"Bearer {TOKEN}"}).json()
            public = c.get("/api/verify").json()
            page = c.get("/m", headers={"Authorization": f"Bearer {TOKEN}"}).text
    finally:
        runner.STATE = saved
        if old is None:
            os.environ.pop("BRAMBLELOOP_OPS_TOKEN", None)
        else:
            os.environ["BRAMBLELOOP_OPS_TOKEN"] = old
    return body, public, page


def _check(body, name):
    return next(c for c in body["checks"] if c["check"] == name)


def test_verify_evidence_carries_the_basis_and_the_advisory_never_turns_the_verdict():
    for seconds, basis, advisory_ok in ((60.0, "handler_running", True),
                                        (runner.HANDLER_LONG_S + 60, "handler_long", False)):
        body, public, _page = _verify(_state(seconds))
        alive = _check(body, "worker_is_alive")
        assert alive["ok"] is True, alive
        assert alive["evidence"]["alive_basis"] == basis, alive["evidence"]
        assert alive["evidence"]["busy"]["job_type"] == "plan.cycle", alive["evidence"]
        adv = _check(body, "worker_handler_within_expected_time")
        assert adv["ok"] is advisory_ok and adv.get("advisory") is True, adv
        assert body["ok"] == all(c["ok"] for c in body["checks"] if not c.get("advisory")), \
            [(c["check"], c["ok"]) for c in body["checks"] if not c["ok"]]
        pub = next(c for c in public["checks"]
                   if c["check"] == "worker_handler_within_expected_time")
        assert pub == {"check": "worker_handler_within_expected_time", "ok": advisory_ok}, pub


def test_the_verdict_ignores_a_failing_advisory_and_nothing_else():
    ok = {"check": "a", "ok": True}
    assert app_main.verify_passed([ok, {"check": "w", "ok": False, "advisory": True}]) is True
    assert app_main.verify_passed([ok, {"check": "b", "ok": False}]) is False
    assert app_main.verify_passed([{"check": "b", "ok": False},
                                   {"check": "w", "ok": True, "advisory": True}]) is False


def test_a_build_that_does_not_report_the_advisory_reads_warn_never_unknown():
    def fetch(url, token=None):
        if url.endswith("/api/verify"):
            return 200, {"ok": True, "checks": [{"check": "phase_is_shadow", "ok": True}]}
        return 200, {}
    rb = readback.run("a" * 40, url="https://x.invalid", fetch=fetch)
    item = next(i for i in rb["features"] if i["feature"] == "worker 0 not held by a long handler")
    assert item["verdict"] == readback.WARN, item


def test_the_dashboard_says_busy_while_a_handler_keeps_the_worker_alive():
    _b, _p, page = _verify(_state(60.0))
    assert "busy" in page and "stalled" not in page.split("worker")[0][-200:], page[:400]
    _b, _p, dead_page = _verify(_state(None))          # stale tick, nothing running
    assert "stalled" in dead_page


def _readback(advisory_ok: bool):
    def fetch(url, token=None):
        if url.endswith("/api/verify"):
            checks = [{"check": n, "ok": True} for n in (
                "phase_is_shadow", "nothing_published",
                "publication_was_actually_attempted_and_refused",
                "no_unexpected_dead_letters_in_24h", "every_agent_has_a_cost_ceiling")]
            checks.append({"check": "worker_handler_within_expected_time", "ok": advisory_ok})
            return 200, {"ok": True, "checks": checks}
        return 200, {}
    return readback.run("a" * 40, url="https://x.invalid", fetch=fetch)


def test_readback_reads_a_false_advisory_as_warn_and_rollback_does_not_contain_on_it():
    row = next(r for r in readback.MANIFEST if r[0] == "worker 0 not held by a long handler")
    assert row[6] == readback.WARN_ONLY, row
    warn = _readback(False)
    item = next(i for i in warn["features"] if i["feature"] == row[0])
    assert item["verdict"] == readback.WARN, item
    ok = _readback(True)
    assert next(i for i in ok["features"] if i["feature"] == row[0])["verdict"] == readback.PASS
    # rollback: a report whose only non-PASS is the WARN row is not contained
    only_warn = {"reachable": True, "verdict": readback.WARN,
                 "features": [{"feature": "release identity", "verdict": "PASS"},
                              {"feature": row[0], "verdict": readback.WARN}]}
    d = rollback_decision.decide(only_warn, previous="abc")
    assert d["decision"] == rollback_decision.NONE and d["warnings"] == [row[0]], d
    # ...but WARN never hides a real failure beside it
    mixed = {**only_warn, "verdict": "FAIL",
             "features": only_warn["features"] + [{"feature": "embedded worker alive",
                                                   "verdict": "FAIL"}]}
    assert rollback_decision.decide(mixed, previous="abc")["decision"] == \
        rollback_decision.ROLLBACK


def test_a_warn_only_readback_is_not_undone_and_exits_with_its_own_success_code():
    """Review 6789501427 LOW-1: WARN rows are listed as warnings, not `not_done`; the CLI
    exits WARN_EXIT (3), which ops/deploy.sh deploys on."""
    import test_w4_smoke as smoke_t

    def healthy(advisory_ok):
        b = smoke_t._prod_bodies(sha="a" * 40)
        code, verify = b["/api/verify"]
        checks = [{**c, "ok": advisory_ok}
                  if c["check"] == "worker_handler_within_expected_time" else c
                  for c in verify["checks"]]
        b = {**b, "/api/verify": (code, {**verify, "checks": checks})}
        return readback.run("a" * 40, url="https://prod.invalid",
                            fetch=smoke_t._fetcher(b), token=smoke_t.OPS_TOKEN)
    out = healthy(False)
    row = "worker 0 not held by a long handler"
    assert row in out["warnings"] and row not in out["not_done"], out
    assert out["verdict"] == readback.WARN, out["verdict"]
    clean = healthy(True)
    assert clean["verdict"] == readback.PASS, (clean["verdict"], clean["not_done"])
    saved = readback.run
    readback.run = lambda *a, **k: out
    try:
        assert readback.main(["--sha", "a" * 40]) == readback.WARN_EXIT == 3
        readback.run = lambda *a, **k: clean
        assert readback.main(["--sha", "a" * 40]) == 0
    finally:
        readback.run = saved
    sh = (ROOT.parent / "ops" / "deploy.sh").read_text()
    assert sh.count('[ "$rb" -eq 3 ]') == 2, "deploy.sh must accept WARN on both reads"


def test_etsy_exercise_counts_an_advisory_as_a_warning_not_a_failure():
    src = (ROOT / "src" / "brambleloop" / "integrations" / "etsy_exercise.py").read_text()
    assert 'if not c.get("ok") and not c.get("advisory")]' in src
    assert '"warnings": [c.get("check") for c in checks' in src


def test_the_dashboard_says_busy_long_for_a_long_handler():
    _b, _p, page = _verify(_state(runner.HANDLER_LONG_S + 60))
    assert "busy (long)" in page, page[:600]


def test_overall_readback_ranks_warn_below_every_other_non_pass():
    v = readback
    order = [v.FAIL, v.UNKNOWN, v.NEEDS_OPERATOR, v.WARN, v.PASS]
    src = (ROOT.parent / "ops" / "readback.py").read_text()
    seg = src[src.index("overall = ("):src.index("import datetime as _dt")]
    positions = [seg.index(x) for x in ("FAIL if FAIL", "UNKNOWN if UNKNOWN",
                                        "NEEDS_OPERATOR if NEEDS_OPERATOR", "WARN if WARN")]
    assert positions == sorted(positions), (order, positions)


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                import traceback
                traceback.print_exc()
                print("FAIL", name, repr(e))
    sys.exit(1 if fails else 0)
