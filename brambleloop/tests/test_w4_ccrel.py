"""W4-CCREL: the release approval card on Approvals (candidate SHA, suite result, security
review, rollback target), read from the tracked release evidence the deploy guard trusts.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_w4_ccrel.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
_TMP = tempfile.mkdtemp(prefix="w4_ccrel_")

from brambleloop.app.command_center import release_card as RC  # noqa: E402

SHA = "a" * 40
OLD = "b" * 40


def _root(*, suite_status="passed", failing=0, deployed=(OLD,), review=None, tamper=False,
          evidence_names_candidate=False) -> Path:
    root = Path(tempfile.mkdtemp(dir=_TMP))
    rdir = root / "release"
    (rdir / "suite_runs").mkdir(parents=True)
    run = "20261012T000000Z-1"
    suite = {"git_sha": SHA, "release_eligible": suite_status == "passed", "status": suite_status,
             "scope": "full", "suites_failing": failing, "failing_suites": [] if not failing
             else ["x"], "suites_total": 560, "tests_passing": 7900, "tests_failing_reported": 0,
             "run_id": run, "finished_utc": "2026-10-12T04:00:00Z"}
    sp = rdir / "suite_runs" / f"{run}.json"
    sp.write_text(json.dumps(suite))
    lp = rdir / "suite_runs" / f"{run}.log"
    lp.write_text(f"RUN ID: {run}\nGIT SHA: {SHA}\nTOTAL PASSING: 7900 ; suites failing: "
                  f"{failing}\n")
    rec = {"kind": "brambleloop.release_record", "sha": SHA, "release_eligible": True,
           "recorded_at": "2026-10-12T04:05:00Z",
           "suite_record": {"path": f"suite_runs/{run}.json",
                            "sha256": hashlib.sha256(sp.read_bytes()).hexdigest()},
           "suite_log": {"path": f"suite_runs/{run}.log",
                         "sha256": hashlib.sha256(lp.read_bytes()).hexdigest()}}
    if tamper:
        sp.write_text(json.dumps({**suite, "tests_passing": 1}))
    (rdir / f"RELEASE_{SHA}.json").write_text(json.dumps(rec))
    hist = [{"sha": d, "observed": "2026-10-11", "evidence": "prod /health"} for d in deployed]
    if evidence_names_candidate:
        hist.append({"sha": "c" * 40, "observed": "2026-10-12",
                     "evidence": f"boot_guard record RELEASE_{SHA}.json"})
    (rdir / "DEPLOYED_HISTORY.json").write_text(json.dumps({"deployed": hist}))
    if review is not None:
        (rdir / f"SECURITY_REVIEW_{SHA}.json").write_text(json.dumps(review))
    return root


def test_pending_candidate_shows_sha_suite_unknown_review_and_rollback():
    c = RC.candidate(_root())
    assert c["pending"] and c["sha"] == SHA and c["sha12"] == SHA[:12]
    ev = RC.evidence(c)
    assert [e["label"] for e in ev] == [f"Candidate SHA {SHA[:12]}", "Full release suite",
                                        "Security review", f"Rollback target {OLD[:12]}"]
    states = [e["state"] for e in ev]
    assert states == ["PASS", "PASS", "UNKNOWN", "PASS"], states
    assert "7900 tests passing, 0 of 560 suites failing" in ev[1]["why"]
    assert "not assumed passed" in ev[2]["why"]
    assert not RC.ready(c)                                   # UNKNOWN is never a pass
    f = RC.card_fields(c)
    assert f["recommendation"].startswith("Do not authorise yet") and "Security review" in \
        f["recommendation"]
    assert f["release_candidate"]["rollback_target"]["sha"] == OLD
    env = RC.envelope_for(c)
    assert env["status"] == "BLOCKED" and env["pending"] and env["candidate_sha"] == SHA


def test_ready_only_with_a_passed_review_and_everything_else_passing():
    good = {"sha": SHA, "verdict": "PASS", "open_high_findings": 0, "reviewer": "secreview",
            "reviewed_at": "2026-10-12T04:10:00Z"}
    c = RC.candidate(_root(review=good))
    assert RC.ready(c) and RC.envelope_for(c)["status"] == "OK"
    assert RC.card_fields(c)["recommendation"].startswith("Authorise")
    bad = RC.candidate(_root(review={**good, "open_high_findings": 2}))
    assert not RC.ready(bad) and bad["security_review"]["state"] == "FAIL"
    other = RC.candidate(_root(review={**good, "sha": OLD}))
    assert other["security_review"]["state"] == "FAIL"


def test_failing_or_tampered_suite_evidence_is_not_a_pass():
    f = RC.candidate(_root(suite_status="failed", failing=3))
    assert f["suite"]["state"] == "FAIL" and f["integrity"]["state"] == "FAIL"
    t = RC.candidate(_root(tamper=True))
    assert t["integrity"]["state"] == "FAIL"
    assert any("does not match its pinned sha256" in p for p in t["integrity"]["problems"])


def test_no_rollback_target_and_deployed_detection():
    c = RC.candidate(_root(deployed=()))
    assert c["rollback_target"]["state"] == "UNKNOWN" and c["rollback_target"]["sha"] is None
    deployed = RC.candidate(_root(deployed=(OLD, SHA)))
    assert deployed["pending"] is False and deployed["latest_deployed"] == SHA
    by_record = RC.candidate(_root(evidence_names_candidate=True))
    assert by_record["pending"] is False      # a record-only commit on top of SHA ran
    assert RC.standalone_card(deployed) is None and RC.evidence(deployed) == []


def test_this_repository_has_no_undeployed_record_today():
    c = RC.candidate()
    recs = c.get("records") or []
    if c["pending"]:     # a candidate record was committed: its card must be complete
        assert len(RC.evidence(c)) == 4
    else:
        assert recs and c["latest_deployed"] and c["why"]


def test_inbox_attaches_release_evidence_to_the_deploy_decision():
    from brambleloop.app.command_center import approvals
    from brambleloop.core.db import Database

    db = Database(f"sqlite:///{_TMP}/inbox.sqlite")
    db.create_all()
    pending = RC.candidate(_root())
    real = RC.candidate
    RC.candidate = lambda root=None: pending
    try:
        out = approvals.inbox(db)
        assert out["release"]["pending"] and out["release"]["candidate_sha"] == SHA
        rel = [c for c in out["cards"] if c["card_id"] == f"release:{SHA[:12]}"]
        deploy = [c for c in out["cards"] if c["card_id"] == "gate:production_window"]
        if deploy:
            assert any(e["label"].startswith("Candidate SHA") for e in deploy[0]["evidence"])
            assert deploy[0]["release_candidate"]["sha"] == SHA and not rel
        else:
            assert len(rel) == 1 and rel[0]["executable"] is False and rel[0]["kind"] == "RELEASE"
            assert [e["label"] for e in rel[0]["evidence"]][0].startswith("Candidate SHA")
            assert approvals.card(db, f"release:{SHA[:12]}")["kind"] == "RELEASE"
    finally:
        RC.candidate = real


def test_approvals_view_renders_the_release_card():
    js = (ROOT / "src" / "brambleloop" / "app" / "command_center" / "static" / "js" / "views"
          / "approvals.js").read_text(encoding="utf-8")
    assert "function releaseCard(env)" in js and "releaseCard(data.release)" in js
    assert "evidenceList(items)" in js[js.index("function releaseCard"):]


def test_laura_briefing_view_matches_the_composer_format():
    """The phone view splits on briefing.compose's own section heads and footer, and finds
    record ids inside multi-id brackets ("[E3, E4]" from `_line`)."""
    import inspect

    from brambleloop.laura.agency import briefing

    src = inspect.getsource(briefing.compose)
    assert 'f"\\n{k}. {title}\\n"' in src, "section head format changed"
    assert 'Ask \\"expand decision 2\\"' in src, "footer format changed"
    assert "', '.join(refs)" in inspect.getsource(briefing._line)
    js = (ROOT / "src" / "brambleloop" / "app" / "command_center" / "static" / "js" / "views"
          / "laura.js").read_text(encoding="utf-8")
    assert "const SECTION_HEAD = /^(\\d{1,2})\\. (.+)$/;" in js
    assert '/^Ask "expand decision/' in js
    assert "matchAll(/\\b([EP]\\d+)\\b/g)" in js
    assert "innerHTML" not in js


if __name__ == "__main__":
    import time

    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        t0 = time.time()
        try:
            t()
            print(f"OK   {t.__name__} {time.time() - t0:.1f}s")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL {t.__name__} {type(exc).__name__} {str(exc)[:500]}")
    print(f"{len(tests) - failed}/{len(tests)} passing")
    sys.exit(1 if failed else 0)
