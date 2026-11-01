# Independent security and integrity review: PHYSFIX-PHOTO at c99dde99 (delta 10)

- **Subject:** `claude/w4-PHYSFIX-PHOTO` at `c99dde99`, which includes `claude/w4-PHYSFIX` at `22c7438e`.
- **Delta:** `git diff b8d3dee0..c99dde99`. It has one non-merge commit, `22c7438` (R35–R39). It touches `runtime/release.py`, `products/texture.py`, `tests/test_physfix.py` and `PHYSFIX.md`.
- **Prior review:** `INDEPENDENT_SECREVIEW_PHYSFIX_b8d3dee.md`. Its verdict was DO NOT SHIP, on R35 (Medium).
- **Reviewer:** independent. No PR was opened. Nothing was pushed to `claude/repository-setup-nc9x6o`.
- **Date:** 2026-11-01 (UTC).

## Verdict: **SHIP**

R35, the blocker, is closed. I found nothing at Medium or above. Three new findings are recorded below, all Low or Info:

- **R40 (Low).** A size-halt incident folded as a duplicate takes its failed releases out of the lift's permanent withholding.
- **R41 (Low).** `products.builder.build` shares catalogue `Seam` objects between builds.
- **R42 (Info).** The comment says "SQLite serialises writers", but with pysqlite's lazy BEGIN that is not true.

None of them blocks shipping. I recommend fixing R40 in the next delta, because it fails open and the fix is small.

| ID | Sev | Subject | Status at c99dde9 |
|---|---|---|---|
| R35 | Medium | lift evidence ignored releases measured wrong by resolved halts | **closed** (§1) |
| R36 | Low | lift vs repeat-failure race | **closed for an existing row**; an insert race remains when no row exists yet (→ R40) |
| R37 | Info | sample without digest skipped R31 | **closed** |
| R38 | Info | R31 digest set was this incident's only | **closed** |
| R39 | Low | `texture.py` shared `Gauge` | **closed**; sweep found one more aliasing site (R41) |
| **R40** | **Low** | `close_duplicates` folds a size halt without its `measured_releases`; the lift then never withholds them | **new, open, does not block** |
| **R41** | **Low** | `builder.build` passes catalogue `Seam` instances into every CIR | **new, open, does not block** |
| **R42** | Info | "SQLite serialises writers" is not true under pysqlite's lazy BEGIN; SQLite is dev/test only | **new, does not block** |

## 1. R35: closed across incident lifetimes and orderings

`failed_releases_ever(s, slug)` unions three records:

1. durable `gate.release_withheld` rows of kind `physical_size_failed`;
2. stored `PatternVersion` withholding of that kind;
3. every `physical-size:` incident of the product, open or resolved. This includes `measured_releases`, the legacy single-release fields, `withheld_releases` and `design_digest_for_audit`.

`lift_size_halt` refuses a sample whose version or content hash matches any entry. Entries with an empty version or hash are no longer compared, so they can no longer match each other.

**Reproduction (prior P5).** I ran `test_secreview_physfix_b8d3dee_probes.py` from the prior review branch against c99dde9. Command: `PYTHONPATH=src:tests python <probe>`. P5 now prints `refused: ... (market-basket-medium@1.2.0), not a re-released version`. The author's test `test_a_release_a_resolved_halt_measured_wrong_is_never_lift_evidence` covers two cases:

- a fresh geometry under a new incident;
- the corrected release failing again under its own signature.

Both are checked with the resolved incident present and again with it deleted, so only the durable row remains.

Routes checked:

- **Pruning.** The durable rows are `lifetime_total` in `ops.retention` (line 190). `ops.retention` has no incident pruning, and the incident hygiene closes by rule but "never deletes a row". The `PatternVersion` record is PERMANENT and `carry_permanent` keeps it through re-certification. Any one of the three records is enough to refuse. Not reachable.
- **Orderings.** Covered:
  - a failure after a lift opens a fresh incident (the locked read of `resolved == False` no longer matches);
  - a lift on an older halt after a newer one opened;
  - interleaved failures and passes (prior P1, re-run, ok).
- **Version bump with identical content.** `_content_hash_of` hashes `cir.to_dict()`, which includes `version`. A relabel therefore gets a new version *and* a new hash, so neither identity check catches it. The digest check does (R31/R38): the same geometry needs `same_design_confirmed`. A restatement that moves the digest also escapes that check. This is the accepted R28/R31 design: the digest is refuse-only, the owner decides, and the evidence is still an independent full make *measured at the stated size*. This is not a finding.
- **Hash collision across versions.** The hash is SHA-256 over the CIR (which includes the version) and the US text. A collision is not practical.
- **LIKE on the slug.** `AuditLog.artifact.like(f"{slug}@%")` treats `_` in a slug as a wildcard. That can only add refusals, so it fails closed. Info, no action.

**Residual (R40).** R35 reads the *evidence* refusal from every record. The *permanent withholding* still covers only the releases of the incident being lifted (`for r in failed`). Every other route that resolves a size halt therefore leaves its releases unwithheld. See §2.

## 2. R40 (Low): a duplicate-folded size halt loses its withholding

**Defect.** `ops.incident_lifecycle.close_duplicates` runs on every `ops.health` sweep (`hygiene` → `ops.truth`). When it finds two open rows with one signature, it keeps the oldest and resolves the others. It folds `report_count` only, not `detail.measured_releases`.

`lift_size_halt` withholds only `measured_releases(inc.detail)` of the kept row. So a release measured wrong under the folded duplicate is:

- refused as lift evidence, which is correct (R35 reads resolved incidents);
- **never permanently withheld**: once the kept row is lifted, no open halt holds the product and `for_publish` shows no size withholding for that release.

**How a duplicate arises.** R36's `SELECT ... FOR UPDATE` in `_halt_release_on_size` locks the open row *if one exists*. When none exists, two concurrent first failures of one design (one signature) both read nothing. Both then insert through `open_or_restate`. No unique constraint exists on open signatures (`Incident.signature` is only indexed).

Production runs on PostgreSQL with a worker thread pool (`app/runner.py`, `worker_threads()`). Two `physical.record` jobs enqueued together, for example two testers' sheets entered back to back, can overlap. The window is the short halt transaction, so this is unlikely but reachable.

**Reproduction.** Script: `research/final_build/w4/secreview_c99dde9_probe_dup.py`. It inserts the row that the race would insert, because SQLite cannot reproduce the race itself. Run `cd brambleloop && PYTHONPATH=src:tests python research/final_build/w4/secreview_c99dde9_probe_dup.py`. Output at c99dde9:

```
hygiene: [{'id': 2, 'duplicate_of': 1, 'signature': 'physical-size:market-basket-medium:0552640f6964c73e'}]
lift withheld: ['market-basket-medium@1.2.0']
open size halts: []
A  for_publish size-withheld: ['release withheld (physical size): ... 1.2.0 ...']
A2 for_publish size-withheld: []          <-- A2 (1.2.9) was measured wrong; not withheld
```

A2 is still blocked by unrelated first-customer gates in the fixture, and a fresh independent pass of A2 is needed to clear `gauge_and_size_claims`. So exploiting this needs more than the race. But the guarantee "a release measured wrong never publishes again" does not hold on this route.

**Why Low.** It needs a concurrent first-failure race on one signature plus a hygiene sweep. Other gates still stand. It is also outside the delta's stated scope: R36 only claimed the existing-row race.

**Fix.** Any one of these closes it:

- (a) In `lift_size_halt`, withhold every versioned release in `failed + others` that is not already withheld, rather than `failed` only. This is the most general fix and covers any future resolve route.
- (b) In `_halt_release_on_size`, take `pg_advisory_xact_lock(hash(signature))` before the read.
- (c) Make `close_duplicates` merge `measured_releases` for `physical-size:` rows.

I recommend (a), plus a regression test from the probe.

## 3. R36 locking

- **PostgreSQL, existing row.** Correct.
  - Halt first, lift waits: when the lock is granted, PostgreSQL re-reads the row and returns the halt's appended `measured_releases`. They are in `failed` and get withheld.
  - Lift first, halt waits: the re-check of `resolved == False` excludes the now-resolved row. The halt opens a fresh incident, which keeps the product halted.

  Both orderings fail closed.
- **PostgreSQL, no row yet.** `FOR UPDATE` locks nothing, so the insert race remains → R40.
- **SQLite.** SQLAlchemy drops `FOR UPDATE` on SQLite. pysqlite does not emit BEGIN until the first DML statement, so the SELECT runs outside the write transaction. "SQLite serialises writers" therefore does not protect the read-then-append (R42, Info). Production is PostgreSQL (BUILD_STATE: Railway Postgres), so this affects dev and test only. Fix: emit `BEGIN IMMEDIATE` as `_serialise_owner_queue` does, or correct the comment.
- **Deadlock with `_serialise_owner_queue`.** None.
  - Neither the lift transaction nor the halt transaction takes the owner-queue advisory lock. It is taken only in `launch.readiness` and `etsy_ops`. `_route_conflict_to_owner` and `_route_partial_to_owner` run in their own later sessions.
  - Lock order in the lift is Incident row → `PatternVersion` UPDATEs → AuditLog INSERTs. The halt takes only the Incident row.
  - No other code takes `FOR UPDATE` on `Incident`. Hygiene's unlocked UPDATEs touch only incidents.

  There is no cycle, and PostgreSQL deadlock detection would roll back (fail closed) anyway.

## 4. R37–R39 and the `products/` sweep

- **R37.** `same_geometry = not sample_digest or sample_digest in digests`. A sample with no digest needs `same_design_confirmed`, and the refusal text says why. The display in `handle_physical_record` uses the same rule. Closed.
- **R38.** The digest set is `design_digest_for_audit` of this incident plus every `design_digest` in `failed + others`, which covers every lifetime. The prior P2 note now prints `same_geometry: True`. Closed.
- **R39.** `texture.py`'s three builders use `replace(CHUNKY|WORSTED)` and `dict(vars(...))`. The author's test edits a built gauge and rebuilds. Closed.
- **Sweep.** Script: `research/final_build/w4/secreview_c99dde9_share_sweep.py`. It builds every product builder twice: 35 CIR builders from `launch0.BUILDERS` and `PROPOSED_BUILDERS`, `moment_candidates.ENGINEERED`, `pipeline_board.CREATIVE_ENGINEERED` and every `build*` in `vessels`, `texture`, `nordic_forest` and `builder`. It also covers `builder.build` over all 11 `CATALOGUE` designs and the two garments' `build_all()`. It walks every dict, list and dataclass and reports any object shared between the two builds. Result: **one** shared object.
  - **R41 (Low).** `builder.build(CATALOGUE["cottage-wall-hanging"])` returns `cir.assembly[0]`, which *is* the `Seam` in the module-level `Design.assembly` tuple (`builder.py:257`, `assembly=list(design.assembly)` copies the list, not the seams). `Seam` is a mutable `@dataclass`. An in-place edit of a built CIR's seam (for example `edge_b`) would change `CATALOGUE` and every later build of that product. I found no in-place seam write in `src/`, so this is latent, like R32 and R39 were.
    - Reproduction: `python -c "import sys; sys.path.insert(0,'src'); from brambleloop.products import builder as b; d=b.CATALOGUE['cottage-wall-hanging']; print(b.build(d).assembly[0] is d.assembly[0])"` prints `True`.
    - Fix: `assembly=[replace(x) for x in design.assembly]`.

## 5. Whole branch (`origin/claude/w4-INTEG8-next...origin/claude/w4-PHYSFIX-PHOTO`)

The delta since b8d3dee changes only the four files above. The prior review swept the rest of the branch and found nothing at Medium or above except R35, which is now closed. In this delta's area I found R40–R42 (Low, Low, Info). **Nothing at Medium or above remains, and nothing blocks shipping.**

## 6. Test runs

The runs were made one at a time with `cd brambleloop && PYTHONPATH=src:tests nice -n 19 python tests/<f>.py` on a 4-CPU container. Nothing else was running.

| Suite | rc | Time | Result |
|---|---|---|---|
| test_physfix | 0 | 78s | 46/46 passed |
| test_physfix_size_lift_http | 0 | 4s | 1/1 passed |
| test_secreview_physfix_adversarial | 0 | 9s | 12/12 passed |
| test_secreview_physfix_42eac69_probes | 0 | 8s | 8/8 passed |
| test_secreview_physfix_89eef1e_probes | 0 | 4s | 8/8 passed |
| test_texture | 0 | 8s | all OK |
| test_products_adversarial | 0 | 0s | all OK |
| test_risk_matrix | 0 | 99s | all OK |
| test_physfix_photo_first | 0 | 6s | 8/8 passed |
| test_w4_launchfix | 0 | 23s | 32 passed, 0 failed |
| test_vacuity | 0 | 8s | all OK |
| test_first_customer_gate | 0 | 15s | 12 passing, 0 failing |
| test_w4_b2gates | 0 | 90s | 12/12 passing |
| test_w4_resume_runner, run 1 | 0 | 139s | all OK; p09_a 7.9s |
| test_w4_resume_runner, run 2 | 0 | 128s | all OK; p09_a 7.9s |
| test_w4_resume_runner, run 3 | 0 | 126s | all OK; p09_a 8.0s |
| test_w4_resume_runner, run 4 | 0 | 127s | all OK; p09_a 8.1s |
| test_w4_resume_runner, run 5 | 0 | 128s | all OK; p09_a 8.7s |

I also re-ran the prior review's `test_secreview_physfix_b8d3dee_probes.py` against c99dde9. P1–P5 were all ok, and P5 is now refused (§1).

The 89eef1e probe file needed the repo's `requirements.txt` installed first. The container started without `sqlalchemy` or `fastapi`, and those first attempts were discarded. They are not counted above.

### 6.1 The flaky timing test: `test_p09_a_finalize_failure_fails_the_run_and_never_fails_open`

**Unloaded:** 5/5 passed, 7.9–8.7s each. Under the load I then added, it failed.

**Under load:** 12 busy-loop processes at nice 0 on 4 CPUs, with the test at `nice -n 19`. The first solo run of `tests/test_w4_resume_runner.py test_p09_a` failed:

```
FAIL test_p09_a_finalize_failure_fails_the_run_and_never_fails_open
     TimeoutExpired(['bash', '.../rf-p09-.../repo/run_tests.sh'], 300)
```

**Mechanism.** `_p09` builds a box with `n_filler=100` synthetic suites and runs them with `JOBS=4`. It SIGKILLs the first segment a fixed `time.sleep(1.0)` after `gate.started`. It then runs the resume segment with a hard `subprocess.run(..., timeout=300)`. The resume segment re-runs or verifies about 100 suites through `run_tests.sh` and `suite_checkpoint.py`. At about 8s of CPU unloaded, a CPU share of roughly 1/40 or less exceeds 300s. A nice-19 process competing with a loaded host easily gets that little.

**Does it fail open?** No. The failure is a timeout raised by the test harness. No assertion reaches a passing state on a wrong record, and the runner's guarantee being tested (finalize failure ⇒ run failed, never eligible) is not contradicted.

**Could it break a full certification run?** **Yes: it is load-sensitive enough to turn a certification run red under heavy concurrent load**, such as several suites or reviewer sessions sharing the box, especially when run at nice 19 as here. It cannot make a run falsely green. In a full run it is one of the longer subprocess-heavy tests, and it shares CPU with the rest of the parallel suite.

**Recommendation.** This is a test-only change.
- Scale the 300s timeout, or make it an env-overridable deadline such as `RESUME_TEST_TIMEOUT`, with a default of about 900s.
- Cut `n_filler` from 100 to about 20. The test needs only enough fillers that some complete before the kill.
- Optionally, wait for a filler manifest instead of the fixed 1.0s sleep.

Severity: Info (test reliability). It is not a product defect.

## 7. Reproduction artefacts (this branch)

- `research/final_build/w4/secreview_c99dde9_probe_dup.py`: R40.
- `research/final_build/w4/secreview_c99dde9_share_sweep.py`: the `products/` aliasing sweep (R41).
- The R35 check reuses `tests/test_secreview_physfix_b8d3dee_probes.py` from `claude/w4-SECREVIEW-PHYSFIX-b8d3dee`.

## Verdict (restated)

**SHIP.** R35 is closed, and so are R36 (existing-row case), R37, R38 and R39. Remaining:

- R40 (Low): the duplicate-fold withholding gap. Fix next delta with option (a).
- R41 (Low): shared catalogue `Seam`.
- R42 (Info): SQLite lazy BEGIN comment.
- p09 timing (Info, test-only).

None is Medium or above, and none blocks shipping.
