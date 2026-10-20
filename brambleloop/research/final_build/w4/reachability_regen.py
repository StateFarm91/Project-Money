"""W4-CLOSE5: regenerate module_reachability.json on a clean tree of a given commit.

Same method as W4-FMGATE (0417f35): build2.reachability.reached() for every module under
src/brambleloop of the tree it is run in, plus whether the module exists in the trees the
adjudicator compares against (fcb982d, 0417f35, and the commit given).

  cd <clean worktree of SHA>/brambleloop && PYTHONPATH=src python3 \
      <this file> <full sha> <out.json>
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _tree(sha: str, repo: Path) -> set[str]:
    out = subprocess.run(["git", "-C", str(repo), "ls-tree", "-r", "--name-only", sha, "--",
                          "brambleloop/src/brambleloop"], capture_output=True, text=True).stdout
    return {p.split("brambleloop/src/brambleloop/", 1)[1] for p in out.split() if p.endswith(".py")}


def main(sha: str, out: str) -> int:
    from brambleloop.build2 import reachability as R

    src = Path("src/brambleloop").resolve()
    repo = src.parents[2]
    head = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True,
                          text=True).stdout.strip()
    assert head == sha, (head, sha)
    dirty = subprocess.run(["git", "-C", str(repo), "status", "--porcelain", "--",
                            "brambleloop/src"], capture_output=True, text=True).stdout.strip()
    assert not dirty, f"src is not clean: {dirty[:200]}"
    fcb, f0417, here = (_tree("fcb982d57e291c88d9f78eaa091e90904b6c2cc9", repo),
                        _tree("0417f3516f30bb7c52926187fc475a0f46536e86", repo), _tree(sha, repo))
    mods = {}
    for p in sorted(src.rglob("*.py")):
        rel = p.relative_to(src).as_posix()
        v = R.reached(rel)
        mods[rel] = {"reached": bool(v["reached"]), "why": v["why"],
                     **({"live": v["live"]} if v.get("live") else {}),
                     "in_production_fcb982d": rel in fcb, "in_production_0417f35": rel in f0417,
                     f"in_production_{sha[:7]}": rel in here}
    basis = (f"HEAD {sha[:7]} (deployed production {sha} per /health build.commit "
             f"2026-10-20T04:16Z; clean detached worktree, W4-CLOSE5) reachability; production "
             f"field in_production_fcb982d kept for aggregate.cap, in_production_0417f35 and "
             f"in_production_{sha[:7]} added")
    Path(out).write_text(json.dumps({"basis": basis, "modules": mods}, indent=1) + "\n")
    print(json.dumps({"modules": len(mods), "reached": sum(m["reached"] for m in mods.values())}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1], sys.argv[2]))
