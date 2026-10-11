"""W4-PACKETREL (F-878): the launch packet cites the candidate's own release record.

`launch.packet._recorded_suite(repo_root, sha)` binds `release/RELEASE_<sha>.json` to the
candidate: by exact SHA, or by the candidate's exact deployable-tree digest with the record's
SHA an ancestor (the record-only commit on top of the suite's commit, the deploy guard's rule).
A bound record is checked by `ops.release_record.check_record`; a failing one is FAIL; no
bound record is UNKNOWN. It never falls back to a stale suite file from another commit.

Each test builds a throwaway git repository (no network, no shared state).

Run: cd brambleloop && PYTHONPATH=src python3 tests/test_w4_packetrel.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
for _k in ("RAILWAY_GIT_COMMIT_SHA", "BRAMBLELOOP_COMMIT", "GIT_COMMIT_SHA"):
    os.environ.pop(_k, None)  # no build identity: the filesystem fallback must not apply

from brambleloop.launch import packet as LP  # noqa: E402

RUN = "20261010T000000Z-1"


def _git(repo: Path, *args: str) -> str:
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.invalid")
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True,
                          text=True, env=env).stdout.strip()


def _repo() -> tuple[Path, Path]:
    top = Path(tempfile.mkdtemp(prefix="packetrel_"))
    _git(top, "init", "-q")
    root = top / "brambleloop"
    (root / "src" / "pkg").mkdir(parents=True)
    (root / "src" / "pkg" / "a.py").write_text("X = 1\n")
    (root / "requirements.lock").write_text("pkg==1\n")
    _git(top, "add", "-A")
    _git(top, "commit", "-q", "-m", "code")
    return top, root


def _record(top: Path, root: Path, *, eligible: bool = True) -> tuple[str, str]:
    """Write a record for HEAD on top of it (record-only commit). Returns (code, record)."""
    code = _git(top, "rev-parse", "HEAD")
    digest, how = LP._git_tree_digest(root, code)
    assert digest and how == "git", how
    rel = root / "release" / "suite_runs"
    rel.mkdir(parents=True, exist_ok=True)
    suite = {"run_id": RUN, "git_sha": code, "status": "passed", "scope": "full",
             "release_eligible": eligible, "tree": "clean", "tests_passing": 42,
             "suites_total": 3, "suites_failing": 0, "failing_suites": []}
    (rel / f"{RUN}.json").write_text(json.dumps(suite))
    (rel / f"{RUN}.log").write_text(f"RUN ID: {RUN}\nGIT SHA: {code}\n"
                                    "TOTAL PASSING: 42 ; suites failing: 0\n")
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()  # noqa: E731
    rec = {"kind": "brambleloop.release_record", "sha": code, "release_eligible": eligible,
           "source_tree_sha256": digest, "recorded_at": "2026-10-10T00:00:00Z",
           "suite_record": {"path": f"suite_runs/{RUN}.json", "sha256": sha(rel / f"{RUN}.json")},
           "suite_log": {"path": f"suite_runs/{RUN}.log", "sha256": sha(rel / f"{RUN}.log")}}
    (root / "release" / f"RELEASE_{code}.json").write_text(json.dumps(rec))
    _git(top, "add", "-A")
    _git(top, "commit", "-q", "-m", "release record")
    return code, _git(top, "rev-parse", "HEAD")


def test_record_only_commit_cites_its_release_record_by_tree_digest():
    top, root = _repo()
    code, cand = _record(top, root)
    rs = LP._recorded_suite(root, cand)
    assert rs["state"] == "PASS", rs
    assert rs["binding"] == "tree_digest+ancestor" and rs["record_sha"] == code
    assert rs["record_file"] == f"release/RELEASE_{code}.json"
    assert rs["release_eligible"] is True and rs["record_problems"] == []
    assert rs["suite"]["run_id"] == RUN and rs["suite"]["tests_passing"] == 42
    assert rs["suite"]["suites_failing"] == 0 and rs["suite"]["tree"] == "clean"
    assert rs["tree_sha256"] == LP._git_tree_digest(root, cand)[0]
    assert "suite_file" not in rs  # never the stale RUN_*_full_suite.json quote


def test_the_suite_commit_itself_binds_by_exact_sha():
    top, root = _repo()
    code, _cand = _record(top, root)
    rs = LP._recorded_suite(root, code)
    assert rs["state"] == "PASS" and rs["binding"] == "exact_sha", rs


def test_a_changed_tree_has_no_record_and_is_unknown():
    top, root = _repo()
    _record(top, root)
    (root / "src" / "pkg" / "a.py").write_text("X = 2\n")
    _git(top, "commit", "-qam", "change code")
    rs = LP._recorded_suite(root, _git(top, "rev-parse", "HEAD"))
    assert rs["state"] == "UNKNOWN" and rs["record_file"] is None, rs
    assert "no release record names" in rs["why"]


def test_no_record_and_unknown_sha_are_unknown_never_invented():
    top, root = _repo()
    rs = LP._recorded_suite(root, _git(top, "rev-parse", "HEAD"))
    assert rs["state"] == "UNKNOWN" and "no release record exists" in rs["why"], rs
    _record(top, root)
    rs = LP._recorded_suite(root, "f" * 40)
    assert rs["state"] == "UNKNOWN" and rs["record_file"] is None, rs
    rs = LP._recorded_suite(root, "not-a-sha")
    assert rs["state"] == "UNKNOWN", rs
    assert LP._recorded_suite(None, "f" * 40)["state"] == "UNKNOWN"


def test_a_tampered_or_ineligible_record_is_fail_with_its_problems():
    top, root = _repo()
    code, cand = _record(top, root, eligible=False)
    rs = LP._recorded_suite(root, cand)
    assert rs["state"] == "FAIL" and rs["record_problems"], rs
    top2, root2 = _repo()
    code2, cand2 = _record(top2, root2)
    (root2 / "release" / "suite_runs" / f"{RUN}.json").write_text("{}")
    rs2 = LP._recorded_suite(root2, cand2)
    assert rs2["state"] == "FAIL", rs2
    assert any("pinned sha256" in p for p in rs2["record_problems"]), rs2


def test_markdown_shows_the_release_record():
    top, root = _repo()
    code, cand = _record(top, root)
    p = {"candidate_sha": cand, "generated_at": "t", "verdict": "UNKNOWN", "verdict_rule": "r",
         "phase": {"phase": "shadow", "env": "shadow", "recorded_phase": "shadow",
                   "agree": True}, "products": [],
         "owner_queue": {"owner_actions": [], "state": "UNKNOWN"},
         "spend_limits": [], "recorded_suite": LP._recorded_suite(root, cand),
         "rollback_path": {}, "activation_steps": []}
    md = LP.render_markdown(p)
    assert f"RELEASE_{code}.json" in md and f"Suite run {RUN}" in md, md


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
