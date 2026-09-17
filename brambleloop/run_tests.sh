#!/usr/bin/env bash
# Full Brambleloop acceptance suite. Run from the brambleloop/ directory.
set -u
PY="${PY:-.venv/bin/python}"
total=0; failed=0
for t in tests/test_compiler.py tests/test_reverse.py tests/test_twin.py \
         tests/test_platform.py tests/test_gates.py tests/test_radar.py tests/test_shadow.py \
         tests/test_persistence.py tests/test_chaos.py tests/test_deploy.py; do
  echo "== $t"
  out=$($PY "$t" 2>&1); code=$?
  echo "$out" | sed 's/^/   /'
  n=$(echo "$out" | grep -c '^OK' || true)
  total=$((total+n))
  [ $code -ne 0 ] && failed=$((failed+1))
done
echo
echo "TOTAL PASSING: $total ; suites failing: $failed"
exit $failed
