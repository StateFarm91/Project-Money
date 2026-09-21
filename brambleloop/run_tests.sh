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
set -u
cd "$(dirname "${BASH_SOURCE[0]}")"
PY="${PY:-.venv/bin/python}"
JOBS="${JOBS:-$(nproc 2>/dev/null || echo 4)}"

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
BRAMBLELOOP_RUN_TMP="$(mktemp -d "${TMPDIR:-/tmp}/brambleloop-run-XXXXXXXX")"
export TMPDIR="$BRAMBLELOOP_RUN_TMP"
_brambleloop_cleanup() { rm -rf "${outdir:-}" "${BRAMBLELOOP_RUN_TMP:-}"; }
trap _brambleloop_cleanup EXIT INT TERM

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
SUITES=()
while IFS= read -r f; do SUITES+=("$f"); done < <(ls tests/test_*.py | sort)
if [ "${#SUITES[@]}" -lt 100 ]; then
  echo "only ${#SUITES[@]} suites found; the discovery is not working" >&2
  exit 1
fi

# Scheduling order is not the printing order. These six are the ones that take minutes, and
# a suite that takes six minutes and starts last sets the floor for the entire run, so they
# are started first and everything else fills in around them. Measured, in descending cost:
# product_run 342s, shadow 245s, acceptance_gates 183s, chaos 129s, deploy 107s, physical 92s.
SLOW=(
  tests/test_product_run.py tests/test_shadow.py tests/test_acceptance_gates.py
  tests/test_chaos.py tests/test_deploy.py tests/test_physical.py
)

outdir=$(mktemp -d)   # inside the run's own TMPDIR; cleaned by the trap set above

schedule() {
  local t="$1" safe
  safe="${t//\//_}"
  ( "$PY" "$t" >"$outdir/$safe.out" 2>&1; echo $? >"$outdir/$safe.code" ) &
}

order=("${SLOW[@]}")
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

total=0; failed=0
for t in "${SUITES[@]}"; do
  safe="${t//\//_}"
  echo "== $t"
  if [ -f "$outdir/$safe.out" ]; then
    sed 's/^/   /' "$outdir/$safe.out"
  else
    echo "   NO OUTPUT: this suite never ran"
    failed=$((failed+1))
    continue
  fi
  n=$(grep -c '^OK' "$outdir/$safe.out" || true)
  total=$((total+n))
  code=$(cat "$outdir/$safe.code" 2>/dev/null || echo 1)
  [ "$code" -ne 0 ] && failed=$((failed+1))
  # A suite that exits clean and reports no passes is not a passing suite; it is a suite
  # whose results are not reaching this total. Nine files printing a lowercase marker were
  # counted as zero here for a whole session -- exit codes still caught their failures, so
  # nothing was broken and the headline number was quietly wrong, which is the harder fault
  # to notice. Counted as a failure so the log says so on the line somebody reads.
  if [ "$code" -eq 0 ] && [ "$n" -eq 0 ]; then
    echo "   SUITE REPORTED NO PASSES: its results are not reaching the total"
    failed=$((failed+1))
  fi
done

echo
echo "TOTAL PASSING: $total ; suites failing: $failed"
exit "$failed"
