"""W4-FMBATCH1: F-381 Rollback First-Class -- containment and rollback by severity.

F-381: "Every material autonomous deployment preserves a known-good predecessor and an
executable rollback/recovery path. Detected regression triggers containment and rollback
according to severity." The predecessor and the path were already proven (W4-ROLLBACK,
tests/test_w4_rollback_rehearsal.py). These tests pin the missing half: the post-deploy
readback's failures are classified by severity (`ops/rollback_decision.py`) and
`ops/deploy.sh` acts on it -- a P0 regression is rolled back to the commit production ran
before the push, through the guarded rollback path; a P1 is fixed forward. The end-to-end
tests run the real deploy.sh against a local bare repository with stub guard/readback
scripts: no network, no production, no Railway.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OPS = ROOT.parent / "ops"
sys.path.insert(0, str(OPS))

import readback as RB  # noqa: E402
import rollback_decision as RD  # noqa: E402


def _rb(*failed, reachable=True):
    features = [{"feature": f, "verdict": RD.PASS} for f, *_ in RB.MANIFEST]
    for name, verdict in failed:
        next(x for x in features if x["feature"] == name)["verdict"] = verdict
    verdicts = {x["verdict"] for x in features}
    overall = (RD.UNKNOWN if not reachable else RD.FAIL if RD.FAIL in verdicts else
               RD.UNKNOWN if RD.UNKNOWN in verdicts else RD.PASS)
    return {"sha": "c" * 40, "verdict": overall, "reachable": reachable, "features": features}


def test_a_clean_readback_needs_no_containment():
    out = RD.decide(_rb(), previous="a" * 40)
    assert out["decision"] == RD.NONE and out["rollback_to"] is None


def test_a_p1_failure_is_fixed_forward_and_keeps_the_deploy():
    out = RD.decide(_rb(("no unexpected dead letters", RD.FAIL)), previous="a" * 40)
    assert out["decision"] == RD.FIX_FORWARD and out["severity"] == "P1"
    assert out["rollback_to"] is None and RD.EXIT[out["decision"]] == 5


def test_a_safety_regression_is_a_p0_rollback_to_the_predecessor():
    for feature in ("shadow phase holds", "nothing published in shadow",
                    "every agent has a cost ceiling", "embedded worker alive"):
        out = RD.decide(_rb(("no unexpected dead letters", RD.FAIL), (feature, RD.FAIL)),
                        previous="a" * 40)
        assert out["decision"] == RD.ROLLBACK and out["severity"] == "P0", (feature, out)
        assert out["rollback_to"] == "a" * 40 and feature in out["why"]
        assert RD.EXIT[out["decision"]] == 6


def test_unknown_is_never_a_pass_on_a_p0_feature_or_an_unreachable_production():
    out = RD.decide(_rb(("shadow phase holds", RD.UNKNOWN)), previous="a" * 40)
    assert out["decision"] == RD.ROLLBACK
    out = RD.decide(_rb(reachable=False), previous="a" * 40)
    assert out["decision"] == RD.ROLLBACK and "did not answer" in out["why"]
    assert RD.decide(None, previous="a" * 40)["decision"] == RD.ROLLBACK
    assert RD.decide({"verdict": "FAIL"}, previous="a" * 40)["decision"] == RD.ROLLBACK


def test_an_unlisted_feature_is_p1_and_every_p0_name_is_a_real_readback_feature():
    assert RD.severity("a feature added later") == "P1"
    names = {f for f, *_ in RB.MANIFEST}
    assert RD.P0_FEATURES and RD.P0_FEATURES <= names, RD.P0_FEATURES - names


# ---- the real ops/deploy.sh, against a local bare remote with stub scripts -----------------

_STUB_GUARD = r'''
import subprocess, sys
args = sys.argv[1:]
cmd = args[0]
def opt(name):
    return args[args.index(name) + 1]
if cmd in ("check", "rehearse-rollback"):
    sys.exit(0)
if cmd == "rollback-commit":
    to, reason, deployed, repo = opt("--to"), opt("--reason"), opt("--deployed"), opt("--repo")
    tree = subprocess.run(["git", "-C", repo, "rev-parse", to + "^{tree}"], check=True,
                          capture_output=True, text=True).stdout.strip()
    sha = subprocess.run(["git", "-C", repo, "-c", "user.name=t", "-c",
                          "user.email=t@example.invalid", "commit-tree", tree, "-p", deployed,
                          "-m", reason], check=True, capture_output=True, text=True).stdout
    print(sha.strip())
    sys.exit(0)
sys.exit(2)
'''

_STUB_READBACK = r'''
import json, os, sys
args = sys.argv[1:]
sha = args[args.index("--sha") + 1]
out = args[args.index("--json") + 1]
plan = json.loads(open(os.environ["RB_PLAN"]).read())
seen = 0
if os.path.exists(os.environ["RB_LOG"]):
    seen = open(os.environ["RB_LOG"]).read().split().count(sha)
with open(os.environ["RB_LOG"], "a") as f:
    f.write(sha + "\n")
failed = dict(plan.get(sha, plan.get("*", [])))
if plan.get("_pass_on_second") and seen >= 1:
    failed = {}
features = [{"feature": n, "verdict": failed.get(n, "PASS")} for n in plan["names"]]
verdict = "FAIL" if any(f["verdict"] != "PASS" for f in features) else "PASS"
json.dump({"sha": sha, "verdict": verdict, "reachable": True, "features": features},
          open(out, "w"))
sys.exit(0 if verdict == "PASS" else 5)
'''


def _git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c",
                           "user.email=t@example.invalid", *args],
                          capture_output=True, text=True, check=True).stdout.strip()


def _world():
    base = Path(tempfile.mkdtemp(prefix="fmb1-rb-"))
    remote, repo = base / "remote.git", base / "repo"
    subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    (repo / "ops").mkdir()
    for name in ("deploy.sh", "rollback_decision.py"):
        shutil.copy(OPS / name, repo / "ops" / name)
    (repo / "ops" / "deploy_guard.py").write_text(_STUB_GUARD)
    (repo / "ops" / "readback.py").write_text(_STUB_READBACK)
    (repo / "ops" / "verify_deploy.py").write_text("import sys; sys.exit(0)\n")
    (repo / "app.txt").write_text("v1\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "deployed")
    deployed = _git(repo, "rev-parse", "HEAD")
    _git(repo, "remote", "add", "origin", str(remote))
    _git(repo, "push", "-q", "origin", f"{deployed}:refs/heads/claude/repository-setup-nc9x6o")
    (repo / "app.txt").write_text("v2\n")
    _git(repo, "commit", "-q", "-am", "candidate")
    candidate = _git(repo, "rev-parse", "HEAD")
    return base, remote, repo, deployed, candidate


def _deploy(repo, base, plan, *args, **env):
    names = [f for f, *_ in RB.MANIFEST]
    (base / "plan.json").write_text(json.dumps({**plan, "names": names}))
    e = {k: v for k, v in os.environ.items() if k != "TMPDIR"}
    e.update({"RB_PLAN": str(base / "plan.json"), "RB_LOG": str(base / "rb.log"),
              "TMPDIR": str(base)}, **env)
    return subprocess.run(["sh", str(repo / "ops" / "deploy.sh"), "--deployed",
                           plan["_deployed"], *args],
                          cwd=str(repo), env=e, capture_output=True, text=True)


def _production(remote):
    return _git(remote, "rev-parse", "refs/heads/claude/repository-setup-nc9x6o")


def test_deploy_sh_rolls_a_p0_regression_back_to_the_predecessor():
    base, remote, repo, deployed, candidate = _world()
    try:
        r = _deploy(repo, base, {"_deployed": deployed,
                                 candidate: [["shadow phase holds", "FAIL"]]},
                    "--auto-rollback-reason", "owner accepted automatic containment (test)",
                    AUTO_ROLLBACK="1", READBACK_RETRY_S="0")
        assert r.returncode == 0, (r.returncode, r.stderr)
        assert "rolling back to " + deployed in r.stderr, r.stderr
        prod = _production(remote)
        assert prod not in (deployed, candidate)
        # The rollback commit carries exactly the predecessor's tree, on top of the candidate.
        assert _git(remote, "rev-parse", prod + "^{tree}") == _git(repo, "rev-parse",
                                                                    deployed + "^{tree}")
        assert _git(remote, "rev-parse", prod + "^") == candidate
        assert "owner accepted automatic containment" in _git(remote, "log", "-1",
                                                               "--format=%B", prod)
        # The candidate was read back twice (one re-read before acting), then the rollback.
        assert (base / "rb.log").read_text().split() == [candidate, candidate, prod]
    finally:
        shutil.rmtree(base, ignore_errors=True)


def test_deploy_sh_fixes_a_p1_regression_forward_and_keeps_the_candidate():
    base, remote, repo, deployed, candidate = _world()
    try:
        r = _deploy(repo, base, {"_deployed": deployed,
                                 candidate: [["no unexpected dead letters", "FAIL"]]})
        assert r.returncode == 5, (r.returncode, r.stderr)
        assert _production(remote) == candidate and "rolling back" not in r.stderr
    finally:
        shutil.rmtree(base, ignore_errors=True)


def test_auto_rollback_off_reports_the_p0_and_never_pushes_a_rollback():
    base, remote, repo, deployed, candidate = _world()
    try:
        r = _deploy(repo, base, {"_deployed": deployed,
                                 candidate: [["every agent has a cost ceiling", "FAIL"]]},
                    AUTO_ROLLBACK="0", READBACK_RETRY_S="0")
        assert r.returncode == 6 and "--rollback-to " + deployed in r.stderr, r.stderr
        assert _production(remote) == candidate
    finally:
        shutil.rmtree(base, ignore_errors=True)


def test_by_default_a_p0_is_reported_and_production_is_not_pushed():
    """Review F-3: no AUTO_ROLLBACK in the environment means no automatic push."""
    base, remote, repo, deployed, candidate = _world()
    try:
        r = _deploy(repo, base, {"_deployed": deployed,
                                 candidate: [["shadow phase holds", "FAIL"]]},
                    READBACK_RETRY_S="0")
        assert r.returncode == 6 and "--rollback-to " + deployed in r.stderr, r.stderr
        assert "rolling back to" not in r.stderr
        assert _production(remote) == candidate
    finally:
        shutil.rmtree(base, ignore_errors=True)


def test_auto_rollback_without_an_owner_reason_refuses_to_push():
    base, remote, repo, deployed, candidate = _world()
    try:
        r = _deploy(repo, base, {"_deployed": deployed,
                                 candidate: [["shadow phase holds", "FAIL"]]},
                    AUTO_ROLLBACK="1", READBACK_RETRY_S="0")
        assert r.returncode == 6 and _production(remote) == candidate, r.stderr
    finally:
        shutil.rmtree(base, ignore_errors=True)


def test_n4_a_standing_environment_reason_never_authorises_a_rollback():
    """Review cbd4ff1 N-4: the reason must be given on this invocation; a standing
    AUTO_ROLLBACK_REASON in the environment is refused and nothing is pushed."""
    base, remote, repo, deployed, candidate = _world()
    try:
        r = _deploy(repo, base, {"_deployed": deployed,
                                 candidate: [["shadow phase holds", "FAIL"]]},
                    AUTO_ROLLBACK="1", AUTO_ROLLBACK_REASON="standing reason set months ago",
                    READBACK_RETRY_S="0")
        assert r.returncode == 6 and _production(remote) == candidate, r.stderr
        assert "rolling back to" not in r.stderr
        assert "--auto-rollback-reason" in r.stderr
    finally:
        shutil.rmtree(base, ignore_errors=True)


def test_n4_header_documents_the_real_default():
    head = (OPS / "deploy.sh").read_text().split("\n\n", 1)[0]
    assert "default 1, F-381" not in head and "default 0" in head


def test_a_p0_that_clears_on_the_re_read_is_not_rolled_back():
    base, remote, repo, deployed, candidate = _world()
    try:
        r = _deploy(repo, base, {"_deployed": deployed,
                                 candidate: [["shadow phase holds", "FAIL"]],
                                 "_pass_on_second": True},
                    AUTO_ROLLBACK="1", AUTO_ROLLBACK_REASON="x", READBACK_RETRY_S="0")
        assert r.returncode == 0 and "PASS on re-read" in r.stdout, (r.stdout, r.stderr)
        assert _production(remote) == candidate
    finally:
        shutil.rmtree(base, ignore_errors=True)


def test_a_rollback_that_itself_regresses_is_not_rolled_back_again():
    base, remote, repo, deployed, candidate = _world()
    try:
        r = _deploy(repo, base, {"_deployed": deployed,
                                 "*": [["shadow phase holds", "FAIL"]]},
                    "--auto-rollback-reason", "owner accepted automatic containment (test)",
                    AUTO_ROLLBACK="1", READBACK_RETRY_S="0")
        assert r.returncode == 6, (r.returncode, r.stderr)
        assert "NOT rolling back again" in r.stderr
        # candidate, its re-read, then one rollback (which is never rolled back again)
        assert len((base / "rb.log").read_text().split()) == 3
    finally:
        shutil.rmtree(base, ignore_errors=True)


if __name__ == "__main__":
    fails = passes = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                passes += 1
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                traceback.print_exc()
                fails += 1
                print("FAIL", name, repr(e))
    print(f"\n  {passes} passing, {fails} failing")
    sys.exit(1 if fails else 0)
