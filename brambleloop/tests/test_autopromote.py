"""ENG-AUTOPROMOTE: ops/autopromote.py (backup gate, history append, release subject) and the
certify-and-promote workflow's guard invariants. Stdlib only; no network."""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import datetime as dt
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "ops"))

import autopromote as A  # noqa: E402

WF = REPO_ROOT / ".github" / "workflows" / "certify-and-promote.yml"
NOW = dt.datetime(2026, 11, 20, 12, 0, tzinfo=dt.timezone.utc)


class FakeRailway:
    """Scripted db-backup service: deployments appear after redeploy, with given logs."""

    def __init__(self, *, existing=None, new_logs=None, new_status="SUCCESS",
                 redeploy_error=None, appear_after=1, logs_error=False):
        self.deps = list(existing or [])          # [(id, status, logs)]
        self.new = ("new-1", new_status, new_logs or [])
        self.redeploy_error, self.appear_after = redeploy_error, appear_after
        self.logs_error, self.polls, self.redeployed = logs_error, 0, False

    def deployments(self, first=10):
        if self.redeployed:
            self.polls += 1
            if self.polls > self.appear_after and self.new not in self.deps:
                self.deps.insert(0, self.new)
        return [{"id": i, "status": s, "createdAt": ""} for i, s, _ in self.deps[:first]]

    def logs(self, dep_id):
        if self.logs_error:
            raise RuntimeError("boom")
        return next(lg for i, _s, lg in self.deps if i == dep_id)

    def redeploy(self):
        if self.redeploy_error:
            raise RuntimeError(self.redeploy_error)
        self.redeployed = True


def _ok(ts):
    return {"message": "BK RESULT OK /backup/brambleloop_prod_x.dump", "timestamp": ts}


def _decide(fake, token="t", **kw):
    clock = iter(range(0, 100000, 20))
    return A.decide(token, max_age_hours=24, wait=200, railway_factory=lambda _t: fake,
                    now=NOW, clock=lambda: next(clock), sleep=lambda _s: None, **kw)


def test_no_token_refuses_and_never_reads_anything():
    called = []
    for tok in (None, "", "   "):
        out = A.decide(tok, max_age_hours=24, wait=1,
                       railway_factory=lambda t: called.append(t))
        assert out["ok"] is False and out["verdict"] == "REFUSE", out
        assert "RAILWAY_TOKEN" in out["why"]
    assert called == []


def test_triggered_backup_ok():
    fake = FakeRailway(new_logs=[{"message": "BK restore_ok"}, _ok("2026-11-20T11:59:00Z")])
    out = _decide(fake)
    assert out["ok"] and out["source"] == "triggered" and fake.redeployed, out


def test_triggered_backup_fail_refuses_even_with_fresh_old_ok():
    fake = FakeRailway(existing=[("old", "SUCCESS", [_ok("2026-11-20T11:00:00Z")])],
                       new_logs=[{"message": "BK RESULT FAIL restore"}])
    out = _decide(fake)
    assert not out["ok"] and "failed" in out["why"], out


def test_crashed_deployment_without_ok_refuses():
    fake = FakeRailway(existing=[("old", "SUCCESS", [_ok("2026-11-20T11:00:00Z")])],
                       new_logs=[{"message": "BK dumping"}], new_status="CRASHED")
    out = _decide(fake)
    assert not out["ok"] and "CRASHED" in out["why"], out


def test_trigger_error_falls_back_to_recent_ok():
    fake = FakeRailway(existing=[("old", "SUCCESS", [_ok("2026-11-20T02:00:00Z")])],
                       redeploy_error="forbidden")
    out = _decide(fake)
    assert out["ok"] and out["source"] == "recent" and out["age_hours"] == 10.0, out


def test_trigger_error_and_stale_ok_refuses():
    fake = FakeRailway(existing=[("old", "SUCCESS", [_ok("2026-11-18T12:00:00Z")])],
                       redeploy_error="forbidden")
    out = _decide(fake)
    assert not out["ok"] and "48.0 h old" in out["why"], out


def test_timeout_without_verdict_uses_freshness_rule():
    fake = FakeRailway(existing=[("old", "SUCCESS", [_ok("2026-11-19T00:00:00Z")])],
                       appear_after=10 ** 6)
    out = _decide(fake)  # 36 h old, limit 24 -> refuse
    assert not out["ok"] and out["trigger"]["verdict"] == "UNKNOWN", out


def test_no_dated_ok_anywhere_refuses():
    fake = FakeRailway(existing=[("old", "SUCCESS", [{"message": "BK RESULT OK x"}])],
                       redeploy_error="nope")
    assert not _decide(fake)["ok"]


def test_unreadable_logs_refuse():
    fake = FakeRailway(existing=[("old", "SUCCESS", [])], redeploy_error="nope",
                       logs_error=True)
    out = _decide(fake)
    assert not out["ok"] and "unreadable" in out["why"], out


def test_scan_logs_distinguishes_ok_and_fail():
    s = A.scan_logs([{"message": "BK RESULT FAIL x"}, _ok("2026-11-20T00:00:00Z")])
    assert s["ok"] and s["fail"]
    assert A.scan_logs([{"message": "BK RESULT OKAY"}])["ok"] is None


def test_history_append_is_idempotent_and_validates():
    d = Path(tempfile.mkdtemp())
    p = d / "H.json"
    p.write_text(json.dumps({"kind": "brambleloop.deployed_history", "deployed": []}))
    sha = "a" * 40
    assert not A.history_append("abc", "observed in production", path=p)["ok"]
    assert not A.history_append(sha, "", path=p)["ok"]
    r1 = A.history_append(sha, "observed in production", path=p, observed="2026-11-20T12:00Z")
    r2 = A.history_append(sha, "observed in production", path=p)
    assert r1["changed"] and not r2["changed"]
    assert [e["sha"] for e in json.loads(p.read_text())["deployed"]] == [sha]
    shutil.rmtree(d)


def test_history_format_matches_tracked_file():
    real = REPO_ROOT / "brambleloop" / "release" / "DEPLOYED_HISTORY.json"
    d = Path(tempfile.mkdtemp())
    p = d / "H.json"
    shutil.copy(real, p)
    sha = json.loads(real.read_text())["deployed"][-1]["sha"]
    A.history_append(sha, "already present, no rewrite", path=p)
    assert p.read_text() == real.read_text()
    A.history_append("b" * 40, "observed in production", path=p)
    assert p.read_text().startswith(real.read_text()[:200])
    shutil.rmtree(d)


def test_release_subject_reads_tracked_record():
    rel = REPO_ROOT / "brambleloop" / "release"
    rec = sorted(rel.glob("RELEASE_*.json"))[-1]
    sha = rec.stem[len("RELEASE_"):]
    subj = A.release_subject(sha)
    assert subj.startswith(f"Release record for {sha[:8]} (full suite ") and "0 failing" in subj


def test_workflow_keeps_the_guard_intact():
    wf = WF.read_text()
    assert "bash run_tests.sh" in wf and "REQUIRE_CLEAN=1" in wf
    for banned in ("CHECKPOINT=", "RESUME=", "SHARD=", "--no-verify", "push --force",
                   "push -f", "DRY_RUN=1 sh ops/deploy.sh --deployed \"$DEPLOYED\" ||"):
        assert banned not in wf, banned
    assert "ops/deploy_guard.py record" in wf
    assert 'sh ops/deploy.sh --deployed "$DEPLOYED"' in wf
    assert "ops/deployed_sha.py" in wf
    assert "permissions:\n  contents: read\n" in wf and "issues:" not in wf
    assert "group: brambleloop-promote" in wf and "cancel-in-progress: false" in wf
    assert "BRAMBLELOOP_READBACK_TOKEN" in wf and "SKIPPED (WARN)" in wf
    assert "ops/autopromote.py backup" in wf and "secrets.RAILWAY_TOKEN" in wf
    assert "claude/w6-release-*" in wf and "workflow_dispatch" in wf
    # The backup gate runs before the real deploy, after the dry run.
    assert wf.index("DRY_RUN=1 sh ops/deploy.sh") < wf.index("python3 ops/autopromote.py backup |") \
        < wf.index('          sh ops/deploy.sh --deployed "$DEPLOYED" || rc=$?')


# ---- B19: the workflow's shell, trigger, permission and job-split invariants ------------------

def _yaml(text):
    import yaml

    return yaml.safe_load(text)


def _steps(job):
    return job.get("steps") or []


def workflow_failures(text: str) -> list[str]:
    """Every B19 invariant of certify-and-promote.yml; empty = holds."""
    import re

    out = []
    try:
        wf = _yaml(text)
    except Exception as exc:  # noqa: BLE001
        return [f"does not parse: {exc}"]
    on = wf.get(True, wf.get("on")) or {}
    # B4/B6: dispatch only, run from the default branch.
    if set(on) != {"workflow_dispatch"}:
        out.append(f"triggers must be exactly workflow_dispatch, got {sorted(map(str, on))}")
    for banned in ("pull_request_target", "workflow_run", "pull_request:"):
        if banned in text:
            out.append(f"{banned} present")
    jobs = wf.get("jobs") or {}
    certify, record, promote = (jobs.get(k) or {} for k in ("certify", "record", "promote"))
    target = next((st for st in _steps(certify) if st.get("id") == "target"), {})
    if "DEFAULT_BRANCH" not in str(target.get("run")) or "default_branch" not in str(target):
        out.append("certify does not refuse a run from a non-default branch")
    # B1/B6: pipefail everywhere; the backup gate checks its own verdict; no `|| true`.
    if (wf.get("defaults") or {}).get("run", {}).get("shell") != "bash":
        out.append("defaults.run.shell must be bash (pipefail)")
    for name, job in jobs.items():
        for st in _steps(job):
            sh = st.get("shell")
            if sh is not None and sh != "bash":
                out.append(f"{name}/{st.get('name')}: shell {sh!r} drops pipefail")
            run = str(st.get("run") or "")
            if re.search(r"\$\{\{\s*(github\.event\.|inputs\.)", run):
                out.append(f"{name}/{st.get('name')}: untrusted input interpolated into run:")
    backup = next((st for st in _steps(promote) if "backup" in str(st.get("name")).lower()), {})
    brun = str(backup.get("run") or "")
    if "python3 ops/autopromote.py backup" not in brun:
        out.append("no backup gate in promote")
    if backup.get("shell") != "bash" or "set -o pipefail" not in brun:
        out.append("the backup gate is not pipefail (B1)")
    if ".get('ok') is True" not in brun:
        out.append("the backup gate does not check the verdict's ok")
    deploy = next((st for st in _steps(promote) if st.get("id") == "deploy"), {})
    for label, st in (("backup", backup), ("deploy", deploy)):
        if "|| true" in str(st.get("run") or ""):
            out.append(f"`|| true` in the {label} step")
    # B2: one certify at a time; promote refuses a non-descendant.
    conc = wf.get("concurrency") or {}
    if conc.get("group") != "brambleloop-certify" or conc.get("cancel-in-progress") is not False:
        out.append(f"certify concurrency must be one repository-wide group: {conc}")
    if "merge-base --is-ancestor" not in str(promote):
        out.append("promote does not check that the release descends from the deployed SHA")
    # B3: the suite runs read-only; a separate fresh job pushes the record, without hooks.
    if wf.get("permissions") != {"contents": "read"}:
        out.append(f"workflow permissions must default to contents: read: {wf.get('permissions')}")
    if certify.get("permissions") != {"contents": "read"}:
        out.append("certify (the suite) must have contents: read only")
    if any("push" in str(st.get("run") or "") for st in _steps(certify)):
        out.append("certify pushes")
    if "github.token" in str(certify):
        out.append("certify sees the token")
    if record.get("needs") != "certify" or record.get("permissions") != {"contents": "write"}:
        out.append("record must follow certify with contents: write")
    if any("run_tests.sh" in str(st.get("run") or "") for st in _steps(record)):
        out.append("record runs the suite")
    rrun = "\n".join(str(st.get("run") or "") for st in _steps(record))
    if "git -c core.hooksPath=/dev/null commit" not in rrun \
            or "git -c core.hooksPath=/dev/null -c http.https://github.com/.extraheader" not in rrun \
            or "RELEASE_$SHA.json" not in rrun:
        out.append("record must verify the record names the SHA and push with hooks disabled")
    if promote.get("needs") != "record":
        out.append("promote must follow record")
    return out


def test_workflow_b19_invariants_hold():
    assert workflow_failures(WF.read_text()) == [], workflow_failures(WF.read_text())


def test_workflow_b19_mutants_are_killed():
    base = WF.read_text()
    mutants = {
        "backup || true": base.replace("python3 ops/autopromote.py backup | tee backup.json",
                                       "python3 ops/autopromote.py backup | tee backup.json || true"),
        "backup without pipefail": base.replace("          set -o pipefail\n          # Absent",
                                                "          # Absent"),
        "pull_request_target trigger": base.replace("  workflow_dispatch:\n",
                                                    "  pull_request_target:\n  workflow_dispatch:\n"),
        "push trigger back": base.replace("  workflow_dispatch:\n",
                                          "  push:\n    branches: [\"claude/w6-release-*\"]\n"
                                          "  workflow_dispatch:\n"),
        "per-SHA certify group": base.replace("group: brambleloop-certify",
                                              "group: certify-${{ inputs.sha }}"),
        "certify can write": base.replace("      contents: read     # B19 B3",
                                          "      contents: write     # B19 B3"),
        "hooks enabled on push": base.replace("git -c core.hooksPath=/dev/null -c http",
                                              "git -c http"),
        "sh shell on backup": base.replace("        shell: bash      # B19 B1", "        shell: sh"),
        "no ancestry check": base.replace("git merge-base --is-ancestor", "true"),
        "input interpolated": base.replace('[ "$EVENT" = "workflow_dispatch" ]',
                                           '[ "${{ inputs.sha }}" != x ]'),
    }
    survived = [k for k, v in mutants.items() if v == base or not workflow_failures(v)]
    assert survived == [], survived


def test_backup_gate_fails_the_step_when_the_backup_refuses():
    """B1, executed: the shipped backup step's script, run under the shell GitHub uses for
    `shell: bash`, exits non-zero when `autopromote.py backup` refuses (exit 1) -- and the
    old form (no pipefail) is shown to continue, so this test can tell them apart."""
    wf = _yaml(WF.read_text())
    step = next(st for st in wf["jobs"]["promote"]["steps"]
                if "backup" in str(st.get("name")).lower())
    tmp = Path(tempfile.mkdtemp())
    (tmp / "ops").mkdir()
    for verdict, rc in (({"ok": False, "verdict": "REFUSE"}, 1), ({"ok": True}, 0),
                        ({"ok": False}, 0)):     # a lying exit status is caught by the verdict
        (tmp / "ops/autopromote.py").write_text(
            f"import json,sys\nprint(json.dumps({verdict!r}))\nsys.exit({rc})\n")
        r = subprocess.run(["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c",
                            step["run"]], cwd=tmp, capture_output=True, text=True)
        want_ok = verdict.get("ok") is True and rc == 0
        assert (r.returncode == 0) is want_ok, (verdict, rc, r.returncode, r.stderr)
    old = "python3 ops/autopromote.py backup | tee backup.json\necho continued\n"
    (tmp / "ops/autopromote.py").write_text("import sys\nprint('{}')\nsys.exit(1)\n")
    r = subprocess.run(["bash", "-e", "-c", old], cwd=tmp, capture_output=True, text=True)
    assert r.returncode == 0 and "continued" in r.stdout   # why B1 needed fixing


def test_dispatch_board_runs_pinned_reviewed_code_only():
    """B5: the board checks out a pinned 40-hex commit, never a branch name, and no
    expression is interpolated into its run line."""
    import re

    wf = _yaml((REPO_ROOT / ".github/workflows/dispatch.yml").read_text())
    steps = [st for job in wf["jobs"].values() for st in job.get("steps") or []]
    assert steps, "dispatch.yml has no steps"
    checkouts = [st for st in steps if "checkout" in str(st.get("uses") or "")]
    assert checkouts, "dispatch.yml has no checkout step"
    for st in checkouts:
        assert re.fullmatch(r"[0-9a-f]{40}", str((st.get("with") or {}).get("ref"))), st
    runs = [str(st.get("run")) for st in steps if st.get("run")]
    assert runs, "dispatch.yml runs nothing"
    for run in runs:
        assert "${{" not in run, run


def test_workflow_lint():
    exe = shutil.which("actionlint")
    if exe is None:
        print("SKIP actionlint not installed (pip install actionlint-py)")
        return
    r = subprocess.run([exe, str(WF), str(REPO_ROOT / ".github/workflows/dispatch.yml")],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


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
