#!/usr/bin/env python3
"""F-861 / F-862 / F-863: build-session handoffs that live in Git, not in a conversation.

F-861 Repository Is Shared Memory -- "Critical state lives in Git/database/evidence artifacts,
not conversation context."
F-862 Durable Handoffs -- "Long AI-development tasks persist objective, branch/head, decisions,
defects, tests, unfinished work and next actions."
F-863 Context Is a Cache -- "Persist conclusions before context pressure and reread durable
state after compaction/restart."

`ops/session_log.py checkpoint` (F-864) records a lane's SHA and uncommitted paths. That is
where a lane stopped, not what it knew. A successor also needs the objective, the decisions
already made, the defects found, the tests that prove it, the unfinished work and the next
action -- and until now those lived in the session's context and its final chat message.

  write     the handoff for a lane: a JSON file in the repository
            (`research/final_build/handoffs/<lane>.json`), every field required (defects may be
            an explicit empty list), branch and head read from git, never typed.
            It is DURABLE only when the head is on a remote ref and nothing tracked is left
            uncommitted; otherwise it says NOT_DURABLE and why (F-861: a head that exists
            only in this container is conversation state with extra steps).
  conclude  append one conclusion to the lane's decisions immediately (F-863: persisted when
            reached, not at the end of a session that may not get one).
  resume    reread a lane's handoff and re-verify it against git now: is the recorded head
            still the branch's remote tip, or did the branch move / vanish (F-863: after a
            restart the durable state is reread and checked, not remembered).

Writes only the handoff file; never commits, pushes or touches production.

  python3 ops/handoff.py write --lane L --objective "..." --decisions a;b --defects "" \
          --tests t1.py,t2.py --unfinished x;y --next "..." [--repo DIR]
  python3 ops/handoff.py conclude --lane L --text "..."
  python3 ops/handoff.py resume --lane L [--repo DIR]
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HANDOFF_DIR = ROOT / "brambleloop" / "research" / "final_build" / "handoffs"
LIST_FIELDS = ("decisions", "defects", "tests", "unfinished", "next_actions")
DURABLE, NOT_DURABLE = "DURABLE", "NOT_DURABLE"


class HandoffRefused(ValueError):
    pass


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _git(repo: Path, *args) -> tuple[int, str]:
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    return r.returncode, r.stdout.strip()


def _path(lane: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,80}", lane or ""):
        raise HandoffRefused(f"lane name {lane!r} is not a plain identifier")
    return HANDOFF_DIR / f"{lane}.json"


def _clean_list(name: str, value) -> list[str]:
    if value is None:
        raise HandoffRefused(f"{name} is missing (give an explicit empty list if there are none)")
    if isinstance(value, str):
        value = [v for v in re.split(r"[;\n]", value)]
    out = [str(v).strip() for v in value if str(v).strip()]
    if name != "defects" and not out:
        raise HandoffRefused(f"{name} is empty: a handoff without {name} cannot be resumed")
    return out


def durability(repo: Path, head: str) -> dict:
    code, remotes = _git(repo, "branch", "-r", "--contains", head)
    on_remote = code == 0 and bool(remotes.strip())
    st = subprocess.run(["git", "-C", str(repo), "status", "--porcelain",
                         "--untracked-files=no"], capture_output=True, text=True).stdout
    uncommitted = [ln[3:] for ln in st.splitlines() if ln.strip()]   # unstripped: "XY path"
    reasons = []
    if not on_remote:
        reasons.append(f"head {head[:12]} is on no remote ref: push it, or a restart loses it")
    if uncommitted:
        reasons.append(f"{len(uncommitted)} tracked path(s) uncommitted: {uncommitted[:10]}")
    return {"state": NOT_DURABLE if reasons else DURABLE, "on_remote": on_remote,
            "uncommitted": uncommitted, "reasons": reasons}


def write(*, lane: str, objective: str, repo: Path = ROOT, **fields) -> dict:
    if len(str(objective or "").split()) < 3:
        raise HandoffRefused("objective must say what the lane achieves (a sentence)")
    lists = {k: _clean_list(k, fields.get(k)) for k in LIST_FIELDS}
    code, head = _git(repo, "rev-parse", "HEAD")
    if code != 0:
        raise HandoffRefused(f"{repo} is not a git checkout with a commit")
    _, branch = _git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    p = _path(lane)
    prior = {}
    try:
        prior = json.loads(p.read_text())
    except (OSError, ValueError):
        pass
    rec = {"lane": lane, "objective": " ".join(str(objective).split()), "branch": branch,
           "head": head, "written_utc": _utc(), **lists,
           "conclusions": prior.get("conclusions", []),
           "durability": durability(repo, head)}
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(rec, indent=1) + "\n")
    os.replace(tmp, p)
    return rec


def conclude(*, lane: str, text: str) -> dict:
    text = " ".join(str(text or "").split())
    if not text:
        raise HandoffRefused("an empty conclusion persists nothing")
    p = _path(lane)
    try:
        rec = json.loads(p.read_text())
    except (OSError, ValueError):
        rec = {"lane": lane, "conclusions": []}
    rec.setdefault("conclusions", []).append({"utc": _utc(), "text": text})
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(rec, indent=1) + "\n")
    os.replace(tmp, p)
    return rec


def resume(*, lane: str, repo: Path = ROOT, remote: str = "origin") -> dict:
    p = _path(lane)
    try:
        rec = json.loads(p.read_text())
    except (OSError, ValueError):
        return {"lane": lane, "found": False,
                "why": f"no handoff at {p}: nothing durable to resume from"}
    missing = [k for k in ("objective", "branch", "head", *LIST_FIELDS) if k not in rec]
    check = {"recorded_head": rec.get("head"), "branch": rec.get("branch")}
    if rec.get("branch") and rec.get("head"):
        code, tip = _git(repo, "rev-parse", "--verify", "--quiet",
                         f"refs/remotes/{remote}/{rec['branch']}")
        if code != 0 or not tip:
            check["remote"] = "MISSING"
        elif tip == rec["head"]:
            check["remote"] = "AT_HEAD"
        else:
            anc = _git(repo, "merge-base", "--is-ancestor", rec["head"], tip)[0] == 0
            check.update(remote="MOVED_AHEAD" if anc else "DIVERGED", remote_tip=tip)
    return {"lane": lane, "found": True, "incomplete_fields": missing, "verify": check,
            "handoff": rec,
            "read_first": ["objective", "next_actions", "unfinished", "conclusions",
                           "decisions", "defects", "tests"]}


def main(argv: list[str]) -> int:
    args = list(argv[1:])
    if not args:
        print(__doc__)
        return 2
    cmd, opts = args[0], {}
    rest = args[1:]
    while rest:
        k = rest.pop(0)
        if not k.startswith("--") or not rest:
            print(__doc__)
            return 2
        opts[k[2:]] = rest.pop(0)
    repo = Path(opts.pop("repo", ROOT))
    try:
        if cmd == "write":
            out = write(lane=opts.get("lane", ""), objective=opts.get("objective", ""),
                        repo=repo, decisions=opts.get("decisions"),
                        defects=opts.get("defects"), tests=(opts.get("tests") or "")
                        .replace(",", ";") if "tests" in opts else None,
                        unfinished=opts.get("unfinished"),
                        next_actions=opts.get("next"))
        elif cmd == "conclude":
            out = conclude(lane=opts.get("lane", ""), text=opts.get("text", ""))
        elif cmd == "resume":
            out = resume(lane=opts.get("lane", ""), repo=repo)
        else:
            print(__doc__)
            return 2
    except HandoffRefused as exc:
        print(f"refused: {exc}")
        return 2
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
