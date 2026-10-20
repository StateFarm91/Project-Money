# Independent security review: release candidate 6b25eb0

**VERDICT: NO BLOCKER.** M1 is fixed, I7 and I8 are fixed, and moving the live taxonomy
verifier out of the suite weakens no gate. The range adds no BLOCKER, HIGH or MEDIUM. Across
the whole range `b931d17..6b25eb0`, taking the two earlier reviews into account, no BLOCKER
remains.

New findings: **I12-I15 INFO** only. Status: **M1 FIXED, I7 FIXED, I8 FIXED**, I9 and I10 OPEN
(unchanged), I11 PARTIAL.

Reviewer: W-SECREVIEW6. I am independent and wrote none of the code reviewed, including the
fixes. Date: 2026-10-20 (UTC). The review was read-only: nothing was deployed, no request was
sent to production, nothing was spent, and no credential was read or printed.

## Scope

- Production: `b931d17a738d6a5bcd96580f620069b669ca5f57`
- Earlier reviews: `INDEPENDENT_SECREVIEW_7f6dbe8.md` (B1 BLOCKER) and
  `INDEPENDENT_SECREVIEW_17bc373.md` (NO BLOCKER; M1 MEDIUM, I7-I11 INFO).
- Candidate: `6b25eb07453ee5896ca9c6ad396fa90099d522af` (branch `claude/final-candidate-6b25eb0`).
- Diff: `git diff 17bc373e 6b25eb07 -- brambleloop/src brambleloop/tests ops
  brambleloop/requirements.lock brambleloop/Dockerfile`. The code changes are in
  `experiments/controlled.py` (+44), `app/main.py` (+4/−2) and `gateway/credentials.py` (+7/−1),
  plus tests. `ops/`, `requirements.lock` and `Dockerfile` do not change in the range.
- Data files: `core/decision_index.json` (3 new decision ids → integer counts) and
  `build2/final_master_closure.json` are plain JSON. In `final_master_closure.json` the only
  change is `rows[838..839].overridden` going from `[]` to `["evidence","tests"]` for F-852 and
  F-853, which mirrors the `research/final_build/overrides.json` records from d81dd4e. Both rows
  were already COMPLETE/INTEGRATED. These are records only, with no executable content. The
  generated board snapshot was ignored.

## (1) Is M1 closed? **Yes. M1 is FIXED.**

### The fix

The fix is `experiments/controlled.py:480-490` together with `_settle_if_any_paid_call`
(`:562-592`). It runs after the existing no-scope branch (`:468-479`). So this code is reached
only when the run is `running` under this same `job_id`, `attempts > 0`, no image is stored, and
the paid-call scope is this job. In that case it reads every `paid_call_records` row for the
job:

- If every row is DECLINED (or there are no rows), it returns `None` and the loop proceeds.
  Nothing was billed and nothing is in flight. The guard writes its PENDING record before
  `call()`, so any request that reached the provider has a row.
- Any other outcome (PENDING, UNCERTAIN, OK, FAILED_BILLED) settles the run as `failed` and
  **sends nothing**. Billing is reported as `billed` when every row is OK, FAILED_BILLED or
  DECLINED, and as `unknown` otherwise.
- A PENDING row is counted through the guard's own `PC._count_orphan`. That function writes one
  `CostEntry` at the reservation estimate, releases the gateway reservation at that amount, and
  sets the row to `orphan_billed=True, outcome=UNCERTAIN`. Its `if row.orphan_billed: return`
  makes it idempotent.
- Any exception (unreadable table, failed query, failed count) is caught and the run settles
  with billing `unknown`. Nothing is resent.

Prerequisites I checked:

- Every worker execution runs inside the scope. `runtime/worker.py:430` opens
  `attributed_to(job_product(...))`, which opens `paid_calls.job_scope` (`finance/spend_report.py:89`).
  Because the first execution was guarded too, "no row" really means "nothing was sent".
- `experiments/controlled.py` does not exist in production `b931d17`. No unguarded legacy run
  can be resumed by this code.

### Probe: every outcome, on both backends

The probe (not committed) uses the candidate's own harness (`test_w4_credhealth._claimed_run`,
the BFL stand-in from `test_w4_controlled_experiments.Transport`), with outbound sockets disabled
except to a local database. For each case it seeds `paid_call_records` for the claimed job, sets
the run to `running` with `attempts=N`, and calls `run_job` inside `job_scope`.

| Earlier paid calls of the job | New provider posts | Settled | Run | Orphan `CostEntry` rows | Row after |
|---|---|---|---|---|---|
| DECLINED, PENDING (the M1 path) | **0** | `billing_unknown` | failed | 0, **1** | DECLINED; UNCERTAIN, `orphan_billed` |
| PENDING | **0** | `billing_unknown` | failed | **1** | UNCERTAIN, `orphan_billed` |
| DECLINED, UNCERTAIN | **0** | `billing_unknown` | failed | 0, 0 | unchanged |
| OK (image not yet stored) | **0** | `billing_billed` | failed | 0 | unchanged (see I12) |
| DECLINED, FAILED_BILLED | **0** | `billing_billed` | failed | 0, 0 | unchanged |
| table unreadable (committed test) | **0** | `billing_unknown` | failed | n/a | n/a |
| DECLINED, DECLINED | 1 (correct: nothing billed or in flight) | none | completed | 0, 0 | unchanged |
| no rows, `attempts=1` (killed before the write-ahead) | 1 (correct) | none | completed | none | none |

Calling `_settle_if_any_paid_call` a second time on the same job left the orphan count at
**1**. So a PENDING call is counted **exactly once**: never zero (the row is counted before the
run settles) and never twice (`orphan_billed`, and the row is no longer PENDING).

I ran the table above on **SQLite** (the harness default) and on **PostgreSQL 16.x**, using a
local throwaway cluster on `127.0.0.1:55432` and `psycopg2-binary` from the candidate lock.
The results were identical on both.

### Session handling and expunge

The outer session only reads, with a plain SELECT and no row locks. `s.expunge(r)` detaches the
PENDING row before `_count_orphan` reads its already-loaded attributes. `_count_orphan` writes
through its own sessions: `spend_report.record`, `release_reservation`, and `PC._update`, which
reloads the row by primary key. The outer session never holds a dirty copy of the row, so its
commit on exit writes nothing and cannot overwrite `orphan_billed` or `outcome`.

- On PostgreSQL, the open outer read transaction takes no lock that conflicts with the inner
  UPDATE and INSERT. Each nested session uses its own pooled connection.
- On SQLite, the read has been fully consumed (`list(...)`) before the nested writes begin.

The PostgreSQL run of the probe and of the committed test confirms both.

### The test is sound and fails on 17bc373e

`tests/test_w4_integ4_resume.py` reproduces the exact M1 sequence:

- attempt 1 raises `TransientError` before acceptance, so it is DECLINED;
- attempt 2 is accepted, then the worker is killed while polling;
- the test asserts two posts and records `[DECLINED, PENDING|UNCERTAIN]`.

It then resumes in the same job scope and asserts no new post, `billing_unknown`, a failed run,
and no PENDING row left. A second test makes `ensure_table` raise.

- On `6b25eb07`: **2/2 passed** on SQLite and **2/2 passed** on PostgreSQL.
- On `17bc373e` (the file copied into a scratch worktree): **0/2 passed**.
  `test_m1_declined_then_in_flight_is_never_resent_on_resume` fails with "a resumed run resent a
  paid render while billing was unknown" (the M1 defect). `test_m1_unreadable_records_never_resend`
  fails with `KeyError: 'settled'`.
- Regression: `test_w4_credhealth.py` 13 passed and 0 failed, including the earlier
  restart-during-the-paid-call and stored-image resume tests.

## (2) I7 and I8: **both FIXED, no regression**

**I7** (`app/main.py:4955-4975`):

- `_DIGEST64` is now `([0-9a-fA-F]{12})[0-9a-fA-F]{52,}` with no look-arounds. Any hex run of 64
  or more characters keeps only its first 12 characters plus `…`. That covers a glued prefix
  (`ab<sha>`), two concatenated digests, and upper case.
- The `artifact` column now goes through the same `shorten`, which is the identity for the
  operator credential.
- The regex is linear-time: greedy, with no nested quantifiers.

Over-match check:

- Only strings containing 64 or more consecutive hex characters change. Git SHAs (40), the
  4-hex rotation marker, the 12-hex fingerprint, Etsy taxonomy ids (JSON integers, untouched),
  taxonomy names, timestamps and actors are all unaffected.
- `ops/overnight_grade.py` public mode reads only `at` and `actor`. The taxonomy verifier reads
  `detail.category_choices` and `name_evidence`, which are integers and names.
- `test_w4_overnight_grade.py` 7 passed and 0 failed. `test_w4_firstsale_taxonomy.py` 7/7
  passed. `test_w4_integ4_secfixes.py` 12/12 passed, including the new I7 test (glued digests,
  upper case, artifact column) and `test_b1_the_operator_reads_the_audit_digests_unchanged`.
- Residuals are listed under I14.

**I8** (`gateway/credentials.py:79-88`):

- The fingerprint is now `sha256(b"brambleloop-owner-key-fingerprint:v1:" + key)[:12]`, which
  is domain-separated and differs from the plain sha256 prefix (tested).
- It is still computed live and never stored. The only consumer is the owner card
  (`static/js/views/_checks.js:82`), which displays it. No code compares it with a stored value,
  so changing the domain breaks nothing.
- The 4-hex `rotation_marker` keeps its own, different domain.
- `test_w4_credhealth` still scans every log, row and response for the fingerprint: it passed.

## (3) The live verifier move: **no gate weakened**

- `run_tests.sh:143` discovers suites with `ls tests/test_*.py`, so `verify_w4_firstsale_taxonomy_live.py`
  is no longer run. Before the move, the live file's result depended on production and, by
  design, exited 3 (UNKNOWN). Inside a hermetic suite it was either a network-dependent failure
  or a vacuous pass. It was never a gate.
- The rename is 98% similar, with only the docstring "Run:" line changed. `_self_test`, `verify`
  and `check_choices` are byte-identical.
- The new `test_the_live_verifiers_own_rules_hold_offline` (`test_w4_firstsale_taxonomy.py:168`)
  loads the file by path and runs `_self_test()`. That covers CHOSEN ending at its own id, a
  missing crochet basis being refused, CONTRADICTED on a wrong path, and UNKNOWN on name-only
  evidence. Loading the module makes no network call: `fetch()` runs only under `__main__`. The
  sockets-off probe ran the suite file with this test passing.
- No acceptance-gate code, `deploy_guard.py` rule or CI workflow names the old file. The only
  remaining stale mention is a table label in `FIRSTSALE.md` (I15).

## (4) Other changes and the overall range

- `tests/test_w4_close5_rows.py` (ea23282) adds three SCRATCH registry entries
  (`flux3_generator._scratch`, `controlled.run_job`, `fidelity.read`). The test checks that each
  named caller's source contains the persisting calls it claims. Those claims are true:
  `image_production._generate` calls `store_bytes`/`record_candidate`, `run_job` stores via
  `ArtifactStore().put(..., keep=...)`, and the handler audits. `test_w4_close5_rows.py` reports
  0 failing of 8. It is test-only and does not relax any runtime check.
- F-852/F-853 override (d81dd4e) is records only (see Scope). The code it cites
  (`publish/eligibility.verified_exception`) is not in this range.
- **Overall `b931d17..6b25eb0`:**
  - B1 was closed in `17bc373e` and verified there. This range adds only further shortening on
    `/api/audit` and does not touch `api_model_tournament_image`, `tournament_image_refusal`,
    `security.py` or `core/artifacts.py`.
  - The B1 sweep (`test_w4_integ4_deliverable_routes.py`) passes **4/4** on `6b25eb07`.
  - L1-L4 stay fixed (secfixes 12/12). M1 is now fixed.
  - No new route, public endpoint, dependency, Dockerfile change or ops change.
  - **No BLOCKER remains.**

## Findings

No BLOCKER, HIGH, MEDIUM or LOW findings. All four new findings are INFO.

- **I12 (INFO): a resumed run with an OK render but no stored image discards a paid image.**
  `experiments/controlled.py:571-592`. If the worker dies after `images.generate` returns and
  before `_update(image_sha256=...)` (the read, `ArtifactStore().put` and update), the job has
  an OK row. The run then settles `failed` / `billing_billed`, and the render that was paid for
  is never judged. In 17bc373 the guard would have replayed the OK payload instead.
  - This is fail-safe: no money is lost twice, and the render's cost is already in the ledger.
    At most one image (about CA$0.14) is wasted in a millisecond window.
  - Possible fix: when the only non-DECLINED rows are OK, return `None` and let the guard replay
    them. Do this only once the occurrence mapping is made per attempt. Otherwise leave it as is,
    because it is the conservative choice.
- **I13 (INFO): no P1 incident for an orphan settled on resume.** `controlled.py:577-580`. The
  guard's `_replay` path (`gateway/paid_calls.py:432-435`) opens a `paid_call.unresolved`
  incident after counting an orphan. `_settle_if_any_paid_call` counts the orphan and fails the
  run, but opens no incident. The owner sees the failed run and its `why` ("billing unknown,
  counted, not resent"), and the cost row carries `ORPHAN_BILLING`, but there is no incident card
  for reconciliation.
  - Fix: call `PC._incident(db, r.key, r.effect, job_id, "worker lost during the call")` for
    each PENDING or UNCERTAIN row it finds.
- **I14 (INFO): I7 residuals.**
  - The `actor` column (`String(64)`) is still not shortened. No writer puts a digest there.
  - Digests in other encodings (base64, `sha256-` SRI form) pass through unchanged.
  - Neither matters for B1, because the byte route is an allowlist.
  - Note: re-exporting `visual/approval_record.json` from `GET /api/audit?action=model.frozen`
    now needs the operator credential to keep full digests. This has been the case since
    17bc373 for `detail`, and is now also the case for `artifact`.
- **I15 (INFO): stale doc label.** `research/final_build/w4/FIRSTSALE.md:391` still names
  `test_w4_firstsale_taxonomy_live` in its results table. Rename it to `verify_…`.

## Status of earlier findings

| ID | Status | Evidence |
|---|---|---|
| B1 | FIXED (17bc373; holds) | sweep 4/4 on `6b25eb07`; byte route untouched in range |
| L1-L4 | FIXED (holds) | `test_w4_integ4_secfixes.py` 12/12 |
| **M1** | **FIXED** | `controlled.py:480-592`; probe: 0 posts for every non-DECLINED outcome on SQLite and PostgreSQL; PENDING counted exactly once; new test 2/2 on candidate (both backends), 0/2 on `17bc373e` |
| **I7** | **FIXED** (residuals I14) | look-arounds dropped, 64+ hex runs shortened, `artifact` shortened; I7 test passes; overnight-grade and taxonomy tests pass |
| **I8** | **FIXED** | domain-separated `FINGERPRINT_DOMAIN`; I8 test and credhealth leak scan pass |
| I9 | OPEN (unchanged) | public `/api/audit` still shows `provider.credential_health` rows with BFL credits |
| I10 | OPEN (unchanged) | sweep fills path parameters only |
| I11 | PARTIAL | the settle entry now records `paid_call_outcomes` (the earlier attempts' guard outcomes), but `attempt_log` is still only persisted at the end of the loop, so `resume["log"]` is `[]`; the on-demand 60 s floor is still non-atomic; `candidate_gates`/`release_gates` still call the fail-open `is_experiment_image` (Etsy upload choke point is fail-closed) |
| I1-I3, I5, I6 | OPEN (unchanged) | not touched in range |
| I4 | BY DESIGN | |

## Method

1. Read both earlier reviews, then the full scoped diff `17bc373e..6b25eb07`. Read by hand:
   - `controlled.run_job` and `_settle_if_any_paid_call`;
   - `paid_calls.guarded`, `_replay`, `_count_orphan` and `ensure_table`;
   - the worker's scope entry;
   - `api_audit` and `_shorten_digests`;
   - `credentials.fingerprint` and its consumers;
   - the verifier and `run_tests.sh` discovery;
   - the consumers of `/api/audit`.
2. Set up a venv from the candidate `requirements.lock` (`--no-deps --require-hashes`, plus
   `httpx`) on Python 3.13, and made scratch worktrees at `6b25eb07` and `17bc373e`.
3. Ran these focused tests on `6b25eb07`:
   - `test_w4_integ4_resume`: 2/2, also 2/2 on PostgreSQL;
   - `test_w4_integ4_secfixes`: 12/12;
   - `test_w4_credhealth`: 13/0;
   - `test_w4_firstsale_taxonomy`: 7/7;
   - `test_w4_overnight_grade`: 7/0;
   - `test_w4_close5_rows`: 0 failing of 8;
   - `test_w4_integ4_deliverable_routes`: 4/4.

   On `17bc373e` I ran `test_w4_integ4_resume` (copied in): 0/2.
4. Ran an M1 outcome probe (table above) on SQLite and on a local throwaway PostgreSQL 16
   cluster. Sockets were disabled except to the local database. The probe is not committed.
5. Made no request to production, no deploy and no spend, and read no credential.

## Verdict

**NO BLOCKER.** M1 is closed: a resumed controlled-experiment run sends a paid render only when
every earlier paid call of the job was DECLINED. A PENDING call is counted exactly once, and
unreadable records never cause a resend. I7 and I8 hold with no regression. Moving the live
verifier keeps its offline rules in the hermetic suite and removes no gate. No BLOCKER remains
in `b931d17..6b25eb0`. I12-I15 are INFO and can follow.
