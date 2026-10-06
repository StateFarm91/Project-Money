#!/usr/bin/env python3
"""Refuse a production deploy that could overwrite newer verified state or is not proven (F-461).

Usage:
  python3 ops/deploy_guard.py check --candidate <rev> --deployed <sha>   -> exit 0 ALLOW, 1 REFUSE
  python3 ops/deploy_guard.py latest-suite [--sha <rev>] [--eligible]    -> the newest run record
  python3 ops/deploy_guard.py pre-push <remote> <url>  (stdin: git pre-push lines) -> 0 / 1

ON THE DEPLOY PATH (F-461, wired). Production deploys on a push to the production branch
(`PRODUCTION_BRANCH`; Railway builds it). Two doors lead there and both pass through `check`:

* `ops/hooks/pre-push` (installed by `ops/install_hooks.sh`, which sets `core.hooksPath`):
  git hands it every ref being pushed; any update to the production branch is checked and a
  REFUSE aborts the push. Pushes to any other branch are not deploys and pass untouched.
* `ops/deploy.sh`: the one sanctioned deploy command. It runs `check` on HEAD against the
  deployed commit and pushes to the production branch only on ALLOW.

The deployed commit comes from `--deployed`, else `BRAMBLELOOP_DEPLOYED_SHA` -- which the hook
and `ops/deploy.sh` fill from `ops/deployed_sha.py` (production's own `/api/status`,
`build.commit`, only when `build.known`). This module itself makes no network call. If nobody
says, the deployed commit is unknown and the verdict is REFUSE.

THIS SCRIPT NEVER DEPLOYS. It reads git and the suite run records and prints a verdict; the
integrator (the only role allowed to deploy) runs it and acts on the answer. It makes no network
call and starts no process other than read-only `git`. Deploy serialisation was a rule --
integrator-only deploys, departments GET-only in production -- and a rule is what a second
session racing the first does not know about. A guard is the rule as a computation.

TWO REFUSALS, BOTH COMPUTED

1. The candidate must be the deployed commit or a DESCENDANT of it. Seven workers develop in
   parallel on branches cut from different bases; deploying one of them whose history does not
   contain what production is running would silently roll production back -- overwrite a newer
   verified state with an older one. `git merge-base --is-ancestor <deployed> <candidate>`
   answers it. The deployed commit is an argument, read by the caller from production's own
   `/api/verify`; if it is unknown, or is not in this repository, descent cannot be established
   and the answer is REFUSE, not "probably fine". Unknown stays unknown.

2. The candidate must have a GREEN, RELEASE-ELIGIBLE full-suite record for that exact SHA:
   `run_tests.sh` writes one per run (F-345) and sets `release_eligible` only for a full,
   clean-tree, unmoved-HEAD, zero-failing run. The record is not believed on its own: its log
   must still exist, must name the same run and SHA in its header, and must carry the TOTAL line
   with `suites failing: 0` -- the job's own words, re-read, not the record's summary of them.
   Missing, red, filtered, dirty, or contradicted by its log: REFUSE.

TRACKED EVIDENCE ONLY (A3-05). The run record and its log live in `brambleloop/artifacts/`,
which is gitignored: nobody reviews it, a fresh clone does not have it, and the container
cannot see it. So `check` no longer believes it. The proof is a TRACKED release record,
`brambleloop/release/RELEASE_<sha>.json`, written by `record` from the local run record (after
the checks above pass) together with tracked copies of the run record and its log, each pinned
by sha256, and bound to the deployable tree digest (`src/**` without bytecode +
`requirements.lock`) of the SHA the suite ran on. It is committed on top of that SHA (a commit
cannot contain its own hash) and read by `check` from git at the candidate -- never from the
working tree. The same record is what the runtime boot guard (`brambleloop.ops.release_record`)
verifies inside the container, so a push that skipped this hook still runs only as SHADOW.

ROLLBACK (A3-06). Rolling production back is refused by rule 1 -- correctly, for an accident.
A deliberate rollback is a different act and has its own door: `rollback-commit --to <sha>
--reason "<owner reason>"` writes a commit on top of the deployed one whose tree is exactly
the tree of a previously deployed, recorded SHA (`brambleloop/release/DEPLOYED_HISTORY.json`),
with `Rollback-To:` / `Rollback-Reason:` trailers. `check` recognises it from those trailers:
the target must be in the deployed history (read from the deployed commit), the tree must be
identical to the target's, the reason must be stated, and the deployed commit must still be an
ancestor (it is a fast-forward, so history keeps the forward release). No release record is
asked of the target: it ran in production before, and that is its evidence. See
`ops/ROLLBACK_RUNBOOK.md`.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PRODUCTION_BRANCH = "claude/repository-setup-nc9x6o"
PRODUCTION_REF = f"refs/heads/{PRODUCTION_BRANCH}"
DEPLOYED_ENV = "BRAMBLELOOP_DEPLOYED_SHA"
ZERO = "0" * 40
RECORD_DIR = REPO / "brambleloop" / "artifacts" / "suite_runs"
_TOTAL = re.compile(r"^TOTAL PASSING: (\d+) ; suites failing: (\d+)\s*$", re.M)

#: Where the deployable tree and the tracked release evidence live, relative to the repo root.
#: `prefix` is stripped from paths before hashing, so the digest equals the one the boot
#: guard computes inside the image (where `brambleloop/` is the working directory).
LAYOUT = {"prefix": "brambleloop/", "dirs": ("src/",), "files": ("requirements.lock",),
          "release": "release"}
HISTORY_FILE = "DEPLOYED_HISTORY.json"
ROLLBACK_TO = "Rollback-To:"
ROLLBACK_REASON = "Rollback-Reason:"
MIN_REASON = 10


def _git_raw(repo: Path, *args: str, stdin: bytes | None = None):
    """The one process this module starts: read-only `git` (plus `commit-tree`, which only
    writes an unreferenced object for `rollback-commit`)."""
    return subprocess.run(["git", "-C", str(repo), *args], input=stdin, capture_output=True)


def _git(repo: Path, *args: str) -> tuple[int, str]:
    r = _git_raw(repo, *args)
    return r.returncode, r.stdout.decode(errors="replace").strip()


def resolve(repo: Path, rev: str) -> str | None:
    if not rev:
        return None
    code, out = _git(repo, "rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}")
    return out if code == 0 and out else None


def records(record_dir: Path = RECORD_DIR) -> list[dict]:
    """Every readable run record, newest first. An unreadable one is skipped, and counted."""
    out = []
    for p in sorted(Path(record_dir).glob("*.json")):
        try:
            rec = json.loads(p.read_text())
        except (OSError, ValueError):
            continue
        rec["_path"] = str(p)
        out.append(rec)
    out.sort(key=lambda r: (r.get("started_utc") or "", r.get("run_id") or ""), reverse=True)
    return out


def latest_suite(record_dir: Path = RECORD_DIR, *, sha: str | None = None,
                 eligible_only: bool = False) -> dict | None:
    """The newest run record, optionally for one SHA and/or release-eligible only."""
    for rec in records(record_dir):
        if sha and rec.get("git_sha") != sha:
            continue
        if eligible_only and not rec.get("release_eligible"):
            continue
        return rec
    return None


def _log_confirms(rec: dict, base: Path) -> str | None:
    """None if the record's own log backs it; otherwise why not."""
    raw = rec.get("log") or ""
    log = Path(raw) if Path(raw).is_absolute() else base / raw
    try:
        text = log.read_text(errors="replace")
    except OSError:
        return f"the run's log {raw!r} is gone, so the record cannot be re-derived"
    if f"RUN ID: {rec.get('run_id')}" not in text or f"GIT SHA: {rec.get('git_sha')}" not in text:
        return "the log does not name this run and SHA; record and log disagree"
    totals = _TOTAL.findall(text)
    if not totals:
        return "the log has no TOTAL line; the run did not finish"
    if int(totals[-1][1]) != 0:
        return f"the log says suites failing: {totals[-1][1]}"
    return None


# ---- tracked release evidence (A3-05) ------------------------------------------------------

def deployable(rel: str, layout: dict = LAYOUT) -> bool:
    """Same rule as `brambleloop.ops.release_record.deployable` (a test holds them equal)."""
    if rel in layout["files"]:
        return True
    if not rel.startswith(tuple(layout["dirs"])):
        return False
    return "__pycache__" not in rel.split("/") and not rel.endswith((".pyc", ".pyo"))


def tree_digest(entries) -> str:
    """Same function as `brambleloop.ops.release_record.tree_digest`."""
    h = hashlib.sha256()
    for rel, data in sorted(entries, key=lambda e: e[0]):
        h.update(rel.encode() + b"\0" + hashlib.sha256(data).hexdigest().encode() + b"\n")
    return h.hexdigest()


def _ls_tree(repo: Path, rev: str, *paths: str) -> list[tuple[str, str]]:
    """(mode, path) for every blob under `paths` at `rev`."""
    r = _git_raw(repo, "ls-tree", "-r", "-z", rev, "--", *paths)
    if r.returncode != 0:
        return []
    out = []
    for item in r.stdout.split(b"\0"):
        if not item:
            continue
        meta, path = item.split(b"\t", 1)
        mode, kind, _obj = meta.decode().split()
        if kind == "blob":
            out.append((mode, path.decode()))
    return out


def _blobs(repo: Path, rev: str, paths: list[str]) -> dict[str, bytes | None]:
    """Contents of `rev:path` for each path, read in one `git cat-file --batch`."""
    if not paths:
        return {}
    r = _git_raw(repo, "cat-file", "--batch",
                 stdin="".join(f"{rev}:{p}\n" for p in paths).encode())
    data, pos, out = r.stdout, 0, {p: None for p in paths}
    for p in paths:
        nl = data.find(b"\n", pos)
        if nl < 0:
            break
        header = data[pos:nl].decode(errors="replace").split()
        pos = nl + 1
        if len(header) == 3 and header[1] == "blob":
            size = int(header[2])
            out[p] = data[pos:pos + size]
            pos += size + 1
        else:
            out[p] = None
    return out


def git_tree_digest(repo: Path, rev: str, layout: dict = LAYOUT) -> str:
    pre = layout["prefix"]
    roots = [pre + d.rstrip("/") for d in layout["dirs"]] + [pre + f for f in layout["files"]]
    files = [p for mode, p in _ls_tree(repo, rev, *roots)
             if mode in ("100644", "100755") and deployable(p[len(pre):], layout)]
    blobs = _blobs(repo, rev, files)
    return tree_digest((p[len(pre):], blobs[p] or b"") for p in files)


def _record_problems(rec: dict, read) -> list[str]:
    """Why a release record does not prove its SHA; mirrors release_record.check_record."""
    reasons: list[str] = []
    sha = str(rec.get("sha") or "")
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        reasons.append("tracked release record does not name a full commit SHA")
    if rec.get("release_eligible") is not True:
        reasons.append("tracked release record is not marked release_eligible")
    suite = None
    for label, ref in (("suite run record", rec.get("suite_record") or {}),
                       ("suite log", rec.get("suite_log") or {})):
        rel = str(ref.get("path") or "")
        data = read(rel) if rel and ".." not in rel.split("/") else None
        if data is None:
            reasons.append(f"tracked {label} copy {rel!r} is gone from the commit")
            continue
        if hashlib.sha256(data).hexdigest() != ref.get("sha256"):
            reasons.append(f"tracked {label} copy {rel!r} does not match its pinned sha256")
            continue
        if label == "suite run record":
            try:
                suite = json.loads(data)
            except ValueError:
                reasons.append("tracked suite run record is not JSON")
        else:
            text = data.decode(errors="replace")
            if suite is not None and (f"RUN ID: {suite.get('run_id')}" not in text
                                      or f"GIT SHA: {sha}" not in text):
                reasons.append("the tracked log does not name this run and SHA; record and "
                               "log disagree")
            totals = _TOTAL.findall(text)
            if not totals:
                reasons.append("the tracked log has no TOTAL line; the run did not finish")
            elif int(totals[-1][1]) != 0:
                reasons.append(f"the tracked log says suites failing: {totals[-1][1]}")
    if suite is not None:
        if suite.get("git_sha") != sha:
            reasons.append("tracked suite run record ran on a different SHA than the record")
        if not suite.get("release_eligible") or suite.get("status") != "passed":
            reasons.append(f"tracked suite run record is {suite.get('status')} (scope "
                           f"{suite.get('scope')}, tree {suite.get('tree')}, failing "
                           f"{suite.get('suites_failing')}): not release-eligible")
        elif suite.get("scope") != "full" or suite.get("failing_suites") or int(
                suite.get("suites_failing") or 0):
            reasons.append("tracked suite run record is not a full run with zero failing")
    return reasons


def release_proof(repo: Path, cand: str, layout: dict = LAYOUT) -> tuple[dict | None, list[str]]:
    """The tracked release record at `cand` that proves `cand`'s deployable tree, or why not."""
    rel_dir = layout["prefix"] + layout["release"]
    names = [p for _m, p in _ls_tree(repo, cand, rel_dir)
             if re.fullmatch(r"RELEASE_[0-9a-f]+\.json", p.rsplit("/", 1)[-1])]
    digest = git_tree_digest(repo, cand, layout)
    if not names:
        return None, [f"no tracked release record (and so no suite run record) for "
                      f"{cand[:12]}: run REQUIRE_CLEAN=1 ./run_tests.sh on exactly the commit, "
                      f"then `ops/deploy_guard.py record` and commit {rel_dir}/"]
    blobs = _blobs(repo, cand, names)
    best: list[str] = [f"no tracked release record in {rel_dir}/ names the deployable tree "
                       f"digest of {cand[:12]} ({digest[:16]}...)"]
    for name in names:
        try:
            rec = json.loads(blobs.get(name) or b"")
        except ValueError:
            continue
        if rec.get("source_tree_sha256") != digest:
            continue

        def read(rel: str) -> bytes | None:
            return _blobs(repo, cand, [f"{rel_dir}/{rel}"]).get(f"{rel_dir}/{rel}")

        why = _record_problems(rec, read)
        sha = str(rec.get("sha") or "")
        if not why:
            code, _ = _git(repo, "merge-base", "--is-ancestor", sha, cand)
            if code != 0:
                why = [f"tracked release record names {sha[:12]}, which is not {cand[:12]} "
                       "or an ancestor of it"]
        if not why:
            suite = json.loads(read(rec["suite_record"]["path"]) or b"{}")
            return {"file": name, "sha": sha, "tree_sha256": digest, "suite": suite}, []
        best = why
    return None, best


def _commit_message(repo: Path, rev: str) -> str:
    code, out = _git(repo, "log", "-1", "--format=%B", rev)
    return out if code == 0 else ""


def _trailer(message: str, key: str) -> str:
    for line in message.splitlines():
        if line.startswith(key):
            return line[len(key):].strip()
    return ""


def deployed_history(repo: Path, rev: str, layout: dict = LAYOUT) -> list[str]:
    """SHAs recorded as having run in production, read from git at `rev` (tracked only)."""
    path = f"{layout['prefix']}{layout['release']}/{HISTORY_FILE}"
    data = _blobs(repo, rev, [path]).get(path)
    try:
        return [str(e["sha"]) for e in json.loads(data or b"{}").get("deployed", [])
                if e.get("sha")]
    except (ValueError, TypeError, KeyError):
        return []


def _rollback(repo: Path, cand: str, dep: str | None, target_arg: str, reason: str,
              layout: dict) -> list[str]:
    """Why a deliberate rollback candidate is not sanctioned; empty when it is."""
    reasons: list[str] = []
    if len(reason.strip()) < MIN_REASON:
        reasons.append("rollback needs the owner's stated reason (Rollback-Reason)")
    target = resolve(repo, target_arg)
    if target is None:
        return reasons + [f"rollback target {target_arg!r} is not a commit in this repository"]
    if dep is None:
        return reasons + ["deployed commit unknown: a rollback must name what it replaces"]
    history = set(deployed_history(repo, dep, layout)) | set(
        deployed_history(repo, cand + "^1", layout))
    if target not in history:
        reasons.append(f"rollback target {target[:12]} is not in the tracked deployed history "
                       f"({layout['release']}/{HISTORY_FILE})")
    if cand == target:
        return reasons  # a direct (non-fast-forward) rollback to the exact recorded commit
    _c, cand_tree = _git(repo, "rev-parse", f"{cand}^{{tree}}")
    _t, target_tree = _git(repo, "rev-parse", f"{target}^{{tree}}")
    if not cand_tree or cand_tree != target_tree:
        reasons.append(f"rollback commit {cand[:12]} does not carry exactly the tree of "
                       f"{target[:12]}")
    code, _ = _git(repo, "merge-base", "--is-ancestor", dep, cand)
    if code != 0:
        reasons.append(f"rollback commit {cand[:12]} is not on top of deployed {dep[:12]}")
    return reasons


def check(candidate: str, deployed: str | None, *, repo: Path = REPO,
          record_dir: Path = RECORD_DIR, log_base: Path | None = None,
          layout: dict = LAYOUT, rollback_to: str = "", rollback_reason: str = "") -> dict:
    reasons: list[str] = []
    cand = resolve(repo, candidate)
    if cand is None:
        reasons.append(f"candidate {candidate!r} is not a commit in this repository")

    # A3-06: a deliberate, owner-reasoned rollback has its own door (see the docstring).
    message = _commit_message(repo, cand) if cand else ""
    rollback_to = rollback_to or _trailer(message, ROLLBACK_TO)
    rollback_reason = rollback_reason or _trailer(message, ROLLBACK_REASON)
    if cand is not None and rollback_to:
        dep = resolve(repo, deployed or "")
        why = _rollback(repo, cand, dep, rollback_to, rollback_reason, layout)
        return {"verdict": "REFUSE" if why else "ALLOW", "mode": "rollback",
                "candidate": cand, "deployed": dep,
                "rollback": {"to": resolve(repo, rollback_to), "reason": rollback_reason},
                "suite_run": None, "reasons": why,
                "note": "verdict only; this script never deploys (F-461, A3-06)"}

    dep = resolve(repo, deployed or "")
    if not deployed:
        reasons.append("deployed commit unknown: descent cannot be established (read it from "
                       "production /api/verify and pass --deployed)")
    elif dep is None:
        reasons.append(f"deployed commit {deployed!r} is not in this repository; fetch it "
                       "before deciding -- descent cannot be established")
    elif cand is not None:
        code, _ = _git(repo, "merge-base", "--is-ancestor", dep, cand)
        if code == 1:
            reasons.append(f"candidate {cand[:12]} is not a descendant of deployed {dep[:12]}: "
                           "deploying it would roll production back")
        elif code != 0:
            reasons.append("git could not compute ancestry; refusing rather than guessing")

    # A3-05: only tracked evidence is believed -- the release record, run record and log as
    # committed at the candidate, bound to its deployable tree. `record_dir`/`log_base` (the
    # gitignored local run records) are read only by `record`, which makes the tracked copy.
    suite = None
    proof = None
    if cand is not None:
        proof, why = release_proof(repo, cand, layout)
        reasons.extend(why)
        if proof is not None:
            suite = proof["suite"]
    return {
        "verdict": "REFUSE" if reasons else "ALLOW", "mode": "forward",
        "release_record": None if proof is None else {
            k: proof[k] for k in ("file", "sha", "tree_sha256")},
        "candidate": cand, "deployed": dep,
        "suite_run": None if suite is None else {k: suite.get(k) for k in (
            "run_id", "status", "git_sha", "scope", "tree", "tests_passing",
            "suites_failing", "finished_utc", "log", "release_eligible")},
        "reasons": reasons,
        "note": "verdict only; this script never deploys (F-461)",
    }


def record_release(sha: str, *, repo: Path = REPO, record_dir: Path = RECORD_DIR,
                   log_base: Path | None = None, layout: dict = LAYOUT,
                   now: str = "") -> dict:
    """Write the tracked release record for `sha` into the working tree (never commits).

    Refuses unless the local run record for exactly `sha` is release-eligible and its log
    confirms it (the original F-461 checks). Copies the run record and log into
    `<release>/suite_runs/`, pins both by sha256, and binds them to `sha`'s deployable tree
    digest. The operator reviews and commits the result; `check` then reads it from git.
    """
    full = resolve(repo, sha)
    if full is None:
        return {"ok": False, "reasons": [f"{sha!r} is not a commit in this repository"]}
    rec = latest_suite(record_dir, sha=full, eligible_only=True)
    if rec is None:
        return {"ok": False, "reasons": [f"no release-eligible local suite run record for "
                                         f"{full[:12]}"]}
    why = _log_confirms(rec, log_base or (repo / layout["prefix"].rstrip("/")))
    if why:
        return {"ok": False, "reasons": [why]}
    raw_log = rec.get("log") or ""
    base = log_base or (repo / layout["prefix"].rstrip("/"))
    log_path = Path(raw_log) if Path(raw_log).is_absolute() else base / raw_log
    rel_dir = repo / (layout["prefix"] + layout["release"])
    (rel_dir / "suite_runs").mkdir(parents=True, exist_ok=True)
    rec_bytes = Path(rec["_path"]).read_bytes()
    log_bytes = log_path.read_bytes()
    rid = re.sub(r"[^A-Za-z0-9_.-]", "_", str(rec.get("run_id") or full[:12]))
    (rel_dir / "suite_runs" / f"{rid}.json").write_bytes(rec_bytes)
    (rel_dir / "suite_runs" / f"{rid}.log").write_bytes(log_bytes)
    record = {
        "kind": "brambleloop.release_record", "version": 1, "sha": full,
        "source_tree_sha256": git_tree_digest(repo, full, layout),
        "deployable": {"prefix_stripped": layout["prefix"], "dirs": list(layout["dirs"]),
                       "files": list(layout["files"]),
                       "excluded": ["__pycache__/", "*.pyc", "*.pyo", "symlinks"]},
        "suite_record": {"path": f"suite_runs/{rid}.json",
                         "sha256": hashlib.sha256(rec_bytes).hexdigest()},
        "suite_log": {"path": f"suite_runs/{rid}.log",
                      "sha256": hashlib.sha256(log_bytes).hexdigest()},
        "release_eligible": True, "recorded_at": now or rec.get("finished_utc"),
        "note": "commit this file and suite_runs/ on top of `sha`; the deploy guard and the "
                "runtime boot guard read it from git / the image, never from artifacts/",
    }
    out = rel_dir / f"RELEASE_{full}.json"
    out.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    return {"ok": True, "record": str(out), "sha": full,
            "tree_sha256": record["source_tree_sha256"]}


def rollback_commit(to: str, reason: str, *, deployed: str, repo: Path = REPO,
                    layout: dict = LAYOUT) -> dict:
    """Write (do not push) a commit on top of `deployed` carrying exactly `to`'s tree."""
    dep, target = resolve(repo, deployed or ""), resolve(repo, to)
    if dep is None or target is None:
        return {"ok": False, "reasons": ["deployed and target must both be commits here"]}
    msg = (f"Rollback production to {target[:12]}\n\n{reason.strip()}\n\n"
           f"{ROLLBACK_TO} {target}\n{ROLLBACK_REASON} {' '.join(reason.split())}\n")
    r = _git_raw(repo, "commit-tree", f"{target}^{{tree}}", "-p", dep, "-m", msg)
    sha = r.stdout.decode(errors="replace").strip()
    if r.returncode != 0 or not sha:
        return {"ok": False, "reasons": ["git commit-tree failed: "
                                         + r.stderr.decode(errors="replace").strip()[:300]]}
    verdict = check(sha, dep, repo=repo, layout=layout)
    return {"ok": verdict["verdict"] == "ALLOW", "commit": sha, "check": verdict}


def deployed_from(explicit: str | None = None, env: dict | None = None) -> tuple[str | None, str]:
    """The deployed commit the caller supplied: `--deployed`, else `BRAMBLELOOP_DEPLOYED_SHA`.

    This module never asks production itself (no network, by test). `ops/deployed_sha.py`
    reads production's `/api/status`; the hook and `ops/deploy.sh` run it and pass the answer
    in. Nothing supplied is unknown, and `check` refuses on unknown.
    """
    import os

    if explicit:
        return explicit, "argument"
    e = os.environ if env is None else env
    if e.get(DEPLOYED_ENV):
        return e[DEPLOYED_ENV], DEPLOYED_ENV
    return None, (f"deployed commit not supplied: pass --deployed or set {DEPLOYED_ENV} "
                  "(ops/deployed_sha.py reads it from production /api/status)")


def pre_push(lines, *, deployed: str | None = None, env: dict | None = None,
             repo: Path = REPO, record_dir: Path = RECORD_DIR, checker=None) -> dict:
    """Decide a `git push` from the lines git gives a pre-push hook.

    Each line is `<local ref> <local sha> <remote ref> <remote sha>`. Only updates to the
    production branch are deploys; each is run through `check` and any REFUSE refuses the
    push. Deleting the production branch is refused outright.
    """
    checker = checker or check
    decisions = []
    for raw in lines:
        parts = raw.split()
        if len(parts) != 4:
            continue
        local_ref, local_sha, remote_ref, _remote_sha = parts
        if remote_ref != PRODUCTION_REF:
            decisions.append({"remote_ref": remote_ref, "verdict": "NOT_A_DEPLOY"})
            continue
        if local_sha == ZERO:
            decisions.append({"remote_ref": remote_ref, "verdict": "REFUSE",
                              "reasons": ["deleting the production branch is not a deploy "
                                          "this guard can prove safe"]})
            continue
        dep, source = deployed_from(deployed, env)
        out = checker(local_sha, dep, repo=repo, record_dir=record_dir)
        out = {**out, "remote_ref": remote_ref, "local_ref": local_ref,
               "deployed_source": source}
        if dep is None:
            out["reasons"] = list(out.get("reasons") or []) + [source]
            out["verdict"] = "REFUSE"
        decisions.append(out)
    refused = [d for d in decisions if d["verdict"] == "REFUSE"]
    return {"verdict": "REFUSE" if refused else "ALLOW", "decisions": decisions,
            "production_ref": PRODUCTION_REF,
            "note": "verdict only; the push itself is git's (F-461)"}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("--candidate", default="HEAD")
    c.add_argument("--deployed", default="")
    c.add_argument("--records", default=str(RECORD_DIR))
    c.add_argument("--repo", default=str(REPO))
    c.add_argument("--rollback-to", default="")
    c.add_argument("--reason", default="")
    rr = sub.add_parser("record")
    rr.add_argument("--sha", default="HEAD")
    rr.add_argument("--records", default=str(RECORD_DIR))
    rr.add_argument("--repo", default=str(REPO))
    rb = sub.add_parser("rollback-commit")
    rb.add_argument("--to", required=True)
    rb.add_argument("--reason", required=True)
    rb.add_argument("--deployed", default="")
    rb.add_argument("--repo", default=str(REPO))
    pp = sub.add_parser("pre-push")
    pp.add_argument("remote", nargs="?", default="")
    pp.add_argument("url", nargs="?", default="")
    pp.add_argument("--deployed", default="")
    pp.add_argument("--records", default=str(RECORD_DIR))
    pp.add_argument("--repo", default=str(REPO))
    ls = sub.add_parser("latest-suite")
    ls.add_argument("--sha", default="")
    ls.add_argument("--eligible", action="store_true")
    ls.add_argument("--records", default=str(RECORD_DIR))
    a = ap.parse_args(argv)
    if a.cmd == "check":
        out = check(a.candidate, deployed_from(a.deployed or None)[0], repo=Path(a.repo),
                    record_dir=Path(a.records), rollback_to=a.rollback_to,
                    rollback_reason=a.reason)
        print(json.dumps(out, indent=2, sort_keys=True))
        return 0 if out["verdict"] == "ALLOW" else 1
    if a.cmd == "record":
        out = record_release(a.sha, repo=Path(a.repo), record_dir=Path(a.records))
        print(json.dumps(out, indent=2, sort_keys=True))
        return 0 if out["ok"] else 1
    if a.cmd == "rollback-commit":
        out = rollback_commit(a.to, a.reason, deployed=deployed_from(a.deployed or None)[0]
                              or "", repo=Path(a.repo))
        print(json.dumps(out, indent=2, sort_keys=True), file=sys.stderr)
        if out.get("ok"):
            print(out["commit"])
        return 0 if out.get("ok") else 1
    if a.cmd == "pre-push":
        out = pre_push(sys.stdin.read().splitlines(), deployed=a.deployed or None,
                       repo=Path(a.repo), record_dir=Path(a.records))
        print(json.dumps(out, indent=2, sort_keys=True), file=sys.stderr)
        if out["verdict"] != "ALLOW":
            print("deploy_guard: REFUSED push to the production branch (F-461); see reasons "
                  "above. Push to a work branch instead.", file=sys.stderr)
        return 0 if out["verdict"] == "ALLOW" else 1
    sha = resolve(REPO, a.sha) if a.sha else None
    rec = latest_suite(Path(a.records), sha=sha or (a.sha or None), eligible_only=a.eligible)
    print(json.dumps(rec, indent=2, sort_keys=True) if rec else "no matching suite run record")
    return 0 if rec else 1


if __name__ == "__main__":
    raise SystemExit(main())
