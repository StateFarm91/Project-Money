# handoff — W4-CHAIN (difficult debugging: claude-independence chain stall)

Branch: `claude/w4-CHAIN` (from origin/claude/visual-investigation 3f6cc75).

## Symptom
`tests/test_cert_claude_independence.py::test_production_start_command_runs_kills_and_resumes_without_this_session`
failed with "the chain never reached the publish gate: stalled for 240s at [('ads.adjust', PENDING) ...".

## Root cause (measured, not inferred)
Bounded repro (uvicorn start command, job table sampled every 2 s, faulthandler dump):
`ops.maturity_disagreements` held the single embedded worker for 293.9 s at boot. No job
status changed for that whole window, so the test's 240 s stall detector fired with
`ads.adjust` still PENDING behind it.

cProfile of `build2.maturity.disagreements`: 399 of 608 s inside `_Analysis.__init__` went to
`reachability._Analysis._provider_pairs` → `reachability._dynamic_importer`. That function
ran 11,116 times without a cache, and every call re-walked a whole module AST (49M generator
steps). Introduced by 9e9cf0d (W4-FM WIP checkpoint, merged via c525244), at
`src/brambleloop/build2/reachability.py` `_dynamic_importer` / `_provider_pairs`.

## Fix
`_dynamic_importer` is now cached per graph snapshot (`_dynamic_importer_cached`, lru_cache
keyed on the snapshot, the same pattern as `_imports_cached`). It is cleared by
`clear_cache()` and `_dynamic_importer.cache_clear`.

Evidence: same DB, unprofiled `disagreements()`:
- unfixed HEAD: 191 s (294 s inside the loaded test run)
- fixed: 82 s
- cc4a129: 79.5 s

The result is byte-identical before and after the fix (sha256 prefix e6e537e1, count 180).

## Next
None for this lane. A possible follow-up (AUTO-owned, not done here): long read-only analysis
cadences share one embedded worker with the release chain.
