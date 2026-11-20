"""W4-ROLLBACK (F-380/F-381): every forward deploy rehearses its own rollback first.

`ops/deploy_guard.py rehearse-rollback` builds (never pushes) the rollback commit from the
candidate back to the commit production runs now and checks it like a real rollback;
`ops/deploy.sh` refuses the deploy when that way back would be refused."""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OPS = ROOT.parent / "ops"
sys.path.insert(0, str(OPS))

import deploy_guard as G  # noqa: E402

HIST = "brambleloop/release/DEPLOYED_HISTORY.json"


def _git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c",
                           "user.email=t@example.invalid", *args],
                          capture_output=True, text=True, check=True).stdout.strip()


def _commit(repo, msg, files):
    for rel, text in files.items():
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", msg)
    return _git(repo, "rev-parse", "HEAD")


def _hist(*shas):
    return json.dumps({"deployed": [{"sha": s} for s in shas]})


def _repo():
    repo = Path(tempfile.mkdtemp(prefix="rbreh-")) / "repo"
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    deployed = _commit(repo, "deployed", {"brambleloop/src/app.py": "v=1\n", HIST: _hist()})
    good = _commit(repo, "candidate records its predecessor",
                   {"brambleloop/src/app.py": "v=2\n", HIST: _hist(deployed)})
    _git(repo, "checkout", "-q", "-b", "other", deployed)
    bad = _commit(repo, "candidate forgot the predecessor", {"brambleloop/src/app.py": "v=3\n"})
    return repo, deployed, good, bad


def test_a_candidate_that_preserves_its_predecessor_has_an_executable_rollback():
    repo, deployed, good, _bad = _repo()
    try:
        out = G.rehearse_rollback(good, deployed, repo=repo)
        assert out["ok"] is True and out["verdict"] == "ALLOW", out
        assert out["pushed"] is False and out["to"] == deployed and out["rehearsal_commit"]
        # never referenced: no branch or tag points at the rehearsal object
        refs = _git(repo, "for-each-ref", "--format=%(objectname)")
        assert out["rehearsal_commit"] not in refs
    finally:
        shutil.rmtree(repo.parent, ignore_errors=True)


def test_a_candidate_without_its_predecessor_in_history_is_refused():
    repo, deployed, _good, bad = _repo()
    try:
        out = G.rehearse_rollback(bad, deployed, repo=repo)
        assert out["ok"] is False and out["verdict"] == "REFUSE"
        assert any("deployed history" in r for r in out["reasons"]), out
    finally:
        shutil.rmtree(repo.parent, ignore_errors=True)


def test_an_unknown_deployed_commit_is_refused_never_assumed():
    repo, _deployed, good, _bad = _repo()
    try:
        assert G.rehearse_rollback(good, None, repo=repo)["verdict"] == "REFUSE"
        assert G.rehearse_rollback(good, "f" * 40, repo=repo)["verdict"] == "REFUSE"
    finally:
        shutil.rmtree(repo.parent, ignore_errors=True)


def test_the_cli_exit_code_follows_the_verdict():
    repo, deployed, good, bad = _repo()
    try:
        ok = subprocess.run([sys.executable, str(OPS / "deploy_guard.py"), "rehearse-rollback",
                             "--candidate", good, "--deployed", deployed, "--repo", str(repo)],
                            capture_output=True, text=True)
        no = subprocess.run([sys.executable, str(OPS / "deploy_guard.py"), "rehearse-rollback",
                             "--candidate", bad, "--deployed", deployed, "--repo", str(repo)],
                            capture_output=True, text=True)
        assert ok.returncode == 0 and '"ALLOW"' in ok.stdout, ok.stderr
        assert no.returncode == 1 and '"REFUSE"' in no.stdout
    finally:
        shutil.rmtree(repo.parent, ignore_errors=True)


def test_deploy_sh_rehearses_after_the_guard_and_before_its_only_push():
    text = (OPS / "deploy.sh").read_text()
    guard = text.index('deploy_guard.py" check')
    rehearse = text.index('deploy_guard.py" rehearse-rollback')
    push = text.index('git -C "$top" push')
    assert guard < rehearse < push
    block = text[rehearse:push]
    assert "exit 1" in block and 'if [ -z "$rollback_to" ]' in text[guard:rehearse + 200]


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                traceback.print_exc()
                fails += 1
                print("FAIL", name, repr(e))
    sys.exit(1 if fails else 0)
