#!/usr/bin/env python3
"""Durable per-suite checkpoints for run_tests.sh: resume and shard (W4-B1, 2026-10-27).

WHY. Container restarts (about 2026-10-26T08:17Z and 2026-10-27T01:29Z; no OOM, no disk
exhaustion, no journal -- the platform's container lifecycle is the likely cause, unproven)
killed two multi-hour full suites, and a killed run had to start again from nothing. With
CHECKPOINT=1 each suite's result is written to disk the moment it finishes, so RESUME=<run id>
re-runs only what has no passing result.

WHAT IS PERSISTED. `artifacts/suite_runs/<run id>/` holds

  * `manifest.json` -- the run KEY and one entry per segment (an invocation of the run);
  * `<suite>.json` -- one result per suite: status (`running` until the suite exits, then
    `passed`/`failed`), its own start/finish times, exit code, OK count, segment and key;
  * `<suite>.out`  -- the suite's output, so a resumed run prints every suite in its report.

THE KEY. A resumed run is the same run only if everything that could change a result is the
same: git SHA, tree-clean flag, sha256 of requirements.lock and requirements-test.lock, the
Python/venv identity (real executable, version, prefix), JOBS, the suite set (scope + shard)
and a fingerprint of the environment flags that steer the suites. Any mismatch REFUSES the
resume (exit 4) and names the fields; nothing is re-run and the original record is untouched.

WHAT COUNTS. A suite counts as passed only from a `passed` result with the matching key. A
suite interrupted mid-run leaves `running`, which is never passed and is re-run. The final
record lists every suite exactly once with its own timestamps and segment, marks the run
`resumed: true` with the gaps between segments, and sets `release_eligible` to false for a
resumed or sharded run: whether a resumed run may ever certify a release is an owner
certification-policy decision, not this tool's.

SHARD=i/n selects the suites whose sha256(name) % n == i -- deterministic, independent of
which other suites exist, so adding a suite never moves the others between shards.

Subcommands (all used by run_tests.sh):
  shard SPEC SUITE...                       print this shard's suites (exit 2 on a bad SPEC)
  plan --dir D --jobs J --scope S [--shard X] [--resume] -- SUITE...
                                             print the suites to run; exit 4 on a key mismatch
  begin --dir D --run-id R [--resume] [--shard X] --jobs J --scope S -- SUITE...
  start --dir D SUITE                        write the `running` result
  finish --dir D SUITE --code C --out FILE   write the terminal result and keep the output
  restore --dir D --outdir O -- SUITE...     put reused results where the report reads them
  finalize --dir D --record R -- SUITE...    merge per-suite results into the run record
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

LOCKS = ("requirements.lock", "requirements-test.lock")
# Environment flags that change what a suite does. Run-local plumbing is excluded.
ENV_PREFIXES = ("BRAMBLELOOP_", "ETSY_", "ANTHROPIC_", "TMP_LEAK_STRICT", "REQUIRE_CLEAN")
ENV_EXCLUDE = {"BRAMBLELOOP_RUN_TMP", "_BRAMBLELOOP_SUITE_JOB"}
REFUSED = 4


def utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _safe(suite: str) -> str:
    return suite.replace("/", "_")


def _write(path: Path, body: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n")
    os.replace(tmp, path)                     # a reader never sees half a result


def _read(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def _git(*args: str) -> str:
    try:
        return subprocess.run(["git", *args], capture_output=True, text=True,
                              check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return ""


def _file_hash(name: str) -> str:
    p = Path(name)
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else "absent"


def env_fingerprint(env=None) -> dict:
    env = os.environ if env is None else env
    names = sorted(k for k in env if k.startswith(ENV_PREFIXES) and k not in ENV_EXCLUDE)
    digest = hashlib.sha256("\n".join(f"{k}={env[k]}" for k in names).encode()).hexdigest()
    return {"names": names, "sha256": digest}


def run_key(*, jobs: str, scope: str, shard: str, suites: list[str]) -> dict:
    sha = _git("rev-parse", "HEAD").strip() or "UNKNOWN"
    porcelain = _git("status", "--porcelain")
    # A dirty tree is the same tree only if its uncommitted content is the same too.
    dirty = hashlib.sha256((porcelain + _git("diff", "HEAD", "--binary")).encode()).hexdigest()
    return {
        "git_sha": sha,
        "tree_clean": sha != "UNKNOWN" and porcelain.strip() == "",
        "dirty_content_sha256": None if porcelain.strip() == "" else dirty,
        "locks": {name: _file_hash(name) for name in LOCKS},
        "python": {"executable": os.path.realpath(sys.executable),
                   "version": sys.version.split()[0], "prefix": os.path.realpath(sys.prefix)},
        "jobs": str(jobs),
        "scope": scope,
        "shard": shard or None,
        "suites_sha256": hashlib.sha256("\n".join(sorted(suites)).encode()).hexdigest(),
        "env": env_fingerprint(),
    }


def key_mismatch(a: dict, b: dict) -> list[str]:
    out = []
    for k in sorted(set(a) | set(b)):
        if k == "locks":
            for name in LOCKS:
                if (a.get(k) or {}).get(name) != (b.get(k) or {}).get(name):
                    out.append(f"locks.{name}")
        elif a.get(k) != b.get(k):
            out.append(k)
    return out


def shard_of(suite: str, n: int) -> int:
    return int(hashlib.sha256(Path(suite).name.encode()).hexdigest(), 16) % n


def parse_shard(spec: str) -> tuple[int, int]:
    try:
        i, n = (int(x) for x in spec.split("/"))
    except ValueError:
        raise SystemExit(f"SHARD must be i/n, got {spec!r}") from None
    if n < 1 or not 0 <= i < n:
        raise SystemExit(f"SHARD {spec!r}: need 0 <= i < n")
    return i, n


def passed(result: dict | None, key: dict) -> bool:
    return bool(result and result.get("status") == "passed" and result.get("key") == key)


# ---- subcommands ----------------------------------------------------------------------------

def cmd_shard(a) -> int:
    try:
        i, n = parse_shard(a.spec)
    except SystemExit as exc:
        print(exc, file=sys.stderr)
        return 2
    for s in a.suites:
        if shard_of(s, n) == i:
            print(s)
    return 0


def cmd_plan(a) -> int:
    d = Path(a.dir)
    key = run_key(jobs=a.jobs, scope=a.scope, shard=a.shard, suites=a.suites)
    if not a.resume:
        if (d / "manifest.json").exists():
            print(f"REFUSED: {d} already holds a run; use RESUME=<run id>", file=sys.stderr)
            return REFUSED
        print("\n".join(a.suites))
        return 0
    man = _read(d / "manifest.json")
    if man is None:
        print(f"REFUSED: RESUME: no checkpoint manifest at {d}/manifest.json", file=sys.stderr)
        return REFUSED
    bad = key_mismatch(man["key"], key)
    if bad:
        print("REFUSED: RESUME key mismatch on " + ", ".join(bad) + "; nothing was run. A "
              "resumed run must match the original exactly (SHA, tree, locks, Python, JOBS, "
              "suite set, environment flags).", file=sys.stderr)
        return REFUSED
    todo = [s for s in a.suites if not passed(_read(d / f"{_safe(s)}.json"), man["key"])]
    print("\n".join(todo))
    return 0


def cmd_begin(a) -> int:
    d = Path(a.dir)
    d.mkdir(parents=True, exist_ok=True)
    key = run_key(jobs=a.jobs, scope=a.scope, shard=a.shard, suites=a.suites)
    man = _read(d / "manifest.json") if a.resume else None
    if man is None:
        man = {"run_id": a.run_id, "key": key, "segments": [], "suites": sorted(a.suites)}
    man["segments"].append({"n": len(man["segments"]) + 1, "started_utc": utc(),
                            "pid": os.getppid(), "to_run": sorted(a.to_run or [])})
    _write(d / "manifest.json", man)
    return 0


def _segment(d: Path) -> tuple[dict, int]:
    man = _read(d / "manifest.json") or {"key": None, "segments": [{"n": 1}]}
    return man, man["segments"][-1]["n"]


def cmd_start(a) -> int:
    d = Path(a.dir)
    man, seg = _segment(d)
    _write(d / f"{_safe(a.suite)}.json",
           {"suite": a.suite, "status": "running", "started_utc": utc(), "finished_utc": None,
            "exit_code": None, "ok_count": None, "segment": seg, "key": man["key"]})
    return 0


def cmd_finish(a) -> int:
    d = Path(a.dir)
    man, seg = _segment(d)
    path = d / f"{_safe(a.suite)}.json"
    res = _read(path) or {"suite": a.suite, "started_utc": None, "segment": seg}
    out = Path(a.out)
    text = out.read_text(errors="replace") if out.is_file() else ""
    (d / f"{_safe(a.suite)}.out").write_text(text)
    ok = sum(1 for line in text.splitlines() if line.startswith("OK"))
    code = int(a.code)
    res.update(status="passed" if code == 0 and ok > 0 else "failed", exit_code=code,
               ok_count=ok, finished_utc=utc(), key=man["key"])
    _write(path, res)
    return 0


def cmd_restore(a) -> int:
    d, o = Path(a.dir), Path(a.outdir)
    for s in a.suites:
        safe = _safe(s)
        if (o / f"{safe}.code").exists():
            continue                          # ran in this segment
        res = _read(d / f"{safe}.json")
        src = d / f"{safe}.out"
        if res is None or res.get("status") != "passed" or not src.is_file():
            continue                          # the report says "never ran"
        (o / f"{safe}.out").write_text(src.read_text(errors="replace"))
        (o / f"{safe}.code").write_text(f"{res['exit_code']}\n")
        (o / f"{safe}.leak").write_text("0 0\n")
    return 0


def cmd_finalize(a) -> int:
    d = Path(a.dir)
    man = _read(d / "manifest.json")
    rec = _read(Path(a.record)) or {}
    if man is None:
        return 0
    man["segments"][-1]["finished_utc"] = utc()
    _write(d / "manifest.json", man)
    results = []
    for s in sorted(a.suites):
        r = _read(d / f"{_safe(s)}.json") or {"status": "never_ran"}
        results.append({"suite": s, "status": r.get("status"),
                        "started_utc": r.get("started_utc"),
                        "finished_utc": r.get("finished_utc"), "exit_code": r.get("exit_code"),
                        "ok_count": r.get("ok_count"), "segment": r.get("segment")})
    segs = man["segments"]
    gaps = []
    for prev, nxt in zip(segs, segs[1:]):
        gaps.append({"after_segment": prev["n"], "from_utc": prev.get("finished_utc"),
                     "to_utc": nxt["started_utc"]})
    resumed = len(segs) > 1
    rec["checkpoint"] = {"dir": str(d), "key": man["key"], "segments": segs,
                         "resumed": resumed, "gaps": gaps, "shard": man["key"].get("shard")}
    rec["resumed"] = resumed
    rec["suite_results"] = results
    rec["started_utc"] = segs[0]["started_utc"]
    if resumed or man["key"].get("shard"):
        rec["release_eligible"] = False
        rec["release_eligible_reason"] = (
            "resumed run: whether a resumed run may certify a release is an owner "
            "certification-policy decision (default false)" if resumed else
            "sharded run: one shard is not the full suite")
    _write(Path(a.record), rec)
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("shard"); s.add_argument("spec"); s.add_argument("suites", nargs="*")
    for name in ("plan", "begin"):
        s = sub.add_parser(name)
        s.add_argument("--dir", required=True); s.add_argument("--jobs", required=True)
        s.add_argument("--scope", required=True); s.add_argument("--shard", default="")
        s.add_argument("--resume", action="store_true")
        if name == "begin":
            s.add_argument("--run-id", required=True); s.add_argument("--to-run", nargs="*")
        s.add_argument("suites", nargs="*")
    s = sub.add_parser("start"); s.add_argument("--dir", required=True); s.add_argument("suite")
    s = sub.add_parser("finish"); s.add_argument("--dir", required=True)
    s.add_argument("suite"); s.add_argument("--code", required=True)
    s.add_argument("--out", required=True)
    s = sub.add_parser("restore"); s.add_argument("--dir", required=True)
    s.add_argument("--outdir", required=True); s.add_argument("suites", nargs="*")
    s = sub.add_parser("finalize"); s.add_argument("--dir", required=True)
    s.add_argument("--record", required=True); s.add_argument("suites", nargs="*")
    a = p.parse_args(argv)
    return {"shard": cmd_shard, "plan": cmd_plan, "begin": cmd_begin, "start": cmd_start,
            "finish": cmd_finish, "restore": cmd_restore, "finalize": cmd_finalize}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
