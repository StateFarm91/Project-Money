"""The deploy guard is on the deploy path, not beside it (F-461).

A push to the production branch is the deploy. These tests drive the guard's pre-push
decision with injected checkers and status readers, run the real hook and `ops/deploy.sh`
against throwaway repositories with a local bare "origin", and read the operator documents.
Nothing here deploys, pushes to a real remote, or makes a network call.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
OPS = REPO_ROOT / "ops"
sys.path.insert(0, str(OPS))

import deploy_guard as G  # noqa: E402
import deployed_sha as D  # noqa: E402

# Hermetic git: throwaway repositories must not inherit the machine's global git config (a
# global commit-signing requirement or helper would make every fixture commit fail).
os.environ["GIT_CONFIG_GLOBAL"] = os.devnull
os.environ["GIT_CONFIG_NOSYSTEM"] = "1"


SHA_A = "a" * 40
SHA_B = "b" * 40


def _line(remote_ref: str, local: str = SHA_A) -> str:
    return f"refs/heads/work {local} {remote_ref} {SHA_B}"


def _allow(candidate, deployed, **kw):
    return {"verdict": "ALLOW", "candidate": candidate, "deployed": deployed, "reasons": []}


def _refuse(candidate, deployed, **kw):
    return {"verdict": "REFUSE", "candidate": candidate, "deployed": deployed,
            "reasons": ["not a descendant"]}


def test_a_push_to_another_branch_is_not_a_deploy_and_is_not_checked():
    calls = []
    out = G.pre_push([_line("refs/heads/claude/fb4-OPS")],
                     checker=lambda *a, **k: calls.append(a) or _refuse(*a))
    assert out["verdict"] == "ALLOW" and not calls
    assert out["decisions"][0]["verdict"] == "NOT_A_DEPLOY"


def test_a_push_to_production_runs_the_guard_with_the_deployed_commit():
    seen = []

    def checker(candidate, deployed, **kw):
        seen.append((candidate, deployed))
        return _allow(candidate, deployed)

    out = G.pre_push([_line(G.PRODUCTION_REF)], env={G.DEPLOYED_ENV: SHA_B}, checker=checker)
    assert out["verdict"] == "ALLOW" and seen == [(SHA_A, SHA_B)]
    assert out["decisions"][0]["deployed_source"] == G.DEPLOYED_ENV
    out = G.pre_push([_line(G.PRODUCTION_REF)], env={G.DEPLOYED_ENV: SHA_B}, checker=_refuse)
    assert out["verdict"] == "REFUSE"


def test_one_refused_ref_refuses_the_whole_push():
    out = G.pre_push([_line("refs/heads/other"), _line(G.PRODUCTION_REF)],
                     env={G.DEPLOYED_ENV: SHA_B}, checker=_refuse)
    assert out["verdict"] == "REFUSE"


def test_the_deployed_commit_comes_from_production_status_and_unknown_refuses():
    status = {"build": {"commit": SHA_B, "known": True}}
    dep, source = D.deployed_commit(env={}, fetch=lambda url: status)
    assert dep == SHA_B and source == "production /api/status"
    dep, _ = D.deployed_commit(env={}, fetch=lambda url: {"build": {"commit": "unknown",
                                                                     "known": False}})
    assert dep is None

    def down(url):
        raise OSError("unreachable")

    assert D.deployed_commit(env={}, fetch=down)[0] is None
    assert D.deployed_commit(env={D.DEPLOYED_ENV: SHA_A}, fetch=down) == (SHA_A, D.DEPLOYED_ENV)
    # The guard itself never asks production: nothing supplied is unknown, and REFUSE.
    seen = []
    out = G.pre_push([_line(G.PRODUCTION_REF)], env={},
                     checker=lambda c, d, **k: seen.append(d) or _allow(c, d))
    assert out["verdict"] == "REFUSE", "an unknown deployed commit was allowed"
    assert seen == [None]


def test_deleting_the_production_branch_is_refused():
    out = G.pre_push([_line(G.PRODUCTION_REF, local=G.ZERO)], checker=_allow)
    assert out["verdict"] == "REFUSE"


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c",
                           "user.email=t@example.invalid", *args],
                          capture_output=True, text=True, check=check)


def _scratch_repo() -> tuple[Path, Path]:
    """A repo containing this checkout's ops/ scripts, with a local bare origin."""
    base = Path(tempfile.mkdtemp(prefix="deploypath-"))
    origin, repo = base / "origin.git", base / "repo"
    subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    (repo / "ops" / "hooks").mkdir(parents=True)
    for name in ("deploy_guard.py", "deployed_sha.py", "deploy.sh", "install_hooks.sh"):
        (repo / "ops" / name).write_bytes((OPS / name).read_bytes())
    (repo / "ops" / "hooks" / "pre-push").write_bytes((OPS / "hooks" / "pre-push").read_bytes())
    os.chmod(repo / "ops" / "hooks" / "pre-push", 0o755)
    (repo / "README").write_text("x\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "init")
    _git(repo, "remote", "add", "origin", str(origin))
    return repo, origin


def _remote_has(origin: Path, branch: str) -> bool:
    r = subprocess.run(["git", "--git-dir", str(origin), "rev-parse", "--verify", "--quiet",
                        f"refs/heads/{branch}"], capture_output=True, text=True)
    return r.returncode == 0


def test_the_installed_hook_refuses_an_unproven_push_to_production_and_passes_others():
    repo, origin = _scratch_repo()
    r = subprocess.run(["sh", "ops/install_hooks.sh"], cwd=repo, capture_output=True, text=True)
    assert r.returncode == 0 and "ops/hooks" in r.stdout, r.stderr
    env = dict(os.environ, **{G.DEPLOYED_ENV: _git(repo, "rev-parse", "HEAD").stdout.strip()})
    r = subprocess.run(["git", "push", "-q", "origin", f"HEAD:refs/heads/{G.PRODUCTION_BRANCH}"],
                       cwd=repo, env=env, capture_output=True, text=True)
    assert r.returncode != 0, "an unproven push reached the production branch"
    assert "REFUSE" in r.stderr and "suite run record" in r.stderr
    assert not _remote_has(origin, G.PRODUCTION_BRANCH)
    r = subprocess.run(["git", "push", "-q", "origin", "HEAD:refs/heads/claude/work"],
                       cwd=repo, env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert _remote_has(origin, "claude/work")


def test_deploy_sh_pushes_nothing_when_the_guard_refuses():
    repo, origin = _scratch_repo()
    env = dict(os.environ, **{G.DEPLOYED_ENV: "f" * 40})     # not a commit here: REFUSE
    r = subprocess.run(["sh", "ops/deploy.sh"], cwd=repo, env=env, capture_output=True,
                       text=True)
    assert r.returncode == 1 and "REFUSED" in r.stderr, (r.stdout, r.stderr)
    assert not _remote_has(origin, G.PRODUCTION_BRANCH)
    head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    r = subprocess.run(["sh", "ops/deploy.sh", "--deployed", head], cwd=repo,
                       env=dict(os.environ), capture_output=True, text=True)
    assert r.returncode == 1, "no suite record, still refused"
    assert not _remote_has(origin, G.PRODUCTION_BRANCH)


def test_deploy_sh_runs_the_guard_before_its_only_push():
    text = (OPS / "deploy.sh").read_text()
    guard, push = text.index("deploy_guard.py\" check"), text.index("git -C \"$top\" push")
    code = [ln for ln in text.splitlines() if not ln.lstrip().startswith("#")]
    assert guard < push and sum(" push " in ln for ln in code) == 1
    assert "exit 1" in text[guard:push]
    assert G.PRODUCTION_BRANCH in text


def test_the_operator_loop_and_the_resume_manifest_carry_the_step():
    heartbeat = (OPS / "HEARTBEAT_PROMPT.md").read_text()
    manifest = (ROOT / "research" / "final_build" / "FINAL_BUILD_RESUME_MANIFEST.md").read_text()
    for doc in (heartbeat, manifest):
        assert "ops/deploy.sh" in doc and "install_hooks.sh" in doc and "deploy_guard" in doc
    assert f"git push -u origin {G.PRODUCTION_BRANCH}" not in heartbeat, \
        "the heartbeat still pushes to production around the guard"


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                traceback.print_exc()
                fails += 1
                print("FAIL", name, repr(e))
    print(f"\n{'PASS' if not fails else 'FAIL'}: {fails} failing")
    sys.exit(1 if fails else 0)
