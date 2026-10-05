#!/usr/bin/env python3
"""F-845 / F-846: freeze a Final Build launch candidate, or refuse and say exactly why.

A candidate is one exact commit that a release-eligible full suite ran on, with a clean tree,
bound to the closure-matrix summary and the shadow-rehearsal evidence of that code. Freezing:

  * creates the LOCAL annotated tag `final-candidate-<sha7>` on that commit (never pushed here;
    pushing a tag is the integrator's decision);
  * writes `research/final_build/CANDIDATE_<sha7>.json` binding the suite record, the matrix
    summary (with its launch-critical OPEN count) and the rehearsal evidence, each by sha256;
  * opens `research/final_build/DEFECT_LEDGER_<sha7>.json`: the defects the independent audit
    of the candidate starts from (rehearsal blocking defects, launch-critical matrix defects).
    Repairs are made on a successor, regression-tested, full-suited and re-audited (F-846).

Refused (exit 2, nothing written, no tag) when any of these fails:
  * the SHA is not a commit, or is not the checked-out HEAD;
  * the working tree is not clean (tracked or untracked changes);
  * no suite record for exactly that SHA is release-eligible (full scope, passed, 0 failing
    suites/tests, clean tree, HEAD unmoved during the run);
  * no shadow-rehearsal evidence in production mode for that SHA, or for an ancestor whose
    diff to it touches no code (src/, scripts/, tests/, deploy files);
  * the closure matrix is missing or does not carry the computed completion summary;
  * the tag already exists.

    cd brambleloop && .venv/bin/python scripts/freeze_candidate.py [--sha SHA] [--suite-record P]
        [--rehearsal P] [--dry-run]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]          # brambleloop/
FB = ROOT / "research" / "final_build"
CODE_PATHS = ("brambleloop/src/", "brambleloop/scripts/", "brambleloop/tests/",
              "brambleloop/railway.json", "brambleloop/Dockerfile",
              "brambleloop/requirements", "brambleloop/run_tests.sh")


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def suite_refusal(rec: dict, sha: str) -> str | None:
    """Why this suite record does not make `sha` release-eligible, or None."""
    problems = []
    if rec.get("git_sha") != sha:
        problems.append(f"record is for {str(rec.get('git_sha'))[:12]}, not {sha[:12]}")
    if rec.get("git_sha_at_end") not in (None, sha):
        problems.append("HEAD moved during the run")
    if rec.get("release_eligible") is not True:
        problems.append("not release_eligible")
    if rec.get("scope") != "full":
        problems.append(f"scope {rec.get('scope')!r}, not full")
    if rec.get("status") != "passed":
        problems.append(f"status {rec.get('status')!r}")
    if rec.get("suites_failing") != 0 or rec.get("failing_suites"):
        problems.append("failing suites")
    if rec.get("tests_failing_reported") not in (0, None):
        problems.append("failing tests")
    if not isinstance(rec.get("tests_passing"), int) or rec["tests_passing"] <= 0:
        problems.append("no passing tests recorded")
    if rec.get("tree") != "clean":
        problems.append(f"tree {rec.get('tree')!r} during the run")
    return "; ".join(problems) or None


def find_suite_record(sha: str, fb: Path, explicit: Path | None) -> tuple[Path | None, str]:
    cands = [explicit] if explicit else sorted(
        list(fb.glob("RUN_*_full_suite.json"))
        + list((fb.parents[1] / "artifacts" / "suite_runs").glob("*.json")))
    why = []
    for p in cands:
        try:
            rec = json.loads(Path(p).read_text())
        except (OSError, ValueError) as e:
            why.append(f"{p}: unreadable ({type(e).__name__})")
            continue
        if not isinstance(rec, dict):
            continue
        r = suite_refusal(rec, sha)
        if r is None:
            return Path(p), ""
        if explicit or rec.get("git_sha") == sha:
            why.append(f"{Path(p).name}: {r}")
    return None, ("; ".join(why) or f"no suite record for {sha[:12]}")


def _code_changed(repo: Path, a: str, b: str) -> list[str]:
    names = _git(repo, "diff", "--name-only", a, b).stdout.split()
    return [n for n in names if n.startswith(CODE_PATHS)]


def find_rehearsal(repo: Path, sha: str, fb: Path, explicit: Path | None):
    cands = [explicit] if explicit else sorted((fb / "evidence").glob("shadow_rehearsal_*.json"),
                                               reverse=True)
    why = []
    for p in cands:
        try:
            ev = json.loads(Path(p).read_text())
        except (OSError, ValueError) as e:
            why.append(f"{p}: unreadable ({type(e).__name__})")
            continue
        head = ev.get("head") or ""
        if ev.get("kind") != "shadow_rehearsal" or ev.get("mode") != "production":
            why.append(f"{Path(p).name}: not a production-mode shadow rehearsal")
            continue
        if ev.get("tree_dirty"):
            why.append(f"{Path(p).name}: rehearsed on a dirty tree")
            continue
        if head == sha:
            return Path(p), ev, "exact"
        if len(head) == 40 and _git(repo, "merge-base", "--is-ancestor", head, sha).returncode == 0:
            changed = _code_changed(repo, head, sha)
            if not changed:
                return Path(p), ev, f"ancestor {head[:12]} with no code change to {sha[:12]}"
            why.append(f"{Path(p).name}: code changed since {head[:7]}: {changed[:5]}")
        elif explicit:
            why.append(f"{Path(p).name}: rehearsed {head[:12]}, not {sha[:12]} or an ancestor")
    return None, None, ("; ".join(why) or f"no shadow-rehearsal evidence for {sha[:12]}")


def check(repo: Path, sha_arg: str, *, fb: Path = FB, suite: Path | None = None,
          rehearsal: Path | None = None) -> dict:
    """Every precondition, evaluated; `refusals` empty means the freeze may proceed."""
    refusals: list[str] = []
    r = _git(repo, "rev-parse", "--verify", f"{sha_arg}^{{commit}}")
    sha = r.stdout.strip() if r.returncode == 0 else ""
    if not sha:
        return {"sha": None, "refusals": [f"{sha_arg!r} is not a commit"]}
    sha7 = sha[:7]
    head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    if head != sha:
        refusals.append(f"{sha7} is not the checked-out HEAD ({head[:7]}); the clean-tree "
                        f"check would not be about it")
    dirty = _git(repo, "status", "--porcelain").stdout.strip()
    if dirty:
        refusals.append(f"working tree not clean: {dirty.splitlines()[:5]}")
    suite_path, why = find_suite_record(sha, fb, suite)
    if suite_path is None:
        refusals.append(f"no release-eligible suite record for exactly {sha7}: {why}")
    reh_path, reh, reh_why = find_rehearsal(repo, sha, fb, rehearsal)
    if reh_path is None:
        refusals.append(f"no shadow-rehearsal evidence binding {sha7}: {reh_why}")
    matrix_p = fb / "closure_matrix.json"
    summary = None
    try:
        summary = json.loads(matrix_p.read_text())["summary"]
        if "launch_critical_open" not in summary:
            refusals.append("closure matrix lacks the computed completion summary "
                            "(re-run research/final_build/aggregate.py)")
    except (OSError, ValueError, KeyError) as e:
        refusals.append(f"closure matrix unreadable: {type(e).__name__}")
    tag = f"final-candidate-{sha7}"
    if _git(repo, "rev-parse", "--verify", "--quiet", f"refs/tags/{tag}").returncode == 0:
        refusals.append(f"tag {tag} already exists")
    return {"sha": sha, "sha7": sha7, "tag": tag, "refusals": refusals,
            "suite": suite_path, "rehearsal": reh_path, "rehearsal_binding": reh_why
            if reh_path else None, "rehearsal_evidence": reh, "matrix": matrix_p,
            "summary": summary}


def freeze(repo: Path, sha_arg: str, *, fb: Path = FB, suite: Path | None = None,
           rehearsal: Path | None = None, dry_run: bool = False) -> dict:
    c = check(repo, sha_arg, fb=fb, suite=suite, rehearsal=rehearsal)
    if c["refusals"] or dry_run:
        return {"frozen": False, **{k: (str(v) if isinstance(v, Path) else v)
                                    for k, v in c.items() if k != "rehearsal_evidence"}}
    sha, sha7, tag = c["sha"], c["sha7"], c["tag"]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    matrix = json.loads(c["matrix"].read_text())
    lc_defects = [{"uid": r["uid"], "defect": r["defect"], "completion": r.get("completion")}
                  for r in matrix["matrix"]
                  if r.get("launch_class") == "LAUNCH-CRITICAL" and r.get("defect")]
    reh = c["rehearsal_evidence"]
    ledger_p = fb / f"DEFECT_LEDGER_{sha7}.json"
    candidate_p = fb / f"CANDIDATE_{sha7}.json"
    rel = lambda p: str(Path(p).resolve().relative_to(repo.resolve()))  # noqa: E731
    candidate = {
        "candidate": sha, "tag": tag, "frozen_at": now, "pushed": False,
        "suite_record": {"path": rel(c["suite"]), "sha256": _sha256(c["suite"])},
        "matrix": {"path": rel(c["matrix"]), "sha256": _sha256(c["matrix"]),
                   "basis": matrix.get("basis"), "summary": c["summary"],
                   "launch_critical_open": c["summary"].get("launch_critical_open")},
        "rehearsal": {"path": rel(c["rehearsal"]), "sha256": _sha256(c["rehearsal"]),
                      "binding": c["rehearsal_binding"], "complete": reh.get("complete"),
                      "outcomes": reh.get("outcomes")},
        "defect_ledger": rel(ledger_p),
        "next": "independent audit of this exact SHA by a different model/session (F-846); "
                "repairs land on a successor candidate, never on this tag",
    }
    ledger = {"candidate": sha, "opened_at": now, "status": "open",
              "rule": "F-846: freeze -> independent audit -> ledger -> repair -> regression "
                      "test -> full suite -> independent re-audit",
              "defects": [{"source": "shadow_rehearsal", "key": d["key"], "where": d["where"],
                           "detail": d["detail"], "status": "open"}
                          for d in reh.get("blocking_defects") or []]
              + [{"source": "closure_matrix", "key": d["uid"], "where": "closure_matrix.json",
                  "detail": d["defect"], "status": "open"} for d in lc_defects]}
    msg = (f"Final Build launch candidate {sha7}\n\nsuite {candidate['suite_record']['path']} "
           f"sha256 {candidate['suite_record']['sha256']}\nmatrix launch-critical OPEN "
           f"{candidate['matrix']['launch_critical_open']}\nrehearsal "
           f"{candidate['rehearsal']['path']} ({c['rehearsal_binding']})\n")
    t = _git(repo, "tag", "-a", tag, sha, "-m", msg)
    if t.returncode != 0:
        return {"frozen": False, "sha": sha, "refusals": [f"git tag failed: {t.stderr[:300]}"]}
    candidate_p.write_text(json.dumps(candidate, indent=1) + "\n")
    ledger_p.write_text(json.dumps(ledger, indent=1) + "\n")
    return {"frozen": True, "sha": sha, "tag": tag, "candidate": str(candidate_p),
            "defect_ledger": str(ledger_p), "refusals": []}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--sha", default="HEAD")
    p.add_argument("--suite-record", type=Path, default=None)
    p.add_argument("--rehearsal", type=Path, default=None)
    p.add_argument("--dry-run", action="store_true", help="evaluate only; write and tag nothing")
    a = p.parse_args()
    out = freeze(ROOT.parent, a.sha, suite=a.suite_record, rehearsal=a.rehearsal,
                 dry_run=a.dry_run)
    print(json.dumps(out, indent=1, default=str))
    return 0 if out["frozen"] or (a.dry_run and not out["refusals"]) else 2


if __name__ == "__main__":
    sys.exit(main())
