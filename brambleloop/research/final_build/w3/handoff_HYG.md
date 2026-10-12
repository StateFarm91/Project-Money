# W3-HYG handoff — test temp-directory hygiene

Branch `claude/w3-HYG` (base `claude/visual-investigation` @ e7b207c). 2026-10-06 UTC.

## Defect

/tmp held ≈16.7 GB in >7,000 entries (≈900 new per hour while suites ran), filled the disk and
invalidated a test run. `run_tests.sh` already used a per-run TMPDIR, but lane workers run test
files directly (`PYTHONPATH=src python tests/test_x.py`), which bypasses it entirely; and a
SIGKILLed harness run never reached its trap.

## Creators found → fix

AST/grep over `tests/`, `src/`, `scripts/`, `ops/`, `research/` for `mkdtemp(`, `mkstemp(`,
`gettempdir(`, `NamedTemporaryFile(..., delete=False)`:

| family seen in /tmp | creator | fix |
|---|---|---|
| oauth-store-, export- | tests/test_etsy_oauth_callback.py, test_continuity.py | sandbox install |
| v11a-, v11a-kpi-, v11a-tl-, v11a-night- | test_v11_autonomy_{orchestrator,kpis,timeline,overnight}.py | sandbox install |
| r2auto-, r2-m3- | tests/r2_autonomy_harness.py, test_r2_autonomy_soak_effects.py | sandbox install (helper too) |
| v11wire-, v11wire-exp- | test_v11_wiring.py | sandbox install |
| w3d-ex/id/co/wire/cont/det/log- | test_w3_laura_core_{executive,identity,constitution,wiring,continuity}.py | sandbox install |
| contops- | test_continuous_operations.py | sandbox install |
| cert-assets- | test_cert_commerce.py, test_cert_identity.py | sandbox install |
| waiter-, relwait-, relled- | test_waiter.py, test_reliability_ledger.py | sandbox install |
| deployguard(-copy)-, deploypath- | test_deploy_guard.py, test_deploy_path.py | sandbox install |
| w3spend(-kill)- | test_w3_spend_paid_calls.py | sandbox install |
| refs-, refs-hash-, licence-, libuse-, fp- | test_originality.py, test_specification.py | sandbox install |
| cert_design_, cert_wave_improve_, cert_wiring_, w6_ | test_cert_design_pipeline / improve_wave / wiring / growth_seasonal | sandbox install |
| v11ads_, fb4_, fb4ops_, fb1b_, bands_, customer_auth_ | test_v11_ads_readiness, test_{storefront_fb4,ranking_readiness,search_visibility,fb4_lc,fb4_ops}, test_etsy_readback_observe, test_protected_bands, test_customer_data_auth | sandbox install |
| disclosed_runtime_, disclosed_upload_ | test_disclosed_render_runtime.py, test_disclosed_certified_upload.py | sandbox install |
| generic tmpXXXXXXXX holding only uv.sqlite | test_cert_unique_value.py (bare `mkdtemp()`) | sandbox install |
| stray tmpXXXX.png/.json | test_model_photography.py, test_model_freeze.py, test_build2.py (`NamedTemporaryFile(delete=False)`) | sandbox install |
| shadow_rehearsal_ | scripts/shadow_rehearsal.py (evidence claimed "discarded after the run"; it was not) | try/finally rmtree |
| (unprefixed) | scripts/shadow_dossier.py, ops/test_caps.py | atexit rmtree (prefixes shadow_dossier_, opscaps-) |
| J_fin_ | research/final_build/audit_ddf9c6e/_h.py | atexit rmtree |
| cc_proof_, acct_proof_ | already fixed upstream in ddf9c6e (historical leftovers) | none needed |
| w3k11- | tests/test_w3_k11_authority.py on **claude/w3-K11 (not in this base)** | the static guard will fail on merge until that file gets the one-line install — intended |

**Shared helper:** `tests/_tmp.py`. `import _tmp; _tmp.install()` (one line, inserted after the
docstring/`__future__` of **220 test files**) creates `<TMPDIR>/bl-test-<file>-XXXX`, points
`tempfile.tempdir` and `TMPDIR` at it (so src code and subprocesses land there too) and removes it
on normal exit, uncaught exception, `sys.exit`, SIGTERM and SIGINT; only the creating pid removes
it (fork-safe). SIGKILL/`os._exit` cannot be handled in-process — covered by the harness.
`_tmp.scoped(prefix)` is a block-scoped TemporaryDirectory for new code. No assertion was changed.

**Harness (`run_tests.sh`, the real one; there is no scripts/run_tests.sh):** per-run TMPDIR + trap
already existed; added (1) per-suite TMPDIR under it, counted after each suite and removed at once:
`TMP LEAK: n entries, b bytes` per suite, `TMP LEAKED: …` per run, record fields
`tmp_leak_entries/tmp_leak_bytes/tmp_leaking_suites`; `TMP_LEAK_STRICT=1` turns a leaking suite into
a failing one; (2) each run stamps `.owner` (pid + start time) in its run dir and every new run removes
run dirs whose owner is provably dead (SIGKILL case); unstamped dirs are left alone.

**ops/health.py TEMP_PREFIXES:** added `bl-laura-proof-` (used in src/laura/executive/proof.py and
not counted — test_cost_governance_wave2 was failing on it). `bl-test-` is test-only and is pinned so that
it neither shadows nor is shadowed by any production prefix; `brambleloop-run-` pinned present.

## Tests

`tests/test_w3_tmp_hygiene.py` — **16 OK, 0 FAIL**, and leaves its own TMPDIR empty:
(a) a child using every temp API + a grandchild exits clean → empty; 4 formerly-leaking test files
(test_waiter, test_deploy_path, test_cert_unique_value, test_protected_bands — before: 10/2/6/5
entries) run for real → TMPDIR empty; (b) raise mid-way, `sys.exit(1)`, SIGTERM, SIGINT → empty;
fork child does not delete parent sandbox; `scoped` removes on raise; (c) harness in a throwaway repo:
leaking passing + leaking failing suites reported (2+2 entries, 202 bytes) and run TMPDIR empty after a
failing run; strict mode fails a leaking suite; SIGTERM'd run leaves nothing; SIGKILLed run's dir is
swept by the next run; (d) static guard: every tests/*.py that creates temp files must install the
sandbox before its first temp call; every creator in src/, scripts/, ops/ must have
rmtree/atexit/unlink/TemporaryDirectory in its function (allow-list `ALLOWED` is empty); guard
self-test; TEMP_PREFIXES consistency.

Other suites run (each with a private TMPDIR, leftover entries in brackets):
test_vacuity 7 OK [0], test_secret_scan 7 OK [0], test_reachability 11 OK [0],
test_run_tests_script 10 OK [0], test_rehearsal_stall 4 OK [0], test_spend_governance 36 OK [0],
ops/test_caps.py 4 OK [0], test_cost_governance_wave2 35 OK / **4 FAIL [0]** — the 4 are
pre-existing on the base (`retention.KNOWN_READ_ACTIONS` lacks launch.assessed/held/planned,
ops.rollback_baseline, ops.sentinel); not this lane's files. The same pre-existing retention refusal
is why test_etsy_oauth_callback and test_v11_autonomy_timeline exit 1 both before and after.

## Measured leak, before vs after (22 formerly-leaking files, one run each, TMPDIR = private dir)

| test file | before: entries | before: bytes | after: entries | OK lines before → after | exit before → after |
|---|---:|---:|---:|---|---|
| test_cert_identity | 6 | 7111602 | 0 | 19 → 19 | 0 → 0 |
| test_cert_unique_value | 6 | 14024704 | 0 | 6 → 6 | 0 → 0 |
| test_continuous_operations | 6 | 13971456 | 0 | 5 → 5 | 0 → 0 |
| test_customer_data_auth | 1 | 2330624 | 0 | 9 → 9 | 0 → 0 |
| test_deploy_guard | 8 | 176832 | 0 | 7 → 7 | 0 → 0 |
| test_deploy_path | 2 | 233486 | 0 | 9 → 9 | 0 → 0 |
| test_disclosed_certified_upload | 3 | 8905960 | 0 | 7 → 7 | 0 → 0 |
| test_etsy_oauth_callback | 22 | 48632081 | 0 | 39 → 39 | 1 → 1 |
| test_etsy_readback_observe | 1 | 78538405 | 0 | 37 → 37 | 0 → 0 |
| test_fb4_ops | 1 | 23416832 | 0 | 12 → 12 | 0 → 0 |
| test_originality | 5 | 3395986 | 0 | 28 → 28 | 0 → 0 |
| test_protected_bands | 5 | 11620352 | 0 | 6 → 6 | 0 → 0 |
| test_reliability_ledger | 7 | 6283 | 0 | 7 → 7 | 0 → 0 |
| test_v11_ads_readiness | 10 | 23142400 | 0 | 11 → 11 | 0 → 0 |
| test_v11_autonomy_kpis | 6 | 13967360 | 0 | 7 → 7 | 0 → 0 |
| test_v11_autonomy_overnight | 1 | 3096576 | 0 | 1 → 1 | 0 → 0 |
| test_v11_autonomy_timeline | 5 | 10035200 | 0 | 5 → 5 | 1 → 1 |
| test_v11_wiring | 8 | 16454490 | 0 | 14 → 14 | 0 → 0 |
| test_w3_laura_core_executive | 7 | 17084416 | 0 | 7 → 7 | 0 → 0 |
| test_w3_laura_core_identity | 9 | 18673693 | 0 | 11 → 11 | 0 → 0 |
| test_w3_spend_paid_calls | 10 | 21102469 | 0 | 8 → 8 | 0 → 0 |
| test_waiter | 10 | 10377 | 0 | 11 → 11 | 0 → 0 |
| **total (22 files)** | **139** | **335,931,584** | **0** | | |

Before = base e7b207c; after = this branch. OK-line counts and exit codes are identical, so nothing
was weakened. Not run: the full suite (lane rule), test_shadow_rehearsal (heavy; the script change
is a try/finally around the unchanged body).

## Notes / gaps

- SIGKILL of a directly-run test file (no harness) still leaves its `bl-test-*` sandbox; only the
  harness sweep covers SIGKILL. Leftovers are attributable by the `bl-test-<file>-` prefix.
- The existing /tmp backlog was not touched (other lanes' runs are live); it can be removed once no
  suite is running.
- WIRING: none. On merging claude/w3-K11, add the install line to tests/test_w3_k11_authority.py.
