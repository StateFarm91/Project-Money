#!/usr/bin/env python3
"""F-864 (session-limit survival), F-868 (empirical model routing), F-869 (approval friction).

Build-side only. One JSON line per event in `research/final_build/SESSION_LOG.jsonl` (in the
repository, so the next session and the integrator read it; never the production database):

  record     a session's outcome: model, lane, rows closed, commits, cost (CA$ or UNMEASURED),
             approval prompts seen (an integer the session counted, or UNMEASURED)
  checkpoint the lane's last pushed SHA plus every uncommitted path, written before a session
             risks its limit -- a successor resumes from the SHA and sees exactly what was
             left uncommitted (nothing is auto-committed or pushed by this tool)

`summary` routes by evidence: per model, rows closed per session, cost per row and approval
prompts per session -- each UNMEASURED where no session reported it, never zero.

  python3 ops/session_log.py record --model M --lane L --rows F-1,F-2 --commits a,b
                                    [--cost-cad 1.2] [--approvals 3]
  python3 ops/session_log.py checkpoint --lane L [--repo DIR]
  python3 ops/session_log.py summary
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOG = Path(os.environ.get("BRAMBLELOOP_SESSION_LOG")
           or HERE.parent / "brambleloop" / "research" / "final_build" / "SESSION_LOG.jsonl")
UNMEASURED = "UNMEASURED"


def _append(rec: dict) -> dict:
    rec = {"at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(), **rec}
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(json.dumps(rec, sort_keys=True) + "\n")
    return rec


def record(*, model: str, lane: str, rows: list[str], commits: list[str],
           cost_cad: float | None = None, approvals: int | None = None) -> dict:
    if not model.strip() or not lane.strip():
        raise ValueError("a session record names its model and lane")
    if approvals is not None and int(approvals) < 0:
        raise ValueError("approval prompts cannot be negative")
    return _append({"event": "session", "model": model.strip(), "lane": lane.strip(),
                    "rows": sorted(set(rows)), "commits": list(commits),
                    "cost_cad": round(float(cost_cad), 4) if cost_cad is not None else UNMEASURED,
                    "approval_prompts": int(approvals) if approvals is not None else UNMEASURED})


def checkpoint(*, lane: str, repo: Path) -> dict:
    def git(*a):
        r = subprocess.run(["git", "-C", str(repo), *a], capture_output=True, text=True)
        return r.stdout.strip() if r.returncode == 0 else None

    head = git("rev-parse", "HEAD")
    upstream = git("rev-parse", "@{u}")
    dirty = [ln[3:] for ln in (git("status", "--porcelain") or "").splitlines() if ln]
    return _append({"event": "checkpoint", "lane": lane, "head": head,
                    "pushed": head is not None and head == upstream,
                    "upstream": upstream, "uncommitted": dirty[:200]})


def _read() -> list[dict]:
    try:
        return [json.loads(ln) for ln in LOG.read_text().splitlines() if ln.strip()]
    except OSError:
        return []


def summary() -> dict:
    by: dict[str, dict] = {}
    for r in _read():
        if r.get("event") != "session":
            continue
        m = by.setdefault(r["model"], {"sessions": 0, "rows": 0, "cost": [], "approvals": []})
        m["sessions"] += 1
        m["rows"] += len(r.get("rows") or [])
        if isinstance(r.get("cost_cad"), (int, float)):
            m["cost"].append(r["cost_cad"])
        if isinstance(r.get("approval_prompts"), int):
            m["approvals"].append(r["approval_prompts"])
    out = {}
    for model, m in sorted(by.items()):
        out[model] = {
            "sessions": m["sessions"], "rows_per_session": round(m["rows"] / m["sessions"], 2),
            "cost_per_row_cad": (round(sum(m["cost"]) / m["rows"], 4)
                                 if m["cost"] and m["rows"] else UNMEASURED),
            "approval_prompts_per_session": (round(sum(m["approvals"]) / len(m["approvals"]), 2)
                                             if m["approvals"] else UNMEASURED)}
    return {"models": out, "log": str(LOG)}


def main(argv: list[str]) -> int:
    def opt(name, default=None):
        return argv[argv.index(name) + 1] if name in argv else default

    cmd = argv[1] if len(argv) > 1 else "summary"
    try:
        if cmd == "record":
            out = record(model=opt("--model", ""), lane=opt("--lane", ""),
                         rows=[r for r in (opt("--rows") or "").split(",") if r],
                         commits=[c for c in (opt("--commits") or "").split(",") if c],
                         cost_cad=float(opt("--cost-cad")) if opt("--cost-cad") else None,
                         approvals=int(opt("--approvals")) if opt("--approvals") else None)
        elif cmd == "checkpoint":
            out = checkpoint(lane=opt("--lane", "unknown"), repo=Path(opt("--repo", ".")))
        else:
            out = summary()
    except ValueError as exc:
        print(f"refused: {exc}")
        return 2
    print(json.dumps(out, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
