"""The board after a restart: the night it was built to watch, remembered.

WHAT HAPPENED ON 2026-09-25, and what this file defends.

At about 09:00Z the container restarted. Four department lanes had run overnight against
`ops/board.py` -- a module written specifically so that a lane's status is computed from the
job's own evidence and never from a watcher's belief, with 21 checks green behind it. It could
not answer a single question about those four lanes.

Not because it was wrong. Because **its job set was constructed in memory by whichever caller
happened to be running, and the evidence it pointed at was task-output files under `/tmp`.**
The process died and took the job list; the container died and took the logs. The integrator
reconstructed the night from `git log` and one surviving suite log -- which is precisely the
reconstruct-it-from-what-you-can-remember that the board was built to abolish, performed by
hand, by the person holding the tool.

That is the same defect as the two in `board.py`'s own docstring, one level up: **a verdict
that cannot be computed, because the evidence it rests on was never made durable.**

So the shape of the regression below is the shape of that morning:

  1. four lanes run and write their evidence;
  2. the process holding the job list ends -- simulated faithfully, by asking a GENUINELY
     FRESH interpreter, with nothing in it, to answer;
  3. the container is gone too, so one lane's `/tmp` log has been reclaimed;
  4. and the board must still name every lane and be right about each one, including being
     right that one of them can no longer be established at all.

Against the code as it stood on the morning of 2026-09-25 this file does not merely fail an
assertion -- it cannot import, because there was nothing durable to import. That is the
honest measure of the gap.

The states this adds are checked one at a time below the regression, including the two that
only a durable record can express: INTERRUPTED (the restart killed it, established from the
recorded container identity rather than guessed from a missing process) and EVIDENCE_LOST
(the log a container reclaimed -- which is a real state, and is NOT complete).
"""
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory

OPS = str(Path(__file__).resolve().parents[2] / "ops")
sys.path.insert(0, OPS)
import board as B                                                      # noqa: E402
import registry as R                                                   # noqa: E402

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

# A host epoch that is certainly not this container's. Enrolling under it and then reading
# from here is exactly what a restart looks like from the registry's side: the recorded
# container identity no longer matches the running one.
BEFORE = {"boot_id": "0000-before-the-restart", "btime": 1, "pid1_start": 1}


def log(tmp, name, text, *, age_s=0.0):
    p = Path(tmp) / f"{name}.log"
    p.write_text(text)
    if age_s:
        t = time.time() - age_s
        os.utime(p, (t, t))
    return p


def repo(tmp, name="repo"):
    """A real git repository. Integration is a fact about git, so git is what is asked."""
    r = Path(tmp) / name
    r.mkdir()

    def g(*args):
        return subprocess.run(["git", "-C", str(r), *args], capture_output=True, text=True)

    g("init", "-q")
    g("checkout", "-q", "-b", "trunk")
    g("config", "user.email", "board@brambleloop.test")
    g("config", "user.name", "board")
    g("config", "commit.gpgsign", "false")
    (r / "base.txt").write_text("base\n")
    g("add", "-A")
    g("commit", "-qm", "base")
    return r, g


def sha(g, ref="HEAD"):
    return g("rev-parse", ref).stdout.strip()


# =========================================================================================
# THE REGRESSION: 2026-09-25, ~09:00Z. Evidence on disk, job set gone, container gone.
# =========================================================================================
with TemporaryDirectory() as tmp:
    r, g = repo(tmp)

    # --- the night. Four lanes, each with its own evidence, each enrolled when it was
    # dispatched -- which is the only moment at which the container identity is truthful.
    reg = R.Registry(Path(tmp) / "JOBS.json", epoch=lambda: dict(BEFORE),
                     git=R.git_at(r))

    finished = log(tmp, "commerce", "TOTAL PASSING: 3647 ; suites failing: 0\nEXIT 0\n",
                   age_s=47 * 60)
    midrun = log(tmp, "visual", "relaxing 3000 iterations\n", age_s=40 * 60)
    reclaimed = log(tmp, "childrens", "TOTAL PASSING: 12 ; suites failing: 0\nEXIT 0\n")
    merged = log(tmp, "reliability", "TOTAL PASSING: 91 ; suites failing: 0\nEXIT 0\n",
                 age_s=60 * 60)

    for nm, p, lane in (("commerce", finished, "Etsy / Commerce"),
                        ("visual", midrun, "Visual"),
                        ("childrens", reclaimed, "Children's Safety"),
                        ("reliability", merged, "Reliability")):
        reg.enrol(B.Job(name=nm, log=p, result=RESULT, marker=f"lane-{nm}"),
                  lane=lane, branch=f"lane/{nm}", integration_ref="trunk")

    # Reliability's work actually landed on the branch overnight.
    g("checkout", "-q", "-b", "lane/reliability")
    (r / "retention.py").write_text("policy\n")
    g("add", "-A")
    g("commit", "-qm", "retention policy")
    g("checkout", "-q", "trunk")
    g("merge", "-q", "--no-ff", "-m", "merge reliability", "lane/reliability")
    reg.integrate("reliability", sha(g, "HEAD"))

    # --- the restart. `/tmp` is reclaimed, so one lane's evidence is simply not there.
    reclaimed.unlink()

    # --- and the answer is demanded of a GENUINELY fresh interpreter: a new process, no
    # imports from this one, no job list, nothing but the file on disk. This is the part the
    # code on the morning of 2026-09-25 had no way to satisfy.
    child = Path(tmp) / "after_the_restart.py"
    child.write_text(
        "import json, sys\n"
        f"sys.path.insert(0, {OPS!r})\n"
        "import registry as R\n"
        "reg = R.Registry(sys.argv[1], git=R.git_at(sys.argv[2]))\n"
        "print(json.dumps(reg.survey()))\n")
    proc = subprocess.run([sys.executable, str(child), str(reg.path), str(r)],
                          capture_output=True, text=True)
    check("a fresh process can answer at all after the restart",
          proc.returncode == 0 and proc.stdout.strip(), proc.stderr[-400:])
    out = json.loads(proc.stdout)
    rows = {row["job"]: row for row in out["rows"]}

    check("the board names every lane of the night it never saw in this process",
          sorted(rows) == ["childrens", "commerce", "reliability", "visual"], sorted(rows))
    check("and it knows which department each lane was",
          rows["visual"]["lane"] == "Visual", str(rows["visual"].get("lane")))
    check("and it knows, from the record, that it is not the container they ran on",
          all(row["same_host"] is False for row in rows.values()),
          str({k: v["same_host"] for k, v in rows.items()}))

    check("the finished lane nobody acted on is COMPLETE_UNREPORTED across the restart",
          rows["commerce"]["state"] == R.COMPLETE_UNREPORTED, str(rows["commerce"]))
    check("and it still carries its age, so the idle time is visible and not inferred",
          rows["commerce"]["age_s"] >= 47 * 60 - 5, str(rows["commerce"].get("age_s")))
    check("and it still quotes the job's own RESULT line",
          rows["commerce"]["evidence"] == "TOTAL PASSING: 3647 ; suites failing: 0",
          str(rows["commerce"].get("evidence")))

    check("the lane the restart killed is INTERRUPTED, not silently 'stalled'",
          rows["visual"]["state"] == R.INTERRUPTED, str(rows["visual"]))
    check("and it says the restart killed it rather than guessing from a missing process",
          "killed by the restart" in rows["visual"]["why"], rows["visual"]["why"])

    check("the lane whose /tmp log the container reclaimed is EVIDENCE_LOST",
          rows["childrens"]["state"] == R.EVIDENCE_LOST, str(rows["childrens"]))
    check("and EVIDENCE_LOST is emphatically not COMPLETE",
          rows["childrens"]["state"] not in (R.COMPLETE, R.COMPLETE_REPORTED,
                                             R.COMPLETE_UNREPORTED))
    check("and a lane whose completion cannot be established is not offered as refillable",
          "childrens" not in out["refillable"], str(out["refillable"]))
    check("and it is pulled to attention, because somebody has to decide about it",
          "childrens" in [x["job"] for x in out["needs_attention"]])

    check("the lane whose work reached the branch is INTEGRATED",
          rows["reliability"]["state"] == R.INTEGRATED, str(rows["reliability"]))
    check("and INTEGRATED is computed from git, not read back from the record",
          "ancestor of trunk" in rows["reliability"]["why"], rows["reliability"]["why"])

    check("the board says where the durable record is, so the answer can be audited",
          out["registry"] == str(reg.path))
    check("and it restates the rule it still enforces",
          "never from a watcher" in out["rule"])


# =========================================================================================
# The registry stores WHERE the evidence is, never WHAT the verdict was.
# =========================================================================================
with TemporaryDirectory() as tmp:
    reg = R.Registry(Path(tmp) / "JOBS.json", git=R.git_at(tmp))
    p = log(tmp, "suite", "TOTAL PASSING: 7 ; suites failing: 0\nEXIT 0\n")
    reg.enrol(B.Job(name="suite", log=p, result=RESULT, marker="m"), lane="L")
    raw = json.loads(reg.path.read_text())["jobs"]["suite"]

    check("the persisted record holds no state, status or verdict of any kind",
          not ({"state", "status", "verdict", "complete", "result_state"} & set(raw)),
          str(sorted(raw)))
    check("it holds the authoritative evidence LOCATION",
          raw["log"] == str(p), str(raw.get("log")))
    check("it holds no pids, which after a restart name a different process or none",
          "pid" not in json.dumps(raw).lower().replace("pid1_start", ""), str(raw))
    check("it records the container identity, which is what makes RUNNING re-derivable",
          set(raw["host"]) & {"boot_id", "btime", "pid1_start"} != set(), str(raw.get("host")))

    # The sentinel convention is part of the job's identity. NO_SENTINEL exists because a job
    # can finish under a convention this Job was not told about; a restarted process that
    # fell back to the default would mis-classify the lanes that write `SUITE EXIT 0`.
    old = log(tmp, "oldconv", "TOTAL PASSING: 3308 ; suites failing: 1\nSUITE EXIT 1\n")
    reg.enrol(B.Job(name="oldconv", log=old, result=RESULT, marker="m2"), lane="L")
    check("a job enrolled under the default sentinel still reads NO_SENTINEL after a restart",
          reg.recall("oldconv", table=[], epoch=dict(BEFORE))["state"] == R.NO_SENTINEL,
          str(reg.recall("oldconv", table=[], epoch=dict(BEFORE))))

    reg.enrol(B.Job(name="oldconv", log=old, result=RESULT, marker="m2",
                    terminal=re.compile(r"^SUITE EXIT (\d+)\s*$", re.M)), lane="L")
    after = reg.recall("oldconv", table=[], epoch=dict(BEFORE))
    check("and a job enrolled under its OWN sentinel convention keeps it across the restart",
          after["state"] == R.FAILED and after["exit_code"] == 1, str(after))

    # Found by the line above, in board.py, while building this: the exit code was taken only
    # when `job.terminal` was board's own compiled `_EXIT` OBJECT -- an identity test -- so a
    # job carrying any other sentinel, including the identical default pattern rebuilt from
    # the durable record, reported exit code 0 and read COMPLETE however it exited.
    j = B.Job(name="own", log=log(tmp, "own", "boom\nSUITE EXIT 3\n"),
              terminal=re.compile(r"^SUITE EXIT (\d+)\s*$", re.M))
    check("a non-default sentinel's exit code is parsed, not recognised by pattern identity",
          B.read(j, table=[])["exit_code"] == 3, str(B.read(j, table=[])))
    check("so a job that failed under its own sentinel convention reads FAILED, not COMPLETE",
          B.read(j, table=[])["state"] == B.FAILED, str(B.read(j, table=[])))
    same = B.Job(name="same", log=log(tmp, "same", "boom\nEXIT 4\n"),
                 terminal=re.compile(B._EXIT.pattern, B._EXIT.flags))
    check("and the very same default pattern, recompiled, behaves identically to the original",
          B.read(same, table=[])["exit_code"] == 4, str(B.read(same, table=[])))


# =========================================================================================
# RUNNING: the process probe speaks only about now, and only about this container.
# =========================================================================================
with TemporaryDirectory() as tmp:
    reg = R.Registry(Path(tmp) / "JOBS.json", git=R.git_at(tmp))
    p = log(tmp, "live", "working\n")
    reg.enrol(B.Job(name="live", log=p, result=RESULT, marker="lane-live"), lane="L")
    table = [(os.getpid() + 31337, "bash lane-live")]

    same = reg.recall("live", table=table)
    check("on the container it was launched on, a live process still reads RUNNING",
          same["state"] == R.RUNNING and same["same_host"] is True, str(same))

    # The self-match defect wearing a restart instead of a waiter: after a restart, a NEW job
    # carrying the same marker would make the OLD job read RUNNING. The probe is therefore
    # not consulted at all once the container identity has changed.
    across = reg.recall("live", table=table, epoch={"boot_id": "a-different-container"})
    check("after a restart a new process sharing the marker does NOT make the old job RUNNING",
          across["state"] == R.INTERRUPTED, str(across))
    check("and no pid from a foreign container is ever reported as this job's",
          not across.get("pids"), str(across.get("pids")))

    # And the honest middle: if the container identity cannot be determined at all, the cause
    # is not stated. Refusing to tell is a third answer, not a worse version of one of two.
    unknown = reg.recall("live", table=[], epoch={})
    check("with the container identity unknowable, the state is STALLED and says the cause "
          "was not determined",
          unknown["state"] == R.STALLED and "could not be determined" in unknown["why"],
          str(unknown))


# =========================================================================================
# Acknowledgement records that a completion was ACTED ON -- and survives the evidence.
# =========================================================================================
with TemporaryDirectory() as tmp:
    reg = R.Registry(Path(tmp) / "JOBS.json", git=R.git_at(tmp))
    p = log(tmp, "done", "TOTAL PASSING: 3647 ; suites failing: 0\nEXIT 0\n", age_s=47 * 60)
    reg.enrol(B.Job(name="done", log=p, result=RESULT, marker="lane-done"), lane="L")

    loud = reg.recall("done", table=[])
    check("before anyone acts, a finished lane is COMPLETE_UNREPORTED and carries its age",
          loud["state"] == R.COMPLETE_UNREPORTED and loud["age_s"] >= 47 * 60 - 5, str(loud))

    ack = reg.acknowledge("done", table=[])
    check("acknowledging records the job's own evidence, not a summary of it",
          ack["evidence"] == "TOTAL PASSING: 3647 ; suites failing: 0", str(ack))
    acted = reg.recall("done", table=[])
    check("and the lane then reads COMPLETE_REPORTED: action, not observation",
          acted["state"] == R.COMPLETE_REPORTED, str(acted))

    # The container is reclaimed. The log and its `.reported` sidecar go together.
    B.Job(name="done", log=p).ack.unlink(missing_ok=True)
    p.unlink()
    survivor = reg.recall("done", table=[], epoch=dict(BEFORE))
    check("a completion acted on before the restart is still COMPLETE_REPORTED after it",
          survivor["state"] == R.COMPLETE_REPORTED, str(survivor))
    check("and it still quotes the job's own words, copied at the moment somebody acted",
          survivor["evidence"] == "TOTAL PASSING: 3647 ; suites failing: 0", str(survivor))
    check("and it says plainly that the evidence file itself is gone",
          survivor["evidence_present"] is False and "evidence file is gone" in survivor["why"],
          str(survivor))

    # A watcher may never write a completion that the job did not write first.
    unfinished = log(tmp, "partial", "half way\n")
    reg.enrol(B.Job(name="partial", log=unfinished, result=RESULT, marker="lane-partial"),
              lane="L")
    refused = reg.acknowledge("partial", table=[])
    check("a job with no terminal evidence CANNOT be acknowledged as complete",
          refused["acknowledged"] is False, str(refused))
    check("and the refusal names the reason: that would be the watcher asserting completion",
          "watcher asserting" in refused["why"], refused["why"])
    check("and the lane is not thereby made reportable",
          reg.recall("partial", table=[])["state"] != R.COMPLETE_REPORTED)


# =========================================================================================
# Missing evidence: three different facts, and they are not one state.
# =========================================================================================
with TemporaryDirectory() as tmp:
    reg = R.Registry(Path(tmp) / "JOBS.json", git=R.git_at(tmp))
    ghost = Path(tmp) / "never-written.log"
    reg.enrol(B.Job(name="ghost", log=ghost, marker="lane-ghost"), lane="L")

    check("on this container, a job that has written nothing is MISSING",
          reg.recall("ghost", table=[])["state"] == R.MISSING,
          str(reg.recall("ghost", table=[])))
    lost = reg.recall("ghost", table=[], epoch=dict(BEFORE))
    check("across a restart the same absent file is EVIDENCE_LOST, which is a different fact",
          lost["state"] == R.EVIDENCE_LOST, str(lost))
    check("and it states that completion cannot be established at all for that lane",
          "cannot be established" in lost["why"], lost["why"])

    check("a job the registry never heard of is UNENROLLED, not assumed anything",
          reg.recall("nobody")["state"] == R.UNENROLLED, str(reg.recall("nobody")))


# =========================================================================================
# INTEGRATED is a fact about git, so git is asked -- every read, never once.
# =========================================================================================
with TemporaryDirectory() as tmp:
    r, g = repo(tmp)
    reg = R.Registry(Path(tmp) / "JOBS.json", git=R.git_at(r))

    def lane(name, text="TOTAL PASSING: 5 ; suites failing: 0\nEXIT 0\n", branch=None):
        p = log(tmp, name, text)
        reg.enrol(B.Job(name=name, log=p, result=RESULT, marker=f"lane-{name}"),
                  lane=name, branch=branch, integration_ref="trunk")
        return p

    # (a) branch merged with a real merge commit -> reachable, therefore in.
    g("checkout", "-q", "-b", "lane/in")
    (r / "in.txt").write_text("x\n")
    g("add", "-A")
    g("commit", "-qm", "in")
    g("checkout", "-q", "trunk")
    g("merge", "-q", "--no-ff", "-m", "merge in", "lane/in")
    lane("in", branch="lane/in")
    row = reg.recall("in", table=[])
    check("a lane whose branch is an ancestor of the integration ref is INTEGRATED",
          row["state"] == R.INTEGRATED, str(row))
    check("and the integration record names the ref it was computed against",
          row["integration"]["ref"] == "trunk", str(row["integration"]))

    # (b) branch with work not yet in trunk -> not in, and its own evidence still stands.
    g("checkout", "-q", "-b", "lane/out")
    (r / "out.txt").write_text("y\n")
    g("add", "-A")
    g("commit", "-qm", "out")
    g("checkout", "-q", "trunk")
    lane("out", branch="lane/out")
    row = reg.recall("out", table=[])
    check("a lane with commits not in the branch is NOT reported integrated",
          row["state"] != R.INTEGRATED and row["integration"]["status"] == R.NOT_IN_BRANCH,
          str(row))
    check("and its own evidence state is what it reads instead",
          row["state"] == R.COMPLETE_REPORTED or row["state"] == R.COMPLETE, str(row))

    # (c) squashed in: the lane's commits are unreachable, and the squash commit is the only
    # durable evidence there is. That is why a recorded commit outranks the branch tip.
    g("checkout", "-q", "-b", "lane/squash")
    (r / "squash.txt").write_text("z\n")
    g("add", "-A")
    g("commit", "-qm", "squash work")
    g("checkout", "-q", "trunk")
    g("merge", "-q", "--squash", "lane/squash")
    g("commit", "-qm", "squashed lane/squash")
    squash_sha = sha(g, "HEAD")
    lane("squash", branch="lane/squash")
    pre = reg.recall("squash", table=[])
    check("before the squash commit is recorded, the lane's own commits are NOT in the branch",
          pre["integration"]["status"] == R.NOT_IN_BRANCH, str(pre["integration"]))
    reg.integrate("squash", squash_sha)
    post = reg.recall("squash", table=[])
    check("with the squash commit recorded and verified, the lane reads INTEGRATED",
          post["state"] == R.INTEGRATED, str(post))

    # (d) a recorded merge that git contradicts. The record is never believed on its own.
    lane("rewound", branch=None)
    reg.integrate("rewound", "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef")
    row = reg.recall("rewound", table=[])
    check("a recorded merge commit git does not know is INTEGRATION_UNVERIFIED, not INTEGRATED",
          row["state"] == R.INTEGRATION_UNVERIFIED, str(row))
    check("and the row says the record could not be verified rather than restating it",
          "not believed" in row["why"] or "not reachable" in row["why"], row["why"])
    check("an unverifiable integration is pulled to attention",
          "rewound" in [x["job"] for x in reg.survey(table=[])["needs_attention"]])

    # A commit that IS known but is not reachable -- the branch was reset after the merge.
    g("checkout", "-q", "lane/out")
    orphan = sha(g, "HEAD")
    g("checkout", "-q", "trunk")
    lane("reset", branch=None)
    reg.integrate("reset", orphan)
    row = reg.recall("reset", table=[])
    check("a recorded merge that is no longer reachable stops reporting INTEGRATED",
          row["state"] == R.INTEGRATION_UNVERIFIED
          and "reset or rewritten" in row["why"], str(row))

    # (e) the branch is gone and nothing was recorded. This CANNOT be computed, and saying
    # "not integrated" would be a verdict from absence of evidence.
    lane("vanished", branch="lane/deleted-after-merge")
    row = reg.recall("vanished", table=[])
    check("with the branch deleted and no merge recorded, integration is UNKNOWN",
          row["integration"]["status"] == R.INTEGRATION_UNKNOWN, str(row["integration"]))
    check("and it is not reported as out of the branch, because that is a different claim",
          "cannot be computed" in row["integration"]["why"], row["integration"]["why"])

    # (f) merged work whose suite failed is still merged -- and is still surfaced.
    g("checkout", "-q", "-b", "lane/bad")
    (r / "bad.txt").write_text("b\n")
    g("add", "-A")
    g("commit", "-qm", "bad")
    g("checkout", "-q", "trunk")
    g("merge", "-q", "--no-ff", "-m", "merge bad", "lane/bad")
    lane("bad", text="TOTAL PASSING: 3 ; suites failing: 2\nEXIT 2\n", branch="lane/bad")
    row = reg.recall("bad", table=[])
    check("merged work whose suite failed reads INTEGRATED but keeps its evidence state",
          row["state"] == R.INTEGRATED and row["evidence_state"] == R.FAILED, str(row))
    check("and 'it is in the branch' never erases 'its suite failed'",
          "bad" in [x["job"] for x in reg.survey(table=[])["needs_attention"]])

    out = reg.survey(table=[])
    check("the survey lists the integrated lanes it verified",
          set(out["integrated"]) >= {"in", "squash", "bad"}, str(out["integrated"]))


# =========================================================================================
# The file itself: a registry that crashes or half-writes has forgotten, loudly.
# =========================================================================================
with TemporaryDirectory() as tmp:
    path = Path(tmp) / "JOBS.json"
    path.write_text("{ this is not json")
    reg = R.Registry(path, git=R.git_at(tmp))
    check("a corrupt registry reads as empty rather than raising into its caller",
          reg.load()["jobs"] == {}, str(reg.load()))
    check("and a survey against it still answers, with nothing in it",
          reg.survey(table=[])["rows"] == [])

    p = log(tmp, "j", "EXIT 0\n")
    reg.enrol(B.Job(name="j", log=p, marker="lane-j"), lane="L")
    check("enrolling over a corrupt registry repairs it",
          json.loads(path.read_text())["jobs"]["j"]["name"] == "j")
    check("and no temporary file is left beside it",
          [f.name for f in Path(tmp).glob("JOBS*.tmp")] == [])

    # Re-enrolment is a NEW run of the lane. Inheriting the previous run's acknowledgement or
    # merge would be this morning's defect in miniature: a verdict about work nobody saw.
    reg.acknowledge("j", table=[])
    reg.enrol(B.Job(name="j", log=p, marker="lane-j"), lane="L")
    check("re-enrolling a lane clears the previous run's acknowledgement",
          json.loads(path.read_text())["jobs"]["j"]["acknowledged"] is None)
    check("and clears the previous run's merge record",
          json.loads(path.read_text())["jobs"]["j"]["integrated"] is None)

    check("forgetting a lane it never had is not an error",
          reg.forget("never") is False)

print(f"\n  {PASSED} passing, {FAILED_N} failing")
sys.exit(1 if FAILED_N else 0)
