#!/usr/bin/env python3
"""Durable, authenticated per-suite checkpoints for run_tests.sh: resume and shard.

W4-B1 (2026-10-27) introduced this tool; W4-RESUMEFIX (2026-10-27) rebuilt it after the
independent review `research/final_build/w4/RESUME_REVIEW.md` found it NOT SAFE (C1-C3, H4-H5,
M6-L8). The fix for each finding is named where it is implemented (F1..F8).

WHY. Container restarts killed two multi-hour full suites, and a killed run had to start again
from nothing. With CHECKPOINT=1 each suite's result is persisted the moment its verdict is final,
so RESUME=<run id> can continue an INTERRUPTED run without re-running what already finished.

A CHECKPOINTED, RESUMED OR SHARDED RUN NEVER CERTIFIES A RELEASE (F1; owner decision
D-W4-OWNER-RESUME-POLICY, DECISION_LOG.md). run_tests.sh writes `release_eligible: false` from
the record's first write, and ops/deploy_guard.py and brambleloop.ops.release_record refuse any
record with checkpoint or resume provenance. There is no bypass: changing that needs new code,
a fresh independent review and a new owner decision. Resume saves operator time (a red result
early, a diagnosis); certification still takes one uninterrupted full run.

WHAT IS PERSISTED. `<record dir>/<run id>/` holds

  * `manifest.json` -- run id, the run KEY, the suite set, the declared final-segment set and an
    append-only HASH CHAIN of events (segment begin, suite result, segment end), every entry
    HMAC-SHA256'd with a per-run secret, and the header MACed too (F3);
  * `<suite>.s<N>.json` / `<suite>.s<N>.out` -- the attempt of that suite in segment N. Attempt
    files are created exclusively and never overwritten: every attempt is kept (F2). The JSON
    carries run id, segment, host, the sha256 and OK/FAIL/SKIP counts of its `.out`, the leak
    census and the exit code, and its own MAC (F3). Both are written temp + fsync + link, and the
    directory is fsynced (F6).
  * `<suite>.s<N>.running` -- informational marker while the suite runs.

THE RUN SECRET (F3). 32 random bytes in `$SUITE_RUNKEY_DIR/<run id>` (default
`~/.brambleloop/runkeys`; on the build host set SUITE_RUNKEY_DIR=/home/user/bl-runs/runkeys),
mode 600 in a mode-700 directory, refused if that directory is inside the repository, the working
tree or the record directory. Without it nothing can be resumed. LIMIT, stated honestly: the MAC
defeats copied, edited, torn and forged checkpoints by anything that does not read the key file;
it does not defeat a same-uid process that reads the key. That is one reason F1 holds regardless.

THE KEY (F4). A resumed run is the same run only if everything that could change a result is
the same: git SHA, porcelain status + `git diff HEAD`, the CONTENT of every untracked file and of
every git-ignored file under the tree (venvs, `__pycache__`, bytecode and the `artifacts/` output
store excluded -- see IGNORED_EXCLUDED_DIRS), both lock files, the interpreter (real path, version,
prefix), the content of every file in the interpreter's site-packages directories (the installed
distribution set, including unpackaged modules), the whole environment deny-by-default (every
variable except the run-local ones in RUN_LOCAL_ENV; values are HMACed, never stored), host name,
machine id and kernel, JOBS, scope, shard and the suite set. Any mismatch REFUSES (exit 4) and
names the fields.

WHAT COUNTS. Resume is allowed only after an INTERRUPTED segment (F2): the last segment has no
`end` chain entry, the run record says `running` or `interrupted`, and the log carries no `EXIT n`
sentinel other than `EXIT 130`. A suite with a terminal `failed` result anywhere in the chain is
never re-run in the same run, and the run stays failed (F2). A suite counts as passed only from a
`passed` chain entry whose attempt files verify: MAC, run id, key digest, `.out` sha256 and
counts (F3, F6). A passed entry whose files are missing or altered is treated as no result and
re-run (F6). The verdict is written only after the per-suite TMPDIR leak census and the
TMP_LEAK_STRICT decision; the leak counts are stored and restored (F5).

GROUPING AND TIME (F7). Timing- and clock-sensitive suites -- the declared list in
`scripts/suite_final_segment.txt` plus any suite matching FINAL_SET_PATTERNS (the review's
`timeout=`, `sleep`, `date.today()`/`datetime.now()` criteria) -- always re-run together in the
final segment, and a resume that crosses the UTC date of the run's first segment is refused
(and a resumed run whose final segment ends on another UTC date fails).

CONSISTENCY (F8). `finalize` derives `suite_results` from the same per-suite verdicts the report
used for `failing_suites` and fails the run if the checkpoint disagrees with them. run_tests.sh
holds an exclusive flock per run id for every checkpointed segment, whatever ALLOW_PARALLEL says.

SHARD=i/n selects the suites whose sha256(name) % n == i.

Subcommands (all used by run_tests.sh):
  shard SPEC SUITE...
  plan     --dir D --record-dir R --run-id I --jobs J --scope S [--shard X] [--resume] -- SUITE...
  begin    --dir D --record-dir R --run-id I --jobs J --scope S [--shard X] [--resume]
           [--to-run ...] -- SUITE...
  start    --dir D SUITE
  finish   --dir D SUITE --code C --out FILE --leak-entries N --leak-bytes B
  restore  --dir D --outdir O -- SUITE...
  finalize --dir D --record-dir R --run-id I --verdicts F --fragment OUT -- SUITE...
  seal     --dir D --run-id I --status S --record FILE
"""
from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import hmac
import json
import os
import platform
import re
import secrets
import stat
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

FORMAT = 2
LOCKS = ("requirements.lock", "requirements-test.lock")
REFUSED = 4
#: F4: the environment is bound deny-by-default. Only these run-local variables are left out:
#: the runner's own mode knobs and plumbing (JOBS, the suite set and the interpreter are bound
#: separately), and shell bookkeeping that differs per invocation. Everything else (PYTHONPATH,
#: PATH, HOME, TZ, OPENAI_*, RAILWAY_*, DATABASE_URL, CERT_TRACE, ...) is bound.
RUN_LOCAL_ENV = frozenset({
    "RESUME", "CHECKPOINT", "CHECKPOINT_TOOL", "SHARD", "SUITES", "JOBS", "PY",
    "SUITE_RECORD_DIR", "SUITE_RUNKEY_DIR", "SUITE_REGISTRY", "SUITE_REGISTRY_CLI",
    "ATTACH", "ATTACH_TIMEOUT", "ALLOW_PARALLEL", "THEN_FULL",
    "BRAMBLELOOP_RUN_TMP", "_BRAMBLELOOP_SUITE_JOB", "TMPDIR",
    "PWD", "OLDPWD", "SHLVL", "_",
})
#: F4: git-ignored paths under the tree that are NOT inputs. `artifacts/` is the output store
#: (run records, checkpoints, the content-addressed blob store whose names are their hashes);
#: venvs are bound through their site-packages instead; bytecode is derived from bound source.
IGNORED_EXCLUDED_DIRS = ("artifacts",)
FINAL_SET_FILE = "scripts/suite_final_segment.txt"
#: F7: the review's criteria for timing- and clock-sensitive suites (RESUME_REVIEW.md M7).
FINAL_SET_PATTERNS = (r"timeout\s*=", r"sleep",
                      r"date\.today\(|datetime\.now\(|datetime\.utcnow\(")
_OK = re.compile(r"^OK", re.M)
_FAIL = re.compile(r"^FAIL([ \t\r\f\v:]|$)", re.M)
_SKIP = re.compile(r"^SKIP", re.M)
_EXIT = re.compile(r"^EXIT (-?\d+)\s*$", re.M)


class Refused(Exception):
    """A checkpoint that cannot be trusted or a resume the policy forbids."""


def _now() -> datetime:                       # one clock, so tests can pin it
    return datetime.now(timezone.utc)


def utc() -> str:
    return _now().strftime("%Y-%m-%dT%H:%M:%SZ")


def _safe(suite: str) -> str:
    return suite.replace("/", "_")


def canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---- durable IO (F6) ---------------------------------------------------------------------------

def _fsync_dir(d: Path) -> None:
    fd = os.open(str(d), os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _tmp_write(path: Path, data: bytes) -> Path:
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{secrets.token_hex(4)}.tmp")
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    return tmp


def atomic_replace(path: Path, data: bytes) -> None:
    """temp + fsync + rename + fsync(dir): a reader sees the old or the new file, whole."""
    tmp = _tmp_write(path, data)
    os.replace(tmp, path)
    _fsync_dir(path.parent)


def create_exclusive(path: Path, data: bytes) -> None:
    """temp + fsync + link: the file appears whole or not at all, and is never overwritten."""
    tmp = _tmp_write(path, data)
    try:
        os.link(tmp, path)                   # fails if `path` exists: attempts are append-only
    finally:
        os.unlink(tmp)
    _fsync_dir(path.parent)


def _read_json(path: Path) -> dict | None:
    try:
        v = json.loads(path.read_bytes())
    except (OSError, ValueError):
        return None
    return v if isinstance(v, dict) else None


@contextlib.contextmanager
def _locked(d: Path):
    """Serialise chain appends from concurrently finishing suites."""
    with open(d / ".chain.lock", "a") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)


# ---- the per-run secret (F3) -------------------------------------------------------------------

def runkey_dir() -> Path:
    raw = os.environ.get("SUITE_RUNKEY_DIR") or "~/.brambleloop/runkeys"
    return Path(os.path.realpath(os.path.expanduser(raw)))


def _inside(p: Path, root: Path) -> bool:
    p, root = Path(os.path.realpath(p)), Path(os.path.realpath(root))
    return p == root or root in p.parents


def _check_key_location(kd: Path, record_dir: Path) -> None:
    top = _git("rev-parse", "--show-toplevel").strip()
    for root, what in ((Path(top) if top else None, "the repository"),
                       (Path(os.getcwd()), "the working tree"),
                       (record_dir, "the record directory")):
        if root is not None and _inside(kd, root):
            raise Refused(f"SUITE_RUNKEY_DIR {kd} is inside {what}; the run secret must live "
                          "outside artifacts/ and the repository")


def create_runkey(run_id: str, record_dir: Path) -> bytes:
    kd = runkey_dir()
    _check_key_location(kd, record_dir)
    kd.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(kd, 0o700)
    key = secrets.token_bytes(32)
    try:
        fd = os.open(str(kd / run_id), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        raise Refused(f"a run secret for {run_id} already exists; refusing to replace it") from None
    with os.fdopen(fd, "w") as f:
        f.write(key.hex() + "\n")
        f.flush()
        os.fsync(f.fileno())
    _fsync_dir(kd)
    return key


def load_runkey(run_id: str, record_dir: Path) -> bytes:
    kd = runkey_dir()
    _check_key_location(kd, record_dir)
    p = kd / run_id
    try:
        st = os.stat(p)
        raw = p.read_text().strip()
    except OSError:
        raise Refused(f"no run secret for {run_id} in {kd}: this checkpoint cannot be "
                      "authenticated (copied from another run or host?)") from None
    if stat.S_IMODE(st.st_mode) & 0o077 or st.st_uid != os.getuid():
        raise Refused(f"the run secret {p} is not mode 600 and owned by this user")
    try:
        key = bytes.fromhex(raw)
    except ValueError:
        raise Refused(f"the run secret {p} is unreadable") from None
    if len(key) != 32:
        raise Refused(f"the run secret {p} is unreadable")
    return key


def mac(key: bytes, obj) -> str:
    return hmac.new(key, canonical(obj), hashlib.sha256).hexdigest()


# ---- the run key: everything that can change a result (F4) ------------------------------------

def _git(*args: str) -> str:
    try:
        return subprocess.run(["git", *args], capture_output=True, text=True,
                              check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return ""


def _git_z(*args: str) -> list[str]:
    try:
        out = subprocess.run(["git", *args], capture_output=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return []
    return [x.decode(errors="surrogateescape") for x in out.split(b"\0") if x]


def _file_hash(name: str) -> str:
    p = Path(name)
    return sha256(p.read_bytes()) if p.is_file() else "absent"


def _entry_digest(p: Path) -> str:
    try:
        if p.is_symlink():
            return "link:" + os.readlink(p)
        return sha256(p.read_bytes())
    except OSError as exc:
        return f"unreadable:{exc.errno}"


def _is_venv(d: Path) -> bool:
    return (d / "pyvenv.cfg").is_file()


def _skip_dir(rel: str, d: Path, record_dir: Path) -> bool:
    return (d.name in ("__pycache__", ".git") or _is_venv(d) or _inside(d, record_dir)
            or rel.split("/", 1)[0] in IGNORED_EXCLUDED_DIRS)


def _skip_file(rel: str) -> bool:
    return rel.endswith((".pyc", ".pyo")) or "/__pycache__/" in f"/{rel}"


def tree_inputs(record_dir: Path) -> dict:
    """Content digests of every untracked and every git-ignored input under the tree."""
    out = {}
    for label, args in (("untracked", ("ls-files", "-z", "--others", "--exclude-standard")),
                        ("ignored", ("ls-files", "-z", "--others", "--ignored",
                                     "--exclude-standard", "--directory"))):
        h, n = hashlib.sha256(), 0
        for rel in sorted(_git_z(*args)):
            p = Path(rel.rstrip("/"))
            if p.is_dir() and not p.is_symlink():
                if _skip_dir(rel.rstrip("/"), p, record_dir):
                    continue
                for root, dirs, files in os.walk(p):
                    r = Path(root)
                    dirs[:] = sorted(x for x in dirs
                                     if not _skip_dir(f"{root}/{x}", r / x, record_dir))
                    for fn in sorted(files):
                        fr = f"{root}/{fn}"
                        if not _skip_file(fr):
                            h.update(fr.encode(errors="surrogateescape") + b"\0"
                                     + _entry_digest(r / fn).encode() + b"\n")
                            n += 1
                continue
            if _skip_file(rel) or _inside(p, record_dir) or (
                    rel.split("/", 1)[0] in IGNORED_EXCLUDED_DIRS):
                continue
            h.update(rel.encode(errors="surrogateescape") + b"\0"
                     + _entry_digest(p).encode() + b"\n")
            n += 1
        out[label] = {"files": n, "sha256": h.hexdigest()}
    return out


def installed_set() -> dict:
    """The content of every file in this interpreter's site-packages directories.

    Covers distributions (their RECORDed files and dist-info) and also bare modules no RECORD
    lists, because a changed module changes a result whether or not pip knows about it."""
    roots = sorted({os.path.realpath(p) for p in sys.path
                    if p and os.path.isdir(p) and ("site-packages" in p or "dist-packages" in p)})
    h, n, dists = hashlib.sha256(), 0, set()
    for top in roots:
        for root, dirs, files in os.walk(top):
            dirs[:] = sorted(x for x in dirs if x != "__pycache__")
            if root == top:
                dists.update(x for x in dirs if x.endswith((".dist-info", ".egg-info")))
            for fn in sorted(files):
                if fn.endswith((".pyc", ".pyo")):
                    continue
                p = Path(root) / fn
                h.update(str(p).encode(errors="surrogateescape") + b"\0"
                         + _entry_digest(p).encode() + b"\n")
                n += 1
    return {"roots": roots, "files": n, "distributions": len(dists), "sha256": h.hexdigest()}


def host_identity() -> dict:
    mid = "absent"
    for f in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
        try:
            mid = sha256(Path(f).read_bytes().strip())
            break
        except OSError:
            continue
    u = os.uname()
    return {"hostname": platform.node(), "machine_id_sha256": mid,
            "kernel": f"{u.sysname} {u.release} {u.version} {u.machine}"}


def env_fingerprint(runkey: bytes, env=None) -> dict:
    """Deny-by-default: every variable outside RUN_LOCAL_ENV, value HMACed (never stored)."""
    env = os.environ if env is None else env
    return {k: hmac.new(runkey, f"{k}={env[k]}".encode(errors="surrogateescape"),
                        hashlib.sha256).hexdigest()
            for k in sorted(env) if k not in RUN_LOCAL_ENV}


def run_key(*, runkey: bytes, jobs: str, scope: str, shard: str, suites: list[str],
            record_dir: Path) -> dict:
    sha = _git("rev-parse", "HEAD").strip() or "UNKNOWN"
    porcelain = _git("status", "--porcelain")
    dirty = sha256((porcelain + _git("diff", "HEAD", "--binary")).encode())
    return {
        "git_sha": sha,
        "tree_clean": sha != "UNKNOWN" and porcelain.strip() == "",
        "dirty_content_sha256": None if porcelain.strip() == "" else dirty,
        "tree_inputs": tree_inputs(record_dir),
        "locks": {name: _file_hash(name) for name in LOCKS},
        "python": {"executable": os.path.realpath(sys.executable),
                   "version": sys.version.split()[0], "prefix": os.path.realpath(sys.prefix)},
        "installed": installed_set(),
        "host": host_identity(),
        "jobs": str(jobs),
        "scope": scope,
        "shard": shard or None,
        "suites_sha256": sha256("\n".join(sorted(suites)).encode()),
        "env": env_fingerprint(runkey),
    }


def key_mismatch(a: dict, b: dict) -> list[str]:
    out = []
    for k in sorted(set(a) | set(b)):
        va, vb = a.get(k), b.get(k)
        if va == vb:
            continue
        if isinstance(va, dict) and isinstance(vb, dict) and k in (
                "locks", "env", "host", "tree_inputs", "python", "installed"):
            for sub in sorted(set(va) | set(vb)):
                if va.get(sub) != vb.get(sub):
                    out.append(f"{k}.{sub}")
        else:
            out.append(k)
    return out


def key_digest(key: dict) -> str:
    return sha256(canonical(key))


# ---- F7: the final-segment (rerun-together) set -----------------------------------------------

def declared_final_set(path: str = FINAL_SET_FILE) -> set[str]:
    try:
        text = Path(path).read_text()
    except OSError:
        return set()
    return {ln.strip() for ln in text.splitlines() if ln.strip() and not ln.startswith("#")}


def detect_timing_sensitive(suites) -> set[str]:
    pats = [re.compile(p) for p in FINAL_SET_PATTERNS]
    out = set()
    for s in suites:
        try:
            text = Path(s).read_text(errors="replace")
        except OSError:
            continue
        if any(p.search(text) for p in pats):
            out.add(s)
    return out


def final_set(suites) -> list[str]:
    suites = list(suites)
    return sorted((declared_final_set() & set(suites)) | detect_timing_sensitive(suites))


# ---- the manifest and its chain (F3) ----------------------------------------------------------

def _header(man: dict) -> dict:
    return {k: man[k] for k in ("format", "run_id", "created_utc", "key", "suites", "final_set")}


def _genesis(run_id: str) -> str:
    return sha256(f"genesis:{run_id}".encode())


def load_manifest(d: Path, run_id: str, runkey: bytes) -> dict:
    """The manifest, verified end to end, or Refused."""
    man = _read_json(d / "manifest.json")
    if man is None:
        raise Refused(f"no readable checkpoint manifest at {d}/manifest.json")
    if man.get("format") != FORMAT:
        raise Refused(f"checkpoint manifest format {man.get('format')!r} is not {FORMAT}")
    if man.get("run_id") != run_id:
        raise Refused(f"checkpoint manifest names run {man.get('run_id')!r}, not {run_id!r}: "
                      "a checkpoint is never adopted by another run id")
    try:
        if not hmac.compare_digest(str(man.get("header_mac")), mac(runkey, _header(man))):
            raise Refused("checkpoint manifest header MAC does not verify")
    except KeyError:
        raise Refused("checkpoint manifest header is incomplete") from None
    prev = _genesis(run_id)
    chain = man.get("chain")
    if not isinstance(chain, list) or not chain:
        raise Refused("checkpoint chain is empty")
    for i, e in enumerate(chain):
        if not isinstance(e, dict):
            raise Refused(f"checkpoint chain entry {i} is not an object")
        body = {k: v for k, v in e.items() if k != "mac"}
        if e.get("seq") != i or e.get("prev") != prev:
            raise Refused(f"checkpoint chain broken at entry {i}")
        if not hmac.compare_digest(str(e.get("mac")), mac(runkey, body)):
            raise Refused(f"checkpoint chain entry {i} MAC does not verify")
        prev = e["mac"]
    if chain[0].get("kind") != "begin" or chain[0].get("segment") != 1:
        raise Refused("checkpoint chain does not open with segment 1")
    return man


def _append(man: dict, runkey: bytes, entry: dict) -> dict:
    chain = man["chain"]
    entry = {**entry, "seq": len(chain),
             "prev": chain[-1]["mac"] if chain else _genesis(man["run_id"])}
    entry["mac"] = mac(runkey, entry)
    chain.append(entry)
    return entry


def segments(man: dict) -> list[dict]:
    segs: dict[int, dict] = {}
    for e in man["chain"]:
        n = e.get("segment")
        if e["kind"] == "begin":
            segs[n] = {"n": n, "started_utc": e["at_utc"], "pid": e.get("pid"),
                       "to_run": e.get("to_run_count"), "finished_utc": None,
                       "last_result_utc": None, "ended": False}
        elif n in segs and e["kind"] == "result":
            segs[n]["last_result_utc"] = e["at_utc"]
        elif n in segs and e["kind"] == "end":
            segs[n].update(finished_utc=e["at_utc"], ended=True, status=e.get("status"))
    return [segs[k] for k in sorted(segs)]


def current_segment(man: dict) -> int:
    return max(e["segment"] for e in man["chain"] if e["kind"] == "begin")


def _counts(text: str) -> dict:
    return {"ok": len(_OK.findall(text)), "fail": len(_FAIL.findall(text)),
            "skip": len(_SKIP.findall(text))}


def _attempt_paths(d: Path, suite: str, seg: int) -> tuple[Path, Path]:
    base = f"{_safe(suite)}.s{seg}"
    return d / f"{base}.json", d / f"{base}.out"


def verify_attempt(d: Path, man: dict, runkey: bytes, entry: dict) -> tuple[dict | None, str]:
    """The attempt a chain entry names, if every byte of it verifies (F3, F6)."""
    jp, op = _attempt_paths(d, entry["suite"], entry["segment"])
    try:
        raw = jp.read_bytes()
        out = op.read_bytes()
    except OSError:
        return None, "attempt file missing"
    if sha256(raw) != entry.get("result_sha256"):
        return None, "attempt JSON does not match its chain entry"
    try:
        res = json.loads(raw)
    except ValueError:
        return None, "attempt JSON unreadable"
    body = {k: v for k, v in res.items() if k != "mac"}
    if not hmac.compare_digest(str(res.get("mac")), mac(runkey, body)):
        return None, "attempt MAC does not verify"
    if (res.get("run_id") != man["run_id"] or res.get("segment") != entry["segment"]
            or res.get("suite") != entry["suite"] or res.get("status") != entry.get("status")
            or res.get("key_sha256") != key_digest(man["key"])):
        return None, "attempt does not belong to this run, segment and key"
    if sha256(out) != res.get("out_sha256") or _counts(out.decode(errors="replace")) != res.get(
            "counts"):
        return None, "attempt output does not match its stored sha256 and counts"
    return res, ""


def classify(d: Path, man: dict, runkey: bytes, suite: str) -> tuple[str, dict | None, str]:
    """('failed' | 'passed' | 'none', the counted chain entry, why).

    F2: any terminal failure in the chain is final for this run, whatever the files say now.
    F3/F6: a pass counts only if its attempt verifies; otherwise it is no result."""
    entries = [e for e in man["chain"] if e["kind"] == "result" and e.get("suite") == suite]
    failed = [e for e in entries if e.get("status") != "passed"]
    if failed:
        return "failed", failed[0], "terminal failure recorded in the chain"
    if not entries:
        return "none", None, "no result"
    last = entries[-1]
    res, why = verify_attempt(d, man, runkey, last)
    return ("passed", last, "") if res is not None else ("none", last, why)


# ---- F2: was the last segment interrupted? -----------------------------------------------------

def _prior_segment_interrupted(man: dict, record_dir: Path, run_id: str) -> str:
    """Empty when RESUME is allowed; otherwise why not."""
    segs = segments(man)
    if segs[-1]["ended"]:
        return (f"segment {segs[-1]['n']} of run {run_id} completed "
                f"({segs[-1].get('status')}); RESUME continues only an interrupted run. "
                "Start a new run.")
    rec = _read_json(record_dir / f"{run_id}.json")
    if rec is None:
        return f"run record {record_dir}/{run_id}.json is missing or unreadable"
    if rec.get("status") not in ("running", "interrupted"):
        return (f"run {run_id} ended {rec.get('status')!r}, not interrupted; RESUME continues "
                "only an interrupted run")
    try:
        log = (record_dir / f"{run_id}.log").read_text(errors="replace")
    except OSError:
        log = ""
    done = [c for c in _EXIT.findall(log) if c != "130"]
    if done:
        return f"run {run_id}'s log carries a terminal sentinel EXIT {done[-1]}; it completed"
    return ""


def _date_of(ts: str) -> str:
    return (ts or "")[:10]


# ---- subcommands ------------------------------------------------------------------------------

def parse_shard(spec: str) -> tuple[int, int]:
    try:
        i, n = (int(x) for x in spec.split("/"))
    except ValueError:
        raise SystemExit(f"SHARD must be i/n, got {spec!r}") from None
    if n < 1 or not 0 <= i < n:
        raise SystemExit(f"SHARD {spec!r}: need 0 <= i < n")
    return i, n


def shard_of(suite: str, n: int) -> int:
    return int(hashlib.sha256(Path(suite).name.encode()).hexdigest(), 16) % n


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


def resume_state(a) -> tuple[Path, dict, bytes]:
    d, rd = Path(a.dir), Path(a.record_dir)
    runkey = load_runkey(a.run_id, rd)
    man = load_manifest(d, a.run_id, runkey)
    why = _prior_segment_interrupted(man, rd, a.run_id)
    if why:
        raise Refused(why)
    first = segments(man)[0]["started_utc"]
    now = utc()
    if _date_of(first) != _date_of(now):
        raise Refused(f"RESUME would cross the UTC date: run {a.run_id} began {first}, it is now "
                      f"{now}; clock-reading suites would see another day (F7). Start a new run.")
    key = run_key(runkey=runkey, jobs=a.jobs, scope=a.scope, shard=a.shard, suites=a.suites,
                  record_dir=rd)
    bad = key_mismatch(man["key"], key)
    if bad:
        raise Refused("RESUME key mismatch on " + ", ".join(bad) + "; nothing was run. A "
                      "resumed run must match the original exactly (SHA, tree, untracked and "
                      "ignored inputs, locks, Python and installed packages, environment, host, "
                      "JOBS, suite set).")
    return d, man, runkey


def cmd_plan(a) -> int:
    d = Path(a.dir)
    if not a.resume:
        if (d / "manifest.json").exists():
            print(f"REFUSED: {d} already holds a run; use RESUME=<run id>", file=sys.stderr)
            return REFUSED
        try:
            _check_key_location(runkey_dir(), Path(a.record_dir))
        except Refused as exc:
            print(f"REFUSED: {exc}; nothing was run", file=sys.stderr)
            return REFUSED
        print("\n".join(a.suites))
        return 0
    try:
        d, man, runkey = resume_state(a)
    except Refused as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return REFUSED
    fset = set(man["final_set"])
    todo, kept_failed, rerun_final = [], [], []
    for s in a.suites:
        state, _e, _why = classify(d, man, runkey, s)
        if state == "failed":
            kept_failed.append(s)              # F2: never re-run inside the same run
        elif state == "none":
            todo.append(s)
        elif s in fset:
            todo.append(s)                     # F7: re-run together in the final segment
            rerun_final.append(s)
    if kept_failed:
        print(f"RESUME: {len(kept_failed)} suite(s) already failed in this run and are NOT re-run;"
              " the run cannot pass: " + " ".join(kept_failed), file=sys.stderr)
    if rerun_final:
        print(f"RESUME: {len(rerun_final)} timing/clock-sensitive suite(s) re-run in the final "
              "segment although they passed earlier (F7)", file=sys.stderr)
    print("\n".join(todo))
    return 0


def _begin_entry(n: int, to_run: list[str], at: str) -> dict:
    return {"kind": "begin", "segment": n, "at_utc": at, "pid": os.getppid(),
            "to_run_count": len(to_run), "to_run_sha256": sha256("\n".join(sorted(to_run)).encode())}


def cmd_begin(a) -> int:
    d, rd = Path(a.dir), Path(a.record_dir)
    try:
        if a.resume:
            runkey = load_runkey(a.run_id, rd)
            with _locked(d):
                man = load_manifest(d, a.run_id, runkey)
                _append(man, runkey, _begin_entry(current_segment(man) + 1, a.to_run or [], utc()))
                atomic_replace(d / "manifest.json", canonical(man))
            return 0
        runkey = create_runkey(a.run_id, rd)
        d.mkdir(parents=True, exist_ok=False)
        key = run_key(runkey=runkey, jobs=a.jobs, scope=a.scope, shard=a.shard,
                      suites=a.suites, record_dir=rd)
        man = {"format": FORMAT, "run_id": a.run_id, "created_utc": utc(), "key": key,
               "suites": sorted(a.suites), "final_set": final_set(a.suites), "chain": []}
        man["header_mac"] = mac(runkey, _header(man))
        _append(man, runkey, _begin_entry(1, a.to_run or [], man["created_utc"]))
        with _locked(d):
            atomic_replace(d / "manifest.json", canonical(man))
        return 0
    except (Refused, FileExistsError) as exc:
        print(f"REFUSED: checkpoint begin: {exc}", file=sys.stderr)
        return REFUSED


def _seg_from_manifest(d: Path) -> int:
    man = _read_json(d / "manifest.json") or {}
    begins = [e.get("segment") for e in man.get("chain") or [] if e.get("kind") == "begin"]
    return max(begins) if begins else 0


def cmd_start(a) -> int:
    d = Path(a.dir)
    try:
        (d / f"{_safe(a.suite)}.s{_seg_from_manifest(d)}.running").write_text(utc() + "\n")
    except OSError:
        return 1
    return 0


def cmd_finish(a) -> int:
    """Persist the suite's FINAL verdict: called after the leak census (F5)."""
    d = Path(a.dir)
    run_id = d.name
    try:
        runkey = load_runkey(run_id, d.parent)
        out = Path(a.out)
        data = out.read_bytes() if out.is_file() else b""
        counts = _counts(data.decode(errors="replace"))
        code = int(a.code)
        leak_n, leak_b = int(a.leak_entries), int(a.leak_bytes)
        strict = os.environ.get("TMP_LEAK_STRICT", "0") == "1"
        why = []
        if code != 0:
            why.append(f"exit {code}")
        if counts["ok"] == 0:
            why.append("reported no passes")
        if strict and leak_n > 0:
            why.append(f"TMP_LEAK_STRICT=1 and {leak_n} temp entries leaked")
        status = "failed" if why else "passed"
        with _locked(d):
            man = load_manifest(d, run_id, runkey)
            seg = current_segment(man)
            jp, op = _attempt_paths(d, a.suite, seg)
            started = None
            with contextlib.suppress(OSError):
                started = (d / f"{_safe(a.suite)}.s{seg}.running").read_text().strip()
            res = {"suite": a.suite, "run_id": run_id, "segment": seg, "attempt": seg,
                   "host": host_identity(), "key_sha256": key_digest(man["key"]),
                   "status": status, "why": why, "exit_code": code, "ok_count": counts["ok"],
                   "counts": counts, "leak_entries": leak_n, "leak_bytes": leak_b,
                   "tmp_leak_strict": strict, "started_utc": started, "finished_utc": utc(),
                   "out_sha256": sha256(data), "out_bytes": len(data)}
            res["mac"] = mac(runkey, res)
            create_exclusive(op, data)
            raw = json.dumps(res, indent=2, sort_keys=True).encode() + b"\n"
            create_exclusive(jp, raw)
            _append(man, runkey, {"kind": "result", "segment": seg, "suite": a.suite,
                                  "status": status, "exit_code": code,
                                  "leak_entries": leak_n, "leak_bytes": leak_b,
                                  "result_sha256": sha256(raw), "at_utc": res["finished_utc"]})
            atomic_replace(d / "manifest.json", canonical(man))
        with contextlib.suppress(OSError):
            (d / f"{_safe(a.suite)}.s{seg}.running").unlink()
        return 0
    except (Refused, OSError, ValueError) as exc:
        print(f"CHECKPOINT finish {a.suite}: {exc}", file=sys.stderr)
        return 1


def cmd_restore(a) -> int:
    """Put earlier segments' verified results where the report reads them, leak counts included
    (F5). A failure recorded in the chain is restored as a failure even if its files are gone."""
    d, o = Path(a.dir), Path(a.outdir)
    run_id = d.name
    try:
        runkey = load_runkey(run_id, d.parent)
        man = load_manifest(d, run_id, runkey)
    except Refused as exc:
        print(f"CHECKPOINT restore: {exc}", file=sys.stderr)
        return 1
    for s in a.suites:
        safe = _safe(s)
        if (o / f"{safe}.code").exists():
            continue                          # ran in this segment
        state, e, _why = classify(d, man, runkey, s)
        if state == "none" or e is None:
            continue                          # the report says "never ran"
        res, bad = verify_attempt(d, man, runkey, e)
        if res is not None:
            out = _attempt_paths(d, s, e["segment"])[1].read_bytes()
            code = res["exit_code"]
        else:                                 # only reachable for a failure (classify)
            out = (f"CHECKPOINT: the failed attempt of segment {e['segment']} cannot be shown "
                   f"({bad}); the chain records it as failed (exit {e.get('exit_code')})\n"
                   ).encode()
            code = e.get("exit_code") or 1
        (o / f"{safe}.out").write_bytes(out)
        (o / f"{safe}.leak").write_text(f"{e.get('leak_entries', 0)} {e.get('leak_bytes', 0)}\n")
        (o / f"{safe}.code").write_text(f"{code}\n")
    return 0


def cmd_finalize(a) -> int:
    """Merge the checkpoint into a record fragment; exit 1 (the run fails) on any problem."""
    d, rd = Path(a.dir), Path(a.record_dir)
    problems: list[str] = []
    try:
        runkey = load_runkey(a.run_id, rd)
        man = load_manifest(d, a.run_id, runkey)
    except Refused as exc:
        frag = {"checkpoint": {"dir": str(d), "run_id": a.run_id,
                               "problems": [f"checkpoint integrity: {exc}"]},
                "suite_results": []}
        atomic_replace(Path(a.fragment), canonical(frag))
        print(f"CHECKPOINT FINALIZE FAILED: {exc}", file=sys.stderr)
        return 1
    verdicts = {}
    try:
        for ln in Path(a.verdicts).read_text().splitlines():
            if "\t" in ln:
                s, v = ln.split("\t", 1)
                verdicts[s] = v.strip()
    except OSError:
        problems.append("the report's per-suite verdicts are missing")
    segs = segments(man)
    seg = segs[-1]["n"]
    fset = set(man["final_set"])
    results = []
    for s in sorted(a.suites):
        state, e, why = classify(d, man, runkey, s)
        attempts = [{"segment": x["segment"], "status": x["status"]} for x in man["chain"]
                    if x["kind"] == "result" and x.get("suite") == s]
        res = verify_attempt(d, man, runkey, e)[0] if e else None
        verdict = verdicts.get(s, "missing")
        if verdict not in ("passed", "failed"):
            problems.append(f"{s}: the report gave no verdict")
            verdict = "failed"
        # F8: the record's per-suite status IS the report's verdict, and the checkpoint must agree.
        if verdict == "passed" and state != "passed":
            problems.append(f"{s}: the report counted a pass the checkpoint cannot verify ({why})")
        if verdict == "failed" and state == "passed":
            problems.append(f"{s}: the report failed a suite the checkpoint holds as passed")
        if verdict == "passed" and s in fset and e is not None and e["segment"] != seg:
            problems.append(f"{s}: timing/clock-sensitive suite counted from segment "
                            f"{e['segment']}, not the final segment {seg} (F7)")
        results.append({"suite": s, "status": verdict, "segment": e["segment"] if e else None,
                        "checkpoint_state": state,
                        "started_utc": res.get("started_utc") if res else None,
                        "finished_utc": res.get("finished_utc") if res else None,
                        "exit_code": e.get("exit_code") if e else None,
                        "ok_count": res.get("ok_count") if res else None,
                        "leak_entries": e.get("leak_entries") if e else None,
                        "final_segment_set": s in fset, "attempts": attempts})
    resumed = len(segs) > 1
    now = utc()
    if resumed and _date_of(segs[0]["started_utc"]) != _date_of(now):
        problems.append(f"resumed run crossed the UTC date ({segs[0]['started_utc']} -> {now})")
    gaps = [{"after_segment": p["n"], "from_utc": p["finished_utc"] or p["last_result_utc"],
             "to_utc": nx["started_utc"]} for p, nx in zip(segs, segs[1:])]
    frag = {
        "checkpoint": {"dir": str(d), "run_id": a.run_id, "format": FORMAT,
                       "key_sha256": key_digest(man["key"]), "segments": segs, "gaps": gaps,
                       "resumed": resumed, "shard": man["key"].get("shard"),
                       "final_segment_suites": len(fset),
                       "chain_length": len(man["chain"]), "chain_head": man["chain"][-1]["mac"],
                       "problems": problems},
        "resumed": resumed,
        "suite_results": results,
        "started_utc": segs[0]["started_utc"],
    }
    atomic_replace(Path(a.fragment), canonical(frag))
    for p in problems:
        print(f"CHECKPOINT FINALIZE: {p}", file=sys.stderr)
    return 1 if problems else 0


def cmd_seal(a) -> int:
    """Close the segment in the chain after the terminal record is written."""
    d = Path(a.dir)
    try:
        runkey = load_runkey(a.run_id, d.parent)
        with _locked(d):
            man = load_manifest(d, a.run_id, runkey)
            try:
                rec_sha = sha256(Path(a.record).read_bytes())
            except OSError:
                rec_sha = None
            _append(man, runkey, {"kind": "end", "segment": current_segment(man),
                                  "status": a.status, "record_sha256": rec_sha, "at_utc": utc()})
            atomic_replace(d / "manifest.json", canonical(man))
        return 0
    except (Refused, OSError) as exc:
        print(f"CHECKPOINT seal: {exc}", file=sys.stderr)
        return 1


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("shard"); s.add_argument("spec"); s.add_argument("suites", nargs="*")
    for name in ("plan", "begin"):
        s = sub.add_parser(name)
        s.add_argument("--dir", required=True); s.add_argument("--jobs", required=True)
        s.add_argument("--record-dir", required=True); s.add_argument("--run-id", required=True)
        s.add_argument("--scope", required=True); s.add_argument("--shard", default="")
        s.add_argument("--resume", action="store_true")
        if name == "begin":
            s.add_argument("--to-run", nargs="*")
        s.add_argument("suites", nargs="*")
    s = sub.add_parser("start"); s.add_argument("--dir", required=True); s.add_argument("suite")
    s = sub.add_parser("finish"); s.add_argument("--dir", required=True)
    s.add_argument("suite"); s.add_argument("--code", required=True)
    s.add_argument("--out", required=True)
    s.add_argument("--leak-entries", default="0"); s.add_argument("--leak-bytes", default="0")
    s = sub.add_parser("restore"); s.add_argument("--dir", required=True)
    s.add_argument("--outdir", required=True); s.add_argument("suites", nargs="*")
    s = sub.add_parser("finalize"); s.add_argument("--dir", required=True)
    s.add_argument("--record-dir", required=True); s.add_argument("--run-id", required=True)
    s.add_argument("--verdicts", required=True); s.add_argument("--fragment", required=True)
    s.add_argument("suites", nargs="*")
    s = sub.add_parser("seal"); s.add_argument("--dir", required=True)
    s.add_argument("--run-id", required=True); s.add_argument("--status", required=True)
    s.add_argument("--record", required=True)
    a = p.parse_args(argv)
    return {"shard": cmd_shard, "plan": cmd_plan, "begin": cmd_begin, "start": cmd_start,
            "finish": cmd_finish, "restore": cmd_restore, "finalize": cmd_finalize,
            "seal": cmd_seal}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
