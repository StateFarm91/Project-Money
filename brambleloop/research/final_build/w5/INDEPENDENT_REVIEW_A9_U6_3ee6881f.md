# Independent review: U6 "A9 package/event" at `codex/a9-sweep-isolation` 3ee6881f (2026-11-07)

Target: `claude/w6-INTEG1` 5913931f. Merge-base: 7c42e706. The diff is 37 files, +3661/-72.
The unit contains A1R (1dd257be, 48bc30c0, c3a7b93a) and the Codex A1 continuation up to 048449cd.

## Verdict: DO NOT SHIP

The fence logic I could exercise fails closed for ORM writes. Even so, the unit cannot ship as it stands:

1. **The A9 tests are red, or invisible to the suite gate.**
   - The unit's own `test_opus2_listing_package` fails 2 tests at 3ee6881f, both on the head alone and on the trial merge.
   - 9 of the 15 new test files produce no `^OK` line under `run_tests.sh`. That is because they import pytest (which is not installed) or have no `__main__` runner, or print `PASS`/`11/11 passed` instead of `OK`.
   - The harness counts a suite with no OK line as failed (`nopass`, run_tests.sh:604), so a full run of the merged tree would report about 10 failing suites.
2. **The record-time source re-verification has no test.** A combined mutant removes all four content checks, and it survives every A9 suite. A probe shows that the mutant raises an owner review for listing copy that changed after assembly.
3. **The A1 HIGH carry-over is still present.** Infant-only product nouns are not recognised as child-audience words (`launch0.py:1677`). Mutants N6 and N10 still survive.
4. **The authors themselves say "Do not integrate as a complete A9 fence".** See CODEX_A9_EVENT_RELEASE_HANDOFF.md and DEFER_STATE_HANDOFF.md. The gaps they name are PostgreSQL interleavings, bulk/Core SQL, gallery/PDF/policy writers, and post-commit evidence changes. All of them are confirmed below.

**Separable shippable subset: none today.** The A9 work that does not depend on A1 is 6ee81c19 + #38 (28a7befd). #38 is DO NOT INTEGRATE alone, and it has the post-commit staleness that the later commits fix. Every later A9 commit (f31ff087 onward) sits on the A1 merges and calls A1 code (see the A1 dependency section).

## A1 dependency analysis

| Earlier A1 finding (INDEPENDENT_REVIEW_A1_FULL.md) | In U6? | Evidence |
|---|---|---|
| F1 HIGH: `test_childrens` 7 failures | **Not present.** The cause is the whole-toy hold from leaf 2af2a48e, which U6 does not contain. | `test_childrens`: 40/40 OK on the trial merge |
| F2 HIGH: `test_codex_a1_hard_eyes` 4 failures | **Not present.** The file and its leaves (2af2a48e, 4800b597) are not in U6. | the file is absent from the diff |
| F3 HIGH: baby-item vocabulary gap (`CHILD_AUDIENCE_WORDS`, now `launch0.py:1677`; it was :1697 in the A1-full tree) | **PRESENT** | probe P2: `child_words_in_listing` returns `()` for "Pacifier Clip", "Teething Ring", "Rattle", "Bib", "Binky Leash", "Stroller Blanket", "Toy", "Plushie", "Doll", "12M Hat". "Baby Rattle" is caught only by "baby". |
| F5 MED: N6 / N10 fail-closed branches untested | **PRESENT** | N6 (`launch0.py:1552` `return []`) and N10 (`small_parts.py:97` `return []`) both SURVIVE all 6 A1 suites (5 codex_a1 + a1r core) |
| F4 MED: vacuous UNKNOWN-band test | Probably not applicable. U6's `small_parts.blocking` still drops CLEAR pieces (`verdict != CLEAR`), and 7e54c330 is not in U6. | Not mutated, so this is UNKNOWN |
| F6 LOW: Codex `__main__` subsets | Partly. All 5 codex_a1 files in U6 run every test they define, but they print `PASS`, not `OK`, so they are nopass under the harness. | plain runs below |

**Is A1R separable from A9?** Not at this head.
- `publish/listing_package.py` `_identity` calls `launch0.childrens_decision_for(...)` (A1R).
- `assemble` calls `launch0.child_words_in_listing`, `ASSIGNED` and `UNDECIDED` (Codex A1 d1d3e899/4a827584).
- `eligibility.name_truth` and `release.handle_listing_seo` use the A1 assignment binding.
- `runtime/release.py` `_childrens_hold` / `handle_assets_build_with_successor` and `publish/pdf.py` are A1R.

To ship A9 without A1 you would have to rebuild A9 commits 951f777c..3ee6881f on 28a7befd and drop the child-audience lines from `assemble` and `_identity`. That is rework, not a cherry-pick. The recommended order is to land the A1 unit first, with F3/N6/N10 fixed, and then re-review U6 as a delta on it.

## Findings

**H1 HIGH: the unit's own listing-package suite is red. `test_opus2_listing_package`: 2 failed / 12 OK. Reproduced on 3ee6881f alone and on the trial merge.**
- `tests/test_opus2_listing_package.py:235` (a3) asserts `review_withdrawn is True` on the second `record()`. The new ORM fence already superseded the old request when the release hash was edited. A diagnostic showed `dddd…` superseded by the fence, then `eeee…` raised. The behaviour is safe; the assertion is stale.
- `:371` (l51) expects the parked request to be superseded on a new fingerprint. The rendered owner question is byte-identical (`render()` equal), so the new `same_parked` rule keeps the parked decision. That matches the new `test_deferred_same_value_is_not_a_new_owner_question`, so the assertion is stale.
- Fix: update both assertions to the new semantics. In a3, assert that the fence withdrew the old request. In l51, change rendered content so a new question exists, and keep a second case where an identical render stays parked.

**H2 HIGH: most A9/A1 test evidence never reaches the suite gate.**
- pytest is not in venv-integ4 or in requirements-test.lock.
- `test_codex_a9_defer_state`, `_defer_state_pg`, `_event_scope` and `_sweep_isolation` (inner `import pytest`, lines 88/115), and `_event_release` (which imports `_event_scope`), die on import with ModuleNotFoundError.
- `test_codex_a9_owner_action_fence`, `_parked_source_change` and `_sweep_isolation` have no `__main__` block, so they exit 0 having run nothing.
- `test_codex_a9_source_binding` prints `11/11 passed`, and the 5 codex_a1 files print `PASS …`. None of them emits `^OK`.
- Only `test_w5_a9_package_event` is listed in `suite_final_segment.txt`.
- Under run_tests.sh these are 4 crashes plus 6 nopass suites, all counted as failures, and their assertions contribute nothing visible.
- Fix: add `__main__` runners that print `OK name`, drop pytest (use a small local `raises`/parametrize, as other suites do), and verify on a full checkpointed run.
- With a pytest shim I wrote (scratchpad), all of these pass: 4 + 16 + 3 + 6 + 14 + 5 = 48 OK; `_pg` 1 SKIP (no PostgreSQL).

**M1 MED-HIGH: the record-time source re-verification is unguarded by tests (mutant RX survives). Removing it is a demonstrated fail-open.**
- Where: `publish/listing_package.py` `record()`, the READY check. It checks `pv.certificate.granted`, `digest != expected_digest`, the emitted copy against the stored copy, and `_release_source_digest(...) != source_snapshot_sha256`.
- Each check survives on its own (R1, R2, R3, R6), because the checks overlap one another. All four removed together (RX) also SURVIVE all 5 A9 suites.
- The tests reach these races only through the ORM fence and the fingerprint STALE check (R4, which is killed).
- Probe `a9u6_rxprobe.py`: assemble, then a bulk `UPDATE listings SET title='Baby Teether Clip'`, then `record()`.
  - Original code: `blocked, retry, 0 open`.
  - RX: `ready_for_owner_review, review_requested=True, 1 open`. The owner is asked to review copy that is not the listing.
- The code is correct today. Nothing stops a refactor from deleting the only defence against non-ORM writers.
- Fix: add the probe as a test, with one case per source (copy, certificate, CIR, release).

**M2 MED: the fence covers only ORM `before_flush`. Bulk, Core and raw SQL, and every non-ORM evidence writer, leave a committed review open with stale content. This is the post-commit staleness, confirmed.**
- Probes P1, P1b, P1c and P1d all leave `open_requests=1, package_state=ready_for_owner_review`:
  - `update(Listing).values(title=…)`
  - raw `UPDATE listings`
  - `update(PatternVersion).values(certified=False)`
  - `delete(Listing)`
- P1e (`flag_modified` on `cir_json`) is caught.
- Today, no src code issues bulk writes to listings, pattern_versions or products (grep). So this is latent, and the docstring at `listing_package_fence.py:1-5` admits it.
- Gallery, `listing_assets`, `listing_set_certificates`, PDF artefacts, withholding and policy writers are not fenced at all, so a package's gallery or PDF can change under an open request until the 6-hourly sweep.
- This matches the evidence-writer map (CODEX_BATCH6_EVIDENCE_WRITER_MAP.md rows 1-3): the fence is not the shared evidence fence.
- Impact is bounded: a `listing_package:` owner action grants no authority. The command center offers only `owner_action.defer` for it. Publication and activation need a separate sealed grant that binds the content (approvals.py ACTIONS), and nothing reads a satisfied listing-package request. So stale or other-release evidence cannot authorise anything, but the owner can be shown a question that no longer matches the listing.

**M3 MED (UNKNOWN): the PostgreSQL semantics are unverified.**
- `listing_package_fence.py:64-71`: on PostgreSQL, any ORM change to a Listing, PatternVersion or Product while *another* transaction holds `OWNER_QUEUE_LOCK` raises `TransientError` (try-lock, which avoids the queue→row-lock deadlock).
- Many handlers hold that lock (`_serialise_owner_queue`, `owner_queue_guard`). Every listing, certify or product write that overlaps them fails and must be retried by its caller.
- Non-job writers, such as command-center actions or scripts, get a hard error.
- Mutant F8 (busy lock proceeds unlocked) is untestable on SQLite and SURVIVES.
- `test_codex_a9_defer_state_pg` needs a disposable loopback PostgreSQL, so it SKIPs.
- The handoff claims one precommit PG pass; I did not reproduce it. UNKNOWN is not PASS.

**M4 MED: a single poison release fails every sweep job.**
- `listing_package_ops.py:47-49` raises `RuntimeError` when any result has `retry`. `_package_one` returns `retry` for any exception in assemble or record.
- One release whose assembly fails deterministically therefore makes every 6-hourly sweep job fail, retry and dead-letter. Other releases still commit per release (E4 is killed, so isolation works), but the sweep's audit row is never written, and the job never reports done.
- Fix: retry only the failing releases, for example through per-release events, or cap the retries and record a named hold.

**L1 LOW: an empty `release` makes the event unbound.**
- `listing_package_ops.py:27-28` accepts `release` missing or `""`, and `_package_one` binds only when it is non-empty. Behaviour is then sweep-equivalent for one slug@version, and `record()` still re-verifies under the lock, so this is defence in depth only.
- A non-hex `release` is not validated, but any non-empty mismatch is refused.

**L2 LOW: `record()` with more than one parked question is untested (R7 SURVIVES).**
- The `len(parked) != 1` refuse branch at listing_package.py (record, "multiple parked review questions") has no test.

**L3 LOW: other surviving mutants.**
- D1: the `if row.done: raise` in `approvals.py` defer SURVIVES. A done row with a closed state is still refused by `state != PARKED`, so only a legacy done+`open`/`parked` row depends on it, and that case is untested.
- F7 (`prior is None` treated as no change): this path is reachable only when the row disappears concurrently, and it is untested.

**L4 LOW: an UNKNOWN children's decision in the identity does not by itself block READY.**
- `_identity` stores `"UNKNOWN: …"`, but `assemble` adds a blocker only when the listing copy has child words.
- It is held in practice by `release_gates.for_publish` → `eligibility.name_truth` and the PDF refusal, but the package can display "Children's decision: UNKNOWN" next to READY.

**INFO**
- Thresholds: no relaxation found in the diff.
- Etsy: no publishing. The job is class B and returns `publishes: False`.
- Paid providers: none touched. The V0 gate suite passes, 52 OK.
- Laura canonical: the diff contains no `laura` references.
- `period_key` widened to 200: PostgreSQL depends on `core.migrate.widen` at boot, which uses a 5 s lock_timeout and retries on the next boot.

## Trial merge and conflict recipe

```
git fetch origin codex/a9-sweep-isolation claude/w6-INTEG1 claude/w4-INTEG8-next
git -C /home/user/Project-Money worktree add /home/user/bl-runs/wt-rv-a9 origin/claude/w6-INTEG1   # 5913931f
cd /home/user/bl-runs/wt-rv-a9 && git merge --no-commit --no-ff 3ee6881f
# CONFLICT COORDINATION.json (one hunk in the claims array): HEAD adds CODEX-A7-FRESHNESS-FIX;
#   theirs adds CODEX-A9-PACKAGE-RACE, OPUS2-A1R-CHILD-SAFETY-CORE, CODEX-A1-STUFFING-EVIDENCE,
#   CODEX-A9-PARKED-MATERIAL-CHANGE, ... Resolution: union. Keep the HEAD object, close it with "}," then open "{"
#   and append theirs. json.load validates.
# CONFLICT brambleloop/scripts/suite_final_segment.txt (tail): union. Keep HEAD's 6 lines
#   (secret_leak_escalate, a7_supply_stall, support_defect_incident, v0_paid_provider_gate,
#   governor_invalid_cost, codex_v0_postgres), then append tests/test_w5_a9_package_event.py.
# core/db.py and runtime/release.py auto-merge; both py_compile.
```
Exactly 2 conflicts, both bookkeeping, matching the map. No source conflicts. The worktree was removed after the review.

## Tests (trial merge, venv-integ4, from brambleloop/, PYTHONPATH=src:tests, run as plain scripts)

| Suite | Plain script (harness view) | Assertions (pytest shim) |
|---|---|---|
| test_codex_a9_defer_state | exit 1, ModuleNotFoundError pytest | 4/4 OK |
| test_codex_a9_defer_state_pg | exit 1, pytest | 1 SKIP (no PostgreSQL): UNKNOWN |
| test_codex_a9_event_scope | exit 1, pytest | 16/16 OK |
| test_codex_a9_event_release | exit 1 (imports event_scope) | 3/3 OK |
| test_codex_a9_owner_action_fence | exit 0, **0 tests run** (no `__main__`) | 6/6 OK |
| test_codex_a9_parked_source_change | exit 0, **0 tests run** | 14/14 OK |
| test_codex_a9_sweep_isolation | exit 0, **0 tests run** | 5/5 OK |
| test_codex_a9_source_binding | exit 0, "11/11 passed", 0 `OK` (nopass) | 11/11 |
| test_w5_a9_package_event | **8 OK** (521 s) | — |
| test_opus2_listing_package | **12 OK, 2 FAIL** (a3, l51; also FAIL at 3ee6881f alone) | — |
| test_codex_a1_assignment_content / child_title / listing_child / small_parts_finite / stuffing_evidence | exit 0, `PASS` lines, 0 `OK` (nopass) | 1/1/3/2/2 pass |
| test_a1r_child_safety_core | 12 OK | — |
| test_childrens | 40 OK, 0 FAIL | — |
| test_w5_v0_paid_provider_gate | 52 OK | — |
| test_w6_fix_only_rebuild | 14 OK | — |
| test_w6_support_defect_incident | 27 OK | — |

## Mutants (one copy in /home/user/bl-runs/mut-a9u6, deleted at the end; pytest shim, fail-fast)

The 2 baseline-red opus2 tests were deselected. The first pass "kills" of R1-R4 by those red tests were invalid and were re-run.

| ID | Mutation | Result |
|---|---|---|
| F1 | fence never invalidates | KILLED (owner_action_fence) |
| F2 | content change never supersedes parked | KILLED (parked_source_change) |
| F3 | old listing identity not read | KILLED |
| F4 | product rename ignored | KILLED |
| F5 | new listing always "material" | KILLED |
| F6 | new listing never "material" | KILLED |
| F7 | missing prior row not a change | **SURVIVED** (L3) |
| F8 | PG busy fence proceeds unlocked | **SURVIVED** (PostgreSQL only: UNKNOWN, M3) |
| R1 | listing digest check dropped | SURVIVED (redundant with R2) |
| R2 | source snapshot check dropped | SURVIVED (redundant with R1) |
| R3 | certificate `granted` check dropped | SURVIVED |
| R6 | emitted copy vs stored check dropped | SURVIVED |
| **RX** | R1+R2+R3+R6 together | **SURVIVED; real fail-open, shown by probe (M1)** |
| R4 | stale fingerprint check dropped | KILLED (w5_a9_package_event) |
| R5 | durable markdown failure allowed | KILLED (source_binding) |
| R7 | multiple parked tolerated | **SURVIVED** (L2) |
| R8 | unknown parked identity tolerated | KILLED |
| E1 | event release binding dropped | KILLED (event_release) |
| E2 | any dict treated as a sweep | KILLED (event_scope) |
| E3 | retry not raised | KILLED (sweep_isolation) |
| E4 | sweep stops at first failure | KILLED |
| E5 | `_try` swallows LeaseLost | KILLED |
| E6 | ineligible reconcile skipped in sweep | KILLED |
| D1 | closed action deferrable | **SURVIVED** (L3) |
| D2 | defer without owner-queue lock | KILLED (defer_state) |
| C1 | package ignores listing child words | KILLED (codex_a1_listing_child) |
| N6 | unreadable construction returns [] (A1) | **SURVIVED** |
| N10 | small_parts exception returns [] (A1) | **SURVIVED** |

## Required before re-review
1. Fix H1: update the two stale assertions in `test_opus2_listing_package`.
2. Fix H2: OK-emitting `__main__` runners for all 15 files, with no pytest dependency.
3. Add RX, R7, D1, N6 and N10 killer tests.
4. Fix A1 F3 (infant nouns), in the A1 unit.
5. Run on real PostgreSQL: the fence try-lock, defer and record interleavings.
6. Decide on M4, the poison-release sweep failure.
7. Then rebase U6 on the integrated A1 unit and run a full checkpointed suite.

Artifacts are in /tmp/claude-0/-home-user-Project-Money/0aa334b9-5ba9-5fd2-9058-e50b4b8604ea/scratchpad/a9u6/ :
- `run_shim.py`, `shim/pytest.py`, `a9u6_one.py` (runners)
- `a9u6_mutants.py`, `a9u6_mutants.jsonl`, `a9u6_mutants_pass1.jsonl` (mutants)
- `a9u6_probes.py`, `a9u6_rxprobe.py`, `a9u6_diag*.py` (probes and diagnostics)
- `logs/` (run logs)
