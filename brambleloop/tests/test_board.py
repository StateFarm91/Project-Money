"""The job board, and the two historical failures it exists to prevent.

Both are reproduced as tests rather than described in a comment, because both were
previously believed not to be happening. A belief about a watcher cannot be run in CI.
"""
import os
import re
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "ops"))
import board as B                                                  # noqa: E402

PASSED = FAILED_N = 0


def check(name, ok, detail=""):
    global PASSED, FAILED_N
    if ok:
        PASSED += 1
        print("OK  ", name)
    else:
        FAILED_N += 1
        print("FAIL", name, detail)


RESULT = re.compile(r"TOTAL PASSING: \d+ ; suites failing: \d+")


def _job(tmp, text, name="suite", marker="run_tests.sh"):
    log = Path(tmp) / f"{name}.log"
    log.write_text(text)
    return B.Job(name=name, log=log, result=RESULT, marker=marker)


# --- REGRESSION 1: the observer that matched itself (~100 minutes lost) -------------------
# A waiter looped on `pgrep -f "run_tests.sh"` from inside a shell whose own command line
# contained `run_tests.sh`. Every waiter matched itself, so the loop could never end, and the
# rising match count read as progress when it was the waiter count. The suite had finished in
# about seven minutes.
#
# The process table is injected so the exact shape of that failure can be built: the ONLY
# process carrying the marker is the observer itself.
with TemporaryDirectory() as tmp:
    me = os.getpid()
    observer_only = [(me, "/bin/bash -c until pgrep -f run_tests.sh; do sleep 1; done")]

    check("a liveness probe does not count the observer's own process",
          B.alive("run_tests.sh", table=observer_only) == [],
          str(B.alive("run_tests.sh", table=observer_only)))

    # And with the job genuinely running, it IS counted -- the exclusion must not be a
    # blanket refusal that would make everything look finished.
    both = observer_only + [(me + 99999, "bash run_tests.sh")]
    check("a genuinely running job is still counted alongside the observer",
          B.alive("run_tests.sh", table=both) == [me + 99999],
          str(B.alive("run_tests.sh", table=both)))

    check("the caller's whole lineage is excluded, not merely its own pid",
          me in B.lineage() and len(B.lineage()) >= 1, str(sorted(B.lineage())[:4]))

    # The end-to-end shape: no terminal evidence, and the only match is the observer. The old
    # code reported RUNNING for a hundred minutes. The board must say STALLED instead.
    j = _job(tmp, "some partial output\n")
    r = B.read(j, table=observer_only)
    check("a job with no sentinel whose only match is the observer reads STALLED, not RUNNING",
          r["state"] == B.STALLED, str(r))


# --- REGRESSION 2: the finished job nobody read (~47 minutes idle) ------------------------
# No self-match. The suite was launched, other work intervened, and the log was never
# re-read. "Awaiting the suite" was reported while TOTAL PASSING sat in the file.
with TemporaryDirectory() as tmp:
    done = "TOTAL PASSING: 3469 ; suites failing: 0\nEXIT 0\n"
    j = _job(tmp, done)

    fresh = B.read(j, now=os.stat(j.log).st_mtime + 1)
    check("a job that has just finished reads COMPLETE", fresh["state"] == B.COMPLETE,
          str(fresh))

    stale = B.read(j, now=os.stat(j.log).st_mtime + 47 * 60)
    check("a finished job nobody acknowledged becomes COMPLETE_UNREPORTED",
          stale["state"] == B.COMPLETE_UNREPORTED, str(stale))
    check("and it carries its age, so the idle time is visible rather than inferred",
          stale["age_s"] >= 47 * 60 - 1, str(stale.get("age_s")))
    check("and it quotes the RESULT, not merely the fact of completion",
          stale["evidence"] == "TOTAL PASSING: 3469 ; suites failing: 0", str(stale))

    B.acknowledge(j)
    after = B.read(j, now=os.stat(j.log).st_mtime + 47 * 60)
    check("acknowledging clears it, so the state tracks action and not observation",
          after["state"] == B.COMPLETE and after["acknowledged"], str(after))


# --- the states the old code could not express -------------------------------------------
with TemporaryDirectory() as tmp:
    check("a failing job is FAILED rather than merely complete",
          B.read(_job(tmp, "boom\nEXIT 1\n", name="bad"))["state"] == B.FAILED)
    check("a job that has written nothing is MISSING rather than assumed running",
          B.read(B.Job(name="ghost", log=Path(tmp) / "nope.log",
                       marker="nothing"))["state"] == B.MISSING)
    running_table = [(os.getpid() + 12345, "bash run_tests.sh")]
    check("a job with no sentinel and a live process is RUNNING",
          B.read(_job(tmp, "working\n"), table=running_table)["state"] == B.RUNNING)


# --- the board pulls the neglected lane to the front --------------------------------------
with TemporaryDirectory() as tmp:
    a = _job(tmp, "TOTAL PASSING: 10 ; suites failing: 0\nEXIT 0\n", name="finished")
    b = _job(tmp, "still going\n", name="live", marker="live-marker")
    table = [(os.getpid() + 4242, "bash live-marker")]
    out = B.board([a, b], now=os.stat(a.log).st_mtime + 47 * 60, table=table)

    check("a finished-but-unread lane is surfaced as needing attention",
          [r["job"] for r in out["needs_attention"]] == ["finished"], str(out["needs_attention"]))
    check("the running lane is not reported as needing attention",
          [r["job"] for r in out["running"]] == ["live"], str(out["running"]))
    check("a finished lane is reported refillable without anyone having to notice",
          "finished" in out["refillable"] and "live" not in out["refillable"],
          str(out["refillable"]))
    check("the board states the rule it enforces",
          "never from a watcher" in out["rule"])

# --- the board must not compute a death from absence of evidence -------------------------
# Found on the board's first real use against live logs: older scripts end `SUITE EXIT 0`
# rather than `EXIT 0`, and the first version called those "died without finishing". That is
# a verdict from absence of evidence -- the exact defect the board exists to catch, in the
# board itself. Two facts, not one: a job can die, or it can finish under a sentinel
# convention this Job was not told about, and nothing in the log distinguishes them.
with TemporaryDirectory() as tmp:
    j = _job(tmp, "TOTAL PASSING: 3308 ; suites failing: 1\nSUITE EXIT 1\n", name="oldconv")
    r = B.read(j, table=[])
    check("a finished-looking log with an unrecognised sentinel is NOT called dead",
          r["state"] == B.NO_SENTINEL, str(r))
    check("and it says which fact is missing rather than inventing one",
          "not the same as having died" in r["why"], str(r))
    check("it is still pulled to attention, because it cannot be trusted as complete",
          "oldconv" in [x["job"] for x in B.board([j], table=[])["needs_attention"]])
    check("it is NOT reported refillable, because completion was never established",
          "oldconv" not in B.board([j], table=[])["refillable"])

    truncated = _job(tmp, "starting up\n", name="died")
    check("an output with no result and no sentinel and no process is still STALLED",
          B.read(truncated, table=[])["state"] == B.STALLED)


# --- REGRESSION 3: a log that exists and cannot be read ----------------------------------
# `read` used to call `read_text` bare, so a log path that exists and refuses its bytes -- a
# directory where a file should be, a permission the container lost -- raised out of `read`,
# out of `board`, and out of `registry.survey`. That is not one lane's problem: it is every
# lane's, because it destroys the one call that answers for all of them while their finished
# evidence sits on disk. Evidence that exists and goes unread is the whole defect family.
with TemporaryDirectory() as tmp:
    unreadable = Path(tmp) / "wedged.log"
    unreadable.mkdir()
    j = B.Job(name="wedged", log=unreadable, result=RESULT, marker="lane-wedged")
    r = B.read(j, table=[])
    check("a log whose bytes cannot be read is EVIDENCE_UNREADABLE, not an exception",
          r["state"] == B.EVIDENCE_UNREADABLE, str(r))
    check("and not MISSING, because writing nothing and refusing to be read differ",
          r["state"] != B.MISSING and "having written nothing" in r["why"], str(r))

    finished = _job(tmp, "TOTAL PASSING: 3469 ; suites failing: 0\nEXIT 0\n", name="ok")
    out = B.board([j, finished], now=os.stat(finished.log).st_mtime + 47 * 60, table=[])
    check("one unreadable lane does not stop the board answering about the others",
          {x["job"] for x in out["rows"]} == {"wedged", "ok"}, str(out["rows"]))
    check("the finished lane is still surfaced as finished-and-unread beside it",
          "ok" in [x["job"] for x in out["needs_attention"]], str(out["needs_attention"]))
    check("the unreadable lane is surfaced and is not refillable",
          "wedged" in [x["job"] for x in out["needs_attention"]]
          and "wedged" not in out["refillable"], str(out["refillable"]))


# --- REGRESSION 4: the age of a completion was the filesystem's opinion -------------------
# COMPLETE_UNREPORTED is regression 2 named as a state, and it fired on the log's mtime.
# An mtime is not something the job wrote: a copied, restored or relocated log carries a
# fresh one, so a suite that finished 47 minutes ago reads COMPLETE and silently leaves
# `needs_attention`. The age now comes from a stamp the job wrote when one exists, and every
# finished row says which of the two it used.
with TemporaryDirectory() as tmp:
    stopped = time.time() - 47 * 60
    body = (f"TOTAL PASSING: 3469 ; suites failing: 0\nFINISHED AT {stopped:.0f}\nEXIT 0\n")
    stamp = re.compile(r"FINISHED AT (\S+)")

    copied = _job(tmp, body, name="copied")               # mtime is now, by construction
    check("a copied log with no stamp reads COMPLETE: the 47 minutes are invisible",
          B.read(copied, table=[])["state"] == B.COMPLETE)
    check("and the row discloses that the age is the filesystem's",
          B.read(copied, table=[])["age_source"] == "mtime")

    told = B.Job(name="copied", log=copied.log, result=RESULT, marker="x", finished=stamp)
    r = B.read(told, table=[])
    check("with the job's own stamp the same bytes read COMPLETE_UNREPORTED",
          r["state"] == B.COMPLETE_UNREPORTED, str(r))
    check("and the age is the job's, not the filesystem's",
          r["age_source"] == "job" and r["age_s"] >= 47 * 60 - 5, str(r))
    check("an ISO 8601 stamp is read too, not only epoch seconds",
          B._stamp("2026-09-25T17:24:00Z") == B._stamp("2026-09-25T17:24:00+00:00")
          and B._stamp("2026-09-25T17:24:00Z") is not None)
    check("a stamp that will not parse is refused rather than read as the epoch",
          B._stamp("never") is None and B._stamp("") is None)

print(f"\n  {PASSED} passing, {FAILED_N} failing")
sys.exit(1 if FAILED_N else 0)
