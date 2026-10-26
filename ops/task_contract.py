#!/usr/bin/env python3
"""F-712 (model-to-model task contract) and F-713 (isolation before collaboration).

A dispatched build lane used to carry its contract as a prose brief. This is the
machine-checked form, a JSON object with:

  base_sha      the commit the lane starts from (7-40 hex)
  objective     what the lane must achieve (a sentence, not a label)
  owned_paths   repository paths/globs the lane may change (ops/registry.py `--owns`)
  authority     one of BUILD_ONLY, BUILD_AND_PROPOSE -- never deploy, never push to a
                protected branch, never spend (the owner's per-SHA deploy approval and the
                independent review stay where they are)
  budget        {"max_hours": >0, "max_spend_cad": >=0}
  dependencies  lanes or rows it waits on (may be empty)
  outputs       what it hands back (non-empty)
  tests         test files it must leave passing (non-empty)
  sentinel      the line its log ends with when it finishes

`validate(contract)` refuses a missing or malformed field by name. `boundary(repo, base, head,
owned_paths)` lists the files changed between base and head that fall outside `owned_paths`
(path-segment aware, via ops/registry.paths_overlap); `ops/integrate.py` runs it as a
checklist item when a queued lane carries a contract, so an out-of-boundary change fails
integration instead of landing silently. Local tooling only: no network, no push.

  python3 ops/task_contract.py validate CONTRACT.json
  python3 ops/task_contract.py boundary CONTRACT.json HEAD_REF [--repo DIR]
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
AUTHORITIES = ("BUILD_ONLY", "BUILD_AND_PROPOSE")
FIELDS = ("base_sha", "objective", "owned_paths", "authority", "budget", "dependencies",
          "outputs", "tests", "sentinel")


class ContractRefused(ValueError):
    pass


def validate(c: dict) -> dict:
    if not isinstance(c, dict):
        raise ContractRefused("a task contract is a JSON object")
    missing = [f for f in FIELDS if f not in c]
    if missing:
        raise ContractRefused(f"missing field(s): {missing}")
    extra = sorted(set(c) - set(FIELDS))
    if extra:
        raise ContractRefused(f"unknown field(s): {extra}")
    problems = []
    if not re.fullmatch(r"[0-9a-f]{7,40}", str(c["base_sha"])):
        problems.append("base_sha must be 7-40 lowercase hex")
    if len(str(c["objective"]).split()) < 5:
        problems.append("objective must say what the lane achieves, not label it")
    for f in ("owned_paths", "outputs", "tests"):
        v = c[f]
        if not isinstance(v, list) or not v or not all(isinstance(x, str) and x.strip()
                                                        for x in v):
            problems.append(f"{f} must be a non-empty list of strings")
    if not isinstance(c["dependencies"], list):
        problems.append("dependencies must be a list (may be empty)")
    if c["authority"] not in AUTHORITIES:
        problems.append(f"authority must be one of {AUTHORITIES}")
    b = c["budget"]
    try:
        if not (isinstance(b, dict) and float(b["max_hours"]) > 0
                and float(b["max_spend_cad"]) >= 0 and set(b) == {"max_hours", "max_spend_cad"}):
            raise ValueError
    except (KeyError, TypeError, ValueError):
        problems.append("budget must be {max_hours > 0, max_spend_cad >= 0}")
    if not str(c["sentinel"]).strip():
        problems.append("sentinel must be the line the lane's log ends with")
    if problems:
        raise ContractRefused("; ".join(problems))
    return c


def changed_files(repo: Path, base: str, head: str) -> list[str]:
    r = subprocess.run(["git", "-C", str(repo), "diff", "--name-only", f"{base}...{head}"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise ContractRefused(f"git diff failed: {r.stderr.strip()[:200]}")
    return [ln for ln in r.stdout.splitlines() if ln.strip()]


def boundary(repo: Path, base: str, head: str, owned_paths: list[str]) -> list[str]:
    sys.path.insert(0, str(HERE))
    import registry

    return [f for f in changed_files(repo, base, head)
            if not any(registry.paths_overlap(f, p) and _inside(f, p) for p in owned_paths)]


def _inside(f: str, pattern: str) -> bool:
    """A changed file is inside a manifest entry when the entry's literal prefix contains it
    (a manifest entry *below* the file -- e.g. owning `a/b/c` -- does not cover `a/b`)."""
    import registry

    pre = registry._literal_prefix(pattern).rstrip("/")
    return not pre or f == pre or f.startswith(pre + "/") or (
        pre != pattern.rstrip("/") and f.startswith(pre))


def main(argv: list[str]) -> int:
    if len(argv) >= 3 and argv[1] == "validate":
        try:
            validate(json.loads(Path(argv[2]).read_text()))
        except (ContractRefused, ValueError) as exc:
            print(f"refused: {exc}")
            return 2
        print("valid")
        return 0
    if len(argv) >= 4 and argv[1] == "boundary":
        repo = Path(argv[argv.index("--repo") + 1]) if "--repo" in argv else Path.cwd()
        c = validate(json.loads(Path(argv[2]).read_text()))
        out = boundary(repo, c["base_sha"], argv[3], c["owned_paths"])
        print(json.dumps({"outside_boundary": out}, indent=1))
        return 1 if out else 0
    print(__doc__.strip().splitlines()[0])
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
