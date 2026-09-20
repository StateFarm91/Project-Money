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
SUITES=(
  tests/test_compiler.py tests/test_reverse.py tests/test_rowcycle.py
  tests/test_geometry.py tests/test_division.py tests/test_substitution.py tests/test_prototype.py tests/test_value_stack.py tests/test_twin.py tests/test_grading.py
  tests/test_platform.py tests/test_gates.py tests/test_proof.py tests/test_radar.py tests/test_arbitrage.py tests/test_provenance.py tests/test_gateway.py tests/test_model_provider.py
  tests/test_intel.py tests/test_learning.py tests/test_complaints.py tests/test_deliverable.py tests/test_response.py tests/test_mission.py tests/test_pods_routing.py tests/test_teardown.py tests/test_teardown_audits.py tests/test_culture.py tests/test_cast.py tests/test_creative.py tests/test_blinded.py tests/test_prospecting.py tests/test_invention.py tests/test_seasonal_transform.py tests/test_breakthrough.py tests/test_universe.py tests/test_family.py tests/test_funnel.py tests/test_certification.py tests/test_improve.py tests/test_league.py tests/test_league_holdout.py tests/test_roles.py tests/test_freshness.py tests/test_upgrades.py tests/test_nightly.py tests/test_weekly.py tests/test_roi.py tests/test_tiers.py tests/test_profiles.py tests/test_growth.py tests/test_owned.py tests/test_swarm.py tests/test_visual.py tests/test_layout_qa.py tests/test_eligibility.py
  tests/test_etsy.py tests/test_brand.py tests/test_takeover.py tests/test_moat.py tests/test_commerce.py tests/test_intent.py tests/test_portfolio.py tests/test_preproduction.py tests/test_lanes.py tests/test_creators.py tests/test_listing_tests.py tests/test_benchmarks.py tests/test_offers.py tests/test_free_to_paid.py tests/test_replication.py tests/test_allocation.py tests/test_trajectory.py tests/test_artefacts.py tests/test_health.py tests/test_governor.py tests/test_ladder.py tests/test_clusters.py tests/test_pins.py tests/test_video.py tests/test_tools.py tests/test_reviews.py tests/test_first_hundred.py tests/test_personalisation.py tests/test_club.py tests/test_rebuild_graph.py tests/test_friction.py tests/test_interviews.py tests/test_departments.py
  tests/test_buyer_trust.py tests/test_trust.py tests/test_quality.py tests/test_physical.py tests/test_finance.py tests/test_currency.py tests/test_commercial_truth.py tests/test_promotion.py
  tests/test_leadtime.py tests/test_uncertainty.py tests/test_depth.py tests/test_compression.py tests/test_seasonal_cycle.py tests/test_colour.py tests/test_benchmark_matrix.py tests/test_collections.py tests/test_teams.py tests/test_fastlane.py tests/test_rollforward.py tests/test_remerchandising.py tests/test_model_access.py tests/test_etsy_capability.py tests/test_scale.py tests/test_discipline.py tests/test_dependency.py tests/test_runrate.py tests/test_calibration.py
  tests/test_launch.py tests/test_access.py tests/test_platform_policy.py
  tests/test_shadow.py
  tests/test_persistence.py tests/test_continuity.py tests/test_chaos.py tests/test_deploy.py
  tests/test_product_run.py tests/test_products.py tests/test_texture.py
  tests/test_accessibility.py tests/test_build2.py tests/test_executor.py tests/test_acceptance_gates.py
)

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
