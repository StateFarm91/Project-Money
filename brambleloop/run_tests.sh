#!/usr/bin/env bash
# Full Brambleloop acceptance suite.
#
# Runs the suites concurrently and prints them back in the canonical order, so the log reads
# exactly as it did when this was a sequential loop: `== <suite>`, its indented output, and
# one `TOTAL PASSING: n ; suites failing: m` line, with the exit code being the number of
# failing suites.
#
# Why concurrency rather than faster tests. Measured 2026-09-18: the whole suite is 1133
# seconds and six files are 97% of it, because each of them drives the full eleven-product
# pipeline including 2000-pixel image rendering. The standing rule here is that slow and
# representative beats fast and unrepresentative -- and the blank-hero defect is what that
# rule is for: a check that passed locally at a smaller scale while production, at the real
# scale, was right to refuse. So nothing about what the tests do is changed. The suites were
# already independent processes with their own temporary databases; they were simply queued
# one behind another.
#
# PY overrides the interpreter. JOBS overrides the concurrency; JOBS=1 is the original
# sequential behaviour and the escape hatch if a suite ever turns out not to be independent
# after all.
#
# ---- Run binding, concurrency guard and targeted runs (F-169, F-170, F-345, F-346, F-347) ----
#
# WHY THE RUNNER WRITES ITS OWN PROVENANCE. The Build 2 certification log was bound to its
# commit only by its hand-typed filename, and "the suite is green" was a sentence somebody
# carried from one message to the next. A total nobody can tie to a SHA and a tree state is a
# claim, not evidence. So the log now opens with RUN ID / RUN STARTED / GIT SHA / TREE / SCOPE
# and closes with RUN FINISHED / DURATION / the same SHA, all written by this script from git
# and the clock, and a JSON run record is written beside a full copy of the log:
#
#   $SUITE_RECORD_DIR (default artifacts/suite_runs, git-ignored, survives a container restart
#   because the checkout does)/<run id>.json and <run id>.log
#
# The record is written at start with status "running" and rewritten at the end ("passed",
# "failed", or "interrupted" from the trap), so the latest validated suite is a file query --
# `python3 ../ops/deploy_guard.py latest-suite` -- rather than an inspection of shell processes.
# `release_eligible` is true only for a full (unfiltered) run, on a clean tree, whose HEAD did
# not move during the run, with zero failing suites. That is the one flag the deploy guard
# accepts, which is how "full suite against the exact committed tree" stops being a habit.
#
# REQUIRE_CLEAN=1 refuses a dirty tree before anything runs (exit 3). Without it a dirty run
# is allowed -- workers validate uncommitted work all day -- but it is recorded as dirty and
# can never be release-eligible.
#
# ONE RUN PER COMMIT, SCOPE AND ENVIRONMENT. Two full suites for the same commit on the same
# machine double the wall time of both and prove nothing twice; it happened more than once
# when a second session could not see that the first was already running. The lock is a
# single `noclobber` create (O_EXCL, as in ops/lock.py) keyed by SHA + scope + interpreter +
# host. A second invocation prints the running run's lock and record and exits 75 without
# starting anything. A lock whose process is gone (pid not alive, or alive with a different
# start time, i.e. a reused pid) is stale and is taken over, and the takeover is said. The
# deliberate-parallel override is ALLOW_PARALLEL=1.
#
# TARGETED FIRST. SUITES="test_a test_b.py tests/test_c.py" (spaces or commas) runs only the
# named suites -- the smallest affected set, which is what to run after diagnosing a hang or
# observer defect, before paying twenty minutes for the full suite. An unknown name is an
# error (exit 2), never a vacuous green run of nothing. THEN_FULL=1 with SUITES runs the full
# suite afterwards only if the targeted suites passed.
#
# Exit codes: the number of failing suites (unchanged); 2 unknown suite name; 3 dirty tree
# under REQUIRE_CLEAN; 75 another identical run is in progress; 130 interrupted.
#
# ---- Job identity, durable completion, one state per operation (F-331, F-333, F-335, F-341,
# F-342; wave 3 lane TOOLS) ----
#
# IDENTITY. The run id is minted before anything else and the script re-executes itself once
# with argv[0] = `brambleloop-suite[<run id>]`, so the process carries its own durable job id
# in its command line. A liveness probe for this run (ops/board.py `alive`) matches that
# marker, which no observer, waiter or parent shell carries -- the workload is separately
# identifiable from anything watching it (F-342). The run then enrols itself in the job
# registry (`../ops/registry.py enrol suite-<run id> ... --role work`; SUITE_REGISTRY=0 opts
# out, SUITE_REGISTRY_CLI / BRAMBLELOOP_JOB_REGISTRY relocate it) so consumers read the id and
# its persisted state instead of rediscovering the run by process-name matching (F-331).
#
# DURABLE COMPLETION. Every terminal path -- passed, failed, interrupted -- rewrites the JSON
# record once and then appends `EXIT <code>` as the last line of the run's log: the sentinel
# board.py/registry.py read. Completion is a fact on disk, independent of whoever was watching
# (F-335); the record and the sentinel carry the same code, written by the producer only
# (F-341).
#
# ATTACH, DON'T DUPLICATE. ATTACH=1 turns "an identical run is already in progress" from exit 75
# into observing THAT run: the invocation starts nothing, takes no lock, writes no record, waits
# (ATTACH_TIMEOUT seconds, default 7200) for the running run's record to become terminal, prints
# it and exits with its exit code (130 if it was interrupted, 124 on timeout) -- one operation,
# one state, every observer reading the same record (F-333).
set -u
if [ -z "${_BRAMBLELOOP_SUITE_JOB:-}" ]; then
  export _BRAMBLELOOP_SUITE_JOB="$(date -u +%Y%m%dT%H%M%SZ)-$$"
  exec -a "brambleloop-suite[$_BRAMBLELOOP_SUITE_JOB]" bash "${BASH_SOURCE[0]}" "$@"
fi
RUN_ID="$_BRAMBLELOOP_SUITE_JOB"
# Not inherited: a suite (or a THEN_FULL chain) that starts run_tests.sh again is a new job.
unset _BRAMBLELOOP_SUITE_JOB
JOB_MARKER="brambleloop-suite[$RUN_ID]"
cd "$(dirname "${BASH_SOURCE[0]}")"
PY="${PY:-.venv/bin/python}"
JOBS="${JOBS:-$(nproc 2>/dev/null || echo 4)}"
RECORD_DIR="${SUITE_RECORD_DIR:-artifacts/suite_runs}"

utc() { date -u +%Y-%m-%dT%H:%M:%SZ; }
# Field 22 of /proc/<pid>/stat: when that process started, in clock ticks since boot. A pid is
# only "the same process" if this matches too; pids are reused.
proc_start() {
  local s
  s=$(cat "/proc/$1/stat" 2>/dev/null) || return 1
  s=${s##*) }
  # shellcheck disable=SC2086
  set -- $s
  echo "${20}"
}

RUN_STARTED="$(utc)"
RUN_STARTED_EPOCH=$(date +%s)
GIT_SHA="$(git rev-parse HEAD 2>/dev/null || echo UNKNOWN)"
if porcelain="$(git status --porcelain 2>/dev/null)"; then
  DIRTY_PATHS=$(printf '%s' "$porcelain" | grep -c . || true)
  if [ "$DIRTY_PATHS" -eq 0 ]; then TREE_STATE="clean"; else TREE_STATE="dirty"; fi
else
  DIRTY_PATHS=-1; TREE_STATE="unknown"
fi

if [ "${REQUIRE_CLEAN:-0}" = "1" ] && [ "$TREE_STATE" != "clean" ]; then
  echo "REFUSED: REQUIRE_CLEAN=1 and the tree is $TREE_STATE ($DIRTY_PATHS paths) at $GIT_SHA." >&2
  echo "Commit or discard the changes; a release suite must run on the exact committed tree." >&2
  exit 3
fi

# ---- which suites -------------------------------------------------------------------------------
# Canonical order. This is the order results are printed in, cheapest first, so a failure in
# the CIR engine is visible at the top of the log rather than buried.
# Discovered rather than listed.
#
# This was a hand-maintained array, and on 2026-09-21 it was three suites out of date: two
# test files written that morning -- for the teardown reader and the canonical reference
# pack -- were not in it, so "the suite is green" was true and did not include the code it
# was written for. A list somebody has to remember to update is a list that is wrong
# exactly when new work lands, which is the moment the check matters most. The glob has the
# property the endpoint walk already has: a new suite is covered the moment it exists.
SUITES_REQUEST="${SUITES:-}"
SUITES=()
if [ -z "$SUITES_REQUEST" ]; then
  SCOPE="full"
  while IFS= read -r f; do SUITES+=("$f"); done < <(ls tests/test_*.py | sort)
  if [ "${#SUITES[@]}" -lt 100 ]; then
    echo "only ${#SUITES[@]} suites found; the discovery is not working" >&2
    exit 1
  fi
else
  SCOPE="filtered"
  for name in ${SUITES_REQUEST//,/ }; do
    case "$name" in */*) ;; *) name="tests/$name" ;; esac
    case "$name" in *.py) ;; *) name="$name.py" ;; esac
    if [ ! -f "$name" ]; then
      echo "unknown suite '$name' in SUITES; nothing was run" >&2
      exit 2
    fi
    dup=""
    for s in "${SUITES[@]+"${SUITES[@]}"}"; do [ "$s" = "$name" ] && dup=1 && break; done
    [ -z "$dup" ] && SUITES+=("$name")
  done
  if [ "${#SUITES[@]}" -eq 0 ]; then
    echo "SUITES was set but named nothing; nothing was run" >&2
    exit 2
  fi
  mapfile -t SUITES < <(printf '%s\n' "${SUITES[@]}" | sort)
fi
SCOPE_KEY="$SCOPE:$(printf '%s ' "${SUITES[@]}")"
[ "$SCOPE" = "full" ] && SCOPE_KEY="full"

# ---- the concurrency guard ------------------------------------------------------------------------
mkdir -p "$RECORD_DIR/locks"
RECORD_FILE="$RECORD_DIR/$RUN_ID.json"
LOG_FILE="$RECORD_DIR/$RUN_ID.log"
PY_REAL="$(readlink -f "$PY" 2>/dev/null || echo "$PY")"
LOCK_KEY="$(printf '%s|%s|%s|%s' "$GIT_SHA" "$SCOPE_KEY" "$PY_REAL" "$(hostname 2>/dev/null)" \
            | sha256sum | cut -c1-16)"
LOCK_FILE="$RECORD_DIR/locks/$LOCK_KEY.lock"
MY_START="$(proc_start $$ || echo 0)"
LOCK_HELD=""
PARALLEL="${ALLOW_PARALLEL:-0}"
TAKEOVER=""

lock_body() {
  printf 'run_id=%s\npid=%s\npid_start=%s\nstarted=%s\ngit_sha=%s\nscope=%s\nrecord=%s\nlog=%s\n' \
    "$RUN_ID" "$$" "$MY_START" "$RUN_STARTED" "$GIT_SHA" "$SCOPE_KEY" "$RECORD_FILE" "$LOG_FILE"
}
lock_field() { sed -n "s/^$1=//p" "$LOCK_FILE" 2>/dev/null | head -1; }

if [ "$PARALLEL" != "1" ]; then
  for attempt in 1 2; do
    if ( set -o noclobber; lock_body > "$LOCK_FILE" ) 2>/dev/null; then
      LOCK_HELD=1
      break
    fi
    other_pid="$(lock_field pid)"; other_start="$(lock_field pid_start)"
    live_start="$( [ -n "$other_pid" ] && proc_start "$other_pid" || true)"
    if [ -n "$other_pid" ] && [ -n "$live_start" ] && [ "$live_start" = "$other_start" ] \
       && [ "${ATTACH:-0}" = "1" ]; then
      other_record="$(lock_field record)"
      echo "ATTACHED (observer) to run $(lock_field run_id) for commit $GIT_SHA, scope $SCOPE."
      echo "Starting nothing; reading its record until it is terminal (F-333)."
      ATTACH_RECORD="$other_record" ATTACH_TIMEOUT="${ATTACH_TIMEOUT:-7200}" "$PY" - <<'PYEOF'
import json, os, sys, time
path, limit = os.environ["ATTACH_RECORD"], float(os.environ["ATTACH_TIMEOUT"])
deadline = time.time() + limit
rec = None
while time.time() < deadline:
    try:
        rec = json.load(open(path))
    except (OSError, ValueError):
        rec = None
    if rec and rec.get("status") not in (None, "running"):
        break
    time.sleep(0.5)
else:
    print(f"ATTACH TIMEOUT after {limit:.0f}s; the run is still {rec and rec.get('status')}")
    sys.exit(124)
print(f"ATTACHED RESULT: run {rec['run_id']} {rec['status']}; suites failing "
      f"{rec.get('suites_failing')}; tests passing {rec.get('tests_passing')}; "
      f"exit {rec.get('exit_code')}; record {path}")
sys.exit(int(rec.get("exit_code") if rec.get("exit_code") is not None else 1))
PYEOF
      exit $?
    fi
    if [ -n "$other_pid" ] && [ -n "$live_start" ] && [ "$live_start" = "$other_start" ]; then
      echo "SUITE ALREADY RUNNING for commit $GIT_SHA, scope $SCOPE, this environment."
      echo "Not starting a second one (F-346). Read the running run instead:"
      sed 's/^/   /' "$LOCK_FILE"
      other_record="$(lock_field record)"
      if [ -n "$other_record" ] && [ -f "$other_record" ]; then
        echo "   its run record:"; sed 's/^/     /' "$other_record"
      fi
      echo "Set ATTACH=1 to wait on it and take its result, or ALLOW_PARALLEL=1 to run in parallel deliberately."
      exit 75
    fi
    # Stale: the process that took it is gone. Move it aside atomically and retry the create
    # once; if another invocation wins that race, the second attempt reports it as running.
    TAKEOVER="$(lock_field run_id)"
    mv -f "$LOCK_FILE" "$LOCK_FILE.stale.$$" 2>/dev/null; rm -f "$LOCK_FILE.stale.$$"
  done
  if [ -z "$LOCK_HELD" ]; then
    echo "could not take the suite lock $LOCK_FILE after removing a stale one" >&2
    exit 75
  fi
fi

# ---- the run record -------------------------------------------------------------------------------
# Written by the interpreter the suite runs under, atomically (temp + rename), so a reader never
# sees half a record. Values arrive through the environment, not through string interpolation.
write_record() {
  RR_STATUS="$1" RR_FINISHED="${2:-}" RR_DURATION="${3:-}" RR_EXIT="${4:-}" \
  RR_TOTAL="${total:-0}" RR_FAILED="${failed:-0}" RR_FAILTESTS="${fail_tests:-0}" \
  RR_SKIPS="${skip_tests:-0}" RR_FAILING="${failing_list:-}" RR_NOPASS="${nopass_list:-}" \
  RR_END_SHA="${END_SHA:-}" RR_RECORD="$RECORD_FILE" RR_LOG="$LOG_FILE" RR_RUN_ID="$RUN_ID" \
  RR_STARTED="$RUN_STARTED" RR_SHA="$GIT_SHA" RR_TREE="$TREE_STATE" RR_DIRTY="$DIRTY_PATHS" \
  RR_SCOPE="$SCOPE" RR_SUITES="$(printf '%s\n' "${SUITES[@]}")" RR_PARALLEL="$PARALLEL" \
  RR_TAKEOVER="$TAKEOVER" RR_PY="$PY_REAL" RR_JOBS="$JOBS" RR_LOCK="${LOCK_HELD:+$LOCK_FILE}" \
  RR_JOB="suite-$RUN_ID" RR_MARKER="$JOB_MARKER" RR_ENROLLED="${ENROLLED:-}" \
  RR_LEAK_N="${leak_entries:-}" RR_LEAK_B="${leak_bytes:-}" RR_LEAKING="${leak_list:-}" \
  "$PY" - <<'PYEOF'
import json, os, socket
e = os.environ
lines = lambda k: [x for x in e.get(k, "").split("\n") if x]
num = lambda k: int(e[k]) if e.get(k, "").lstrip("-").isdigit() else None
status = e["RR_STATUS"]
end_sha = e.get("RR_END_SHA") or None
rec = {
    "run_id": e["RR_RUN_ID"], "status": status,
    "started_utc": e["RR_STARTED"], "finished_utc": e.get("RR_FINISHED") or None,
    "duration_s": num("RR_DURATION"),
    "git_sha": e["RR_SHA"], "git_sha_at_end": end_sha,
    "tree": e["RR_TREE"], "dirty_paths": num("RR_DIRTY"),
    "scope": e["RR_SCOPE"], "suites": lines("RR_SUITES"),
    "suites_total": len(lines("RR_SUITES")),
    "suites_failing": num("RR_FAILED") if status != "running" else None,
    "failing_suites": lines("RR_FAILING"), "suites_reporting_no_passes": lines("RR_NOPASS"),
    # Counted from each suite's own column-zero markers. OK is what the TOTAL line has always
    # counted; FAIL and SKIP are the same convention's other markers, and a suite that fails
    # by crashing prints neither -- its exit code, in suites_failing, is authoritative.
    "tests_passing": num("RR_TOTAL") if status != "running" else None,
    "tests_failing_reported": num("RR_FAILTESTS") if status != "running" else None,
    "tests_skipped_reported": num("RR_SKIPS") if status != "running" else None,
    "exit_code": num("RR_EXIT"),
    "log": e["RR_LOG"], "record": e["RR_RECORD"],
    "host": socket.gethostname(), "python": e["RR_PY"], "jobs": num("RR_JOBS"),
    "parallel_override": e.get("RR_PARALLEL") == "1",
    "lock": e.get("RR_LOCK") or None, "took_over_stale_lock_of": e.get("RR_TAKEOVER") or None,
    # F-331 / F-342: the durable job identity, the process marker only this run carries, and
    # where it is enrolled (null when no registry was reachable or SUITE_REGISTRY=0).
    "job_id": e["RR_JOB"], "role": "work", "process_marker": e["RR_MARKER"],
    "registry": e.get("RR_ENROLLED") or None,
    # W3-HYG: temp entries suites left in their own TMPDIR (counted, then removed).
    "tmp_leak_entries": num("RR_LEAK_N") if status != "running" else None,
    "tmp_leak_bytes": num("RR_LEAK_B") if status != "running" else None,
    "tmp_leaking_suites": lines("RR_LEAKING"),
    # F-335 / F-341: the producer appends this exact line to the log after the terminal record.
    "terminal_sentinel": (f"EXIT {num('RR_EXIT')}" if status != "running"
                          and num("RR_EXIT") is not None else None),
}
rec["release_eligible"] = bool(
    status == "passed" and rec["scope"] == "full" and rec["tree"] == "clean"
    and rec["git_sha"] not in ("", "UNKNOWN") and end_sha == rec["git_sha"]
    and rec["suites_failing"] == 0)
tmp = e["RR_RECORD"] + ".tmp"
with open(tmp, "w") as f:
    json.dump(rec, f, indent=2, sort_keys=True)
    f.write("\n")
os.replace(tmp, e["RR_RECORD"])
PYEOF
}

# Every suite gets its own TMPDIR, and it is removed when the run ends.
#
# Found 2026-09-20, by a run that failed eleven suites on "No space left on device" with no
# code change behind it: the suites had left 37,284 temporary directories totalling 29 GB in
# /tmp, which is about twelve hundred per run. Sixty-four test files call `tempfile.mkdtemp`,
# which -- unlike `TemporaryDirectory` -- never cleans up, and each of those directories
# holds a SQLite database, sometimes a rendered image.
#
# The fix is here rather than in sixty-four files on purpose. `mkdtemp` honours TMPDIR, so
# pointing it at a per-run directory makes every one of them land in a place this script can
# delete in a single line, whatever any individual test forgets. Fixing the call sites would
# be sixty-four edits that each have to stay correct, and the sixty-fifth would leak again.
#
# The trap covers the interrupt path too, because the runs that get killed half way are
# exactly the ones nobody goes back to tidy up after.
# One cleanup function and one trap, because a second `trap ... EXIT` replaces the first
# rather than adding to it. The first version of this set its own EXIT trap here and the
# `$outdir` trap thirty lines below silently discarded it: the run was green, the containment
# worked, and 342 MB in 399 directories survived anyway. Caught only by counting what was
# left instead of trusting the fix -- the same defect this build keeps naming, in a shell
# script, written while fixing something else.
#
# INT/TERM now only mark the run interrupted and exit; the exit runs the one EXIT trap. (Under
# the old `trap ... EXIT INT TERM`, an interrupt ran the cleanup and then carried on waiting.)
# The cleanup releases the lock only if this run holds it, and a record still marked running
# is rewritten as interrupted, so a killed run never looks like a live one.
# A run killed with SIGKILL (or a host OOM kill) never reaches its trap, so its directory
# would survive. Each run therefore writes its owner (pid + process start time) into the
# directory, and every new run removes the run directories whose owner is provably gone --
# only directories this script made and stamped; an unstamped one is left alone (W3-HYG).
for _stale in "${TMPDIR:-/tmp}"/brambleloop-run-*; do
  [ -f "$_stale/.owner" ] || continue
  read -r _opid _ostart < "$_stale/.owner" 2>/dev/null || continue
  _olive="$( [ -n "${_opid:-}" ] && proc_start "$_opid" || true)"
  if [ -z "$_olive" ] || [ "$_olive" != "${_ostart:-}" ]; then
    echo "TMP: removing the run directory of a dead run ($_stale, pid ${_opid:-?})"
    rm -rf "$_stale"
  fi
done
BRAMBLELOOP_RUN_TMP="$(mktemp -d "${TMPDIR:-/tmp}/brambleloop-run-XXXXXXXX")"
echo "$$ $MY_START" > "$BRAMBLELOOP_RUN_TMP/.owner"
export TMPDIR="$BRAMBLELOOP_RUN_TMP"
RUN_DONE=""
_brambleloop_cleanup() {
  if [ -z "$RUN_DONE" ]; then
    kill $(jobs -p) 2>/dev/null
    write_record interrupted "$(utc)" "$(( $(date +%s) - RUN_STARTED_EPOCH ))" 130 2>/dev/null
    echo "EXIT 130" >> "$LOG_FILE" 2>/dev/null
  fi
  if [ -n "$LOCK_HELD" ] && [ "$(lock_field run_id)" = "$RUN_ID" ]; then rm -f "$LOCK_FILE"; fi
  rm -rf "${outdir:-}" "${BRAMBLELOOP_RUN_TMP:-}"
}
trap _brambleloop_cleanup EXIT
trap 'exit 130' INT TERM

write_record running

header() {
  echo "RUN ID: $RUN_ID"
  echo "RUN STARTED: $RUN_STARTED"
  echo "GIT SHA: $GIT_SHA"
  echo "TREE: $TREE_STATE ($DIRTY_PATHS changed paths)"
  if [ "$SCOPE" = "full" ]; then echo "SCOPE: full (${#SUITES[@]} suites)"
  else echo "SCOPE: filtered (${#SUITES[@]} suites): ${SUITES[*]}"; fi
  [ -n "$TAKEOVER" ] && echo "LOCK: took over the stale lock of run $TAKEOVER"
  [ "$PARALLEL" = "1" ] && echo "LOCK: ALLOW_PARALLEL=1, no concurrency guard"
  echo "RUN RECORD: $RECORD_FILE"
  echo
}
header | tee "$LOG_FILE"

# F-331: enrol this run in the durable job registry as the workload, under its own id.
ENROLLED=""
REGISTRY_CLI="${SUITE_REGISTRY_CLI:-../ops/registry.py}"
if [ "${SUITE_REGISTRY:-1}" != "0" ] && [ -f "$REGISTRY_CLI" ]; then
  if "$PY" "$REGISTRY_CLI" enrol "suite-$RUN_ID" "$PWD/$LOG_FILE" suite \
       "$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo)" "$JOB_MARKER" --role work \
       >/dev/null 2>&1; then
    ENROLLED="suite-$RUN_ID"
    echo "JOB: suite-$RUN_ID enrolled in the job registry (role work)" | tee -a "$LOG_FILE"
  fi
fi
write_record running

# Scheduling order is not the printing order. These six are the ones that take minutes, and
# a suite that takes six minutes and starts last sets the floor for the entire run, so they
# are started first and everything else fills in around them. Measured, in descending cost:
# product_run 342s, shadow 245s, acceptance_gates 183s, chaos 129s, deploy 107s, physical 92s.
SLOW=(
  tests/test_product_run.py tests/test_shadow.py tests/test_acceptance_gates.py
  tests/test_chaos.py tests/test_deploy.py tests/test_physical.py
)

outdir=$(mktemp -d)   # inside the run's own TMPDIR; cleaned by the trap set above

# Per-suite TMPDIR and a leak census (W3-HYG, 2026-10-06). The run-level directory above stops
# leaks accumulating ACROSS runs; this makes them visible WITHIN one. Each suite gets its own
# directory under the run's, and when the suite exits whatever it left there is counted
# (entries, bytes) into $outdir/<suite>.leak and removed straight away, so one leaky suite
# cannot fill the disk for the rest of a twenty-minute run either. The count is printed per
# suite and in total, and written to the run record; TMP_LEAK_STRICT=1 makes a leaking suite
# a failing one. Test files clean up after themselves through tests/_tmp.py, so a non-zero
# count here is a regression -- tests/test_w3_tmp_hygiene.py fails on the known ones.
schedule() {
  local t="$1" safe
  safe="${t//\//_}"
  (
    st="$BRAMBLELOOP_RUN_TMP/suite-$safe"
    mkdir -p "$st"
    TMPDIR="$st" "$PY" "$t" >"$outdir/$safe.out" 2>&1; echo $? >"$outdir/$safe.code"
    n=$(find "$st" -mindepth 1 -maxdepth 1 2>/dev/null | wc -l)
    b=$(find "$st" -mindepth 1 -type f -printf '%s\n' 2>/dev/null | awk '{s+=$1} END {print s+0}')
    echo "$n $b" >"$outdir/$safe.leak"
    rm -rf "$st"
  ) &
}

order=()
for s in "${SLOW[@]}"; do
  for t in "${SUITES[@]}"; do [ "$t" = "$s" ] && order+=("$t") && break; done
done
for t in "${SUITES[@]}"; do
  skip=""
  for s in "${SLOW[@]}"; do [ "$t" = "$s" ] && skip=1 && break; done
  [ -z "$skip" ] && order+=("$t")
done

for t in "${order[@]}"; do
  # `wait -n` returns as soon as any one child finishes, which keeps every core busy instead
  # of draining a whole batch before starting the next.
  while [ "$(jobs -rp | wc -l)" -ge "$JOBS" ]; do wait -n; done
  schedule "$t"
done
wait

total=0; failed=0; fail_tests=0; skip_tests=0; failing_list=""; nopass_list=""
leak_entries=0; leak_bytes=0; leak_list=""
{
for t in "${SUITES[@]}"; do
  safe="${t//\//_}"
  echo "== $t"
  if [ -f "$outdir/$safe.out" ]; then
    sed 's/^/   /' "$outdir/$safe.out"
  else
    echo "   NO OUTPUT: this suite never ran"
    failed=$((failed+1)); failing_list+="$t"$'\n'
    continue
  fi
  n=$(grep -c '^OK' "$outdir/$safe.out" || true)
  total=$((total+n))
  fail_tests=$((fail_tests + $(grep -c '^FAIL' "$outdir/$safe.out" || true)))
  skip_tests=$((skip_tests + $(grep -c '^SKIP' "$outdir/$safe.out" || true)))
  code=$(cat "$outdir/$safe.code" 2>/dev/null || echo 1)
  [ "$code" -ne 0 ] && failed=$((failed+1)) && failing_list+="$t"$'\n'
  # A suite that exits clean and reports no passes is not a passing suite; it is a suite
  # whose results are not reaching this total. Nine files printing a lowercase marker were
  # counted as zero here for a whole session -- exit codes still caught their failures, so
  # nothing was broken and the headline number was quietly wrong, which is the harder fault
  # to notice. Counted as a failure so the log says so on the line somebody reads.
  # W3-HYG: what the suite left in its own TMPDIR (already removed by schedule()).
  read -r ln lb < "$outdir/$safe.leak" 2>/dev/null || { ln=0; lb=0; }
  if [ "${ln:-0}" -gt 0 ]; then
    echo "   TMP LEAK: $ln entries, $lb bytes left in this suite's TMPDIR (removed by the harness)"
    leak_entries=$((leak_entries+ln)); leak_bytes=$((leak_bytes+lb)); leak_list+="$t"$'\n'
    if [ "${TMP_LEAK_STRICT:-0}" = "1" ] && [ "$code" -eq 0 ]; then
      echo "   TMP_LEAK_STRICT=1: a suite that leaks temporary files is a failing suite"
      failed=$((failed+1)); failing_list+="$t"$'\n'
    fi
  fi
  if [ "$code" -eq 0 ] && [ "$n" -eq 0 ]; then
    echo "   SUITE REPORTED NO PASSES: its results are not reaching the total"
    failed=$((failed+1)); failing_list+="$t"$'\n'; nopass_list+="$t"$'\n'
  fi
done
} > "$outdir/report"

END_SHA="$(git rev-parse HEAD 2>/dev/null || echo UNKNOWN)"
RUN_FINISHED="$(utc)"
DURATION=$(( $(date +%s) - RUN_STARTED_EPOCH ))
if [ "$failed" -eq 0 ]; then status=passed; else status=failed; fi
{
  cat "$outdir/report"
  echo
  echo "TOTAL PASSING: $total ; suites failing: $failed"
  echo "TMP LEAKED: $leak_entries entries, $leak_bytes bytes across $(printf '%s' "$leak_list" | grep -c . || true) suites (removed; TMPDIR was $BRAMBLELOOP_RUN_TMP)"
  echo "RUN FINISHED: $RUN_FINISHED"
  echo "DURATION: ${DURATION}s"
  echo "GIT SHA: $GIT_SHA (tree $TREE_STATE at start)"
  [ "$END_SHA" != "$GIT_SHA" ] && echo "WARNING: HEAD moved to $END_SHA during the run; not release-eligible"
  echo "RUN RECORD: $RECORD_FILE ($status)"
} | tee -a "$LOG_FILE"
write_record "$status" "$RUN_FINISHED" "$DURATION" "$failed"
RUN_DONE=1
# F-335: the terminal sentinel, last line of the job's own evidence, after the record.
echo "EXIT $failed" >> "$LOG_FILE"

if [ "$SCOPE" = "filtered" ] && [ "${THEN_FULL:-0}" = "1" ]; then
  if [ "$failed" -ne 0 ]; then
    echo "THEN_FULL: targeted suites failed; the full suite was not started (F-347)."
  else
    echo "THEN_FULL: targeted suites passed; starting the full suite."
    _brambleloop_cleanup; trap - EXIT
    SUITES="" THEN_FULL=0 bash "$PWD/run_tests.sh"
    exit $?
  fi
fi
exit "$failed"
