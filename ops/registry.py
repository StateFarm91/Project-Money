#!/usr/bin/env python3
"""The durable half of the job board: what must still be answerable after the container dies.

WHY THIS EXISTS. `board.py` computes a job's state from the job's own evidence, and it is
right about every job it is handed. The defect is upstream of that: **nothing ever handed it
the same jobs twice.** The job list was built in memory by whichever caller happened to be
running, and the evidence it pointed at was task-output files under `/tmp`.

  2026-09-25, ~09:00Z. The container restarted. Four department lanes had run overnight. The
  in-memory job set went with the process, `/tmp` went with the container, and the board --
  the tool built specifically so that a lane's status is never reconstructed from somebody's
  belief -- could say nothing at all about the night it had been watching. The integrator
  rebuilt the picture from `git log` and one surviving suite log, which is exactly the
  reconstruct-from-belief the board exists to replace, performed by hand.

That is the same defect family as the two failures in `board.py`'s own docstring: **a verdict
that cannot be computed, because the evidence it rests on was never made durable.** A watcher
that forgets is not a smaller version of a watcher that remembers; it is a watcher that has
to guess, and guessing is the thing.

WHAT IS PERSISTED, AND WHY EACH FIELD EARNS ITS PLACE

Only what is needed to *recompute* a verdict. No verdict is ever stored, because a stored
verdict is a watcher's state and `board.py`'s one rule forbids reading completion from that.

  name, lane          -- identity: which department this was, so a row can be named.
  log                 -- where the job's own evidence lives. The authoritative location, not
                         a copy of the evidence.
  terminal, result    -- the *regex sources* of the sentinel and headline conventions. Not
                         cosmetic: `NO_SENTINEL` exists precisely because a job can finish
                         under a convention this Job was not told about. A restarted process
                         that fell back to the default pattern would mis-classify a lane that
                         writes `SUITE EXIT 0`, so the convention has to survive with the job.
  marker              -- the job's process marker, never a watcher's command line.
  host                -- the boot identity of the container the job was launched in. This is
                         what makes RUNNING re-derivable rather than guessable; see below.
  branch, integration_ref
                      -- git coordinates, so "is this lane's work in the branch" is a
                         question git can be asked instead of a claim somebody types.
  integrated.commit   -- a recorded merge/squash commit. A *record*, which is then VERIFIED
                         against git on every read; it is never believed on its own.
  acknowledged        -- that a completion was acted on, with the evidence text copied at the
                         moment of acting. The copy is not a shortcut: it is the only thing
                         that survives `/tmp` being reclaimed, and it is the job's own words,
                         not the watcher's summary.

WHAT IS DELIBERATELY NOT PERSISTED

  * No state, status or verdict. Recomputed every read, from the job's evidence, by
    `board.read`. One rule, one implementation of it.
  * No pids. A pid from before a restart names a different process now, or nothing.
  * No log contents beyond the two matched lines copied at acknowledgement time. The log is
    the log; this is a registry, not an archive.
  * No schedule, no queue, no ownership, no retry policy, no supervision. This file cannot
    start, stop, retry, merge or promote anything. It answers one question -- what happened
    to lane X -- and it is the *caller* that acts.

HOW EACH STATE SURVIVES A RESTART

  RUNNING              The process probe only ever speaks about *now*, so after a restart it
                       cannot establish that a pre-restart job is running -- and worse, a new
                       job carrying the same marker would make it say so falsely. That is the
                       self-match defect wearing a different hat. So the probe is consulted
                       ONLY when the recorded host epoch still matches the current one. Same
                       container: `board.read` decides as it always has. Different container:
                       the probe is not consulted at all.
  COMPLETE_UNREPORTED  From the log's own sentinel plus the absence of a durable
                       acknowledgement, with its age. Unchanged, and now durable on both
                       halves rather than on a `.reported` file living next to a `/tmp` log.
  COMPLETE_REPORTED    From the durable acknowledgement record. This is the one state that is
                       *about* the watcher -- it records that somebody acted -- so it is the
                       one state that legitimately lives here rather than in the log.
  FAILED / NO_SENTINEL From the log, with the job's own recorded sentinel convention.
  INTERRUPTED          Computed, not guessed: the recorded host epoch differs from the current
                       one AND the log carries no terminal sentinel. Both halves are facts, so
                       "this job was killed by the restart" is established rather than
                       inferred from the absence of a process.
  EVIDENCE_LOST        The registry recorded a log that is no longer on disk, across a
                       restart. This is NOT `MISSING` ("wrote nothing") and it is emphatically
                       not `COMPLETE`. It is the state the reclaimed `/tmp` produces, and it
                       says that completion can no longer be established for this lane at all.
  INTEGRATED           A fact about git, so git is asked. Never asserted; see below.

INTEGRATION IS A GIT QUESTION AND IS ASKED OF GIT

A recorded merge commit is a claim. `git merge-base --is-ancestor <commit> <integration ref>`
is a computation, and it is re-run on every read, so a branch that was later reset or
rewritten stops reporting INTEGRATED instead of continuing to assert it. Two honest limits,
named rather than papered over:

  * `--is-ancestor` answers "are these commits reachable", not "is this content present". A
    squash merge leaves the lane's commits unreachable while its work is in. That is why the
    recorded commit takes priority over the branch tip: for a squash, the squash commit is
    the only durable evidence there is.
  * If the lane's branch has been deleted and no merge commit was recorded, integration is
    `unknown` and says so. It is not reported as not-integrated, because "we cannot compute
    it" and "it is not in" are different facts and conflating them is how this whole family
    of bugs starts.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import board as B                                                      # noqa: E402

# Beside `ops/LOCK`, and untracked for the same reason: it names machine-local paths. It
# survives a container restart because the checkout does; that is the whole requirement.
REGISTRY = Path(os.environ.get("BRAMBLELOOP_JOB_REGISTRY") or (_HERE / "JOBS.json"))
# F-342: every enrolled job says whether it IS the workload or merely WATCHES one. A query for
# the workload (`workloads`) never returns an observer, and an observer's marker must differ
# from the workload's, so neither the observer nor its shell can satisfy a liveness probe for
# the work it watches.
ROLES = ("work", "observer")

# The branch every lane is integrated into. Recorded per job so it cannot silently change
# underneath an old record.
INTEGRATION_REF = "claude/repository-setup-nc9x6o"

# --- the durable vocabulary ---------------------------------------------------------------
# board.py's states, re-exported so callers of this module need one import, then the states
# that only a durable record can express.
RUNNING = B.RUNNING
COMPLETE = B.COMPLETE
COMPLETE_UNREPORTED = B.COMPLETE_UNREPORTED
FAILED = B.FAILED
STALLED = B.STALLED
NO_SENTINEL = B.NO_SENTINEL
MISSING = B.MISSING
EVIDENCE_UNREADABLE = B.EVIDENCE_UNREADABLE

COMPLETE_REPORTED = "complete_reported"
INTERRUPTED = "interrupted"
EVIDENCE_LOST = "evidence_lost"
# This lane's own row could not be turned into a verdict at all -- a corrupt record, a
# pattern that no longer compiles, a git call that threw. It is a state rather than an
# exception because an exception here is not one lane's problem: it is every lane's, since
# it comes out of `survey` and takes the whole board with it. See `_row_or_refusal`.
UNREADABLE_RECORD = "unreadable_record"
INTEGRATED = "integrated"
INTEGRATION_UNVERIFIED = "integration_unverified"
UNENROLLED = "unenrolled"

# Integration sub-states, reported alongside the headline on every row.
IN_BRANCH = "in_branch"
NOT_IN_BRANCH = "not_in_branch"
INTEGRATION_UNKNOWN = "unknown"
INTEGRATION_CONTRADICTED = "contradicted"
INTEGRATION_NOT_RECORDED = "not_recorded"

_ATTENTION = (COMPLETE_UNREPORTED, FAILED, STALLED, NO_SENTINEL, INTERRUPTED,
              EVIDENCE_LOST, EVIDENCE_UNREADABLE, UNREADABLE_RECORD,
              INTEGRATION_UNVERIFIED)
_REFILLABLE = (COMPLETE, COMPLETE_UNREPORTED, COMPLETE_REPORTED, INTEGRATED)


def utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


# --- host identity -------------------------------------------------------------------------
def host_epoch() -> dict:
    """Which container this is, as three independent facts that a restart changes.

    Three rather than one because no single one is reliable everywhere: `boot_id` is the
    host kernel's and does not change when only the container is replaced; `btime` has
    one-second granularity; pid 1's start time is per-namespace and is the sharpest signal
    for a container restart. Any key that differs means a different container. A key that
    cannot be read is simply absent, so an unreadable `/proc` degrades to "cannot tell"
    rather than to a confident wrong answer.
    """
    out: dict = {}
    try:
        out["boot_id"] = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    except Exception:
        pass
    try:
        for line in Path("/proc/stat").read_text().splitlines():
            if line.startswith("btime "):
                out["btime"] = int(line.split()[1])
                break
    except Exception:
        pass
    try:
        # /proc/1/stat field 22 is starttime; fields 1 and 2 are pid and (comm), and comm can
        # contain spaces, so the split is on the closing paren rather than on whitespace.
        out["pid1_start"] = int(Path("/proc/1/stat").read_text().rsplit(") ", 1)[1].split()[19])
    except Exception:
        pass
    return out


def same_host(recorded: dict | None, current: dict | None) -> bool | None:
    """True / False / None, and None genuinely means None.

    Returning False when we simply cannot tell would turn every job on a `/proc`-less
    platform into an INTERRUPTED one, which is the manufactured verdict this module exists
    to refuse.
    """
    recorded = recorded or {}
    current = current or {}
    shared = set(recorded) & set(current)
    if not shared:
        return None
    return all(recorded[k] == current[k] for k in shared)


# --- git ------------------------------------------------------------------------------------
def git_at(repo: Path | str):
    """A callable that runs git in `repo` and returns (returncode, stdout).

    Injectable so that integration can be tested against a real repository built by the test,
    rather than against a mock that agrees with whatever the code does.
    """
    repo = str(repo)

    def run(*args: str) -> tuple[int, str]:
        try:
            p = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True,
                               timeout=30)
        except Exception as exc:                                  # git absent, repo absent
            return 127, str(exc)
        return p.returncode, p.stdout.strip()

    return run


def _repo_root() -> Path:
    return _HERE.parent


def integration_state(rec: dict, git) -> dict:
    """Is this lane's work in the branch? Asked of git, every time, never trusted from record.

    Priority is deliberate: a recorded commit beats the branch tip, because a squash merge
    leaves the branch's own commits unreachable and the squash commit is then the only
    durable evidence that the work landed.
    """
    ref = rec.get("integration_ref") or INTEGRATION_REF
    recorded = (rec.get("integrated") or {}).get("commit")
    branch = rec.get("branch")

    code, ref_sha = git("rev-parse", "--verify", f"{ref}^{{commit}}")
    if code != 0:
        return {"status": INTEGRATION_UNKNOWN, "ref": ref, "integrated": False,
                "why": (f"the integration ref {ref!r} does not resolve in this repository, so "
                        "whether anything is in it cannot be computed here")}

    if recorded:
        code, sha = git("rev-parse", "--verify", f"{recorded}^{{commit}}")
        if code != 0:
            return {"status": INTEGRATION_CONTRADICTED, "ref": ref, "commit": recorded,
                    "integrated": False,
                    "why": ("a merge commit was recorded for this lane but git does not know "
                            "it; the record cannot be verified and is not believed")}
        code, _ = git("merge-base", "--is-ancestor", sha, ref_sha)
        if code == 0:
            return {"status": IN_BRANCH, "ref": ref, "commit": sha, "integrated": True,
                    "why": f"the recorded commit {sha[:7]} is an ancestor of {ref}"}
        return {"status": INTEGRATION_CONTRADICTED, "ref": ref, "commit": sha,
                "integrated": False,
                "why": (f"the recorded commit {sha[:7]} is NOT reachable from {ref}: the "
                        "branch was reset or rewritten after the merge was recorded")}

    if branch:
        code, tip = git("rev-parse", "--verify", f"{branch}^{{commit}}")
        if code != 0:
            return {"status": INTEGRATION_UNKNOWN, "ref": ref, "branch": branch,
                    "integrated": False,
                    "why": (f"the lane's branch {branch!r} no longer exists and no merge "
                            "commit was recorded, so whether its work reached " + ref +
                            " cannot be computed -- this is not the same as it being out")}
        code, _ = git("merge-base", "--is-ancestor", tip, ref_sha)
        if code == 0:
            return {"status": IN_BRANCH, "ref": ref, "branch": branch, "commit": tip,
                    "integrated": True,
                    "why": f"every commit on {branch} is reachable from {ref}"}
        return {"status": NOT_IN_BRANCH, "ref": ref, "branch": branch, "commit": tip,
                "integrated": False,
                "why": f"{branch} carries commits that are not in {ref}"}

    return {"status": INTEGRATION_NOT_RECORDED, "ref": ref, "integrated": False,
            "why": "no branch and no merge commit were recorded for this lane"}


def merge_delay(rec: dict, git) -> dict:
    """F-489: seconds from a lane's last commit to the commit that integrated it.

    Asked of git, like `integration_state`: the lane's tip commit time against the recorded
    merge commit, or else the first merge on the integration ref's ancestry path that contains
    the tip. None with the reason when either end cannot be established -- a lane still out of
    the branch has no merge delay yet, which is different from a delay of zero.
    """
    state = integration_state(rec, git)
    if not state.get("integrated"):
        return {"seconds": None, "why": f"not integrated: {state.get('status')}"}
    ref = state.get("ref") or INTEGRATION_REF
    branch = rec.get("branch")
    tip = None
    if branch:
        code, out = git("rev-parse", "--verify", f"{branch}^{{commit}}")
        tip = out if code == 0 else None
    recorded = (rec.get("integrated") or {}).get("commit")
    merge = recorded
    if merge is None and tip:
        code, out = git("log", "--merges", "--ancestry-path", "--reverse", "--format=%H",
                        f"{tip}..{ref}")
        merge = out.splitlines()[0] if code == 0 and out else None
    if not tip or not merge:
        return {"seconds": None,
                "why": "the lane tip or its merge commit cannot be identified in git"}
    c1, t_tip = git("log", "-1", "--format=%ct", tip)
    c2, t_merge = git("log", "-1", "--format=%ct", merge)
    if c1 != 0 or c2 != 0 or not t_tip.isdigit() or not t_merge.isdigit():
        return {"seconds": None, "why": "commit times unreadable"}
    return {"seconds": max(0, int(t_merge) - int(t_tip)), "tip": tip, "merge": merge,
            "why": "integration commit time minus lane tip commit time"}


class OwnershipConflict(ValueError):
    """Two live lanes claiming overlapping paths (F-457)."""

    def __init__(self, clashes: list[dict]):
        self.clashes = clashes
        super().__init__("; ".join(
            f"{c['path']} overlaps {c['other_path']} owned by live lane {c['lane']!r}"
            for c in clashes[:5]))


def _literal_prefix(pattern: str) -> str:
    """The part of a path pattern before its first wildcard."""
    cut = len(pattern)
    for ch in "*?[":
        i = pattern.find(ch)
        if i != -1:
            cut = min(cut, i)
    return pattern[:cut]


class DuplicateWork(ValueError):
    """F-476: another live lane already holds these rows or this question."""

    def __init__(self, dups: list[dict]):
        self.duplicates = dups
        super().__init__("duplicate work with a live lane: " + "; ".join(
            f"{d['lane']} ({d['why']})" for d in dups))


def question_fingerprint(question: str) -> str:
    import hashlib

    words = re.findall(r"[a-z0-9]+", (question or "").lower())
    return hashlib.sha256(" ".join(words).encode()).hexdigest()[:16] if words else ""


def duplicate_work(data: dict, name: str, rows: list[str], qfp: str) -> list[dict]:
    out = []
    for other, rec in (data.get("jobs") or {}).items():
        if other == name or rec.get("integrated") or rec.get("role", "work") != "work":
            continue
        shared = sorted(set(rows) & set(rec.get("rows") or []))
        if shared:
            out.append({"lane": other, "why": f"already holds rows {shared}"})
        elif qfp and rec.get("question_fp") == qfp:
            out.append({"lane": other, "why": "already answering the same question"})
    return out


def paths_overlap(a: str, b: str) -> bool:
    """Conservative: two manifests overlap when either one's literal prefix contains the
    other's, path-segment aware (`src/a` does not overlap `src/ab`)."""
    pa, pb = _literal_prefix(a).rstrip("/"), _literal_prefix(b).rstrip("/")
    if not pa or not pb:
        return True  # a bare wildcard owns everything

    def under(x, y):  # x is y or inside y
        return x == y or x.startswith(y + "/") or (y.endswith("/") and x.startswith(y))

    wild_a, wild_b = pa != a.rstrip("/"), pb != b.rstrip("/")
    if under(pa, pb) or under(pb, pa):
        return True
    # A wildcard mid-segment ("src/a*") also covers names that extend the prefix.
    return (wild_a and pb.startswith(pa)) or (wild_b and pa.startswith(pb))


def ownership_conflicts(data: dict, name: str, owns: list[str]) -> list[dict]:
    out = []
    for other, rec in (data.get("jobs") or {}).items():
        if other == name or rec.get("role", "work") != "work" or rec.get("integrated"):
            continue
        for p in owns:
            for q in rec.get("owns") or []:
                if paths_overlap(p, q):
                    out.append({"path": p, "other_path": q, "lane": other})
    return out


# --- the registry ----------------------------------------------------------------------------
class Registry:
    """A JSON file and the functions that read and write it. That is the whole mechanism."""

    VERSION = 1

    def __init__(self, path: Path | str = REGISTRY, *, epoch=host_epoch, git=None):
        self.path = Path(path)
        self._epoch = epoch
        self._git = git or git_at(_repo_root())

    # -- storage ------------------------------------------------------------------------
    def load(self) -> dict:
        """Never raises. A registry that crashes its reader has forgotten in a louder way."""
        try:
            data = json.loads(self.path.read_text())
        except Exception:
            return {"version": self.VERSION, "jobs": {}}
        if not isinstance(data, dict) or not isinstance(data.get("jobs"), dict):
            return {"version": self.VERSION, "jobs": {}}
        return data

    def _save(self, data: dict) -> None:
        """Write-then-rename, so a registry is never half a registry.

        `ops/lock.py` learned this the expensive way about read-then-write; the same applies
        to a file whose entire job is to still be readable after an abrupt stop.
        """
        data["version"] = self.VERSION
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
        os.replace(tmp, self.path)

    # -- writing ------------------------------------------------------------------------
    def enrol(self, job: B.Job, *, lane: str = "", branch: str | None = None,
              integration_ref: str = INTEGRATION_REF, role: str = "work",
              watches: str | None = None, owns: tuple[str, ...] | list[str] = (),
              rows: tuple[str, ...] | list[str] = (), question: str = "",
              stop: dict | None = None) -> dict:
        """Record where this job's evidence will be, before it is needed.

        Enrolment is the only moment at which the host identity is truthful, which is why it
        is captured here and not at read time.

        F-457 (ownership boundaries): `owns` is the lane's path manifest (repository paths or
        globs). Enrolment -- the pre-dispatch moment -- refuses a manifest that overlaps a live
        lane's, so two lanes cannot be dispatched onto the same files. A lane is live until
        its work is integrated or the record is forgotten.
        """
        if role not in ROLES:
            raise ValueError(f"role must be one of {ROLES}, not {role!r}")
        data = self.load()
        owns = [str(p).strip()[2:] if str(p).strip().startswith("./") else str(p).strip()
                for p in owns or () if str(p).strip()]
        if owns and role == "work":
            clash = ownership_conflicts(data, job.name, owns)
            if clash:
                raise OwnershipConflict(clash)
        rows = sorted({str(r).strip().upper() for r in rows or () if str(r).strip()})
        stop = validate_stop(stop) if stop else None
        qfp = question_fingerprint(question)
        if role == "work" and (rows or qfp):
            dup = duplicate_work(data, job.name, rows, qfp)
            if dup:
                raise DuplicateWork(dup)
        if role == "observer":
            target = data["jobs"].get(watches or "")
            if target is None:
                raise ValueError("an observer must name the enrolled job it watches")
            if job.marker and job.marker == target.get("marker"):
                raise ValueError("an observer cannot carry its workload's marker: a liveness "
                                 "probe for the work would then be satisfied by the observer")
        prior = data["jobs"].get(job.name, {})
        rec = {
            "name": job.name,
            "role": role,
            "watches": watches if role == "observer" else None,
            "lane": lane or prior.get("lane", ""),
            "log": str(job.log),
            "terminal": job.terminal.pattern,
            "terminal_flags": int(job.terminal.flags),
            "result": job.result.pattern if job.result is not None else None,
            # The job's own stop-time convention, persisted for the same reason `terminal` is:
            # a restarted process that fell back to "no stamp" would silently go back to
            # reading the age off the filesystem, which is the thing `board.age_source`
            # exists to stop being invisible.
            "finished": job.finished.pattern if job.finished is not None else None,
            "marker": job.marker,
            "host": self._epoch(),
            "branch": branch if branch is not None else prior.get("branch"),
            "integration_ref": integration_ref,
            "enrolled_utc": utc(),
            "owns": owns or prior.get("owns") or [],
            # F-476: the requirement rows and the question this lane answers, so a second
            # live lane on the same work is refused before it is dispatched.
            "rows": rows or prior.get("rows") or [],
            "question_fp": qfp or prior.get("question_fp") or "",
            # F-492: the lane's own stop and escalation criteria, checked by `survey`.
            "stop": stop or prior.get("stop"),
            # A re-enrolment is a new run of the lane; an old acknowledgement or merge would
            # otherwise be inherited by work it never saw.
            "acknowledged": None,
            "integrated": None,
        }
        data["jobs"][job.name] = rec
        self._save(data)
        return rec

    def wait(self, name: str, on: list[str], *, why: str = "") -> dict:
        """F-485: record that lane `name` waits on lanes `on`; returns the graph after it."""
        data = self.load()
        rec = data["jobs"].get(name)
        if rec is None:
            raise ValueError(f"{name!r} is not enrolled")
        if not str(why).strip():
            raise ValueError("a wait names what it waits for")
        have = {w.get("lane") for w in rec.get("waits_on") or []}
        rec["waits_on"] = list(rec.get("waits_on") or []) + [
            {"lane": t, "why": str(why)[:200], "since": utc()} for t in on if t and t not in have]
        self._save(data)
        return wait_for_cycles(data)

    def unwait(self, name: str, on: list[str] | None = None) -> dict:
        data = self.load()
        rec = data["jobs"].get(name)
        if rec is not None:
            rec["waits_on"] = [w for w in rec.get("waits_on") or []
                               if on is not None and w.get("lane") not in on]
            self._save(data)
        return wait_for_cycles(data)

    def workloads(self) -> list[str]:
        """Names of jobs that ARE work. Records written before roles existed count as work."""
        return sorted(n for n, r in self.load()["jobs"].items()
                      if r.get("role", "work") == "work")

    def forget(self, name: str) -> bool:
        data = self.load()
        gone = data["jobs"].pop(name, None) is not None
        if gone:
            self._save(data)
        return gone

    def acknowledge(self, name: str, *, now: float | None = None, table=None) -> dict:
        """Record that a completion was ACTED ON, and copy the evidence that justified it.

        Two refusals, both load-bearing:
          * a job with no terminal evidence cannot be acknowledged as complete. Acknowledging
            one would be a watcher writing a completion, which is the forbidden direction.
          * the snapshot is the job's own matched lines, verbatim. It is what lets this
            module answer COMPLETE_REPORTED after `/tmp` is reclaimed without inventing
            anything.
        """
        data = self.load()
        rec = data["jobs"].get(name)
        if rec is None:
            raise KeyError(f"{name!r} was never enrolled; there is nothing to acknowledge")
        job = self.job(name)
        row = B.read(job, now=now, table=table)
        if row["state"] not in (B.COMPLETE, B.COMPLETE_UNREPORTED, B.FAILED):
            return {"acknowledged": False, "state": row["state"],
                    "why": ("this job has no terminal evidence, so there is no completion to "
                            "acknowledge; acknowledging it would be the watcher asserting one")}
        rec["acknowledged"] = {
            "at_utc": utc(),
            "evidence": row.get("evidence"),
            "exit_code": row.get("exit_code"),
            "state_at_ack": B.FAILED if row.get("exit_code") else B.COMPLETE,
        }
        data["jobs"][name] = rec
        self._save(data)
        B.acknowledge(job)          # keep the sidecar too, for anything still reading it
        return {"acknowledged": True, **rec["acknowledged"]}

    def integrate(self, name: str, commit: str) -> dict:
        """Record the commit that carried this lane in. Recorded, then verified on every read.

        Writing the commit here does not make the lane integrated. `integration_state` asks
        git on every single read, so a recorded merge that git cannot reach reports
        CONTRADICTED rather than INTEGRATED.
        """
        data = self.load()
        rec = data["jobs"].get(name)
        if rec is None:
            raise KeyError(f"{name!r} was never enrolled")
        code, sha = self._git("rev-parse", "--verify", f"{commit}^{{commit}}")
        rec["integrated"] = {"commit": sha if code == 0 else commit, "recorded_utc": utc(),
                             "resolved_at_record": code == 0}
        data["jobs"][name] = rec
        self._save(data)
        return rec["integrated"]

    # -- reading ------------------------------------------------------------------------
    def job(self, name: str) -> B.Job:
        """Rebuild the `Job` exactly as it was enrolled, conventions included."""
        rec = self.load()["jobs"].get(name)
        if rec is None:
            raise KeyError(name)
        return self._job(rec)

    @staticmethod
    def _job(rec: dict) -> B.Job:
        terminal = re.compile(rec.get("terminal") or B._EXIT.pattern,
                              rec.get("terminal_flags", int(B._EXIT.flags)))
        result = re.compile(rec["result"]) if rec.get("result") else None
        finished = re.compile(rec["finished"]) if rec.get("finished") else None
        return B.Job(name=rec["name"], log=Path(rec["log"]), terminal=terminal,
                     result=result, marker=rec.get("marker", ""), finished=finished)

    def recall(self, name: str, *, now: float | None = None, table=None,
               epoch: dict | None = None) -> dict:
        """One lane's durable verdict."""
        rec = self.load()["jobs"].get(name)
        if rec is None:
            return {"job": name, "state": UNENROLLED, "evidence": None,
                    "why": ("the registry has no record of this job, so nothing about it can "
                            "be established; it was never enrolled, or the registry was lost")}
        return self._row_or_refusal(rec, now=now, table=table,
                                    epoch=self._epoch() if epoch is None else epoch)

    def survey(self, *, now: float | None = None, table=None,
               epoch: dict | None = None) -> dict:
        """Every enrolled lane, from the durable record alone.

        Takes no job list. That is the point: the caller does not have to remember what ran.
        """
        data = self.load()
        here = self._epoch() if epoch is None else epoch
        rows = [self._row_or_refusal(r, now=now, table=table, epoch=here)
                for _, r in sorted(data["jobs"].items())]
        return {
            "rows": rows,
            # A lane that is in the branch is normally done with. Three exceptions, because
            # "merged" is not "verified": work merged from a lane whose suite failed, whose
            # completion was never established, or that the restart killed mid-run, is
            # exactly the thing somebody has to look at.
            "needs_attention": [r for r in rows if r["state"] in _ATTENTION
                                or (r["state"] == INTEGRATED and r.get("evidence_state")
                                    in (FAILED, NO_SENTINEL, INTERRUPTED))],
            "running": [r for r in rows if r["state"] == RUNNING],
            "refillable": [r["job"] for r in rows if r["state"] in _REFILLABLE],
            "integrated": [r["job"] for r in rows if r["state"] == INTEGRATED],
            # F-485: lanes waiting on each other in a cycle can never finish.
            "deadlocks": wait_for_cycles(data),
            # F-492: live lanes past their own escalation or stop criteria.
            "stop_criteria": stop_states(data, now=now),
            "registry": str(self.path),
            "host": here,
            "rule": ("completion comes from the job's own terminal evidence, never from a "
                     "watcher's state; the registry records only where that evidence is"),
        }

    # -- the verdict ---------------------------------------------------------------------
    def _row_or_refusal(self, rec: dict, *, now, table, epoch: dict) -> dict:
        """One lane's verdict, or a named refusal -- never an exception out of `survey`.

        THE REASON THIS WRAPPER EXISTS, because a bare try/except deserves an argument.

        `survey`'s promise is that the caller does not have to remember what ran. That promise
        is void if one lane can make the call raise: a corrupt record, a `terminal` pattern
        that no longer compiles, a log path that is a directory, a git binary that is gone --
        any one of them used to come out of `survey` as a traceback, and a traceback is not a
        board. The operator then does what the integrator did on 2026-09-25: reconstructs the
        night from `git log`, by hand, while the completed evidence of every OTHER lane sits
        on disk unread. The one rule is not "compute a verdict from the job's own evidence
        when nothing goes wrong"; a watcher that falls over is a watcher that forgets.

        So a lane that cannot be read reports that, as itself, in the row where it belongs,
        and the other lanes are answered. `UNREADABLE_RECORD` is in `_ATTENTION`, so it is
        surfaced rather than swallowed, and it is never in `_REFILLABLE`.
        """
        try:
            return self._row(rec, now=now, table=table, epoch=epoch)
        except Exception as exc:                                   # noqa: BLE001
            return {"job": str(rec.get("name") or "<unnamed>"),
                    "lane": rec.get("lane", ""),
                    "state": UNREADABLE_RECORD,
                    "evidence": None,
                    "evidence_state": UNREADABLE_RECORD,
                    "evidence_path": rec.get("log"),
                    "error": type(exc).__name__,
                    "why": ("this lane's registry record could not be turned into a verdict "
                            f"({type(exc).__name__}). Nothing about it is established -- it "
                            "is not complete and it is not failed -- and it is reported here "
                            "rather than raised so that every other lane still gets an "
                            "answer")}

    def _row(self, rec: dict, *, now, table, epoch: dict) -> dict:
        now = now or time.time()
        job = self._job(rec)
        integ = integration_state(rec, self._git)
        ack = rec.get("acknowledged")
        here = same_host(rec.get("host"), epoch)
        base = {
            "job": rec["name"],
            "lane": rec.get("lane", ""),
            "role": rec.get("role", "work"),
            "evidence_path": rec["log"],
            "evidence_present": job.log.exists(),
            "same_host": here,
            "reported": bool(ack),
            "reported_utc": (ack or {}).get("at_utc"),
            "integration": integ,
            "enrolled_utc": rec.get("enrolled_utc"),
        }

        # --- the evidence state, from board.py, under this job's own recorded conventions.
        # The process probe is consulted only on the container the job was launched in. On a
        # different container it cannot establish liveness, and it CAN match a new job that
        # happens to carry the same marker -- the self-match defect with a restart in place
        # of a waiter. `table=[]` means the probe is asked about an empty world, so the
        # restart branches below decide instead.
        probe_is_meaningful = here is not False
        if job.log.exists():
            ev = B.read(job, now=now, table=(table if probe_is_meaningful else []))
        else:
            ev = None

        if ev is None:
            if ack:
                # The evidence file is gone, but somebody copied the job's own terminal lines
                # at the moment they acted on them. That copy is the job's words, not ours.
                state = FAILED if ack.get("exit_code") else COMPLETE_REPORTED
                row = {**base, "state": state,
                       "evidence": ack.get("evidence"), "exit_code": ack.get("exit_code"),
                       "why": ("the evidence file is gone, but this completion was "
                               f"acknowledged at {ack.get('at_utc')} and the job's own "
                               "terminal lines were copied then")}
            elif here is False:
                row = {**base, "state": EVIDENCE_LOST, "evidence": None,
                       "why": ("this lane was enrolled on a container that no longer exists "
                               "and its evidence file is gone with it. Completion cannot be "
                               "established for this lane at all -- this is NOT complete, "
                               "and it is not the same as a job that wrote nothing")}
            else:
                row = {**base, "state": MISSING, "evidence": None,
                       "why": "the job has written no output at all"}
            return self._with_integration(row, integ)

        state = ev["state"]

        # --- restart refinements, each computed from two facts rather than from an absence.
        if here is False and state in (STALLED, RUNNING):
            state = INTERRUPTED
            ev = {**ev, "why": (
                "the container this job was launched in no longer exists and the log carries "
                "no terminal sentinel: the job was killed by the restart. It is certainly "
                "not running, and it did not finish. Whether its work was nearly done cannot "
                "be read from the log and is not guessed here")}
        elif here is None and state == STALLED:
            ev = {**ev, "why": (ev["why"] + "; whether the container it ran in is still this "
                                "one could not be determined, so the cause is not stated")}

        # Acknowledgement is durable-first. The `.reported` sidecar still counts, but only on
        # the container that wrote it: across a restart it is as gone as the log it sat
        # beside, and a missing sidecar must not be read as "nobody acted".
        acked = bool(ack) or (here is not False and bool(ev.get("acknowledged")))
        base["reported"] = acked
        if state in (COMPLETE, COMPLETE_UNREPORTED):
            state = COMPLETE_REPORTED if acked else (
                COMPLETE_UNREPORTED if ev.get("age_s", 0) >= B.UNREPORTED_AFTER_S else COMPLETE)

        row = {**base, "state": state,
               "evidence": ev.get("evidence"), "exit_code": ev.get("exit_code"),
               "age_s": ev.get("age_s"), "age_source": ev.get("age_source"),
               "pids": ev.get("pids"), "why": ev["why"]}
        return self._with_integration(row, integ)

    @staticmethod
    def _with_integration(row: dict, integ: dict) -> dict:
        """Integration is the terminal answer for a lane -- but it never erases the evidence.

        `evidence_state` keeps whatever the job's own output established, so merged work
        whose suite failed, or merged work whose log the container reclaimed, is still
        visible as that. A board that let "it is in the branch" overwrite "its suite failed"
        would be the same collapse of two facts into one that this module exists to refuse.
        """
        row["evidence_state"] = row["state"]
        if integ["integrated"]:
            row["state"] = INTEGRATED
            row["why"] = integ["why"] + f"; its own evidence reads {row['evidence_state']}"
        elif integ["status"] == INTEGRATION_CONTRADICTED:
            row["state"] = INTEGRATION_UNVERIFIED
            row["why"] = integ["why"] + f"; its own evidence reads {row['evidence_state']}"
        return row


# --- convenience ------------------------------------------------------------------------------
# ---- F-485: deadlock detection across lanes ----------------------------------------------

def _live(rec: dict) -> bool:
    return not rec.get("integrated") and rec.get("role", "work") == "work"


STOP_KEYS = ("escalate_after_hours", "stop_after_hours", "escalate_to", "stop_when")


def validate_stop(stop: dict) -> dict:
    """F-492: a lane's stop/escalation criteria. Hours are checkable; the prose names what
    stopping means for this lane. A criterion with neither hour bound is refused."""
    if not isinstance(stop, dict) or set(stop) - set(STOP_KEYS):
        raise ValueError(f"stop criteria take only {STOP_KEYS}")
    out = {}
    for k in ("escalate_after_hours", "stop_after_hours"):
        if stop.get(k) is not None:
            v = float(stop[k])
            if v <= 0:
                raise ValueError(f"{k} must be positive")
            out[k] = v
    if not out:
        raise ValueError("stop criteria need escalate_after_hours or stop_after_hours")
    if out.get("escalate_after_hours", 0) > out.get("stop_after_hours", float("inf")):
        raise ValueError("escalation comes before the stop")
    if not str(stop.get("escalate_to") or "").strip() or not str(
            stop.get("stop_when") or "").strip():
        raise ValueError("stop criteria name who is escalated to and what stopping means")
    out["escalate_to"] = str(stop["escalate_to"]).strip()
    out["stop_when"] = str(stop["stop_when"]).strip()
    return out


def stop_states(data: dict, *, now: float | None = None) -> list[dict]:
    """Live work lanes with criteria, past escalation or stop, from the enrolment time."""
    now_dt = (datetime.fromtimestamp(now, timezone.utc) if now is not None
              else datetime.now(timezone.utc))
    out = []
    for name, rec in sorted((data.get("jobs") or {}).items()):
        st = rec.get("stop")
        if not st or rec.get("integrated") or rec.get("role", "work") != "work":
            continue
        try:
            started = datetime.fromisoformat(str(rec.get("enrolled_utc")).replace("Z", "+00:00"))
        except ValueError:
            out.append({"lane": name, "state": "UNKNOWN", "why": "no readable enrolment time"})
            continue
        hours = (now_dt - started).total_seconds() / 3600
        state = ("stop" if hours >= st.get("stop_after_hours", float("inf")) else
                 "escalate" if hours >= st.get("escalate_after_hours", float("inf")) else None)
        if state:
            out.append({"lane": name, "state": state, "hours": round(hours, 1),
                        "escalate_to": st["escalate_to"], "stop_when": st["stop_when"]})
    return out


def wait_for_cycles(data: dict) -> dict:
    """F-485: the wait-for graph across live lanes (lane A waits on lane B), its cycles, and
    waits naming a lane that is not enrolled or no longer live (which can never clear).

    A cycle is a deadlock: every lane in it is waiting for another lane in it, so none of
    them can finish. Reported, never resolved here -- breaking a cycle is a decision about
    which lane gives way, and this file decides nothing.
    """
    jobs = data.get("jobs") or {}
    live = {n for n, r in jobs.items() if _live(r)}
    edges = {n: sorted({w.get("lane") for w in (jobs[n].get("waits_on") or [])
                        if w.get("lane")}) for n in live}
    dangling = [{"lane": n, "waits_on": t,
                 "why": ("not enrolled" if t not in jobs else "no longer live (integrated "
                         "or an observer): the wait can never clear")}
                for n, ts in sorted(edges.items()) for t in ts if t not in live]
    cycles, seen = [], set()
    for start in sorted(live):
        stack = [(start, [start])]
        while stack:
            node, path = stack.pop()
            for nxt in edges.get(node, []):
                if nxt == start:
                    cyc = path[:]
                    key = frozenset(cyc)
                    if key not in seen:
                        seen.add(key)
                        cycles.append(cyc)
                elif nxt in live and nxt not in path and nxt > start:
                    stack.append((nxt, path + [nxt]))
    return {"edges": {k: v for k, v in edges.items() if v}, "cycles": cycles,
            "dangling": dangling, "deadlocked": bool(cycles)}


def survey(path: Path | str = REGISTRY, **kw) -> dict:
    return Registry(path).survey(**kw)


def ack_and_account(reg: "Registry", name: str, *, waiter=None) -> dict:
    """Acknowledge `name` and account its idle gap (F-344), exactly as `waiter.py ack` does.

    Imported lazily: `waiter` imports this module. A waiter that cannot be built still lets
    the acknowledgement through, and says the gap went unaccounted.
    """
    if waiter is None:
        try:
            import waiter as W

            waiter = W.Waiter(registry=reg)
        except Exception as exc:  # noqa: BLE001
            out = reg.acknowledge(name)
            out["idle"] = {"accounted": False, "why": f"waiter unavailable: {exc}"[:200]}
            return out
    return waiter.ack(name)


def reliability_lines(*, ledger=None, waste: dict | None = None) -> list[str]:
    """Open reliability incidents and the week's time waste, for the board (F-344, F-350)."""
    try:
        import incidents as I

        if waste is None:
            import waiter as W

            waste = W.Waiter().waste_report(7)
        return I.board_lines(ledger, waste)
    except Exception as exc:  # noqa: BLE001 - the board must not fail on its own accounting
        return [f"reliability ledger unavailable ({type(exc).__name__}); NOT checked"]


def _cli(argv: list[str]) -> int:
    """Read and write the file. No scheduling, no supervision, no daemon -- on purpose."""
    argv = list(argv)
    opts = {}
    for flag in ("--role", "--watches", "--owns", "--rows", "--question", "--stop"):
        if flag in argv:
            i = argv.index(flag)
            if i + 1 >= len(argv):
                print(f"{flag} needs a value")
                return 2
            opts[flag[2:]] = argv[i + 1]
            del argv[i:i + 2]
    cmd = argv[1] if len(argv) > 1 else "survey"
    reg = Registry(Path(os.environ.get("BRAMBLELOOP_JOB_REGISTRY") or REGISTRY))
    if cmd == "survey":
        out = reg.survey()
        out["reliability"] = reliability_lines()
        print(json.dumps(out, indent=2, sort_keys=True))
        return 1 if (out["needs_attention"] or out["deadlocks"]["deadlocked"]
                     or out["stop_criteria"]) else 0
    if cmd == "wait" and len(argv) >= 4:
        # ops/registry.py wait NAME ON1,ON2 WHY...
        try:
            out = reg.wait(argv[2], [x for x in argv[3].split(",") if x],
                           why=" ".join(argv[4:]))
        except ValueError as exc:
            print(f"refused: {exc}")
            return 2
        print(json.dumps(out, indent=2, sort_keys=True))
        return 1 if out["deadlocked"] else 0
    if cmd == "unwait" and len(argv) >= 3:
        on = [x for x in argv[3].split(",") if x] if len(argv) > 3 else None
        print(json.dumps(reg.unwait(argv[2], on), indent=2, sort_keys=True))
        return 0
    if cmd == "enrol" and len(argv) >= 4:
        name, log = argv[2], argv[3]
        lane = argv[4] if len(argv) > 4 else ""
        branch = argv[5] if len(argv) > 5 else None
        marker = argv[6] if len(argv) > 6 else ""
        try:
            rec = reg.enrol(B.Job(name=name, log=Path(log), marker=marker), lane=lane,
                            branch=branch, role=opts.get("role", "work"),
                            watches=opts.get("watches"),
                            owns=[p for p in (opts.get("owns") or "").split(",") if p],
                            rows=[r for r in (opts.get("rows") or "").split(",") if r],
                            question=opts.get("question") or "",
                            stop=json.loads(opts["stop"]) if opts.get("stop") else None)
        except ValueError as exc:
            print(f"refused: {exc}")
            return 2
        print(json.dumps(rec, indent=2, sort_keys=True))
        return 0
    if cmd == "ack" and len(argv) >= 3:
        # F-344: the heartbeat's ack (step 3) accounts the lane's idle wall-clock too, through
        # the waiter -- acknowledging here used to record the ack and forget the gap.
        print(json.dumps(ack_and_account(reg, argv[2]), indent=2, sort_keys=True,
                         default=str))
        return 0
    if cmd == "integrate" and len(argv) >= 4:
        print(json.dumps(reg.integrate(argv[2], argv[3]), indent=2, sort_keys=True))
        return 0
    if cmd == "forget" and len(argv) >= 3:
        print("forgotten" if reg.forget(argv[2]) else "not enrolled")
        return 0
    print(__doc__.strip().splitlines()[0])
    if cmd == "workloads":
        print(json.dumps(reg.workloads(), indent=2))
        return 0
    print("usage: registry.py [survey | workloads | enrol <name> <log> [lane] [branch] "
          "[marker] [--role work|observer] [--watches <job>] [--owns path,glob,...] | "
          "ack <name> | integrate <name> <commit> | forget <name>]")
    return 2


if __name__ == "__main__":
    raise SystemExit(_cli(sys.argv))
