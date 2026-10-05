"""F-845 / F-846: a launch candidate is frozen only on exact, clean, release-eligible evidence.

Every refusal path of `scripts/freeze_candidate.py` is driven against a throwaway git
repository built in a temp directory, never this repository: no tag is created here and
nothing is pushed anywhere. One success path in the throwaway repository shows what a freeze
writes (local annotated tag, candidate record, defect ledger) so the refusals are refusals of
a mechanism that works.

Run: cd brambleloop && $PY tests/test_freeze_candidate.py
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import os
# Hermetic git: throwaway repositories must not inherit the machine's global git config (a
# global commit-signing requirement or helper would make every fixture commit fail).
os.environ["GIT_CONFIG_GLOBAL"] = os.devnull
os.environ["GIT_CONFIG_NOSYSTEM"] = "1"


ROOT = Path(__file__).resolve().parents[1]


def _mod():
    spec = importlib.util.spec_from_file_location("freeze_candidate",
                                                  ROOT / "scripts" / "freeze_candidate.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _git(repo, *args):
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    assert r.returncode == 0, (args, r.stderr)
    return r.stdout.strip()


def _suite(sha, **over):
    rec = {"git_sha": sha, "git_sha_at_end": sha, "release_eligible": True, "scope": "full",
           "status": "passed", "suites_failing": 0, "failing_suites": [],
           "tests_failing_reported": 0, "tests_passing": 5653, "tree": "clean"}
    rec.update(over)
    return rec


def _rehearsal(sha, **over):
    ev = {"kind": "shadow_rehearsal", "mode": "production", "head": sha, "tree_dirty": False,
          "complete": False, "outcomes": {"store.publish[shadow]": "REFUSED_AS_EXPECTED"},
          "blocking_defects": [{"key": "search_certificate_not_pass", "where": "x",
                                "detail": "stored verdict never PASS"}]}
    ev.update(over)
    return ev


class Repo:
    """A throwaway repository shaped like this one: brambleloop/research/final_build/."""

    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name)
        _git(self.path, "init", "-q")
        _git(self.path, "config", "user.email", "t@example.invalid")
        _git(self.path, "config", "user.name", "t")
        self.fb = self.path / "brambleloop" / "research" / "final_build"
        (self.fb / "evidence").mkdir(parents=True)
        (self.path / "brambleloop" / "src").mkdir(parents=True)
        (self.path / "brambleloop" / "src" / "code.py").write_text("x = 1\n")
        (self.fb / "closure_matrix.json").write_text(json.dumps({
            "basis": {"mapping": {}}, "summary": {"launch_critical_open": 300},
            "matrix": [{"uid": "F-1", "launch_class": "LAUNCH-CRITICAL", "defect": "wrong",
                        "completion": "OPEN"}]}))
        self.commit("base")

    def commit(self, msg):
        _git(self.path, "add", "-A")
        _git(self.path, "commit", "-q", "-m", msg)
        return _git(self.path, "rev-parse", "HEAD")

    def evidence(self, sha, *, suite=None, rehearsal=None, commit=True):
        (self.fb / f"RUN_{sha[:7]}_full_suite.json").write_text(
            json.dumps(suite if suite is not None else _suite(sha)))
        (self.fb / "evidence" / f"shadow_rehearsal_{sha[:7]}_x.json").write_text(
            json.dumps(rehearsal if rehearsal is not None else _rehearsal(sha)))
        return self.commit("evidence") if commit else None

    def close(self):
        self.tmp.cleanup()


def _refusals(repo, sha="HEAD", **kw):
    out = _mod().freeze(repo.path, sha, fb=repo.fb, **kw)
    assert out["frozen"] is False
    assert _git(repo.path, "tag", "-l") == "", "a refused freeze created a tag"
    assert not list(repo.fb.glob("CANDIDATE_*.json")) and not list(repo.fb.glob("DEFECT_*"))
    return " | ".join(out["refusals"])


def test_a_suite_record_for_a_different_sha_is_refused():
    repo = Repo()
    try:
        base = _git(repo.path, "rev-parse", "HEAD")
        repo.evidence(base)            # evidence commit moves HEAD past the suite's SHA
        why = _refusals(repo)
        assert "no release-eligible suite record for exactly" in why, why
    finally:
        repo.close()


def test_a_suite_record_that_is_not_release_eligible_is_refused():
    for over in ({"release_eligible": False}, {"scope": "filtered"}, {"suites_failing": 1},
                 {"tests_failing_reported": 2}, {"tree": "dirty"}, {"status": "failed"},
                 {"tests_passing": 0}):
        repo = Repo()
        try:
            sha = _git(repo.path, "rev-parse", "HEAD")
            suite = repo.fb / "suite.json"
            suite.write_text(json.dumps(_suite(sha, **over)))
            reh = repo.fb / "reh.json"
            reh.write_text(json.dumps(_rehearsal(sha)))
            # Evidence is outside the tree check here: write it to an ignored path.
            (repo.path / ".git" / "info" / "exclude").write_text("suite.json\nreh.json\n")
            why = _refusals(repo, suite=suite, rehearsal=reh)
            assert "no release-eligible suite record" in why, (over, why)
        finally:
            repo.close()


def test_a_dirty_tree_is_refused():
    repo = Repo()
    try:
        base = _git(repo.path, "rev-parse", "HEAD")
        sha = repo.evidence(base, suite=_suite("0" * 40))   # placeholder; rewritten below
        (repo.fb / f"RUN_{base[:7]}_full_suite.json").unlink()
        (repo.fb / f"RUN_{sha[:7]}_full_suite.json").write_text(json.dumps(_suite(sha)))
        why = _refusals(repo)
        assert "working tree not clean" in why, why
    finally:
        repo.close()


def test_a_sha_that_is_not_head_or_not_a_commit_is_refused():
    repo = Repo()
    try:
        base = _git(repo.path, "rev-parse", "HEAD")
        repo.evidence(base)
        why = _refusals(repo, sha=base)
        assert "is not the checked-out HEAD" in why, why
        assert "is not a commit" in _refusals(repo, sha="deadbeef" * 5)
    finally:
        repo.close()


def test_missing_fast_or_code_stale_rehearsal_is_refused():
    repo = Repo()
    try:
        sha = _git(repo.path, "rev-parse", "HEAD")
        suite, reh = repo.fb / "suite.json", repo.fb / "reh.json"
        (repo.path / ".git" / "info" / "exclude").write_text("suite.json\nreh.json\n")
        suite.write_text(json.dumps(_suite(sha)))
        why = _refusals(repo, suite=suite, rehearsal=repo.fb / "absent.json")
        assert "no shadow-rehearsal evidence" in why, why
        reh.write_text(json.dumps(_rehearsal(sha, mode="fast")))
        assert "not a production-mode shadow rehearsal" in _refusals(repo, suite=suite,
                                                                      rehearsal=reh)
        reh.write_text(json.dumps(_rehearsal(sha, tree_dirty=True)))
        assert "dirty tree" in _refusals(repo, suite=suite, rehearsal=reh)
        # Rehearsed on an ancestor, then code changed: the rehearsal is about other code.
        (repo.path / "brambleloop" / "src" / "code.py").write_text("x = 2\n")
        new = repo.commit("code change")
        suite.write_text(json.dumps(_suite(new)))
        reh.write_text(json.dumps(_rehearsal(sha)))
        why = _refusals(repo, suite=suite, rehearsal=reh)
        assert "code changed since" in why and "brambleloop/src/code.py" in why, why
    finally:
        repo.close()


def test_an_existing_tag_and_a_matrix_without_the_summary_are_refused():
    repo = Repo()
    try:
        sha = _git(repo.path, "rev-parse", "HEAD")
        suite, reh = repo.fb / "suite.json", repo.fb / "reh.json"
        (repo.path / ".git" / "info" / "exclude").write_text("suite.json\nreh.json\n")
        suite.write_text(json.dumps(_suite(sha)))
        reh.write_text(json.dumps(_rehearsal(sha)))
        _git(repo.path, "tag", "-a", f"final-candidate-{sha[:7]}", "-m", "earlier")
        out = _mod().freeze(repo.path, "HEAD", fb=repo.fb, suite=suite, rehearsal=reh)
        assert out["frozen"] is False and any("already exists" in r for r in out["refusals"])
        _git(repo.path, "tag", "-d", f"final-candidate-{sha[:7]}")
        (repo.fb / "closure_matrix.json").write_text(json.dumps({"summary": {}, "matrix": []}))
        repo.commit("matrix without completion")
        new = _git(repo.path, "rev-parse", "HEAD")
        suite.write_text(json.dumps(_suite(new)))
        reh.write_text(json.dumps(_rehearsal(new)))
        assert "lacks the computed completion summary" in _refusals(repo, suite=suite,
                                                                    rehearsal=reh)
    finally:
        repo.close()


def test_exact_clean_eligible_evidence_freezes_locally_and_opens_the_ledger():
    """The mechanism the refusals guard: a local annotated tag, a candidate, a ledger."""
    repo = Repo()
    try:
        base = _git(repo.path, "rev-parse", "HEAD")
        # Rehearsed on base; the evidence commit changes no code, so it still binds.
        (repo.fb / "evidence" / "shadow_rehearsal_b_x.json").write_text(
            json.dumps(_rehearsal(base)))
        sha = repo.commit("rehearsal evidence")
        (repo.fb / f"RUN_{sha[:7]}_full_suite.json").write_text(json.dumps(_suite(sha)))
        sha = repo.commit("suite record")      # moves HEAD again: suite is now for HEAD~1
        assert "no release-eligible suite record" in _refusals(repo)
        suite = repo.fb / "suite.json"
        (repo.path / ".git" / "info" / "exclude").write_text("suite.json\n")
        suite.write_text(json.dumps(_suite(sha)))
        dry = _mod().freeze(repo.path, "HEAD", fb=repo.fb, suite=suite, dry_run=True)
        assert dry["frozen"] is False and dry["refusals"] == []
        assert _git(repo.path, "tag", "-l") == ""
        out = _mod().freeze(repo.path, "HEAD", fb=repo.fb, suite=suite)
        assert out["frozen"] is True, out
        tag = f"final-candidate-{sha[:7]}"
        assert _git(repo.path, "tag", "-l") == tag
        assert _git(repo.path, "cat-file", "-t", tag) == "tag"          # annotated
        assert _git(repo.path, "rev-parse", f"{tag}^{{commit}}") == sha
        cand = json.loads((repo.fb / f"CANDIDATE_{sha[:7]}.json").read_text())
        assert cand["candidate"] == sha and cand["pushed"] is False
        assert cand["matrix"]["launch_critical_open"] == 300
        assert cand["rehearsal"]["binding"].startswith("ancestor")
        ledger = json.loads((repo.fb / f"DEFECT_LEDGER_{sha[:7]}.json").read_text())
        keys = {d["key"] for d in ledger["defects"]}
        assert ledger["status"] == "open" and {"search_certificate_not_pass", "F-1"} <= keys
    finally:
        repo.close()


if __name__ == "__main__":
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
