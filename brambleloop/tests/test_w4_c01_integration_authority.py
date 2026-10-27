"""F-711 Single Integration Authority: a worker cannot push onto, rewrite or delete an
integration branch; only the integrator role fast-forwards it, and lanes stay free."""
import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

OPS = Path(__file__).resolve().parents[2] / "ops"
sys.path.insert(0, str(OPS))
import deploy_guard as G  # noqa: E402
import integration_authority as IA  # noqa: E402

INTEG = "claude/w4-INTEG99"


def _git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), "-c", "user.name=t",
                           "-c", "user.email=t@e.invalid", *args],
                          capture_output=True, text=True, check=True).stdout.strip()


def _repo(with_module=True):
    base = Path(tempfile.mkdtemp(prefix="c01ia-"))
    origin, repo = base / "origin.git", base / "repo"
    subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    (repo / "ops" / "hooks").mkdir(parents=True)
    names = ["deploy_guard.py", "deployed_sha.py"] + (["integration_authority.py"]
                                                      if with_module else [])
    for n in names:
        shutil.copy(OPS / n, repo / "ops" / n)
    shutil.copy(OPS / "hooks" / "pre-push", repo / "ops" / "hooks" / "pre-push")
    os.chmod(repo / "ops" / "hooks" / "pre-push", 0o755)
    (repo / "f").write_text("1\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "init")
    _git(repo, "remote", "add", "origin", str(origin))
    _git(repo, "config", "core.hooksPath", "ops/hooks")
    return base, repo, origin


def _push(repo, *args, role=None):
    env = {k: v for k, v in os.environ.items() if k != IA.ROLE_ENV}
    if role:
        env[IA.ROLE_ENV] = role
    return subprocess.run(["git", "-C", str(repo), "push", "-q", "origin", *args],
                          env=env, capture_output=True, text=True)


def _remote(origin, branch):
    r = subprocess.run(["git", "--git-dir", str(origin), "rev-parse", "--verify", "--quiet",
                        f"refs/heads/{branch}"], capture_output=True, text=True)
    return r.stdout.strip() or None


def test_the_hook_holds_integration_branches_to_the_integrator():
    base, repo, origin = _repo()
    try:
        head = _git(repo, "rev-parse", "HEAD")
        # A worker's own lane: free.
        assert _push(repo, "HEAD:refs/heads/claude/w4-C01").returncode == 0
        # A worker pushing onto an integration branch: refused, the remote untouched.
        r = _push(repo, f"HEAD:refs/heads/{INTEG}")
        assert r.returncode != 0 and "only the integrator" in r.stderr, r.stderr
        assert _remote(origin, INTEG) is None
        # The integrator: allowed.
        assert _push(repo, f"HEAD:refs/heads/{INTEG}", role="integrator").returncode == 0
        assert _remote(origin, INTEG) == head
        # A fast-forward by the integrator: allowed.
        (repo / "f").write_text("2\n")
        _git(repo, "commit", "-qam", "two")
        two = _git(repo, "rev-parse", "HEAD")
        assert _push(repo, f"HEAD:refs/heads/{INTEG}", role="integrator").returncode == 0
        # A history rewrite, even by the integrator: refused.
        _git(repo, "reset", "-q", "--hard", head)
        (repo / "f").write_text("3\n")
        _git(repo, "commit", "-qam", "rewrite")
        r = _push(repo, "--force", f"HEAD:refs/heads/{INTEG}", role="integrator")
        assert r.returncode != 0 and "not a fast-forward" in r.stderr, r.stderr
        assert _remote(origin, INTEG) == two
        # Deleting it: refused.
        r = _push(repo, f":refs/heads/{INTEG}", role="integrator")
        assert r.returncode != 0 and "deleting an integration branch" in r.stderr, r.stderr
        assert _remote(origin, INTEG) == two
    finally:
        shutil.rmtree(base, ignore_errors=True)


def test_the_guard_refuses_when_the_rule_cannot_be_loaded():
    base, repo, origin = _repo(with_module=False)
    try:
        r = _push(repo, f"HEAD:refs/heads/{INTEG}", role="integrator")
        assert r.returncode != 0 and "authority check unavailable" in r.stderr, r.stderr
        assert _remote(origin, INTEG) is None
        assert _push(repo, "HEAD:refs/heads/claude/w4-lane").returncode == 0
    finally:
        shutil.rmtree(base, ignore_errors=True)


def test_decide_ref_unit_cases():
    z = IA.ZERO
    a = "a" * 40
    assert IA.is_integration_ref("refs/heads/claude/w4-INTEG8")
    assert IA.is_integration_ref("refs/heads/claude/w4-INTEG6-prep")
    assert not IA.is_integration_ref("refs/heads/claude/w4-SECREVIEW-INTEG7-24ada53")
    assert not IA.is_integration_ref("refs/heads/claude/w4-C01")
    assert IA.decide_ref("x", a, "refs/heads/claude/w4-C01", z, env={})["verdict"] == "ALLOW"
    out = IA.decide_ref("x", a, "refs/heads/claude/w4-INTEG8", "b" * 40,
                        env={IA.ROLE_ENV: "integrator"})
    # A remote commit this checkout does not hold: no fast-forward can be shown.
    assert out["verdict"] == "REFUSE" and "fetch first" in out["reasons"][0]
    # Through deploy_guard.pre_push, production behaviour is unchanged for other refs.
    out = G.pre_push([f"refs/heads/x {a} refs/heads/claude/w4-INTEG8 {z}"], env={},
                     checker=lambda *k, **kw: {"verdict": "ALLOW"})
    assert out["verdict"] == "REFUSE"
    out = G.pre_push([f"refs/heads/x {a} refs/heads/claude/w4-C01 {z}"], env={},
                     checker=lambda *k, **kw: {"verdict": "REFUSE"})
    assert out["verdict"] == "ALLOW"


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("OK  ", n)  # run_tests.sh counts lines beginning OK
