"""F-459 / F-460: the local merge queue integrates one lane at a time behind the integration
checklist, refuses conflicts, failed checks, a moved target and protected branches, and never
pushes."""
import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import os
import subprocess
import sys
import tempfile
from pathlib import Path

OPS = Path(__file__).resolve().parents[2] / "ops"
sys.path.insert(0, str(OPS))
import integrate as I  # noqa: E402

CONTRACT = "brambleloop/tests/test_w4_fmbatch1_contracts.py"


def _git(repo, *a):
    return subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c",
                           "user.email=t@example.invalid", *a], capture_output=True, text=True,
                          check=True).stdout.strip()


def _repo():
    base = Path(tempfile.mkdtemp(prefix="fmb1-int-"))
    repo = base / "r"
    subprocess.run(["git", "init", "-q", "-b", "integration", str(repo)], check=True)
    (repo / "brambleloop" / "tests").mkdir(parents=True)
    (repo / CONTRACT).write_text("import sys; sys.exit(0)\n")
    (repo / "a.txt").write_text("base\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    I.QUEUE = base / "MERGE_QUEUE.json"
    return base, repo


def _lane(repo, name, filename, text, *, extra_test=None, rc=0):
    _git(repo, "checkout", "-q", "-b", name, "integration")
    (repo / filename).write_text(text)
    if extra_test:
        (repo / extra_test).write_text(f"import sys; sys.exit({rc})\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", name)
    _git(repo, "checkout", "-q", "integration")


def test_a_lane_is_merged_behind_the_checklist_and_nothing_is_pushed():
    base, repo = _repo()
    _lane(repo, "lane-a", "b.txt", "a\n", extra_test="brambleloop/tests/test_a.py")
    before = _git(repo, "rev-parse", "integration")
    I.enqueue("lane-a", "lane-a", ["brambleloop/tests/test_a.py"])
    out = I.next_lane(target="integration", repo=repo)
    assert out["merged"] is True and out["base"] == before, out
    assert _git(repo, "rev-parse", "integration") == out["commit"]
    assert _git(repo, "rev-parse", f"{out['commit']}^1") == before
    assert [c["check"] for c in out["checks"]] == [CONTRACT, "brambleloop/tests/test_a.py"]
    assert _git(repo, "remote") == ""                                  # no remote, no push
    assert "never pushes" in out["next_step"]
    assert I._load()["queue"] == []


def test_a_failed_check_or_a_conflict_leaves_the_target_untouched():
    base, repo = _repo()
    _lane(repo, "lane-b", "b.txt", "b\n", extra_test="brambleloop/tests/test_b.py", rc=1)
    before = _git(repo, "rev-parse", "integration")
    I.enqueue("lane-b", "lane-b", ["brambleloop/tests/test_b.py"])
    out = I.next_lane(target="integration", repo=repo)
    assert out["merged"] is False and "checklist failed" in out["why"]
    assert _git(repo, "rev-parse", "integration") == before
    assert I._load()["queue"][0]["lane"] == "lane-b"                   # stays queued
    I._save({"queue": [], "done": []})
    _lane(repo, "lane-c", "a.txt", "c\n")
    (repo / "a.txt").write_text("conflicting\n")
    _git(repo, "commit", "-q", "-am", "target moves a.txt")
    before = _git(repo, "rev-parse", "integration")
    I.enqueue("lane-c", "lane-c")
    out = I.next_lane(target="integration", repo=repo)
    assert out["merged"] is False and "conflict" in out["why"]
    assert _git(repo, "rev-parse", "integration") == before


def test_a_target_that_moves_during_the_checks_is_not_overwritten():
    base, repo = _repo()
    _lane(repo, "lane-d", "d.txt", "d\n")
    I.enqueue("lane-d", "lane-d")
    real = I._checklist

    def racing(wt, tests, python):
        (repo / "z.txt").write_text("someone else\n")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-q", "-m", "another writer")
        return real(wt, tests, python)

    I._checklist = racing
    try:
        out = I.next_lane(target="integration", repo=repo)
    finally:
        I._checklist = real
    assert out["merged"] is False and "moved while the checks ran" in out["why"]
    assert _git(repo, "log", "-1", "--format=%s", "integration") == "another writer"


def test_protected_targets_are_refused():
    base, repo = _repo()
    for t in ("claude/repository-setup-nc9x6o", "main", "refs/remotes/origin/x"):
        try:
            I.next_lane(target=t, repo=repo)
            raise AssertionError(f"{t} was accepted")
        except I.Refused as exc:
            assert "protected" in str(exc)


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("OK  ", n)  # run_tests.sh counts lines beginning OK
