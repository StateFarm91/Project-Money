#!/usr/bin/env python3
"""F-459 merge queue and F-460 integration checklist -- local build-side tooling only.

Completed lanes enter a FIFO queue (`enqueue`). `next` integrates the head of the queue into
a local target branch, and only in this checkout:

  1. refuses a protected target outright (the production branch is deployed only through
     ops/deploy.sh with the owner's per-SHA approval and the independent review -- never
     from here);
  2. reads the target's commit (the base), merges the lane's branch onto it in a throwaway
     worktree, and refuses on any conflict;
  3. runs the integration checklist there (F-460): the shared-contract pins
     (tests/test_w4_fmbatch1_contracts.py) and the lane's targeted suites; any failure
     refuses the merge;
  4. moves the local target ref with a compare-and-swap (`git update-ref new old`), so a
     target that moved while the checks ran is refused -- last-writer-wins cannot happen;
  5. records the merge commit on the lane in ops/registry.py, and prints the push command
     for the integrator. **It never pushes, never deploys, and never touches a remote.**

  python3 ops/integrate.py enqueue LANE BRANCH [--tests a.py,b.py]
  python3 ops/integrate.py list
  python3 ops/integrate.py next --target BRANCH [--repo DIR]
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
QUEUE = Path(os.environ.get("BRAMBLELOOP_MERGE_QUEUE") or (HERE / "MERGE_QUEUE.json"))
PROTECTED = frozenset({"claude/repository-setup-nc9x6o", "main", "master"})
CONTRACT_TESTS = ("brambleloop/tests/test_w4_fmbatch1_contracts.py",)


class Refused(RuntimeError):
    pass


def _git(repo, *args, check=True):
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if check and r.returncode != 0:
        raise Refused(f"git {' '.join(args)} failed: {r.stderr.strip()[:300]}")
    return r


def _load() -> dict:
    try:
        return json.loads(QUEUE.read_text())
    except (OSError, ValueError):
        return {"queue": [], "done": []}


def _save(d: dict) -> None:
    tmp = QUEUE.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, indent=1))
    os.replace(tmp, QUEUE)


def enqueue(lane: str, branch: str, tests: list[str] | None = None) -> dict:
    d = _load()
    if any(e["lane"] == lane for e in d["queue"]):
        raise Refused(f"{lane} is already queued")
    d["queue"].append({"lane": lane, "branch": branch, "tests": list(tests or []),
                       "enqueued_utc": datetime.now(timezone.utc).isoformat()})
    _save(d)
    return {"queued": lane, "position": len(d["queue"])}


def _checklist(worktree: Path, tests: list[str], python: str) -> list[dict]:
    out = []
    for t in list(CONTRACT_TESTS) + list(tests):
        path = worktree / t
        if not path.exists():
            out.append({"check": t, "ok": False, "why": "test file not in the merged tree"})
            continue
        r = subprocess.run([python, str(path)], capture_output=True, text=True,
                           cwd=str(path.parent.parent))
        out.append({"check": t, "ok": r.returncode == 0,
                    "tail": (r.stdout + r.stderr)[-400:]})
    return out


def next_lane(*, target: str, repo: Path, python: str = sys.executable,
              registry_path: Path | None = None) -> dict:
    if target in PROTECTED or target.startswith("refs/remotes/"):
        raise Refused(f"{target!r} is protected: production is deployed only through "
                      "ops/deploy.sh with the owner's per-SHA approval and review")
    d = _load()
    if not d["queue"]:
        return {"merged": None, "why": "the queue is empty"}
    entry = d["queue"][0]
    base = _git(repo, "rev-parse", f"refs/heads/{target}").stdout.strip()
    branch_sha = _git(repo, "rev-parse", entry["branch"]).stdout.strip()
    wt = Path(tempfile.mkdtemp(prefix="integrate-"))
    result = {"lane": entry["lane"], "branch": entry["branch"], "target": target,
              "base": base}
    try:
        _git(repo, "worktree", "add", "-q", "--detach", str(wt), base)
        m = _git(wt, "-c", "user.name=integrate", "-c", "user.email=integrate@local.invalid",
                 "merge", "--no-ff", "--no-edit", "-m",
                 f"integrate {entry['lane']} ({entry['branch']})", branch_sha, check=False)
        if m.returncode != 0:
            _git(wt, "merge", "--abort", check=False)
            return {**result, "merged": False, "why": "merge conflict: resolve on the lane "
                    "branch and re-queue", "detail": m.stdout[-400:]}
        checks = _checklist(wt, entry.get("tests") or [], python)
        result["checks"] = checks
        if not all(c["ok"] for c in checks):
            return {**result, "merged": False,
                    "why": "the integration checklist failed: " +
                           ", ".join(c["check"] for c in checks if not c["ok"])}
        new = _git(wt, "rev-parse", "HEAD").stdout.strip()
        cas = _git(repo, "update-ref", f"refs/heads/{target}", new, base, check=False)
        if cas.returncode != 0:
            return {**result, "merged": False,
                    "why": f"{target} moved while the checks ran; nothing was overwritten "
                           "(re-run next to integrate onto the new base)"}
    finally:
        _git(repo, "worktree", "remove", "--force", str(wt), check=False)
    d = _load()
    d["queue"] = [e for e in d["queue"] if e["lane"] != entry["lane"]]
    d["done"].append({**entry, "commit": new, "target": target,
                      "integrated_utc": datetime.now(timezone.utc).isoformat()})
    _save(d)
    try:
        sys.path.insert(0, str(HERE))
        import registry

        reg = registry.Registry(registry_path) if registry_path else registry.Registry()
        if entry["lane"] in reg.load()["jobs"]:
            reg.integrate(entry["lane"], new)
    except Exception:                                                  # noqa: BLE001
        pass
    return {**result, "merged": True, "commit": new,
            "next_step": (f"review, then push it yourself: git push origin {target} "
                          "(this tool never pushes; production stays behind ops/deploy.sh)")}


def main(argv: list[str]) -> int:
    argv = list(argv)
    opts = {}
    for flag in ("--tests", "--target", "--repo"):
        if flag in argv:
            i = argv.index(flag)
            opts[flag[2:]] = argv[i + 1]
            del argv[i:i + 2]
    cmd = argv[1] if len(argv) > 1 else "list"
    try:
        if cmd == "enqueue" and len(argv) >= 4:
            out = enqueue(argv[2], argv[3], [t for t in (opts.get("tests") or "").split(",") if t])
        elif cmd == "list":
            out = _load()
        elif cmd == "next" and opts.get("target"):
            out = next_lane(target=opts["target"], repo=Path(opts.get("repo") or HERE.parent))
        else:
            print(__doc__)
            return 2
    except Refused as exc:
        print(f"refused: {exc}")
        return 2
    print(json.dumps(out, indent=1))
    return 0 if out.get("merged", True) is not False else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
