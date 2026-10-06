"""A3-05 / A3-06 / A3-08: runtime boot guard, sanctioned rollback, default-on SQLite refusal.

Hermetic: throwaway git repositories and directories, no network, no deploy, no push to any
real remote.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "ops"))

import deploy_guard as G  # noqa: E402
from brambleloop.ops import release_record as R  # noqa: E402

os.environ["GIT_CONFIG_GLOBAL"] = os.devnull
os.environ["GIT_CONFIG_NOSYSTEM"] = "1"
for _k, _v in (("GIT_AUTHOR_NAME", "t"), ("GIT_AUTHOR_EMAIL", "t@example.invalid"),
               ("GIT_COMMITTER_NAME", "t"), ("GIT_COMMITTER_EMAIL", "t@example.invalid")):
    os.environ.setdefault(_k, _v)
FCB = "fcb982d57e291c88d9f78eaa091e90904b6c2cc9"
REASON = "owner: checkout broke after deploy, roll back to last known good"


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c",
                           "user.email=t@example.invalid", *args],
                          capture_output=True, text=True, check=True).stdout.strip()


def _commit(repo: Path, msg: str) -> str:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "--allow-empty", "-m", msg)
    return _git(repo, "rev-parse", "HEAD")


def _write(base: Path, rel: str, text: str) -> None:
    p = base / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


# ---- A3-06: the rollback path ----------------------------------------------------------------

def _history_repo() -> tuple[Path, dict]:
    """A (old code) <- B (new code, history lists A; production runs B); S a side commit."""
    repo = Path(tempfile.mkdtemp(prefix="rc1own-rollback-")) / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _write(repo, "brambleloop/src/brambleloop/app.py", "VERSION = 1\n")
    _write(repo, "brambleloop/requirements.lock", "x==1\n")
    s = {"A": _commit(repo, "A")}
    _git(repo, "checkout", "-q", "-b", "side")
    _write(repo, "brambleloop/src/brambleloop/app.py", "VERSION = 'side'\n")
    s["S"] = _commit(repo, "S")
    _git(repo, "checkout", "-q", "main")
    _write(repo, "brambleloop/src/brambleloop/app.py", "VERSION = 2\n")
    _write(repo, "brambleloop/release/DEPLOYED_HISTORY.json",
           json.dumps({"deployed": [{"sha": s["A"]}]}))
    s["B"] = _commit(repo, "B")
    return repo, s


def test_rollback_to_a_recorded_deployed_sha_is_sanctioned_and_rehearsable():
    repo, s = _history_repo()
    try:
        # The forward rule still refuses an accidental rollback.
        assert G.check(s["A"], s["B"], repo=repo)["verdict"] == "REFUSE"
        out = G.rollback_commit(s["A"], REASON, deployed=s["B"], repo=repo)
        assert out["ok"], out
        c = out["commit"]
        assert _git(repo, "rev-parse", f"{c}^{{tree}}") == _git(repo, "rev-parse",
                                                                 f"{s['A']}^{{tree}}")
        assert _git(repo, "rev-parse", f"{c}^1") == s["B"]          # a fast-forward
        verdict = G.check(c, s["B"], repo=repo)
        assert verdict["verdict"] == "ALLOW" and verdict["mode"] == "rollback", verdict
        assert verdict["rollback"]["reason"] == " ".join(REASON.split())
        # The hook sees the same push and allows it from the commit's own trailers.
        line = f"refs/heads/x {c} {G.PRODUCTION_REF} {'0' * 39}1"
        pp = G.pre_push([line], deployed=s["B"], repo=repo)
        assert pp["verdict"] == "ALLOW", pp
        # Exact recorded commit (a force push) is also sanctioned with a reason.
        assert G.check(s["A"], s["B"], repo=repo, rollback_to=s["A"],
                       rollback_reason=REASON)["verdict"] == "ALLOW"
    finally:
        shutil.rmtree(repo.parent, ignore_errors=True)


def test_rollback_refusals():
    repo, s = _history_repo()
    try:
        assert not G.rollback_commit(s["A"], "because", deployed=s["B"], repo=repo)["ok"]
        side = G.rollback_commit(s["S"], REASON, deployed=s["B"], repo=repo)
        assert not side["ok"] and any("deployed history" in r
                                      for r in side["check"]["reasons"]), side
        unknown = G.check(s["A"], None, repo=repo, rollback_to=s["A"], rollback_reason=REASON)
        assert unknown["verdict"] == "REFUSE"
        # Trailers on a commit whose tree is not the target's are refused.
        _write(repo, "brambleloop/src/brambleloop/app.py", "VERSION = 'sneaky'\n")
        sneaky = _commit(repo, f"x\n\n{G.ROLLBACK_TO} {s['A']}\n{G.ROLLBACK_REASON} {REASON}\n")
        v = G.check(sneaky, s["B"], repo=repo)
        assert v["verdict"] == "REFUSE" and any("exactly the tree" in r for r in v["reasons"])
    finally:
        shutil.rmtree(repo.parent, ignore_errors=True)


def test_deploy_sh_rollback_dry_run_pushes_nothing():
    repo, s = _history_repo()
    try:
        origin = repo.parent / "origin.git"
        subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True)
        (repo / "ops").mkdir()
        for name in ("deploy_guard.py", "deployed_sha.py", "deploy.sh"):
            (repo / "ops" / name).write_bytes((REPO_ROOT / "ops" / name).read_bytes())
        _git(repo, "remote", "add", "origin", str(origin))
        env = {k: v for k, v in os.environ.items() if k != G.DEPLOYED_ENV}
        env["DRY_RUN"] = "1"
        r = subprocess.run(["sh", "ops/deploy.sh", "--rollback-to", s["A"], "--reason", REASON,
                            "--deployed", s["B"]], cwd=repo, env=env, capture_output=True,
                           text=True)
        assert r.returncode == 0 and "ALLOW" in r.stdout, (r.stdout, r.stderr)
        r = subprocess.run(["sh", "ops/deploy.sh", "--rollback-to", s["A"], "--deployed",
                            s["B"]], cwd=repo, env=env, capture_output=True, text=True)
        assert r.returncode == 1, "a rollback without the owner's reason was allowed"
        heads = subprocess.run(["git", "--git-dir", str(origin), "for-each-ref"],
                               capture_output=True, text=True).stdout
        assert heads.strip() == "", "a dry run pushed"
    finally:
        shutil.rmtree(repo.parent, ignore_errors=True)


def test_the_real_history_names_production_and_the_runbook_exists():
    hist = json.loads((ROOT / "release" / "DEPLOYED_HISTORY.json").read_text())
    assert FCB in [e["sha"] for e in hist["deployed"]]
    runbook = (REPO_ROOT / "ops" / "ROLLBACK_RUNBOOK.md").read_text()
    for needle in ("fcb982d", "POSTGRES_MIGRATION_EVIDENCE.md", "--rollback-to",
                   "additive", "Rollback-Reason", "DRY_RUN=1"):
        assert needle in runbook, needle


# ---- A3-05: the runtime boot guard ----------------------------------------------------------

def _build_dir(eligible: bool = True) -> tuple[Path, str]:
    root = Path(tempfile.mkdtemp(prefix="rc1own-boot-"))
    _write(root, "src/brambleloop/app.py", "VERSION = 1\n")
    _write(root, "src/brambleloop/__pycache__/app.cpython-311.pyc", "bytecode")
    _write(root, "requirements.lock", "x==1\n")
    sha = "c" * 40
    suite = {"run_id": "run1", "git_sha": sha, "release_eligible": eligible,
             "status": "passed" if eligible else "failed", "scope": "full",
             "suites_failing": 0 if eligible else 1, "failing_suites": []}
    sb = json.dumps(suite).encode()
    lb = (f"RUN ID: run1\nGIT SHA: {sha}\nTOTAL PASSING: 9 ; suites failing: "
          f"{0 if eligible else 1}\n").encode()
    (root / "release" / "suite_runs").mkdir(parents=True)
    (root / "release" / "suite_runs" / "run1.json").write_bytes(sb)
    (root / "release" / "suite_runs" / "run1.log").write_bytes(lb)
    rec = {"sha": sha, "release_eligible": True,
           "source_tree_sha256": R.filesystem_digest(root),
           "suite_record": {"path": "suite_runs/run1.json",
                            "sha256": hashlib.sha256(sb).hexdigest()},
           "suite_log": {"path": "suite_runs/run1.log",
                         "sha256": hashlib.sha256(lb).hexdigest()}}
    (root / "release" / f"RELEASE_{sha}.json").write_text(json.dumps(rec))
    return root, sha


def test_boot_guard_accepts_a_recorded_build_and_rejects_tampering():
    root, sha = _build_dir()
    try:
        env = {"RAILWAY_ENVIRONMENT": "production", "BRAMBLELOOP_PHASE": "limited_production"}
        ok = R.apply_at_import(env, root=root)
        assert ok["ok"] and ok["action"] == "none" and ok["record"]["sha"] == sha, ok
        assert env["BRAMBLELOOP_PHASE"] == "limited_production"
        # A change to deployable code the record does not name: forced to SHADOW.
        _write(root, "src/brambleloop/app.py", "VERSION = 'unproven'\n")
        bad = R.apply_at_import(env, root=root)
        assert not bad["ok"] and bad["action"] == "forced_shadow", bad
        assert env["BRAMBLELOOP_PHASE"] == "shadow"
        # Refuse mode exits instead.
        try:
            R.apply_at_import({"RAILWAY_ENVIRONMENT": "x", R.MODE_ENV: "refuse"}, root=root)
        except SystemExit:
            pass
        else:
            raise AssertionError("refuse mode started an unproven build")
        # There is no switch that turns enforcement off on the platform.
        off = {"RAILWAY_SERVICE_ID": "s", R.MODE_ENV: "off", "BRAMBLELOOP_PHASE": "production"}
        assert R.apply_at_import(off, root=root)["action"] == "forced_shadow"
        # Off the platform it only reports.
        local = {"BRAMBLELOOP_PHASE": "production"}
        res = R.apply_at_import(local, root=root)
        assert res["enforced"] is False and local["BRAMBLELOOP_PHASE"] == "production"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_boot_guard_rejects_a_red_or_unpinned_suite_record():
    root, _sha = _build_dir(eligible=False)
    try:
        res = R.verify_build(root, {"RAILWAY_ENVIRONMENT": "p"})
        assert not res["ok"] and any("release-eligible" in r for r in res["reasons"]), res
    finally:
        shutil.rmtree(root, ignore_errors=True)
    root, _sha = _build_dir()
    try:
        (root / "release" / "suite_runs" / "run1.log").write_text("TOTAL PASSING: 9 ; "
                                                                  "suites failing: 0\n")
        res = R.verify_build(root, {"RAILWAY_ENVIRONMENT": "p"})
        assert not res["ok"] and any("pinned sha256" in r for r in res["reasons"]), res
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_boot_guard_opens_and_resolves_a_p1_incident():
    from sqlalchemy import select

    from brambleloop.core.db import Database
    from brambleloop.core.models import Incident

    tmp = tempfile.mkdtemp(prefix="rc1own-bootdb-")
    try:
        db = Database(f"sqlite:///{tmp}/b.db")
        db.create_all()
        bad = {"enforced": True, "ok": False, "reasons": ["x"], "action": "forced_shadow"}
        assert R.record_incident(db, bad) == "opened"
        assert R.record_incident(db, bad) == "restated"
        with db.session() as s:
            row = s.scalar(select(Incident).where(Incident.signature == R.INCIDENT_SIGNATURE))
            assert row.severity == "P1" and row.halts_publication and not row.resolved
        assert R.record_incident(db, {"enforced": True, "ok": True}) == "resolved"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_guard_and_boot_digests_are_the_same_function():
    """The deploy guard (from git) and the boot guard (from the image) hash the same tree."""
    tmp = Path(tempfile.mkdtemp(prefix="rc1own-digest-"))
    try:
        arch = subprocess.run(["git", "-C", str(REPO_ROOT), "archive", "HEAD",
                               "brambleloop/src", "brambleloop/requirements.lock"],
                              capture_output=True, check=True).stdout
        subprocess.run(["tar", "-x", "-C", str(tmp)], input=arch, check=True)
        assert G.git_tree_digest(REPO_ROOT, "HEAD") == R.filesystem_digest(tmp / "brambleloop")
        for rel in ("src/a/__pycache__/x.pyc", "src/a.py", "requirements.lock", "tests/x.py",
                    "release/RELEASE_x.json", "src/a.pyc"):
            assert G.deployable(rel) == R.deployable(rel), rel
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_dockerfile_ships_the_release_records_and_main_runs_the_guard():
    assert "COPY release ./release" in (ROOT / "Dockerfile").read_text()
    main = (ROOT / "src" / "brambleloop" / "app" / "main.py").read_text()
    assert main.index("apply_at_import()") < main.index("db = Database()")
    assert "_release_record.record_incident(db)" in main


# ---- A3-08: SQLite refused by default where it would be ephemeral ---------------------------

def test_sqlite_refusal_is_default_on_hosted_and_outside_shadow():
    from brambleloop.core import db as dbmod

    keys = ("DATABASE_URL", "BRAMBLELOOP_DATABASE_URL", "BRAMBLELOOP_REQUIRE_POSTGRES",
            "BRAMBLELOOP_PHASE", *dbmod.HOSTED_MARKERS)
    saved = {k: os.environ.get(k) for k in keys}

    def env(**kw):
        for k in keys:
            os.environ.pop(k, None)
        os.environ.update(kw)

    def refused(**kw) -> bool:
        try:
            dbmod.resolve_url(**kw)
        except dbmod.EphemeralStorageRefused:
            return True
        return False

    try:
        env()
        assert not refused()                                        # dev default: allowed
        env(RAILWAY_ENVIRONMENT="production")
        assert refused(), "hosted with no DATABASE_URL fell back to SQLite"
        env(RAILWAY_ENVIRONMENT="production", BRAMBLELOOP_REQUIRE_POSTGRES="0")
        assert refused(), "an env switch turned the hosted refusal off"
        env(RAILWAY_ENVIRONMENT="production", DATABASE_URL="sqlite:///x.db")
        assert refused()
        env(RAILWAY_PROJECT_ID="p", DATABASE_URL="postgres://u:p@h/db")
        assert dbmod.resolve_url().startswith("postgresql+psycopg2://")
        env(BRAMBLELOOP_PHASE="limited_production")
        assert refused(), "a live phase ran on SQLite"
        env(BRAMBLELOOP_PHASE="shadow")
        assert not refused()
        env(RAILWAY_ENVIRONMENT="production")
        assert not refused(scratch=True)                            # the restore proof
        assert not refused(url="sqlite:///tool.db")                 # explicit, by code
        env(BRAMBLELOOP_REQUIRE_POSTGRES="1")
        assert refused(url="sqlite:///tool.db")                     # original opt-in kept
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


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
    sys.exit(1 if fails else 0)
