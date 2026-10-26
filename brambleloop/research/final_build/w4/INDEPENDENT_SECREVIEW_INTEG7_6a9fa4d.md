# Independent review: INTEG7 fixes, `6792094..6a9fa4dc` (branch `claude/w4-INTEG7`)

Reviewed: 2026-10-26 (UTC). Reviewer: an independent Claude Code session that did not write this code.
This is a review only. Nothing was fixed, no production endpoint was called, nothing was deployed
and no secret was read.

## Verdict

| Question | Answer |
|---|---|
| **Ship?** | **YES.** No blocking finding. Two LOW notes and a few INFO notes follow; none needs to be fixed before ship. |
| Any assertion weakened, removed or made vacuous? | **No.** No assertion was removed or made vacuous. One assertion was *re-scoped* (`test_w4_fm_provider_table`, F1): it is still non-vacuous, and the end-to-end path is still exercised, but no assertion pins that path's reason any more. |
| Bulk change (item 1) touches print strings only? | **Yes.** 74 files, 74 lines out, 74 lines in, every one a `print(...)` in the `__main__` runner. `run_tests.sh` is untouched. |
| Production code changed beyond `fallback_contract.py`? | **No.** Outside `tests/`, the range changes only `gateway/fallback_contract.py` and `release/DEPLOYED_HISTORY.json` (data). |
| `fallback_contract.CAPABILITIES` keeps the same content? | **Yes.** It is equal to the old literal by value and by key order (checked with `ast.literal_eval` of the old source against the imported new module). |
| Do the six fixes address real causes? | **Yes, all six.** Five of the original failures were reproduced on `6792094`; the sixth (`test_persistence`) was shown to be a real, legitimate window change, not a bug. |
| `test_persistence`: straddled window, or a duplicate-enqueue bug? | **Straddled window. There is no duplicate-enqueue bug.** Windows are epoch-aligned (`int(now // period)`), and a same-window repeat is refused by the idempotency key. |
| `test_w4_swarmcontrol`: host disk, or F-490 logic? | **Host disk.** `resources.read` never touches F-490 (`swarm/backpressure.py`). The old test fails exactly on its two `saturated is False` assertions when disk is faked at 1.9% free. |
| Touched suites pass? | See the "Suites run" section. |

## Method

- Venv built from `brambleloop/requirements.lock` + `requirements-test.lock` (Python 3.13), in the
  session scratchpad.
- The suites were run at `nice -n 19`, one at a time, with `PYTHONPATH=src:tests`, as `run_tests.sh` runs them.
  Counts use the same rules as `run_tests.sh`: `^OK` for passes, and `^FAIL([[:space:]:]|$)` for failures.
- To reproduce the original failures, a detached worktree of `6792094` was run against the same venv.

## Findings

### F1 (LOW, test strength): `test_w4_fm_provider_table` no longer pins the provider-table reason end to end

The old assertion said that the real analysis's *first-found* reason for
`dashboard.drill` names the provider table. FMBATCH1 added `GET /api/finance/owner`, which reaches
`summary -> _summary -> drill`, so drill's first-found reason is now that API path. I reproduced the
old failure on `6792094`:
`AssertionError('API get api_finance_owner -> app/main.py:_finance_owner_view -> ... dashboard.py:_summary')`.
The cause is real, and it is not a regression: drill is still live, now for an additional reason.

The replacement is not vacuous:
- It asserts that drill is live.
- It pops drill's mark, then asserts that the real `providers.py` literally contains the pair `(DASH, "drill")`.
- It runs `_provider_pairs` with those literal tuples and asserts that drill is marked again "(provider table)".

If the rule broke, `a.live.get(...)` would return `""` and the assertion would fail.

What it gives up: it proves the rule *in isolation*, using tuples the test collected itself.
It no longer proves that the real walk reaches the table and applies the rule. That walk still
happens today. In the real analysis, `seo/status.summary` and
`learn/improvement_status.summary` are live *only* via `... providers.py:module constant (provider table)`.
But the test asserts only `reached` for them, not the reason. The test also dropped the
`"providers.py" in why` check.

**Suggestion (non-blocking):** add `assert "provider table" in R.analysis().live[("brambleloop.seo.status", "summary")]`.
That restores an end-to-end pin on a row that no other path reaches.

### F2 (LOW, test hygiene): `test_w4_fm_provider_table` mutates the process-cached analysis

`R.analysis()` is cached per source snapshot. The test pops `a.live[(DASH, "drill")]` and restores it in
`finally`, so `live` ends up as it was. However, `_mark` also appends `(DASH, "drill", "full", ...)` to
`a._queue`. `_queue` is drained only inside `_run()` during construction, so the entry stays inert and
is never visited. `test_modules_behind_the_table_are_reached` runs later in the same process and passes.
Today this has no effect. If a future change drains `_queue` lazily, the entry would be re-visited
(harmless, since drill is already live). No action is needed.

### F3 (INFO): `test_cert_intel_wave` fixture

The cause is real. W-AGENTS E-12 (`intel/mission_runtime.py:1144`) skips photography for any slug where
`for_slug(slug) is None`. `striped-cardigan` is not in `builder.CATALOGUE`, so the old fixture produced no job. I reproduced
this on `6792094`: `assert [j.inputs["slug"] for j in jobs] == ["striped-cardigan"]` fails.

The fix gives `striped-cardigan` a stand-in CIR and adds `retired-cardigan` with no CIR. The
existing, unchanged assertion `jobs == ["striped-cardigan"]` now also proves that the no-CIR slug is
skipped, so coverage *increased*. The CATALOGUE entry is popped in `finally`, and neither slug is in
CATALOGUE beforehand, so the pop cannot remove a real entry.

One nit: the CATALOGUE assignment happens before `_db()`, outside the `try`. If `_db()` raised, the
stand-in would leak for the rest of that process, which is harmless in a single-suite process.

### F4 (INFO): `test_persistence`: the straddle explanation is correct, and there is no duplicate-enqueue bug

`Scheduler.tick` keys every cadence `cadence:{name}:{int(now.timestamp() // period)}` and catches
`DuplicateJob`. `idle_wake` keys `autonomy.orchestrate:idle:{int(now // 300)}` and receives the same `now`.
The shortest cadence is 300 s (`laura_executive`), followed by four 900 s cadences.

On current code, against a fresh SQLite database, with the first tick 0.5 s before a 900 s boundary:
- First tick: 126 enqueued.
- A restarted scheduler at the **same instant**: `[]`.
- A restarted scheduler **1 s later**: `['infra_heartbeat', 'health_sweep', 'executive_orchestrator', 'laura_executive', 'slo_check']`.

Those five cadences are correctly opening new windows. So the wall-clock version of the test was
time-dependent: it failed whenever the two ticks spanned a boundary, and that gets more likely under
load. Pinning one `now` tests the actual claim ("same window, no re-enqueue"). Both
assertions are unchanged (`again == []` and `total == len(first)`). The only thing lost is coverage of
`tick()`'s default `now=None` path, which is trivial.

### F5 (INFO): `test_w4_swarmcontrol`: host disk, not F-490

`resources.read` adds `storage {name}` to `hot` when a working filesystem has less than 2% or less than
2 GB free (F-470, FMBATCH1). The old test passed `storage_paths=None`, so it read the real `tempfile.gettempdir()`
and `artifacts`. On a host with 2% free, three of its `saturated is False` checks would fail.

Reproduced: I ran the `6792094` test with `shutil.disk_usage` faked at 1.9 GB free out of 100 GB. It failed with
`FAIL test_memory_or_cpu_pressure_saturates_and_host_load_never_does host-wide load must not scale the pool down`
and `FAIL test_unreadable_resources_are_unknown_not_healthy` (6 passed, 2 failed). The new test passes under the same fake (8/8).

F-490 (`swarm/backpressure.py`, `orchestrate.py:1687`) is not on this code path.

`storage_paths={}` means "no paths", not "default paths" (`paths if paths is not None`). Every
assertion is unchanged. Storage saturation is still covered by
`test_w4_fmbatch1_swarm.test_f470_storage_and_io_pressure_saturate_and_absent_paths_are_unknown`, which passes (4/4).

### F6 (INFO): `fallback_contract.py` (cherry-pick 8111ce1d / local 9860763)

- Content is equal by value and key order: three models, all `vision=True`, 200k context, provider `anthropic`.
- There is no import cycle. `routing` does not import `fallback_contract`; the import is local to `_capabilities()`.
- `CAPABILITIES` is a snapshot taken at import time. Nothing in `src/` or `tests/` mutates `routing.TIERS` after import.
- Fixes `test_visual_inspection.test_no_module_names_a_model_string_outside_the_routing_table`. I reproduced
  this on `6792094`, where lines 36, 38 and 40 named model strings. It now passes (24/24). `test_w4_fmbatch1_providers`
  passes (7/7).
- Future-proofing notes, with no effect today:
  - `provider` is hard-coded to `"anthropic"` and `context_tokens` to 200k for every tier, exactly as before.
    A future non-Anthropic tier would be mislabelled rather than becoming UNKNOWN.
  - Two tiers on one model would collapse into one key.

### F7 (INFO): bulk `ok` → `OK` (item 1)

- 74 files and 74 line pairs. All of them are in the `if __name__ == "__main__":` runner:
  - 73 are `print("ok", n)` → `print("OK  ", n)  # run_tests.sh counts lines beginning OK`. This prints
    `OK   name`, because `print` adds a space separator.
  - 1 is `test_w4_fmbatch2_research_docs_absent.py`: `print("ok")` → `print("OK   test_absent_repository_documents_are_reported_unavailable")`, which names its single test.
- No runner block contains an `except`, so a failing test still raises and exits non-zero before its `OK` line.
- Counting effect: these suites' passes were previously invisible to `run_tests.sh` ("SUITE REPORTED NO PASSES").
  Now they count. That is a reporting fix and does not change pass or fail behaviour.

### F8 (INFO): credential-shaped string (item 3)

`SECRET = "sk-" + "ant-api03-" + "ABCDEF...012345"` has the same runtime value as before, so every
provider_health assertion that checks redaction of `SECRET` is unchanged. This is the established pattern.
I reproduced the old `test_secret_scan` failure on `6792094`
(`tests/test_w4_fmbatch1_provider_health.py:20 anthropic_key`). Both suites now pass: secret_scan 7/7 and
provider_health 8/8. The value is a fake test fixture, not a real key.

### F9 (INFO): DEPLOYED_HISTORY records b2e49455

- The JSON parses.
- `b2e49455` exists and is an ancestor of `6a9fa4d`. It descends from the suite SHA `4ff953da` (W4-SECPATCH), and
  `git diff 4ff953da b2e49455` touches only release records and suite logs, with no `src/` or `ops/` change.
  So the deployed code is the tree that the cited suite (`20261026T172357Z-3395`) tested.
- I did not and could not verify the production observation itself (no production calls). The entry
  says so honestly ("as reported by the operator session"), and it records the 11/12 readback with its
  known failing item.

## Suites run

All on `6a9fa4d`, one at a time, at `nice -n 19`:

- **Every test file the range touches: 78 suites, all exit 0, 282 `OK` lines, 0 `FAIL` lines.** Every suite
  reports at least one `OK`, so none would be listed as "SUITE REPORTED NO PASSES".
- Of those, the six named in items 2–7: `test_w4_fm_provider_table` 4/4, `test_w4_swarmcontrol` 8/8,
  `test_persistence` 11/11, `test_cert_intel_wave` 9/9, `test_w4_fmbatch1_provider_health` 8/8.
- Untouched suites that cover the changes: `test_secret_scan` 7/7, `test_visual_inspection` 24/24,
  `test_w4_fmbatch1_providers` 7/7, `test_w4_fmbatch1_swarm` 4/4.
- Reproduced on `6792094` (before the fixes): `test_w4_fm_provider_table`, `test_cert_intel_wave`,
  `test_visual_inspection` and `test_secret_scan` fail as described above. `test_w4_swarmcontrol` passes on this
  host (30 GB free) and fails with disk faked at 1.9% free.

This review did not run the full `run_tests.sh` suite. The integrator's full-suite run on this head is
still the release gate.
