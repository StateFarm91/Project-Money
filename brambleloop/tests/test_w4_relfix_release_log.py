"""The release record ships a suite-level log summary and keeps the full log outside the image.

Owner decision 2026-10-11 (option 1). `release/` is copied into the image and
test_cert_claude_independence refuses any release file naming a Claude-session marker, while
runtime test names legitimately contain "heartbeat" (job/worker/scheduler heartbeats). So
`record_release` writes the unindented summary (run id, SHA, one line per suite, totals) into
release/, the full per-test log into research/release_evidence/ (not copied by the Dockerfile),
pins both by sha256, and the deploy guard verifies the full log against its pin at the
candidate. That security test is unchanged; these tests hold the mechanism.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import test_deploy_guard as T  # installs the temp sandbox and the hermetic git env
from test_deploy_guard import G

ROOT = Path(__file__).resolve().parents[1]


def _record_and_load(repo: Path, sha: str) -> tuple[str, dict]:
    head = T._record(repo, sha)
    _p, rec = T._tracked(repo)
    return head, rec


def test_record_writes_a_summary_into_release_and_the_full_log_outside_it():
    repo, s = T._repo_with_suite()
    head, rec = _record_and_load(repo, s["C"])
    summary = (repo / "release" / rec["suite_log"]["path"]).read_bytes()
    full = (repo / rec["full_log"]["path"]).read_bytes()
    assert rec["full_log"]["path"].startswith(G.FULL_LOG_DIR + "/")
    assert hashlib.sha256(summary).hexdigest() == rec["suite_log"]["sha256"]
    assert hashlib.sha256(full).hexdigest() == rec["full_log"]["sha256"]
    text = summary.decode()
    assert all(ln and not ln[0].isspace() for ln in text.splitlines()), "summary is unindented"
    for need in (f"GIT SHA: {s['C']}", "RUN ID: ", "TOTAL PASSING: 100"):
        assert need in text, need
    assert "   OK" in full.decode() and "   OK" not in text, "per-test lines live in the full log"
    assert T._check(repo, head, s["B"])["verdict"] == "ALLOW"


def test_a_tampered_or_missing_full_log_refuses_the_release():
    repo, s = T._repo_with_suite()
    head, rec = _record_and_load(repo, s["C"])
    full = repo / rec["full_log"]["path"]
    full.write_bytes(full.read_bytes() + b"   OK   test_forged\n")
    tampered = T._commit(repo, "T (tamper full log)")
    out = T._check(repo, tampered, s["B"])
    assert out["verdict"] == "REFUSE" and any("full log" in r and "sha256" in r
                                              for r in out["reasons"]), out
    full.unlink()
    gone = T._commit(repo, "G (drop full log)")
    out = T._check(repo, gone, s["B"])
    assert out["verdict"] == "REFUSE" and any("full log" in r and "gone" in r
                                              for r in out["reasons"]), out


def test_the_summary_carries_no_session_marker_and_paths_become_repo_relative():
    repo = Path("/work/x/.claude/worktrees/lane")
    raw = (f"RUN ID: r1\nGIT SHA: {'a' * 40}\n== tests/test_scheduler.py\n"
           f"   OK   test_a_heartbeat_extends_only_the_holders_lease\n"
           f"   {repo}/brambleloop/tests/test_x.py:1: SAWarning: something\n"
           "TOTAL PASSING: 2 ; suites failing: 0\n").encode()
    full = G.portable_log(raw, repo)
    assert str(repo) not in full.decode() and "<repo>/brambleloop/tests/test_x.py" in full.decode()
    summary = G.summary_log(full).decode().lower()
    for marker in G.SESSION_MARKERS:
        assert marker not in summary, marker
    assert "total passing: 2" in summary and "== tests/test_scheduler.py" in summary


def test_the_shipped_release_directory_holds_only_summaries_with_pinned_full_logs():
    records = sorted((ROOT / "release").glob("RELEASE_*.json"))
    assert records, "release/ holds no release record"
    for p in records:
        rec = json.loads(p.read_text())
        ref = rec.get("full_log")
        assert isinstance(ref, dict), (p.name, "record has no out-of-image full log")
        data = (ROOT / ref["path"]).read_bytes()
        assert hashlib.sha256(data).hexdigest() == ref["sha256"], p.name
        assert not ref["path"].startswith("release/"), "the full log must stay out of the image"
    docker = (ROOT / "Dockerfile").read_text()
    assert "COPY research" not in docker


if __name__ == "__main__":
    import sys
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, repr(e))
    sys.exit(1 if fails else 0)
