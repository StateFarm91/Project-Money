"""The deploy guard refuses a rollback and an unproven candidate, and never deploys (F-461).

End to end on a throwaway repository: a real `run_tests.sh` full run over 100 trivial suites (the
script's own discovery floor) writes a real run record, and the guard is asked about commits
that are and are not descendants of the "deployed" one. No production call, no deploy.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(REPO_ROOT / "ops"))

import deploy_guard as G  # noqa: E402

# Hermetic git: throwaway repositories must not inherit the machine's global git config (a
# global commit-signing requirement or helper would make every fixture commit fail).
os.environ["GIT_CONFIG_GLOBAL"] = os.devnull
os.environ["GIT_CONFIG_NOSYSTEM"] = "1"



def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c",
                           "user.email=t@example.invalid", *args],
                          capture_output=True, text=True, check=True).stdout.strip()


def _commit(repo: Path, msg: str) -> str:
    (repo / "history.txt").write_text(((repo / "history.txt").read_text()
                                       if (repo / "history.txt").exists() else "") + msg + "\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", msg)
    return _git(repo, "rev-parse", "HEAD")


_BUILT: dict[bool, tuple[Path, dict]] = {}


def _repo_with_suite(green: bool = True) -> tuple[Path, dict]:
    """A private copy of a repo A - B - C(HEAD, suite-run) with a side branch S off A.

    The real full run is paid once per colour and each test gets its own copy to mutate.
    """
    if green not in _BUILT:
        _BUILT[green] = _build(green)
    src, shas = _BUILT[green]
    dst = Path(tempfile.mkdtemp(prefix="deployguard-copy-")) / "repo"
    shutil.copytree(src, dst, symlinks=True)
    return dst, shas


def _build(green: bool) -> tuple[Path, dict]:
    repo = Path(tempfile.mkdtemp(prefix="deployguard-"))
    (repo / "tests").mkdir()
    shutil.copy(ROOT / "run_tests.sh", repo / "run_tests.sh")
    for i in range(100):
        (repo / "tests" / f"test_s{i:03d}.py").write_text('print("OK   test_trivial")\n')
    if not green:
        (repo / "tests" / "test_s000.py").write_text('import sys\nprint("FAIL x")\nsys.exit(1)\n')
    (repo / ".gitignore").write_text("artifacts/\n")
    _git(repo, "init", "-q", "-b", "main")
    shas = {"A": _commit(repo, "A")}
    _git(repo, "checkout", "-q", "-b", "side")
    shas["S"] = _commit(repo, "S")
    _git(repo, "checkout", "-q", "main")
    shas["B"] = _commit(repo, "B")
    shas["C"] = _commit(repo, "C")
    knobs = ("SUITES", "REQUIRE_CLEAN", "THEN_FULL", "ALLOW_PARALLEL", "SUITE_RECORD_DIR")
    env = {k: v for k, v in os.environ.items() if k not in knobs}
    env.update(PY=sys.executable, JOBS="8", REQUIRE_CLEAN="1")
    r = subprocess.run(["bash", str(repo / "run_tests.sh")], capture_output=True, text=True,
                       env=env, timeout=300)
    shas["_run"] = r
    return repo, shas


def _check(repo: Path, candidate: str, deployed: str | None) -> dict:
    return G.check(candidate, deployed, repo=repo, record_dir=repo / "artifacts" / "suite_runs",
                   log_base=repo)


def test_a_green_full_clean_run_on_a_descendant_of_production_is_allowed():
    repo, s = _repo_with_suite()
    try:
        assert s["_run"].returncode == 0, s["_run"].stdout[-2000:] + s["_run"].stderr
        rec = G.latest_suite(repo / "artifacts" / "suite_runs", sha=s["C"])
        assert rec and rec["release_eligible"] is True and rec["scope"] == "full"
        assert rec["tests_passing"] == 100 and rec["suites_total"] == 100
        out = _check(repo, s["C"], s["B"])
        assert out["verdict"] == "ALLOW", out
        assert out["suite_run"]["run_id"] == rec["run_id"]
        assert _check(repo, s["C"], s["C"])["verdict"] == "ALLOW", "redeploying the same commit"
    finally:
        shutil.rmtree(repo, ignore_errors=True)


def test_a_candidate_that_is_not_a_descendant_of_production_is_refused_as_a_rollback():
    repo, s = _repo_with_suite()
    try:
        # C is proven, but production runs S, which C's history does not contain.
        out = _check(repo, s["C"], s["S"])
        assert out["verdict"] == "REFUSE"
        assert any("not a descendant" in r and "roll production back" in r for r in out["reasons"])
        # An older commit than production is refused the same way (and has no suite record).
        old = _check(repo, s["B"], s["C"])
        assert old["verdict"] == "REFUSE"
        assert any("not a descendant" in r for r in old["reasons"])
    finally:
        shutil.rmtree(repo, ignore_errors=True)


def test_unknown_or_foreign_deployed_commit_is_refused_not_assumed():
    repo, s = _repo_with_suite()
    try:
        assert any("deployed commit unknown" in r for r in _check(repo, s["C"], None)["reasons"])
        foreign = _check(repo, s["C"], "0" * 40)
        assert foreign["verdict"] == "REFUSE"
        assert any("not in this repository" in r for r in foreign["reasons"])
    finally:
        shutil.rmtree(repo, ignore_errors=True)


def test_a_missing_or_red_suite_record_is_refused():
    repo, s = _repo_with_suite(green=False)
    try:
        assert s["_run"].returncode == 1
        red = _check(repo, s["C"], s["B"])
        assert red["verdict"] == "REFUSE"
        assert any("not release-eligible" in r and "failed" in r for r in red["reasons"]), red
        for p in (repo / "artifacts" / "suite_runs").glob("*.json"):
            p.unlink()
        missing = _check(repo, s["C"], s["B"])
        assert any("no suite run record" in r for r in missing["reasons"]), missing
    finally:
        shutil.rmtree(repo, ignore_errors=True)


def test_a_record_whose_log_contradicts_it_or_is_gone_is_refused():
    repo, s = _repo_with_suite()
    try:
        rec = G.latest_suite(repo / "artifacts" / "suite_runs", sha=s["C"])
        log = repo / rec["log"]
        text = log.read_text()
        log.write_text(re.sub(r"suites failing: 0", "suites failing: 3", text))
        out = _check(repo, s["C"], s["B"])
        assert out["verdict"] == "REFUSE" and any("suites failing: 3" in r
                                                  for r in out["reasons"]), out
        log.unlink()
        gone = _check(repo, s["C"], s["B"])
        assert any("log" in r and "gone" in r for r in gone["reasons"]), gone
    finally:
        shutil.rmtree(repo, ignore_errors=True)


def test_latest_suite_is_a_file_query_and_the_cli_exit_code_is_the_verdict():
    repo, s = _repo_with_suite()
    try:
        recs = repo / "artifacts" / "suite_runs"
        extra = dict(G.latest_suite(recs))
        extra.update(run_id="zzz", started_utc="2999-01-01T00:00:00Z", release_eligible=False)
        (recs / "zzz.json").write_text(json.dumps(extra))
        assert G.latest_suite(recs)["run_id"] == "zzz"
        assert G.latest_suite(recs, eligible_only=True)["run_id"] != "zzz"
        assert G.main(["latest-suite", "--records", str(recs), "--sha", "f" * 40]) == 1
    finally:
        shutil.rmtree(repo, ignore_errors=True)


def test_the_guard_contains_no_deploy_path():
    src = (REPO_ROOT / "ops" / "deploy_guard.py").read_text()
    code = src.split('"""', 2)[2]                                  # past the docstring
    for forbidden in ("railway", "requests", "urllib", "http.client", "socket", "os.system",
                      "shell=True"):
        assert forbidden not in code.lower(), f"deploy_guard.py references {forbidden!r}"
    calls = re.findall(r'subprocess\.run\(\[\s*"([^"]+)"', code)
    assert calls == ["git"], calls


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
