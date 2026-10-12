"""W4-FMGATE: freeze record for the DEPLOYED candidate 0417f35 (F-845/F-846), via
scripts/freeze_candidate.py's own `check()`.

`freeze_candidate.freeze()` writes its files into the checkout it validates and requires that
checkout to be clean, so it cannot also hold the rehearsal evidence it binds. This adapter runs
`check()` against a clean detached worktree at the candidate (refusals must be []), then writes
CANDIDATE_<sha7>.json / DEFECT_LEDGER_<sha7>.json here with exactly freeze()'s fields, paths
relative to the repository and every bound file pinned by sha256. It creates no tag and pushes
nothing (a freeze ref is the integrator's push).

  python3 research/final_build/w4/fmgate_freeze.py --rc <clean worktree at sha> --sha <sha> \
      --rehearsal research/final_build/evidence/shadow_rehearsal_<sha7>.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
BL = HERE.parents[2]                      # brambleloop/ of this checkout
REPO = BL.parent


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rc", required=True, type=Path)
    ap.add_argument("--sha", required=True)
    ap.add_argument("--rehearsal", required=True)
    a = ap.parse_args(argv)
    rc = a.rc.resolve()
    src = (BL / "scripts" / "freeze_candidate.py").read_text().replace(
        "ROOT = Path(__file__).resolve().parents[1]", f"ROOT = Path({str(rc / 'brambleloop')!r})")
    ns = {"__name__": "freeze_candidate_rc", "__file__": str(BL / "scripts/freeze_candidate.py")}
    exec(compile(src, "freeze_candidate.py", "exec"), ns)
    reh = (BL / a.rehearsal) if not Path(a.rehearsal).is_absolute() else Path(a.rehearsal)
    c = ns["check"](rc, a.sha, fb=rc / "brambleloop/research/final_build", rehearsal=reh)
    if c["refusals"]:
        print(json.dumps({"frozen": False, "refusals": c["refusals"]}, indent=1))
        return 2
    sha, sha7 = c["sha"], c["sha7"]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    matrix_bytes = subprocess.run(["git", "-C", str(rc), "show",
                                   f"{sha}:brambleloop/research/final_build/closure_matrix.json"],
                                  capture_output=True, check=True).stdout
    matrix = json.loads(matrix_bytes)
    suite_rel = Path(c["suite"]).resolve().relative_to(rc).as_posix()
    suite_bytes = (rc / suite_rel).read_bytes()
    ev = json.loads(reh.read_text())
    reh_rel = reh.resolve().relative_to(REPO).as_posix()
    fb = BL / "research" / "final_build"
    lc_defects = [{"uid": r["uid"], "defect": r["defect"], "completion": r.get("completion")}
                  for r in matrix["matrix"]
                  if r.get("launch_class") == "LAUNCH-CRITICAL" and r.get("defect")]
    candidate = {
        "candidate": sha, "tag": None,
        "tag_not_created": ("no local tag or freeze-ref branch is created by this lane (pushes "
                            "are restricted to claude/w4-FMGATE); the deployed production "
                            "branch claude/repository-setup-nc9x6o points at this SHA "
                            "(/health build.commit) and release/DEPLOYED_HISTORY.json records "
                            "it. Integrator: push refs/heads/claude/final-candidate-" + sha7),
        "deployed": {"observed": "2026-10-11T14:39:50Z", "how": "GET /health build.commit, "
                     "known:true; /api/status boot_guard enforced:true ok:true",
                     "evidence": "brambleloop/research/final_build/w4/evidence_FMGATE_0417f35/"},
        "frozen_at": now, "pushed": False,
        "freeze_check": {"tool": "scripts/freeze_candidate.py::check (PACKETREL guard-rule "
                                 "binding)", "worktree": "clean detached worktree at " + sha,
                         "refusals": []},
        "suite_record": {"path": suite_rel, "sha256": _sha(suite_bytes),
                         "binding": c["suite_binding"]},
        "matrix": {"path": "brambleloop/research/final_build/closure_matrix.json", "at": sha,
                   "sha256": _sha(matrix_bytes), "basis": matrix.get("basis"),
                   "summary": c["summary"],
                   "launch_critical_open": c["summary"].get("launch_critical_open")},
        "rehearsal": {"path": reh_rel, "sha256": _sha(reh.read_bytes()),
                      "binding": c["rehearsal_binding"], "complete": ev.get("complete"),
                      "outcomes": ev.get("outcomes")},
        "defect_ledger": f"brambleloop/research/final_build/DEFECT_LEDGER_{sha7}.json",
        "next": "independent audit of this exact SHA by a different model/session (F-846); "
                "repairs land on a successor candidate, never on this SHA",
    }
    ledger = {"candidate": sha, "opened_at": now, "status": "open",
              "rule": "F-846: freeze -> independent audit -> ledger -> repair -> regression "
                      "test -> full suite -> independent re-audit",
              "defects": [{"source": "shadow_rehearsal", "key": d["key"], "where": d["where"],
                           "detail": d["detail"], "status": "open"}
                          for d in ev.get("blocking_defects") or []]
              + [{"source": "closure_matrix", "key": d["uid"], "where": "closure_matrix.json",
                  "detail": d["defect"], "status": "open"} for d in lc_defects]}
    (fb / f"CANDIDATE_{sha7}.json").write_text(json.dumps(candidate, indent=1) + "\n")
    (fb / f"DEFECT_LEDGER_{sha7}.json").write_text(json.dumps(ledger, indent=1) + "\n")
    print(json.dumps({"frozen": True, "sha": sha, "defects": len(ledger["defects"])}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
